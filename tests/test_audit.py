"""Tests for tmux_cli_python.audit — JSONL logging, rotation, and query."""

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from tmux_cli_python.audit import AuditEntry, AuditLogger, AuditQuery, HookResult
from tmux_cli_python.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# AuditEntry tests
# ---------------------------------------------------------------------------


class TestAuditEntry:
    def test_to_dict_basic(self):
        entry = AuditEntry(
            ts="2026-04-12T14:30:00+00:00",
            agent="hermes",
            server="web1",
            action="run",
            command="uptime",
            exit_code=0,
            duration_ms=1200,
        )
        d = entry.to_dict()
        assert d["ts"] == "2026-04-12T14:30:00+00:00"
        assert d["agent"] == "hermes"
        assert d["server"] == "web1"
        assert d["action"] == "run"
        assert d["command"] == "uptime"
        assert d["exit_code"] == 0
        assert d["duration_ms"] == 1200
        assert d["validation"] == []
        assert d["redaction"] == []

    def test_to_dict_omits_none(self):
        entry = AuditEntry(ts="2026-04-12T14:30:00+00:00", action="list")
        d = entry.to_dict()
        assert "exit_code" not in d
        assert "duration_ms" not in d
        assert "command" in d  # empty string, not None
        assert d["command"] == ""

    def test_to_jsonl(self):
        entry = AuditEntry(
            ts="2026-04-12T14:30:00+00:00",
            agent="hermes",
            server="web1",
            action="run",
            command="uptime",
            exit_code=0,
        )
        line = entry.to_jsonl()
        parsed = json.loads(line)
        assert parsed["action"] == "run"
        # Should be a single line
        assert "\n" not in line

    def test_to_dict_with_hooks(self):
        entry = AuditEntry(
            ts="2026-04-12T14:30:00+00:00",
            action="run",
            validation=[{"hook": "dippy", "result": "approved"}],
            redaction=[{"hook": "secretctl", "result": "pass"}],
        )
        d = entry.to_dict()
        assert len(d["validation"]) == 1
        assert d["validation"][0]["hook"] == "dippy"
        assert len(d["redaction"]) == 1

    def test_hook_result_as_dict(self):
        hr = HookResult(hook="dippy", result="denied", reason="Destructive command")
        # Can be serialized to dict via dataclasses.asdict
        from dataclasses import asdict

        d2 = asdict(hr)
        assert d2["hook"] == "dippy"
        assert d2["result"] == "denied"
        assert d2["reason"] == "Destructive command"


# ---------------------------------------------------------------------------
# AuditLogger tests
# ---------------------------------------------------------------------------


