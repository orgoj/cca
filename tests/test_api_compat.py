"""API compatibility tests — verify Python CLI surface matches bash cca-tmux-cli.

These tests validate that every flag, subcommand, option, and behavior from the
bash cca-tmux-cli v1.8.0 has a matching surface in the Python rewrite.

Reference: bin/cca-tmux-cli
"""

import textwrap
from pathlib import Path

from typer.testing import CliRunner

from tmux_cli_python.cli import app
from tmux_cli_python.config import (
    derive_session_name,
    load_bash_env_config,
    load_config,
)

runner = CliRunner()


# ===========================================================================
# 1. Global option flags
# ===========================================================================


class TestGlobalFlagsCompat:
    """Every global flag from bash must exist in Python."""

    def test_version_short_flag(self):
        """bash: -V shows version."""
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout

    def test_version_long_flag(self):
        """bash: --version shows version."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout

    def test_help_short_flag(self):
        """bash: -h shows help."""
        result = runner.invoke(app, ["-h"])
        assert result.exit_code == 0

    def test_help_long_flag(self):
        """bash: --help shows help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_target_server_short(self):
        """bash: -t <server> targets specific server."""
        result = runner.invoke(app, ["-t", "web1", "list"])
        assert result.exit_code == 0

    def test_session_short(self):
        """bash: -s <session> targets specific session."""
        result = runner.invoke(app, ["-s", "cca-test", "list"])
        assert result.exit_code == 0
        assert "cca-test" in result.stdout

    def test_debug_flag(self):
        """bash: -x enables debug mode (set -x)."""
        result = runner.invoke(app, ["-x", "list"])
        # Should not error — flag is accepted
        assert result.exit_code == 0

    def test_robot_init_flag(self):
        """bash: --robot-init shows config template."""
        result = runner.invoke(app, ["--robot-init"])
        assert result.exit_code == 0
        assert "Configuration Template" in result.stdout

    def test_doctor_flag(self):
        """bash: --doctor validates configuration and shows status."""
        result = runner.invoke(app, ["--doctor"])
        assert "Status Check" in result.stdout
        assert "tmux-cli-python" in result.stdout.lower() or "Status" in result.stdout

    def test_robot_help_flag(self):
        """bash: --robot-help shows agent-specific documentation."""
        result = runner.invoke(app, ["--robot-help"])
        assert result.exit_code == 0
        assert "Agent Guide" in result.stdout

    def test_unknown_flag_errors(self):
        """bash: Unknown global option -> error exit 64."""
        result = runner.invoke(app, ["--nonexistent"])
        assert result.exit_code != 0


# ===========================================================================
# 2. Subcommand surface
# ===========================================================================


