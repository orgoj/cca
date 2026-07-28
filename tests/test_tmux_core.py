"""Tests for tmux_cli_python.tmux_core — core tmux interaction layer.

These tests validate the core tmux operations:
- ensure_session() — create session if missing
- ensure_ssh_window() — create SSH window for server
- find_window() — locate window by server name
- run_command() — execute command with markers
- read_output() — capture pane output
- list_windows() — list active windows
- create_session() — create session with SSH windows
- Marker parsing and exit code extraction

All tmux operations are mocked since we don't have a tmux server in tests.
"""

from __future__ import annotations

import textwrap
from unittest.mock import MagicMock, patch

import pytest

from tmux_cli_python.tmux_core import (
    SIGNAL_EXIT_CODES,
    CommandResult,
    TmuxCoreError,
    WindowInfo,
    _extract_between_markers,
    _extract_marker_output,
    _has_end_marker,
    _parse_exit_code,
    _strip_marker_lines,
    _strip_tmux_markers,
    create_session,
    ensure_session,
    ensure_ssh_window,
    find_window,
    format_window_list,
    list_windows,
    read_output,
    run_command,
    session_exists,
)

# ---------------------------------------------------------------------------
# Marker parsing tests (pure logic, no tmux needed)
# ---------------------------------------------------------------------------


class TestHasEndMarker:
    """Test the _has_end_marker helper."""

    def test_exitcode_marker(self):
        marker = "TMUX_MARKER_12345_999"
        screen = f"=== END {marker} EXITCODE=0 ==="
        assert _has_end_marker(screen, marker) is True

    def test_interrupted_marker(self):
        marker = "TMUX_MARKER_12345_999"
        screen = f"=== END {marker} INTERRUPTED ==="
        assert _has_end_marker(screen, marker) is True

    def test_terminated_marker(self):
        marker = "TMUX_MARKER_12345_999"
        screen = f"=== END {marker} TERMINATED ==="
        assert _has_end_marker(screen, marker) is True

    def test_hangup_marker(self):
        marker = "TMUX_MARKER_12345_999"
        screen = f"=== END {marker} HANGUP ==="
        assert _has_end_marker(screen, marker) is True

    def test_killed_marker(self):
        marker = "TMUX_MARKER_12345_999"
        screen = f"=== END {marker} KILLED ==="
        assert _has_end_marker(screen, marker) is True

    def test_no_marker(self):
        marker = "TMUX_MARKER_12345_999"
        screen = "some random output\nno markers here"
        assert _has_end_marker(screen, marker) is False

    def test_start_but_no_end(self):
        marker = "TMUX_MARKER_12345_999"
        screen = f"=== START {marker} ===\nsome output"
        assert _has_end_marker(screen, marker) is False

    def test_multiline_with_marker(self):
        marker = "TMUX_MARKER_12345_999"
        screen = textwrap.dedent(f"""\
        some previous output
        === START {marker} ===
        command output line 1
        command output line 2
        === END {marker} EXITCODE=0 ===
        some trailing output""")
        assert _has_end_marker(screen, marker) is True

    def test_nonzero_exitcode(self):
        marker = "TMUX_MARKER_12345_999"
        screen = f"=== END {marker} EXITCODE=42 ==="
        assert _has_end_marker(screen, marker) is True


class TestExtractBetweenMarkers:
    """Test the _extract_between_markers helper."""

    def test_basic_extraction(self):
        marker = "TMUX_MARKER_123"
        text = textwrap.dedent(f"""\
        before
        === START {marker} ===
        line 1
        line 2
        === END {marker} EXITCODE=0 ===
        after""")
        result = _extract_between_markers(text, marker)
        assert "=== START" in result
        assert "line 1" in result
        assert "line 2" in result
        assert "=== END" in result
        assert "before" not in result
        assert "after" not in result

    def test_extraction_without_end(self):
        marker = "TMUX_MARKER_123"
        text = textwrap.dedent(f"""\
        before
        === START {marker} ===
        line 1
        line 2""")
        result = _extract_between_markers(text, marker, include_end=False)
        assert "line 1" in result
        assert "line 2" in result

    def test_no_markers_returns_empty(self):
        text = "just some text\nno markers"
        result = _extract_between_markers(text, "NONEXISTENT")
        assert result == ""


