#!/bin/bash

# Headless tests for cca-run-on-server: config loading, logging of failed
# ssh commands, and byte-exact atomic --create-file (ssh and tmux backends).

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CLI="$SCRIPT_DIR/../bin/cca-run-on-server"
TEST_TMP=$(mktemp -d)
FAKE_BIN="$TEST_TMP/bin"
PROJECT="$TEST_TMP/project"
REMOTE="$TEST_TMP/remote"
mkdir -p "$FAKE_BIN" "$PROJECT/.git" "$PROJECT/sub" "$PROJECT/logs" "$REMOTE" "$TEST_TMP/state"
trap 'rm -rf "$TEST_TMP"' EXIT

# Fake ssh: run the remote command locally, passing stdin through
cat >"$FAKE_BIN/ssh" <<'FAKE_SSH'
#!/bin/bash
exec bash -c "$2"
FAKE_SSH
chmod +x "$FAKE_BIN/ssh"

# Minimal fake tmux for the cca-tmux-cli backend
cat >"$FAKE_BIN/tmux" <<'FAKE_TMUX'
#!/bin/bash
case "$1" in
has-session) exit 0 ;;
list-windows) echo '@1 server1' ;;
send-keys) bash -c "${*: -2:1}" >"$FAKE_STATE/pane" 2>&1 ;;
capture-pane) cat "$FAKE_STATE/pane" ;;
*) echo "unexpected tmux command: $*" >&2; exit 99 ;;
esac
FAKE_TMUX
chmod +x "$FAKE_BIN/tmux"
printf '#!/bin/bash\nexit 0\n' >"$FAKE_BIN/sleep"
chmod +x "$FAKE_BIN/sleep"

export PATH="$FAKE_BIN:$PATH"
export FAKE_STATE="$TEST_TMP/state"
unset RUN_ON_CMD TMUX_SESSION_SERVERS ADMIN_NAME

# Project config; once a .cca-env is loaded, .env files (same dir or above)
# are not read
cat >"$PROJECT/.cca-env" <<'EOF'
RUN_ON_CMD=ssh
TMUX_SESSION_SERVERS="server1 server2"
ADMIN_NAME=tester
EOF
printf 'TMUX_SESSION_SERVERS=from-dot-env\n' >"$PROJECT/.env"
printf 'TMUX_SESSION_SERVERS=leaked-from-parent\n' >"$TEST_TMP/.env"

PASSED=0
FAILED=0

check() {
    if [ "$2" = true ]; then
        echo "PASS: $1"
        PASSED=$((PASSED + 1))
    else
        echo "FAIL: $1"
        FAILED=$((FAILED + 1))
    fi
}

is() { [ "$1" = "$2" ] && echo true || echo false; }

# --- config loading ---
out=$(cd "$PROJECT/sub" && "$CLI" --list 2>&1)
check "loads .cca-env, not .env in same dir or parent" "$(is "$out" $'server1\nserver2')"

# A nested git repo with its own .env still inherits the main project's .cca-env
mkdir -p "$PROJECT/repos/sub/.git"
printf 'OWN=1\n' >"$PROJECT/repos/sub/.env"
out=$(cd "$PROJECT/repos/sub" && source "$SCRIPT_DIR/../lib/cca-env.sh" && cca_load_env &&
    echo "own=${OWN:-} servers=${TMUX_SESSION_SERVERS:-}")
check "nested git repo inherits main project .cca-env" "$(is "$out" "own=1 servers=server1 server2")"

# Config is sourced from its own directory: relative paths inside it resolve
# against that directory even when called from a subdirectory
printf 'source ./local.inc\n' >"$PROJECT/repos/sub/.cca-env"
printf 'FROM_LOCAL=sub\n' >"$PROJECT/repos/sub/local.inc"
printf 'FROM_LOCAL=root\n' >"$PROJECT/local.inc"
printf 'source ./local.inc\n' >>"$PROJECT/.cca-env"
mkdir -p "$PROJECT/repos/sub/deep"
out=$(cd "$PROJECT/repos/sub/deep" && source "$SCRIPT_DIR/../lib/cca-env.sh" && cca_load_env &&
    echo "local=${FROM_LOCAL:-} pwd=$PWD")
check "config relative paths resolve against config dir, cwd restored" \
    "$(is "$out" "local=root pwd=$PROJECT/repos/sub/deep")"
rm "$PROJECT/repos/sub/.cca-env"

# --- failed ssh command is logged with its exit code ---
(cd "$PROJECT" && "$CLI" server1 'echo out; exit 3' >/dev/null 2>&1)
rc=$?
check "ssh exit code is propagated" "$(is "$rc" 3)"
log_line=$(cat "$PROJECT"/logs/*-tester.log 2>/dev/null)
check "failed ssh command is logged" "$([[ "$log_line" == *"server1 echo out; exit 3 [exit: 3]"* ]] && echo true || echo false)"

(cd "$PROJECT" && "$CLI" server1 'mysql -h db --password hunter2 mongodb://u:p@h/x' >/dev/null 2>&1)
log_line=$(tail -n 1 "$PROJECT"/logs/*-tester.log 2>/dev/null)
check "logged command is sanitized, not emptied" "$([[ "$log_line" == *"server1 mysql -h db --password [REDACTED] mongodb://[REDACTED] [exit: "* ]] && echo true || echo false)"

# --- create-file over ssh ---
printf 'line1\n\n\n' >"$TEST_TMP/expected"
(cd "$PROJECT" && "$CLI" server1 --create-file "$REMOTE/new file.txt" <"$TEST_TMP/expected" >/dev/null 2>&1)
check "ssh create-file keeps trailing newlines" "$(cmp -s "$TEST_TMP/expected" "$REMOTE/new file.txt" && echo true || echo false)"
check "ssh create-file new file gets umask default" "$(is "$(stat -c %a "$REMOTE/new file.txt")" "$(printf '%o' $((0666 & ~0$(umask))))")"

printf 'old\n' >"$REMOTE/existing"
chmod 640 "$REMOTE/existing"
(cd "$PROJECT" && "$CLI" server1 --create-file "$REMOTE/existing" "$TEST_TMP/expected" >/dev/null 2>&1)
check "ssh create-file from local file is exact" "$(cmp -s "$TEST_TMP/expected" "$REMOTE/existing" && echo true || echo false)"
check "ssh create-file keeps existing mode" "$(is "$(stat -c %a "$REMOTE/existing")" 640)"

(cd "$PROJECT" && "$CLI" server1 --create-file "$REMOTE/missing-dir/x" </dev/null >/dev/null 2>&1)
check "ssh create-file fails for missing directory" "$([ $? -ne 0 ] && echo true || echo false)"
check "no temp files left behind" "$(is "$(find "$REMOTE" -name '.cca-create.*' | wc -l | tr -d ' ')" 0)"

# --- create-file over cca-tmux-cli ---
printf 'tmux\n\n' >"$TEST_TMP/expected-tmux"
(cd "$PROJECT" && RUN_ON_CMD=cca-tmux-cli TMUX_SESSION_NAME=cca-test ADMIN_NAME=tester \
    "$CLI" server1 --create-file "$REMOTE/via-tmux" <"$TEST_TMP/expected-tmux" >/dev/null 2>&1)
check "tmux create-file keeps trailing newlines" "$(cmp -s "$TEST_TMP/expected-tmux" "$REMOTE/via-tmux" && echo true || echo false)"

echo
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[ "$FAILED" -eq 0 ]
