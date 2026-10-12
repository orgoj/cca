#!/bin/bash

# Headless integration tests for cca-tmux-cli run --script.

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CLI="$SCRIPT_DIR/../bin/cca-tmux-cli"
TEST_TMP=$(mktemp -d)
FAKE_BIN="$TEST_TMP/bin"
FAKE_STATE="$TEST_TMP/state"
TOKF_TMP="$TEST_TMP/tokf-tmp"
NO_TOKF_BIN="$TEST_TMP/no-tokf-bin"
mkdir -p "$FAKE_BIN" "$FAKE_STATE" "$TOKF_TMP" "$NO_TOKF_BIN"
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
        marker=$(printf '%s' "$command" | sed -n "s/.*echo '\(TMUX_MARKER_[^ ]*\) ===.*/\1/p")
        printf '=== START %s ===\nstill running\n' "$marker" >"$FAKE_TMUX_STATE/pane"
    elif [ "${FAKE_TMUX_WRAP_TYPED:-false}" = true ]; then
        # Echo the typed command as tmux shows it, wrapped right before each
        # "=== START " so a wrapped line starts with the START marker text.
        printf '$ %s\n' "$command" | sed 's/=== START /\n&/g' >"$FAKE_TMUX_STATE/pane"
        bash -c "$command" >>"$FAKE_TMUX_STATE/pane" 2>&1
    else
        bash -c "$command" >"$FAKE_TMUX_STATE/pane" 2>&1
    fi
    ;;
capture-pane)
    if [[ " $* " == *" -S -5000 "* ]]; then
        case "${FAKE_TMUX_CAPTURE_MODE:-}" in
        missing-start)
            tail -n 1 "$FAKE_TMUX_STATE/pane"
            exit 0
            ;;
        missing-end)
            sed '$d' "$FAKE_TMUX_STATE/pane"
            exit 0
            ;;
        empty-history)
            exit 0
            ;;
        capture-fail)
            exit 75
            ;;
        esac
    fi
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

cat >"$FAKE_BIN/tokf" <<'FAKE_TOKF'
#!/bin/bash
printf 'call\n' >>"$FAKE_TMUX_STATE/tokf-calls"

if [ "$1" = process ] && [ "${2:-}" = --supports-protocol ] && [ "${3:-}" = cca-v1 ]; then
    printf 'probe\n' >>"$FAKE_TMUX_STATE/tokf-probes"
    printf 'probe stdout must be suppressed\n'
    printf 'probe stderr must be suppressed\n' >&2
    if [ "${FAKE_TOKF_MODE:-success}" = probe-fail ]; then
        exit 64
    fi
    if [ "${FAKE_TOKF_MODE:-success}" = vanish ]; then
        chmod -x "$0"
    fi
    exit 0
fi

printf 'process\n' >>"$FAKE_TMUX_STATE/tokf-processes"
printf '%s' "$0" >"$FAKE_TMUX_STATE/tokf-path"
shift
while [ $# -gt 0 ]; do
    case "$1" in
    --protocol)
        printf '%s' "$2" >"$FAKE_TMUX_STATE/tokf-protocol"
        shift 2
        ;;
    --return-processor-status)
        printf 'yes' >"$FAKE_TMUX_STATE/tokf-processor-status"
        shift
        ;;
    --command)
        printf '%s' "$2" >"$FAKE_TMUX_STATE/tokf-command"
        shift 2
        ;;
    --exit-code)
        printf '%s' "$2" >"$FAKE_TMUX_STATE/tokf-exit-code"
        shift 2
        ;;
    *)
        printf 'unexpected argument: %s\n' "$1" >&2
        exit 65
        ;;
    esac
done
if [ "${FAKE_TOKF_MODE:-success}" = read-fail ]; then
    printf 'tokf read failure\n' >&2
    exit 74
fi
cat >"$FAKE_TMUX_STATE/tokf-stdin"

case "${FAKE_TOKF_MODE:-success}" in
success | vanish)
    printf 'processed output\n'
    ;;
