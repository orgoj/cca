"""cca install skills: link the packaged skills into an agent skill directory."""

from __future__ import annotations

import argparse

from cca import skilllinks, validate
from cca.output import CcaError

DEFAULT_TARGET = ".claude/skills"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="what", metavar="WHAT", required=True)
    skills = sub.add_parser("skills", help="symlink the cca skills into an agent skill dir")
    skills.add_argument("name", nargs="?", metavar="NAME", help="only this skill")
    skills.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        metavar="DIR",
        help=f"existing skill directory (default: {DEFAULT_TARGET})",
    )


def run(args: argparse.Namespace) -> int:
    available = skilllinks.packaged_names()
    if args.name is not None and args.name not in available:
        raise CcaError(
            f"unknown skill '{validate.display(args.name)}' (available: {', '.join(available)})"
        )
    target = skilllinks.check_target(args.target)
    results = skilllinks.install(target, [args.name] if args.name else available)
    for r in results:
        print(f"{r.status}: {target / r.name}" + (f" ({r.detail})" if r.detail else ""))
    return 1 if any(r.status == "skipped" for r in results) else 0
