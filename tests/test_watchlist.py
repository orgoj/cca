"""Tests for bin/cca-watchlist (schema v2).

The script has no .py suffix (it is installed as a symlink in PATH), so it is
loaded through importlib rather than a plain import.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "bin" / "cca-watchlist"


def _load_module():
    spec = importlib.util.spec_from_loader(
        "cca_watchlist", importlib.machinery.SourceFileLoader("cca_watchlist", str(SCRIPT))
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


watchlist = _load_module()


def run_cli(path: Path, *args, expect_ok: bool = True):
    """Run the CLI against a throwaway watchlist file."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--watchlist", str(path), *args],
        capture_output=True,
        text=True,
    )
    if expect_ok:
        assert result.returncode == 0, f"{args} failed: {result.stderr}"
    return result


def run_json(path: Path, *args):
    item_mutations = {
        "update", "add-routine", "add-note", "add-task", "add-incident",
        "edit", "park", "activate", "standby", "done",
    }
    if args and args[0] in item_mutations | {"list-today"} and "--json" not in args:
        args = (*args, "--json")
    return json.loads(run_cli(path, *args).stdout)


@pytest.fixture
def wl(tmp_path):
    """Empty v2 watchlist file."""
    path = tmp_path / "cca" / "watchlist.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": "2.0", "items": []}), encoding="utf-8")
    return path


