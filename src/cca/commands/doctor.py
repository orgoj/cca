"""cca doctor: is the current project ready for cca."""

from __future__ import annotations

import argparse
import os
import shutil
from importlib.metadata import version
from pathlib import Path

from cca import config, executor, skilllinks, validate
from cca.commands import run as run_command
from cca.commands import watchlist
from cca.commands.install import DEFAULT_TARGET
from cca.output import CcaError

PROJECT_DIRS = ("cca/guides", "cca/incidents")

# agent skill install dirs checked for links into an old CCA tree (doc-2 "Old CCA links")
PROJECT_SKILL_DIRS = (
    ".claude/skills",
    ".agents/skills",
    ".codex/skills",
    ".gemini/skills",
    ".opencode/skills",
    ".cursor/skills",
    ".pi/skills",
    ".github/skills",
)
USER_SKILL_DIRS = (
    ".claude/skills",
    ".agents/skills",
    ".codex/skills",
    ".gemini/skills",
    ".config/opencode/skills",
    ".cursor/skills",
    ".pi/agent/skills",
)


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
    _check_age_key(report, cfg)

    missing = [d for d in PROJECT_DIRS if not os.path.isdir(d)]
    report(
        "FAIL" if missing else "OK",
        "directories",
        ", ".join(missing or PROJECT_DIRS) + (" missing" if missing else ""),
    )

    if cfg is not None:
        _check_run(report, cfg)

    if cfg is not None and "log" in cfg.data["run"]:
        log_dir = cfg.resolve(cfg.data["run"]["log"]["dir"])
        report(
            "OK" if log_dir.is_dir() else "FAIL",
            "run.log.dir",
            str(log_dir) + ("" if log_dir.is_dir() else " missing"),
        )
        try:
            name, source = executor.operator(cfg)
            report("OK", "run.log.operator", f"{name} ({source})")
        except CcaError as e:
            report("FAIL", "run.log.operator", str(e).partition("run.log.operator: ")[2])

    if cfg is not None:
        _check_backlog(report, str(cfg.dir))
    _check_skills(report, args.fix)
    if cfg is not None:
        _check_old_cca(report, cfg.dir)
    return 1 if failed else 0


def _readable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.R_OK)


def _check_age_key(report, cfg: config.Config | None) -> None:
    """Can sops find an age key: the environment cca hands to sops, diagnostics only (cca
    itself reads no setting from it). Paths only, never a key; SOPS_AGE_KEY is never shown."""
    key_file = os.environ.get("SOPS_AGE_KEY_FILE")
    if key_file:
        shown = validate.display(key_file)
        if not _readable_file(key_file):
            report("FAIL", "age key", f"SOPS_AGE_KEY_FILE={shown}: not a readable file")
        elif not os.path.isabs(key_file):
            report("WARN", "age key", f"SOPS_AGE_KEY_FILE={shown} is relative (resolved from the "
                   "current directory, breaks in subdirectories)")  # fmt: skip
        else:
            report("OK", "age key", f"SOPS_AGE_KEY_FILE={shown}")
        return
    for name in ("SOPS_AGE_KEY", "SOPS_AGE_KEY_CMD"):
        if os.environ.get(name):
            report("OK", "age key", f"{name} is set")
            return
    default = Path.home() / ".config" / "sops" / "age" / "keys.txt"
    if _readable_file(str(default)):
        report("OK", "age key", f"{default} (sops default)")
        return
    secrets = [] if cfg is None else [cfg.resolve(p) for p in cfg.data["secrets"].values()]
    present = [str(p) for p in secrets if p.exists()]
    report(
        "FAIL" if present else "WARN",
        "age key",
        "SOPS_AGE_KEY_FILE not set and no sops default key"
        + (f" (needed for {', '.join(present)})" if present else " (needed by secrets)"),
    )


