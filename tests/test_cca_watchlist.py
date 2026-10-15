"""cca watchlist: Backlog.md conventions over a fake `backlog` CLI, one real-backlog test."""

import json
import shutil
import stat
import subprocess
from datetime import date
from pathlib import Path

import pytest

from cca.cli import main
from cca.commands import watchlist

TODAY = date(2026, 10, 15)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Project with .cca.toml, CWD in a subdir, a fake backlog as the only PATH entry."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "project" / "sub").mkdir(parents=True)
    (tmp_path / "project" / ".cca.toml").write_text("schema_version = 1\n")
    monkeypatch.chdir(tmp_path / "project" / "sub")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setenv("BACKLOG_CWD", "/nonexistent")  # must not reach backlog
    monkeypatch.setattr(watchlist, "today", lambda: TODAY)
    script = tmp_path / "bin" / "backlog"
    script.write_text(
        "#!/bin/sh\n"
        f'd="{tmp_path}"\n'
        'line="$(pwd) ${BACKLOG_CWD-unset}"\n'
        'for a; do line="$line\t$a"; done\n'
        'printf "%s\\n" "$line" >> "$d/log"\n'
        '[ -f "$d/stderr" ] && /bin/cat "$d/stderr" >&2\n'
        '[ -f "$d/stdout" ] && /bin/cat "$d/stdout"\n'
        '[ -f "$d/exit" ] && exit "$(/bin/cat "$d/exit")"\n'
        'case "$*" in\n'
        '  "task list"*"--status Note"*) /bin/cat "$d/notes.json";;\n'
        '  "task list"*) /bin/cat "$d/open.json";;\n'
        '  "task view"*) /bin/cat "$d/view.json";;\n'
        "esac\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    serve(tmp_path, open_tasks=[], notes=[])
    return tmp_path


def task(ident, title="Title", labels=(), due=None, status="To Do", priority=None):
    return {
        "id": ident,
        "title": title,
        "status": status,
        "labels": list(labels),
        "dueDate": due,
        "priority": priority,
    }


def serve(env: Path, open_tasks=None, notes=None, view=None) -> None:
    for name, tasks in (("open", open_tasks), ("notes", notes)):
        if tasks is not None:
            body = {"schemaVersion": 1, "kind": "task-list", "tasks": tasks}
            (env / f"{name}.json").write_text(json.dumps(body))
    if view is not None:
        (env / "view.json").write_text(
            json.dumps({"schemaVersion": 1, "kind": "task-view", "task": view})
        )


def calls(env: Path) -> list[list[str]]:
    log = env / "log"
    return [line.split("\t") for line in log.read_text().splitlines()] if log.exists() else []


def out_err(argv, capsys, code=0):
    assert main(["watchlist", *argv]) == code
    captured = capsys.readouterr()
    return captured.out, captured.err


# --- today


def test_today_due_tasks_and_valid_notes(env, capsys):
    serve(
        env,
        open_tasks=[
            task("TASK-5", "Low prio", due="2026-10-14", priority="low"),
            task("TASK-3", "High prio", due="2026-10-14", priority="high"),
            task("TASK-9", "Older", ["every:7d", "infra"], due="2026-10-01"),
            task("TASK-2", "Today", ["every:1d"], due="2026-10-15"),
            task("TASK-4", "Tomorrow", ["every:1d"], due="2026-10-16"),
            task("TASK-6", "No due date"),
            task("TASK-7", "Ended", ["every:1d", "until:2026-10-10"], due="2026-10-12"),
        ],
        notes=[
            task("TASK-20", "Window", ["from:2026-10-15", "until:2026-10-15"], status="Note"),
            task("TASK-21", "Open start", ["until:2026-10-15"], status="Note"),
            task("TASK-22", "Forever", status="Note"),
            task("TASK-23", "Future", ["from:2026-10-16"], status="Note"),
            task("TASK-24", "Past", ["until:2026-10-14"], status="Note"),
        ],
    )
    out, err = out_err(["today"], capsys)
    assert err == ""
    assert out.splitlines() == [
        "Due:",
        "TASK-9 | 2026-10-01 | +14d | every:7d | Older",
        "TASK-7 | 2026-10-12 | +3d | every:1d | Ended [ended]",
        "TASK-3 | 2026-10-14 | +1d | - | High prio",
        "TASK-5 | 2026-10-14 | +1d | - | Low prio",
        "TASK-2 | 2026-10-15 | +0d | every:1d | Today",
        "Notes:",
        "TASK-21 | *..2026-10-15 | Open start",
        "TASK-22 | *..* | Forever",
        "TASK-20 | 2026-10-15..2026-10-15 | Window",
    ]
    project = str(env / "project")
    assert calls(env) == [
        [f"{project} unset", "task", "list", "--exclude-status", "Note,Done", "--json"],
        [f"{project} unset", "task", "list", "--status", "Note", "--json"],
    ]


def test_today_empty(env, capsys):
    out, _ = out_err(["today"], capsys)
    assert out.splitlines() == ["Due:", "none", "Notes:", "none"]


def test_today_json(env, capsys):
    due = task("TASK-1", due="2026-10-15")
    note = task("TASK-2", status="Note")
    serve(env, open_tasks=[due, task("TASK-3", due="2026-10-20")], notes=[note])
    out, _ = out_err(["today", "--json"], capsys)
    assert json.loads(out) == {"due": [due], "notes": [note]}


def test_today_malformed_labels_reported(env, capsys):
    serve(
        env,
        open_tasks=[
            task("TASK-1", "Bad every", ["every:abc"], due="2026-10-15"),
            task("TASK-2", "Too long", ["every:400d"], due="2026-10-15"),
            task("TASK-3", "Twice", ["every:1d", "every:2d"], due="2026-10-15"),
        ],
        notes=[
            task("TASK-4", "Bad date", ["from:2026-13-01"], status="Note"),
            task("TASK-5", "Reversed", ["from:2026-10-16", "until:2026-10-14"], status="Note"),
        ],
    )
    out, err = out_err(["today"], capsys, code=1)
    assert err.splitlines() == [
        "cca: warning: TASK-1: malformed label every:abc (expected every:Nd, N 1-366)",
        "cca: warning: TASK-2: malformed label every:400d (expected every:Nd, N 1-366)",
        "cca: warning: TASK-3: duplicate every: label",
        "cca: warning: TASK-4: malformed label from:2026-13-01 (expected from:YYYY-MM-DD)",
        "cca: warning: TASK-5: from: is after until:",
    ]
    assert "TASK-1 | 2026-10-15 | +0d | - | Bad every" in out  # still listed
    assert "TASK-3 | 2026-10-15 | +0d | every:1d | Twice" in out
    assert "TASK-4 | *..* | Bad date" in out  # the bad boundary is ignored, never hidden


def test_malformed_label_escaped_in_warning(env, capsys):
    serve(env, open_tasks=[task("TASK-1", labels=["every:\x1b[2J"], due="2026-10-15")])
    _, err = out_err(["today"], capsys, code=1)
    assert "malformed label every:\\x1b[2J (expected" in err
    assert "\x1b" not in err


def test_today_escapes_control_characters(env, capsys):
    serve(env, open_tasks=[task("TASK-1", "evil\x1b[2Jtitle\nnext", due="2026-10-15")])
    out, _ = out_err(["today"], capsys)
    assert "TASK-1 | 2026-10-15 | +0d | - | evil\\x1b[2Jtitle next" in out
    out, _ = out_err(["today", "--json"], capsys)
    assert "\x1b" not in out
    assert json.loads(out)["due"][0]["title"] == "evil\\x1b[2Jtitle\\nnext"


def test_today_due_date_with_time(env, capsys):
    serve(env, open_tasks=[task("TASK-1", due="2026-10-15T08:00:00Z"), task("TASK-2", due="x")])
    out, _ = out_err(["today"], capsys)
    assert out.splitlines()[1:3] == ["TASK-1 | 2026-10-15 | +0d | - | Title", "Notes:"]


# --- notes


def test_notes_on_date_inclusive(env, capsys):
    serve(
        env,
        notes=[
            task("TASK-1", "Outage window", ["from:2026-09-16", "until:2026-09-17"], status="Note"),
            task("TASK-2", "Later", ["from:2026-09-18"], status="Note"),
        ],
    )
    out, _ = out_err(["notes", "--on", "2026-09-17"], capsys)
    assert out.splitlines() == ["Notes:", "TASK-1 | 2026-09-16..2026-09-17 | Outage window"]
    out, _ = out_err(["notes", "--on", "2026-09-18", "--json"], capsys)
    assert [t["id"] for t in json.loads(out)] == ["TASK-2"]


def test_notes_default_today(env, capsys):
    serve(env, notes=[task("TASK-1", "Now", ["until:2026-10-15"], status="Note")])
    out, _ = out_err(["notes"], capsys)
    assert out.splitlines() == ["Notes:", "TASK-1 | *..2026-10-15 | Now"]


def test_notes_search_is_one_argument(env, capsys):
    out_err(["notes", "--search", "-x outage"], capsys)
    assert calls(env)[0][1:] == ["task", "list", "--status", "Note", "--search=-x outage", "--json"]


def test_notes_search_control_character(env, capsys):
    _, err = out_err(["notes", "--search", "a\nb"], capsys, code=2)
    assert "--search contains a control character" in err
    assert calls(env) == []


@pytest.mark.parametrize("value", ["2026-9-1", "2026-02-30", "tomorrow"])
def test_notes_bad_date_is_usage_error(env, capsys, value):
    with pytest.raises(SystemExit) as exc:
        main(["watchlist", "notes", "--on", value])
    assert exc.value.code == 2
    assert "invalid date" in capsys.readouterr().err


# --- checked


def test_checked_moves_due_date_from_today(env, capsys):
    serve(env, view=task("TASK-12", labels=["every:7d"], due="2026-10-01"))
    out, _ = out_err(["checked", "task-12"], capsys)
    assert out == "checked TASK-12: next 2026-10-22\n"
    assert [c[1:] for c in calls(env)] == [
        ["task", "view", "TASK-12", "--json"],
        [
            "task",
            "edit",
            "TASK-12",
            "--due-date",
            "2026-10-22",
            "--comment",
            "checked",
            "--comment-author",
            "cca",
            "--plain",
        ],
    ]


def test_checked_until_reached_closes(env, capsys):
    serve(env, view=task("TASK-1", labels=["every:7d", "until:2026-10-20"], due="2026-10-15"))
    out, _ = out_err(["checked", "TASK-1", "--json"], capsys)
    assert json.loads(out) == {"id": "TASK-1", "status": "Done", "until": "2026-10-20"}
    assert calls(env)[1][1:] == [
        "task",
        "edit",
        "TASK-1",
        "-s",
        "Done",
        "--comment",
        "checked; ended (until: 2026-10-20)",
        "--comment-author",
        "cca",
        "--plain",
    ]


def test_checked_until_not_yet_reached(env, capsys):
    serve(env, view=task("TASK-1", labels=["every:5d", "until:2026-10-20"]))
    out, _ = out_err(["checked", "TASK-1"], capsys)
    assert out == "checked TASK-1: next 2026-10-20\n"


@pytest.mark.parametrize(
    ("view", "message"),
    [
        (task("TASK-1"), "TASK-1 is not a recurring check (no every:Nd label)"),
        (task("TASK-1", labels=["every:1d"], status="Note"), "TASK-1 has status Note"),
        (task("TASK-1", labels=["every:1d"], status="Done"), "TASK-1 has status Done"),
        (task("TASK-1", labels=["every:0d"]), "TASK-1: malformed label every:0d"),
    ],
)
def test_checked_refuses(env, capsys, view, message):
    serve(env, view=view)
    _, err = out_err(["checked", "TASK-1"], capsys, code=2)
    assert message in err
    assert len(calls(env)) == 1  # nothing edited


@pytest.mark.parametrize("value", ["--help-me", "TASK-1;x", "TASK", "1", "TASK-1.", "TASK--1"])
def test_checked_bad_id_is_usage_error(env, capsys, value):
    with pytest.raises(SystemExit) as exc:
        main(["watchlist", "checked", "--", value])
    assert exc.value.code == 2
    assert calls(env) == []


def test_checked_subtask_id(env, capsys):
    serve(env, view=task("TASK-1.2", labels=["every:1d"]))
    out, _ = out_err(["checked", "TASK-1.2"], capsys)
    assert out == "checked TASK-1.2: next 2026-10-16\n"


# --- backlog and config failures


def test_backlog_missing(env, monkeypatch, capsys):
    (env / "bin" / "backlog").unlink()
    _, err = out_err(["today"], capsys, code=2)
    assert "backlog CLI not found on PATH" in err


def test_backlog_failure_stderr_escaped(env, capsys):
    (env / "exit").write_text("1")
    (env / "stderr").write_text("Task not\x1b[31m found\n")
    _, err = out_err(["checked", "TASK-1"], capsys, code=2)
    assert "backlog task view failed: Task not\\x1b[31m found" in err
    assert "\x1b" not in err


def test_backlog_failure_message_on_stdout(env, capsys):
    (env / "exit").write_text("1")
    (env / "stdout").write_text("Task TASK-1 not found.\n")
    _, err = out_err(["checked", "TASK-1"], capsys, code=2)
    assert "backlog task view failed: Task TASK-1 not found." in err


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("not json", "backlog task list did not return JSON"),
        ('{"schemaVersion": 2, "kind": "task-list", "tasks": []}', "unsupported backlog JSON"),
        ('{"schemaVersion": 1, "kind": "task-view", "tasks": []}', "unsupported backlog JSON"),
        ('{"schemaVersion": 1, "kind": "task-list", "tasks": [1]}', "tasks is not a list"),
    ],
)
def test_backlog_bad_json(env, capsys, body, message):
    (env / "open.json").write_text(body)
    _, err = out_err(["today"], capsys, code=2)
    assert message in err


