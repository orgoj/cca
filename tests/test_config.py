"""Tests for tmux_cli_python.config — config loader, schema, and derivation."""

import textwrap
from pathlib import Path

from tmux_cli_python.config import (
    ConfirmationConfig,
    SessionConfig,
    _parse_env_file,
    derive_session_name,
    load_bash_env_config,
    load_config,
    load_yaml_config,
    resolve_agent,
)

# ---------------------------------------------------------------------------
# SessionConfig tests
# ---------------------------------------------------------------------------


class TestSessionConfig:
    def test_defaults(self):
        cfg = SessionConfig()
        assert cfg.name == ""
        assert cfg.servers == []


# ---------------------------------------------------------------------------
# ConfirmationConfig tests
# ---------------------------------------------------------------------------


class TestConfirmationConfig:
    def test_defaults(self):
        cfg = ConfirmationConfig()
        assert cfg.cmd == ""

    def test_format_message(self):
        cfg = ConfirmationConfig(cmd="zenity --question --text '{message}'")
        result = cfg.format_message("Destructive command")
        assert result == "zenity --question --text 'Destructive command'"

    def test_format_message_no_placeholder(self):
        cfg = ConfirmationConfig(cmd="echo ok")
        result = cfg.format_message("anything")
        assert result == "echo ok"


# ---------------------------------------------------------------------------
# YAML config loader tests
# ---------------------------------------------------------------------------


class TestLoadYamlConfig:
    def test_full_config(self, tmp_path: Path):
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-testproject
              servers: "web1 web2 db1"

            validation:
              enabled: true
              hooks:
                - "dippy --cmd-stdin --json --remote"
              confirmation:
                cmd: "zenity --question --text '{message}'"

            redaction:
              enabled: true
              hooks:
                - "secretctl sanitize"
              confirmation:
                cmd: "zenity --question --text '{message}'"

            audit:
              enabled: true
              dir: logs

            logging:
              enabled: false
              admin_name: ""
        """)
        )

        cfg = load_yaml_config(yaml_file)
        assert cfg.session.name == "cca-testproject"
        assert cfg.session.servers == ["web1", "web2", "db1"]
        assert cfg.validation.enabled is True
        assert cfg.validation.hooks == ["dippy --cmd-stdin --json --remote"]
        assert cfg.validation.confirmation.cmd == "zenity --question --text '{message}'"
        assert cfg.redaction.enabled is True
        assert cfg.redaction.hooks == ["secretctl sanitize"]
        assert cfg.audit.enabled is True
        assert cfg.audit.dir == "logs"
        assert cfg.logging.enabled is False
        assert cfg.config_path == str(yaml_file)

    def test_minimal_config(self, tmp_path: Path):
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text("session:\n  name: cca-minimal\n")

        cfg = load_yaml_config(yaml_file)
        assert cfg.session.name == "cca-minimal"
        assert cfg.session.servers == []
        assert cfg.validation.enabled is False
        assert cfg.redaction.enabled is False
        assert cfg.audit.enabled is True  # default

    def test_empty_file(self, tmp_path: Path):
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text("")

        cfg = load_yaml_config(yaml_file)
        assert cfg.session.name == ""
        assert cfg.session.servers == []

    def test_servers_as_list(self, tmp_path: Path):
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            session:
              servers:
                - web1
                - web2
        """)
        )

        cfg = load_yaml_config(yaml_file)
        assert cfg.session.servers == ["web1", "web2"]


# ---------------------------------------------------------------------------
# Bash env loader tests
# ---------------------------------------------------------------------------


