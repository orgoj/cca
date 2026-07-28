"""Integration tests: verify that CLI subcommands produce audit log entries.

These tests exercise the full CLI pipeline (Typer CliRunner → cli.py → audit.py)
to confirm that every subcommand writes audit entries when audit is enabled.

The conftest.py mocks all tmux operations, so no real tmux sessions are created.
"""

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tmux_cli_python.cli import app

runner = CliRunner()


def _setup_project(tmp_path: Path, *, audit_enabled: bool = True, audit_dir: str = "logs") -> Path:
    """Create a minimal project directory with .tmux-cli-python.yaml config."""
    config_dir = tmp_path / "project"
    config_dir.mkdir()
    config_file = config_dir / ".tmux-cli-python.yaml"
    config_file.write_text(
        textwrap.dedent(f"""\
        session:
          name: cca-test
          servers: "web1 web2"
        audit:
          enabled: {str(audit_enabled).lower()}
          dir: {audit_dir}
        """)
    )
    return config_dir


def _read_audit_entries(log_dir: Path) -> list[dict]:
    """Read all audit entries from all JSONL files in log_dir."""
    entries = []
    for f in sorted(log_dir.glob("audit-*.jsonl")):
        for line in f.read_text().strip().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


# ---------------------------------------------------------------------------
# Tests: run subcommand audit integration
# ---------------------------------------------------------------------------


