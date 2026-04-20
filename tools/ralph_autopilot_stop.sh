#!/bin/zsh
set -euo pipefail
if [[ -n "${ZSH_VERSION:-}" ]]; then
  setopt NULL_GLOB
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PID_DIR="tmp/ralph_pids"
SUP_PID_FILE="$PID_DIR/supervisor.pid"
DISPATCH_PID_FILE="$PID_DIR/dispatcher.pid"
TIMEHOOK_PID_FILE="$PID_DIR/time_hook.pid"
SUP_MARKER="tools/ralph_loop_supervisor.sh"
DISPATCH_MARKER="tools/ralph_hook_dispatcher.sh"
TIMEHOOK_MARKER="tools/ralph_time_hook.sh"
HEALTH_DIR="tmp/ralph_health"
SUP_HEALTH_FILE="$HEALTH_DIR/supervisor_heartbeat.json"
DISPATCH_HEALTH_FILE="$HEALTH_DIR/dispatcher_heartbeat.json"
TIMEHOOK_HEALTH_FILE="$HEALTH_DIR/time_hook_heartbeat.json"

pid_cmd() {
  local pid="$1"
  ps -ax -o pid,ppid,etime,%cpu,%mem,command 2>/dev/null \
    | awk -v p="$pid" '$1==p{ for(i=1;i<=5;i++) $i=""; sub(/^ +/, ""); print; exit }' || true
}

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

kill_pid_graceful() {
  local pid="$1"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  for _ in {1..10}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  kill -KILL "$pid" 2>/dev/null || true
}

pid_matches() {
  local pid="$1"
  local marker="$2"
  local cmdline
  cmdline="$(pid_cmd "$pid")"
  [[ -n "$cmdline" ]] && echo "$cmdline" | rg -q --fixed-strings "$marker"
}

stop_pid_file() {
  local pid_file="$1"
  local marker="$2"
  local name="$3"
  local pid
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file" 2>/dev/null || true)"
  else
    pid=""
  fi
  if [[ -z "$pid" ]]; then
    pid="$(discover_pid_by_marker "$marker")"
  elif ! kill -0 "$pid" >/dev/null 2>&1 || ! pid_matches "$pid" "$marker"; then
    pid="$(discover_pid_by_marker "$marker")"
  fi
  local stopped=0
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1 && pid_matches "$pid" "$marker"; then
    kill_pid_graceful "$pid"
    stopped=$((stopped + 1))
  fi
  while true; do
    pid="$(discover_pid_by_marker "$marker")"
    if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1 || ! pid_matches "$pid" "$marker"; then
      break
    fi
    kill_pid_graceful "$pid"
    stopped=$((stopped + 1))
  done
  if (( stopped > 0 )); then
    echo "$name stopped count=$stopped"
  else
    echo "$name not running"
  fi
  rm -f "$pid_file"
}

stop_pid_file "$TIMEHOOK_PID_FILE" "$TIMEHOOK_MARKER" "time_hook"
stop_pid_file "$DISPATCH_PID_FILE" "$DISPATCH_MARKER" "dispatcher"
stop_pid_file "$SUP_PID_FILE" "$SUP_MARKER" "supervisor"

# Clean up orphan loop/eval children that may survive after supervisor exit.
for marker in \
  "tools/ralph_wiggum_loop.py --worker" \
  "tools/ralph_wiggum_loop.py --start-cycle" \
  "tmp/ralph_loop_runs_v2"
do
  while true; do
    pid="$(discover_pid_by_marker "$marker")"
    if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
      break
    fi
    kill_pid_graceful "$pid"
  done
done

rm -f tmp/ralph_loop_supervisor.lock tmp/ralph_hook_dispatcher.lock tmp/ralph_time_hook.lock
rm -f tmp/ralph_loop_state_v2.json.parent.lock
rm -f tmp/ralph_loop_runs_v2/cycle_*.lock
rm -f "$SUP_HEALTH_FILE" "$DISPATCH_HEALTH_FILE" "$TIMEHOOK_HEALTH_FILE"