class TestAuditLogger:
    def test_write_creates_file(self, tmp_path: Path):
        logger = AuditLogger(log_dir=str(tmp_path / "logs"), enabled=True)
        entry = AuditEntry(
            ts="2026-04-12T14:30:00+00:00",
            agent="test",
            server="web1",
            action="run",
            command="uptime",
            exit_code=0,
        )
        logger.write(entry)

        log_file = tmp_path / "logs" / "audit-2026-04-12.jsonl"
        assert log_file.exists()

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["agent"] == "test"
        assert parsed["action"] == "run"

    def test_write_disabled_is_noop(self, tmp_path: Path):
        logger = AuditLogger(log_dir=str(tmp_path / "logs"), enabled=False)
        entry = AuditEntry(ts="2026-04-12T14:30:00+00:00", action="run")
        logger.write(entry)

        # No directory should be created
        assert not (tmp_path / "logs").exists()

    def test_daily_rotation(self, tmp_path: Path):
        """Entries from different dates go to different files."""
        logger = AuditLogger(log_dir=str(tmp_path / "logs"), enabled=True)

        entry1 = AuditEntry(ts="2026-04-12T14:30:00+00:00", action="run", command="cmd1")
        entry2 = AuditEntry(ts="2026-04-13T09:00:00+00:00", action="run", command="cmd2")
        entry3 = AuditEntry(ts="2026-04-12T23:59:59+00:00", action="run", command="cmd3")

        logger.write(entry1)
        logger.write(entry2)
        logger.write(entry3)

        day1 = tmp_path / "logs" / "audit-2026-04-12.jsonl"
        day2 = tmp_path / "logs" / "audit-2026-04-13.jsonl"

        assert day1.exists()
        assert day2.exists()

        day1_lines = day1.read_text().strip().splitlines()
        day2_lines = day2.read_text().strip().splitlines()

        assert len(day1_lines) == 2  # entry1 and entry3
        assert len(day2_lines) == 1  # entry2

        parsed_day2 = json.loads(day2_lines[0])
        assert parsed_day2["command"] == "cmd2"

    def test_write_appends_to_existing(self, tmp_path: Path):
        """Multiple writes to same day append to the same file."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "audit-2026-04-12.jsonl").write_text('{"existing": true}\n')

        logger = AuditLogger(log_dir=str(log_dir), enabled=True)
        entry = AuditEntry(ts="2026-04-12T14:30:00+00:00", action="run")
        logger.write(entry)

        lines = (log_dir / "audit-2026-04-12.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2

    def test_write_now_convenience(self, tmp_path: Path):
        logger = AuditLogger(log_dir=str(tmp_path / "logs"), enabled=True)
        validation = [HookResult(hook="dippy", result="approved")]
        redaction = [HookResult(hook="secretctl", result="pass")]

        entry = logger.write_now(
            agent="hermes",
            server="web1",
            action="run",
            command="uptime",
            exit_code=0,
            duration_ms=500,
            validation=validation,
            redaction=redaction,
        )

        # Entry should have been written and returned
        assert entry.agent == "hermes"
        assert entry.server == "web1"
        assert len(entry.validation) == 1
        assert len(entry.redaction) == 1

        # Verify it was actually written
        log_files = list((tmp_path / "logs").glob("audit-*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().splitlines()
        assert len(lines) == 1

    def test_creates_log_dir_if_missing(self, tmp_path: Path):
        nested = tmp_path / "deep" / "nested" / "logs"
        logger = AuditLogger(log_dir=str(nested), enabled=True)
        entry = AuditEntry(ts="2026-04-12T14:30:00+00:00", action="run")
        logger.write(entry)
        assert nested.exists()

    def test_entry_with_denied_validation(self, tmp_path: Path):
        """Spec example: denied validation with reason."""
        logger = AuditLogger(log_dir=str(tmp_path / "logs"), enabled=True)
        entry = AuditEntry(
            ts="2026-04-12T14:30:15+00:00",
            agent="hermes",
            server="db1",
            action="run",
            command="rm -rf /var/log/*",
            validation=[{"hook": "dippy", "result": "denied", "reason": "Destructive command"}],
        )
        logger.write(entry)

        log_file = tmp_path / "logs" / "audit-2026-04-12.jsonl"
        parsed = json.loads(log_file.read_text().strip())
        assert parsed["validation"][0]["result"] == "denied"
        assert "Destructive" in parsed["validation"][0]["reason"]


# ---------------------------------------------------------------------------
# AuditQuery tests
# ---------------------------------------------------------------------------


class TestAuditQuery:
    def _write_log(self, log_dir: Path, date: str, entries: list[dict]) -> None:
        """Helper: write JSONL entries to a specific date file."""
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"audit-{date}.jsonl"
        with open(path, "a") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def test_query_returns_all(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        self._write_log(
            log_dir,
            "2026-04-12",
            [
                {"ts": "2026-04-12T10:00:00+00:00", "action": "run", "server": "web1"},
                {"ts": "2026-04-12T11:00:00+00:00", "action": "read", "server": "web2"},
            ],
        )

        q = AuditQuery(log_dir=str(log_dir))
        results = q.query()
        assert len(results) == 2

    def test_query_by_server(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        self._write_log(
            log_dir,
            "2026-04-12",
            [
                {"ts": "2026-04-12T10:00:00+00:00", "action": "run", "server": "web1"},
                {"ts": "2026-04-12T11:00:00+00:00", "action": "run", "server": "web2"},
                {"ts": "2026-04-12T12:00:00+00:00", "action": "run", "server": "web1"},
            ],
        )

        q = AuditQuery(log_dir=str(log_dir))
        results = q.query(server="web1")
        assert len(results) == 2
        assert all(r["server"] == "web1" for r in results)

    def test_query_by_agent(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        self._write_log(
            log_dir,
            "2026-04-12",
            [
                {"ts": "2026-04-12T10:00:00+00:00", "action": "run", "agent": "hermes"},
                {"ts": "2026-04-12T11:00:00+00:00", "action": "run", "agent": "athena"},
            ],
        )

        q = AuditQuery(log_dir=str(log_dir))
        results = q.query(agent="hermes")
        assert len(results) == 1
        assert results[0]["agent"] == "hermes"

    def test_query_by_action(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        self._write_log(
            log_dir,
            "2026-04-12",
            [
                {"ts": "2026-04-12T10:00:00+00:00", "action": "run"},
                {"ts": "2026-04-12T11:00:00+00:00", "action": "read"},
                {"ts": "2026-04-12T12:00:00+00:00", "action": "run"},
            ],
        )

        q = AuditQuery(log_dir=str(log_dir))
        results = q.query(action="run")
        assert len(results) == 2

    def test_query_by_date(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        self._write_log(
            log_dir,
            "2026-04-12",
            [
                {"ts": "2026-04-12T10:00:00+00:00", "action": "run"},
            ],
        )
        self._write_log(
            log_dir,
            "2026-04-13",
            [
                {"ts": "2026-04-13T10:00:00+00:00", "action": "run"},
            ],
        )

        q = AuditQuery(log_dir=str(log_dir))
        results = q.query(date="2026-04-12")
        assert len(results) == 1

    def test_query_newest_first(self, tmp_path: Path):
        """Results should be reversed so newest come first."""
        log_dir = tmp_path / "logs"
        self._write_log(
            log_dir,
            "2026-04-12",
            [
                {"ts": "2026-04-12T10:00:00+00:00", "action": "run", "command": "first"},
                {"ts": "2026-04-12T11:00:00+00:00", "action": "run", "command": "second"},
                {"ts": "2026-04-12T12:00:00+00:00", "action": "run", "command": "third"},
            ],
        )

        q = AuditQuery(log_dir=str(log_dir))
        results = q.query()
        assert results[0]["command"] == "third"
        assert results[2]["command"] == "first"

    def test_query_empty_dir(self, tmp_path: Path):
        q = AuditQuery(log_dir=str(tmp_path / "nonexistent"))
        results = q.query()
        assert results == []

    def test_query_skips_malformed_lines(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        path = log_dir / "audit-2026-04-12.jsonl"
        path.write_text(
            '{"ts": "ok", "action": "run"}\nnot-json\n\n{"ts": "ok2", "action": "read"}\n'
        )

        q = AuditQuery(log_dir=str(log_dir))
        results = q.query()
        assert len(results) == 2

    def test_query_combined_filters(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        self._write_log(
            log_dir,
            "2026-04-12",
            [
                {
                    "ts": "2026-04-12T10:00:00+00:00",
                    "action": "run",
                    "server": "web1",
                    "agent": "hermes",
                },
                {
                    "ts": "2026-04-12T11:00:00+00:00",
                    "action": "run",
                    "server": "web2",
                    "agent": "hermes",
                },
                {
                    "ts": "2026-04-12T12:00:00+00:00",
                    "action": "read",
                    "server": "web1",
                    "agent": "hermes",
                },
            ],
        )

        q = AuditQuery(log_dir=str(log_dir))
        # Filter by both server and action
        results = q.query(server="web1", action="run")
        assert len(results) == 1
        assert results[0]["server"] == "web1"
        assert results[0]["action"] == "run"

    def test_query_across_multiple_files(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        self._write_log(
            log_dir,
            "2026-04-11",
            [
                {"ts": "2026-04-11T10:00:00+00:00", "action": "run", "server": "web1"},
            ],
        )
        self._write_log(
            log_dir,
            "2026-04-12",
            [
                {"ts": "2026-04-12T10:00:00+00:00", "action": "run", "server": "web1"},
                {"ts": "2026-04-12T11:00:00+00:00", "action": "run", "server": "web2"},
            ],
        )

        q = AuditQuery(log_dir=str(log_dir))
        results = q.query(server="web1")
        assert len(results) == 2  # one from each day


# ---------------------------------------------------------------------------
# CLI audit query integration tests
# ---------------------------------------------------------------------------


class TestAuditQueryCLI:
    def _write_log(self, log_dir: Path, date: str, entries: list[dict]) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"audit-{date}.jsonl"
        with open(path, "a") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def test_query_disabled(self, tmp_path: Path, monkeypatch):
        """When audit is disabled, query should return error."""
        # Create a config that has audit disabled
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
            audit:
              enabled: false
              dir: logs
        """)
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["audit", "query", "--today"])
        assert result.exit_code == 1
        # Typer puts the error message in result.output
        assert "disabled" in result.output.lower()

    def test_query_no_entries(self, tmp_path: Path, monkeypatch):
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
            audit:
              enabled: true
              dir: logs
        """)
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["audit", "query", "--today"])
        assert "No audit entries" in result.stdout

    def test_query_with_entries(self, tmp_path: Path, monkeypatch):
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
            audit:
              enabled: true
              dir: logs
        """)
        )

        log_dir = config_dir / "logs"
        today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        self._write_log(
            log_dir,
            today_str,
            [
                {"ts": "2026-04-12T10:00:00+00:00", "action": "run", "server": "web1"},
                {"ts": "2026-04-12T11:00:00+00:00", "action": "read", "server": "web2"},
            ],
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["audit", "query", "--today"])
        assert result.exit_code == 0
        # Should output JSONL lines
        lines = [line for line in result.stdout.strip().splitlines() if line.startswith("{")]
        assert len(lines) == 2

    def test_query_filter_by_server(self, tmp_path: Path, monkeypatch):
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
            audit:
              enabled: true
              dir: logs
        """)
        )

        log_dir = config_dir / "logs"
        today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        self._write_log(
            log_dir,
            today_str,
            [
                {"ts": "2026-04-12T10:00:00+00:00", "action": "run", "server": "web1"},
                {"ts": "2026-04-12T11:00:00+00:00", "action": "run", "server": "web2"},
            ],
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["audit", "query", "--today", "--server", "web1"])
        lines = [line for line in result.stdout.strip().splitlines() if line.startswith("{")]
        assert len(lines) == 1
        assert "web1" in lines[0]
