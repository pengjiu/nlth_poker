#!/bin/zsh
set -euo pipefail
unsetopt BG_NICE 2>/dev/null || true

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

RUNS_ROOT="tmp/ralph_loop_runs_v2"
STATE_FILE="tmp/ralph_loop_state_v2.json"
EVENT_LOG="tmp/ralph_loop_events.ndjson"
SUP_LOG="tmp/ralph_loop_supervisor.log"
LOCK_FILE="tmp/ralph_loop_supervisor.lock"
HEALTH_DIR="tmp/ralph_health"
SUP_HEALTH_FILE="$HEALTH_DIR/supervisor_heartbeat.json"
MAX_RESTARTS="${MAX_RESTARTS:-999}"
SLEEP_ON_FAIL="${SLEEP_ON_FAIL:-8}"
FAIL_SLEEP_ESCALATE_AT="${FAIL_SLEEP_ESCALATE_AT:-8}"
FAIL_SLEEP_MAX_SEC="${FAIL_SLEEP_MAX_SEC:-90}"
HEARTBEAT_SEC="${HEARTBEAT_SEC:-60}"
STALL_SEC_RAW="${STALL_SEC:-3600}"
CHUNK_CYCLES="${CHUNK_CYCLES:-6}"
LOOP_JOBS="${LOOP_JOBS:-8}"
QUICK_JOBS_RATIO="${QUICK_JOBS_RATIO:-0.75}"
CPU_TARGET_UTIL="${CPU_TARGET_UTIL:-0.75}"
MIN_FREE_CORES="${MIN_FREE_CORES:-1}"
MAX_CANDIDATES="${MAX_CANDIDATES:-6}"
MAX_FULL_EVAL_CANDIDATES="${MAX_FULL_EVAL_CANDIDATES:-2}"
QUICK_SEED_START="${QUICK_SEED_START:-3000}"
QUICK_SEED_COUNT="${QUICK_SEED_COUNT:-4}"
FULL_SEED_START="${FULL_SEED_START:-2000}"
FULL_SEED_COUNT="${FULL_SEED_COUNT:-4}"
CONFIRM_SEED_START="${CONFIRM_SEED_START:-2010}"
CONFIRM_SEED_COUNT="${CONFIRM_SEED_COUNT:-4}"
QUICK_HANDS="${QUICK_HANDS:-600}"
FULL_HANDS="${FULL_HANDS:-1600}"
TIMEOUT_SEC="${TIMEOUT_SEC:-5400}"
LOOP_HEARTBEAT_SEC="${LOOP_HEARTBEAT_SEC:-120}"
MODEL_REVIEW_EVERY="${MODEL_REVIEW_EVERY:-1}"
REQUIRE_LLM_ACTION_TICKET="${REQUIRE_LLM_ACTION_TICKET:-0}"
LLM_REVIEW_FULL_GATE_FAIL_STREAK="${LLM_REVIEW_FULL_GATE_FAIL_STREAK:-2}"
LLM_REVIEW_MIN_NO_IMPROVE_STREAK="${LLM_REVIEW_MIN_NO_IMPROVE_STREAK:-2}"
LLM_REVIEW_FAIL_OPEN="${LLM_REVIEW_FAIL_OPEN:-1}"
BASELINE_INTEGRITY_AUTO_REPAIR="${BASELINE_INTEGRITY_AUTO_REPAIR:-1}"
GOAL_PACK="${GOAL_PACK:-specs/loop_goals/goal_pack_top_human_v2.json}"
WAIT_ON_PARENT_LOCK_SEC="${WAIT_ON_PARENT_LOCK_SEC:-45}"
WAIT_ON_CYCLE_LOCK_SEC="${WAIT_ON_CYCLE_LOCK_SEC:-20}"
CYCLE_LOCK_RETRIES="${CYCLE_LOCK_RETRIES:-60}"
SUP_LOCK_STALE_SEC="${SUP_LOCK_STALE_SEC:-180}"
AUTO_CLEANUP_ENABLE="${AUTO_CLEANUP_ENABLE:-1}"
AUTO_CLEANUP_MIN_FREE_GB="${AUTO_CLEANUP_MIN_FREE_GB:-120}"
AUTO_CLEANUP_TARGET_FREE_GB="${AUTO_CLEANUP_TARGET_FREE_GB:-160}"
AUTO_CLEANUP_KEEP_LATEST_GLOBAL="${AUTO_CLEANUP_KEEP_LATEST_GLOBAL:-4}"
AUTO_CLEANUP_KEEP_PER_CYCLE="${AUTO_CLEANUP_KEEP_PER_CYCLE:-1}"
AUTO_CLEANUP_KEEP_RECENT_CYCLES="${AUTO_CLEANUP_KEEP_RECENT_CYCLES:-3}"
AUTO_CLEANUP_PRESERVE_STATE_RECENT_CYCLES="${AUTO_CLEANUP_PRESERVE_STATE_RECENT_CYCLES:-3}"
AUTO_CLEANUP_MAX_REMOVE="${AUTO_CLEANUP_MAX_REMOVE:-800}"
AUTO_CLEANUP_KEEP_PARENT_LOGS="${AUTO_CLEANUP_KEEP_PARENT_LOGS:-12}"
AUTO_CLEANUP_COMPACT_ENABLE="${AUTO_CLEANUP_COMPACT_ENABLE:-1}"
AUTO_CLEANUP_COMPACT_KEEP_LATEST="${AUTO_CLEANUP_COMPACT_KEEP_LATEST:-1}"
AUTO_CLEANUP_COMPACT_MAX_DIRS="${AUTO_CLEANUP_COMPACT_MAX_DIRS:-12}"
AUTO_CLEANUP_KEEP_QUICK_CACHE="${AUTO_CLEANUP_KEEP_QUICK_CACHE:-120}"
AUTO_CLEANUP_INTERVAL_SEC="${AUTO_CLEANUP_INTERVAL_SEC:-300}"
AUTO_PRUNE_HISTORY_ENABLE="${AUTO_PRUNE_HISTORY_ENABLE:-1}"
AUTO_PRUNE_HISTORY_INTERVAL_SEC="${AUTO_PRUNE_HISTORY_INTERVAL_SEC:-21600}"
AUTO_PRUNE_HISTORY_KEEP_BASELINES="${AUTO_PRUNE_HISTORY_KEEP_BASELINES:-4}"
AUTO_PRUNE_HISTORY_KEEP_EVAL="${AUTO_PRUNE_HISTORY_KEEP_EVAL:-0}"
SCRIMMAGE_ARTIFACT_MODE="${SCRIMMAGE_ARTIFACT_MODE:-lean}"
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

