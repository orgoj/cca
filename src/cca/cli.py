"""Entry point: argparse front end, only the selected subcommand module is imported."""

from __future__ import annotations

import argparse
import sys
from importlib import import_module
from importlib.metadata import version

from cca.output import CcaError, error

# subcommand -> (module under cca.commands, one-line help); each module provides
# add_arguments(parser) and run(args) -> int; a module with RAW_ARGS = True gets the
# arguments after its name unparsed in args.raw (wrappers of another tool's options)
COMMANDS: dict[str, tuple[str, str]] = {
    "asn": ("asn", "routing, owner, country, type and PTR of IP addresses"),
    "check-domain": ("check_domain", "check whether a domain points to our hosting"),
    "clean": ("clean", "delete old entries of the project's tmp/ (plan by default)"),
    "cloudflare": ("cloudflare", "Cloudflare zones: DNS records, WAF rules, audit, exports"),
    "config": ("config", "show the project .cca.toml"),
    "curl": ("curl", "curl with a project credential hidden from argv and output"),
    "doctor": ("doctor", "check that the current project is ready for cca"),
    "hetrix": ("hetrix", "HetrixTools monitors: status, outages, server stats, blacklists"),
    "install": ("install", "install cca skills into an agent skill directory"),
    "ioc": ("ioc", "host-ioc compromise check: state, findings, baseline of the hosts"),
    "netdata": ("netdata", "query Netdata metrics of a server, over ssh or directly"),
    "open-ports": ("open_ports", "probe TCP ports of a host with nmap, nc or curl"),
    "run": ("run", "run a command on a configured server over tmux or ssh"),
    "server": ("server", "hostname, quick status or inventory of a server, over ssh"),
    "watchlist": ("watchlist", "daily checks, work selection and dated notes on Backlog.md"),
}


def _selected(argv: list[str]) -> tuple[str | None, int]:
    """The subcommand named in argv (first positional after the global options), its index."""
    skip = False
    for i, arg in enumerate(argv):
        if skip:
            skip = False
        elif arg == "--config":
            skip = True
        elif arg == "--" or not arg.startswith("-"):
            return (arg, i) if arg in COMMANDS else (None, -1)
    return None, -1


class Parser(argparse.ArgumentParser):
    """No abbreviated long options (`--appl` is not `--apply`): command rules match exact
    option names. Subparsers inherit the class, so every cca parser gets it."""

    def __init__(self, *args, **kwargs):
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)


def build_parser(selected: str | None = None) -> argparse.ArgumentParser:
    parser = Parser(prog="cca", description="Cyber-CLI Admin toolkit.")
    parser.add_argument("--version", action="version", version=f"cca {version('cca')}")
    parser.add_argument(
        "--config", metavar="PATH", help="use this .cca.toml instead of discovering one"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, (module, help_text) in COMMANDS.items():
        cmd_parser = sub.add_parser(name, help=help_text, description=help_text)
        if name == selected:
            import_module(f"cca.commands.{module}").add_arguments(cmd_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    selected, index = _selected(argv)
    parser = build_parser(selected)
    raw = None
    if selected is not None:
        if getattr(import_module(f"cca.commands.{COMMANDS[selected][0]}"), "RAW_ARGS", False):
            argv, raw = argv[: index + 1], argv[index + 1 :]
    args = parser.parse_args(argv)
    if raw is not None:
        args.raw = raw
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return import_module(f"cca.commands.{COMMANDS[args.command][0]}").run(args)
    except CcaError as e:
        error(str(e))
        return e.code


if __name__ == "__main__":
    sys.exit(main())
