"""cca checkouts: compare local checkouts of one repository (read-only).

Prints per checkout its branch, HEAD and uncommitted changes, then the commits each one
lacks compared with the others. Nothing is fetched, merged, pushed or written: git runs
without optional locks (no index refresh) and without fsmonitor hooks.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess

from cca import validate
from cca.output import CcaError

SHOW_MAX = 30  # changed files / missing commits listed per checkout
TIMEOUT = 120

EPILOG = """\
Commits are compared by hash over everything reachable from each HEAD, so a cherry-pick
or rebased copy of a commit counts as a different commit. Remotes are not fetched:
compare the local checkouts as they are.

exit status: 0 all on the identical HEAD and clean; 1 HEADs differ or a checkout has
uncommitted changes; 2 usage error, a path that is not a git checkout, or git missing.

examples:
  cca checkouts ../repo-a/lib ../repo-b/lib ../repo-c/lib"""


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.epilog = EPILOG
    parser.add_argument("paths", nargs="+", metavar="PATH", help="git checkouts (2 or more)")


def _git(path: str, *args: str) -> str:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    command = ["git", "--no-pager", "-c", "core.fsmonitor=false", "-C", path, *args]
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, env=env, timeout=TIMEOUT, check=False
        )
    except subprocess.TimeoutExpired:
        raise CcaError(f"{validate.display(path)}: git {args[0]} timed out", 1) from None
    if done.returncode != 0:
        detail = validate.display(done.stderr.strip().splitlines()[-1] if done.stderr else "")
        raise CcaError(f"{validate.display(path)}: git {args[0]} failed: {detail}")
    return done.stdout


class Checkout:
    def __init__(self, label: str, path: str):
        self.label = label
        self.path = path
        if _git(path, "rev-parse", "--is-inside-work-tree").strip() != "true":
            raise CcaError(f"{validate.display(path)}: not a git work tree")
        self.top = os.path.realpath(_git(path, "rev-parse", "--show-toplevel").strip())
        self.head = _git(path, "rev-parse", "--verify", "HEAD^{commit}").strip()
        self.branch = _git(path, "branch", "--show-current").strip() or "(detached)"
        status = _git(path, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
        self.changes = _entries(status)
        log = _git(path, "log", "-z", "--format=%H %s", "HEAD")
        self.commits: dict[str, str] = {}  # hash -> subject, newest first
        for record in log.split("\0"):
            if record:
                sha, _, subject = record.partition(" ")
                self.commits[sha] = subject


def _entries(status: str) -> list[str]:
    """`XY path` per change; a rename's original path (the next -z field) is skipped."""
    out = []
    fields = iter(status.split("\0"))
    for field in fields:
        if not field:
            continue
        out.append(field)
        if field[:1] in ("R", "C"):
            next(fields, None)
    return out


def _listing(items: list[str]) -> list[str]:
    lines = [f"    {validate.display(item)}" for item in items[:SHOW_MAX]]
    if len(items) > SHOW_MAX:
        lines.append(f"    ... {len(items) - SHOW_MAX} more")
    return lines


def run(args: argparse.Namespace) -> int:
    if len(args.paths) < 2:
        raise CcaError("give at least two checkouts to compare")
    if shutil.which("git") is None:
        raise CcaError("git not found on PATH")
    checkouts = [Checkout(f"[{i}]", path) for i, path in enumerate(args.paths, 1)]
    tops = [c.top for c in checkouts]
    if len(set(tops)) != len(tops):
        raise CcaError("the same checkout is given twice")

    for c in checkouts:
        state = f"{len(c.changes)} uncommitted" if c.changes else "clean"
        print(f"{c.label} {validate.display(c.path)}")
        print(f"    {validate.display(c.branch)} {c.head[:12]} {state}")
        for line in _listing(c.changes):
            print(line)

    common = set.intersection(*(set(c.commits) for c in checkouts))
    if not common:
        print("WARN no common commit: these checkouts do not share history")
    union: dict[str, str] = {}
    for c in checkouts:
        for sha, subject in c.commits.items():
            union.setdefault(sha, subject)
    print("--- missing commits ---")
    for c in checkouts:
        missing = [sha for sha in union if sha not in c.commits]
        print(f"{c.label} lacks {len(missing)}")
        rows = []
        for sha in missing:
            have = " ".join(o.label for o in checkouts if sha in o.commits)
            rows.append(f"{sha[:12]} {union[sha]} (in {have})")
        for line in _listing(rows):
            print(line)

    heads = {c.head for c in checkouts}
    dirty = [c.label for c in checkouts if c.changes]
    if len(heads) == 1 and not dirty:
        print(f"IN SYNC: identical HEAD {checkouts[0].head[:12]}, all clean")
        return 0
    problems = []
    if len(heads) > 1:
        problems.append(f"{len(heads)} different HEADs")
    if dirty:
        problems.append("uncommitted changes in " + " ".join(dirty))
    print("DIVERGED: " + ", ".join(problems))
    return 1
