#!/bin/bash
# Leak scan of backlog/ and src/ with the repository fixture denylist, plus a self-test
# that a planted name is caught.
# The consumer denylist runs in tests/test-shared-clean.sh and tests/release-check.sh.

set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCAN="$ROOT/tests/leak_scan.py"
DENY="$ROOT/tests/fixtures/leak-denylist.txt"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
FAIL=0

check() {
    local want=$1 name=$2
    shift 2
    "$@" >"$TMP/out" 2>&1
    local got=$?
    if [ "$got" -eq "$want" ]; then
        echo "ok: $name"
    else
        echo "FAIL: $name (exit $got, want $want)"
        cat "$TMP/out"
        FAIL=1
    fi
}

check 0 "backlog/ and src/ clean" python3 -I "$SCAN" "$DENY" --repo "$ROOT" backlog src

mkdir -p "$TMP/dist/pkg"
echo "nothing to see" >"$TMP/dist/pkg/a.txt"
check 0 "clean dir" python3 -I "$SCAN" "$DENY" --dir "$TMP/dist"
echo "host leak-canary-$$ here" >"$TMP/dist/pkg/b.txt"
check 1 "planted name caught" python3 -I "$SCAN" "$DENY" --dir "$TMP/dist"
check 2 "missing denylist fails" python3 -I "$SCAN" "$TMP/missing.txt" --dir "$TMP/dist"

# Several denylists (one per consumer project): each one is applied
mkdir -p "$TMP/multi"
echo "server of project two: other-canary-$$" >"$TMP/multi/c.txt"
printf '# project two\nother-canary-[0-9]+\n' >"$TMP/deny-two.txt"
check 0 "first list alone misses it" python3 -I "$SCAN" "$DENY" --dir "$TMP/multi"
check 1 "second list in FILE:FILE caught" python3 -I "$SCAN" "$DENY:$TMP/deny-two.txt" --dir "$TMP/multi"
check 2 "missing file in the list fails" python3 -I "$SCAN" "$DENY:$TMP/missing.txt" --dir "$TMP/multi"
check 2 "empty entry in the list fails" python3 -I "$SCAN" "$DENY::$TMP/deny-two.txt" --dir "$TMP/multi"
echo "# comments only" >"$TMP/deny-empty.txt"
check 2 "list file without patterns fails" python3 -I "$SCAN" "$DENY:$TMP/deny-empty.txt" --dir "$TMP/multi"

# Symlinks: link text is scanned, the target never read
mkdir -p "$TMP/outside" "$TMP/links/sub"
echo "leak-canary-1 outside" >"$TMP/outside/file"
ln -s "$TMP/outside/file" "$TMP/links/live-file"
ln -s "$TMP/outside" "$TMP/links/sub/live-dir"
check 0 "live links to outside are not followed" python3 -I "$SCAN" "$DENY" --dir "$TMP/links"
ln -s "/nonexistent/leak-canary-2" "$TMP/links/broken"
check 1 "broken link text caught" python3 -I "$SCAN" "$DENY" --dir "$TMP/links"

# Tracked files: links not followed, a tracked file missing from the work tree fails
git init -q "$TMP/repo"
echo "plain" >"$TMP/repo/a.txt"
ln -s "$TMP/outside/file" "$TMP/repo/link"
git -C "$TMP/repo" add a.txt link
check 0 "tracked live link not followed" python3 -I "$SCAN" "$DENY" --repo "$TMP/repo" .
rm "$TMP/repo/a.txt"
check 2 "tracked file missing from work tree" python3 -I "$SCAN" "$DENY" --repo "$TMP/repo" .

# The release step fails closed without the consumer denylist (before running anything)
check 1 "release check without CCA_DENYLIST" env -u CCA_DENYLIST "$ROOT/tests/release-check.sh" pre-tag
check 1 "release check with a missing denylist" \
    env CCA_DENYLIST="$TMP/missing.txt" "$ROOT/tests/release-check.sh" pre-tag
check 1 "release check with one missing denylist in the list" \
    env CCA_DENYLIST="$DENY:$TMP/missing.txt" "$ROOT/tests/release-check.sh" pre-tag
check 1 "release check with an empty list entry" \
    env CCA_DENYLIST="$DENY:" "$ROOT/tests/release-check.sh" pre-tag

exit $FAIL
