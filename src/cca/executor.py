"""Remote command execution over tmux or ssh (doc-1 "cca run").

The one executor every server-taking command uses; `cca run` is a thin CLI over it.
No local shell: every child process gets an argv, the server comes from [servers] and
the command travels base64-encoded. The tmux marker protocol (START/END markers,
signal traps, exit codes) is the one of the former cca-tmux-cli and tmux_cli_python.
"""

from __future__ import annotations

import base64
import os
import re
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cca import ssh, validate
from cca.config import Config
from cca.output import CcaError, warn

COMMAND_MAX = 64 * 1024  # bytes of one command
TMUX_INPUT_MAX = 64 * 1024  # bytes of stdin content sent through a tmux pane
SSH_SETTLE = 2.0  # seconds a new tmux window gets for ssh to connect
POLL = 0.2  # seconds between checks for the END marker
TMUX_TIMEOUT = 30  # seconds for one tmux client call

SIGNAL_EXIT_CODES = {"INTERRUPTED": 130, "TERMINATED": 143, "HANGUP": 129, "KILLED": 137}
MARKER_RE = re.compile(r"CCA_[0-9]+_[0-9]+")
_CONTROL_EXCEPT_NL_TAB = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass
class Result:
    server: str
    code: int  # the remote command's exit code; 124 when timed out
    output: str  # combined stdout and stderr, control characters escaped
    marker: str | None = None  # tmux: the marker to find the output again
    timed_out: bool = False


# --- remote form (both transports)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def remote_command(command: str, stdin: bool = False) -> str:
    """The remote shell line running command with bash, its stdin /dev/null unless given."""
    run = f'bash -c "$(printf %s {_b64(command.encode())} | base64 -d)"'
    return run if stdin else run + " </dev/null"


def check_command(command: str) -> str:
    if not command.strip():
        raise CcaError("empty command")
    if "\x00" in command:
        raise CcaError("command contains a NUL character")
    if len(command.encode()) > COMMAND_MAX:
        raise CcaError(f"command longer than {COMMAND_MAX} bytes")
    return command


def safe_output(data: bytes | str) -> str:
    """Remote output for the terminal: control characters except newline and tab escaped."""
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    return _CONTROL_EXCEPT_NL_TAB.sub(lambda m: f"\\x{ord(m.group()):02x}", text)


# --- command log ([run.log])

_SECRET_PATTERNS = [
    (re.compile(r"(https?://)[^\s@]+:[^\s@]+@", re.I), r"\1[USER]:[REDACTED]@"),
    (
        re.compile(
            r"(password|passwd|token|key|secret|api[_-]?key|access[_-]?key|auth[_-]?key)"
            r"(\s*[:=]\s*)(['\"])[^'\"]*['\"]",
            re.I,
        ),
        r'\1\2"[REDACTED]"',
    ),
    (
        re.compile(
            r"(password|passwd|token|key|secret|api[_-]?key|access[_-]?key|auth[_-]?key)"
            r"(\s*[:=]\s*)(?![\"'])\S+",
            re.I,
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(r"(^|\s)(-+)(password|passwd|token|key|secret|api[_-]?key)(\s+)\S+", re.I),
        r"\1\2\3\4[REDACTED]",
    ),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA[REDACTED]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36}"), "gh*_[REDACTED]"),
    (re.compile(r"eyJ[A-Za-z0-9_/+-]*\.[A-Za-z0-9_/+-]*\.[A-Za-z0-9_/+-]*"), "eyJ[JWT_REDACTED]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_/.-]+", re.I), "Bearer [REDACTED]"),
    (re.compile(r"(mongodb|postgres|mysql|mariadb)://\S+", re.I), r"\1://[REDACTED]"),
    (re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"), "[BASE64_REDACTED]"),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "-----BEGIN [REDACTED] PRIVATE KEY-----",
    ),
]


