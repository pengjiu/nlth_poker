#!/bin/zsh
set -euo pipefail
unsetopt BG_NICE 2>/dev/null || true

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "/opt/miniconda3/bin/python" ]]; then
    PYTHON_BIN="/opt/miniconda3/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    PYTHON_BIN="python"
  fi
fi

PID_DIR="tmp/ralph_pids"
SUP_PID_FILE="$PID_DIR/supervisor.pid"
DISPATCH_PID_FILE="$PID_DIR/dispatcher.pid"
SUP_MARKER="tools/ralph_loop_supervisor.sh"
DISPATCH_MARKER="tools/ralph_hook_dispatcher.sh"
SUP_LOCK_FILE="tmp/ralph_loop_supervisor.lock"
DISPATCH_LOCK_FILE="tmp/ralph_hook_dispatcher.lock"
EVENT_LOG="tmp/ralph_loop_events.ndjson"
TIME_HOOK_LOG="tmp/ralph_time_hook.log"
LOCK_FILE="tmp/ralph_time_hook.lock"
HEALTH_DIR="tmp/ralph_health"
SUP_HEALTH_FILE="$HEALTH_DIR/supervisor_heartbeat.json"
DISPATCH_HEALTH_FILE="$HEALTH_DIR/dispatcher_heartbeat.json"
TIMEHOOK_HEALTH_FILE="$HEALTH_DIR/time_hook_heartbeat.json"
CHECK_SEC="${CHECK_SEC:-60}"
RESTART_COOLDOWN_SEC="${RESTART_COOLDOWN_SEC:-180}"
MISS_THRESHOLD="${MISS_THRESHOLD:-3}"
COMPONENT_MAX_STALE_SEC="${COMPONENT_MAX_STALE_SEC:-300}"
LOCK_LIVENESS_SEC="${LOCK_LIVENESS_SEC:-120}"
STARTUP_GRACE_SEC="${STARTUP_GRACE_SEC:-90}"
TIMEHOOK_LOCK_STALE_SEC="${TIMEHOOK_LOCK_STALE_SEC:-180}"
HUMAN_LOG_PATH="tmp/ralph_loop_human_log.md"
HUMAN_LOG_CYCLE_MARK_FILE="$HEALTH_DIR/human_log_last_cycle.txt"
HUMAN_LOG_LAST_REFRESH_FILE="$HEALTH_DIR/human_log_last_refresh_epoch.txt"
HUMAN_LOG_REFRESH_SEC="${HUMAN_LOG_REFRESH_SEC:-1800}"
PARENT_LOCK_FILE="tmp/ralph_loop_state_v2.json.parent.lock"
PARENT_LOCK_MAX_AGE_SEC="${PARENT_LOCK_MAX_AGE_SEC:-43200}"
SUP_START_EPOCH_FILE="$HEALTH_DIR/supervisor_start_epoch.txt"
DISPATCH_START_EPOCH_FILE="$HEALTH_DIR/dispatcher_start_epoch.txt"

mkdir -p tmp "$PID_DIR" "$HEALTH_DIR"
touch "$EVENT_LOG" "$TIME_HOOK_LOG"
LOCK_OWNED=0

lock_age_sec() {
  local lock_file="$1"
  if [[ ! -f "$lock_file" ]]; then
    echo ""
    return
  fi
  local m now age
  m="$(stat -f "%m" "$lock_file" 2>/dev/null || true)"
  if [[ -z "$m" ]]; then
    echo ""
    return
  fi
  now="$(date +%s)"
  age=$((now - m))
  echo "$age"
}

pid_is_alive() {
  local pid="${1:-}"
  if [[ -z "$pid" ]] || [[ ! "$pid" =~ '^[0-9]+$' ]]; then
    return 1
  fi
  kill -0 "$pid" 2>/dev/null
}