def test_backlog_timeout(env, monkeypatch, capsys):
    (env / "bin" / "backlog").write_text("#!/bin/sh\nexec /bin/sleep 5\n")
    monkeypatch.setattr(watchlist, "TIMEOUT", 0.2)
    _, err = out_err(["today"], capsys, code=2)
    assert "backlog task list timed out" in err


def test_no_config(env, monkeypatch, capsys):
    (env / "project" / ".cca.toml").unlink()
    _, err = out_err(["today"], capsys, code=2)
    assert ".cca.toml" in err
    assert calls(env) == []


# --- real backlog


@pytest.mark.skipif(shutil.which("backlog") is None, reason="backlog CLI not installed")
def test_real_backlog(tmp_path, monkeypatch, capsys):
    real = shutil.which("backlog")
    monkeypatch.setattr(watchlist, "today", lambda: TODAY)
    monkeypatch.delenv("BACKLOG_CWD", raising=False)

    def backlog(*args):
        subprocess.run([real, *args], cwd=tmp_path, check=True, capture_output=True)

    backlog("init", "demo", "--defaults", "--no-git", "--integration-mode", "none")
    cfg = tmp_path / "backlog" / "config.yml"
    cfg.write_text(
        cfg.read_text().replace(
            'statuses: ["To Do", "In Progress", "Done"]',
            'statuses: ["To Do", "In Progress", "Note", "Done"]',
        )
    )
    (tmp_path / ".cca.toml").write_text("schema_version = 1\n")
    backlog("task", "create", "Status check", "-l", "every:1d", "--due-date", "2026-10-15")
    backlog("task", "create", "Outage", "-s", "Note", "-l", "from:2026-10-14,until:2026-10-16")
    monkeypatch.chdir(tmp_path)
    assert main(["watchlist", "today"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Due:",
        "TASK-1 | 2026-10-15 | +0d | every:1d | Status check",
        "Notes:",
        "TASK-2 | 2026-10-14..2026-10-16 | Outage",
    ]
    assert main(["watchlist", "checked", "TASK-1"]) == 0
    assert capsys.readouterr().out == "checked TASK-1: next 2026-10-16\n"
    assert main(["watchlist", "today"]) == 0
    assert capsys.readouterr().out.splitlines()[:2] == ["Due:", "none"]