def sanitize(command: str) -> str:
    """The command as logged: likely secrets replaced, one line, control characters escaped."""
    for pattern, replacement in _SECRET_PATTERNS:
        command = pattern.sub(replacement, command)
    return validate.display(command)


def _log_dir(cfg: Config) -> Path | None:
    """The log dir when [run.log] is set; it must exist (cca never creates it)."""
    log = cfg.data["run"].get("log")
    if log is None:
        return None
    path = cfg.resolve(log["dir"])
    if not path.is_dir():
        raise CcaError(f"{cfg.path}: run.log.dir: {path} does not exist (create it)")
    return path


def _log(cfg: Config, log_dir: Path | None, server: str, text: str, status: str) -> None:
    if log_dir is None:
        return
    operator = cfg.data["run"]["log"]["operator"]
    now = datetime.now().astimezone()
    path = log_dir / f"{now:%Y-%m-%d}-{operator}.log"
    stamp = now.isoformat(timespec="seconds")
    line = f"{stamp} {operator} {server} {sanitize(text)} [exit: {status}]\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        warn(f"cannot write command log {path}: {e.strerror}")


# --- entry points


def transport(cfg: Config) -> str:
    return cfg.data["run"]["transport"]


def execute(
    cfg: Config,
    server: str,
    command: str,
    *,
    timeout: float = 300,
    stdin: bytes | None = None,
    log_text: str | None = None,
    via: str | None = None,
) -> Result:
    """Run command on server with the configured transport and return its output.

    stdin (bytes) becomes the remote command's stdin, otherwise it reads /dev/null.
    log_text replaces the command in the log line. via="ssh" overrides run.transport:
    finished scripts (server, diagnose) always use ssh, run.transport is for the
    agent's live `cca run` commands. A local Ctrl-C raises CcaError 130 after logging;
    the remote command may keep running.
    """
    if via not in (None, "ssh"):
        raise ValueError(f"via must be None or 'ssh', not {via!r}")
    check_command(command)
    target = ssh.target(cfg, server)
    log_dir = _log_dir(cfg)
    text = command if log_text is None else log_text
    try:
        if (via or transport(cfg)) == "ssh":
            result = _ssh_execute(server, target, command, timeout, stdin)
        else:
            result = _tmux_execute(cfg, server, target, command, timeout, stdin)
    except KeyboardInterrupt:
        _log(cfg, log_dir, server, text, "interrupted")
        raise CcaError(f"{server}: interrupted locally; the command may still run", 130) from None
    except _InterruptedError as e:
        _log(cfg, log_dir, server, text, "interrupted")
        raise CcaError(
            f"{server}: interrupted locally; the command may still run "
            f"(check later: cca run --read --marker {e.marker} {server})",
            130,
        ) from None
    _log(cfg, log_dir, server, text, "timeout" if result.timed_out else str(result.code))
    return result


def create_file(
    cfg: Config, server: str, path: str, content: bytes, *, timeout: float = 300
) -> Result:
    """Write content to the absolute remote path atomically (temp file + mv in its dir).

    An existing file keeps its mode, a new one gets the remote umask default; the output
    is `ls -ld` of the result.
    """
    if not path.startswith("/") or validate.has_control(path):
        raise CcaError(
            f"remote path '{validate.display(path)}' must be absolute, without control characters"
        )
    script = f"""target={shlex.quote(path)}
temp_path=$(mktemp "$(dirname -- "$target")/.cca-create.XXXXXX") || exit 1
if cat >"$temp_path" &&
    if [ -e "$target" ]; then
        chmod --reference="$target" -- "$temp_path"
    else
        chmod "$(printf '%o' $((0666 & ~0$(umask))))" -- "$temp_path"
    fi &&
    mv -f -- "$temp_path" "$target"; then
    ls -ld -- "$target"
else
    rc=$?
    rm -f -- "$temp_path"
    exit $rc
fi"""
    return execute(
        cfg,
        server,
        script,
        timeout=timeout,
        stdin=content,
        log_text=f"create-file {path}",
    )