@pytest.fixture
def v1_file(tmp_path):
    """A v1 file as written by the previous version of the tool."""
    path = tmp_path / "watchlist.json"
    path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "items": [
                    {
                        "id": "hetrix-status",
                        "type": "routine",
                        "name": "Hetrix status",
                        "description": "check",
                        "guide_keywords": "hetrix",
                        "last_check": "never",
                        "check_after": None,
                        "monitor_until": None,
                        "enabled": True,
                    },
                    {
                        "id": "old-thing",
                        "type": "routine",
                        "name": "Old thing",
                        "description": "done long ago",
                        "last_check": "2025-10-17T09:01:00",
                        "enabled": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------- unit tests


def test_slugify():
    assert watchlist.Watchlist.slugify("Test Name") == "test-name"
    assert watchlist.Watchlist.slugify("Jméno s diakritikou") == "jmeno-s-diakritikou"
    assert watchlist.Watchlist.slugify("  leading & trailing spaces  ") == "leading-trailing-spaces"
    assert watchlist.Watchlist.slugify("Special---Chars!!") == "special-chars"
    assert watchlist.Watchlist.slugify("server1 OOM kills") == "server1-oom-kills"


def test_parse_check_after():
    assert watchlist.Watchlist.parse_check_after("2025-10-16 morning") == "2025-10-16T06:00:00"
    assert watchlist.Watchlist.parse_check_after("2025-10-16 afternoon") == "2025-10-16T12:00:00"
    assert watchlist.Watchlist.parse_check_after("2025-10-16") == "2025-10-16T06:00:00"
    assert watchlist.Watchlist.parse_check_after("invalid date") is None
    assert watchlist.Watchlist.parse_check_after("2025-13-45") is None
    assert watchlist.Watchlist.parse_check_after(None) is None
    assert watchlist.Watchlist.parse_check_after("") is None


def test_parse_monitor_until():
    today = datetime.now(timezone.utc).date()
    assert (
        watchlist.Watchlist.parse_monitor_until("1 week") == f"{today + timedelta(days=7)}T00:00:00"
    )
    assert (
        watchlist.Watchlist.parse_monitor_until("3 days") == f"{today + timedelta(days=3)}T00:00:00"
    )
    assert (
        watchlist.Watchlist.parse_monitor_until("10 day")
        == f"{today + timedelta(days=10)}T00:00:00"
    )
    assert watchlist.Watchlist.parse_monitor_until("invalid duration") is None
    assert watchlist.Watchlist.parse_monitor_until(None) is None
    assert watchlist.Watchlist.parse_monitor_until("") is None


# ---------------------------------------------------------- CLI integration


def test_add_routine_is_active_and_shows_today(wl):
    item = run_json(wl, "add-routine", "--name", "Hetrix status", "--description", "check")
    assert item["state"] == "active"
    assert item["type"] == "routine"
    today = run_json(wl, "list-today")
    assert [i["id"] for i in today] == ["hetrix-status"]


def test_idle_item_never_in_list_today_but_is_searchable(wl, tmp_path):
    (tmp_path / "incidents").mkdir()
    (tmp_path / "incidents" / "x.md").write_text("ctx", encoding="utf-8")
    run_cli(
        wl,
        "add-task",
        "--name",
        "server1 web limits",
        "--description",
        "deploy limits",
        "--area",
        "server1",
        "--refs",
        "incidents/x.md",
        "--blocked-on",
        "user approval",
    )
    assert run_json(wl, "list-today") == []
    found = run_json(wl, "search", "web limits", "--json")
    assert [i["id"] for i in found] == ["server1-web-limits"]
    # searchable by other text fields; reference paths require --deep
    assert run_json(wl, "search", "user approval", "--json")[0]["blocked_on"] == "user approval"
    assert run_json(wl, "search", "server1", "--json")[0]["area"] == "server1"
    assert run_json(wl, "search", "incidents/x.md", "--deep", "--json")


def test_idle_requires_at_least_one_ref(wl):
    result = run_cli(wl, "add-task", "--name", "No context", "--description", "d", expect_ok=False)
    assert result.returncode == 1
    assert "at least one --refs" in result.stderr


def test_duplicate_id_is_refused(wl):
    run_cli(wl, "add-routine", "--name", "Hetrix status", "--description", "check")
    result = run_cli(
        wl, "add-routine", "--name", "Hetrix status", "--description", "again", expect_ok=False
    )
    assert result.returncode == 1
    assert "already exists" in result.stderr


def test_invalid_date_is_refused_not_silently_dropped(wl):
    result = run_cli(
        wl,
        "add-routine",
        "--name",
        "X",
        "--description",
        "d",
        "--check-after",
        "next tuesday",
        expect_ok=False,
    )
    assert result.returncode == 1
    assert "unparseable --check-after" in result.stderr


def test_park_activate_done_roundtrip(wl, tmp_path):
    (tmp_path / "guide.md").write_text("g", encoding="utf-8")
    run_cli(wl, "add-routine", "--name", "Thing", "--description", "d", "--refs", "guide.md")
    assert run_json(wl, "park", "thing", "--blocked-on", "user approval")["state"] == "idle"
    assert run_json(wl, "list-today") == []

    activated = run_json(wl, "activate", "thing", "--check-after", "2026-09-04 morning")
    assert activated["state"] == "active"
    assert activated["check_after"] == "2026-09-04T06:00:00"

    assert run_json(wl, "done", "thing")["state"] == "done"
    assert run_json(wl, "list", "--json") == []
    assert len(run_json(wl, "list", "--all", "--json")) == 1


def test_check_after_in_the_future_hides_item_today(wl):
    future = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    run_cli(wl, "add-routine", "--name", "Later", "--description", "d", "--check-after", future)
    assert run_json(wl, "list-today") == []


def test_edit_changes_fields_and_refs(wl, tmp_path):
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    run_cli(wl, "add-routine", "--name", "Thing", "--description", "d", "--refs", "a.md")
    item = run_json(wl, "edit", "thing", "--area", "storage", "--add-ref", "b.md")
    assert item["area"] == "storage"
    assert item["refs"] == ["a.md", "b.md"]
    item = run_json(wl, "edit", "thing", "--remove-ref", "a.md")
    assert item["refs"] == ["b.md"]


def test_edit_empty_schedule_clears_each_field(wl):
    item = run_json(
        wl, "add-routine", "--name", "Thing", "--description", "d",
        "--check-after", "2026-10-01", "--monitor-until", "1 week",
    )
    monitor_until = item["monitor_until"]

    item = run_json(wl, "edit", "thing", "--check-after", "")
    assert item["check_after"] is None
    assert item["monitor_until"] == monitor_until

    item = run_json(wl, "edit", "thing", "--monitor-until", "")
    assert item["check_after"] is None
    assert item["monitor_until"] is None
    assert json.loads(wl.read_text(encoding="utf-8"))["items"][0] == item


def test_edit_without_any_change_is_refused(wl):
    run_cli(wl, "add-routine", "--name", "Thing", "--description", "d")
    result = run_cli(wl, "edit", "thing", expect_ok=False)
    assert result.returncode == 1
    assert "at least one field" in result.stderr


def test_list_filters_by_area_and_state(wl, tmp_path):
    (tmp_path / "r.md").write_text("r", encoding="utf-8")
    run_cli(wl, "add-routine", "--name", "A", "--description", "d", "--area", "server1")
    run_cli(
        wl, "add-task", "--name", "B", "--description", "d", "--area", "server2", "--refs", "r.md"
    )
    assert [i["id"] for i in run_json(wl, "list", "--area", "server1", "--json")] == ["a"]
    assert [i["id"] for i in run_json(wl, "list", "--state", "idle", "--json")] == ["b"]
    assert [i["id"] for i in run_json(wl, "list", "--type", "task", "--json")] == ["b"]


def test_once_task_is_done_after_first_check(wl):
    run_cli(wl, "add-routine", "--name", "One shot", "--description", "d", "--once")
    assert run_json(wl, "update", "one-shot")["state"] == "done"
    assert run_json(wl, "list-today") == []


def test_incident_only_shows_today_while_monitoring(wl, tmp_path):
    (tmp_path / "inc.md").write_text("i", encoding="utf-8")
    run_cli(wl, "add-incident", "--name", "Boom", "--file", "inc.md", "--status", "monitoring")
    assert len(run_json(wl, "list-today")) == 1
    item_id = run_json(wl, "list", "--json")[0]["id"]
    run_cli(wl, "edit", item_id, "--status", "resolved")
    assert run_json(wl, "list-today") == []


def test_incident_file_lands_in_refs(wl, tmp_path):
    (tmp_path / "inc.md").write_text("i", encoding="utf-8")
    item = run_json(
        wl, "add-incident", "--name", "Boom", "--file", "inc.md", "--status", "monitoring"
    )
    assert item["refs"] == ["inc.md"]


def test_incident_file_under_cca_is_normalized(wl):
    incident = wl.parent / "incidents" / "x.md"
    incident.parent.mkdir()
    incident.write_text("i", encoding="utf-8")
    result = run_cli(
        wl,
        "add-incident",
        "--name",
        "Boom",
        "--file",
        "incidents/x.md",
        "--status",
        "monitoring",
        "--json",
    )
    item = json.loads(result.stdout)
    assert result.stderr == ""
    assert item["file"] == "cca/incidents/x.md"
    assert item["refs"] == ["cca/incidents/x.md"]


def test_incident_with_missing_file_is_refused_without_write(wl):
    result = run_cli(
        wl,
        "add-incident",
        "--name",
        "Ghost",
        "--file",
        "incidents/missing.md",
        "--status",
        "monitoring",
        expect_ok=False,
    )
    assert result.returncode == 1
    assert "ref not found on disk" in result.stderr
    assert json.loads(wl.read_text(encoding="utf-8"))["items"] == []


def test_v1_file_is_refused_until_migrated(v1_file):
    result = run_cli(v1_file, "list-today", expect_ok=False)
    assert result.returncode == 1
    assert "migrate" in result.stderr


def test_migrate_maps_enabled_to_state(v1_file):
    report = run_json(v1_file, "migrate")
    assert report["migrated"] == 2
    assert report["version"] == "2.0"
    items = {i["id"]: i for i in run_json(v1_file, "list", "--all", "--json")}
    assert items["hetrix-status"]["state"] == "active"
    assert items["old-thing"]["state"] == "done"
    assert "enabled" not in items["hetrix-status"]
    assert items["hetrix-status"]["refs"] == []
    # migrated file is usable straight away
    assert [i["id"] for i in run_json(v1_file, "list-today")] == ["hetrix-status"]


def test_unknown_major_version_is_refused(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"version": "9.0", "items": []}), encoding="utf-8")
    result = run_cli(path, "list-today", expect_ok=False)
    assert result.returncode == 1
    assert "schema v9.0" in result.stderr


