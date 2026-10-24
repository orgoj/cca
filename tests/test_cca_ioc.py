"""cca ioc: fake ssh on PATH runs the remote script with a few real tools only."""

import hashlib
import json
import os
import shutil
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cca import executor
from cca.cli import main
from cca.commands import ioc

REMOTE_REAL = (
    "bash", "sh", "base64", "cat", "sed", "grep", "head", "cut", "tr", "ls", "readlink",
    "sha256sum", "ps", "stat", "tail",
)  # fmt: skip
SCRIPT = b"#!/usr/bin/env python3\nprint('host-ioc')\n"
SHA = hashlib.sha256(SCRIPT).hexdigest()


def write_exe(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """PATH = only the fake ssh; the remote side sees only rbin/; state in state/<ssh>/."""
    for d in ("bin", "work", "rbin", "state/host1", "state/host2"):
        (tmp_path / d).mkdir(parents=True)
    for tool in REMOTE_REAL:
        (tmp_path / "rbin" / tool).symlink_to(shutil.which(tool))
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(ioc, "PREFIX", "set -o pipefail; ")
    monkeypatch.setattr(ioc, "STATE_DIR", '"$STATE"')
    write_exe(
        tmp_path / "bin" / "ssh",
        "#!/bin/sh\n"
        '[ "$1" = "--" ] && [ $# -eq 3 ] || exit 99\n'
        'if [ "$2" = fail ]; then echo "ssh: connect to host fail: refused" >&2; exit 255; fi\n'
        f'exec /usr/bin/env -i PATH="{tmp_path}/rbin" STATE="{tmp_path}/state/$2" '
        '/bin/sh -c "$3"\n',
    )
    (tmp_path / "work" / "host-ioc.py").write_bytes(SCRIPT)
    return tmp_path


def project(env: Path, ioc_extra: str = "") -> None:
    (env / "work" / ".cca.toml").write_text(
        "schema_version = 1\n"
        '[servers.server1]\nssh = "host1"\n'
        '[servers.server2]\nssh = "host2"\n'
        '[servers.server3]\nssh = "fail"\n'
        '[run]\ntransport = "tmux"\n'
        f'[ioc]\nhosts = ["server1", "server2"]\nscript = "host-ioc.py"\n{ioc_extra}'
    )


def state(hours_ago: float = 1, **changes) -> dict:
    """The shape host-ioc writes, extra fields (host, mode, started_epoch, counts) included."""
    started = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=hours_ago)
    doc = {
        "version": "1.0",
        "script_sha256": SHA,
        "host": "host1",
        "mode": "quick",
        "started": started.isoformat(timespec="seconds"),
        "started_epoch": started.timestamp(),
        "duration_s": 12.5,
        "modules": {
            "process": {"status": "ok", "duration_s": 1.0, "uncovered": [], "counts": {"p": 3}}
        },
        "findings": [],
    }
    doc.update(changes)
    return doc


def put(env: Path, ssh: str, run: str, doc) -> None:
    text = doc if isinstance(doc, str) else json.dumps(doc, indent=2)
    (env / "state" / ssh / f"last-{run}.json").write_text(text)


def put_ok(env: Path, ssh: str = "host1") -> None:
    put(env, ssh, "quick", state())
    put(env, ssh, "deep", state())


FINDING = {
    "id": "abc123",
    "module": "php_logs",
    "container": "web1",
    "path": "",
    "line": 8,
    "detail": "Allowed memory size exhausted",
    "new": True,
}


# --- status


