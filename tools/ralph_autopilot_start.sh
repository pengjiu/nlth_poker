#!/bin/zsh
set -euo pipefail
# Some shells auto-nice background jobs (BG_NICE), which can fail in restricted environments.
unsetopt BG_NICE 2>/dev/null || true

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PID_DIR="tmp/ralph_pids"
SUP_PID_FILE="$PID_DIR/supervisor.pid"
DISPATCH_PID_FILE="$PID_DIR/dispatcher.pid"
TIMEHOOK_PID_FILE="$PID_DIR/time_hook.pid"
SUP_MARKER="tools/ralph_loop_supervisor.sh"
DISPATCH_MARKER="tools/ralph_hook_dispatcher.sh"
TIMEHOOK_MARKER="tools/ralph_time_hook.sh"
SUP_LOCK_FILE="tmp/ralph_loop_supervisor.lock"
DISPATCH_LOCK_FILE="tmp/ralph_hook_dispatcher.lock"
TIMEHOOK_LOCK_FILE="tmp/ralph_time_hook.lock"
HEALTH_DIR="tmp/ralph_health"
SUP_HEALTH_FILE="$HEALTH_DIR/supervisor_heartbeat.json"
DISPATCH_HEALTH_FILE="$HEALTH_DIR/dispatcher_heartbeat.json"
TIMEHOOK_HEALTH_FILE="$HEALTH_DIR/time_hook_heartbeat.json"
COMPONENT_MAX_STALE_SEC="${COMPONENT_MAX_STALE_SEC:-300}"

mkdir -p "$PID_DIR" tmp "$HEALTH_DIR"

discover_pid_by_marker() {
  local marker="$1"
  local pid=""
  if command -v pgrep >/dev/null 2>&1; then
    pid="$(pgrep -f "$marker" 2>/dev/null | head -n 1 || true)"
  fi
  if [[ -z "$pid" ]]; then
    pid="$(
      ps -ax -o pid,ppid,etime,%cpu,%mem,command 2>/dev/null \
        | rg --fixed-strings "$marker" \
        | rg -v 'rg --fixed-strings' \
        | head -n 1 \
        | awk '{print $1}' || true
    )"
  fi
  echo "$pid"
}

