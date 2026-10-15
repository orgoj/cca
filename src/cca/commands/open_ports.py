"""cca open-ports: probe TCP ports of a host with nmap, nc or curl (doc-3)."""

from __future__ import annotations

import argparse
import ipaddress
import shlex
import shutil
import subprocess
import sys

from cca import config, ssh, validate
from cca.output import CcaError

DEFAULT_PORTS = [20, 22, 25, 80, 443]
KUBERNETES_PORTS = [2379, 2380, 5473, 6443, 8472, 9345, 10250, 10257, 10259]
METHODS = ("nmap", "nc", "curl")


def _host(value: str) -> str:
    # an IPv6 zone id (fe80::1%eth0) is rejected: it does not fit the curl URL
    host = None if "%" in value else validate.host(value)
    if host is None:
        raise argparse.ArgumentTypeError(
            f"invalid host '{validate.display(value)}' (expected a DNS name, IPv4 or IPv6)"
        )
    return host


def _port(value: str) -> int:
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 65535:
        raise argparse.ArgumentTypeError(f"invalid port '{validate.display(value)}' (1-65535)")
    return int(value)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.description = (
        "Probe TCP ports of HOST. Default ports: "
        + " ".join(map(str, DEFAULT_PORTS))
        + "; ports given on the command line replace the list."
    )
    parser.add_argument("host", metavar="HOST", type=_host, help="DNS name, IPv4 or IPv6")
    parser.add_argument("ports", metavar="PORT", type=_port, nargs="*", help="1-65535")
    parser.add_argument(
        "-d",
        "--delegate",
        metavar="SERVER",
        help="run the probes on this server from [servers] in .cca.toml (over ssh)",
    )
    parser.add_argument(
        "-k",
        "--kubernetes",
        action="store_true",
        help="add Kubernetes ports: " + " ".join(map(str, KUBERNETES_PORTS)),
    )
    parser.add_argument(
        "-m", "--method", choices=METHODS, default="nmap", help="probe tool (default: nmap)"
    )
    parser.add_argument(
        "-n", "--noact", action="store_true", help="print the commands instead of running them"
    )


def _ports(args: argparse.Namespace) -> list[int]:
    if args.ports:
        return args.ports
    return DEFAULT_PORTS + (KUBERNETES_PORTS if args.kubernetes else [])


def _is_ipv6(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).version == 6
    except ValueError:
        return False


def _probes(method: str, host: str, ports: list[int]) -> list[tuple[int | None, list[str]]]:
    """(port or None for one call covering all ports, tool argv)."""
    if method == "nmap":
        family = ["-6"] if _is_ipv6(host) else []
        return [(None, ["nmap", *family, "-Pn", "--reason", "-p", ",".join(map(str, ports)), host])]
    if method == "nc":
        return [(p, ["nc", "-zv", "-w", "5", host, str(p)]) for p in ports]
    url_host = f"[{host}]" if _is_ipv6(host) else host
    return [
        (p, ["curl", "-s", "--connect-timeout", "5", "-o", "/dev/null", f"http://{url_host}:{p}"])
        for p in ports
    ]


def run(args: argparse.Namespace) -> int:
    method, host, ports = args.method, args.host, _ports(args)
    destination = None
    if args.delegate is not None:
        destination = ssh.target(config.require(args.config), args.delegate)
    commands = [
        (port, ssh.argv(destination, shlex.join(tool)) if destination else tool)
        for port, tool in _probes(method, host, ports)
    ]
    if args.noact:
        for _, argv in commands:
            print(shlex.join(argv))
        return 0
    program = "ssh" if destination else method
    if shutil.which(program) is None:
        raise CcaError(f"{program} not found on PATH")

    failed = False
    for port, argv in commands:
        sys.stdout.flush()
        try:
            code = subprocess.run(argv, stdin=subprocess.DEVNULL).returncode
        except KeyboardInterrupt:
            return 130
        if destination and code == 255:
            raise CcaError(f"ssh to {args.delegate} failed (exit 255)")
        if destination and code == 127:
            raise CcaError(f"{method} not found on {args.delegate}")
        if port is None:  # nmap: one call, its exit code is the result
            return code
        if method == "curl":
            shown = f"[{host}]" if _is_ipv6(host) else host
            state = "ok" if code == 0 else f"failed (curl exit {code})"
            print(f"{shown}:{port} {state}", flush=True)
        failed = failed or code != 0
    return 1 if failed else 0
