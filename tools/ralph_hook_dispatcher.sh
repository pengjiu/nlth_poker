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

EVENT_LOG="tmp/ralph_loop_events.ndjson"
DISPATCH_LOG="tmp/ralph_hook_dispatcher.log"
RUNS_DIR="tmp/ralph_hook_runs"
LAST_HASH_FILE="tmp/ralph_hook_last_hash.txt"
LOCK_FILE="tmp/ralph_hook_dispatcher.lock"
NEXT_ACTION_FILE="tmp/ralph_next_action.json"
HEALTH_DIR="tmp/ralph_health"
DISPATCH_HEALTH_FILE="$HEALTH_DIR/dispatcher_heartbeat.json"
DEFAULT_CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
CODEX_HOME_DIR="${RALPH_CODEX_HOME:-$DEFAULT_CODEX_HOME}"
FAIL_STREAK_FILE="tmp/ralph_hook_fail_streak.txt"
CIRCUIT_UNTIL_FILE="tmp/ralph_hook_circuit_until.txt"
HOOK_TIMEOUT_SEC="${HOOK_TIMEOUT_SEC:-480}"
HOOK_MAX_RETRIES="${HOOK_MAX_RETRIES:-2}"
HOOK_RETRY_BACKOFF_SEC="${HOOK_RETRY_BACKOFF_SEC:-10}"
HOOK_FAIL_STREAK_LIMIT="${HOOK_FAIL_STREAK_LIMIT:-3}"
HOOK_COOLDOWN_SEC="${HOOK_COOLDOWN_SEC:-900}"
DISPATCH_HEARTBEAT_SEC="${DISPATCH_HEARTBEAT_SEC:-30}"
DISPATCH_LOCK_STALE_SEC="${DISPATCH_LOCK_STALE_SEC:-180}"
AWAITING_MIN_INTERVAL_SEC="${AWAITING_MIN_INTERVAL_SEC:-120}"
PROMPT_MAX_BYTES="${PROMPT_MAX_BYTES:-262144}"
HOOK_STATS_FILE="tmp/ralph_hook_stats.json"
AWAITING_GUARD_FILE="tmp/ralph_hook_awaiting_guard.json"
HOOK_REQUIRE_CODE_PATCH="${HOOK_REQUIRE_CODE_PATCH:-0}"
HOOK_CODE_PATCH_FILES="${HOOK_CODE_PATCH_FILES:-tools/ralph_wiggum_loop.py,poker2/runtime/system_policy.py,poker2/cli/scrimmage.py,poker2/cli/scrimmage_batch.py}"
HOOK_REQUIRE_STRATEGY_PATCH="${HOOK_REQUIRE_STRATEGY_PATCH:-0}"
HOOK_STRATEGY_PATCH_FILES="${HOOK_STRATEGY_PATCH_FILES:-poker2/runtime/system_policy.py}"
HOOK_ALLOW_PLAN_ONLY="${HOOK_ALLOW_PLAN_ONLY:-1}"
HOOK_ALLOW_SHARED_RUNTIME_PATCH="${HOOK_ALLOW_SHARED_RUNTIME_PATCH:-0}"
HOOK_SHARED_RUNTIME_PATCH_FILES="${HOOK_SHARED_RUNTIME_PATCH_FILES:-tools/ralph_wiggum_loop.py,poker2/runtime/system_policy.py,poker2/cli/scrimmage.py,poker2/cli/scrimmage_batch.py}"

mkdir -p tmp "$RUNS_DIR" "$HEALTH_DIR"
touch "$EVENT_LOG"
mkdir -p "$CODEX_HOME_DIR"
LOCK_OWNED=0
if [[ "$CODEX_HOME_DIR" != "$HOME/.codex" ]] && [[ ! -f "$CODEX_HOME_DIR/auth.json" ]] && [[ -f "$HOME/.codex/auth.json" ]]; then
  cp "$HOME/.codex/auth.json" "$CODEX_HOME_DIR/auth.json" 2>/dev/null || true
fi

last_evt_status="idle"
last_evt_reason="boot"
last_evt_rc=0
last_evt_restart=0
heartbeat_pid=""

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

init_hook_stats() {
  if [[ -f "$HOOK_STATS_FILE" ]]; then
    return
  fi
  cat > "$HOOK_STATS_FILE" <<'EOF'
{
  "total": 0,
  "success": 0,
  "failed": 0,
  "reasons": {},
  "last": {}
}
EOF
}

init_hook_stats

requires_code_patch_for_reason() {
  local reason="$1"
  if [[ "$HOOK_REQUIRE_CODE_PATCH" != "1" ]]; then
    return 1
  fi
  [[ "$reason" == "cycle_completed" || "$reason" == "model_review_due" || "$reason" == "awaiting_llm_action" ]]
}

requires_strategy_patch_for_reason() {
  local reason="$1"
  if [[ "$HOOK_REQUIRE_STRATEGY_PATCH" != "1" ]]; then
    return 1
  fi
  [[ "$reason" == "cycle_completed" || "$reason" == "model_review_due" || "$reason" == "awaiting_llm_action" ]]
}

