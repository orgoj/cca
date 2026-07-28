"""Test configuration — tmux isolation guard.

ALL tmux operations in tests MUST use mocked or isolated tmux.
No real tmux sessions should ever be created on the host machine.

This conftest provides a THREE-LAYER defense:

Layer 1 — subprocess guard (autouse):
    Patches subprocess.run to BLOCK any direct `tmux` CLI calls.
    This catches raw subprocess.run(["tmux", ...]) invocations that
    bypass libtmux entirely.

Layer 2 — libtmux + CLI mocks (autouse):
    Patches tmux I/O at TWO levels:
    - Low-level: _get_server, _tmux_send_keys, _tmux_capture_pane, time.sleep
    - CLI-level: session_exists, ensure_session, run_command, etc.
    This prevents CLI tests from entering the run_command polling loop.

Layer 3 — session guard (session-scoped, autouse):
    Fails the entire test session if ANY new tmux session is detected
    after tests complete, regardless of name pattern.

Opt-in fixtures:
    isolated_tmux_server — for real isolated tmux tests (unique socket in tmpdir).
    Uses libtmux.Server with socket_name in tmp_path, completely isolated.
"""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Layer 1: Block ALL direct subprocess calls to tmux CLI
# ---------------------------------------------------------------------------

# Track whether isolated_tmux_server is active — if so, allow tmux subprocess
_isolated_server_active = False


class _TmuxSubprocessBlocker:
    """Wrapper around subprocess.run that blocks direct `tmux` CLI calls.

    When an isolated_tmux_server fixture is active, tmux calls are allowed
    (they target a unique socket). Otherwise, any subprocess call starting
    with "tmux" is blocked with a clear error message.
    """

    def __init__(self, original_run):
        self._original_run = original_run

    def __call__(self, *args, **kwargs):
        # Extract the command from args or kwargs
        cmd = args[0] if args else kwargs.get("args", [])

        # Check if this is a tmux command
        is_tmux_cmd = False
        if isinstance(cmd, (list, tuple)) and cmd:
            is_tmux_cmd = str(cmd[0]).endswith("tmux") or cmd[0] == "tmux"
        elif isinstance(cmd, str):
            is_tmux_cmd = cmd.startswith("tmux ") or cmd == "tmux"

        if is_tmux_cmd and not _isolated_server_active:
            raise RuntimeError(
                f"BLOCKED: Direct tmux subprocess call in test: {cmd}\n"
                f"All tmux operations must use mocked or isolated servers.\n"
                f"See tests/conftest.py for isolation requirements."
            )

        return self._original_run(*args, **kwargs)

    # Forward all attribute access to the original
    def __getattr__(self, name):
        return getattr(self._original_run, name)


@pytest.fixture(autouse=True)
def _block_tmux_subprocess():
    """Block direct subprocess calls to tmux CLI during tests.

    This catches any code path that calls `subprocess.run(["tmux", ...])`
    directly, bypassing the mock layer.
    """
    original_run = subprocess.run
    blocker = _TmuxSubprocessBlocker(original_run)
    subprocess.run = blocker
    try:
        yield
    finally:
        subprocess.run = original_run