class TestRunAuditIntegration:
    def test_run_creates_audit_entry(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["-t", "web1", "run", "uptime"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        assert len(entries) >= 1
        run_entries = [e for e in entries if e["action"] == "run"]
        assert len(run_entries) >= 1
        assert run_entries[0]["server"] == "web1"
        assert run_entries[0]["command"] == "uptime"

    def test_run_no_server_no_audit(self, tmp_path: Path, monkeypatch):
        """Missing -t flag exits 64 before audit logger is involved."""
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["run", "uptime"])
        assert result.exit_code == 64

        # No audit entry because server check happens before logger init
        entries = _read_audit_entries(log_dir)
        run_entries = [e for e in entries if e["action"] == "run"]
        assert len(run_entries) == 0


# ---------------------------------------------------------------------------
# Tests: read subcommand audit integration
# ---------------------------------------------------------------------------


class TestReadAuditIntegration:
    def test_read_creates_audit_entry(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["-t", "web1", "read"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        read_entries = [e for e in entries if e["action"] == "read"]
        assert len(read_entries) == 1
        assert read_entries[0]["server"] == "web1"

    def test_read_no_server_exits_64(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["read"])
        assert result.exit_code == 64

        # No audit entry — server check is before logger init
        entries = _read_audit_entries(log_dir)
        read_entries = [e for e in entries if e["action"] == "read"]
        assert len(read_entries) == 0


# ---------------------------------------------------------------------------
# Tests: list subcommand audit integration
# ---------------------------------------------------------------------------


class TestListAuditIntegration:
    def test_list_creates_audit_entry(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        list_entries = [e for e in entries if e["action"] == "list"]
        assert len(list_entries) == 1

    def test_list_with_target_server(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["-t", "web1", "list"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        list_entries = [e for e in entries if e["action"] == "list"]
        assert len(list_entries) == 1
        assert list_entries[0]["server"] == "web1"


# ---------------------------------------------------------------------------
# Tests: session subcommand audit integration
# ---------------------------------------------------------------------------


class TestSessionAuditIntegration:
    def test_session_creates_audit_entry(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["session", "web1", "web2"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        session_entries = [e for e in entries if e["action"] == "session"]
        assert len(session_entries) == 1
        # Server field should contain the server list
        assert "web1" in session_entries[0]["server"]

    def test_session_uses_config_servers(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        # No server args — should use config servers (web1 web2)
        result = runner.invoke(app, ["session"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        session_entries = [e for e in entries if e["action"] == "session"]
        assert len(session_entries) == 1


# ---------------------------------------------------------------------------
# Tests: audit disabled
# ---------------------------------------------------------------------------


class TestAuditDisabledIntegration:
    def test_no_audit_when_disabled(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path, audit_enabled=False)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["-t", "web1", "run", "uptime"])
        assert result.exit_code == 0

        # No log directory should be created
        assert not log_dir.exists()

    def test_list_no_audit_when_disabled(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path, audit_enabled=False)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0

        assert not log_dir.exists()


# ---------------------------------------------------------------------------
# Tests: audit query returns CLI-generated entries
# ---------------------------------------------------------------------------


class TestAuditQueryRoundTrip:
    def test_query_returns_entries_from_run(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)

        # Run a command
        result = runner.invoke(app, ["-t", "web1", "run", "hostname"])
        assert result.exit_code == 0

        # Query audit entries
        result = runner.invoke(app, ["audit", "query", "--today"])
        assert result.exit_code == 0

        lines = [l for l in result.stdout.strip().splitlines() if l.startswith("{")]
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        assert entry["action"] == "run"
        assert entry["server"] == "web1"

    def test_query_filter_by_action(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)

        # Run multiple commands
        runner.invoke(app, ["-t", "web1", "run", "uptime"])
        runner.invoke(app, ["-t", "web1", "read"])
        runner.invoke(app, ["list"])

        # Query only run entries
        result = runner.invoke(app, ["audit", "query", "--today", "--action", "run"])
        assert result.exit_code == 0
        lines = [l for l in result.stdout.strip().splitlines() if l.startswith("{")]
        for line in lines:
            entry = json.loads(line)
            assert entry["action"] == "run"


# ---------------------------------------------------------------------------
# Tests: agent field population from config and env var
# ---------------------------------------------------------------------------


def _setup_project_with_agent(tmp_path: Path, agent: str) -> Path:
    """Create a project with audit.agent set in YAML config."""
    config_dir = tmp_path / "project"
    config_dir.mkdir()
    config_file = config_dir / ".tmux-cli-python.yaml"
    config_file.write_text(
        textwrap.dedent(f"""\
        session:
          name: cca-test
          servers: "web1 web2"
        audit:
          enabled: true
          dir: logs
          agent: {agent}
        """)
    )
    return config_dir


class TestAgentFieldPopulation:
    def test_agent_from_yaml_config(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project_with_agent(tmp_path, agent="hermes")
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["-t", "web1", "run", "uptime"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        run_entries = [e for e in entries if e["action"] == "run"]
        assert len(run_entries) >= 1
        assert run_entries[0]["agent"] == "hermes"

    def test_agent_from_env_var(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        monkeypatch.setenv("CCA_AGENT", "athena")

        result = runner.invoke(app, ["-t", "web1", "run", "uptime"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        run_entries = [e for e in entries if e["action"] == "run"]
        assert len(run_entries) >= 1
        assert run_entries[0]["agent"] == "athena"

    def test_config_agent_overrides_env_var(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project_with_agent(tmp_path, agent="hermes")
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        monkeypatch.setenv("CCA_AGENT", "athena")

        result = runner.invoke(app, ["-t", "web1", "run", "uptime"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        run_entries = [e for e in entries if e["action"] == "run"]
        assert len(run_entries) >= 1
        assert run_entries[0]["agent"] == "hermes"

    def test_agent_in_read_entry(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project_with_agent(tmp_path, agent="hermes")
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["-t", "web1", "read"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        read_entries = [e for e in entries if e["action"] == "read"]
        assert len(read_entries) == 1
        assert read_entries[0]["agent"] == "hermes"

    def test_agent_in_list_entry(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project_with_agent(tmp_path, agent="hermes")
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        list_entries = [e for e in entries if e["action"] == "list"]
        assert len(list_entries) == 1
        assert list_entries[0]["agent"] == "hermes"

    def test_agent_in_session_entry(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project_with_agent(tmp_path, agent="hermes")
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["session", "web1", "web2"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        session_entries = [e for e in entries if e["action"] == "session"]
        assert len(session_entries) == 1
        assert session_entries[0]["agent"] == "hermes"

    def test_agent_empty_when_not_configured(self, tmp_path: Path, monkeypatch):
        config_dir = _setup_project(tmp_path)
        log_dir = config_dir / "logs"

        monkeypatch.chdir(config_dir)
        monkeypatch.delenv("CCA_AGENT", raising=False)

        result = runner.invoke(app, ["-t", "web1", "run", "uptime"])
        assert result.exit_code == 0

        entries = _read_audit_entries(log_dir)
        run_entries = [e for e in entries if e["action"] == "run"]
        assert len(run_entries) >= 1
        assert run_entries[0]["agent"] == ""
