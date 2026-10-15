"""cca curl: curl with a project credential that the caller never sees (doc-1 request policy).

Every curl option passes through except a few that would send the credential somewhere
unchecked. The credential, the URL and every option value with {TOKEN} reach curl as a
config on stdin, never in argv; secrets are redacted from curl stdout and stderr and from
the files curl writes request data to.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote, quote_plus

from cca import config, secrets, validate
from cca.output import CcaError, error

USAGE = "cca curl [--cred-id ID] [CURL-OPTION...] URL"
DESCRIPTION = "curl with a credential from the project's sops file, hidden from argv and output"
EPILOG = """\
The credential is the one whose origins contain the URL's origin (https only);
--cred-id ID picks one among several. {TOKEN} in the URL or an option value is replaced
by the bearer token. Every curl option passes through except -L/--location,
--location-trusted, -K/--config, --expand-config and --expand-url; request data cannot
come from stdin (@-). Secrets are redacted from curl stdout, stderr and the files
written by --trace, --trace-ascii, --libcurl, --stderr, -D and -w %output{FILE}; -o
output is not changed.
"""

PLACEHOLDER = "{TOKEN}"
REDACTED = b"[REDACTED]"
REJECTED = {
    "location": "redirects are not followed with a credential",
    "location-trusted": "redirects are not followed with a credential",
    "config": "a curl config file can hold URLs that cannot be checked",
    "expand-url": "an expanded URL cannot be checked",
}
# options whose file receives request data (headers, auth); "-" and "%" mean stdout/stderr
TRACE_FILES = ("trace", "trace-ascii", "libcurl", "stderr", "dump-header")
OUTPUT_TEMPLATE = re.compile(r"%output\{(?:>>)?([^}]*)\}")
TO_FILE = ("output", "remote-name", "remote-name-all")
CSRF_MAX = 4 * 1024 * 1024  # bytes read from the CSRF page
CSRF_PATTERNS = (
    re.compile(r"""name=["']csrf-token["'][^>]*content=["']?([^"'>\s]+)"""),
    re.compile(r"""name=["']_token["'][^>]*value=["']?([^"'>\s]+)"""),
    re.compile(r"""content=["']?([^"'>\s]+)["']?[^>]*name=["']csrf-token["']"""),
)
_HELP_LINE = re.compile(r"\s*(?:-(\S), )?--([A-Za-z0-9][A-Za-z0-9.-]*)( <)?")
DROP_ENV = ("SSLKEYLOGFILE",)  # TLS session keys would decrypt the credential


class Options:
    """curl's option table: long name -> takes a value, short letter -> long name."""

    def __init__(self, help_text: str):
        self.takes_value: dict[str, bool] = {}
        self.short: dict[str, str] = {}
        for line in help_text.splitlines():
            m = _HELP_LINE.match(line)
            if m:
                self.takes_value[m.group(2)] = m.group(3) is not None
                if m.group(1):
                    self.short[m.group(1)] = m.group(2)
        if "url" not in self.takes_value or "config" not in self.takes_value:
            raise CcaError("cannot read curl's option table from 'curl --help all'")

    def lookup(self, name: str) -> bool | None:
        """Whether --name takes a value; None for an option curl does not have."""
        if name in self.takes_value:
            return self.takes_value[name]
        # curl accepts --no-NAME for every boolean option
        if name.startswith("no-") and self.takes_value.get(name[3:]) is False:
            return False
        # and --expand-NAME (variables expanded in the value) for every option with a value
        if name.startswith("expand-") and self.takes_value.get(name[7:]) is True:
            return True
        return None