echo)
    cat "$FAKE_TMUX_STATE/tokf-stdin"
    ;;
partial-fail)
    printf 'partial processed output\n'
    printf 'tokf diagnostic\n' >&2
    exit 75
    ;;
pipe-fail)
    printf 'partial pipe output\n'
    exit 141
    ;;
unexpected)
    printf 'unexpected processed output\n'
    exit 42
    ;;
esac
FAKE_TOKF
chmod +x "$FAKE_BIN/tokf"

cat >"$FAKE_BIN/mktemp" <<'FAKE_MKTEMP'
#!/bin/bash
result=$(/usr/bin/mktemp "$@") || exit $?
if [ "${FAKE_MKTEMP_MODE:-}" = unwritable ]; then
    chmod 500 "$result"
fi
printf '%s\n' "$result"
FAKE_MKTEMP
chmod +x "$FAKE_BIN/mktemp"

ln -s "$FAKE_BIN/tmux" "$NO_TOKF_BIN/tmux"
ln -s "$FAKE_BIN/sleep" "$NO_TOKF_BIN/sleep"

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

run_tokf_cli() {
    local mode=$1
    shift
    RUN_OUTPUT=$(cd "$TEST_TMP" && CCA_TMUX_TOKF=1 FAKE_TOKF_MODE="$mode" TMPDIR="$TOKF_TMP" \
        "$CLI" -t server1 "$@" 2>&1)
    RUN_STATUS=$?
}

reset_tokf_state() {
    rm -f "$FAKE_STATE"/tokf-*
    chmod +x "$FAKE_BIN/tokf"
}

tokf_call_count() {
    if [ -f "$FAKE_STATE/tokf-calls" ]; then
        wc -l <"$FAKE_STATE/tokf-calls" | tr -d ' '
    else
        printf '0\n'
    fi
}

tokf_process_count() {
    if [ -f "$FAKE_STATE/tokf-processes" ]; then
        wc -l <"$FAKE_STATE/tokf-processes" | tr -d ' '
    else
        printf '0\n'
    fi
}

tokf_probe_count() {
    if [ -f "$FAKE_STATE/tokf-probes" ]; then
        wc -l <"$FAKE_STATE/tokf-probes" | tr -d ' '
    else
        printf '0\n'
    fi
}

