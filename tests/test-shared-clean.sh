#!/bin/bash
# Guard: this shared repo must contain no project-specific identifiers.
#
# Runs cca-check-shared-clean against a denylist supplied by the PROJECT
# (found in $CCA_DENYLIST or the current working directory). The denylist is
# never stored here - it would leak the names it guards.
#
# Generic examples are checked even without a project denylist. When a project
# denylist is available, the full scanner runs as an additional check.

REPO_ROOT="$(dirname "$(readlink -f "$0")")/.."

if grep -RniE \
    --exclude-dir='__pycache__' \
    --exclude='test-shared-clean.sh' \
    'cca-tmux-cli -t ([a-z0-9.-]+)' \
    "$REPO_ROOT/bin" "$REPO_ROOT/skills" \
    | grep -viE 'cca-tmux-cli -t (SERVER|server|server[0-9]+(\.example\.com)?|localhost)([[:space:]]|$)'; then
    echo "Failed: non-generic cca-tmux-cli target found. Use server1 or server1.example.com."
    exit 1
fi

if grep -RniE \
    --exclude-dir='__pycache__' \
    --exclude='test-shared-clean.sh' \
    '(ansible-[a-z0-9_-]+|cca-check-domain [a-z0-9.-]+)' \
    "$REPO_ROOT/bin" "$REPO_ROOT/skills" \
    | grep -viE '(ansible-example|cca-check-domain (example\.com|DOMAIN))'; then
    echo "Failed: non-generic project or domain example found."
    exit 1
fi

if [ -z "$CCA_DENYLIST" ] && [ ! -f "cca-shared-denylist.txt" ] && [ ! -f ".cca-shared-denylist.txt" ]; then
    echo "Generic shared-clean checks passed (project denylist not available)."
    exit 0
fi

DENYLIST=${CCA_DENYLIST:-}
[ -n "$DENYLIST" ] || { [ -f cca-shared-denylist.txt ] && DENYLIST=cca-shared-denylist.txt; }
[ -n "$DENYLIST" ] || DENYLIST=.cca-shared-denylist.txt

# bin/cca-check-shared-clean stays unchanged until TASK-2; backlog/ and src/ are
# scanned by tests/leak_scan.py with the same denylist
if "$REPO_ROOT/bin/cca-check-shared-clean" "$REPO_ROOT" \
    && python3 -I "$REPO_ROOT/tests/leak_scan.py" "$DENYLIST" --repo "$REPO_ROOT" backlog src; then
    echo "All tests passed!"
    exit 0
else
    echo "Failed: project-specific names must not live in this shared repo."
    exit 1
fi
