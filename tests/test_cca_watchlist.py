"""cca watchlist: Backlog.md conventions over a fake `backlog` CLI, one real-backlog test."""

import json
import shutil
import stat
import subprocess
import sys
from datetime import UTC, date, timedelta, timezone
from pathlib import Path

import pytest

from cca import watchlist_migrate
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
        '  "task view"*) f="$d/view-$3.json"; [ -f "$f" ] || f="$d/view.json"; /bin/cat "$f";;\n'
        "esac\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    serve(tmp_path, open_tasks=[], notes=[])
    return tmp_path


def task(ident, title="Title", labels=(), due=None, status="To Do", priority=None, ready=True):
    return {
        "id": ident,
        "title": title,
        "status": status,
        "labels": list(labels),
        "dueDate": due,
        "priority": priority,
        "isReady": ready,
    }


def serve(env: Path, open_tasks=None, notes=None, view=None, plans=None) -> None:
    """plans: {id: Implementation Plan} served by task view of that id (with its list entry)."""
    for name, tasks in (("open", open_tasks), ("notes", notes)):
        if tasks is not None:
            body = {"schemaVersion": 1, "kind": "task-list", "tasks": tasks}
            (env / f"{name}.json").write_text(json.dumps(body))
    if view is not None:
        (env / "view.json").write_text(
            json.dumps({"schemaVersion": 1, "kind": "task-view", "task": view})
        )
    for ident, text in (plans or {}).items():
        full = next(t for t in open_tasks if t["id"] == ident) | {"implementationPlan": text}
        (env / f"view-{ident}.json").write_text(
            json.dumps({"schemaVersion": 1, "kind": "task-view", "task": full})
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
        "Priority:",
        "none",
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
    assert out.splitlines() == ["Due:", "none", "Priority:", "none", "Notes:", "none"]


def test_today_json(env, capsys):
    due = task("TASK-1", due="2026-10-15")
    note = task("TASK-2", status="Note")
    serve(env, open_tasks=[due, task("TASK-3", due="2026-10-20")], notes=[note])
    out, _ = out_err(["today", "--json"], capsys)
    assert json.loads(out) == {"due": [due], "priority": [], "notes": [note]}


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
    assert out.splitlines()[1:3] == ["TASK-1 | 2026-10-15 | +0d | - | Title", "Priority:"]


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


# --- notes --expired


def test_notes_expired(env, capsys):
    serve(
        env,
        notes=[
            task("TASK-1", "Old", ["until:2026-10-01"], status="Note"),
            task("TASK-2", "Older", ["until:2026-09-01"], status="Note"),
            task("TASK-3", "Ends today", ["until:2026-10-15"], status="Note"),
            task("TASK-4", "Forever", status="Note"),
        ],
    )
    out, _ = out_err(["notes", "--expired"], capsys)
    assert out.splitlines() == [
        "Notes:",
        "TASK-2 | *..2026-09-01 | Older",
        "TASK-1 | *..2026-10-01 | Old",
    ]
    out, _ = out_err(["notes", "--expired", "--on", "2026-10-16", "--json"], capsys)
    assert [t["id"] for t in json.loads(out)] == ["TASK-2", "TASK-1", "TASK-3"]


# --- ready, next, today Priority


def work(ident, effort="e1h", extra=(), window="wany", **kw):
    """A work task; window:wany unless extra names a window (no window = never ready)."""
    labels = ([f"effort:{effort}"] if effort else []) + list(extra)
    if window and not any(x.startswith("window:") for x in extra):
        labels.append(f"window:{window}")
    return task(ident, f"Work {ident}", labels, **kw)


def test_ready_filters_and_order(env, capsys):
    serve(
        env,
        open_tasks=[
            work("TASK-10", priority="low"),
            work("TASK-9", "e15", priority="low"),
            work("TASK-3", priority="high"),
            work("TASK-4", "e4h", priority="high"),  # longer than 1h
            work("TASK-5", "exl"),  # never ready
            work("TASK-6", extra=["standby"]),
            work("TASK-7", extra=["blocked:external"]),
            work("TASK-8", ready=False),  # unfinished dependency
            work("TASK-11", extra=["change-risk:r2"]),  # minimum window woff
            work("TASK-12", extra=["window:wnight"]),
            work("TASK-13", status="Idea"),
            work("TASK-14", effort=None),
            work("TASK-15", effort=None, extra=["standby"]),
        ],
    )
    out, err = out_err(["ready"], capsys)
    assert err == ""
    assert out.splitlines() == [
        "TASK-3 | high | e1h | wany | Work TASK-3",
        "TASK-9 | low | e15 | wany | Work TASK-9",
        "TASK-10 | low | e1h | wany | Work TASK-10",
        "untagged (no effort:): 1",
    ]
    out, _ = out_err(["ready", "--time", "4h", "--window", "woff", "--include-blocked"], capsys)
    assert [line.split(" | ")[0] for line in out.splitlines()[:-1]] == [
        "TASK-3",
        "TASK-4",
        "TASK-9",
        "TASK-10",
        "TASK-7",
        "TASK-8",
        "TASK-11",
    ]
    assert "TASK-11 | - | e1h | woff | Work TASK-11" in out


def test_ready_window_and_change_risk(env, capsys):
    serve(
        env,
        open_tasks=[
            work("TASK-1", extra=["window:wany", "change-risk:r0"]),
            work("TASK-2", extra=["window:wany", "change-risk:r3"]),  # lifted to wnight
            work("TASK-3", extra=["window:woff"]),  # no change risk
            work("TASK-4", window=None),  # neither window nor change risk: never ready
        ],
    )
    out, _ = out_err(["ready", "--window", "wnight", "--max-change-risk", "r1"], capsys)
    assert out.splitlines() == ["TASK-1 | - | e1h | wany | Work TASK-1", "untagged (no effort:): 0"]
    out, _ = out_err(["ready", "--window", "wnight"], capsys)
    assert [line.split(" | ")[0] for line in out.splitlines()[:-1]] == [
        "TASK-1",
        "TASK-2",
        "TASK-3",
    ]
    assert "TASK-2 | - | e1h | wnight | Work TASK-2" in out


def test_ready_area_verbose_and_json(env, capsys):
    tasks = [
        work("TASK-1", extra=["area:server1", "window:wany"]),
        work("TASK-2", extra=["area:server2", "window:wany"]),
        work("TASK-3", effort=None, extra=["area:server1"]),
    ]
    serve(env, open_tasks=tasks, plans={"TASK-1": "Restart\nthe service", "TASK-3": ""})
    out, _ = out_err(["ready", "--area", "server1", "--verbose"], capsys)
    assert out.splitlines() == [
        "TASK-1 | - | e1h | wany | Work TASK-1",
        "  next: Restart the service",
        "untagged (no effort:): 1",
    ]
    out, _ = out_err(["ready", "--area", "server1", "--json"], capsys)
    body = json.loads(out)
    assert sorted(body) == ["ready", "untagged"]
    assert [(t["id"], t["implementationPlan"]) for t in body["ready"]] == [
        ("TASK-1", "Restart\\nthe service")
    ]
    assert [t["id"] for t in body["untagged"]] == ["TASK-3"]


def test_ready_rows_limited(env, capsys):
    serve(env, open_tasks=[work(f"TASK-{n}", extra=["window:wany"]) for n in range(1, 23)])
    out, _ = out_err(["ready"], capsys)
    lines = out.splitlines()
    assert len(lines) == 22
    assert lines[-2:] == ["... 2 more (--json lists all)", "untagged (no effort:): 0"]


def test_ready_malformed_tag_reported(env, capsys):
    serve(env, open_tasks=[work("TASK-1", effort="e2h", extra=["window:wany"])])
    out, err = out_err(["ready"], capsys, code=1)
    assert "TASK-1: malformed label effort:e2h (expected effort:e15|e1h|e4h|exl)" in err
    assert out.splitlines() == ["none", "untagged (no effort:): 1"]


def test_ready_requires_is_ready(env, capsys):
    item = work("TASK-1", extra=["window:wany"])
    del item["isReady"]
    serve(env, open_tasks=[item])
    _, err = out_err(["ready"], capsys, code=2)
    assert "unsupported backlog JSON from task list (TASK-1: no isReady)" in err


def test_next_skips_empty_plan_and_future_due(env, capsys):
    tasks = [
        work("TASK-1", extra=["window:wany"], priority="high"),  # no plan
        work("TASK-2", extra=["window:wany", "idle"], priority="high", due="2026-10-16"),
        work("TASK-3", extra=["window:wany", "idle"], due="2026-10-15"),
        work("TASK-4", extra=["window:wany"]),
    ]
    serve(env, open_tasks=tasks, plans={"TASK-1": " ", "TASK-2": "x", "TASK-3": "Check logs"})
    out, _ = out_err(["next"], capsys)
    assert out.splitlines() == ["TASK-3 | - | e1h | wany | Work TASK-3", "  next: Check logs"]
    viewed = [c[3] for c in calls(env) if c[1:3] == ["task", "view"]]
    assert viewed == ["TASK-1", "TASK-3"]  # TASK-2 skipped without a view, stops at the hit
    out, _ = out_err(["next", "--json"], capsys)
    assert json.loads(out)["implementationPlan"] == "Check logs"


def test_next_none(env, capsys):
    serve(env, open_tasks=[work("TASK-1", extra=["window:wany", "blocked:external"])])
    out, _ = out_err(["next"], capsys)
    assert out == "none\n"
    out, _ = out_err(["next", "--json"], capsys)
    assert json.loads(out) is None


def test_today_priority_section(env, capsys):
    tasks = [
        work("TASK-1", extra=["window:wany"], priority="high", due="2026-10-15"),  # in Due
        work("TASK-2", extra=["window:wany"], priority="high"),
        work("TASK-3", extra=["window:wany"], priority="medium"),
        work("TASK-4", "e4h", extra=["window:wany"], priority="high"),  # does not fit 1h
        work("TASK-5", extra=["window:wnight"], priority="high"),  # does not fit wany
        work("TASK-6", extra=["window:wany"], priority="high"),  # no plan
        work("TASK-7", extra=["window:wany", "idle"], priority="high", due="2026-10-20"),
        work("TASK-8", extra=["window:wany", "idle"], priority="high", due="2026-10-10"),
    ]
    plans = {i: "Do it" for i in ("TASK-1", "TASK-2", "TASK-3", "TASK-7", "TASK-8")}
    serve(env, open_tasks=tasks, plans=plans | {"TASK-6": None})
    out, _ = out_err(["today"], capsys)
    assert out.splitlines() == [
        "Due:",
        "TASK-1 | 2026-10-15 | +0d | - | Work TASK-1",  # TASK-8 is idle: never due
        "Priority:",
        "TASK-2 | high | e1h | wany | Work TASK-2",
        "TASK-8 | high | e1h | wany | Work TASK-8",
        "Notes:",
        "none",
    ]
    out, _ = out_err(["today", "--json"], capsys)
    body = json.loads(out)
    assert [t["id"] for t in body["priority"]] == ["TASK-2", "TASK-8"]
    assert body["priority"][0]["implementationPlan"] == "Do it"


def test_today_skips_idle_and_standby_due(env, capsys):
    serve(
        env,
        open_tasks=[
            task("TASK-1", labels=["idle"], due="2026-10-01"),
            task("TASK-2", labels=["standby"], due="2026-10-01"),
            task("TASK-3", due="2026-10-01"),
        ],
    )
    out, _ = out_err(["today"], capsys)
    assert out.splitlines()[:3] == ["Due:", "TASK-3 | 2026-10-01 | +14d | - | Title", "Priority:"]


def test_today_skips_due_idea(env, capsys):
    idea = task("TASK-1", due="2026-10-01", status="Idea", priority="high")
    serve(env, open_tasks=[idea, task("TASK-2", due="2026-10-01")])
    out, _ = out_err(["today"], capsys)
    assert out.splitlines()[:3] == ["Due:", "TASK-2 | 2026-10-01 | +14d | - | Title", "Priority:"]
    out, _ = out_err(["today", "--json"], capsys)
    assert [t["id"] for t in json.loads(out)["due"]] == ["TASK-2"]


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


# --- migrate

FAKE = """\
import json, sys
from pathlib import Path

d = Path(sys.argv[1])
args = sys.argv[2:]
with open(d / "log", "a") as log:
    log.write(json.dumps(args) + "\\n")
state = json.loads((d / "state.json").read_text())
tasks = state["tasks"]


def body(kind, **kw):
    print(json.dumps({"schemaVersion": 1, "kind": kind, **kw}))


def find(ident):
    return next(t for t in tasks if t["id"] == ident)


if args[:3] == ["config", "get", "statuses"]:
    print(state["statuses"])
elif args[:2] == ["task", "list"]:
    summaries = [{k: v for k, v in t.items() if k != "implementationPlan"} for t in tasks]
    body("task-list", tasks=summaries)
elif args[:2] == ["task", "view"]:
    body("task-view", task=find(args[2]))
elif args[:2] == ["task", "create"]:
    state["creates"] = state.get("creates", 0) + 1
    if state["creates"] == state.get("fail_create"):
        print("Error: disk full", file=sys.stderr)
        sys.exit(1)
    opts = [a for a in args[2:args.index("--")]]
    value = lambda key: next((a.split("=", 1)[1] for a in opts if a.startswith(key + "=")), None)
    labels = value("--labels")
    tasks.append({
        "id": f"TASK-{len(tasks) + 1}",
        "title": args[-1],
        "status": value("--status"),
        "labels": labels.split(",") if labels else [],
        "priority": value("--priority"),
        "dueDate": value("--due-date"),
        "references": [a.split("=", 1)[1] for a in opts if a.startswith("--ref=")],
        "description": value("--description"),
        "isReady": True,
        "implementationPlan": None,
    })
elif args[:2] == ["task", "edit"]:
    find(args[2])["implementationPlan"] = args[3].split("=", 1)[1]
(d / "state.json").write_text(json.dumps(state))
"""


@pytest.fixture
def menv(tmp_path, monkeypatch):
    """Project with cca/watchlist.json, a stateful fake backlog, local zone UTC+2."""
    (tmp_path / "bin").mkdir()
    project = tmp_path / "project"
    (project / "cca" / "incidents" / "archive" / "2026").mkdir(parents=True)
    (project / "cca" / "guides" / "servers").mkdir(parents=True)
    (project / "cca" / "incidents" / "archive" / "2026" / "disk-full.md").write_text("x")
    (project / "cca" / "guides" / "servers" / "server1.md").write_text("x")
    (project / "cca" / "incidents" / "web-down.md").write_text("x")
    (project / ".cca.toml").write_text("schema_version = 1\n")
    monkeypatch.chdir(project)
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(watchlist, "today", lambda: TODAY)
    monkeypatch.setattr(watchlist_migrate, "LOCAL", timezone(timedelta(hours=2)))
    (tmp_path / "fake.py").write_text(FAKE)
    script = tmp_path / "bin" / "backlog"
    script.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{tmp_path}/fake.py" "{tmp_path}" "$@"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    store(tmp_path, [])
    return tmp_path


def store(menv, tasks, statuses="Idea, To Do, In Progress, Note, Done", **extra):
    (menv / "state.json").write_text(json.dumps({"tasks": tasks, "statuses": statuses, **extra}))


def state(menv):
    return json.loads((menv / "state.json").read_text())


def mcalls(menv):
    log = menv / "log"
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def legacy(*items, version="2.0"):
    return {"version": version, "items": list(items)}


def item(ident, kind="task", state="idle", **fields):
    return {"id": ident, "type": kind, "state": state, "name": f"Item {ident}", **fields}


def write_watchlist(menv, data):
    path = menv / "project" / "cca" / "watchlist.json"
    path.write_text(json.dumps(data))
    return "cca/watchlist.json"


ITEMS = legacy(
    item(
        "daily-backup",
        "routine",
        "active",
        description="Check the backup report",
        last_check="2026-10-14T05:00:00+00:00",
        guide_keywords="backup",
        effort="e15",
        prio="p1",
        refs=["server1.md"],
        next_action="Read the report",
        area="Server1 web",
    ),
    item(
        "web-down",
        "incident",
        "active",
        status="monitoring",
        file="cca/incidents/web-down.md",
        risk="HIGH (data loss)",
        last_check="2026-10-14T23:30:00Z",  # 2026-10-15 01:30 local
        monitor_until="2026-10-20T00:00:00",  # exclusive, 02:00 local
    ),
    item("cert-renewal", "routine", "active", once=True, check_after="2026-10-18T06:00:00"),
    item(
        "disk-cleanup",
        check_after="2026-10-20T21:30:00",
        blocked_on="vendor",
        refs=["disk-full.md"],
    ),
    item("wait-reply", state="standby", next_action="Capture the headers"),
    item("old-incident", "incident", "active", status="resolved", file="web-down.md"),
    item("outage", "note", valid_from="2026-09-16", valid_until="2026-09-17", prio="p2"),
    item("finished", state="done"),
)


def test_migrate_dry_run_mapping(menv, capsys):
    path = write_watchlist(menv, ITEMS)
    out, err = out_err(["migrate", path], capsys)
    assert err == ""
    assert out.splitlines() == [
        "daily-backup -> new | To Do | 2026-10-15 | watchlist:daily-backup,every:1d,"
        "area:server1-web,effort:e15 | Item daily-backup",
        "web-down -> new | To Do | 2026-10-16 | watchlist:web-down,every:1d,risk:high-data-loss,"
        "incident,until:2026-10-20 | Item web-down",
        "cert-renewal -> new | To Do | 2026-10-18 | watchlist:cert-renewal | Item cert-renewal",
        "disk-cleanup -> new | To Do | 2026-10-20 | watchlist:disk-cleanup,blocked:external,idle"
        " | Item disk-cleanup",
        "wait-reply -> new | To Do | - | watchlist:wait-reply,standby | Item wait-reply",
        "old-incident -> new | To Do | - | watchlist:old-incident,incident,idle"
        " | Item old-incident",
        "outage -> new | Note | - | watchlist:outage,from:2026-09-16,until:2026-09-17"
        " | Item outage",
        "finished -> skipped (done)",
        "items 8: new 7, exists 0, done 1, excluded 0; warnings 0 "
        "(dry run, nothing written; --apply creates them)",
    ]
    assert [c[:2] for c in mcalls(menv)] == [["config", "get"], ["task", "list"]]


def test_migrate_monitor_until_in_utc_zone(menv, monkeypatch, capsys):
    monkeypatch.setattr(watchlist_migrate, "LOCAL", UTC)
    path = write_watchlist(menv, legacy(ITEMS["items"][1]))
    out, _ = out_err(["migrate", path], capsys)
    assert "| 2026-10-15 | " in out  # last check 2026-10-14 (UTC) + 1 day
    assert "until:2026-10-19" in out  # the instant 2026-10-20T00:00Z is already excluded


def test_migrate_apply(menv, capsys):
    path = write_watchlist(menv, ITEMS)
    out, err = out_err(["migrate", path, "--apply", "--exclude", "outage"], capsys)
    assert err == ""
    assert out.splitlines()[-7:] == [
        "created TASK-1 <- daily-backup",
        "created TASK-2 <- web-down",
        "created TASK-3 <- cert-renewal",
        "created TASK-4 <- disk-cleanup",
        "created TASK-5 <- wait-reply",
        "created TASK-6 <- old-incident",
        "items 8: new 6, exists 0, done 1, excluded 1; warnings 0",
    ]
    tasks = state(menv)["tasks"]
    first = tasks[0]
    assert first["title"] == "Item daily-backup"
    assert first["priority"] == "high"
    assert first["references"] == ["cca/guides/servers/server1.md"]
    assert first["implementationPlan"] == "Read the report"
    assert first["description"] == (
        "Check the backup report\n\n"
        "Keywords: backup\n"
        "Migrated from watchlist item daily-backup, last check 2026-10-14T05:00:00+00:00."
    )
    assert tasks[1]["references"] == ["cca/incidents/web-down.md"]
    assert tasks[1]["description"] == (
        "Status: monitoring\n"
        "Migrated from watchlist item web-down, last check 2026-10-14T23:30:00Z."
    )
    assert tasks[3]["references"] == ["cca/incidents/archive/2026/disk-full.md"]
    assert "Blocked on: vendor\nCheck after: 2026-10-20T21:30:00+00:00\n" in tasks[3]["description"]
    assert tasks[4]["implementationPlan"] == "Capture the headers"
    creates = [c for c in mcalls(menv) if c[:2] == ["task", "create"]]
    assert creates[0] == [
        "task",
        "create",
        f"--description={first['description']}",
        "--status=To Do",
        "--labels=watchlist:daily-backup,every:1d,area:server1-web,effort:e15",
        "--priority=high",
        "--due-date=2026-10-15",
        "--ref=cca/guides/servers/server1.md",
        "--plain",
        "--",
        "Item daily-backup",
    ]
    edits = [c for c in mcalls(menv) if c[:2] == ["task", "edit"]]
    assert edits == [
        ["task", "edit", "TASK-1", "--plan=Read the report", "--plain"],
        ["task", "edit", "TASK-5", "--plan=Capture the headers", "--plain"],
    ]
    # rerun: everything exists, nothing written
    before = len(mcalls(menv))
    out, _ = out_err(["migrate", path, "--apply", "--exclude", "outage"], capsys)
    assert out.splitlines()[-1] == "items 8: new 0, exists 6, done 1, excluded 1; warnings 0"
    assert all(c[:2] != ["task", "create"] for c in mcalls(menv)[before:])
    assert all(c[:2] != ["task", "edit"] for c in mcalls(menv)[before:])


def test_migrate_rerun_after_failure(menv, capsys):
    path = write_watchlist(menv, ITEMS)
    store(menv, [], fail_create=3)
    _, err = out_err(["migrate", path, "--apply"], capsys, code=2)
    assert "backlog task create failed: Error: disk full" in err
    assert len(state(menv)["tasks"]) == 2
    data = state(menv)
    data.pop("fail_create")
    (menv / "state.json").write_text(json.dumps(data))
    out, _ = out_err(["migrate", path, "--apply"], capsys)
    assert out.splitlines()[-1] == "items 8: new 5, exists 2, done 1, excluded 0; warnings 0"
    assert [t["title"] for t in state(menv)["tasks"]][2:] == [
        "Item cert-renewal",
        "Item disk-cleanup",
        "Item wait-reply",
        "Item old-incident",
        "Item outage",
    ]
    # TASK-1 lost its plan edit in the failed run: set now
    assert state(menv)["tasks"][0]["implementationPlan"] == "Read the report"
    assert "plan set TASK-1 <- daily-backup" in out


def test_migrate_warnings(menv, capsys):
    data = legacy(
        item("a", refs=["missing.md"], area="!!!", extra_key=1),
        item("b", "routine", "active", monitor_until="2026-10-01T00:00:00"),
        item("c", monitor_until="2026-10-30T00:00:00"),
    )
    out, err = out_err(["migrate", write_watchlist(menv, data)], capsys, code=1)
    assert err.splitlines() == [
        "cca: warning: a: area '!!!' has no label form, dropped",
        "cca: warning: a: ref not found, kept as is: missing.md",
        "cca: warning: a: unknown key extra_key not migrated",
        "cca: warning: b: monitoring ended 2026-10-01 (today shows it [ended])",  # 01:59 local
        "cca: warning: c: monitor_until dropped (not a daily check)",
    ]
    assert "warnings 5" in out.splitlines()[-1]


def test_migrate_preflight_lists_every_problem(menv, capsys):
    good = [item(f"ok-{n}") for n in range(3)]
    bad = [
        item("dup"),
        item("dup"),
        {"id": "x,y", "type": "chore", "state": "open", "name": ""},
        item("n1", "note", "active", next_action="do"),
        item("t1", valid_from="2026-01-01"),
        item("i1", "incident", "active"),
        item("d1", last_check="yesterday", check_after="soon", monitor_until="2026-13-01"),
        item("e1", effort="1h", prio="high", refs="a.md", once="yes"),
        item("s1", status=["x"], description="ok\nmulti", name="a\nb"),
        "not an item",
    ]
    data = legacy(*good, *bad)
    _, err = out_err(["migrate", write_watchlist(menv, data), "--exclude", "nope"], capsys, code=2)
    expected = [
        "item 5 (dup): duplicate id",
        "item 6 (x,y): id must match",
        "item 6 (x,y): type must be one of",
        "item 6 (x,y): state must be one of",
        "item 6 (x,y): name must be a non-empty one-line string",
        "item 7 (n1): state of a note must be idle or done",
        "item 7 (n1): next_action is not allowed on a note",
        "item 8 (t1): valid_from/valid_until are only allowed on notes",
        "item 9 (i1): file is required for an incident",
        "item 10 (d1): last_check must be never or an ISO timestamp",
        "item 10 (d1): check_after must be an ISO timestamp",
        "item 10 (d1): monitor_until must be an ISO timestamp",
        "item 11 (e1): effort must be one of",
        "item 11 (e1): prio must be one of",
        "item 11 (e1): refs must be a list",
        "item 11 (e1): once must be true or false",
        "item 12 (s1): name must be a non-empty one-line string",
        "item 12 (s1): status must be a string",
        "item 13: not an object",
        "--exclude nope: no such item",
    ]
    for line in expected:
        assert line in err, line
    assert "(s1): description" not in err  # multi-line description is fine
    assert mcalls(menv) == []  # nothing ran, nothing written


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (legacy(version="1.0"), "schema v1.0 is not supported"),
        ({"version": "2.0"}, "expected an object with an items list"),
    ],
)
def test_migrate_refuses_file(menv, capsys, data, message):
    _, err = out_err(["migrate", write_watchlist(menv, data)], capsys, code=2)
    assert message in err