assert_tokf_temp_clean() {
    local name=$1
    if find "$TOKF_TMP" -mindepth 1 -print -quit | grep -q .; then
        fail "$name (processing tempfiles remain)"
    else
        pass "$name"
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

run_cli run --script <<'REMOTE'
:
REMOTE
assert_status "valid markers with empty body succeed" 0
assert_output "valid markers with empty body produce empty output" ""

FAKE_TMUX_CAPTURE_MODE=missing-start run_cli run --script <<'REMOTE'
printf 'uncaptured output\n'
REMOTE
assert_status "missing START marker fails locally" 70
if [[ "$RUN_OUTPUT" == *"Incomplete tmux command output (missing START or END marker:"* ]] &&
    [[ "$RUN_OUTPUT" == *"cca-tmux-cli read --all"* ]] &&
    [[ "$RUN_OUTPUT" != *"uncaptured output"* ]]; then
    pass "missing START marker reports recovery command without partial output"
else
    fail "missing START marker reports recovery command without partial output"
fi

FAKE_TMUX_CAPTURE_MODE=empty-history run_cli run --script <<'REMOTE'
printf 'uncaptured output\n'
REMOTE
assert_status "empty final capture fails locally" 70
if [[ "$RUN_OUTPUT" == *"Incomplete tmux command output (missing START or END marker:"* ]]; then
    pass "empty final capture reports missing markers"
else
    fail "empty final capture reports missing markers"
fi

FAKE_TMUX_CAPTURE_MODE=missing-end run_cli run --script <<'REMOTE'
printf 'uncaptured output\n'
REMOTE
assert_status "missing END marker fails locally" 70
if [[ "$RUN_OUTPUT" == *"Incomplete tmux command output (missing START or END marker:"* ]] &&
    [[ "$RUN_OUTPUT" != *"uncaptured output"* ]]; then
    pass "missing END marker rejects partial output"
else
    fail "missing END marker rejects partial output"
fi

FAKE_TMUX_CAPTURE_MODE=capture-fail run_cli run --script <<'REMOTE'
printf 'uncaptured output\n'
REMOTE
assert_status "failed final capture fails locally" 70
if [[ "$RUN_OUTPUT" == *"Failed to capture command output from tmux"* ]]; then
    pass "failed final capture reports capture error"
else
    fail "failed final capture reports capture error"
fi

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

FAKE_TMUX_WRAP_TYPED=true run_cli run "printf '0\n'; exit 1"
assert_status "wrapped typed command keeps nonzero status" 1
assert_output "wrapped typed command does not fake START marker" "0"

run_cli run --timeout 1 --script <<'REMOTE'
exit 23
REMOTE
assert_status "completion at first poll beats timeout" 23

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

# tokf captured-output processing is strictly opt-in and fail-open.
unset CCA_TMUX_TOKF
for tokf_setting in unset empty 0 other; do
    reset_tokf_state
    case "$tokf_setting" in
    unset)
        RUN_OUTPUT=$(cd "$TEST_TMP" && TMPDIR="$TOKF_TMP" "$CLI" -t server1 run "printf 'raw disabled'" 2>&1)
        ;;
    empty)
        RUN_OUTPUT=$(cd "$TEST_TMP" && CCA_TMUX_TOKF='' TMPDIR="$TOKF_TMP" "$CLI" -t server1 run "printf 'raw disabled'" 2>&1)
        ;;
    0)
        RUN_OUTPUT=$(cd "$TEST_TMP" && CCA_TMUX_TOKF=0 TMPDIR="$TOKF_TMP" "$CLI" -t server1 run "printf 'raw disabled'" 2>&1)
        ;;
    other)
        RUN_OUTPUT=$(cd "$TEST_TMP" && CCA_TMUX_TOKF=yes TMPDIR="$TOKF_TMP" "$CLI" -t server1 run "printf 'raw disabled'" 2>&1)
        ;;
    esac
    RUN_STATUS=$?
    assert_status "tokf $tokf_setting setting preserves status" 0
    assert_output "tokf $tokf_setting setting preserves output" "raw disabled"
    if [ "$(tokf_call_count)" -eq 0 ]; then
        pass "tokf $tokf_setting setting does not probe"
    else
        fail "tokf $tokf_setting setting does not probe"
    fi
    assert_tokf_temp_clean "tokf $tokf_setting setting creates no tempfiles"
done

reset_tokf_state
RUN_OUTPUT=$(cd "$TEST_TMP" && PATH="$NO_TOKF_BIN:/usr/bin:/bin" CCA_TMUX_TOKF=1 TMPDIR="$TOKF_TMP" \
    "$CLI" -t server1 run "printf 'raw missing'" 2>&1)
RUN_STATUS=$?
assert_status "missing tokf preserves status" 0
assert_output "missing tokf preserves raw output" "raw missing"
assert_tokf_temp_clean "missing tokf creates no processing tempfiles"

reset_tokf_state
run_tokf_cli probe-fail run "printf 'raw old tokf'"
assert_status "old tokf preserves status" 0
assert_output "old tokf preserves raw output" "raw old tokf"
if [ "$(tokf_probe_count)" -eq 1 ] && [ "$(tokf_process_count)" -eq 0 ]; then
    pass "old tokf is probed once and never processes"
else
    fail "old tokf is probed once and never processes"
fi
assert_tokf_temp_clean "old tokf creates no processing tempfiles"

reset_tokf_state
FAKE_TMUX_CAPTURE_MODE=missing-start run_tokf_cli success run "printf 'uncaptured output'"
assert_status "tokf skips incomplete capture" 70
if [ "$(tokf_process_count)" -eq 0 ]; then
    pass "tokf does not process incomplete output"
else
    fail "tokf does not process incomplete output"
fi