def test_migrate_refuses_unknown_major_version(tmp_path):
    path = tmp_path / "watchlist.json"
    original = json.dumps({"version": "9.0", "items": [{"future": True}]})
    path.write_text(original, encoding="utf-8")
    result = run_cli(path, "migrate", expect_ok=False)
    assert result.returncode == 1
    assert "Refusing to rewrite" in result.stderr
    assert path.read_text(encoding="utf-8") == original


def test_compatible_minor_version_survives_a_write(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"version": "2.1", "items": []}), encoding="utf-8")
    run_cli(path, "add-routine", "--name", "Thing", "--description", "d")
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == "2.1"


def test_unknown_fields_survive_a_write(wl):
    data = json.loads(wl.read_text(encoding="utf-8"))
    data["items"].append(
        {
            "id": "future-item",
            "type": "routine",
            "name": "Future",
            "state": "active",
            "description": "d",
            "refs": [],
            "last_check": "never",
            "some_future_field": {"kept": True},
        }
    )
    wl.write_text(json.dumps(data), encoding="utf-8")
    run_cli(wl, "edit", "future-item", "--area", "storage")
    reloaded = {i["id"]: i for i in json.loads(wl.read_text(encoding="utf-8"))["items"]}
    assert reloaded["future-item"]["some_future_field"] == {"kept": True}


def test_missing_ref_warns_but_succeeds(wl):
    result = run_cli(
        wl, "add-task", "--name", "Ghost", "--description", "d", "--refs", "nope/missing.md"
    )
    assert "WARNING: ref not found" in result.stderr


@pytest.mark.parametrize(
    "location",
    ["incidents", "deniky", "incidents/archive/2026", "guides", "guides/servers"],
)
def test_bare_ref_found_in_standard_locations(wl, location):
    """A ref given as a bare filename is resolved in incidents/, deniky/,
    the incident archive and guides/ — not only repo-relative."""
    target = wl.parent / location
    target.mkdir(parents=True, exist_ok=True)
    (target / "2026-09-06-thing.md").write_text("x", encoding="utf-8")
    result = run_cli(
        wl, "add-task", "--name", "Bare", "--description", "d",
        "--refs", "2026-09-06-thing.md",
    )
    assert "WARNING: ref not found" not in result.stderr


def test_bare_ref_missing_everywhere_still_warns(wl):
    (wl.parent / "incidents").mkdir()
    result = run_cli(
        wl, "add-task", "--name", "Nowhere", "--description", "d", "--refs", "nothing.md"
    )
    assert "WARNING: ref not found" in result.stderr


def test_failed_write_leaves_original_intact(wl, monkeypatch):
    """A crash mid-save must not truncate the register."""
    before = wl.read_text(encoding="utf-8")
    module = _load_module()
    instance = module.Watchlist(wl)
    monkeypatch.setattr(
        module.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
    )
    with pytest.raises(SystemExit):
        instance.add_routine(name="Thing", description="d")
    assert wl.read_text(encoding="utf-8") == before
    assert not [p for p in wl.parent.glob(".watchlist-*.tmp")]