csv_contains_any_required_path() {
  local csv_paths="${1:-}"
  local csv_required="${2:-}"
  "$PYTHON_BIN" - "$csv_paths" "$csv_required" <<'PY'
import sys

paths_csv = sys.argv[1] if len(sys.argv) > 1 else ""
required_csv = sys.argv[2] if len(sys.argv) > 2 else ""

def norm(v: str) -> str:
    s = (v or "").strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s

paths = {norm(v) for v in paths_csv.split(",") if norm(v)}
required = {norm(v) for v in required_csv.split(",") if norm(v)}
if not required:
    raise SystemExit(0)
for row in required:
    if row in paths:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

snapshot_code_patch_hashes() {
  local out_file="$1"
  "$PYTHON_BIN" - "$ROOT_DIR" "$HOOK_CODE_PATCH_FILES" "$out_file" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
csv = sys.argv[2]
out = Path(sys.argv[3])
rows = []
for raw in csv.split(","):
    rel = raw.strip()
    if not rel:
        continue
    p = root / rel
    if p.is_file():
        dig = hashlib.sha256(p.read_bytes()).hexdigest()
    else:
        dig = "MISSING"
    rows.append((rel, dig))
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", encoding="utf-8") as f:
    for rel, dig in rows:
        f.write(f"{rel}\t{dig}\n")
PY
}

detect_code_patch_changes() {
  local before_file="$1"
  local after_file="$2"
  "$PYTHON_BIN" - "$before_file" "$after_file" <<'PY'
import sys
from pathlib import Path

def read_rows(path: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    if not path.exists():
        return d
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "\t" not in line:
            continue
        rel, dig = line.split("\t", 1)
        d[rel.strip()] = dig.strip()
    return d

before = read_rows(Path(sys.argv[1]))
after = read_rows(Path(sys.argv[2]))
changed = [rel for rel in sorted(set(before) | set(after)) if before.get(rel) != after.get(rel)]
if changed:
    print(",".join(changed))
    raise SystemExit(0)
raise SystemExit(1)
PY
}

validate_final_message_contract() {
  local msg_file="$1"
  local require_patch="$2"
  "$PYTHON_BIN" - "$msg_file" "$require_patch" <<'PY'
import json
import sys
from pathlib import Path

msg_path = Path(sys.argv[1])
require_patch = sys.argv[2] == "1"
if not msg_path.exists() or msg_path.stat().st_size == 0:
    print("missing_final_message")
    raise SystemExit(1)
try:
    obj = json.loads(msg_path.read_text(encoding="utf-8"))
except Exception:
    print("invalid_final_message_json")
    raise SystemExit(1)
if not isinstance(obj, dict):
    print("invalid_final_message_payload")
    raise SystemExit(1)
if require_patch and obj.get("change_applied") is not True:
    print("change_applied_false")
    raise SystemExit(1)
print("ok")
PY
}

resolve_expected_source_cycle() {
  local reason="$1"
  local evt_cycle="${2:-}"
  if [[ -z "$evt_cycle" || ! "$evt_cycle" =~ ^[0-9]+$ ]]; then
    echo ""
    return
  fi
  if [[ "$reason" == "cycle_completed" || "$reason" == "model_review_due" ]]; then
    echo "$evt_cycle"
    return
  fi
  if [[ "$reason" == "awaiting_llm_action" ]]; then
    if (( evt_cycle >= 1 )); then
      echo $((evt_cycle - 1))
    else
      echo "0"
    fi
    return
  fi
  echo ""
}

should_throttle_awaiting_event() {
  local evt_cycle="${1:-}"
  if [[ -z "$evt_cycle" || ! "$evt_cycle" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  local throttled
  throttled="$(
    "$PYTHON_BIN" - "$AWAITING_GUARD_FILE" "$evt_cycle" "$AWAITING_MIN_INTERVAL_SEC" <<'PY'
import json
import sys
import time
from pathlib import Path

guard_path = Path(sys.argv[1])
cycle = int(sys.argv[2])
interval = int(sys.argv[3])
now = int(time.time())

payload = {}
if guard_path.exists():
    try:
        payload = json.loads(guard_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
if not isinstance(payload, dict):
    payload = {}

last_cycle = payload.get("cycle")
last_epoch = payload.get("epoch")
if isinstance(last_cycle, int) and isinstance(last_epoch, int):
    if last_cycle == cycle and now - last_epoch < interval:
        print("1")
        raise SystemExit(0)

guard_path.parent.mkdir(parents=True, exist_ok=True)
guard_path.write_text(
    json.dumps({"cycle": cycle, "epoch": now}, ensure_ascii=False, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
print("0")
PY
  )"
  [[ "$throttled" == "1" ]]
}

normalize_next_action_file() {
  local reason="${1:-}"
  local event_ts="${2:-}"
  local expected_cycle="${3:-}"
  local patched_paths_csv="${4:-}"
  local strategy_paths_csv="${5:-}"
  local allow_plan_only="${6:-1}"
  if [[ ! -s "$NEXT_ACTION_FILE" ]]; then
    echo "missing_next_action"
    return 1
  fi
  "$PYTHON_BIN" - "$NEXT_ACTION_FILE" "$reason" "$event_ts" "$expected_cycle" "$patched_paths_csv" "$strategy_paths_csv" "$allow_plan_only" <<'PY'
import json
import sys
from pathlib import Path

action_path = Path(sys.argv[1])
reason = sys.argv[2] if len(sys.argv) > 2 else ""
event_ts = sys.argv[3] if len(sys.argv) > 3 else ""
expected_cycle_raw = sys.argv[4] if len(sys.argv) > 4 else ""
patched_paths_csv = sys.argv[5] if len(sys.argv) > 5 else ""
strategy_paths_csv = sys.argv[6] if len(sys.argv) > 6 else ""
allow_plan_only = (sys.argv[7] if len(sys.argv) > 7 else "1") == "1"

try:
    payload = json.loads(action_path.read_text(encoding="utf-8"))
except Exception:
    print("invalid_json")
    raise SystemExit(1)
if not isinstance(payload, dict):
    print("invalid_payload")
    raise SystemExit(1)

changed = False

if "source_event_ts" not in payload and event_ts:
    payload["source_event_ts"] = event_ts
    changed = True

if "focus_metric" not in payload:
    payload["focus_metric"] = None
    changed = True

mechanism_plan = payload.get("mechanism_plan")
knob_plan = payload.get("knob_plan")
if not isinstance(mechanism_plan, list):
    mechanism_plan = []
    payload["mechanism_plan"] = mechanism_plan
    changed = True
if not isinstance(knob_plan, list):
    knob_plan = []
    payload["knob_plan"] = knob_plan
    changed = True
if not mechanism_plan and not knob_plan:
    payload["mechanism_plan"] = [
        {
            "mechanism": "low_spr_wet_firewall",
            "scale": 1.0,
            "reason": "dispatcher_autofill_min_plan",
        }
    ]
    changed = True

def _scale_valid(v):
    if v is None:
        return True
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        s = v.strip().lower()
        if not s:
            return False
        if s in {"tiny", "small", "medium", "large", "xlarge"}:
            return True
        try:
            float(s)
            return True
        except ValueError:
            return False
    return False

normalized_mechanism_plan = []
for row in payload.get("mechanism_plan") if isinstance(payload.get("mechanism_plan"), list) else []:
    if not isinstance(row, dict):
        continue
    row_obj = dict(row)
    if not _scale_valid(row_obj.get("scale")):
        row_obj["scale"] = 1.0
        changed = True
    normalized_mechanism_plan.append(row_obj)
if normalized_mechanism_plan != payload.get("mechanism_plan"):
    payload["mechanism_plan"] = normalized_mechanism_plan
    changed = True

expected_cycle = None
if expected_cycle_raw.lstrip("-").isdigit():
    expected_cycle = int(expected_cycle_raw)
if expected_cycle is not None and payload.get("source_cycle") != expected_cycle:
    payload["source_cycle"] = expected_cycle
    changed = True

patched_paths = []
for raw in patched_paths_csv.split(","):
    item = raw.strip().replace("\\", "/")
    while item.startswith("./"):
        item = item[2:]
    if item:
        patched_paths.append(item)

if reason in {"cycle_completed", "model_review_due", "awaiting_llm_action"}:
    patched_files = payload.get("patched_files")
    if not isinstance(patched_files, list):
        patched_files = []
        payload["patched_files"] = patched_files
        changed = True

    cleaned = []
    for row in patched_files:
        if isinstance(row, str):
            v = row.strip().replace("\\", "/")
            while v.startswith("./"):
                v = v[2:]
            if v:
                cleaned.append(v)
    if cleaned != patched_files:
        payload["patched_files"] = cleaned
        patched_files = cleaned
        changed = True

    if not patched_files and not allow_plan_only and patched_paths:
        payload["patched_files"] = patched_paths
        patched_files = list(patched_paths)
        changed = True

    desired_change_applied = bool(payload.get("patched_files"))
    if payload.get("change_applied") is not desired_change_applied:
        payload["change_applied"] = desired_change_applied
        changed = True

if changed:
    action_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("patched")
else:
    print("ok")
PY
}

write_dispatcher_heartbeat() {
  local hb_status="${1:-$last_evt_status}"
  local hb_reason="${2:-$last_evt_reason}"
  local hb_rc="${3:-$last_evt_rc}"
  local hb_restart="${4:-$last_evt_restart}"
  local ts
  ts="$(date '+%Y-%m-%dT%H:%M:%S%z')"
  local hb_status_json hb_reason_json
  hb_status_json="$(json_escape "$hb_status")"
  hb_reason_json="$(json_escape "$hb_reason")"
  printf '{"ts":"%s","pid":%s,"status":"%s","reason":"%s","rc":%s,"restart_count":%s}\n' \
    "$ts" "$$" "$hb_status_json" "$hb_reason_json" "$hb_rc" "$hb_restart" > "$DISPATCH_HEALTH_FILE"
  refresh_lock_lease
}

start_dispatcher_heartbeat_loop() {
  (
    while true; do
      write_dispatcher_heartbeat "alive" "heartbeat" "$last_evt_rc" "$last_evt_restart"
      sleep "$DISPATCH_HEARTBEAT_SEC"
    done
  ) &
  heartbeat_pid=$!
}

read_int_file() {
  local path="$1"
  local fallback="$2"
  local val=""
  if [[ -f "$path" ]]; then
    val="$(tr -cd '0-9' < "$path" 2>/dev/null || true)"
  fi
  if [[ -n "$val" ]]; then
    echo "$val"
  else
    echo "$fallback"
  fi
}

current_fail_streak() {
  read_int_file "$FAIL_STREAK_FILE" 0
}

reset_fail_state() {
  echo "0" > "$FAIL_STREAK_FILE"
  rm -f "$CIRCUIT_UNTIL_FILE"
}

open_circuit() {
  local now until
  now="$(date +%s)"
  until=$((now + HOOK_COOLDOWN_SEC))
  echo "$until" > "$CIRCUIT_UNTIL_FILE"
}

open_circuit_for_seconds() {
  local cool_sec="$1"
  local reason="${2:-dynamic}"
  if [[ ! "$cool_sec" =~ ^[0-9]+$ ]]; then
    cool_sec="$HOOK_COOLDOWN_SEC"
  fi
  if (( cool_sec < 60 )); then
    cool_sec=60
  fi
  if (( cool_sec > 43200 )); then
    cool_sec=43200
  fi
  local now until
  now="$(date +%s)"
  until=$((now + cool_sec))
  echo "$until" > "$CIRCUIT_UNTIL_FILE"
  echo "[$(date '+%F %T')] dispatcher: circuit opened reason=$reason cooldown_sec=$cool_sec" >> "$DISPATCH_LOG"
}

is_circuit_open() {
  local now until remain
  now="$(date +%s)"
  until="$(read_int_file "$CIRCUIT_UNTIL_FILE" 0)"
  if (( until > now )); then
    remain=$((until - now))
    echo "$remain"
    return 0
  fi
  if (( until > 0 )); then
    echo "[$(date '+%F %T')] dispatcher: circuit expired now=$now until=$until" >> "$DISPATCH_LOG"
  fi
  rm -f "$CIRCUIT_UNTIL_FILE"
  return 1
}

mark_hook_failure() {
  local streak
  streak="$(current_fail_streak)"
  streak=$((streak + 1))
  echo "$streak" > "$FAIL_STREAK_FILE"
  if (( streak >= HOOK_FAIL_STREAK_LIMIT )); then
    open_circuit
    echo "[$(date '+%F %T')] dispatcher: circuit opened fail_streak=$streak cooldown_sec=$HOOK_COOLDOWN_SEC" >> "$DISPATCH_LOG"
  fi
}

extract_usage_limit_reset_sec() {
  local err_file="$1"
  if [[ ! -s "$err_file" ]]; then
    echo ""
    return
  fi
  "$PYTHON_BIN" - "$err_file" <<'PY'
import re
import sys
from pathlib import Path

p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8", errors="replace")
if "usage_limit_reached" in text:
    m = re.search(r'"resets_in_seconds"\s*:\s*([0-9]+)', text)
    if not m:
        print("3600")
    else:
        print(m.group(1))
    raise SystemExit(0)
if "429 Too Many Requests" in text:
    print("900")
    raise SystemExit(0)
print("")
PY
}

update_hook_stats() {
  local status="$1"
  local reason="$2"
  local rc="$3"
  local run_id="$4"
  "$PYTHON_BIN" - "$HOOK_STATS_FILE" "$status" "$reason" "$rc" "$run_id" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path

path = Path(sys.argv[1])
status = sys.argv[2]
reason = sys.argv[3]
rc_raw = sys.argv[4]
run_id = sys.argv[5]
try:
    rc = int(rc_raw)
except Exception:
    rc = -1

if path.exists():
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        obj = {}
else:
    obj = {}
if not isinstance(obj, dict):
    obj = {}

obj.setdefault("total", 0)
obj.setdefault("success", 0)
obj.setdefault("failed", 0)
obj.setdefault("reasons", {})
obj.setdefault("last", {})

obj["total"] = int(obj["total"]) + 1
if status == "success":
    obj["success"] = int(obj["success"]) + 1
else:
    obj["failed"] = int(obj["failed"]) + 1

reasons = obj.get("reasons")
if not isinstance(reasons, dict):
    reasons = {}
reasons[reason] = int(reasons.get(reason, 0)) + 1
obj["reasons"] = reasons

obj["last"] = {
    "ts": datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
    "status": status,
    "reason": reason,
    "rc": rc,
    "run_id": run_id,
}

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

write_hook_result() {
  local out_dir="$1"
  local hook_status="$2"
  local attempts="$3"
  local used_attempt="$4"
  local rc="$5"
  local fail_reason="$6"
  local hook_status_json fail_reason_json
  hook_status_json="$(json_escape "$hook_status")"
  fail_reason_json="$(json_escape "$fail_reason")"
  printf '{"status":"%s","attempts":%s,"used_attempt":%s,"rc":%s,"fail_reason":"%s","timeout_sec":%s,"max_retries":%s}\n' \
    "$hook_status_json" "$attempts" "$used_attempt" "$rc" "$fail_reason_json" "$HOOK_TIMEOUT_SEC" "$HOOK_MAX_RETRIES" > "$out_dir/hook_result.json"
}

sanitize_token() {
  local s="${1:-}"
  s="$(printf "%s" "$s" | tr -cs '[:alnum:]_.-' '_' | sed -E 's/^_+|_+$//g')"
  if [[ -z "$s" ]]; then
    echo "na"
  else
    echo "$s"
  fi
}

build_prompt() {
  local prompt_file="$1"
  local raw_line="$2"
  local latest_cycle_dir="$3"
  local latest_completed_review="$4"
  local latest_completed_result="$5"
  local patch_files_csv="$HOOK_CODE_PATCH_FILES"
  local strategy_patch_files_csv="$HOOK_STRATEGY_PATCH_FILES"

  cat > "$prompt_file" <<'EOF'
你是 poker2 的无人值守 hook 子代理。请在本仓库执行以下流程并直接落地：
1) 读取事件：__RAW_LINE__
2) 必读（限量读取）：
   - AGENTS.md：只读前 220 行；
   - notes/iteration_journal.md：只读前 220 行 + 最后 220 行（严禁全量 cat）；
   - tmp/ralph_loop_state_v2.json（若存在）。
   - 最新 cycle 目录（可能未完成）: __LATEST_CYCLE_DIR__
   - 最新“已完成”周期 review: __LATEST_COMPLETED_REVIEW__
   - 最新“已完成”周期 result: __LATEST_COMPLETED_RESULT__
3) 执行约束（必须遵守）：
   - 禁止全局扫描：不要运行 find tmp、rg tmp、ls -R、du、tree 等大范围命令。
   - 仅允许读取本 prompt 已给出的关键文件路径；若文件不存在，直接按保守 fallback 继续，不做替代性全局搜索。
   - 命令预算控制在 10 条以内，优先最短链路完成“写 next_action + 写 next_plan”；除非明确是 runtime/syntax/import 崩溃，否则不要主动改共享 runtime core。
   - 验证命令必须使用 `python3`，不要使用 `python`。
   - 在 reason=cycle_completed / model_review_due / awaiting_llm_action 时，默认允许 plan-only ticket：只写 `tmp/ralph_next_action.json` + `tmp/ralph_next_plan.md`，不要求实际改代码文件。
   - 默认禁止修改共享 runtime/eval core：`tools/ralph_wiggum_loop.py,poker2/runtime/system_policy.py,poker2/cli/scrimmage.py,poker2/cli/scrimmage_batch.py`。
   - 只有当最近 completed cycle 明确是 runtime error / syntax / import crash 时，才允许进入 shared-runtime repair 模式；若真进入该模式，patched_files 才需要包含 `__PATCH_FILES__`。
   - 若确需落地文件，优先修改 trial-only 策略束而不是共享 runtime core；`patched_files` 若非空，必须包含 `__STRATEGY_PATCH_FILES__` 之一。
4) 按事件类型处理：
   - 若 reason=cycle_completed：
     a) 默认做轻量复盘，不跑重型评测，
     b) 产出下一轮可消费动作文件 tmp/ralph_next_action.json（覆盖写入），字段至少包含：
        - source_event_ts（string）
        - source_cycle（int|null）
        - change_applied（bool；仅当实际改了代码文件时为 true，plan-only 时为 false）
        - patched_files（array[string]；plan-only 时允许为空，只有实际 repair/patch 时才非空）
        - patch_manifest_ref（string|null；plan-only 时为 null，记录本轮补丁清单路径）
        - focus_metric（string|null）
        - mechanism_plan（array，元素为 {mechanism,scale,reason}，优先）
        - knob_plan（array，可为空；元素为 {key,delta,reason}）
        - quick_gate_hints（object，可含 focus_support_min_hands/focus_support_min_hits/behavior_delta_min）
        - note（string）
     c) 同时写入人类可读 tmp/ralph_next_plan.md（why/what/how/rollback/verify）；
     d) 若命中任一条件，优先输出更强的 mechanism_plan/knob_plan；不要默认改共享 runtime core：
        - state.no_improve_streak >= 2
        - 最近 completed review 的 quick_gate.reason 属于 quick_gate_no_behavior_delta / quick_gate_low_focus_support / quick_gate_no_eligible_candidate / quick_gate_forced_bet_integrity_fail
        - 最新 completed cycle 显示候选大量同分或行为无变化
        若最近 completed review 明确是 quick_gate_runtime_error 或语法/导入崩溃，才执行“1个可回退的 repair 改动 + 最小验证”；否则保持 plan-only。
     e) 若未命中上述条件，则保持“计划+动作文件”模式。
   - 若 reason=model_review_due：
     a) 执行“强化审查”，优先识别阻塞迭代效率的机制缺陷，
     b) 输出单机制改进计划（why/what/how/rollback/verify）并覆盖写入 tmp/ralph_next_action.json，
        且 mechanism_plan 至少 1 项（knob_plan 可为空），
     c) 默认只输出 plan；只有 runtime/syntax/import 崩溃时才执行 1 个高ROI repair 改动并做最小验证，
     d) 在 notes/iteration_journal.md 追加一条结果（change_type=Plan/Restructure/Patch）。
   - 若 reason=awaiting_llm_action：
     a) 视为当前迭代被 action ticket 门禁阻塞，必须优先解除阻塞；
     b) 覆盖写入 tmp/ralph_next_action.json，字段同 cycle_completed，且 source_cycle 必须等于 (event.cycle - 1)；
     c) 默认 plan-only 即可解除阻塞；仅当当前阻塞本身是 runtime/syntax/import 崩溃时，才要求 patched_files 非空并包含修复文件；
     d) 若不是 shared-runtime repair，优先用 mechanism_plan/knob_plan 解除阻塞，不要修改共享 runtime core。
   - 若 reason=target_achieved：生成最终结果摘要（含目标是否达成、关键证据、残余风险）到 tmp/ralph_autopilot_status.md；不要重启循环。
   - 若 reason=no_improve_limit 或 reason=worker_failed_or_unexpected_exit 或 reason=restart_limit_reached：
     a) 先定位根因（机制/评测/流程），
     b) 仅做一个高ROI、可回退、可解释的改动，
     c) 运行最小必要验证，
     d) 在 notes/iteration_journal.md 追加一条结果，
     e) 确保 tools/ralph_loop_supervisor.sh 在运行（若没运行则启动）。
   - 其他 reason：写明状态并退出。