def test_status_ok(env, capsys):
    project(env)
    put_ok(env)
    put_ok(env, "host2")
    assert main(["ioc", "status"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in out] == [
        "server1 quick", "server1 deep", "server2 quick", "server2 deep",
    ]  # fmt: skip
    assert "(1h ago), 12.5s, version 1.0, findings 0 (0 new)" in out[0]
    assert "WARN" not in "\n".join(out)


def test_status_findings_exit_1(env, capsys):
    project(env)
    put_ok(env)
    put(env, "host1", "deep", state(findings=[FINDING, {**FINDING, "id": "d2", "new": False}]))
    assert main(["ioc", "status", "server1"]) == 1
    assert "findings 2 (1 new)" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("deep", "warning"),
    [
        (state(hours_ago=49), "stale (older than 2x 24h)"),
        (state(script_sha256="0" * 64), "script_sha256 differs from ioc.script"),
        (
            state(modules={"process": {"status": "ok"}, "php_logs": {"status": "uncovered"}}),
            "uncovered: php_logs",
        ),
        (state(started="2026-10-24T03:00:00"), "no valid started time"),
        ("not json", "not a JSON object"),
        ({k: v for k, v in state().items() if k != "findings"}, "findings is not a list"),
        (state(findings={"id": "a"}), "findings is not a list of objects"),
        (state(findings=[FINDING, "x"]), "findings is not a list of objects"),
        ("[1]", "not a JSON object"),
        (None, "cannot read: head:"),
    ],
)
def test_status_warnings_exit_2(env, capsys, deep, warning):
    project(env)
    put(env, "host1", "quick", state())
    if deep is not None:
        put(env, "host1", "deep", deep)
    assert main(["ioc", "status", "server1"]) == 2
    out = capsys.readouterr().out.splitlines()
    assert "WARN" not in out[0]
    assert out[1].startswith("server1 deep: ") and warning in out[1]


def test_status_interval_from_config(env, capsys):
    project(env, "deep_interval_hours = 168\n")
    put(env, "host1", "quick", state())
    put(env, "host1", "deep", state(hours_ago=100))
    assert main(["ioc", "status", "server1"]) == 0


def test_status_host_error_continues(env, capsys):
    project(env)
    text = (env / "work" / ".cca.toml").read_text()
    (env / "work" / ".cca.toml").write_text(text.replace('"server2"]', '"server3", "server2"]'))
    put_ok(env)
    put_ok(env, "host2")
    assert main(["ioc", "status"]) == 2
    out = capsys.readouterr().out.splitlines()
    assert out[2].startswith("server3: ERROR server3: remote command failed (exit 255)")
    assert out[3].startswith("server2 quick: ")


def test_status_needs_script(env, capsys):
    project(env)
    text = (env / "work" / ".cca.toml").read_text().replace('script = "host-ioc.py"\n', "")
    (env / "work" / ".cca.toml").write_text(text)
    assert main(["ioc", "status"]) == 2
    assert "ioc.script: required by this command" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("hosts", "args", "message"),
    [
        ('["server1"]', ["status", "server2"], "'server2' is not in ioc.hosts (server1)"),
        ("[]", ["status"], "ioc.hosts: required by this command but not set"),
        ('["nosuch"]', ["status"], "unknown server 'nosuch'"),
    ],
)
def test_host_selection_errors(env, capsys, hosts, args, message):
    project(env)
    text = (env / "work" / ".cca.toml").read_text()
    (env / "work" / ".cca.toml").write_text(text.replace('["server1", "server2"]', hosts))
    assert main(["ioc", *args]) == 2
    assert message in capsys.readouterr().err


def test_sudo_wraps_remote_script(env, capsys):
    project(env, "sudo = true\n")
    write_exe(
        env / "rbin" / "sudo",
        f'#!/bin/sh\n[ "$1" = -n ] || exit 98\nshift\necho sudo >> "{env}/sudo.log"\nexec "$@"\n',
    )
    put_ok(env)
    assert main(["ioc", "status", "server1"]) == 0
    assert (env / "sudo.log").read_text() == "sudo\n"


@pytest.mark.parametrize(("transport", "via"), [("ssh", "ssh"), ("run", None)])
def test_transport_choice(env, monkeypatch, transport, via):
    project(env, f'transport = "{transport}"\n')
    seen = []

    def fake(cfg, server, command, **kw):
        seen.append(kw["via"])
        return executor.Result(server, 0, "")

    monkeypatch.setattr(executor, "execute", fake)
    assert main(["ioc", "status", "server1"]) == 2  # no state in the output
    assert seen == [via]


def test_parse_states_ignores_noise():
    output = (
        'banner\n@@host-ioc quick\n{"findings": []}\n\n@@host-ioc-end quick 0\n'
        "@@host-ioc deep\nhead: x: Permission denied\n\n@@host-ioc-end deep 1\n"
    )
    assert ioc.parse_states(output) == {
        "quick": {"findings": []},
        "deep": "cannot read: head: x: Permission denied",
        "error": None,
    }


# --- show


