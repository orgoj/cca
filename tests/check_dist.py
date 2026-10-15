#!/usr/bin/env python3
"""Release content checks used by tests/test-package.sh.

Usage:
    tests/check_dist.py dist DISTDIR OUTDIR   check wheel + sdist listings, extract into OUTDIR
    tests/check_dist.py skills SKILLSDIR COMMAND...
        every `cca <word>` anywhere in the installed skills (bare `cca` in prose goes in
        backticks) must name a provided COMMAND or a global option; no legacy command names

Exit codes: 0 = ok, 1 = check failed, 2 = usage error.
"""

import re
import sys
import tarfile
import zipfile
from pathlib import Path

WHEEL_REQUIRED = [
    "cca/__init__.py",
    "cca/cli.py",
    "cca/skills/.cca-skills",
    "cca/skills/cca/SKILL.md",
]
SDIST_TOP_FILES = {"pyproject.toml", "README.md", "PKG-INFO", ".gitignore"}
# old scripts (bin/ at legacy-baseline) and the removed experiment; ".cca-skills" is
# a file name, not a command, hence the lookbehind
LEGACY_RE = re.compile(r"(?<![\w.-])(cca-[a-z][a-z0-9-]*|asn-wrap|tmux-cli-python|tmux_cli_python)")
CCA_CALL_RE = re.compile(r"(?<![\w.-])cca[ \t]+([a-z-][\w-]*)")
GLOBAL_OPTIONS = {"--version", "--config", "--help", "-h"}


def fail(errors: list[str]) -> int:
    for e in errors:
        print(f"FAIL: {e}")
    return 1 if errors else 0


def check_dist(dist: Path, out: Path) -> int:
    wheels = sorted(dist.glob("cca-*.whl"))
    sdists = sorted(dist.glob("cca-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        return fail([f"expected one wheel and one sdist in {dist}"])
    errors = []
    with zipfile.ZipFile(wheels[0]) as z:
        names = z.namelist()
        for required in WHEEL_REQUIRED:
            if required not in names:
                errors.append(f"wheel lacks {required}")
        for name in names:
            top = name.split("/")[0]
            if top != "cca" and not top.endswith(".dist-info"):
                errors.append(f"wheel ships {name} outside the cca package")
        entry = [n for n in names if n.endswith(".dist-info/entry_points.txt")]
        if not entry or "cca = cca.cli:main" not in z.read(entry[0]).decode():
            errors.append("wheel has no console script cca = cca.cli:main")
        z.extractall(out / "wheel")
    with tarfile.open(sdists[0]) as t:
        members = t.getmembers()
        root = sdists[0].name.removesuffix(".tar.gz")
        for m in members:
            rel = m.name.removeprefix(root + "/")
            if rel not in SDIST_TOP_FILES and not rel.startswith("src/cca/"):
                errors.append(f"sdist ships {rel}")
            if not m.isfile():
                errors.append(f"sdist member {rel} is not a regular file")
        if f"{root}/src/cca/skills/cca/SKILL.md" not in [m.name for m in members]:
            errors.append("sdist lacks src/cca/skills/cca/SKILL.md")
        if not errors:
            t.extractall(out / "sdist", filter="data")
    return fail(errors)


def check_skills(skills: Path, commands: list[str]) -> int:
    errors = []
    allowed = set(commands) | GLOBAL_OPTIONS
    files = sorted(p for p in skills.rglob("*") if p.is_file())
    if not any(p.name == "SKILL.md" for p in files):
        errors.append(f"no SKILL.md under {skills}")
    for path in files:
        text = path.read_text()
        rel = path.relative_to(skills)
        for m in LEGACY_RE.finditer(text):
            errors.append(f"{rel}: legacy command name {m.group(1)}")
        for m in CCA_CALL_RE.finditer(text):
            if m.group(1) not in allowed:
                errors.append(f"{rel}: `cca {m.group(1)}` is not a provided command")
    return fail(errors)


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "dist":
        return check_dist(Path(argv[1]), Path(argv[2]))
    if len(argv) >= 3 and argv[0] == "skills":
        return check_skills(Path(argv[1]), argv[2:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
