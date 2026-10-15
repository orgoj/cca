"""cca install skills and cca doctor: link ownership, idempotence, cleanup."""

import json
import os
from pathlib import Path

import pytest

from cca import skilllinks
from cca.cli import main


@pytest.fixture
def target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / ".claude" / "skills"
    path.mkdir(parents=True)
    return path


def manifest(target: Path) -> dict:
    return json.loads((target / skilllinks.MANIFEST).read_text())["links"]


def other_install(tmp_path: Path) -> Path:
    """Skills dir of another cca install (marker + skill dir)."""
    skills = tmp_path / "other-install" / "cca" / "skills"
    (skills / "cca").mkdir(parents=True)
    (skills / "cca" / "SKILL.md").write_text("old\n")
    (skills / skilllinks.MARKER).write_text("marker\n")
    return skills


def test_install_links_and_records(target, capsys):
    assert main(["install", "skills"]) == 0
    source = skilllinks.package_dir() / "cca"
    assert os.readlink(target / "cca") == str(source)
    assert (target / "cca" / "SKILL.md").is_file()
    assert manifest(target) == {"cca": str(source)}
    assert f"linked: {target / 'cca'}" in capsys.readouterr().out


def test_install_is_idempotent(target, capsys):
    assert main(["install", "skills", "cca"]) == 0
    assert main(["install", "skills", "cca"]) == 0
    assert "unchanged:" in capsys.readouterr().out.splitlines()[-1]


def test_install_into_explicit_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agents").mkdir()
    assert main(["install", "skills", "--target", "agents"]) == 0
    assert (tmp_path / "agents" / "cca").is_symlink()


def test_missing_target_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["install", "skills"]) == 2
    assert "skills directory does not exist" in capsys.readouterr().err
    assert not (tmp_path / ".claude").exists()


@pytest.mark.parametrize("name", ["../escape", "/abs/cca", "cca/..", "nope", ".."])
def test_name_must_be_a_packaged_skill(target, name, capsys):
    assert main(["install", "skills", name]) == 2
    assert "unknown skill" in capsys.readouterr().err
    assert os.listdir(target) == []
    assert os.listdir(target.parent) == ["skills"]


def test_replaces_recorded_broken_link(target):
    (target / "cca").symlink_to("/nonexistent/old-install/skills/cca")
    (target / skilllinks.MANIFEST).write_text(
        json.dumps({"version": 1, "links": {"cca": "/nonexistent/old-install/skills/cca"}})
    )
    assert main(["install", "skills"]) == 0
    assert (target / "cca" / "SKILL.md").is_file()


def test_replaces_live_link_to_other_install_without_touching_it(target, tmp_path):
    old = other_install(tmp_path)
    (target / "cca").symlink_to(old / "cca")
    assert main(["install", "skills"]) == 0
    assert os.readlink(target / "cca") == str(skilllinks.package_dir() / "cca")
    assert (old / "cca" / "SKILL.md").read_text() == "old\n"


def skipped(target, capsys) -> str:
    assert main(["install", "skills"]) == 1
    out = capsys.readouterr().out
    assert "skipped:" in out
    assert not (target / skilllinks.MANIFEST).exists()
    return out


def test_foreign_live_link_untouched(target, tmp_path, capsys):
    foreign = tmp_path / "elsewhere" / "cca"
    foreign.mkdir(parents=True)
    (target / "cca").symlink_to(foreign)
    assert "is a link not owned by cca" in skipped(target, capsys)
    assert os.readlink(target / "cca") == str(foreign)
    assert os.listdir(foreign) == []


def test_foreign_broken_link_untouched(target, capsys):
    (target / "cca").symlink_to("/nonexistent/cca")
    skipped(target, capsys)
    assert os.readlink(target / "cca") == "/nonexistent/cca"


def test_marker_adjacent_foreign_targets_untouched(target, tmp_path, capsys):
    old = other_install(tmp_path)
    (old / "other").mkdir()
    (target / "cca").symlink_to(old / "other")
    skipped(target, capsys)
    (target / "cca").unlink()
    (old / "cca" / "sub").mkdir()
    (target / "cca").symlink_to(old / "cca" / "sub")
    skipped(target, capsys)
    assert os.readlink(target / "cca") == str(old / "cca" / "sub")


def test_manifest_with_other_link_text_does_not_own(target, capsys):
    (target / "cca").symlink_to("/nonexistent/foreign")
    (target / skilllinks.MANIFEST).write_text(
        json.dumps({"version": 1, "links": {"cca": "/nonexistent/recorded"}})
    )
    assert main(["install", "skills"]) == 1
    assert os.readlink(target / "cca") == "/nonexistent/foreign"


