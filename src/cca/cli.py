"""Entry point: argparse front end, only the selected subcommand module is imported."""

from __future__ import annotations

import argparse
import sys
from importlib import import_module
from importlib.metadata import version

from cca.output import CcaError, error

# subcommand -> (module under cca.commands, one-line help); each module provides
# add_arguments(parser) and run(args) -> int
COMMANDS: dict[str, tuple[str, str]] = {
    "config": ("config", "show the project .cca.toml"),
    "doctor": ("doctor", "check that the current project is ready for cca"),
    "install": ("install", "install cca skills into an agent skill directory"),
}


def _selected(argv: list[str]) -> str | None:
    """The subcommand named in argv (first positional after the global options)."""
    skip = False
    for arg in argv:
        if skip:
            skip = False
        elif arg == "--config":
            skip = True
        elif arg == "--" or not arg.startswith("-"):
            return arg if arg in COMMANDS else None
    return None


def build_parser(selected: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cca", description="Cyber-CLI Admin toolkit.")
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
    selected = _selected(argv)
    parser = build_parser(selected)
    args = parser.parse_args(argv)
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
