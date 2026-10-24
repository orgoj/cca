"""cca ioc: read the state of the host-ioc compromise check from the project's hosts.

host-ioc itself (script, cron, mail, config) is deployed by the project's Ansible role;
cca only reads: the last-quick.json / last-deep.json state files, read-only raw data for
one finding, and the baseline proposal `host-ioc baseline` prints. Nothing is written
on a host. Remote output is untrusted: every value is shown escaped and validated before
it goes into a remote command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from datetime import UTC, datetime
from typing import Any

from cca import config, executor, validate
from cca.output import CcaError

STATE_DIR = "/var/lib/host-ioc"
RUNS = ("quick", "deep")
PREFIX = "set -o pipefail; PATH=$PATH:/usr/local/sbin:/usr/sbin:/sbin; "
MARK = "@@host-ioc"
TIMEOUT_MAX = 86400
CONTEXT = 5  # log/file lines before and after a finding's line
CUT = 500  # characters per raw data line
STATE_MAX = 4 * 1024 * 1024  # bytes of one state file read from a host
DETAIL_MAX = 300  # characters of a finding's detail in listings
ID_RE = re.compile(r"[A-Za-z0-9]{1,128}")
PID_MAX = 4194304  # Linux pid_max limit

EPILOG = """\
commands:
  status [HOST...]    last quick/deep run per host: time, age, duration, version,
                      script_sha256 vs ioc.script, uncovered modules, findings
  show HOST [ID]      findings of HOST; with ID the finding and read-only raw data
                      (process from /proc, file lines around it)
  baseline HOST       run `host-ioc baseline` on HOST, save the proposal to
                      ioc.baseline_dir for review

Hosts come from ioc.hosts, transport from ioc.transport ("ssh", or "run" = the
run.transport of `cca run`), ioc.sudo = true reads through `sudo -n`.

status warns when a run is missing, unreadable, older than 2x its interval
(ioc.quick_interval_hours, ioc.deep_interval_hours), has uncovered modules or another
script_sha256 than ioc.script.

exit status: 0 nothing to report; 1 findings (status, show); 2 a warning, an error on
a host, usage or config error (2 wins).