class TestSubcommandSurfaceCompat:
    """Every subcommand from bash must exist with matching argument surface."""

    # --- list ---

    def test_list_subcommand(self):
        """bash: cca-tmux-cli list."""
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0

    def test_list_raw_flag(self):
        """bash: cca-tmux-cli list --raw."""
        result = runner.invoke(app, ["list", "--raw"])
        assert result.exit_code == 0

    # --- run ---

    def test_run_requires_command(self):
        """bash: cca-tmux-cli -t srv run (no command) -> error exit 64."""
        result = runner.invoke(app, ["run"])
        assert result.exit_code != 0

    def test_run_with_command(self):
        """bash: cca-tmux-cli -t srv run "uptime"."""
        result = runner.invoke(app, ["-t", "web1", "run", "uptime"])
        assert result.exit_code == 0
        assert "uptime" in result.output

    def test_run_interval_flag(self):
        """bash: cca-tmux-cli -t srv run --interval 5 "cmd"."""
        result = runner.invoke(app, ["-t", "web1", "run", "--interval", "5", "uptime"])
        assert result.exit_code == 0

    def test_run_timeout_flag(self):
        """bash: cca-tmux-cli -t srv run --timeout 60 "cmd"."""
        result = runner.invoke(app, ["-t", "web1", "run", "--timeout", "60", "uptime"])
        assert result.exit_code == 0

    def test_run_all_flags_combined(self):
        """bash: full run invocation with all options."""
        result = runner.invoke(
            app,
            [
                "-t",
                "web1",
                "-s",
                "cca-test",
                "run",
                "--interval",
                "3",
                "--timeout",
                "120",
                "uptime",
            ],
        )
        assert result.exit_code == 0
        assert "uptime" in result.output

    # --- read ---

    def test_read_subcommand(self):
        """bash: cca-tmux-cli -t srv read."""
        result = runner.invoke(app, ["-t", "web1", "read"])
        assert result.exit_code == 0

    def test_read_all_flag(self):
        """bash: cca-tmux-cli -t srv read --all."""
        result = runner.invoke(app, ["-t", "web1", "read", "--all"])
        assert result.exit_code == 0

    def test_read_marker_flag(self):
        """bash: cca-tmux-cli -t srv read --marker TMUX_MARKER_xxx."""
        result = runner.invoke(app, ["-t", "web1", "read", "--marker", "TMUX_MARKER_123"])
        assert result.exit_code == 0

    def test_read_history_lines(self):
        """bash: cca-tmux-cli -t srv read 100."""
        result = runner.invoke(app, ["-t", "web1", "read", "100"])
        assert result.exit_code == 0

    def test_read_invalid_history_errors(self):
        """bash: cca-tmux-cli -t srv read abc -> error (must be number)."""
        result = runner.invoke(app, ["read", "abc"])
        # Typer should reject non-integer argument
        assert result.exit_code != 0

    # --- session ---

    def test_session_subcommand_with_servers(self):
        """bash: cca-tmux-cli session web1 web2."""
        result = runner.invoke(app, ["session", "web1", "web2"])
        assert result.exit_code == 0
        assert "web1" in result.stdout
        assert "web2" in result.stdout

    def test_session_subcommand_no_servers_uses_config(self):
        """bash: cca-tmux-cli session (no args -> uses TMUX_SESSION_SERVERS)."""
        result = runner.invoke(app, ["session"])
        # With no config, no servers available — should error
        assert result.exit_code != 0


# ===========================================================================
# 3. --robot-init output format
# ===========================================================================


class TestRobotInitCompat:
    """--robot-init must provide equivalent functionality to bash version."""

    def test_shows_config_template(self):
        result = runner.invoke(app, ["--robot-init"])
        assert result.exit_code == 0
        assert "Configuration Template" in result.stdout

    def test_mentions_yaml_config(self):
        """Python version uses .tmux-cli-python.yaml instead of .cca-tmux-cli."""
        result = runner.invoke(app, ["--robot-init"])
        assert ".tmux-cli-python.yaml" in result.stdout

    def test_shows_step_by_step_instructions(self):
        """bash version has STEP 1/2/3 instructions."""
        result = runner.invoke(app, ["--robot-init"])
        assert "STEP 1" in result.stdout
        assert "STEP 2" in result.stdout
        assert "STEP 3" in result.stdout

    def test_mentions_robot_help(self):
        """bash: 'For detailed help: cca-tmux-cli --robot-help'."""
        result = runner.invoke(app, ["--robot-init"])
        assert "--robot-help" in result.stdout

    def test_shows_server_discovery_hints(self):
        """bash shows hints about finding servers in project docs."""
        result = runner.invoke(app, ["--robot-init"])
        assert "servers" in result.stdout.lower()


# ===========================================================================
# 4. --doctor output format
# ===========================================================================


class TestDoctorCompat:
    """--doctor must match bash behavior: validate config, check tmux, show status."""

    def test_shows_status_header(self):
        result = runner.invoke(app, ["--doctor"])
        assert "Status Check" in result.stdout

    def test_checks_config_file(self):
        """bash: checks for .cca-tmux-cli or .env."""
        result = runner.invoke(app, ["--doctor"])
        assert "Config file" in result.stdout

    def test_checks_session_name(self):
        result = runner.invoke(app, ["--doctor"])
        assert "Session name" in result.stdout

    def test_checks_servers(self):
        result = runner.invoke(app, ["--doctor"])
        assert "Servers" in result.stdout

    def test_checks_tmux_installed(self):
        """bash: 'Tmux: ✓ Installed' or '✗ Not found'."""
        result = runner.invoke(app, ["--doctor"])
        assert "Tmux" in result.stdout

    def test_shows_final_status(self):
        """bash: '=== Status: OK ===' or '=== Status: ISSUES FOUND ==='."""
        result = runner.invoke(app, ["--doctor"])
        assert "Status:" in result.stdout

    def test_with_valid_config(self, tmp_path: Path, monkeypatch):
        """Doctor with valid config should show all checkmarks."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-testproject
              servers: "web1 web2"
            """)
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["--doctor"])
        assert "cca-testproject" in result.stdout
        assert "web1" in result.stdout


