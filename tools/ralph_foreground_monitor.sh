#!/bin/zsh
set -euo pipefail
unsetopt BG_NICE 2>/dev/null || true

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

INTERVAL_SEC="${INTERVAL_SEC:-1800}"
LOG_FILE="${LOG_FILE:-tmp/ralph_front_monitor.log}"
STATE_FILE="tmp/ralph_loop_state_v2.json"
RUNS_ROOT="tmp/ralph_loop_runs_v2"
HOOK_STATS_FILE="tmp/ralph_hook_stats.json"
DISPATCH_LOG="tmp/ralph_hook_dispatcher.log"

mkdir -p tmp
touch "$LOG_FILE"

is_num() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

file_age_sec() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    echo "na"
    return
  fi
  local m now
  m="$(stat -f "%m" "$file_path" 2>/dev/null || true)"
  if ! is_num "$m"; then
    echo "na"
    return
  fi
  now="$(date +%s)"
  echo $((now - m))
}

fmt_age() {
  local age="$1"
  if is_num "$age"; then
    echo "${age}s"
  else
    echo "na"
  fi
}

state_snapshot() {
  if [[ ! -f "$STATE_FILE" ]]; then
    echo "state=missing"
    return
  fi
  python3 - "$STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    obj = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print("state=invalid_json")
    raise SystemExit(0)
if not isinstance(obj, dict):
    print("state=invalid_payload")
    raise SystemExit(0)
print(
    "state"
    f" last_cycle={obj.get('last_cycle')}"
    f" no_improve_streak={obj.get('no_improve_streak')}"
    f" target_achieved={obj.get('target_achieved')}"
    f" active_policy={obj.get('active_policy_label')}"
)
PY
}

latest_cycle_result() {
  local latest_dir
  latest_dir="$(find "$RUNS_ROOT" -maxdepth 1 -type d -name 'cycle_*' | sort | tail -n 1 || true)"
  if [[ -z "$latest_dir" ]]; then
    echo "latest_cycle=missing"
    return
  fi
  local result_file="$latest_dir/cycle_result.json"
  if [[ ! -f "$result_file" ]]; then
    echo "latest_cycle=$(basename "$latest_dir") result=pending"
    return
  fi
  python3 - "$result_file" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    obj = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print(f"latest_cycle={p.parent.name} result=invalid_json")
    raise SystemExit(0)
if not isinstance(obj, dict):
    print(f"latest_cycle={p.parent.name} result=invalid_payload")
    raise SystemExit(0)
print(
    f"latest_cycle={p.parent.name}"
    f" decision={obj.get('decision')}"
    f" reason={obj.get('reason')}"
    f" quick_gate={obj.get('quick_gate', {}).get('reason') if isinstance(obj.get('quick_gate'), dict) else None}"
)
PY
}

hook_stats_snapshot() {
  if [[ ! -f "$HOOK_STATS_FILE" ]]; then
    echo "hook_stats=missing"
    return
  fi
  python3 - "$HOOK_STATS_FILE" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    obj = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print("hook_stats=invalid_json")
    raise SystemExit(0)
if not isinstance(obj, dict):
    print("hook_stats=invalid_payload")
    raise SystemExit(0)
last = obj.get("last") if isinstance(obj.get("last"), dict) else {}
print(
    "hook_stats"
    f" total={obj.get('total')}"
    f" success={obj.get('success')}"
    f" failed={obj.get('failed')}"
    f" last_status={last.get('status')}"
    f" last_reason={last.get('reason')}"
    f" last_run={last.get('run_id')}"
)
PY
}

dispatcher_tail() {
  if [[ ! -f "$DISPATCH_LOG" ]]; then
    echo "dispatcher_tail=missing"
    return
  fi
  local line
  line="$(tail -n 40 "$DISPATCH_LOG" | rg 'dispatcher: (completed|failed|attempt_failed|handling)' | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    echo "dispatcher_tail=none"
  else
    echo "$line"
  fi
}

snapshot_once() {
  local ts
  local sup_age dispatch_age hook_age
  sup_age="$(file_age_sec tmp/ralph_health/supervisor_heartbeat.json)"
  dispatch_age="$(file_age_sec tmp/ralph_health/dispatcher_heartbeat.json)"
  hook_age="$(file_age_sec tmp/ralph_health/time_hook_heartbeat.json)"
  ts="$(date '+%Y-%m-%d %H:%M:%S %z')"
  {
    echo ""
    echo "=== ralph monitor @ $ts ==="
    echo "uptime: $(uptime)"
    echo "heartbeat_age supervisor=$(fmt_age "$sup_age") dispatcher=$(fmt_age "$dispatch_age") time_hook=$(fmt_age "$hook_age")"
    state_snapshot
    latest_cycle_result
    hook_stats_snapshot
    dispatcher_tail
  } | tee -a "$LOG_FILE"
}

echo "foreground monitor started interval_sec=$INTERVAL_SEC log=$LOG_FILE" | tee -a "$LOG_FILE"
snapshot_once
while true; do
  sleep "$INTERVAL_SEC"
  snapshot_once
done