# ---------------------------------------------------------------------------
# Layer 2: Mock all tmux operations at libtmux and CLI level
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_tmux():
    """Prevent tests from creating real tmux sessions.

    Two-level mock defense:

    Level A — CLI mocks (high-level):
      Patches the functions imported in cli.py so CLI tests get mock
      responses without entering run_command's polling loop.

    Level B — tmux_core mocks (low-level safety net):
      Patches _get_server, _tmux_send_keys, _tmux_capture_pane, and
      time.sleep so that even if a test bypasses CLI mocks and calls
      tmux_core directly, no real tmux subprocess calls happen.

    Individual tests can override any of these with their own @patch
    decorators (e.g., test_tmux_core.py has explicit per-test mocks).
    """
    from tmux_cli_python.tmux_core import CommandResult

    # --- Shared mock objects ---
    mock_server = MagicMock()
    mock_session = MagicMock()
    mock_session.windows = []
    mock_server.find_where.return_value = None
    mock_server.new_session.return_value = mock_session

    def _mock_run_command(session, server_name, command, **kwargs):
        """Return a CommandResult that echoes the command — tests can check
        for the command text in the output."""
        return CommandResult(
            output=command,
            exit_code=0,
            marker="TMUX_MARKER_TEST_MOCK",
            timed_out=False,
        )

    with (
        # Level A: CLI-level mocks — prevent CLI from calling real tmux_core
        # session_exists=True by default so list/session commands work
        patch("tmux_cli_python.cli.session_exists", return_value=True),
        patch("tmux_cli_python.cli.ensure_session", return_value=mock_session),
        patch("tmux_cli_python.cli.tmux_run_command", side_effect=_mock_run_command),
        patch("tmux_cli_python.cli.tmux_read_output", return_value="mock read output"),
        patch("tmux_cli_python.cli.tmux_create_session", return_value=mock_session),
        patch("tmux_cli_python.cli.tmux_list_windows", return_value=[]),
        patch("tmux_cli_python.cli.format_window_list", return_value=""),
        # Level B: Low-level safety net — block subprocess calls to tmux
        patch("tmux_cli_python.tmux_core._get_server", return_value=mock_server),
        patch("tmux_cli_python.tmux_core._tmux_send_keys"),
        patch("tmux_cli_python.tmux_core._tmux_capture_pane", return_value=""),
        # Speed up any remaining polling loops (overridden by explicit mocks)
        patch("tmux_cli_python.tmux_core.time.sleep"),
    ):
        yield


# ---------------------------------------------------------------------------
# Layer 3: Session-scoped guard — detect ANY stray tmux sessions
# ---------------------------------------------------------------------------


def _list_tmux_session_names() -> list[str]:
    """Get current tmux session names (empty list if tmux not running).

    Uses os-level operations to avoid being affected by mock patches.
    """
    try:
        # Use os.popen instead of subprocess.run to avoid our own blocker
        with os.popen("tmux list-sessions -F '#{session_name}' 2>/dev/null") as pipe:
            output = pipe.read()
        if not output:
            return []
        return [line.strip() for line in output.strip().splitlines() if line.strip()]
    except Exception:
        return []


@pytest.fixture(scope="session", autouse=True)
def _guard_real_tmux_sessions():
    """Fail the test session if ANY test creates real tmux sessions.

    Records sessions before tests start, then checks for new ones after.
    ANY new session is killed and causes a failure — regardless of name.
    This catches ALL leaks, not just test-pattern-named sessions.
    """
    pre_existing = set(_list_tmux_session_names())
    yield
    post_sessions = set(_list_tmux_session_names())
    new_sessions = post_sessions - pre_existing

    if new_sessions:
        # Clean up ALL stray sessions
        for name in new_sessions:
            os.system(f"tmux kill-session -t {name} 2>/dev/null")
        pytest.fail(
            f"CRITICAL: Tests created real tmux sessions on the host: {sorted(new_sessions)}. "
            f"All tmux operations must use mocked or isolated servers. "
            f"See tests/conftest.py for isolation requirements."
        )


# ---------------------------------------------------------------------------
# Opt-in fixture: isolated tmux server for integration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_tmux_server(tmp_path):
    """Provide a REAL but ISOLATED tmux server for integration tests.

    Uses a unique socket path in tmp_path so it never touches the
    default tmux socket or existing sessions.

    Usage:
        def test_something(isolated_tmux_server):
            server = isolated_tmux_server
            session = server.new_session("my-test", detach=True)
            # ... test with real tmux, but completely isolated ...

    The server and all its sessions are cleaned up on teardown.
    """
    import libtmux

    global _isolated_server_active

    socket_path = tmp_path / "tmux-test-socket"

    try:
        server = libtmux.Server(
            socket_path=str(socket_path),
        )
    except Exception:
        pytest.skip("tmux not available for isolated server fixture")

    # Allow subprocess calls to tmux while this fixture is active
    _isolated_server_active = True

    yield server

    # Cleanup: kill all sessions in this isolated server
    try:
        for session in server.sessions:
            session.kill_session()
    except Exception:
        pass

    # Re-block subprocess calls
    _isolated_server_active = False