def test_concurrent_writers_do_not_lose_items(wl):
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "--watchlist",
                str(wl),
                "add-routine",
                "--name",
                f"Routine {number}",
                "--description",
                "check",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for number in range(12)
    ]
    results = [process.communicate() + (process.returncode,) for process in processes]
    assert all(returncode == 0 for _, _, returncode in results), results
    assert len(json.loads(wl.read_text(encoding="utf-8"))["items"]) == 12


def test_show_returns_single_item(wl):
    run_cli(wl, "add-routine", "--name", "Thing", "--description", "d")
    assert run_json(wl, "show", "thing", "--json")["id"] == "thing"
    result = run_cli(wl, "show", "nope", expect_ok=False)
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_tag_fields_default_to_null_and_can_be_edited(wl):
    item = run_json(wl, "add-routine", "--name", "Thing", "--description", "d")
    assert {field: item[field] for field in ("effort", "change_risk", "window", "prio")} == {
        "effort": None,
        "change_risk": None,
        "window": None,
        "prio": None,
    }

    item = run_json(
        wl,
        "edit",
        "thing",
        "--effort",
        "e15",
        "--change-risk",
        "r2",
        "--window",
        "woff",
        "--prio",
        "p1",
    )
    assert (item["effort"], item["change_risk"], item["window"], item["prio"]) == (
        "e15",
        "r2",
        "woff",
        "p1",
    )


def test_change_risk_is_separate_from_incident_severity(wl, tmp_path):
    (tmp_path / "inc.md").write_text("i", encoding="utf-8")
    item = run_json(
        wl,
        "add-incident",
        "--name",
        "Boom",
        "--file",
        "inc.md",
        "--status",
        "monitoring",
        "--risk",
        "HIGH",
        "--change-risk",
        "r1",
        "--window",
        "wany",
    )
    assert item["risk"] == "HIGH"
    assert item["change_risk"] == "r1"
    shown = run_cli(wl, "show", item["id"]).stdout
    assert "Incident severity: HIGH" in shown
    assert "Change risk: r1" in shown


def test_window_below_change_risk_minimum_is_raised_on_add(wl):
    added = run_cli(
        wl,
        "add-routine",
        "--name",
        "Unsafe",
        "--description",
        "d",
        "--change-risk",
        "r3",
        "--window",
        "woff",
        "--json",
    )
    assert "woff raised to wnight" in added.stderr
    assert json.loads(added.stdout)["window"] == "wnight"
    assert run_json(wl, "show", "unsafe", "--json")["window"] == "wnight"


def test_window_below_change_risk_minimum_is_raised_on_add_task_and_incident(wl):
    task = run_cli(
        wl,
        "add-task",
        "--name",
        "Risky task",
        "--description",
        "d",
        "--state",
        "active",
        "--change-risk",
        "r2",
        "--window",
        "wany",
        "--json",
    )
    assert "wany raised to woff" in task.stderr
    assert json.loads(task.stdout)["window"] == "woff"

    incident_file = wl.parent / "incidents" / "2026-01-01-x.md"
    incident_file.parent.mkdir()
    incident_file.write_text("i", encoding="utf-8")
    incident = run_cli(
        wl,
        "add-incident",
        "--name",
        "Risky incident",
        "--file",
        "incidents/2026-01-01-x.md",
        "--status",
        "monitoring",
        "--change-risk",
        "r3",
        "--window",
        "wany",
        "--json",
    )
    assert "wany raised to wnight" in incident.stderr
    assert json.loads(incident.stdout)["window"] == "wnight"


def test_window_below_change_risk_minimum_is_raised_on_edit_and_set_state(wl):
    run_cli(
        wl,
        "add-routine",
        "--name",
        "Safe",
        "--description",
        "d",
        "--change-risk",
        "r1",
        "--window",
        "wany",
    )
    edited = run_cli(wl, "edit", "safe", "--change-risk", "r2", "--json")
    assert "wany raised to woff" in edited.stderr
    assert json.loads(edited.stdout)["window"] == "woff"
    assert run_json(wl, "show", "safe", "--json")["window"] == "woff"

    # a window lowered below the stored risk is raised back on the next edit
    edited = run_cli(wl, "edit", "safe", "--window", "wany", "--json")
    assert "wany raised to woff" in edited.stderr
    assert json.loads(edited.stdout)["window"] == "woff"

    # a state change re-checks an item whose stored tags already violate the minimum
    stored = json.loads(wl.read_text(encoding="utf-8"))
    stored["items"][0]["window"] = "wany"
    wl.write_text(json.dumps(stored), encoding="utf-8")
    activated = run_cli(wl, "activate", "safe", "--json")
    assert "wany raised to woff" in activated.stderr
    assert json.loads(activated.stdout)["window"] == "woff"