class TestExtractMarkerOutput:
    """Test the _extract_marker_output helper (used by read --marker)."""

    def test_extracts_between_markers_stripping_marker_lines(self):
        marker = "TMUX_MARKER_123"
        text = textwrap.dedent(f"""\
        === START {marker} ===
        command output line 1
        command output line 2
        === END {marker} EXITCODE=0 ===""")
        result = _extract_marker_output(text, marker)
        assert result == "command output line 1\ncommand output line 2"

    def test_empty_output_between_markers(self):
        marker = "TMUX_MARKER_123"
        text = f"=== START {marker} ===\n=== END {marker} EXITCODE=0 ==="
        result = _extract_marker_output(text, marker)
        assert result == ""

    def test_only_start_no_end(self):
        marker = "TMUX_MARKER_123"
        text = f"=== START {marker} ===\nsome output"
        result = _extract_marker_output(text, marker)
        assert result == ""


class TestParseExitCode:
    """Test exit code parsing from END marker."""

    def test_exitcode_zero(self):
        marker = "TMUX_MARKER_123"
        content = f"=== START {marker} ===\noutput\n=== END {marker} EXITCODE=0 ==="
        assert _parse_exit_code(content, marker) == 0

    def test_exitcode_nonzero(self):
        marker = "TMUX_MARKER_123"
        content = f"=== START {marker} ===\nerror\n=== END {marker} EXITCODE=1 ==="
        assert _parse_exit_code(content, marker) == 1

    def test_exitcode_42(self):
        marker = "TMUX_MARKER_123"
        content = f"=== START {marker} ===\noutput\n=== END {marker} EXITCODE=42 ==="
        assert _parse_exit_code(content, marker) == 42

    def test_interrupted_signal(self):
        marker = "TMUX_MARKER_123"
        content = f"=== START {marker} ===\noutput\n=== END {marker} INTERRUPTED ==="
        assert _parse_exit_code(content, marker) == 130

    def test_terminated_signal(self):
        marker = "TMUX_MARKER_123"
        content = f"=== START {marker} ===\noutput\n=== END {marker} TERMINATED ==="
        assert _parse_exit_code(content, marker) == 143

    def test_hangup_signal(self):
        marker = "TMUX_MARKER_123"
        content = f"=== START {marker} ===\noutput\n=== END {marker} HANGUP ==="
        assert _parse_exit_code(content, marker) == 129

    def test_killed_signal(self):
        marker = "TMUX_MARKER_123"
        content = f"=== START {marker} ===\noutput\n=== END {marker} KILLED ==="
        assert _parse_exit_code(content, marker) == 137

    def test_no_end_marker_defaults_zero(self):
        marker = "TMUX_MARKER_123"
        content = "=== START {marker} ===\noutput"
        assert _parse_exit_code(content, marker) == 0

    def test_empty_content_defaults_zero(self):
        assert _parse_exit_code("", "any") == 0


class TestStripMarkerLines:
    """Test _strip_marker_lines helper."""

    def test_strips_start_and_end(self):
        content = "=== START M ===\nhello\n=== END M EXITCODE=0 ==="
        assert _strip_marker_lines(content) == "hello"

    def test_strips_only_start(self):
        content = "=== START M ===\nhello\nworld"
        assert _strip_marker_lines(content) == "hello\nworld"

    def test_strips_only_end(self):
        content = "hello\n=== END M EXITCODE=0 ==="
        assert _strip_marker_lines(content) == "hello"

    def test_no_markers(self):
        content = "hello\nworld"
        assert _strip_marker_lines(content) == "hello\nworld"

    def test_multiline_output(self):
        content = "=== START M ===\nline1\nline2\nline3\n=== END M EXITCODE=0 ==="
        assert _strip_marker_lines(content) == "line1\nline2\nline3"


