"""cca hetrix: options, output and exit codes.

A local HTTP server plays the HetrixTools API v3 (the module's API_BASE points at it);
the token comes from a fake `sops` on a PATH that holds only fake tools.
"""

import json
import stat
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cca.cli import main
from cca.commands import hetrix

TOKEN = "hetrix-token-sentinel"
NOW = 1767268800  # 2026-01-01 12:00:00 UTC
HOUR = 3600
CREDENTIALS = {
    "credentials": {
        "hetrix": {"origins": ["https://api.hetrixtools.com"], "bearer": TOKEN},
        "other": {"origins": ["https://api.example.com"], "bearer": "other-token-sentinel"},
    }
}


def mid(n: int) -> str:
    return f"{n:032x}"


def monitor(n: int, name: str, status: str = "up", changed: int = NOW - 2 * HOUR, **extra):
    return {
        "id": mid(n),
        "name": name,
        "type": "website",
        "target": f"https://{name}.example.com/",
        "category": "web",
        "uptime_status": status,
        "monitor_status": "active",
        "uptime": "99.95",
        "last_status_change": changed,
        **extra,
    }


def listing(key: str, items: list, page: int = 1, last: int = 1) -> dict:
    nxt = page + 1 if page < last else None
    meta = {"returned": len(items), "pagination": {"current": page, "last": last, "next": nxt}}
    return {key: items, "meta": meta}


class Api:
    """Routes by path; a route is a dict, a (status, body) tuple or callable(query)."""

    def __init__(self):
        self.routes: dict = {}
        self.requests: list[tuple[str, dict[str, str], dict[str, str]]] = []
        self.monitors: list[dict] = []

    def respond(self, path: str, query: dict[str, str], headers: dict[str, str]):
        self.requests.append((path, query, headers))
        route = self.routes.get(path)
        if route is None and path == "/v3/uptime-monitors":
            route = self.list_monitors
        if callable(route):
            route = route(query)
        if route is None:
            return 404, json.dumps({"status": "not_found", "message": "not found"})
        if isinstance(route, tuple):
            return route
        return 200, json.dumps(route)

    def list_monitors(self, query: dict[str, str]) -> dict:
        items = self.monitors
        if "uptime_status" in query:
            items = [m for m in items if m["uptime_status"] == query["uptime_status"]]
        if "id" in query:
            items = [m for m in items if m["id"] == query["id"]]
        return listing("monitors", items)

    def paths(self) -> list[str]:
        return [path for path, _q, _h in self.requests]


