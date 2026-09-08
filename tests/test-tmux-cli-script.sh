#!/bin/bash

# Headless integration tests for cca-tmux-cli run --script.

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CLI="$SCRIPT_DIR/../bin/cca-tmux-cli"
TEST_TMP=$(mktemp -d)
FAKE_BIN="$TEST_TMP/bin"
FAKE_STATE="$TEST_TMP/state"
mkdir -p "$FAKE_BIN" "$FAKE_STATE"
trap 'rm -rf "$TEST_TMP"' EXIT

cat >"$FAKE_BIN/tmux" <<'FAKE_TMUX'
#!/bin/bash
case "$1" in
has-session)
    exit 0
    ;;
list-windows)
    echo '@1 server1'
    ;;
send-keys)
    command=${*: -2:1}
    printf '%s' "$command" >"$FAKE_TMUX_STATE/sent-command"
    if [ "${FAKE_TMUX_TIMEOUT:-false}" = true ]; then
        marker=$(printf '%s' "$command" | sed -n "s/.*=== START \([^ ]*\) ===.*/\1/p")
        printf '=== START %s ===\nstill running\n' "$marker" >"$FAKE_TMUX_STATE/pane"
    else
        bash -c "$command" >"$FAKE_TMUX_STATE/pane" 2>&1
    fi
    ;;
capture-pane)
    cat "$FAKE_TMUX_STATE/pane"
    ;;
*)
    echo "unexpected tmux command: $*" >&2
    exit 99
    ;;
esac
FAKE_TMUX
chmod +x "$FAKE_BIN/tmux"

cat >"$FAKE_BIN/sleep" <<'FAKE_SLEEP'
#!/bin/bash
exit 0
FAKE_SLEEP
chmod +x "$FAKE_BIN/sleep"

export PATH="$FAKE_BIN:$PATH"
export FAKE_TMUX_STATE="$FAKE_STATE"
export TMUX_SESSION_NAME="cca-test"
export ADMIN_NAME="test"

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
    RUN_OUTPUT=$(cd "$TEST_TMP" && "$CLI" -t server1 "$@" 2>&1)
    RUN_STATUS=$?
}

assert_status() {
    local name=$1 expected=$2
    if [ "$RUN_STATUS" -eq "$expected" ]; then
        pass "$name"
    else
        fail "$name (expected status $expected, got $RUN_STATUS: $RUN_OUTPUT)"
    fi
}

assert_output() {
    local name=$1 expected=$2
    if [ "$RUN_OUTPUT" = "$expected" ]; then
        pass "$name"
    else
        fail "$name (unexpected output: $RUN_OUTPUT)"
    fi
}

decoded_sent_script() {
    sed -n "s/.*echo '\([^']*\)' | base64 -d.*/\1/p" "$FAKE_STATE/sent-command" |
        head -n 1 | base64 -d
}

# This literal quoted heredoc is the supported caller form. Its contents must
# reach the remote Bash without local expansion or quote interpretation.
RUN_OUTPUT=$(cd "$TEST_TMP" && "$CLI" -t server1 run --script 2>&1 <<'REMOTE'
cat <<'PAYLOAD'
spaces: two words
utf8: Příliš žluťoučký kůň
dollar: $HOME $(printf evaluated)
backticks: `printf evaluated`
quotes: "double" and 'single'
backslash: C:\tmp\file
operators: left | right > file *
PAYLOAD
REMOTE
)
RUN_STATUS=$?
expected=$(cat <<'EXPECTED'
spaces: two words
utf8: Příliš žluťoučký kůň
dollar: $HOME $(printf evaluated)
backticks: `printf evaluated`
quotes: "double" and 'single'
backslash: C:\tmp\file
operators: left | right > file *
EXPECTED
)
assert_status "literal multiline script succeeds" 0
assert_output "literal multiline script output" "$expected"

RUN_OUTPUT=$(cd "$TEST_TMP" && "$CLI" -t server1 run --script 2>&1 <<'REMOTE'
python3 - <<'PY'
print("line 1")
print("line 2")
PY
REMOTE
)
RUN_STATUS=$?
assert_status "multiline Python succeeds" 0
assert_output "multiline Python output" $'line 1\nline 2'

script_file="$TEST_TMP/trailing-newlines"
printf '%s\n\n\n' 'printf preserved' >"$script_file"
run_cli run --script <"$script_file"
decoded_file="$TEST_TMP/decoded-script"
decoded_sent_script >"$decoded_file"
if cmp -s "$script_file" "$decoded_file"; then
    pass "trailing newlines preserved exactly"
else
    fail "trailing newlines preserved exactly"
fi

run_cli run --script </dev/null
assert_status "empty script rejected" 64

run_cli run --script 'echo mixed'
assert_status "script and positional command rejected" 64

run_cli run --timeout 1 --script --timeout 99
assert_status "wrapper-looking token after script rejected" 64

run_cli run --script --interval 9
assert_status "interval token after script rejected" 64

run_cli run 'echo legacy' --script </dev/null
assert_status "positional command before script rejected" 64

run_cli run --script <<'REMOTE'
exit 23
REMOTE
assert_status "ordinary nonzero status propagated" 23

run_cli run --script <<'REMOTE'
command_that_does_not_exist_for_cca_test
REMOTE
assert_status "command-not-found status propagated" 127

FAKE_TMUX_TIMEOUT=true run_cli run --interval 1 --timeout 1 --script <<'REMOTE'
printf 'never completed\n'
REMOTE
assert_status "script timeout status propagated" 124
if head -n 1 "$FAKE_STATE/pane" | grep -q '^=== START TMUX_MARKER_' &&
    [[ "$RUN_OUTPUT" == *"Check if finished later: cca-tmux-cli read --marker \"TMUX_MARKER_"* ]]; then
    pass "timeout retains marker recovery output"
else
    fail "timeout retains marker recovery output"
fi

run_cli run "uptime"
assert_status "legacy uptime succeeds" 0
if [[ "$RUN_OUTPUT" == *"load average"* ]] || [[ "$RUN_OUTPUT" == *"load averages"* ]]; then
    pass "legacy uptime output"
else
    fail "legacy uptime output (unexpected output: $RUN_OUTPUT)"
fi

run_cli run "cat /etc/hostname"
assert_status "legacy hostname command succeeds" 0
if [ -n "$RUN_OUTPUT" ]; then
    pass "legacy hostname command output"
else
    fail "legacy hostname command output"
fi

help_output=$(cd "$TEST_TMP" && "$CLI" --help)
if [[ "$help_output" == *"run --script <<'REMOTE'"* ]] &&
    [[ "$help_output" == *"only supported multiline command form"* ]]; then
    pass "help documents direct quoted heredoc"
else
    fail "help documents direct quoted heredoc"
fi

robot_help_output=$(cd "$TEST_TMP" && "$CLI" --robot-help)
if [[ "$robot_help_output" == *"run --script <<'REMOTE'"* ]] &&
    [[ "$robot_help_output" == *"only supported multiline form"* ]]; then
    pass "robot help documents direct quoted heredoc"
else
    fail "robot help documents direct quoted heredoc"
fi

echo
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[ "$FAILED" -eq 0 ]
