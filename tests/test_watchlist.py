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
    # searchable by every text field, not just name
    assert run_json(wl, "search", "user approval", "--json")[0]["blocked_on"] == "user approval"
    assert run_json(wl, "search", "server1", "--json")[0]["area"] == "server1"
    assert run_json(wl, "search", "incidents/x.md", "--json")


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


def test_window_below_change_risk_minimum_is_refused_on_add_and_edit(wl):
    rejected = run_cli(
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
        expect_ok=False,
    )
    assert "wnight minimum" in rejected.stderr

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
    before = wl.read_text(encoding="utf-8")
    rejected = run_cli(wl, "edit", "safe", "--change-risk", "r2", expect_ok=False)
    assert "woff minimum" in rejected.stderr
    assert wl.read_text(encoding="utf-8") == before


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