resolve_sleep_on_fail() {
  local base sleep_cap escalate_at restart_count extra bumped
  base="$SLEEP_ON_FAIL"
  sleep_cap="$FAIL_SLEEP_MAX_SEC"
  escalate_at="$FAIL_SLEEP_ESCALATE_AT"
  restart_count=0

  if [[ ! "$base" =~ ^[0-9]+$ ]] || (( base < 1 )); then
    base=8
  fi
  if [[ ! "$sleep_cap" =~ ^[0-9]+$ ]] || (( sleep_cap < base )); then
    sleep_cap=90
  fi
  if [[ ! "$escalate_at" =~ ^[0-9]+$ ]] || (( escalate_at < 1 )); then
    escalate_at=8
  fi

  if [[ -f "$STATE_FILE" ]]; then
    restart_count="$(
      "$PYTHON_BIN" - "$STATE_FILE" <<'PY' 2>/dev/null || true
import json
import sys
from pathlib import Path

try:
    obj = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    print(0)
    raise SystemExit

value = obj.get("restart_count")
if isinstance(value, int) and value >= 0:
    print(value)
else:
    print(0)
PY
    )"
  fi

  if [[ "$restart_count" =~ ^[0-9]+$ ]] && (( restart_count >= escalate_at )); then
    extra=$(( (restart_count - escalate_at + 1) * 2 ))
    bumped=$(( base + extra ))
    if (( bumped > sleep_cap )); then
      bumped="$sleep_cap"
    fi
    echo "$bumped"
    return
  fi

  echo "$base"
}
SLEEP_ON_FAIL="$(resolve_sleep_on_fail)"

resolve_stall_sec() {
  local configured timeout_sec heartbeat_sec buffer min_stall
  configured="$STALL_SEC_RAW"
  timeout_sec="$TIMEOUT_SEC"
  heartbeat_sec="$HEARTBEAT_SEC"

  if [[ ! "$timeout_sec" =~ ^[0-9]+$ ]] || (( timeout_sec < 60 )); then
    timeout_sec=5400
  fi
  if [[ ! "$heartbeat_sec" =~ ^[0-9]+$ ]] || (( heartbeat_sec < 5 )); then
    heartbeat_sec=60
  fi

  # Avoid false stall kills while a long-running eval is still within timeout budget.
  buffer=$(( heartbeat_sec * 3 ))
  if (( buffer < 300 )); then
    buffer=300
  fi
  min_stall=$(( timeout_sec + buffer ))

  if [[ ! "$configured" =~ ^[0-9]+$ ]] || (( configured <= 0 )); then
    echo "$min_stall"
    return
  fi
  if (( configured < min_stall )); then
    echo "$min_stall"
    return
  fi
  echo "$configured"
}
STALL_SEC="$(resolve_stall_sec)"

mkdir -p tmp "$RUNS_ROOT" "$HEALTH_DIR"
touch "$EVENT_LOG" "$SUP_LOG"
LOCK_OWNED=0
LAST_CLEANUP_EPOCH=0
LAST_PRUNE_HISTORY_EPOCH=0