def _check_run(report, cfg: config.Config) -> None:
    """What cca run and the commands using its executor need; nothing without servers."""
    run_cfg = cfg.data["run"]
    servers = cfg.data["servers"]
    if not servers:  # a project without servers is valid, it just does not use cca run
        report("OK", "servers", "none in [servers] (cca run checks skipped)")
        return
    report("OK", "servers", f"{len(servers)} configured")
    report("OK", "run.transport", run_cfg["transport"])
    ssh_path = shutil.which("ssh")
    report("OK" if ssh_path else "FAIL", "ssh", ssh_path or "not on PATH")
    if run_cfg["transport"] == "tmux":
        tmux_path = shutil.which("tmux")
        report("OK" if tmux_path else "FAIL", "tmux", tmux_path or "not on PATH")
        session = run_cfg["tmux"].get("session")
        report(
            "OK" if session else "FAIL",
            "run.tmux.session",
            session or 'not set (required with run.transport = "tmux")',
        )
    if run_cfg["tokf"]:
        found = run_command.tokf_path()
        report(
            "OK" if found else "WARN",
            "tokf",
            found or "not on PATH or no cca-v1 protocol support (output stays unprocessed)",
        )


def _check_backlog(report, project: str) -> None:
    """The register of cca watchlist: backlog CLI and the statuses it relies on."""
    try:
        found = watchlist.run_backlog(project, ["--version"]).strip()
        statuses = watchlist.run_backlog(project, ["config", "get", "statuses"])
    except CcaError as e:
        report("FAIL", "backlog", str(e))
        return
    report("OK", "backlog", validate.display(found[:40]))
    names = {s.strip() for s in statuses.split(",")}
    missing = [s for s in watchlist.REQUIRED_STATUSES if s not in names]
    report(
        "FAIL" if missing else "OK",
        "backlog statuses",
        "missing " + ", ".join(missing) + " (add to the statuses list in backlog/config.yml)"
        if missing
        else ", ".join(watchlist.REQUIRED_STATUSES) + " present",
    )


def _old_root(path: str) -> Path | None:
    """The old CCA tree R containing path (R itself included), if any."""
    for candidate in (Path(path), *Path(path).parents):
        if os.path.isfile(candidate / "lib" / "cca-env.sh") and os.path.isfile(
            candidate / "bin" / "cca-run-on-server"
        ):
            return candidate
    return None


def _old_install(path: str, root: Path) -> bool:
    """True when path lies in <R>/bin or <R>/skills (the installed scripts and skills)."""
    return Path(path).relative_to(root).parts[:1] in (("bin",), ("skills",))


def _old_paths(directory: str) -> list[tuple[str, str]]:
    """(path, realpath) of the dir itself or its direct entries resolving into an old tree.

    Only link metadata is read; no file is opened, no entry is descended into and nothing
    inside an old tree is listed.
    """
    if not os.path.lexists(directory):  # a dangling link exists and is classified below
        return []
    real = os.path.realpath(directory)  # resolves the dir itself and any linked ancestor
    root = _old_root(real)
    if root is not None:
        return [(directory, real)] if _old_install(real, root) else []
    if not os.path.isdir(directory):
        return []
    found = []
    with os.scandir(directory) as entries:
        for entry in sorted(entries, key=lambda e: e.name):
            if entry.is_symlink():
                real = os.path.realpath(entry.path)  # dangling: resolved from the link text
                root = _old_root(real)
                if root is not None and _old_install(real, root):
                    found.append((entry.path, real))
    return found


def _check_old_cca(report, project: Path) -> None:
    """Old cca-* scripts or skills still linked: FAIL in the project, WARN when shared."""
    dirs: dict[str, str] = {}
    for rel in PROJECT_SKILL_DIRS:
        dirs.setdefault(os.path.abspath(project / rel), "FAIL")
    home = Path.home()
    for rel in USER_SKILL_DIRS:
        dirs.setdefault(os.path.abspath(home / rel), "WARN")
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        dirs.setdefault(os.path.abspath(entry or os.curdir), "WARN")  # empty entry = CWD
    clean = True
    for directory, status in dirs.items():
        try:
            found = _old_paths(directory)
        except OSError as e:
            clean = False
            report(status, "old cca", f"cannot list {directory}: {e.strerror}")
            continue
        for path, real in found:
            clean = False
            report(status, "old cca", f"{path} -> {real}")
    if clean:
        report("OK", "old cca", f"no links to old scripts or skills in {len(dirs)} dirs")


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
