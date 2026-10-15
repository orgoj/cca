"""cca doctor: is the current project ready for cca."""

from __future__ import annotations

import argparse
import os
import shutil
from importlib.metadata import version
from pathlib import Path

from cca import config, skilllinks
from cca.commands.install import DEFAULT_TARGET
from cca.output import CcaError

PROJECT_DIRS = ("cca/guides", "cca/incidents")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fix",
        action="store_true",
        help=f"remove broken skill links created by cca install skills ({DEFAULT_TARGET})",
    )


def run(args: argparse.Namespace) -> int:
    failed = False

    def report(status: str, check: str, detail: str) -> None:
        nonlocal failed
        failed = failed or status == "FAIL"
        print(f"{status:4} {check}: {detail}")

    report("OK", "cca", version("cca"))

    cfg = None
    try:
        cfg = config.load(args.config)
    except CcaError as e:
        report("FAIL", "config", str(e))
    else:
        if cfg is None:
            report("FAIL", "config", f"no {config.FILENAME} found (run from the project directory)")
        else:
            report("OK", "config", str(cfg.path))

    sops = shutil.which("sops")
    report(
        "OK" if sops else "WARN", "sops", sops or "not on PATH (needed by commands using secrets)"
    )

    missing = [d for d in PROJECT_DIRS if not os.path.isdir(d)]
    report(
        "FAIL" if missing else "OK",
        "directories",
        ", ".join(missing or PROJECT_DIRS) + (" missing" if missing else ""),
    )

    if cfg is not None and "log" in cfg.data["run"]:
        log_dir = cfg.resolve(cfg.data["run"]["log"]["dir"])
        report(
            "OK" if log_dir.is_dir() else "FAIL",
            "run.log.dir",
            str(log_dir) + ("" if log_dir.is_dir() else " missing"),
        )

    _check_skills(report, args.fix)
    return 1 if failed else 0


def _check_skills(report, fix: bool) -> None:
    target = Path(os.path.abspath(DEFAULT_TARGET))
    if not target.is_dir():
        report("FAIL", "skills", f"{target} missing (create it, then: cca install skills)")
        return
    try:
        broken = skilllinks.broken_owned(target)
        if broken and fix:
            skilllinks.remove_broken(target, broken)
            report("OK", "skills", "removed broken links: " + ", ".join(broken))
            broken = []
        if broken:
            report("FAIL", "skills", "broken links (cca doctor --fix): " + ", ".join(broken))
        manifest = skilllinks.read_manifest(target)
        names = skilllinks.packaged_names()
    except CcaError as e:
        report("FAIL", "skills", str(e))
        return
    for name in names:
        dest = target / name
        if name in broken:
            continue  # reported above
        if not os.path.lexists(dest):
            report("FAIL", f"skill {name}", "not installed (cca install skills)")
        elif not skilllinks.owned(dest, name, manifest):
            report("FAIL", f"skill {name}", f"{dest} exists but is not a cca link")
        elif not dest.exists():
            report("FAIL", f"skill {name}", "broken link")
        elif os.path.realpath(dest) != os.path.realpath(skilllinks.package_dir() / name):
            report("WARN", f"skill {name}", "links to another cca install (cca install skills)")
        else:
            report("OK", f"skill {name}", str(dest))