resolve_loop_jobs() {
  if [[ "$LOOP_JOBS" =~ ^[0-9]+$ ]] && (( LOOP_JOBS > 0 )); then
    echo "$LOOP_JOBS"
    return 0
  fi
  "$PYTHON_BIN" - "$CPU_TARGET_UTIL" "$MIN_FREE_CORES" <<'PY'
import math
import os
import sys

def _as_float(x: str, d: float) -> float:
    try:
        return float(x)
    except Exception:
        return d

def _as_int(x: str, d: int) -> int:
    try:
        return int(x)
    except Exception:
        return d

util = _as_float(sys.argv[1] if len(sys.argv) > 1 else "0.75", 0.75)
util = max(0.3, min(0.95, util))
reserve = _as_int(sys.argv[2] if len(sys.argv) > 2 else "1", 1)
cpu = int(os.cpu_count() or 4)
reserve = max(1, min(cpu - 1 if cpu > 1 else 1, reserve))
max_jobs = max(1, cpu - reserve)
target = max(1, int(math.floor(cpu * util)))
jobs = max(1, min(max_jobs, target))
if cpu >= 6:
    jobs = max(4, jobs)
print(jobs)
PY
}
LOOP_JOBS_RESOLVED="$(resolve_loop_jobs)"

resolve_quick_seeds_json() {
  "$PYTHON_BIN" - "$QUICK_SEED_START" "$QUICK_SEED_COUNT" "$LOOP_JOBS_RESOLVED" <<'PY'
import json
import sys

def _as_int(v: str, d: int) -> int:
    try:
        return int(v)
    except Exception:
        return d

seed_start = _as_int(sys.argv[1] if len(sys.argv) > 1 else "3000", 3000)
seed_count = _as_int(sys.argv[2] if len(sys.argv) > 2 else "0", 0)
jobs = max(1, _as_int(sys.argv[3] if len(sys.argv) > 3 else "4", 4))

if seed_count <= 0:
    # Keep quick gate economical but ensure enough parallel lanes for modern CPUs.
    seed_count = min(8, max(4, jobs))
seeds = [seed_start + i for i in range(seed_count)]
print(json.dumps(seeds, separators=(",", ":")))
PY
}
QUICK_SEEDS_JSON="$(resolve_quick_seeds_json)"

resolve_seed_range_json() {
  local seed_start="$1"
  local seed_count="$2"
  "$PYTHON_BIN" - "$seed_start" "$seed_count" <<'PY'
import json
import sys

def _as_int(v: str, d: int) -> int:
    try:
        return int(v)
    except Exception:
        return d

seed_start = _as_int(sys.argv[1] if len(sys.argv) > 1 else "2000", 2000)
seed_count = max(1, _as_int(sys.argv[2] if len(sys.argv) > 2 else "4", 4))
seeds = [seed_start + i for i in range(seed_count)]
print(json.dumps(seeds, separators=(",", ":")))
PY
}
FULL_SEEDS_JSON="$(resolve_seed_range_json "$FULL_SEED_START" "$FULL_SEED_COUNT")"
CONFIRM_SEEDS_JSON="$(resolve_seed_range_json "$CONFIRM_SEED_START" "$CONFIRM_SEED_COUNT")"

json_escape() {
  local s="${1:-}"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/ }"
  s="${s//$'\r'/ }"
  echo "$s"
}

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

free_gb_int() {
  "$PYTHON_BIN" -c 'import shutil; print(int(shutil.disk_usage(".").free // (1024**3)))' 2>/dev/null || echo 0
}

maybe_auto_cleanup() {
  if [[ "$AUTO_CLEANUP_ENABLE" != "1" ]]; then
    return
  fi
  local now free_gb reason run_cleanup
  local need_cleanup=0
  now="$(date +%s)"
  free_gb="$(free_gb_int)"
  if [[ -z "$free_gb" ]]; then
    free_gb=0
  fi

  reason="periodic"
  if (( LAST_CLEANUP_EPOCH == 0 )); then
    need_cleanup=1
    reason="startup"
  elif (( free_gb < AUTO_CLEANUP_MIN_FREE_GB )); then
    need_cleanup=1
    reason="low_disk"
  elif (( now - LAST_CLEANUP_EPOCH >= AUTO_CLEANUP_INTERVAL_SEC )); then
    need_cleanup=1
    reason="periodic"
  fi

  if (( need_cleanup == 0 )); then
    return
  fi

  run_cleanup="$(
    "$PYTHON_BIN" tools/ralph_cleanup_runs.py \
      --runs-root "$RUNS_ROOT" \
      --state-file "$STATE_FILE" \
      --keep-latest-global "$AUTO_CLEANUP_KEEP_LATEST_GLOBAL" \
      --keep-per-cycle "$AUTO_CLEANUP_KEEP_PER_CYCLE" \
      --keep-recent-cycles "$AUTO_CLEANUP_KEEP_RECENT_CYCLES" \
      --preserve-state-recent-cycles "$AUTO_CLEANUP_PRESERVE_STATE_RECENT_CYCLES" \
      --max-remove "$AUTO_CLEANUP_MAX_REMOVE" \
      --min-free-gb "$AUTO_CLEANUP_MIN_FREE_GB" \
      --target-free-gb "$AUTO_CLEANUP_TARGET_FREE_GB" \
      --keep-parent-logs "$AUTO_CLEANUP_KEEP_PARENT_LOGS" \
      --compact-enable "$AUTO_CLEANUP_COMPACT_ENABLE" \
      --compact-keep-latest "$AUTO_CLEANUP_COMPACT_KEEP_LATEST" \
      --compact-max-dirs "$AUTO_CLEANUP_COMPACT_MAX_DIRS" \
      --keep-quick-cache "$AUTO_CLEANUP_KEEP_QUICK_CACHE" 2>>"$SUP_LOG" || true
  )"
  LAST_CLEANUP_EPOCH="$now"

  if [[ -n "$run_cleanup" ]]; then
    echo "[$(date '+%F %T')] supervisor: auto_cleanup reason=$reason free_gb_before=$free_gb result=$run_cleanup" >> "$SUP_LOG"
  else
    echo "[$(date '+%F %T')] supervisor: auto_cleanup reason=$reason free_gb_before=$free_gb result=<empty>" >> "$SUP_LOG"
  fi
}