@pytest.mark.parametrize("kind", ["dir", "file"])
def test_real_skill_untouched(target, kind, capsys):
    if kind == "dir":
        (target / "cca").mkdir()
    else:
        (target / "cca").write_text("mine\n")
    skipped(target, capsys)
    assert (target / "cca").is_symlink() is False


def test_symlinked_manifest_refused(target, tmp_path, capsys):
    (tmp_path / "real.json").write_text('{"links": {}}')
    (target / skilllinks.MANIFEST).symlink_to(tmp_path / "real.json")
    assert main(["install", "skills"]) == 2
    assert "not a regular file" in capsys.readouterr().err
    assert (tmp_path / "real.json").read_text() == '{"links": {}}'


def test_manifest_write_never_follows_planted_temp_links(target, tmp_path):
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("keep\n")
    for name in (f"{skilllinks.MANIFEST}.tmp-{os.getpid()}", f"{skilllinks.MANIFEST}.tmp"):
        (target / name).symlink_to(sentinel)
    assert main(["install", "skills"]) == 0
    assert sentinel.read_text() == "keep\n"
    assert manifest(target) == {"cca": str(skilllinks.package_dir() / "cca")}


def no_space(*args, **kwargs):
    raise OSError(28, "No space left on device")


def test_manifest_failure_removes_new_link(target, monkeypatch, capsys):
    monkeypatch.setattr(skilllinks.tempfile, "mkstemp", no_space)
    assert main(["install", "skills"]) == 2
    assert "cannot write" in capsys.readouterr().err
    assert os.listdir(target) == []


def test_manifest_failure_restores_replaced_link(target, tmp_path, monkeypatch, capsys):
    old = other_install(tmp_path)
    (target / "cca").symlink_to(old / "cca")
    monkeypatch.setattr(skilllinks.tempfile, "mkstemp", no_space)
    assert main(["install", "skills"]) == 2
    assert os.readlink(target / "cca") == str(old / "cca")
    assert os.listdir(target) == ["cca"]


def test_no_symlink_support(target, monkeypatch, capsys):
    def unsupported(*args, **kwargs):
        raise NotImplementedError

    monkeypatch.setattr(os, "symlink", unsupported)
    assert main(["install", "skills"]) == 2
    assert "cannot create symlinks on this system" in capsys.readouterr().err
    assert os.listdir(target) == []


# --- doctor


@pytest.fixture
def ready(target, tmp_path, monkeypatch):
    """A project that passes every doctor check."""
    (tmp_path / ".cca.toml").write_text('schema_version = 1\n[run.log]\noperator = "admin1"\n')
    for d in ("cca/guides", "cca/incidents", "logs"):
        (tmp_path / d).mkdir(parents=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "sops").write_text("#!/bin/sh\nexit 1\n")
    (bindir / "sops").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    assert main(["install", "skills"]) == 0
    return tmp_path


def test_doctor_ready_project(ready, capsys):
    capsys.readouterr()
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and "WARN" not in out
    assert f"OK   config: {ready / '.cca.toml'}" in out


def test_doctor_empty_dir_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "/nonexistent")
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    for line in ("FAIL config:", "WARN sops:", "FAIL directories:", "FAIL skills:"):
        assert line in out


def test_doctor_invalid_config_and_missing_log_dir(ready, capsys):
    (ready / "logs").rmdir()
    assert main(["doctor"]) == 1
    assert "FAIL run.log.dir:" in capsys.readouterr().out
    (ready / ".cca.toml").write_text("schema_version = 2\n")
    assert main(["doctor"]) == 1
    assert "FAIL config:" in capsys.readouterr().out


def test_doctor_fix_removes_only_recorded_broken_links(ready, capsys):
    target = ready / ".claude" / "skills"
    (target / "cca").unlink()
    (target / "cca").symlink_to("/nonexistent/cca-install/skills/cca")
    data = {"version": 1, "links": {"cca": "/nonexistent/cca-install/skills/cca"}}
    (target / skilllinks.MANIFEST).write_text(json.dumps(data))
    (target / "foreign").symlink_to("/nonexistent/foreign")
    assert main(["doctor"]) == 1
    assert "broken links (cca doctor --fix): cca" in capsys.readouterr().out
    assert main(["doctor", "--fix"]) == 1  # removed, but the skill is now missing
    out = capsys.readouterr().out
    assert "removed broken links: cca" in out and "not installed" in out
    assert not os.path.lexists(target / "cca")
    assert manifest(target) == {}
    assert os.readlink(target / "foreign") == "/nonexistent/foreign"
