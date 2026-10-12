"""Core tmux interaction layer.

Provides the fundamental tmux operations that mirror the bash cca-tmux-cli:
- ensure_session() — create tmux session if missing, always detached
- ensure_ssh_window() — create SSH window for server
- find_window() — locate tmux window by server name
- run_command() — base64 encode, send-keys, poll END marker, extract output
- read_output() — capture-pane with --all, --marker, history lines
- list_windows() — list active windows (default + raw)
- create_session() — create session with SSH windows for multiple servers

Key design choices (matching bash behavior):
- Marker-based output isolation (START/END markers)
- Base64 command encoding (safe chars)
- Signal trapping via subshell (INT/TERM/HUP)
- Timeout polling with configurable interval and max timeout
- Exit code extraction from END marker (EXITCODE=N, INTERRUPTED, TERMINATED, HANGUP, KILLED)
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import time
from dataclasses import dataclass

import libtmux

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CommandResult:
    """Result from a command execution via run_command()."""

    output: str
    exit_code: int
    marker: str
    timed_out: bool = False


@dataclass
class WindowInfo:
    """Information about a tmux window."""

    window_id: str
    name: str
    active: bool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Exit codes for signal-based termination
SIGNAL_EXIT_CODES = {
    "INTERRUPTED": 130,  # SIGINT
    "TERMINATED": 143,  # SIGTERM
    "HANGUP": 129,  # SIGHUP
    "KILLED": 137,  # SIGKILL
}

# Pattern to match END marker lines
END_MARKER_RE = re.compile(
    r"^=== END (?P<marker>.+?) "
    r"(?:(?P<exitcode>EXITCODE=\d+)|(?P<signal>INTERRUPTED|TERMINATED|HANGUP|KILLED))"
    r" ===$"
)

# Pattern to match START marker line
START_MARKER_RE = re.compile(r"^=== START (?P<marker>.+?) ===$")


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def _get_server() -> libtmux.Server:
    """Get a libtmux Server instance."""
    return libtmux.Server()


def ensure_session(session_name: str) -> libtmux.Session:
    """Ensure a tmux session exists (create if missing, always detached).

    Args:
        session_name: The tmux session name.

    Returns:
        The libtmux Session object.

    Raises:
        TmuxCoreError: If session_name is empty.
    """
    if not session_name:
        raise TmuxCoreError("No session specified. Use -s option or set session.name in config.")

    server = _get_server()

    # Check if session already exists
    try:
        session = server.find_where({"session_name": session_name})
        if session is not None:
            return session
    except Exception:
        pass

    # Create new detached session
    try:
        session = server.new_session(session_name, detach=True)
        return session
    except libtmux.LibTmuxException as exc:
        raise TmuxCoreError(f"Failed to create session '{session_name}': {exc}") from exc


def ensure_ssh_window(session: libtmux.Session, server_name: str) -> libtmux.Window:
    """Ensure an SSH window exists for a server in the session.

    Creates the window if it doesn't exist. Waits briefly for SSH to initialize
    after creating a new window.

    Args:
        session: The tmux session.
        server_name: The server name (used as window name).

    Returns:
        The libtmux Window object.
    """
    window = _find_window_by_name(session, server_name)
    if window is not None:
        return window

    # Create new SSH window
    try:
        window = session.new_window(window_name=server_name, window_shell=f"ssh {server_name}")
        # Brief pause for SSH to initialize (matches bash behavior)
        time.sleep(2)
        return window
    except libtmux.LibTmuxException as exc:
        raise TmuxCoreError(f"Failed to create SSH window for '{server_name}': {exc}") from exc


def find_window(session: libtmux.Session, server_name: str) -> libtmux.Window:
    """Find a tmux window by server name, creating it if missing.

    This is the primary entry point for subcommands that need a window.
    It will call ensure_ssh_window() if the window doesn't exist.

    Args:
        session: The tmux session.
        server_name: The server name to find.

    Returns:
        The libtmux Window object.

    Raises:
        TmuxCoreError: If window cannot be found or created.
    """
    window = _find_window_by_name(session, server_name)
    if window is not None:
        return window

    # Window doesn't exist — create it
    window = ensure_ssh_window(session, server_name)

    # Verify it was created
    window = _find_window_by_name(session, server_name)
    if window is None:
        raise TmuxCoreError(f"Failed to create window for server '{server_name}'")

    return window


def _strip_tmux_markers(name: str) -> str:
    """Strip tmux activity markers from a window name.

    Tmux appends at most one marker character:
      '*' = active window
      '-' = last (previous) window

    Python's str.rstrip strips individual characters, not a suffix,
    so rstrip("-*") would over-strip names like "build--" or "test-".
    We must strip at most one trailing '-' or '*'.

    Args:
        name: The raw tmux window name (may end with '-' or '*').

    Returns:
        The cleaned window name with at most one tmux marker removed.
    """
    if name and name[-1] in "-*":
        return name[:-1]
    return name


def _find_window_by_name(session: libtmux.Session, name: str) -> libtmux.Window | None:
    """Find a window in a session by exact name match.

    Args:
        session: The tmux session.
        name: The exact window name to match.

    Returns:
        The Window object if found, None otherwise.
    """
    try:
        for window in session.windows:
            # Strip tmux activity markers (-, *) from window name
            clean_name = _strip_tmux_markers(window.window_name) if window.window_name else ""
            if clean_name == name:
                return window
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Command execution (run subcommand)
# ---------------------------------------------------------------------------


def run_command(
    session: libtmux.Session,
    server_name: str,
    command: str,
    poll_interval: int = 2,
    timeout: int = 300,
) -> CommandResult:
    """Execute a command on a remote server via tmux.

    This mirrors the bash 'run' subcommand:
    1. Generate unique marker with timestamp and PID
    2. Base64-encode the command
    3. Send the wrapped command via send-keys
    4. Poll for END marker
    5. Extract output between markers
    6. Parse exit code from END marker

    Args:
        session: The tmux session.
        server_name: Target server name.
        command: The command string to execute.
        poll_interval: Polling interval in seconds (default: 2).
        timeout: Max timeout in seconds (default: 300).

    Returns:
        CommandResult with output, exit_code, marker, and timed_out flag.
    """
    window = find_window(session, server_name)

    # Generate unique marker (matches bash: TMUX_MARKER_$(date +%s%N)_$$)
    marker = f"TMUX_MARKER_{int(time.time() * 1e9)}_{os.getpid()}"

    # Base64 encode the command
    encoded_cmd = base64.b64encode(command.encode()).decode("ascii")

    # Build the wrapped command with signal trapping and markers
    # This matches the bash implementation's send-keys exactly:
    # - trap INT/TERM/HUP in outer shell
    # - run command in subshell with restored signals
    # - print START marker, execute, print END marker with exit code
    # - split marker echoes so a pane-wrapped line of the typed command
    #   never starts with a complete marker line
    wrapped = (
        f"trap '' INT TERM HUP; "
        f"echo; "
        f"echo '# Command:'; "
        f"echo '{encoded_cmd}' | base64 -d; "
        f"echo; "
        f"echo -n '=== START '; echo '{marker} ==='; "
        f"( trap - INT TERM HUP; echo '{encoded_cmd}' | base64 -d | bash ); "
        f"exitcode=$?; "
        f"trap - INT TERM HUP; "
        f"echo; "
        f"echo -n '=== END '; "
        f"case $exitcode in "
        f"130) echo '{marker} INTERRUPTED ===';; "
        f"143) echo '{marker} TERMINATED ===';; "
        f"129) echo '{marker} HANGUP ===';; "
        f"137) echo '{marker} KILLED ===';; "
        f"*) echo '{marker} EXITCODE='$exitcode' ===';; "
        f"esac"
    )

    # Get the window target for tmux commands
    window_target = window.window_id

    # Send the command (Enter is sent separately inside _tmux_send_keys,
    # matching bash: tmux send-keys "text" Enter)
    _tmux_send_keys(window_target, wrapped)

    # Poll for END marker
    elapsed = 0
    found = False
    while elapsed < timeout:
        time.sleep(poll_interval)
        elapsed += poll_interval

        current_screen = _tmux_capture_pane(window_target)
        if _has_end_marker(current_screen, marker):
            found = True
            break

    # Handle timeout
    if not found:
        # Return partial output (from START marker to current state)
        full_output = _tmux_capture_pane(window_target, history=5000)
        partial = _extract_between_markers(full_output, marker, include_end=False)
        return CommandResult(
            output=partial,
            exit_code=124,  # Same as bash timeout exit code
            marker=marker,
            timed_out=True,
        )

    # Normal completion — extract output between markers
    full_output = _tmux_capture_pane(window_target, history=5000)
    marker_content = _extract_between_markers(full_output, marker, include_end=True)

    # Extract exit code from END marker
    exit_code = _parse_exit_code(marker_content, marker)

    # Strip the START and END marker lines from output
    output = _strip_marker_lines(marker_content)

    return CommandResult(
        output=output,
        exit_code=exit_code,
        marker=marker,
        timed_out=False,
    )


# ---------------------------------------------------------------------------
# Output reading (read subcommand)
# ---------------------------------------------------------------------------


def read_output(
    session: libtmux.Session,
    server_name: str,
    history: int | None = None,
    all_output: bool = False,
    marker: str | None = None,
) -> str:
    """Read screen output from tmux.

    Mirrors the bash 'read' subcommand:
    - No args: visible content only
    - history N: last N lines of history
    - --all: all scrollback history
    - --marker: output between START/END markers

    Args:
        session: The tmux session.
        server_name: Target server name.
        history: Number of history lines (None = visible only).
        all_output: Read all scrollback.
        marker: Read output between specific markers.

    Returns:
        The captured output string.
    """
    window = find_window(session, server_name)
    window_target = window.window_id

    if marker:
        # Extract content between markers
        full_output = _tmux_capture_pane(window_target, history=5000)
        return _extract_marker_output(full_output, marker)

    if all_output:
        return _tmux_capture_pane(window_target, history=-1)

    if history is not None:
        # Negative start line for history
        start_line = -history
        return _tmux_capture_pane(window_target, history=start_line)

    # Default: visible content only
    return _tmux_capture_pane(window_target)


# ---------------------------------------------------------------------------
# Window listing (list subcommand)
# ---------------------------------------------------------------------------


def list_windows(
    session: libtmux.Session,
    raw: bool = False,
) -> list[WindowInfo]:
    """List active windows in a session.

    Args:
        session: The tmux session.
        raw: If True, return detailed info including tmux markers.

    Returns:
        List of WindowInfo objects.
    """
    windows = []
    for window in session.windows:
        name = window.window_name or ""
        # Strip tmux activity markers from name for display
        clean_name = _strip_tmux_markers(name)

        windows.append(
            WindowInfo(
                window_id=window.window_id,
                name=clean_name,
                active=name.endswith("*"),
            )
        )
    return windows


def format_window_list(windows: list[WindowInfo], raw: bool = False) -> str:
    """Format window list for display.

    Args:
        windows: List of WindowInfo objects.
        raw: If True, include window IDs and activity markers.

    Returns:
        Formatted string for display.
    """
    if raw:
        lines = []
        for w in windows:
            marker = "*" if w.active else " "
            lines.append(f"{w.window_id} {marker} {w.name}")
        return "\n".join(lines)

    # Default: just server names, skip 'bash'
    names = [w.name for w in windows if w.name != "bash"]
    return "\n".join(names)


# ---------------------------------------------------------------------------
# Session creation (session subcommand)
# ---------------------------------------------------------------------------


def create_session(
    session_name: str,
    servers: list[str],
    attach: bool = False,
) -> libtmux.Session:
    """Create a tmux session with SSH windows for multiple servers.

    Mirrors the bash 'session' subcommand:
    - First server creates the session
    - Additional servers create new windows
    - Attach only if session was newly created

    Args:
        session_name: The tmux session name.
        servers: List of server names.
        attach: Whether to attach to the session after creation.

    Returns:
        The libtmux Session object.

    Raises:
        TmuxCoreError: If session_name is empty or no servers provided.
    """
    if not session_name:
        raise TmuxCoreError("No session specified. Use -s option or set session.name in config.")

    if not servers:
        raise TmuxCoreError("No servers specified and none configured.")

    server = _get_server()

    # Check if session already exists
    existing = None
    try:
        existing = server.find_where({"session_name": session_name})
    except Exception:
        pass

    session_created = False

    if existing is not None:
        session_obj = existing
    else:
        # Create session with first server
        first_server = servers[0]
        try:
            session_obj = server.new_session(
                session_name,
                window_name=first_server,
                window_shell=f"ssh {first_server}",
                detach=True,
            )
            session_created = True
        except libtmux.LibTmuxException as exc:
            raise TmuxCoreError(f"Failed to create session '{session_name}': {exc}") from exc

    # Create windows for all servers
    # When session is new, first server already has a window from session creation
    # When session exists, all servers need windows
    start_idx = 1 if session_created else 0
    for srv in servers[start_idx:]:
        try:
            # Check if window already exists
            if _find_window_by_name(session_obj, srv) is None:
                session_obj.new_window(window_name=srv, window_shell=f"ssh {srv}")
        except libtmux.LibTmuxException:
            # Non-fatal: continue creating other windows
            pass

    return session_obj


def session_exists(session_name: str) -> bool:
    """Check if a tmux session exists.

    Args:
        session_name: The session name to check.

    Returns:
        True if the session exists, False otherwise.
    """
    server = _get_server()
    try:
        session = server.find_where({"session_name": session_name})
        return session is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Low-level tmux helpers (subprocess-based for reliability)
# ---------------------------------------------------------------------------


def _tmux_send_keys(target: str, text: str) -> None:
    """Send keys to a tmux window.

    Uses subprocess to call tmux send-keys directly for maximum compatibility.

    Args:
        target: The tmux target (window ID).
        text: The text to send.
    """
    subprocess.run(
        ["tmux", "send-keys", "-t", target, text],
        check=True,
        capture_output=True,
    )
    # Send Enter separately (matches bash: ... Enter)
    # Actually, bash appends Enter at the end of the whole send-keys command
    # The text already contains the full command, so we need to press Enter
    subprocess.run(
        ["tmux", "send-keys", "-t", target, "Enter"],
        check=True,
        capture_output=True,
    )


def _tmux_capture_pane(target: str, history: int | None = None) -> str:
    """Capture pane content from tmux.

    Args:
        target: The tmux target (window ID).
        history: Start line (-N for N lines of history, -1 for all).
                 None means visible content only.

    Returns:
        The captured text.
    """
    cmd = ["tmux", "capture-pane", "-t", target, "-p"]

    if history is not None:
        cmd.extend(["-S", str(history)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout


# ---------------------------------------------------------------------------
# Marker parsing helpers
# ---------------------------------------------------------------------------


def _has_end_marker(screen_output: str, marker: str) -> bool:
    """Check if the END marker appears in the screen output.

    Matches the bash regex: ^=== END $marker (EXITCODE=|INTERRUPTED|TERMINATED|HANGUP|KILLED)
    """
    pattern = f"^=== END {marker} (EXITCODE=|INTERRUPTED|TERMINATED|HANGUP|KILLED)"
    for line in screen_output.splitlines():
        if re.match(pattern, line):
            return True
    return False


def _extract_between_markers(text: str, marker: str, include_end: bool = True) -> str:
    """Extract content between START and END markers.

    Args:
        text: The full pane capture.
        marker: The marker identifier.
        include_end: If True, include END marker line; if False, stop at START.

    Returns:
        The content between markers (including marker lines if include_end).
    """
    start_pattern = f"=== START {marker} ==="
    end_pattern = f"=== END {marker}"

    lines = text.splitlines()
    in_block = False
    result_lines: list[str] = []

    for line in lines:
        if line == start_pattern:
            in_block = True
            result_lines.append(line)
            continue

        if in_block and line.startswith(end_pattern):
            if include_end:
                result_lines.append(line)
            break

        if in_block:
            result_lines.append(line)

    return "\n".join(result_lines)


def _extract_marker_output(text: str, marker: str) -> str:
    """Extract output between markers for the read --marker command.

    Returns content between START and END markers, excluding the marker lines themselves.
    Matches bash: sed -En "/^=== START $marker ===/,/^=== END $marker .../p"
    then strips first and last lines.
    """
    content = _extract_between_markers(text, marker, include_end=True)
    lines = content.splitlines()

    if len(lines) <= 2:
        # Just markers or empty
        return ""

    # Remove first (START) and last (END) lines
    return "\n".join(lines[1:-1])


def _parse_exit_code(marker_content: str, marker: str) -> int:
    """Parse the exit code from the END marker line.

    Handles EXITCODE=N and signal-based markers.
    """
    end_line = ""
    end_prefix = f"=== END {marker} "
    for line in marker_content.splitlines():
        if line.startswith(end_prefix):
            end_line = line
            break

    if not end_line:
        return 0

    # Check signal markers
    for signal_name, code in SIGNAL_EXIT_CODES.items():
        if signal_name in end_line:
            return code

    # Parse EXITCODE=N
    match = re.search(r"EXITCODE=(\d+)", end_line)
    if match:
        return int(match.group(1))

    return 0


def _strip_marker_lines(content: str) -> str:
    """Remove START and END marker lines from content."""
    lines = content.splitlines()

    # Remove first and last lines if they are marker lines
    if lines and lines[0].startswith("=== START "):
        lines = lines[1:]
    if lines and lines[-1].startswith("=== END "):
        lines = lines[:-1]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TmuxCoreError(Exception):
    """Error in tmux core operations."""

    pass