acquire_lock() {
  local tries=0
  while true; do
    if ( set -o noclobber; echo "$$" > "$LOCK_FILE" ) 2>/dev/null; then
      LOCK_OWNED=1
      return
    fi
    local old_pid lock_age
    old_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
    lock_age="$(lock_age_sec "$LOCK_FILE")"
    if [[ -n "$old_pid" ]] && [[ -n "$lock_age" ]] && (( lock_age <= TIMEHOOK_LOCK_STALE_SEC )); then
      if pid_is_alive "$old_pid"; then
        echo "[$(date '+%F %T')] time_hook already running lock_pid=$old_pid age=${lock_age}s" >> "$TIME_HOOK_LOG"
        exit 0
      fi
    fi
    rm -f "$LOCK_FILE"
    tries=$((tries + 1))
    if (( tries >= 5 )); then
      echo "[$(date '+%F %T')] time_hook failed to acquire lock after retries" >> "$TIME_HOOK_LOG"
      exit 1
    fi
    sleep 1
  done
}

release_lock() {
  if [[ "$LOCK_OWNED" != "1" ]]; then
    return
  fi
  if [[ -f "$LOCK_FILE" ]]; then
    local lock_pid
    lock_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
    if [[ "$lock_pid" == "$$" ]]; then
      rm -f "$LOCK_FILE"
    fi
  fi
  LOCK_OWNED=0
}
trap release_lock EXIT INT TERM
acquire_lock

discover_pid_by_marker() {
  local marker="$1"
  local pid=""
  local cand=""
  local cmdline=""
  if command -v pgrep >/dev/null 2>&1; then
    for cand in $(pgrep -f "$marker" 2>/dev/null || true); do
      [[ -z "$cand" ]] && continue
      [[ "$cand" == "$$" ]] && continue
      cmdline="$(
        ps -ax -o pid,ppid,etime,%cpu,%mem,command 2>/dev/null \
          | awk -v p="$cand" '$1==p{ for(i=1;i<=5;i++) $i=""; sub(/^ +/, ""); print; exit }' || true
      )"
      [[ -z "$cmdline" ]] && continue
      if [[ "$cmdline" == *"pgrep -f "* ]] || [[ "$cmdline" == *"rg --fixed-strings"* ]]; then
        continue
      fi
      if [[ "$cmdline" == *"$marker"* ]]; then
        pid="$cand"
        break
      fi
    done
  fi
  if [[ -z "$pid" ]]; then
    pid="$(
      ps -ax -o pid,ppid,etime,%cpu,%mem,command 2>/dev/null \
        | rg --fixed-strings "$marker" \
        | rg -v 'rg --fixed-strings|pgrep -f' \
        | head -n 1 \
        | awk '{print $1}' || true
    )"
  fi
  echo "$pid"
}

pid_matches_marker() {
  local pid="$1"
  local marker="$2"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  local cmdline=""
  cmdline="$(
    ps -ax -o pid,ppid,etime,%cpu,%mem,command 2>/dev/null \
      | awk -v p="$pid" '$1==p{ for(i=1;i<=5;i++) $i=""; sub(/^ +/, ""); print; exit }' || true
  )"
  if [[ -n "$cmdline" ]]; then
    echo "$cmdline" | rg -q --fixed-strings "$marker"
    return $?
  fi
  if command -v pgrep >/dev/null 2>&1; then
    if pgrep -f "$marker" 2>/dev/null | rg -q "^${pid}$"; then
      return 0
    fi
    return 1
  fi
  return 1
}

heartbeat_age_sec() {
  local hb_file="$1"
  if [[ ! -f "$hb_file" ]]; then
    echo ""
    return
  fi
  local m now age
  m="$(stat -f "%m" "$hb_file" 2>/dev/null || true)"
  if [[ -z "$m" ]]; then
    echo ""
    return
  fi
  now="$(date +%s)"
  age=$((now - m))
  echo "$age"
}

