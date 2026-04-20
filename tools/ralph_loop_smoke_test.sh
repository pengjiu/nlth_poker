#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MAX_CYCLES="${MAX_CYCLES:-2}"
CHUNK_CYCLES="${CHUNK_CYCLES:-1}"
JOBS="${JOBS:-1}"
QUICK_HANDS="${QUICK_HANDS:-1}"
FULL_HANDS="${FULL_HANDS:-1}"
TIMEOUT_SEC="${TIMEOUT_SEC:-180}"
HEARTBEAT_SEC="${HEARTBEAT_SEC:-30}"
RUN_ROOT="${RUN_ROOT:-$(mktemp -d /tmp/ralph_loop_smoke_test_XXXXXX)}"

if [[ "$MAX_CYCLES" -lt 2 ]]; then
  echo "ERROR: MAX_CYCLES must be >= 2 (current: $MAX_CYCLES)" >&2
  exit 1
fi
if [[ "$CHUNK_CYCLES" -lt 1 || "$CHUNK_CYCLES" -ge "$MAX_CYCLES" ]]; then
  echo "ERROR: CHUNK_CYCLES must satisfy 1 <= CHUNK_CYCLES < MAX_CYCLES (current: $CHUNK_CYCLES)" >&2
  exit 1
fi

STATE_FILE="$RUN_ROOT/state.json"
GOAL_PACK="$RUN_ROOT/goal_pack_nohit.json"
RUNS_DIR="$RUN_ROOT/runs"
mkdir -p "$RUNS_DIR"

TAG="$(date +%Y%m%d_%H%M%S)"
ACTIVE_POLICY="system_bot_policy_v3_loop_active_smoke_${TAG}"
TRIAL_POLICY="system_bot_policy_v3_loop_trial_smoke_${TAG}"
EXPECTED_CHUNK_END="$CHUNK_CYCLES"
EXPECTED_NEXT="$((EXPECTED_CHUNK_END + 1))"

cat >"$GOAL_PACK" <<'JSON'
{
  "goal_pack_id": "loop_goal_pack_smoke_nohit_v1",
  "description": "Force target not met for checkpoint/resume/max_cycles smoke test.",
  "target_gates": {
    "coinpoker_tierA_min_bb100": 9999.0,
    "coinpoker_tierP_min_bb100": 9999.0,
    "coinpoker_pool_weighted_min_bb100": 9999.0,
    "coinpoker_br_worst_min_bb100": 9999.0,
    "gg_tierA_min_bb100": 9999.0,
    "gg_tierP_min_bb100": 9999.0
  },
  "promotion_gates": {
    "quick_min_delta": 9999.0,
    "full_min_delta": 9999.0,
    "regress_tolerance": 0.15
  }
}
JSON

cat >"$STATE_FILE" <<'JSON'
{
  "active_full_metrics": {
    "score": -1.0,
    "coinpoker": {
      "tierA_mean": -1.0,
      "tierP_mean": -1.0,
      "pool_weighted_mean": -1.0,
      "br_worst_mean": -1.0
    },
    "gg": {
      "tierA_mean": -1.0,
      "tierP_mean": -1.0
    }
  },
  "no_improve_streak": 0,
  "target_achieved": false
}
JSON

LOOP_CMD=(
  python3 tools/ralph_wiggum_loop.py
  --start-cycle 1
  --max-cycles "$MAX_CYCLES"
  --chunk-cycles "$CHUNK_CYCLES"
  --stop-no-improve 999
  --jobs "$JOBS"
  --quick-hands "$QUICK_HANDS"
  --quick-seeds "[3000]"
  --full-hands "$FULL_HANDS"
  --full-seeds "[2000]"
  --confirm-seeds "[2010]"
  --timeout-sec "$TIMEOUT_SEC"
  --heartbeat-sec "$HEARTBEAT_SEC"
  --quick-min-delta 9999
  --goal-pack "$GOAL_PACK"
  --state-file "$STATE_FILE"
  --runs-root "$RUNS_DIR"
  --active-policy "$ACTIVE_POLICY"
  --trial-policy "$TRIAL_POLICY"
  --quiet
)

RUN1_LOG="$RUN_ROOT/run1.log"
RUN2_LOG="$RUN_ROOT/run2.log"

echo "SMOKE RUN_ROOT=$RUN_ROOT"
echo "SMOKE RUN1: expect chunk checkpoint at cycle=$EXPECTED_CHUNK_END"
"${LOOP_CMD[@]}" >"$RUN1_LOG" 2>&1

if ! rg -q '"reason"\s*:\s*"chunk_checkpoint"' "$RUN1_LOG"; then
  echo "ERROR: run1 did not stop with chunk_checkpoint" >&2
  tail -n 40 "$RUN1_LOG" >&2
  exit 1
fi
if ! rg -q "\"cycle\"\\s*:\\s*${EXPECTED_CHUNK_END}" "$RUN1_LOG"; then
  echo "ERROR: run1 cycle is not ${EXPECTED_CHUNK_END}" >&2
  tail -n 40 "$RUN1_LOG" >&2
  exit 1
fi
if ! rg -q "\"next_cycle\"\\s*:\\s*${EXPECTED_NEXT}" "$RUN1_LOG"; then
  echo "ERROR: run1 next_cycle is not ${EXPECTED_NEXT}" >&2
  tail -n 40 "$RUN1_LOG" >&2
  exit 1
fi

echo "SMOKE RUN2: expect resume + max_cycles at cycle=$MAX_CYCLES"
"${LOOP_CMD[@]}" >"$RUN2_LOG" 2>&1

if ! rg -q '"reason"\s*:\s*"max_cycles"' "$RUN2_LOG"; then
  echo "ERROR: run2 did not stop with max_cycles" >&2
  tail -n 40 "$RUN2_LOG" >&2
  exit 1
fi
if ! rg -q "\"cycle\"\\s*:\\s*${MAX_CYCLES}" "$RUN2_LOG"; then
  echo "ERROR: run2 cycle is not ${MAX_CYCLES}" >&2
  tail -n 40 "$RUN2_LOG" >&2
  exit 1
fi

for c in $(seq 1 "$MAX_CYCLES"); do
  cid="$(printf "%03d" "$c")"
  count="$(find "$RUNS_DIR" -maxdepth 1 -type d -name "cycle_${cid}_*" | wc -l | tr -d ' ')"
  if [[ "$count" != "1" ]]; then
    echo "ERROR: cycle_${cid} directory count must be 1, actual=$count" >&2
    find "$RUNS_DIR" -maxdepth 1 -type d -name "cycle_${cid}_*" -print >&2
    exit 1
  fi
done

if ! rg -q "\"last_cycle\"\\s*:\\s*${MAX_CYCLES}" "$STATE_FILE"; then
  echo "ERROR: state last_cycle is not ${MAX_CYCLES}" >&2
  cat "$STATE_FILE" >&2
  exit 1
fi

echo "PASS: checkpoint/resume/max_cycles regression smoke passed."
echo "PASS: state=$STATE_FILE"
echo "PASS: runs=$RUNS_DIR"
echo "PASS: run1_log=$RUN1_LOG"
echo "PASS: run2_log=$RUN2_LOG"
