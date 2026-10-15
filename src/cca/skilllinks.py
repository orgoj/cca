"""Skill links into agent skill dirs: which links cca owns, install and cleanup.

A destination link is owned by cca when
- the manifest TARGET/.cca-skills.json records its exact link text (also proves a
  broken link was created by cca), or
- it is live and resolves to `<dir with MARKER>/<name>`, i.e. the same skill of any
  installed cca package.
Nothing else is replaced or removed; existing destination links are never followed
for writing.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from cca import validate
from cca.output import CcaError

MANIFEST = ".cca-skills.json"
MARKER = ".cca-skills"


def package_dir() -> Path:
    """The installed package's skills directory as a real filesystem path."""
    skills = resources.files("cca") / "skills"
    if not isinstance(skills, Path) or not (skills / MARKER).is_file():
        raise CcaError("the installed cca has no skills directory on the filesystem")
    return Path(os.path.abspath(skills))


def packaged_names() -> list[str]:
    root = package_dir()
    return sorted(p.name for p in root.iterdir() if (p / "SKILL.md").is_file())


def check_target(target: str | os.PathLike) -> Path:
    path = Path(os.path.abspath(target))
    if not path.is_dir():
        raise CcaError(f"skills directory does not exist: {path} (create it first)")
    return path


def read_manifest(target: Path) -> dict[str, str]:
    path = target / MANIFEST
    if not os.path.lexists(path):
        return {}
    if path.is_symlink() or not path.is_file():
        raise CcaError(f"{path} is not a regular file; refusing to use it")
    try:
        links = json.loads(path.read_text()).get("links")
    except (OSError, ValueError, AttributeError):
        links = None
    if not isinstance(links, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in links.items()
    ):
        raise CcaError(f"{path} is not a valid cca skills manifest")
    return links


def write_manifest(target: Path, links: dict[str, str]) -> None:
    path = target / MANIFEST
    if path.is_symlink():
        raise CcaError(f"{path} is a symlink; refusing to write it")
    # a fresh file created exclusively: never writes through a planted link
    fd, tmp = tempfile.mkstemp(prefix=f"{MANIFEST}.", dir=target)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"version": 1, "links": dict(sorted(links.items()))}, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise


def owned(dest: Path, name: str, manifest: dict[str, str]) -> bool:
    if not dest.is_symlink():
        return False
    text = os.readlink(dest)
    if manifest.get(name) == text:
        return True
    resolved = Path(os.path.realpath(dest))
    return resolved.is_dir() and resolved.name == name and (resolved.parent / MARKER).is_file()


@dataclass
class Result:
    name: str
    status: str  # "linked", "unchanged", "replaced", "skipped"
    detail: str = ""


def _symlink(source: Path, dest: Path) -> None:
    """Create or atomically replace dest with a link to source (never follows dest)."""
    tmp = dest.parent / f".{dest.name}.cca-tmp-{os.getpid()}"
    try:
        os.symlink(source, tmp, target_is_directory=True)
    except (OSError, NotImplementedError) as e:
        if isinstance(e, NotImplementedError) or getattr(e, "winerror", None) == 1314:
            raise CcaError("cannot create symlinks on this system; skills need symlinks") from None
        raise CcaError(f"cannot create link {dest}: {e.strerror}") from None
    os.replace(tmp, dest)


def install(target: Path, names: list[str]) -> list[Result]:
    root = package_dir()
    manifest = read_manifest(target)
    results = []
    for name in names:
        source = root / name
        dest = target / name
        if not os.path.lexists(dest):
            _symlink(source, dest)
            status = "linked"
        elif dest.is_symlink() and os.readlink(dest) == str(source):
            status = "unchanged"
        elif owned(dest, name, manifest):
            _symlink(source, dest)
            status = "replaced"
        else:
            kind = "link" if dest.is_symlink() else "directory" if dest.is_dir() else "file"
            results.append(Result(name, "skipped", f"{dest} is a {kind} not owned by cca"))
            continue
        manifest[name] = str(source)
        write_manifest(target, manifest)
        results.append(Result(name, status))
    return results


def broken_owned(target: Path) -> list[str]:
    """Names of recorded links that are broken and still carry the recorded link text."""
    manifest = read_manifest(target)
    return [
        name
        for name, text in manifest.items()
        if validate.is_name(name)
        and (target / name).is_symlink()
        and os.readlink(target / name) == text
        and not (target / name).exists()
    ]


def remove_broken(target: Path, names: list[str]) -> None:
    manifest = read_manifest(target)
    for name in names:
        dest = target / name
        if dest.is_symlink() and os.readlink(dest) == manifest.get(name) and not dest.exists():
            dest.unlink()
            del manifest[name]
    write_manifest(target, manifest)
