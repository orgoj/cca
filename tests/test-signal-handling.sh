#!/bin/bash
# Signal handling of cca-tmux-cli run against a real, private tmux server.
# Never touches the user's tmux: the server socket lives in its own TMUX_TMPDIR.

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CLI="$SCRIPT_DIR/../bin/cca-tmux-cli"

if ! command -v tmux >/dev/null 2>&1; then
    echo "SKIP: tmux not installed"
    exit 0
fi

TEST_TMP=$(mktemp -d)
export TMUX_TMPDIR="$TEST_TMP"
unset TMUX
SESSION="cca-signal-test"
WINDOW="$SESSION:localhost"
trap 'tmux kill-server 2>/dev/null; rm -rf "$TEST_TMP"' EXIT

tmux new-session -d -s "$SESSION" -n localhost -x 200 -y 50 "bash --norc --noprofile"

PASSED=0
FAILED=0
RUN_OUTPUT=""
RUN_STATUS=0

pass() {
    echo "PASS: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "FAIL: $1"
    FAILED=$((FAILED + 1))
}

run_cli() {
    RUN_OUTPUT=$(cd "$TEST_TMP" && "$CLI" -s "$SESSION" -t localhost run --interval 1 --timeout 20 "$@" 2>&1)
    RUN_STATUS=$?
}

# Start run in the background and wait until the command is running
start_bg() {
    (cd "$TEST_TMP" && "$CLI" -s "$SESSION" -t localhost run --interval 1 --timeout 20 "$1" \
        >"$TEST_TMP/bg-output" 2>&1)
}

wait_for_pane() {
    local pattern=$1 _
    for _ in $(seq 1 50); do
        if tmux capture-pane -t "$WINDOW" -p | grep -q "$pattern"; then
            return 0
        fi
        sleep 0.2
    done
    return 1
}

assert_last_end_marker() {
    local name=$1 expected=$2 last
    last=$(tmux capture-pane -t "$WINDOW" -p -S -5000 | grep -E '^=== END TMUX_MARKER_[0-9_]+ .* ===$' | tail -n 1)
    if [[ "$last" == *" $expected ==="* ]]; then
        pass "$name"
    else
        fail "$name (last END marker: $last)"
    fi
}

assert_status() {
    local name=$1 expected=$2
    if [ "$RUN_STATUS" -eq "$expected" ]; then
        pass "$name"
    else
        fail "$name (expected status $expected, got $RUN_STATUS: $RUN_OUTPUT)"
    fi
}

run_cli "echo hello"
assert_status "normal exit status" 0
if [ "$RUN_OUTPUT" = "hello" ]; then
    pass "normal exit output"
else
    fail "normal exit output (got: $RUN_OUTPUT)"
fi

run_cli "exit 42"
assert_status "nonzero exit status" 42

start_bg "echo SIGINT_READY; sleep 30" &
bg_pid=$!
if wait_for_pane '^SIGINT_READY$'; then
    tmux send-keys -t "$WINDOW" C-c
fi
wait "$bg_pid"
RUN_STATUS=$?
RUN_OUTPUT=$(cat "$TEST_TMP/bg-output")
assert_status "Ctrl-C reports INTERRUPTED status" 130
assert_last_end_marker "Ctrl-C prints INTERRUPTED marker" INTERRUPTED

start_bg 'echo "SIGTERM_PID=$$"; sleep 30' &
bg_pid=$!
if wait_for_pane '^SIGTERM_PID=[0-9][0-9]*$'; then
    kill -TERM "$(tmux capture-pane -t "$WINDOW" -p | sed -n 's/^SIGTERM_PID=\([0-9][0-9]*\)$/\1/p' | tail -n 1)"
fi
wait "$bg_pid"
RUN_STATUS=$?
RUN_OUTPUT=$(cat "$TEST_TMP/bg-output")
assert_status "SIGTERM reports TERMINATED status" 143
assert_last_end_marker "SIGTERM prints TERMINATED marker" TERMINATED

run_cli "echo still usable"
assert_status "shell survives signals" 0

echo
echo "Passed: $PASSED, Failed: $FAILED"
[ "$FAILED" -eq 0 ]