def test_show_lists_findings(env, capsys):
    project(env)
    put(env, "host1", "quick", state())
    put(env, "host1", "deep", state(findings=[{**FINDING, "detail": "x\x1b[2Jy"}]))
    assert main(["ioc", "show", "server1"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("quick ")
    assert "\x1b" not in out and "x\\x1b[2Jy" in out
    assert "  abc123  php_logs  container=web1  path=  new  " in out


def test_show_finding_file_window(env, capsys):
    project(env)
    log = env / "error.log"
    log.write_text("".join(f"line {i}\n" for i in range(1, 21)))
    put(env, "host1", "quick", state(findings=[{**FINDING, "path": str(log)}]))
    put(env, "host1", "deep", state())
    assert main(["ioc", "show", "server1", "abc123"]) == 1
    out = capsys.readouterr().out
    assert "run: quick\nid: abc123\n" in out
    assert "lines 3-13:\nline 3\n" in out and "line 13\n" in out and "line 14" not in out


def test_show_finding_binary_and_missing(env, capsys):
    project(env)
    binary = env / "x.bin"
    binary.write_bytes(b"\x7fELF\x00\x01\x02")
    findings = [
        {"id": "b1", "module": "tmp", "path": str(binary)},
        {"id": "m1", "module": "tmp", "path": str(env / "gone")},
    ]
    put(env, "host1", "quick", state(findings=findings))
    put(env, "host1", "deep", state())
    assert main(["ioc", "show", "server1", "b1"]) == 1
    out = capsys.readouterr().out
    assert "binary or empty, content not shown" in out and "ELF" not in out
    assert main(["ioc", "show", "server1", "m1"]) == 1
    assert "No such file" in capsys.readouterr().out


def test_show_hostile_path_stays_quoted(env, capsys):
    project(env)
    pwn = env / "pwned"
    path = f"/nonexistent'; touch {pwn}; echo '"
    put(env, "host1", "quick", state(findings=[{"id": "h1", "path": path}]))
    put(env, "host1", "deep", state())
    assert main(["ioc", "show", "server1", "h1"]) == 1
    assert not pwn.exists()


@pytest.mark.parametrize(
    ("finding", "message"),
    [
        ({"path": "relative/x"}, "invalid path"),
        ({"path": "/a\nb"}, "invalid path"),
        ({"pid": "1; id"}, "invalid pid"),
        ({"pid": True}, "invalid pid"),
        ({"pid": 0}, "invalid pid"),
    ],
)
def test_show_rejects_bad_targets(env, capsys, finding, message):
    project(env)
    put(env, "host1", "quick", state(findings=[{"id": "z1", **finding}]))
    put(env, "host1", "deep", state())
    assert main(["ioc", "show", "server1", "z1"]) == 2
    assert message in capsys.readouterr().err


def test_show_finding_process(env, capsys):
    project(env)
    put(
        env,
        "host1",
        "quick",
        state(findings=[{"id": "p1", "module": "process", "pid": os.getpid()}]),
    )
    put(env, "host1", "deep", state())
    assert main(["ioc", "show", "server1", "p1"]) == 1
    out = capsys.readouterr().out
    assert "exe: /" in out and "\nName:" in out and "process and children:" in out


def test_status_state_size_limit(env, capsys, monkeypatch):
    """A file of exactly STATE_MAX bytes is read; one byte more (here trailing whitespace,
    which the JSON parse would ignore) is rejected."""
    project(env)
    text = json.dumps(state()) + "\n"
    monkeypatch.setattr(ioc, "STATE_MAX", len(text))
    put(env, "host1", "quick", text)
    put(env, "host1", "deep", text + " ")
    assert main(["ioc", "status", "server1"]) == 2
    out = capsys.readouterr().out.splitlines()
    assert "WARN" not in out[0] and f"state file over {len(text)} bytes" in out[1]


def test_show_id_with_unreadable_run(env, capsys):
    project(env)
    put(env, "host1", "quick", state())
    assert main(["ioc", "show", "server1", "abc123"]) == 2
    err = capsys.readouterr().err
    assert "no finding abc123 in the readable runs; deep: cannot read: " in err


def test_show_large_directory_no_sigpipe(env, capsys):
    project(env)
    big = env / "big"
    big.mkdir()
    for i in range(1500):
        (big / f"{i:04d}-{'x' * 100}").touch()
    put(env, "host1", "quick", state(findings=[{"id": "d1", "path": str(big)}]))
    put(env, "host1", "deep", state())
    assert main(["ioc", "show", "server1", "d1"]) == 1
    raw = capsys.readouterr().out.partition("raw data:\n")[2]
    assert len(raw.splitlines()) == 51  # ls -ld + 50 listing lines


def test_show_log_without_line_shows_tail(env, capsys):
    project(env)
    log = env / "error.log.1"
    log.write_text("".join(f"line {i}\n" for i in range(1, 21)))
    finding = {"id": "l1", "module": "php_logs", "path": str(log)}
    put(env, "host1", "quick", state(findings=[finding]))
    put(env, "host1", "deep", state())
    assert main(["ioc", "show", "server1", "l1"]) == 1
    out = capsys.readouterr().out
    assert "last 11 lines:\nline 10\n" in out and "line 20\n" in out


@pytest.mark.parametrize("pid", [4194303, os.getpid()])
def test_show_container_path_after_restart(env, capsys, pid):
    """A gone init, or a PID now used by a host process: unavailable, never the host file."""
    project(env)
    path = f"/proc/{pid}/root/etc/hostname"
    put(env, "host1", "quick", state(findings=[{"id": "c1", "module": "tmp", "path": path}]))
    put(env, "host1", "deep", state())
    assert main(["ioc", "show", "server1", "c1"]) == 1
    raw = capsys.readouterr().out.partition("raw data:\n")[2]
    assert raw == (
        f"unavailable: container init {pid} no longer runs (container restarted?); "
        "path inside the container: /etc/hostname\n"
    )


def test_show_lists_uncovered_reasons(env, capsys):
    project(env)
    modules = {"files": {"status": "uncovered", "uncovered": ["web1: chybi index"]}}
    put(env, "host1", "quick", state())
    put(env, "host1", "deep", state(modules=modules))
    assert main(["ioc", "show", "server1"]) == 0
    assert "deep " in (out := capsys.readouterr().out)
    assert "\n  uncovered files: web1: chybi index\n" in out


@pytest.mark.parametrize(("age_h", "warned"), [(0, True), (5, False)])
def test_status_last_error(env, capsys, age_h, warned):
    project(env)
    put(env, "host1", "quick", state(hours_ago=2))
    put(env, "host1", "deep", state(hours_ago=3))
    error = env / "state" / "host1" / "last-error.txt"
    error.write_text("Traceback (most recent call last):\nKeyError: 'x'\n")
    mtime = (datetime.now(UTC) - timedelta(hours=age_h)).timestamp()
    os.utime(error, (mtime, mtime))
    assert main(["ioc", "status", "server1"]) == (2 if warned else 0)
    out = capsys.readouterr().out.splitlines()
    assert len(out) == (3 if warned else 2)
    if warned:
        assert out[2].startswith("server1 error: WARN last-error.txt ")
        assert out[2].endswith("after a last run: KeyError: 'x'")


def test_show_unknown_and_invalid_id(env, capsys):
    project(env)
    put_ok(env)
    assert main(["ioc", "show", "server1", "abc"]) == 2
    assert "no finding abc" in capsys.readouterr().err
    assert main(["ioc", "show", "server1", "../x"]) == 2
    assert "invalid finding id" in capsys.readouterr().err


# --- baseline


def test_baseline_saves_stdout_only(env, capsys):
    project(env)
    write_exe(
        env / "rbin" / "host-ioc",
        '#!/bin/sh\n[ "$1" = baseline ] || exit 97\necho "warning: slow" >&2\n'
        'printf "containers:\\n  web1:\\n    cron: []\\n"\n',
    )
    assert main(["ioc", "baseline", "server1"]) == 0
    captured = capsys.readouterr()
    assert "server1: warning: slow" in captured.err
    saved = Path(captured.out.strip())
    assert saved.parent == env / "work" / "tmp" / "host-ioc"
    assert saved.name.startswith("server1+") and saved.suffix == ".yaml"
    assert saved.read_text() == "containers:\n  web1:\n    cron: []\n"


def test_baseline_failure_writes_nothing(env, capsys):
    project(env)
    write_exe(env / "rbin" / "host-ioc", "#!/bin/sh\necho 'config missing' >&2\nexit 2\n")
    assert main(["ioc", "baseline", "server1"]) == 2
    assert "remote command failed (exit 2): config missing" in capsys.readouterr().err
    assert not (env / "work" / "tmp").exists()
