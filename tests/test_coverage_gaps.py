"""Tests for coverage gaps — edge cases in audit, config, and cli modules.

Targets uncovered lines identified by pytest-cov:
- audit.py:72 (_today_filename)
- audit.py:208-209 (OSError handling in AuditQuery)
- cli.py:305-306, 320, 327, 336, 340-345, 356-357 (_doctor branches)
- config.py:97, 103 (edge cases in _parse_session, _parse_confirmation)
"""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from tmux_cli_python.audit import AuditEntry, AuditLogger, AuditQuery, _today_filename
from tmux_cli_python.cli import _doctor, app
from tmux_cli_python.config import (
    AppConfig,
    AuditConfig,
    ConfirmationConfig,
    HookPipelineConfig,
    LoggingConfig,
    SessionConfig,
    _parse_confirmation,
    _parse_session,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# audit.py: _today_filename
# ---------------------------------------------------------------------------


class TestTodayFilename:
    def test_today_filename_format(self):
        """_today_filename returns audit-YYYY-MM-DD.jsonl."""
        filename = _today_filename()
        assert filename.startswith("audit-")
        assert filename.endswith(".jsonl")
        # audit-YYYY-MM-DD.jsonl = 22 chars
        assert len(filename) == 22

    def test_today_filename_uses_utc(self):
        """_today_filename uses UTC date."""
        from datetime import datetime, timezone

        filename = _today_filename()
        expected_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert expected_date in filename


# ---------------------------------------------------------------------------
# audit.py: OSError handling in AuditQuery._find_files
# ---------------------------------------------------------------------------


class TestAuditQueryOSError:
    def test_query_handles_unreadable_file(self, tmp_path: Path):
        """AuditQuery should skip files that raise OSError."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create a valid JSONL file
        valid = log_dir / "audit-2026-04-12.jsonl"
        valid.write_text('{"ts": "ok", "action": "run"}\n')

        # Mock read_text to raise OSError for the file
        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            q = AuditQuery(log_dir=str(log_dir))
            results = q.query()
            assert results == []  # OSError caught, skipped

    def test_query_handles_mixed_valid_and_oserror(self, tmp_path: Path):
        """When some files have OSError, valid files still return results."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        f1 = log_dir / "audit-2026-04-11.jsonl"
        f1.write_text('{"ts": "ok", "action": "run", "server": "s1"}\n')

        f2 = log_dir / "audit-2026-04-12.jsonl"
        f2.write_text('{"ts": "ok", "action": "read", "server": "s2"}\n')

        original_read_text = Path.read_text

        def mock_read_text(self, *args, **kwargs):
            if "audit-2026-04-11" in str(self):
                raise OSError("broken")
            return original_read_text(self, *args, **kwargs)

        with patch.object(Path, "read_text", mock_read_text):
            q = AuditQuery(log_dir=str(log_dir))
            results = q.query()
            assert len(results) == 1
            assert results[0]["server"] == "s2"


# ---------------------------------------------------------------------------
# config.py: _parse_session edge cases
# ---------------------------------------------------------------------------


class TestParseSessionEdgeCases:
    def test_servers_as_integer_type(self):
        """Servers field as integer (unexpected type) should yield empty list."""
        raw = {"servers": 42}
        result = _parse_session(raw)
        assert result.servers == []

    def test_servers_as_none(self):
        """Servers field missing should yield empty list."""
        raw = {}
        result = _parse_session(raw)
        assert result.servers == []

    def test_servers_as_float(self):
        """Servers field as float should yield empty list."""
        raw = {"servers": 3.14}
        result = _parse_session(raw)
        assert result.servers == []

    def test_servers_empty_string(self):
        """Empty string servers should yield empty list."""
        raw = {"servers": ""}
        result = _parse_session(raw)
        assert result.servers == []


# ---------------------------------------------------------------------------
# config.py: _parse_confirmation edge case (line 103)
# ---------------------------------------------------------------------------


class TestParseConfirmationEdgeCases:
    def test_none_input(self):
        """None input returns default ConfirmationConfig."""
        result = _parse_confirmation(None)
        assert result.cmd == ""

    def test_empty_dict(self):
        """Empty dict returns default ConfirmationConfig."""
        result = _parse_confirmation({})
        assert result.cmd == ""

    def test_dict_with_cmd(self):
        """Dict with cmd returns ConfirmationConfig with that cmd."""
        result = _parse_confirmation({"cmd": "zenity --question"})
        assert result.cmd == "zenity --question"


# ---------------------------------------------------------------------------
# cli.py: _doctor branches — full coverage
# ---------------------------------------------------------------------------


class TestDoctorBranches:
    def test_doctor_no_session_name_shows_derived(self, tmp_path: Path, monkeypatch):
        """When session name is empty and no config file, doctor shows derived name."""
        # No config file — doctor will show "None found" and derived session name
        work_dir = tmp_path / "workdir"
        work_dir.mkdir()
        monkeypatch.chdir(work_dir)
        result = runner.invoke(app, ["--doctor"])
        # With no config file, session name is derived from directory name
        assert "Derived" in result.stdout or "cca-workdir" in result.stdout

    def test_doctor_derived_name_direct_call(self, tmp_path: Path, monkeypatch):
        """Directly test _doctor with empty session name triggers derivation."""
        monkeypatch.chdir(tmp_path)
        # Create a config with no session name, but with config_path set
        # so it doesn't show "None found"
        config = AppConfig(
            config_path=str(tmp_path / ".tmux-cli-python.yaml"),
            session=SessionConfig(name="", servers=["web1"]),
        )
        # _doctor raises typer.Exit, so we catch it
        from typer import Exit

        with pytest.raises(Exit):
            _doctor(config)

    def test_doctor_with_validation_enabled(self, tmp_path: Path, monkeypatch):
        """Doctor shows validation hooks when enabled."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
              servers: "web1"
            validation:
              enabled: true
              hooks:
                - "dippy --cmd-stdin"
        """)
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["--doctor"])
        assert "Validation" in result.stdout
        assert "Enabled" in result.stdout

    def test_doctor_with_redaction_enabled(self, tmp_path: Path, monkeypatch):
        """Doctor shows redaction hooks when enabled."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
              servers: "web1"
            redaction:
              enabled: true
              hooks:
                - "secretctl sanitize"
        """)
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["--doctor"])
        assert "Redaction" in result.stdout
        assert "Enabled" in result.stdout

    def test_doctor_with_audit_disabled(self, tmp_path: Path, monkeypatch):
        """Doctor shows audit disabled when audit.enabled=false."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
              servers: "web1"
            audit:
              enabled: false
        """)
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["--doctor"])
        assert "Audit" in result.stdout
        assert "Disabled" in result.stdout

    def test_doctor_logging_enabled_with_admin(self, tmp_path: Path, monkeypatch):
        """Doctor shows logging enabled with admin_name."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
              servers: "web1"
            logging:
              enabled: true
              admin_name: "agent"
        """)
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["--doctor"])
        assert "Logging" in result.stdout
        assert "agent" in result.stdout

    def test_doctor_logging_enabled_without_admin(self, tmp_path: Path, monkeypatch):
        """Doctor shows error when logging enabled but admin_name missing."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
              servers: "web1"
            logging:
              enabled: true
              admin_name: ""
        """)
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["--doctor"])
        assert "admin_name missing" in result.stdout
        assert "ISSUES FOUND" in result.stdout

    def test_doctor_tmux_not_found(self, tmp_path: Path, monkeypatch):
        """Doctor shows 'Not found' when tmux binary is not available."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
              servers: "web1"
        """)
        )

        monkeypatch.chdir(config_dir)

        # Mock shutil.which to simulate tmux not being installed
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["--doctor"])
            assert "Not found" in result.stdout
            assert "ISSUES FOUND" in result.stdout

    def test_doctor_full_config_all_ok(self, tmp_path: Path, monkeypatch):
        """Doctor with full valid config shows all OK."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-testproject
              servers: "web1 web2"
            validation:
              enabled: true
              hooks:
                - "dippy"
            redaction:
              enabled: true
              hooks:
                - "secretctl"
            audit:
              enabled: true
              dir: logs
            logging:
              enabled: false
        """)
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["--doctor"])
        assert "cca-testproject" in result.stdout
        assert "2 configured" in result.stdout
        assert "Enabled (1 hook(s))" in result.stdout

    def test_doctor_no_config_file(self, monkeypatch, tmp_path: Path):
        """Doctor with no config file at all shows 'None found'."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)
        result = runner.invoke(app, ["--doctor"])
        assert "None found" in result.stdout


# ---------------------------------------------------------------------------
# cli.py: debug flag (line 109 edge)
# ---------------------------------------------------------------------------


class TestDebugFlag:
    def test_debug_flag_accepted(self):
        """The -x flag is accepted without error."""
        result = runner.invoke(app, ["-x", "--version"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# HookPipelineConfig dataclass coverage
# ---------------------------------------------------------------------------


class TestHookPipelineConfigDataclass:
    def test_defaults(self):
        cfg = HookPipelineConfig()
        assert cfg.enabled is False
        assert cfg.hooks == []
        assert cfg.confirmation.cmd == ""

    def test_with_values(self):
        cfg = HookPipelineConfig(
            enabled=True,
            hooks=["dippy --cmd-stdin"],
            confirmation=ConfirmationConfig(cmd="zenity --question '{message}'"),
        )
        assert cfg.enabled is True
        assert len(cfg.hooks) == 1
        assert cfg.confirmation.cmd == "zenity --question '{message}'"


# ---------------------------------------------------------------------------
# AppConfig defaults and construction
# ---------------------------------------------------------------------------


class TestAppConfigDefaults:
    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.session.name == ""
        assert cfg.validation.enabled is False
        assert cfg.redaction.enabled is False
        assert cfg.audit.enabled is True  # default is True per spec
        assert cfg.logging.enabled is False
        assert cfg.config_path is None

    def test_config_path_set(self):
        cfg = AppConfig(config_path="/tmp/.tmux-cli-python.yaml")
        assert cfg.config_path == "/tmp/.tmux-cli-python.yaml"


# ---------------------------------------------------------------------------
# AuditConfig and LoggingConfig defaults
# ---------------------------------------------------------------------------


class TestConfigDataclassDefaults:
    def test_audit_config_defaults(self):
        cfg = AuditConfig()
        assert cfg.enabled is True
        assert cfg.dir == "logs"

    def test_logging_config_defaults(self):
        cfg = LoggingConfig()
        assert cfg.enabled is False
        assert cfg.admin_name == ""

    def test_session_config_defaults(self):
        cfg = SessionConfig()
        assert cfg.name == ""
        assert cfg.servers == []


# ---------------------------------------------------------------------------
# AuditEntry edge cases
# ---------------------------------------------------------------------------


class TestAuditEntryEdgeCases:
    def test_empty_entry(self):
        """Minimal entry with only timestamp."""
        entry = AuditEntry(ts="2026-04-12T00:00:00+00:00")
        d = entry.to_dict()
        assert d["ts"] == "2026-04-12T00:00:00+00:00"
        assert "exit_code" not in d
        assert "duration_ms" not in d
        assert d["agent"] == ""
        assert d["server"] == ""

    def test_jsonl_sort_keys(self):
        """JSONL output should have sorted keys."""
        entry = AuditEntry(ts="2026-04-12T00:00:00+00:00", action="run")
        line = entry.to_jsonl()
        parsed = json.loads(line)
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_write_now_returns_entry_with_correct_ts(self, tmp_path: Path):
        """write_now generates a valid ISO timestamp."""
        logger = AuditLogger(log_dir=str(tmp_path / "logs"), enabled=True)
        entry = logger.write_now(action="run", server="web1")
        assert entry.ts  # non-empty
        # Should be parseable as ISO
        from datetime import datetime

        datetime.fromisoformat(entry.ts)