reset_tokf_state
simple_source="printf 'raw combined\\n'; exit 23"
run_tokf_cli success run "$simple_source"
assert_status "tokf preserves nonzero remote status" 23
assert_output "tokf processor success emits processed output" "processed output"
if [ "$(tokf_probe_count)" -eq 1 ] && [ "$(tokf_process_count)" -eq 1 ]; then
    pass "tokf is probed exactly once before processing"
else
    fail "tokf is probed exactly once before processing"
fi
if [ "$(cat "$FAKE_STATE/tokf-command")" = "$simple_source" ] &&
    [ "$(cat "$FAKE_STATE/tokf-exit-code")" = 23 ] &&
    [ "$(cat "$FAKE_STATE/tokf-protocol")" = cca-v1 ] &&
    [ "$(cat "$FAKE_STATE/tokf-processor-status")" = yes ] &&
    [ "$(cat "$FAKE_STATE/tokf-path")" = "$FAKE_BIN/tokf" ]; then
    pass "tokf receives exact command, status, protocol, processor mode, and absolute path"
else
    fail "tokf receives exact command, status, protocol, processor mode, and absolute path"
fi
printf 'raw combined\n\n' >"$TEST_TMP/expected-combined"
if cmp -s "$TEST_TMP/expected-combined" "$FAKE_STATE/tokf-stdin"; then
    pass "tokf receives exact current-behavior combined body"
else
    fail "tokf receives exact current-behavior combined body"
fi
assert_tokf_temp_clean "successful tokf processing cleans tempfiles"

reset_tokf_state
cat >"$TEST_TMP/expected-tokf-script" <<'REMOTE'
cat <<'PAYLOAD'
literal: $HOME $(printf not-local) `printf not-local`
PAYLOAD
REMOTE
run_tokf_cli echo run --script <"$TEST_TMP/expected-tokf-script"
assert_status "tokf multiline heredoc preserves status" 0
# shellcheck disable=SC2016  # Literal expansion syntax must survive unchanged.
assert_output "tokf multiline heredoc output" 'literal: $HOME $(printf not-local) `printf not-local`'
if cmp -s "$TEST_TMP/expected-tokf-script" "$FAKE_STATE/tokf-command"; then
    pass "tokf receives multiline heredoc source as one exact argv"
else
    fail "tokf receives multiline heredoc source as one exact argv"
fi

reset_tokf_state
run_tokf_cli echo run --script <<'REMOTE'
printf 'line


'
REMOTE
printf 'line\n\n\n\n' >"$TEST_TMP/expected-trailing-output"
if cmp -s "$TEST_TMP/expected-trailing-output" "$FAKE_STATE/tokf-stdin"; then
    pass "tokf stdin preserves current combined trailing blank lines"
else
    fail "tokf stdin preserves current combined trailing blank lines"
fi

reset_tokf_state
run_tokf_cli echo run ":"
assert_status "tokf empty output preserves status" 0
assert_output "tokf empty output stays empty" ""
printf '\n' >"$TEST_TMP/expected-empty-body"
if cmp -s "$TEST_TMP/expected-empty-body" "$FAKE_STATE/tokf-stdin"; then
    pass "tokf receives current empty-command terminal body"
else
    fail "tokf receives current empty-command terminal body"
fi

for remote_status in 0 1 23 127 129 130 137 143; do
    reset_tokf_state
    run_tokf_cli success run "printf 'status $remote_status'; exit $remote_status"
    assert_status "tokf preserves remote status $remote_status" "$remote_status"
    assert_output "tokf processes remote status $remote_status" "processed output"
done

reset_tokf_state
run_tokf_cli partial-fail run "printf 'raw after processor failure'; exit 23"
assert_status "tokf processor failure preserves remote status" 23
assert_output "tokf processor failure discards partial output silently" "raw after processor failure"
assert_tokf_temp_clean "tokf processor failure cleans tempfiles"

reset_tokf_state
run_tokf_cli read-fail run "printf 'raw after read failure'; exit 23"
assert_status "tokf read failure preserves remote status" 23
assert_output "tokf read failure falls back silently" "raw after read failure"

