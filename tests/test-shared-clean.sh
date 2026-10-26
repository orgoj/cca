#!/bin/bash
# Guard: this shared repo must contain no project-specific identifiers.
#
# Scans every git-tracked file with tests/leak_scan.py against a denylist supplied by
# the PROJECT (found in $CCA_DENYLIST or the current working directory). The denylist
# is never stored here - it would leak the names it guards.
#
# Generic examples are checked even without a project denylist. When a project
# denylist is available, the full scan runs as an additional check.

REPO_ROOT="$(dirname "$(readlink -f "$0")")/.."
DOCS=("$REPO_ROOT/src" "$REPO_ROOT/README.md" "$REPO_ROOT/AGENTS.md")

if grep -RniE \
    --exclude-dir='__pycache__' \
    'cca run -t ([a-z0-9.-]+)' \
    "${DOCS[@]}" \
    | grep -viE 'cca run -t (SERVER|server|server[0-9]+(\.example\.com)?|localhost|S|\.\.\.)([[:space:]]|$)'; then
    echo "Failed: non-generic cca run target found. Use server1 or server1.example.com."
    exit 1
fi

if grep -RniE \
    --exclude-dir='__pycache__' \
    '(ansible-[a-z0-9_-]+|cca check-domain [a-z0-9.-]+)' \
    "${DOCS[@]}" \
    | grep -viE '(ansible-example|cca check-domain (([a-z0-9-]+\.)*example\.(com|net|org)|DOMAIN|D)([^a-z0-9.-]|$))'; then
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

if python3 -I "$REPO_ROOT/tests/leak_scan.py" "$DENYLIST" --repo "$REPO_ROOT"; then
    echo "All tests passed!"
    exit 0
else
    echo "Failed: project-specific names must not live in this shared repo."
    exit 1
fi
