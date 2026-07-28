#!/bin/bash

# Test script for command escaping safety
# Tests base64 encode/decode + pipe to bash pattern
# Can run locally without SSH/tmux - simulates the escaping behavior

# NO set -e - we want to continue after failed tests!

PASSED=0
FAILED=0

# Test helper: compare base64-encoded command result with expected output
test_escape() {
    local test_name="$1"
    local command="$2"
    local expected="$3"

    # Simulate cca-tmux/SSH approach (base64 encode + decode + pipe to bash)
    encoded_cmd=$(printf '%s' "$command" | base64 | tr -d '\n')
    result=$(echo "$encoded_cmd" | base64 -d | bash 2>&1) || true

    # Compare using diff (handles newlines correctly)
    if diff -q <(printf '%s' "$result") <(printf '%s' "$expected") >/dev/null 2>&1; then
        echo "PASS: $test_name"
        ((PASSED++))
        return 0
    else
        echo "FAIL: $test_name"
        echo "  Expected: $(printf '%s' "$expected" | head -c 80 | tr '\n' ' ')..."
        echo "  Got:      $(printf '%s' "$result" | head -c 80 | tr '\n' ' ')..."
        ((FAILED++))
        return 1
    fi
}

# Test helper: check output line count
test_escape_multiline() {
    local test_name="$1"
    local command="$2"
    local expected_lines="$3"

    # Simulate cca-tmux/SSH approach (base64 encode + decode + pipe to bash)
    encoded_cmd=$(printf '%s' "$command" | base64 | tr -d '\n')
    result=$(echo "$encoded_cmd" | base64 -d | bash 2>&1) || true
    actual_lines=$(printf '%s' "$result" | wc -l)
    # wc -l counts newlines, so add 1 if there's content without trailing newline
    if [ -n "$result" ] && [ "${result: -1}" != $'\n' ]; then
        actual_lines=$((actual_lines + 1))
    fi

    if [ "$actual_lines" -eq "$expected_lines" ]; then
        echo "PASS: $test_name ($actual_lines lines)"
        ((PASSED++))
        return 0
    else
        echo "FAIL: $test_name"
        echo "  Expected lines: $expected_lines"
        echo "  Got lines:      $actual_lines"
        echo "  Output: $(printf '%s' "$result" | head -c 80 | tr '\n' ' ')..."
        ((FAILED++))
        return 1
    fi
}

echo "=== Testing command escaping safety ==="
echo ""

# Edge cases
echo "--- Edge cases ---"
# Empty command is an edge case - bash -c "" gives error, which is expected
# test_escape "empty command" "" ""  # Skipped - empty command is user error
test_escape "whitespace only" "echo ''" ""

# Basic tests
echo ""
echo "--- Basic commands ---"
test_escape "simple command" "echo hello" "hello"
test_escape "command with spaces" "echo hello world" "hello world"

# Quote tests
echo ""
echo "--- Quote handling ---"
test_escape "double quotes" 'echo "hello world"' "hello world"
test_escape "single quotes" "echo 'hello world'" "hello world"
test_escape "mixed quotes" "echo \"it's working\"" "it's working"
test_escape "nested quotes" 'echo "say '\''hello'\''"' "say 'hello'"

# Multiline tests
echo ""
echo "--- Multiline commands ---"
test_escape_multiline "newline in command" "echo line1
echo line2" 2

test_escape_multiline "three lines" "echo a
echo b
echo c" 3

# Special characters
echo ""
echo "--- Special characters ---"
test_escape "semicolon" "echo first; echo second" "first
second"
test_escape "pipe" "echo hello | cat" "hello"
test_escape "ampersand" "echo test && echo ok" "test
ok"

# Command substitution
echo ""
echo "--- Command substitution ---"
test_escape "dollar expansion" 'echo $(echo subshell)' "subshell"
test_escape "backticks" 'echo `echo nested`' "nested"

# Variable expansion (should happen on remote side)
echo ""
echo "--- Variables (expand remotely) ---"
test_escape "dollar variable" 'echo $USER' "$USER"
test_escape "braces variable" 'echo ${HOME}' "$HOME"

# Heredoc test
echo ""
echo "--- Heredoc ---"
heredoc_cmd='cat <<EOF
line1
line2
EOF'
test_escape_multiline "heredoc" "$heredoc_cmd" 2

# Complex heredoc
complex_heredoc='cat <<EOF
first line
  indented line
last line
EOF'
test_escape_multiline "complex heredoc" "$complex_heredoc" 3

# Dangerous patterns that should NOT cause issues
echo ""
echo "--- Security: patterns that should be safe ---"
test_escape "injection attempt" "echo 'test; rm -rf /'" "test; rm -rf /"
test_escape "quote escape attempt" "echo \"test\\\"; echo hacked\"" 'test"; echo hacked'

echo ""
echo "=== Test Summary ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"

if [ "$FAILED" -gt 0 ]; then
    echo ""
    echo "SOME TESTS FAILED!"
    exit 1
else
    echo ""
    echo "All tests passed!"
    exit 0
fi
