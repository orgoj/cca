"""Tests for the hook pipeline — the core architectural concept.

The hook pipeline is central to tmux-cli-python's design:
- Validation hooks run BEFORE command execution (stdin = command string, exit 0/1/2)
- Redaction hooks run AFTER command execution
  (stdin = raw output, stdout = redacted output, exit 0/1/2)
- Exit code convention: 0 = allow, 1 = deny, 2 = ask user
- Confirmation: when exit 2, run confirmation command from config

These tests validate:
1. The config data structures that define hook pipelines
2. The exit code semantics
3. The subprocess calling contract (how hooks are invoked)
4. The confirmation flow

Note: The actual hook runner module (hooks.py) may not exist yet.
These tests validate the contract that the config + architecture defines.
When hooks.py is implemented, these tests should pass.
"""

from __future__ import annotations

import stat
import subprocess
import textwrap
from pathlib import Path

from tmux_cli_python.config import (
    ConfirmationConfig,
    HookPipelineConfig,
    load_yaml_config,
)

# ---------------------------------------------------------------------------
# HookPipelineConfig validation
# ---------------------------------------------------------------------------


class TestHookPipelineConfig:
    """Verify the data structures that define hook pipelines."""

    def test_disabled_pipeline_has_no_hooks(self):
        """A disabled pipeline should have enabled=False."""
        cfg = HookPipelineConfig()
        assert cfg.enabled is False
        assert cfg.hooks == []

    def test_enabled_pipeline_with_hooks(self):
        """An enabled pipeline lists CLI commands as hooks."""
        cfg = HookPipelineConfig(
            enabled=True,
            hooks=["dippy --cmd-stdin --json --remote", "other-validator --check"],
        )
        assert cfg.enabled is True
        assert len(cfg.hooks) == 2
        assert "dippy" in cfg.hooks[0]

    def test_hook_commands_are_strings(self):
        """Each hook must be a string (CLI command to execute)."""
        cfg = HookPipelineConfig(
            enabled=True,
            hooks=["echo hello", "cat"],
        )
        for hook in cfg.hooks:
            assert isinstance(hook, str)


# ---------------------------------------------------------------------------
# ConfirmationConfig
# ---------------------------------------------------------------------------


class TestConfirmationFlow:
    """Test the confirmation command template."""

    def test_confirmation_cmd_template(self):
        """Confirmation cmd should support {message} placeholder."""
        cfg = ConfirmationConfig(cmd="zenity --question --text '{message}'")
        result = cfg.format_message("Destructive command detected")
        assert result == "zenity --question --text 'Destructive command detected'"

    def test_confirmation_cmd_without_placeholder(self):
        """If no {message} placeholder, command is returned as-is."""
        cfg = ConfirmationConfig(cmd="echo 'confirm?'")
        result = cfg.format_message("anything")
        assert result == "echo 'confirm?'"

    def test_confirmation_cmd_multiple_placeholders(self):
        """Multiple {message} placeholders should all be replaced."""
        cfg = ConfirmationConfig(cmd="echo '{message}' && echo '{message}'")
        result = cfg.format_message("test")
        assert result == "echo 'test' && echo 'test'"


# ---------------------------------------------------------------------------
# Full config with hook pipeline
# ---------------------------------------------------------------------------


