#!/bin/bash
# Build the wheel and sdist, check their content, install the wheel into a temporary
# uv tool dir and use it from a project outside the source checkout.
# Usage: tests/test-package.sh [DENYLIST]   (default: the repository fixture denylist)

set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DENY=${1:-"$ROOT/tests/fixtures/leak-denylist.txt"}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export UV_TOOL_DIR="$TMP/tools" UV_TOOL_BIN_DIR="$TMP/bin"
CCA="$TMP/bin/cca"
PROJ="$TMP/project"
FAIL=0

step() {
    local name=$1
    shift
    if "$@" >"$TMP/out" 2>&1; then
        echo "ok: $name"
    else
        echo "FAIL: $name"
        cat "$TMP/out"
        FAIL=1
    fi
}

# Runs in the project dir, outside the source checkout
in_project() { (cd "$PROJ" && "$@"); }

expect_out() {
    local want=$1
    shift
    "$@" >"$TMP/cmd" 2>&1 || { cat "$TMP/cmd"; return 1; }
    grep -q -- "$want" "$TMP/cmd" || { echo "missing '$want' in:"; cat "$TMP/cmd"; return 1; }
}

VERSION=$(python3 -I -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$ROOT/pyproject.toml")

step "uv build" uv build --quiet --out-dir "$TMP/dist" "$ROOT"
step "wheel/sdist content" python3 -I "$ROOT/tests/check_dist.py" dist "$TMP/dist" "$TMP/extracted"
step "dist leak scan" python3 -I "$ROOT/tests/leak_scan.py" "$DENY" --dir "$TMP/extracted"
[ "$FAIL" -eq 0 ] || exit 1

WHEEL=$(echo "$TMP"/dist/cca-*.whl)
mkdir -p "$PROJ/.claude/skills" "$PROJ/cca/guides" "$PROJ/cca/incidents" "$PROJ/backlog"
# ssh transport: cca doctor then needs ssh on PATH, not tmux and a session
printf 'schema_version = 1\n\n[servers.server1]\n\n[run]\ntransport = "ssh"\n' >"$PROJ/.cca.toml"
# cca doctor needs the backlog CLI and these statuses (cca watchlist)
printf 'statuses: ["To Do", "In Progress", "Note", "Done"]\n' >"$PROJ/backlog/config.yml"

step "uv tool install" uv tool install --quiet "$WHEEL"
step "installed from the wheel, not the checkout" expect_out "$UV_TOOL_DIR/cca/" \
    "$UV_TOOL_DIR/cca/bin/python" -I -c 'import cca; print(cca.__file__)'
step "cca --version" expect_out "^cca $VERSION\$" in_project "$CCA" --version
step "cca config show" expect_out "^# $PROJ/.cca.toml\$" in_project "$CCA" config show
step "cca install skills" expect_out "^linked: " in_project "$CCA" install skills
step "cca install skills NAME" expect_out "^unchanged: " in_project "$CCA" install skills cca
step "cca doctor" in_project "$CCA" doctor
step "cca doctor --fix" in_project "$CCA" doctor --fix
step "uv tool install --reinstall" uv tool install --quiet --reinstall "$WHEEL"
step "skill link valid after reinstall" test -f "$PROJ/.claude/skills/cca/SKILL.md"
step "install skills idempotent after reinstall" expect_out "^unchanged: " \
    in_project "$CCA" install skills

COMMANDS=$("$UV_TOOL_DIR/cca/bin/python" -I -c 'from cca.cli import COMMANDS; print(*COMMANDS)')
SKILLS=$(dirname "$(readlink "$PROJ/.claude/skills/cca")")
# shellcheck disable=SC2086 # one argument per command name
step "installed skills reference only provided commands" \
    python3 -I "$ROOT/tests/check_dist.py" skills "$SKILLS" $COMMANDS

# the scan itself catches what it must
mkdir -p "$TMP/bad/one" "$TMP/bad/two" "$TMP/bad/three"
printf 'Run `cca nosuchcommand --all` first. See .cca-skills.json\n' >"$TMP/bad/one/SKILL.md"
printf 'Legacy: cca-tmux-cli -t server1\n' >"$TMP/bad/two/SKILL.md"
printf 'In prose: run cca nosuchcommand first.\n' >"$TMP/bad/three/SKILL.md"
for bad in one two three; do
    step "skill scan rejects $bad" \
        bash -c '! python3 -I "$1" skills "$2" config doctor install' _ \
        "$ROOT/tests/check_dist.py" "$TMP/bad/$bad"
done

exit "$FAIL"