class TestStripTmuxMarkers:
    """Test _strip_tmux_markers — the fix for rstrip over-stripping (TMU-24)."""

    def test_active_marker_stripped(self):
        assert _strip_tmux_markers("web1*") == "web1"

    def test_last_marker_stripped(self):
        assert _strip_tmux_markers("web1-") == "web1"

    def test_no_marker(self):
        assert _strip_tmux_markers("web1") == "web1"

    def test_empty_string(self):
        assert _strip_tmux_markers("") == ""

    def test_server_name_with_dashes_not_over_stripped(self):
        """Regression: rstrip("-*") would strip trailing dashes from names."""
        assert _strip_tmux_markers("build--") == "build-"

    def test_server_name_ending_with_dash_as_marker(self):
        """Single trailing dash (tmux marker) should be stripped."""
        assert _strip_tmux_markers("build-") == "build"

    def test_server_name_ending_with_asterisk_as_marker(self):
        """Single trailing asterisk (tmux marker) should be stripped."""
        assert _strip_tmux_markers("build*") == "build"

    def test_dash_in_middle_preserved(self):
        """Dashes in the middle of a name are not touched."""
        assert _strip_tmux_markers("web-deploy") == "web-deploy"

    def test_only_marker_characters(self):
        assert _strip_tmux_markers("*") == ""
        assert _strip_tmux_markers("-") == ""

    def test_only_dashes_single_stripped(self):
        """Only one trailing marker character is stripped."""
        assert _strip_tmux_markers("---") == "--"

    def test_find_window_with_dashed_server_name(self):
        """Verify that a server name containing dashes is found correctly."""
        mock_session = MagicMock()
        mock_window = MagicMock()
        mock_window.window_name = "web-deploy-*"
        mock_session.windows = [mock_window]

        result = find_window(mock_session, "web-deploy-")
        assert result == mock_window

    def test_find_window_with_dashed_server_name_no_marker(self):
        """When window name is 'web-deploy' (no marker), find by exact name."""
        from tmux_cli_python.tmux_core import _find_window_by_name

        mock_session = MagicMock()
        mock_window = MagicMock()
        mock_window.window_name = "web-deploy"
        mock_session.windows = [mock_window]

        result = _find_window_by_name(mock_session, "web-deploy")
        assert result == mock_window

    def test_list_windows_with_dashed_name_and_marker(self):
        """Verify list_windows doesn't over-strip names with dashes."""
        mock_session = MagicMock()
        w1 = MagicMock()
        w1.window_id = "@0"
        w1.window_name = "build--*"
        mock_session.windows = [w1]

        windows = list_windows(mock_session)
        # "build--*" → strip trailing '*' → "build--"
        assert windows[0].name == "build--"
        assert windows[0].active is True


class TestSignalExitCodes:
    """Verify signal exit code constants match bash conventions."""

    def test_interrupted_is_130(self):
        assert SIGNAL_EXIT_CODES["INTERRUPTED"] == 130

    def test_terminated_is_143(self):
        assert SIGNAL_EXIT_CODES["TERMINATED"] == 143

    def test_hangup_is_129(self):
        assert SIGNAL_EXIT_CODES["HANGUP"] == 129

    def test_killed_is_137(self):
        assert SIGNAL_EXIT_CODES["KILLED"] == 137


# ---------------------------------------------------------------------------
# ensure_session tests (mocked tmux)
# ---------------------------------------------------------------------------


class TestEnsureSession:
    """Test session creation/retrieval."""

    def test_empty_session_name_raises(self):
        with pytest.raises(TmuxCoreError, match="No session specified"):
            ensure_session("")

    @patch("tmux_cli_python.tmux_core._get_server")
    def test_existing_session_returned(self, mock_get_server):
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_server.find_where.return_value = mock_session
        mock_get_server.return_value = mock_server

        result = ensure_session("cca-test")
        assert result == mock_session
        mock_server.new_session.assert_not_called()

    @patch("tmux_cli_python.tmux_core._get_server")
    def test_new_session_created(self, mock_get_server):
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_server.find_where.return_value = None
        mock_server.new_session.return_value = mock_session
        mock_get_server.return_value = mock_server

        result = ensure_session("cca-newsession")
        assert result == mock_session
        mock_server.new_session.assert_called_once_with("cca-newsession", detach=True)


# ---------------------------------------------------------------------------
# find_window / ensure_ssh_window tests (mocked)
# ---------------------------------------------------------------------------