refresh_lock_lease() {
  if [[ "$LOCK_OWNED" != "1" ]]; then
    return
  fi
  if [[ ! -f "$LOCK_FILE" ]]; then
    return
  fi
  local lock_pid
  lock_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
  if [[ "$lock_pid" == "$$" ]]; then
    touch "$LOCK_FILE" 2>/dev/null || true
  fi
}

is_heartbeat_fresh() {
  local hb_file="$1"
  local max_age="$2"
  local age
  age="$(heartbeat_age_sec "$hb_file")"
  if [[ -z "$age" ]]; then
    return 1
  fi
  (( age <= max_age ))
}

read_start_epoch() {
  local start_file="$1"
  local val=""
  if [[ -f "$start_file" ]]; then
    val="$(tr -cd '0-9' < "$start_file" 2>/dev/null || true)"
  fi
  if [[ -n "$val" ]]; then
    echo "$val"
  else
    echo ""
  fi
}

is_within_startup_grace() {
  local start_file="$1"
  local start_epoch now_epoch
  start_epoch="$(read_start_epoch "$start_file")"
  if [[ -z "$start_epoch" ]]; then
    return 1
  fi
  now_epoch="$(date +%s)"
  (( now_epoch - start_epoch <= STARTUP_GRACE_SEC ))
}

discover_pid_by_lock() {
  local lock_file="$1"
  local marker="${2:-}"
  local pid="" age=""
  if [[ -f "$lock_file" ]]; then
    pid="$(cat "$lock_file" 2>/dev/null || true)"
    age="$(lock_age_sec "$lock_file")"
  fi
  if [[ -n "$pid" ]] && [[ -n "$age" ]] && (( age <= LOCK_LIVENESS_SEC )) && pid_is_alive "$pid"; then
    if [[ -n "$marker" ]] && ! pid_matches_marker "$pid" "$marker"; then
      # Marker validation is best-effort in restricted sandboxes.
      :
    fi
    echo "$pid"
    return
  fi
  echo ""
}

is_running() {
  local pid_file="$1"
  local marker="$2"
  local lock_file="$3"
  local pid=""
  pid="$(discover_pid_by_lock "$lock_file" "$marker")"
  if [[ -n "$pid" ]]; then
    echo "$pid" > "$pid_file"
    return 0
  fi
  return 1
}

is_component_alive() {
  local pid_file="$1"
  local marker="$2"
  local lock_file="$3"
  local hb_file="$4"
  local start_file="${5:-}"
  if is_running "$pid_file" "$marker" "$lock_file"; then
    return 0
  fi
  if is_heartbeat_fresh "$hb_file" "$COMPONENT_MAX_STALE_SEC"; then
    if [[ -n "$start_file" ]] && is_within_startup_grace "$start_file"; then
      return 0
    fi
  fi
  return 1
}

stop_component_if_running() {
  local pid_file="$1"
  local marker="$2"
  local lock_file="$3"
  local lock_age
  lock_age="$(lock_age_sec "$lock_file")"
  if [[ -n "$lock_age" ]] && (( lock_age > LOCK_LIVENESS_SEC )); then
    rm -f "$lock_file" "$pid_file"
  fi
}

write_time_hook_heartbeat() {
  local sup_alive="$1"
  local dis_alive="$2"
  local ts
  ts="$(date '+%Y-%m-%dT%H:%M:%S%z')"
  printf '{"ts":"%s","pid":%s,"status":"running","supervisor_alive":%s,"dispatcher_alive":%s}\n' \
    "$ts" "$$" "$sup_alive" "$dis_alive" > "$TIMEHOOK_HEALTH_FILE"
  refresh_lock_lease
}

json_event() {
  local evt_status="$1"
  local reason="$2"
  local rc="$3"
  local ts
  ts="$(date '+%Y-%m-%dT%H:%M:%S%z')"
  printf '{"ts":"%s","status":"%s","reason":"%s","rc":%s,"restart_count":0,"state_file":"%s","runs_root":"%s"}\n' \
    "$ts" "$evt_status" "$reason" "$rc" "tmp/ralph_loop_state_v2.json" "tmp/ralph_loop_runs_v2" >> "$EVENT_LOG"
}