5) 最终输出 machine-readable JSON：包含 decision、reason、evidence_ref、next_action、change_applied（bool）、verify_result。
EOF

  "$PYTHON_BIN" - "$prompt_file" "$raw_line" "$latest_cycle_dir" "$latest_completed_review" "$latest_completed_result" "$patch_files_csv" "$strategy_patch_files_csv" <<'PY'
from pathlib import Path
import sys

prompt_path = Path(sys.argv[1])
raw_line = sys.argv[2] if len(sys.argv) > 2 else "null"
latest_cycle_dir = sys.argv[3] if len(sys.argv) > 3 else "null"
latest_completed_review = sys.argv[4] if len(sys.argv) > 4 else "null"
latest_completed_result = sys.argv[5] if len(sys.argv) > 5 else "null"
patch_files_csv = sys.argv[6] if len(sys.argv) > 6 else ""
strategy_patch_files_csv = sys.argv[7] if len(sys.argv) > 7 else ""

text = prompt_path.read_text(encoding="utf-8")
repl = {
    "__RAW_LINE__": raw_line or "null",
    "__LATEST_CYCLE_DIR__": latest_cycle_dir or "null",
    "__LATEST_COMPLETED_REVIEW__": latest_completed_review or "null",
    "__LATEST_COMPLETED_RESULT__": latest_completed_result or "null",
    "__PATCH_FILES__": patch_files_csv or "tools/ralph_wiggum_loop.py",
    "__STRATEGY_PATCH_FILES__": strategy_patch_files_csv or "poker2/runtime/system_policy.py",
}
for k, v in repl.items():
    text = text.replace(k, v)
