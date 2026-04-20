#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poker2.contractkit import canonicalize_json_bytes, sha256_hex
from poker2.protocol.policy import policy_id
from poker2.protocol.spot_policy import load_spot_policy, spot_policy_digest, validate_spot_policy

POLICIES_DIR = ROOT / "specs" / "policies"
POLICY_PARAMS_DIR = ROOT / "specs" / "policy_params"
SPOT_POLICIES_DIR = ROOT / "specs" / "spot_policies"
GENERATED_SPOT_POLICIES_DIR = SPOT_POLICIES_DIR / "generated"
JOURNAL_PATH = ROOT / "notes" / "iteration_journal.md"
LOCK_STALE_SEC_DEFAULT = 12 * 3600

DEFAULT_BASELINE_LABEL = "system_bot_policy_v3_retaliation_weight_v1"
DEFAULT_ACTIVE_LABEL = "system_bot_policy_v3_loop_active"
DEFAULT_TRIAL_LABEL = "system_bot_policy_v3_loop_trial"
LOOP_SYSTEM_PARAMS_SCHEMA_ID = "system_bot_params_v6"

DEFAULT_COINPOKER_SCENARIO = "coinpoker_7max_mw_v3_actionspace_v2"
DEFAULT_GG_SCENARIO = "gg_7max_mw_v3_actionspace_league_frozen_v2"
DEFAULT_PROFILE = "internal_profile_v1"

DEFAULT_TIER_A = "system_bot_league_7max_frozen_v1"
DEFAULT_TIER_P = "system_bot_league_7max_frozen_v3"
DEFAULT_POOL = str((ROOT / "specs" / "opponents" / "pools" / "system_bot_pool_v2.json"))
DEFAULT_GOAL_PACK = str((ROOT / "specs" / "loop_goals" / "goal_pack_top_human_v2.json"))
DEFAULT_PARETO_CONTRACT = str((ROOT / "specs" / "loop_goals" / "pareto_contract_v1.json"))
NEXT_ACTION_PATH = Path(os.environ.get("RALPH_NEXT_ACTION_PATH", str(ROOT / "tmp" / "ralph_next_action.json")))
FOCUS_SUPPORT_FOCUS_METRIC = "coinpoker.tierP_facingY_turnriver_worst_bb100"
DEFAULT_FOCUS_SUPPORT_MIN_HANDS = 12
DEFAULT_FOCUS_SUPPORT_MIN_HITS = 1
DEFAULT_BEHAVIOR_DELTA_MIN = 0.03
DEFAULT_QUICK_REGRESSION_TOLERANCE = 0.30
DEFAULT_FOCUS_SUPPORT_ADAPTIVE_SCALE = 0.75
DEFAULT_FOCUS_SUPPORT_ADAPTIVE_Z = 1.28155
DEFAULT_FOCUS_SUPPORT_ADAPTIVE_MIN_HANDS_RATIO = 0.40
DEFAULT_FOCUS_SUPPORT_ADAPTIVE_MIN_HANDS_ABS = 20
DEFAULT_FOCUS_TARGETED_ENABLE = True
DEFAULT_FOCUS_TARGETED_HANDS_RATIO = 0.45
DEFAULT_FOCUS_TARGETED_HANDS_MIN = 220
DEFAULT_FOCUS_TARGETED_HANDS_MAX = 700
DEFAULT_FOCUS_TARGETED_MAX_JOBS = 2
DEFAULT_FOCUS_STARVATION_SWITCH_STREAK = 4
DEFAULT_FOCUS_STARVATION_MAX_SWITCHES = 1
DEFAULT_RANKED_PROMOTION_RAW_FLOOR_MARGIN = 0.25
DEFAULT_QUICK_JOBS_RATIO = 0.75
DEFAULT_MAX_CANDIDATES = 6
DEFAULT_MAX_FULL_EVAL_CANDIDATES = 2
DEFAULT_MECHANISM_MIN_SHARE = 0.80
DEFAULT_MECHANISM_PRIORITY_STREAK = 2
DEFAULT_MECHANISM_ONLY_STREAK = 10
DEFAULT_FORCE_FULL_PROBE_STREAK = 4
DEFAULT_FORCE_FULL_PROBE_DEADLOCK = 2
DEFAULT_FORCE_FULL_PROBE_RAW_MARGIN = 0.60
DEFAULT_LLM_REVIEW_FULL_GATE_FAIL_STREAK = 2
DEFAULT_LLM_REVIEW_MIN_NO_IMPROVE_STREAK = 2
DEFAULT_LLM_REVIEW_FAIL_OPEN = True
DEFAULT_LOOP_SPOT_POLICY_REF = "path:specs/spot_policies/facing_y_turnriver_high_price_v1.json"
SPOT_GATE_SUPPORT_HANDS_MIN = 4
DEFAULT_RELATIVE_PROMOTION_STRENGTH_MARGIN = 1.50
DEFAULT_RELATIVE_PROMOTION_STABILITY_MARGIN = 0.25
DEFAULT_RELATIVE_PROMOTION_SCORE_MARGIN = 2.00
DEFAULT_RELATIVE_PROMOTION_STABILITY_WEIGHT = 1.50
DEFAULT_CYCLE_LOCK_RETRIES = 60
DEFAULT_RECENT_OPTION_HASH_WINDOW = 256
LOCK_HELD_EXIT_CODE = 75
QUICK_EVAL_CACHE_DIR = ROOT / "tmp" / "ralph_cache_v2" / "quick_eval"
QUICK_EVAL_CACHE_SCHEMA = "quick_eval_v2"
EVENT_TRACE_LOG = ROOT / "tmp" / "ralph_loop_events.ndjson"
RUNTIME_BASELINE_SCHEMA = "single_runtime_baseline_v2"
RUNTIME_BASELINE_BINDING_SCHEMA = "runtime_baseline_binding_v1"
GATE_SCORE_MEAN_WEIGHT = 0.20
CORE_PATCH_FILES = {
    "tools/ralph_wiggum_loop.py",
    "poker2/runtime/system_policy.py",
    "poker2/cli/scrimmage.py",
    "poker2/cli/scrimmage_batch.py",
}
SHARED_RUNTIME_PATCH_FILES = set(CORE_PATCH_FILES)
CORE_STRATEGY_PATCH_FILES = {
    "poker2/runtime/system_policy.py",
}
DEFAULT_ALLOW_SHARED_RUNTIME_PATCH_TICKETS = False
DEFAULT_STAGNATION_MECHANISM_LANES: tuple[str, ...] = (
    "high_price_turn_river_hardening",
    "oop_mw_defense_clamp",
    "river_threshold_recenter",
)
SPOT_POLICY_ADJUSTMENT_BOUNDS: dict[str, tuple[int, int]] = {
    "defend_target_scale_bp": (0, 20000),
    "defend_target_floor_bp": (0, 10000),
    "defend_target_max_bp": (0, 10000),
    "call_pref_floor_bp": (0, 10000),
    "raise_cap_max_bp": (0, 10000),
}
SPOT_POLICY_MECHANISM_LIBRARY: dict[str, tuple[tuple[str, int], ...]] = {
    "high_price_turn_river_hardening": (
        ("defend_target_scale_bp", -650),
        ("defend_target_max_bp", -300),
        ("call_pref_floor_bp", +250),
        ("raise_cap_max_bp", -150),
    ),
    "oop_mw_defense_clamp": (
        ("defend_target_scale_bp", -450),
        ("defend_target_max_bp", -250),
        ("call_pref_floor_bp", +200),
        ("raise_cap_max_bp", -200),
    ),
    "river_threshold_recenter": (
        ("defend_target_scale_bp", -300),
        ("defend_target_floor_bp", +150),
        ("defend_target_max_bp", -150),
        ("call_pref_floor_bp", +120),
    ),
    "low_spr_wet_firewall": (
        ("defend_target_scale_bp", -550),
        ("defend_target_max_bp", -275),
        ("call_pref_floor_bp", +325),
        ("raise_cap_max_bp", -180),
    ),
    "balanced_pressure_mix": (
        ("defend_target_scale_bp", -250),
        ("defend_target_max_bp", -100),
        ("call_pref_floor_bp", +80),
        ("raise_cap_max_bp", -100),
    ),
    "counter_aggression_stability": (
        ("defend_target_scale_bp", -150),
        ("defend_target_max_bp", -75),
        ("call_pref_floor_bp", +50),
        ("raise_cap_max_bp", -50),
    ),
}
RELATIVE_PROMOTION_STRENGTH_COMPONENTS: tuple[tuple[str, float], ...] = (
    ("coinpoker.tierA_mean", 1.00),
    ("coinpoker.tierP_mean", 1.10),
    ("coinpoker.pool_weighted_mean", 1.30),
    ("coinpoker.br_worst_mean", 1.40),
    ("gg.tierA_mean", 0.70),
    ("gg.tierP_mean", 1.00),
)
RELATIVE_PROMOTION_STABILITY_COMPONENTS: tuple[tuple[str, float, float, float], ...] = (
    ("coinpoker.tierA_seed_min", 0.08, -25.0, 30.0),
    ("coinpoker.tierP_seed_min", 0.10, -25.0, 30.0),
    ("gg.tierA_seed_min", 0.06, -25.0, 30.0),
    ("gg.tierP_seed_min", 0.08, -25.0, 30.0),
    ("coinpoker.tierA_std", -0.04, 0.0, 40.0),
    ("coinpoker.tierP_std", -0.05, 0.0, 35.0),
    ("gg.tierA_std", -0.03, 0.0, 35.0),
    ("gg.tierP_std", -0.04, 0.0, 35.0),
    ("coinpoker.tierP_facingY_turnriver_worst_bb100", 0.01, -600.0, 0.0),
)
RELATIVE_PROMOTION_HOLDOUT_COMPONENT = ("holdout_phase1_mean", 0.04, -120.0, 40.0)

TARGET_GATE_TO_METRIC_PATH: tuple[tuple[str, str], ...] = (
    ("coinpoker_tierA_min_bb100", "coinpoker.tierA_mean"),
    ("coinpoker_tierP_min_bb100", "coinpoker.tierP_mean"),
    ("coinpoker_pool_weighted_min_bb100", "coinpoker.pool_weighted_mean"),
    ("coinpoker_br_worst_min_bb100", "coinpoker.br_worst_mean"),
    ("gg_tierA_min_bb100", "gg.tierA_mean"),
    ("gg_tierP_min_bb100", "gg.tierP_mean"),
)
ALLOWED_GATE_OPS = {"gte", "lte"}

KNOB_SPECS: tuple[tuple[str, int, int, int], ...] = (
    ("retaliation_weight_bp", -60, 120, 800),
    ("facing_high_price_defend_gap2_bp", +120, 100, 1500),
    ("facing_high_price_defend_gap_spr_high_penalty_bp", +100, 50, 1200),
    ("facing_high_price_threshold2_bp", -150, 2200, 4500),
    ("facing_high_price_defend_gap_wet_penalty_bp", +80, 20, 600),
    ("facing_high_price_defend_gap_turn_penalty_bp", +60, 20, 500),
    ("facing_high_price_defend_gap_oop_penalty_bp", +45, 20, 600),
    ("facing_high_price_defend_gap_mw_penalty_bp", +45, 20, 600),
    ("facing_high_price_defend_gap_spr_low_penalty_bp", +90, 20, 1200),
    ("facing_high_price_defend_gap_spr_mid_penalty_bp", +80, 20, 1000),
    ("facing_high_price_defend_gap2_turn_wet_bp", +160, 120, 2500),
    ("facing_high_price_defend_gap2_river_wet_bp", +180, 120, 2500),
    ("facing_high_price_threshold2_spr_low_bp", -180, 2000, 4200),
    ("facing_high_price_threshold2_turn_wet_bp", -150, 2200, 4500),
    ("facing_high_price_threshold2_river_wet_bp", -170, 2200, 4500),
)

FOCUS_METRIC_TO_KNOBS: dict[str, tuple[tuple[str, int], ...]] = {
    "coinpoker.br_worst_mean": (
        ("facing_high_price_defend_gap2_bp", +160),
        ("facing_high_price_defend_gap_spr_high_penalty_bp", +100),
        ("retaliation_weight_bp", -80),
    ),
    "coinpoker.tierP_mean": (
        ("facing_high_price_defend_gap2_bp", +140),
        ("facing_high_price_defend_gap_turn_penalty_bp", +60),
        ("facing_high_price_threshold2_bp", -180),
    ),
    "coinpoker.pool_weighted_mean": (
        ("retaliation_weight_bp", -70),
        ("facing_high_price_defend_gap_wet_penalty_bp", +70),
        ("facing_high_price_threshold2_bp", -120),
    ),
    "gg.tierP_mean": (
        ("facing_high_price_defend_gap2_bp", +130),
        ("facing_high_price_defend_gap_turn_penalty_bp", +70),
        ("retaliation_weight_bp", -60),
    ),
    "coinpoker.tierP_seed_min": (
        ("facing_high_price_defend_gap2_bp", +180),
        ("facing_high_price_defend_gap_turn_penalty_bp", +100),
        ("retaliation_weight_bp", -80),
    ),
    "coinpoker.tierP_facingY_turnriver_worst_bb100": (
        ("facing_high_price_defend_gap2_bp", +220),
        ("facing_high_price_defend_gap_turn_penalty_bp", +120),
        ("facing_high_price_defend_gap_wet_penalty_bp", +100),
        ("facing_high_price_defend_gap_spr_low_penalty_bp", +140),
        ("facing_high_price_defend_gap2_turn_wet_bp", +180),
        ("facing_high_price_defend_gap2_river_wet_bp", +220),
        ("facing_high_price_threshold2_spr_low_bp", -160),
        ("facing_high_price_threshold2_turn_wet_bp", -140),
        ("facing_high_price_threshold2_river_wet_bp", -180),
    ),
    "gg.tierP_seed_min": (
        ("facing_high_price_defend_gap2_bp", +160),
        ("facing_high_price_defend_gap_turn_penalty_bp", +100),
        ("retaliation_weight_bp", -70),
    ),
}

MECHANISM_LIBRARY: dict[str, tuple[tuple[str, int], ...]] = {
    "high_price_turn_river_hardening": (
        ("facing_high_price_defend_gap2_bp", +260),
        ("facing_high_price_defend_gap_turn_penalty_bp", +140),
        ("facing_high_price_defend_gap_wet_penalty_bp", +120),
        ("retaliation_weight_bp", -90),
    ),
    "river_threshold_recenter": (
        ("facing_high_price_threshold2_bp", -260),
        ("facing_high_price_defend_gap2_bp", +150),
        ("facing_high_price_defend_gap_spr_high_penalty_bp", +120),
    ),
    "counter_aggression_stability": (
        ("retaliation_weight_bp", -120),
        ("facing_high_price_threshold2_bp", -120),
        ("facing_high_price_defend_gap_turn_penalty_bp", +80),
    ),
    "balanced_pressure_mix": (
        ("facing_high_price_defend_gap2_bp", +180),
        ("facing_high_price_defend_gap_turn_penalty_bp", +90),
        ("facing_high_price_defend_gap_wet_penalty_bp", +70),
        ("facing_high_price_threshold2_bp", -140),
    ),
    "low_spr_wet_firewall": (
        ("facing_high_price_defend_gap2_bp", +220),
        ("facing_high_price_defend_gap_spr_low_penalty_bp", +180),
        ("facing_high_price_defend_gap2_turn_wet_bp", +220),
        ("facing_high_price_defend_gap2_river_wet_bp", +260),
        ("facing_high_price_threshold2_spr_low_bp", -220),
        ("facing_high_price_threshold2_turn_wet_bp", -180),
        ("facing_high_price_threshold2_river_wet_bp", -220),
    ),
    "oop_mw_defense_clamp": (
        ("facing_high_price_defend_gap_oop_penalty_bp", +80),
        ("facing_high_price_defend_gap_mw_penalty_bp", +80),
        ("facing_high_price_defend_gap_spr_mid_penalty_bp", +120),
        ("facing_high_price_defend_gap_spr_high_penalty_bp", +120),
        ("retaliation_weight_bp", -80),
    ),
}

FOCUS_METRIC_TO_MECHANISMS: dict[str, tuple[str, ...]] = {
    "coinpoker.tierP_facingY_turnriver_worst_bb100": (
        "low_spr_wet_firewall",
        "oop_mw_defense_clamp",
        "high_price_turn_river_hardening",
        "river_threshold_recenter",
        "balanced_pressure_mix",
    ),
    "coinpoker.br_worst_mean": (
        "high_price_turn_river_hardening",
        "counter_aggression_stability",
    ),
    "coinpoker.tierP_seed_min": (
        "high_price_turn_river_hardening",
        "river_threshold_recenter",
    ),
    "coinpoker.tierP_mean": (
        "balanced_pressure_mix",
        "counter_aggression_stability",
    ),
    "coinpoker.pool_weighted_mean": (
        "counter_aggression_stability",
        "balanced_pressure_mix",
    ),
    "gg.tierP_mean": (
        "balanced_pressure_mix",
        "high_price_turn_river_hardening",
    ),
}


def _now_ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def _pid_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # In restricted runtimes kill(0) may be denied for live processes.
        return True
    except OSError:
        return False


def _acquire_file_lock(lock_path: Path, *, stale_sec: int) -> tuple[bool, dict[str, Any] | None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    owner: dict[str, Any] | None = None

    for _ in range(2):
        payload = {"pid": int(os.getpid()), "acquired_at_epoch": now, "acquired_at_ts": _now_ts()}
        # Recover quickly from dead owners to avoid supervisor restart churn.
        dead_grace_sec = min(8, max(3, int(stale_sec) // 7200 if int(stale_sec) > 0 else 3))
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                owner = _json_load(lock_path)
            except Exception:
                owner = None
            if not isinstance(owner, dict):
                age_sec = None
                try:
                    age_sec = max(0, now - int(lock_path.stat().st_mtime))
                except Exception:
                    age_sec = None
                if age_sec is None or age_sec >= dead_grace_sec:
                    try:
                        lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                owner = {"pid": None, "lock_age_sec": age_sec, "owner_alive": False, "raw": "invalid_lock_payload"}
                return False, owner
            owner_pid = owner.get("pid")
            owner_epoch = owner.get("acquired_at_epoch")
            age_sec = None
            if isinstance(owner_epoch, int):
                age_sec = max(0, now - owner_epoch)
            owner_alive = _pid_alive(owner_pid if isinstance(owner_pid, int) else None)
            stale = False
            if not owner_alive:
                if isinstance(age_sec, int) and age_sec >= dead_grace_sec:
                    stale = True
                elif not isinstance(owner_pid, int) and isinstance(age_sec, int) and age_sec >= dead_grace_sec:
                    stale = True
                elif not isinstance(age_sec, int):
                    try:
                        mtime_age = max(0, now - int(lock_path.stat().st_mtime))
                    except Exception:
                        mtime_age = None
                    if isinstance(mtime_age, int) and mtime_age >= dead_grace_sec:
                        stale = True
            if stale:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            owner = {"pid": owner_pid, "lock_age_sec": age_sec, "owner_alive": owner_alive}
            return False, owner
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=True, separators=(",", ":"))
                f.write("\n")
            return True, None
    return False, owner


def _release_file_lock(lock_path: Path) -> None:
    if not lock_path.exists():
        return
    try:
        owner = _json_load(lock_path)
    except Exception:
        owner = None
    if isinstance(owner, dict):
        pid = owner.get("pid")
        if isinstance(pid, int) and pid != int(os.getpid()):
            return
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return


def _json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_trace_event(
    *,
    status: str,
    reason: str,
    cycle: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    row: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "status": status,
        "reason": reason,
        "cycle": int(cycle) if isinstance(cycle, int) else None,
    }
    if isinstance(payload, dict):
        for key, val in payload.items():
            if key in row:
                continue
            row[key] = val
    EVENT_TRACE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EVENT_TRACE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")


def _canonical_digest_obj(obj: Any) -> dict[str, str]:
    dig = sha256_hex(canonicalize_json_bytes(obj, strict_mode=True))
    return {"alg": "sha256", "hex": dig}


def _find_policy_spec_path(policy_label: str) -> Path:
    direct = POLICIES_DIR / f"{policy_label}.json"
    if direct.exists():
        return direct
    for path in sorted(POLICIES_DIR.glob("*.json")):
        try:
            obj = _json_load(path)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("policy_label") == policy_label:
            return path
    raise FileNotFoundError(f"policy_label not found: {policy_label}")


def _find_json_by_digest_hex(target_hex: str) -> tuple[Path, dict[str, Any]]:
    for path in sorted(POLICY_PARAMS_DIR.glob("*.json")):
        try:
            obj = _json_load(path)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        dig = _canonical_digest_obj(obj).get("hex")
        if dig == target_hex:
            return path, obj
    raise FileNotFoundError(f"digest not found under specs/policy_params: {target_hex}")


def _resolve_path_artifact_ref(artifact_ref: str) -> Path | None:
    if not isinstance(artifact_ref, str) or not artifact_ref.startswith("path:"):
        return None
    candidate = (ROOT / artifact_ref.removeprefix("path:")).resolve()
    if candidate.exists():
        return candidate
    return None


def _build_loop_system_params(system_params: dict[str, Any]) -> dict[str, Any]:
    sys_obj = copy.deepcopy(system_params)
    sys_obj["params_schema_id"] = LOOP_SYSTEM_PARAMS_SCHEMA_ID
    return sys_obj


def _load_loop_spot_policy_template(
    system_params: dict[str, Any],
    *,
    focus_metric: str | None,
) -> dict[str, Any] | None:
    artifact_ref = system_params.get("spot_policy_ref")
    if not isinstance(artifact_ref, str) or not artifact_ref:
        if focus_metric != FOCUS_SUPPORT_FOCUS_METRIC:
            return None
        artifact_ref = DEFAULT_LOOP_SPOT_POLICY_REF
    path = _resolve_path_artifact_ref(artifact_ref)
    if path is None:
        return None
    try:
        spec = load_spot_policy(path, strict_mode=True)
    except Exception:
        return None
    return {
        "artifact_ref": artifact_ref,
        "path": path,
        "spec": spec,
        "digest": spot_policy_digest(spec, strict_mode=True),
    }


def _scaled_delta(step: int, scale: float) -> int:
    scaled = int(round(float(step) * float(scale)))
    if step > 0 and scaled <= 0:
        return 1
    if step < 0 and scaled >= 0:
        return -1
    return scaled


def _mutate_spot_policy(
    base_spec: dict[str, Any],
    *,
    mechanism_name: str,
    delta_map: dict[str, int],
    scale: float,
) -> tuple[dict[str, Any], list[str]] | tuple[None, list[str]]:
    if not isinstance(base_spec, dict):
        return None, []
    spec = copy.deepcopy(base_spec)
    spots = spec.get("spots")
    if not isinstance(spots, list):
        return None, []
    changed_keys: list[str] = []
    for spot in spots:
        if not isinstance(spot, dict) or not bool(spot.get("enabled")):
            continue
        adjustments = spot.get("adjustments")
        if not isinstance(adjustments, dict):
            continue
        local_changed = False
        for key, raw_delta in delta_map.items():
            bounds = SPOT_POLICY_ADJUSTMENT_BOUNDS.get(key)
            if bounds is None:
                continue
            delta = _scaled_delta(int(raw_delta), scale)
            if delta == 0:
                continue
            low, high = bounds
            current = adjustments.get(key)
            current_int = int(current) if isinstance(current, int) else int(low)
            updated = max(int(low), min(int(high), int(current_int) + int(delta)))
            if current == updated:
                continue
            adjustments[key] = int(updated)
            local_changed = True
            if key not in changed_keys:
                changed_keys.append(key)
        floor_bp = adjustments.get("defend_target_floor_bp")
        max_bp = adjustments.get("defend_target_max_bp")
        if isinstance(floor_bp, int) and isinstance(max_bp, int) and floor_bp > max_bp:
            adjustments["defend_target_max_bp"] = int(floor_bp)
            if "defend_target_max_bp" not in changed_keys:
                changed_keys.append("defend_target_max_bp")
            local_changed = True
        if local_changed:
            trace_tag = adjustments.get("trace_tag")
            base_tag = trace_tag if isinstance(trace_tag, str) and trace_tag else "loop_spot"
            adjustments["trace_tag"] = f"{base_tag}__{mechanism_name}"
    if not changed_keys:
        return None, []
    validate_spot_policy(spec, strict_mode=True)
    return spec, changed_keys


def _generated_spot_policy_ref_from_digest(digest_hex: str) -> str:
    safe = str(digest_hex).lower()[:24]
    return f"path:specs/spot_policies/generated/loop_spot_{safe}.json"


def _candidate_system_params(
    system_params: dict[str, Any],
    *,
    spot_policy: dict[str, Any] | None = None,
    spot_policy_ref: str | None = None,
) -> tuple[dict[str, Any], str | None, dict[str, str] | None]:
    sys_obj = _build_loop_system_params(system_params)
    ref_out = spot_policy_ref if isinstance(spot_policy_ref, str) and spot_policy_ref else None
    digest_out = sys_obj.get("spot_policy_digest") if isinstance(sys_obj.get("spot_policy_digest"), dict) else None
    if isinstance(spot_policy, dict):
        digest_out = spot_policy_digest(spot_policy, strict_mode=True)
        if not isinstance(ref_out, str) or not ref_out:
            ref_out = _generated_spot_policy_ref_from_digest(str(digest_out.get("hex")))
        sys_obj["spot_policy_ref"] = ref_out
        sys_obj["spot_policy_digest"] = digest_out
    return sys_obj, ref_out, digest_out if isinstance(digest_out, dict) else None


def _write_spot_policy_artifact(
    *,
    system_params: dict[str, Any],
    spot_policy: dict[str, Any] | None,
) -> None:
    if not isinstance(spot_policy, dict):
        return
    artifact_ref = system_params.get("spot_policy_ref")
    path = _resolve_path_artifact_ref(artifact_ref) if isinstance(artifact_ref, str) else None
    if path is None and isinstance(artifact_ref, str) and artifact_ref.startswith("path:"):
        path = (ROOT / artifact_ref.removeprefix("path:")).resolve()
    if path is None:
        raise ValueError("spot_policy_ref missing for spot policy materialization")
    validate_spot_policy(spot_policy, strict_mode=True)
    GENERATED_SPOT_POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    _json_dump(path, spot_policy)


def _resolve_policy_bundle(policy_label: str) -> dict[str, Any]:
    spec_path = _find_policy_spec_path(policy_label)
    spec = _json_load(spec_path)
    if not isinstance(spec, dict):
        raise ValueError(f"invalid policy spec at {spec_path}")

    params_digest = (((spec.get("policy_params_digest") or {}).get("hex")) if isinstance(spec.get("policy_params_digest"), dict) else None)
    if not isinstance(params_digest, str) or len(params_digest) != 64:
        raise ValueError(f"policy_params_digest missing/invalid in {spec_path}")
    policy_params_path, policy_params_obj = _find_json_by_digest_hex(params_digest)

    sys_digest = (((policy_params_obj.get("system_bot_params_digest") or {}).get("hex")) if isinstance(policy_params_obj.get("system_bot_params_digest"), dict) else None)
    if not isinstance(sys_digest, str) or len(sys_digest) != 64:
        raise ValueError(f"system_bot_params_digest missing/invalid in {policy_params_path}")
    system_params_path, system_params_obj = _find_json_by_digest_hex(sys_digest)

    if not isinstance(system_params_obj, dict):
        raise ValueError(f"system params must be dict: {system_params_path}")

    return {
        "policy_spec_path": spec_path,
        "policy_spec": spec,
        "policy_params_path": policy_params_path,
        "policy_params": policy_params_obj,
        "system_params_path": system_params_path,
        "system_params": system_params_obj,
    }


def _materialize_policy(
    *,
    policy_label: str,
    template_policy_spec: dict[str, Any],
    template_policy_params: dict[str, Any],
    system_params: dict[str, Any],
    note_tag: str,
    spot_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe = policy_label.replace("-", "_")
    system_path = POLICY_PARAMS_DIR / f"system_bot_params_v3_{safe}.json"
    policy_params_path = POLICY_PARAMS_DIR / f"{safe}.params.json"
    policy_spec_path = POLICIES_DIR / f"{policy_label}.json"

    sys_obj, _, _ = _candidate_system_params(
        system_params,
        spot_policy=spot_policy if isinstance(spot_policy, dict) else None,
    )
    _write_spot_policy_artifact(system_params=sys_obj, spot_policy=spot_policy)
    _json_dump(system_path, sys_obj)
    sys_digest = _canonical_digest_obj(sys_obj)

    pp_obj = copy.deepcopy(template_policy_params)
    pp_obj["system_bot_params_digest"] = sys_digest
    pp_obj["notes"] = note_tag
    _json_dump(policy_params_path, pp_obj)
    pp_digest = _canonical_digest_obj(pp_obj)

    spec_obj = {
        "policy_kind": template_policy_spec.get("policy_kind"),
        "policy_deps": template_policy_spec.get("policy_deps"),
        "policy_params_digest": pp_digest,
        "stochastic": bool(template_policy_spec.get("stochastic", False)),
        "policy_label": policy_label,
    }
    pid = policy_id(spec_obj, strict_mode=True)
    spec_obj["policy_id"] = pid
    _json_dump(policy_spec_path, spec_obj)

    return {
        "policy_label": policy_label,
        "policy_id": pid,
        "policy_spec_path": str(policy_spec_path),
        "policy_params_path": str(policy_params_path),
        "system_params_path": str(system_path),
        "policy_params_digest": pp_digest,
        "system_params_digest": sys_digest,
    }


def _run_cmd(cmd: list[str], *, log_path: Path, timeout_sec: float | None = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        f.write("CMD: " + " ".join(cmd) + "\n")
        f.flush()
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        try:
            if isinstance(timeout_sec, (int, float)) and float(timeout_sec) > 0:
                deadline = time.monotonic() + max(1.0, float(timeout_sec))
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        f.write(
                            f"[ralph_wiggum_loop] command_timeout timeout_sec={float(timeout_sec):.1f}\n"
                        )
                        f.flush()
                        proc.terminate()
                        try:
                            proc.wait(timeout=10.0)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        return 124
                    try:
                        return int(proc.wait(timeout=min(5.0, max(0.1, remaining))))
                    except subprocess.TimeoutExpired:
                        f.flush()
                        continue
            return int(proc.wait())
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def _extract_reason_from_log(log_path: Path) -> str | None:
    if not log_path.exists():
        return None
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None
    for raw in reversed(lines[-80:]):
        s = raw.strip()
        if not s.startswith("{") or not s.endswith("}"):
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        reason = obj.get("reason")
        if isinstance(reason, str) and reason:
            return reason
    return None


def _next_action_file_signature(action_path: Path) -> tuple[int, int] | None:
    try:
        st = action_path.stat()
    except OSError:
        return None
    return int(st.st_mtime_ns), int(st.st_size)


def _wait_for_valid_action_ticket(
    *,
    action_path: Path,
    cycle: int,
    timeout_sec: float,
    poll_sec: float = 2.0,
    baseline_signature: tuple[int, int] | None = None,
) -> dict[str, Any]:
    deadline = time.time() + max(1.0, float(timeout_sec))
    checks = 0
    last_status = "absent"
    last_ticket: dict[str, Any] = {"pass": False, "reason": "missing_action"}
    while True:
        checks += 1
        action_obj, status = _load_next_action(action_path, cycle=cycle)
        ticket = _validate_action_ticket(action_obj if isinstance(action_obj, dict) else None, cycle=cycle)
        last_status = status
        last_ticket = ticket
        sig = _next_action_file_signature(action_path)
        if bool(ticket.get("pass")):
            return {
                "ready": True,
                "checks": int(checks),
                "status": status,
                "ticket_reason": ticket.get("reason"),
                "signature_changed": bool(baseline_signature is None or sig != baseline_signature),
            }
        now = time.time()
        if now >= deadline:
            return {
                "ready": False,
                "checks": int(checks),
                "status": last_status,
                "ticket_reason": last_ticket.get("reason"),
                "signature_changed": bool(baseline_signature is None or sig != baseline_signature),
            }
        remaining = max(0.0, deadline - now)
        sleep_sec = max(0.2, min(float(poll_sec), remaining))
        time.sleep(sleep_sec)


def _as_float(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _scale_factor(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        return max(0.25, min(4.0, float(v)))
    if isinstance(v, str):
        s = v.strip().lower()
        if not s:
            return None
        named = {
            "tiny": 0.50,
            "small": 0.75,
            "medium": 1.00,
            "large": 1.35,
            "xlarge": 1.80,
        }.get(s)
        if isinstance(named, float):
            return named
        try:
            num = float(s)
        except ValueError:
            return None
        return max(0.25, min(4.0, num))
    return None


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float) and float(v).is_integer():
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("-") and s[1:].isdigit():
            return int(s)
        if s.isdigit():
            return int(s)
    return None


def _normalize_hash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    if len(s) != 64:
        return None
    if any(ch not in "0123456789abcdef" for ch in s):
        return None
    return s


def _recent_option_hashes_from_state(state: dict[str, Any], *, limit: int) -> list[str]:
    rows = state.get("recent_option_hashes")
    if not isinstance(rows, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for row in rows:
        h = _normalize_hash(row)
        if not isinstance(h, str) or h in seen:
            continue
        seen.add(h)
        normalized.append(h)
    if limit > 0 and len(normalized) > limit:
        normalized = normalized[-limit:]
    return normalized


def _append_recent_option_hashes(
    state: dict[str, Any],
    hashes: list[str],
    *,
    window: int,
) -> list[str]:
    existing = _recent_option_hashes_from_state(state, limit=max(1, int(window)))
    merged = list(existing)
    seen = set(existing)
    for row in hashes:
        h = _normalize_hash(row)
        if not isinstance(h, str) or h in seen:
            continue
        merged.append(h)
        seen.add(h)
    if len(merged) > int(window):
        merged = merged[-int(window):]
    state["recent_option_hashes"] = merged
    return merged


def _candidate_origin_priority(origin: Any) -> int:
    if not isinstance(origin, str):
        return 9
    order = {
        "action_plan": 0,
        "adaptive_focus": 1,
        "focus_metric": 2,
        "global": 3,
        "lane_explore": 4,
        "mix": 5,
        "explore": 6,
    }
    return int(order.get(origin, 9))


def _candidate_priority_key(row: dict[str, Any]) -> tuple[int, int, int, int, str]:
    kind = row.get("kind")
    mechanism = row.get("mechanism")
    spot_rank = 0 if bool(row.get("spot_policy_variant")) else 1
    kind_rank = 0 if kind == "mechanism" else 1
    mechanism_rank = 0 if isinstance(mechanism, str) and mechanism != "explore_mix" else 1
    return (
        _candidate_origin_priority(row.get("origin")),
        spot_rank,
        kind_rank,
        mechanism_rank,
        str(row.get("name")),
    )


def _metric_get(metrics: dict[str, Any], path: str) -> float | None:
    cur: Any = metrics
    for token in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(token)
    return _as_float(cur)


def _focus_metric_rotation(
    base_focus_metric: str | None,
    next_hypothesis: dict[str, Any] | None,
) -> list[str]:
    rotation: list[str] = []
    if isinstance(base_focus_metric, str) and base_focus_metric:
        rotation.append(base_focus_metric)
    alternates = next_hypothesis.get("alternate_focus_metrics") if isinstance(next_hypothesis, dict) else None
    if isinstance(alternates, list):
        for row in alternates:
            if isinstance(row, str) and row and row not in rotation:
                rotation.append(row)
    return rotation


def _resolve_focus_control(
    *,
    state: dict[str, Any],
    cycle: int,
    base_focus_metric: str | None,
    next_hypothesis: dict[str, Any] | None,
    action_overrides_focus: bool,
) -> tuple[str | None, dict[str, Any] | None, bool, dict[str, Any] | None]:
    if action_overrides_focus or not isinstance(base_focus_metric, str) or not base_focus_metric:
        return base_focus_metric, None, False, None

    rotation = _focus_metric_rotation(base_focus_metric, next_hypothesis)
    if not rotation:
        return base_focus_metric, None, False, None

    raw_control = state.get("focus_control")
    focus_control = copy.deepcopy(raw_control) if isinstance(raw_control, dict) else {}
    active_metric = focus_control.get("active_metric")
    if not isinstance(active_metric, str) or active_metric not in rotation:
        active_metric = base_focus_metric

    base_changed = focus_control.get("base_metric") != base_focus_metric
    if base_changed:
        active_metric = base_focus_metric
        focus_control["switch_count"] = 0
        focus_control["starvation_streak"] = 0

    starvation_streak = max(0, _as_int(focus_control.get("starvation_streak")) or 0)
    switch_count = max(0, _as_int(focus_control.get("switch_count")) or 0)
    switched = False
    stop_payload: dict[str, Any] | None = None

    if starvation_streak >= DEFAULT_FOCUS_STARVATION_SWITCH_STREAK:
        next_metric: str | None = None
        if active_metric in rotation:
            active_idx = rotation.index(active_metric)
            for offset in range(1, len(rotation)):
                candidate = rotation[(active_idx + offset) % len(rotation)]
                if candidate != active_metric:
                    next_metric = candidate
                    break
        if switch_count < DEFAULT_FOCUS_STARVATION_MAX_SWITCHES and isinstance(next_metric, str):
            focus_control["last_switch_from"] = active_metric
            focus_control["last_switch_to"] = next_metric
            focus_control["switched_at_cycle"] = int(cycle)
            focus_control["switch_count"] = int(switch_count + 1)
            focus_control["starvation_streak"] = 0
            active_metric = next_metric
            switched = True
        else:
            stop_payload = {
                "reason": "focus_support_starvation_requires_manual_hypothesis",
                "base_focus_metric": base_focus_metric,
                "active_focus_metric": active_metric,
                "rotation": rotation,
                "switch_count": int(switch_count),
                "starvation_streak": int(starvation_streak),
                "cycle": int(cycle),
            }
            focus_control["stop_requested"] = True
            focus_control["stop_reason"] = str(stop_payload["reason"])

    focus_control["base_metric"] = base_focus_metric
    focus_control["active_metric"] = active_metric
    focus_control["rotation"] = rotation
    focus_control["switch_count"] = int(_as_int(focus_control.get("switch_count")) or 0)
    focus_control["starvation_streak"] = int(_as_int(focus_control.get("starvation_streak")) or 0)
    if stop_payload is None:
        focus_control["stop_requested"] = False
        focus_control["stop_reason"] = None
    return active_metric, focus_control, switched, stop_payload


def _update_focus_control_after_cycle(
    *,
    state: dict[str, Any],
    base_focus_metric: str | None,
    active_focus_metric: str | None,
    quick_gate_reason: str | None,
    quick_gate: dict[str, Any] | None,
    decision: str | None,
) -> dict[str, Any] | None:
    if not isinstance(active_focus_metric, str) or not active_focus_metric:
        return None

    raw_control = state.get("focus_control")
    focus_control = copy.deepcopy(raw_control) if isinstance(raw_control, dict) else {}
    focus_control["base_metric"] = (
        base_focus_metric if isinstance(base_focus_metric, str) and base_focus_metric else active_focus_metric
    )
    focus_control["active_metric"] = active_focus_metric
    focus_control["last_cycle_reason"] = quick_gate_reason if isinstance(quick_gate_reason, str) else None
    focus_control["last_cycle_decision"] = decision if isinstance(decision, str) else None

    support_pass_count = _as_int((quick_gate or {}).get("support_pass_count")) or 0
    support_hits_delta_total = _as_int((quick_gate or {}).get("targeted_focus_support_hits_delta_total")) or 0
    starved = bool(
        quick_gate_reason in {"quick_gate_low_focus_support", "quick_gate_spot_no_effect"}
        and support_pass_count <= 0
        and support_hits_delta_total <= 0
    )
    if decision == "ADOPT":
        focus_control["switch_count"] = 0
        focus_control["starvation_streak"] = 0
        focus_control["active_metric"] = focus_control.get("base_metric")
    elif starved:
        focus_control["starvation_streak"] = int((_as_int(focus_control.get("starvation_streak")) or 0) + 1)
    else:
        focus_control["starvation_streak"] = 0
        if quick_gate_reason not in {"quick_gate_low_focus_support", "quick_gate_spot_no_effect"}:
            focus_control["switch_count"] = 0
            base_metric = focus_control.get("base_metric")
            if isinstance(base_metric, str) and base_metric:
                focus_control["active_metric"] = base_metric
    focus_control["stop_requested"] = False
    focus_control["stop_reason"] = None
    return focus_control


def _focus_metric_value_from_quick(quick: dict[str, Any], focus_metric: str | None) -> float | None:
    if not isinstance(quick, dict) or not isinstance(focus_metric, str) or not focus_metric:
        return None
    if focus_metric == FOCUS_SUPPORT_FOCUS_METRIC:
        probe = quick.get("focus_probe")
        if isinstance(probe, dict):
            return _as_float(probe.get("tierP_facingY_turnriver_worst_bb100"))
        return None
    direct = _metric_get(quick, focus_metric)
    if isinstance(direct, float):
        return direct
    probe = quick.get("focus_probe")
    if isinstance(probe, dict):
        return _as_float(probe.get(focus_metric.rsplit(".", 1)[-1]))
    return None


def _spot_gate_eval(
    *,
    focus_metric: str | None,
    spot_policy_variant: bool,
    focus_metric_delta: float | None,
    support_hits_delta: int,
    support_hands_delta: int,
) -> dict[str, Any]:
    applicable = bool(spot_policy_variant and focus_metric == FOCUS_SUPPORT_FOCUS_METRIC)
    focus_improved = bool(
        isinstance(focus_metric_delta, float) and math.isfinite(focus_metric_delta) and float(focus_metric_delta) > 0.0
    )
    support_improved = int(support_hits_delta) > 0
    coverage_non_regressing = bool(
        int(support_hands_delta) >= int(SPOT_GATE_SUPPORT_HANDS_MIN)
        and isinstance(focus_metric_delta, float)
        and math.isfinite(focus_metric_delta)
        and float(focus_metric_delta) >= 0.0
    )
    passed = bool((not applicable) or focus_improved or support_improved or coverage_non_regressing)
    if not applicable:
        reason = "not_applicable"
    elif focus_improved:
        reason = "focus_metric_delta"
    elif support_improved:
        reason = "support_hits_delta"
    elif coverage_non_regressing:
        reason = "coverage_non_regressing"
    else:
        reason = "no_spot_effect"
    return {
        "applicable": bool(applicable),
        "pass": bool(passed),
        "reason": reason,
        "focus_improved": bool(focus_improved),
        "support_improved": bool(support_improved),
        "coverage_non_regressing": bool(coverage_non_regressing),
        "support_hands_min": int(SPOT_GATE_SUPPORT_HANDS_MIN),
    }


def _support_delta_from_targeted_focus(targeted_focus: dict[str, Any] | None) -> tuple[int, int]:
    delta = targeted_focus.get("support_delta") if isinstance(targeted_focus, dict) else None
    hits = _as_int((delta or {}).get("hits")) if isinstance(delta, dict) else None
    hands = _as_int((delta or {}).get("hands")) if isinstance(delta, dict) else None
    return int(hits or 0), int(hands or 0)


def _extract_baseline_metrics(full_obj: dict[str, Any] | None) -> dict[str, float | None]:
    if not isinstance(full_obj, dict):
        return {}
    coin = full_obj.get("coinpoker") if isinstance(full_obj.get("coinpoker"), dict) else {}
    gg = full_obj.get("gg") if isinstance(full_obj.get("gg"), dict) else {}
    return {
        "coinpoker.tierA_mean": _as_float(coin.get("tierA_mean")),
        "coinpoker.tierP_mean": _as_float(coin.get("tierP_mean")),
        "coinpoker.pool_weighted_mean": _as_float(coin.get("pool_weighted_mean")),
        "coinpoker.br_worst_mean": _as_float(coin.get("br_worst_mean")),
        "coinpoker.tierP_facingY_turnriver_worst_bb100": _as_float(coin.get("tierP_facingY_turnriver_worst_bb100")),
        "gg.tierA_mean": _as_float(gg.get("tierA_mean")),
        "gg.tierP_mean": _as_float(gg.get("tierP_mean")),
    }


def _bind_full_metrics(
    full_metrics: dict[str, Any] | None,
    *,
    policy_label: str,
    policy_options_hash: str | None,
    eval_context_digest: str | None,
) -> dict[str, Any]:
    if not isinstance(full_metrics, dict):
        return {}
    out = copy.deepcopy(full_metrics)
    out["policy"] = policy_label
    out["policy_options_hash"] = _normalize_hash(policy_options_hash)
    out["eval_context_digest"] = _normalize_hash(eval_context_digest)
    out["baseline_binding_schema"] = RUNTIME_BASELINE_BINDING_SCHEMA
    return out


def _baseline_metric_aligned(lhs: Any, rhs: Any) -> bool:
    lv = _as_float(lhs)
    rv = _as_float(rhs)
    if isinstance(lv, float) and isinstance(rv, float):
        return abs(lv - rv) <= 1e-9
    return lv is None and rv is None


def _runtime_baseline_integrity_report(
    baseline: dict[str, Any] | None,
    *,
    expected_policy_label: str,
    expected_policy_options_hash: str | None,
    expected_eval_context_digest: str | None,
) -> dict[str, Any]:
    expected_hash = _normalize_hash(expected_policy_options_hash)
    expected_context = _normalize_hash(expected_eval_context_digest)
    issues: list[dict[str, Any]] = []
    if not isinstance(baseline, dict):
        return {
            "pass": False,
            "issues": [{"reason": "missing_baseline"}],
            "expected": {
                "policy_label": expected_policy_label,
                "policy_options_hash": expected_hash,
                "eval_context_digest": expected_context,
            },
        }

    schema = baseline.get("schema")
    if schema != RUNTIME_BASELINE_SCHEMA:
        issues.append({"reason": "schema_mismatch", "value": schema, "expected": RUNTIME_BASELINE_SCHEMA})

    baseline_policy = baseline.get("policy_label")
    if baseline_policy != expected_policy_label:
        issues.append(
            {
                "reason": "policy_label_mismatch",
                "value": baseline_policy,
                "expected": expected_policy_label,
            }
        )

    baseline_hash = _normalize_hash(baseline.get("policy_options_hash"))
    baseline_context = _normalize_hash(baseline.get("eval_context_digest"))
    if isinstance(expected_hash, str):
        if not isinstance(baseline_hash, str):
            issues.append({"reason": "missing_policy_options_hash"})
        elif baseline_hash != expected_hash:
            issues.append(
                {
                    "reason": "policy_options_hash_mismatch",
                    "value": baseline_hash,
                    "expected": expected_hash,
                }
            )
    if isinstance(expected_context, str):
        if not isinstance(baseline_context, str):
            issues.append({"reason": "missing_eval_context_digest"})
        elif baseline_context != expected_context:
            issues.append(
                {
                    "reason": "eval_context_digest_mismatch",
                    "value": baseline_context,
                    "expected": expected_context,
                }
            )

    baseline_metrics = baseline.get("metrics")
    full_metrics = baseline.get("full_metrics")
    if not isinstance(baseline_metrics, dict):
        issues.append({"reason": "missing_baseline_metrics"})
        baseline_metrics = {}
    if not isinstance(full_metrics, dict):
        issues.append({"reason": "missing_full_metrics"})
        full_metrics = {}

    full_metrics_extracted = _extract_baseline_metrics(full_metrics)
    metric_mismatches: dict[str, dict[str, Any]] = {}
    for key in full_metrics_extracted.keys():
        left = baseline_metrics.get(key)
        right = full_metrics_extracted.get(key)
        if not _baseline_metric_aligned(left, right):
            metric_mismatches[key] = {"baseline": left, "full_metrics": right}
    if metric_mismatches:
        issues.append({"reason": "baseline_metrics_mismatch", "details": metric_mismatches})

    full_hash = _normalize_hash(full_metrics.get("policy_options_hash")) if isinstance(full_metrics, dict) else None
    full_context = _normalize_hash(full_metrics.get("eval_context_digest")) if isinstance(full_metrics, dict) else None
    if not isinstance(full_hash, str):
        issues.append({"reason": "missing_full_metrics_policy_options_hash"})
    elif isinstance(baseline_hash, str) and full_hash != baseline_hash:
        issues.append(
            {
                "reason": "full_metrics_policy_options_hash_mismatch",
                "value": full_hash,
                "expected": baseline_hash,
            }
        )
    if not isinstance(full_context, str):
        issues.append({"reason": "missing_full_metrics_eval_context_digest"})
    elif isinstance(baseline_context, str) and full_context != baseline_context:
        issues.append(
            {
                "reason": "full_metrics_eval_context_digest_mismatch",
                "value": full_context,
                "expected": baseline_context,
            }
        )
    full_policy = full_metrics.get("policy")
    if isinstance(full_policy, str) and isinstance(baseline_policy, str) and full_policy != baseline_policy:
        issues.append(
            {
                "reason": "full_metrics_policy_label_mismatch",
                "value": full_policy,
                "expected": baseline_policy,
            }
        )

    return {
        "pass": not issues,
        "issues": issues,
        "expected": {
            "policy_label": expected_policy_label,
            "policy_options_hash": expected_hash,
            "eval_context_digest": expected_context,
        },
        "actual": {
            "policy_label": baseline_policy,
            "policy_options_hash": baseline_hash,
            "eval_context_digest": baseline_context,
        },
    }


def _digest_json_file(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return _normalize_hash(sha256_hex(path.read_bytes()))
    except Exception:
        return None


def _safe_resolved_path(path_value: str) -> str:
    try:
        return str(Path(path_value).resolve())
    except Exception:
        return path_value


def _build_eval_context(
    *,
    profile: str,
    coinpoker_scenario: str,
    gg_scenario: str,
    tier_a_opponents: str,
    tier_p_opponents: str,
    pool_path: str,
    full_hands: int,
    full_seeds_json: str,
    confirm_seeds_json: str,
    goal_pack: dict[str, Any],
    pareto_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pool_ref = _safe_resolved_path(pool_path)
    goal_pack_ref = str(goal_pack.get("path")) if isinstance(goal_pack.get("path"), str) else None
    goal_payload = {
        "goal_pack_id": goal_pack.get("goal_pack_id"),
        "target_gates": goal_pack.get("target_gates"),
        "robust_gates": goal_pack.get("robust_gates"),
        "promotion_gates": goal_pack.get("promotion_gates"),
    }
    goal_payload_raw = json.dumps(goal_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return {
        "schema": "ralph_eval_context_v1",
        "profile": profile,
        "coinpoker_scenario": coinpoker_scenario,
        "gg_scenario": gg_scenario,
        "tier_a_opponents": tier_a_opponents,
        "tier_p_opponents": tier_p_opponents,
        "pool_path": pool_ref,
        "pool_digest": _digest_json_file(Path(pool_path)),
        "full_hands": int(max(1, int(full_hands))),
        "full_seeds": _parse_seed_list_or_empty(full_seeds_json),
        "confirm_seeds": _parse_seed_list_or_empty(confirm_seeds_json),
        "goal_pack_id": goal_pack.get("goal_pack_id"),
        "goal_pack_ref": _safe_resolved_path(goal_pack_ref) if isinstance(goal_pack_ref, str) else None,
        "goal_pack_digest": _normalize_hash(sha256_hex(goal_payload_raw.encode("utf-8"))),
        "pareto_contract_ref": (
            _safe_resolved_path(str(pareto_contract.get("path")))
            if isinstance(pareto_contract, dict) and isinstance(pareto_contract.get("path"), str)
            else None
        ),
        "pareto_contract_digest": (
            _normalize_hash(pareto_contract.get("digest"))
            if isinstance(pareto_contract, dict)
            else None
        ),
    }


def _build_holdout_context(
    *,
    eval_context_digest: str | None,
    scenario: str,
    profile: str,
    hands: int,
    seeds_json: str,
    phase1_suite: str | None,
    phase2_suite: str | None,
    phase2_on_promotion: bool,
) -> dict[str, Any]:
    return {
        "schema": "ralph_holdout_context_v1",
        "eval_context_digest": _normalize_hash(eval_context_digest),
        "scenario": scenario,
        "profile": profile,
        "hands": int(max(1, int(hands))),
        "seeds": _parse_seed_list_or_empty(seeds_json),
        "phase1_suite": phase1_suite if isinstance(phase1_suite, str) else None,
        "phase2_suite": phase2_suite if isinstance(phase2_suite, str) else None,
        "phase2_on_promotion": bool(phase2_on_promotion),
    }


def _build_runtime_baseline(
    *,
    policy_label: str,
    policy_options_hash: str | None,
    full_metrics: dict[str, Any],
    source: str,
    adopted_cycle: int | None,
    eval_context_digest: str | None = None,
    eval_context: dict[str, Any] | None = None,
    adopt_mode: str | None = None,
    previous_policy_options_hash: str | None = None,
) -> dict[str, Any]:
    bound_full_metrics = _bind_full_metrics(
        full_metrics,
        policy_label=policy_label,
        policy_options_hash=policy_options_hash,
        eval_context_digest=eval_context_digest,
    )
    return {
        "schema": RUNTIME_BASELINE_SCHEMA,
        "policy_label": policy_label,
        "policy_options_hash": _normalize_hash(policy_options_hash),
        "eval_context_digest": _normalize_hash(eval_context_digest),
        "eval_context": copy.deepcopy(eval_context) if isinstance(eval_context, dict) else None,
        "source": source,
        "adopted_cycle": int(adopted_cycle) if isinstance(adopted_cycle, int) else None,
        "adopt_mode": adopt_mode if isinstance(adopt_mode, str) else None,
        "previous_policy_options_hash": _normalize_hash(previous_policy_options_hash),
        "updated_at": _now_ts(),
        "metrics": _extract_baseline_metrics(bound_full_metrics),
        "full_metrics": bound_full_metrics,
    }


def _runtime_baseline_from_state(
    state: dict[str, Any],
    *,
    active_options_hash: str | None = None,
    expected_eval_context_digest: str | None = None,
) -> dict[str, Any] | None:
    raw = state.get("baseline")
    if not isinstance(raw, dict):
        return None
    full_metrics = raw.get("full_metrics")
    if not isinstance(full_metrics, dict):
        return None
    baseline_hash = _normalize_hash(raw.get("policy_options_hash"))
    active_hash = _normalize_hash(active_options_hash)
    if isinstance(active_hash, str) and isinstance(baseline_hash, str) and baseline_hash != active_hash:
        return None
    baseline_context_hash = _normalize_hash(raw.get("eval_context_digest"))
    expected_context_hash = _normalize_hash(expected_eval_context_digest)
    if isinstance(expected_context_hash, str) and baseline_context_hash != expected_context_hash:
        return None
    out = copy.deepcopy(raw)
    out["schema"] = RUNTIME_BASELINE_SCHEMA
    out["policy_options_hash"] = baseline_hash or active_hash
    out["eval_context_digest"] = baseline_context_hash
    out["eval_context"] = copy.deepcopy(raw.get("eval_context")) if isinstance(raw.get("eval_context"), dict) else None
    out["metrics"] = _extract_baseline_metrics(full_metrics)
    out["full_metrics"] = copy.deepcopy(full_metrics)
    return out


def _set_runtime_baseline(
    state: dict[str, Any],
    *,
    policy_label: str,
    policy_options_hash: str | None,
    full_metrics: dict[str, Any],
    source: str,
    adopted_cycle: int | None,
    eval_context_digest: str | None = None,
    eval_context: dict[str, Any] | None = None,
    adopt_mode: str | None = None,
    previous_policy_options_hash: str | None = None,
) -> dict[str, Any]:
    baseline = _build_runtime_baseline(
        policy_label=policy_label,
        policy_options_hash=policy_options_hash,
        full_metrics=full_metrics,
        source=source,
        adopted_cycle=adopted_cycle,
        eval_context_digest=eval_context_digest,
        eval_context=eval_context,
        adopt_mode=adopt_mode,
        previous_policy_options_hash=previous_policy_options_hash,
    )
    state["baseline"] = baseline
    # Backward compatible readers still consume active_full_metrics.
    state["active_full_metrics"] = copy.deepcopy(baseline.get("full_metrics"))
    state["active_full_eval_context_digest"] = _normalize_hash(eval_context_digest)
    state.pop("active_source_baseline_label", None)
    return baseline


def _runtime_baseline_summary(baseline: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(baseline, dict):
        return {
            "policy_label": None,
            "policy_options_hash": None,
            "eval_context_digest": None,
            "source": None,
            "adopted_cycle": None,
            "updated_at": None,
            "metrics": {},
        }
    metrics = baseline.get("metrics")
    if not isinstance(metrics, dict):
        metrics = _extract_baseline_metrics(baseline.get("full_metrics") if isinstance(baseline.get("full_metrics"), dict) else None)
    return {
        "policy_label": baseline.get("policy_label"),
        "policy_options_hash": _normalize_hash(baseline.get("policy_options_hash")),
        "adopt_mode": baseline.get("adopt_mode"),
        "previous_policy_options_hash": _normalize_hash(baseline.get("previous_policy_options_hash")),
        "eval_context_digest": _normalize_hash(baseline.get("eval_context_digest")),
        "source": baseline.get("source"),
        "adopted_cycle": _as_int(baseline.get("adopted_cycle")),
        "updated_at": baseline.get("updated_at"),
        "metrics": metrics,
    }


def _derive_phase_jobs(total_jobs: int, ratio: float, *, leave_headroom: bool = True) -> int:
    total = max(1, int(total_jobs))
    r = max(0.10, min(1.0, float(ratio)))
    jobs = max(1, int(round(total * r)))
    if leave_headroom and total >= 4:
        jobs = min(jobs, total - 1)
    return max(1, min(total, jobs))


def _distribute_jobs(total_jobs: int, slots: int) -> list[int]:
    total = max(1, int(total_jobs))
    slot_count = max(1, min(total, int(slots)))
    base = total // slot_count
    remainder = total % slot_count
    out = [base for _ in range(slot_count)]
    for idx in range(remainder):
        out[idx] += 1
    return out


def _eval_gate(
    *,
    gate_key: str,
    metric_path: str,
    threshold: float,
    op: str,
    metrics: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    value = _metric_get(metrics, metric_path)
    op_norm = op if op in ALLOWED_GATE_OPS else "gte"
    if not isinstance(value, float):
        passed = False
        gap = None
    else:
        if op_norm == "lte":
            gap = float(threshold) - float(value)
        else:
            gap = float(value) - float(threshold)
        passed = bool(gap >= 0.0)
    return {
        "gate_key": gate_key,
        "metric_path": metric_path,
        "source": source,
        "op": op_norm,
        "value_bb100": value,
        "threshold_bb100": float(threshold),
        "pass": bool(passed),
        "gap_bb100": gap,
    }


def _load_goal_pack(goal_pack_path: str) -> dict[str, Any]:
    path = Path(goal_pack_path)
    obj = _json_load(path)
    if not isinstance(obj, dict):
        raise ValueError(f"goal pack must be object: {path}")

    target = obj.get("target_gates")
    if not isinstance(target, dict):
        raise ValueError(f"target_gates missing/invalid: {path}")
    norm_target: dict[str, float] = {}
    for key, _ in TARGET_GATE_TO_METRIC_PATH:
        v = _as_float(target.get(key))
        if v is None:
            raise ValueError(f"target_gates.{key} missing/invalid: {path}")
        norm_target[key] = float(v)

    promo = obj.get("promotion_gates")
    if promo is None:
        promo = {}
    if not isinstance(promo, dict):
        raise ValueError(f"promotion_gates invalid: {path}")
    quick = _as_float(promo.get("quick_min_delta"))
    full = _as_float(promo.get("full_min_delta"))
    regress = _as_float(promo.get("regress_tolerance"))
    holdout_regress = _as_float(promo.get("holdout_regress_tolerance"))
    holdout_phase1_required_raw = promo.get("holdout_phase1_required")
    holdout_phase2_on_promotion_raw = promo.get("holdout_phase2_on_promotion")
    holdout_phase1_required = (
        bool(holdout_phase1_required_raw) if isinstance(holdout_phase1_required_raw, bool) else True
    )
    holdout_phase2_on_promotion = (
        bool(holdout_phase2_on_promotion_raw) if isinstance(holdout_phase2_on_promotion_raw, bool) else True
    )

    robust_rows_raw = obj.get("robust_gates")
    if robust_rows_raw is None:
        robust_rows_raw = []
    if not isinstance(robust_rows_raw, list):
        raise ValueError(f"robust_gates invalid: {path}")
    robust_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(robust_rows_raw):
        if not isinstance(row, dict):
            raise ValueError(f"robust_gates[{idx}] invalid object: {path}")
        gate_key = row.get("gate_key")
        metric_path = row.get("metric_path")
        threshold = _as_float(row.get("threshold"))
        op = row.get("op")
        if not isinstance(gate_key, str) or not gate_key:
            raise ValueError(f"robust_gates[{idx}].gate_key missing/invalid: {path}")
        if not isinstance(metric_path, str) or not metric_path:
            raise ValueError(f"robust_gates[{idx}].metric_path missing/invalid: {path}")
        if threshold is None:
            raise ValueError(f"robust_gates[{idx}].threshold missing/invalid: {path}")
        op_norm = str(op).lower() if isinstance(op, str) else "gte"
        if op_norm not in ALLOWED_GATE_OPS:
            raise ValueError(f"robust_gates[{idx}].op must be one of {sorted(ALLOWED_GATE_OPS)}: {path}")
        robust_rows.append(
            {
                "gate_key": gate_key,
                "metric_path": metric_path,
                "threshold": float(threshold),
                "op": op_norm,
            }
        )

    return {
        "goal_pack_id": obj.get("goal_pack_id") if isinstance(obj.get("goal_pack_id"), str) else "unknown_goal_pack",
        "path": str(path.resolve()),
        "target_gates": norm_target,
        "robust_gates": robust_rows,
        "promotion_gates": {
            "quick_min_delta": float(quick) if quick is not None else 0.25,
            "full_min_delta": float(full) if full is not None else 0.10,
            "regress_tolerance": float(regress) if regress is not None else 0.15,
            "holdout_regress_tolerance": float(holdout_regress) if holdout_regress is not None else (
                float(regress) if regress is not None else 0.15
            ),
            "holdout_phase1_required": bool(holdout_phase1_required),
            "holdout_phase2_on_promotion": bool(holdout_phase2_on_promotion),
        },
    }


def _load_pareto_contract(pareto_contract_path: str) -> dict[str, Any]:
    path = Path(pareto_contract_path)
    obj = _json_load(path)
    if not isinstance(obj, dict):
        raise ValueError(f"pareto contract must be object: {path}")

    schema_id = obj.get("schema_id")
    if not isinstance(schema_id, str) or not schema_id:
        raise ValueError(f"pareto contract schema_id missing/invalid: {path}")

    raw_objectives = obj.get("objectives")
    if not isinstance(raw_objectives, list) or not raw_objectives:
        raise ValueError(f"pareto contract objectives missing/invalid: {path}")
    objectives: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for idx, row in enumerate(raw_objectives):
        if not isinstance(row, dict):
            raise ValueError(f"pareto contract objectives[{idx}] invalid: {path}")
        key = row.get("key")
        metric_path = row.get("metric_path")
        direction = str(row.get("direction", "max")).lower()
        weight = _as_float(row.get("weight"))
        reference = _as_float(row.get("reference"))
        if not isinstance(key, str) or not key:
            raise ValueError(f"pareto contract objectives[{idx}].key missing/invalid: {path}")
        if key in seen_keys:
            raise ValueError(f"pareto contract objectives[{idx}].key duplicated ({key}): {path}")
        if not isinstance(metric_path, str) or not metric_path:
            raise ValueError(f"pareto contract objectives[{idx}].metric_path missing/invalid: {path}")
        if direction != "max":
            raise ValueError(f"pareto contract objectives[{idx}].direction only supports 'max': {path}")
        if not isinstance(weight, float) or weight <= 0.0:
            raise ValueError(f"pareto contract objectives[{idx}].weight missing/invalid: {path}")
        if not isinstance(reference, float):
            raise ValueError(f"pareto contract objectives[{idx}].reference missing/invalid: {path}")
        seen_keys.add(key)
        objectives.append(
            {
                "key": key,
                "metric_path": metric_path,
                "direction": direction,
                "weight": float(weight),
                "reference": float(reference),
            }
        )

    raw_constraints = obj.get("hard_constraints")
    if raw_constraints is None:
        raw_constraints = []
    if not isinstance(raw_constraints, list):
        raise ValueError(f"pareto contract hard_constraints invalid: {path}")
    hard_constraints: list[dict[str, Any]] = []
    for idx, row in enumerate(raw_constraints):
        if not isinstance(row, dict):
            raise ValueError(f"pareto contract hard_constraints[{idx}] invalid: {path}")
        gate_key = row.get("gate_key")
        metric_path = row.get("metric_path")
        threshold = _as_float(row.get("threshold"))
        op = str(row.get("op", "gte")).lower()
        if not isinstance(gate_key, str) or not gate_key:
            raise ValueError(f"pareto contract hard_constraints[{idx}].gate_key missing/invalid: {path}")
        if not isinstance(metric_path, str) or not metric_path:
            raise ValueError(f"pareto contract hard_constraints[{idx}].metric_path missing/invalid: {path}")
        if not isinstance(threshold, float):
            raise ValueError(f"pareto contract hard_constraints[{idx}].threshold missing/invalid: {path}")
        if op not in ALLOWED_GATE_OPS:
            raise ValueError(
                f"pareto contract hard_constraints[{idx}].op must be one of {sorted(ALLOWED_GATE_OPS)}: {path}"
            )
        hard_constraints.append(
            {
                "gate_key": gate_key,
                "metric_path": metric_path,
                "op": op,
                "threshold": float(threshold),
            }
        )

    promotion = obj.get("promotion")
    if promotion is None:
        promotion = {}
    if not isinstance(promotion, dict):
        raise ValueError(f"pareto contract promotion invalid: {path}")
    require_nondominated_raw = promotion.get("require_nondominated")
    require_nondominated = bool(require_nondominated_raw) if isinstance(require_nondominated_raw, bool) else True
    min_hv_delta = _as_float(promotion.get("min_hv_delta"))
    dominance_epsilon = _as_float(promotion.get("dominance_epsilon"))

    payload = {
        "schema_id": schema_id,
        "objectives": objectives,
        "hard_constraints": hard_constraints,
        "promotion": {
            "require_nondominated": require_nondominated,
            "min_hv_delta": float(min_hv_delta) if isinstance(min_hv_delta, float) else 0.0,
            "dominance_epsilon": float(dominance_epsilon) if isinstance(dominance_epsilon, float) else 0.0,
        },
    }
    return {
        "schema_id": schema_id,
        "path": str(path.resolve()),
        "digest": _normalize_hash(sha256_hex(path.read_bytes())),
        "objectives": objectives,
        "hard_constraints": hard_constraints,
        "promotion": payload["promotion"],
    }


def _pareto_vector(metrics: dict[str, Any], objectives: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, float | None] = {}
    missing: list[str] = []
    for row in objectives:
        key = row["key"]
        val = _metric_get(metrics, row["metric_path"])
        values[key] = val
        if not isinstance(val, float):
            missing.append(key)
    return {
        "values": values,
        "missing": missing,
        "complete": bool(not missing),
    }


def _pareto_eval_constraints(metrics: dict[str, Any], constraints: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    passed_all = True
    for row in constraints:
        eval_row = _eval_gate(
            gate_key=str(row["gate_key"]),
            metric_path=str(row["metric_path"]),
            threshold=float(row["threshold"]),
            op=str(row["op"]),
            metrics=metrics,
            source="pareto_hard_constraints",
        )
        rows.append(eval_row)
        if not bool(eval_row.get("pass")):
            passed_all = False
    return {"pass": bool(passed_all), "rows": rows}


def _pareto_dominates(a: dict[str, float | None], b: dict[str, float | None], *, epsilon: float) -> bool:
    better_any = False
    eps = max(0.0, float(epsilon))
    for key, av in a.items():
        bv = b.get(key)
        if not isinstance(av, float) or not isinstance(bv, float):
            return False
        if av + eps < bv:
            return False
        if av > bv + eps:
            better_any = True
    return bool(better_any)


def _pareto_hypervolume(values: dict[str, float | None], objectives: list[dict[str, Any]]) -> float | None:
    hv = 1.0
    for row in objectives:
        key = str(row["key"])
        val = values.get(key)
        if not isinstance(val, float):
            return None
        reference = float(row["reference"])
        weight = max(0.01, float(row["weight"]))
        gain = max(0.0, float(val) - reference)
        hv *= gain ** weight
    return float(hv)


def _pareto_compare(
    *,
    candidate_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
    pareto_contract: dict[str, Any],
) -> dict[str, Any]:
    objectives = pareto_contract["objectives"]
    hard_constraints = pareto_contract["hard_constraints"]
    promotion = pareto_contract["promotion"]
    epsilon = float(promotion.get("dominance_epsilon", 0.0))
    min_hv_delta = float(promotion.get("min_hv_delta", 0.0))
    require_nondominated = bool(promotion.get("require_nondominated", True))

    candidate_vector = _pareto_vector(candidate_metrics, objectives)
    baseline_vector = _pareto_vector(baseline_metrics, objectives)
    candidate_constraints = _pareto_eval_constraints(candidate_metrics, hard_constraints)
    baseline_constraints = _pareto_eval_constraints(baseline_metrics, hard_constraints)

    candidate_vals = candidate_vector["values"]
    baseline_vals = baseline_vector["values"]
    candidate_complete = bool(candidate_vector.get("complete"))
    baseline_complete = bool(baseline_vector.get("complete"))

    candidate_dominates = False
    baseline_dominates = False
    if candidate_complete and baseline_complete:
        candidate_dominates = _pareto_dominates(candidate_vals, baseline_vals, epsilon=epsilon)
        baseline_dominates = _pareto_dominates(baseline_vals, candidate_vals, epsilon=epsilon)
    non_dominated = bool(candidate_complete and baseline_complete and not baseline_dominates)

    candidate_hv = _pareto_hypervolume(candidate_vals, objectives) if candidate_complete else None
    baseline_hv = _pareto_hypervolume(baseline_vals, objectives) if baseline_complete else None
    hv_delta = (
        float(candidate_hv) - float(baseline_hv)
        if isinstance(candidate_hv, float) and isinstance(baseline_hv, float)
        else None
    )

    hv_pass = bool(isinstance(hv_delta, float) and hv_delta >= min_hv_delta)
    nondominated_pass = bool(non_dominated) if require_nondominated else True
    candidate_constraints_pass = bool(candidate_constraints.get("pass"))
    adoptable = bool(candidate_constraints_pass and nondominated_pass and hv_pass)
    return {
        "candidate_vector": candidate_vector,
        "baseline_vector": baseline_vector,
        "candidate_constraints": candidate_constraints,
        "baseline_constraints": baseline_constraints,
        "candidate_dominates_baseline": bool(candidate_dominates),
        "baseline_dominates_candidate": bool(baseline_dominates),
        "candidate_non_dominated": bool(non_dominated),
        "candidate_hv": candidate_hv,
        "baseline_hv": baseline_hv,
        "hv_delta": hv_delta,
        "require_nondominated": bool(require_nondominated),
        "min_hv_delta": float(min_hv_delta),
        "dominance_epsilon": float(epsilon),
        "adoptable": bool(adoptable),
    }


def _clip_score_value(value: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(value)))


def _relative_promotion_scores(
    *,
    candidate_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
    candidate_holdout_phase1_mean: float | None = None,
    baseline_holdout_phase1_mean: float | None = None,
    stability_weight: float = DEFAULT_RELATIVE_PROMOTION_STABILITY_WEIGHT,
) -> dict[str, Any]:
    strength_components: list[dict[str, Any]] = []
    candidate_strength = 0.0
    baseline_strength = 0.0
    for metric_path, weight in RELATIVE_PROMOTION_STRENGTH_COMPONENTS:
        candidate_value = _metric_get(candidate_metrics, metric_path)
        baseline_value = _metric_get(baseline_metrics, metric_path)
        if not isinstance(candidate_value, float) or not isinstance(baseline_value, float):
            continue
        candidate_strength += float(candidate_value) * float(weight)
        baseline_strength += float(baseline_value) * float(weight)
        strength_components.append(
            {
                "metric_path": metric_path,
                "weight": float(weight),
                "candidate": float(candidate_value),
                "baseline": float(baseline_value),
                "delta": float(candidate_value) - float(baseline_value),
            }
        )

    stability_components: list[dict[str, Any]] = []
    candidate_stability = 0.0
    baseline_stability = 0.0
    for metric_path, weight, lo, hi in RELATIVE_PROMOTION_STABILITY_COMPONENTS:
        candidate_value = _metric_get(candidate_metrics, metric_path)
        baseline_value = _metric_get(baseline_metrics, metric_path)
        if not isinstance(candidate_value, float) or not isinstance(baseline_value, float):
            continue
        candidate_clipped = _clip_score_value(candidate_value, lo, hi)
        baseline_clipped = _clip_score_value(baseline_value, lo, hi)
        candidate_stability += candidate_clipped * float(weight)
        baseline_stability += baseline_clipped * float(weight)
        stability_components.append(
            {
                "metric_path": metric_path,
                "weight": float(weight),
                "candidate": float(candidate_value),
                "baseline": float(baseline_value),
                "candidate_clipped": float(candidate_clipped),
                "baseline_clipped": float(baseline_clipped),
                "delta": float(candidate_value) - float(baseline_value),
            }
        )

    holdout_name, holdout_weight, holdout_lo, holdout_hi = RELATIVE_PROMOTION_HOLDOUT_COMPONENT
    if isinstance(candidate_holdout_phase1_mean, float) and isinstance(baseline_holdout_phase1_mean, float):
        candidate_clipped = _clip_score_value(candidate_holdout_phase1_mean, holdout_lo, holdout_hi)
        baseline_clipped = _clip_score_value(baseline_holdout_phase1_mean, holdout_lo, holdout_hi)
        candidate_stability += candidate_clipped * float(holdout_weight)
        baseline_stability += baseline_clipped * float(holdout_weight)
        stability_components.append(
            {
                "metric_path": holdout_name,
                "weight": float(holdout_weight),
                "candidate": float(candidate_holdout_phase1_mean),
                "baseline": float(baseline_holdout_phase1_mean),
                "candidate_clipped": float(candidate_clipped),
                "baseline_clipped": float(baseline_clipped),
                "delta": float(candidate_holdout_phase1_mean) - float(baseline_holdout_phase1_mean),
            }
        )

    strength_delta = float(candidate_strength - baseline_strength)
    stability_delta = float(candidate_stability - baseline_stability)
    candidate_promotion_score = float(candidate_strength + float(stability_weight) * candidate_stability)
    baseline_promotion_score = float(baseline_strength + float(stability_weight) * baseline_stability)
    return {
        "strength_score": float(candidate_strength),
        "baseline_strength_score": float(baseline_strength),
        "strength_delta": float(strength_delta),
        "stability_score": float(candidate_stability),
        "baseline_stability_score": float(baseline_stability),
        "stability_delta": float(stability_delta),
        "promotion_score": float(candidate_promotion_score),
        "baseline_promotion_score": float(baseline_promotion_score),
        "promotion_score_delta": float(candidate_promotion_score - baseline_promotion_score),
        "stability_weight": float(stability_weight),
        "strength_components": strength_components,
        "stability_components": stability_components,
    }


def _relative_promotion_gate(
    *,
    candidate_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
    score_improved: bool,
    no_regression_pass: bool,
    focus_pass: bool,
    candidate_holdout_phase1_mean: float | None,
    baseline_holdout_phase1_mean: float | None,
    holdout_required: bool,
    holdout_regress_tolerance: float,
    strength_margin: float = DEFAULT_RELATIVE_PROMOTION_STRENGTH_MARGIN,
    stability_margin: float = DEFAULT_RELATIVE_PROMOTION_STABILITY_MARGIN,
    promotion_score_margin: float = DEFAULT_RELATIVE_PROMOTION_SCORE_MARGIN,
    stability_weight: float = DEFAULT_RELATIVE_PROMOTION_STABILITY_WEIGHT,
) -> dict[str, Any]:
    scores = _relative_promotion_scores(
        candidate_metrics=candidate_metrics,
        baseline_metrics=baseline_metrics,
        candidate_holdout_phase1_mean=candidate_holdout_phase1_mean,
        baseline_holdout_phase1_mean=baseline_holdout_phase1_mean,
        stability_weight=stability_weight,
    )
    holdout_floor_pass = True
    if holdout_required:
        holdout_floor_pass = bool(
            isinstance(candidate_holdout_phase1_mean, float)
            and isinstance(baseline_holdout_phase1_mean, float)
            and float(candidate_holdout_phase1_mean) >= float(baseline_holdout_phase1_mean) - float(holdout_regress_tolerance)
        )
    hard_floor_rows = [
        {"gate": "score_improved", "pass": bool(score_improved)},
        {"gate": "no_regression", "pass": bool(no_regression_pass)},
        {"gate": "focus_pass", "pass": bool(focus_pass)},
        {
            "gate": "holdout_floor",
            "pass": bool(holdout_floor_pass),
            "required": bool(holdout_required),
            "candidate": float(candidate_holdout_phase1_mean) if isinstance(candidate_holdout_phase1_mean, float) else None,
            "baseline": float(baseline_holdout_phase1_mean) if isinstance(baseline_holdout_phase1_mean, float) else None,
            "tolerance": float(holdout_regress_tolerance),
        },
    ]
    hard_floor_pass = all(bool(row.get("pass")) for row in hard_floor_rows)
    strength_pass = bool(scores["strength_delta"] >= float(strength_margin))
    stability_pass = bool(scores["stability_delta"] >= float(stability_margin))
    promotion_score_pass = bool(scores["promotion_score_delta"] >= float(promotion_score_margin))
    gate_pass = bool(hard_floor_pass and strength_pass and stability_pass and promotion_score_pass)
    return {
        "pass": bool(gate_pass),
        "hard_floor_pass": bool(hard_floor_pass),
        "hard_floor_rows": hard_floor_rows,
        "strength_pass": bool(strength_pass),
        "stability_pass": bool(stability_pass),
        "promotion_score_pass": bool(promotion_score_pass),
        "strength_margin": float(strength_margin),
        "stability_margin": float(stability_margin),
        "promotion_score_margin": float(promotion_score_margin),
        "scores": scores,
    }


def _provisional_confirmation_gate(
    *,
    candidate_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
    candidate_holdout_phase1_mean: float | None,
    baseline_holdout_phase1_mean: float | None,
    candidate_holdout_phase2_mean: float | None,
    baseline_holdout_phase2_mean: float | None,
    holdout_phase1_required: bool,
    holdout_phase2_required: bool,
    holdout_regress_tolerance: float,
) -> dict[str, Any]:
    relative = _relative_promotion_gate(
        candidate_metrics=candidate_metrics,
        baseline_metrics=baseline_metrics,
        score_improved=True,
        no_regression_pass=_passes_no_regression(
            candidate_metrics,
            baseline_metrics,
            float(holdout_regress_tolerance),
        ),
        focus_pass=True,
        candidate_holdout_phase1_mean=candidate_holdout_phase1_mean,
        baseline_holdout_phase1_mean=baseline_holdout_phase1_mean,
        holdout_required=bool(holdout_phase1_required),
        holdout_regress_tolerance=float(holdout_regress_tolerance),
    )
    phase2_pass = True
    if bool(holdout_phase2_required):
        if isinstance(candidate_holdout_phase2_mean, float):
            if isinstance(baseline_holdout_phase2_mean, float):
                phase2_pass = bool(
                    candidate_holdout_phase2_mean
                    >= baseline_holdout_phase2_mean - float(holdout_regress_tolerance)
                )
            else:
                phase2_pass = True
        else:
            phase2_pass = False
    return {
        "pass": bool(relative.get("pass")) and bool(phase2_pass),
        "relative_promotion": relative,
        "phase2_pass": bool(phase2_pass),
        "candidate_holdout_phase2_mean": (
            float(candidate_holdout_phase2_mean) if isinstance(candidate_holdout_phase2_mean, float) else None
        ),
        "baseline_holdout_phase2_mean": (
            float(baseline_holdout_phase2_mean) if isinstance(baseline_holdout_phase2_mean, float) else None
        ),
        "holdout_phase2_required": bool(holdout_phase2_required),
        "holdout_regress_tolerance": float(holdout_regress_tolerance),
    }


def _pareto_archive_update(
    *,
    state: dict[str, Any],
    pareto_contract: dict[str, Any],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    archive_raw = state.get("pareto_archive")
    archive: list[dict[str, Any]] = []
    if isinstance(archive_raw, list):
        for row in archive_raw:
            if isinstance(row, dict):
                archive.append(copy.deepcopy(row))
    for row in entries:
        if isinstance(row, dict):
            archive.append(copy.deepcopy(row))
    if len(archive) > 256:
        archive = archive[-256:]

    objectives = pareto_contract["objectives"]
    epsilon = float(pareto_contract["promotion"].get("dominance_epsilon", 0.0))
    front: list[dict[str, Any]] = []
    for idx, row in enumerate(archive):
        vec = row.get("vector")
        if not isinstance(vec, dict):
            continue
        if not bool(row.get("constraints_pass")):
            continue
        dominated = False
        for jdx, other in enumerate(archive):
            if idx == jdx:
                continue
            other_vec = other.get("vector")
            if not isinstance(other_vec, dict):
                continue
            if not bool(other.get("constraints_pass")):
                continue
            if _pareto_dominates(other_vec, vec, epsilon=epsilon):
                dominated = True
                break
        if not dominated:
            front.append(copy.deepcopy(row))
    if len(front) > 64:
        front = front[-64:]

    state["pareto_archive"] = archive
    state["pareto_front"] = front
    return {
        "archive_size": int(len(archive)),
        "front_size": int(len(front)),
        "front": front,
    }


def _normalize_relpath(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if s.startswith("path:"):
        s = s.removeprefix("path:").strip()
        if not s:
            return None
    s = s.replace("\\", "/")
    root_prefix = ROOT.as_posix().rstrip("/")
    if root_prefix:
        if s.startswith(root_prefix + "/"):
            s = s[len(root_prefix) + 1 :]
        else:
            root_no_leading = root_prefix.lstrip("/")
            if root_no_leading and s.startswith(root_no_leading + "/"):
                s = s[len(root_no_leading) + 1 :]
    while s.startswith("./"):
        s = s[2:]
    while s.startswith("/"):
        s = s[1:]
    return s or None


def _action_ticket_has_plan(action_obj: dict[str, Any] | None) -> bool:
    if not isinstance(action_obj, dict):
        return False
    mechanism_plan = action_obj.get("mechanism_plan")
    if isinstance(mechanism_plan, list) and mechanism_plan:
        return True
    knob_plan = action_obj.get("knob_plan")
    return bool(isinstance(knob_plan, list) and knob_plan)


def _validate_action_ticket(
    action_obj: dict[str, Any] | None,
    *,
    cycle: int,
    allow_shared_runtime_patches: bool = DEFAULT_ALLOW_SHARED_RUNTIME_PATCH_TICKETS,
) -> dict[str, Any]:
    if not isinstance(action_obj, dict):
        return {"pass": False, "reason": "missing_action"}
    source_cycle = _as_int(action_obj.get("source_cycle"))
    if not isinstance(source_cycle, int):
        return {"pass": False, "reason": "missing_source_cycle"}
    expected_source_cycle = int(cycle) - 1
    if expected_source_cycle >= 1 and source_cycle != expected_source_cycle:
        return {
            "pass": False,
            "reason": "source_cycle_mismatch",
            "source_cycle": source_cycle,
            "expected_source_cycle": expected_source_cycle,
        }
    has_plan = _action_ticket_has_plan(action_obj)
    change_applied = action_obj.get("change_applied")
    patched_files_raw = action_obj.get("patched_files")
    patched_files: list[str] = []
    if isinstance(patched_files_raw, list):
        for row in patched_files_raw:
            rel = _normalize_relpath(row)
            if isinstance(rel, str):
                patched_files.append(rel)
    if patched_files and change_applied is not True:
        return {"pass": False, "reason": "change_not_applied", "source_cycle": source_cycle}
    touched_core = sorted({row for row in patched_files if row in CORE_PATCH_FILES})
    touched_shared_runtime = sorted({row for row in patched_files if row in SHARED_RUNTIME_PATCH_FILES})
    touched_strategy = sorted({row for row in patched_files if row in CORE_STRATEGY_PATCH_FILES})
    if touched_shared_runtime and not bool(allow_shared_runtime_patches):
        return {
            "pass": False,
            "reason": "shared_runtime_patch_forbidden",
            "source_cycle": source_cycle,
            "patched_files": patched_files,
            "touched_shared_runtime_files": touched_shared_runtime,
        }
    if patched_files:
        return {
            "pass": True,
            "reason": "ok_patch",
            "mode": "patch",
            "source_cycle": source_cycle,
            "expected_source_cycle": expected_source_cycle if expected_source_cycle >= 1 else None,
            "patched_files": patched_files,
            "touched_core_files": touched_core,
            "touched_strategy_files": touched_strategy,
            "touched_shared_runtime_files": touched_shared_runtime,
            "patch_manifest_ref": action_obj.get("patch_manifest_ref"),
            "plan_only": False,
        }
    if not has_plan:
        return {
            "pass": False,
            "reason": "missing_plan",
            "source_cycle": source_cycle,
            "patched_files": patched_files,
        }
    return {
        "pass": True,
        "reason": "ok_plan_only",
        "mode": "plan_only",
        "source_cycle": source_cycle,
        "expected_source_cycle": expected_source_cycle if expected_source_cycle >= 1 else None,
        "patched_files": patched_files,
        "touched_core_files": touched_core,
        "touched_strategy_files": touched_strategy,
        "touched_shared_runtime_files": touched_shared_runtime,
        "patch_manifest_ref": action_obj.get("patch_manifest_ref"),
        "plan_only": True,
    }


def _batch_report_paths(batch_path: Path) -> list[Path]:
    if not batch_path.exists():
        return []
    data = _json_load(batch_path)
    runs = data.get("runs") if isinstance(data, dict) else None
    out: list[Path] = []
    if not isinstance(runs, list):
        return out
    for run in runs:
        if not isinstance(run, dict):
            continue
        ref = run.get("report_ref")
        if isinstance(ref, str) and ref.startswith("path:"):
            p = Path(ref.removeprefix("path:"))
            if p.exists():
                out.append(p)
            continue
        out_dir = run.get("out_dir")
        if isinstance(out_dir, str):
            p = Path(out_dir) / "scrimmage_report.json"
            if p.exists():
                out.append(p)
    return out


def _report_bb100(report_path: Path) -> float | None:
    if not report_path.exists():
        return None
    report = _json_load(report_path)
    if not isinstance(report, dict):
        return None
    analysis = report.get("analysis")
    if not isinstance(analysis, dict):
        return None
    bb = analysis.get("bb_per_100")
    return float(bb) if isinstance(bb, (int, float)) else None


def _batch_bb100_values(batch_path: Path) -> list[float]:
    vals: list[float] = []
    for report_path in _batch_report_paths(batch_path):
        v = _report_bb100(report_path)
        if isinstance(v, float):
            vals.append(v)
    return vals


def _aggregate_forced_bet_integrity(batch_path: Path) -> dict[str, Any]:
    reports = 0
    hands_total = 0
    mismatch_hands_total = 0
    mismatch_abs_sum_bb = 0.0
    mismatch_max_bb = 0.0
    ante_gap_abs_max_bb = 0.0

    for report_path in _batch_report_paths(batch_path):
        report = _json_load(report_path)
        if not isinstance(report, dict):
            continue
        analysis = report.get("analysis")
        if not isinstance(analysis, dict):
            continue

        reports += 1
        hands = _as_int(analysis.get("hands"))
        mismatch_count = _as_int(analysis.get("forced_mismatch_count"))
        mismatch_total_bb = _as_float(analysis.get("forced_mismatch_bb"))
        mismatch_max_item_bb = _as_float(analysis.get("forced_mismatch_max_bb"))
        model_ante_bb = _as_float(analysis.get("model_ante_bb"))
        ante_expected_bb = _as_float(analysis.get("ante_expected_bb"))

        if isinstance(hands, int) and hands > 0:
            hands_total += hands
        if isinstance(mismatch_count, int) and mismatch_count > 0:
            mismatch_hands_total += mismatch_count
        if isinstance(mismatch_total_bb, float):
            mismatch_abs_sum_bb += abs(mismatch_total_bb)
        if isinstance(mismatch_max_item_bb, float):
            mismatch_max_bb = max(mismatch_max_bb, abs(mismatch_max_item_bb))
        if isinstance(model_ante_bb, float) and isinstance(ante_expected_bb, float):
            ante_gap_abs_max_bb = max(ante_gap_abs_max_bb, abs(model_ante_bb - ante_expected_bb))

    epsilon = 1e-9
    passed = bool(
        reports > 0
        and mismatch_hands_total == 0
        and mismatch_abs_sum_bb <= epsilon
        and mismatch_max_bb <= epsilon
        and ante_gap_abs_max_bb <= epsilon
    )
    return {
        "reports": int(reports),
        "hands_total": int(hands_total),
        "mismatch_hands_total": int(mismatch_hands_total),
        "mismatch_abs_sum_bb": float(mismatch_abs_sum_bb),
        "mismatch_max_bb": float(mismatch_max_bb),
        "ante_gap_abs_max_bb": float(ante_gap_abs_max_bb),
        "pass": bool(passed),
    }


def _seed_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
    mean = sum(values) / len(values)
    if len(values) <= 1:
        std = 0.0
    else:
        var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        std = math.sqrt(var)
    return {"n": len(values), "mean": mean, "std": std, "min": min(values), "max": max(values)}


def _composite_gate_score(values: list[float], *, mean_weight: float = GATE_SCORE_MEAN_WEIGHT) -> float:
    cleaned = [float(v) for v in values if isinstance(v, (int, float))]
    if not cleaned:
        return float("-inf")
    return min(cleaned) + float(mean_weight) * (sum(cleaned) / len(cleaned))


def _aggregate_facing_turnriver_y(batch_path: Path) -> dict[str, Any]:
    street_agg: dict[str, dict[str, float]] = {
        "TURN": {"hands": 0.0, "profit_bb": 0.0},
        "RIVER": {"hands": 0.0, "profit_bb": 0.0},
    }
    for report_path in _batch_report_paths(batch_path):
        report = _json_load(report_path)
        if not isinstance(report, dict):
            continue
        analysis = report.get("analysis")
        if not isinstance(analysis, dict):
            continue
        rows = analysis.get("bb_flat_postflop_facing_by_street")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            street = row.get("street")
            facing = row.get("facing")
            if street not in ("TURN", "RIVER") or facing != "Y":
                continue
            hands = row.get("hands")
            profit = row.get("profit_bb")
            if not isinstance(hands, (int, float)) or not isinstance(profit, (int, float)):
                continue
            street_agg[street]["hands"] += float(hands)
            street_agg[street]["profit_bb"] += float(profit)

    street_metrics: dict[str, dict[str, Any]] = {}
    total_hands = 0.0
    high_support_guard = 1.0
    worst_street: str | None = None
    worst_bb100: float | None = None
    worst_hands: float | None = None
    for street, row in street_agg.items():
        hands = float(row["hands"])
        profit = float(row["profit_bb"])
        total_hands += hands
        bb100 = (profit / hands * 100.0) if hands > 0.0 else None
        street_metrics[street] = {"hands": int(hands), "profit_bb": profit, "bb100": bb100}
        if isinstance(bb100, float):
            if worst_bb100 is None or bb100 < worst_bb100:
                worst_bb100 = bb100
                worst_street = street
                worst_hands = hands
            if hands >= 50.0 and bb100 < -150.0:
                high_support_guard = 0.0
    return {
        "streets": street_metrics,
        "total_hands": int(total_hands),
        "worst_street": worst_street,
        "worst_bb100": worst_bb100,
        "worst_hands": int(worst_hands) if isinstance(worst_hands, (int, float)) else None,
        "high_support_guard": high_support_guard,
    }


def _aggregate_high_price_focus_probe(batch_path: Path) -> dict[str, Any]:
    high_price_hits_total = 0
    high_price_hits_by_street = {"TURN": 0, "RIVER": 0}
    facing_counts = {
        "TURN": {"fold": 0, "call": 0, "raise": 0},
        "RIVER": {"fold": 0, "call": 0, "raise": 0},
    }
    for report_path in _batch_report_paths(batch_path):
        report = _json_load(report_path)
        if not isinstance(report, dict):
            continue
        analysis = report.get("analysis")
        if not isinstance(analysis, dict):
            continue
        hits = analysis.get("high_price_low_spr_hits")
        if isinstance(hits, (int, float)):
            high_price_hits_total += int(hits)
        hits_by_street = analysis.get("high_price_low_spr_hits_by_street")
        if isinstance(hits_by_street, dict):
            for street in ("TURN", "RIVER"):
                v = hits_by_street.get(street)
                if isinstance(v, (int, float)):
                    high_price_hits_by_street[street] += int(v)

        outcomes_by_street = analysis.get("facing_bet_outcomes_by_street")
        if not isinstance(outcomes_by_street, dict):
            continue
        for street in ("TURN", "RIVER"):
            street_rows = outcomes_by_street.get(street)
            if not isinstance(street_rows, dict):
                continue
            row = street_rows.get(f"{street}_>2")
            if not isinstance(row, dict):
                continue
            for action in ("fold", "call", "raise"):
                val = row.get(action)
                if isinstance(val, (int, float)):
                    facing_counts[street][action] += int(val)

    action_mix: dict[str, float | None] = {}
    for street in ("TURN", "RIVER"):
        total = float(sum(facing_counts[street].values()))
        if total <= 0:
            action_mix[f"{street.lower()}_high_price_fold_rate"] = None
            action_mix[f"{street.lower()}_high_price_call_rate"] = None
            action_mix[f"{street.lower()}_high_price_raise_rate"] = None
            continue
        action_mix[f"{street.lower()}_high_price_fold_rate"] = facing_counts[street]["fold"] / total
        action_mix[f"{street.lower()}_high_price_call_rate"] = facing_counts[street]["call"] / total
        action_mix[f"{street.lower()}_high_price_raise_rate"] = facing_counts[street]["raise"] / total

    return {
        "high_price_low_spr_hits": int(high_price_hits_total),
        "high_price_low_spr_hits_by_street": high_price_hits_by_street,
        "high_price_facing_counts": facing_counts,
        "high_price_action_mix": action_mix,
    }


def _action_mix_from_facing_counts(facing_counts: dict[str, dict[str, int]]) -> dict[str, float | None]:
    action_mix: dict[str, float | None] = {}
    for street in ("TURN", "RIVER"):
        row = facing_counts.get(street) if isinstance(facing_counts, dict) else None
        if not isinstance(row, dict):
            action_mix[f"{street.lower()}_high_price_fold_rate"] = None
            action_mix[f"{street.lower()}_high_price_call_rate"] = None
            action_mix[f"{street.lower()}_high_price_raise_rate"] = None
            continue
        fold_ct = int(_as_int(row.get("fold")) or 0)
        call_ct = int(_as_int(row.get("call")) or 0)
        raise_ct = int(_as_int(row.get("raise")) or 0)
        total = float(max(0, fold_ct + call_ct + raise_ct))
        if total <= 0:
            action_mix[f"{street.lower()}_high_price_fold_rate"] = None
            action_mix[f"{street.lower()}_high_price_call_rate"] = None
            action_mix[f"{street.lower()}_high_price_raise_rate"] = None
            continue
        action_mix[f"{street.lower()}_high_price_fold_rate"] = float(fold_ct) / total
        action_mix[f"{street.lower()}_high_price_call_rate"] = float(call_ct) / total
        action_mix[f"{street.lower()}_high_price_raise_rate"] = float(raise_ct) / total
    return action_mix


def _build_focus_probe(*, turnriver: dict[str, Any], high_price: dict[str, Any]) -> dict[str, Any]:
    return {
        "tierP_facingY_turnriver_total_hands": _as_int(turnriver.get("total_hands")),
        "tierP_facingY_turnriver_worst_hands": _as_int(turnriver.get("worst_hands")),
        "tierP_facingY_turnriver_worst_bb100": _as_float(turnriver.get("worst_bb100")),
        "tierP_facingY_turnriver_high_support_guard": _as_float(turnriver.get("high_support_guard")),
        "high_price_low_spr_hits": _as_int(high_price.get("high_price_low_spr_hits")),
        "high_price_low_spr_hits_by_street": high_price.get("high_price_low_spr_hits_by_street"),
        "high_price_facing_counts": high_price.get("high_price_facing_counts"),
        "high_price_action_mix": high_price.get("high_price_action_mix"),
    }


def _merge_focus_probe(base_probe: dict[str, Any], add_probe: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base_probe if isinstance(base_probe, dict) else {})
    add = add_probe if isinstance(add_probe, dict) else {}

    base_hands = int(_as_int(merged.get("tierP_facingY_turnriver_total_hands")) or 0)
    add_hands = int(_as_int(add.get("tierP_facingY_turnriver_total_hands")) or 0)
    merged["tierP_facingY_turnriver_total_hands"] = int(base_hands + add_hands)

    base_hits = int(_as_int(merged.get("high_price_low_spr_hits")) or 0)
    add_hits = int(_as_int(add.get("high_price_low_spr_hits")) or 0)
    merged["high_price_low_spr_hits"] = int(base_hits + add_hits)

    base_guard = _as_float(merged.get("tierP_facingY_turnriver_high_support_guard"))
    add_guard = _as_float(add.get("tierP_facingY_turnriver_high_support_guard"))
    if isinstance(base_guard, float) and isinstance(add_guard, float):
        merged["tierP_facingY_turnriver_high_support_guard"] = float(min(base_guard, add_guard))
    elif isinstance(add_guard, float):
        merged["tierP_facingY_turnriver_high_support_guard"] = float(add_guard)

    base_worst = _as_float(merged.get("tierP_facingY_turnriver_worst_bb100"))
    add_worst = _as_float(add.get("tierP_facingY_turnriver_worst_bb100"))
    if isinstance(add_worst, float) and (not isinstance(base_worst, float) or add_worst < base_worst):
        merged["tierP_facingY_turnriver_worst_bb100"] = float(add_worst)
        merged["tierP_facingY_turnriver_worst_hands"] = _as_int(add.get("tierP_facingY_turnriver_worst_hands"))

    base_hits_by_street = merged.get("high_price_low_spr_hits_by_street")
    if not isinstance(base_hits_by_street, dict):
        base_hits_by_street = {"TURN": 0, "RIVER": 0}
    add_hits_by_street = add.get("high_price_low_spr_hits_by_street")
    if isinstance(add_hits_by_street, dict):
        for street in ("TURN", "RIVER"):
            base_hits_by_street[street] = int(_as_int(base_hits_by_street.get(street)) or 0) + int(
                _as_int(add_hits_by_street.get(street)) or 0
            )
    merged["high_price_low_spr_hits_by_street"] = base_hits_by_street

    base_counts = merged.get("high_price_facing_counts")
    if not isinstance(base_counts, dict):
        base_counts = {"TURN": {"fold": 0, "call": 0, "raise": 0}, "RIVER": {"fold": 0, "call": 0, "raise": 0}}
    add_counts = add.get("high_price_facing_counts")
    if isinstance(add_counts, dict):
        for street in ("TURN", "RIVER"):
            row = base_counts.get(street)
            if not isinstance(row, dict):
                row = {"fold": 0, "call": 0, "raise": 0}
                base_counts[street] = row
            add_row = add_counts.get(street)
            if not isinstance(add_row, dict):
                continue
            for action in ("fold", "call", "raise"):
                row[action] = int(_as_int(row.get(action)) or 0) + int(_as_int(add_row.get(action)) or 0)
    merged["high_price_facing_counts"] = base_counts
    merged["high_price_action_mix"] = _action_mix_from_facing_counts(base_counts)
    return merged


def _read_batch_mean_std(batch_path: Path) -> tuple[float | None, float | None]:
    vals = _batch_bb100_values(batch_path)
    if not vals:
        return None, None
    mean = sum(vals) / len(vals)
    if len(vals) <= 1:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return mean, math.sqrt(var)


def _run_scrimmage_batch(
    *,
    scenario: str,
    profile: str,
    policy: str,
    opponents: str,
    hands: int,
    seeds: str,
    jobs: int,
    out_dir: Path,
    quiet: bool,
    timeout_sec: float | None = None,
    heartbeat_sec: float | None = None,
) -> tuple[int, float | None, float | None]:
    cmd = [
        sys.executable,
        "-m",
        "poker2.cli.scrimmage_batch",
        "--scenario",
        scenario,
        "--profile",
        profile,
        "--policy",
        policy,
        "--opponents",
        opponents,
        "--hands",
        str(hands),
        "--seeds",
        seeds,
        "--jobs",
        str(jobs),
        "--out-dir",
        str(out_dir),
    ]
    if quiet:
        cmd.append("--quiet")
    if isinstance(timeout_sec, (int, float)) and float(timeout_sec) > 0:
        cmd.extend(["--timeout-sec", str(float(timeout_sec))])
    if isinstance(heartbeat_sec, (int, float)) and float(heartbeat_sec) > 0:
        cmd.extend(["--heartbeat-sec", str(float(heartbeat_sec))])
    rc = _run_cmd(cmd, log_path=out_dir / "run.log", timeout_sec=timeout_sec)
    mean, std = _read_batch_mean_std(out_dir / "scrimmage_batch.json")
    return rc, mean, std


def _quick_eval(
    *,
    policy_label: str,
    run_root: Path,
    profile: str,
    quick_scenarios: list[str],
    tier_a_opponents: str,
    tier_p_opponents: str,
    hands: int,
    seeds_json: str,
    jobs: int,
    quiet: bool,
    timeout_sec: float | None = None,
    heartbeat_sec: float | None = None,
) -> dict[str, Any]:
    per_metric: dict[str, Any] = {}
    vals: list[float] = []
    focus_probe: dict[str, Any] | None = None
    targeted_focus_diag: dict[str, Any] = {
        "enabled": bool(DEFAULT_FOCUS_TARGETED_ENABLE),
        "attempted": False,
        "merged": False,
        "scenario": None,
        "hands": None,
        "jobs": None,
        "returncode": None,
        "mean_bb100": None,
        "std_bb100": None,
        "out_dir": None,
        "support_before": {"hands": 0, "hits": 0},
        "support_after": {"hands": 0, "hits": 0},
    }
    ante_integrity_fail_metrics: list[str] = []
    ante_integrity_reports = 0
    ante_integrity_hands = 0
    ante_integrity_mismatch_hands = 0
    ante_integrity_mismatch_abs_sum_bb = 0.0
    ante_integrity_mismatch_max_bb = 0.0
    ante_integrity_gap_abs_max_bb = 0.0
    task_rows: list[tuple[str, str, str, Path]] = []
    for scenario in quick_scenarios:
        task_rows.append((scenario, "tierA", tier_a_opponents, run_root / scenario / "tierA"))
        task_rows.append((scenario, "tierP", tier_p_opponents, run_root / scenario / "tierP"))
    task_count = len(task_rows)
    worker_slots = max(1, min(task_count, max(1, int(jobs))))
    jobs_plan = _distribute_jobs(max(1, int(jobs)), worker_slots)
    jobs_per_task = max(jobs_plan) if jobs_plan else 1

    with ThreadPoolExecutor(max_workers=worker_slots) as pool:
        futures: dict[Any, tuple[str, str, Path]] = {}
        for idx, (scenario, tier_name, opp, out_dir) in enumerate(task_rows):
            task_jobs = jobs_plan[idx % len(jobs_plan)] if jobs_plan else 1
            fut = pool.submit(
                _run_scrimmage_batch,
                scenario=scenario,
                profile=profile,
                policy=policy_label,
                opponents=opp,
                hands=hands,
                seeds=seeds_json,
                jobs=task_jobs,
                out_dir=out_dir,
                quiet=quiet,
                timeout_sec=timeout_sec,
                heartbeat_sec=heartbeat_sec,
            )
            futures[fut] = (scenario, tier_name, out_dir)

        for fut in as_completed(futures):
            scenario, tier_name, out_dir = futures[fut]
            key = f"{scenario}:{tier_name}"
            rc: int = 1
            mean: float | None = None
            std: float | None = None
            runtime_error: dict[str, Any] | None = None
            try:
                rc, mean, std = fut.result()
            except Exception as exc:
                # Keep quick-gate alive on single task failure instead of bubbling up and exiting the worker.
                runtime_error = {
                    "stage": "run_scrimmage_batch",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            integrity = None
            if rc == 0:
                try:
                    integrity = _aggregate_forced_bet_integrity(out_dir / "scrimmage_batch.json")
                except Exception as exc:
                    runtime_error = runtime_error or {}
                    runtime_error.update(
                        {
                            "stage": "forced_bet_integrity",
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                if isinstance(integrity, dict):
                    ante_integrity_reports += int(integrity.get("reports", 0) or 0)
                    ante_integrity_hands += int(integrity.get("hands_total", 0) or 0)
                    ante_integrity_mismatch_hands += int(integrity.get("mismatch_hands_total", 0) or 0)
                    ante_integrity_mismatch_abs_sum_bb += float(integrity.get("mismatch_abs_sum_bb", 0.0) or 0.0)
                    ante_integrity_mismatch_max_bb = max(
                        ante_integrity_mismatch_max_bb,
                        float(integrity.get("mismatch_max_bb", 0.0) or 0.0),
                    )
                    ante_integrity_gap_abs_max_bb = max(
                        ante_integrity_gap_abs_max_bb,
                        float(integrity.get("ante_gap_abs_max_bb", 0.0) or 0.0),
                    )
                    if not bool(integrity.get("pass")):
                        ante_integrity_fail_metrics.append(key)
            per_metric[key] = {
                "returncode": int(rc),
                "mean_bb100": mean,
                "std_bb100": std,
                "out_dir": str(out_dir),
                "forced_bet_integrity": integrity,
                "runtime_error": runtime_error,
            }
            if rc == 0 and isinstance(mean, (int, float)):
                vals.append(float(mean))
            if rc == 0 and tier_name == "tierP" and "coinpoker" in scenario.lower():
                batch_path = out_dir / "scrimmage_batch.json"
                try:
                    turnriver = _aggregate_facing_turnriver_y(batch_path)
                    high_price = _aggregate_high_price_focus_probe(batch_path)
                    next_probe = _build_focus_probe(turnriver=turnriver, high_price=high_price)
                    if isinstance(focus_probe, dict):
                        focus_probe = _merge_focus_probe(focus_probe, next_probe)
                    else:
                        focus_probe = next_probe
                except Exception as exc:
                    runtime_error = runtime_error or {}
                    runtime_error.update(
                        {
                            "stage": "focus_probe",
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                    per_metric[key]["runtime_error"] = runtime_error

    if bool(DEFAULT_FOCUS_TARGETED_ENABLE):
        coinpoker_focus_scenario = None
        for scenario_name in quick_scenarios:
            if isinstance(scenario_name, str) and "coinpoker" in scenario_name.lower():
                coinpoker_focus_scenario = scenario_name
                break
        targeted_focus_diag["scenario"] = coinpoker_focus_scenario
        if isinstance(coinpoker_focus_scenario, str):
            targeted_hands = int(round(float(hands) * float(DEFAULT_FOCUS_TARGETED_HANDS_RATIO)))
            targeted_hands = max(int(DEFAULT_FOCUS_TARGETED_HANDS_MIN), targeted_hands)
            targeted_hands = min(int(DEFAULT_FOCUS_TARGETED_HANDS_MAX), targeted_hands)
            targeted_jobs = max(1, min(int(jobs), int(DEFAULT_FOCUS_TARGETED_MAX_JOBS)))
            targeted_out_dir = run_root / "_targeted_focus_set" / coinpoker_focus_scenario / "tierP"
            targeted_focus_diag.update(
                {
                    "attempted": True,
                    "hands": int(targeted_hands),
                    "jobs": int(targeted_jobs),
                    "out_dir": str(targeted_out_dir),
                    "support_before": _focus_support_from_quick(
                        {"focus_probe": focus_probe if isinstance(focus_probe, dict) else {}}
                    ),
                }
            )
            rc, mean, std = _run_scrimmage_batch(
                scenario=coinpoker_focus_scenario,
                profile=profile,
                policy=policy_label,
                opponents=tier_p_opponents,
                hands=targeted_hands,
                seeds=seeds_json,
                jobs=targeted_jobs,
                out_dir=targeted_out_dir,
                quiet=quiet,
                timeout_sec=timeout_sec,
                heartbeat_sec=heartbeat_sec,
            )
            targeted_focus_diag["returncode"] = int(rc)
            targeted_focus_diag["mean_bb100"] = float(mean) if isinstance(mean, (int, float)) else None
            targeted_focus_diag["std_bb100"] = float(std) if isinstance(std, (int, float)) else None
            if int(rc) == 0:
                batch_path = targeted_out_dir / "scrimmage_batch.json"
                turnriver = _aggregate_facing_turnriver_y(batch_path)
                high_price = _aggregate_high_price_focus_probe(batch_path)
                targeted_probe = _build_focus_probe(turnriver=turnriver, high_price=high_price)
                if isinstance(focus_probe, dict):
                    focus_probe = _merge_focus_probe(focus_probe, targeted_probe)
                else:
                    focus_probe = targeted_probe
                targeted_focus_diag["merged"] = True
                targeted_focus_diag["support_after"] = _focus_support_from_quick({"focus_probe": focus_probe})
            else:
                targeted_focus_diag["support_after"] = dict(targeted_focus_diag.get("support_before") or {})
        else:
            targeted_focus_diag["skip_reason"] = "no_coinpoker_quick_scenario"

    if isinstance(focus_probe, dict):
        focus_probe["targeted_focus_set"] = targeted_focus_diag
    elif bool(DEFAULT_FOCUS_TARGETED_ENABLE):
        focus_probe = {"targeted_focus_set": targeted_focus_diag}
    score = _composite_gate_score(vals)
    ante_integrity = {
        "reports": int(ante_integrity_reports),
        "hands_total": int(ante_integrity_hands),
        "mismatch_hands_total": int(ante_integrity_mismatch_hands),
        "mismatch_abs_sum_bb": float(ante_integrity_mismatch_abs_sum_bb),
        "mismatch_max_bb": float(ante_integrity_mismatch_max_bb),
        "ante_gap_abs_max_bb": float(ante_integrity_gap_abs_max_bb),
        "failed_metrics": ante_integrity_fail_metrics,
        "pass": bool(ante_integrity_reports > 0 and not ante_integrity_fail_metrics),
    }
    return {
        "policy": policy_label,
        "score": score,
        "metrics": per_metric,
        "focus_probe": focus_probe,
        "ante_integrity": ante_integrity,
        "execution_plan": {
            "task_count": int(task_count),
            "parallelism": int(worker_slots),
            "jobs_requested": int(jobs),
            "jobs_per_task": int(jobs_per_task),
            "jobs_per_task_plan": jobs_plan,
        },
    }


def _normalize_seeds_for_cache(seeds_json: str) -> list[int] | None:
    try:
        obj = json.loads(seeds_json)
    except Exception:
        return None
    if not isinstance(obj, list):
        return None
    out: list[int] = []
    for row in obj:
        if isinstance(row, bool):
            return None
        if isinstance(row, int):
            out.append(int(row))
            continue
        if isinstance(row, str) and row.isdigit():
            out.append(int(row))
            continue
        return None
    return out


def _core_patch_files_digest() -> str:
    rows: list[dict[str, Any]] = []
    for rel_path in sorted(CORE_PATCH_FILES):
        file_path = ROOT / rel_path
        file_digest: str
        if file_path.exists() and file_path.is_file():
            try:
                file_digest = sha256_hex(file_path.read_bytes())
            except Exception:
                file_digest = "READ_ERROR"
        else:
            file_digest = "MISSING"
        rows.append({"path": rel_path, "digest": file_digest})
    return str(_canonical_digest_obj(rows).get("hex"))


def _quick_eval_cache_key(
    *,
    policy_label: str,
    policy_fingerprint: str,
    profile: str,
    quick_scenarios: list[str],
    tier_a_opponents: str,
    tier_p_opponents: str,
    hands: int,
    seeds_json: str,
    jobs: int,
) -> str:
    normalized_seeds = _normalize_seeds_for_cache(seeds_json)
    payload = {
        "schema": QUICK_EVAL_CACHE_SCHEMA,
        "policy_label": policy_label,
        "policy_fingerprint": policy_fingerprint,
        "core_patch_files_digest": _core_patch_files_digest(),
        "profile": profile,
        "quick_scenarios": list(quick_scenarios),
        "tier_a_opponents": tier_a_opponents,
        "tier_p_opponents": tier_p_opponents,
        "hands": int(hands),
        "seeds": normalized_seeds if isinstance(normalized_seeds, list) else seeds_json,
        "jobs": int(jobs),
        "python_executable": sys.executable,
    }
    return str(_canonical_digest_obj(payload)["hex"])


def _policy_fingerprint_from_label(policy_label: str) -> str:
    try:
        bundle = _resolve_policy_bundle(policy_label)
    except Exception:
        return str(_canonical_digest_obj({"policy_label": policy_label})["hex"])
    params = bundle.get("system_params")
    if isinstance(params, dict):
        return str(_canonical_digest_obj(params)["hex"])
    return str(_canonical_digest_obj({"policy_label": policy_label})["hex"])


def _quick_eval_cached(
    *,
    policy_label: str,
    run_root: Path,
    profile: str,
    quick_scenarios: list[str],
    tier_a_opponents: str,
    tier_p_opponents: str,
    hands: int,
    seeds_json: str,
    jobs: int,
    quiet: bool,
    timeout_sec: float | None = None,
    heartbeat_sec: float | None = None,
    policy_fingerprint: str | None = None,
) -> dict[str, Any]:
    cache_policy_fingerprint = (
        policy_fingerprint if isinstance(policy_fingerprint, str) and policy_fingerprint else _policy_fingerprint_from_label(policy_label)
    )
    cache_key = _quick_eval_cache_key(
        policy_label=policy_label,
        policy_fingerprint=cache_policy_fingerprint,
        profile=profile,
        quick_scenarios=quick_scenarios,
        tier_a_opponents=tier_a_opponents,
        tier_p_opponents=tier_p_opponents,
        hands=hands,
        seeds_json=seeds_json,
        jobs=jobs,
    )
    cache_path = QUICK_EVAL_CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists():
        try:
            cached = _json_load(cache_path)
        except Exception:
            cached = None
        if isinstance(cached, dict) and cached.get("schema") == QUICK_EVAL_CACHE_SCHEMA:
            result = cached.get("result")
            if isinstance(result, dict):
                hit_meta = {
                    "cache_hit": True,
                    "cache_key": cache_key,
                    "cache_ref": f"path:{cache_path.resolve()}",
                    "cached_at": cached.get("cached_at"),
                }
                _json_dump(run_root / "quick_eval_cache_hit.json", hit_meta)
                out = copy.deepcopy(result)
                out["_cache"] = hit_meta
                return out

    out = _quick_eval(
        policy_label=policy_label,
        run_root=run_root,
        profile=profile,
        quick_scenarios=quick_scenarios,
        tier_a_opponents=tier_a_opponents,
        tier_p_opponents=tier_p_opponents,
        hands=hands,
        seeds_json=seeds_json,
        jobs=jobs,
        quiet=quiet,
        timeout_sec=timeout_sec,
        heartbeat_sec=heartbeat_sec,
    )
    cache_payload = {
        "schema": QUICK_EVAL_CACHE_SCHEMA,
        "cache_key": cache_key,
        "cached_at": _now_ts(),
        "policy_label": policy_label,
        "policy_fingerprint": cache_policy_fingerprint,
        "result": out,
    }
    _json_dump(cache_path, cache_payload)
    miss_meta = {
        "cache_hit": False,
        "cache_key": cache_key,
        "cache_ref": f"path:{cache_path.resolve()}",
    }
    _json_dump(run_root / "quick_eval_cache_miss.json", miss_meta)
    out = copy.deepcopy(out)
    out["_cache"] = miss_meta
    return out


def _count_pool_suites(pool_path: str, *, include_holdout: bool) -> int:
    try:
        pool_obj = _json_load(Path(pool_path))
    except Exception:
        return 1
    if not isinstance(pool_obj, dict):
        return 1

    suites: set[str] = set()
    candidates = pool_obj.get("candidates")
    if isinstance(candidates, list):
        for row in candidates:
            if isinstance(row, dict):
                suite = row.get("suite")
                if isinstance(suite, str) and suite:
                    suites.add(suite)
    if include_holdout:
        holdout = pool_obj.get("holdout")
        if isinstance(holdout, list):
            for row in holdout:
                if isinstance(row, dict):
                    suite = row.get("suite")
                    if isinstance(suite, str) and suite:
                        suites.add(suite)
    return max(1, len(suites))


def _load_pool_holdout_suites(pool_path: str) -> list[str]:
    try:
        pool_obj = _json_load(Path(pool_path))
    except Exception:
        return []
    if not isinstance(pool_obj, dict):
        return []
    holdout = pool_obj.get("holdout")
    if not isinstance(holdout, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for row in holdout:
        if not isinstance(row, dict):
            continue
        suite = row.get("suite")
        if not isinstance(suite, str) or not suite:
            continue
        if suite in seen:
            continue
        seen.add(suite)
        out.append(suite)
    return out


def _parse_seed_list_or_empty(seeds_json: str) -> list[int]:
    parsed = _normalize_seeds_for_cache(seeds_json)
    return parsed if isinstance(parsed, list) else []


def _split_suite_jobs(total_jobs: int, suite_count: int) -> tuple[int, int]:
    total = max(1, int(total_jobs))
    suites = max(1, int(suite_count))
    suite_jobs = max(1, min(total, suites))
    jobs_per_run = max(1, total // suite_jobs)
    return suite_jobs, jobs_per_run


def _run_holdout_suite_eval(
    *,
    scenario: str,
    profile: str,
    policy: str,
    suite: str,
    hands: int,
    seeds_json: str,
    jobs: int,
    out_dir: Path,
    quiet: bool,
    timeout_sec: float | None = None,
    heartbeat_sec: float | None = None,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "poker2.cli.br_proxy",
        "--scenario",
        scenario,
        "--profile",
        profile,
        "--policy",
        policy,
        "--hands",
        str(max(1, int(hands))),
        "--seeds",
        seeds_json,
        "--candidates",
        json.dumps([suite], separators=(",", ":")),
        "--suite-jobs",
        "1",
        "--jobs",
        str(max(1, int(jobs))),
        "--out-dir",
        str(out_dir),
    ]
    if quiet:
        cmd.append("--quiet")
    if isinstance(timeout_sec, (int, float)) and float(timeout_sec) > 0:
        cmd.extend(["--timeout-sec", str(float(timeout_sec))])
    if isinstance(heartbeat_sec, (int, float)) and float(heartbeat_sec) > 0:
        cmd.extend(["--heartbeat-sec", str(float(heartbeat_sec))])
    rc = _run_cmd(cmd, log_path=out_dir / "run.log", timeout_sec=timeout_sec)
    summary_path = out_dir / "br_proxy_summary.json"
    summary = _json_load(summary_path) if summary_path.exists() else None

    mean_bb100 = None
    std_bb100 = None
    seed_vals: list[float] = []
    if isinstance(summary, dict):
        worst = summary.get("worst_case")
        if isinstance(worst, dict):
            m = worst.get("mean_bb100")
            s = worst.get("std_bb100")
            if isinstance(m, (int, float)):
                mean_bb100 = float(m)
            if isinstance(s, (int, float)):
                std_bb100 = float(s)
            raw_vals = worst.get("seed_vals")
            if isinstance(raw_vals, list):
                for row in raw_vals:
                    if isinstance(row, (int, float)):
                        seed_vals.append(float(row))
        if mean_bb100 is None:
            rows = summary.get("results")
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if row.get("suite") != suite:
                        continue
                    m = row.get("mean_bb100")
                    s = row.get("std_bb100")
                    if isinstance(m, (int, float)):
                        mean_bb100 = float(m)
                    if isinstance(s, (int, float)):
                        std_bb100 = float(s)
                    raw_vals = row.get("seed_vals")
                    if isinstance(raw_vals, list):
                        seed_vals = [float(v) for v in raw_vals if isinstance(v, (int, float))]
                    break
    if mean_bb100 is None and seed_vals:
        mean_bb100 = float(sum(seed_vals) / len(seed_vals))
    if std_bb100 is None and seed_vals:
        stat = _seed_stats(seed_vals)
        std_raw = stat.get("std")
        if isinstance(std_raw, (int, float)):
            std_bb100 = float(std_raw)

    seeds = _parse_seed_list_or_empty(seeds_json)
    return {
        "suite": suite,
        "returncode": int(rc),
        "mean_bb100": mean_bb100,
        "std_bb100": std_bb100,
        "seed_count": int(len(seed_vals) if seed_vals else len(seeds)),
        "hands": int(max(1, int(hands)) * max(1, len(seeds))),
        "summary_ref": f"path:{summary_path.resolve()}" if summary_path.exists() else None,
        "out_dir": str(out_dir),
    }


def _full_eval(
    *,
    policy_label: str,
    run_root: Path,
    profile: str,
    coinpoker_scenario: str,
    gg_scenario: str,
    tier_a_opponents: str,
    tier_p_opponents: str,
    pool_path: str,
    full_hands: int,
    full_seeds_json: str,
    confirm_seeds_json: str,
    jobs_total: int,
    quick_jobs_ratio: float,
    quiet: bool,
    timeout_sec: float | None = None,
    heartbeat_sec: float | None = None,
) -> dict[str, Any]:
    quick_jobs = _derive_phase_jobs(jobs_total, quick_jobs_ratio, leave_headroom=True)
    pool_suite_count = _count_pool_suites(pool_path, include_holdout=False)
    pool_suite_jobs, pool_jobs_per_run = _split_suite_jobs(jobs_total, pool_suite_count)
    br_suite_jobs, br_jobs_per_run = _split_suite_jobs(jobs_total, pool_suite_count)

    coin_dir = run_root / "coinpoker_full"
    coin_cmd = [
        sys.executable,
        "-m",
        "poker2.cli.eval_full",
        "--scenario",
        coinpoker_scenario,
        "--profile",
        profile,
        "--policy",
        policy_label,
        "--tierA-opponents",
        tier_a_opponents,
        "--tierP-opponents",
        tier_p_opponents,
        "--pool",
        pool_path,
        "--hands",
        str(full_hands),
        "--seeds",
        full_seeds_json,
        "--confirm-seeds",
        confirm_seeds_json,
        "--jobs",
        str(max(1, jobs_total)),
        "--pool-suite-jobs",
        str(pool_suite_jobs),
        "--pool-jobs-per-run",
        str(pool_jobs_per_run),
        "--br-suite-jobs",
        str(br_suite_jobs),
        "--br-jobs-per-run",
        str(br_jobs_per_run),
        "--br-from-pool",
        "--out-dir",
        str(coin_dir),
    ]
    if quiet:
        coin_cmd.append("--quiet")
    if isinstance(timeout_sec, (int, float)) and float(timeout_sec) > 0:
        coin_cmd.extend(["--timeout-sec", str(float(timeout_sec))])
    if isinstance(heartbeat_sec, (int, float)) and float(heartbeat_sec) > 0:
        coin_cmd.extend(["--heartbeat-sec", str(float(heartbeat_sec))])
    rc_coin = _run_cmd(coin_cmd, log_path=coin_dir / "run.log", timeout_sec=timeout_sec)

    coin_summary_path = coin_dir / "eval_full_summary.json"
    coin_summary = _json_load(coin_summary_path) if coin_summary_path.exists() else {}
    coin_metrics = (coin_summary.get("metrics") or {}) if isinstance(coin_summary, dict) else {}

    pool_summary_path = coin_dir / "pool_eval" / "pool_eval_summary.json"
    br_summary_path = coin_dir / "br_proxy" / "br_proxy_summary.json"
    pool_weighted = None
    br_worst = None
    if pool_summary_path.exists():
        pool_obj = _json_load(pool_summary_path)
        if isinstance(pool_obj, dict):
            w = pool_obj.get("weighted_mean_bb100")
            if isinstance(w, (int, float)):
                pool_weighted = float(w)
    if br_summary_path.exists():
        br_obj = _json_load(br_summary_path)
        if isinstance(br_obj, dict):
            worst = br_obj.get("worst_case")
            if isinstance(worst, dict):
                m = worst.get("mean_bb100")
                if isinstance(m, (int, float)):
                    br_worst = float(m)

    gg_dir = run_root / "gg_full"
    gg_jobs = _distribute_jobs(max(1, int(quick_jobs)), 2)
    gg_tasks = [
        ("tierA", tier_a_opponents, gg_jobs[0] if gg_jobs else max(1, int(quick_jobs))),
        ("tierP", tier_p_opponents, gg_jobs[1] if len(gg_jobs) >= 2 else max(1, int(quick_jobs))),
    ]
    gg_results: dict[str, tuple[int, float | None, float | None]] = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures: dict[Any, str] = {}
        for tier_name, opponents, tier_jobs in gg_tasks:
            fut = pool.submit(
                _run_scrimmage_batch,
                scenario=gg_scenario,
                profile=profile,
                policy=policy_label,
                opponents=opponents,
                hands=full_hands,
                seeds=full_seeds_json,
                jobs=tier_jobs,
                out_dir=gg_dir / tier_name,
                quiet=quiet,
                timeout_sec=timeout_sec,
                heartbeat_sec=heartbeat_sec,
            )
            futures[fut] = tier_name
        for fut in as_completed(futures):
            tier_name = futures[fut]
            gg_results[tier_name] = fut.result()

    rc_gg_a, gg_a_mean, gg_a_std = gg_results.get("tierA", (1, None, None))
    rc_gg_p, gg_p_mean, gg_p_std = gg_results.get("tierP", (1, None, None))

    coin_tier_a_batch = coin_dir / "tierA" / "scrimmage_batch.json"
    coin_tier_p_batch = coin_dir / "tierP" / "scrimmage_batch.json"
    gg_tier_a_batch = gg_dir / "tierA" / "scrimmage_batch.json"
    gg_tier_p_batch = gg_dir / "tierP" / "scrimmage_batch.json"

    coin_tier_a_stats = _seed_stats(_batch_bb100_values(coin_tier_a_batch))
    coin_tier_p_stats = _seed_stats(_batch_bb100_values(coin_tier_p_batch))
    gg_tier_a_stats = _seed_stats(_batch_bb100_values(gg_tier_a_batch))
    gg_tier_p_stats = _seed_stats(_batch_bb100_values(gg_tier_p_batch))
    tier_p_facing_turnriver = _aggregate_facing_turnriver_y(coin_tier_p_batch)

    tier_a_mean = coin_metrics.get("tierA_mean")
    tier_p_mean = coin_metrics.get("tierP_mean")
    tier_a_confirm = coin_metrics.get("tierA_confirm_mean")
    if not isinstance(tier_a_mean, (int, float)):
        tier_a_mean = coin_tier_a_stats.get("mean")
    if not isinstance(tier_p_mean, (int, float)):
        tier_p_mean = coin_tier_p_stats.get("mean")

    values = []
    for v in (tier_a_mean, tier_p_mean, gg_a_mean, gg_p_mean, pool_weighted, br_worst):
        if isinstance(v, (int, float)):
            values.append(float(v))
    full_score = _composite_gate_score(values)

    return {
        "policy": policy_label,
        "returncodes": {"coinpoker_eval_full": rc_coin, "gg_tierA": rc_gg_a, "gg_tierP": rc_gg_p},
        "coinpoker": {
            "out_dir": str(coin_dir),
            "summary_ref": f"path:{coin_summary_path.resolve()}" if coin_summary_path.exists() else None,
            "execution_plan": {
                "jobs_total": max(1, int(jobs_total)),
                "quick_jobs": int(quick_jobs),
                "gg_tier_jobs": gg_jobs,
                "pool_suite_count": int(pool_suite_count),
                "pool_suite_jobs": int(pool_suite_jobs),
                "pool_jobs_per_run": int(pool_jobs_per_run),
                "br_suite_jobs": int(br_suite_jobs),
                "br_jobs_per_run": int(br_jobs_per_run),
            },
            "tierA_mean": tier_a_mean,
            "tierA_std": coin_tier_a_stats.get("std"),
            "tierA_seed_min": coin_tier_a_stats.get("min"),
            "tierA_seed_max": coin_tier_a_stats.get("max"),
            "tierP_mean": tier_p_mean,
            "tierP_std": coin_tier_p_stats.get("std"),
            "tierP_seed_min": coin_tier_p_stats.get("min"),
            "tierP_seed_max": coin_tier_p_stats.get("max"),
            "tierA_confirm_mean": tier_a_confirm,
            "pool_weighted_mean": pool_weighted,
            "br_worst_mean": br_worst,
            "tierP_facingY_turnriver_worst_bb100": tier_p_facing_turnriver.get("worst_bb100"),
            "tierP_facingY_turnriver_worst_street": tier_p_facing_turnriver.get("worst_street"),
            "tierP_facingY_turnriver_worst_hands": tier_p_facing_turnriver.get("worst_hands"),
            "tierP_facingY_turnriver_total_hands": tier_p_facing_turnriver.get("total_hands"),
            "tierP_facingY_turnriver_high_support_guard": tier_p_facing_turnriver.get("high_support_guard"),
            "tierP_facingY_turnriver_by_street": tier_p_facing_turnriver.get("streets"),
        },
        "gg": {
            "out_dir": str(gg_dir),
            "tierA_mean": gg_a_mean,
            "tierA_std": gg_tier_a_stats.get("std", gg_a_std),
            "tierA_seed_min": gg_tier_a_stats.get("min"),
            "tierA_seed_max": gg_tier_a_stats.get("max"),
            "tierP_mean": gg_p_mean,
            "tierP_std": gg_tier_p_stats.get("std", gg_p_std),
            "tierP_seed_min": gg_tier_p_stats.get("min"),
            "tierP_seed_max": gg_tier_p_stats.get("max"),
        },
        "score": full_score,
    }


def _passes_no_regression(candidate: dict[str, Any], baseline: dict[str, Any], tolerance: float) -> bool:
    c = candidate.get("coinpoker") or {}
    b = baseline.get("coinpoker") or {}
    cg = candidate.get("gg") or {}
    bg = baseline.get("gg") or {}
    pairs = [
        (c.get("tierA_mean"), b.get("tierA_mean")),
        (c.get("tierP_mean"), b.get("tierP_mean")),
        (c.get("pool_weighted_mean"), b.get("pool_weighted_mean")),
        (c.get("br_worst_mean"), b.get("br_worst_mean")),
        (cg.get("tierA_mean"), bg.get("tierA_mean")),
        (cg.get("tierP_mean"), bg.get("tierP_mean")),
    ]
    for cur, base in pairs:
        if isinstance(cur, (int, float)) and isinstance(base, (int, float)):
            if float(cur) < float(base) - tolerance:
                return False
    return True


def _target_eval(
    metrics: dict[str, Any],
    target_gates: dict[str, float],
    robust_gates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    passed_all = True
    for gate_key, metric_path in TARGET_GATE_TO_METRIC_PATH:
        row = _eval_gate(
            gate_key=gate_key,
            metric_path=metric_path,
            threshold=float(target_gates[gate_key]),
            op="gte",
            metrics=metrics,
            source="target_gates",
        )
        if not bool(row.get("pass")):
            passed_all = False
        rows.append(row)
    for row_cfg in robust_gates or []:
        if not isinstance(row_cfg, dict):
            continue
        row = _eval_gate(
            gate_key=str(row_cfg.get("gate_key")),
            metric_path=str(row_cfg.get("metric_path")),
            threshold=float(row_cfg.get("threshold")),
            op=str(row_cfg.get("op", "gte")).lower(),
            metrics=metrics,
            source="robust_gates",
        )
        if not bool(row.get("pass")):
            passed_all = False
        rows.append(row)
    return {"met": bool(passed_all), "gates": rows}


def _weakness_support_for_metric(metrics: dict[str, Any], metric_path: str) -> int | None:
    coin = metrics.get("coinpoker")
    if not isinstance(coin, dict):
        return None
    if metric_path == "coinpoker.tierP_facingY_turnriver_worst_bb100":
        n = _as_int(coin.get("tierP_facingY_turnriver_worst_hands"))
        return int(n) if isinstance(n, int) and n > 0 else None
    return None


def _rank_weaknesses(target_eval: dict[str, Any], *, metrics: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = target_eval.get("gates")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    metrics_obj = metrics if isinstance(metrics, dict) else {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        metric_path = row.get("metric_path")
        gap = row.get("gap_bb100")
        value = row.get("value_bb100")
        threshold = row.get("threshold_bb100")
        if not isinstance(metric_path, str):
            continue
        if not isinstance(gap, (int, float)):
            continue
        if float(gap) >= 0.0:
            continue
        support_n = _weakness_support_for_metric(metrics_obj, metric_path)
        support_conf = 1.0
        if isinstance(support_n, int):
            support_conf = max(0.25, min(1.0, math.sqrt(float(support_n) / 80.0)))
        out.append(
            {
                "metric_path": metric_path,
                "value_bb100": float(value) if isinstance(value, (int, float)) else None,
                "threshold_bb100": float(threshold) if isinstance(threshold, (int, float)) else None,
                "gap_bb100": float(gap),
                "support_n": int(support_n) if isinstance(support_n, int) else None,
                "support_confidence": float(support_conf),
                "severity": abs(float(gap)) * float(support_conf),
            }
        )
    out.sort(key=lambda x: x["severity"], reverse=True)
    return out


def _derive_next_hypothesis(weaknesses: list[dict[str, Any]]) -> dict[str, Any]:
    if not weaknesses:
        return {
            "focus_metric": None,
            "reason": "all target gates passing; switch to stability hardening",
            "suggested_knobs": [],
            "suggested_mechanisms": [],
            "alternate_focus_metrics": [],
        }
    focus_metric = weaknesses[0]["metric_path"]
    top_metrics: list[str] = []
    for row in weaknesses:
        metric = row.get("metric_path")
        if isinstance(metric, str) and metric not in top_metrics:
            top_metrics.append(metric)
        if len(top_metrics) >= 3:
            break
    knob_pairs = FOCUS_METRIC_TO_KNOBS.get(str(focus_metric), ())
    suggested_knobs = [k for k, _ in knob_pairs]
    suggested_mechanisms = [m for m in FOCUS_METRIC_TO_MECHANISMS.get(str(focus_metric), ())]
    return {
        "focus_metric": focus_metric,
        "reason": f"largest target gap on {focus_metric}",
        "suggested_knobs": suggested_knobs,
        "suggested_mechanisms": suggested_mechanisms,
        "alternate_focus_metrics": [m for m in top_metrics if m != focus_metric],
        "weakness_top_metrics": top_metrics,
    }


def _target_met(
    metrics: dict[str, Any],
    target_gates: dict[str, float],
    robust_gates: list[dict[str, Any]] | None = None,
) -> bool:
    return bool(_target_eval(metrics, target_gates, robust_gates).get("met", False))


def _load_next_action(action_path: Path, *, cycle: int) -> tuple[dict[str, Any] | None, str]:
    if not action_path.exists():
        return None, "absent"
    try:
        obj = _json_load(action_path)
    except Exception:
        return None, "invalid_json"
    if not isinstance(obj, dict):
        return None, "invalid_payload"
    min_cycle = _as_int(obj.get("min_cycle"))
    if isinstance(min_cycle, int) and cycle < min_cycle:
        return None, "future_cycle"
    max_cycle = _as_int(obj.get("max_cycle"))
    if isinstance(max_cycle, int) and cycle > max_cycle:
        return None, "expired_cycle"
    return obj, "ready"


def _path_from_ref(value: Any) -> Path | None:
    if not isinstance(value, str):
        return None
    ref = value.strip()
    if not ref:
        return None
    if ref.startswith("path:"):
        ref = ref.removeprefix("path:")
    if not ref:
        return None
    return Path(ref)


def _mechanism_from_candidate_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate_name = value.strip()
    if not candidate_name:
        return None
    if candidate_name in MECHANISM_LIBRARY:
        return candidate_name
    parts = [part for part in candidate_name.split("_") if part]
    if len(parts) < 3:
        return None
    mechanism = "_".join(parts[2:])
    if mechanism in MECHANISM_LIBRARY:
        return mechanism
    return None


def _preferred_fallback_mechanism_from_review(review_ref: Any) -> str | None:
    review_path = _path_from_ref(review_ref)
    if not isinstance(review_path, Path) or not review_path.exists():
        return None
    try:
        review_obj = _json_load(review_path)
    except Exception:
        return None
    if not isinstance(review_obj, dict):
        return None
    quick_gate = review_obj.get("quick_gate")
    if not isinstance(quick_gate, dict):
        return None

    candidate_names: list[Any] = []
    selected_candidate = quick_gate.get("selected_full_eval_candidate")
    if isinstance(selected_candidate, dict):
        candidate_names.append(selected_candidate.get("name"))
    forced_probe = quick_gate.get("forced_probe")
    if isinstance(forced_probe, dict):
        candidate_names.append(forced_probe.get("candidate_name"))
    for name in candidate_names:
        mechanism = _mechanism_from_candidate_name(name)
        if isinstance(mechanism, str):
            return mechanism
    return None


def _fallback_action_plan_for_missing_ticket(
    *,
    cycle: int,
    no_improve_streak: int,
    next_hypothesis: dict[str, Any] | None,
    recent_reasons: list[str] | None,
    review_ref: Any = None,
) -> dict[str, Any] | None:
    streak = int(no_improve_streak)
    trailing_deadlock = _trailing_deadlock_count(recent_reasons if isinstance(recent_reasons, list) else [])
    recent_reason_set = {row for row in (recent_reasons or []) if isinstance(row, str)}
    # Trigger fallback earlier (>=1) to avoid repeated worker stalls on
    # transient/missing action tickets while still requiring observable stagnation.
    if streak < 1 and trailing_deadlock < 1:
        return None
    hypothesis = next_hypothesis if isinstance(next_hypothesis, dict) else {}
    focus_metric = hypothesis.get("focus_metric")
    if not isinstance(focus_metric, str) or not focus_metric:
        focus_metric = FOCUS_SUPPORT_FOCUS_METRIC
    if not isinstance(focus_metric, str) or not focus_metric:
        return None

    mechanism_names: list[str] = []
    preferred_mechanism = _preferred_fallback_mechanism_from_review(review_ref)
    if isinstance(preferred_mechanism, str):
        mechanism_names.append(preferred_mechanism)
    suggested = hypothesis.get("suggested_mechanisms")
    if isinstance(suggested, list):
        for row in suggested:
            if isinstance(row, str) and row in MECHANISM_LIBRARY and row not in mechanism_names:
                mechanism_names.append(row)
            if len(mechanism_names) >= 2:
                break
    if not mechanism_names:
        for row in FOCUS_METRIC_TO_MECHANISMS.get(focus_metric, ()):
            if isinstance(row, str) and row in MECHANISM_LIBRARY and row not in mechanism_names:
                mechanism_names.append(row)
            if len(mechanism_names) >= 2:
                break
    if not mechanism_names:
        return None

    robustness_recovery = bool(
        ("full_gate_fail" in recent_reason_set) and (streak >= 2 or trailing_deadlock >= 1)
    )
    primary_scale = 1.0
    if trailing_deadlock >= 5 or streak >= 20:
        primary_scale = 1.55
    elif trailing_deadlock >= 3 or streak >= 12:
        primary_scale = 1.35

    primary_reason = "auto_missing_action_fallback_primary"
    if isinstance(preferred_mechanism, str) and mechanism_names and mechanism_names[0] == preferred_mechanism:
        primary_reason = "auto_missing_action_fallback_review_probe"

    companion_mechanism: str | None = mechanism_names[1] if len(mechanism_names) >= 2 else None
    companion_reason = "auto_missing_action_fallback_companion"
    if robustness_recovery and mechanism_names:
        for row in ("counter_aggression_stability", "high_price_turn_river_hardening"):
            if isinstance(row, str) and row in MECHANISM_LIBRARY and row != mechanism_names[0]:
                companion_mechanism = row
                companion_reason = "auto_missing_action_fallback_robustness_companion"
                break

    mechanism_plan: list[dict[str, Any]] = [
        {
            "mechanism": mechanism_names[0],
            "scale": float(primary_scale),
            "reason": primary_reason,
        }
    ]
    if isinstance(companion_mechanism, str) and companion_mechanism != mechanism_names[0]:
        companion_scale = float(max(0.75, primary_scale * 0.75))
        if robustness_recovery:
            companion_scale = float(max(companion_scale, 0.95))
        mechanism_plan.append(
            {
                "mechanism": companion_mechanism,
                "scale": companion_scale,
                "reason": companion_reason,
            }
        )

    behavior_hint = 0.02
    effective_streak = max(streak, trailing_deadlock)
    if effective_streak >= 20:
        behavior_hint = 0.008
    elif effective_streak >= 8:
        behavior_hint = 0.012

    return {
        "focus_metric": focus_metric,
        "mechanism_priority_mode": "prefer",
        "mechanism_plan": mechanism_plan,
        "knob_plan": [],
        "quick_gate_hints": {
            "focus_support_min_hands": 12,
            "focus_support_min_hits": 1,
            "behavior_delta_min": float(behavior_hint),
        },
        "_auto_generated": True,
        "_auto_generated_reason": "missing_action_with_stagnation",
        "_auto_generated_cycle": int(cycle),
        "_auto_generated_deadlock_streak": int(trailing_deadlock),
        "_auto_generated_robustness_recovery": bool(robustness_recovery),
    }


def _consume_next_action(action_path: Path, *, cycle_root: Path, cycle: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    action_obj, status = _load_next_action(action_path, cycle=cycle)
    meta: dict[str, Any] = {
        "path": str(action_path),
        "status": status,
        "consumed": False,
        "consumed_ref": None,
    }
    if not isinstance(action_obj, dict):
        return None, meta
    consumed_path = cycle_root / "input_next_action.json"
    _json_dump(consumed_path, action_obj)
    meta["consumed"] = True
    meta["consumed_ref"] = f"path:{consumed_path.resolve()}"
    try:
        action_path.unlink()
    except FileNotFoundError:
        pass
    return action_obj, meta


def _requires_focus_support_guard(focus_metric: str | None) -> bool:
    return isinstance(focus_metric, str) and focus_metric == FOCUS_SUPPORT_FOCUS_METRIC


def _focus_support_from_quick(quick: dict[str, Any]) -> dict[str, int]:
    probe = quick.get("focus_probe") if isinstance(quick, dict) else None
    if not isinstance(probe, dict):
        return {"hands": 0, "hits": 0}
    hands = _as_int(probe.get("tierP_facingY_turnriver_total_hands"))
    hits = _as_int(probe.get("high_price_low_spr_hits"))
    return {"hands": int(hands) if isinstance(hands, int) else 0, "hits": int(hits) if isinstance(hits, int) else 0}


def _targeted_focus_summary_from_quick(quick: dict[str, Any]) -> dict[str, Any] | None:
    probe = quick.get("focus_probe") if isinstance(quick, dict) else None
    if not isinstance(probe, dict):
        return None
    targeted = probe.get("targeted_focus_set")
    if not isinstance(targeted, dict):
        return None
    support_before_raw = targeted.get("support_before")
    support_after_raw = targeted.get("support_after")
    support_before = support_before_raw if isinstance(support_before_raw, dict) else {}
    support_after = support_after_raw if isinstance(support_after_raw, dict) else {}
    hands_before = int(_as_int(support_before.get("hands")) or 0)
    hits_before = int(_as_int(support_before.get("hits")) or 0)
    hands_after = int(_as_int(support_after.get("hands")) or 0)
    hits_after = int(_as_int(support_after.get("hits")) or 0)
    out_dir = targeted.get("out_dir")
    return {
        "enabled": bool(targeted.get("enabled")),
        "attempted": bool(targeted.get("attempted")),
        "merged": bool(targeted.get("merged")),
        "returncode": _as_int(targeted.get("returncode")),
        "hands": _as_int(targeted.get("hands")),
        "jobs": _as_int(targeted.get("jobs")),
        "support_before": {"hands": hands_before, "hits": hits_before},
        "support_after": {"hands": hands_after, "hits": hits_after},
        "support_delta": {
            "hands": int(hands_after - hands_before),
            "hits": int(hits_after - hits_before),
        },
        "out_dir": out_dir if isinstance(out_dir, str) else None,
    }


def _wilson_lower_bound(*, success: int, total: int, z: float) -> float:
    n = int(total)
    k = int(success)
    if n <= 0:
        return 0.0
    p = max(0.0, min(1.0, float(k) / float(n)))
    z2 = float(z) * float(z)
    denom = 1.0 + z2 / float(n)
    center = p + z2 / (2.0 * float(n))
    margin = float(z) * math.sqrt((p * (1.0 - p) + z2 / (4.0 * float(n))) / float(n))
    return max(0.0, min(1.0, (center - margin) / denom))


def _focus_support_eval(*, support: dict[str, int], min_hands: int, min_hits: int) -> dict[str, Any]:
    hands = max(0, int(support.get("hands", 0)))
    hits = max(0, int(support.get("hits", 0)))
    hard_min_hands = max(1, int(min_hands))
    hard_min_hits = max(1, int(min_hits))
    hard_pass = bool(hands >= hard_min_hands and hits >= hard_min_hits)
    observed_rate = (float(hits) / float(hands)) if hands > 0 else 0.0
    base_target_rate = float(hard_min_hits) / float(max(1, hard_min_hands))
    adaptive_target_rate = base_target_rate * float(DEFAULT_FOCUS_SUPPORT_ADAPTIVE_SCALE)
    adaptive_min_hands = max(
        int(DEFAULT_FOCUS_SUPPORT_ADAPTIVE_MIN_HANDS_ABS),
        int(math.ceil(float(hard_min_hands) * float(DEFAULT_FOCUS_SUPPORT_ADAPTIVE_MIN_HANDS_RATIO))),
    )
    wilson_lb = _wilson_lower_bound(success=hits, total=hands, z=float(DEFAULT_FOCUS_SUPPORT_ADAPTIVE_Z))
    adaptive_pass = bool(hands >= adaptive_min_hands and wilson_lb >= adaptive_target_rate)
    return {
        "hands": int(hands),
        "hits": int(hits),
        "hard_min_hands": int(hard_min_hands),
        "hard_min_hits": int(hard_min_hits),
        "hard_pass": bool(hard_pass),
        "adaptive_pass": bool(adaptive_pass),
        "adaptive_min_hands": int(adaptive_min_hands),
        "base_target_rate": float(base_target_rate),
        "adaptive_target_rate": float(adaptive_target_rate),
        "observed_rate": float(observed_rate),
        "wilson_lb": float(wilson_lb),
        "pass": bool(hard_pass or adaptive_pass),
    }


def _focus_support_pass(*, support: dict[str, int], min_hands: int, min_hits: int) -> bool:
    return bool(
        _focus_support_eval(
            support=support,
            min_hands=min_hands,
            min_hits=min_hits,
        ).get("pass")
    )


def _apply_quick_gate_hints(
    *,
    base_focus_support_min_hands: int,
    base_focus_support_min_hits: int,
    base_behavior_delta_min: float,
    base_quick_regression_tolerance: float,
    hints: dict[str, Any] | None,
) -> tuple[int, int, float, float, dict[str, Any]]:
    base_hands = max(1, int(base_focus_support_min_hands))
    base_hits = max(1, int(base_focus_support_min_hits))
    base_hits = min(base_hits, base_hands)
    base_behavior = max(0.0, float(base_behavior_delta_min))
    base_regression = max(0.0, float(base_quick_regression_tolerance))
    effective_hands = int(base_hands)
    effective_hits = int(base_hits)
    effective_behavior = float(base_behavior)
    effective_regression = float(base_regression)
    quick_regression_hint_cap = float(base_regression + 0.60)
    diag: dict[str, Any] = {
        "policy": "bounded_relaxation_only_v1",
        "base": {
            "focus_support_min_hands": int(base_hands),
            "focus_support_min_hits": int(base_hits),
            "behavior_delta_min": float(base_behavior),
            "quick_regression_tolerance": float(base_regression),
        },
        "requested": None,
        "effective": {
            "focus_support_min_hands": int(effective_hands),
            "focus_support_min_hits": int(effective_hits),
            "behavior_delta_min": float(effective_behavior),
            "quick_regression_tolerance": float(effective_regression),
        },
        "applied": {},
        "ignored": {},
    }
    if not isinstance(hints, dict):
        return (
            int(effective_hands),
            int(effective_hits),
            float(effective_behavior),
            float(effective_regression),
            diag,
        )
    requested_hands = _as_int(hints.get("focus_support_min_hands"))
    requested_hits = _as_int(hints.get("focus_support_min_hits"))
    requested_behavior = _as_float(hints.get("behavior_delta_min"))
    requested_regression = _as_float(hints.get("quick_regression_tolerance"))
    diag["requested"] = {
        "focus_support_min_hands": requested_hands,
        "focus_support_min_hits": requested_hits,
        "behavior_delta_min": requested_behavior,
        "quick_regression_tolerance": requested_regression,
    }

    if isinstance(requested_hands, int):
        if requested_hands <= 0:
            diag["ignored"]["focus_support_min_hands"] = "non_positive"
        else:
            clamped = max(1, min(base_hands, int(requested_hands)))
            if clamped != int(effective_hands):
                diag["applied"]["focus_support_min_hands"] = {
                    "requested": int(requested_hands),
                    "effective": int(clamped),
                }
                effective_hands = int(clamped)
            elif int(requested_hands) != int(base_hands):
                diag["ignored"]["focus_support_min_hands"] = "tightening_blocked_or_noop"

    if isinstance(requested_hits, int):
        if requested_hits <= 0:
            diag["ignored"]["focus_support_min_hits"] = "non_positive"
        else:
            hits_upper = max(1, min(base_hits, effective_hands))
            clamped = max(1, min(hits_upper, int(requested_hits)))
            if clamped != int(effective_hits):
                diag["applied"]["focus_support_min_hits"] = {
                    "requested": int(requested_hits),
                    "effective": int(clamped),
                }
                effective_hits = int(clamped)
            elif int(requested_hits) != int(base_hits):
                diag["ignored"]["focus_support_min_hits"] = "tightening_blocked_or_noop"
    if effective_hits > effective_hands:
        diag["applied"]["focus_support_min_hits_auto"] = {
            "requested": int(effective_hits),
            "effective": int(effective_hands),
            "reason": "hits_cannot_exceed_hands",
        }
        effective_hits = int(effective_hands)

    if isinstance(requested_behavior, float):
        if requested_behavior < 0.0:
            diag["ignored"]["behavior_delta_min"] = "negative"
        else:
            clamped_behavior = max(0.0, min(base_behavior, float(requested_behavior)))
            if abs(clamped_behavior - float(effective_behavior)) > 1e-12:
                diag["applied"]["behavior_delta_min"] = {
                    "requested": float(requested_behavior),
                    "effective": float(clamped_behavior),
                }
                effective_behavior = float(clamped_behavior)
            elif abs(float(requested_behavior) - float(base_behavior)) > 1e-12:
                diag["ignored"]["behavior_delta_min"] = "tightening_blocked_or_noop"

    if isinstance(requested_regression, float):
        if requested_regression < 0.0:
            diag["ignored"]["quick_regression_tolerance"] = "negative"
        else:
            clamped_regression = min(
                float(quick_regression_hint_cap),
                max(float(base_regression), float(requested_regression)),
            )
            if abs(clamped_regression - float(effective_regression)) > 1e-12:
                diag["applied"]["quick_regression_tolerance"] = {
                    "requested": float(requested_regression),
                    "effective": float(clamped_regression),
                }
                effective_regression = float(clamped_regression)
            elif abs(float(requested_regression) - float(base_regression)) > 1e-12:
                diag["ignored"]["quick_regression_tolerance"] = "tightening_blocked_or_noop"

    diag["effective"] = {
        "focus_support_min_hands": int(effective_hands),
        "focus_support_min_hits": int(effective_hits),
        "behavior_delta_min": float(effective_behavior),
        "quick_regression_tolerance": float(effective_regression),
    }
    diag["caps"] = {
        "focus_support_min_hands_max": int(base_hands),
        "focus_support_min_hits_max": int(base_hits),
        "behavior_delta_min_max": float(base_behavior),
        "quick_regression_tolerance_min": float(base_regression),
        "quick_regression_tolerance_max": float(quick_regression_hint_cap),
    }
    return (
        int(effective_hands),
        int(effective_hits),
        float(effective_behavior),
        float(effective_regression),
        diag,
    )


def _ante_integrity_from_quick(quick: dict[str, Any]) -> dict[str, Any]:
    integ = quick.get("ante_integrity") if isinstance(quick, dict) else None
    if not isinstance(integ, dict):
        return {
            "pass": False,
            "reports": 0,
            "mismatch_hands_total": 0,
            "mismatch_max_bb": None,
            "ante_gap_abs_max_bb": None,
        }
    return {
        "pass": bool(integ.get("pass")),
        "reports": int(_as_int(integ.get("reports")) or 0),
        "mismatch_hands_total": int(_as_int(integ.get("mismatch_hands_total")) or 0),
        "mismatch_max_bb": _as_float(integ.get("mismatch_max_bb")),
        "ante_gap_abs_max_bb": _as_float(integ.get("ante_gap_abs_max_bb")),
    }


def _runtime_health_from_quick(quick: dict[str, Any]) -> dict[str, Any]:
    metrics = quick.get("metrics") if isinstance(quick, dict) else None
    if not isinstance(metrics, dict):
        return {
            "pass": False,
            "task_count": 0,
            "failed_task_count": 0,
            "failure_ratio": 1.0,
            "failed_tasks": [],
        }
    task_count = 0
    failed_rows: list[dict[str, Any]] = []
    for metric_key, metric_row in metrics.items():
        if not isinstance(metric_key, str) or not isinstance(metric_row, dict):
            continue
        rc = _as_int(metric_row.get("returncode"))
        if not isinstance(rc, int):
            continue
        task_count += 1
        if int(rc) != 0:
            failed_rows.append({"metric": metric_key, "returncode": int(rc)})
    failed_task_count = len(failed_rows)
    failure_ratio = (float(failed_task_count) / float(task_count)) if task_count > 0 else 1.0
    return {
        "pass": bool(task_count > 0 and failed_task_count == 0),
        "task_count": int(task_count),
        "failed_task_count": int(failed_task_count),
        "failure_ratio": float(failure_ratio),
        "failed_tasks": failed_rows,
    }


def _quick_metric_means(quick: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    metrics = quick.get("metrics") if isinstance(quick, dict) else None
    if not isinstance(metrics, dict):
        return out
    for key, row in metrics.items():
        if not isinstance(key, str) or not isinstance(row, dict):
            continue
        mean = _as_float(row.get("mean_bb100"))
        if isinstance(mean, float):
            out[key] = float(mean)
    return out


def _quick_regression_guard(
    *,
    active_quick: dict[str, Any],
    trial_quick: dict[str, Any],
    tolerance: float,
) -> tuple[bool, list[dict[str, float | str]]]:
    margin = max(0.0, float(tolerance))
    active_means = _quick_metric_means(active_quick)
    trial_means = _quick_metric_means(trial_quick)
    regressions: list[dict[str, float | str]] = []
    for metric_key, base in active_means.items():
        cur = trial_means.get(metric_key)
        if not isinstance(cur, float):
            continue
        delta = float(cur) - float(base)
        if delta < -margin:
            regressions.append(
                {
                    "metric": metric_key,
                    "active_mean_bb100": float(base),
                    "trial_mean_bb100": float(cur),
                    "delta_bb100": float(delta),
                }
            )
    return (len(regressions) == 0), regressions


def _high_price_mix_snapshot(quick: dict[str, Any]) -> dict[str, float | int | None]:
    probe = quick.get("focus_probe") if isinstance(quick, dict) else None
    mix = probe.get("high_price_action_mix") if isinstance(probe, dict) else None
    turn_call = _as_float(mix.get("turn_high_price_call_rate")) if isinstance(mix, dict) else None
    river_call = _as_float(mix.get("river_high_price_call_rate")) if isinstance(mix, dict) else None
    turn_fold = _as_float(mix.get("turn_high_price_fold_rate")) if isinstance(mix, dict) else None
    river_fold = _as_float(mix.get("river_high_price_fold_rate")) if isinstance(mix, dict) else None
    call_vals = [v for v in (turn_call, river_call) if isinstance(v, float)]
    fold_vals = [v for v in (turn_fold, river_fold) if isinstance(v, float)]
    low_spr_hits = _as_int(probe.get("high_price_low_spr_hits")) if isinstance(probe, dict) else None
    return {
        "call_peak": (max(call_vals) if call_vals else None),
        "fold_floor": (min(fold_vals) if fold_vals else None),
        "low_spr_hits": (int(low_spr_hits) if isinstance(low_spr_hits, int) else 0),
        "turn_call_rate": turn_call,
        "river_call_rate": river_call,
        "turn_fold_rate": turn_fold,
        "river_fold_rate": river_fold,
    }


def _adaptive_focus_hardening_scale(active_quick: dict[str, Any]) -> tuple[float, dict[str, float | int | None]]:
    snapshot = _high_price_mix_snapshot(active_quick)
    call_peak = _as_float(snapshot.get("call_peak"))
    fold_floor = _as_float(snapshot.get("fold_floor"))
    low_spr_hits = int(snapshot.get("low_spr_hits", 0) or 0)

    evidence = 0
    scale = 1.0
    if isinstance(call_peak, float):
        if call_peak >= 0.56:
            scale += 0.90
            evidence += 2
        elif call_peak >= 0.50:
            scale += 0.50
            evidence += 1
        elif call_peak >= 0.46:
            scale += 0.25
            evidence += 1
    if isinstance(fold_floor, float):
        if fold_floor <= 0.16:
            scale += 0.70
            evidence += 2
        elif fold_floor <= 0.20:
            scale += 0.40
            evidence += 1
        elif fold_floor <= 0.24:
            scale += 0.20
            evidence += 1
    if low_spr_hits >= 8:
        scale += 0.60
        evidence += 2
    elif low_spr_hits >= 3:
        scale += 0.30
        evidence += 1

    if evidence <= 0:
        return 0.0, snapshot
    return min(2.8, max(0.8, float(scale))), snapshot


def _behavior_vector_from_quick(quick: dict[str, Any]) -> list[float] | None:
    probe = quick.get("focus_probe") if isinstance(quick, dict) else None
    if not isinstance(probe, dict):
        return None
    mix = probe.get("high_price_action_mix")
    if not isinstance(mix, dict):
        return None
    keys = (
        "turn_high_price_fold_rate",
        "turn_high_price_call_rate",
        "turn_high_price_raise_rate",
        "river_high_price_fold_rate",
        "river_high_price_call_rate",
        "river_high_price_raise_rate",
    )
    vals: list[float] = []
    for key in keys:
        v = _as_float(mix.get(key))
        if not isinstance(v, float):
            return None
        vals.append(v)
    return vals


def _behavior_delta(active_quick: dict[str, Any], trial_quick: dict[str, Any]) -> float | None:
    va = _behavior_vector_from_quick(active_quick)
    vb = _behavior_vector_from_quick(trial_quick)
    if not isinstance(va, list) or not isinstance(vb, list) or len(va) != len(vb) or not va:
        return None
    diff = sum(abs(a - b) for a, b in zip(va, vb)) / float(len(va))
    return float(diff)


def _effective_behavior_delta_min(*, base_min: float, no_improve_streak: int) -> tuple[float, bool]:
    base = max(0.0, float(base_min))
    streak = int(no_improve_streak)
    if base <= 0.0:
        return base, False
    if streak < 1:
        return base, False
    # Start relaxing after the first no-improve cycle. This avoids repeating
    # quick_gate_no_behavior_delta with near-identical scores while still
    # keeping a non-zero behavior guard.
    if streak >= 20:
        ratio = 0.20
    elif streak >= 8:
        ratio = 0.30
    elif streak >= 2:
        ratio = 0.40
    else:
        ratio = 0.20
    effective = max(min(base, 0.003), base * ratio)
    return float(effective), bool(effective < base)


def _trailing_deadlock_count(recent_reasons: list[str] | None) -> int:
    if not isinstance(recent_reasons, list):
        return 0
    deadlock_reasons = {
        "quick_gate_no_behavior_delta",
        "quick_gate_no_improvement",
        "quick_gate_no_eligible_candidate",
        "quick_gate_quick_regression",
        "quick_gate_low_focus_support",
        "quick_gate_spot_no_effect",
        "quick_gate_ranked_only_blocked",
        "llm_action_gate_fail",
    }
    trailing_deadlock = 0
    for reason in reversed(recent_reasons):
        if isinstance(reason, str) and reason in deadlock_reasons:
            trailing_deadlock += 1
        else:
            break
    return int(trailing_deadlock)


def _trailing_reason_streak(recent_reasons: list[str] | None, *, target_reason: str) -> int:
    if not isinstance(recent_reasons, list) or not isinstance(target_reason, str) or not target_reason:
        return 0
    streak = 0
    for reason in reversed(recent_reasons):
        if reason == target_reason:
            streak += 1
        else:
            break
    return int(streak)


def _llm_review_policy(
    *,
    base_require_llm_action_ticket: bool,
    recent_reasons: list[str] | None,
    no_improve_streak: int,
    full_gate_fail_streak: int,
    min_no_improve_streak: int,
    fail_open: bool,
) -> dict[str, Any]:
    trailing_full_gate_fail_streak = _trailing_reason_streak(recent_reasons, target_reason="full_gate_fail")
    recent_full_gate_fail_count = 0
    if isinstance(recent_reasons, list):
        recent_full_gate_fail_count = sum(1 for reason in recent_reasons[-4:] if reason == "full_gate_fail")

    threshold = max(0, int(full_gate_fail_streak))
    min_streak = max(0, int(min_no_improve_streak))
    base_required = bool(base_require_llm_action_ticket)
    dynamic_triggered = bool(
        (not base_required)
        and threshold > 0
        and trailing_full_gate_fail_streak >= threshold
        and int(no_improve_streak) >= min_streak
    )
    effective_required = bool(base_required or dynamic_triggered)
    fail_open_enabled = bool(fail_open and dynamic_triggered and not base_required)
    trigger_reason: str | None = None
    if base_required:
        trigger_reason = "explicit_flag"
    elif dynamic_triggered:
        trigger_reason = "full_gate_fail_streak"

    return {
        "base_required": bool(base_required),
        "effective_required": bool(effective_required),
        "dynamic_triggered": bool(dynamic_triggered),
        "reason": trigger_reason,
        "thresholds": {
            "full_gate_fail_streak": int(threshold),
            "min_no_improve_streak": int(min_streak),
        },
        "recent": {
            "trailing_full_gate_fail_streak": int(trailing_full_gate_fail_streak),
            "recent_full_gate_fail_count": int(recent_full_gate_fail_count),
            "no_improve_streak": int(no_improve_streak),
        },
        "fail_open_enabled": bool(fail_open_enabled),
    }


def _behavior_bonus_for_stagnation(*, behavior_delta: float | None, no_improve_streak: int) -> float:
    if not isinstance(behavior_delta, float) or behavior_delta <= 0.0:
        return 0.0
    streak = int(no_improve_streak)
    if streak < 2:
        return 0.0
    scale = 80.0
    if streak >= 20:
        scale = 300.0
    elif streak >= 16:
        scale = 220.0
    elif streak >= 8:
        scale = 150.0
    bonus = float(behavior_delta) * float(scale)
    return max(0.0, min(2.0, bonus))


def _candidate_behavior_delta_min(
    *,
    behavior_delta_min_effective: float,
    candidate_kind: str | None,
    mechanism_policy: dict[str, Any] | None,
) -> tuple[float, float]:
    base = max(0.0, float(behavior_delta_min_effective))
    if base <= 0.0:
        return 0.0, 1.0
    if candidate_kind != "mechanism" or not isinstance(mechanism_policy, dict):
        return float(base), 1.0
    if not bool(mechanism_policy.get("prioritize")):
        return float(base), 1.0

    trailing_deadlock = _as_int(mechanism_policy.get("trailing_deadlock_count")) or 0
    no_improve_streak = _as_int(mechanism_policy.get("no_improve_streak")) or 0
    mechanism_only = bool(mechanism_policy.get("mechanism_only"))
    ratio = 0.80
    if mechanism_only or trailing_deadlock >= 3:
        ratio = 0.55
    elif trailing_deadlock >= 2:
        ratio = 0.60
    elif trailing_deadlock >= 1:
        ratio = 0.70
    # Under prolonged no-improve streaks, loosen mechanism behavior guard a bit
    # more so near-miss candidates can reach full gate; keep non-zero floor.
    if no_improve_streak >= 10 and trailing_deadlock >= 1:
        ratio = min(ratio, 0.45)
    if no_improve_streak >= 12 and mechanism_only:
        ratio = min(ratio, 0.40)
    adjusted = max(min(base, 0.003), float(base) * float(ratio))
    return float(adjusted), float(ratio)


def _effective_ranked_promotion_raw_floor_margin(
    *,
    base_margin: float,
    no_improve_streak: int,
    recent_reasons: list[str] | None,
    mechanism_policy: dict[str, Any] | None,
) -> tuple[float, bool]:
    margin = max(0.0, float(base_margin))
    streak = int(no_improve_streak)
    trailing_deadlock = _trailing_deadlock_count(recent_reasons)
    last_reason: str | None = None
    if isinstance(recent_reasons, list) and recent_reasons:
        last = recent_reasons[-1]
        if isinstance(last, str):
            last_reason = last

    # Repeated ranked-only blocks indicate ranking signal exists but raw score
    # sits just below floor; widen floor slightly so full gate can arbitrate.
    if last_reason == "quick_gate_ranked_only_blocked":
        margin = max(margin, 0.55)
        # Under prolonged mechanism-only stagnation, allow one extra step of
        # raw-floor slack so near-miss ranked winners can reach full gate.
        if (
            streak >= 12
            and isinstance(mechanism_policy, dict)
            and bool(mechanism_policy.get("mechanism_only"))
        ):
            margin = max(margin, 0.70)
    if trailing_deadlock >= 4:
        margin = max(margin, 0.60)
    elif trailing_deadlock >= 2:
        margin = max(margin, 0.45)

    if streak >= 16:
        margin = max(margin, 0.70)
    elif streak >= 8:
        margin = max(margin, 0.60)
    elif streak >= 4:
        margin = max(margin, 0.50)

    if isinstance(mechanism_policy, dict) and bool(mechanism_policy.get("mechanism_only")):
        margin = max(margin, 0.55)

    margin = min(0.80, margin)
    return float(margin), bool(margin > max(0.0, float(base_margin)))


def _effective_force_probe_raw_margin(
    *,
    base_margin: float,
    no_improve_streak: int,
    recent_reasons: list[str] | None,
) -> tuple[float, bool]:
    base = max(0.0, float(base_margin))
    margin = float(base)
    streak = int(no_improve_streak)
    trailing_deadlock = _trailing_deadlock_count(recent_reasons)
    last_reason: str | None = None
    if isinstance(recent_reasons, list) and recent_reasons:
        last = recent_reasons[-1]
        if isinstance(last, str):
            last_reason = last

    # When quick gate repeatedly stalls, widen forced-probe raw floor so full
    # gate can arbitrate mechanism candidates with behavior movement.
    if isinstance(last_reason, str) and last_reason in {"quick_gate_no_improvement", "full_gate_fail"}:
        margin = max(margin, 0.80)
    if trailing_deadlock >= 2:
        margin = max(margin, 0.95)
    if streak >= 12:
        margin = max(margin, 1.00)
    if streak >= 16:
        margin = max(margin, 1.20)
    if streak >= 20 and trailing_deadlock >= 1:
        margin = max(margin, 1.35)

    margin = min(1.50, margin)
    return float(margin), bool(margin > base)


def _effective_quick_min_delta(
    *,
    base_delta: float,
    no_improve_streak: int,
    recent_reasons: list[str] | None,
    mechanism_policy: dict[str, Any] | None,
) -> tuple[float, bool]:
    delta = max(0.0, float(base_delta))
    streak = int(no_improve_streak)
    trailing_deadlock = _trailing_deadlock_count(recent_reasons)
    last_reason: str | None = None
    if isinstance(recent_reasons, list) and recent_reasons:
        last = recent_reasons[-1]
        if isinstance(last, str):
            last_reason = last

    prioritize_mechanism = bool(isinstance(mechanism_policy, dict) and mechanism_policy.get("prioritize"))
    mechanism_only = bool(isinstance(mechanism_policy, dict) and mechanism_policy.get("mechanism_only"))

    # Under prolonged stagnation, allow smaller ranked deltas so quick gate can
    # promote mechanism candidates to full gate instead of repeating no-improve.
    if prioritize_mechanism and isinstance(last_reason, str) and last_reason in {
        "quick_gate_no_improvement",
        "quick_gate_ranked_only_blocked",
    }:
        delta = min(delta, 0.35)
    # If no-improve keeps repeating, widen the same-cycle promotion window so
    # full gate can arbitrate near-tie mechanism candidates instead of stalling.
    if prioritize_mechanism and last_reason == "quick_gate_no_improvement" and streak >= 4:
        delta = min(delta, 0.25)
    if prioritize_mechanism and trailing_deadlock >= 3:
        delta = min(delta, 0.30)
    if prioritize_mechanism and streak >= 8:
        delta = min(delta, 0.20)
    if prioritize_mechanism and (streak >= 12 or mechanism_only):
        delta = min(delta, 0.15)
    if streak >= 20:
        delta = min(delta, 0.10)

    if delta > 0.0:
        delta = max(0.05, delta)
    return float(delta), bool(delta < max(0.0, float(base_delta)))


def _effective_full_min_delta(
    *,
    base_delta: float,
    no_improve_streak: int,
    recent_reasons: list[str] | None,
    mechanism_policy: dict[str, Any] | None,
) -> tuple[float, bool]:
    delta = max(0.0, float(base_delta))
    streak = int(no_improve_streak)
    recent_full_gate_fails = 0
    last_reason: str | None = None
    if isinstance(recent_reasons, list):
        for reason in recent_reasons[-4:]:
            if reason == "full_gate_fail":
                recent_full_gate_fails += 1
        if recent_reasons:
            last = recent_reasons[-1]
            if isinstance(last, str):
                last_reason = last

    prioritize_mechanism = bool(isinstance(mechanism_policy, dict) and mechanism_policy.get("prioritize"))
    mechanism_only = bool(isinstance(mechanism_policy, dict) and mechanism_policy.get("mechanism_only"))

    # If quick gate keeps reaching full gate but promotion still fails, relax
    # only the full-score margin so robust/focus gates can arbitrate adoption.
    if prioritize_mechanism and last_reason == "full_gate_fail":
        delta = min(delta, max(0.06, float(base_delta) * 0.85))
    if prioritize_mechanism and recent_full_gate_fails >= 2:
        delta = min(delta, max(0.05, float(base_delta) * 0.70))
    if prioritize_mechanism and streak >= 12 and recent_full_gate_fails >= 2:
        delta = min(delta, max(0.04, float(base_delta) * 0.60))
    if mechanism_only and streak >= 16 and recent_full_gate_fails >= 3:
        delta = min(delta, max(0.03, float(base_delta) * 0.50))

    if delta > 0.0:
        delta = max(0.02, delta)
    return float(delta), bool(delta < max(0.0, float(base_delta)))


def _select_forced_probe_candidate(
    *,
    candidate_rows: list[dict[str, Any]],
    active_quick_score: float,
    no_improve_streak: int,
    trailing_deadlock: int,
    last_reason: str | None,
    quick_guard_enabled: bool,
    probe_streak: int,
    probe_deadlock: int,
    raw_margin: float,
) -> dict[str, Any] | None:
    if not isinstance(candidate_rows, list) or not candidate_rows:
        return None
    trigger = bool(
        int(no_improve_streak) >= int(probe_streak)
        or int(trailing_deadlock) >= int(probe_deadlock)
        or (
            isinstance(last_reason, str)
            and last_reason in {"quick_gate_no_behavior_delta", "quick_gate_ranked_only_blocked", "quick_gate_quick_regression"}
        )
    )
    if not trigger:
        return None

    if not math.isfinite(active_quick_score):
        active_quick_score = float("-inf")
    min_raw_score = float(active_quick_score) - max(0.0, float(raw_margin))
    allow_support_miss = bool(
        quick_guard_enabled
        and (
            int(no_improve_streak) >= int(probe_streak)
            or int(trailing_deadlock) >= int(probe_deadlock)
            or (
                isinstance(last_reason, str)
                and last_reason in {"quick_gate_low_focus_support", "quick_gate_spot_no_effect", "quick_gate_no_eligible_candidate"}
            )
        )
    )

    # Under repeated full-gate failures, prioritize candidates with observable
    # behavior movement so probe runs do not repeatedly spend budget on
    # near-identical candidates.
    prefer_behavior_pass = bool(
        quick_guard_enabled
        and isinstance(last_reason, str)
        and last_reason == "full_gate_fail"
        and int(no_improve_streak) >= int(probe_streak)
    )
    has_behavior_pass_candidate = False
    if prefer_behavior_pass:
        for row in candidate_rows:
            if not isinstance(row, dict):
                continue
            if not bool(row.get("runtime_pass")):
                continue
            if not bool(row.get("ante_integrity_pass")):
                continue
            if bool(row.get("spot_gate_applicable")) and not bool(row.get("spot_gate_pass")):
                continue
            if quick_guard_enabled and not bool(row.get("support_pass")) and not allow_support_miss:
                continue
            quick_score = _as_float(row.get("quick_score"))
            if not isinstance(quick_score, float) or not math.isfinite(quick_score):
                continue
            if quick_score < min_raw_score:
                continue
            if bool(row.get("behavior_pass")):
                has_behavior_pass_candidate = True
                break

    best_row: dict[str, Any] | None = None
    best_rank = float("-inf")
    for row in candidate_rows:
        if not isinstance(row, dict):
            continue
        if not bool(row.get("runtime_pass")):
            continue
        if not bool(row.get("ante_integrity_pass")):
            continue
        if bool(row.get("spot_gate_applicable")) and not bool(row.get("spot_gate_pass")):
            continue
        if quick_guard_enabled and not bool(row.get("support_pass")) and not allow_support_miss:
            continue
        quick_score = _as_float(row.get("quick_score"))
        if not isinstance(quick_score, float) or not math.isfinite(quick_score):
            continue
        if quick_score < min_raw_score:
            continue
        ranked_bonus = _as_float(row.get("quick_rank_behavior_bonus"))
        kind = row.get("kind")
        behavior_pass = bool(row.get("behavior_pass"))
        support_pass = bool(row.get("support_pass"))
        focus_delta = _as_float(row.get("focus_metric_delta"))
        support_hits_delta = _as_int(row.get("targeted_focus_support_hits_delta")) or 0
        support_hands_delta = _as_int(row.get("targeted_focus_support_hands_delta")) or 0
        if prefer_behavior_pass and has_behavior_pass_candidate and not behavior_pass:
            continue
        rank = float(quick_score)
        if isinstance(ranked_bonus, float) and math.isfinite(ranked_bonus):
            rank += 0.25 * max(0.0, float(ranked_bonus))
        if kind == "mechanism":
            rank += 0.35
        if behavior_pass:
            rank += 0.15
        if support_pass:
            rank += 0.10
        if isinstance(last_reason, str) and last_reason in {"quick_gate_low_focus_support", "quick_gate_spot_no_effect"}:
            if isinstance(focus_delta, float) and math.isfinite(focus_delta):
                rank += float(focus_delta) * 0.50
            rank += float(support_hits_delta) * 0.20
            rank += float(support_hands_delta) * 0.02
        if rank > best_rank:
            best_rank = rank
            best_row = row
    return best_row


def _select_targeted_shadow_candidate(
    *,
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    best_row: dict[str, Any] | None = None
    best_rank: tuple[float, ...] | None = None
    for row in candidate_rows:
        if not isinstance(row, dict):
            continue
        if not bool(row.get("runtime_pass")) or not bool(row.get("ante_integrity_pass")):
            continue
        if not bool(row.get("stage2_effect_pass")):
            continue
        focus_delta = _as_float(row.get("focus_metric_delta"))
        quick_score = _as_float(row.get("quick_score"))
        support = row.get("support") if isinstance(row.get("support"), dict) else {}
        support_hits = _as_int(support.get("hits")) or 0
        support_hands = _as_int(support.get("hands")) or 0
        support_hits_delta = _as_int(row.get("targeted_focus_support_hits_delta")) or 0
        support_hands_delta = _as_int(row.get("targeted_focus_support_hands_delta")) or 0
        rank = (
            1.0 if isinstance(focus_delta, float) and math.isfinite(focus_delta) else 0.0,
            float(focus_delta) if isinstance(focus_delta, float) and math.isfinite(focus_delta) else float("-inf"),
            float(support_hits_delta),
            float(support_hands_delta),
            float(support_hits),
            float(support_hands),
            float(quick_score) if isinstance(quick_score, float) and math.isfinite(quick_score) else float("-inf"),
            1.0 if row.get("kind") == "mechanism" else 0.0,
        )
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_row = row
    return best_row


def _candidate_escalation_factor(
    *,
    action_plan: dict[str, Any] | None,
    no_improve_streak: int,
    recent_reasons: list[str] | None = None,
) -> tuple[float, float | None, float, bool]:
    requested: float | None = None
    if isinstance(action_plan, dict):
        v = _as_float(action_plan.get("behavior_escalation_factor"))
        if isinstance(v, float):
            requested = max(1.0, min(4.0, float(v)))

    auto = 1.0
    trailing_deadlock = _trailing_deadlock_count(recent_reasons)
    recent_full_gate_fails = 0
    if isinstance(recent_reasons, list):
        for reason in recent_reasons[-4:]:
            if reason == "full_gate_fail":
                recent_full_gate_fails += 1
    last_reason: str | None = None
    if isinstance(recent_reasons, list) and recent_reasons:
        last = recent_reasons[-1]
        if isinstance(last, str):
            last_reason = last
    # Recent deadlocks usually indicate behavior-identical candidates; escalate
    # deltas earlier to restore observable behavior movement in quick gate.
    if trailing_deadlock >= 3:
        auto = max(auto, 2.4)
    elif trailing_deadlock >= 2:
        auto = max(auto, 2.1)
    elif trailing_deadlock >= 1:
        auto = max(auto, 1.5)

    # If the most recent gate already failed on behavior delta, force a stronger
    # perturbation floor for the next candidate batch.
    if last_reason == "quick_gate_no_behavior_delta":
        auto = max(auto, 2.4)
    if last_reason == "quick_gate_quick_regression":
        auto = max(auto, 2.2)
    # quick gate passes but full gate fails means the search is stuck in a
    # locally "good-quick / bad-full" region; push bigger deltas next cycle.
    if last_reason == "full_gate_fail":
        auto = max(auto, 2.6)
    # Repeated full-gate failures indicate quick-score local maxima that do not
    # survive robustness gates; escalate harder to force mechanism divergence.
    if recent_full_gate_fails >= 2:
        auto = max(auto, 3.2)
    if recent_full_gate_fails >= 3 and int(no_improve_streak) >= 12:
        auto = max(auto, 3.4)
    # Under prolonged full-gate stagnation, push one stronger step so the next
    # mechanism batch is less likely to stay in the same local basin.
    if recent_full_gate_fails >= 3 and int(no_improve_streak) >= 16:
        auto = max(auto, 3.7)
    # Ranked-only blocked means behavior bonus helped ranking but raw quick
    # score stayed below promotion floor; push larger perturbations to search
    # for truly stronger raw candidates.
    if last_reason == "quick_gate_ranked_only_blocked":
        auto = max(auto, 3.0)

    # Step up exploration more aggressively under prolonged stagnation to avoid
    # repeated tie scores with near-identical behavior profiles.
    if int(no_improve_streak) >= 20:
        auto = max(auto, 3.0)
    elif int(no_improve_streak) >= 16:
        auto = max(auto, 2.0)
    elif int(no_improve_streak) >= 8:
        auto = max(auto, 1.5)

    # If recent cycles already pass quick gate but repeatedly fail full gate,
    # avoid escalating into the same over-shoot regime; keep one conservative
    # mechanism step available for the next cycle.
    if (
        last_reason == "full_gate_fail"
        and recent_full_gate_fails >= 2
        and int(trailing_deadlock) == 0
    ):
        full_fail_cap = 2.2
        if int(no_improve_streak) >= 16:
            full_fail_cap = 2.4
        auto = min(auto, float(full_fail_cap))

    effective = max(requested if isinstance(requested, float) else 1.0, auto)
    auto_applied = bool(auto > 1.0 and ((not isinstance(requested, float)) or (requested < auto)))
    return float(effective), (float(requested) if isinstance(requested, float) else None), float(auto), auto_applied


def _scaled_delta(delta: int, scale: float) -> int:
    scaled = int(round(float(delta) * float(scale)))
    if delta > 0 and scaled <= 0:
        return 1
    if delta < 0 and scaled >= 0:
        return -1
    return scaled


def _normalize_delta_map(raw: Any, bounds: dict[str, tuple[int, int, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if not isinstance(key, str) or key not in bounds:
            continue
        delta = _as_int(value)
        if not isinstance(delta, int) or delta == 0:
            continue
        out[key] = int(delta)
    return out


def _apply_delta_map(
    base_params: dict[str, Any],
    delta_map: dict[str, int],
    *,
    bounds: dict[str, tuple[int, int, int]],
    scale: float,
) -> dict[str, Any] | None:
    if not isinstance(delta_map, dict) or not delta_map:
        return None
    p = copy.deepcopy(base_params)
    changed = False
    for key, delta in delta_map.items():
        spec = bounds.get(key)
        if not isinstance(spec, tuple) or len(spec) != 3:
            continue
        _, low, high = spec
        cur = p.get(key)
        if not isinstance(cur, int):
            continue
        step = _scaled_delta(int(delta), scale)
        nxt = max(low, min(high, int(cur) + int(step)))
        if nxt != cur:
            p[key] = int(nxt)
            changed = True
    if not changed:
        return None
    return p


def _recent_quick_gate_reasons(state: dict[str, Any], *, limit: int = 6) -> list[str]:
    rows = state.get("quick_gate_reason_history")
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows[-max(1, int(limit)):]:
        if isinstance(row, str) and row:
            out.append(row)
    return out


def _mechanism_priority_policy(
    *,
    no_improve_streak: int,
    recent_reasons: list[str],
    action_plan: dict[str, Any] | None,
    mechanism_min_share: float,
    mechanism_priority_streak: int,
    mechanism_only_streak: int,
) -> dict[str, Any]:
    mode_hint = ""
    if isinstance(action_plan, dict):
        raw_mode = action_plan.get("mechanism_priority_mode")
        if isinstance(raw_mode, str):
            mode_hint = raw_mode.strip().lower()

    trailing_deadlock = _trailing_deadlock_count(recent_reasons)
    last_reason: str | None = None
    if recent_reasons:
        last = recent_reasons[-1]
        if isinstance(last, str):
            last_reason = last
    behavior_deadlock_recent = last_reason == "quick_gate_no_behavior_delta"

    mechanism_only = False
    if mode_hint in {"only", "force_only", "mechanism_only"}:
        mechanism_only = True
    elif int(no_improve_streak) >= int(mechanism_only_streak) or trailing_deadlock >= 3:
        mechanism_only = True
    elif behavior_deadlock_recent and int(no_improve_streak) >= 2:
        mechanism_only = True

    prioritize = mechanism_only
    if not prioritize:
        prioritize = (
            mode_hint in {"prefer", "first", "mechanism_first"}
            or int(no_improve_streak) >= int(mechanism_priority_streak)
            or trailing_deadlock >= 2
            or (behavior_deadlock_recent and int(no_improve_streak) >= 2)
        )

    min_share = max(0.0, min(1.0, float(mechanism_min_share)))
    if mechanism_only:
        min_share = 1.0
    elif not prioritize:
        min_share = min(min_share, 0.5)

    trigger_reasons: list[str] = []
    if mode_hint:
        trigger_reasons.append(f"mode_hint:{mode_hint}")
    if int(no_improve_streak) >= int(mechanism_priority_streak):
        trigger_reasons.append("streak_priority")
    if int(no_improve_streak) >= int(mechanism_only_streak):
        trigger_reasons.append("streak_only")
    if trailing_deadlock >= 2:
        trigger_reasons.append("deadlock_priority")
    if trailing_deadlock >= 3:
        trigger_reasons.append("deadlock_only")
    if behavior_deadlock_recent and int(no_improve_streak) >= 2:
        trigger_reasons.append("recent_no_behavior_deadlock_only")

    return {
        "prioritize": bool(prioritize),
        "mechanism_only": bool(mechanism_only),
        "min_share": float(min_share),
        "mode_hint": mode_hint or None,
        "no_improve_streak": int(no_improve_streak),
        "trailing_deadlock_count": int(trailing_deadlock),
        "recent_reasons": recent_reasons,
        "trigger_reasons": trigger_reasons,
    }


def _append_journal_entry(
    *,
    cycle: int,
    decision: str,
    baseline_label: str | None,
    baseline_cycle: int | None,
    active_policy: str,
    trial_policy: str | None,
    refs: dict[str, str],
    note: str,
    review_ref: str,
    next_hypothesis: dict[str, Any],
) -> None:
    focus_metric = next_hypothesis.get("focus_metric") if isinstance(next_hypothesis, dict) else None
    block = [
        "",
        f"### {_now_ts().replace('_', '-')}-ralph-loop-cycle-{cycle:03d}",
        f"- change_id: {_now_ts().replace('_', '-')}-ralph-loop-cycle-{cycle:03d}",
        "- change_type: Eval",
        f"- scope: ralph-wiggum-loop cycle {cycle:03d}",
        f"- baseline: {baseline_label if isinstance(baseline_label, str) and baseline_label else 'null'}"
        + (
            f" (adopted_cycle={baseline_cycle})"
            if isinstance(baseline_cycle, int)
            else ""
        ),
        f"- delta: decision={decision}; active={active_policy}; trial={trial_policy if trial_policy else 'null'}",
        "- evidence:",
        f"  - coinpoker summary | ref={refs.get('coin', 'null')}",
        f"  - pool summary | ref={refs.get('pool', 'null')}",
        f"  - br summary | ref={refs.get('br', 'null')}",
        f"  - cycle review | ref={review_ref}",
        f"- outcome: {decision}",
        f"- next_hypothesis: focus_metric={focus_metric if isinstance(focus_metric, str) else 'null'}",
        f"- rationale: {note}",
    ]
    with JOURNAL_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(block) + "\n")


def _propose_candidates(
    base_params: dict[str, Any],
    *,
    cycle: int,
    focus_metric: str | None,
    active_quick: dict[str, Any] | None = None,
    action_plan: dict[str, Any] | None = None,
    no_improve_streak: int = 0,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    mechanism_policy: dict[str, Any] | None = None,
    exclude_hashes: set[str] | None = None,
) -> list[dict[str, Any]]:
    bounds = {k: (d, lo, hi) for k, d, lo, hi in KNOB_SPECS}
    resolved_mechanism_policy = (
        mechanism_policy
        if isinstance(mechanism_policy, dict)
        else _mechanism_priority_policy(
            no_improve_streak=no_improve_streak,
            recent_reasons=[],
            action_plan=action_plan if isinstance(action_plan, dict) else None,
            mechanism_min_share=DEFAULT_MECHANISM_MIN_SHARE,
            mechanism_priority_streak=DEFAULT_MECHANISM_PRIORITY_STREAK,
            mechanism_only_streak=DEFAULT_MECHANISM_ONLY_STREAK,
        )
    )

    mechanism_candidates: list[dict[str, Any]] = []
    knob_candidates: list[dict[str, Any]] = []
    escalation_factor, _requested_escalation, _auto_escalation, _auto_applied = _candidate_escalation_factor(
        action_plan=action_plan if isinstance(action_plan, dict) else None,
        no_improve_streak=no_improve_streak,
    )
    recent_reasons = (
        resolved_mechanism_policy.get("recent_reasons")
        if isinstance(resolved_mechanism_policy, dict)
        else None
    )
    last_reason: str | None = None
    if isinstance(recent_reasons, list) and recent_reasons:
        last = recent_reasons[-1]
        if isinstance(last, str):
            last_reason = last
    recent_full_gate_fails = 0
    if isinstance(recent_reasons, list):
        for reason in recent_reasons[-4:]:
            if reason == "full_gate_fail":
                recent_full_gate_fails += 1
    trailing_full_gate_fail_streak = _trailing_reason_streak(
        recent_reasons,
        target_reason="full_gate_fail",
    )
    mechanism_rotation_active = bool(int(no_improve_streak) >= 8 and recent_full_gate_fails >= 3)
    mechanism_rotation_offset = int(cycle + no_improve_streak + recent_full_gate_fails)
    # Under repeated quick-pass/full-fail stagnation, add a conservative-scale
    # mechanism companion so selection can compare intensity levels directly.
    stability_dual_scale = bool(int(no_improve_streak) >= 12 and recent_full_gate_fails >= 2)
    stability_scale = max(1.0, min(2.0, float(escalation_factor) * 0.55))
    has_action_mechanism_plan = bool(
        isinstance(action_plan, dict)
        and isinstance(action_plan.get("mechanism_plan"), list)
        and action_plan.get("mechanism_plan")
    )
    robustness_recovery_active = bool(
        trailing_full_gate_fail_streak >= 2
        and int(no_improve_streak) >= 2
        and not has_action_mechanism_plan
        and last_reason == "full_gate_fail"
    )
    robustness_recovery_scale = max(0.95, min(1.35, float(stability_scale)))
    if recent_full_gate_fails >= 3:
        robustness_recovery_scale = max(robustness_recovery_scale, 1.10)
    robustness_recovery_mechanisms: list[str] = []
    if robustness_recovery_active:
        for row in (
            "counter_aggression_stability",
            "balanced_pressure_mix",
            "high_price_turn_river_hardening",
        ):
            if isinstance(row, str) and row in MECHANISM_LIBRARY and row not in robustness_recovery_mechanisms:
                robustness_recovery_mechanisms.append(row)
    used_mechanisms: set[str] = set()
    used_knob_keys: set[str] = set()
    blocked_hashes: set[str] = set()
    if isinstance(exclude_hashes, set):
        for row in exclude_hashes:
            h = _normalize_hash(row)
            if isinstance(h, str):
                blocked_hashes.add(h)
    spot_template = _load_loop_spot_policy_template(base_params, focus_metric=focus_metric)

    def _append_candidate(
        sink: list[dict[str, Any]],
        *,
        name: str,
        params: dict[str, Any] | None,
        kind: str,
        origin: str,
        mechanism: str | None = None,
        keys: list[str] | None = None,
        spot_policy: dict[str, Any] | None = None,
        spot_policy_ref: str | None = None,
    ) -> None:
        if not isinstance(params, dict):
            return
        effective_params, resolved_spot_ref, resolved_spot_digest = _candidate_system_params(
            params,
            spot_policy=spot_policy if isinstance(spot_policy, dict) else None,
            spot_policy_ref=spot_policy_ref if isinstance(spot_policy_ref, str) else None,
        )
        digest = _canonical_digest_obj(effective_params).get("hex")
        if not isinstance(digest, str):
            return
        digest = digest.lower()
        if digest in blocked_hashes:
            return
        sink.append(
            {
                "name": name,
                "params": effective_params,
                "kind": kind,
                "origin": origin,
                "mechanism": mechanism,
                "keys": list(keys) if isinstance(keys, list) else [],
                "options_hash": digest,
                "spot_policy": copy.deepcopy(spot_policy) if isinstance(spot_policy, dict) else None,
                "spot_policy_ref": resolved_spot_ref,
                "spot_policy_digest": copy.deepcopy(resolved_spot_digest) if isinstance(resolved_spot_digest, dict) else None,
                "spot_policy_variant": bool(isinstance(spot_policy, dict)),
            }
        )

    def _append_mechanism_from_map(
        *,
        base_name: str,
        mechanism_name: str | None,
        delta_map: dict[str, int],
        idx: int,
        origin: str,
        scale: float,
    ) -> None:
        params = _apply_delta_map(base_params, delta_map, bounds=bounds, scale=scale)
        if not isinstance(params, dict):
            return
        name_mech = mechanism_name if isinstance(mechanism_name, str) and mechanism_name else "custom"
        _append_candidate(
            mechanism_candidates,
            name=f"c{cycle:03d}_{base_name}{idx}_{name_mech}",
            params=params,
            kind="mechanism",
            origin=origin,
            mechanism=name_mech,
            keys=sorted(delta_map.keys()),
        )
        if (
            stability_dual_scale
            and origin in {"action_plan", "adaptive_focus", "focus_metric"}
            and float(scale) > float(stability_scale) + 0.05
        ):
            stable_params = _apply_delta_map(base_params, delta_map, bounds=bounds, scale=stability_scale)
            if isinstance(stable_params, dict):
                _append_candidate(
                    mechanism_candidates,
                    name=f"c{cycle:03d}_{base_name}{idx}s_{name_mech}",
                    params=stable_params,
                    kind="mechanism",
                    origin=origin,
                    mechanism=name_mech,
                    keys=sorted(delta_map.keys()),
                )
        if isinstance(mechanism_name, str) and mechanism_name:
            used_mechanisms.add(mechanism_name)

    def _append_spot_candidate_from_map(
        *,
        base_name: str,
        mechanism_name: str | None,
        idx: int,
        origin: str,
        scale: float,
    ) -> None:
        if not isinstance(spot_template, dict):
            return
        if not isinstance(mechanism_name, str) or not mechanism_name:
            return
        spot_delta_map = {
            key: int(delta)
            for key, delta in SPOT_POLICY_MECHANISM_LIBRARY.get(mechanism_name, ())
            if key in SPOT_POLICY_ADJUSTMENT_BOUNDS
        }
        if not spot_delta_map:
            return
        spot_policy_obj, spot_keys = _mutate_spot_policy(
            spot_template["spec"],
            mechanism_name=mechanism_name,
            delta_map=spot_delta_map,
            scale=scale,
        )
        if not isinstance(spot_policy_obj, dict):
            return
        spot_digest_obj = spot_policy_digest(spot_policy_obj, strict_mode=True)
        _append_candidate(
            mechanism_candidates,
            name=f"c{cycle:03d}_{base_name}{idx}_{mechanism_name}_spot",
            params=base_params,
            kind="mechanism",
            origin=origin,
            mechanism=mechanism_name,
            keys=sorted(spot_keys),
            spot_policy=spot_policy_obj,
            spot_policy_ref=_generated_spot_policy_ref_from_digest(str(spot_digest_obj.get("hex"))),
        )

    if isinstance(action_plan, dict):
        mechanism_plan = action_plan.get("mechanism_plan")
        if isinstance(mechanism_plan, list):
            for idx, row in enumerate(mechanism_plan, start=1):
                if not isinstance(row, dict):
                    continue
                mechanism_name = row.get("mechanism")
                mechanism_name = mechanism_name if isinstance(mechanism_name, str) else None
                row_scale = _scale_factor(row.get("scale"))
                if row.get("scale") is not None and not isinstance(row_scale, float):
                    raise ValueError(
                        "invalid mechanism_plan scale (expected number or one of tiny/small/medium/large/xlarge)"
                    )
                plan_scale = float(row_scale) if isinstance(row_scale, float) else 1.0
                if isinstance(mechanism_name, str) and mechanism_name in MECHANISM_LIBRARY:
                    delta_map = {k: int(v) for k, v in MECHANISM_LIBRARY[mechanism_name]}
                else:
                    delta_map = _normalize_delta_map(row.get("deltas"), bounds)
                _append_spot_candidate_from_map(
                    base_name="m",
                    mechanism_name=mechanism_name,
                    idx=idx,
                    origin="action_plan",
                    scale=escalation_factor * plan_scale,
                )
                _append_mechanism_from_map(
                    base_name="m",
                    mechanism_name=mechanism_name,
                    delta_map=delta_map,
                    idx=idx,
                    origin="action_plan",
                    scale=escalation_factor * plan_scale,
                )

        knob_plan = action_plan.get("knob_plan")
        if isinstance(knob_plan, list):
            for idx, row in enumerate(knob_plan, start=1):
                if not isinstance(row, dict):
                    continue
                key = row.get("key")
                delta = _as_int(row.get("delta"))
                if not isinstance(key, str) or key not in bounds or not isinstance(delta, int):
                    continue
                _, low, high = bounds[key]
                scaled_delta = int(round(float(delta) * escalation_factor))
                if delta > 0 and scaled_delta <= 0:
                    scaled_delta = 1
                elif delta < 0 and scaled_delta >= 0:
                    scaled_delta = -1
                p = copy.deepcopy(base_params)
                if isinstance(p.get(key), int):
                    p[key] = max(low, min(high, int(p[key]) + int(scaled_delta)))
                _append_candidate(
                    knob_candidates,
                    name=f"c{cycle:03d}_a{idx}_{key}",
                    params=p,
                    kind="knob",
                    origin="action_plan",
                    keys=[key],
                )
                used_knob_keys.add(key)

    if robustness_recovery_active:
        # Fail-open keeps the loop moving, but it also means action-plan-only
        # robustness companions disappear. Re-introduce a bounded recovery lane
        # after repeated full-gate failures so the next batch can target gg/BR
        # stability instead of only pushing the focus weakness harder.
        for idx, mechanism_name in enumerate(robustness_recovery_mechanisms, start=1):
            if mechanism_name in used_mechanisms:
                continue
            delta_map = {k: int(v) for k, v in MECHANISM_LIBRARY.get(mechanism_name, ())}
            _append_spot_candidate_from_map(
                base_name="rr",
                mechanism_name=mechanism_name,
                idx=idx,
                origin="robustness_recovery",
                scale=robustness_recovery_scale,
            )
            _append_mechanism_from_map(
                base_name="rr",
                mechanism_name=mechanism_name,
                delta_map=delta_map,
                idx=idx,
                origin="robustness_recovery",
                scale=robustness_recovery_scale,
            )
            if idx >= 2:
                break

    if isinstance(focus_metric, str) and focus_metric == FOCUS_SUPPORT_FOCUS_METRIC and isinstance(active_quick, dict):
        adaptive_scale, mix_snapshot = _adaptive_focus_hardening_scale(active_quick)
        if adaptive_scale > 0.0:
            adaptive_origin = "adaptive_focus"
            # Evidence-conditioned hardening: prioritize low-SPR + wet-board defense
            # when quick probe shows persistent high-price CALL bias.
            _append_spot_candidate_from_map(
                base_name="af",
                mechanism_name="low_spr_wet_firewall",
                idx=1,
                origin=adaptive_origin,
                scale=escalation_factor * adaptive_scale,
            )
            _append_mechanism_from_map(
                base_name="af",
                mechanism_name="low_spr_wet_firewall",
                delta_map={k: int(v) for k, v in MECHANISM_LIBRARY.get("low_spr_wet_firewall", ())},
                idx=1,
                origin=adaptive_origin,
                scale=escalation_factor * adaptive_scale,
            )
            call_peak = _as_float(mix_snapshot.get("call_peak"))
            if isinstance(call_peak, float) and call_peak >= 0.50:
                _append_spot_candidate_from_map(
                    base_name="af",
                    mechanism_name="oop_mw_defense_clamp",
                    idx=2,
                    origin=adaptive_origin,
                    scale=escalation_factor * max(1.0, adaptive_scale - 0.20),
                )
                _append_mechanism_from_map(
                    base_name="af",
                    mechanism_name="oop_mw_defense_clamp",
                    delta_map={k: int(v) for k, v in MECHANISM_LIBRARY.get("oop_mw_defense_clamp", ())},
                    idx=2,
                    origin=adaptive_origin,
                    scale=escalation_factor * max(1.0, adaptive_scale - 0.20),
                )

    if isinstance(focus_metric, str):
        focus_mechanisms = [
            mechanism_name
            for mechanism_name in FOCUS_METRIC_TO_MECHANISMS.get(focus_metric, ())
            if isinstance(mechanism_name, str)
        ]
        if mechanism_rotation_active and len(focus_mechanisms) > 1:
            offset = int(mechanism_rotation_offset) % len(focus_mechanisms)
            focus_mechanisms = focus_mechanisms[offset:] + focus_mechanisms[:offset]
        for idx, mechanism_name in enumerate(focus_mechanisms, start=1):
            if not isinstance(mechanism_name, str):
                continue
            if mechanism_name in used_mechanisms:
                continue
            delta_map = {k: int(v) for k, v in MECHANISM_LIBRARY.get(mechanism_name, ())}
            _append_spot_candidate_from_map(
                base_name="fm",
                mechanism_name=mechanism_name,
                idx=idx,
                origin="focus_metric",
                scale=escalation_factor,
            )
            _append_mechanism_from_map(
                base_name="fm",
                mechanism_name=mechanism_name,
                delta_map=delta_map,
                idx=idx,
                origin="focus_metric",
                scale=escalation_factor,
            )

        for idx, (key, focus_delta) in enumerate(FOCUS_METRIC_TO_KNOBS.get(focus_metric, ()), start=1):
            if key not in bounds:
                continue
            _, low, high = bounds[key]
            scaled_delta = int(round(float(focus_delta) * escalation_factor))
            if focus_delta > 0 and scaled_delta <= 0:
                scaled_delta = 1
            elif focus_delta < 0 and scaled_delta >= 0:
                scaled_delta = -1
            p = copy.deepcopy(base_params)
            if isinstance(p.get(key), int):
                p[key] = max(low, min(high, int(p[key]) + int(scaled_delta)))
            _append_candidate(
                knob_candidates,
                name=f"c{cycle:03d}_f{idx}_{key}",
                params=p,
                kind="knob",
                origin="focus_metric",
                keys=[key],
            )
            used_knob_keys.add(key)

    global_mechanisms = [str(name) for name in MECHANISM_LIBRARY.keys()]
    if mechanism_rotation_active and len(global_mechanisms) > 1:
        offset = int(mechanism_rotation_offset) % len(global_mechanisms)
        global_mechanisms = global_mechanisms[offset:] + global_mechanisms[:offset]
    for idx, mechanism_name in enumerate(global_mechanisms, start=1):
        if mechanism_name in used_mechanisms:
            continue
        delta_map = {k: int(v) for k, v in MECHANISM_LIBRARY[mechanism_name]}
        _append_spot_candidate_from_map(
            base_name="g",
            mechanism_name=mechanism_name,
            idx=idx,
            origin="global",
            scale=escalation_factor,
        )
        _append_mechanism_from_map(
            base_name="g",
            mechanism_name=mechanism_name,
            delta_map=delta_map,
            idx=idx,
            origin="global",
            scale=escalation_factor,
        )
        if len(mechanism_candidates) >= max(2, int(max_candidates)):
            break

    for idx, (key, delta, low, high) in enumerate(KNOB_SPECS[:4], start=1):
        if key in used_knob_keys:
            continue
        scaled_delta = int(round(float(delta) * escalation_factor))
        if delta > 0 and scaled_delta <= 0:
            scaled_delta = 1
        elif delta < 0 and scaled_delta >= 0:
            scaled_delta = -1
        p = copy.deepcopy(base_params)
        if isinstance(p.get(key), int):
            p[key] = max(low, min(high, int(p[key]) + int(scaled_delta)))
        _append_candidate(
            knob_candidates,
            name=f"c{cycle:03d}_k{idx}_{key}",
            params=p,
            kind="knob",
            origin="global",
            keys=[key],
        )
        used_knob_keys.add(key)

    rng = random.Random(cycle * 7919 + 17)
    p_mix = copy.deepcopy(base_params)
    for key, delta, low, high in KNOB_SPECS:
        if not isinstance(p_mix.get(key), int):
            continue
        sign = -1 if rng.random() < 0.5 else 1
        step = int(round(abs(delta) * escalation_factor * (0.5 + rng.random() * 0.75)))
        if step <= 0:
            step = 1
        p_mix[key] = max(low, min(high, int(p_mix[key]) + sign * step))
    _append_candidate(
        knob_candidates,
        name=f"c{cycle:03d}_mix",
        params=p_mix,
        kind="knob",
        origin="mix",
        keys=[k for k, *_ in KNOB_SPECS],
    )

    # Preserve mechanism intent ordering: action_plan/focus proposals first,
    # then global/mix/explore backfill. This keeps model-suggested candidates
    # from being drowned by lexical name sorting.
    mechanism_candidates.sort(key=_candidate_priority_key)
    knob_candidates.sort(key=_candidate_priority_key)

    limit = max(1, int(max_candidates))
    min_share = _as_float(resolved_mechanism_policy.get("min_share"))
    mechanism_min_share = max(0.0, min(1.0, min_share if isinstance(min_share, float) else DEFAULT_MECHANISM_MIN_SHARE))
    mechanism_only = bool(resolved_mechanism_policy.get("mechanism_only"))
    if mechanism_only:
        mechanism_target = limit
    else:
        mechanism_target = max(1, int(math.ceil(limit * mechanism_min_share)))

    selected: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    def _push(rows: list[dict[str, Any]], count: int | None = None) -> None:
        for row in rows:
            if count is not None and len(selected) >= count:
                break
            if len(selected) >= limit:
                break
            h = row.get("options_hash")
            if not isinstance(h, str) or h in seen_hashes:
                continue
            seen_hashes.add(h)
            selected.append(row)

    if robustness_recovery_active:
        for row in mechanism_candidates:
            if row.get("origin") != "robustness_recovery":
                continue
            h = row.get("options_hash")
            if not isinstance(h, str) or h in seen_hashes:
                continue
            seen_hashes.add(h)
            selected.append(row)
            break
    _push(mechanism_candidates, count=mechanism_target)
    if not mechanism_only:
        _push(knob_candidates, count=limit)
    if len(selected) < limit:
        _push(mechanism_candidates, count=limit)
    if len(selected) < limit and not mechanism_only:
        _push(knob_candidates, count=limit)

    # Final safety dedupe in case candidate source changes in future.
    deduped: list[dict[str, Any]] = []
    seen_hashes.clear()
    for row in selected:
        h = row.get("options_hash")
        if not isinstance(h, str) or h in seen_hashes:
            continue
        seen_hashes.add(h)
        deduped.append(row)

    # If deterministic proposals collapse into previously explored hashes, backfill
    # with bounded stochastic exploration to keep cycles progressing.
    if len(deduped) < limit:
        rng_explore = random.Random(cycle * 28657 + no_improve_streak * 271 + 19)
        attempts = 0
        max_attempts = max(32, limit * 24)
        # Keep mechanism-priority cycles attributable and avoid behavior-identical
        # backfill candidates under repeated no-improve/deadlock streaks.
        trailing_deadlock = _as_int(resolved_mechanism_policy.get("trailing_deadlock_count")) or 0
        prioritize = bool(resolved_mechanism_policy.get("prioritize"))
        lane_mechanisms: list[str] = []
        if robustness_recovery_active:
            for mechanism_name in robustness_recovery_mechanisms:
                if mechanism_name in MECHANISM_LIBRARY and mechanism_name not in lane_mechanisms:
                    lane_mechanisms.append(mechanism_name)
        for mechanism_name in DEFAULT_STAGNATION_MECHANISM_LANES:
            if mechanism_name in MECHANISM_LIBRARY and mechanism_name not in lane_mechanisms:
                lane_mechanisms.append(mechanism_name)
        for mechanism_name in FOCUS_METRIC_TO_MECHANISMS.get(focus_metric, ()):
            if mechanism_name in MECHANISM_LIBRARY and mechanism_name not in lane_mechanisms:
                lane_mechanisms.append(mechanism_name)
        if mechanism_only:
            explore_min_changes = 3
        elif prioritize and (trailing_deadlock >= 2 or int(no_improve_streak) >= 2):
            explore_min_changes = 3
        elif prioritize or trailing_deadlock >= 1:
            explore_min_changes = 2
        else:
            explore_min_changes = 1
        while len(deduped) < limit and attempts < max_attempts:
            attempts += 1
            p = copy.deepcopy(base_params)
            touched: list[str] = []
            change_count = 0
            lane_name: str | None = None
            candidate_specs: list[tuple[str, int, int, int]] = []
            if (mechanism_only or prioritize) and lane_mechanisms:
                lane_name = lane_mechanisms[(attempts - 1) % len(lane_mechanisms)]
                for key, base_delta in MECHANISM_LIBRARY.get(lane_name, ()):
                    if key not in bounds:
                        continue
                    _, low, high = bounds[key]
                    candidate_specs.append((key, int(base_delta), int(low), int(high)))
            if not candidate_specs:
                candidate_specs = list(KNOB_SPECS)
            for key, base_delta, low, high in candidate_specs:
                if not isinstance(p.get(key), int):
                    continue
                skip_rate = 0.15 if isinstance(lane_name, str) else 0.35
                if rng_explore.random() < skip_rate:
                    continue
                sign = -1 if rng_explore.random() < 0.5 else 1
                mag = abs(int(base_delta))
                if mag <= 0:
                    continue
                stretch = 0.45 + rng_explore.random() * 1.75
                step = int(round(float(mag) * float(escalation_factor) * stretch))
                if step <= 0:
                    step = 1
                nxt = int(p[key]) + sign * step
                clamped = max(low, min(high, nxt))
                if clamped == int(p[key]):
                    continue
                p[key] = clamped
                touched.append(key)
                change_count += 1
            if change_count < explore_min_changes:
                continue
            h = _canonical_digest_obj(p).get("hex")
            if not isinstance(h, str):
                continue
            h = h.lower()
            if h in seen_hashes or h in blocked_hashes:
                continue
            seen_hashes.add(h)
            deduped.append(
                {
                    "name": f"c{cycle:03d}_x{len(deduped)+1}",
                    "params": p,
                    "kind": "mechanism" if change_count >= 3 else "knob",
                    "origin": "lane_explore" if isinstance(lane_name, str) else "explore",
                    "mechanism": (
                        lane_name
                        if isinstance(lane_name, str) and change_count >= 3
                        else ("explore_mix" if change_count >= 3 else None)
                    ),
                    "keys": sorted(touched),
                    "options_hash": h,
                }
            )
    return deduped[:limit]


def _load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        obj = _json_load(state_path)
    except Exception as exc:
        backup_ref = None
        try:
            backup_path = state_path.with_suffix(state_path.suffix + f".invalid_{_now_ts()}")
            state_path.replace(backup_path)
            backup_ref = f"path:{backup_path.resolve()}"
        except Exception:
            backup_ref = None
        _append_trace_event(
            status="error",
            reason="state_file_invalid_json_recovered",
            cycle=None,
            payload={
                "state_file": str(state_path),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "backup_ref": backup_ref,
            },
        )
        return {}
    if not isinstance(obj, dict):
        return {}
    return obj


def _save_state(state_path: Path, state: dict[str, Any]) -> None:
    _json_dump(state_path, state)


def _ensure_active_policy(
    *,
    state: dict[str, Any],
    source_baseline_label: str,
    active_label: str,
) -> dict[str, Any]:
    active_path = POLICIES_DIR / f"{active_label}.json"
    if active_path.exists():
        bundle = _resolve_policy_bundle(active_label)
        state["active_policy_label"] = active_label
        return bundle

    base = _resolve_policy_bundle(source_baseline_label)
    note = f"loop active alias init from {source_baseline_label} at {_now_ts()}"
    _materialize_policy(
        policy_label=active_label,
        template_policy_spec=base["policy_spec"],
        template_policy_params=base["policy_params"],
        system_params=base["system_params"],
        note_tag=note,
    )
    bundle = _resolve_policy_bundle(active_label)
    state["active_policy_label"] = active_label
    state.pop("active_source_baseline_label", None)
    return bundle


def _build_cycle_review(
    *,
    cycle: int,
    decision: str,
    goal_pack: dict[str, Any],
    promotion_gates: dict[str, Any],
    baseline_before: dict[str, Any] | None,
    baseline_after: dict[str, Any] | None,
    active_metrics: dict[str, Any],
    full_trial: dict[str, Any] | None,
    best_trial: dict[str, Any] | None,
    active_quick: dict[str, Any],
    quick_gate: dict[str, Any] | None,
    next_action_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    target_eval_active = _target_eval(active_metrics, goal_pack["target_gates"], goal_pack.get("robust_gates"))
    target_eval_trial = (
        _target_eval(full_trial, goal_pack["target_gates"], goal_pack.get("robust_gates"))
        if isinstance(full_trial, dict)
        else None
    )
    weaknesses = _rank_weaknesses(target_eval_active, metrics=active_metrics if isinstance(active_metrics, dict) else {})
    next_hypothesis = _derive_next_hypothesis(weaknesses)

    active_score = _as_float((active_metrics or {}).get("score"))
    trial_score = _as_float((full_trial or {}).get("score"))
    quick_active = _as_float((active_quick or {}).get("score"))
    quick_trial = _as_float(((best_trial or {}).get("quick") or {}).get("score")) if isinstance(best_trial, dict) else None
    quick_trial_rank_bonus = _as_float((best_trial or {}).get("quick_rank_behavior_bonus")) if isinstance(best_trial, dict) else None
    quick_trial_ranked = (
        float(quick_trial + quick_trial_rank_bonus)
        if isinstance(quick_trial, float) and isinstance(quick_trial_rank_bonus, float)
        else quick_trial
    )

    return {
        "cycle": int(cycle),
        "decision": decision,
        "goal_pack": {
            "goal_pack_id": goal_pack.get("goal_pack_id"),
            "goal_pack_ref": f"path:{goal_pack.get('path')}",
        },
        "promotion_gates": {
            "quick_min_delta": float(promotion_gates["quick_min_delta"]),
            "full_min_delta": float(promotion_gates["full_min_delta"]),
            "regress_tolerance": float(promotion_gates["regress_tolerance"]),
            "holdout_regress_tolerance": float(
                promotion_gates.get("holdout_regress_tolerance", promotion_gates["regress_tolerance"])
            ),
            "holdout_phase1_required": bool(promotion_gates.get("holdout_phase1_required", True)),
            "holdout_phase2_on_promotion": bool(promotion_gates.get("holdout_phase2_on_promotion", True)),
        },
        "baseline": {
            "before": _runtime_baseline_summary(baseline_before),
            "after": _runtime_baseline_summary(baseline_after),
        },
        "target_eval_active": target_eval_active,
        "target_eval_trial": target_eval_trial,
        "comparison": {
            "active_quick_score": quick_active,
            "best_trial_quick_score": quick_trial,
            "best_trial_quick_score_ranked": quick_trial_ranked,
            "best_trial_quick_rank_behavior_bonus": quick_trial_rank_bonus,
            "active_full_score": active_score,
            "trial_full_score": trial_score,
            "quick_delta": (quick_trial - quick_active) if isinstance(quick_trial, float) and isinstance(quick_active, float) else None,
            "quick_delta_ranked": (
                quick_trial_ranked - quick_active
                if isinstance(quick_trial_ranked, float) and isinstance(quick_active, float)
                else None
            ),
            "full_delta": (trial_score - active_score) if isinstance(trial_score, float) and isinstance(active_score, float) else None,
        },
        "quick_gate": quick_gate if isinstance(quick_gate, dict) else None,
        "next_action": next_action_meta if isinstance(next_action_meta, dict) else None,
        "weakness_ranked": weaknesses,
        "next_hypothesis": next_hypothesis,
    }


def _run_worker(args: argparse.Namespace) -> int:
    state_path = Path(args.state_file)
    state = _load_state(state_path)
    cycle = int(args.cycle)
    no_improve_streak_before = int(state.get("no_improve_streak", 0))
    recent_gate_reasons = _recent_quick_gate_reasons(state, limit=6)
    runs_root = Path(args.runs_root)
    cycle_lock_path = runs_root / f"cycle_{cycle:03d}.lock"
    stale_sec = max(int(float(args.timeout_sec) * 3.0), LOCK_STALE_SEC_DEFAULT) if isinstance(args.timeout_sec, (int, float)) else LOCK_STALE_SEC_DEFAULT
    lock_ok, lock_owner = _acquire_file_lock(cycle_lock_path, stale_sec=stale_sec)
    if not lock_ok:
        print(
            json.dumps(
                {
                    "status": "retry",
                    "cycle": cycle,
                    "reason": "cycle_lock_held",
                    "lock_ref": f"path:{cycle_lock_path.resolve()}",
                    "owner": lock_owner,
                }
            )
        )
        return LOCK_HELD_EXIT_CODE

    try:
        require_llm_action_ticket_base = bool(args.require_llm_action_ticket)
        llm_review_policy = _llm_review_policy(
            base_require_llm_action_ticket=require_llm_action_ticket_base,
            recent_reasons=recent_gate_reasons,
            no_improve_streak=no_improve_streak_before,
            full_gate_fail_streak=int(args.llm_review_full_gate_fail_streak),
            min_no_improve_streak=int(args.llm_review_min_no_improve_streak),
            fail_open=bool(args.llm_review_fail_open),
        )
        require_llm_action_ticket = bool(llm_review_policy.get("effective_required"))
        llm_review_fail_open_enabled = bool(llm_review_policy.get("fail_open_enabled"))
        if require_llm_action_ticket and not llm_review_fail_open_enabled:
            pre_action_obj, pre_action_status = _load_next_action(NEXT_ACTION_PATH, cycle=cycle)
            pre_action_ticket = _validate_action_ticket(pre_action_obj, cycle=cycle)
            pre_action_ticket_pass = bool(pre_action_ticket.get("pass"))
            if not pre_action_ticket_pass:
                pre_next_action_meta = {
                    "path": str(NEXT_ACTION_PATH),
                    "status": pre_action_status,
                    "consumed": False,
                    "consumed_ref": None,
                    "action_ticket": pre_action_ticket,
                    "action_ticket_pass": False,
                    "llm_action_required": True,
                    "llm_action_required_base": bool(require_llm_action_ticket_base),
                    "llm_review_policy": llm_review_policy,
                }
                print(
                    json.dumps(
                        {
                            "status": "stop",
                            "cycle": cycle,
                            "reason": "awaiting_llm_action",
                            "action_ticket": pre_action_ticket,
                            "next_action": pre_next_action_meta,
                            "llm_action_required": True,
                            "llm_review_policy": llm_review_policy,
                        }
                    )
                )
                _append_trace_event(
                    status="heartbeat",
                    reason="awaiting_llm_action",
                    cycle=cycle,
                    payload={
                        "ticket_reason": pre_action_ticket.get("reason"),
                        "llm_action_required": True,
                        "llm_review_policy": llm_review_policy,
                    },
                )
                return LOCK_HELD_EXIT_CODE

        cycle_root = runs_root / f"cycle_{cycle:03d}_{_now_ts()}"
        cycle_root.mkdir(parents=True, exist_ok=True)
        goal_pack = _load_goal_pack(args.goal_pack)
        pareto_contract = _load_pareto_contract(args.pareto_contract)
        promo_defaults = goal_pack["promotion_gates"]
        quick_min_delta = float(args.quick_min_delta) if args.quick_min_delta is not None else float(promo_defaults["quick_min_delta"])
        full_min_delta = float(args.full_min_delta) if args.full_min_delta is not None else float(promo_defaults["full_min_delta"])
        regress_tolerance = float(args.regress_tolerance) if args.regress_tolerance is not None else float(promo_defaults["regress_tolerance"])
        holdout_regress_tolerance = float(promo_defaults.get("holdout_regress_tolerance", regress_tolerance))
        holdout_phase1_required = bool(promo_defaults.get("holdout_phase1_required", True))
        holdout_phase2_on_promotion = bool(promo_defaults.get("holdout_phase2_on_promotion", True))
        eval_context = _build_eval_context(
            profile=args.profile,
            coinpoker_scenario=args.coinpoker_scenario,
            gg_scenario=args.gg_scenario,
            tier_a_opponents=args.tier_a_opponents,
            tier_p_opponents=args.tier_p_opponents,
            pool_path=args.pool_path,
            full_hands=args.full_hands,
            full_seeds_json=args.full_seeds,
            confirm_seeds_json=args.confirm_seeds,
            goal_pack=goal_pack,
            pareto_contract=pareto_contract,
        )
        eval_context_digest = _normalize_hash(_canonical_digest_obj(eval_context).get("hex"))
        quick_jobs_ratio = float(args.quick_jobs_ratio)
        quick_jobs = _derive_phase_jobs(int(args.jobs), quick_jobs_ratio, leave_headroom=True)
        baseline_integrity_auto_repair = bool(args.baseline_integrity_auto_repair)
        _append_trace_event(
            status="trace",
            reason="cycle_start",
            cycle=cycle,
            payload={
                "run_root": str(cycle_root),
                "jobs_total": int(args.jobs),
                "quick_jobs": int(quick_jobs),
                "max_candidates": int(args.max_candidates),
                "max_full_eval_candidates": int(args.max_full_eval_candidates),
                "quick_regression_tolerance": float(args.quick_regression_tolerance),
                "force_full_probe_streak": int(args.force_full_probe_streak),
                "force_full_probe_deadlock": int(args.force_full_probe_deadlock),
                "force_full_probe_raw_margin": float(args.force_full_probe_raw_margin),
                "llm_review_full_gate_fail_streak": int(args.llm_review_full_gate_fail_streak),
                "llm_review_min_no_improve_streak": int(args.llm_review_min_no_improve_streak),
                "llm_review_fail_open": bool(args.llm_review_fail_open),
                "holdout_phase1_required": bool(holdout_phase1_required),
                "holdout_phase2_on_promotion": bool(holdout_phase2_on_promotion),
                "holdout_regress_tolerance": float(holdout_regress_tolerance),
                "eval_context_digest": eval_context_digest,
                "pareto_contract_digest": pareto_contract.get("digest"),
                "require_llm_action_ticket": bool(require_llm_action_ticket),
                "require_llm_action_ticket_base": bool(require_llm_action_ticket_base),
                "llm_review_policy": llm_review_policy,
            },
        )

        active_bundle = _ensure_active_policy(
            state=state,
            source_baseline_label=args.source_baseline_policy,
            active_label=args.active_policy,
        )
        active_policy = state.get("active_policy_label", args.active_policy)
        base_params = active_bundle["system_params"]
        template_spec = active_bundle["policy_spec"]
        template_pp = active_bundle["policy_params"]
        active_options_hash = _normalize_hash(_canonical_digest_obj(base_params).get("hex"))
        active_options_hash_current = active_options_hash

        baseline_state_changed = False
        baseline_obj = _runtime_baseline_from_state(
            state,
            active_options_hash=active_options_hash_current,
            expected_eval_context_digest=eval_context_digest,
        )
        if not isinstance(baseline_obj, dict):
            legacy_active_full = state.get("active_full_metrics")
            legacy_context_digest = _normalize_hash(state.get("active_full_eval_context_digest"))
            can_migrate_legacy = bool(
                isinstance(legacy_active_full, dict)
                and isinstance(eval_context_digest, str)
                and legacy_context_digest == eval_context_digest
            )
            if can_migrate_legacy:
                baseline_obj = _set_runtime_baseline(
                    state,
                    policy_label=active_policy,
                    policy_options_hash=active_options_hash_current,
                    full_metrics=legacy_active_full,
                    source="migrated_from_active_full_metrics",
                    adopted_cycle=_as_int(state.get("last_cycle")),
                    eval_context_digest=eval_context_digest,
                    eval_context=eval_context,
                )
                baseline_state_changed = True
            else:
                full_boot_root = cycle_root / "bootstrap_active_full"
                active_full_boot = _full_eval(
                    policy_label=active_policy,
                    run_root=full_boot_root,
                    profile=args.profile,
                    coinpoker_scenario=args.coinpoker_scenario,
                    gg_scenario=args.gg_scenario,
                    tier_a_opponents=args.tier_a_opponents,
                    tier_p_opponents=args.tier_p_opponents,
                    pool_path=args.pool_path,
                    full_hands=args.full_hands,
                    full_seeds_json=args.full_seeds,
                    confirm_seeds_json=args.confirm_seeds,
                    jobs_total=args.jobs,
                    quick_jobs_ratio=quick_jobs_ratio,
                    quiet=args.quiet,
                    timeout_sec=args.timeout_sec,
                    heartbeat_sec=args.heartbeat_sec,
                )
                baseline_obj = _set_runtime_baseline(
                    state,
                    policy_label=active_policy,
                    policy_options_hash=active_options_hash_current,
                    full_metrics=active_full_boot,
                    source="bootstrap_active_full",
                    adopted_cycle=None,
                    eval_context_digest=eval_context_digest,
                    eval_context=eval_context,
                )
                baseline_state_changed = True

        baseline_integrity = _runtime_baseline_integrity_report(
            baseline_obj,
            expected_policy_label=active_policy,
            expected_policy_options_hash=active_options_hash_current,
            expected_eval_context_digest=eval_context_digest,
        )
        if not bool(baseline_integrity.get("pass")):
            _append_trace_event(
                status="error",
                reason="baseline_integrity_fail",
                cycle=cycle,
                payload={"integrity": baseline_integrity, "auto_repair": bool(baseline_integrity_auto_repair)},
            )
            if baseline_integrity_auto_repair:
                repair_root = cycle_root / "baseline_integrity_repair"
                repaired_full = _full_eval(
                    policy_label=active_policy,
                    run_root=repair_root,
                    profile=args.profile,
                    coinpoker_scenario=args.coinpoker_scenario,
                    gg_scenario=args.gg_scenario,
                    tier_a_opponents=args.tier_a_opponents,
                    tier_p_opponents=args.tier_p_opponents,
                    pool_path=args.pool_path,
                    full_hands=args.full_hands,
                    full_seeds_json=args.full_seeds,
                    confirm_seeds_json=args.confirm_seeds,
                    jobs_total=args.jobs,
                    quick_jobs_ratio=quick_jobs_ratio,
                    quiet=args.quiet,
                    timeout_sec=args.timeout_sec,
                    heartbeat_sec=args.heartbeat_sec,
                )
                baseline_obj = _set_runtime_baseline(
                    state,
                    policy_label=active_policy,
                    policy_options_hash=active_options_hash_current,
                    full_metrics=repaired_full,
                    source=f"baseline_integrity_repair_cycle_{cycle:03d}",
                    adopted_cycle=_as_int((baseline_obj or {}).get("adopted_cycle"))
                    if isinstance(baseline_obj, dict)
                    else _as_int(state.get("last_cycle")),
                    eval_context_digest=eval_context_digest,
                    eval_context=eval_context,
                )
                baseline_state_changed = True
                baseline_integrity = _runtime_baseline_integrity_report(
                    baseline_obj,
                    expected_policy_label=active_policy,
                    expected_policy_options_hash=active_options_hash_current,
                    expected_eval_context_digest=eval_context_digest,
                )
            if not bool(baseline_integrity.get("pass")):
                print(
                    json.dumps(
                        {
                            "status": "stop",
                            "cycle": cycle,
                            "reason": "baseline_integrity_fail",
                            "integrity": baseline_integrity,
                        }
                    )
                )
                return 2
        pending_confirmation = (
            copy.deepcopy(state.get("baseline_pending_confirmation"))
            if isinstance(state.get("baseline_pending_confirmation"), dict)
            else None
        )
        if isinstance(pending_confirmation, dict):
            pending_hash = _normalize_hash(pending_confirmation.get("policy_options_hash"))
            pending_cycle = _as_int(pending_confirmation.get("cycle"))
            rollback_baseline = (
                copy.deepcopy(pending_confirmation.get("rollback_baseline"))
                if isinstance(pending_confirmation.get("rollback_baseline"), dict)
                else None
            )
            rollback_policy_spec = (
                copy.deepcopy(pending_confirmation.get("rollback_policy_spec"))
                if isinstance(pending_confirmation.get("rollback_policy_spec"), dict)
                else None
            )
            rollback_policy_params = (
                copy.deepcopy(pending_confirmation.get("rollback_policy_params"))
                if isinstance(pending_confirmation.get("rollback_policy_params"), dict)
                else None
            )
            rollback_system_params = (
                copy.deepcopy(pending_confirmation.get("rollback_system_params"))
                if isinstance(pending_confirmation.get("rollback_system_params"), dict)
                else None
            )
            rollback_active_holdout_metrics = (
                copy.deepcopy(pending_confirmation.get("rollback_active_holdout_metrics"))
                if isinstance(pending_confirmation.get("rollback_active_holdout_metrics"), dict)
                else None
            )
            previous_full_metrics = (
                copy.deepcopy(pending_confirmation.get("previous_full_metrics"))
                if isinstance(pending_confirmation.get("previous_full_metrics"), dict)
                else None
            )
            previous_holdout_phase1_mean = _as_float(pending_confirmation.get("previous_holdout_phase1_mean"))
            previous_holdout_phase2_mean = _as_float(pending_confirmation.get("previous_holdout_phase2_mean"))
            if isinstance(pending_hash, str) and pending_hash != active_options_hash_current:
                state.pop("baseline_pending_confirmation", None)
                baseline_state_changed = True
                _append_trace_event(
                    status="trace",
                    reason="provisional_confirmation_stale",
                    cycle=cycle,
                    payload={
                        "pending_policy_options_hash": pending_hash,
                        "active_policy_options_hash": active_options_hash_current,
                    },
                )
            elif (
                isinstance(pending_hash, str)
                and pending_hash == active_options_hash_current
                and isinstance(pending_cycle, int)
                and cycle > pending_cycle
            ):
                holdout_suites_confirm = _load_pool_holdout_suites(args.pool_path)
                confirm_phase1_suite = holdout_suites_confirm[0] if holdout_suites_confirm else None
                confirm_phase2_suite = holdout_suites_confirm[1] if len(holdout_suites_confirm) >= 2 else None
                if not isinstance(confirm_phase1_suite, str) or not confirm_phase1_suite:
                    confirm_phase1_suite = None
                    confirm_phase2_suite = None
                confirm_root = cycle_root / "baseline_confirmation"
                confirm_full = _full_eval(
                    policy_label=active_policy,
                    run_root=confirm_root / "full",
                    profile=args.profile,
                    coinpoker_scenario=args.coinpoker_scenario,
                    gg_scenario=args.gg_scenario,
                    tier_a_opponents=args.tier_a_opponents,
                    tier_p_opponents=args.tier_p_opponents,
                    pool_path=args.pool_path,
                    full_hands=args.full_hands,
                    full_seeds_json=args.confirm_seeds,
                    confirm_seeds_json=args.confirm_seeds,
                    jobs_total=args.jobs,
                    quick_jobs_ratio=quick_jobs_ratio,
                    quiet=args.quiet,
                    timeout_sec=args.timeout_sec,
                    heartbeat_sec=args.heartbeat_sec,
                )
                confirm_phase1_result = None
                confirm_phase2_result = None
                confirm_phase1_mean: float | None = None
                confirm_phase2_mean: float | None = None
                if isinstance(confirm_phase1_suite, str):
                    confirm_phase1_result = _run_holdout_suite_eval(
                        scenario=args.coinpoker_scenario,
                        profile=args.profile,
                        policy=active_policy,
                        suite=confirm_phase1_suite,
                        hands=args.full_hands,
                        seeds_json=args.confirm_seeds,
                        jobs=max(1, _derive_phase_jobs(int(args.jobs), 0.50, leave_headroom=True)),
                        out_dir=confirm_root / "holdout_phase1",
                        quiet=args.quiet,
                        timeout_sec=args.timeout_sec,
                        heartbeat_sec=args.heartbeat_sec,
                    )
                    confirm_phase1_mean = (
                        _as_float(confirm_phase1_result.get("mean_bb100"))
                        if isinstance(confirm_phase1_result, dict)
                        else None
                    )
                if bool(holdout_phase2_on_promotion) and isinstance(confirm_phase2_suite, str):
                    confirm_phase2_result = _run_holdout_suite_eval(
                        scenario=args.coinpoker_scenario,
                        profile=args.profile,
                        policy=active_policy,
                        suite=confirm_phase2_suite,
                        hands=args.full_hands,
                        seeds_json=args.confirm_seeds,
                        jobs=max(1, _derive_phase_jobs(int(args.jobs), 0.50, leave_headroom=True)),
                        out_dir=confirm_root / "holdout_phase2",
                        quiet=args.quiet,
                        timeout_sec=args.timeout_sec,
                        heartbeat_sec=args.heartbeat_sec,
                    )
                    confirm_phase2_mean = (
                        _as_float(confirm_phase2_result.get("mean_bb100"))
                        if isinstance(confirm_phase2_result, dict)
                        else None
                    )
                confirm_gate = _provisional_confirmation_gate(
                    candidate_metrics=confirm_full,
                    baseline_metrics=previous_full_metrics if isinstance(previous_full_metrics, dict) else {},
                    candidate_holdout_phase1_mean=confirm_phase1_mean,
                    baseline_holdout_phase1_mean=previous_holdout_phase1_mean,
                    candidate_holdout_phase2_mean=confirm_phase2_mean,
                    baseline_holdout_phase2_mean=previous_holdout_phase2_mean,
                    holdout_phase1_required=bool(confirm_phase1_suite),
                    holdout_phase2_required=bool(holdout_phase2_on_promotion and isinstance(confirm_phase2_suite, str)),
                    holdout_regress_tolerance=float(holdout_regress_tolerance),
                )
                if bool(confirm_gate.get("pass")):
                    baseline_obj = _set_runtime_baseline(
                        state,
                        policy_label=active_policy,
                        policy_options_hash=active_options_hash_current,
                        full_metrics=baseline_obj.get("full_metrics")
                        if isinstance(baseline_obj, dict) and isinstance(baseline_obj.get("full_metrics"), dict)
                        else confirm_full,
                        source=f"provisional_confirm_cycle_{cycle:03d}",
                        adopted_cycle=_as_int((baseline_obj or {}).get("adopted_cycle"))
                        if isinstance(baseline_obj, dict)
                        else pending_cycle,
                        eval_context_digest=eval_context_digest,
                        eval_context=eval_context,
                        adopt_mode="confirmed",
                        previous_policy_options_hash=_normalize_hash(
                            pending_confirmation.get("previous_policy_options_hash")
                        ),
                    )
                    state.pop("baseline_pending_confirmation", None)
                    state["last_provisional_confirmation"] = {
                        "status": "confirmed",
                        "cycle": int(cycle),
                        "policy_options_hash": active_options_hash_current,
                        "pending_cycle": int(pending_cycle),
                        "gate": confirm_gate,
                        "full_ref": f"path:{(confirm_root / 'full').resolve()}",
                    }
                    baseline_state_changed = True
                    _append_trace_event(
                        status="trace",
                        reason="provisional_confirmation_pass",
                        cycle=cycle,
                        payload={
                            "pending_cycle": int(pending_cycle),
                            "policy_options_hash": active_options_hash_current,
                            "gate": confirm_gate,
                        },
                    )
                else:
                    if (
                        isinstance(rollback_policy_spec, dict)
                        and isinstance(rollback_policy_params, dict)
                        and isinstance(rollback_system_params, dict)
                    ):
                        _materialize_policy(
                            policy_label=active_policy,
                            template_policy_spec=rollback_policy_spec,
                            template_policy_params=rollback_policy_params,
                            system_params=rollback_system_params,
                            note_tag=f"rollback provisional baseline cycle={cycle} ts={_now_ts()}",
                        )
                        active_bundle = _resolve_policy_bundle(active_policy)
                        base_params = active_bundle["system_params"]
                        template_spec = active_bundle["policy_spec"]
                        template_pp = active_bundle["policy_params"]
                        active_options_hash_current = _normalize_hash(_canonical_digest_obj(base_params).get("hex"))
                    if isinstance(rollback_baseline, dict) and isinstance(rollback_baseline.get("full_metrics"), dict):
                        baseline_obj = _set_runtime_baseline(
                            state,
                            policy_label=active_policy,
                            policy_options_hash=_normalize_hash(rollback_baseline.get("policy_options_hash"))
                            or active_options_hash_current,
                            full_metrics=rollback_baseline["full_metrics"],
                            source=f"provisional_rollback_cycle_{cycle:03d}",
                            adopted_cycle=_as_int(rollback_baseline.get("adopted_cycle")),
                            eval_context_digest=eval_context_digest,
                            eval_context=eval_context,
                            adopt_mode=rollback_baseline.get("adopt_mode")
                            if isinstance(rollback_baseline.get("adopt_mode"), str)
                            else None,
                            previous_policy_options_hash=_normalize_hash(
                                rollback_baseline.get("previous_policy_options_hash")
                            ),
                        )
                    if isinstance(rollback_active_holdout_metrics, dict):
                        state["active_holdout_metrics"] = rollback_active_holdout_metrics
                    else:
                        state.pop("active_holdout_metrics", None)
                    state["no_improve_streak"] = int((_as_int(pending_confirmation.get("rollback_no_improve_streak")) or 0) + 1)
                    state.pop("baseline_pending_confirmation", None)
                    state["last_provisional_confirmation"] = {
                        "status": "rolled_back",
                        "cycle": int(cycle),
                        "policy_options_hash": pending_hash,
                        "pending_cycle": int(pending_cycle),
                        "gate": confirm_gate,
                        "full_ref": f"path:{(confirm_root / 'full').resolve()}",
                    }
                    baseline_state_changed = True
                    _append_trace_event(
                        status="trace",
                        reason="provisional_confirmation_fail",
                        cycle=cycle,
                        payload={
                            "pending_cycle": int(pending_cycle),
                            "policy_options_hash": pending_hash,
                            "gate": confirm_gate,
                        },
                    )

        if baseline_state_changed:
            _save_state(state_path, state)
        active_options_hash = active_options_hash_current
        baseline_before = copy.deepcopy(baseline_obj)
        active_full = (
            baseline_before.get("full_metrics")
            if isinstance(baseline_before, dict) and isinstance(baseline_before.get("full_metrics"), dict)
            else {}
        )
        active_policy_fingerprint = active_options_hash or str(_canonical_digest_obj(base_params)["hex"])
        active_quick_run_root = cycle_root / "active_quick"
        state["cycle"] = cycle
        state["phase"] = "active_quick"
        state["status"] = "running"
        state["current_run_dir"] = str(active_quick_run_root)
        state["updated_at"] = _now_ts()
        _save_state(state_path, state)
        try:
            active_quick = _quick_eval_cached(
                policy_label=active_policy,
                run_root=active_quick_run_root,
                profile=args.profile,
                quick_scenarios=[args.coinpoker_scenario, args.gg_scenario],
                tier_a_opponents=args.tier_a_opponents,
                tier_p_opponents=args.tier_p_opponents,
                hands=args.quick_hands,
                seeds_json=args.quick_seeds,
                jobs=quick_jobs,
                quiet=args.quiet,
                timeout_sec=args.timeout_sec,
                heartbeat_sec=args.heartbeat_sec,
                policy_fingerprint=active_policy_fingerprint,
            )
        except Exception as exc:
            failure = {
                "status": "error",
                "stage": "active_quick",
                "cycle": int(cycle),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "run_root": str(active_quick_run_root),
            }
            _json_dump(cycle_root / "active_quick_failure.json", failure)
            _append_trace_event(
                status="heartbeat",
                reason="active_quick_eval_failed",
                cycle=cycle,
                payload={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "run_root": str(active_quick_run_root),
                },
            )
            # Keep the cycle alive and emit a review/result instead of crashing the worker.
            active_quick = {
                "policy": active_policy,
                "score": None,
                "metrics": {
                    "_runtime_error": {
                        "returncode": 2,
                        "runtime_error": failure,
                    }
                },
                "runtime_error": failure,
            }
        next_action_obj, next_action_meta = _consume_next_action(NEXT_ACTION_PATH, cycle_root=cycle_root, cycle=cycle)
        action_ticket = _validate_action_ticket(next_action_obj, cycle=cycle)
        action_ticket_pass = bool(action_ticket.get("pass"))
        if not action_ticket_pass:
            next_action_obj = None
        state_next_hypothesis = state.get("next_hypothesis") if isinstance(state.get("next_hypothesis"), dict) else {}
        fallback_action_obj: dict[str, Any] | None = None
        llm_review_fail_open_active = bool((not action_ticket_pass) and llm_review_fail_open_enabled)
        if (not action_ticket_pass) and ((not require_llm_action_ticket) or llm_review_fail_open_active):
            fallback_action_obj = _fallback_action_plan_for_missing_ticket(
                cycle=cycle,
                no_improve_streak=no_improve_streak_before,
                next_hypothesis=state_next_hypothesis,
                recent_reasons=recent_gate_reasons,
                review_ref=state.get("review_ref"),
            )
        if isinstance(next_action_meta, dict):
            next_action_meta["action_ticket"] = action_ticket
            next_action_meta["action_ticket_pass"] = bool(action_ticket_pass)
            next_action_meta["llm_action_required"] = bool(require_llm_action_ticket)
            next_action_meta["llm_action_required_base"] = bool(require_llm_action_ticket_base)
            next_action_meta["llm_review_policy"] = llm_review_policy
            if llm_review_fail_open_active:
                next_action_meta["llm_review_fail_open"] = {
                    "applied": True,
                    "reason": "ticket_missing_or_invalid",
                }
        if (not action_ticket_pass) and bool(require_llm_action_ticket) and not llm_review_fail_open_active:
            print(
                json.dumps(
                    {
                        "status": "stop",
                        "cycle": cycle,
                        "reason": "awaiting_llm_action",
                        "action_ticket": action_ticket,
                        "next_action": next_action_meta,
                        "llm_action_required": True,
                        "llm_review_policy": llm_review_policy,
                    }
                )
            )
            _append_trace_event(
                status="heartbeat",
                reason="awaiting_llm_action",
                cycle=cycle,
                payload={
                    "ticket_reason": action_ticket.get("reason"),
                    "llm_action_required": True,
                    "llm_review_policy": llm_review_policy,
                },
            )
            return LOCK_HELD_EXIT_CODE
        if (not action_ticket_pass) and (not isinstance(fallback_action_obj, dict)):
            print(
                json.dumps(
                    {
                        "status": "stop",
                        "cycle": cycle,
                        "reason": "awaiting_llm_action",
                        "action_ticket": action_ticket,
                        "next_action": next_action_meta,
                        "llm_review_policy": llm_review_policy,
                    }
                )
            )
            _append_trace_event(
                status="heartbeat",
                reason="awaiting_llm_action",
                cycle=cycle,
                payload={"ticket_reason": action_ticket.get("reason"), "llm_review_policy": llm_review_policy},
            )
            return LOCK_HELD_EXIT_CODE
        effective_action_plan = (
            next_action_obj
            if isinstance(next_action_obj, dict)
            else (fallback_action_obj if isinstance(fallback_action_obj, dict) else None)
        )
        if isinstance(next_action_meta, dict) and isinstance(fallback_action_obj, dict):
            fallback_mechanisms: list[str] = []
            raw_plan = fallback_action_obj.get("mechanism_plan")
            if isinstance(raw_plan, list):
                for row in raw_plan:
                    if not isinstance(row, dict):
                        continue
                    mechanism_name = row.get("mechanism")
                    if isinstance(mechanism_name, str):
                        fallback_mechanisms.append(mechanism_name)
            next_action_meta["auto_fallback"] = {
                "applied": True,
                "reason": "missing_action_with_stagnation",
                "focus_metric": fallback_action_obj.get("focus_metric"),
                "mechanisms": fallback_mechanisms,
            }
        base_focus_metric = (
            state_next_hypothesis.get("focus_metric") if isinstance(state_next_hypothesis, dict) else None
        )
        focus_metric = base_focus_metric
        action_overrides_focus = False
        if isinstance(effective_action_plan, dict):
            action_focus = effective_action_plan.get("focus_metric")
            if isinstance(action_focus, str) and action_focus:
                focus_metric = action_focus
                action_overrides_focus = True
        focus_control: dict[str, Any] | None = None
        focus_metric_switched = False
        focus_stop: dict[str, Any] | None = None
        focus_metric, focus_control, focus_metric_switched, focus_stop = _resolve_focus_control(
            state=state,
            cycle=cycle,
            base_focus_metric=base_focus_metric if isinstance(base_focus_metric, str) else None,
            next_hypothesis=state_next_hypothesis if isinstance(state_next_hypothesis, dict) else None,
            action_overrides_focus=bool(action_overrides_focus),
        )
        if isinstance(focus_control, dict):
            state["focus_control"] = focus_control
            _save_state(state_path, state)
        if focus_metric_switched:
            _append_trace_event(
                status="trace",
                reason="focus_metric_switched",
                cycle=cycle,
                payload={
                    "base_focus_metric": base_focus_metric,
                    "active_focus_metric": focus_metric,
                    "focus_control": focus_control,
                },
            )
        if isinstance(focus_stop, dict):
            _append_trace_event(
                status="stopped",
                reason="needs_manual_hypothesis",
                cycle=cycle,
                payload=focus_stop,
            )
            print(
                json.dumps(
                    {
                        "status": "stop",
                        "cycle": cycle,
                        "reason": "needs_manual_hypothesis",
                        "focus_control": focus_stop,
                    }
                )
            )
            return 0

        focus_support_min_hands = int(args.focus_support_min_hands)
        focus_support_min_hits = int(args.focus_support_min_hits)
        behavior_delta_min = float(args.behavior_delta_min)
        quick_regression_tolerance = float(args.quick_regression_tolerance)
        hint_obj = (
            effective_action_plan.get("quick_gate_hints")
            if isinstance(effective_action_plan, dict)
            else None
        )
        (
            focus_support_min_hands,
            focus_support_min_hits,
            behavior_delta_min,
            quick_regression_tolerance,
            quick_gate_hint_overrides,
        ) = _apply_quick_gate_hints(
            base_focus_support_min_hands=int(args.focus_support_min_hands),
            base_focus_support_min_hits=int(args.focus_support_min_hits),
            base_behavior_delta_min=float(args.behavior_delta_min),
            base_quick_regression_tolerance=float(args.quick_regression_tolerance),
            hints=hint_obj if isinstance(hint_obj, dict) else None,
        )

        recent_full_gate_fails = sum(1 for reason in recent_gate_reasons[-4:] if reason == "full_gate_fail")
        mechanism_priority = _mechanism_priority_policy(
            no_improve_streak=no_improve_streak_before,
            recent_reasons=recent_gate_reasons,
            action_plan=effective_action_plan if isinstance(effective_action_plan, dict) else None,
            mechanism_min_share=float(args.mechanism_min_share),
            mechanism_priority_streak=int(args.mechanism_priority_streak),
            mechanism_only_streak=int(args.mechanism_only_streak),
        )
        trailing_deadlock_count = _trailing_deadlock_count(recent_gate_reasons)
        behavior_delta_min_effective, stagnation_escape_applied = _effective_behavior_delta_min(
            base_min=behavior_delta_min,
            no_improve_streak=no_improve_streak_before,
        )
        quick_regression_streak_bonus = min(1.2, max(0, int(no_improve_streak_before) - 1) * 0.15)
        # Repeated full-gate failures mean quick regression guard likely became too
        # permissive under streak inflation; tighten bonus before next quick pass.
        if recent_full_gate_fails >= 2:
            quick_regression_streak_bonus = min(quick_regression_streak_bonus, 0.35)
        if recent_full_gate_fails >= 3 and int(no_improve_streak_before) >= 12:
            quick_regression_streak_bonus = min(quick_regression_streak_bonus, 0.20)
        quick_regression_tolerance_effective = max(
            0.0,
            float(quick_regression_tolerance) + float(quick_regression_streak_bonus),
        )

        recent_option_hashes = _recent_option_hashes_from_state(
            state,
            limit=DEFAULT_RECENT_OPTION_HASH_WINDOW,
        )
        excluded_option_hashes = set(recent_option_hashes)
        if isinstance(active_options_hash, str):
            excluded_option_hashes.add(active_options_hash.lower())
        holdout_suites = _load_pool_holdout_suites(args.pool_path)
        holdout_phase1_suite = holdout_suites[0] if holdout_suites else None
        holdout_phase2_suite = holdout_suites[1] if len(holdout_suites) >= 2 else None
        if not isinstance(holdout_phase1_suite, str) or not holdout_phase1_suite:
            holdout_phase1_required = False
            holdout_phase2_on_promotion = False
            holdout_phase2_suite = None
        holdout_context = _build_holdout_context(
            eval_context_digest=eval_context_digest,
            scenario=args.coinpoker_scenario,
            profile=args.profile,
            hands=args.full_hands,
            seeds_json=args.full_seeds,
            phase1_suite=holdout_phase1_suite if isinstance(holdout_phase1_suite, str) else None,
            phase2_suite=holdout_phase2_suite if isinstance(holdout_phase2_suite, str) else None,
            phase2_on_promotion=bool(holdout_phase2_on_promotion),
        )
        holdout_context_digest = _normalize_hash(_canonical_digest_obj(holdout_context).get("hex"))

        if isinstance(effective_action_plan, dict):
            proposals = _propose_candidates(
                base_params,
                cycle=cycle,
                focus_metric=focus_metric if isinstance(focus_metric, str) else None,
                active_quick=active_quick if isinstance(active_quick, dict) else None,
                action_plan=effective_action_plan if isinstance(effective_action_plan, dict) else None,
                no_improve_streak=no_improve_streak_before,
                max_candidates=int(args.max_candidates),
                mechanism_policy=mechanism_priority,
                exclude_hashes=excluded_option_hashes,
            )
        else:
            proposals = []
        (
            candidate_behavior_escalation_factor,
            candidate_behavior_escalation_requested,
            candidate_behavior_escalation_auto,
            candidate_behavior_escalation_auto_applied,
        ) = _candidate_escalation_factor(
            action_plan=effective_action_plan if isinstance(effective_action_plan, dict) else None,
            no_improve_streak=no_improve_streak_before,
            recent_reasons=recent_gate_reasons,
        )

        best_trial: dict[str, Any] | None = None
        best_overall: dict[str, Any] | None = None
        best_targeted_probe_row: dict[str, Any] | None = None
        best_quick_score = float("-inf")
        best_overall_quick_score = float("-inf")
        best_quick_behavior_bonus = float("-inf")
        best_overall_behavior_bonus = float("-inf")
        best_quick_mechanism = False
        best_overall_mechanism = False
        active_quick_score = float(active_quick.get("score", float("-inf")))
        quick_guard_enabled = _requires_focus_support_guard(focus_metric if isinstance(focus_metric, str) else None)
        active_focus_support = _focus_support_from_quick(active_quick)
        active_focus_support_eval = _focus_support_eval(
            support=active_focus_support,
            min_hands=focus_support_min_hands,
            min_hits=focus_support_min_hits,
        )
        if not quick_guard_enabled:
            active_focus_support_eval["guard_enabled"] = False
            active_focus_support_eval["hard_pass"] = True
            active_focus_support_eval["adaptive_pass"] = True
            active_focus_support_eval["pass"] = True
        else:
            active_focus_support_eval["guard_enabled"] = True
        active_focus_support_pass = bool(active_focus_support_eval.get("pass"))
        active_ante_integrity = _ante_integrity_from_quick(active_quick)
        active_ante_integrity_pass = bool(active_ante_integrity.get("pass"))
        active_runtime = _runtime_health_from_quick(active_quick)
        active_runtime_pass = bool(active_runtime.get("pass"))
        active_targeted_focus = _targeted_focus_summary_from_quick(active_quick)
        candidate_diagnostics: list[dict[str, Any]] = []
        candidate_contexts: dict[str, dict[str, Any]] = {}
        trial_label = args.trial_policy
        for proposal in proposals:
            if not isinstance(proposal, dict):
                continue
            cand_name = proposal.get("name")
            cand_params = proposal.get("params")
            cand_kind = proposal.get("kind")
            cand_origin = proposal.get("origin")
            cand_mechanism = proposal.get("mechanism")
            cand_keys = proposal.get("keys")
            cand_spot_policy = proposal.get("spot_policy")
            cand_spot_policy_ref = proposal.get("spot_policy_ref")
            cand_spot_policy_digest = proposal.get("spot_policy_digest")
            cand_spot_policy_variant = bool(proposal.get("spot_policy_variant"))
            if not isinstance(cand_name, str) or not isinstance(cand_params, dict):
                continue
            cand_options_hash = proposal.get("options_hash")
            if not isinstance(cand_options_hash, str):
                cand_options_hash = _canonical_digest_obj(cand_params).get("hex")
            _append_trace_event(
                status="trace",
                reason="candidate_start",
                cycle=cycle,
                payload={
                    "candidate": cand_name,
                    "kind": cand_kind if isinstance(cand_kind, str) else None,
                    "origin": cand_origin if isinstance(cand_origin, str) else None,
                    "mechanism": cand_mechanism if isinstance(cand_mechanism, str) else None,
                    "spot_policy_variant": bool(cand_spot_policy_variant),
                },
            )
            note = f"loop trial {cand_name} cycle={cycle} ts={_now_ts()}"
            _materialize_policy(
                policy_label=trial_label,
                template_policy_spec=template_spec,
                template_policy_params=template_pp,
                system_params=cand_params,
                note_tag=note,
                spot_policy=cand_spot_policy if isinstance(cand_spot_policy, dict) else None,
            )
            trial_quick_run_root = cycle_root / "trial_quick" / cand_name
            try:
                q = _quick_eval_cached(
                    policy_label=trial_label,
                    run_root=trial_quick_run_root,
                    profile=args.profile,
                    quick_scenarios=[args.coinpoker_scenario, args.gg_scenario],
                    tier_a_opponents=args.tier_a_opponents,
                    tier_p_opponents=args.tier_p_opponents,
                    hands=args.quick_hands,
                    seeds_json=args.quick_seeds,
                    jobs=quick_jobs,
                    quiet=args.quiet,
                    timeout_sec=args.timeout_sec,
                    heartbeat_sec=args.heartbeat_sec,
                    policy_fingerprint=cand_options_hash if isinstance(cand_options_hash, str) else None,
                )
            except Exception as exc:
                runtime_failure = {
                    "status": "error",
                    "stage": "trial_quick",
                    "cycle": int(cycle),
                    "candidate": cand_name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "run_root": str(trial_quick_run_root),
                }
                trial_quick_run_root.mkdir(parents=True, exist_ok=True)
                _json_dump(trial_quick_run_root / "runtime_error.json", runtime_failure)
                _append_trace_event(
                    status="heartbeat",
                    reason="trial_quick_eval_failed",
                    cycle=cycle,
                    payload={
                        "candidate": cand_name,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "run_root": str(trial_quick_run_root),
                    },
                )
                candidate_diagnostics.append(
                    {
                        "name": cand_name,
                        "kind": cand_kind if isinstance(cand_kind, str) else None,
                        "origin": cand_origin if isinstance(cand_origin, str) else None,
                        "mechanism": cand_mechanism if isinstance(cand_mechanism, str) else None,
                        "policy_options_hash": cand_options_hash if isinstance(cand_options_hash, str) else None,
                        "spot_policy_variant": bool(cand_spot_policy_variant),
                        "spot_policy_ref": cand_spot_policy_ref if isinstance(cand_spot_policy_ref, str) else None,
                        "spot_policy_digest": (
                            cand_spot_policy_digest if isinstance(cand_spot_policy_digest, dict) else None
                        ),
                        "quick_score": None,
                        "quick_score_ranked": None,
                        "eligible": False,
                        "runtime_pass": False,
                        "runtime_error": runtime_failure,
                    }
                )
                continue
            targeted_focus = _targeted_focus_summary_from_quick(q)
            support = _focus_support_from_quick(q)
            targeted_focus_support_hits_delta, targeted_focus_support_hands_delta = _support_delta_from_targeted_focus(
                targeted_focus if isinstance(targeted_focus, dict) else None
            )
            support_eval = _focus_support_eval(
                support=support,
                min_hands=focus_support_min_hands,
                min_hits=focus_support_min_hits,
            )
            if not quick_guard_enabled:
                support_eval["guard_enabled"] = False
                support_eval["hard_pass"] = True
                support_eval["adaptive_pass"] = True
                support_eval["pass"] = True
            else:
                support_eval["guard_enabled"] = True
            support_pass = bool(support_eval.get("pass"))
            delta = _behavior_delta(active_quick, q) if quick_guard_enabled else None
            behavior_delta_min_candidate, behavior_delta_min_ratio = _candidate_behavior_delta_min(
                behavior_delta_min_effective=behavior_delta_min_effective,
                candidate_kind=cand_kind if isinstance(cand_kind, str) else None,
                mechanism_policy=mechanism_priority,
            )
            behavior_pass = (
                (isinstance(delta, float) and delta >= behavior_delta_min_candidate) if quick_guard_enabled else True
            )
            behavior_bonus = _behavior_bonus_for_stagnation(
                behavior_delta=delta if quick_guard_enabled else None,
                no_improve_streak=no_improve_streak_before,
            )
            cand_ante_integrity = _ante_integrity_from_quick(q)
            ante_integrity_pass = bool(cand_ante_integrity.get("pass"))
            cand_runtime = _runtime_health_from_quick(q)
            runtime_pass = bool(cand_runtime.get("pass"))
            quick_regression_pass, quick_regressions = _quick_regression_guard(
                active_quick=active_quick,
                trial_quick=q,
                tolerance=quick_regression_tolerance_effective,
            )
            stage1_coverage_pass = bool(runtime_pass and support_pass and ante_integrity_pass)

            cand_quick_score = _as_float(q.get("score"))
            cand_base_score = cand_quick_score if isinstance(cand_quick_score, float) else float("-inf")
            cand_rank_bonus = max(0.0, float(behavior_bonus))
            cand_score_for_rank = cand_base_score
            cand_kind_is_mechanism = bool(cand_kind == "mechanism")
            cand_focus_metric_value = _focus_metric_value_from_quick(
                q,
                focus_metric if isinstance(focus_metric, str) else None,
            )
            active_focus_metric_value = _focus_metric_value_from_quick(
                active_quick,
                focus_metric if isinstance(focus_metric, str) else None,
            )
            cand_focus_metric_delta = (
                float(cand_focus_metric_value) - float(active_focus_metric_value)
                if isinstance(cand_focus_metric_value, float) and isinstance(active_focus_metric_value, float)
                else None
            )
            spot_gate = _spot_gate_eval(
                focus_metric=focus_metric if isinstance(focus_metric, str) else None,
                spot_policy_variant=bool(cand_spot_policy_variant),
                focus_metric_delta=cand_focus_metric_delta,
                support_hits_delta=int(targeted_focus_support_hits_delta),
                support_hands_delta=int(targeted_focus_support_hands_delta),
            )
            spot_gate_pass = bool(spot_gate.get("pass"))
            stage2_effect_pass = bool(behavior_pass and quick_regression_pass and spot_gate_pass)
            eligible = bool(stage1_coverage_pass and stage2_effect_pass)
            candidate_diagnostics.append(
                {
                    "name": cand_name,
                    "options_hash": cand_options_hash,
                    "kind": cand_kind if isinstance(cand_kind, str) else "unknown",
                    "origin": cand_origin if isinstance(cand_origin, str) else None,
                    "mechanism": cand_mechanism if isinstance(cand_mechanism, str) else None,
                    "keys": cand_keys if isinstance(cand_keys, list) else [],
                    "spot_policy_variant": bool(cand_spot_policy_variant),
                    "spot_policy_ref": cand_spot_policy_ref if isinstance(cand_spot_policy_ref, str) else None,
                    "spot_policy_digest": (
                        cand_spot_policy_digest if isinstance(cand_spot_policy_digest, dict) else None
                    ),
                    "quick_score": cand_quick_score,
                    "quick_score_ranked": cand_score_for_rank if cand_score_for_rank != float("-inf") else None,
                    "quick_rank_behavior_bonus": float(cand_rank_bonus),
                    "focus_metric_value": cand_focus_metric_value,
                    "focus_metric_delta": cand_focus_metric_delta,
                    "support": support,
                    "support_eval": support_eval,
                    "support_pass": bool(support_pass),
                    "behavior_delta": delta,
                    "behavior_delta_min_required": (
                        float(behavior_delta_min_candidate) if quick_guard_enabled else None
                    ),
                    "behavior_delta_min_ratio": (
                        float(behavior_delta_min_ratio) if quick_guard_enabled else None
                    ),
                    "behavior_bonus": float(behavior_bonus),
                    "behavior_pass": bool(behavior_pass),
                    "ante_integrity": cand_ante_integrity,
                    "ante_integrity_pass": bool(ante_integrity_pass),
                    "runtime_health": cand_runtime,
                    "runtime_pass": bool(runtime_pass),
                    "quick_regression_pass": bool(quick_regression_pass),
                    "quick_regression_tolerance": float(quick_regression_tolerance_effective),
                    "quick_regressions": quick_regressions,
                    "targeted_focus_set": targeted_focus,
                    "targeted_focus_support_hits_delta": int(targeted_focus_support_hits_delta),
                    "targeted_focus_support_hands_delta": int(targeted_focus_support_hands_delta),
                    "spot_gate": spot_gate,
                    "spot_gate_applicable": bool(spot_gate.get("applicable")),
                    "spot_gate_pass": bool(spot_gate_pass),
                    "stage1_coverage_pass": bool(stage1_coverage_pass),
                    "stage2_effect_pass": bool(stage2_effect_pass),
                    "eligible": bool(eligible),
                }
            )
            candidate_contexts[cand_name] = {
                "name": cand_name,
                "params": cand_params,
                "quick": q,
                "kind": cand_kind if isinstance(cand_kind, str) else None,
                "origin": cand_origin if isinstance(cand_origin, str) else None,
                "mechanism": cand_mechanism if isinstance(cand_mechanism, str) else None,
                "spot_policy": copy.deepcopy(cand_spot_policy) if isinstance(cand_spot_policy, dict) else None,
                "spot_policy_ref": cand_spot_policy_ref if isinstance(cand_spot_policy_ref, str) else None,
                "spot_policy_digest": (
                    copy.deepcopy(cand_spot_policy_digest) if isinstance(cand_spot_policy_digest, dict) else None
                ),
                "spot_policy_variant": bool(cand_spot_policy_variant),
                "quick_score_ranked": cand_score_for_rank,
                "quick_rank_behavior_bonus": float(cand_rank_bonus),
            }
            _append_trace_event(
                status="trace",
                reason="candidate_end",
                cycle=cycle,
                payload={
                    "candidate": cand_name,
                    "quick_score": cand_quick_score,
                    "quick_score_ranked": (cand_score_for_rank if cand_score_for_rank != float("-inf") else None),
                    "quick_rank_behavior_bonus": float(cand_rank_bonus),
                    "support_pass": bool(support_pass),
                    "behavior_pass": bool(behavior_pass),
                    "ante_integrity_pass": bool(ante_integrity_pass),
                    "runtime_pass": bool(runtime_pass),
                    "quick_regression_pass": bool(quick_regression_pass),
                    "spot_gate_pass": bool(spot_gate_pass),
                    "targeted_focus_merged": bool(
                        isinstance(targeted_focus, dict) and bool(targeted_focus.get("merged"))
                    ),
                    "targeted_focus_returncode": (
                        _as_int(targeted_focus.get("returncode")) if isinstance(targeted_focus, dict) else None
                    ),
                    "targeted_focus_support_delta_hits": (
                        _as_int((targeted_focus.get("support_delta") or {}).get("hits"))
                        if isinstance(targeted_focus, dict)
                        else None
                    ),
                    "stage1_coverage_pass": bool(stage1_coverage_pass),
                    "stage2_effect_pass": bool(stage2_effect_pass),
                    "eligible": bool(eligible),
                },
            )
            better_overall = cand_base_score > best_overall_quick_score
            if not better_overall and cand_base_score == best_overall_quick_score:
                better_overall = cand_rank_bonus > best_overall_behavior_bonus
            if (
                not better_overall
                and cand_base_score == best_overall_quick_score
                and cand_rank_bonus == best_overall_behavior_bonus
            ):
                better_overall = bool(cand_kind_is_mechanism and not best_overall_mechanism)
            if better_overall:
                best_overall_quick_score = cand_base_score
                best_overall_behavior_bonus = cand_rank_bonus
                best_overall_mechanism = cand_kind_is_mechanism
                best_overall = {
                    "name": cand_name,
                    "params": cand_params,
                    "quick": q,
                    "kind": cand_kind if isinstance(cand_kind, str) else None,
                    "origin": cand_origin if isinstance(cand_origin, str) else None,
                    "mechanism": cand_mechanism if isinstance(cand_mechanism, str) else None,
                    "spot_policy": copy.deepcopy(cand_spot_policy) if isinstance(cand_spot_policy, dict) else None,
                    "spot_policy_ref": cand_spot_policy_ref if isinstance(cand_spot_policy_ref, str) else None,
                    "spot_policy_digest": (
                        copy.deepcopy(cand_spot_policy_digest) if isinstance(cand_spot_policy_digest, dict) else None
                    ),
                    "spot_policy_variant": bool(cand_spot_policy_variant),
                    "quick_score_ranked": cand_score_for_rank,
                    "quick_rank_behavior_bonus": float(cand_rank_bonus),
                }
            better_trial = eligible and cand_base_score > best_quick_score
            if (
                eligible
                and not better_trial
                and cand_base_score == best_quick_score
            ):
                better_trial = cand_rank_bonus > best_quick_behavior_bonus
            if (
                eligible
                and not better_trial
                and cand_base_score == best_quick_score
                and cand_rank_bonus == best_quick_behavior_bonus
            ):
                better_trial = bool(cand_kind_is_mechanism and not best_quick_mechanism)
            if better_trial:
                best_quick_score = cand_base_score
                best_quick_behavior_bonus = cand_rank_bonus
                best_quick_mechanism = cand_kind_is_mechanism
                best_trial = {
                    "name": cand_name,
                    "params": cand_params,
                    "quick": q,
                    "kind": cand_kind if isinstance(cand_kind, str) else None,
                    "origin": cand_origin if isinstance(cand_origin, str) else None,
                    "mechanism": cand_mechanism if isinstance(cand_mechanism, str) else None,
                    "spot_policy": copy.deepcopy(cand_spot_policy) if isinstance(cand_spot_policy, dict) else None,
                    "spot_policy_ref": cand_spot_policy_ref if isinstance(cand_spot_policy_ref, str) else None,
                    "spot_policy_digest": (
                        copy.deepcopy(cand_spot_policy_digest) if isinstance(cand_spot_policy_digest, dict) else None
                    ),
                    "spot_policy_variant": bool(cand_spot_policy_variant),
                    "quick_score_ranked": cand_score_for_rank,
                    "quick_rank_behavior_bonus": float(cand_rank_bonus),
                }

        best_targeted_probe_row = _select_targeted_shadow_candidate(candidate_rows=candidate_diagnostics)

        decision = "REJECT"
        note = "quick gate no improvement"
        quick_gate_reason = "quick_gate_no_improvement"
        adopted = False
        full_trial: dict[str, Any] | None = None
        target_achieved = False
        baseline_after = copy.deepcopy(baseline_before)

        base_raw_promotion_margin = float(DEFAULT_RANKED_PROMOTION_RAW_FLOOR_MARGIN)
        raw_promotion_margin, raw_promotion_margin_escalated = _effective_ranked_promotion_raw_floor_margin(
            base_margin=base_raw_promotion_margin,
            no_improve_streak=no_improve_streak_before,
            recent_reasons=recent_gate_reasons,
            mechanism_policy=mechanism_priority,
        )
        quick_min_delta_effective, quick_min_delta_relaxed = _effective_quick_min_delta(
            base_delta=quick_min_delta,
            no_improve_streak=no_improve_streak_before,
            recent_reasons=recent_gate_reasons,
            mechanism_policy=mechanism_priority,
        )
        best_trial_raw_quick_score = (
            _as_float((best_trial.get("quick") or {}).get("score")) if isinstance(best_trial, dict) else None
        )
        best_trial_rank_behavior_bonus = (
            _as_float(best_trial.get("quick_rank_behavior_bonus")) if isinstance(best_trial, dict) else None
        )
        ranked_delta_pass = bool(
            isinstance(best_trial_raw_quick_score, float)
            and math.isfinite(best_trial_raw_quick_score)
            and best_trial_raw_quick_score > active_quick_score + quick_min_delta_effective
        )
        raw_floor_pass = bool(
            (not isinstance(best_trial_raw_quick_score, float))
            or (not math.isfinite(best_trial_raw_quick_score))
            or (best_trial_raw_quick_score >= (active_quick_score - raw_promotion_margin))
        )
        mechanism_candidate_count = sum(1 for row in candidate_diagnostics if row.get("kind") == "mechanism")
        knob_candidate_count = sum(1 for row in candidate_diagnostics if row.get("kind") == "knob")
        spot_policy_candidate_count = sum(1 for row in candidate_diagnostics if bool(row.get("spot_policy_variant")))
        candidate_origin_counts: dict[str, int] = {}
        candidate_option_hashes: list[str] = []
        for row in candidate_diagnostics:
            origin = row.get("origin")
            if isinstance(origin, str) and origin:
                candidate_origin_counts[origin] = int(candidate_origin_counts.get(origin, 0)) + 1
            h = _normalize_hash(row.get("options_hash"))
            if isinstance(h, str):
                candidate_option_hashes.append(h)
        support_pass_count = sum(1 for row in candidate_diagnostics if bool(row.get("support_pass")))
        behavior_pass_count = sum(1 for row in candidate_diagnostics if bool(row.get("behavior_pass")))
        behavior_bonus_count = sum(
            1
            for row in candidate_diagnostics
            if isinstance(row.get("behavior_bonus"), (int, float)) and float(row.get("behavior_bonus")) > 0.0
        )
        ante_integrity_pass_count = sum(1 for row in candidate_diagnostics if bool(row.get("ante_integrity_pass")))
        runtime_pass_count = sum(1 for row in candidate_diagnostics if bool(row.get("runtime_pass")))
        runtime_fail_count = int(len(candidate_diagnostics) - runtime_pass_count)
        quick_regression_pass_count = sum(1 for row in candidate_diagnostics if bool(row.get("quick_regression_pass")))
        spot_gate_applicable_count = sum(1 for row in candidate_diagnostics if bool(row.get("spot_gate_applicable")))
        spot_gate_pass_count = sum(1 for row in candidate_diagnostics if bool(row.get("spot_gate_pass")))
        stage1_coverage_pass_count = sum(1 for row in candidate_diagnostics if bool(row.get("stage1_coverage_pass")))
        stage2_effect_pass_count = sum(1 for row in candidate_diagnostics if bool(row.get("stage2_effect_pass")))
        targeted_focus_attempted_count = sum(
            1
            for row in candidate_diagnostics
            if bool((row.get("targeted_focus_set") or {}).get("attempted"))
        )
        targeted_focus_merged_count = sum(
            1
            for row in candidate_diagnostics
            if bool((row.get("targeted_focus_set") or {}).get("merged"))
        )
        targeted_focus_support_hits_delta_total = sum(
            int(_as_int(((row.get("targeted_focus_set") or {}).get("support_delta") or {}).get("hits")) or 0)
            for row in candidate_diagnostics
        )
        targeted_focus_support_hands_delta_total = sum(
            int(_as_int(((row.get("targeted_focus_set") or {}).get("support_delta") or {}).get("hands")) or 0)
            for row in candidate_diagnostics
        )
        eligible_count = sum(1 for row in candidate_diagnostics if bool(row.get("eligible")))
        mechanism_eligible_count = sum(
            1 for row in candidate_diagnostics if bool(row.get("eligible")) and row.get("kind") == "mechanism"
        )
        stage1_coverage_any_pass = bool(
            runtime_pass_count > 0
            and ante_integrity_pass_count > 0
            and ((not quick_guard_enabled) or support_pass_count > 0)
        )
        stage2_effect_any_pass = bool(
            ((not quick_guard_enabled) or behavior_pass_count > 0)
            and quick_regression_pass_count > 0
        )
        last_reason: str | None = None
        if recent_gate_reasons:
            last_item = recent_gate_reasons[-1]
            if isinstance(last_item, str):
                last_reason = last_item
        forced_probe_streak = max(1, int(args.force_full_probe_streak))
        forced_probe_deadlock = max(1, int(args.force_full_probe_deadlock))
        base_forced_probe_raw_margin = max(0.0, float(args.force_full_probe_raw_margin))
        forced_probe_raw_margin, forced_probe_raw_margin_escalated = _effective_force_probe_raw_margin(
            base_margin=base_forced_probe_raw_margin,
            no_improve_streak=no_improve_streak_before,
            recent_reasons=recent_gate_reasons,
        )
        no_improve_probe_streak = max(10, forced_probe_streak)
        prioritize_mechanism_probe = bool(mechanism_priority.get("prioritize")) and int(mechanism_eligible_count) > 0
        # Under repeated stagnation with mechanism-priority enabled, lower probe
        # threshold so full gate can arbitrate near-miss mechanism trials
        # instead of looping on quick-gate score ties.
        if (
            isinstance(last_reason, str)
            and last_reason in {"quick_gate_no_improvement", "full_gate_fail"}
            and prioritize_mechanism_probe
        ):
            target_probe_streak = 2 if last_reason == "quick_gate_no_improvement" else 4
            no_improve_probe_streak = min(no_improve_probe_streak, int(target_probe_streak))
        # Persistent deadlock should probe earlier even when the latest reason
        # is not explicitly no-improvement.
        if int(trailing_deadlock_count) >= 2:
            no_improve_probe_streak = min(no_improve_probe_streak, 3)
        forced_probe_diag = _select_forced_probe_candidate(
            candidate_rows=candidate_diagnostics,
            active_quick_score=active_quick_score,
            no_improve_streak=no_improve_streak_before,
            trailing_deadlock=trailing_deadlock_count,
            last_reason=last_reason,
            quick_guard_enabled=quick_guard_enabled,
            probe_streak=forced_probe_streak,
            probe_deadlock=forced_probe_deadlock,
            raw_margin=forced_probe_raw_margin,
        )
        # Under repeated no-improve loops, quick-score ties from knob-only
        # candidates can block mechanism exploration even when an eligible
        # mechanism is very close in score. Prefer probing that mechanism.
        best_overall_is_mechanism = bool(isinstance(best_overall, dict) and best_overall.get("kind") == "mechanism")
        top_non_mechanism_behavior_flat = 0
        if math.isfinite(best_overall_quick_score):
            for row in candidate_diagnostics:
                row_score = _as_float(row.get("quick_score"))
                if not (isinstance(row_score, float) and math.isfinite(row_score)):
                    continue
                if abs(float(row_score) - float(best_overall_quick_score)) > 1e-9:
                    continue
                if row.get("kind") == "mechanism":
                    continue
                if bool(row.get("behavior_pass")):
                    continue
                top_non_mechanism_behavior_flat += 1
        best_trial_name = best_trial.get("name") if isinstance(best_trial, dict) else None
        best_trial_is_mechanism = bool(isinstance(best_trial, dict) and best_trial.get("kind") == "mechanism")
        should_prefer_mechanism_probe = bool(
            bool(mechanism_priority.get("prioritize"))
            and int(no_improve_streak_before) >= 2
            and best_trial_is_mechanism
            and isinstance(best_trial_name, str)
            and isinstance(best_trial_raw_quick_score, float)
            and math.isfinite(best_trial_raw_quick_score)
            and math.isfinite(best_overall_quick_score)
            and not best_overall_is_mechanism
            and top_non_mechanism_behavior_flat >= 2
            and best_trial_raw_quick_score >= (float(best_overall_quick_score) - float(forced_probe_raw_margin))
        )
        if should_prefer_mechanism_probe:
            for row in candidate_diagnostics:
                if row.get("name") != best_trial_name or not bool(row.get("eligible")):
                    continue
                forced_probe_diag = dict(row)
                forced_probe_diag["probe_override_reason"] = "stagnation_top_tie_behavior_flat"
                break
        forced_probe: dict[str, Any] | None = None
        if isinstance(forced_probe_diag, dict):
            forced_probe_name = forced_probe_diag.get("name")
            if isinstance(forced_probe_name, str):
                candidate_ref = candidate_contexts.get(forced_probe_name)
                if isinstance(candidate_ref, dict):
                    forced_probe = candidate_ref

        full_eval_candidate: dict[str, Any] | None = None
        full_eval_mode = "none"
        if best_trial is None:
            if (not action_ticket_pass) and (not isinstance(effective_action_plan, dict)):
                state["no_improve_streak"] = int(state.get("no_improve_streak", 0)) + 1
                quick_gate_reason = "llm_action_gate_fail"
                note = f"llm action gate fail ({action_ticket.get('reason')})"
            elif isinstance(forced_probe, dict):
                full_eval_candidate = forced_probe
                full_eval_mode = "probe"
                quick_gate_reason = "quick_gate_probe_full_eval"
                note = f"quick gate probe selected ({forced_probe.get('name')}) after no eligible candidate"
            else:
                state["no_improve_streak"] = int(state.get("no_improve_streak", 0)) + 1
                if runtime_pass_count == 0:
                    quick_gate_reason = "quick_gate_runtime_error"
                    note = "quick gate runtime error (all trial quick batches failed)"
                elif ante_integrity_pass_count == 0:
                    quick_gate_reason = "quick_gate_forced_bet_integrity_fail"
                    note = "quick gate forced-bet integrity fail"
                elif spot_gate_applicable_count > 0 and spot_gate_pass_count == 0:
                    quick_gate_reason = "quick_gate_spot_no_effect"
                    note = "quick gate spot no effect"
                elif quick_guard_enabled and support_pass_count == 0:
                    quick_gate_reason = "quick_gate_low_focus_support"
                    note = "quick gate low focus support"
                elif quick_guard_enabled and behavior_pass_count == 0:
                    quick_gate_reason = "quick_gate_no_behavior_delta"
                    note = "quick gate no behavior delta"
                elif (
                    ante_integrity_pass_count > 0
                    and (not quick_guard_enabled or support_pass_count > 0)
                    and (not quick_guard_enabled or behavior_pass_count > 0)
                    and quick_regression_pass_count == 0
                ):
                    quick_gate_reason = "quick_gate_quick_regression"
                    note = "quick gate regression guard"
                else:
                    quick_gate_reason = "quick_gate_no_eligible_candidate"
                    note = "quick gate no eligible candidate"
        elif ranked_delta_pass and raw_floor_pass:
            full_eval_candidate = best_trial
            full_eval_mode = "standard"
            quick_gate_reason = "quick_gate_pass"
        elif ranked_delta_pass and (not raw_floor_pass):
            if isinstance(forced_probe, dict):
                full_eval_candidate = forced_probe
                full_eval_mode = "probe"
                quick_gate_reason = "quick_gate_probe_full_eval"
                note = (
                    "quick gate probe selected after ranked-only blocked "
                    f"(trial_raw={best_trial_raw_quick_score}, active_raw={active_quick_score}, "
                    f"raw_floor_margin={raw_promotion_margin})"
                )
            else:
                state["no_improve_streak"] = int(state.get("no_improve_streak", 0)) + 1
                quick_gate_reason = "quick_gate_ranked_only_blocked"
                note = (
                    "quick gate ranked-only blocked "
                    f"(trial_raw={best_trial_raw_quick_score}, active_raw={active_quick_score}, "
                    f"raw_floor_margin={raw_promotion_margin})"
                )
        else:
            focus_starvation_probe_enabled = bool(
                isinstance(forced_probe, dict)
                and quick_guard_enabled
                and int(support_pass_count) == 0
                and int(targeted_focus_support_hits_delta_total) <= 0
            )
            no_improve_probe_enabled = bool(
                isinstance(forced_probe, dict)
                and int(no_improve_streak_before) >= int(no_improve_probe_streak)
                and isinstance(last_reason, str)
                and last_reason in {
                    "quick_gate_no_improvement",
                    "full_gate_fail",
                    "quick_gate_low_focus_support",
                    "quick_gate_spot_no_effect",
                }
            )
            if no_improve_probe_enabled or focus_starvation_probe_enabled:
                full_eval_candidate = forced_probe
                full_eval_mode = "probe"
                quick_gate_reason = "quick_gate_probe_full_eval"
                note = (
                    "quick gate probe selected after stagnation "
                    f"(trial_raw={best_trial_raw_quick_score}, trial_rank_bonus={best_trial_rank_behavior_bonus}, "
                    f"active_raw={active_quick_score}, "
                    f"ranked_delta_threshold={quick_min_delta_effective}, "
                    f"support_hits_delta_total={targeted_focus_support_hits_delta_total})"
                )
            else:
                state["no_improve_streak"] = int(state.get("no_improve_streak", 0)) + 1

        full_min_delta_effective = float(full_min_delta)
        full_min_delta_relaxed = False
        full_gate_diag: dict[str, Any] = {
            "mode": full_eval_mode,
            "improved": None,
            "no_regression_pass": None,
            "robust_pass": None,
            "pareto_adoptable": None,
            "focus_metric": focus_metric if isinstance(focus_metric, str) else None,
            "focus_pass": None,
            "focus_base": None,
            "focus_trial": None,
            "focus_delta": None,
            "focus_tolerance": None,
            "pareto": None,
            "holdout_phase1_required": bool(holdout_phase1_required),
            "holdout_phase2_on_promotion": bool(holdout_phase2_on_promotion),
            "holdout_regress_tolerance": float(holdout_regress_tolerance),
            "holdout_phase1_suite": holdout_phase1_suite,
            "holdout_phase2_suite": holdout_phase2_suite,
            "holdout_phase1_pass": None,
            "holdout_phase2_pass": None,
            "holdout_pass": None,
            "holdout_active_ref": None,
            "holdout_trial_ref": None,
            "holdout_context_digest": holdout_context_digest,
        }

        max_full_eval_candidates = max(1, int(args.max_full_eval_candidates))
        full_eval_candidates: list[tuple[dict[str, Any], str]] = []
        if isinstance(full_eval_candidate, dict):
            full_eval_candidates.append((full_eval_candidate, full_eval_mode))
        if max_full_eval_candidates > 1 and candidate_diagnostics:
            seen_names = {
                str(row[0].get("name"))
                for row in full_eval_candidates
                if isinstance(row[0], dict) and isinstance(row[0].get("name"), str)
            }
            if isinstance(best_targeted_probe_row, dict):
                targeted_name = best_targeted_probe_row.get("name")
                if isinstance(targeted_name, str) and targeted_name not in seen_names:
                    targeted_ctx = candidate_contexts.get(targeted_name)
                    if isinstance(targeted_ctx, dict):
                        full_eval_candidates.append((targeted_ctx, "targeted_shadow"))
                        seen_names.add(targeted_name)
            if len(full_eval_candidates) < max_full_eval_candidates:
                ranked_rows = sorted(
                    [row for row in candidate_diagnostics if bool(row.get("eligible"))],
                    key=lambda row: (
                        _as_float(row.get("quick_score_ranked"))
                        if isinstance(_as_float(row.get("quick_score_ranked")), float)
                        else float("-inf"),
                        _as_float(row.get("quick_rank_behavior_bonus"))
                        if isinstance(_as_float(row.get("quick_rank_behavior_bonus")), float)
                        else 0.0,
                        1 if row.get("kind") == "mechanism" else 0,
                    ),
                    reverse=True,
                )
                for row in ranked_rows:
                    name = row.get("name")
                    if not isinstance(name, str) or name in seen_names:
                        continue
                    ctx = candidate_contexts.get(name)
                    if not isinstance(ctx, dict):
                        continue
                    full_eval_candidates.append((ctx, "shadow"))
                    seen_names.add(name)
                    if len(full_eval_candidates) >= max_full_eval_candidates:
                        break

        full_eval_attempts: list[dict[str, Any]] = []
        if full_eval_candidates:
            final_fail_note: str | None = None
            final_fail_reason = "full_gate_fail"
            for full_eval_idx, (candidate_ref, candidate_mode) in enumerate(full_eval_candidates, start=1):
                selected_name = str(candidate_ref.get("name"))
                selected_params = candidate_ref.get("params")
                selected_spot_policy = candidate_ref.get("spot_policy")
                current_eval_mode = full_eval_mode if full_eval_idx == 1 else str(candidate_mode or "shadow")
                current_eval_mode = current_eval_mode if current_eval_mode != "none" else "shadow"
                if not isinstance(selected_params, dict):
                    full_eval_attempts.append(
                        {
                            "candidate_name": selected_name,
                            "mode": current_eval_mode,
                            "valid_payload": False,
                        }
                    )
                    final_fail_note = f"full gate skipped: invalid candidate payload ({selected_name})"
                    final_fail_reason = "quick_gate_no_eligible_candidate"
                    continue

                note_tag = f"loop selected trial {selected_name} cycle={cycle} ts={_now_ts()}"
                _materialize_policy(
                    policy_label=trial_label,
                    template_policy_spec=template_spec,
                    template_policy_params=template_pp,
                    system_params=selected_params,
                    note_tag=note_tag,
                    spot_policy=selected_spot_policy if isinstance(selected_spot_policy, dict) else None,
                )
                full_eval_root = (
                    cycle_root / "trial_full"
                    if full_eval_idx == 1
                    else cycle_root / "trial_full_shadow" / selected_name
                )
                full_trial = _full_eval(
                    policy_label=trial_label,
                    run_root=full_eval_root,
                    profile=args.profile,
                    coinpoker_scenario=args.coinpoker_scenario,
                    gg_scenario=args.gg_scenario,
                    tier_a_opponents=args.tier_a_opponents,
                    tier_p_opponents=args.tier_p_opponents,
                    pool_path=args.pool_path,
                    full_hands=args.full_hands,
                    full_seeds_json=args.full_seeds,
                    confirm_seeds_json=args.confirm_seeds,
                    jobs_total=args.jobs,
                    quick_jobs_ratio=quick_jobs_ratio,
                    quiet=args.quiet,
                    timeout_sec=args.timeout_sec,
                    heartbeat_sec=args.heartbeat_sec,
                )
                active_full_metrics = active_full if isinstance(active_full, dict) else {}
                full_score = float(full_trial.get("score", float("-inf")))
                base_score = float((active_full_metrics or {}).get("score", float("-inf")))
                full_min_delta_effective, full_min_delta_relaxed = _effective_full_min_delta(
                    base_delta=full_min_delta,
                    no_improve_streak=no_improve_streak_before,
                    recent_reasons=recent_gate_reasons,
                    mechanism_policy=mechanism_priority,
                )
                score_improved = full_score > base_score + full_min_delta_effective
                no_reg = _passes_no_regression(full_trial, active_full_metrics, regress_tolerance)
                pareto_diag = _pareto_compare(
                    candidate_metrics=full_trial,
                    baseline_metrics=active_full_metrics,
                    pareto_contract=pareto_contract,
                )
                pareto_adoptable = bool(pareto_diag.get("adoptable"))
                pareto_constraints_pass = bool((pareto_diag.get("candidate_constraints") or {}).get("pass"))
                improved = bool(pareto_adoptable)

                focus_path = focus_metric if isinstance(focus_metric, str) and focus_metric else None
                focus_tolerance = min(0.05, max(0.0, float(regress_tolerance)))
                focus_base = _metric_get(active_full_metrics, focus_path) if isinstance(focus_path, str) else None
                focus_trial = _metric_get(full_trial, focus_path) if isinstance(focus_path, str) else None
                focus_pass = True
                if isinstance(focus_base, float) and isinstance(focus_trial, float):
                    focus_pass = bool(float(focus_trial) >= float(focus_base) - focus_tolerance)
                focus_delta = (
                    float(focus_trial) - float(focus_base)
                    if isinstance(focus_base, float) and isinstance(focus_trial, float)
                    else None
                )

                holdout_phase1_result: dict[str, Any] | None = None
                holdout_phase2_result: dict[str, Any] | None = None
                holdout_phase1_pass = True
                holdout_phase2_pass = True
                holdout_pass = True
                trial_phase1_mean: float | None = None
                trial_phase2_mean: float | None = None
                active_holdout = state.get("active_holdout_metrics")
                active_holdout_valid = False
                active_phase1: dict[str, Any] | None = None
                active_phase2: dict[str, Any] | None = None
                active_phase1_mean: float | None = None
                active_phase2_mean: float | None = None
                if bool(holdout_phase1_required) and isinstance(holdout_phase1_suite, str):
                    if isinstance(active_holdout, dict):
                        cached_hash = _normalize_hash(active_holdout.get("active_options_hash"))
                        cached_holdout_context = _normalize_hash(active_holdout.get("holdout_context_digest"))
                        active_holdout_valid = bool(
                            isinstance(active_options_hash, str)
                            and cached_hash == active_options_hash.lower()
                            and isinstance(holdout_context_digest, str)
                            and cached_holdout_context == holdout_context_digest
                        )
                    if not active_holdout_valid:
                        active_holdout = {
                            "active_options_hash": active_options_hash,
                            "holdout_context_digest": holdout_context_digest,
                            "phase1": _run_holdout_suite_eval(
                                scenario=args.coinpoker_scenario,
                                profile=args.profile,
                                policy=active_policy,
                                suite=holdout_phase1_suite,
                                hands=args.full_hands,
                                seeds_json=args.full_seeds,
                                jobs=max(1, _derive_phase_jobs(int(args.jobs), 0.50, leave_headroom=True)),
                                out_dir=cycle_root / "bootstrap_active_holdout" / "phase1",
                                quiet=args.quiet,
                                timeout_sec=args.timeout_sec,
                                heartbeat_sec=args.heartbeat_sec,
                            ),
                            "phase2": None,
                        }
                        if bool(holdout_phase2_on_promotion) and isinstance(holdout_phase2_suite, str):
                            active_holdout["phase2"] = _run_holdout_suite_eval(
                                scenario=args.coinpoker_scenario,
                                profile=args.profile,
                                policy=active_policy,
                                suite=holdout_phase2_suite,
                                hands=args.full_hands,
                                seeds_json=args.full_seeds,
                                jobs=max(1, _derive_phase_jobs(int(args.jobs), 0.50, leave_headroom=True)),
                                out_dir=cycle_root / "bootstrap_active_holdout" / "phase2",
                                quiet=args.quiet,
                                timeout_sec=args.timeout_sec,
                                heartbeat_sec=args.heartbeat_sec,
                            )
                        state["active_holdout_metrics"] = active_holdout
                    active_phase1 = (
                        active_holdout.get("phase1")
                        if isinstance(active_holdout, dict) and isinstance(active_holdout.get("phase1"), dict)
                        else None
                    )
                    active_phase2 = (
                        active_holdout.get("phase2")
                        if isinstance(active_holdout, dict) and isinstance(active_holdout.get("phase2"), dict)
                        else None
                    )
                    active_phase1_mean = _as_float(active_phase1.get("mean_bb100")) if isinstance(active_phase1, dict) else None
                    active_phase2_mean = _as_float(active_phase2.get("mean_bb100")) if isinstance(active_phase2, dict) else None
                relative_promotion_preholdout = _relative_promotion_gate(
                    candidate_metrics=full_trial,
                    baseline_metrics=active_full_metrics,
                    score_improved=bool(score_improved),
                    no_regression_pass=bool(no_reg),
                    focus_pass=bool(focus_pass),
                    candidate_holdout_phase1_mean=None,
                    baseline_holdout_phase1_mean=active_phase1_mean,
                    holdout_required=False,
                    holdout_regress_tolerance=float(holdout_regress_tolerance),
                )
                should_run_holdout = bool(
                    bool(holdout_phase1_required)
                    and isinstance(holdout_phase1_suite, str)
                    and focus_pass
                    and (
                        pareto_constraints_pass
                        or bool(relative_promotion_preholdout.get("pass"))
                    )
                )

                if bool(holdout_phase1_required) and isinstance(holdout_phase1_suite, str) and not should_run_holdout:
                    holdout_phase1_pass = False
                    holdout_phase2_pass = False
                    holdout_pass = False

                if should_run_holdout:
                    holdout_phase1_result = _run_holdout_suite_eval(
                        scenario=args.coinpoker_scenario,
                        profile=args.profile,
                        policy=trial_label,
                        suite=holdout_phase1_suite,
                        hands=args.full_hands,
                        seeds_json=args.full_seeds,
                        jobs=max(1, _derive_phase_jobs(int(args.jobs), 0.50, leave_headroom=True)),
                        out_dir=full_eval_root / "holdout_phase1",
                        quiet=args.quiet,
                        timeout_sec=args.timeout_sec,
                        heartbeat_sec=args.heartbeat_sec,
                    )
                    trial_phase1_mean = (
                        _as_float(holdout_phase1_result.get("mean_bb100"))
                        if isinstance(holdout_phase1_result, dict)
                        else None
                    )
                    if isinstance(trial_phase1_mean, float):
                        if isinstance(active_phase1_mean, float):
                            holdout_phase1_pass = bool(
                                trial_phase1_mean >= active_phase1_mean - holdout_regress_tolerance
                            )
                        else:
                            holdout_phase1_pass = bool(int(holdout_phase1_result.get("returncode", 1)) == 0)
                    else:
                        holdout_phase1_pass = False

                    if holdout_phase1_pass and bool(holdout_phase2_on_promotion) and isinstance(holdout_phase2_suite, str):
                        holdout_phase2_result = _run_holdout_suite_eval(
                            scenario=args.coinpoker_scenario,
                            profile=args.profile,
                            policy=trial_label,
                            suite=holdout_phase2_suite,
                            hands=args.full_hands,
                            seeds_json=args.full_seeds,
                            jobs=max(1, _derive_phase_jobs(int(args.jobs), 0.50, leave_headroom=True)),
                            out_dir=full_eval_root / "holdout_phase2",
                            quiet=args.quiet,
                            timeout_sec=args.timeout_sec,
                            heartbeat_sec=args.heartbeat_sec,
                        )
                        trial_phase2_mean = (
                            _as_float(holdout_phase2_result.get("mean_bb100"))
                            if isinstance(holdout_phase2_result, dict)
                            else None
                        )
                        if isinstance(trial_phase2_mean, float):
                            if isinstance(active_phase2_mean, float):
                                holdout_phase2_pass = bool(
                                    trial_phase2_mean >= active_phase2_mean - holdout_regress_tolerance
                                )
                            else:
                                holdout_phase2_pass = bool(int(holdout_phase2_result.get("returncode", 1)) == 0)
                        else:
                            holdout_phase2_pass = False
                    holdout_pass = bool(holdout_phase1_pass and holdout_phase2_pass)

                robust_pass = bool(pareto_constraints_pass and holdout_pass)
                relative_promotion = _relative_promotion_gate(
                    candidate_metrics=full_trial,
                    baseline_metrics=active_full_metrics,
                    score_improved=bool(score_improved),
                    no_regression_pass=bool(no_reg),
                    focus_pass=bool(focus_pass),
                    candidate_holdout_phase1_mean=trial_phase1_mean,
                    baseline_holdout_phase1_mean=active_phase1_mean,
                    holdout_required=bool(holdout_phase1_required and isinstance(holdout_phase1_suite, str)),
                    holdout_regress_tolerance=float(holdout_regress_tolerance),
                )
                strict_adopt_pass = bool(pareto_adoptable and robust_pass and focus_pass)
                provisional_adopt_pass = bool(relative_promotion.get("pass"))
                if isinstance(full_trial, dict):
                    full_trial["holdout"] = {
                        "phase1": holdout_phase1_result,
                        "phase2": holdout_phase2_result,
                        "phase1_pass": bool(holdout_phase1_pass),
                        "phase2_pass": bool(holdout_phase2_pass),
                        "pass": bool(holdout_pass),
                        "regress_tolerance": float(holdout_regress_tolerance),
                        "context_digest": holdout_context_digest,
                    }
                    full_trial["pareto"] = pareto_diag
                    full_trial["relative_promotion"] = relative_promotion

                attempt_diag = {
                    "candidate_name": selected_name,
                    "mode": current_eval_mode,
                    "improved": bool(improved),
                    "no_regression_pass": bool(no_reg),
                    "robust_pass": bool(robust_pass),
                    "pareto_adoptable": bool(pareto_adoptable),
                    "focus_pass": bool(focus_pass),
                    "focus_delta": focus_delta,
                    "holdout_phase1_pass": bool(holdout_phase1_pass),
                    "holdout_phase2_pass": bool(holdout_phase2_pass),
                    "holdout_pass": bool(holdout_pass),
                    "full_min_delta": float(full_min_delta),
                    "full_min_delta_effective": float(full_min_delta_effective),
                    "full_min_delta_relaxed": bool(full_min_delta_relaxed),
                    "score_improved": bool(score_improved),
                    "strict_adopt_pass": bool(strict_adopt_pass),
                    "provisional_adopt_pass": bool(provisional_adopt_pass),
                    "relative_promotion_preholdout": relative_promotion_preholdout,
                    "relative_promotion": relative_promotion,
                    "pareto": pareto_diag,
                    "holdout_active_ref": (
                        state.get("active_holdout_metrics", {}).get("phase1", {}).get("summary_ref")
                        if isinstance(state.get("active_holdout_metrics"), dict)
                        else None
                    ),
                    "holdout_trial_ref": (
                        holdout_phase1_result.get("summary_ref") if isinstance(holdout_phase1_result, dict) else None
                    ),
                }
                full_eval_attempts.append(attempt_diag)
                full_gate_diag.update(attempt_diag)

                if strict_adopt_pass or provisional_adopt_pass:
                    adopt_mode = "strict" if strict_adopt_pass else "provisional"
                    prior_active_options_hash = active_options_hash_current
                    adopt_note = f"loop adopt cycle={cycle} from trial={selected_name} ts={_now_ts()}"
                    _materialize_policy(
                        policy_label=active_policy,
                        template_policy_spec=template_spec,
                        template_policy_params=template_pp,
                        system_params=selected_params,
                        note_tag=adopt_note,
                        spot_policy=selected_spot_policy if isinstance(selected_spot_policy, dict) else None,
                    )
                    adopted_sys = copy.deepcopy(selected_params)
                    adopted_sys["params_schema_id"] = LOOP_SYSTEM_PARAMS_SCHEMA_ID
                    adopted_options_hash = _normalize_hash(_canonical_digest_obj(adopted_sys).get("hex"))
                    baseline_after = _set_runtime_baseline(
                        state,
                        policy_label=active_policy,
                        policy_options_hash=adopted_options_hash or active_options_hash_current,
                        full_metrics=full_trial,
                        source=f"adopt_cycle_{cycle:03d}",
                        adopted_cycle=cycle,
                        eval_context_digest=eval_context_digest,
                        eval_context=eval_context,
                        adopt_mode=adopt_mode,
                        previous_policy_options_hash=prior_active_options_hash,
                    )
                    if isinstance(adopted_options_hash, str):
                        active_options_hash_current = adopted_options_hash
                        state["active_holdout_metrics"] = {
                            "active_options_hash": adopted_options_hash,
                            "phase1": holdout_phase1_result,
                            "phase2": holdout_phase2_result,
                            "holdout_context_digest": holdout_context_digest,
                        }
                    if adopt_mode == "provisional":
                        state["baseline_pending_confirmation"] = {
                            "policy_options_hash": adopted_options_hash or active_options_hash_current,
                            "cycle": int(cycle),
                            "candidate_name": selected_name,
                            "relative_promotion": relative_promotion,
                            "previous_policy_options_hash": prior_active_options_hash,
                            "previous_full_metrics": copy.deepcopy(active_full_metrics),
                            "previous_holdout_phase1_mean": active_phase1_mean,
                            "previous_holdout_phase2_mean": active_phase2_mean,
                            "rollback_baseline": copy.deepcopy(baseline_before),
                            "rollback_active_holdout_metrics": (
                                copy.deepcopy(state.get("active_holdout_metrics"))
                                if isinstance(state.get("active_holdout_metrics"), dict)
                                else None
                            ),
                            "rollback_policy_spec": copy.deepcopy(template_spec),
                            "rollback_policy_params": copy.deepcopy(template_pp),
                            "rollback_system_params": copy.deepcopy(base_params),
                            "rollback_no_improve_streak": int(no_improve_streak_before),
                        }
                    else:
                        state.pop("baseline_pending_confirmation", None)
                    state["no_improve_streak"] = 0
                    decision = "ADOPT"
                    note = (
                        f"full gate {current_eval_mode} {adopt_mode} pass: "
                        f"score_delta={(full_score - base_score):.3f}, "
                        f"promotion_score_delta={relative_promotion['scores']['promotion_score_delta']:.3f}, "
                        f"stability_delta={relative_promotion['scores']['stability_delta']:.3f}"
                    )
                    adopted = True
                    break

                final_fail_note = (
                    f"full gate {current_eval_mode} fail (strict_adopt={strict_adopt_pass}, "
                    f"provisional_adopt={provisional_adopt_pass}, score_delta={(full_score - base_score):.3f}, "
                    f"promotion_score_delta={relative_promotion['scores']['promotion_score_delta']:.3f}, "
                    f"stability_delta={relative_promotion['scores']['stability_delta']:.3f}, "
                    f"robust_pass={robust_pass}, focus_pass={focus_pass})"
                )
                final_fail_reason = "full_gate_fail"

            full_gate_diag["attempt_count"] = int(len(full_eval_attempts))
            full_gate_diag["attempts"] = full_eval_attempts
            if not adopted and isinstance(final_fail_note, str):
                state["no_improve_streak"] = int(state.get("no_improve_streak", 0)) + 1
                decision = "REJECT"
                note = final_fail_note
                quick_gate_reason = final_fail_reason

        quick_gate = {
            "reason": quick_gate_reason,
            "focus_metric": focus_metric if isinstance(focus_metric, str) else None,
            "focus_metric_base": base_focus_metric if isinstance(base_focus_metric, str) else None,
            "focus_metric_switched": bool(focus_metric_switched),
            "focus_control": focus_control if isinstance(focus_control, dict) else None,
            "guard_enabled": bool(quick_guard_enabled),
            "llm_action_gate": action_ticket,
            "llm_review_policy": llm_review_policy,
            "hint_overrides": quick_gate_hint_overrides if isinstance(quick_gate_hint_overrides, dict) else None,
            "thresholds": {
                "quick_min_delta": float(quick_min_delta_effective),
                "quick_min_delta_base": float(quick_min_delta),
                "quick_min_delta_relaxed": bool(quick_min_delta_relaxed),
                "full_min_delta": float(full_min_delta),
                "full_min_delta_effective": float(full_min_delta_effective),
                "full_min_delta_relaxed": bool(full_min_delta_relaxed),
                "focus_support_min_hands": int(focus_support_min_hands),
                "focus_support_min_hits": int(focus_support_min_hits),
                "behavior_delta_min": float(behavior_delta_min),
                "behavior_delta_min_effective": float(behavior_delta_min_effective),
                "quick_regression_tolerance": float(quick_regression_tolerance),
                "quick_regression_tolerance_effective": float(quick_regression_tolerance_effective),
                "quick_regression_streak_bonus": float(quick_regression_streak_bonus),
                "quick_regression_recent_full_gate_fails": int(recent_full_gate_fails),
                "behavior_bonus_cap": 2.0,
                "ranked_promotion_raw_floor_margin": float(raw_promotion_margin),
                "ranked_promotion_raw_floor_margin_base": float(base_raw_promotion_margin),
                "ranked_promotion_raw_floor_margin_escalated": bool(raw_promotion_margin_escalated),
                "no_improve_probe_streak": int(no_improve_probe_streak),
                "forced_bet_integrity_required": True,
                "llm_action_required": bool(require_llm_action_ticket),
                "llm_action_required_base": bool(require_llm_action_ticket_base),
                "llm_review_fail_open": bool(args.llm_review_fail_open),
                "max_full_eval_candidates": int(max(1, int(args.max_full_eval_candidates))),
            },
            "promotion_checks": {
                "ranked_delta_pass": bool(ranked_delta_pass),
                "ranked_delta_threshold": float(quick_min_delta_effective),
                "raw_floor_pass": bool(raw_floor_pass),
                "active_raw_quick_score": (float(active_quick_score) if math.isfinite(active_quick_score) else None),
                "best_trial_ranked_quick_score": (
                    float(best_trial_raw_quick_score + best_trial_rank_behavior_bonus)
                    if isinstance(best_trial_raw_quick_score, float)
                    and math.isfinite(best_trial_raw_quick_score)
                    and isinstance(best_trial_rank_behavior_bonus, float)
                    and math.isfinite(best_trial_rank_behavior_bonus)
                    else (
                        float(best_trial_raw_quick_score)
                        if isinstance(best_trial_raw_quick_score, float) and math.isfinite(best_trial_raw_quick_score)
                        else None
                    )
                ),
                "best_trial_raw_quick_score": (
                    float(best_trial_raw_quick_score)
                    if isinstance(best_trial_raw_quick_score, float) and math.isfinite(best_trial_raw_quick_score)
                    else None
                ),
                "best_trial_rank_behavior_bonus": (
                    float(best_trial_rank_behavior_bonus)
                    if isinstance(best_trial_rank_behavior_bonus, float) and math.isfinite(best_trial_rank_behavior_bonus)
                    else None
                ),
            },
            "stage1_coverage": {
                "required": {
                    "runtime": True,
                    "ante_integrity": True,
                    "focus_support": bool(quick_guard_enabled),
                },
                "active": {
                    "runtime_pass": bool(active_runtime_pass),
                    "ante_integrity_pass": bool(active_ante_integrity_pass),
                    "focus_support_pass": bool(active_focus_support_pass),
                },
                "candidates": {
                    "runtime_pass_count": int(runtime_pass_count),
                    "ante_integrity_pass_count": int(ante_integrity_pass_count),
                    "focus_support_pass_count": int(support_pass_count),
                    "stage1_coverage_pass_count": int(stage1_coverage_pass_count),
                    "targeted_focus_attempted_count": int(targeted_focus_attempted_count),
                    "targeted_focus_merged_count": int(targeted_focus_merged_count),
                    "targeted_focus_support_hands_delta_total": int(targeted_focus_support_hands_delta_total),
                    "targeted_focus_support_hits_delta_total": int(targeted_focus_support_hits_delta_total),
                },
                "pass": bool(stage1_coverage_any_pass),
            },
            "stage2_effect": {
                "required": {
                    "behavior_delta": bool(quick_guard_enabled),
                    "quick_regression": True,
                    "ranked_delta": True,
                    "raw_floor": True,
                },
                "candidates": {
                    "behavior_pass_count": int(behavior_pass_count),
                    "quick_regression_pass_count": int(quick_regression_pass_count),
                    "stage2_effect_pass_count": int(stage2_effect_pass_count),
                },
                "ranked": {
                    "ranked_delta_pass": bool(ranked_delta_pass),
                    "raw_floor_pass": bool(raw_floor_pass),
                },
                "pass": bool(stage2_effect_any_pass),
            },
            "forced_probe": {
                "streak_threshold": int(forced_probe_streak),
                "deadlock_threshold": int(forced_probe_deadlock),
                "raw_margin": float(forced_probe_raw_margin),
                "raw_margin_base": float(base_forced_probe_raw_margin),
                "raw_margin_escalated": bool(forced_probe_raw_margin_escalated),
                "candidate_name": forced_probe.get("name") if isinstance(forced_probe, dict) else None,
                "candidate_kind": forced_probe.get("kind") if isinstance(forced_probe, dict) else None,
                "candidate_origin": forced_probe.get("origin") if isinstance(forced_probe, dict) else None,
                "candidate_quick_score": (
                    _as_float((forced_probe.get("quick") or {}).get("score")) if isinstance(forced_probe, dict) else None
                ),
                "used_for_full_eval": bool(full_eval_mode == "probe"),
            },
            "selected_full_eval_candidate": {
                "name": full_eval_candidate.get("name") if isinstance(full_eval_candidate, dict) else None,
                "kind": full_eval_candidate.get("kind") if isinstance(full_eval_candidate, dict) else None,
                "origin": full_eval_candidate.get("origin") if isinstance(full_eval_candidate, dict) else None,
                "spot_policy_variant": (
                    bool(full_eval_candidate.get("spot_policy_variant")) if isinstance(full_eval_candidate, dict) else None
                ),
                "quick_score": (
                    _as_float((full_eval_candidate.get("quick") or {}).get("score"))
                    if isinstance(full_eval_candidate, dict)
                    else None
                ),
                "mode": full_eval_mode,
            },
            "full_gate": full_gate_diag,
            "active_support": active_focus_support,
            "active_support_eval": active_focus_support_eval,
            "active_support_pass": bool(active_focus_support_pass),
            "active_targeted_focus": active_targeted_focus,
            "active_ante_integrity": active_ante_integrity,
            "active_ante_integrity_pass": bool(active_ante_integrity_pass),
            "active_runtime": active_runtime,
            "active_runtime_pass": bool(active_runtime_pass),
            "stagnation_escape_applied": bool(stagnation_escape_applied),
            "candidate_behavior_escalation_factor": float(candidate_behavior_escalation_factor),
            "candidate_behavior_escalation_requested": (
                float(candidate_behavior_escalation_requested)
                if isinstance(candidate_behavior_escalation_requested, float)
                else None
            ),
            "candidate_behavior_escalation_auto": float(candidate_behavior_escalation_auto),
            "candidate_behavior_escalation_auto_applied": bool(candidate_behavior_escalation_auto_applied),
            "candidate_behavior_deadlock_trailing": int(trailing_deadlock_count),
            "mechanism_priority": mechanism_priority,
            "no_improve_streak_before_cycle": int(no_improve_streak_before),
            "candidate_count": int(len(candidate_diagnostics)),
            "mechanism_candidate_count": int(mechanism_candidate_count),
            "knob_candidate_count": int(knob_candidate_count),
            "spot_policy_candidate_count": int(spot_policy_candidate_count),
            "candidate_origin_counts": candidate_origin_counts,
            "support_pass_count": int(support_pass_count),
            "behavior_pass_count": int(behavior_pass_count),
            "behavior_bonus_count": int(behavior_bonus_count),
            "ante_integrity_pass_count": int(ante_integrity_pass_count),
            "runtime_pass_count": int(runtime_pass_count),
            "runtime_fail_count": int(runtime_fail_count),
            "quick_regression_pass_count": int(quick_regression_pass_count),
            "spot_gate_applicable_count": int(spot_gate_applicable_count),
            "spot_gate_pass_count": int(spot_gate_pass_count),
            "stage1_coverage_pass_count": int(stage1_coverage_pass_count),
            "stage2_effect_pass_count": int(stage2_effect_pass_count),
            "targeted_focus_attempted_count": int(targeted_focus_attempted_count),
            "targeted_focus_merged_count": int(targeted_focus_merged_count),
            "targeted_focus_support_hands_delta_total": int(targeted_focus_support_hands_delta_total),
            "targeted_focus_support_hits_delta_total": int(targeted_focus_support_hits_delta_total),
            "eligible_count": int(eligible_count),
            "mechanism_eligible_count": int(mechanism_eligible_count),
            "excluded_recent_hashes": int(len(excluded_option_hashes)),
            "recent_option_hash_window": int(DEFAULT_RECENT_OPTION_HASH_WINDOW),
            "best_overall_candidate": {
                "name": best_overall.get("name"),
                "kind": best_overall.get("kind"),
                "origin": best_overall.get("origin"),
                "mechanism": best_overall.get("mechanism"),
                "spot_policy_variant": bool(best_overall.get("spot_policy_variant")),
                "quick_score": _as_float((best_overall.get("quick") or {}).get("score")),
            }
            if isinstance(best_overall, dict)
            else None,
            "best_targeted_candidate": {
                "name": best_targeted_probe_row.get("name"),
                "kind": best_targeted_probe_row.get("kind"),
                "origin": best_targeted_probe_row.get("origin"),
                "mechanism": best_targeted_probe_row.get("mechanism"),
                "spot_policy_variant": bool(best_targeted_probe_row.get("spot_policy_variant")),
                "quick_score": _as_float(best_targeted_probe_row.get("quick_score")),
                "focus_metric_delta": _as_float(best_targeted_probe_row.get("focus_metric_delta")),
                "support_hits_delta": _as_int(best_targeted_probe_row.get("targeted_focus_support_hits_delta")),
                "support_hands_delta": _as_int(best_targeted_probe_row.get("targeted_focus_support_hands_delta")),
            }
            if isinstance(best_targeted_probe_row, dict)
            else None,
            "candidates": candidate_diagnostics,
        }

        _append_recent_option_hashes(
            state,
            candidate_option_hashes,
            window=DEFAULT_RECENT_OPTION_HASH_WINDOW,
        )

        baseline_after_state = _runtime_baseline_from_state(
            state,
            active_options_hash=active_options_hash_current,
            expected_eval_context_digest=eval_context_digest,
        )
        if not isinstance(baseline_after_state, dict):
            fallback_full_metrics = (
                baseline_after.get("full_metrics")
                if isinstance(baseline_after, dict) and isinstance(baseline_after.get("full_metrics"), dict)
                else (active_full if isinstance(active_full, dict) else {})
            )
            baseline_after_state = _set_runtime_baseline(
                state,
                policy_label=active_policy,
                policy_options_hash=active_options_hash_current,
                full_metrics=fallback_full_metrics,
                source="baseline_after_repair",
                adopted_cycle=(
                    _as_int((baseline_after or {}).get("adopted_cycle"))
                    if isinstance(baseline_after, dict)
                    else _as_int(state.get("last_cycle"))
                ),
                eval_context_digest=eval_context_digest,
                eval_context=eval_context,
            )
        baseline_after = copy.deepcopy(baseline_after_state)
        active_full_now = (
            baseline_after_state.get("full_metrics")
            if isinstance(baseline_after_state.get("full_metrics"), dict)
            else {}
        )
        baseline_before_summary = _runtime_baseline_summary(baseline_before)
        baseline_after_summary = _runtime_baseline_summary(baseline_after)
        if isinstance(active_full_now, dict):
            target_achieved = _target_met(
                active_full_now,
                goal_pack["target_gates"],
                goal_pack.get("robust_gates"),
            )
        pareto_archive_summary: dict[str, Any] | None = None
        if isinstance(active_full_now, dict):
            pareto_entries: list[dict[str, Any]] = []
            active_vec = _pareto_vector(active_full_now, pareto_contract["objectives"])
            active_constraints = _pareto_eval_constraints(active_full_now, pareto_contract["hard_constraints"])
            active_hv = (
                _pareto_hypervolume(active_vec["values"], pareto_contract["objectives"])
                if bool(active_vec.get("complete"))
                else None
            )
            pareto_entries.append(
                {
                    "cycle": int(cycle),
                    "label": "active_after_cycle",
                    "decision": decision,
                    "policy_label": active_policy,
                    "policy_options_hash": _normalize_hash(active_options_hash_current),
                    "vector": active_vec["values"],
                    "vector_complete": bool(active_vec.get("complete")),
                    "constraints_pass": bool(active_constraints.get("pass")),
                    "hv": active_hv,
                    "source_ref": baseline_after_summary.get("source"),
                }
            )
            if isinstance(full_trial, dict):
                trial_vec = _pareto_vector(full_trial, pareto_contract["objectives"])
                trial_constraints = _pareto_eval_constraints(full_trial, pareto_contract["hard_constraints"])
                trial_hv = (
                    _pareto_hypervolume(trial_vec["values"], pareto_contract["objectives"])
                    if bool(trial_vec.get("complete"))
                    else None
                )
                pareto_entries.append(
                    {
                        "cycle": int(cycle),
                        "label": "trial_candidate",
                        "decision": decision,
                        "policy_label": trial_label,
                        "policy_options_hash": _normalize_hash(
                            _canonical_digest_obj(selected_params).get("hex")
                        )
                        if isinstance(selected_params, dict)
                        else None,
                        "vector": trial_vec["values"],
                        "vector_complete": bool(trial_vec.get("complete")),
                        "constraints_pass": bool(trial_constraints.get("pass")),
                        "hv": trial_hv,
                        "source_ref": f"path:{(cycle_root / 'trial_full').resolve()}",
                    }
                )
            pareto_archive_summary = _pareto_archive_update(
                state=state,
                pareto_contract=pareto_contract,
                entries=pareto_entries,
            )

        review = _build_cycle_review(
            cycle=cycle,
            decision=decision,
            goal_pack=goal_pack,
            promotion_gates={
                "quick_min_delta": quick_min_delta,
                "full_min_delta": full_min_delta,
                "regress_tolerance": regress_tolerance,
                "holdout_regress_tolerance": holdout_regress_tolerance,
                "holdout_phase1_required": holdout_phase1_required,
                "holdout_phase2_on_promotion": holdout_phase2_on_promotion,
            },
            baseline_before=baseline_before,
            baseline_after=baseline_after,
            active_metrics=active_full_now if isinstance(active_full_now, dict) else {},
            full_trial=full_trial,
            best_trial=best_trial,
            active_quick=active_quick,
            quick_gate=quick_gate,
            next_action_meta=next_action_meta,
        )
        review_path = cycle_root / "review.json"
        _json_dump(review_path, review)
        state["next_hypothesis"] = review.get("next_hypothesis")

        state["last_cycle"] = cycle
        state["cycle"] = None
        state["phase"] = None
        state["status"] = None
        state["current_run_dir"] = None
        state["updated_at"] = _now_ts()
        state["target_achieved"] = bool(target_achieved)
        state["last_quick_gate_reason"] = quick_gate_reason
        state["last_mechanism_priority"] = mechanism_priority
        history_rows = state.get("quick_gate_reason_history")
        if not isinstance(history_rows, list):
            history_rows = []
        history_rows = [row for row in history_rows if isinstance(row, str) and row]
        history_rows.append(str(quick_gate_reason))
        state["quick_gate_reason_history"] = history_rows[-24:]
        updated_focus_control = _update_focus_control_after_cycle(
            state=state,
            base_focus_metric=base_focus_metric if isinstance(base_focus_metric, str) else None,
            active_focus_metric=focus_metric if isinstance(focus_metric, str) else None,
            quick_gate_reason=quick_gate_reason,
            quick_gate=quick_gate if isinstance(quick_gate, dict) else None,
            decision=decision,
        )
        if isinstance(updated_focus_control, dict):
            state["focus_control"] = updated_focus_control
        _save_state(state_path, state)

        refs = {
            "coin": (
                (full_trial or {}).get("coinpoker", {}).get("summary_ref")
                if adopted or full_trial is not None
                else (active_full_now.get("coinpoker") or {}).get("summary_ref")
            )
            or "null",
            "pool": f"path:{(cycle_root / 'trial_full' / 'coinpoker_full' / 'pool_eval' / 'pool_eval_summary.json').resolve()}"
            if full_trial is not None
            else "null",
            "br": f"path:{(cycle_root / 'trial_full' / 'coinpoker_full' / 'br_proxy' / 'br_proxy_summary.json').resolve()}"
            if full_trial is not None
            else "null",
        }
        _append_journal_entry(
            cycle=cycle,
            decision=decision,
            baseline_label=baseline_before_summary.get("policy_label"),
            baseline_cycle=baseline_before_summary.get("adopted_cycle"),
            active_policy=active_policy,
            trial_policy=trial_label if best_trial is not None else None,
            refs=refs,
            note=note,
            review_ref=f"path:{review_path.resolve()}",
            next_hypothesis=review.get("next_hypothesis") if isinstance(review, dict) else {},
        )

        result = {
            "cycle": cycle,
            "decision": decision,
            "note": note,
            "target_achieved": bool(target_achieved),
            "goal_pack_ref": f"path:{goal_pack.get('path')}",
            "promotion_gates": {
                "quick_min_delta": quick_min_delta,
                "full_min_delta": full_min_delta,
                "regress_tolerance": regress_tolerance,
                "holdout_regress_tolerance": holdout_regress_tolerance,
                "holdout_phase1_required": holdout_phase1_required,
                "holdout_phase2_on_promotion": holdout_phase2_on_promotion,
            },
            "execution_controls": {
                "timeout_sec": float(args.timeout_sec) if isinstance(args.timeout_sec, (int, float)) else None,
                "heartbeat_sec": float(args.heartbeat_sec) if isinstance(args.heartbeat_sec, (int, float)) else None,
                "jobs_total": int(args.jobs),
                "quick_jobs_ratio": float(quick_jobs_ratio),
                "quick_jobs": int(quick_jobs),
                "max_candidates": int(args.max_candidates),
                "max_full_eval_candidates": int(args.max_full_eval_candidates),
                "focus_support_min_hands": int(args.focus_support_min_hands),
                "focus_support_min_hits": int(args.focus_support_min_hits),
                "behavior_delta_min": float(args.behavior_delta_min),
                "quick_regression_tolerance": float(args.quick_regression_tolerance),
                "mechanism_min_share": float(args.mechanism_min_share),
                "mechanism_priority_streak": int(args.mechanism_priority_streak),
                "mechanism_only_streak": int(args.mechanism_only_streak),
                "force_full_probe_streak": int(args.force_full_probe_streak),
                "force_full_probe_deadlock": int(args.force_full_probe_deadlock),
                "force_full_probe_raw_margin": float(args.force_full_probe_raw_margin),
                "llm_review_full_gate_fail_streak": int(args.llm_review_full_gate_fail_streak),
                "llm_review_min_no_improve_streak": int(args.llm_review_min_no_improve_streak),
                "llm_review_fail_open": bool(args.llm_review_fail_open),
                "holdout_phase1_required": bool(holdout_phase1_required),
                "holdout_phase2_on_promotion": bool(holdout_phase2_on_promotion),
                "holdout_regress_tolerance": float(holdout_regress_tolerance),
                "require_llm_action_ticket": bool(require_llm_action_ticket),
                "require_llm_action_ticket_base": bool(require_llm_action_ticket_base),
                "baseline_integrity_auto_repair": bool(baseline_integrity_auto_repair),
            },
            "active_policy": active_policy,
            "baseline": {
                "before": baseline_before_summary,
                "after": baseline_after_summary,
            },
            "active_quick": active_quick,
            "quick_gate": quick_gate,
            "llm_review_policy": llm_review_policy,
            "best_trial": best_trial,
            "trial_full": full_trial,
            "active_full_metrics": active_full_now if isinstance(active_full_now, dict) else {},
            "next_action": next_action_meta,
            "pareto_contract": {
                "path": pareto_contract.get("path"),
                "digest": pareto_contract.get("digest"),
                "schema_id": pareto_contract.get("schema_id"),
            },
            "pareto_archive": pareto_archive_summary,
            "no_improve_streak": int(state.get("no_improve_streak", 0)),
            "next_hypothesis": review.get("next_hypothesis") if isinstance(review, dict) else None,
            "baseline_integrity": baseline_integrity,
            "review_ref": f"path:{review_path.resolve()}",
            "run_root": str(cycle_root),
        }
        result_path = cycle_root / "cycle_result.json"
        _json_dump(result_path, result)
        _append_trace_event(
            status="trace",
            reason="cycle_end",
            cycle=cycle,
            payload={
                "decision": decision,
                "note": note,
                "quick_gate_reason": quick_gate_reason,
                "review_ref": f"path:{review_path.resolve()}",
                "result_ref": f"path:{result_path.resolve()}",
                "no_improve_streak": int(state.get("no_improve_streak", 0)),
                "target_achieved": bool(target_achieved),
            },
        )
        print(json.dumps({"status": "ok", "cycle": cycle, "decision": decision, "result_ref": f"path:{result_path.resolve()}"}))
        return 0
    finally:
        _release_file_lock(cycle_lock_path)


def _run_parent(args: argparse.Namespace) -> int:
    state_path = Path(args.state_file)
    runs_root = Path(args.runs_root)
    runs_root.mkdir(parents=True, exist_ok=True)
    parent_lock_path = Path(str(state_path) + ".parent.lock")
    parent_lock_ok, parent_owner = _acquire_file_lock(parent_lock_path, stale_sec=LOCK_STALE_SEC_DEFAULT)
    if not parent_lock_ok:
        print(
            json.dumps(
                {
                    "status": "stop",
                    "cycle": int(_load_state(state_path).get("last_cycle", 0) or 0),
                    "reason": "parent_lock_held",
                    "lock_ref": f"path:{parent_lock_path.resolve()}",
                    "owner": parent_owner,
                }
            )
        )
        return 0

    try:
        state_boot = _load_state(state_path)
        if bool(state_boot.get("target_achieved", False)):
            print(json.dumps({"status": "stop", "cycle": int(state_boot.get("last_cycle", 0) or 0), "reason": "target_achieved"}))
            return 0

        max_cycles = int(args.max_cycles)
        start_cycle = int(args.start_cycle)
        if not bool(args.no_resume_from_state):
            last_cycle = state_boot.get("last_cycle")
            if isinstance(last_cycle, int) and last_cycle >= 1:
                start_cycle = max(start_cycle, int(last_cycle) + 1)
        if start_cycle > max_cycles:
            print(json.dumps({"status": "stop", "cycle": max_cycles, "reason": "max_cycles"}))
            return 0

        chunk_cycles = max(1, int(args.chunk_cycles))
        end_cycle = min(max_cycles, start_cycle + chunk_cycles - 1)
        no_improve_stop = int(args.stop_no_improve)
        cycle_lock_retries = max(1, int(args.cycle_lock_retries))
        worker_fail_retries = max(0, int(args.worker_fail_retries))
        for cycle in range(start_cycle, end_cycle + 1):
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--cycle",
                str(cycle),
                "--state-file",
                str(state_path),
                "--runs-root",
                str(runs_root),
                "--source-baseline-policy",
                args.source_baseline_policy,
                "--active-policy",
                args.active_policy,
                "--trial-policy",
                args.trial_policy,
                "--profile",
                args.profile,
                "--coinpoker-scenario",
                args.coinpoker_scenario,
                "--gg-scenario",
                args.gg_scenario,
                "--tier-a-opponents",
                args.tier_a_opponents,
                "--tier-p-opponents",
                args.tier_p_opponents,
                "--pool-path",
                args.pool_path,
                "--goal-pack",
                args.goal_pack,
                "--pareto-contract",
                args.pareto_contract,
                "--quick-hands",
                str(args.quick_hands),
                "--quick-seeds",
                args.quick_seeds,
                "--full-hands",
                str(args.full_hands),
                "--full-seeds",
                args.full_seeds,
                "--confirm-seeds",
                args.confirm_seeds,
                "--jobs",
                str(args.jobs),
            ]
            if isinstance(args.timeout_sec, (int, float)):
                cmd.extend(["--timeout-sec", str(float(args.timeout_sec))])
            if isinstance(args.heartbeat_sec, (int, float)):
                cmd.extend(["--heartbeat-sec", str(float(args.heartbeat_sec))])
            if args.quick_min_delta is not None:
                cmd.extend(["--quick-min-delta", str(args.quick_min_delta)])
            if args.full_min_delta is not None:
                cmd.extend(["--full-min-delta", str(args.full_min_delta)])
            if args.regress_tolerance is not None:
                cmd.extend(["--regress-tolerance", str(args.regress_tolerance)])
            if args.focus_support_min_hands is not None:
                cmd.extend(["--focus-support-min-hands", str(args.focus_support_min_hands)])
            if args.focus_support_min_hits is not None:
                cmd.extend(["--focus-support-min-hits", str(args.focus_support_min_hits)])
            if args.behavior_delta_min is not None:
                cmd.extend(["--behavior-delta-min", str(args.behavior_delta_min)])
            if args.quick_regression_tolerance is not None:
                cmd.extend(["--quick-regression-tolerance", str(args.quick_regression_tolerance)])
            if args.quick_jobs_ratio is not None:
                cmd.extend(["--quick-jobs-ratio", str(args.quick_jobs_ratio)])
            if args.max_candidates is not None:
                cmd.extend(["--max-candidates", str(args.max_candidates)])
            if args.max_full_eval_candidates is not None:
                cmd.extend(["--max-full-eval-candidates", str(args.max_full_eval_candidates)])
            if args.mechanism_min_share is not None:
                cmd.extend(["--mechanism-min-share", str(args.mechanism_min_share)])
            if args.mechanism_priority_streak is not None:
                cmd.extend(["--mechanism-priority-streak", str(args.mechanism_priority_streak)])
            if args.mechanism_only_streak is not None:
                cmd.extend(["--mechanism-only-streak", str(args.mechanism_only_streak)])
            if args.force_full_probe_streak is not None:
                cmd.extend(["--force-full-probe-streak", str(args.force_full_probe_streak)])
            if args.force_full_probe_deadlock is not None:
                cmd.extend(["--force-full-probe-deadlock", str(args.force_full_probe_deadlock)])
            if args.force_full_probe_raw_margin is not None:
                cmd.extend(["--force-full-probe-raw-margin", str(args.force_full_probe_raw_margin)])
            if args.llm_review_full_gate_fail_streak is not None:
                cmd.extend(["--llm-review-full-gate-fail-streak", str(args.llm_review_full_gate_fail_streak)])
            if args.llm_review_min_no_improve_streak is not None:
                cmd.extend(["--llm-review-min-no-improve-streak", str(args.llm_review_min_no_improve_streak)])
            if bool(args.llm_review_fail_open):
                cmd.append("--llm-review-fail-open")
            if not bool(args.require_llm_action_ticket):
                cmd.append("--no-require-llm-action-ticket")
            if not bool(args.baseline_integrity_auto_repair):
                cmd.append("--no-baseline-integrity-auto-repair")
            if args.quiet:
                cmd.append("--quiet")

            cycle_log = runs_root / f"cycle_{cycle:03d}.parent.log"
            lock_retry_count = 0
            worker_fail_retry_count = 0
            while True:
                rc = _run_cmd(cmd, log_path=cycle_log)
                if rc == 0:
                    worker_reason = _extract_reason_from_log(cycle_log)
                    if worker_reason == "needs_manual_hypothesis":
                        print(
                            json.dumps(
                                {
                                    "status": "stop",
                                    "cycle": cycle,
                                    "reason": "needs_manual_hypothesis",
                                    "log_ref": f"path:{cycle_log.resolve()}",
                                }
                            )
                        )
                        return 0
                    break
                worker_reason = _extract_reason_from_log(cycle_log)
                if rc == LOCK_HELD_EXIT_CODE and worker_reason == "cycle_lock_held":
                    lock_retry_count += 1
                    if lock_retry_count > cycle_lock_retries:
                        print(
                            json.dumps(
                                {
                                    "status": "error",
                                    "cycle": cycle,
                                    "reason": "cycle_lock_retry_exhausted",
                                    "retry_count": lock_retry_count,
                                    "log_ref": f"path:{cycle_log.resolve()}",
                                }
                            )
                        )
                        return rc
                    # Wait for in-flight worker on the same cycle to complete.
                    time.sleep(min(30, 2 * lock_retry_count))
                    continue
                if rc == LOCK_HELD_EXIT_CODE and worker_reason == "awaiting_llm_action":
                    action_sig = _next_action_file_signature(NEXT_ACTION_PATH)
                    if isinstance(args.heartbeat_sec, (int, float)) and float(args.heartbeat_sec) > 0:
                        wait_timeout = max(30.0, min(900.0, float(args.heartbeat_sec) * 8.0))
                    else:
                        wait_timeout = 240.0
                    wait_diag = _wait_for_valid_action_ticket(
                        action_path=NEXT_ACTION_PATH,
                        cycle=cycle,
                        timeout_sec=wait_timeout,
                        poll_sec=2.0,
                        baseline_signature=action_sig,
                    )
                    _append_trace_event(
                        status="trace",
                        reason="awaiting_llm_action_wait",
                        cycle=cycle,
                        payload={
                            "timeout_sec": float(wait_timeout),
                            "ready": bool(wait_diag.get("ready")),
                            "checks": int(_as_int(wait_diag.get("checks")) or 0),
                            "ticket_reason": wait_diag.get("ticket_reason"),
                            "signature_changed": bool(wait_diag.get("signature_changed")),
                        },
                    )
                    continue
                if worker_fail_retry_count < worker_fail_retries:
                    worker_fail_retry_count += 1
                    _append_trace_event(
                        status="trace",
                        reason="worker_retry_after_failure",
                        cycle=cycle,
                        payload={
                            "rc": int(rc),
                            "worker_reason": worker_reason,
                            "retry_count": int(worker_fail_retry_count),
                            "max_retries": int(worker_fail_retries),
                            "log_ref": f"path:{cycle_log.resolve()}",
                        },
                    )
                    time.sleep(min(20, 5 * worker_fail_retry_count))
                    continue
                # Convert repeated worker failures into a controlled stop so the supervisor
                # can hand control to hook automation instead of entering restart storms.
                _append_trace_event(
                    status="trace",
                    reason="worker_failed_or_unexpected_exit",
                    cycle=cycle,
                    payload={
                        "rc": int(rc),
                        "worker_reason": worker_reason,
                        "retry_count": int(worker_fail_retry_count),
                        "max_retries": int(worker_fail_retries),
                        "log_ref": f"path:{cycle_log.resolve()}",
                    },
                )
                print(
                    json.dumps(
                        {
                            "status": "stop",
                            "cycle": cycle,
                            "reason": "worker_failed_or_unexpected_exit",
                            "returncode": int(rc),
                            "worker_reason": worker_reason,
                            "retry_count": int(worker_fail_retry_count),
                            "max_retries": int(worker_fail_retries),
                            "log_ref": f"path:{cycle_log.resolve()}",
                        }
                    )
                )
                return 0

            state = _load_state(state_path)
            if bool(state.get("target_achieved", False)):
                print(json.dumps({"status": "stop", "cycle": cycle, "reason": "target_achieved"}))
                return 0
            if int(state.get("no_improve_streak", 0)) >= no_improve_stop:
                print(json.dumps({"status": "stop", "cycle": cycle, "reason": "no_improve_limit"}))
                return 0
        if end_cycle < max_cycles:
            print(json.dumps({"status": "stop", "cycle": end_cycle, "reason": "chunk_checkpoint", "next_cycle": end_cycle + 1}))
            return 0
        print(json.dumps({"status": "stop", "cycle": max_cycles, "reason": "max_cycles"}))
        return 0
    finally:
        _release_file_lock(parent_lock_path)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ralph Wiggum loop runner (continuous optimize/evaluate/compare).")
    p.add_argument("--worker", action="store_true", help="Run one isolated cycle worker process")
    p.add_argument("--cycle", type=int, default=1)
    p.add_argument("--start-cycle", type=int, default=1)
    p.add_argument("--max-cycles", type=int, default=6)
    p.add_argument("--chunk-cycles", type=int, default=6)
    p.add_argument("--state-file", default=str(ROOT / "tmp" / "ralph_loop_state.json"))
    p.add_argument("--runs-root", default=str(ROOT / "tmp" / "ralph_loop_runs"))

    p.add_argument("--source-baseline-policy", default=DEFAULT_BASELINE_LABEL)
    p.add_argument("--active-policy", default=DEFAULT_ACTIVE_LABEL)
    p.add_argument("--trial-policy", default=DEFAULT_TRIAL_LABEL)
    p.add_argument("--profile", default=DEFAULT_PROFILE)
    p.add_argument("--coinpoker-scenario", default=DEFAULT_COINPOKER_SCENARIO)
    p.add_argument("--gg-scenario", default=DEFAULT_GG_SCENARIO)
    p.add_argument("--tier-a-opponents", default=DEFAULT_TIER_A)
    p.add_argument("--tier-p-opponents", default=DEFAULT_TIER_P)
    p.add_argument("--pool-path", default=DEFAULT_POOL)
    p.add_argument("--goal-pack", default=DEFAULT_GOAL_PACK)
    p.add_argument("--pareto-contract", default=DEFAULT_PARETO_CONTRACT)

    p.add_argument("--quick-hands", type=int, default=600)
    p.add_argument("--quick-seeds", default="[3000,3001,3002,3003]")
    p.add_argument("--full-hands", type=int, default=1600)
    p.add_argument("--full-seeds", default="[2000,2001,2002,2003]")
    p.add_argument("--confirm-seeds", default="[2010,2011,2012,2013]")
    p.add_argument("--jobs", type=int, default=max(1, min(8, int(os.cpu_count() or 4))))
    p.add_argument("--timeout-sec", type=float, default=5400.0)
    p.add_argument("--heartbeat-sec", type=float, default=120.0)

    p.add_argument("--quick-min-delta", type=float, default=None)
    p.add_argument("--full-min-delta", type=float, default=None)
    p.add_argument("--regress-tolerance", type=float, default=None)
    p.add_argument("--focus-support-min-hands", type=int, default=DEFAULT_FOCUS_SUPPORT_MIN_HANDS)
    p.add_argument("--focus-support-min-hits", type=int, default=DEFAULT_FOCUS_SUPPORT_MIN_HITS)
    p.add_argument("--behavior-delta-min", type=float, default=DEFAULT_BEHAVIOR_DELTA_MIN)
    p.add_argument("--quick-regression-tolerance", type=float, default=DEFAULT_QUICK_REGRESSION_TOLERANCE)
    p.add_argument("--quick-jobs-ratio", type=float, default=DEFAULT_QUICK_JOBS_RATIO)
    p.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    p.add_argument("--max-full-eval-candidates", type=int, default=DEFAULT_MAX_FULL_EVAL_CANDIDATES)
    p.add_argument("--mechanism-min-share", type=float, default=DEFAULT_MECHANISM_MIN_SHARE)
    p.add_argument("--mechanism-priority-streak", type=int, default=DEFAULT_MECHANISM_PRIORITY_STREAK)
    p.add_argument("--mechanism-only-streak", type=int, default=DEFAULT_MECHANISM_ONLY_STREAK)
    p.add_argument("--force-full-probe-streak", type=int, default=DEFAULT_FORCE_FULL_PROBE_STREAK)
    p.add_argument("--force-full-probe-deadlock", type=int, default=DEFAULT_FORCE_FULL_PROBE_DEADLOCK)
    p.add_argument("--force-full-probe-raw-margin", type=float, default=DEFAULT_FORCE_FULL_PROBE_RAW_MARGIN)
    p.add_argument(
        "--llm-review-full-gate-fail-streak",
        type=int,
        default=DEFAULT_LLM_REVIEW_FULL_GATE_FAIL_STREAK,
        help="When explicit ticket requirement is off, require a new LLM action after this many trailing full_gate_fail cycles.",
    )
    p.add_argument(
        "--llm-review-min-no-improve-streak",
        type=int,
        default=DEFAULT_LLM_REVIEW_MIN_NO_IMPROVE_STREAK,
        help="Minimum no_improve_streak before dynamic LLM review gating becomes active.",
    )
    p.add_argument(
        "--llm-review-fail-open",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_LLM_REVIEW_FAIL_OPEN,
        help="Allow dynamic LLM review gating to fall back to auto-generated action plans when no valid ticket arrives.",
    )
    p.add_argument(
        "--require-llm-action-ticket",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require a valid LLM-produced next_action ticket each cycle; otherwise stop with awaiting_llm_action.",
    )
    p.add_argument(
        "--baseline-integrity-auto-repair",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When runtime baseline integrity check fails, rebuild baseline via full eval before continuing.",
    )
    p.add_argument("--cycle-lock-retries", type=int, default=DEFAULT_CYCLE_LOCK_RETRIES)
    p.add_argument(
        "--worker-fail-retries",
        type=int,
        default=1,
        help="Retry worker process after non-lock failure before surfacing worker_failed.",
    )
    p.add_argument("--stop-no-improve", type=int, default=2)
    p.add_argument("--no-resume-from-state", action="store_true")
    p.add_argument("--quiet", action="store_true")
    return p


def main() -> int:
    parser = _build_parser()
    args, unknown = parser.parse_known_args()
    if unknown:
        _append_trace_event(
            status="trace",
            reason="unknown_cli_args_ignored",
            cycle=None,
            payload={"unknown_args": [str(x) for x in unknown]},
        )
    if args.worker:
        return _run_worker(args)
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