def test_list_filters_by_all_tags_and_max_change_risk(wl):
    for name, risk, window in (("Low", "r0", "wany"), ("High", "r2", "woff")):
        run_cli(
            wl,
            "add-routine",
            "--name",
            name,
            "--description",
            "d",
            "--effort",
            "e15",
            "--change-risk",
            risk,
            "--window",
            window,
            "--prio",
            "p2",
        )
    assert [item["id"] for item in run_json(wl, "list", "--change-risk", "r2", "--json")] == [
        "high"
    ]
    assert [item["id"] for item in run_json(wl, "list", "--max-change-risk", "r1", "--json")] == [
        "low"
    ]
    matching = run_json(wl, "list", "--effort", "e15", "--window", "wany", "--prio", "p2", "--json")
    assert len(matching) == 1


def test_ready_filters_sorts_and_reports_untagged(wl):
    def add(name, effort=None, risk="r0", window="wany", prio="p3", blocked=False):
        args = [
            "add-routine",
            "--name",
            name,
            "--description",
            "d",
            "--next-action",
            f"Do {name}",
            "--change-risk",
            risk,
            "--window",
            window,
            "--prio",
            prio,
        ]
        if effort:
            args.extend(("--effort", effort))
        if blocked:
            args.extend(("--blocked-on", "user approval"))
        run_cli(wl, *args)

    add("Second", "e15", prio="p2")
    add("First", "e1h", prio="p1")
    add("Too long", "e4h", prio="p1")
    add("Night only", "e15", risk="r3", window="wnight", prio="p1")
    add("Blocked", "e15", prio="p1", blocked=True)
    add("Unknown")
    run_cli(wl, "done", "second")
    add("Second open", "e15", prio="p2")

    result = run_json(wl, "ready", "--time", "1h", "--window", "woff", "--json")
    assert [item["id"] for item in result["ready"]] == ["first", "second-open"]
    assert result["ready"][0]["effective_window"] == "wany"
    assert [item["id"] for item in result["untagged"]] == ["unknown"]

    with_blocked = run_json(
        wl,
        "ready",
        "--time",
        "15m",
        "--window",
        "wany",
        "--include-blocked",
        "--max-change-risk",
        "r0",
        "--json",
    )
    assert [item["id"] for item in with_blocked["ready"]] == ["blocked", "second-open"]
    plain = run_cli(wl, "ready", "--time", "15m", "--window", "wany").stdout
    assert "second-open · p2 · e15 · r0 · wany · Do Second open" in plain
    assert "Untagged (effort=null): 1" in plain


def test_ready_uses_change_risk_minimum_when_window_is_unset(wl):
    run_cli(
        wl,
        "add-routine",
        "--name",
        "Shared change",
        "--description",
        "d",
        "--next-action",
        "Apply shared config",
        "--effort",
        "e15",
        "--change-risk",
        "r2",
        "--prio",
        "p2",
    )
    assert run_json(wl, "ready", "--time", "15m", "--window", "wany", "--json")["ready"] == []
    ready = run_json(wl, "ready", "--time", "15m", "--window", "woff", "--json")["ready"]
    assert ready[0]["id"] == "shared-change"
    assert ready[0]["window"] is None
    assert ready[0]["effective_window"] == "woff"


def test_note_lifecycle_and_queries(wl):
    note = run_json(
        wl,
        "add-note",
        "--name",
        "Power maintenance",
        "--description",
        "Possible outage",
        "--prio",
        "p1",
        "--valid-from",
        "2026-09-16",
        "--valid-until",
        "2026-09-17",
    )
    assert note["state"] == "idle"
    assert note["prio"] == "p1"
    assert "next_action" not in note
    assert run_json(wl, "search", "outage", "--json") == [note]
    assert run_json(wl, "list", "--type", "note", "--prio", "p1", "--json") == [note]
    assert "2026-09-16 through 2026-09-17" in run_cli(wl, "show", note["id"]).stdout
    assert "2026-09-16 through 2026-09-17" not in run_cli(wl, "list").stdout
    assert run_json(wl, "list-today") == []
    assert run_json(wl, "ready", "--json") == {"ready": [], "untagged": []}
    run_cli(wl, "migrate")
    run_cli(wl, "edit", note["id"], "--valid-from", "", "--valid-until", "")
    edited = run_json(wl, "show", note["id"], "--json")
    assert edited["valid_from"] is None and edited["valid_until"] is None
    assert "next_action" not in edited
    run_cli(wl, "park", note["id"])
    run_cli(wl, "done", note["id"])
    assert run_json(wl, "search", "outage", "--json") == []
    assert len(run_json(wl, "search", "outage", "--all", "--json")) == 1


@pytest.mark.parametrize(
    "args",
    [
        ("--valid-from", "2026-02-30"),
        ("--valid-until", "2026-9-16"),
        ("--valid-until", ""),
        ("--valid-from", "2026-09-17", "--valid-until", "2026-09-16"),
        ("--next-action", "Do something"),
        ("--prio", "p0"),
    ],
)
def test_invalid_note_creation_does_not_write(wl, args):
    before = wl.read_bytes()
    result = run_cli(
        wl, "add-note", "--name", "Note", "--description", "Context", *args, expect_ok=False
    )
    assert result.returncode != 0
    assert wl.read_bytes() == before