maybe_prune_history() {
  if [[ "$AUTO_PRUNE_HISTORY_ENABLE" != "1" ]]; then
    return
  fi
  local now run_prune reason
  local need_prune=0
  now="$(date +%s)"
  reason="periodic"
  if (( LAST_PRUNE_HISTORY_EPOCH == 0 )); then
    need_prune=1
    reason="startup"
  elif (( now - LAST_PRUNE_HISTORY_EPOCH >= AUTO_PRUNE_HISTORY_INTERVAL_SEC )); then
    need_prune=1
    reason="periodic"
  fi

  if (( need_prune == 0 )); then
    return
  fi

  run_prune="$(
    "$PYTHON_BIN" tools/prune_history_artifacts.py \
      --tmp-root "tmp" \
      --artifacts-eval-root "artifacts/eval" \
      --artifacts-baselines-root "artifacts/baselines" \
      --keep-baseline-dirs "$AUTO_PRUNE_HISTORY_KEEP_BASELINES" \
      --keep-eval-dirs "$AUTO_PRUNE_HISTORY_KEEP_EVAL" 2>>"$SUP_LOG" || true
  )"
  LAST_PRUNE_HISTORY_EPOCH="$now"
  if [[ -n "$run_prune" ]]; then
    echo "[$(date '+%F %T')] supervisor: prune_history reason=$reason result=$run_prune" >> "$SUP_LOG"
  else
    echo "[$(date '+%F %T')] supervisor: prune_history reason=$reason result=<empty>" >> "$SUP_LOG"
  fi
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
    if [[ -n "$old_pid" ]] && [[ -n "$lock_age" ]] && (( lock_age <= SUP_LOCK_STALE_SEC )); then
      if pid_is_alive "$old_pid"; then
        echo "supervisor already running lock_pid=$old_pid age=${lock_age}s" >> "$SUP_LOG"
        exit 1
      fi
    fi
    rm -f "$LOCK_FILE"
    tries=$((tries + 1))
    if (( tries >= 5 )); then
      echo "supervisor failed to acquire lock after retries" >> "$SUP_LOG"
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
CHILD_PID=""
cleanup_on_exit() {
  if [[ -n "$CHILD_PID" ]]; then
    kill -TERM "$CHILD_PID" 2>/dev/null || true
    sleep 2
    kill -KILL "$CHILD_PID" 2>/dev/null || true
  fi
  release_lock
}
trap cleanup_on_exit EXIT INT TERM
acquire_lock

latest_progress_epoch() {
  local latest
  latest="$(
    {
      if [[ -f "$STATE_FILE" ]]; then
        stat -f "%m" "$STATE_FILE" 2>/dev/null || true
      fi
      find "$RUNS_ROOT" -type f \( -name "run.log" -o -name "cycle_result.json" -o -name "review.json" \) -exec stat -f "%m" {} \; 2>/dev/null || true
    } \
      | sort -nr \
      | head -n 1 || true
  )"
  if [[ -z "$latest" ]]; then
    date +%s
  else
    echo "$latest"
  fi
}

extract_reason_for_run() {
  local start_line="$1"
  local reason=""
  reason="$("$PYTHON_BIN" - "$SUP_LOG" "$start_line" <<'PY'
import json
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
start_line = int(sys.argv[2])
try:
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
except Exception:
    print("")
    raise SystemExit(0)
for raw in reversed(lines[start_line:]):
    s = raw.strip()
    if not (s.startswith("{") and s.endswith("}")):
        continue
    try:
        obj = json.loads(s)
    except Exception:
        continue
    r = obj.get("reason")
    if isinstance(r, str) and r:
        print(r)
        raise SystemExit(0)
print("")
PY
  )"
  echo "$reason"
}

