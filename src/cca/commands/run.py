"""cca run: run a command on a configured server over tmux or ssh (doc-1 "cca run").

A thin CLI over cca.executor. The command shape is a public contract for external
validators: options only before SERVER, the command after `--` or on stdin.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from cca import config, executor, validate
from cca.output import CcaError

USAGE = """\
cca run [--timeout SEC] SERVER [-- CMD...]
       cca run [--timeout SEC] --all [-- CMD...]
       cca run [--timeout SEC] --create-file PATH SERVER
       cca run --list
       cca run --read [--lines N | --marker M | --scrollback] SERVER
       cca run --session [SERVER...]"""

DESCRIPTION = """\
Run a command on a server from [servers] of .cca.toml over the transport set in
run.transport: tmux (a visible ssh window per server in session run.tmux.session) or
ssh. Without CMD the command is read from stdin (a quoted heredoc for multiline
scripts); the remote command's stdin is /dev/null."""

EPILOG = """\
options (only before SERVER):
  --timeout SEC        wait at most SEC seconds (1-86400, default 300); exit 124
  --all                run on every server in config order, stop on the first failure
  --create-file PATH   write stdin to the absolute remote PATH atomically
  --list               configured servers: name, ssh target, tmux window state
  --read               tmux only: the visible pane, or --lines N of history,
                       --scrollback (all) or the output of --marker M (exit: the
                       command's, 124 while it still runs)
  --session            tmux only: open missing ssh windows (all servers by default)

exit status: the remote command's; 124 timeout; 130/143/129/137 when the command was
interrupted, terminated, hung up or killed; 2 usage, config or transport error.

examples:
  cca run server1 -- uptime
  cca run server1 <<'EOF'
  df -h /
  systemctl is-active nginx
  EOF
  cca run --all -- uptime
  cca run --create-file /etc/motd server1 < motd.txt
  cca run --read --marker CCA_1760000000000000000_1234 server1"""

RAW_ARGS = True
TIMEOUT_MAX = 86400
SURFACES = ("--all", "--create-file", "--list", "--read", "--session")


