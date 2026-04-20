#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LABEL="com.poker2.ralph-loop"
AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$AGENT_DIR/$LABEL.plist"
UID_NUM="$(id -u)"

launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

zsh tools/ralph_autopilot_stop.sh || true

echo "uninstalled: $LABEL"
echo "removed_plist: $PLIST_PATH"
