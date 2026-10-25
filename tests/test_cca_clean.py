"""cca clean: only old top-level entries of tmp/, links never followed, plan by default."""

import os
import time
from pathlib import Path

import pytest

from cca.cli import main

DAY = 86400


def age(path: Path, days: float) -> None:
    t = time.time() - days * DAY
    os.utime(path, (t, t), follow_symlinks=False)


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".cca.toml").write_text("schema_version = 1\n")
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    (tmp / "old.log").write_text("x" * 10)
    age(tmp / "old.log", 40)
    (tmp / "new.log").write_text("x")
    age(tmp / "new.log", 2)
    work = tmp / "work"  # old files, one fresh one: unfinished work, kept whole
    (work / "sub").mkdir(parents=True)
    (work / "sub" / "a.md").write_text("a")
    age(work / "sub" / "a.md", 90)
    (work / "b.md").write_text("b")
    age(work / "b.md", 1)
    for p in (work / "sub", work):  # directory mtimes count as activity too
        age(p, 90)
    done = tmp / "done"
    (done / "sub").mkdir(parents=True)
    (done / "sub" / "c.md").write_text("c")
    for p in (done / "sub" / "c.md", done / "sub", done):
        age(p, 50)
    cf = tmp / "cloudflare"
    cf.mkdir()
    (cf / "example.com+20260101t000000z.dns.json").write_text("{}")
    for p in (*cf.iterdir(), cf):
        age(p, 300)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(capsys, *argv):
    code = main(["clean", *argv])
    return code, capsys.readouterr().out


def test_plan_lists_and_deletes_nothing(project, capsys):
    code, out = run(capsys)
    assert code == 0
    lines = out.splitlines()
    assert "KEEP cloudflare (protected)" in lines
    assert any(line.startswith("DELETE done 50d") for line in lines)
    assert any(line.startswith("DELETE old.log 40d") for line in lines)
    assert "KEEP new.log 2d" in lines and "KEEP work 1d" in lines
    assert "--- delete=2 (0.0 MB) keep=3 ---" in lines
    assert lines[-1] == "PLAN - nothing deleted (add --apply to delete)"
    assert (project / "tmp" / "old.log").exists() and (project / "tmp" / "done").exists()


def test_apply_deletes_only_old_entries(project, capsys):
    code, _ = run(capsys, "--apply")
    assert code == 0
    assert sorted(p.name for p in (project / "tmp").iterdir()) == ["cloudflare", "new.log", "work"]
    assert (project / "tmp" / "work" / "sub" / "a.md").exists()


def test_days_option_and_config(project, capsys):
    code, out = run(capsys, "--days", "1")
    assert "DELETE new.log 2d" in out and "DELETE work 1d" in out  # newest just over 1 day
    (project / ".cca.toml").write_text("schema_version = 1\n[clean]\ndays = 60\nkeep = ['done']\n")
    code, out = run(capsys)
    assert "KEEP old.log 40d" in out and "KEEP done (protected)" in out and "delete=0" in out
    assert main(["clean", "--days", "0"]) == 2


def test_links_are_never_followed(project, tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("precious")
    link = project / "tmp" / "link"
    link.symlink_to(outside)
    age(link, 100)
    inner = project / "tmp" / "done" / "inner-link"
    inner.symlink_to(outside / "keep.txt")
    for p in (inner, inner.parent):
        age(p, 100)
    code, out = run(capsys, "--apply")
    assert code == 0 and "DELETE link 100d" in out
    assert not os.path.lexists(link) and not (project / "tmp" / "done").exists()
    assert (outside / "keep.txt").read_text() == "precious"


def test_export_dir_outside_default_is_protected(project, capsys):
    (project / ".cca.toml").write_text(
        "schema_version = 1\n[cloudflare]\nexport_dir = 'tmp/done/cf'\n"
    )
    code, out = run(capsys)
    assert "KEEP done (protected)" in out and "KEEP cloudflare" not in out
    (project / ".cca.toml").write_text("schema_version = 1\n[cloudflare]\nexport_dir = 'tmp'\n")
    assert main(["clean"]) == 2
    assert "cloudflare.export_dir is tmp/ itself" in capsys.readouterr().err


def test_unreadable_entry_is_kept_exit_1(project, capsys):
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    locked = project / "tmp" / "done" / "sub"
    locked.chmod(0)
    try:
        code, out = run(capsys, "--apply")
    finally:
        locked.chmod(0o755)
    assert code == 1 and "KEEP done (cannot read:" in out and (project / "tmp" / "done").exists()


def test_entry_on_another_filesystem_is_kept(project, monkeypatch, capsys):
    """A mount point at the top or inside: never walked into, never deleted."""
    real = os.lstat
    mounted = {str(project / "tmp" / "done"), str(project / "tmp" / "old.log")}

    class Other:
        def __init__(self, st):
            self._st = st

        def __getattr__(self, name):
            return self._st.st_dev + 1 if name == "st_dev" else getattr(self._st, name)

    monkeypatch.setattr(
        os, "lstat", lambda p, *a, **k: Other(real(p)) if str(p) in mounted else real(p)
    )
    code, out = run(capsys, "--apply")
    assert code == 1 and "KEEP done (cannot read:" in out and "another filesystem" in out
    assert (project / "tmp" / "done" / "sub" / "c.md").exists()


def test_missing_or_linked_tmp(tmp_path, monkeypatch, capsys):
    (tmp_path / ".cca.toml").write_text("schema_version = 1\n")
    monkeypatch.chdir(tmp_path)
    code, out = run(capsys)
    assert code == 0 and "nothing to clean" in out
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "tmp").symlink_to(tmp_path / "elsewhere")
    assert main(["clean"]) == 2
    assert "is not a directory (a link is never followed)" in capsys.readouterr().err
