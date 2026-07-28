"""Hook pipeline runner — validation and redaction.

The hook pipeline is the core architectural concept of tmux-cli-python.
It reads lists of CLI commands from config and executes them sequentially
via subprocess, reacting to exit codes.

Exit code convention:
    0 = allow / pass
    1 = deny / block (stderr contains reason)
    2 = ask user (trigger confirmation command)

Validation hooks run BEFORE command execution:
    stdin  = command string
    stdout = ignored
    stderr = deny reason (when exit 1)

Redaction hooks run AFTER command execution:
    stdin  = raw output text
    stdout = redacted output text (chains to next hook)
    stderr = ignored

Confirmation: when a hook returns exit 2, the configured confirmation
command is invoked with {message} replaced by context.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum

from tmux_cli_python.config import ConfirmationConfig, HookPipelineConfig

logger = logging.getLogger("tmux_cli_python")

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class HookAction(str, Enum):
    """Result action from a single hook or pipeline run."""

    APPROVED = "approved"
    DENIED = "denied"
    BLOCKED = "blocked"
    ASK_USER = "ask"
    PASS = "pass"


@dataclass
class HookResult:
    """Result from a single hook execution."""

    hook: str
    action: str  # "approved", "denied", "ask"
    reason: str = ""


@dataclass
class PipelineResult:
    """Result from a complete hook pipeline run."""

    allowed: bool
    results: list[HookResult] = field(default_factory=list)
    reason: str = ""
    output: str = ""  # For redaction: the final (redacted) output


# ---------------------------------------------------------------------------
# Single hook execution
# ---------------------------------------------------------------------------


def _run_single_hook(
    hook_cmd: str,
    stdin_text: str,
    timeout: int = 30,
) -> tuple[int, str, str]:
    """Execute a single hook command as a subprocess.

    Args:
        hook_cmd: The CLI command to execute.
        stdin_text: Text to pipe to stdin.
        timeout: Timeout in seconds for the subprocess.

    Returns:
        Tuple of (exit_code, stdout, stderr).
    """
    logger.debug("running hook: %s", hook_cmd)
    try:
        result = subprocess.run(
            hook_cmd,
            shell=True,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        logger.debug("hook exited %d: %s", result.returncode, hook_cmd)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.debug("hook timed out (%ds): %s", timeout, hook_cmd)
        return 1, "", f"Hook timed out after {timeout}s: {hook_cmd}"
    except FileNotFoundError:
        logger.debug("hook not found: %s", hook_cmd)
        return 1, "", f"Hook command not found: {hook_cmd}"
    except OSError as exc:
        logger.debug("hook error: %s — %s", hook_cmd, exc)
        return 1, "", f"Hook execution error: {exc}"


# ---------------------------------------------------------------------------
# Confirmation handler
# ---------------------------------------------------------------------------


def run_confirmation(
    confirmation: ConfirmationConfig,
    message: str,
) -> bool:
    """Run the confirmation command.

    The confirmation command is configured with a {message} placeholder.
    It should return exit 0 (approve) or exit 1 (deny).

    Args:
        confirmation: The confirmation config with cmd template.
        message: The context message to display.

    Returns:
        True if approved, False if denied.
    """
    cmd = confirmation.format_message(message)

    if not cmd:
        # No confirmation command configured — default to deny
        logger.debug("no confirmation command configured, defaulting to deny")
        return False

    logger.debug("running confirmation: %s", cmd)
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        approved = result.returncode == 0
        logger.debug("confirmation %s", "approved" if approved else "denied")
        return approved
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        logger.debug("confirmation failed (timeout or error)")
        return False


# ---------------------------------------------------------------------------
# Validation hook pipeline
# ---------------------------------------------------------------------------


def run_validation_hooks(
    command: str,
    config: HookPipelineConfig,
    timeout: int = 30,
) -> PipelineResult:
    """Run validation hooks before command execution.

    Validation hooks receive the command string via stdin.
    - exit 0: approve, continue to next hook
    - exit 1: deny, stderr is the reason
    - exit 2: ask user via confirmation command

    Args:
        command: The command string to validate.
        config: The validation hook pipeline config.
        timeout: Timeout per hook in seconds.

    Returns:
        PipelineResult with allowed=True if all hooks approve.
    """
    if not config.enabled or not config.hooks:
        logger.debug("validation hooks %s", "enabled" if config.enabled else "disabled")
        return PipelineResult(allowed=True)

    logger.debug("running %d validation hook(s)", len(config.hooks))
    results: list[HookResult] = []

    for hook_cmd in config.hooks:
        exit_code, stdout, stderr = _run_single_hook(hook_cmd, command, timeout)

        if exit_code == 0:
            # Approved — continue to next hook
            logger.debug("validation approved: %s", hook_cmd)
            results.append(HookResult(hook=hook_cmd, action=HookAction.APPROVED))
            continue

        if exit_code == 1:
            # Denied
            reason = stderr.strip() or f"Hook denied: {hook_cmd}"
            logger.debug("validation denied: %s — %s", hook_cmd, reason)
            results.append(HookResult(hook=hook_cmd, action=HookAction.DENIED, reason=reason))
            return PipelineResult(allowed=False, results=results, reason=reason)

        if exit_code == 2:
            # Ask user
            logger.debug("validation asks user confirmation: %s", hook_cmd)
            results.append(HookResult(hook=hook_cmd, action=HookAction.ASK_USER))

            # Run confirmation
            message = stderr.strip() or f"Hook asks confirmation for: {hook_cmd}"
            approved = run_confirmation(config.confirmation, message)

            if not approved:
                reason = f"User denied confirmation for: {hook_cmd}"
                logger.debug("user denied confirmation")
                results.append(
                    HookResult(hook="(confirmation)", action=HookAction.DENIED, reason=reason)
                )
                return PipelineResult(allowed=False, results=results, reason=reason)

            # User approved — continue to next hook
            logger.debug("user approved confirmation")
            results.append(HookResult(hook="(confirmation)", action=HookAction.APPROVED))
            continue

        # Unknown exit code — treat as deny for safety
        reason = f"Hook returned unexpected exit code {exit_code}: {hook_cmd}"
        logger.debug("unexpected exit code %d: %s", exit_code, hook_cmd)
        results.append(HookResult(hook=hook_cmd, action=HookAction.DENIED, reason=reason))
        return PipelineResult(allowed=False, results=results, reason=reason)

    logger.debug("all validation hooks passed")
    return PipelineResult(allowed=True, results=results)


# ---------------------------------------------------------------------------
# Redaction hook pipeline
# ---------------------------------------------------------------------------


def run_redaction_hooks(
    output: str,
    config: HookPipelineConfig,
    timeout: int = 30,
) -> PipelineResult:
    """Run redaction hooks after command execution.

    Redaction hooks receive raw output via stdin and emit redacted
    output via stdout. Each hook's stdout becomes the next hook's stdin.
    - exit 0: pass, stdout is the (possibly redacted) output
    - exit 1: block entire output
    - exit 2: ask user via confirmation command

    Args:
        output: The raw output text to redact.
        config: The redaction hook pipeline config.
        timeout: Timeout per hook in seconds.

    Returns:
        PipelineResult with the final (redacted) output in .output field.
    """
    if not config.enabled or not config.hooks:
        logger.debug("redaction hooks %s", "enabled" if config.enabled else "disabled")
        return PipelineResult(allowed=True, output=output)

    logger.debug("running %d redaction hook(s)", len(config.hooks))
    results: list[HookResult] = []
    current_text = output

    for hook_cmd in config.hooks:
        exit_code, stdout, stderr = _run_single_hook(hook_cmd, current_text, timeout)

        if exit_code == 0:
            # Pass — stdout becomes input for next hook
            current_text = stdout if stdout else current_text
            logger.debug("redaction passed: %s", hook_cmd)
            results.append(HookResult(hook=hook_cmd, action=HookAction.PASS))
            continue

        if exit_code == 1:
            # Block entire output
            reason = stderr.strip() or f"Output blocked by hook: {hook_cmd}"
            logger.debug("redaction blocked: %s — %s", hook_cmd, reason)
            results.append(HookResult(hook=hook_cmd, action=HookAction.BLOCKED, reason=reason))
            return PipelineResult(allowed=False, results=results, reason=reason, output="")

        if exit_code == 2:
            # Ask user
            logger.debug("redaction asks user confirmation: %s", hook_cmd)
            results.append(HookResult(hook=hook_cmd, action=HookAction.ASK_USER))

            message = stderr.strip() or f"Hook asks confirmation for output: {hook_cmd}"
            approved = run_confirmation(config.confirmation, message)

            if not approved:
                reason = f"User denied confirmation for output redaction: {hook_cmd}"
                logger.debug("user denied redaction confirmation")
                results.append(
                    HookResult(hook="(confirmation)", action=HookAction.BLOCKED, reason=reason)
                )
                return PipelineResult(allowed=False, results=results, reason=reason, output="")

            # User approved — keep current text, continue to next hook
            logger.debug("user approved redaction confirmation")
            results.append(HookResult(hook="(confirmation)", action=HookAction.APPROVED))
            continue

        # Unknown exit code — treat as block for safety
        reason = f"Hook returned unexpected exit code {exit_code}: {hook_cmd}"
        logger.debug("unexpected exit code %d: %s", exit_code, hook_cmd)
        results.append(HookResult(hook=hook_cmd, action=HookAction.BLOCKED, reason=reason))
        return PipelineResult(allowed=False, results=results, reason=reason, output="")

    logger.debug("all redaction hooks passed")
    return PipelineResult(allowed=True, results=results, output=current_text)