start_supervisor() {
  date +%s > "$SUP_START_EPOCH_FILE"
  nohup tools/ralph_loop_supervisor.sh > /tmp/ralph_loop_supervisor.out 2>&1 &
  echo $! > "$SUP_PID_FILE"
}

start_dispatcher() {
  date +%s > "$DISPATCH_START_EPOCH_FILE"
  nohup tools/ralph_hook_dispatcher.sh > /tmp/ralph_hook_dispatcher.out 2>&1 &
  echo $! > "$DISPATCH_PID_FILE"
}

read_state_last_cycle() {
  if [[ ! -f "tmp/ralph_loop_state_v2.json" ]]; then
    echo ""
    return
  fi
  "$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

p = Path("tmp/ralph_loop_state_v2.json")
try:
    d = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)
v = d.get("last_cycle")
if isinstance(v, bool):
    print("")
elif isinstance(v, int):
    print(v)
elif isinstance(v, str) and v.isdigit():
    print(v)
else:
    print("")
PY
}

read_supervisor_pause_reason() {
  if [[ ! -f "tmp/ralph_loop_state_v2.json" ]]; then
    echo ""
    return
  fi
  "$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

p = Path("tmp/ralph_loop_state_v2.json")
try:
    d = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)

focus = d.get("focus_control")
if not isinstance(focus, dict):
    print("")
    raise SystemExit(0)

if focus.get("stop_requested") is True:
    reason = focus.get("stop_reason")
    if isinstance(reason, str) and reason:
        print(reason)
        raise SystemExit(0)
print("")
PY
}

read_parent_lock_owner_pid() {
  if [[ ! -f "$PARENT_LOCK_FILE" ]]; then
    echo ""
    return
  fi
  "$PYTHON_BIN" - "$PARENT_LOCK_FILE" "$PARENT_LOCK_MAX_AGE_SEC" "tools/ralph_wiggum_loop.py --start-cycle" <<'PY'
import json
import os
import subprocess
import sys
import time
from pathlib import Path

lock_path = Path(sys.argv[1])
try:
    max_age = int(sys.argv[2])
except Exception:
    max_age = 43200
owner_marker = str(sys.argv[3]) if len(sys.argv) >= 4 else "tools/ralph_wiggum_loop.py --start-cycle"

try:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)

pid = payload.get("pid")
acquired = payload.get("acquired_at_epoch")
if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
    print("")
    raise SystemExit(0)

if isinstance(acquired, int):
    age = max(0, int(time.time()) - acquired)
    if age > max_age:
        try:
            lock_path.unlink()
        except Exception:
            pass
        print("")
        raise SystemExit(0)

try:
    os.kill(pid, 0)
except ProcessLookupError:
    try:
        lock_path.unlink()
    except Exception:
        pass
    print("")
    raise SystemExit(0)
except PermissionError:
    # Restricted runtimes may deny kill(0) while the process is still alive.
    pass
except Exception:
    pass

try:
    proc = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    cmdline = (proc.stdout or "").strip()
except Exception:
    cmdline = ""

# Only enforce marker match when ps command line is available. In restricted
# environments, ps may return empty output even for live processes.
if owner_marker and cmdline and owner_marker not in cmdline:
    try:
        lock_path.unlink()
    except Exception:
        pass
    print("")
    raise SystemExit(0)

print(pid)
PY
}

read_human_log_last_refresh_epoch() {
  if [[ ! -f "$HUMAN_LOG_LAST_REFRESH_FILE" ]]; then
    echo 0
    return
  fi
  local epoch
  epoch="$(tr -cd '0-9' < "$HUMAN_LOG_LAST_REFRESH_FILE" 2>/dev/null || true)"
  if [[ -z "$epoch" ]]; then
    echo 0
  else
    echo "$epoch"
  fi
}

