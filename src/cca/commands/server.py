"""cca server: hostname, quick status and inventory of a configured server.

Every section is one remote command through cca.executor, always over ssh (run.transport
is for the agent's live `cca run` commands). Output is XML-like tags, one per section.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from cca import config, executor
from cca.output import CcaError

TIMEOUT_MAX = 86400
SSH_FAILED = 255  # ssh's own exit status: no point in more calls to that server
# non-login ssh shells of non-root users often lack the sbin directories (zpool, lxc-ls)
PREFIX = "set -o pipefail; PATH=$PATH:/usr/local/sbin:/usr/sbin:/sbin; "

EPILOG = """\
sections:
  hostname  the server's hostname
  status    admin-time (local), server-time, load, memory, storage (ext/xfs), zfs
  info      hostname, os, cpu, memory, disks, zfs, network, loopback, docker, swarm,
            lxc, qemu

A section whose command fails gets exit="N" on its tag; the other sections still run.
--timeout is the total time for one server.

exit status: 0 all sections ran; 124 timeout; 255 ssh failed; 125 output over 16 MiB
(ssh killed, report stopped); 2 usage or config error.
With --all the servers run in config order and the first non-zero exit stops it.

examples:
  cca server hostname --all
  cca server status server1
  cca server info --timeout 300 server1"""


def _have(tool: str, command: str, missing: str) -> str:
    return f"if command -v {tool} >/dev/null 2>&1; then {command}; else echo '{missing}'; fi"


def _listing(command: str, empty: str) -> str:
    """command's output, or `empty` when it printed nothing; its failure stays a failure."""
    return (
        f"out=$({command}) || exit; "
        f"if [ -n \"$out\" ]; then printf '%s\\n' \"$out\"; else echo '{empty}'; fi"
    )


def status_sections() -> list[tuple[str, str]]:
    return [
        ("server-time", "date -Iseconds"),
        ("load", "uptime"),
        ("memory", "free -h"),
        (
            "storage",
            "if findmnt -n -t ext2,ext3,ext4,xfs >/dev/null; "
            "then df -hT -t ext2 -t ext3 -t ext4 -t xfs; else echo 'no ext/xfs filesystems'; fi",
        ),
        ("zfs", _have("zpool", "zpool list", "ZFS not available")),
    ]


def info_sections(cfg: config.Config) -> list[tuple[str, str]]:
    # config validates each prefix as [A-Za-z0-9]+, so the awk regex is plain text
    prefixes = "|".join(cfg.data["server_info"]["net_iface_prefixes"])
    return [
        ("hostname", "hostname"),
        ("os", "sed -n 's/^PRETTY_NAME=//p' /etc/os-release | tr -d '\"'; uname -sr"),
        ("cpu", "lscpu | awk '/^(CPU\\(s\\)|Model name):/'"),
        ("memory", "free -h | awk '/^(Mem|Swap):/ {print $1, $2}'"),
        ("disks", "lsblk -d -e 1,7,11 -o NAME,SIZE,ROTA,MODEL"),
        ("zfs", _have("zpool", "zpool status", "ZFS not available")),
        (
            "network",
            _listing(
                f"ip -br addr show | awk '$1 ~ /^({prefixes})/'",
                f"no interfaces matching {prefixes}",
            ),
        ),
        (
            "loopback",
            _listing(
                "ip -o addr show dev lo | awk '$4 !~ /^(127\\.|::1\\/)/ {print $4}'",
                "no loopback aliases",
            ),
        ),
        (
            "docker",
            _have(
                "docker",
                "docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}'",
                "Docker not available",
            ),
        ),
        (
            "swarm",
            "if ! command -v docker >/dev/null 2>&1; then echo 'Docker not available'; "
            "else ctl=$(docker info --format '{{.Swarm.ControlAvailable}}') || exit; "
            'if [ "$ctl" = true ]; then docker service ls; '
            "else echo 'not a Swarm manager'; fi; fi",
        ),
        ("lxc", _have("lxc-ls", "sudo -n lxc-ls -f", "LXC not available")),
        ("qemu", _listing("ps -eo pid,etime,args | awk '/[q]emu/'", "no QEMU processes")),
    ]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.epilog = EPILOG
    parser.add_argument("section", choices=("hostname", "status", "info"))
    parser.add_argument("server", nargs="?", metavar="SERVER", help="a server from [servers]")
    parser.add_argument(
        "--all", action="store_true", help="every server in config order, stop on failure"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        metavar="SEC",
        help="total seconds per server (1-86400, default 120)",
    )


def _tag(name: str, attrs: str, body: str) -> str:
    body = body.rstrip("\n")
    if "\n" in body:
        return f"<{name}{attrs}>\n{body}\n</{name}>\n"
    return f"<{name}{attrs}>{body}</{name}>\n"


def _section(
    cfg: config.Config, server: str, name: str, command: str, deadline: float, attrs: str = ""
) -> int:
    """Run one section, print its tag; return 0 to go on, else the server's exit status."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        print(f"cca: error: {server}: timed out before section {name}", file=sys.stderr)
        return 124
    result = executor.execute(cfg, server, PREFIX + command, timeout=remaining, via="ssh")
    if result.timed_out:
        sys.stdout.write(_tag(name, f'{attrs} exit="timeout"', result.output))
        print(f"cca: error: {server}: section {name} did not finish in time", file=sys.stderr)
        return 124
    if result.code:
        attrs += f' exit="{result.code}"'
    sys.stdout.write(_tag(name, attrs, result.output))
    if result.code == SSH_FAILED:
        print(f"cca: error: {server}: ssh failed (exit 255)", file=sys.stderr)
        return SSH_FAILED
    return 0


def _report(cfg: config.Config, server: str, section: str, timeout: int) -> int:
    deadline = time.monotonic() + timeout
    attrs = f' server="{server}"'  # server names are [A-Za-z0-9][A-Za-z0-9_-]*
    if section == "hostname":
        return _section(cfg, server, "hostname", "hostname", deadline, attrs)
    root = f"server-{section}"
    print(f"<{root}{attrs}>")
    code = 0
    if section == "status":
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        print(f"<admin-time>{now}</admin-time>")
        sections = status_sections()
    else:
        sections = info_sections(cfg)
    try:
        for name, command in sections:
            code = _section(cfg, server, name, command, deadline)
            if code:
                break
    finally:
        print(f"</{root}>", flush=True)
    return code


def run(args: argparse.Namespace) -> int:
    if not 1 <= args.timeout <= TIMEOUT_MAX:
        raise CcaError(f"--timeout must be an integer 1-{TIMEOUT_MAX}")
    if args.all == (args.server is not None):
        raise CcaError("give either SERVER or --all")
    cfg = config.require(args.config)
    if args.all:
        servers = list(cfg.data["servers"])
        if not servers:
            raise CcaError(f"{cfg.path}: no [servers] configured")
    else:
        servers = [cfg.canonical(args.server)]  # alias -> entry; unknown -> error now
    for server in servers:
        code = _report(cfg, server, args.section, args.timeout)
        if code:
            return code
    return 0