@pytest.fixture
def api(monkeypatch):
    state = Api()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            url = urllib.parse.urlsplit(self.path)
            query = dict(urllib.parse.parse_qsl(url.query))
            status, body = state.respond(url.path, query, dict(self.headers))
            if body == "<slow>":
                time.sleep(2)
                body = "{}"
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "/v3/redirected")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True)
    thread.start()
    monkeypatch.setattr(hetrix, "API_BASE", f"http://127.0.0.1:{server.server_address[1]}/v3")
    yield state
    server.shutdown()
    server.server_close()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project with .cca.toml and a sops file, fake sops, UTC, fixed time, hostile env."""
    (tmp_path / ".cca.toml").write_text("schema_version = 1\n")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "curl.secret.yaml").write_text("credentials: ENC[...]\n")
    (tmp_path / "plain.json").write_text(json.dumps(CREDENTIALS))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    sops = bindir / "sops"
    sops.write_text(f"#!/bin/sh\nexec /bin/cat {tmp_path / 'plain.json'}\n")
    sops.chmod(sops.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bindir))
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # would fail every request if used
    monkeypatch.setenv("HETRIX_API_KEY", "env-key-sentinel")
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    monkeypatch.setattr(hetrix, "now", lambda: NOW)
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    monkeypatch.delenv("TZ")
    time.tzset()


def credentials(project: Path, creds: dict) -> None:
    (project / "plain.json").write_text(json.dumps({"credentials": creds}))


def cca(capsys, *argv: str) -> tuple[int, str, str]:
    try:
        code = main(["hetrix", *argv])
    except SystemExit as e:  # argparse errors
        code = e.code
    out, err = capsys.readouterr()
    for secret in (TOKEN, "env-key-sentinel"):
        assert secret not in out and secret not in err
    return code, out, err


# --- credential and transport


def test_status_all_up_sends_the_bearer_token(project, api, capsys):
    api.monitors = [monitor(1, "web")]
    code, out, _ = cca(capsys, "status")
    assert (code, out) == (0, "All monitors are UP\n")
    path, query, headers = api.requests[0]
    assert path == "/v3/uptime-monitors"
    assert query["uptime_status"] == "down" and query["per_page"] == "200"
    assert headers["Authorization"] == f"Bearer {TOKEN}"


def test_status_down_exits_1_and_names_monitors(project, api, capsys):
    api.monitors = [monitor(1, "web"), monitor(2, "api", "down"), monitor(3, "db", "down")]
    api.monitors[2]["monitor_status"] = "maint"
    code, out, _ = cca(capsys, "status")
    assert code == 1
    assert out == "2 monitor(s) DOWN:\n  api [website]\n  db [website] (maint)\n"


def test_lists_follow_pagination(project, api, capsys):
    pages = {"1": [monitor(1, "a")], "2": [monitor(2, "b", "down")]}
    api.routes["/v3/uptime-monitors"] = lambda q: listing(
        "monitors", pages[q["page"]], int(q["page"]), 2
    )
    code, out, _ = cca(capsys, "status")
    assert code == 1 and "  b [website]" in out
    assert [q["page"] for _p, q, _h in api.requests] == ["1", "2"]


def test_api_error_exits_2_with_message_and_hint(project, api, capsys):
    api.routes["/v3/uptime-monitors"] = (403, json.dumps({"message": "api key not allowed"}))
    code, out, err = cca(capsys, "status")
    assert code == 2 and out == ""
    assert "HTTP 403: api key not allowed" in err and "API key settings" in err


def test_rate_limit_is_not_retried(project, api, capsys):
    api.routes["/v3/uptime-monitors"] = (429, json.dumps({"message": "rate limit exceeded"}))
    code, _, err = cca(capsys, "down")
    assert code == 2 and "HTTP 429" in err
    assert len(api.requests) == 1


def test_redirect_is_not_followed(project, api, capsys):
    api.routes["/v3/uptime-monitors"] = (302, "")
    api.routes["/v3/redirected"] = listing("monitors", [])
    code, _, err = cca(capsys, "status")
    assert code == 2 and "HTTP 302" in err
    assert api.paths() == ["/v3/uptime-monitors"]


def test_timeout_exits_2(project, api, capsys, monkeypatch):
    monkeypatch.setattr(hetrix, "TIMEOUT", 0.3)
    monkeypatch.setattr(hetrix, "SLACK", 0.2)
    api.routes["/v3/uptime-monitors"] = (200, "<slow>")
    code, _, err = cca(capsys, "status")
    assert code == 2 and "timed out" in err


def test_oversized_and_invalid_responses_exit_2(project, api, capsys, monkeypatch):
    api.routes["/v3/uptime-monitors"] = (200, "not json")
    assert cca(capsys, "status")[0] == 2
    monkeypatch.setattr(hetrix, "MAX_BODY", 10)
    api.routes["/v3/uptime-monitors"] = listing("monitors", [])
    code, _, err = cca(capsys, "status")
    assert code == 2 and "larger than 10 bytes" in err


def test_missing_sops_exits_2_without_api_call(project, api, capsys):
    (project / "bin" / "sops").unlink()
    code, out, err = cca(capsys, "status")
    assert code == 2 and out == "" and "sops not found" in err
    assert api.requests == []


def test_credential_must_be_unique_and_bearer(project, api, capsys):
    credentials(project, {"x": {"origins": ["https://api.example.com"], "bearer": "t"}})
    code, _, err = cca(capsys, "status")
    assert code == 2 and "no credential" in err
    origin = ["https://api.hetrixtools.com"]
    two = {"a": {"origins": origin, "bearer": "t"}, "b": {"origins": origin, "bearer": "u"}}
    credentials(project, two)
    code, _, err = cca(capsys, "status")
    assert code == 2 and "several credentials" in err
    credentials(project, {"a": {"origins": origin, "username": "u", "password": "p"}})
    code, _, err = cca(capsys, "status")
    assert code == 2 and "must be a bearer token" in err
    assert api.requests == []


def test_no_config_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, _, err = cca(capsys, "status")
    assert code == 2 and ".cca.toml" in err


def test_without_command_prints_help_and_exits_2(project, capsys):
    code, _, err = cca(capsys)
    assert code == 2 and "monitor-outages" in err


def test_api_strings_are_escaped(project, api, capsys):
    api.monitors = [monitor(1, "evil\x1b[2Jname", "down")]
    code, out, _ = cca(capsys, "down")
    assert code == 0 and "\x1b" not in out and "evil\\x1b[2Jname" in out


# --- monitor listings


def test_down_and_all(project, api, capsys):
    api.monitors = [monitor(1, "web", changed=NOW - 90 * 60), monitor(2, "api", "down")]
    code, out, _ = cca(capsys, "down")
    assert code == 0
    assert out == (
        "DOWN monitors:\n"
        "  api [website]: DOWN since 2026-01-01 10:00 UTC - https://api.example.com/\n"
    )
    api.monitors = [monitor(1, "web")]
    assert cca(capsys, "down")[1] == "DOWN monitors:\n  (none)\n"
    api.monitors = [monitor(1, "web", changed=NOW - 90 * 60), monitor(2, "api", "down")]
    code, out, _ = cca(capsys, "all")
    assert code == 0
    assert out == (
        "UP monitors:\n"
        "  web [website]: UP for 1h 30m (99.95% uptime)\n"
        "\n"
        "DOWN monitors:\n"
        "  api [website]: DOWN since 2026-01-01 10:00 UTC\n"
    )


def test_response_times_marks_slow_locations(project, api, capsys):
    locations = {"london": {"response_time": 120}, "tokyo": {"response_time": 3500},
                 "sydney": {"response_time": 6000}}  # fmt: skip
    api.monitors = [monitor(1, "web", locations=locations), monitor(2, "nolocations")]
    code, out, _ = cca(capsys, "response-times")
    assert code == 0
    assert out == (
        "Response times of UP monitors:\n"
        "  web [website] (99.95% uptime):\n"
        "    london: 120 ms\n"
        "    sydney: 6000 ms very slow\n"
        "    tokyo: 3500 ms slow\n"
    )
    assert api.requests[0][1]["uptime_status"] == "up"
    api.monitors = [monitor(2, "nolocations")]
    assert cca(capsys, "response-times")[1] == "Response times of UP monitors:\n  (none)\n"


def test_outages_window(project, api, capsys):
    api.monitors = [
        monitor(1, "recent", "down", changed=NOW - HOUR),
        monitor(2, "older", changed=NOW - 5 * HOUR),
        monitor(3, "outside", changed=NOW - 30 * HOUR),
    ]
    code, out, _ = cca(capsys, "outages")
    assert code == 0
    assert "recent [website]: changed 2026-01-01 11:00 UTC (1h 0m ago), now DOWN" in out
    assert out.index("recent") < out.index("older") and "outside" not in out
    code, out, _ = cca(capsys, "outages", "--since", "12h", "--until", "2h")
    assert "Status changes since 12h until 2h:" in out
    assert "older" in out and "recent" not in out
    code, out, _ = cca(capsys, "outages", "--since", "2025-12-31")
    assert "outside" in out


def test_invalid_times_exit_2(project, api, capsys):
    code, _, err = cca(capsys, "outages", "--since", "yesterday")
    assert code == 2 and "invalid time" in err
    code, _, err = cca(capsys, "outages", "--since", "1h", "--until", "2h")
    assert code == 2 and "--since must be before --until" in err


# --- one monitor


def test_monitor_info_by_name_and_id(project, api, capsys):
    api.monitors = [monitor(1, "Search Web"), monitor(2, "api")]
    code, out, _ = cca(capsys, "monitor-info", "search")
    assert code == 0 and "Name:     Search Web" in out and f"ID:       {mid(1)}" in out
    api.requests.clear()
    code, out, _ = cca(capsys, "monitor-info", mid(2))
    assert code == 0 and "Name:     api" in out
    assert api.requests[0][1]["id"] == mid(2)


def test_monitor_lookup_failures_exit_1(project, api, capsys):
    api.monitors = [monitor(1, "web-a"), monitor(2, "web-b"), monitor(3, "web")]
    code, out, err = cca(capsys, "monitor-info", "nothing")
    assert code == 1 and out == "" and "no monitor name contains 'nothing'" in err
    code, _, err = cca(capsys, "monitor-info", "web-")
    assert code == 1 and "several monitors match 'web-': web-a, web-b" in err
    assert cca(capsys, "monitor-info", "WEB")[0] == 0  # exact name wins over substrings
    code, _, err = cca(capsys, "monitor-info", mid(9))
    assert code == 1 and "no monitor with id" in err


def fail_entry(ts: int, location: str, data: str) -> dict:
    return {"timestamp": ts, "location": location, "data": data}


def test_monitor_outages_groups_windows_and_pages_backwards(project, api, capsys):
    api.monitors = [monitor(1, "web")]
    start = NOW - 3 * HOUR
    pages = {
        str(NOW): {
            "entries": [
                fail_entry(start + 60, "tokyo", "Timeout after 30000 milliseconds of waiting"),
                fail_entry(start + 60, "tokyo", "Timeout after 30000 milliseconds of waiting"),
                fail_entry(start, "london", "Connection refused (12ms)"),
            ],
            "meta": {"next_page_timestamp": start - HOUR},
        },
        str(start - HOUR): {
            "entries": [fail_entry(start - 2 * HOUR, "london", "Connection refused (40ms)")],
            "meta": {"next_page_timestamp": None},
        },
    }
    path = f"/v3/uptime-monitors/{mid(1)}/location-fail-log"
    api.routes[path] = lambda q: pages[q["timestamp"]]
    code, out, _ = cca(capsys, "monitor-outages", "web", "--since", "1d")
    assert code == 0
    assert out == (
        f"Outage history: web [website] ({mid(1)})\n"
        "Period: since 1d\n"
        "\n"
        "Failures (3 entries in 2 outage windows):\n"
        "  2026-01-01 07:00 UTC | 1 entry | 1x Connection refused\n"
        "      1 location: london\n"
        "  2026-01-01 09:00-09:01 UTC | 2 entries | 1x Connection refused, 1x Timeout\n"
        "      2 locations: london, tokyo\n"
        "\n"
        "Summary:\n"
        "  Failure times: 3\n"
        "  Locations: 2\n"
        "  First and last failure: 2026-01-01 07:00 UTC -> 2026-01-01 09:01 UTC\n"
    )
    fail_queries = [q for p, q, _h in api.requests if p == path]
    assert [q["timestamp"] for q in fail_queries] == [str(NOW), str(start - HOUR)]
    assert all(q["minutes"] == "100" for q in fail_queries)

    code, out, _ = cca(capsys, "monitor-outages", "web", "--since", "4h", "--full")
    assert "Failures (2 entries):" in out
    assert "  2026-01-01 09:00 UTC [london]: Connection refused (12ms)\n" in out
    assert "07:00" not in out


def test_monitor_outages_stops_before_since_and_at_page_limit(project, api, capsys, monkeypatch):
    api.monitors = [monitor(1, "web")]
    path = f"/v3/uptime-monitors/{mid(1)}/location-fail-log"
    api.routes[path] = lambda q: {
        "entries": [fail_entry(int(q["timestamp"]) - 60, "london", "Timeout")],
        "meta": {"next_page_timestamp": int(q["timestamp"]) - HOUR},
    }
    code, out, _ = cca(capsys, "monitor-outages", "web", "--since", "150m")
    assert code == 0 and "Warning" not in out
    assert len([p for p in api.paths() if p == path]) == 3  # NOW, -1h, -2h; -3h < since
    monkeypatch.setattr(hetrix, "FAIL_LOG_PAGES", 2)
    code, out, _ = cca(capsys, "monitor-outages", "web", "--since", "1d")
    assert "Warning: stopped after 2 pages, older failures are missing" in out
    api.routes[path] = {"entries": [], "meta": {"next_page_timestamp": None}}
    code, out, _ = cca(capsys, "monitor-outages", "web")
    assert code == 0 and "No failures in this period" in out


def test_server_stats(project, api, capsys):
    api.monitors = [monitor(1, "web")]
    api.routes[f"/v3/uptime-monitors/{mid(1)}/server-agent/metrics"] = {
        "agent": {"version": "2.3.0", "type": "linux"},
        "system": {"hostname": "server1", "operating_system": "Debian 13", "kernel": "6.12",
                   "uptime": 10 * 86400 + 5, "reboot_required": False},  # fmt: skip
        "stats": [{"cpu": 12.5, "ram": 40, "load_1": 0.5, "load_5": 0.25, "load_15": 0.1}],
        "disk": {"disks": [
            {"mount": "/", "size": 50 * 2**30, "used": 46 * 2**30, "available": 4 * 2**30,
             "usage_percent": 92.0, "raid": {"type": "raid1", "health": "healthy",
                                             "state": "clean", "active_drives": 2,
                                             "total_drives": 2, "failed_drives": 0}},
            {"mount": "/srv", "size": 100 * 2**30, "used": 10 * 2**30, "available": 90 * 2**30},
        ]},
        "meta": {"last_updated": NOW - 60},
    }  # fmt: skip
    code, out, _ = cca(capsys, "server-stats", "web")
    assert code == 0
    assert out == (
        "Server stats: web\n"
        "  Host:    server1, Debian 13, kernel 6.12\n"
        "  Reboot required: no\n"
        "  Uptime:  10 days\n"
        "  Agent:   2.3.0 [linux], last data 2026-01-01 11:59 UTC\n"
        "  Now:     CPU 12.5%, RAM 40%, load 0.5/0.25/0.1\n"
        "  Disks:\n"
        "    /                         92.0% used (4.0G free of 50.0G) CRITICAL\n"
        "    /srv                      10.0% used (90.0G free of 100.0G)\n"
        "  RAID /: raid1 healthy clean (2/2 active, 0 failed)\n"
    )


def test_server_stats_api_error_exits_2(project, api, capsys):
    api.monitors = [monitor(1, "web")]
    code, _, err = cca(capsys, "server-stats", "web")
    assert code == 2 and "server-agent/metrics: HTTP 404: not found" in err


# --- blacklists


def blacklisted(n: int, name: str, target: str, *rbls: str) -> dict:
    listed = [{"rbl": r, "delist": f"https://{r}/delist"} for r in rbls]
    return {"id": mid(n), "name": name, "target": target, "listed": listed}


def test_blacklist_overview_exit_codes(project, api, capsys):
    path = "/v3/blacklist-monitors"
    api.routes[path] = listing("monitors", [])
    code, out, _ = cca(capsys, "blacklist")
    assert (code, out) == (0, "Blacklist status:\n  No monitored target is listed\n")
    assert api.requests[0][1]["listed"] == "true"

    api.routes[path] = listing("monitors", [
        blacklisted(1, "server1", "203.0.113.10", "dnsbl-3.uceprotect.net"),
        blacklisted(2, "server2", "203.0.113.11", "dnsbl-2.uceprotect.net"),
    ])  # fmt: skip
    code, out, _ = cca(capsys, "blacklist")
    assert code == 0
    assert "  server1 (203.0.113.10): 1 blacklist: dnsbl-3.uceprotect.net (warning)\n" in out

    for rbl in ("dnsbl-1.uceprotect.net", "zen.spamhaus.org"):
        api.routes[path] = listing("monitors", [
            blacklisted(1, "server1", "203.0.113.10", "dnsbl-3.uceprotect.net", rbl)
        ])  # fmt: skip
        code, out, _ = cca(capsys, "blacklist")
        assert code == 1
        assert f"2 blacklists: dnsbl-3.uceprotect.net (warning), {rbl}" in out


def test_blacklist_target(project, api, capsys):
    path = "/v3/blacklist-monitors"
    api.routes[path] = listing("monitors", [
        blacklisted(1, "server1", "203.0.113.10", "dnsbl-3.uceprotect.net")
    ])  # fmt: skip
    code, out, _ = cca(capsys, "blacklist", "203.0.113.10")
    assert code == 0
    assert out == (
        "server1 (203.0.113.10) is on 1 blacklist:\n"
        "  dnsbl-3.uceprotect.net (warning only)\n"
        "      delist: https://dnsbl-3.uceprotect.net/delist\n"
    )
    query = api.requests[0][1]
    assert (query["target"], query["exact_target"]) == ("203.0.113.10", "true")

    api.routes[path] = listing("monitors", [blacklisted(1, "server1", "203.0.113.10", "b.example")])
    assert cca(capsys, "blacklist", "203.0.113.10")[0] == 1
    api.routes[path] = listing("monitors", [blacklisted(1, "server1", "203.0.113.10")])
    code, out, _ = cca(capsys, "blacklist", "203.0.113.10")
    assert (code, out) == (0, "server1 (203.0.113.10) is not on any blacklist\n")
    api.routes[path] = listing("monitors", [])
    code, _, err = cca(capsys, "blacklist", "203.0.113.99")
    assert code == 1 and "no blacklist monitor for 203.0.113.99" in err
    api.requests.clear()
    code, _, err = cca(capsys, "blacklist", "203.0.113.10&listed=false")
    assert code == 2 and "invalid target" in err and api.requests == []
