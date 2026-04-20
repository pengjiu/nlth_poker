#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LABEL="com.poker2.ralph-loop"
UID_NUM="$(id -u)"
TARGET="gui/$UID_NUM/$LABEL"

echo "label=$LABEL"
echo "target=$TARGET"
echo ""

launchctl print "$TARGET" 2>/dev/null | rg -n "state =|pid =|last exit code =|path =" || {
  echo "launchctl print failed or service not loaded"
}

echo ""
echo "health files:"
for f in tmp/ralph_health/supervisor_heartbeat.json tmp/ralph_health/dispatcher_heartbeat.json tmp/ralph_health/time_hook_heartbeat.json; do
  if [[ -f "$f" ]]; then
    echo "--- $f"
    cat "$f"
  else
    echo "--- $f (missing)"
  fi
done