prompt_path.write_text(text, encoding="utf-8")
PY

  local prompt_size=0
  prompt_size="$(wc -c < "$prompt_file" | tr -d ' ')"
  if [[ "$prompt_size" =~ ^[0-9]+$ ]] && (( prompt_size > PROMPT_MAX_BYTES )); then
    cat > "$prompt_file" <<'EOF'
你是 poker2 的无人值守 hook 子代理。输出 machine-readable JSON，包含 decision、reason、evidence_ref、next_action、change_applied、verify_result。
仅执行以下最小动作：
1) 读取事件：__RAW_LINE__
2) 读取：AGENTS.md(前220行)、notes/iteration_journal.md(前220+后220)、tmp/ralph_loop_state_v2.json、__LATEST_COMPLETED_REVIEW__、__LATEST_COMPLETED_RESULT__。
3) 写入 tmp/ralph_next_action.json 与 tmp/ralph_next_plan.md。
4) 禁止全局扫描命令（find tmp/rg tmp/ls -R/du/tree）。
5) 验证命令必须使用 `python3`，不要使用 `python`。
6) 若 reason=cycle_completed 或 reason=model_review_due 或 reason=awaiting_llm_action，默认允许只写 plan-only ticket。
7) 只有在 runtime/syntax/import 崩溃 repair 模式下，才要求 patched_files(非空) 且 `evidence_ref` 包含被修改代码文件路径。
8) 若 patched_files 非空，则必须至少包含一个策略文件：__STRATEGY_PATCH_FILES__。
EOF
    "$PYTHON_BIN" - "$prompt_file" "$raw_line" "$latest_completed_review" "$latest_completed_result" "$patch_files_csv" "$strategy_patch_files_csv" <<'PY'