normalize_reason() {
  local reason="${1:-}"
  if [[ "$reason" == *"parent_lock_held"* ]]; then
    echo "parent_lock_held"
    return
  fi
  if [[ "$reason" == *"cycle_lock_held"* ]]; then
    echo "cycle_lock_held"
    return
  fi
  if [[ "$reason" == *"chunk_checkpoint"* ]]; then
    echo "chunk_checkpoint"
    return
  fi
  echo "$reason"
}

read_last_cycle() {
  if [[ ! -f "$STATE_FILE" ]]; then
    echo 0
    return
  fi
  local v
  v="$(PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BIN" -c 'import json,sys
p=sys.argv[1]
try:
    d=json.load(open(p, "r", encoding="utf-8"))
    x=d.get("last_cycle", 0)
    if isinstance(x, bool):
        print(0)
    elif isinstance(x, int):
        print(x)
    elif isinstance(x, str) and x.isdigit():
        print(int(x))
    else:
        print(0)
except Exception:
    print(0)
' "$STATE_FILE" 2>/dev/null || echo 0)"
  if [[ -z "$v" ]]; then
    echo 0
  else
    echo "$v"
  fi
}

json_event() {
  local evt_status="$1"
  local reason="$2"
  local rc="$3"
  local restart_count="$4"
  local child_pid="${5:-}"
  local progress_age="${6:-}"
  local cycle="${7:-}"
  local ts child_pid_json progress_age_json cycle_json
  ts="$(date '+%Y-%m-%dT%H:%M:%S%z')"
  if [[ -n "$child_pid" ]]; then
    child_pid_json="$child_pid"
  else
    child_pid_json="null"
  fi
  if [[ -n "$progress_age" ]]; then
    progress_age_json="$progress_age"
  else
    progress_age_json="null"
  fi
  if [[ -n "$cycle" ]]; then
    cycle_json="$cycle"
  else
    cycle_json="null"
  fi
  local evt_status_json reason_json state_json runs_json
  evt_status_json="$(json_escape "$evt_status")"
  reason_json="$(json_escape "$reason")"
  state_json="$(json_escape "$STATE_FILE")"
  runs_json="$(json_escape "$RUNS_ROOT")"
  printf '{"ts":"%s","status":"%s","reason":"%s","rc":%s,"restart_count":%s,"child_pid":%s,"progress_age_sec":%s,"cycle":%s,"state_file":"%s","runs_root":"%s"}\n' \
    "$ts" "$evt_status_json" "$reason_json" "$rc" "$restart_count" "$child_pid_json" "$progress_age_json" "$cycle_json" "$state_json" "$runs_json" >> "$EVENT_LOG"
}

write_supervisor_heartbeat() {
  local hb_status="$1"
  local hb_reason="$2"
  local hb_child_pid="${3:-}"
  local hb_progress_age="${4:-}"
  local hb_restart_count="${5:-$restart_count}"
  local ts child_pid_json progress_age_json
  ts="$(date '+%Y-%m-%dT%H:%M:%S%z')"
  if [[ -n "$hb_child_pid" ]]; then
    child_pid_json="$hb_child_pid"
  else
    child_pid_json="null"
  fi
  if [[ -n "$hb_progress_age" ]]; then
    progress_age_json="$hb_progress_age"
  else
    progress_age_json="null"
  fi
  local hb_status_json hb_reason_json
  hb_status_json="$(json_escape "$hb_status")"
  hb_reason_json="$(json_escape "$hb_reason")"
  printf '{"ts":"%s","pid":%s,"status":"%s","reason":"%s","restart_count":%s,"child_pid":%s,"progress_age_sec":%s}\n' \
    "$ts" "$$" "$hb_status_json" "$hb_reason_json" "$hb_restart_count" "$child_pid_json" "$progress_age_json" > "$SUP_HEALTH_FILE"
  refresh_lock_lease
}

discover_existing_start_cycle_pid() {
  "$PYTHON_BIN" - "$$" "$STATE_FILE" "$RUNS_ROOT" <<'PY'
import subprocess
import sys

try:
    self_pid = int(sys.argv[1])
except Exception:
    self_pid = -1
state_file = str(sys.argv[2]) if len(sys.argv) > 2 else ""
runs_root = str(sys.argv[3]) if len(sys.argv) > 3 else ""

try:
    out = subprocess.check_output(
        ["ps", "-ax", "-o", "pid,ppid,etime,%cpu,%mem,command"],
        text=True,
        errors="replace",
    )
except Exception:
    print("")
    raise SystemExit(0)

start_cycle_pids = []
worker_ppids = set()
for raw in out.splitlines()[1:]:
    parts = raw.strip().split(None, 5)
    if len(parts) < 6:
        continue
    try:
        pid = int(parts[0])
        ppid = int(parts[1])
    except Exception:
        continue
    cmd = parts[5]
    if "ralph_wiggum_loop.py --worker" in cmd:
        worker_ppids.add(ppid)
    if "ralph_wiggum_loop.py --start-cycle" not in cmd:
        continue
    if pid == self_pid:
        continue
    if f"--state-file {state_file}" not in cmd:
        continue
    if f"--runs-root {runs_root}" not in cmd:
        continue
    start_cycle_pids.append(pid)

if not start_cycle_pids:
    print("")
    raise SystemExit(0)

# Prefer the loop process that is already supervising a worker.
start_cycle_pids.sort(key=lambda pid: (0 if pid in worker_ppids else 1, pid))
print(start_cycle_pids[0])
PY
}