def test_discovery_outputs_one_line_per_item_and_show_keeps_detail(wl):
    item = run_json(
        wl, "add-routine", "--name", "Power\ncheck", "--description", "Long trigger details",
        "--next-action", "Capture logs", "--refs", "guides/power.md",
    )
    for args in (("list",), ("list-today",)):
        lines = run_cli(wl, *args).stdout.splitlines()
        assert lines == [f"{item['id']} | routine | active | - | - | Power check"]
        assert "guides/power.md" not in lines[0]
        assert "Long trigger details" not in lines[0]
    assert run_cli(wl, "search", "power", "--brief").stdout.strip() == item["id"]
    assert "Long trigger details" in run_cli(wl, "show", item["id"]).stdout
    assert run_json(wl, "list-today")[0]["refs"] == ["guides/power.md"]


@pytest.mark.parametrize("command", ["list", "search", "list-today"])
def test_discovery_limits_large_result_sets(wl, command):
    items = [
        {
            "id": f"power-{n:02d}", "name": f"Power {n:02d}", "type": "routine",
            "state": "active", "description": "Long details", "last_check": "never",
            "refs": ["guides/power.md"],
        }
        for n in range(25)
    ]
    wl.write_text(json.dumps({"version": "2.0", "items": items}), encoding="utf-8")
    args = ("search", "power") if command == "search" else (command,)
    lines = run_cli(wl, *args).stdout.splitlines()
    if command == "search":
        assert len(lines) == 22
        assert lines[0] == "25 matches; first 20:"
        assert lines[1:21] == [i["id"] for i in items[:20]]
        assert "more specific search query" in lines[-1]
    else:
        assert len(lines) == 21
        assert [line.split(" | ")[0] for line in lines[:20]] == [i["id"] for i in items[:20]]
        assert "Showing 20 of 25 items" in lines[-1]
        assert "show ID for details" in lines[-1]
    assert len(run_json(wl, *args, "--json")) == 25


def test_search_words_ranking_deep_and_states(wl):
    items = [
        {"id": "deep", "name": "Unrelated", "state": "active", "refs": ["guides/power-check.md"]},
        {"id": "description", "name": "Unrelated", "state": "idle", "description": "Power check"},
        {"id": "mixed", "name": "Power", "state": "standby", "next_action": "Check logs"},
        {"id": "power-check", "name": "Power check", "state": "active"},
        {"id": "keywords", "name": "Unrelated", "state": "active", "guide_keywords": "Power check"},
        {"id": "closed", "name": "Power check", "state": "done"},
    ]
    wl.write_text(json.dumps({"version": "2.0", "items": items}), encoding="utf-8")
    assert [i["id"] for i in run_json(wl, "search", "POWER CHECK", "--json")] == [
        "power-check", "keywords", "mixed", "description"
    ]
    assert [i["id"] for i in run_json(wl, "search", "power check", "--deep", "--json")] == [
        "power-check", "keywords", "mixed", "description", "deep"
    ]
    assert [i["id"] for i in run_json(wl, "search", "power check", "--all", "--json")] == [
        "power-check", "keywords", "closed", "mixed", "description"
    ]
    assert [i["id"] for i in run_json(wl, "search", "power check", "--state", "idle", "--json")] == [
        "description"
    ]
    assert [i["id"] for i in run_json(wl, "search", "power check", "--state", "done", "--json")] == [
        "closed"
    ]
    assert run_cli(wl, "search", "power check", "--brief", "--json", expect_ok=False).returncode != 0


def test_search_single_brief_done_marker_and_no_open_match(wl):
    items = [
        {"id": "power-check", "name": "Power check", "state": "active", "description": "Read logs"},
        {"id": "archived", "name": "Archived power", "state": "done", "description": "Historic"},
    ]
    wl.write_text(json.dumps({"version": "2.0", "items": items}), encoding="utf-8")
    assert run_cli(wl, "search", "power-check", "--brief").stdout.strip() == "power-check"
    assert "Description: Read logs" in run_cli(wl, "search", "power-check").stdout
    assert run_cli(wl, "search", "archived").stdout.strip() == "0 otevrenych; 1 uzavrenych (--all)"
    assert run_cli(wl, "search", "missing").stdout.strip() == "0 otevrenych; 0 uzavrenych (--all)"
    assert run_cli(wl, "search", "power", "--all", "--brief").stdout.splitlines() == [
        "power-check", "archived | Archived power [done]"
    ]
    assert "State: done" in run_cli(wl, "search", "archived", "--state", "done").stdout
    assert run_json(wl, "search", "archived", "--json") == []