examples:
  cca ioc status
  cca ioc show server1
  cca ioc show server1 3f9a2c
  cca ioc baseline server1"""


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.epilog = EPILOG
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        metavar="SEC",
        help="seconds per remote call (1-86400, default 60)",
    )
    sub = parser.add_subparsers(dest="ioc_command", metavar="COMMAND", required=True)
    p = sub.add_parser("status", help="last runs of every host (or the given hosts)")
    p.add_argument("hosts", nargs="*", metavar="HOST")
    p = sub.add_parser("show", help="findings of a host, or one finding with raw data")
    p.add_argument("host", metavar="HOST")
    p.add_argument("id", nargs="?", metavar="ID")
    p = sub.add_parser("baseline", help="save the host's baseline proposal for review")
    p.add_argument("host", metavar="HOST")


# --- remote calls


def _remote(cfg: config.Config, host: str, script: str, timeout: int, log: str):
    if cfg.data["ioc"]["sudo"]:
        script = "sudo -n bash -c " + shlex.quote(script)
    via = "ssh" if cfg.data["ioc"]["transport"] == "ssh" else None
    return executor.execute(
        cfg, host, PREFIX + script, timeout=timeout, log_text=f"ioc {log}", via=via
    )


def _failed(host: str, result) -> CcaError:
    if result.timed_out:
        return CcaError(f"{host}: timed out")
    tail = result.output.strip().splitlines()[-1:] or ["no output"]
    return CcaError(f"{host}: remote command failed (exit {result.code}): {tail[0]}")


def read_states(cfg: config.Config, host: str, timeout: int) -> dict[str, Any]:
    """{run: parsed state document | error text} for both runs of host."""
    script = "".join(
        f'echo "{MARK} {run}"; head -c {STATE_MAX + 1} -- {STATE_DIR}/last-{run}.json 2>&1; '
        "rc=$?; echo; "
        f'echo "{MARK}-end {run} $rc"; '
        for run in RUNS
    )
    result = _remote(cfg, host, script, timeout, "status")
    if result.timed_out or result.code:
        raise _failed(host, result)
    return parse_states(result.output)


def parse_states(output: str) -> dict[str, Any]:
    states: dict[str, Any] = {run: "no state in the output" for run in RUNS}
    current: str | None = None
    body: list[str] = []
    for line in output.splitlines():
        if current is None:
            if line.startswith(MARK + " ") and line[len(MARK) + 1 :] in RUNS:
                current, body = line[len(MARK) + 1 :], []
            continue
        end = re.fullmatch(rf"{MARK}-end {current} (\d+)", line)
        if not end:
            body.append(line)
            continue
        text = "\n".join(body).strip()
        if end.group(1) != "0":
            states[current] = "cannot read: " + (text.splitlines() or ["no output"])[0][:CUT]
        elif len(text.encode()) > STATE_MAX:
            states[current] = f"state file over {STATE_MAX} bytes"
        else:
            states[current] = _document(text)
        current = None
    return states


def _document(text: str) -> dict[str, Any] | str:
    """The parsed state, or why it is invalid: findings must be a list of objects, since
    a dropped or malformed entry would hide a finding."""
    try:
        doc = json.loads(text)
    except ValueError:
        return "not a JSON object"
    if not isinstance(doc, dict):
        return "not a JSON object"
    findings = doc.get("findings")
    if not isinstance(findings, list) or not all(isinstance(f, dict) for f in findings):
        return "findings is not a list of objects"
    return doc


# --- state documents (untrusted)


def _text(value: Any, limit: int = DETAIL_MAX) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = validate.display(text)
    return text if len(text) <= limit else text[:limit] + "..."


def _findings(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc["findings"]  # checked by _document


def _started(doc: dict[str, Any]) -> datetime | None:
    value = doc.get("started")
    if not isinstance(value, str):
        return None
    try:
        started = datetime.fromisoformat(value)
    except ValueError:
        return None
    return started if started.tzinfo is not None else None


def _age(seconds: float) -> str:
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 172800:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def run_status(
    cfg: config.Config, run: str, state: Any, expected_sha: str, now: datetime
) -> tuple[str, int]:
    """One status line for a run and its exit contribution (0, 1 findings, 2 warning)."""
    if not isinstance(state, dict):
        return f"{run}: WARN {state}", 2
    warnings = []
    started = _started(state)
    if started is None:
        warnings.append("no valid started time")
        when = "started ?"
    else:
        age = (now - started).total_seconds()
        when = f"{started.isoformat()} ({_age(max(age, 0))} ago)"
        hours = cfg.data["ioc"][f"{run}_interval_hours"]
        if age > 2 * hours * 3600:
            warnings.append(f"stale (older than 2x {hours}h)")
    duration = state.get("duration_s")
    took = f"{duration:g}s" if isinstance(duration, int | float) else "?s"
    sha = state.get("script_sha256")
    if sha != expected_sha:
        warnings.append("script_sha256 differs from ioc.script")
    modules = state.get("modules")
    uncovered = []
    if isinstance(modules, dict):
        uncovered = [
            validate.display(name)
            for name, m in modules.items()
            if not isinstance(m, dict) or m.get("status") not in ("ok", "finding")
        ]
    else:
        warnings.append("no modules")
    if uncovered:
        warnings.append("uncovered: " + ", ".join(uncovered))
    findings = _findings(state)
    new = sum(1 for f in findings if f.get("new") is True)
    line = (
        f"{run}: {when}, {took}, version {_text(state.get('version', '?'), 40)}, "
        f"findings {len(findings)} ({new} new)"
    )
    if warnings:
        line += "; WARN " + "; ".join(warnings)
    return line, 2 if warnings else (1 if findings else 0)


def _hosts(cfg: config.Config, names: list[str]) -> list[str]:
    configured = cfg.data["ioc"]["hosts"]
    if not configured:
        raise CcaError(f"{cfg.path}: ioc.hosts: required by this command but not set")
    for name in configured:
        cfg.server(name)  # every ioc host must be a [servers] entry
    for name in names:
        if name not in configured:
            raise CcaError(
                f"'{validate.display(name)}' is not in ioc.hosts ({', '.join(configured)})"
            )
    return names or list(configured)


def _expected_sha(cfg: config.Config) -> str:
    path = cfg.resolve(cfg.require("ioc.script"))
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as e:
        raise CcaError(f"{cfg.path}: ioc.script: cannot read {path}: {e.strerror}") from None


def status(cfg: config.Config, hosts: list[str], timeout: int) -> int:
    expected = _expected_sha(cfg)
    now = datetime.now(UTC)
    code = 0
    for host in hosts:
        try:
            states = read_states(cfg, host, timeout)
        except CcaError as e:
            print(f"{host}: ERROR {e}")
            code = 2
            continue
        for run in RUNS:
            line, run_code = run_status(cfg, run, states[run], expected, now)
            print(f"{host} {line}")
            code = max(code, run_code)
    return code


# --- show


def _target(finding: dict[str, Any]) -> str:
    if "pid" in finding:
        return f"pid={_text(finding['pid'], 20)}"
    if "path" in finding:
        return f"path={_text(finding['path'], 200)}"
    return "-"


def _listing(run: str, state: dict[str, Any]) -> list[str]:
    lines = []
    for f in _findings(state):
        lines.append(
            f"  {_text(f.get('id', '?'), 128)}  {_text(f.get('module', '?'), 40)}"
            f"  container={_text(f.get('container') or '-', 64)}  {_target(f)}"
            f"  {'new  ' if f.get('new') is True else ''}{_text(f.get('detail', ''))}"
        )
    started = _text(state.get("started", "?"), 40)
    return [f"{run} {started}: {len(lines)} findings", *lines]


def raw_script(finding: dict[str, Any]) -> str | None:
    """Read-only shell script printing raw data for the finding, None when it has none.

    pid and path come from the host and are validated here, never trusted.
    """
    pid = finding.get("pid")
    if pid is not None:
        if isinstance(pid, bool) or not isinstance(pid, int) or not 1 <= pid <= PID_MAX:
            raise CcaError(f"finding has an invalid pid {_text(pid, 40)}")
        d = f"/proc/{pid}"
        return (
            f"[ -d {d} ] || {{ echo 'process {pid} no longer exists'; exit 0; }}; "
            f'echo "exe: $(readlink {d}/exe)"; echo "cwd: $(readlink {d}/cwd)"; '
            f"printf 'cmdline: '; tr '\\0' ' ' < {d}/cmdline | cut -c1-{CUT}; echo; "
            f"grep -E '^(Name|State|PPid|Uid|Gid):' {d}/status; "
            f"echo 'cgroup:'; head -n 5 {d}/cgroup | cut -c1-{CUT}; "
            f"echo 'process and children:'; "
            f"ps -o pid,ppid,user,etime,args -p {pid} --ppid {pid} | cut -c1-{CUT}"
        )
    path = finding.get("path")
    if path is None:
        return None
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or validate.has_control(path)
        or len(path) > 4096
    ):
        raise CcaError(f"finding has an invalid path {_text(path, 200)}")
    p = shlex.quote(path)
    line = finding.get("line")
    if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
        window = f"sed -n '{max(1, line - CONTEXT)},{line + CONTEXT}p' -- {p}"
        what = f"lines {max(1, line - CONTEXT)}-{line + CONTEXT}"
    else:
        window = f"head -n {2 * CONTEXT + 1} -- {p}"
        what = f"first {2 * CONTEXT + 1} lines"
    # sed -n reads to EOF (head would SIGPIPE ls under pipefail)
    return (
        f"ls -ld -- {p} || exit 0; "
        f"if [ -d {p} ]; then ls -la -- {p} | cut -c1-{CUT} | sed -n '1,50p'; "
        f"elif [ ! -f {p} ]; then echo 'not a regular file'; "
        f"elif grep -Iq . -- {p}; then echo '{what}:'; {window} | cut -c1-{CUT}; "
        f"else echo 'binary or empty, content not shown'; sha256sum -- {p}; fi"
    )


def show(cfg: config.Config, host: str, finding_id: str | None, timeout: int) -> int:
    if finding_id is not None and not ID_RE.fullmatch(finding_id):
        raise CcaError(f"invalid finding id '{validate.display(finding_id)}'")
    states = read_states(cfg, host, timeout)
    code = 0
    if finding_id is None:
        for run in RUNS:
            state = states[run]
            if not isinstance(state, dict):
                print(f"{run}: WARN {state}")
                code = 2
                continue
            lines = _listing(run, state)
            print("\n".join(lines))
            if len(lines) > 1:
                code = max(code, 1)
        return code
    for run in RUNS:
        state = states[run]
        if not isinstance(state, dict):
            continue
        for f in _findings(state):
            if f.get("id") == finding_id:
                return _detail(cfg, host, run, f, timeout)
    unread = [f"{run}: {states[run]}" for run in RUNS if not isinstance(states[run], dict)]
    if unread:
        raise CcaError(
            f"{host}: no finding {finding_id} in the readable runs; " + "; ".join(unread)
        )
    raise CcaError(f"{host}: no finding {finding_id} in the last quick/deep runs")


def _detail(cfg: config.Config, host: str, run: str, finding: dict[str, Any], timeout: int) -> int:
    print(f"run: {run}")
    for key, value in finding.items():
        print(f"{validate.display(key)}: {_text(value, 2000)}")
    script = raw_script(finding)
    if script is None:
        print("raw data: none (the finding has no pid or path)")
        return 1
    result = _remote(cfg, host, script, timeout, "show")
    print("raw data:")
    sys.stdout.write(result.output if result.output.endswith("\n") else result.output + "\n")
    if result.timed_out or result.code:
        raise _failed(host, result)
    return 1


# --- baseline


def baseline(cfg: config.Config, host: str, timeout: int) -> int:
    # stdout lines get "O|", so stderr (merged by the transport) stays out of the file
    result = _remote(cfg, host, "host-ioc baseline | sed 's/^/O|/'", timeout, "baseline")
    out, err = [], []
    for line in result.output.splitlines():
        (out if line.startswith("O|") else err).append(line.removeprefix("O|"))
    for line in err:
        print(f"{host}: {line}", file=sys.stderr)
    if result.timed_out or result.code:
        raise _failed(host, result)
    if not out:
        raise CcaError(f"{host}: host-ioc baseline printed nothing")
    directory = cfg.resolve(cfg.data["ioc"]["baseline_dir"])
    stamp = datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz")
    path = directory / f"{host.lower()}+{stamp}.yaml"
    if path.resolve().parent != directory.resolve():
        raise CcaError(f"{path}: not under {directory}")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with open(path, "x") as f:
            f.write("\n".join(out) + "\n")
    except OSError as e:
        raise CcaError(f"cannot write {path}: {e.strerror}") from None
    print(path)
    return 0


def run(args: argparse.Namespace) -> int:
    if not 1 <= args.timeout <= TIMEOUT_MAX:
        raise CcaError(f"--timeout must be an integer 1-{TIMEOUT_MAX}")
    cfg = config.require(args.config)
    if args.ioc_command == "status":
        return status(cfg, _hosts(cfg, args.hosts), args.timeout)
    host = _hosts(cfg, [args.host])[0]
    if args.ioc_command == "show":
        return show(cfg, host, args.id, args.timeout)
    return baseline(cfg, host, args.timeout)
