#!/bin/bash
# Load config from script directory
# Priority: .cca-env (avoids collisions with other tools owning .env) > .env
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
for candidate in .cca-env .env; do
    if [ -f "$SCRIPT_DIR/$candidate" ]; then
        source "$SCRIPT_DIR/$candidate"
        break
    fi
done

if [ -z "$TMUX_SESSION_NAME" ]; then
    echo "Error: TMUX_SESSION_NAME not set in .cca-env"
    exit 1
fi

if tmux has-session -t "$TMUX_SESSION_NAME" 2>/dev/null; then
    echo "Session '$TMUX_SESSION_NAME' already exists"
    tmux attach-session -t "$TMUX_SESSION_NAME"
else
    tmux new-session -s "$TMUX_SESSION_NAME"
fi