is_direct_child_pid() {
  local pid="${1:-}"
  if [[ -z "$pid" ]] || [[ ! "$pid" =~ '^[0-9]+$' ]]; then
    return 1
  fi
  local ppid
  ppid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
  [[ "$ppid" == "$$" ]]
}

run_once_bg() {
  local llm_flag=()
  local llm_review_fail_open_flag=()
  local baseline_repair_flag=()
  if [[ "$REQUIRE_LLM_ACTION_TICKET" == "0" ]]; then
    llm_flag=(--no-require-llm-action-ticket)
  fi
  if [[ "$LLM_REVIEW_FAIL_OPEN" == "1" ]]; then
    llm_review_fail_open_flag=(--llm-review-fail-open)
  fi
  if [[ "$BASELINE_INTEGRITY_AUTO_REPAIR" == "0" ]]; then
    baseline_repair_flag=(--no-baseline-integrity-auto-repair)
  fi
  PYTHONDONTWRITEBYTECODE=1 SCRIMMAGE_ARTIFACT_MODE="$SCRIMMAGE_ARTIFACT_MODE" \
  "$PYTHON_BIN" tools/ralph_wiggum_loop.py \
    --start-cycle 1 \
    --max-cycles 999 \
    --chunk-cycles "$CHUNK_CYCLES" \
    --cycle-lock-retries "$CYCLE_LOCK_RETRIES" \
    --stop-no-improve 999 \
    --quick-hands "$QUICK_HANDS" \
    --quick-seeds "$QUICK_SEEDS_JSON" \
    --full-hands "$FULL_HANDS" \
    --full-seeds "$FULL_SEEDS_JSON" \
    --confirm-seeds "$CONFIRM_SEEDS_JSON" \
    --jobs "$LOOP_JOBS_RESOLVED" \
    --quick-jobs-ratio "$QUICK_JOBS_RATIO" \
    --max-candidates "$MAX_CANDIDATES" \
    --max-full-eval-candidates "$MAX_FULL_EVAL_CANDIDATES" \
    --timeout-sec "$TIMEOUT_SEC" \
    --heartbeat-sec "$LOOP_HEARTBEAT_SEC" \
    --llm-review-full-gate-fail-streak "$LLM_REVIEW_FULL_GATE_FAIL_STREAK" \
    --llm-review-min-no-improve-streak "$LLM_REVIEW_MIN_NO_IMPROVE_STREAK" \
    --goal-pack "$GOAL_PACK" \
    --state-file "$STATE_FILE" \
    --runs-root "$RUNS_ROOT" \
    "${llm_review_fail_open_flag[@]-}" \
    "${llm_flag[@]-}" \
    "${baseline_repair_flag[@]-}" \
    --quiet >> "$SUP_LOG" 2>&1 &
  CHILD_PID="$!"
}

restart_count=0
quick_fail_streak=0
model_review_every=0
if [[ "$MODEL_REVIEW_EVERY" =~ ^[0-9]+$ ]]; then
  model_review_every="$MODEL_REVIEW_EVERY"
fi
next_model_review_cycle=0
last_emitted_cycle=0
boot_last_cycle="$(read_last_cycle)"
last_emitted_cycle="$boot_last_cycle"
if (( model_review_every > 0 )); then
  next_model_review_cycle=$(( (boot_last_cycle / model_review_every + 1) * model_review_every ))