def test_migrate_missing_file_and_statuses(menv, capsys):
    _, err = out_err(["migrate", "nope.json"], capsys, code=2)
    assert "cannot read nope.json" in err
    store(menv, [], statuses="To Do, In Progress, Done")
    _, err = out_err(["migrate", write_watchlist(menv, legacy(item("a")))], capsys, code=2)
    assert "backlog statuses lack Note" in err


def test_migrate_duplicate_label_in_backlog(menv, capsys):
    clash = {"id": "TASK-1", "labels": ["watchlist:a"], "isReady": True}
    store(menv, [clash, clash | {"id": "TASK-2"}])
    _, err = out_err(["migrate", write_watchlist(menv, legacy(item("a")))], capsys, code=2)
    assert "two tasks carry the label watchlist:a" in err


@pytest.mark.parametrize("labels", [["watchlist:a", "watchlist:b"], ["watchlist:"]])
def test_migrate_task_with_several_legacy_labels(menv, capsys, labels):
    store(menv, [{"id": "TASK-1", "labels": labels, "isReady": True}])
    data = legacy(item("a"), item("b"))
    _, err = out_err(["migrate", write_watchlist(menv, data)], capsys, code=2)
    assert "TASK-1 needs exactly one watchlist:<id> label" in err


# --- real backlog