last_supervisor_restart=0
last_dispatcher_restart=0
supervisor_miss_count=0
dispatcher_miss_count=0

# Bootstrap components once at startup to avoid waiting MISS_THRESHOLD * CHECK_SEC
# before the very first supervisor/dispatcher launch.
if ! is_component_alive "$SUP_PID_FILE" "$SUP_MARKER" "$SUP_LOCK_FILE" "$SUP_HEALTH_FILE" "$SUP_START_EPOCH_FILE"; then
  echo "[$(date '+%F %T')] time_hook: bootstrap supervisor start" >> "$TIME_HOOK_LOG"
  stop_component_if_running "$SUP_PID_FILE" "$SUP_MARKER" "$SUP_LOCK_FILE"
  start_supervisor
  last_supervisor_restart="$(date +%s)"
fi
if ! is_component_alive "$DISPATCH_PID_FILE" "$DISPATCH_MARKER" "$DISPATCH_LOCK_FILE" "$DISPATCH_HEALTH_FILE" "$DISPATCH_START_EPOCH_FILE"; then
  echo "[$(date '+%F %T')] time_hook: bootstrap dispatcher start" >> "$TIME_HOOK_LOG"
  stop_component_if_running "$DISPATCH_PID_FILE" "$DISPATCH_MARKER" "$DISPATCH_LOCK_FILE"
  start_dispatcher
  last_dispatcher_restart="$(date +%s)"
fi

