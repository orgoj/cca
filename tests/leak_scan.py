#!/usr/bin/env python3
"""Leak scan of this repo or a built dist against a project denylist.

Usage:
    tests/leak_scan.py DENYLIST --repo REPO [PATH...]   git-tracked files (under PATHs)
    tests/leak_scan.py DENYLIST --dir DIR               every file under DIR (built dists)

DENYLIST: one file, or several joined by ':' (os.pathsep), one per consumer project; each
holds one case-insensitive regex per line, '#' comments. Every file must exist and hold a
pattern. Exit codes: 0 = clean, 1 = leak found, 2 = usage/runtime error.
"""

import os
import re
import stat
import subprocess
import sys
from pathlib import Path


def die(message: str):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(2)


def load_all(denylists: str) -> list[re.Pattern]:
    """Patterns of every file in a pathsep-joined list; an empty entry is an error."""
    paths = denylists.split(os.pathsep)
    if not all(paths):
        die(f"empty entry in denylist list '{denylists}'")
    return [p for path in paths for p in load_patterns(Path(path))]


def load_patterns(denylist: Path) -> list[re.Pattern]:
    try:
        lines = denylist.read_text().splitlines()
    except OSError as e:
        die(f"cannot read denylist {denylist}: {e.strerror}")
    patterns = []
    for lineno, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line, re.IGNORECASE))
        except re.error as e:
            die(f"bad regex in {denylist}:{lineno} ({e})")
    if not patterns:
        die(f"denylist {denylist} has no patterns")
    return patterns


def tracked(repo: Path, paths: list[str]) -> list[Path]:
    proc = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--", *paths],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        die(f"git ls-files failed in {repo}: {proc.stderr.strip()}")
    files = [repo / f for f in proc.stdout.split("\0") if f]
    if not files:
        die(f"no tracked files under {' '.join(paths)} in {repo}")
    return files


def walk(base: Path) -> list[Path]:
    """Every file and symlink under base; directory links are listed, never entered."""
    found = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            if path.is_symlink() or name in filenames:
                found.append(path)
    if not found:
        die(f"no files under {base}")
    return sorted(found)


def content(path: Path) -> str:
    """A regular file's text or a symlink's link text; never follows links."""
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            return os.readlink(path)
        if stat.S_ISREG(mode):
            return path.read_text(errors="replace")
    except FileNotFoundError:
        die(f"{path} is tracked but missing from the work tree (stage its deletion)")
    except OSError as e:
        die(f"cannot read {path}: {e.strerror}")
    die(f"{path} is neither a regular file nor a symlink")


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in ("--repo", "--dir"):
        die(__doc__)
    patterns = load_all(argv[0])
    base = Path(argv[2]).resolve()
    files = tracked(base, argv[3:] or ["."]) if argv[1] == "--repo" else walk(base)
    hits = []
    for path in files:
        text = content(path)
        rel = path.relative_to(base)
        if any(p.search(str(rel)) for p in patterns):
            hits.append(f"{rel}: (file name)")
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(p.search(line) for p in patterns):
                hits.append(f"{rel}:{lineno}: {line.strip()[:100]}")
    if hits:
        print(f"LEAK: denylisted names found ({argv[0]})")
        for h in hits:
            print(f"  {h}")
        return 1
    print(f"clean: {len(files)} files under {base} against {argv[0]} ({len(patterns)} patterns)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
