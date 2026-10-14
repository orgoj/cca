#!/bin/bash

# Headless tests for cca-hetrix with a fake cca-curl-secret.

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CLI="$SCRIPT_DIR/../bin/cca-hetrix"
TEST_TMP=$(mktemp -d)
FAKE_BIN="$TEST_TMP/bin"
mkdir -p "$FAKE_BIN"
trap 'rm -rf "$TEST_TMP"' EXIT

# Fake cca-curl-secret: fails like a missing sops when FAKE_FAIL is set,
# otherwise returns an empty monitor list
cat >"$FAKE_BIN/cca-curl-secret" <<'FAKE'
#!/bin/bash
if [ -n "${FAKE_FAIL:-}" ]; then
    echo "Error: 'sops' is not installed or not in PATH." >&2
    exit 1
fi
echo '{"monitors": []}'
FAKE
chmod +x "$FAKE_BIN/cca-curl-secret"
export PATH="$FAKE_BIN:$PATH"

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
lacks() { [[ "$1" == *"$2"* ]] && echo false || echo true; }

out=$("$CLI" --up 2>&1)
check "--up with no monitors down exits 0" "$([ $? -eq 0 ] && echo true || echo false)"
check "--up reports all UP" "$(has "$out" 'All monitors are UP')"

out=$(FAKE_FAIL=1 "$CLI" --up 2>&1)
check "--up exits 2 when the API key cannot be loaded" "$([ $? -eq 2 ] && echo true || echo false)"
check "--up reports the failure" "$(has "$out" 'API request failed')"
check "--up does not claim monitors are DOWN" "$(lacks "$out" 'DOWN')"
check "--up has no shell errors" "$(lacks "$out" 'integer expression')"

out=$(FAKE_FAIL=1 "$CLI" --outages --since 1d 2>&1)
check "--outages exits 2 when the API key cannot be loaded" "$([ $? -eq 2 ] && echo true || echo false)"
check "--outages does not print the result note" "$(lacks "$out" 'Note: Only showing')"

out=$(FAKE_FAIL=1 "$CLI" --down 2>&1)
check "--down exits 2 when the API key cannot be loaded" "$([ $? -eq 2 ] && echo true || echo false)"
check "--down does not claim nothing is down" "$(lacks "$out" 'No monitors are currently down')"

echo
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[ "$FAILED" -eq 0 ]