from pathlib import Path
import sys

prompt_path = Path(sys.argv[1])
raw_line = sys.argv[2] if len(sys.argv) > 2 else "null"
latest_completed_review = sys.argv[3] if len(sys.argv) > 3 else "null"
latest_completed_result = sys.argv[4] if len(sys.argv) > 4 else "null"
patch_files_csv = sys.argv[5] if len(sys.argv) > 5 else ""
strategy_patch_files_csv = sys.argv[6] if len(sys.argv) > 6 else ""
text = prompt_path.read_text(encoding="utf-8")
text = text.replace("__RAW_LINE__", raw_line or "null")
text = text.replace("__LATEST_COMPLETED_REVIEW__", latest_completed_review or "null")
text = text.replace("__LATEST_COMPLETED_RESULT__", latest_completed_result or "null")
text = text.replace("__PATCH_FILES__", patch_files_csv or "tools/ralph_wiggum_loop.py")
text = text.replace("__STRATEGY_PATCH_FILES__", strategy_patch_files_csv or "poker2/runtime/system_policy.py")
prompt_path.write_text(text, encoding="utf-8")
PY
    echo "[$(date '+%F %T')] dispatcher: prompt_truncated size=${prompt_size} max=${PROMPT_MAX_BYTES}" >> "$DISPATCH_LOG"
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
    if [[ -n "$old_pid" ]] && [[ -n "$lock_age" ]] && (( lock_age <= DISPATCH_LOCK_STALE_SEC )); then
      if pid_is_alive "$old_pid"; then
        echo "[$(date '+%F %T')] dispatcher already running lock_pid=$old_pid age=${lock_age}s" >> "$DISPATCH_LOG"
        exit 0
      fi
    fi
    rm -f "$LOCK_FILE"
    tries=$((tries + 1))
    if (( tries >= 5 )); then
      echo "[$(date '+%F %T')] dispatcher failed to acquire lock after retries" >> "$DISPATCH_LOG"
      exit 1
    fi
    sleep 1
  done
}

release_lock() {
  if [[ "$LOCK_OWNED" != "1" ]]; then
    return
  fi
  if [[ -n "$heartbeat_pid" ]]; then
    kill -TERM "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
  fi
  write_dispatcher_heartbeat "stopped" "$last_evt_reason" "$last_evt_rc" "$last_evt_restart"
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
write_dispatcher_heartbeat "running" "startup" 0 0
echo "[$(date '+%F %T')] dispatcher: started pid=$$ codex_home=$CODEX_HOME_DIR" >> "$DISPATCH_LOG"
start_dispatcher_heartbeat_loop

should_handle_event() {
  local evt_status="$1"
  local reason="$2"
  if [[ "$evt_status" == "stopped" ]]; then
    return 0
  fi
  if [[ "$reason" == "awaiting_llm_action" && ( "$evt_status" == "heartbeat" || "$evt_status" == "stop" || "$evt_status" == "restart" || "$evt_status" == "checkpoint" ) ]]; then
    return 0
  fi
  if [[ "$evt_status" == "checkpoint" && "$reason" == "model_review_due" ]]; then
    return 0
  fi
  if [[ "$evt_status" == "checkpoint" && "$reason" == "cycle_completed" ]]; then
    return 0
  fi
  if [[ "$evt_status" == "restart" && ( "$reason" == "worker_failed_or_unexpected_exit" || "$reason" == "stall_timeout" ) ]]; then
    return 0
  fi
  return 1
}

reason_requires_next_action() {
  local reason="$1"
  [[ "$reason" == "cycle_completed" || "$reason" == "model_review_due" || "$reason" == "awaiting_llm_action" ]]
}

extract_field() {
  local line="$1"
  local key="$2"
  "$PYTHON_BIN" - "$line" "$key" <<'PY'
import json
import sys

line = sys.argv[1] if len(sys.argv) > 1 else ""
key = sys.argv[2] if len(sys.argv) > 2 else ""
try:
    obj = json.loads(line)
except Exception:
    print("")
    raise SystemExit(0)
value = obj.get(key)
if isinstance(value, str):
    print(value)
else:
    print("")
PY
}

extract_num_field() {
  local line="$1"
  local key="$2"
  "$PYTHON_BIN" - "$line" "$key" <<'PY'
import json
import sys

line = sys.argv[1] if len(sys.argv) > 1 else ""
key = sys.argv[2] if len(sys.argv) > 2 else ""
try:
    obj = json.loads(line)
except Exception:
    print("")
    raise SystemExit(0)
value = obj.get(key)
if isinstance(value, int):
    print(value)
elif isinstance(value, str) and value.isdigit():
    print(value)
else:
    print("")
PY
}

validate_hook_output() {
  local events_file="$1"
  local msg_file="$2"
  local first_line=""
  if [[ ! -s "$events_file" ]]; then
    echo "missing_events"
    return 1
  fi
  if [[ ! -s "$msg_file" ]]; then
    echo "missing_final_message"
    return 1
  fi
  first_line="$(head -n 1 "$msg_file" 2>/dev/null | tr -d '\r' | sed -E 's/[[:space:]]+$//')"
  if [[ -z "$first_line" ]]; then
    echo "empty_final_message"
    return 1
  fi
  echo "ok"
  return 0
}

hydrate_next_action_from_message() {
  local msg_file="$1"
  local reason="${2:-}"
  local event_ts="${3:-}"
  local expected_source_cycle="${4:-}"
  local patched_paths_csv="${5:-}"
  local strategy_paths_csv="${6:-}"
  local allow_plan_only="${7:-1}"
  "$PYTHON_BIN" - "$msg_file" "$NEXT_ACTION_FILE" "$reason" "$event_ts" "$expected_source_cycle" "$patched_paths_csv" "$strategy_paths_csv" "$allow_plan_only" <<'PY'
import json
import sys
from pathlib import Path

msg_path = Path(sys.argv[1])
action_path = Path(sys.argv[2])
reason = sys.argv[3] if len(sys.argv) > 3 else ""
event_ts = sys.argv[4] if len(sys.argv) > 4 else ""
expected_cycle_raw = sys.argv[5] if len(sys.argv) > 5 else ""
patched_paths_csv = sys.argv[6] if len(sys.argv) > 6 else ""
strategy_paths_csv = sys.argv[7] if len(sys.argv) > 7 else ""
allow_plan_only = (sys.argv[8] if len(sys.argv) > 8 else "1") == "1"

if action_path.exists() and action_path.stat().st_size > 0:
    print("existing")
    raise SystemExit(0)
if not msg_path.exists() or msg_path.stat().st_size <= 0:
    print("missing_message")
    raise SystemExit(1)

text = msg_path.read_text(encoding="utf-8", errors="replace").strip()
parsed = None
if text:
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
if not isinstance(parsed, dict):
    for raw in reversed(text.splitlines()):
        raw = raw.strip()
        if not raw.startswith("{") or not raw.endswith("}"):
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict):
            parsed = obj
            break
if not isinstance(parsed, dict):
    print("invalid_message")
    raise SystemExit(1)

next_action = parsed.get("next_action")
payload = next_action if isinstance(next_action, dict) else {}
if not isinstance(payload, dict):
    payload = {}
payload = dict(payload)

def _norm_csv(csv_text: str) -> list[str]:
    out: list[str] = []
    for raw in (csv_text or "").split(","):
        row = raw.strip().replace("\\", "/")
        while row.startswith("./"):
            row = row[2:]
        if row:
            out.append(row)
    return out

patched_paths = _norm_csv(patched_paths_csv)
strategy_paths = set(_norm_csv(strategy_paths_csv))

if "source_event_ts" not in payload and event_ts:
    payload["source_event_ts"] = event_ts
if "focus_metric" not in payload:
    payload["focus_metric"] = None
if not isinstance(payload.get("mechanism_plan"), list):
    payload["mechanism_plan"] = []
if not isinstance(payload.get("knob_plan"), list):
    payload["knob_plan"] = []
if not payload["mechanism_plan"] and not payload["knob_plan"]:
    payload["mechanism_plan"] = [
        {"mechanism": "low_spr_wet_firewall", "scale": 1.0, "reason": "dispatcher_autofill_min_plan"}
    ]

if expected_cycle_raw.lstrip("-").isdigit():
    payload["source_cycle"] = int(expected_cycle_raw)
if reason in {"cycle_completed", "model_review_due", "awaiting_llm_action"}:
    patched = payload.get("patched_files")
    if not isinstance(patched, list):
        patched = []
    cleaned: list[str] = []
    for raw in patched:
        if not isinstance(raw, str):
            continue
        row = raw.strip().replace("\\", "/")
        while row.startswith("./"):
            row = row[2:]
        if row:
            cleaned.append(row)
    if not cleaned and not allow_plan_only and patched_paths:
        cleaned = list(patched_paths)
    payload["patched_files"] = cleaned
    payload["change_applied"] = bool(cleaned)

action_path.parent.mkdir(parents=True, exist_ok=True)
action_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("patched")
PY
}