class TestFindWindow:
    """Test window finding logic."""

    def test_existing_window_found(self):
        mock_session = MagicMock()
        mock_window = MagicMock()
        mock_window.window_name = "web1"
        mock_session.windows = [mock_window]

        result = find_window(mock_session, "web1")
        assert result == mock_window

    def test_window_with_activity_marker(self):
        mock_session = MagicMock()
        mock_window = MagicMock()
        mock_window.window_name = "web1*"
        mock_session.windows = [mock_window]

        result = find_window(mock_session, "web1")
        assert result == mock_window

    def test_window_with_last_marker(self):
        mock_session = MagicMock()
        mock_window = MagicMock()
        mock_window.window_name = "web1-"
        mock_session.windows = [mock_window]

        result = find_window(mock_session, "web1")
        assert result == mock_window


class TestEnsureSshWindow:
    """Test SSH window creation."""

    @patch("tmux_cli_python.tmux_core.time.sleep")
    def test_creates_window_if_missing(self, mock_sleep):
        mock_session = MagicMock()
        mock_session.windows = []
        mock_window = MagicMock()
        mock_window.window_name = "web1"
        # After creation, window appears
        mock_session.new_window.return_value = mock_window

        with patch("tmux_cli_python.tmux_core._find_window_by_name", return_value=None):
            with patch("tmux_cli_python.tmux_core.find_window", return_value=mock_window):
                result = ensure_ssh_window(mock_session, "web1")
                assert result == mock_window

    @patch("tmux_cli_python.tmux_core.time.sleep")
    def test_returns_existing_window(self, mock_sleep):
        mock_session = MagicMock()
        mock_window = MagicMock()
        mock_window.window_name = "web1"

        with patch("tmux_cli_python.tmux_core._find_window_by_name", return_value=mock_window):
            result = ensure_ssh_window(mock_session, "web1")
            assert result == mock_window
            mock_session.new_window.assert_not_called()


# ---------------------------------------------------------------------------
# list_windows tests (mocked)
# ---------------------------------------------------------------------------


class TestListWindows:
    """Test window listing."""

    def test_list_windows_basic(self):
        mock_session = MagicMock()
        w1 = MagicMock()
        w1.window_id = "@0"
        w1.window_name = "web1"
        w2 = MagicMock()
        w2.window_id = "@1"
        w2.window_name = "web2"
        mock_session.windows = [w1, w2]

        windows = list_windows(mock_session)
        assert len(windows) == 2
        assert windows[0].name == "web1"
        assert windows[1].name == "web2"

    def test_list_windows_strips_markers(self):
        mock_session = MagicMock()
        w1 = MagicMock()
        w1.window_id = "@0"
        w1.window_name = "web1*"
        mock_session.windows = [w1]

        windows = list_windows(mock_session)
        assert windows[0].name == "web1"
        assert windows[0].active is True

    def test_list_windows_empty_session(self):
        mock_session = MagicMock()
        mock_session.windows = []

        windows = list_windows(mock_session)
        assert windows == []


class TestFormatWindowList:
    """Test window list formatting."""

    def test_raw_format(self):
        windows = [
            WindowInfo(window_id="@0", name="web1", active=True),
            WindowInfo(window_id="@1", name="web2", active=False),
        ]
        result = format_window_list(windows, raw=True)
        assert "@0 * web1" in result
        assert "@1   web2" in result

    def test_default_format_skips_bash(self):
        windows = [
            WindowInfo(window_id="@0", name="bash", active=False),
            WindowInfo(window_id="@1", name="web1", active=True),
        ]
        result = format_window_list(windows)
        assert "bash" not in result
        assert "web1" in result

    def test_default_format_just_names(self):
        windows = [
            WindowInfo(window_id="@0", name="web1", active=False),
            WindowInfo(window_id="@1", name="web2", active=True),
        ]
        result = format_window_list(windows)
        assert result == "web1\nweb2"


# ---------------------------------------------------------------------------
# session_exists tests (mocked)
# ---------------------------------------------------------------------------


class TestSessionExists:
    """Test session existence check."""

    @patch("tmux_cli_python.tmux_core._get_server")
    def test_existing_session(self, mock_get_server):
        mock_server = MagicMock()
        mock_server.find_where.return_value = MagicMock()
        mock_get_server.return_value = mock_server

        assert session_exists("cca-test") is True

    @patch("tmux_cli_python.tmux_core._get_server")
    def test_nonexistent_session(self, mock_get_server):
        mock_server = MagicMock()
        mock_server.find_where.return_value = None
        mock_get_server.return_value = mock_server

        assert session_exists("cca-nonexistent") is False

    @patch("tmux_cli_python.tmux_core._get_server")
    def test_exception_returns_false(self, mock_get_server):
        mock_server = MagicMock()
        mock_server.find_where.side_effect = Exception("tmux error")
        mock_get_server.return_value = mock_server

        assert session_exists("cca-test") is False