def load_options(curl: str) -> Options:
    try:
        proc = subprocess.run(
            [curl, "--help", "all"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError as e:
        raise CcaError(f"cannot run {curl}: {e.strerror}") from None
    return Options(proc.stdout)


class Request:
    """The parsed command line: the URL, the cca options and curl options in order."""

    def __init__(self) -> None:
        self.url: str | None = None
        self.cred_id: str | None = None
        self.items: list[tuple[str, str | None]] = []  # (long name, value or None)

    def add_url(self, url: str) -> None:
        if self.url is not None:
            raise CcaError("only one URL is allowed (curl sends the credential to every URL)")
        self.url = url


def parse(argv: list[str], options: Options) -> Request:
    """Split argv as curl does: short clusters, values in the same or the next argument."""
    req = Request()
    i = 0
    end_of_options = False

    def value_after(index: int, name: str) -> str:
        if index >= len(argv):
            raise CcaError(f"option --{name} needs a value")
        return argv[index]

    while i < len(argv):
        arg = argv[i]
        i += 1
        if end_of_options or not arg.startswith("-") or arg == "-":
            req.add_url(arg)
        elif arg == "--":
            end_of_options = True
        elif arg.startswith("--"):
            name = arg[2:]
            if name == "cred-id":
                req.cred_id = value_after(i, name)
                i += 1
                continue
            takes = options.lookup(name)
            if takes is None:
                raise CcaError(f"unknown curl option '{validate.display(arg)}'")
            value = None
            if takes:
                value = value_after(i, name)
                i += 1
            req.items.append((name, value))
        else:
            for j, letter in enumerate(arg[1:], start=1):
                name = options.short.get(letter)
                if name is None:
                    raise CcaError(f"unknown curl option '-{validate.display(letter)}'")
                if options.takes_value[name]:
                    value = arg[j + 1 :]
                    if not value:
                        value = value_after(i, name)
                        i += 1
                    req.items.append((name, value))
                    break
                req.items.append((name, None))
    for name, _value in req.items:
        base = name.removeprefix("expand-")  # --expand-config is --config with variables
        if name in REJECTED or base in REJECTED:
            reason = REJECTED.get(name) or REJECTED[base]
            raise CcaError(f"--{name} is not allowed: {reason}")
    for name, value in req.items:
        if name == "url":
            req.add_url(value)
    req.items = [item for item in req.items if item[0] != "url"]
    if req.url is None:
        raise CcaError(f"no URL given (usage: {USAGE})")
    return req


def select(
    creds: dict[str, secrets.Credential], url: str, cred_id: str | None
) -> secrets.Credential:
    """doc-2 credential selection by the URL's normalized origin."""
    try:
        origin, _tail = validate.parse_https_url(url)
    except ValueError as e:
        raise CcaError(f"invalid URL: {e}") from None
    ids = ", ".join(creds)
    if cred_id is not None:
        cred = creds.get(cred_id)
        if cred is None:
            raise CcaError(f"unknown credential '{validate.display(cred_id)}' (credentials: {ids})")
        if origin not in cred.origins:
            raise CcaError(f"credential '{cred_id}' does not allow the origin of the URL")
        return cred
    matches = [cred for cred in creds.values() if origin in cred.origins]
    if not matches:
        raise CcaError(f"no credential allows the origin of the URL (credentials: {ids})")
    if len(matches) > 1:
        names = ", ".join(cred.id for cred in matches)
        raise CcaError(f"several credentials allow the origin of the URL, use --cred-id ({names})")
    return matches[0]


def quote_config(value: str) -> str:
    """A curl config value: "..." with backslash and double quote escaped."""
    if validate.has_control(value):
        raise CcaError("a value for the curl config contains a control character")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def auth_lines(cred: secrets.Credential) -> list[str]:
    if cred.bearer is not None:
        return [f"header = {quote_config('Authorization: Bearer ' + cred.bearer)}"]
    return [f"user = {quote_config(f'{cred.username}:{cred.password}')}"]


def secret_values(cred: secrets.Credential) -> list[bytes]:
    raw = [cred.bearer] if cred.bearer is not None else [cred.password]
    if cred.username is not None:
        raw.append(base64.b64encode(f"{cred.username}:{cred.password}".encode()).decode())
    forms = set()
    for value in raw:
        escaped = quote_config(value)[1:-1]  # as in the config and in --libcurl C strings
        forms.update((value, escaped, quote(value, safe=""), quote(value), quote_plus(value)))
    return [form.encode() for form in forms if form]


class Redactor:
    """Replaces secrets in a byte stream, also across chunk boundaries."""

    def __init__(self, values: list[bytes]):
        values = sorted(set(values), key=len, reverse=True)  # longest alternative first
        self.pattern = re.compile(b"|".join(re.escape(v) for v in values))
        self.keep = len(values[0]) - 1  # a match starting earlier is fully visible
        self.pending = b""

    def feed(self, data: bytes, final: bool = False) -> bytes:
        buf = self.pending + data
        safe = len(buf) if final else max(len(buf) - self.keep, 0)
        out = []
        pos = 0
        for m in self.pattern.finditer(buf):
            if m.start() >= safe:
                break
            out += [buf[pos : m.start()], REDACTED]
            pos = m.end()
        if pos < safe:
            out.append(buf[pos:safe])
            pos = safe
        self.pending = buf[pos:]
        return b"".join(out)


def _pump(source: BinaryIO, target: BinaryIO, redactor: Redactor, proc: subprocess.Popen) -> None:
    try:
        while chunk := source.read1(65536):
            target.write(redactor.feed(chunk))
            target.flush()
        target.write(redactor.feed(b"", final=True))
        target.flush()
    except OSError:  # the reader is gone (`| head`): stop curl instead of blocking it
        proc.kill()
        while source.read1(65536):
            pass
        try:  # no second broken-pipe error when Python flushes the stream at exit
            os.dup2(os.open(os.devnull, os.O_WRONLY), target.fileno())
        except (OSError, ValueError):
            pass


def written_files(items: list[tuple[str, str | None]]) -> list[Path]:
    """Files curl writes request data to, also under --output-dir."""
    names = [v for n, v in items if n in TRACE_FILES and v not in (None, "-", "%")]
    for n, v in items:
        if n == "write-out" and v is not None:
            names += [m.group(1) for m in OUTPUT_TEMPLATE.finditer(v) if m.group(1)]
    dirs = [v for n, v in items if n == "output-dir" and v]
    return [Path(name) for name in names] + [Path(d) / name for d in dirs for name in names]


def redact_file(path: Path, redactor: Redactor) -> None:
    """Rewrite a regular file in place (a symlink's target, as curl wrote it)."""
    if not path.is_file():
        return
    try:
        data = path.read_bytes()
        clean = redactor.feed(data, final=True)
        if clean != data:
            path.write_bytes(clean)
    except OSError as e:
        raise CcaError(f"cannot redact {validate.display(str(path))}: {e.strerror}") from None


def csrf_token(curl: str, head: list[str], env: dict[str, str]) -> str | None:
    """The page's CSRF token, fetched with the same credential (silent, no redirects)."""
    try:
        proc = subprocess.Popen(
            [curl, "-q", "-s", "--config", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except OSError as e:
        raise CcaError(f"cannot run {curl}: {e.strerror}") from None
    try:
        proc.stdin.write("\n".join(head).encode() + b"\n")
        proc.stdin.close()
    except OSError:
        pass
    page = proc.stdout.read(CSRF_MAX)
    proc.kill()
    proc.wait()
    text = page.decode("utf-8", errors="replace")
    for pattern in CSRF_PATTERNS:
        m = pattern.search(text)
        if m and not validate.has_control(m.group(1)):
            return m.group(1)
    return None


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Help only: cca.cli passes everything after `curl` unparsed (RAW_ARGS)."""
    parser.usage = USAGE
    parser.epilog = EPILOG
    parser.formatter_class = argparse.RawDescriptionHelpFormatter


RAW_ARGS = True


def run(args: argparse.Namespace) -> int:
    argv: list[str] = args.raw
    if argv[:1] in (["-h"], ["--help"]):
        parser = argparse.ArgumentParser(
            prog="cca curl",
            usage=USAGE,
            description=DESCRIPTION,
            epilog=EPILOG,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.print_help()
        return 0
    curl = shutil.which("curl")
    if curl is None:
        raise CcaError("curl not found on PATH")
    options = load_options(curl)
    req = parse(argv, options)
    cfg = config.require(args.config)
    cred = select(secrets.curl_credentials(cfg), req.url, req.cred_id)

    def fill(value: str) -> str:
        if PLACEHOLDER not in value:
            return value
        if cred.bearer is None:
            raise CcaError(f"{PLACEHOLDER} needs a bearer credential ('{cred.id}' has none)")
        return value.replace(PLACEHOLDER, cred.bearer)

    head = [f"url = {quote_config(fill(req.url))}", "globoff", *auth_lines(cred)]
    env = {k: v for k, v in os.environ.items() if k not in DROP_ENV}
    values = secret_values(cred)
    if cred.csrf:
        token = csrf_token(curl, head, env)
        if token is not None:
            head.append(f"header = {quote_config('X-CSRF-Token: ' + token)}")
            values.append(token.encode())
    lines = list(head)
    command = [curl, "-q", "--config", "-"]
    for name, value in req.items:
        if value is not None and PLACEHOLDER in value:
            lines.append(f"{name} = {quote_config(fill(value))}")
        else:
            command += [f"--{name}"] if value is None else [f"--{name}", value]
    names = {name for name, _value in req.items}
    # curl hides the progress meter for terminal output; its stdout is a pipe here
    if (
        sys.stdout.isatty()
        and not names & set(TO_FILE)
        and options.lookup("no-progress-meter") is False
    ):
        lines.append("no-progress-meter")
    try:
        proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
    except OSError as e:
        raise CcaError(f"cannot run {curl}: {e.strerror}") from None
    pumps = [
        threading.Thread(target=_pump, args=(source, target, Redactor(values), proc))
        for source, target in ((proc.stdout, sys.stdout.buffer), (proc.stderr, sys.stderr.buffer))
    ]
    for pump in pumps:
        pump.start()
    try:
        proc.stdin.write("\n".join(lines).encode() + b"\n")
        proc.stdin.close()
    except OSError:
        pass  # curl exited before reading its config; its own error is on stderr
    try:
        code = proc.wait()
    except KeyboardInterrupt:  # curl got the same SIGINT
        code = proc.wait()
    for pump in pumps:
        pump.join()
    status = code if code >= 0 else 128 - code
    try:
        for path in written_files(req.items):
            redact_file(path, Redactor(values))
    except CcaError as e:
        error(str(e))
        return 2
    return status