@pytest.mark.parametrize(
    "command,args,expected_id",
    [
        ("add-routine", ("--name", "Routine", "--description", "Check"), "routine"),
        ("add-task", ("--name", "Task", "--description", "Do", "--state", "active"), "task"),
        ("add-note", ("--name", "Note", "--description", "Info"), "note"),
        ("add-incident", ("--name", "Incident", "--file", "incident.md", "--status", "monitoring"), None),
    ],
)
def test_add_commands_confirm_briefly_and_offer_json(wl, command, args, expected_id):
    if command == "add-incident":
        (wl.parent / "incident.md").write_text("context", encoding="utf-8")
    result = run_cli(wl, command, *args)
    item = run_json(wl, "list", "--json")[0]
    if expected_id:
        assert item["id"] == expected_id
    else:
        assert item["id"].startswith("incident-")
    assert result.stdout == f"{command}: {item['id']}\n"
    assert len(result.stdout.splitlines()) == 1


def test_item_mutations_confirm_briefly_and_json_retains_item(wl):
    item = run_json(
        wl, "add-routine", "--name", "Routine", "--description", "Check",
        "--refs", "guides/context.md",
    )
    for command, extra in (
        ("edit", ("--description", "Changed")),
        ("update", ("--timestamp", "2026-09-27T12:00:00")),
        ("park", ()),
        ("standby", ()),
        ("activate", ()),
        ("done", ()),
    ):
        result = run_cli(wl, command, item["id"], *extra)
        assert result.stdout == f"{command}: {item['id']}\n"
    assert run_json(wl, "show", item["id"], "--json")["state"] == "done"
    assert run_json(wl, "edit", item["id"], "--description", "Again")["description"] == "Again"


@pytest.mark.parametrize(
    "args",
    [
        ("activate", "note"),
        ("update", "note"),
        ("edit", "note", "--next-action", ""),
        ("edit", "note", "--effort", "e15"),
        ("edit", "note", "--change-risk", "r0"),
        ("edit", "note", "--window", "wany"),
        ("park", "note", "--blocked-on", "approval"),
        ("edit", "note", "--check-after", "2026-09-16"),
        ("edit", "note", "--monitor-until", "1 day"),
        ("edit", "note", "--valid-from", "2026-09-18"),
        ("edit", "note", "--valid-until", "invalid"),
    ],
)
def test_invalid_note_mutation_does_not_write(wl, args):
    run_cli(
        wl, "add-note", "--name", "Note", "--description", "Context", "--valid-until", "2026-09-17"
    )
    before = wl.read_bytes()
    assert run_cli(wl, *args, expect_ok=False).returncode != 0
    assert wl.read_bytes() == before


