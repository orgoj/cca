"""cca netdata: compatibility matrix of doc-4, one test per row.

Direct transport talks to a local HTTP server; the ssh transport uses a fake `ssh` on a
PATH that holds only fake tools.
"""

import json
import stat
import threading
import time
import urllib.parse
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cca.cli import main
from cca.commands import netdata

T0 = 1767225600  # 2026-01-01 00:00:00 UTC
TRICKLE_HEADERS, TRICKLE_BODY = "<trickle headers>", "<trickle body>"  # Api route bodies
CHARTS = {
    "charts": {
        "system.cpu": {
            "context": "system.cpu",
            "title": "Total CPU utilization",
            "units": "percentage",
            "family": "cpu",
            "chart_type": "stacked",
            "dimensions": {"user": {"name": "user"}, "system": {"name": "system"}},
        },
        "system.load": {"context": "system.load", "title": "System Load Average", "units": "load"},
        "nginx_local.connections": {"context": "nginx.connections", "title": "Active Connections"},
    }
}


class Api:
    """Routes by `scope_contexts` (v3/data) or by path; records every request."""

    def __init__(self):
        self.routes: dict = {}
        self.requests: list[tuple[str, dict[str, str]]] = []

    def respond(self, path: str, query: dict[str, str]) -> tuple[int, str]:
        self.requests.append((path, query))
        route = self.routes.get(query.get("scope_contexts", path))
        if callable(route):
            route = route(query)
        if route is None:
            return 404, "not found"
        if isinstance(route, tuple):
            return route
        return 200, json.dumps(route)

    def data(self, scope: str | None = None) -> list[dict[str, str]]:
        return [q for p, q in self.requests if scope is None or q.get("scope_contexts") == scope]