validate_next_action_file() {
  local reason="${1:-}"
  local expected_source_cycle="${2:-}"
  local required_strategy_paths_csv="${3:-}"
  local allow_plan_only="${4:-1}"
  local shared_runtime_paths_csv="${5:-}"
  local allow_shared_runtime_patch="${6:-0}"
  if [[ ! -s "$NEXT_ACTION_FILE" ]]; then
    echo "missing_next_action"
    return 1
  fi
  if ! "$PYTHON_BIN" - "$NEXT_ACTION_FILE" "$reason" "$expected_source_cycle" "$required_strategy_paths_csv" "$allow_plan_only" "$shared_runtime_paths_csv" "$allow_shared_runtime_patch" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
reason = sys.argv[2] if len(sys.argv) > 2 else ""
expected_cycle_raw = sys.argv[3] if len(sys.argv) > 3 else ""
strategy_csv = sys.argv[4] if len(sys.argv) > 4 else ""
allow_plan_only = (sys.argv[5] if len(sys.argv) > 5 else "1") == "1"
shared_runtime_csv = sys.argv[6] if len(sys.argv) > 6 else ""
allow_shared_runtime_patch = (sys.argv[7] if len(sys.argv) > 7 else "0") == "1"
obj = json.loads(p.read_text(encoding="utf-8"))
if not isinstance(obj, dict):
    raise SystemExit(1)
required = ("source_event_ts", "focus_metric")
for k in required:
    if k not in obj:
        raise SystemExit(1)
def has_nonempty_plan(v):
    return isinstance(v, list) and len(v) >= 1
if not (has_nonempty_plan(obj.get("mechanism_plan")) or has_nonempty_plan(obj.get("knob_plan"))):
    raise SystemExit(1)

def scale_valid(v):
    if v is None:
        return True
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        s = v.strip().lower()
        if not s:
            return False
        if s in {"tiny", "small", "medium", "large", "xlarge"}:
            return True
        try:
            float(s)
            return True
        except ValueError:
            return False
    return False

mechanism_plan = obj.get("mechanism_plan")
if isinstance(mechanism_plan, list):
    for row in mechanism_plan:
        if not isinstance(row, dict):
            raise SystemExit(1)
        if not scale_valid(row.get("scale")):
            raise SystemExit(1)
if reason in {"cycle_completed", "model_review_due", "awaiting_llm_action"}:
    src = obj.get("source_cycle")
    if not isinstance(src, int):
        raise SystemExit(1)
    if expected_cycle_raw.isdigit() and src != int(expected_cycle_raw):
        raise SystemExit(1)
    patched = obj.get("patched_files")
    if patched is None:
        patched = []
    if not isinstance(patched, list):
        raise SystemExit(1)
    if not all(isinstance(x, str) and x for x in patched):
        raise SystemExit(1)
    if patched:
        shared_runtime_paths = []
        for raw in shared_runtime_csv.split(","):
            row = raw.strip().replace("\\", "/")
            while row.startswith("./"):
                row = row[2:]
            if row:
                shared_runtime_paths.append(row)
        if shared_runtime_paths and not allow_shared_runtime_patch:
            patched_now = []
            for raw in patched:
                row = raw.strip().replace("\\", "/")
                while row.startswith("./"):
                    row = row[2:]
                if row:
                    patched_now.append(row)
            if any(row in shared_runtime_paths for row in patched_now):
                raise SystemExit(1)
        if obj.get("change_applied") is not True:
            raise SystemExit(1)
        required = []
        for raw in strategy_csv.split(","):
            row = raw.strip().replace("\\", "/")
            while row.startswith("./"):
                row = row[2:]
            if row:
                required.append(row)
        if required:
            has_required = False
            for raw in patched:
                val = raw.strip().replace("\\", "/")
                while val.startswith("./"):
                    val = val[2:]
                if val in required:
                    has_required = True
                    break
            if not has_required:
                raise SystemExit(1)
    elif not allow_plan_only:
        raise SystemExit(1)
PY
  then
    echo "invalid_next_action"
    return 1
  fi
  echo "ok"
  return 0
}

run_codex_once() {
  local prompt_file="$1"
  local events_file="$2"
  local msg_file="$3"
  local err_file="$4"
  local start_epoch now_epoch elapsed
  local timed_out=0
  local child_pid rc

  CODEX_HOME="$CODEX_HOME_DIR" codex exec \
    --full-auto \
    --sandbox workspace-write \
    --cd "$ROOT_DIR" \
    --json \
    --output-last-message "$msg_file" \
    - < "$prompt_file" > "$events_file" 2>"$err_file" &
  child_pid=$!
  start_epoch="$(date +%s)"

  while kill -0 "$child_pid" 2>/dev/null; do
    sleep 1
    now_epoch="$(date +%s)"
    elapsed=$((now_epoch - start_epoch))
    if (( elapsed >= HOOK_TIMEOUT_SEC )); then
      timed_out=1
      kill -TERM "$child_pid" 2>/dev/null || true
      sleep 2
      kill -KILL "$child_pid" 2>/dev/null || true
      break
    fi
  done

  set +e
  wait "$child_pid"
  rc=$?
  set -e
  if (( timed_out == 1 )); then
    rc=124
  fi
  if [[ -s "$err_file" ]]; then
    {
      echo "[$(date '+%F %T')] dispatcher: codex_stderr_begin rc=$rc"
      tail -n 40 "$err_file"
      echo "[$(date '+%F %T')] dispatcher: codex_stderr_end"
    } >> "$DISPATCH_LOG"
  fi
  echo "$rc"
}