reset_tokf_state
run_tokf_cli pipe-fail run "printf 'raw after pipe failure'; exit 23"
assert_status "tokf pipe failure preserves remote status" 23
assert_output "tokf pipe failure discards partial output" "raw after pipe failure"

reset_tokf_state
run_tokf_cli unexpected run "printf 'raw after unexpected status'; exit 1"
assert_status "unexpected tokf status preserves remote status" 1
assert_output "unexpected tokf status falls back to raw" "raw after unexpected status"

reset_tokf_state
run_tokf_cli vanish run "printf 'raw after spawn failure'; exit 127"
assert_status "tokf spawn failure preserves colliding remote status" 127
assert_output "tokf spawn failure falls back to raw" "raw after spawn failure"
chmod +x "$FAKE_BIN/tokf"

reset_tokf_state
printf 'not a directory\n' >"$TEST_TMP/not-a-temp-dir"
RUN_OUTPUT=$(cd "$TEST_TMP" && CCA_TMUX_TOKF=1 FAKE_TOKF_MODE=success TMPDIR="$TEST_TMP/not-a-temp-dir" \
    "$CLI" -t server1 run "printf 'raw after tempfile failure'" 2>&1)
RUN_STATUS=$?
assert_status "tokf tempfile failure preserves status" 0
assert_output "tokf tempfile failure falls back silently" "raw after tempfile failure"

reset_tokf_state
FAKE_MKTEMP_MODE=unwritable run_tokf_cli success run "printf 'raw after write failure'"
assert_status "tokf raw-buffer write failure preserves status" 0
assert_output "tokf raw-buffer write failure falls back silently" "raw after write failure"
assert_tokf_temp_clean "tokf raw-buffer write failure cleans tempfiles"

reset_tokf_state
RUN_OUTPUT=$(cd "$TEST_TMP" && CCA_TMUX_TOKF=1 FAKE_TOKF_MODE=partial-fail TMPDIR="$TOKF_TMP" \
    "$CLI" -x -t server1 run "printf 'raw debug diagnostic'" 2>&1)
RUN_STATUS=$?
assert_status "tokf debug failure preserves status" 0
if [[ "$RUN_OUTPUT" == *"raw debug diagnostic"* ]] && [[ "$RUN_OUTPUT" == *"tokf diagnostic"* ]] &&
    [[ "$RUN_OUTPUT" != *"partial processed output"* ]]; then
    pass "tokf diagnostics appear only in debug without partial payload"
else
    fail "tokf diagnostics appear only in debug without partial payload"
fi

reset_tokf_state
FAKE_TMUX_TIMEOUT=true run_tokf_cli success run --interval 1 --timeout 1 --script <<'REMOTE'
printf 'never completed\n'
REMOTE
assert_status "tokf-enabled timeout preserves status" 124
if [ "$(tokf_probe_count)" -eq 1 ] && [ "$(tokf_process_count)" -eq 0 ]; then
    pass "timeout probes capability but never processes partial output"
else
    fail "timeout probes capability but never processes partial output"
fi

reset_tokf_state
RUN_OUTPUT=$(cd "$TEST_TMP" && CCA_TMUX_TOKF=1 "$CLI" -t server1 read --all 2>&1)
RUN_STATUS=$?
assert_status "tokf-enabled read preserves status" 0
if [ "$(tokf_call_count)" -eq 0 ]; then
    pass "read recovery never probes or processes with tokf"
else
    fail "read recovery never probes or processes with tokf"
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
    [[ "$help_output" == *"only supported multiline command form"* ]] &&
    [[ "$help_output" == *"CCA_TMUX_TOKF"* ]] &&
    [[ "$help_output" == *"combined terminal body"* ]]; then
    pass "help documents direct quoted heredoc"
else
    fail "help documents direct quoted heredoc"
fi

version_output=$(cd "$TEST_TMP" && "$CLI" --version)
if [[ "$help_output" == *"cca-tmux-cli v$version_output "* ]]; then
    pass "help and version output stay synchronized"
else
    fail "help and version output stay synchronized"
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
