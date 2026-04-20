#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.poker2.ralph-loop"
TEMPLATE="$ROOT_DIR/tools/launchd/$LABEL.plist.template"
AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$AGENT_DIR/$LABEL.plist"
UID_NUM="$(id -u)"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "template not found: $TEMPLATE" >&2
  exit 1
fi

mkdir -p "$AGENT_DIR"

# Escape '&' for sed replacement safety.
ROOT_ESCAPED="${ROOT_DIR//&/\\&}"
sed "s|__ROOT__|$ROOT_ESCAPED|g" "$TEMPLATE" > "$PLIST_PATH"

launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST_PATH"
launchctl enable "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true
launchctl kickstart -k "gui/$UID_NUM/$LABEL"

echo "installed: $PLIST_PATH"
echo "label: $LABEL"
echo "status_cmd: tools/launchd_status_ralph_loop.sh"