def test_note_expiry_uses_inclusive_local_dates(wl, monkeypatch):
    class LocalDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            # The local date has crossed midnight while UTC is still yesterday.
            if tz is None:
                return cls(2026, 9, 17, 0, 30)
            return cls(2026, 9, 16, 22, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(watchlist, "datetime", LocalDateTime)
    store = watchlist.Watchlist(wl)
    store.add_note("Expired", "d", valid_until="2026-09-16")
    store.add_note("Today", "d", valid_from="2026-09-17", valid_until="2026-09-17")
    store.add_note("Future", "d", valid_from="2026-09-18")
    store.add_note("Unlimited", "d")
    assert [i["id"] for i in store.list_items(expired=True)] == ["expired"]
    assert [i["id"] for i in store.list_items(current=True)] == ["today", "unlimited"]
    store.set_state("expired", "done")
    assert store.list_items(expired=True) == []
    assert len(store.list_items(expired=True, include_done=True)) == 1


def test_note_cli_validity_filters_and_first_file(tmp_path):
    path = tmp_path / "watchlist.json"
    note = run_json(path, "add-note", "--name", "Permanent", "--description", "d")
    assert note["prio"] == "p2"
    run_cli(
        path,
        "add-note",
        "--name",
        "Expired",
        "--description",
        "d",
        "--valid-until",
        "2000-01-01",
        "--area",
        "server1",
        "--prio",
        "p1",
    )
    assert run_json(path, "list", "--current", "--json") == [note]
    assert [
        i["id"]
        for i in run_json(path, "list", "--expired", "--area", "server1", "--prio", "p1", "--json")
    ] == ["expired"]
    assert run_cli(path, "list", "--expired", "--current", expect_ok=False).returncode != 0
    assert run_cli(path, "list", "--expired", "--type", "task", expect_ok=False).returncode != 0


def test_next_selection_and_constraints(wl):
    store = watchlist.Watchlist(wl)

    def add(name, **changes):
        args = dict(
            name=name,
            description="d",
            effort="e15",
            change_risk="r0",
            next_action="Apply config",
            prio="p2",
            area="server1",
        )
        args.update(changes)
        return store.add_routine(**args)

    add("Low", prio="p3")
    add("Unset", prio=None)
    add("Priority", prio="p1", effort="e1h")
    add("B tie")
    add("A tie")
    add("Blocked", prio="p1", blocked_on="approval")
    add("Done", prio="p1", state="done")
    add("No action", prio="p1", next_action="  ")
    add("Future", prio="p1", check_after="2099-01-01")
    add("Untagged", prio="p1", effort=None)
    add("Large", prio="p1", effort="exl")
    add("Night", prio="p1", change_risk="r3")
    add("Other", prio="p1", area="server2")
    before = wl.read_bytes()
    assert run_json(wl, "next", "--area", "server1", "--json")["id"] == "priority"
    assert run_json(wl, "next", "--area", "server1", "--time", "15m", "--json")["id"] == "a-tie"
    assert (
        run_json(wl, "next", "--area", "server1", "--time", "15m", "--window", "wnight", "--json")[
            "id"
        ]
        == "night"
    )
    assert (
        run_json(
            wl,
            "next",
            "--area",
            "server1",
            "--time",
            "15m",
            "--window",
            "wnight",
            "--max-change-risk",
            "r0",
            "--json",
        )["id"]
        == "a-tie"
    )
    assert "ID: priority" in run_cli(wl, "next", "--area", "server1").stdout
    assert run_json(wl, "next", "--area", "missing", "--json") is None
    assert run_cli(wl, "next", "--area", "missing").stdout.strip() == "No actionable items found"
    assert wl.read_bytes() == before


def test_manually_tagged_note_never_becomes_work(wl):
    store = watchlist.Watchlist(wl)
    note = store.add_note("Note", "d")
    note.update(state="active", effort="e15", change_risk="r0", next_action="Do it")
    assert store.list_today() == []
    assert store.ready_items("e1h", "wany", None) == ([], [])
    assert store.next_item() is None
    note.pop("effort")
    assert store.ready_items("e1h", "wany", None) == ([], [])


@pytest.mark.parametrize("initial", ["idle", "active"])
@pytest.mark.parametrize("blocker", ["", "approval"])
def test_standby_transitions_preserve_blocker_and_capture(wl, initial, blocker):
    run_cli(
        wl, "add-task", "--name", "Capture outage", "--description", "When power fails",
        "--next-action", "Capture voltage and logs", "--state", initial,
        "--refs", "guides/power.md", "--blocked-on", blocker,
    )
    item = run_json(wl, "standby", "capture-outage")
    assert item["state"] == "standby"
    assert item["blocked_on"] == blocker
    assert run_json(wl, "list", "--standby", "--json") == [item]
    plain = run_cli(wl, "list", "--standby").stdout
    assert plain.strip() == "capture-outage | task | standby | - | - | Capture outage"
    shown = run_cli(wl, "show", "capture-outage").stdout
    assert "When power fails" in shown
    assert "Capture voltage and logs" in shown
    active = run_json(wl, "activate", "capture-outage")
    assert active["state"] == "active"
    assert active["blocked_on"] == blocker
    assert active["next_action"] == item["next_action"]


@pytest.mark.parametrize("tagged", [True, False])
def test_standby_excluded_from_all_work_selections(wl, tagged):
    args = ["--effort", "e15"] if tagged else []
    run_cli(
        wl, "add-routine", "--name", "Capture", "--description", "When outage occurs",
        "--next-action", "Collect logs", "--change-risk", "r0", *args,
    )
    run_cli(wl, "standby", "capture")
    for blocker in ("", "approval"):
        run_cli(wl, "edit", "capture", "--blocked-on", blocker)
        assert run_json(wl, "list-today") == []
        assert run_json(wl, "ready", "--json") == {"ready": [], "untagged": []}
        assert run_json(wl, "ready", "--include-blocked", "--json") == {
            "ready": [], "untagged": []
        }
        assert run_json(wl, "next", "--json") is None


def test_list_all_includes_every_state_and_notes_and_honors_filters(wl):
    for state in ("active", "idle", "standby", "done"):
        run_cli(
            wl, "add-task", "--name", state, "--description", "Trigger",
            "--state", state, "--refs", "guides/context.md", "--area", "server1",
        )
    run_cli(wl, "add-note", "--name", "Context", "--description", "Information")
    assert {i["id"] for i in run_json(wl, "list", "--all", "--json")} == {
        "active", "idle", "standby", "done", "context"
    }
    assert {i["id"] for i in run_json(wl, "list", "--json")} == {
        "active", "idle", "standby", "context"
    }
    assert [i["id"] for i in run_json(wl, "search", "Trigger", "--json")] == [
        "active", "idle", "standby"
    ]
    assert [i["id"] for i in run_json(wl, "list", "--all", "--standby", "--json")] == [
        "standby"
    ]
    assert run_json(wl, "list", "--standby", "--area", "server2", "--json") == []
    assert run_json(wl, "list", "--standby", "--type", "note", "--json") == []
    assert run_cli(wl, "list", "--standby", "--state", "active", expect_ok=False).returncode != 0
    help_text = " ".join(run_cli(wl, "list", "--help").stdout.split())
    assert "Include all states and types (including standby and done)" in help_text
    assert "explicit filters still apply" in help_text


def test_note_cannot_enter_standby(wl):
    run_cli(wl, "add-note", "--name", "Context", "--description", "Information")
    before = wl.read_bytes()
    for args in (("standby", "context"), ("edit", "context", "--state", "standby")):
        result = run_cli(wl, *args, expect_ok=False)
        assert result.returncode != 0
        assert "notes must be idle or done" in result.stderr
        assert wl.read_bytes() == before