# ===========================================================================
# 5. --robot-help output format
# ===========================================================================


class TestRobotHelpCompat:
    """--robot-help must provide equivalent agent guide to bash version."""

    def test_shows_agent_guide(self):
        result = runner.invoke(app, ["--robot-help"])
        assert "Agent Guide" in result.stdout

    def test_explains_what_tool_does(self):
        """bash: 'What This Tool Does' section."""
        result = runner.invoke(app, ["--robot-help"])
        assert "What This Tool Does" in result.stdout

    def test_mentions_visible_sessions(self):
        """bash: Sessions are VISIBLE to users."""
        result = runner.invoke(app, ["--robot-help"])
        assert "VISIBLE" in result.stdout

    def test_shows_common_commands(self):
        """bash: Common Commands section with examples."""
        result = runner.invoke(app, ["--robot-help"])
        assert "Common Commands" in result.stdout
        assert "list" in result.stdout
        assert "run" in result.stdout
        assert "read" in result.stdout

    def test_shows_troubleshooting(self):
        """bash: Troubleshooting section."""
        result = runner.invoke(app, ["--robot-help"])
        assert "Troubleshooting" in result.stdout


# ===========================================================================
# 6. Session name derivation (exact match with bash)
# ===========================================================================


class TestSessionDerivationCompat:
    """Session name derivation must match bash logic exactly.

    bash: strip ansible-/infra- prefix, add cca- prefix.
    """

    def test_basic_directory(self):
        """basename(myproject) -> cca-myproject."""
        assert derive_session_name(Path("/path/to/myproject")) == "cca-myproject"

    def test_strip_ansible_prefix(self):
        """basename(ansible-example) -> cca-example."""
        assert derive_session_name(Path("/path/to/ansible-example")) == "cca-example"

    def test_strip_infra_prefix(self):
        """basename(infra-production) -> cca-production."""
        assert derive_session_name(Path("/path/to/infra-production")) == "cca-production"

    def test_no_double_strip(self):
        """cca- prefix is NOT stripped (not in bash logic)."""
        assert derive_session_name(Path("/path/to/cca-myproject")) == "cca-cca-myproject"

    def test_nested_path(self):
        """Only the final directory name matters."""
        assert derive_session_name(Path("/a/b/c/deep-project")) == "cca-deep-project"


# ===========================================================================
# 7. Config loading (backward compat with bash)
# ===========================================================================