@dataclass
class Request:
    surface: str | None = None  # one of SURFACES, None = run on one server
    timeout: int = 300
    create_path: str | None = None
    lines: int | None = None
    marker: str | None = None
    scrollback: bool = False
    servers: list[str] = field(default_factory=list)
    command: str | None = None  # None: read from stdin


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Help only: cca.cli passes everything after `run` unparsed (RAW_ARGS)."""
    parser.usage = USAGE
    parser.epilog = EPILOG
    parser.formatter_class = argparse.RawDescriptionHelpFormatter


def _value(argv: list[str], i: int, option: str) -> str:
    if i + 1 >= len(argv):
        raise CcaError(f"{option} needs a value (usage: {USAGE})")
    return argv[i + 1]


def _number(text: str, option: str, low: int, high: int) -> int:
    if not text.isascii() or not text.isdigit() or not low <= int(text) <= high:
        raise CcaError(f"{option} must be an integer {low}-{high}")
    return int(text)


def parse(argv: list[str]) -> Request:
    req = Request()
    i = 0
    seen: set[str] = set()

    def surface(name: str) -> None:
        if req.surface is not None:
            raise CcaError(f"{req.surface} and {name} cannot be combined")
        req.surface = name

    while i < len(argv) and argv[i].startswith("-") and argv[i] != "--":
        option = argv[i]
        if option in seen:
            raise CcaError(f"{option} given twice")
        seen.add(option)
        if option == "--timeout":
            req.timeout = _number(_value(argv, i, option), option, 1, TIMEOUT_MAX)
            i += 2
        elif option == "--create-file":
            surface(option)
            req.create_path = _value(argv, i, option)
            i += 2
        elif option in ("--all", "--list", "--read", "--session"):
            surface(option)
            i += 1
        elif option == "--lines":
            req.lines = _number(_value(argv, i, option), option, 0, 10_000_000)
            i += 2
        elif option == "--marker":
            req.marker = _value(argv, i, option)
            if not executor.MARKER_RE.fullmatch(req.marker):
                raise CcaError(f"invalid marker '{validate.display(req.marker)}'")
            i += 2
        elif option == "--scrollback":
            req.scrollback = True
            i += 1
        else:
            raise CcaError(f"unknown option '{validate.display(option)}' (usage: {USAGE})")

    read_options = [o for o in ("--lines", "--marker", "--scrollback") if o in seen]
    if read_options and req.surface != "--read":
        raise CcaError(f"{read_options[0]} needs --read")
    if len(read_options) > 1:
        raise CcaError(" and ".join(read_options) + " cannot be combined")
    if "--timeout" in seen and req.surface in ("--list", "--read", "--session"):
        raise CcaError(f"--timeout does not apply to {req.surface}")

    rest = argv[i:]
    if req.surface in ("--all", None):
        if req.surface is None:
            if not rest or rest[0] == "--":
                raise CcaError(f"SERVER required (usage: {USAGE})")
            req.servers, rest = [rest[0]], rest[1:]
        if rest:
            if rest[0] != "--":
                raise CcaError(
                    f"unexpected '{validate.display(rest[0])}': options go before SERVER, "
                    "the command after --"
                )
            if len(rest) == 1:
                raise CcaError("no command after --")
            req.command = " ".join(rest[1:])  # joined like ssh joins its arguments
        return req
    if rest[:1] == ["--"] or any(a.startswith("-") for a in rest):
        raise CcaError(f"{req.surface} takes no command and no options after SERVER")
    if req.surface == "--session":
        req.servers = rest
    elif req.surface == "--list":
        if rest:
            raise CcaError("--list takes no SERVER")
    elif len(rest) != 1:
        raise CcaError(f"{req.surface} needs exactly one SERVER")
    else:
        req.servers = rest
    return req


def _stdin_bytes() -> bytes:
    if sys.stdin is None or sys.stdin.isatty():
        raise CcaError("stdin is a terminal: give the command after -- or pipe it in")
    return sys.stdin.buffer.read()


def _stdin_command() -> str:
    data = _stdin_bytes()
    try:
        command = data.decode("utf-8")
    except UnicodeDecodeError:
        raise CcaError("command on stdin is not UTF-8") from None
    if not command.strip():
        raise CcaError("empty command on stdin")
    return command


def _tokf(cfg: config.Config, command: str, result: executor.Result) -> str:
    """Output passed through tokf when run.tokf is set and tokf supports protocol cca-v1."""
    if not cfg.data["run"]["tokf"] or result.timed_out:
        return result.output
    path = tokf_path()
    if path is None:
        return result.output
    try:
        proc = subprocess.run(
            [
                path,
                "process",
                "--protocol",
                "cca-v1",
                "--return-processor-status",
                "--command",
                command,
                "--exit-code",
                str(result.code),
            ],
            input=result.output.encode(),
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return result.output
    if proc.returncode != 0:
        return result.output
    return executor.safe_output(proc.stdout)


def tokf_path() -> str | None:
    """tokf from PATH when it answers the cca-v1 protocol probe."""
    path = shutil.which("tokf")
    if path is None:
        return None
    try:
        probe = subprocess.run(
            [path, "process", "--supports-protocol", "cca-v1"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return path if probe.returncode == 0 else None


def _timed_out(result: executor.Result, timeout: int) -> None:
    hint = (
        f"; check later: cca run --read --marker {result.marker} {result.server}"
        if result.marker
        else ""
    )
    print(
        f"cca: error: {result.server}: command did not finish within {timeout}s"
        + (", it may still run" if result.marker else ", ssh was stopped")
        + hint,
        file=sys.stderr,
    )


def run(args: argparse.Namespace) -> int:
    argv: list[str] = args.raw
    if argv[:1] in (["-h"], ["--help"]):
        argparse.ArgumentParser(
            prog="cca run",
            usage=USAGE,
            description=DESCRIPTION,
            epilog=EPILOG,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        ).print_help()
        return 0
    req = parse(argv)
    cfg = config.require(args.config)
    for server in req.servers:
        cfg.server(server)  # unknown server -> error before anything runs
    if req.surface == "--list":
        return _list(cfg)
    if req.surface in ("--read", "--session"):
        if executor.transport(cfg) != "tmux":
            raise CcaError(f'{req.surface} is not available with run.transport = "ssh"')
        return _read(cfg, req) if req.surface == "--read" else _session(cfg, req)
    if req.surface == "--create-file":
        result = executor.create_file(
            cfg, req.servers[0], req.create_path, _stdin_bytes(), timeout=req.timeout
        )
        sys.stdout.write(result.output)
        if result.timed_out:
            _timed_out(result, req.timeout)
        return result.code
    command = req.command if req.command is not None else _stdin_command()
    executor.check_command(command)
    if req.surface == "--all":
        return _all(cfg, command, req.timeout)
    result = executor.execute(cfg, req.servers[0], command, timeout=req.timeout)
    sys.stdout.write(_tokf(cfg, command, result))
    if result.timed_out:
        _timed_out(result, req.timeout)
    return result.code


def _all(cfg: config.Config, command: str, timeout: int) -> int:
    servers = list(cfg.data["servers"])
    if not servers:
        raise CcaError(f"{cfg.path}: no [servers] configured")
    for server in servers:
        result = executor.execute(cfg, server, command, timeout=timeout)
        status = "timeout" if result.timed_out else str(result.code)
        print(f'<server-result name="{server}" exit="{status}">')
        sys.stdout.write(_tokf(cfg, command, result))
        print("</server-result>", flush=True)
        if result.timed_out:
            _timed_out(result, timeout)
        if result.code != 0:
            return result.code
    return 0


def _list(cfg: config.Config) -> int:
    servers = cfg.data["servers"]
    if not servers:
        raise CcaError(f"{cfg.path}: no [servers] configured")
    open_windows: dict[str, str] | None = None
    if executor.transport(cfg) == "tmux":
        open_windows = executor.windows(executor.session(cfg))
    for name, server in servers.items():
        line = f"{name}\t{server['ssh']}"
        if open_windows is not None:
            line += "\twindow" if name in open_windows else "\t-"
        print(line)
    return 0


def _read(cfg: config.Config, req: Request) -> int:
    window_id, _ = executor.window(cfg, req.servers[0], create=False)
    if req.marker is not None:
        block = executor.marker_block(executor.capture(window_id, "-"), req.marker)
        if block is None:
            raise CcaError(f"marker {req.marker} not in the pane history of {req.servers[0]}")
        body, code = block
        sys.stdout.write(executor.block_output(body, code is not None))
        if code is None:
            print(f"cca: note: marker {req.marker} has no END yet (still running)", file=sys.stderr)
            return 124
        return code
    start = "-" if req.scrollback else (f"-{req.lines}" if req.lines is not None else None)
    sys.stdout.write(executor.safe_output(executor.capture(window_id, start)))
    return 0


def _session(cfg: config.Config, req: Request) -> int:
    name = executor.session(cfg)
    servers = req.servers or list(cfg.data["servers"])
    if not servers:
        raise CcaError(f"{cfg.path}: no [servers] configured")
    for server in servers:
        _, created = executor.window(cfg, server)
        print(f"{server}\t{'opened' if created else 'open'}")
    print(f"attach: tmux attach -t ={name}")
    return 0