@pytest.fixture
def api():
    state = Api()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            url = urllib.parse.urlsplit(self.path)
            status, body = state.respond(url.path, dict(urllib.parse.parse_qsl(url.query)))
            if body in (TRICKLE_HEADERS, TRICKLE_BODY):  # one byte faster than any timeout
                self.wfile.write(b"HTTP/1.0 200 OK\r\n")
                if body == TRICKLE_BODY:
                    self.wfile.write(b"\r\n")
                for _ in range(200):
                    try:
                        self.wfile.write(b"x")
                        self.wfile.flush()
                    except OSError:
                        return
                    time.sleep(0.02)
                return
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True)
    thread.start()
    state.port = server.server_address[1]
    yield state
    server.shutdown()
    server.server_close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """CWD without .cca.toml and a PATH holding only the fake tools."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    return tmp_path


def fake_ssh(
    env: Path, output: str = "{}", code: int = 0, stderr: str = "", run: str | None = None
) -> None:
    """Fake ssh: logs its argv (tab separated), prints `output` (or runs the shell code
    `run`), exits `code`."""
    (env / "ssh-out").write_text(output)
    script = env / "bin" / "ssh"
    script.write_text(
        "#!/bin/sh\n"
        'line=ssh\nfor a; do line="$line\t$a"; done\n'
        f'printf "%s\\n" "$line" >> "{env}/log"\n' + (run or f'/bin/cat "{env}/ssh-out"') + "\n"
        f"printf '%s' '{stderr}' >&2\n"
        f"exit {code}\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def calls(env: Path) -> list[list[str]]:
    log = env / "log"
    return [line.split("\t") for line in log.read_text().splitlines()] if log.exists() else []


def project(env: Path, text: str) -> Path:
    path = env / "work" / ".cca.toml"
    path.write_text("schema_version = 1\n" + text)
    return path


def direct_server(name: str, port: int, extra: str = "") -> str:
    return (
        f'[servers.{name}]\nnetdata_host = "127.0.0.1"\nnetdata_port = {port}\n'
        f'netdata_transport = "direct"\n{extra}'
    )


def usage_error(argv: list[str], capsys) -> str:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    return capsys.readouterr().err


def latency(rows: list[tuple]) -> dict:
    return {"result": {"labels": ["time", "minimum", "average", "maximum"], "data": rows}}


def quality(targets: list[str], rows: list[tuple]) -> dict:
    return {"result": {"labels": ["time", *targets], "data": rows}}


# --- invocation, connection and config


def test_no_command_prints_help_exit_2(env, capsys):
    """Intentional change: legacy exit 1."""
    assert main(["netdata"]) == 2
    assert "usage: cca netdata" in capsys.readouterr().err


def test_no_connection_is_direct_localhost_19999(env, api, monkeypatch):
    monkeypatch.setattr(netdata, "DEFAULT_PORT", api.port)
    api.routes["/api/v1/charts"] = CHARTS
    assert main(["netdata", "list"]) == 0
    assert api.requests[0][0] == "/api/v1/charts"


def test_port_alone_is_localhost(env, api):
    api.routes["/api/v1/charts"] = CHARTS
    assert main(["netdata", "--port", str(api.port), "list"]) == 0
    assert len(api.requests) == 1


def test_host_and_port_direct(env, api, capsys):
    api.routes["/api/v1/charts"] = CHARTS
    assert main(["netdata", "--host", "127.0.0.1", "--port", str(api.port), "list"]) == 0
    out = capsys.readouterr()
    assert "Total: 3 charts" in out.out
    assert "Using server" not in out.err  # only with --server


def test_ipv6_host_is_bracketed_in_url():
    nd = netdata.Netdata("2001:db8::1", 19999)
    assert nd.url("v1", "/charts") == "http://[2001:db8::1]:19999/api/v1/charts"


def test_invalid_host_or_port_usage_error(env, capsys):
    assert "invalid host" in usage_error(["netdata", "--host=-x", "list"], capsys)
    assert "invalid host" in usage_error(["netdata", "--host", "fe80::1%eth0", "list"], capsys)
    assert "1-65535" in usage_error(["netdata", "--port", "0", "list"], capsys)


def test_server_direct_transport(env, api, capsys):
    project(env, direct_server("server1", api.port))
    api.routes["/api/v1/charts"] = CHARTS
    assert main(["netdata", "--server", "server1", "list"]) == 0
    assert f"Using server server1 -> 127.0.0.1:{api.port}" in capsys.readouterr().err


def test_server_default_transport_is_ssh(env, capsys):
    project(
        env, '[servers.server1]\nssh = "admin@server1.example.com"\nnetdata_host = "203.0.113.10"\n'
    )
    fake_ssh(env, json.dumps(CHARTS))
    assert main(["netdata", "--server", "server1", "list"]) == 0
    assert calls(env) == [
        [
            "ssh",
            "--",
            "admin@server1.example.com",
            "curl -fsS --max-time 10 http://203.0.113.10:19999/api/v1/charts",
        ]
    ]
    err = capsys.readouterr().err
    assert "Using server server1 -> ssh admin@server1.example.com -> 203.0.113.10:19999" in err


def test_ssh_remote_command_quotes_the_url(env):
    project(env, '[servers.server1]\nnetdata_host = "2001:db8::1"\nnetdata_port = 8080\n')
    fake_ssh(env, "{}")
    assert main(["netdata", "--server", "server1", "query", "--context", "a b;c"]) == 0
    remote = calls(env)[0][3]
    assert remote.startswith("curl -fsS --max-time 10 'http://[2001:db8::1]:8080/api/v3/data?")
    assert "scope_contexts=a+b%3Bc" in remote and remote.endswith("'")
    assert calls(env)[0][2] == "server1"  # ssh defaults to the server name


def test_transport_option_overrides_config(env, api):
    project(env, '[servers.server1]\nnetdata_host = "127.0.0.1"\n' + f"netdata_port = {api.port}\n")
    api.routes["/api/v1/charts"] = CHARTS
    fake_ssh(env, json.dumps(CHARTS))
    assert main(["netdata", "--server", "server1", "--transport", "direct", "list"]) == 0
    assert calls(env) == [] and len(api.requests) == 1
    project(env, direct_server("server1", api.port))
    assert main(["netdata", "--server", "server1", "--transport", "ssh", "list"]) == 0
    assert len(calls(env)) == 1 and len(api.requests) == 1


def test_connection_options_after_command(env, api, capsys):
    project(env, direct_server("server1", api.port))
    api.routes["/api/v1/charts"] = CHARTS
    assert main(["netdata", "list", "--server", "server1", "--pattern", "cpu"]) == 0
    assert "system.cpu" in capsys.readouterr().out


def test_server_and_host_conflict_across_levels(env, capsys):
    assert main(["netdata", "--server", "server1", "list", "--host", "example.com"]) == 2
    assert "mutually exclusive" in capsys.readouterr().err
    assert main(["netdata", "--port", "1", "list", "--server", "server1"]) == 2


def test_transport_ssh_needs_server(env, capsys):
    assert main(["netdata", "--host", "example.com", "--transport", "ssh", "list"]) == 2
    assert "needs --server" in capsys.readouterr().err


def test_server_needs_config(env, capsys):
    assert main(["netdata", "--server", "server1", "list"]) == 2
    assert "no .cca.toml found" in capsys.readouterr().err


def test_unknown_server(env, capsys):
    project(env, '[servers.server1]\nnetdata_host = "203.0.113.10"\n')
    assert main(["netdata", "--server", "server9", "list"]) == 2
    assert "unknown server 'server9'" in capsys.readouterr().err


def test_server_without_netdata_host(env, capsys):
    project(env, "[servers.server1]\n")
    assert main(["netdata", "--server", "server1", "list"]) == 2
    assert "servers.server1.netdata_host: required" in capsys.readouterr().err


def test_server_netdata_host_zone_id_rejected(env, capsys):
    project(env, '[servers.server1]\nnetdata_host = "fe80::1%eth0"\n')
    assert main(["netdata", "--server", "server1", "list"]) == 2
    assert "zone id" in capsys.readouterr().err


def test_malformed_config_fails_also_for_host(env, capsys):
    """Config is loaded whenever found (fping_target, cache dir)."""
    (env / "work" / ".cca.toml").write_text("schema_version = [\n")
    assert main(["netdata", "--host", "example.com", "list"]) == 2
    assert "syntax error" in capsys.readouterr().err


def test_direct_ignores_proxy_environment(env, api, monkeypatch):
    monkeypatch.setenv("http_proxy", "http://203.0.113.99:9")
    monkeypatch.setenv("HTTP_PROXY", "http://203.0.113.99:9")
    api.routes["/api/v1/charts"] = CHARTS
    assert main(["netdata", "--host", "127.0.0.1", "--port", str(api.port), "list"]) == 0


# --- fetch errors


def test_http_error_exit_1(env, api, capsys):
    assert main(["netdata", "--host", "127.0.0.1", "--port", str(api.port), "list"]) == 1
    assert "cca: error: fetching http://127.0.0.1:" in capsys.readouterr().err


def test_invalid_json_exit_1(env, api, capsys):
    api.routes["/api/v1/charts"] = (200, "not json")
    assert main(["netdata", "--host", "127.0.0.1", "--port", str(api.port), "list"]) == 1
    assert "invalid JSON" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (255, "ssh to server1 failed (exit 255)"),
        (127, "curl not found on server1"),
        (22, "on server1: curl: (22) 404"),
    ],  # fmt: skip
)
def test_ssh_failures_exit_1(env, capsys, code, message):
    project(env, '[servers.server1]\nnetdata_host = "203.0.113.10"\n')
    fake_ssh(env, "", code, "curl: (22) 404" if code == 22 else "")
    assert main(["netdata", "--server", "server1", "list"]) == 1
    assert message in capsys.readouterr().err


def test_ssh_timeout_kills_exit_1(env, capsys, monkeypatch):
    """Total time is curl --max-time + 15 s; shortened here."""
    monkeypatch.setattr(netdata, "TIMEOUT", 1)
    monkeypatch.setattr(netdata, "SLACK", 0)
    project(env, '[servers.server1]\nnetdata_host = "203.0.113.10"\n')
    fake_ssh(env, run="exec /bin/sleep 30")
    started = time.monotonic()
    assert main(["netdata", "--server", "server1", "list"]) == 1
    assert time.monotonic() - started < 5
    assert "ssh to server1 timed out" in capsys.readouterr().err
    assert "--max-time 1 " in calls(env)[0][3]


def test_ssh_missing_locally_exit_2(env, capsys):
    project(env, '[servers.server1]\nnetdata_host = "203.0.113.10"\n')
    assert main(["netdata", "--server", "server1", "list"]) == 2
    assert "ssh not found on PATH" in capsys.readouterr().err


def test_direct_response_size_cap(env, api, capsys, monkeypatch):
    monkeypatch.setattr(netdata, "MAX_BODY", 100)
    api.routes["/api/v1/charts"] = CHARTS
    assert run_direct(api, "list") == 1
    assert "response larger than 100 bytes" in capsys.readouterr().err


@pytest.mark.parametrize("mode", [TRICKLE_HEADERS, TRICKLE_BODY])
def test_direct_total_deadline_slow_response(env, api, capsys, monkeypatch, mode):
    monkeypatch.setattr(netdata, "TIMEOUT", 1)
    monkeypatch.setattr(netdata, "SLACK", 0)
    api.routes["/api/v1/charts"] = (200, mode)
    started = time.monotonic()
    assert run_direct(api, "list") == 1
    assert time.monotonic() - started < 3
    assert "timed out" in capsys.readouterr().err


def test_ssh_endless_output_killed_at_cap(env, capsys, monkeypatch):
    monkeypatch.setattr(netdata, "MAX_BODY", 1000)
    project(env, '[servers.server1]\nnetdata_host = "203.0.113.10"\n')
    fake_ssh(env, run="while :; do printf '%s' xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx; done")
    started = time.monotonic()
    assert main(["netdata", "--server", "server1", "list"]) == 1
    assert time.monotonic() - started < 5
    assert "response larger than 1000 bytes" in capsys.readouterr().err


def test_ssh_long_stderr_keeps_first_part(env, capsys):
    project(env, '[servers.server1]\nnetdata_host = "203.0.113.10"\n')
    fake_ssh(env, "", 22, "curl: (22) FIRST" + "y" * 10000)
    assert main(["netdata", "--server", "server1", "list"]) == 1
    err = capsys.readouterr().err
    assert "curl: (22) FIRST" in err and "y" * 5000 not in err


def test_ssh_response_size_cap(env, capsys, monkeypatch):
    monkeypatch.setattr(netdata, "MAX_BODY", 100)
    project(env, '[servers.server1]\nnetdata_host = "203.0.113.10"\n')
    fake_ssh(env, json.dumps(CHARTS))
    assert main(["netdata", "--server", "server1", "list"]) == 1
    assert "response larger than 100 bytes" in capsys.readouterr().err


def test_api_strings_escaped_for_terminal(env, api, capsys):
    """Chart ids, titles and labels from the API never reach the terminal raw."""
    evil = "x\x1b]52;c;AAAA\x07\r\n"
    api.routes["/api/v1/charts"] = {"charts": {evil: {"context": "c." + evil, "title": evil}}}
    api.routes["c"] = {"result": {"labels": ["time", "req" + evil], "data": [[T0, 5]]}}
    for argv in (["list"], ["list", "--pattern", "x"], ["stats", "--context", "c"],
                 ["top", "--context", "c", "--group-by", "instance"]):  # fmt: skip
        assert run_direct(api, *argv) == 0
        out = capsys.readouterr().out
        assert not any(c in out for c in "\x1b\x07\r"), argv
        assert argv == ["list"] or "x\\x1b]52" in out, argv  # groups: prefix only


def test_query_keeps_raw_json(env, api, capsys):
    api.routes["c"] = {"result": {"labels": ["a\x1bb"]}}
    assert run_direct(api, "query", "--context", "c") == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and json.loads(out) == {"result": {"labels": ["a\x1bb"]}}


def test_ssh_error_detail_escaped(env, capsys):
    project(env, '[servers.server1]\nnetdata_host = "203.0.113.10"\n')
    fake_ssh(env, "", 22, "bad\x1b[2Jthing")
    assert main(["netdata", "--server", "server1", "list"]) == 1
    err = capsys.readouterr().err
    assert "\x1b" not in err and "bad\\x1b[2Jthing" in err


# --- time and value arguments


NOW = datetime(2026, 3, 17, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-300", -300),
        ("today 10:30", int(datetime(2026, 3, 17, 10, 30, tzinfo=UTC).timestamp())),
        ("Today 7", int(datetime(2026, 3, 17, 7, 0, tzinfo=UTC).timestamp())),
        ("yesterday 14:00", int(datetime(2026, 3, 16, 14, 0, tzinfo=UTC).timestamp())),
        ("10:30", int(datetime(2026, 3, 17, 10, 30, tzinfo=UTC).timestamp())),
        ("2026-03-01 10:30:15", int(datetime(2026, 3, 1, 10, 30, 15, tzinfo=UTC).timestamp())),
        ("2026-03-01 10:30", int(datetime(2026, 3, 1, 10, 30, tzinfo=UTC).timestamp())),
        ("2026-03-01", int(datetime(2026, 3, 1, tzinfo=UTC).timestamp())),
    ],
)
def test_time_formats_utc(text, expected):
    assert netdata.parse_time(text, NOW) == expected


@pytest.mark.parametrize("text", ["x", "today 25:00", "-3h", "10:3", "2026-13-01", "yesterday"])
def test_bad_time_usage_error(env, capsys, text):
    """Intentional change: legacy raised a traceback (exit 1)."""
    err = usage_error(["netdata", "query", "--context", "system.cpu", f"--after={text}"], capsys)
    assert "invalid time" in err


@pytest.mark.parametrize("points", ["0", "1001", "x"])
def test_points_range_usage_error(env, capsys, points):
    """Intentional change: legacy `--points > 1000` exit 1."""
    for command in ("stats", "top"):
        usage_error(["netdata", command, "--context", "c", "--points", points], capsys)


@pytest.mark.parametrize("hours", ["x", "24", "1,,2", "-1"])
def test_bad_exclude_hours_usage_error(env, capsys, hours):
    """Intentional change: legacy raised a traceback (exit 1)."""
    assert "invalid hours" in usage_error(["netdata", "fping", "--exclude-hours", hours], capsys)


def test_per_target_and_history_exclusive(env, capsys):
    """Intentional change: legacy let --history win silently."""
    usage_error(["netdata", "fping", "--per-target", "--history"], capsys)


def test_bad_target_usage_error(env, capsys):
    assert "invalid target" in usage_error(["netdata", "fping", "--target", "a/b"], capsys)
    usage_error(["netdata", "fping", "--target", "a" * 65], capsys)


# --- commands


def run_direct(api, *argv: str) -> int:
    return main(["netdata", "--host", "127.0.0.1", "--port", str(api.port), *argv])


def test_list_groups(env, api, capsys):
    api.routes["/api/v1/charts"] = CHARTS
    assert run_direct(api, "list") == 0
    out = capsys.readouterr().out
    assert "  system                  2 charts" in out
    assert "--group" not in out  # legacy hint named a nonexistent option


def test_list_pattern(env, api, capsys):
    api.routes["/api/v1/charts"] = CHARTS
    assert run_direct(api, "list", "--pattern", "NGINX") == 0
    out = capsys.readouterr().out
    assert "nginx_local.connections" in out and "system.cpu" not in out
    assert run_direct(api, "list", "--pattern", "nothing") == 0
    assert "No charts match pattern: nothing" in capsys.readouterr().out


def test_query_raw_json_and_params(env, api, capsys):
    api.routes["system.cpu"] = {"result": {"labels": ["time"]}}
    assert run_direct(api, "query", "--context", "system.cpu", "--before", "-60") == 0
    assert json.loads(capsys.readouterr().out) == {"result": {"labels": ["time"]}}
    assert api.data() == [
        {"scope_contexts": "system.cpu", "after": "-300", "before": "-60", "format": "json"}
    ]


def test_stats_auto_columns(env, api, capsys):
    labels = ["time", "load1", "x" * 10, "cpu_" + "y" * 40]
    api.routes["system.load"] = {"result": {"labels": labels, "data": [[T0, 1.5, 2, 3]]}}
    assert run_direct(api, "stats", "--context", "system.load") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("Time (UTC)       | load1")
    assert "xxxx" not in lines[0]  # no keyword
    assert lines[2] == "2026-01-01 00:00 |     1.50"
    assert api.data()[0] == {
        "scope_contexts": "system.load", "after": "-3600", "time_group": "max",
        "points": "24", "format": "json",
    }  # fmt: skip


def test_stats_dimension_shows_all_and_fallback(env, api, capsys):
    api.routes["c"] = {"result": {"labels": ["time", "busy", "idle"], "data": [[T0, 1, 2]]}}
    assert run_direct(api, "stats", "--context", "c", "--dimension", "busy") == 0
    assert "busy" in capsys.readouterr().out.splitlines()[0]
    assert api.data()[0]["dimensions"] == "busy"
    assert run_direct(api, "stats", "--context", "c", "--instance", "i1") == 0
    header = capsys.readouterr().out.splitlines()[0]
    assert "busy" in header and "idle" not in header  # fallback: first column
    assert api.data()[1]["instances"] == "i1"


def test_stats_no_data(env, api, capsys):
    api.routes["c"] = {"result": {}}
    assert run_direct(api, "stats", "--context", "c") == 0
    assert capsys.readouterr().out == "No data\n"


def test_top_domains_first_and_skip_words(env, api, capsys):
    labels = ["time", "www.example.com", "requests", "free", "a.b"]
    rows = [[T0, 1, 50, 9, 7], [T0 + 60, 2, 50, 9, 7]]
    api.routes["web"] = {"result": {"labels": labels, "data": rows}}
    assert run_direct(api, "top", "--context", "web", "-n", "5") == 0
    out = capsys.readouterr().out
    assert "=== TOP 3 (context: web) ===" in out
    ranked = [line for line in out.splitlines() if line[:4].strip().isdigit()]
    assert ranked[0].startswith("   1 *| www.example.com")  # domain ranked first
    assert "requests" in ranked[1] and "free" not in out
    assert api.data()[0]["group_by"] == "dimension"


def test_top_group_by_instance_keeps_all(env, api, capsys):
    api.routes["app.cpu"] = {"result": {"labels": ["time", "free", "cpu"], "data": [[T0, 1, 2]]}}
    assert run_direct(api, "top", "--context", "app.cpu", "--group-by", "instance") == 0
    out = capsys.readouterr().out
    assert "free" in out and "cpu" in out
    assert api.data()[0]["group_by"] == "instance"


def test_discover(env, api, capsys):
    api.routes["/api/v1/charts"] = CHARTS
    assert run_direct(api, "discover", "load spikes") == 0
    out = capsys.readouterr().out
    assert "system.load\n  Title: System Load Average" in out
    assert "Usage: stats --context system.load --after -3600" in out
    assert run_direct(api, "discover", "zzz") == 0
    assert "No matching metrics found." in capsys.readouterr().out


def test_meta(env, api, capsys):
    api.routes["/api/v1/charts"] = CHARTS
    api.routes["system.cpu"] = {"result": {"labels": ["time", "user", "system"]}}
    assert run_direct(api, "meta", "--context", "system.cpu") == 0
    out = capsys.readouterr().out
    assert "=== Chart: system.cpu ===" in out and "  - user: user" in out
    assert "  [1] user" in out
    assert "stats --context system.cpu --after -3600" in out  # legacy example lacked --context
    assert api.data("system.cpu")[0] == {
        "scope_contexts": "system.cpu", "after": "-300", "instances": "system.cpu",
        "points": "5", "format": "json",
    }  # fmt: skip


# --- fping


def shared_path_api(api) -> None:
    api.routes["fping.latency"] = latency(
        [(T0, 10, 20, 30), (T0 + 60, 10, 20, 40), (T0 + 120, 10, 20, 30), (T0 + 180, 200, 300, 400)]
    )
    api.routes["fping.quality"] = quality(["t1", "t2"], [(T0, 100, 100), (T0 + 60, 100, 100)])


def test_fping_window_shared_path(env, api, capsys):
    shared_path_api(api)
    assert run_direct(api, "fping") == 0
    out = capsys.readouterr().out
    assert "baseline (median min): 10.0 ms" in out
    assert "PEAK max: 400.0 ms @ 00:03:00 UTC" in out
    assert "NETWORK EVENT: the minimum rose too" in out
    assert "buckets over threshold (1):" in out
    assert [q["scope_contexts"] for q in api.data()] == ["fping.latency", "fping.quality"]
    assert api.data()[0]["after"] == "-900"
    assert api.data()[1]["group_by"] == "instance"


def test_fping_window_packet_loss(env, api, capsys):
    api.routes["fping.latency"] = latency([(T0, 10, 20, 30)])
    rows = [(T0, 100, 100), (T0 + 60, 0, 0), (T0 + 120, 50, 100), (T0 + 600, 90, 100)]
    api.routes["fping.quality"] = quality(["t1", "t2"], rows)
    assert run_direct(api, "fping") == 0
    out = capsys.readouterr().out
    assert ">>> PACKET LOSS: worst quality 0 % @ 00:01:00 UTC, window 00:01:00-00:03:00 UTC" in out
    assert "ALL targets" in out and "100% loss for 60 s" in out
    assert "(+ 1 more dips outside this window)" in out
    assert ">>> OK: no significant latency spike" in out


def test_fping_loss_window_joins_dips_one_bucket_apart(env, api, capsys):
    """Legacy kept (user decision): bad-good-bad within 2 x step is one window."""
    api.routes["fping.latency"] = latency([(T0, 10, 20, 30)])
    rows = [(T0, 50, 100), (T0 + 60, 100, 100), (T0 + 120, 0, 0), (T0 + 180, 100, 100)]
    api.routes["fping.quality"] = quality(["t1", "t2"], rows)
    assert run_direct(api, "fping") == 0
    out = capsys.readouterr().out
    assert "window 00:00:00-00:03:00 UTC" in out and "more dips" not in out


def test_fping_no_data(env, api, capsys):
    api.routes["fping.latency"] = latency([])
    api.routes["fping.quality"] = quality([], [])
    assert run_direct(api, "fping") == 0
    assert "No fping data" in capsys.readouterr().out


def test_fping_per_target(env, api, capsys):
    api.routes["fping.latency"] = {
        "result": {"labels": ["time", "a.example.com", "b.example.com"],
                   "data": [[T0, 10, 20], [T0 + 60, 12, 300]]}
    }  # fmt: skip
    assert run_direct(api, "fping", "--per-target") == 0
    out = capsys.readouterr().out
    assert "b.example.com" in out and "<-- bad" in out
    assert ">>> LOCALIZATION: 1 targets bad, 1 OK" in out
    assert api.data() == [
        {"scope_contexts": "fping.latency", "after": "-900", "group_by": "instance",
         "format": "json"}
    ]  # fmt: skip


def history_api(api) -> None:
    rows = [[T0 + 60 * i, 10, 150 if i in (5, 6) else 20] for i in range(10)]
    api.routes["fping.latency"] = {
        "result": {"labels": ["time", "a.example.com", "gw.example.com"], "data": rows}
    }


def test_fping_history_needs_target(env, api, capsys):
    """Intentional change: no consumer-specific default target."""
    assert run_direct(api, "fping", "--history") == 2
    assert "needs --target" in capsys.readouterr().err


def test_fping_history_without_config_caches_in_cwd(env, api, capsys):
    history_api(api)
    assert run_direct(api, "fping", "--history", "--target", "GW") == 0
    out = capsys.readouterr().out
    assert "EVENTS (sustained > threshold, >= 60s): 1" in out
    assert "2026-01-01 00:05 UTC  ~2m (2x60s)  peak    150.0 ms" in out
    assert api.data()[0]["after"] == "-7776000"
    cache = env / "work" / "server-logs" / "fping" / "host-127.0.0.1+gw.json"
    blob = json.loads(cache.read_text())
    assert blob["target"] == "GW" and len(blob["series"]) == 10


def test_fping_history_explicit_after_kept(env, api):
    """Intentional change: legacy turned an explicit `--after -900` into 90 days."""
    history_api(api)
    assert run_direct(api, "fping", "--history", "--target", "gw", "--after", "-900") == 0
    assert api.data()[0]["after"] == "-900"


def test_fping_history_config_target_cache_and_refresh(env, api, capsys, monkeypatch):
    project(env, direct_server("server1", api.port) + '[netdata]\nfping_target = "gw"\n'
            'fping_cache_dir = "cache/fping"\n')  # fmt: skip
    history_api(api)
    (env / "work" / "sub").mkdir()
    monkeypatch.chdir(env / "work" / "sub")  # cache dir resolves from the config dir
    argv = ["netdata", "--server", "server1", "fping", "--history"]
    assert main(argv) == 0
    cache = env / "work" / "cache" / "fping" / "server-server1+gw.json"
    assert cache.exists() and len(api.requests) == 1
    assert main(argv) == 0  # read from the cache
    assert len(api.requests) == 1 and "source: cache" in capsys.readouterr().out
    assert main([*argv, "--refresh"]) == 0
    assert len(api.requests) == 2
    cache.write_text("garbage")  # unreadable cache: fetched again
    assert main(argv) == 0
    assert len(api.requests) == 3


def test_fping_history_cache_option_from_cwd(env, api):
    history_api(api)
    assert run_direct(api, "fping", "--history", "--target", "gw", "--cache", "my.json") == 0
    assert (env / "work" / "my.json").exists()


def test_fping_history_exclude_hours_and_min_seconds(env, api, capsys):
    history_api(api)
    assert run_direct(api, "fping", "--history", "--target", "gw", "--min-seconds", "300") == 0
    assert "EVENTS (sustained > threshold, >= 300s): 0" in capsys.readouterr().out
    assert run_direct(api, "fping", "--history", "--target", "gw", "--exclude-hours", "0") == 0
    assert "Empty series" in capsys.readouterr().out


def test_fping_history_event_spans_sample_gap(env, api, capsys):
    """Legacy kept (user decision): no samples during an outage, the event stays open."""
    rows = [[T0 + 60 * i, 20] for i in range(9)] + [[T0 + 540, 150], [T0 + 4140, 150]]
    rows.append([T0 + 4200, 20])
    api.routes["fping.latency"] = {"result": {"labels": ["time", "gw"], "data": rows}}
    assert run_direct(api, "fping", "--history", "--target", "gw") == 0
    out = capsys.readouterr().out
    assert "EVENTS (sustained > threshold, >= 60s): 1" in out
    assert "2026-01-01 00:09 UTC  ~61m (2x60s)" in out


def test_fping_history_no_matching_target(env, api, capsys):
    history_api(api)
    assert run_direct(api, "fping", "--history", "--target", "zz") == 0
    assert "No target matches --target 'zz'" in capsys.readouterr().out


def test_fping_cache_symlink_outside_dir_rejected(env, api, capsys):
    project(env, direct_server("server1", api.port) + '[netdata]\nfping_target = "gw"\n')
    directory = env / "work" / "server-logs" / "fping"
    directory.mkdir(parents=True)
    (directory / "server-server1+gw.json").symlink_to(env / "elsewhere.json")
    assert main(["netdata", "--server", "server1", "fping", "--history"]) == 2
    assert "resolves outside" in capsys.readouterr().err


# --- fping --all


def test_fping_all_mixed_transports_config_order(env, api, capsys):
    """Each server uses its own transport; an ssh failure does not stop the scan."""
    shared_path_api(api)
    project(
        env,
        direct_server("server1", api.port)
        + "[servers.server2]\n"
        + '[servers.server3]\nssh = "admin@server3.example.com"\nnetdata_host = "203.0.113.30"\n'
        + direct_server("server4", api.port),
    )
    fake_ssh(env, "", 255)
    assert main(["netdata", "fping", "--all"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "=== fping scan of 4 servers | window | threshold 100ms ==="
    assert lines[1].startswith("  server1    baseline")
    assert lines[1].endswith("[NET!]")
    assert lines[2] == "  server2    -- not configured (no netdata_host)"
    assert lines[3] == "  server3    -- unreachable / no fping"
    assert lines[4].startswith("  server4    baseline")
    assert calls(env)[0][:3] == ["ssh", "--", "admin@server3.example.com"]
    assert "--max-time 12" in calls(env)[0][3]
    assert "CORRELATED NETWORK EVENT: 2 servers (server1, server4)" in lines[-1]


def test_fping_all_single_shared_path_is_not_correlated(env, api, capsys):
    """Intentional change: legacy called one server a correlated event."""
    shared_path_api(api)
    project(env, direct_server("server1", api.port))
    assert main(["netdata", "fping", "--all"]) == 0
    out = capsys.readouterr().out
    assert "CORRELATED" not in out
    assert "NETWORK EVENT on server1 only: its own path, or an asymmetric" in out


def test_fping_all_loss_details_and_tags(env, api, capsys):
    api.routes["fping.latency"] = latency([(T0, 10, 20, 30)])
    api.routes["fping.quality"] = quality(["t1"], [(T0, 100), (T0 + 60, 0)])
    project(env, direct_server("server1", api.port))
    assert main(["netdata", "fping", "--all"]) == 0
    out = capsys.readouterr().out
    assert "[OUTAGE!]" in out and ">>> server1: PACKET LOSS" in out


def test_fping_all_history_per_server_cache(env, api, capsys):
    history_api(api)
    project(env, direct_server("server1", api.port) + direct_server("server2", api.port))
    assert main(["netdata", "fping", "--all", "--history", "--target", "gw"]) == 0
    out = capsys.readouterr().out
    assert "| history |" in out and "  server1    events   1 in   0d" in out
    directory = env / "work" / "server-logs" / "fping"
    assert sorted(p.name for p in directory.iterdir()) == [
        "server-server1+gw.json", "server-server2+gw.json",
    ]  # fmt: skip


@pytest.mark.parametrize(
    "extra",
    [
        ["--server", "server1"],
        ["--host", "example.com"],
        ["--port", "1"],
        ["--transport", "direct"],
        ["--cache", "x.json"],
        ["--per-target"],
    ],  # fmt: skip
)
def test_fping_all_rejects_connection_cache_per_target(env, capsys, extra):
    """Intentional change: legacy ignored them."""
    project(env, "[servers.server1]\n")
    assert main(["netdata", "fping", "--all", *extra]) == 2
    assert "fping --all takes no" in capsys.readouterr().err
    if extra[0] not in ("--cache", "--per-target"):  # connection options also before COMMAND
        assert main(["netdata", *extra, "fping", "--all"]) == 2
        assert "fping --all takes no" in capsys.readouterr().err


def test_fping_all_needs_config(env, capsys):
    assert main(["netdata", "fping", "--all"]) == 2
    assert "no .cca.toml found" in capsys.readouterr().err


# --- cache file names (doc-2 "Generated file names", required tests)


def test_cache_name_server_vs_host():
    assert netdata.cache_name("server1", "203.0.113.10", "gw") == "server-server1+gw.json"
    assert netdata.cache_name(None, "server1", "gw") == "host-server1+gw.json"


def test_cache_name_ipv6_and_long_host_hashed():
    assert netdata.cache_name(None, "2001:db8::1", "gw").startswith("hostid-")
    long_host = ".".join(["a" * 63] * 3 + ["b" * 61])
    assert len(long_host) == 253
    name = netdata.cache_name(None, long_host, "gw")
    assert name.startswith("hostid-") and len(name) == len("hostid-") + 32 + len("+gw.json")


def test_cache_name_max_parts_fit():
    assert len(netdata.cache_name("s" * 64, "x", "t" * 64)) <= 200


def test_cache_name_separator_cannot_alias():
    assert netdata.cache_name("a-b", "x", "c") != netdata.cache_name("a", "x", "b-c")


def test_cache_name_target_case_is_one_key():
    assert netdata.cache_name("server1", "x", "CPU") == netdata.cache_name("server1", "x", "cpu")
    assert netdata.cache_name("Server1", "x", "cpu") == "server-server1+cpu.json"


def test_cache_name_underscore_in_server_name():
    assert netdata.cache_name("web_1", "x", "gw") == "server-web_1+gw.json"
