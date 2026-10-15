"""cca open-ports: compatibility matrix of doc-3, one test per row, fake tools on PATH."""

import stat
from pathlib import Path

import pytest

from cca.cli import main

K8S = "2379,2380,5473,6443,8472,9345,10250,10257,10259"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """CWD without .cca.toml and a PATH holding only the fake tools."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    return tmp_path


def fake(env: Path, name: str, exits: dict[str, int] | None = None) -> None:
    """Fake tool: logs `name argv...` (one argument per field, tab separated), exits by
    a shell `case` pattern on its last argument."""
    cases = "".join(f"  {pattern}) exit {code};;\n" for pattern, code in (exits or {}).items())
    script = env / "bin" / name
    script.write_text(
        "#!/bin/sh\n"
        f"line={name}\n"
        'for a; do line="$line\t$a"; last=$a; done\n'
        f'printf "%s\\n" "$line" >> "{env}/log"\n'
        f'case "$last" in\n{cases}esac\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def calls(env: Path) -> list[list[str]]:
    log = env / "log"
    return [line.split("\t") for line in log.read_text().splitlines()] if log.exists() else []


def project(env: Path) -> None:
    (env / "work" / ".cca.toml").write_text(
        'schema_version = 1\n[servers.server1]\nssh = "admin@server1.example.com"\n'
        "[servers.server2]\n"
    )


def usage_error(argv: list[str], capsys) -> str:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    return capsys.readouterr().err


# --- options, defaults, port list


def test_default_method_nmap_default_ports(env):
    fake(env, "nmap")
    assert main(["open-ports", "example.com"]) == 0
    assert calls(env) == [["nmap", "-Pn", "--reason", "-p", "20,22,25,80,443", "example.com"]]


def test_kubernetes_adds_ports(env):
    fake(env, "nmap")
    assert main(["open-ports", "-k", "example.com"]) == 0
    assert calls(env)[0][4] == "20,22,25,80,443," + K8S


def test_positional_ports_replace_default_and_kubernetes(env):
    fake(env, "nmap")
    assert main(["open-ports", "--kubernetes", "example.com", "8080", "22", "8080"]) == 0
    assert calls(env)[0][4] == "8080,22,8080"  # legacy: order and duplicates kept


def test_options_after_host_accepted(env):
    """Intentional change: legacy treated options after HOST as ports."""
    fake(env, "nc")
    assert main(["open-ports", "example.com", "22", "--method", "nc"]) == 0
    assert calls(env) == [["nc", "-zv", "-w", "5", "example.com", "22"]]


def test_option_between_ports_is_usage_error(env, capsys):
    assert "unrecognized arguments: 80" in usage_error(
        ["open-ports", "example.com", "22", "-m", "nc", "80"], capsys
    )


def test_help_exits_zero(env, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["open-ports", "--help"])
    assert exc.value.code == 0
    assert "--delegate SERVER" in capsys.readouterr().out


def test_missing_host(env, capsys):
    assert "required: HOST" in usage_error(["open-ports"], capsys)


@pytest.mark.parametrize("option", ["--bogus", "-x", "--xdebug"])
def test_unknown_option_and_dropped_xdebug(env, capsys, option):
    assert "unrecognized arguments" in usage_error(["open-ports", option, "example.com"], capsys)


@pytest.mark.parametrize("method", ["telnet", "", "NMAP"])
def test_unknown_method_rejected(env, capsys, method):
    """Intentional change: legacy ran nothing and exited 0; telnet dropped."""
    assert "invalid choice" in usage_error(["open-ports", "-m", method, "example.com"], capsys)


def test_option_without_value(env, capsys):
    assert "expected one argument" in usage_error(["open-ports", "example.com", "-m"], capsys)


@pytest.mark.parametrize("port", ["0", "65536", "http", "-1", "２２", "22;id", "22 80", "+22"])
def test_invalid_port(env, capsys, port):
    """Intentional change: ports are validated as 1-65535."""
    err = usage_error(["open-ports", "example.com", "--", port], capsys)
    assert "invalid port" in err


@pytest.mark.parametrize(
    "host",
    [
        "a b",
        "-x.example.com",
        "ex_ample.com",
        "[2001:db8::1]",
        "",
        "example.com;id",
        "$(id).example.com",
        "example.com'",
        "fe80::1%eth0",
    ],
)
def test_invalid_host(env, capsys, host):
    err = usage_error(["open-ports", "--", host], capsys)
    assert "invalid host" in err


# --- probe commands


def test_nmap_ipv6_target(env):
    fake(env, "nmap")
    assert main(["open-ports", "2001:DB8:0::1", "22"]) == 0
    assert calls(env) == [["nmap", "-6", "-Pn", "--reason", "-p", "22", "2001:db8::1"]]


def test_nmap_exit_code_passes_through(env):
    fake(env, "nmap", {"*": 3})
    assert main(["open-ports", "203.0.113.10"]) == 3


def test_nc_probes_every_port_exit_1_on_failure(env):
    """Intentional change: legacy ignored nc failures (exit 0)."""
    fake(env, "nc", {"25": 1})
    assert main(["open-ports", "-m", "nc", "203.0.113.10", "22", "25", "80"]) == 1
    assert [c[-1] for c in calls(env)] == ["22", "25", "80"]
    assert calls(env)[0] == ["nc", "-zv", "-w", "5", "203.0.113.10", "22"]


def test_nc_all_open(env):
    fake(env, "nc")
    assert main(["open-ports", "-m", "nc", "example.com"]) == 0
    assert len(calls(env)) == 5


def test_curl_probes_every_port_and_reports(env, capsys):
    """Intentional change: legacy stopped at the first failing port."""
    fake(env, "curl", {"*:25": 7})
    assert main(["open-ports", "-m", "curl", "example.com", "25", "80"]) == 1
    assert calls(env) == [
        ["curl", "-s", "--connect-timeout", "5", "-o", "/dev/null", "http://example.com:25"],
        ["curl", "-s", "--connect-timeout", "5", "-o", "/dev/null", "http://example.com:80"],
    ]
    assert capsys.readouterr().out == "example.com:25 failed (curl exit 7)\nexample.com:80 ok\n"


def test_curl_ipv6_url(env, capsys):
    fake(env, "curl")
    assert main(["open-ports", "-m", "curl", "2001:db8::1", "80"]) == 0
    assert calls(env)[0][-1] == "http://[2001:db8::1]:80"
    assert capsys.readouterr().out == "[2001:db8::1]:80 ok\n"


# --- lazy tool check


@pytest.mark.parametrize("method", ["nmap", "nc", "curl"])
def test_missing_tool_named(env, capsys, method):
    for other in {"nmap", "nc", "curl"} - {method}:
        fake(env, other)
    assert main(["open-ports", "-m", method, "example.com"]) == 2
    assert capsys.readouterr().err == f"cca: error: {method} not found on PATH\n"
    assert calls(env) == []


# --- noact


def test_noact_prints_commands_runs_nothing(env, capsys):
    assert main(["open-ports", "-n", "-m", "curl", "example.com", "22", "80"]) == 0
    assert capsys.readouterr().out == (
        "curl -s --connect-timeout 5 -o /dev/null http://example.com:22\n"
        "curl -s --connect-timeout 5 -o /dev/null http://example.com:80\n"
    )


def test_noact_with_delegate(env, capsys):
    project(env)
    assert main(["open-ports", "--noact", "-d", "server1", "example.com", "22"]) == 0
    assert capsys.readouterr().out == (
        "ssh -- admin@server1.example.com 'nmap -Pn --reason -p 22 example.com'\n"
    )


# --- delegate


def test_delegate_runs_over_ssh(env):
    project(env)
    fake(env, "ssh")
    assert main(["open-ports", "-d", "server1", "-m", "nc", "example.com", "22", "80"]) == 0
    assert calls(env) == [
        ["ssh", "--", "admin@server1.example.com", "nc -zv -w 5 example.com 22"],
        ["ssh", "--", "admin@server1.example.com", "nc -zv -w 5 example.com 80"],
    ]


def test_delegate_ssh_defaults_to_server_name(env):
    project(env)
    fake(env, "ssh")
    assert main(["open-ports", "-d", "server2", "example.com", "22"]) == 0
    assert calls(env)[0][:3] == ["ssh", "--", "server2"]


def test_delegate_needs_only_ssh_locally(env):
    project(env)
    fake(env, "ssh", {"*:25": 7})
    assert main(["open-ports", "-d", "server1", "-m", "curl", "example.com", "25"]) == 1


def test_delegate_unknown_server(env, capsys):
    project(env)
    assert main(["open-ports", "-d", "server9", "example.com"]) == 2
    assert "unknown server 'server9' (servers: server1, server2)" in capsys.readouterr().err


def test_delegate_requires_config(env, capsys):
    assert main(["open-ports", "-d", "server1", "example.com"]) == 2
    assert "no .cca.toml found" in capsys.readouterr().err


def test_local_scan_ignores_invalid_config(env):
    """Config is loaded only for --delegate."""
    (env / "work" / ".cca.toml").write_text("schema_version = 0\n")
    fake(env, "nmap")
    assert main(["open-ports", "example.com"]) == 0
    assert main(["--config", str(env / "missing.toml"), "open-ports", "example.com"]) == 0


def test_delegate_ssh_missing(env, capsys):
    project(env)
    fake(env, "nmap")
    assert main(["open-ports", "-d", "server1", "example.com"]) == 2
    assert capsys.readouterr().err == "cca: error: ssh not found on PATH\n"


def test_delegate_ssh_failure_stops(env, capsys):
    project(env)
    fake(env, "ssh", {"*": 255})
    assert main(["open-ports", "-d", "server1", "-m", "nc", "example.com", "22", "80"]) == 2
    assert len(calls(env)) == 1
    assert capsys.readouterr().err == "cca: error: ssh to server1 failed (exit 255)\n"


def test_delegate_remote_tool_missing(env, capsys):
    project(env)
    fake(env, "ssh", {"*": 127})
    assert main(["open-ports", "-d", "server1", "example.com"]) == 2
    assert capsys.readouterr().err == "cca: error: nmap not found on server1\n"
