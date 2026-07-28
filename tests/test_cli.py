"""Tests for tmux_cli_python.cli — CLI entry points (scaffold smoke tests)."""

import logging

from typer.testing import CliRunner

from tmux_cli_python.cli import app, State, _setup_debug_logging

runner = CliRunner()


class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout


class TestRobotInit:
    def test_robot_init_flag(self):
        result = runner.invoke(app, ["--robot-init"])
        assert result.exit_code == 0
        assert "Configuration Template" in result.stdout
        assert ".tmux-cli-python.yaml" in result.stdout


class TestDoctor:
    def test_doctor_flag(self):
        result = runner.invoke(app, ["--doctor"])
        # Doctor exits with 0 or 1 depending on config/tmux state
        assert "Status Check" in result.stdout
        assert "tmux-cli-python" in result.stdout.lower() or "Status" in result.stdout


class TestRobotHelp:
    def test_robot_help_flag(self):
        result = runner.invoke(app, ["--robot-help"])
        assert result.exit_code == 0
        assert "Agent Guide" in result.stdout
        assert "tmux-cli-python" in result.stdout


class TestSubcommands:
    def test_list_no_session(self):
        result = runner.invoke(app, ["list"])
        # list should succeed even with no active windows
        assert result.exit_code == 0

    def test_run_requires_command(self):
        result = runner.invoke(app, ["run"])
        # Should error — command is required
        assert result.exit_code != 0

    def test_run_with_command(self):
        result = runner.invoke(app, ["-t", "web1", "run", "uptime"])
        assert result.exit_code == 0
        assert "uptime" in result.output

    def test_read_subcommand(self):
        result = runner.invoke(app, ["-t", "web1", "read"])
        assert result.exit_code == 0

    def test_session_subcommand(self):
        result = runner.invoke(app, ["session", "web1", "web2"])
        assert result.exit_code == 0
        assert "Session" in result.output

    def test_audit_query(self):
        result = runner.invoke(app, ["audit", "query", "--today"])
        # With audit enabled by default, entries may exist from previous run tests
        # (they write to logs/ dir). Just verify it doesn't crash.
        assert result.exit_code == 0


class TestGlobalOptions:
    def test_target_server(self):
        result = runner.invoke(app, ["-t", "web1", "list"])
        assert result.exit_code == 0

    def test_session_name(self):
        result = runner.invoke(app, ["-s", "test-session", "list"])
        assert result.exit_code == 0
        assert "test-session" in result.output

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "tmux-cli-python" in result.stdout.lower() or "Usage" in result.stdout


class TestDebugFlag:
    """Tests for the -x/--debug flag."""

    def test_debug_flag_accepted(self):
        """--debug should be accepted without error."""
        result = runner.invoke(app, ["--debug", "--version"])
        assert result.exit_code == 0

    def test_short_flag_x_accepted(self):
        """-x should be accepted as short form of --debug."""
        result = runner.invoke(app, ["-x", "--version"])
        assert result.exit_code == 0

    def test_debug_produces_debug_output(self):
        """--debug should produce [debug] lines on stderr."""
        result = runner.invoke(app, ["--debug", "--doctor"])
        # output contains both stdout and stderr mixed by CliRunner
        combined = result.output
        assert "[debug]" in combined
        assert "debug mode enabled" in combined

    def test_no_debug_without_flag(self):
        """Without --debug, no [debug] lines should appear."""
        result = runner.invoke(app, ["--doctor"])
        assert "[debug]" not in result.output

    def test_debug_with_robot_init(self):
        """--debug with --robot-init should log debug context."""
        result = runner.invoke(app, ["--debug", "--robot-init"])
        assert result.exit_code == 0
        assert "[debug]" in result.output
        assert "robot-init requested" in result.output

    def test_debug_with_robot_help(self):
        """--debug with --robot-help should log debug context."""
        result = runner.invoke(app, ["--debug", "--robot-help"])
        assert result.exit_code == 0
        assert "[debug]" in result.output
        assert "robot-help requested" in result.output

    def test_debug_with_run(self):
        """--debug with run command should log execution details."""
        result = runner.invoke(app, ["--debug", "-t", "web1", "run", "uptime"])
        assert result.exit_code == 0
        assert "[debug]" in result.output
        assert "run:" in result.output  # "run: server=web1 ..."
        assert "validation completed" in result.output
        assert "redaction completed" in result.output

    def test_setup_debug_logging(self):
        """_setup_debug_logging configures the logger correctly."""
        logger = logging.getLogger("tmux_cli_python")
        # Clear any existing handlers from previous tests
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)

        _setup_debug_logging()

        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1

        # Cleanup
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)
