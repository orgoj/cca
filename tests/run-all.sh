#!/bin/bash

# Run the whole CCA test suite: shellcheck, bash tests, ruff, pytest.
# Usage: tests/run-all.sh   (exit 0 only when everything passes)

set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
FAILED=()

step() {
    local name=$1
    shift
    echo "=== $name"
    if "$@"; then
        echo "--- ok: $name"
    else
        echo "--- FAILED: $name"
        FAILED+=("$name")
    fi
}

shell_files=("$ROOT"/lib/*.sh "$ROOT"/tests/*.sh)
for f in "$ROOT"/bin/*; do
    # cca-tmux-cli is kept as-is until it is replaced by a dippy wrapper
    [ "$(basename "$f")" = cca-tmux-cli ] && continue
    if [ -f "$f" ] && head -n 1 "$f" | grep -q 'bash'; then
        shell_files+=("$f")
    fi
done
step shellcheck shellcheck -S warning "${shell_files[@]}"

for t in "$ROOT"/tests/test-*.sh; do
    case "$(basename "$t")" in
    # Needs the project denylist; run it from the project directory
    test-shared-clean.sh) continue ;;
    esac
    step "$(basename "$t")" "$t"
done

step ruff uv run --project "$ROOT" ruff check "$ROOT/src" "$ROOT/tests"
step ruff-format uv run --project "$ROOT" ruff format --check "$ROOT/src" "$ROOT/tests"
step pytest uv run --project "$ROOT" pytest -q -p no:cacheprovider "$ROOT/tests"

echo
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "ALL PASSED"
else
    echo "FAILED: ${FAILED[*]}"
    exit 1
fi
