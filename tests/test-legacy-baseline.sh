#!/bin/bash
# bin/, lib/ and root skills/ are symlinked live into consumer projects and stay
# byte-for-byte unchanged until TASK-2: compare them with the legacy-baseline tag,
# including uncommitted, untracked and ignored files.
# Usage: tests/test-legacy-baseline.sh [REPO]
#   without REPO: self-test on a temporary repo, then check this repo

set -u

PATHS=(bin lib skills)

check() {
    local root=$1 fail=0 extra
    if ! git -C "$root" rev-parse -q --verify "refs/tags/legacy-baseline^{commit}" >/dev/null; then
        echo "FAIL: tag legacy-baseline not found in $root (git fetch --tags)"
        return 1
    fi
    if ! git -C "$root" diff --quiet legacy-baseline -- "${PATHS[@]}"; then
        echo "FAIL: ${PATHS[*]} differ from legacy-baseline:"
        git -C "$root" diff --stat legacy-baseline -- "${PATHS[@]}"
        fail=1
    fi
    # untracked files, ignored ones included (they are live in consumer projects too);
    # __pycache__ is Python's bytecode cache written whenever a legacy script is loaded
    extra=$(git -C "$root" ls-files --others -- "${PATHS[@]}" | grep -v '/__pycache__/')
    if [ -n "$extra" ]; then
        echo "FAIL: files not in legacy-baseline under ${PATHS[*]}:"
        echo "$extra"
        fail=1
    fi
    [ "$fail" -eq 0 ] && echo "ok: ${PATHS[*]} match legacy-baseline in $root"
    return "$fail"
}

if [ $# -gt 0 ]; then
    check "$1"
    exit
fi

SELF=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
REPO="$TMP/repo"
FAIL=0

expect() {
    local want=$1 name=$2 got
    "$SELF" "$REPO" >"$TMP/out" 2>&1
    got=$?
    if [ "$got" -eq "$want" ]; then
        echo "ok: self-test: $name"
    else
        echo "FAIL: self-test: $name (exit $got, want $want)"
        cat "$TMP/out"
        FAIL=1
    fi
}

mkdir -p "$REPO/bin" "$REPO/lib" "$REPO/skills/s1"
echo "script" >"$REPO/bin/tool"
echo "lib" >"$REPO/lib/x.sh"
echo "skill" >"$REPO/skills/s1/SKILL.md"
echo "*.log" >"$REPO/.gitignore"
git -C "$REPO" init -q
git -C "$REPO" add -A
git -C "$REPO" -c user.name=t -c user.email=t@example.com commit -q -m base
git -C "$REPO" tag legacy-baseline

expect 0 "unchanged"
echo "changed" >>"$REPO/lib/x.sh"
expect 1 "modified file"
git -C "$REPO" checkout -q -- lib/x.sh
touch "$REPO/skills/s1/untracked.md"
expect 1 "untracked file"
rm "$REPO/skills/s1/untracked.md"
touch "$REPO/skills/s1/ignored.log"
expect 1 "ignored file"
rm "$REPO/skills/s1/ignored.log"
mkdir "$REPO/bin/__pycache__"
touch "$REPO/bin/__pycache__/toolcpython-312.pyc" "$REPO/other.log" "$REPO/README.md"
expect 0 "bytecode cache and changes outside the guarded paths"

check "$ROOT" || FAIL=1
exit "$FAIL"