@pytest.mark.skipif(shutil.which("backlog") is None, reason="backlog CLI not installed")
def test_real_backlog(tmp_path, monkeypatch, capsys):
    real = shutil.which("backlog")
    monkeypatch.setattr(watchlist, "today", lambda: TODAY)
    monkeypatch.setattr(watchlist_migrate, "LOCAL", UTC)
    monkeypatch.delenv("BACKLOG_CWD", raising=False)

    def backlog(*args):
        subprocess.run([real, *args], cwd=tmp_path, check=True, capture_output=True)

    backlog("init", "demo", "--defaults", "--no-git", "--integration-mode", "none")
    cfg = tmp_path / "backlog" / "config.yml"
    cfg.write_text(
        cfg.read_text().replace(
            'statuses: ["To Do", "In Progress", "Done"]',
            'statuses: ["Idea", "To Do", "In Progress", "Note", "Done"]',
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
        "Priority:",
        "none",
        "Notes:",
        "TASK-2 | 2026-10-14..2026-10-16 | Outage",
    ]
    data = legacy(
        item("deploy", next_action="-Run the deploy", effort="e1h", window="wany", prio="p1"),
        item("blocked", effort="e1h", window="wany", prio="p1"),
    )
    (tmp_path / "watchlist.json").write_text(json.dumps(data))
    assert main(["watchlist", "migrate", "watchlist.json", "--apply"]) == 0
    capsys.readouterr()
    backlog("task", "edit", "TASK-4", "--dep", "TASK-1")
    assert main(["watchlist", "ready", "--json"]) == 0
    ready = json.loads(capsys.readouterr().out)
    assert [t["id"] for t in ready["ready"]] == ["TASK-3"]  # TASK-4 waits for TASK-1
    assert ready["ready"][0]["implementationPlan"] == "-Run the deploy"
    assert ready["ready"][0]["labels"] == ["watchlist:deploy", "effort:e1h", "window:wany", "idle"]
    assert main(["watchlist", "next"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "TASK-3 | high | e1h | wany | Item deploy",
        "  next: -Run the deploy",
    ]
    assert main(["watchlist", "today"]) == 0
    assert capsys.readouterr().out.splitlines()[2:4] == [
        "Priority:",
        "TASK-3 | high | e1h | wany | Item deploy",
    ]
    assert main(["watchlist", "migrate", "watchlist.json", "--apply"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == (
        "items 2: new 0, exists 2, done 0, excluded 0; warnings 0"
    )
    assert main(["watchlist", "checked", "TASK-1"]) == 0
    assert capsys.readouterr().out == "checked TASK-1: next 2026-10-16\n"
    assert main(["watchlist", "today"]) == 0
    assert capsys.readouterr().out.splitlines()[:2] == ["Due:", "none"]