class TestLoadBashEnvConfig:
    def test_full_env(self, tmp_path: Path):
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text(
            textwrap.dedent("""\
            # CCA Tmux CLI Configuration
            TMUX_SESSION_NAME=cca-myproject
            TMUX_SESSION_SERVERS="web1 web2 db1"
            CCA_LOGGING=true
            ADMIN_NAME=agent
        """)
        )

        cfg = load_bash_env_config(env_file)
        assert cfg.session.name == "cca-myproject"
        assert cfg.session.servers == ["web1", "web2", "db1"]
        assert cfg.logging.enabled is True
        assert cfg.logging.admin_name == "agent"

    def test_minimal_env(self, tmp_path: Path):
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text("TMUX_SESSION_NAME=cca-simple\n")

        cfg = load_bash_env_config(env_file)
        assert cfg.session.name == "cca-simple"
        assert cfg.session.servers == []
        assert cfg.logging.enabled is False

    def test_export_prefix(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("export TMUX_SESSION_NAME=cca-exported\n")

        cfg = load_bash_env_config(env_file)
        assert cfg.session.name == "cca-exported"

    def test_single_quoted_values(self, tmp_path: Path):
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text("TMUX_SESSION_NAME='cca-quoted'\n")

        cfg = load_bash_env_config(env_file)
        assert cfg.session.name == "cca-quoted"

    def test_servers_without_quotes(self, tmp_path: Path):
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text("TMUX_SESSION_SERVERS=web1 web2\n")

        cfg = load_bash_env_config(env_file)
        assert cfg.session.servers == ["web1", "web2"]


# ---------------------------------------------------------------------------
# _parse_env_file tests
# ---------------------------------------------------------------------------


class TestParseEnvFile:
    def test_skips_comments_and_blanks(self, tmp_path: Path):
        f = tmp_path / "test.env"
        f.write_text(
            textwrap.dedent("""\
            # Comment
            KEY1=val1

            KEY2=val2
            # Another comment
        """)
        )
        result = _parse_env_file(f)
        assert result == {"KEY1": "val1", "KEY2": "val2"}

    def test_quoted_values(self, tmp_path: Path):
        f = tmp_path / "test.env"
        f.write_text('KEY="hello world"\n')
        result = _parse_env_file(f)
        assert result == {"KEY": "hello world"}

    def test_single_quoted_values(self, tmp_path: Path):
        f = tmp_path / "test.env"
        f.write_text("KEY='hello world'\n")
        result = _parse_env_file(f)
        assert result == {"KEY": "hello world"}


# ---------------------------------------------------------------------------
# load_config tests (recursive search + priority)
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_yaml_priority_over_bash_env(self, tmp_path: Path):
        # Both files exist in same dir — YAML wins
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text("session:\n  name: yaml-wins\n")

        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text("TMUX_SESSION_NAME=bash-loses\n")

        cfg = load_config(start_dir=tmp_path)
        assert cfg.session.name == "yaml-wins"

    def test_bash_env_when_no_yaml(self, tmp_path: Path):
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text("TMUX_SESSION_NAME=from-bash\n")

        cfg = load_config(start_dir=tmp_path)
        assert cfg.session.name == "from-bash"

    def test_general_env_fallback(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("TMUX_SESSION_NAME=from-dotenv\n")

        cfg = load_config(start_dir=tmp_path)
        assert cfg.session.name == "from-dotenv"

    def test_cca_env_when_no_bash_env(self, tmp_path: Path):
        env_file = tmp_path / ".cca-env"
        env_file.write_text("TMUX_SESSION_NAME=from-cca-env\n")

        cfg = load_config(start_dir=tmp_path)
        assert cfg.session.name == "from-cca-env"

    def test_cca_env_priority_over_dotenv(self, tmp_path: Path):
        (tmp_path / ".cca-env").write_text("TMUX_SESSION_NAME=cca-env-wins\n")
        (tmp_path / ".env").write_text("TMUX_SESSION_NAME=dotenv-loses\n")

        cfg = load_config(start_dir=tmp_path)
        assert cfg.session.name == "cca-env-wins"

    def test_bash_env_priority_over_cca_env(self, tmp_path: Path):
        (tmp_path / ".cca-tmux-cli").write_text("TMUX_SESSION_NAME=tmux-cli-wins\n")
        (tmp_path / ".cca-env").write_text("TMUX_SESSION_NAME=cca-env-loses\n")

        cfg = load_config(start_dir=tmp_path)
        assert cfg.session.name == "tmux-cli-wins"

    def test_cca_env_in_parent_wins_over_dotenv_in_child(self, tmp_path: Path):
        # Lower-priority .env in child must not stop the search for .cca-env higher up
        (tmp_path / ".cca-env").write_text("TMUX_SESSION_NAME=from-parent-cca-env\n")

        child_dir = tmp_path / "subdir"
        child_dir.mkdir()
        (child_dir / ".env").write_text("TMUX_SESSION_NAME=from-child-dotenv\n")

        cfg = load_config(start_dir=child_dir)
        assert cfg.session.name == "from-parent-cca-env"

    def test_no_config_returns_defaults(self, tmp_path: Path):
        # Use a fresh tmp dir with no config files
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        cfg = load_config(start_dir=empty_dir)
        assert cfg.session.name == ""
        assert cfg.session.servers == []
        assert cfg.config_path is None

    def test_recursive_search_finds_parent_config(self, tmp_path: Path):
        # Config is in parent dir, search from child
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text("TMUX_SESSION_NAME=from-parent\n")

        child_dir = tmp_path / "subdir"
        child_dir.mkdir()

        cfg = load_config(start_dir=child_dir)
        assert cfg.session.name == "from-parent"


# ---------------------------------------------------------------------------
# derive_session_name tests
# ---------------------------------------------------------------------------


class TestDeriveSessionName:
    def test_basic(self):
        result = derive_session_name(Path("/path/to/myproject"))
        assert result == "cca-myproject"

    def test_strip_ansible_prefix(self):
        result = derive_session_name(Path("/path/to/ansible-example"))
        assert result == "cca-example"

    def test_strip_infra_prefix(self):
        result = derive_session_name(Path("/path/to/infra-production"))
        assert result == "cca-production"

    def test_no_double_prefix(self):
        result = derive_session_name(Path("/path/to/cca-myproject"))
        assert result == "cca-cca-myproject"  # Only strips known prefixes


# ---------------------------------------------------------------------------
# AuditConfig.agent tests
# ---------------------------------------------------------------------------


class TestAuditConfigAgent:
    def test_yaml_audit_agent(self, tmp_path: Path):
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
            audit:
              enabled: true
              dir: logs
              agent: hermes
        """)
        )

        cfg = load_yaml_config(yaml_file)
        assert cfg.audit.agent == "hermes"

    def test_yaml_audit_agent_default_empty(self, tmp_path: Path):
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
            audit:
              enabled: true
              dir: logs
        """)
        )

        cfg = load_yaml_config(yaml_file)
        assert cfg.audit.agent == ""

    def test_bash_env_cca_agent(self, tmp_path: Path):
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text(
            textwrap.dedent("""\
            TMUX_SESSION_NAME=cca-test
            CCA_AGENT=athena
        """)
        )

        cfg = load_bash_env_config(env_file)
        assert cfg.audit.agent == "athena"

    def test_bash_env_no_agent(self, tmp_path: Path):
        env_file = tmp_path / ".cca-tmux-cli"
        env_file.write_text("TMUX_SESSION_NAME=cca-test\n")

        cfg = load_bash_env_config(env_file)
        assert cfg.audit.agent == ""