# --- ssh transport


def _stop(proc: subprocess.Popen) -> None:
    """Kill ssh and whatever it started locally (e.g. a ProxyCommand)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _ssh_execute(
    server: str, target: str, command: str, timeout: float, stdin: bytes | None
) -> Result:
    argv = ssh.argv(target, remote_command(command, stdin is not None))
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # its own process group: stopped with its children
        )
    except OSError as e:
        raise CcaError(f"cannot run ssh: {e.strerror}") from None
    try:
        out, _ = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop(proc)
        out, _ = proc.communicate()
        return Result(server, 124, safe_output(out), timed_out=True)
    except BaseException:
        _stop(proc)
        proc.wait()
        raise
    return Result(server, proc.returncode, safe_output(out))


# --- tmux transport


class _InterruptedError(Exception):
    def __init__(self, marker: str):
        self.marker = marker


def _tmux_run(args: tuple[str, ...], input: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["tmux", *args],
            input=input,
            stdin=None if input is not None else subprocess.DEVNULL,
            capture_output=True,
            timeout=TMUX_TIMEOUT,
        )
    except FileNotFoundError:
        raise CcaError('tmux not found on PATH (run.transport = "tmux")') from None
    except subprocess.TimeoutExpired:
        raise CcaError(f"tmux {args[0]} did not answer within {TMUX_TIMEOUT}s") from None


def tmux(*args: str, input: bytes | None = None) -> str:
    """Run one tmux client call; failures raise CcaError with tmux's message."""
    proc = _tmux_run(args, input)
    if proc.returncode != 0:
        message = validate.display(proc.stderr.decode("utf-8", "replace").strip())
        raise CcaError(f"tmux {args[0]}: {message or f'exit {proc.returncode}'}")
    return proc.stdout.decode("utf-8", "replace")


def session(cfg: Config) -> str:
    return cfg.require("run.tmux.session")


def session_exists(name: str) -> bool:
    return _tmux_run(("has-session", "-t", f"={name}")).returncode == 0


def windows(name: str) -> dict[str, str]:
    """Window name -> window id of the session; empty when the session does not exist."""
    if not session_exists(name):
        return {}
    found: dict[str, str] = {}
    for line in tmux(
        "list-windows", "-t", f"={name}", "-F", "#{window_id}\t#{window_name}"
    ).splitlines():
        window_id, _, window_name = line.partition("\t")
        found.setdefault(window_name, window_id)
    return found


def window(cfg: Config, server: str, create: bool = True) -> tuple[str, bool]:
    """(window id, created) of the server's window; a missing one is opened with ssh."""
    name = session(cfg)
    existing = windows(name).get(server)
    if existing is not None:
        return existing, False
    if not create:
        raise CcaError(f"no tmux window for {server} in session {name} (run a command first)")
    target = ssh.target(cfg, server)
    command = ["--", "ssh", "--", target]  # several arguments: tmux runs ssh without a shell
    if session_exists(name):
        out = tmux(
            "new-window",
            "-d",
            "-P",
            "-F",
            "#{window_id}",
            "-t",
            f"={name}:",
            "-n",
            server,
            *command,
        )
    else:
        out = tmux(
            "new-session", "-d", "-P", "-F", "#{window_id}", "-s", name, "-n", server, *command
        )
    return out.strip(), True


def _typed_line(marker: str, command: str, stdin: bytes | None) -> str:
    """The line typed into the pane shell: markers around the command, signals mapped."""
    shown = _b64(command.encode())
    run = remote_command(command, stdin is not None)
    if stdin is not None:
        run = f"printf %s {_b64(stdin)} | base64 -d | {run}"
    cases = " ".join(
        f"{code}) echo '{marker} {name} ===';;" for name, code in SIGNAL_EXIT_CODES.items()
    )
    # START/END echoes are split so a wrapped line of the typed command never starts
    # with a complete marker; the pane shell ignores signals, the subshell restores them
    return (
        "trap '' INT TERM HUP; echo; echo '# Command:'; "
        f"printf %s {shown} | base64 -d; echo; "
        f"echo -n '=== START '; echo '{marker} ==='; "
        f"( trap - INT TERM HUP; {run} ); cca_rc=$?; trap - INT TERM HUP; echo; "
        f"echo -n '=== END '; case $cca_rc in {cases} "
        f"*) echo '{marker} EXITCODE='$cca_rc' ===';; esac"
    )


