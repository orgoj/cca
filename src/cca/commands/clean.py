"""cca clean: delete old entries of the project's tmp/ (plan by default).

Each top-level entry of tmp/ is one unit: a file or link by its own mtime, a directory
by the newest mtime anywhere inside it, so a directory with recent work is kept whole.
Links are never followed; cloudflare.export_dir (rollback snapshots) and [clean] keep
are never deleted.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import time
from pathlib import Path

from cca import config, validate
from cca.output import CcaError

DAYS_MAX = 3650
PLAN_END = "PLAN - nothing deleted (add --apply to delete)"

EPILOG = """\
Only <config dir>/tmp is cleaned. A top-level file or link is old when its mtime is
older than DAYS; a top-level directory only when its newest file or subdirectory is.
Kept always: [clean] keep names and the directory of cloudflare.export_dir.

exit status: 0 done; 1 an entry could not be read or deleted; 2 usage or config error.

examples:
  cca clean
  cca clean --days 60 --apply"""


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.epilog = EPILOG
    parser.add_argument(
        "--days", type=int, metavar="N", help="older than N days (1-3650, default clean.days)"
    )
    parser.add_argument("--apply", action="store_true", help="delete (default: plan)")


def _newest(path: Path, device: int) -> tuple[float, int]:
    """(newest mtime, total size) of a directory tree; OSError when a part is unreadable
    or another filesystem is mounted inside."""
    top = os.lstat(path)
    if top.st_dev != device:  # a mount point itself: rmtree would empty that filesystem
        raise OSError(f"{path} is another filesystem")
    newest, size = top.st_mtime, 0
    for current, dirs, files in os.walk(path, followlinks=False, onerror=_raise):
        for name in dirs + files:
            st = os.lstat(os.path.join(current, name))
            if st.st_dev != device:  # mounted directory or bind-mounted file
                raise OSError(f"{os.path.join(current, name)} is another filesystem")
            newest = max(newest, st.st_mtime)
            size += 0 if stat.S_ISDIR(st.st_mode) else st.st_size
    return newest, size


def _raise(error: OSError) -> None:
    raise error


def _protected(cfg: config.Config, root: Path) -> set[str]:
    keep = set(cfg.data["clean"]["keep"])
    export = os.path.realpath(cfg.resolve(cfg.data["cloudflare"]["export_dir"]))
    real_root = os.path.realpath(root)
    if export == real_root:
        raise CcaError(
            f"{cfg.path}: cloudflare.export_dir is tmp/ itself: cca clean would delete the "
            "rollback snapshots; set a subdirectory such as tmp/cloudflare"
        )
    if Path(export).is_relative_to(real_root):
        keep.add(Path(export).relative_to(real_root).parts[0])
    return keep


def _mb(size: int) -> str:
    return f"{size / 1048576:.1f} MB"


def run(args: argparse.Namespace) -> int:
    cfg = config.require(args.config)
    days = cfg.data["clean"]["days"] if args.days is None else args.days
    if not 1 <= days <= DAYS_MAX:
        raise CcaError(f"--days must be an integer 1-{DAYS_MAX}")
    root = cfg.dir / "tmp"
    if not os.path.lexists(root):
        print(f"nothing to clean: {root} does not exist")
        return 0
    if root.is_symlink() or not root.is_dir():
        raise CcaError(f"{root} is not a directory (a link is never followed)")
    keep = _protected(cfg, root)
    device = os.lstat(root).st_dev
    now = time.time()
    code = 0
    deleted = kept = 0
    freed = 0
    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        name = validate.display(entry.name)
        path = Path(entry.path)
        if entry.name in keep:
            print(f"KEEP {name} (protected)")
            kept += 1
            continue
        try:
            st = os.lstat(path)
            if stat.S_ISDIR(st.st_mode):
                newest, size = _newest(path, device)
            else:
                newest, size = st.st_mtime, st.st_size
        except OSError as e:
            print(f"KEEP {name} (cannot read: {validate.display(str(e))})")
            kept += 1
            code = 1
            continue
        age = max(0, int((now - newest) // 86400))
        if now - newest <= days * 86400:
            print(f"KEEP {name} {age}d")
            kept += 1
            continue
        print(f"DELETE {name} {age}d {_mb(size)}")
        if args.apply:
            try:
                if stat.S_ISDIR(st.st_mode):
                    shutil.rmtree(path)  # never follows links inside
                else:
                    os.unlink(path)
            except OSError as e:
                print(f"  failed: {validate.display(str(e))}")
                code = 1
                continue
        deleted += 1
        freed += size
    print(f"--- delete={deleted} ({_mb(freed)}) keep={kept} ---")
    if not args.apply:
        print(PLAN_END)
    return code
