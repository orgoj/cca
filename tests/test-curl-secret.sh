#!/bin/bash

# Headless tests for cca-curl-secret with fake sops and curl.

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CLI="$SCRIPT_DIR/../bin/cca-curl-secret"
TEST_TMP=$(mktemp -d)
FAKE_BIN="$TEST_TMP/bin"
mkdir -p "$FAKE_BIN" "$TEST_TMP/secrets"
trap 'rm -rf "$TEST_TMP"' EXIT

# Fake sops: the test secrets file is plaintext; count decryptions
cat >"$FAKE_BIN/sops" <<'FAKE_SOPS'
#!/bin/bash
echo x >>"$FAKE_STATE/sops-calls"
cat "$2"
FAKE_SOPS
# Fake curl: print the config from stdin and the arguments
cat >"$FAKE_BIN/curl" <<'FAKE_CURL'
#!/bin/bash
if [ "$1" = -s ]; then
    printf '<meta name="csrf-token" content="tok123">\n'
    exit 0
fi
cat
printf 'ARG %s\n' "$@"
FAKE_CURL
chmod +x "$FAKE_BIN/sops" "$FAKE_BIN/curl"
export PATH="$FAKE_BIN:$PATH"
export FAKE_STATE="$TEST_TMP"

cat >"$TEST_TMP/secrets/curl.secret.yaml" <<'EOF'
credentials:
  example_com:
    bearer: abc
  api_example_org:
    username: admin
    password: 'pa"ss\word'
    csrf: true
EOF

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

has() { [[ "$1" == *"$2"* ]] && echo true || echo false; }

out=$(cd "$TEST_TMP" && "$CLI" 'https://www.example.com/x/{TOKEN}' 2>&1)
check "falls back to ID without subdomain" "$(has "$out" 'header = "Authorization: Bearer abc"')"
check "substitutes {TOKEN}" "$(has "$out" 'ARG https://www.example.com/x/abc')"
check "decrypts only once" "$([ "$(wc -l <"$TEST_TMP/sops-calls")" -eq 1 ] && echo true || echo false)"

out=$(cd "$TEST_TMP" && "$CLI" https://api.example.org/ 2>&1)
check "escapes quotes and backslashes in curl config" "$(has "$out" 'user = "admin:pa\"ss\\word"')"
check "adds CSRF token" "$(has "$out" 'header = "X-CSRF-Token: tok123"')"

out=$(cd "$TEST_TMP" && "$CLI" --cred-id 'a) | .x' https://example.net/ 2>&1)
rc=$?
check "unknown/hostile ID fails cleanly" "$([ "$rc" -ne 0 ] && [[ "$out" == *"not found"* ]] && echo true || echo false)"

echo
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[ "$FAILED" -eq 0 ]