# ---------------------------------------------------------------------------
# resolve_agent tests
# ---------------------------------------------------------------------------


class TestResolveAgent:
    def test_config_agent_takes_priority(self, tmp_path: Path):
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
            audit:
              agent: hermes
        """)
        )

        cfg = load_yaml_config(yaml_file)
        assert resolve_agent(cfg) == "hermes"

    def test_env_var_fallback(self, monkeypatch):
        from tmux_cli_python.config import AppConfig, AuditConfig

        cfg = AppConfig(audit=AuditConfig(agent=""))
        monkeypatch.setenv("CCA_AGENT", "athena")
        assert resolve_agent(cfg) == "athena"

    def test_config_overrides_env_var(self, monkeypatch):
        from tmux_cli_python.config import AppConfig, AuditConfig

        cfg = AppConfig(audit=AuditConfig(agent="hermes"))
        monkeypatch.setenv("CCA_AGENT", "athena")
        assert resolve_agent(cfg) == "hermes"

    def test_empty_when_no_source(self, monkeypatch):
        from tmux_cli_python.config import AppConfig, AuditConfig

        cfg = AppConfig(audit=AuditConfig(agent=""))
        monkeypatch.delenv("CCA_AGENT", raising=False)
        assert resolve_agent(cfg) == ""