class TestConfigLoadingCompat:
    """Config loading must match bash behavior: recursive, priority order."""

    def test_bash_env_file_loading(self, tmp_path: Path):
        """bash: source .cca-tmux-cli sets TMUX_SESSION_NAME, TMUX_SESSION_SERVERS."""
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text(
            textwrap.dedent("""\
            # CCA Tmux CLI Configuration
            TMUX_SESSION_NAME=cca-myproject
            TMUX_SESSION_SERVERS="web1 web2 db1"
            CCA_LOGGING=false
        """)
        )

        cfg = load_bash_env_config(env_file)
        assert cfg.session.name == "cca-myproject"
        assert cfg.session.servers == ["web1", "web2", "db1"]
        assert cfg.logging.enabled is False

    def test_yaml_overrides_bash_env(self, tmp_path: Path):
        """Python adds YAML config with higher priority."""
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text("session:\n  name: yaml-session\n")

        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text("TMUX_SESSION_NAME=bash-session\n")

        cfg = load_config(start_dir=tmp_path)
        assert cfg.session.name == "yaml-session"

    def test_recursive_search_up_to_root(self, tmp_path: Path):
        """bash: loads from current dir up to root, stopping at first match."""
        # Config in parent dir
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text("TMUX_SESSION_NAME=from-parent\n")

        # Search from child dir
        child_dir = tmp_path / "subdir" / "nested"
        child_dir.mkdir(parents=True)

        cfg = load_config(start_dir=child_dir)
        assert cfg.session.name == "from-parent"

    def test_general_env_fallback(self, tmp_path: Path):
        """bash: .env is loaded if .cca-tmux-cli not found."""
        env_file = tmp_path / ".env"
        env_file.write_text("TMUX_SESSION_NAME=from-dotenv\n")

        cfg = load_config(start_dir=tmp_path)
        assert cfg.session.name == "from-dotenv"

    def test_no_config_returns_defaults(self, tmp_path: Path):
        """When no config files exist, defaults are used (no error)."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        cfg = load_config(start_dir=empty_dir)
        assert cfg.session.name == ""
        assert cfg.session.servers == []
        assert cfg.config_path is None


# ===========================================================================
# 8. Audit query subcommand (new in Python)
# ===========================================================================


class TestAuditQueryCompat:
    """audit query — new Python command, must work as specified in spec."""

    def test_audit_query_today(self):
        """tmux-cli-python audit query --today."""
        result = runner.invoke(app, ["audit", "query", "--today"])
        assert result.exit_code == 0

    def test_audit_query_server_filter(self, tmp_path: Path, monkeypatch):
        """tmux-cli-python audit query --server web1."""
        import json

        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text("session:\n  name: cca-test\naudit:\n  enabled: true\n  dir: logs\n")

        log_dir = config_dir / "logs"
        log_dir.mkdir(parents=True)
        from datetime import datetime, timezone

        today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file = log_dir / f"audit-{today_str}.jsonl"
        log_file.write_text(
            json.dumps({"ts": "ok", "server": "web1", "action": "run"})
            + "\n"
            + json.dumps({"ts": "ok", "server": "web2", "action": "run"})
            + "\n"
        )

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["audit", "query", "--server", "web1"])
        assert result.exit_code == 0
        lines = [line for line in result.stdout.strip().splitlines() if line.startswith("{")]
        assert len(lines) == 1

    def test_audit_query_disabled_errors(self, tmp_path: Path, monkeypatch):
        """audit query when disabled should error."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / ".tmux-cli-python.yaml"
        config_file.write_text("session:\n  name: cca-test\naudit:\n  enabled: false\n")

        monkeypatch.chdir(config_dir)
        result = runner.invoke(app, ["audit", "query", "--today"])
        assert result.exit_code == 1


# ===========================================================================
# 9. Help text mentions all expected subcommands
# ===========================================================================


class TestHelpTextCompat:
    """Help output should list all subcommands from bash."""

    def test_help_lists_list(self):
        result = runner.invoke(app, ["--help"])
        assert "list" in result.stdout.lower()

    def test_help_lists_run(self):
        result = runner.invoke(app, ["--help"])
        assert "run" in result.stdout.lower()

    def test_help_lists_read(self):
        result = runner.invoke(app, ["--help"])
        assert "read" in result.stdout.lower()

    def test_help_lists_session(self):
        result = runner.invoke(app, ["--help"])
        assert "session" in result.stdout.lower()


# ===========================================================================
# 10. Combined flags + subcommand — full invocations
# ===========================================================================


class TestCombinedInvocations:
    """Verify flag combinations work as they do in bash."""

    def test_target_and_session_with_list(self):
        """cca-tmux-cli -t web1 -s cca-test list."""
        result = runner.invoke(app, ["-t", "web1", "-s", "cca-test", "list"])
        assert result.exit_code == 0
        assert "cca-test" in result.output

    def test_target_and_session_with_run(self):
        """cca-tmux-cli -t web1 -s cca-test run "uptime"."""
        result = runner.invoke(app, ["-t", "web1", "-s", "cca-test", "run", "uptime"])
        assert result.exit_code == 0
        assert "uptime" in result.output

    def test_target_and_session_with_read(self):
        """cca-tmux-cli -t web1 -s cca-test read."""
        result = runner.invoke(app, ["-t", "web1", "-s", "cca-test", "read"])
        assert result.exit_code == 0

    def test_unknown_subcommand_errors(self):
        """bash: Unknown subcommand -> error."""
        result = runner.invoke(app, ["nonexistent"])
        assert result.exit_code != 0