def _end_re(marker: str) -> re.Pattern[str]:
    return re.compile(
        rf"=== END {re.escape(marker)} "
        rf"(?:EXITCODE=(\d+)|({'|'.join(SIGNAL_EXIT_CODES)})) ==="
    )


def capture(window_id: str, start: str | None = None) -> str:
    """Pane text, wrapped lines joined; start "-" = whole scrollback, "-N" = N lines back."""
    args = ["capture-pane", "-p", "-J", "-t", window_id]
    if start is not None:
        args += ["-S", start]
    return tmux(*args)


def marker_block(text: str, marker: str) -> tuple[list[str], int | None] | None:
    """Lines between the last START of marker and its END, and the exit code.

    None when there is no START line; exit code None when the END line is missing.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    start_line = f"=== START {marker} ==="
    starts = [i for i, line in enumerate(lines) if line == start_line]
    if not starts:
        return None
    end_re = _end_re(marker)
    body: list[str] = []
    for line in text.splitlines()[starts[-1] + 1 :]:
        m = end_re.fullmatch(line.rstrip())
        if m:
            code = int(m.group(1)) if m.group(1) else SIGNAL_EXIT_CODES[m.group(2)]
            return body, code
        body.append(line)
    return body, None


def block_output(body: list[str], complete: bool) -> str:
    """Text of a marker block: without the separator line before END, or, while the
    command still runs, without the empty pane rows below its output."""
    if complete:
        if body and body[-1] == "":  # the separator echo before the END marker
            body = body[:-1]
    else:
        while body and body[-1] == "":
            body = body[:-1]
    return safe_output("".join(line + "\n" for line in body))


def _tmux_execute(
    cfg: Config, server: str, target: str, command: str, timeout: float, stdin: bytes | None
) -> Result:
    if stdin is not None and len(stdin) > TMUX_INPUT_MAX:
        raise CcaError(f"stdin over {TMUX_INPUT_MAX} bytes cannot go through a tmux pane")
    window_id, created = window(cfg, server)
    if created:
        time.sleep(SSH_SETTLE)
    marker = f"CCA_{time.time_ns()}_{os.getpid()}"
    buffer = f"cca-{marker}"
    # paste-buffer writes straight to the pane (no key names, no argv size limit, no copy
    # mode); its default separator turns the final newline into Enter
    tmux(
        "load-buffer",
        "-b",
        buffer,
        "-",
        input=(_typed_line(marker, command, stdin) + "\n").encode(),
    )
    tmux("paste-buffer", "-d", "-b", buffer, "-t", window_id)
    end_re = _end_re(marker)
    deadline = time.monotonic() + timeout
    try:
        while True:
            if any(end_re.fullmatch(line.rstrip()) for line in capture(window_id).splitlines()):
                break
            if time.monotonic() >= deadline:
                block = marker_block(capture(window_id, "-"), marker)
                output = block_output(block[0], False) if block else ""
                return Result(server, 124, output, marker, timed_out=True)
            time.sleep(POLL)
    except KeyboardInterrupt:
        raise _InterruptedError(marker) from None
    block = marker_block(capture(window_id, "-"), marker)
    if block is None or block[1] is None:
        raise CcaError(
            f"{server}: incomplete output (START or END marker {marker} not in the pane "
            f"history); inspect it with: cca run --read --scrollback {server}"
        )
    body, code = block
    return Result(server, code, block_output(body, True), marker)