# ---------------------------------------------------------------------------
# create_session tests (mocked)
# ---------------------------------------------------------------------------


class TestCreateSession:
    """Test session creation with SSH windows."""

    def test_empty_session_name_raises(self):
        with pytest.raises(TmuxCoreError, match="No session specified"):
            create_session("", ["web1"])

    def test_empty_servers_raises(self):
        with pytest.raises(TmuxCoreError, match="No servers specified"):
            create_session("cca-test", [])

    @patch("tmux_cli_python.tmux_core._get_server")
    def test_creates_new_session(self, mock_get_server):
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_server.find_where.return_value = None
        mock_server.new_session.return_value = mock_session
        mock_session.windows = []
        mock_get_server.return_value = mock_server

        result = create_session("cca-test", ["web1", "web2"])
        assert result == mock_session
        mock_server.new_session.assert_called_once()
        mock_session.new_window.assert_called_once_with(window_name="web2", window_shell="ssh web2")

    @patch("tmux_cli_python.tmux_core._get_server")
    def test_adds_windows_to_existing_session(self, mock_get_server):
        mock_server = MagicMock()
        mock_session = MagicMock()
        mock_server.find_where.return_value = mock_session
        mock_session.windows = []
        mock_get_server.return_value = mock_server

        result = create_session("cca-test", ["web1", "web2", "db1"])
        assert result == mock_session
        # When session already exists, all servers get new windows
        # (since first server didn't create the session)
        assert mock_session.new_window.call_count == 3


# ---------------------------------------------------------------------------
# CommandResult dataclass tests
# ---------------------------------------------------------------------------


class TestCommandResult:
    """Test the CommandResult dataclass."""

    def test_basic_result(self):
        result = CommandResult(output="hello", exit_code=0, marker="M123")
        assert result.output == "hello"
        assert result.exit_code == 0
        assert result.marker == "M123"
        assert result.timed_out is False

    def test_timeout_result(self):
        result = CommandResult(output="partial", exit_code=124, marker="M123", timed_out=True)
        assert result.timed_out is True
        assert result.exit_code == 124

    def test_signal_result(self):
        result = CommandResult(output="", exit_code=130, marker="M123")
        assert result.exit_code == 130


# ---------------------------------------------------------------------------
# WindowInfo dataclass tests
# ---------------------------------------------------------------------------


class TestWindowInfo:
    """Test the WindowInfo dataclass."""

    def test_basic_window(self):
        info = WindowInfo(window_id="@0", name="web1", active=False)
        assert info.window_id == "@0"
        assert info.name == "web1"
        assert info.active is False

    def test_active_window(self):
        info = WindowInfo(window_id="@1", name="web2", active=True)
        assert info.active is True


# ---------------------------------------------------------------------------
# run_command tests (mocked subprocess)
# ---------------------------------------------------------------------------


