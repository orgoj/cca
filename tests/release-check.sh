#!/bin/bash
# Release check (see README "Release"): everything in tests/run-all.sh plus the leak
# scans with the consumer project's denylist, and the tag state.
# Usage: CCA_DENYLIST=/path/to/denylist tests/release-check.sh pre-tag|post-tag
#   pre-tag:  clean work tree, tag v<version> does not exist yet
#   post-tag: tag v<version> exists and points at HEAD (tags are never moved)

set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
MODE=${1:-}
case "$MODE" in
pre-tag | post-tag) ;;
*)
    echo "usage: CCA_DENYLIST=FILE $0 pre-tag|post-tag" >&2
    exit 2
    ;;
esac

# Fail closed: the fixture denylist used by run-all.sh does not know consumer names
if [ -z "${CCA_DENYLIST:-}" ] || [ ! -f "$CCA_DENYLIST" ]; then
    echo "FAIL: CCA_DENYLIST must name the consumer project's denylist file" >&2
    exit 1
fi

VERSION=$(python3 -I -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$ROOT/pyproject.toml")
TAG="v$VERSION"
FAILED=()

if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
    echo "FAIL: work tree not clean"
    FAILED+=(clean-tree)
fi
if [ "$MODE" = pre-tag ]; then
    if git -C "$ROOT" rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
        echo "FAIL: tag $TAG already exists; bump the version in pyproject.toml"
        FAILED+=(tag)
    fi
else
    tagged=$(git -C "$ROOT" rev-parse -q --verify "refs/tags/$TAG^{commit}")
    if [ "$tagged" != "$(git -C "$ROOT" rev-parse HEAD)" ]; then
        echo "FAIL: tag $TAG missing or not at HEAD (package version $VERSION)"
        FAILED+=(tag)
    fi
fi

"$ROOT/tests/run-all.sh" || FAILED+=(run-all)
"$ROOT/tests/test-shared-clean.sh" || FAILED+=(shared-clean)
"$ROOT/tests/test-package.sh" "$CCA_DENYLIST" || FAILED+=(package)

echo
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "RELEASE CHECK PASSED ($MODE, $TAG)"
else
    echo "RELEASE CHECK FAILED ($MODE, $TAG): ${FAILED[*]}"
    exit 1
fi
