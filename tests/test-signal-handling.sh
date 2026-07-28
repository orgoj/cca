#!/bin/bash
# Test script for signal handling in cca-tmux
# Usage: ./test-signal-handling.sh SERVER_NAME

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="${1:-localhost}"

# Ignore signals in test script so they don't interrupt us
trap '' INT TERM

echo "=== Testing cca-tmux signal handling ==="
echo "Server: $SERVER"
echo ""

# Test 1: Normal exit (EXITCODE=0)
echo "Test 1: Normal exit (EXITCODE=0)"
output=$("$SCRIPT_DIR/../bin/cca-tmux" -t "$SERVER" run "echo hello" 2>&1) || true
if echo "$output" | grep -q "hello"; then
    echo "  PASS: Command executed, output: $output"
else
    echo "  FAIL: Expected 'hello' in output"
    echo "  Got: $output"
fi
echo ""

# Test 2: Non-zero exit (EXITCODE=42)
echo "Test 2: Non-zero exit (EXITCODE=42)"
exitcode=0
"$SCRIPT_DIR/../bin/cca-tmux" -t "$SERVER" run "exit 42" 2>&1 || exitcode=$?
if [[ "$exitcode" -eq 42 ]]; then
    echo "  PASS: Exit code is 42"
else
    echo "  FAIL: Expected exit code 42, got: $exitcode"
fi
echo ""

# Test 3: SIGINT (Ctrl-C)
echo "Test 3: SIGINT (Ctrl-C)"
echo "  Starting sleep 30 in background with 10s timeout..."
"$SCRIPT_DIR/../bin/cca-tmux" -t "$SERVER" run "sleep 30" --timeout 10 2>&1 &
bg_pid=$!
sleep 2
echo "  Sending Ctrl-C to tmux window '$SERVER'..."
# Send Ctrl-C directly to the server window (cca-tmux uses window name = server name)
tmux send-keys -t "$SERVER" C-c
echo "  Waiting for cca-tmux to complete..."
wait $bg_pid 2>/dev/null || true
sleep 1
# Now check the last marker (only AFTER cca-tmux run completed)
last_marker=$("$SCRIPT_DIR/../bin/cca-tmux" -t "$SERVER" read --all 2>&1 | grep -E "^=== END.*===$" | tail -1)
if echo "$last_marker" | grep -q "INTERRUPTED"; then
    echo "  PASS: Found INTERRUPTED marker"
    echo "  Marker: $last_marker"
else
    echo "  FAIL: Expected INTERRUPTED marker"
    echo "  Last marker: $last_marker"
fi
echo ""

# Test 4: SIGTERM (kill) - skip if localhost (can't kill remote process easily)
echo "Test 4: SIGTERM (kill)"
echo "  Starting 'sleep 30' and will kill the sleep process..."
"$SCRIPT_DIR/../bin/cca-tmux" -t "$SERVER" run 'echo "TEST4_PID=$$"; sleep 30' --timeout 10 2>&1 &
bg_pid=$!
sleep 2
# Read the PID from tmux pane directly (not via cca-tmux which would conflict)
tmux_output=$(tmux capture-pane -t "$SERVER" -p 2>/dev/null)
sleep_pid=$(echo "$tmux_output" | grep -oP 'TEST4_PID=\K[0-9]+' | tail -1)
if [[ -n "$sleep_pid" ]]; then
    echo "  Found PID: $sleep_pid, sending SIGTERM..."
    kill "$sleep_pid" 2>/dev/null || true
else
    echo "  WARNING: Could not extract PID, sending Ctrl-C instead"
    tmux send-keys -t "$SERVER" C-c
fi
echo "  Waiting for cca-tmux to complete..."
wait $bg_pid 2>/dev/null || true
sleep 1
last_marker=$("$SCRIPT_DIR/../bin/cca-tmux" -t "$SERVER" read --all 2>&1 | grep -E "^=== END.*===$" | tail -1)
if echo "$last_marker" | grep -q "TERMINATED"; then
    echo "  PASS: Found TERMINATED marker"
    echo "  Marker: $last_marker"
elif echo "$last_marker" | grep -q "INTERRUPTED"; then
    echo "  INFO: Got INTERRUPTED (Ctrl-C fallback worked)"
    echo "  Marker: $last_marker"
else
    echo "  FAIL: Expected TERMINATED or INTERRUPTED marker"
    echo "  Last marker: $last_marker"
fi
echo ""

echo "=== Tests completed ==="
