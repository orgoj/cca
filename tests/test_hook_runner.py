"""Tests for the hook runner module (hooks.py).

Tests the actual hook pipeline execution:
- run_validation_hooks() — iterate hooks, pipe command to stdin, handle exit codes
- run_redaction_hooks() — iterate hooks, pipe output to stdin, collect stdout
- run_confirmation() — invoke confirmation command when hook returns exit 2
- Pipeline chaining (redaction output feeds into next hook)
- Error handling (timeout, command not found)
"""

from __future__ import annotations

import stat
from pathlib import Path

from tmux_cli_python.config import ConfirmationConfig, HookPipelineConfig
from tmux_cli_python.hooks import (
    HookAction,
    HookResult,
    PipelineResult,
    run_confirmation,
    run_redaction_hooks,
    run_validation_hooks,
)

# ---------------------------------------------------------------------------
# Validation pipeline tests
# ---------------------------------------------------------------------------


class TestValidationPipeline:
    """Test run_validation_hooks()."""

    def test_disabled_pipeline_approves(self):
        """Disabled pipeline approves everything."""
        config = HookPipelineConfig(enabled=False)
        result = run_validation_hooks("rm -rf /", config)
        assert result.allowed is True
        assert result.results == []

    def test_empty_hooks_approves(self):
        """Enabled pipeline with no hooks approves."""
        config = HookPipelineConfig(enabled=True, hooks=[])
        result = run_validation_hooks("anything", config)
        assert result.allowed is True

    def test_single_hook_approves(self, tmp_path: Path):
        """Single hook that exits 0 approves."""
        hook = tmp_path / "approve.sh"
        hook.write_text("#!/bin/bash\nexit 0\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook)])
        result = run_validation_hooks("uptime", config)
        assert result.allowed is True
        assert len(result.results) == 1
        assert result.results[0].action == HookAction.APPROVED

    def test_single_hook_denies(self, tmp_path: Path):
        """Single hook that exits 1 denies with reason."""
        hook = tmp_path / "deny.sh"
        hook.write_text("#!/bin/bash\necho 'Destructive command' >&2\nexit 1\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook)])
        result = run_validation_hooks("rm -rf /", config)
        assert result.allowed is False
        assert "Destructive command" in result.reason
        assert result.results[0].action == HookAction.DENIED

    def test_multiple_hooks_all_approve(self, tmp_path: Path):
        """Multiple hooks that all exit 0 all approve."""
        hook1 = tmp_path / "hook1.sh"
        hook1.write_text("#!/bin/bash\nexit 0\n")
        hook1.chmod(hook1.stat().st_mode | stat.S_IEXEC)

        hook2 = tmp_path / "hook2.sh"
        hook2.write_text("#!/bin/bash\nexit 0\n")
        hook2.chmod(hook2.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook1), str(hook2)])
        result = run_validation_hooks("uptime", config)
        assert result.allowed is True
        assert len(result.results) == 2

    def test_second_hook_denies(self, tmp_path: Path):
        """If first approves but second denies, pipeline stops."""
        hook1 = tmp_path / "approve.sh"
        hook1.write_text("#!/bin/bash\nexit 0\n")
        hook1.chmod(hook1.stat().st_mode | stat.S_IEXEC)

        hook2 = tmp_path / "deny.sh"
        hook2.write_text("#!/bin/bash\necho 'Second check failed' >&2\nexit 1\n")
        hook2.chmod(hook2.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook1), str(hook2)])
        result = run_validation_hooks("some command", config)
        assert result.allowed is False
        assert "Second check failed" in result.reason
        assert len(result.results) == 2  # first approved, second denied

    def test_hook_receives_command_via_stdin(self, tmp_path: Path):
        """Hook receives the command string via stdin."""
        output_file = tmp_path / "received.txt"
        hook = tmp_path / "check.sh"
        hook.write_text(f"#!/bin/bash\ncat > {output_file}\nexit 0\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook)])
        run_validation_hooks("uptime -a", config)
        assert output_file.read_text() == "uptime -a"


class TestValidationAskUser:
    """Test validation hook exit 2 (ask user) flow."""

    def test_ask_user_approved(self, tmp_path: Path):
        """Hook returns exit 2, user approves via confirmation."""
        hook = tmp_path / "ask.sh"
        hook.write_text("#!/bin/bash\necho 'Suspicious command' >&2\nexit 2\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        confirm = tmp_path / "confirm.sh"
        confirm.write_text("#!/bin/bash\nexit 0\n")  # approve
        confirm.chmod(confirm.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(
            enabled=True,
            hooks=[str(hook)],
            confirmation=ConfirmationConfig(cmd=str(confirm)),
        )
        result = run_validation_hooks("reboot", config)
        assert result.allowed is True
        # Should have: hook ask, confirmation approved
        actions = [r.action for r in result.results]
        assert HookAction.ASK_USER in actions
        assert HookAction.APPROVED in actions

    def test_ask_user_denied(self, tmp_path: Path):
        """Hook returns exit 2, user denies via confirmation."""
        hook = tmp_path / "ask.sh"
        hook.write_text("#!/bin/bash\nexit 2\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        confirm = tmp_path / "confirm.sh"
        confirm.write_text("#!/bin/bash\nexit 1\n")  # deny
        confirm.chmod(confirm.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(
            enabled=True,
            hooks=[str(hook)],
            confirmation=ConfirmationConfig(cmd=str(confirm)),
        )
        result = run_validation_hooks("reboot", config)
        assert result.allowed is False

    def test_ask_user_no_confirmation_config_denies(self, tmp_path: Path):
        """Hook returns exit 2, but no confirmation command — deny."""
        hook = tmp_path / "ask.sh"
        hook.write_text("#!/bin/bash\nexit 2\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(
            enabled=True,
            hooks=[str(hook)],
            confirmation=ConfirmationConfig(cmd=""),  # empty
        )
        result = run_validation_hooks("reboot", config)
        assert result.allowed is False


# ---------------------------------------------------------------------------
# Redaction pipeline tests
# ---------------------------------------------------------------------------


class TestRedactionPipeline:
    """Test run_redaction_hooks()."""

    def test_disabled_pipeline_passes_through(self):
        """Disabled pipeline passes output through unchanged."""
        config = HookPipelineConfig(enabled=False)
        result = run_redaction_hooks("secret data", config)
        assert result.allowed is True
        assert result.output == "secret data"

    def test_empty_hooks_passes_through(self):
        """Enabled but empty hooks passes output through."""
        config = HookPipelineConfig(enabled=True, hooks=[])
        result = run_redaction_hooks("some output", config)
        assert result.allowed is True
        assert result.output == "some output"

    def test_single_hook_passes(self, tmp_path: Path):
        """Single hook that redacts and exits 0."""
        hook = tmp_path / "redact.sh"
        hook.write_text("#!/bin/bash\nsed 's/sk-[a-zA-Z0-9]*/[REDACTED]/g'\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook)])
        result = run_redaction_hooks("API_KEY=sk-abc123\nhostname=web1", config)
        assert result.allowed is True
        assert "[REDACTED]" in result.output
        assert "hostname=web1" in result.output
        assert "sk-abc123" not in result.output

    def test_single_hook_blocks(self, tmp_path: Path):
        """Single hook that exits 1 blocks output."""
        hook = tmp_path / "block.sh"
        hook.write_text("#!/bin/bash\necho 'Contains sensitive data' >&2\nexit 1\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook)])
        result = run_redaction_hooks("some output", config)
        assert result.allowed is False
        assert result.output == ""
        assert "sensitive" in result.reason.lower()

    def test_chained_hooks(self, tmp_path: Path):
        """Multiple redaction hooks chain: output of hook1 feeds into hook2."""
        hook1 = tmp_path / "redact_keys.sh"
        hook1.write_text("#!/bin/bash\nsed 's/sk-[a-zA-Z0-9]*/[KEY_REDACTED]/g'\n")
        hook1.chmod(hook1.stat().st_mode | stat.S_IEXEC)

        hook2 = tmp_path / "redact_tokens.sh"
        hook2.write_text("#!/bin/bash\nsed 's/token-[a-zA-Z0-9]*/[TOKEN_REDACTED]/g'\n")
        hook2.chmod(hook2.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook1), str(hook2)])
        raw = "key=sk-abc123 token=token-xyz789 host=web1"
        result = run_redaction_hooks(raw, config)
        assert result.allowed is True
        assert "[KEY_REDACTED]" in result.output
        assert "[TOKEN_REDACTED]" in result.output
        assert "host=web1" in result.output

    def test_hook_receives_output_via_stdin(self, tmp_path: Path):
        """Redaction hook receives text via stdin."""
        output_file = tmp_path / "received.txt"
        hook = tmp_path / "passthrough.sh"
        hook.write_text(f"#!/bin/bash\ntee {output_file}\nexit 0\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook)])
        run_redaction_hooks("raw output text", config)
        assert output_file.read_text() == "raw output text"

    def test_second_hook_blocks(self, tmp_path: Path):
        """First hook passes, second blocks."""
        hook1 = tmp_path / "pass.sh"
        hook1.write_text("#!/bin/bash\ncat\nexit 0\n")
        hook1.chmod(hook1.stat().st_mode | stat.S_IEXEC)

        hook2 = tmp_path / "block.sh"
        hook2.write_text("#!/bin/bash\necho 'Still contains secrets' >&2\nexit 1\n")
        hook2.chmod(hook2.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook1), str(hook2)])
        result = run_redaction_hooks("output", config)
        assert result.allowed is False


# ---------------------------------------------------------------------------
# Confirmation handler tests
# ---------------------------------------------------------------------------


class TestRunConfirmation:
    """Test run_confirmation()."""

    def test_confirmation_approves(self, tmp_path: Path):
        """Confirmation command exits 0 — approved."""
        confirm = tmp_path / "confirm.sh"
        confirm.write_text("#!/bin/bash\nexit 0\n")
        confirm.chmod(confirm.stat().st_mode | stat.S_IEXEC)

        cfg = ConfirmationConfig(cmd=str(confirm))
        assert run_confirmation(cfg, "Test message") is True

    def test_confirmation_denies(self, tmp_path: Path):
        """Confirmation command exits 1 — denied."""
        confirm = tmp_path / "deny.sh"
        confirm.write_text("#!/bin/bash\nexit 1\n")
        confirm.chmod(confirm.stat().st_mode | stat.S_IEXEC)

        cfg = ConfirmationConfig(cmd=str(confirm))
        assert run_confirmation(cfg, "Test message") is False

    def test_empty_command_denies(self):
        """Empty confirmation command defaults to deny."""
        cfg = ConfirmationConfig(cmd="")
        assert run_confirmation(cfg, "Test message") is False

    def test_message_placeholder_replaced(self, tmp_path: Path):
        """Confirmation command has {message} replaced."""
        output_file = tmp_path / "msg.txt"
        confirm = tmp_path / "confirm.sh"
        confirm.write_text(f'#!/bin/bash\necho "$@" > {output_file}\nexit 0\n')
        confirm.chmod(confirm.stat().st_mode | stat.S_IEXEC)

        cfg = ConfirmationConfig(cmd=f"{confirm} '{{message}}'")
        run_confirmation(cfg, "Dangerous!")
        # The message should be passed through
        assert output_file.exists()

    def test_nonexistent_command_denies(self):
        """Non-existent confirmation command defaults to deny."""
        cfg = ConfirmationConfig(cmd="/nonexistent/command")
        assert run_confirmation(cfg, "Test") is False


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestHookErrors:
    """Test error handling in hook execution."""

    def test_hook_timeout(self):
        """Hook that exceeds timeout is treated as deny."""
        config = HookPipelineConfig(
            enabled=True,
            hooks=["sleep 60"],
        )
        result = run_validation_hooks("uptime", config, timeout=1)
        assert result.allowed is False
        assert "timed out" in result.reason.lower()

    def test_nonexistent_hook_command(self):
        """Hook command not found is treated as deny."""
        config = HookPipelineConfig(
            enabled=True,
            hooks=["/nonexistent/hook/command"],
        )
        result = run_validation_hooks("uptime", config)
        assert result.allowed is False

    def test_unexpected_exit_code_treated_as_deny(self, tmp_path: Path):
        """Hook returning unexpected exit code (e.g. 3) is treated as deny."""
        hook = tmp_path / "weird.sh"
        hook.write_text("#!/bin/bash\nexit 3\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        config = HookPipelineConfig(enabled=True, hooks=[str(hook)])
        result = run_validation_hooks("uptime", config)
        assert result.allowed is False
        assert "unexpected exit code" in result.reason.lower()


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestHookResultDataclass:
    """Test HookResult dataclass."""

    def test_basic_result(self):
        r = HookResult(hook="test-hook", action=HookAction.APPROVED)
        assert r.hook == "test-hook"
        assert r.action == HookAction.APPROVED
        assert r.reason == ""

    def test_denied_result_with_reason(self):
        r = HookResult(hook="test", action=HookAction.DENIED, reason="bad command")
        assert r.reason == "bad command"


class TestPipelineResultDataclass:
    """Test PipelineResult dataclass."""

    def test_approved_result(self):
        r = PipelineResult(allowed=True)
        assert r.allowed is True
        assert r.results == []
        assert r.reason == ""
        assert r.output == ""

    def test_denied_result_with_details(self):
        r = PipelineResult(
            allowed=False,
            results=[HookResult(hook="h", action=HookAction.DENIED, reason="nope")],
            reason="nope",
        )
        assert r.allowed is False
        assert len(r.results) == 1
