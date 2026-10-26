"""cca checkouts: branch, HEAD, uncommitted changes and missing commits, read-only."""

import subprocess
from pathlib import Path

import pytest

from cca.cli import main


def git(path: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def commit(path: Path, name: str, subject: str) -> str:
    (path / name).write_text(subject + "\n")
    git(path, "add", name)
    git(path, "commit", "-q", "-m", subject)
    return git(path, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """Three clones a, b, c of one repository on the same commit."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "test@example.com")
    origin = tmp_path / "a"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    commit(origin, "base.txt", "base")
    for name in ("b", "c"):
        git(tmp_path, "clone", "-q", str(origin), name)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file under root including .git, to prove nothing was written."""
    return {str(p): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_identical_and_clean_exit_0(repos, capsys):
    before = snapshot(repos)
    assert main(["checkouts", "a", "b", "c"]) == 0
    out = capsys.readouterr().out
    head = git(repos / "a", "rev-parse", "HEAD")[:12]
    assert f"    main {head} clean" in out
    assert "[1] lacks 0" in out and "[3] lacks 0" in out
    assert out.endswith(f"IN SYNC: identical HEAD {head}, all clean\n")
    assert snapshot(repos) == before


def test_diverged_lists_missing_commits_and_changes(repos, capsys):
    only_a = commit(repos / "a", "a.txt", "fix in a")
    only_b = commit(repos / "b", "b.txt", "feature in b")
    (repos / "c" / "base.txt").write_text("edited\n")
    (repos / "c" / "new.txt").write_text("new\n")
    before = snapshot(repos)
    assert main(["checkouts", "a", "b", "c"]) == 1
    out = capsys.readouterr().out
    assert "    main " in out and "2 uncommitted" in out
    assert "     M base.txt" in out and "    ?? new.txt" in out
    lines = out.splitlines()
    a = lines.index("[1] lacks 1")
    assert lines[a + 1] == f"    {only_b[:12]} feature in b (in [2])"
    c = lines.index("[3] lacks 2")
    assert {lines[c + 1], lines[c + 2]} == {
        f"    {only_a[:12]} fix in a (in [1])",
        f"    {only_b[:12]} feature in b (in [2])",
    }
    assert lines[-1] == "DIVERGED: 3 different HEADs, uncommitted changes in [3]"
    assert snapshot(repos) == before


def test_same_head_but_dirty_exit_1(repos, capsys):
    (repos / "b" / "base.txt").write_text("edited\n")
    assert main(["checkouts", "a", "b"]) == 1
    assert capsys.readouterr().out.endswith("DIVERGED: uncommitted changes in [2]\n")


def test_detached_head_and_unrelated_history(repos, capsys):
    git(repos / "b", "checkout", "-q", "--detach")
    other = repos / "other"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    commit(other, "x.txt", "unrelated")
    assert main(["checkouts", "b", "other"]) == 1
    out = capsys.readouterr().out
    assert "    (detached) " in out
    assert "WARN no common commit: these checkouts do not share history" in out


def test_long_lists_are_capped(repos, capsys):
    for i in range(35):
        (repos / "a" / f"f{i:02}.txt").write_text("x")
    assert main(["checkouts", "a", "b"]) == 1
    out = capsys.readouterr().out
    assert "    ?? f29.txt" in out and "f30.txt" not in out and "    ... 5 more" in out


def test_usage_errors_exit_2(repos, capsys):
    (repos / "plain").mkdir()
    assert main(["checkouts", "a"]) == 2
    assert "at least two checkouts" in capsys.readouterr().err
    assert main(["checkouts", "a", "plain"]) == 2
    assert "plain: git rev-parse failed: " in capsys.readouterr().err
    assert main(["checkouts", "a", str(repos / "a")]) == 2
    assert "the same checkout is given twice" in capsys.readouterr().err


def test_untrusted_fsmonitor_is_never_run(repos, capsys):
    marker = repos / "ran"
    git(repos / "b", "config", "core.fsmonitor", f"touch {marker}")
    (repos / "b" / "base.txt").write_text("edited\n")
    assert main(["checkouts", "a", "b"]) == 1
    assert not marker.exists()