class TestRunCommand:
    """Test command execution with mocked tmux subprocess calls."""

    @patch("tmux_cli_python.tmux_core.time.sleep")
    @patch("tmux_cli_python.tmux_core._tmux_capture_pane")
    @patch("tmux_cli_python.tmux_core._tmux_send_keys")
    @patch("tmux_cli_python.tmux_core.find_window")
    def test_basic_command_execution(self, mock_find, mock_send, mock_capture, mock_sleep):
        mock_window = MagicMock()
        mock_window.window_id = "@0"
        mock_find.return_value = mock_window

        call_count = {"n": 0}

        # First call = poll (no marker yet)
        # Second call = poll (has marker)
        def capture_side_effect(target, history=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First poll — no marker yet
                return ""
            # Second call — find the marker from the send_keys call
            # call_args_list[0][0] is the positional args tuple of the first call.
            # [1] gets the second arg (the text sent to the window).
            sent_text = mock_send.call_args_list[0][0][1] if mock_send.call_args_list else ""
            # Extract marker from the sent command
            import re

            match = re.search(r"=== START (TMUX_MARKER_\S+) ===", sent_text)
            if match:
                marker = match.group(1)
                return textwrap.dedent(f"""\
                some output
                === START {marker} ===
                hello world
                === END {marker} EXITCODE=0 ===""")
            return ""

        mock_capture.side_effect = capture_side_effect

        result = run_command(
            session=MagicMock(),
            server_name="web1",
            command="echo hello world",
            poll_interval=1,
            timeout=10,
        )

        assert result.exit_code == 0
        assert "hello world" in result.output
        assert result.timed_out is False

    @patch("tmux_cli_python.tmux_core.time.sleep")
    @patch("tmux_cli_python.tmux_core._tmux_capture_pane")
    @patch("tmux_cli_python.tmux_core._tmux_send_keys")
    @patch("tmux_cli_python.tmux_core.find_window")
    def test_command_with_nonzero_exit(self, mock_find, mock_send, mock_capture, mock_sleep):
        mock_window = MagicMock()
        mock_window.window_id = "@0"
        mock_find.return_value = mock_window

        call_count = {"n": 0}

        def capture_side_effect(target, history=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return ""
            sent_text = mock_send.call_args_list[0][0][1] if mock_send.call_args_list else ""
            import re

            match = re.search(r"=== START (TMUX_MARKER_\S+) ===", sent_text)
            if match:
                marker = match.group(1)
                return textwrap.dedent(f"""\
                === START {marker} ===
                error: something failed
                === END {marker} EXITCODE=1 ===""")
            return ""

        mock_capture.side_effect = capture_side_effect

        result = run_command(
            session=MagicMock(),
            server_name="web1",
            command="false",
            poll_interval=1,
            timeout=10,
        )

        assert result.exit_code == 1
        assert "error: something failed" in result.output

    @patch("tmux_cli_python.tmux_core.time.sleep")
    @patch("tmux_cli_python.tmux_core._tmux_capture_pane")
    @patch("tmux_cli_python.tmux_core._tmux_send_keys")
    @patch("tmux_cli_python.tmux_core.find_window")
    def test_command_timeout(self, mock_find, mock_send, mock_capture, mock_sleep):
        mock_window = MagicMock()
        mock_window.window_id = "@0"
        mock_find.return_value = mock_window

        # Never return end marker
        mock_capture.return_value = "still running..."

        result = run_command(
            session=MagicMock(),
            server_name="web1",
            command="sleep 999",
            poll_interval=1,
            timeout=2,
        )

        assert result.timed_out is True
        assert result.exit_code == 124

    @patch("tmux_cli_python.tmux_core.time.sleep")
    @patch("tmux_cli_python.tmux_core._tmux_capture_pane")
    @patch("tmux_cli_python.tmux_core._tmux_send_keys")
    @patch("tmux_cli_python.tmux_core.find_window")
    def test_command_interrupted_signal(self, mock_find, mock_send, mock_capture, mock_sleep):
        mock_window = MagicMock()
        mock_window.window_id = "@0"
        mock_find.return_value = mock_window

        call_count = {"n": 0}

        def capture_side_effect(target, history=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return ""
            sent_text = mock_send.call_args_list[0][0][1] if mock_send.call_args_list else ""
            import re

            match = re.search(r"=== START (TMUX_MARKER_\S+) ===", sent_text)
            if match:
                marker = match.group(1)
                return textwrap.dedent(f"""\
                === START {marker} ===
                ^C
                === END {marker} INTERRUPTED ===""")
            return ""

        mock_capture.side_effect = capture_side_effect

        result = run_command(
            session=MagicMock(),
            server_name="web1",
            command="long-running-cmd",
            poll_interval=1,
            timeout=10,
        )

        assert result.exit_code == 130
        assert "^C" in result.output


# ---------------------------------------------------------------------------
# read_output tests (mocked)
# ---------------------------------------------------------------------------


class TestReadOutput:
    """Test output reading with mocked tmux."""

    @patch("tmux_cli_python.tmux_core._tmux_capture_pane")
    @patch("tmux_cli_python.tmux_core.find_window")
    def test_read_visible_only(self, mock_find, mock_capture):
        mock_window = MagicMock()
        mock_window.window_id = "@0"
        mock_find.return_value = mock_window
        mock_capture.return_value = "visible output"

        result = read_output(
            session=MagicMock(),
            server_name="web1",
        )
        assert result == "visible output"
        mock_capture.assert_called_with("@0")

    @patch("tmux_cli_python.tmux_core._tmux_capture_pane")
    @patch("tmux_cli_python.tmux_core.find_window")
    def test_read_with_history(self, mock_find, mock_capture):
        mock_window = MagicMock()
        mock_window.window_id = "@0"
        mock_find.return_value = mock_window
        mock_capture.return_value = "historical output"

        result = read_output(
            session=MagicMock(),
            server_name="web1",
            history=100,
        )
        assert result == "historical output"
        mock_capture.assert_called_with("@0", history=-100)

    @patch("tmux_cli_python.tmux_core._tmux_capture_pane")
    @patch("tmux_cli_python.tmux_core.find_window")
    def test_read_all(self, mock_find, mock_capture):
        mock_window = MagicMock()
        mock_window.window_id = "@0"
        mock_find.return_value = mock_window
        mock_capture.return_value = "all output"

        result = read_output(
            session=MagicMock(),
            server_name="web1",
            all_output=True,
        )
        assert result == "all output"
        mock_capture.assert_called_with("@0", history=-1)

    @patch("tmux_cli_python.tmux_core._tmux_capture_pane")
    @patch("tmux_cli_python.tmux_core.find_window")
    def test_read_marker(self, mock_find, mock_capture):
        mock_window = MagicMock()
        mock_window.window_id = "@0"
        mock_find.return_value = mock_window
        mock_capture.return_value = textwrap.dedent("""\
        some previous
        === START TMUX_MARKER_123 ===
        command output line 1
        command output line 2
        === END TMUX_MARKER_123 EXITCODE=0 ===
        some after""")

        result = read_output(
            session=MagicMock(),
            server_name="web1",
            marker="TMUX_MARKER_123",
        )
        assert "command output line 1" in result
        assert "command output line 2" in result
        assert "=== START" not in result
        assert "=== END" not in result


# ---------------------------------------------------------------------------
# CLI integration tests — verify subcommands now call tmux_core
# ---------------------------------------------------------------------------


class TestCliListIntegration:
    """Verify the list subcommand integrates with tmux_core."""

    @patch("tmux_cli_python.cli.session_exists")
    @patch("tmux_cli_python.cli.ensure_session")
    @patch("tmux_cli_python.cli.tmux_list_windows")
    @patch("tmux_cli_python.cli.format_window_list")
    def test_list_with_active_windows(self, mock_format, mock_list, mock_ensure, mock_exists):
        from typer.testing import CliRunner

        from tmux_cli_python.cli import app

        mock_exists.return_value = True
        mock_session = MagicMock()
        mock_ensure.return_value = mock_session
        mock_list.return_value = [WindowInfo(window_id="@0", name="web1", active=True)]
        mock_format.return_value = "web1"

        runner = CliRunner()
        result = runner.invoke(app, ["-s", "cca-test", "list"])
        assert result.exit_code == 0
        assert "web1" in result.stdout

    @patch("tmux_cli_python.cli.session_exists")
    def test_list_raw_nonexistent_session(self, mock_exists):
        from typer.testing import CliRunner

        from tmux_cli_python.cli import app

        mock_exists.return_value = False

        runner = CliRunner()
        result = runner.invoke(app, ["-s", "cca-test", "list", "--raw"])
        assert result.exit_code == 1
        assert "does not exist" in result.output


class TestCliSessionIntegration:
    """Verify the session subcommand integrates with tmux_core."""

    @patch("tmux_cli_python.cli.tmux_create_session")
    def test_session_creates_successfully(self, mock_create):
        from typer.testing import CliRunner

        from tmux_cli_python.cli import app

        mock_create.return_value = MagicMock()

        runner = CliRunner()
        result = runner.invoke(app, ["-s", "cca-test", "session", "web1", "web2"])
        assert result.exit_code == 0
        assert "cca-test" in result.stdout
        assert "web1" in result.stdout

    @patch("tmux_cli_python.cli.tmux_create_session")
    def test_session_no_servers_no_config(self, mock_create):
        from typer.testing import CliRunner

        from tmux_cli_python.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["-s", "cca-test", "session"])
        assert result.exit_code == 64
        assert "No servers" in result.output