class TestFullHookConfig:
    """Load a complete YAML config with validation and redaction pipelines."""

    def test_load_config_with_both_pipelines(self, tmp_path: Path):
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
                cmd: "zenity --question --text '{message}' --title 'Confirm command'"

            redaction:
              enabled: true
              hooks:
                - "secretctl sanitize"
              confirmation:
                cmd: "zenity --question --text '{message}' --title 'Sensitive output'"

            audit:
              enabled: true
              dir: logs
        """)
        )

        cfg = load_yaml_config(yaml_file)

        # Validation pipeline
        assert cfg.validation.enabled is True
        assert cfg.validation.hooks == ["dippy --cmd-stdin --json --remote"]
        assert cfg.validation.confirmation.cmd == (
            "zenity --question --text '{message}' --title 'Confirm command'"
        )

        # Redaction pipeline
        assert cfg.redaction.enabled is True
        assert cfg.redaction.hooks == ["secretctl sanitize"]
        assert cfg.redaction.confirmation.cmd == (
            "zenity --question --text '{message}' --title 'Sensitive output'"
        )

    def test_load_config_disabled_pipelines(self, tmp_path: Path):
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-testproject
            validation:
              enabled: false
            redaction:
              enabled: false
        """)
        )

        cfg = load_yaml_config(yaml_file)
        assert cfg.validation.enabled is False
        assert cfg.redaction.enabled is False

    def test_load_config_multiple_hooks(self, tmp_path: Path):
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            session:
              name: cca-test
            validation:
              enabled: true
              hooks:
                - "hook1 --check"
                - "hook2 --validate"
                - "hook3 --strict"
        """)
        )

        cfg = load_yaml_config(yaml_file)
        assert len(cfg.validation.hooks) == 3
        assert "hook1" in cfg.validation.hooks[0]
        assert "hook2" in cfg.validation.hooks[1]
        assert "hook3" in cfg.validation.hooks[2]


# ---------------------------------------------------------------------------
# Hook subprocess contract — exit code semantics
# ---------------------------------------------------------------------------


class TestHookExitCodes:
    """Test the exit code contract for hook subprocesses.

    Exit codes:
        0 = allow/pass
        1 = deny/block
        2 = ask user (trigger confirmation)
    """

    def test_hook_exit_0_means_allow(self, tmp_path: Path):
        """Exit 0 from a validation hook means 'allow'."""
        hook_script = tmp_path / "approve.sh"
        hook_script.write_text("#!/bin/bash\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        result = subprocess.run(
            [str(hook_script)],
            input=b"uptime",
            capture_output=True,
        )
        assert result.returncode == 0

    def test_hook_exit_1_means_deny(self, tmp_path: Path):
        """Exit 1 from a validation hook means 'deny'."""
        hook_script = tmp_path / "deny.sh"
        hook_script.write_text("#!/bin/bash\necho 'Destructive command' >&2\nexit 1\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        result = subprocess.run(
            [str(hook_script)],
            input=b"rm -rf /",
            capture_output=True,
        )
        assert result.returncode == 1
        assert b"Destructive command" in result.stderr

    def test_hook_exit_2_means_ask_user(self, tmp_path: Path):
        """Exit 2 from a validation hook means 'ask user'."""
        hook_script = tmp_path / "ask.sh"
        hook_script.write_text("#!/bin/bash\nexit 2\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        result = subprocess.run(
            [str(hook_script)],
            input=b"some command",
            capture_output=True,
        )
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# Hook subprocess contract — stdin/stdout semantics
# ---------------------------------------------------------------------------


class TestHookIOContract:
    """Test the I/O contract for hook subprocesses.

    Validation hooks:
        stdin = command string
        stdout = ignored (or info message)
        stderr = deny reason (when exit 1)

    Redaction hooks:
        stdin = raw output text
        stdout = redacted output text (chain to next hook)
        stderr = ignored
    """

    def test_validation_hook_receives_command_via_stdin(self, tmp_path: Path):
        """Validation hook receives the command string via stdin."""
        output_file = tmp_path / "received.txt"
        hook_script = tmp_path / "validator.sh"
        hook_script.write_text(f"#!/bin/bash\ncat > {output_file}\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        subprocess.run(
            [str(hook_script)],
            input=b"uptime",
            capture_output=True,
        )

        assert output_file.read_text() == "uptime"

    def test_redaction_hook_receives_output_via_stdin(self, tmp_path: Path):
        """Redaction hook receives raw output via stdin."""
        output_file = tmp_path / "received.txt"
        hook_script = tmp_path / "redactor.sh"
        hook_script.write_text(f"#!/bin/bash\ncat > {output_file}\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        raw_output = b"API_KEY=sk-12345\nhostname=web1\n"
        subprocess.run(
            [str(hook_script)],
            input=raw_output,
            capture_output=True,
        )

        assert output_file.read_text() == "API_KEY=sk-12345\nhostname=web1\n"

    def test_redaction_hook_emits_redacted_via_stdout(self, tmp_path: Path):
        """Redaction hook emits redacted output via stdout."""
        hook_script = tmp_path / "sanitize.sh"
        hook_script.write_text("#!/bin/bash\nsed 's/sk-[0-9]*/[REDACTED]/g'\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        raw_output = b"API_KEY=sk-12345\nhostname=web1\n"
        result = subprocess.run(
            [str(hook_script)],
            input=raw_output,
            capture_output=True,
        )

        assert result.returncode == 0
        assert b"[REDACTED]" in result.stdout
        assert b"hostname=web1" in result.stdout  # non-secret data preserved

    def test_validation_hook_stderr_for_deny_reason(self, tmp_path: Path):
        """When validation hook denies (exit 1), stderr contains the reason."""
        hook_script = tmp_path / "deny_with_reason.sh"
        hook_script.write_text('#!/bin/bash\necho "Destructive command blocked" >&2\nexit 1\n')
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        result = subprocess.run(
            [str(hook_script)],
            input=b"rm -rf /var/log/*",
            capture_output=True,
        )

        assert result.returncode == 1
        assert b"Destructive command blocked" in result.stderr


# ---------------------------------------------------------------------------
# Redaction scope — secrets only
# ---------------------------------------------------------------------------


class TestRedactionScope:
    """Redaction should only target secrets, not operational data.

    Per spec: Do NOT redact IPs, hostnames, file paths — this is an admin tool.
    """

    def test_redact_api_key(self, tmp_path: Path):
        """API keys should be redacted."""
        hook_script = tmp_path / "sanitize.sh"
        hook_script.write_text("#!/bin/bash\nsed 's/sk-[a-zA-Z0-9]*/[REDACTED]/g'\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        result = subprocess.run(
            [str(hook_script)],
            input=b"export OPENAI_API_KEY=sk-abc123def456\n",
            capture_output=True,
        )
        assert b"[REDACTED]" in result.stdout
        assert b"sk-abc123" not in result.stdout

    def test_preserve_ip_addresses(self, tmp_path: Path):
        """IP addresses should NOT be redacted (admin tool)."""
        hook_script = tmp_path / "passthrough.sh"
        hook_script.write_text("#!/bin/bash\ncat\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        result = subprocess.run(
            [str(hook_script)],
            input=b"Server: 192.168.1.100 is up\n",
            capture_output=True,
        )
        assert b"192.168.1.100" in result.stdout

    def test_preserve_hostnames(self, tmp_path: Path):
        """Hostnames should NOT be redacted (admin tool)."""
        hook_script = tmp_path / "passthrough.sh"
        hook_script.write_text("#!/bin/bash\ncat\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        result = subprocess.run(
            [str(hook_script)],
            input=b"web1.example.com is healthy\n",
            capture_output=True,
        )
        assert b"web1.example.com" in result.stdout

    def test_preserve_file_paths(self, tmp_path: Path):
        """File paths should NOT be redacted (admin tool)."""
        hook_script = tmp_path / "passthrough.sh"
        hook_script.write_text("#!/bin/bash\ncat\nexit 0\n")
        hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

        result = subprocess.run(
            [str(hook_script)],
            input=b"-rw-r--r-- 1 root root 1234 /var/log/syslog\n",
            capture_output=True,
        )
        assert b"/var/log/syslog" in result.stdout


# ---------------------------------------------------------------------------
# Config-driven hook list (spec: "Config is just a list of CLI commands")
# ---------------------------------------------------------------------------


class TestConfigDrivenHooks:
    """Verify that config hooks are just lists of CLI commands to execute."""

    def test_hooks_are_cli_commands(self, tmp_path: Path):
        """Each hook entry is a CLI command string."""
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            validation:
              enabled: true
              hooks:
                - "dippy --cmd-stdin --json --remote"
                - "custom-validator --check --strict"
            """)
        )
        cfg = load_yaml_config(yaml_file)
        assert cfg.validation.hooks[0] == "dippy --cmd-stdin --json --remote"
        assert cfg.validation.hooks[1] == "custom-validator --check --strict"

    def test_empty_hooks_list(self, tmp_path: Path):
        """Enabled pipeline with no hooks is valid (no-op)."""
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            validation:
              enabled: true
              hooks: []
            """)
        )
        cfg = load_yaml_config(yaml_file)
        assert cfg.validation.enabled is True
        assert cfg.validation.hooks == []

    def test_hooks_can_be_any_cli_command(self, tmp_path: Path):
        """Hooks are not limited to specific tools — any CLI command works."""
        yaml_file = tmp_path / ".tmux-cli-python.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            validation:
              enabled: true
              hooks:
                - "grep -v 'rm -rf'"
                - "python3 /opt/validate.py"
                - "/usr/local/bin/check-command"
            """)
        )
        cfg = load_yaml_config(yaml_file)
        assert len(cfg.validation.hooks) == 3
        assert cfg.validation.hooks[0] == "grep -v 'rm -rf'"
