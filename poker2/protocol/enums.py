from __future__ import annotations

# Single-source-of-truth controlled-enum value sets (ARCHIETECTURE.md Normative anchors).

ACTION_KIND_ORDERED = ("FOLD", "CHECK", "CALL", "BET", "RAISE")
ACTION_KIND_VALUES = set(ACTION_KIND_ORDERED)
ACTION_KIND_ORDER = {k: i for i, k in enumerate(ACTION_KIND_ORDERED)}

STREET_ORDERED = ("PREFLOP", "FLOP", "TURN", "RIVER")
STREET_VALUES = set(STREET_ORDERED)
STREET_DEALT_VALUES = {"FLOP", "TURN", "RIVER"}

FORCED_BETS_KIND_ORDERED = ("sb", "bb", "ante", "straddle", "dead")
FORCED_BETS_KIND_VALUES = set(FORCED_BETS_KIND_ORDERED)

ACTION_SOURCE_ID_ORDERED = (
    "system_policy",
    "opponent_policy",
    "solver",
    "gate",
    "baseline_random",
)
ACTION_SOURCE_ID_VALUES = set(ACTION_SOURCE_ID_ORDERED)

FALLBACK_POLICY_MODE_ORDERED = (
    "fail_fast",
    "conservative_check_call",
    "snap_nearest",
    "clamp_then_snap",
)
FALLBACK_POLICY_MODE_VALUES = set(FALLBACK_POLICY_MODE_ORDERED)

MAPPING_REASON_CODE_ORDERED = (
    "none",
    "kind_override",
    "rounding",
    "illegal_action",
    "snap_to_bin",
    "clamp",
    "conservative_fallback",
    "other",
)
MAPPING_REASON_CODE_VALUES = set(MAPPING_REASON_CODE_ORDERED)

MW_RUNG_ID_ORDERED = ("baseline", "hu_isolate", "micro3", "reducer4p", "failsafe")
MW_RUNG_ID_VALUES = set(MW_RUNG_ID_ORDERED)

POLICY_KIND_ORDERED = ("model", "oracle", "live_oracle", "blueprint", "rule", "baseline")
POLICY_KIND_VALUES = set(POLICY_KIND_ORDERED)

STAGE_ID_ORDERED = ("init", "import-preflop", "solve-postflop", "train", "eval", "doctor", "stats")
STAGE_ID_VALUES = set(STAGE_ID_ORDERED)

ARTIFACT_KIND_ORDERED = (
    "runspec",
    "scenario_package",
    "jobs",
    "chunk",
    "manifest",
    "sqlite_index",
    "dataset",
    "model",
    "event_stream",
    "report",
)
ARTIFACT_KIND_VALUES = set(ARTIFACT_KIND_ORDERED)

STAGE_STATUS_ORDERED = ("pass", "fail")
STAGE_STATUS_VALUES = set(STAGE_STATUS_ORDERED)

STAGE_DEGRADED_REASON_ORDERED = (
    "missing_asset",
    "guard_triggered",
    "illegal_action",
    "mapping_lossy",
    "fallback_policy",
    "other",
)
STAGE_DEGRADED_REASON_VALUES = set(STAGE_DEGRADED_REASON_ORDERED)