run_codex_hook() {
  local raw_line="$1"
  local ts evt_status reason rc restart_count evt_cycle expected_source_cycle
  ts="$(extract_field "$raw_line" "ts")"
  evt_status="$(extract_field "$raw_line" "status")"
  reason="$(extract_field "$raw_line" "reason")"
  rc="$(extract_num_field "$raw_line" "rc")"
  restart_count="$(extract_num_field "$raw_line" "restart_count")"
  evt_cycle="$(extract_num_field "$raw_line" "cycle")"
  [[ -z "$rc" ]] && rc="0"
  [[ -z "$restart_count" ]] && restart_count="0"
  [[ -z "$evt_cycle" ]] && evt_cycle=""
  expected_source_cycle="$(resolve_expected_source_cycle "$reason" "$evt_cycle")"

  local run_id out_dir prompt_file safe_status safe_reason
  safe_status="$(sanitize_token "$evt_status")"
  safe_reason="$(sanitize_token "$reason")"
  run_id="$(date '+%Y%m%d_%H%M%S')_${safe_status}_${safe_reason}_$$_$RANDOM"
  out_dir="$RUNS_DIR/$run_id"
  prompt_file="$out_dir/prompt.txt"
  mkdir -p "$out_dir"

  local latest_cycle_dir latest_completed_cycle latest_completed_review latest_completed_result
  latest_cycle_dir="$(find tmp/ralph_loop_runs_v2 -maxdepth 1 -type d -name 'cycle_*' | sort | tail -n 1 || true)"
  latest_completed_cycle=""
  while IFS= read -r d; do
    [[ -z "$d" ]] && continue
    if [[ -f "$d/review.json" && -f "$d/cycle_result.json" ]]; then
      latest_completed_cycle="$d"
    fi
  done < <(find tmp/ralph_loop_runs_v2 -maxdepth 1 -type d -name 'cycle_*' | sort)
  if [[ -n "$latest_completed_cycle" ]]; then
    latest_completed_review="$latest_completed_cycle/review.json"
    latest_completed_result="$latest_completed_cycle/cycle_result.json"
  else
    latest_completed_review="null"
    latest_completed_result="null"
  fi

  build_prompt "$prompt_file" "$raw_line" "${latest_cycle_dir:-null}" "${latest_completed_review:-null}" "${latest_completed_result:-null}"

  echo "[$(date '+%F %T')] dispatcher: handling status=$evt_status reason=$reason rc=$rc restart=$restart_count" >> "$DISPATCH_LOG"
  last_evt_status="$evt_status"
  last_evt_reason="$reason"
  last_evt_rc="$rc"
  last_evt_restart="$restart_count"
  write_dispatcher_heartbeat "handling" "$last_evt_reason" "$last_evt_rc" "$last_evt_restart"

  local attempt=1
  local max_attempts
  local final_rc=1
  local final_reason="unknown_failure"
  local final_events=""
  local final_msg=""
  local validation_reason
  local action_validation_reason
  local events_attempt
  local msg_attempt
  local err_attempt
  local usage_limit_reset_sec
  local sleep_sec
  local require_code_patch="0"
  local require_strategy_patch="0"
  local required_strategy_paths_csv=""
  local code_hash_before="$out_dir/code_hash_before.txt"
  local code_hash_after
  local code_changed_paths=""
  local contract_validation_reason
  local normalize_reason
  max_attempts=$((HOOK_MAX_RETRIES + 1))
  if requires_code_patch_for_reason "$reason"; then
    require_code_patch="1"
  fi
  if requires_strategy_patch_for_reason "$reason"; then
    require_strategy_patch="1"
    required_strategy_paths_csv="$HOOK_STRATEGY_PATCH_FILES"
  fi
  snapshot_code_patch_hashes "$code_hash_before"

  while (( attempt <= max_attempts )); do
    events_attempt="$out_dir/codex_events_attempt${attempt}.jsonl"
    msg_attempt="$out_dir/final_message_attempt${attempt}.txt"
    err_attempt="$out_dir/codex_stderr_attempt${attempt}.log"
    rm -f "$events_attempt" "$msg_attempt" "$err_attempt"

    final_rc="$(run_codex_once "$prompt_file" "$events_attempt" "$msg_attempt" "$err_attempt")"
    if [[ -z "$final_rc" || ! "$final_rc" =~ ^-?[0-9]+$ ]]; then
      final_rc=1
    fi
    code_changed_paths=""
    normalize_reason="ok"
    validation_reason="$(validate_hook_output "$events_attempt" "$msg_attempt" || true)"
    if [[ -z "$validation_reason" ]]; then
      validation_reason="validation_unknown"
    fi
    if [[ "$final_rc" == "0" && "$validation_reason" == "ok" && "$require_code_patch" == "1" ]]; then
      code_hash_after="$out_dir/code_hash_after_attempt${attempt}.txt"
      snapshot_code_patch_hashes "$code_hash_after"
      code_changed_paths="$(detect_code_patch_changes "$code_hash_before" "$code_hash_after" || true)"
      if [[ -n "$code_changed_paths" ]]; then
        echo "$code_changed_paths" > "$out_dir/code_patch_changed_files_attempt${attempt}.txt"
        echo "[$(date '+%F %T')] dispatcher: code_patch_detected run=$run_id attempt=$attempt files=$code_changed_paths" >> "$DISPATCH_LOG"
      fi
    fi
    if [[ "$final_rc" == "0" && "$validation_reason" == "ok" ]]; then
      if reason_requires_next_action "$reason"; then
        if [[ ! -s "$NEXT_ACTION_FILE" ]]; then
          hydrate_next_action_from_message \
            "$msg_attempt" \
            "$reason" \
            "$ts" \
            "$expected_source_cycle" \
            "$code_changed_paths" \
            "$required_strategy_paths_csv" \
            "$HOOK_ALLOW_PLAN_ONLY" >/dev/null 2>&1 || true
        fi
        normalize_reason="$(normalize_next_action_file "$reason" "$ts" "$expected_source_cycle" "$code_changed_paths" "$required_strategy_paths_csv" "$HOOK_ALLOW_PLAN_ONLY" || true)"
        if [[ "$normalize_reason" == "missing_next_action" || "$normalize_reason" == "invalid_json" || "$normalize_reason" == "invalid_payload" ]]; then
          validation_reason="$normalize_reason"
        fi
      fi
    fi
    if [[ "$final_rc" == "0" && "$validation_reason" == "ok" ]]; then
      if reason_requires_next_action "$reason"; then
        action_validation_reason="$(validate_next_action_file "$reason" "$expected_source_cycle" "$required_strategy_paths_csv" "$HOOK_ALLOW_PLAN_ONLY" "$HOOK_SHARED_RUNTIME_PATCH_FILES" "$HOOK_ALLOW_SHARED_RUNTIME_PATCH" || true)"
        if [[ "$action_validation_reason" != "ok" ]]; then
          validation_reason="$action_validation_reason"
        fi
      fi
    fi
    if [[ "$final_rc" == "0" && "$validation_reason" == "ok" ]]; then
      contract_validation_reason="$(validate_final_message_contract "$msg_attempt" "$require_code_patch" || true)"
      if [[ "$contract_validation_reason" != "ok" ]]; then
        validation_reason="$contract_validation_reason"
      fi
    fi
    if [[ "$final_rc" == "0" && "$validation_reason" == "ok" && "$require_code_patch" == "1" ]]; then
      if [[ -z "$code_changed_paths" ]]; then
        validation_reason="no_mechanism_code_patch"
      fi
    fi
    if [[ "$final_rc" == "0" && "$validation_reason" == "ok" && "$require_strategy_patch" == "1" ]]; then
      if ! csv_contains_any_required_path "$code_changed_paths" "$required_strategy_paths_csv"; then
        validation_reason="missing_strategy_code_patch"
      fi
    fi
    if [[ "$final_rc" == "0" && "$validation_reason" == "ok" ]]; then
      final_reason="ok"
      final_events="$events_attempt"
      final_msg="$msg_attempt"
      break
    fi

    usage_limit_reset_sec="$(extract_usage_limit_reset_sec "$err_attempt")"
    if [[ "$final_rc" == "124" ]]; then
      final_reason="timeout"
    elif [[ -n "$usage_limit_reset_sec" ]]; then
      final_reason="usage_limit_reached"
      open_circuit_for_seconds "$usage_limit_reset_sec" "$final_reason"
    elif [[ "$validation_reason" != "ok" ]]; then
      final_reason="$validation_reason"
    else
      final_reason="codex_rc_${final_rc}"
    fi

    echo "[$(date '+%F %T')] dispatcher: attempt_failed run=$run_id attempt=$attempt rc=$final_rc reason=$final_reason" >> "$DISPATCH_LOG"
    if [[ "$final_reason" == "usage_limit_reached" ]]; then
      break
    fi
    if (( attempt < max_attempts )); then
      sleep_sec=$((HOOK_RETRY_BACKOFF_SEC * attempt))
      sleep "$sleep_sec"
    fi
    attempt=$((attempt + 1))
  done

  if [[ "$final_reason" == "ok" ]]; then
    cp "$final_events" "$out_dir/codex_events.jsonl"
    cp "$final_msg" "$out_dir/final_message.txt"
    write_hook_result "$out_dir" "success" "$attempt" "$attempt" 0 "ok"
    update_hook_stats "success" "ok" 0 "$run_id"
    reset_fail_state
    echo "[$(date '+%F %T')] dispatcher: completed run=$run_id attempts=$attempt" >> "$DISPATCH_LOG"
    write_dispatcher_heartbeat "ok" "$last_evt_reason" 0 "$last_evt_restart"
    return 0
  fi

  if [[ -f "$events_attempt" ]]; then
    cp "$events_attempt" "$out_dir/codex_events.jsonl"
  fi
  if [[ -f "$msg_attempt" ]]; then
    cp "$msg_attempt" "$out_dir/final_message.txt"
  fi
  if [[ -f "$err_attempt" ]]; then
    cp "$err_attempt" "$out_dir/codex_stderr.log"
  fi
  write_hook_result "$out_dir" "failed" "$attempt" "$attempt" "$final_rc" "$final_reason"
  update_hook_stats "failed" "$final_reason" "$final_rc" "$run_id"
  mark_hook_failure
  echo "[$(date '+%F %T')] dispatcher: failed run=$run_id attempts=$attempt rc=$final_rc reason=$final_reason" >> "$DISPATCH_LOG"
  write_dispatcher_heartbeat "failed" "$final_reason" "$final_rc" "$last_evt_restart"
  return 1
}