while true; do
  now_epoch="$(date +%s)"
  sup_alive_flag=false
  dis_alive_flag=false

  if is_component_alive "$SUP_PID_FILE" "$SUP_MARKER" "$SUP_LOCK_FILE" "$SUP_HEALTH_FILE" "$SUP_START_EPOCH_FILE"; then
    supervisor_miss_count=0
    sup_alive_flag=true
  else
    supervisor_miss_count=$((supervisor_miss_count + 1))
    if (( supervisor_miss_count >= MISS_THRESHOLD )) && (( now_epoch - last_supervisor_restart >= RESTART_COOLDOWN_SEC )); then
      pause_reason="$(read_supervisor_pause_reason)"
      parent_lock_owner_pid="$(read_parent_lock_owner_pid)"
      if [[ -n "$pause_reason" ]]; then
        echo "[$(date '+%F %T')] time_hook: supervisor paused reason=$pause_reason, skip restart" >> "$TIME_HOOK_LOG"
        json_event "heartbeat" "time_hook_supervisor_paused" 0
        supervisor_miss_count=0
        sup_alive_flag=true
      elif [[ -n "$parent_lock_owner_pid" ]]; then
        # Parent process still owns the orchestration lock. Restarting
        # supervisor here tends to trigger duplicate contenders and churn.
        echo "[$(date '+%F %T')] time_hook: supervisor missing but parent lock owner alive pid=$parent_lock_owner_pid, skip restart" >> "$TIME_HOOK_LOG"
        json_event "heartbeat" "time_hook_wait_parent_lock_owner" 0
        supervisor_miss_count=0
        sup_alive_flag=true
      else
        echo "[$(date '+%F %T')] time_hook: supervisor missing, restarting" >> "$TIME_HOOK_LOG"
        json_event "restart" "time_hook_restart_supervisor" 1
        stop_component_if_running "$SUP_PID_FILE" "$SUP_MARKER" "$SUP_LOCK_FILE"
        start_supervisor
        sleep 1
        if is_component_alive "$SUP_PID_FILE" "$SUP_MARKER" "$SUP_LOCK_FILE" "$SUP_HEALTH_FILE" "$SUP_START_EPOCH_FILE"; then
          echo "[$(date '+%F %T')] time_hook: supervisor restarted pid=$(cat "$SUP_PID_FILE")" >> "$TIME_HOOK_LOG"
          supervisor_miss_count=0
          sup_alive_flag=true
        else
          echo "[$(date '+%F %T')] time_hook: supervisor restart failed" >> "$TIME_HOOK_LOG"
        fi
        last_supervisor_restart="$now_epoch"
      fi
    fi
  fi

  if is_component_alive "$DISPATCH_PID_FILE" "$DISPATCH_MARKER" "$DISPATCH_LOCK_FILE" "$DISPATCH_HEALTH_FILE" "$DISPATCH_START_EPOCH_FILE"; then
    dispatcher_miss_count=0
    dis_alive_flag=true
  else
    dispatcher_miss_count=$((dispatcher_miss_count + 1))
    if (( dispatcher_miss_count >= MISS_THRESHOLD )) && (( now_epoch - last_dispatcher_restart >= RESTART_COOLDOWN_SEC )); then
      echo "[$(date '+%F %T')] time_hook: dispatcher missing, restarting" >> "$TIME_HOOK_LOG"
      json_event "restart" "time_hook_restart_dispatcher" 1
      stop_component_if_running "$DISPATCH_PID_FILE" "$DISPATCH_MARKER" "$DISPATCH_LOCK_FILE"
      start_dispatcher
      sleep 1
      if is_component_alive "$DISPATCH_PID_FILE" "$DISPATCH_MARKER" "$DISPATCH_LOCK_FILE" "$DISPATCH_HEALTH_FILE" "$DISPATCH_START_EPOCH_FILE"; then
        echo "[$(date '+%F %T')] time_hook: dispatcher restarted pid=$(cat "$DISPATCH_PID_FILE")" >> "$TIME_HOOK_LOG"
        dispatcher_miss_count=0
        dis_alive_flag=true
      else
        echo "[$(date '+%F %T')] time_hook: dispatcher restart failed" >> "$TIME_HOOK_LOG"
      fi
      last_dispatcher_restart="$now_epoch"
    fi
  fi

  # Refresh human log only on cycle transition (or first boot), so operators
  # read one coherent entry per iteration instead of time-based rewrites.
  current_cycle="$(read_state_last_cycle)"
  last_logged_cycle=""
  if [[ -f "$HUMAN_LOG_CYCLE_MARK_FILE" ]]; then
    last_logged_cycle="$(cat "$HUMAN_LOG_CYCLE_MARK_FILE" 2>/dev/null || true)"
  fi
  last_human_refresh_epoch="$(read_human_log_last_refresh_epoch)"
  refresh_human_log=0
  if [[ ! -f "$HUMAN_LOG_PATH" ]]; then
    refresh_human_log=1
  elif [[ -n "$current_cycle" && "$current_cycle" != "$last_logged_cycle" ]]; then
    refresh_human_log=1
  elif (( HUMAN_LOG_REFRESH_SEC > 0 )) && (( now_epoch - last_human_refresh_epoch >= HUMAN_LOG_REFRESH_SEC )); then
    refresh_human_log=1
  fi
  if (( refresh_human_log == 1 )); then
    if "$PYTHON_BIN" tools/ralph_human_log.py --output "$HUMAN_LOG_PATH" >/dev/null 2>&1; then
      if [[ -n "$current_cycle" ]]; then
        echo "$current_cycle" > "$HUMAN_LOG_CYCLE_MARK_FILE"
      fi
      echo "$now_epoch" > "$HUMAN_LOG_LAST_REFRESH_FILE"
      echo "[$(date '+%F %T')] time_hook: human_log refreshed cycle=${current_cycle:-none}" >> "$TIME_HOOK_LOG"
    else
      echo "[$(date '+%F %T')] time_hook: human_log refresh failed" >> "$TIME_HOOK_LOG"
    fi
  fi
  write_time_hook_heartbeat "$sup_alive_flag" "$dis_alive_flag"

  sleep "$CHECK_SEC"
done