discover_pid_by_lock() {
  local lock_file="$1"
  local pid=""
  if [[ -f "$lock_file" ]]; then
    pid="$(cat "$lock_file" 2>/dev/null || true)"
  fi
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    echo "$pid"
    return
  fi
  echo ""
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

is_running() {
  local pid_file="$1"
  local marker="$2"
  local lock_file="$3"
  local hb_file="${4:-}"
  local pid=""
  if [[ -n "$hb_file" ]] && is_heartbeat_fresh "$hb_file" "$COMPONENT_MAX_STALE_SEC"; then
    if [[ -f "$pid_file" ]]; then
      pid="$(cat "$pid_file" 2>/dev/null || true)"
      if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
        return 0
      fi
    fi
  fi
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file" 2>/dev/null || true)"
  fi
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi
  pid="$(discover_pid_by_lock "$lock_file")"
  if [[ -n "$pid" ]]; then
    echo "$pid" > "$pid_file"
    return 0
  fi
  pid="$(discover_pid_by_marker "$marker")"
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    echo "$pid" > "$pid_file"
    return 0
  fi
  return 1
}

cleanup_stale_pid_file() {
  local pid_file="$1"
  local marker="$2"
  local lock_file="$3"
  local hb_file="$4"
  local name="$5"
  if is_running "$pid_file" "$marker" "$lock_file" "$hb_file"; then
    return 0
  fi
  if [[ -f "$pid_file" ]]; then
    echo "$name stale pid file removed"
    rm -f "$pid_file"
  fi
}

start_process() {
  local pid_file="$1"
  local marker="$2"
  local lock_file="$3"
  local hb_file="$4"
  local name="$5"
  local out_file="$6"
  shift 6
  if is_running "$pid_file" "$marker" "$lock_file" "$hb_file"; then
    local existing_pid
    existing_pid="$(cat "$pid_file" 2>/dev/null || true)"
    [[ -z "$existing_pid" ]] && existing_pid="unknown"
    echo "$name already running pid=$existing_pid"
    return
  fi
  cleanup_stale_pid_file "$pid_file" "$marker" "$lock_file" "$hb_file" "$name"
  nohup "$@" > "$out_file" 2>&1 &
  local pid=$!
  echo "$pid" > "$pid_file"
  sleep 1
  if ! is_running "$pid_file" "$marker" "$lock_file" "$hb_file"; then
    echo "$name failed to start; check $out_file"
    return 1
  fi
  echo "$name started pid=$(cat "$pid_file")"
}

cleanup_orphan_loop_children() {
  if is_running "$SUP_PID_FILE" "$SUP_MARKER" "$SUP_LOCK_FILE" "$SUP_HEALTH_FILE"; then
    return
  fi
  local orphan_parent
  orphan_parent="$(discover_pid_by_marker "tools/ralph_wiggum_loop.py --start-cycle")"
  if [[ -z "$orphan_parent" ]]; then
    return
  fi
  echo "orphan loop parent detected pid=$orphan_parent, cleaning stale loop children"
  kill "$orphan_parent" >/dev/null 2>&1 || true
  sleep 1
  local orphan_worker
  orphan_worker="$(discover_pid_by_marker "tools/ralph_wiggum_loop.py --worker")"
  if [[ -n "$orphan_worker" ]]; then
    kill "$orphan_worker" >/dev/null 2>&1 || true
  fi
}

start_supervisor() {
  if is_running "$SUP_PID_FILE" "$SUP_MARKER" "$SUP_LOCK_FILE" "$SUP_HEALTH_FILE"; then
    echo "supervisor already running pid=$(cat "$SUP_PID_FILE")"
    return
  fi
  start_process "$SUP_PID_FILE" "$SUP_MARKER" "$SUP_LOCK_FILE" "$SUP_HEALTH_FILE" "supervisor" "/tmp/ralph_loop_supervisor.out" tools/ralph_loop_supervisor.sh
}

start_dispatcher() {
  if is_running "$DISPATCH_PID_FILE" "$DISPATCH_MARKER" "$DISPATCH_LOCK_FILE" "$DISPATCH_HEALTH_FILE"; then
    echo "dispatcher already running pid=$(cat "$DISPATCH_PID_FILE")"
    return
  fi
  start_process "$DISPATCH_PID_FILE" "$DISPATCH_MARKER" "$DISPATCH_LOCK_FILE" "$DISPATCH_HEALTH_FILE" "dispatcher" "/tmp/ralph_hook_dispatcher.out" tools/ralph_hook_dispatcher.sh
}

start_time_hook() {
  if is_running "$TIMEHOOK_PID_FILE" "$TIMEHOOK_MARKER" "$TIMEHOOK_LOCK_FILE" "$TIMEHOOK_HEALTH_FILE"; then
    echo "time_hook already running pid=$(cat "$TIMEHOOK_PID_FILE")"
    return
  fi
  start_process "$TIMEHOOK_PID_FILE" "$TIMEHOOK_MARKER" "$TIMEHOOK_LOCK_FILE" "$TIMEHOOK_HEALTH_FILE" "time_hook" "/tmp/ralph_time_hook.out" tools/ralph_time_hook.sh
}

cleanup_orphan_loop_children
start_supervisor
start_dispatcher
start_time_hook

echo "event_log=tmp/ralph_loop_events.ndjson"
echo "supervisor_log=tmp/ralph_loop_supervisor.log"
echo "dispatcher_log=tmp/ralph_hook_dispatcher.log"
echo "time_hook_log=tmp/ralph_time_hook.log"