fi
while true; do
  maybe_prune_history
  maybe_auto_cleanup
  write_supervisor_heartbeat "starting" "launch_worker" "" "" "$restart_count"
  local_start_line="$(wc -l < "$SUP_LOG" 2>/dev/null || echo 0)"
  echo "[$(date '+%F %T')] supervisor: start loop run restart_count=$restart_count jobs=$LOOP_JOBS_RESOLVED quick_hands=$QUICK_HANDS quick_seeds=$QUICK_SEEDS_JSON full_hands=$FULL_HANDS full_seeds=$FULL_SEEDS_JSON confirm_seeds=$CONFIRM_SEEDS_JSON quick_jobs_ratio=$QUICK_JOBS_RATIO max_candidates=$MAX_CANDIDATES max_full_eval_candidates=$MAX_FULL_EVAL_CANDIDATES timeout_sec=$TIMEOUT_SEC stall_sec=$STALL_SEC cpu_target_util=$CPU_TARGET_UTIL min_free_cores=$MIN_FREE_CORES require_llm_action_ticket=$REQUIRE_LLM_ACTION_TICKET llm_review_full_gate_fail_streak=$LLM_REVIEW_FULL_GATE_FAIL_STREAK llm_review_min_no_improve_streak=$LLM_REVIEW_MIN_NO_IMPROVE_STREAK llm_review_fail_open=$LLM_REVIEW_FAIL_OPEN baseline_integrity_auto_repair=$BASELINE_INTEGRITY_AUTO_REPAIR scrimmage_artifact_mode=$SCRIMMAGE_ARTIFACT_MODE" >> "$SUP_LOG"
  adopted_pid="$(discover_existing_start_cycle_pid)"
  adopted_foreign_child=0
  if [[ -n "$adopted_pid" ]] && kill -0 "$adopted_pid" 2>/dev/null; then
    CHILD_PID="$adopted_pid"
    child_pid="$adopted_pid"
    if ! is_direct_child_pid "$child_pid"; then
      adopted_foreign_child=1
    fi
    echo "[$(date '+%F %T')] supervisor: adopt existing start-cycle pid=$child_pid" >> "$SUP_LOG"
    json_event "heartbeat" "adopt_existing_loop_child" 0 "$restart_count" "$child_pid" 0
    write_supervisor_heartbeat "running" "adopt_existing_loop_child" "$child_pid" "0" "$restart_count"
  else
    run_once_bg
    child_pid="$CHILD_PID"
  fi
  last_progress="$(latest_progress_epoch)"
  stalled=0
  progress_age=0

  while kill -0 "$child_pid" 2>/dev/null; do
    sleep "$HEARTBEAT_SEC"
    now_epoch="$(date +%s)"
    cur_progress="$(latest_progress_epoch)"
    if [[ "$cur_progress" -gt "$last_progress" ]]; then
      last_progress="$cur_progress"
    fi
    progress_age=$((now_epoch - last_progress))
    if (( progress_age < 0 )); then
      progress_age=0
    fi
    json_event "heartbeat" "running" 0 "$restart_count" "$child_pid" "$progress_age"
    write_supervisor_heartbeat "running" "loop_child_alive" "$child_pid" "$progress_age" "$restart_count"
    cur_cycle="$(read_last_cycle)"
    if (( cur_cycle > last_emitted_cycle )); then
      while (( last_emitted_cycle < cur_cycle )); do
        last_emitted_cycle=$((last_emitted_cycle + 1))
        json_event "checkpoint" "cycle_completed" 0 "$restart_count" "$child_pid" "$progress_age" "$last_emitted_cycle"
      done
    fi
    if (( model_review_every > 0 )) && (( next_model_review_cycle > 0 )); then
      if (( cur_cycle >= next_model_review_cycle )); then
        json_event "checkpoint" "model_review_due" 0 "$restart_count" "$child_pid" "$progress_age" "$cur_cycle"
        next_model_review_cycle=$((next_model_review_cycle + model_review_every))
      fi
    fi
    if (( progress_age >= STALL_SEC )); then
      echo "[$(date '+%F %T')] supervisor: stall timeout child_pid=$child_pid age=${progress_age}s >= ${STALL_SEC}s" >> "$SUP_LOG"
      json_event "restart" "stall_timeout" 124 "$restart_count" "$child_pid" "$progress_age"
      write_supervisor_heartbeat "restart" "stall_timeout" "$child_pid" "$progress_age" "$restart_count"
      kill -TERM "$child_pid" 2>/dev/null || true
      sleep 3
      kill -KILL "$child_pid" 2>/dev/null || true
      stalled=1
      break
    fi
  done

  if [[ "$adopted_foreign_child" -eq 1 ]]; then
    rc=0
  else
    set +e
    wait "$child_pid"
    rc=$?
    set -e
  fi

  if [[ "$stalled" -eq 1 ]]; then
    rc=124
    reason="stall_timeout"
  else
    reason="$(extract_reason_for_run "$local_start_line")"
    if [[ -z "$reason" ]]; then
      reason="unknown"
    fi
  fi
  reason="$(normalize_reason "$reason")"
  sleep_on_fail="$SLEEP_ON_FAIL"

  if [[ $rc -eq 0 ]]; then
    quick_fail_streak=0
    if [[ "$reason" == "parent_lock_held" ]]; then
      # Another parent loop still owns the orchestration lock; wait instead of
      # counting restarts and spawning new children.
      json_event "heartbeat" "waiting_parent_lock" 0 "$restart_count" "$child_pid" 0
      write_supervisor_heartbeat "running" "waiting_parent_lock" "$child_pid" "0" "$restart_count"
      echo "[$(date '+%F %T')] supervisor: waiting parent lock owner" >> "$SUP_LOG"
      CHILD_PID=""
      sleep "$WAIT_ON_PARENT_LOCK_SEC"
      continue
    fi
    if [[ "$reason" == "cycle_lock_held" ]]; then
      # Keep the same parent process alive and let worker retry path settle.
      json_event "heartbeat" "waiting_cycle_lock" 0 "$restart_count" "$child_pid" 0
      write_supervisor_heartbeat "running" "waiting_cycle_lock" "$child_pid" "0" "$restart_count"
      echo "[$(date '+%F %T')] supervisor: waiting cycle lock release" >> "$SUP_LOG"
      CHILD_PID=""
      sleep "$WAIT_ON_CYCLE_LOCK_SEC"
      continue
    fi
    if [[ "$reason" == "chunk_checkpoint" ]]; then
      # Normal rolling checkpoint in continuous mode; do not treat as failure/restart.
      json_event "heartbeat" "chunk_checkpoint_continue" 0 "$restart_count" "$child_pid" 0
      write_supervisor_heartbeat "running" "chunk_checkpoint_continue" "$child_pid" "0" "$restart_count"
      CHILD_PID=""
      continue
    fi
    json_event "stopped" "$reason" "$rc" "$restart_count" "$child_pid" 0
    write_supervisor_heartbeat "stopped" "$reason" "$child_pid" "0" "$restart_count"
    if [[ "$reason" == "target_achieved" || "$reason" == "max_cycles" || "$reason" == "no_improve_limit" || "$reason" == "needs_manual_hypothesis" ]]; then
      echo "[$(date '+%F %T')] supervisor: terminal stop reason=$reason" >> "$SUP_LOG"
      exit 0
    fi
    restart_count=$((restart_count + 1))
    json_event "restart" "non_terminal_stop" "$rc" "$restart_count" "$child_pid" 0
    write_supervisor_heartbeat "restart" "non_terminal_stop" "$child_pid" "0" "$restart_count"
  else
    if [[ "$rc" -eq 75 && "$reason" == "parent_lock_held" ]]; then
      # Lock contention should back off, not burn restart budget.
      quick_fail_streak=0
      json_event "heartbeat" "waiting_parent_lock" 0 "$restart_count" "$child_pid" 0
      write_supervisor_heartbeat "running" "waiting_parent_lock" "$child_pid" "0" "$restart_count"
      echo "[$(date '+%F %T')] supervisor: non-fatal rc=75 reason=parent_lock_held, backing off" >> "$SUP_LOG"
      CHILD_PID=""
      sleep "$WAIT_ON_PARENT_LOCK_SEC"
      continue
    fi
    if [[ "$rc" -eq 75 && ( "$reason" == "cycle_lock_held" || "$reason" == "cycle_lock_retry_exhausted" ) ]]; then
      # A cycle worker is in-flight; avoid restart storms and wait for lock release.
      quick_fail_streak=0
      json_event "heartbeat" "waiting_cycle_lock" 0 "$restart_count" "$child_pid" 0
      write_supervisor_heartbeat "running" "waiting_cycle_lock" "$child_pid" "0" "$restart_count"
      echo "[$(date '+%F %T')] supervisor: non-fatal rc=75 reason=$reason, waiting cycle lock" >> "$SUP_LOG"
      CHILD_PID=""
      sleep "$WAIT_ON_CYCLE_LOCK_SEC"
      continue
    fi
    restart_count=$((restart_count + 1))
    json_event "restart" "worker_failed_or_unexpected_exit" "$rc" "$restart_count" "$child_pid" 0
    write_supervisor_heartbeat "restart" "worker_failed_or_unexpected_exit" "$child_pid" "0" "$restart_count"
    if [[ "$progress_age" =~ ^[0-9]+$ ]] && [[ "$progress_age" -le 5 ]]; then
      quick_fail_streak=$((quick_fail_streak + 1))
      sleep_on_fail=$((SLEEP_ON_FAIL * (quick_fail_streak + 1)))
      if [[ "$sleep_on_fail" -gt 120 ]]; then
        sleep_on_fail=120
      fi
      echo "[$(date '+%F %T')] supervisor: quick-phase worker failure rc=$rc streak=$quick_fail_streak backoff=${sleep_on_fail}s" >> "$SUP_LOG"
    else
      quick_fail_streak=0
    fi
  fi
  CHILD_PID=""

  if [[ $restart_count -ge $MAX_RESTARTS ]]; then
    json_event "stopped" "restart_limit_reached" 1 "$restart_count" "$child_pid" 0
    write_supervisor_heartbeat "stopped" "restart_limit_reached" "$child_pid" "0" "$restart_count"
    echo "[$(date '+%F %T')] supervisor: restart limit reached" >> "$SUP_LOG"
    exit 1
  fi

  sleep "$sleep_on_fail"
done