codex_auth_ready() {
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    return 0
  fi
  if [[ -f "$CODEX_HOME_DIR/auth.json" ]]; then
    return 0
  fi
  if [[ -f "$HOME/.codex/auth.json" ]]; then
    return 0
  fi
  return 1
}

read_state_last_cycle() {
  "$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

p = Path("tmp/ralph_loop_state_v2.json")
if not p.exists():
    print("")
    raise SystemExit(0)
try:
    obj = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)
v = obj.get("last_cycle")
if isinstance(v, int):
    print(v)
elif isinstance(v, str) and v.isdigit():
    print(v)
else:
    print("")
PY
}

tail -n 0 -F "$EVENT_LOG" | while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  line_hash="$(printf "%s" "$line" | shasum -a 256 | awk '{print $1}')"
  last_hash=""
  if [[ -f "$LAST_HASH_FILE" ]]; then
    last_hash="$(cat "$LAST_HASH_FILE" || true)"
  fi
  if [[ "$line_hash" == "$last_hash" ]]; then
    continue
  fi
  echo "$line_hash" > "$LAST_HASH_FILE"

  evt_status="$(extract_field "$line" "status")"
  reason="$(extract_field "$line" "reason")"
  if should_handle_event "$evt_status" "$reason"; then
    rc="$(extract_num_field "$line" "rc")"
    restart_count="$(extract_num_field "$line" "restart_count")"
    evt_cycle="$(extract_num_field "$line" "cycle")"
    state_cycle=""
    [[ -z "$rc" ]] && rc="0"
    [[ -z "$restart_count" ]] && restart_count="0"
    [[ -z "$evt_cycle" ]] && evt_cycle=""

    if [[ "$reason" == "awaiting_llm_action" ]]; then
      if should_throttle_awaiting_event "$evt_cycle"; then
        echo "[$(date '+%F %T')] dispatcher: handling status=skipped reason=awaiting_throttled rc=$rc restart=$restart_count cycle=${evt_cycle:-na}" >> "$DISPATCH_LOG"
        write_dispatcher_heartbeat "skipped" "awaiting_throttled" "$rc" "$restart_count"
        continue
      fi
    fi

    if [[ "$reason" == "cycle_completed" || "$reason" == "model_review_due" ]]; then
      state_cycle="$(read_state_last_cycle || true)"
      if [[ -n "$evt_cycle" && "$evt_cycle" =~ ^[0-9]+$ && -n "$state_cycle" && "$state_cycle" =~ ^[0-9]+$ ]]; then
        if (( evt_cycle < state_cycle )); then
          echo "[$(date '+%F %T')] dispatcher: handling status=skipped reason=stale_event rc=$rc restart=$restart_count event_cycle=$evt_cycle state_cycle=$state_cycle" >> "$DISPATCH_LOG"
          write_dispatcher_heartbeat "skipped" "stale_event" "$rc" "$restart_count"
          continue
        fi
      fi
    fi

    if ! codex_auth_ready; then
      echo "[$(date '+%F %T')] dispatcher: handling status=skipped reason=no_auth rc=$rc restart=$restart_count" >> "$DISPATCH_LOG"
      write_dispatcher_heartbeat "skipped" "no_auth" "$rc" "$restart_count"
      continue
    fi
    if remain_sec="$(is_circuit_open)"; then
      echo "[$(date '+%F %T')] dispatcher: handling status=skipped reason=circuit_open rc=$rc restart=$restart_count remain_sec=$remain_sec" >> "$DISPATCH_LOG"
      continue
    fi
    run_codex_hook "$line" || true
  fi
done
