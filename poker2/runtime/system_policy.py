from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import bisect
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Callable

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.engines.postflop_solver import compute_postflop_solver_build_id, postflop_solver_src_root_from_paths_trace
from poker2.engines.postflop_pyo3 import solve_postflop_pyo3
from poker2.protocol.spot_policy import load_spot_policy, spot_policy_digest
from poker2.runtime.artifact_store import ArtifactStoreError, resolve_artifact_path
from poker2.runtime.ev_core import action_ev, equity_uncertainty, estimate_rake
from poker2.runtime.hand_eval import board_texture, estimate_equity, estimate_equity_vs_range, parse_card_token
from poker2.runtime.spot_policy import apply_spot_policy_overlay, build_spot_context
from poker2.protocol.retaliation_model import load_retaliation_model, retaliation_bucket_key
from poker2.protocol.treepath_mapping import (
    default_internal_treepath_mapping_spec,
    position_key,
    pot_fracs,
    preflop_size_plan,
    parse_size_fraction,
)

PolicyFn = Callable[[dict[str, Any]], dict[str, Any]]

DEFAULT_POSTFLOP_SOLVER_BUILD_ID = "c45abf498dba6426b4ddd8af921ffa9d2067c782e82d1f4a6eeea4c30428e24d"
SUPPORTED_SYSTEM_PARAMS_SCHEMA_IDS = frozenset(
    {
        "system_bot_params_v4",
        "system_bot_params_v5",
        "system_bot_params_v6",
    }
)


def _position_key(actor_seat: int, button_seat: int, seats_in_hand: list[int]) -> str:
    return position_key(actor_seat, button_seat, seats_in_hand)


@dataclass(frozen=True)
class SystemPolicyError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _sha256_file_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pick_nearest_action(
    legal_actions: list[dict[str, Any]],
    *,
    kind: str,
    target: int,
) -> dict[str, Any] | None:
    candidates = [a for a in legal_actions if a.get("kind") == kind]
    if not candidates:
        return None
    return min(candidates, key=lambda a: (abs(int(a.get("target_total_commit_chips", 0)) - target), a.get("target_total_commit_chips", 0)))


def _raise_candidates(legal_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in legal_actions if a.get("kind") in ("RAISE", "BET")]


def _pick_raise_by_bb_ratio(
    legal_actions: list[dict[str, Any]],
    *,
    bb: int,
    actor_commit: int,
    target_bb_ratio: float,
) -> dict[str, Any] | None:
    if bb <= 0:
        return None
    candidates = _raise_candidates(legal_actions)
    if not candidates:
        return None
    target = float(target_bb_ratio)
    def _score(a: dict[str, Any]) -> tuple[float, int]:
        tgt = int(a.get("target_total_commit_chips", 0))
        add = max(0, tgt - actor_commit)
        ratio = add / bb
        return (abs(ratio - target), tgt)
    return min(candidates, key=_score)


def _pick_raise_by_call_mult(
    legal_actions: list[dict[str, Any]],
    *,
    call_target: int,
    target_mult: float,
) -> dict[str, Any] | None:
    if call_target <= 0:
        return None
    candidates = _raise_candidates(legal_actions)
    if not candidates:
        return None
    target = float(target_mult)
    def _score(a: dict[str, Any]) -> tuple[float, int]:
        tgt = int(a.get("target_total_commit_chips", 0))
        ratio = tgt / call_target
        return (abs(ratio - target), tgt)
    return min(candidates, key=_score)


def _pick_raise_by_add_bb(
    legal_actions: list[dict[str, Any]],
    *,
    call_target: int,
    bb: int,
    target_add_bb: float,
) -> dict[str, Any] | None:
    if bb <= 0:
        return None
    candidates = _raise_candidates(legal_actions)
    if not candidates:
        return None
    target = float(target_add_bb)
    def _score(a: dict[str, Any]) -> tuple[float, int]:
        tgt = int(a.get("target_total_commit_chips", 0))
        add = max(0, tgt - call_target)
        ratio = add / bb
        return (abs(ratio - target), tgt)
    return min(candidates, key=_score)


def _pick_raise_by_pot_frac(
    legal_actions: list[dict[str, Any]],
    *,
    pot: int,
    call_target: int,
    target_frac: float,
) -> dict[str, Any] | None:
    if pot <= 0:
        return None
    candidates = _raise_candidates(legal_actions)
    if not candidates:
        return None
    target = float(target_frac)
    def _score(a: dict[str, Any]) -> tuple[float, int]:
        tgt = int(a.get("target_total_commit_chips", 0))
        add = max(0, tgt - call_target)
        ratio = add / pot
        return (abs(ratio - target), tgt)
    return min(candidates, key=_score)


def _resolve_artifact_path_from_trace(
    *,
    artifact_ref: str,
    digest: dict[str, str],
    paths_trace: dict[str, Any],
    strict_mode: bool,
) -> Path:
    validate_digest_object(digest, strict_mode=True)
    if artifact_ref.startswith("artifact://"):
        path = resolve_artifact_path(artifact_ref)
    elif artifact_ref.startswith("path:"):
        entries = [e for e in paths_trace.get("resolved_artifacts", []) if e.get("artifact_ref") == artifact_ref]
        if not entries:
            # Best-effort fallback for legacy traces.
            candidate = Path(artifact_ref.removeprefix("path:"))
            if candidate.exists():
                entries = [{"abs_path_or_null": str(candidate), "resolved_ok": True}]
            else:
                # Try digest match from other resolved artifacts.
                entries = [
                    e for e in paths_trace.get("resolved_artifacts", []) if e.get("digest", {}).get("hex") == digest.get("hex")
                ]
        if not entries:
            raise SystemPolicyError(
                "ARTIFACT_PATH_NOT_RESOLVED",
                "artifact_ref not present in paths_trace.resolved_artifacts",
                {"artifact_ref": artifact_ref},
            )
        entry = entries[0]
        if strict_mode and not entry.get("resolved_ok"):
            raise SystemPolicyError(
                "ARTIFACT_RESOLUTION_FAILED",
                "artifact_ref failed resolution in strict_mode",
                {"artifact_ref": artifact_ref, "error": entry.get("error_or_null")},
            )
        abs_path = entry.get("abs_path_or_null")
        if not isinstance(abs_path, str) or not abs_path:
            raise SystemPolicyError("ARTIFACT_PATH_MISSING", "resolved artifact missing abs_path", {"artifact_ref": artifact_ref})
        path = Path(abs_path)
    else:
        raise SystemPolicyError("UNSUPPORTED_REF", "unsupported artifact_ref scheme", {"artifact_ref": artifact_ref})

    if not path.exists():
        raise SystemPolicyError("ARTIFACT_NOT_FOUND", "resolved artifact path does not exist", {"artifact_ref": artifact_ref, "path": str(path)})
    observed = _sha256_file_hex(path)
    if strict_mode and observed != digest.get("hex"):
        raise SystemPolicyError(
            "DIGEST_MISMATCH",
            "artifact content digest mismatch",
            {"artifact_ref": artifact_ref, "expected": digest.get("hex"), "observed": observed},
        )
    return path


def resolve_policy_artifacts(
    *,
    policy_spec: dict[str, Any],
    paths_trace: dict[str, Any],
    strict_mode: bool,
) -> dict[str, Path]:
    deps = policy_spec.get("policy_deps") or []
    if not isinstance(deps, list):
        raise SystemPolicyError("TYPE_ERROR", "policy_deps must be array", {})
    resolved: dict[str, Path] = {}
    for dep in deps:
        if not isinstance(dep, dict):
            raise SystemPolicyError("TYPE_ERROR", "policy_deps entry must be object", {})
        ref = dep.get("artifact_ref")
        digest = dep.get("digest")
        if not isinstance(ref, str):
            raise SystemPolicyError("TYPE_ERROR", "artifact_ref must be string", {})
        try:
            validate_digest_object(digest, strict_mode=True)
        except Exception as e:  # pragma: no cover - validated elsewhere
            raise SystemPolicyError("DIGEST_INVALID", "artifact digest invalid", {"error": str(e)})
        path = _resolve_artifact_path_from_trace(artifact_ref=ref, digest=digest, paths_trace=paths_trace, strict_mode=strict_mode)
        resolved[ref] = path
    return resolved


def _load_preflop_settings(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except Exception as e:  # pragma: no cover - IO errors
        raise SystemPolicyError("READ_ERROR", "failed to read preflop settings", {"path": str(path), "error": str(e)})


def _load_preflop_freq(
    path: Path,
    *,
    resolved: dict[str, Path] | None,
    strict_mode: bool,
) -> dict[str, Any]:
    import json

    from poker2.protocol.preflop_freq import PreflopFreqError, validate_preflop_freq

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover - IO/parse errors
        raise SystemPolicyError("PREFLOP_FREQ_READ_FAIL", "failed to read preflop freq artifact", {"path": str(path), "error": str(e)})

    manifest_path: Path | None = None
    if isinstance(obj, dict):
        ref = obj.get("manifest_ref")
        if isinstance(ref, str) and ref.startswith("path:"):
            if resolved and ref in resolved:
                manifest_path = resolved[ref]
            else:
                root = Path(__file__).resolve().parents[2]
                rel = ref.removeprefix("path:")
                candidate = (root / rel).resolve()
                if not candidate.exists():
                    candidate = (root / "specs" / rel).resolve()
                manifest_path = candidate

    try:
        validate_preflop_freq(obj, strict_mode=strict_mode, manifest_path=manifest_path)
    except PreflopFreqError as e:
        raise SystemPolicyError("PREFLOP_FREQ_INVALID", "preflop freq validation failed", {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}})

    positions = obj.get("positions")
    if not isinstance(positions, dict):
        raise SystemPolicyError("PREFLOP_FREQ_SHAPE", "preflop freq positions must be object", {"path": str(path)})
    return positions


def _load_preflop_ranges(
    path: Path,
    *,
    resolved: dict[str, Path] | None,
    strict_mode: bool,
) -> dict[str, Any]:
    import json

    from poker2.protocol.preflop_ranges import PreflopRangesError, validate_preflop_ranges

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover - IO/parse errors
        raise SystemPolicyError("PREFLOP_RANGES_READ_FAIL", "failed to read preflop ranges artifact", {"path": str(path), "error": str(e)})

    manifest_path: Path | None = None
    if isinstance(obj, dict):
        ref = obj.get("manifest_ref")
        if isinstance(ref, str) and ref.startswith("path:"):
            if resolved and ref in resolved:
                manifest_path = resolved[ref]
            else:
                root = Path(__file__).resolve().parents[2]
                rel = ref.removeprefix("path:")
                candidate = (root / rel).resolve()
                if not candidate.exists():
                    candidate = (root / "specs" / rel).resolve()
                manifest_path = candidate

    try:
        validate_preflop_ranges(obj, strict_mode=strict_mode, manifest_path=manifest_path)
    except PreflopRangesError as e:
        raise SystemPolicyError(
            "PREFLOP_RANGES_INVALID",
            "preflop ranges validation failed",
            {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}},
        )

    schema_id = obj.get("schema_id")
    if schema_id == "preflop_ranges_v2":
        scenarios = obj.get("scenarios")
        if not isinstance(scenarios, dict):
            raise SystemPolicyError("PREFLOP_RANGES_SHAPE", "preflop ranges scenarios must be object", {"path": str(path)})

        def _extract_hands(entry: Any) -> dict[str, Any] | None:
            if isinstance(entry, dict) and "hands" in entry and isinstance(entry.get("hands"), dict):
                return entry.get("hands")
            if isinstance(entry, dict) and entry and all(isinstance(v, dict) for v in entry.values()):
                return entry
            return None

        entries: list[dict[str, Any]] = []
        for scenario_key, scenario_entry in scenarios.items():
            if not isinstance(scenario_entry, dict):
                continue
            for pos_key, pos_entry in scenario_entry.items():
                if not isinstance(pos_entry, dict):
                    continue
                if scenario_key == "VS_OPEN":
                    for opener_key, opener_entry in pos_entry.items():
                        hands = _extract_hands(opener_entry)
                        if not isinstance(hands, dict):
                            continue
                        entries.append(
                            {
                                "key": {"scenario": scenario_key, "actor_pos": pos_key, "last_raiser_pos": opener_key},
                                "hands": hands,
                            }
                        )
                else:
                    hands = _extract_hands(pos_entry)
                    if not isinstance(hands, dict):
                        continue
                    entries.append(
                        {
                            "key": {"scenario": scenario_key, "actor_pos": pos_key, "last_raiser_pos": None},
                            "hands": hands,
                        }
                    )

        return {"schema_id": schema_id, "entries": entries, "key_fields": ["scenario", "actor_pos", "last_raiser_pos"]}

    if schema_id == "preflop_ranges_v3":
        entries = obj.get("entries")
        if not isinstance(entries, list):
            raise SystemPolicyError("PREFLOP_RANGES_SHAPE", "preflop ranges entries must be list", {"path": str(path)})
        key_fields = obj.get("key_fields")
        if not isinstance(key_fields, list):
            key_fields = []
        return {"schema_id": schema_id, "entries": entries, "key_fields": key_fields}

    raise SystemPolicyError("PREFLOP_RANGES_SCHEMA", "unsupported preflop ranges schema_id", {"path": str(path), "schema_id": schema_id})


def _build_preflop_ranges_index(ranges: dict[str, Any]) -> tuple[dict[tuple[Any, ...], dict[str, Any]], list[str]]:
    entries = ranges.get("entries")
    key_fields = ranges.get("key_fields") or []
    if not isinstance(entries, list) or not key_fields:
        return {}, []
    index: dict[tuple[Any, ...], dict[str, Any]] = {}
    counts: dict[tuple[Any, ...], int] = {}

    def _merge_hand_probs(a: dict[str, Any], b: dict[str, Any], *, weight: int) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for hand in set(a.keys()) | set(b.keys()):
            pa = a.get(hand, {})
            pb = b.get(hand, {})
            try:
                ra = float(pa.get("raise", 0.0) or 0.0)
                ca = float(pa.get("call", 0.0) or 0.0)
                fa = float(pa.get("fold", 0.0) or 0.0)
            except Exception:
                ra = ca = fa = 0.0
            try:
                rb = float(pb.get("raise", 0.0) or 0.0)
                cb = float(pb.get("call", 0.0) or 0.0)
                fb = float(pb.get("fold", 0.0) or 0.0)
            except Exception:
                rb = cb = fb = 0.0
            inv = 1.0 / (weight + 1)
            merged[hand] = {
                "raise": (ra * weight + rb) * inv,
                "call": (ca * weight + cb) * inv,
                "fold": (fa * weight + fb) * inv,
            }
        return merged

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        hands = entry.get("hands")
        if not isinstance(key, dict) or not isinstance(hands, dict):
            continue
        key_tuple = tuple(key.get(field) for field in key_fields)
        if key_tuple in index:
            weight = counts.get(key_tuple, 1)
            index[key_tuple] = _merge_hand_probs(index[key_tuple], hands, weight=weight)
            counts[key_tuple] = weight + 1
        else:
            index[key_tuple] = hands
            counts[key_tuple] = 1
    return index, key_fields


def _lookup_preflop_ranges(
    *,
    index: dict[tuple[Any, ...], dict[str, Any]],
    key_fields: list[str],
    key_values: dict[str, Any],
) -> dict[str, Any] | None:
    if not index or not key_fields:
        return None
    base = [key_values.get(field) for field in key_fields]
    key_tuple = tuple(base)
    if key_tuple in index:
        return index[key_tuple]
    fallback_order = (
        "size_bucket",
        "callers",
        "has_caller",
        "players",
        "last_raiser_pos",
        "raise_count",
        "scenario",
        "actor_pos",
    )
    for field in fallback_order:
        if field not in key_fields:
            continue
        idx = key_fields.index(field)
        if base[idx] is None:
            continue
        base[idx] = None
        key_tuple = tuple(base)
        if key_tuple in index:
            return index[key_tuple]
    return None


def _load_mw_strategy_table(path: Path) -> list[dict[str, Any]]:
    import json

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover - IO/parse errors
        raise SystemPolicyError("MW_STRATEGY_READ_FAIL", "failed to read mw strategy table", {"path": str(path), "error": str(e)})
    if not isinstance(obj, dict) or obj.get("mw_strategy_schema_id") != "mw_strategy_table_v1":
        raise SystemPolicyError("MW_STRATEGY_SCHEMA", "mw strategy schema_id mismatch", {"path": str(path)})
    entries = obj.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SystemPolicyError("MW_STRATEGY_SHAPE", "entries must be non-empty array", {"path": str(path)})
    for idx, ent in enumerate(entries):
        if not isinstance(ent, dict):
            raise SystemPolicyError("MW_STRATEGY_ENTRY_TYPE", "entry must be object", {"index": idx})
        if not isinstance(ent.get("rung_id"), str):
            raise SystemPolicyError("MW_STRATEGY_ENTRY_FIELD", "rung_id must be string", {"index": idx})
        for int_field in (
            "min_players",
            "max_players",
            "call_over_pot_ppm",
            "call_over_stack_ppm",
            "spr_max_ppm",
            "raise_freq_bp",
            "bet_freq_bp",
            "raise_rank",
            "bet_rank",
            "fold_prob_bp",
            "call_prob_bp",
            "raise_prob_bp",
            "bet_prob_bp",
            "cbet_prob_bp",
        ):
            val = ent.get(int_field)
            if val is None:
                continue
            if isinstance(val, bool) or not isinstance(val, int):
                raise SystemPolicyError("MW_STRATEGY_ENTRY_FIELD", f"{int_field} must be int or null", {"index": idx})
            if int_field in ("raise_freq_bp", "bet_freq_bp") and (val < 0 or val > 10000):
                raise SystemPolicyError("MW_STRATEGY_ENTRY_FIELD", f"{int_field} must be 0-10000", {"index": idx})
            if int_field in ("fold_prob_bp", "call_prob_bp", "raise_prob_bp", "bet_prob_bp", "cbet_prob_bp") and (val < 0 or val > 10000):
                raise SystemPolicyError("MW_STRATEGY_ENTRY_FIELD", f"{int_field} must be 0-10000", {"index": idx})
        streets = ent.get("streets")
        if streets is not None:
            if not isinstance(streets, list) or not all(isinstance(s, str) for s in streets):
                raise SystemPolicyError("MW_STRATEGY_ENTRY_FIELD", "streets must be array of strings", {"index": idx})
        facing = ent.get("facing_bet")
        if facing not in (None, True, False):
            raise SystemPolicyError("MW_STRATEGY_ENTRY_FIELD", "facing_bet must be bool or null", {"index": idx})
    return entries


def _canonical_digest_hex(obj: Any, *, strict_mode: bool) -> str:
    return sha256_hex(canonicalize_json_bytes(obj, strict_mode=strict_mode))


def _resolve_json_by_digest(
    *,
    digest: dict[str, Any],
    search_paths: list[Path],
    strict_mode: bool,
    label: str,
) -> tuple[Path | None, dict[str, Any] | None]:
    validate_digest_object(digest, strict_mode=True)
    target = str(digest.get("hex"))
    for path in search_paths:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        observed = _canonical_digest_hex(obj, strict_mode=strict_mode)
        if observed == target:
            return path, obj
    if strict_mode:
        raise SystemPolicyError(
            "PARAMS_RESOLVE_FAIL",
            f"failed to resolve {label} by digest",
            {"digest": target, "search_root": str(search_paths[0].parent) if search_paths else None},
        )
    return None, None


def _resolve_optional_path_ref(
    *,
    artifact_ref: str,
    resolved: dict[str, Path],
    paths_trace: dict[str, Any],
) -> Path | None:
    if artifact_ref in resolved:
        return resolved[artifact_ref]
    if not artifact_ref.startswith("path:"):
        return None
    for entry in paths_trace.get("resolved_artifacts", []) or []:
        if entry.get("artifact_ref") != artifact_ref:
            continue
        abs_path = entry.get("abs_path_or_null")
        if isinstance(abs_path, str) and abs_path:
            return Path(abs_path)
    repo_root = Path(__file__).resolve().parents[2]
    candidate = (repo_root / artifact_ref.removeprefix("path:")).resolve()
    if candidate.exists():
        return candidate
    return None


def _parse_system_params(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise SystemPolicyError("PARAMS_SHAPE", "system bot params must be object", {"path": None})
    schema_id = obj.get("params_schema_id")
    if not isinstance(schema_id, str) or schema_id not in SUPPORTED_SYSTEM_PARAMS_SCHEMA_IDS:
        raise SystemPolicyError(
            "PARAMS_SCHEMA",
            "unsupported system bot params schema_id",
            {
                "schema_id": schema_id,
                "supported_schema_ids": sorted(SUPPORTED_SYSTEM_PARAMS_SCHEMA_IDS),
            },
        )
    params: dict[str, Any] = {}
    for key in (
        "safe_exploit_max_bp",
        "rake_delta_weight_bp",
        "mw_risk_weight_bp",
        "oop_risk_weight_bp",
        "oop_realization_weight_bp",
        "oop_spr_threshold_bp",
        "preflop_ranges_enable_bp",
        "preflop_freq_blend_bp",
        "preflop_defend_tighten_bp",
        "mw_keypot_trigger_bb",
        "retaliation_weight_bp",
        "retaliation_prior_count",
        "opp_defense_prior_count",
        "facing_low_spr_threshold_bp",
        "facing_low_spr_defend_scale_bp",
        "facing_low_spr_raise_share_cap_bp",
        "facing_low_price_threshold_bp",
        "facing_low_price_defend_boost_bp",
        "facing_high_price_threshold_bp",
        "facing_high_price_raise_share_cap_bp",
        "facing_high_price_threshold2_bp",
        "facing_high_price_raise_share_cap2_bp",
        "facing_high_price_raise_share_scale_bp",
        "facing_high_price_raise_share_scale2_bp",
        "facing_high_price_raise_penalty_threshold_bp",
        "facing_high_price_raise_penalty_bp",
        "facing_high_price_raise_penalty_threshold2_bp",
        "facing_high_price_raise_penalty2_bp",
        "facing_high_price_call_penalty_bp",
        "facing_high_price_call_penalty2_bp",
        "facing_high_price_raise_block_threshold_bp",
        "facing_high_price_defend_gap_bp",
        "facing_high_price_defend_gap2_bp",
        "facing_high_price_defend_gap_oop_penalty_bp",
        "facing_high_price_defend_gap_mw_penalty_bp",
        "facing_high_price_defend_gap_spr_low_penalty_bp",
        "facing_high_price_defend_gap_spr_low_price_scale_bp",
        "facing_high_price_defend_gap_spr_low_price_turn_scale_bp",
        "facing_high_price_defend_gap_spr_mid_penalty_bp",
        "facing_high_price_defend_gap_spr_high_penalty_bp",
        "facing_high_price_defend_gap_wet_penalty_bp",
        "facing_high_price_defend_gap_turn_penalty_bp",
        "facing_high_price_threshold2_spr_low_bp",
        "facing_high_price_threshold2_turn_wet_bp",
        "facing_high_price_threshold2_river_wet_bp",
        "facing_high_price_defend_gap2_turn_wet_bp",
        "facing_high_price_defend_gap2_river_wet_bp",
        "aggressive_high_price_penalty_threshold_bp",
        "aggressive_high_price_penalty_bp",
        "aggressive_high_price_penalty_threshold2_bp",
        "aggressive_high_price_penalty2_bp",
        "adaptive_enable_bp",
        "adaptive_alpha_max_bp",
        "adaptive_min_samples",
        "adaptive_opp_defense_low_bp",
        "adaptive_opp_defense_high_bp",
        "adaptive_open_rate_high_bp",
        "adaptive_prior_count",
        "adaptive_tight_enable_bp",
        "hu_range_enable_bp",
        "hu_mixed_strategy_bp",
        "hu_rollout_enable_bp",
        "hu_rollout_turn_enable_bp",
        "hu_rollout_std_beta_bp",
        "hu_solver_gap_enable_bp",
        "hu_rollout_samples",
    ):
        val = obj.get(key)
        if isinstance(val, int):
            params[key] = val
    for key in (
        "retaliation_model_ref",
        "postflop_solver_build_id",
        "opponent_pool_ref",
        "spot_policy_ref",
    ):
        val = obj.get(key)
        if isinstance(val, str):
            params[key] = val
    spot_policy_digest_obj = obj.get("spot_policy_digest")
    if isinstance(spot_policy_digest_obj, dict):
        validate_digest_object(spot_policy_digest_obj, strict_mode=True)
        params["spot_policy_digest"] = {
            "alg": str(spot_policy_digest_obj.get("alg")),
            "hex": str(spot_policy_digest_obj.get("hex")),
        }
    return params


def _load_system_params(path: Path) -> dict[str, Any]:
    import json

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover - IO/parse errors
        raise SystemPolicyError("PARAMS_READ_FAIL", "failed to read system bot params", {"path": str(path), "error": str(e)})
    return _parse_system_params(obj)


def _pool_style_factor(*, label: str | None, role: str | None) -> float:
    text = " ".join([str(label or ""), str(role or "")]).lower()
    factor = 1.0
    if "aggressive" in text:
        factor *= 1.12
    if "elite" in text:
        factor *= 1.08
    if "pressure" in text:
        factor *= 1.06
    if "loose" in text:
        factor *= 1.05
    if "tight" in text:
        factor *= 0.92
    return max(0.85, min(1.20, factor))


def _load_opponent_pool(path: Path, *, strict_mode: bool) -> list[tuple[float, float, str]]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - IO/parse errors
        if strict_mode:
            raise SystemPolicyError(
                "OPPONENT_POOL_READ_FAIL",
                "failed to read opponent pool",
                {"path": str(path), "error": str(exc)},
            ) from exc
        return []
    candidates = obj.get("candidates") if isinstance(obj, dict) else None
    if not isinstance(candidates, list):
        if strict_mode:
            raise SystemPolicyError(
                "OPPONENT_POOL_SCHEMA",
                "opponent pool candidates must be list",
                {"path": str(path)},
            )
        return []
    entries: list[tuple[float, float, str]] = []
    for ent in candidates:
        if not isinstance(ent, dict):
            continue
        label = ent.get("suite")
        weight = ent.get("weight", 1.0)
        role = ent.get("role")
        try:
            w = float(weight)
        except Exception:
            continue
        if w <= 0:
            continue
        factor = _pool_style_factor(label=label if isinstance(label, str) else None, role=role if isinstance(role, str) else None)
        entries.append((w, factor, str(label or role or "unknown")))
    if not entries:
        return []
    total = sum(w for w, _, _ in entries)
    if total <= 0:
        return []
    # normalize weights to cumulative CDF
    cdf: list[tuple[float, float, str]] = []
    acc = 0.0
    for w, factor, label in entries:
        acc += w / total
        cdf.append((acc, factor, label))
    cdf[-1] = (1.0, cdf[-1][1], cdf[-1][2])
    return cdf


def build_system_policy(
    *,
    seat_id: int,
    seed: int,
    policy_spec: dict[str, Any],
    ruleset: dict[str, Any],
    paths_trace: dict[str, Any],
    strict_mode: bool,
) -> tuple[PolicyFn, dict[str, Any]]:
    bench_overrides: dict[str, Any] | None = None
    bench_bb_flat = False
    mapping_spec, mapping_spec_id = default_internal_treepath_mapping_spec(strict_mode=strict_mode)
    open_fraction_by_pos, threebet_by_pos, fourbet_by_pos = preflop_size_plan(mapping_spec)
    postflop_fracs, _postflop_rounding_mode = pot_fracs(mapping_spec)

    resolved = resolve_policy_artifacts(policy_spec=policy_spec, paths_trace=paths_trace, strict_mode=strict_mode)
    preflop_ref = next((ref for ref in resolved if ref.startswith("path:") and "settings" in ref), None)
    if preflop_ref is None:
        # fallback: pick first path dep
        preflop_ref = next((ref for ref in resolved if ref.startswith("path:")), None)
    preflop_freq_refs = [ref for ref in resolved if ref.startswith("path:") and "preflop_freq" in ref]
    preflop_freq_ref = preflop_freq_refs[0] if preflop_freq_refs else None
    preflop_ranges_refs = [ref for ref in resolved if ref.startswith("path:") and "preflop_ranges" in ref]
    preflop_ranges_ref = preflop_ranges_refs[0] if preflop_ranges_refs else None
    postflop_ref = next((ref for ref in resolved if ref.startswith("artifact://")), None)
    # Optional richer postflop bins/range artifact (heuristic id match)
    advanced_postflop_ref = next((ref for ref in resolved if ref.endswith("013a5b1a4f2e1d7422327cf18de589751f4e2d642003bc207a8891bfee3937d4")), None)
    mw_strategy_ref = next((ref for ref in resolved if ref.startswith("path:") and "mw_strategy" in ref), None)

    if preflop_ref is None:
        raise SystemPolicyError("PREFLOP_MISSING", "system policy requires preflop settings artifact", {})
    if strict_mode and preflop_freq_ref is None:
        raise SystemPolicyError("PREFLOP_FREQ_MISSING", "system policy requires preflop freq artifact", {})
    if postflop_ref is None:
        raise SystemPolicyError("POSTFLOP_MISSING", "system policy requires postflop artifact_ref", {})

    # Allow artifact to override mapping_spec defaults when present.
    preflop_text = _load_preflop_settings(resolved[preflop_ref])
    try:
        import json

        doc = json.loads(preflop_text)
        general = (doc.get("treeconfig", {}).get("preflop", {}).get("settings", {})) if isinstance(doc, dict) else {}
        if isinstance(general, dict):
            open_fraction_by_pos.update(
                {
                    "BU": parse_size_fraction(general.get("SIZES_OPEN_BU")) if general.get("SIZES_OPEN_BU") is not None else open_fraction_by_pos.get("BU", Fraction(5, 2)),
                    "SB": parse_size_fraction(general.get("SIZES_OPEN_SB")) if general.get("SIZES_OPEN_SB") is not None else open_fraction_by_pos.get("SB", Fraction(3, 1)),
                    "BB": parse_size_fraction(general.get("SIZES_OPEN_BB")) if general.get("SIZES_OPEN_BB") is not None else open_fraction_by_pos.get("BB", Fraction(5, 2)),
                    "OTHERS": parse_size_fraction(general.get("SIZES_OPEN_OTHERS"))
                    if general.get("SIZES_OPEN_OTHERS") is not None
                    else open_fraction_by_pos.get("OTHERS", Fraction(5, 2)),
                }
            )
            threebet_by_pos.update(
                {
                    "IP": parse_size_fraction(general.get("SIZES_3BET_IP")) if general.get("SIZES_3BET_IP") is not None else threebet_by_pos.get("IP", Fraction(33, 10)),
                    "OOP": parse_size_fraction(general.get("SIZES_3BET_OOP")) if general.get("SIZES_3BET_OOP") is not None else threebet_by_pos.get("OOP", Fraction(21, 5)),
                    "BB_VS_SB": parse_size_fraction(general.get("SIZES_3BET_BB_VS_SB"))
                    if general.get("SIZES_3BET_BB_VS_SB") is not None
                    else threebet_by_pos.get("BB_VS_SB", Fraction(7, 2)),
                    "BB_VS_OTHER": parse_size_fraction(general.get("SIZES_3BET_BB_VS_OTHER"))
                    if general.get("SIZES_3BET_BB_VS_OTHER") is not None
                    else threebet_by_pos.get("BB_VS_OTHER", Fraction(37, 10)),
                    "SB_VS_BB": parse_size_fraction(general.get("SIZES_3BET_SB_VS_BB"))
                    if general.get("SIZES_3BET_SB_VS_BB") is not None
                    else threebet_by_pos.get("SB_VS_BB", Fraction(4, 1)),
                    "SB_VS_OTHER": parse_size_fraction(general.get("SIZES_3BET_SB_VS_OTHER"))
                    if general.get("SIZES_3BET_SB_VS_OTHER") is not None
                    else threebet_by_pos.get("SB_VS_OTHER", Fraction(4, 1)),
                }
            )
            fourbet_by_pos.update(
                {
                    "IP": parse_size_fraction(general.get("SIZES_4BET_IP")) if general.get("SIZES_4BET_IP") is not None else fourbet_by_pos.get("IP", Fraction(23, 10)),
                    "OOP": parse_size_fraction(general.get("SIZES_4BET_OOP")) if general.get("SIZES_4BET_OOP") is not None else fourbet_by_pos.get("OOP", Fraction(13, 5)),
                }
            )
    except Exception:
        pass

    freq_positions: dict[str, Any] = {}
    if preflop_freq_ref is not None:
        freq_positions = _load_preflop_freq(resolved[preflop_freq_ref], resolved=resolved, strict_mode=strict_mode)

    mw_strategy_entries: list[dict[str, Any]] = []
    if mw_strategy_ref is not None:
        mw_strategy_entries = _load_mw_strategy_table(resolved[mw_strategy_ref])
    else:
        fallback = Path(__file__).resolve().parents[2] / "specs" / "mw_strategy" / "mw_strategy_table_v1.json"
        if fallback.exists():
            mw_strategy_entries = _load_mw_strategy_table(fallback)
    if strict_mode and not mw_strategy_entries:
        raise SystemPolicyError("MW_STRATEGY_MISSING", "mw strategy table is required for system policy", {})

    params_ref = next((ref for ref in resolved if ref.startswith("path:") and "system_bot_params" in ref), None)
    params: dict[str, Any] = {}
    policy_params_obj: dict[str, Any] | None = None
    policy_params_path: Path | None = None
    system_params_path: Path | None = None
    system_params_obj: dict[str, Any] | None = None
    if params_ref is not None:
        params = _load_system_params(resolved[params_ref])
        system_params_path = resolved[params_ref]
    else:
        policy_params_digest = policy_spec.get("policy_params_digest")
        if isinstance(policy_params_digest, dict):
            params_root = Path(__file__).resolve().parents[2] / "specs" / "policy_params"
            candidates = sorted(params_root.glob("*.json"))
            if candidates:
                policy_params_path, policy_params_obj = _resolve_json_by_digest(
                    digest=policy_params_digest,
                    search_paths=candidates,
                    strict_mode=strict_mode,
                    label="policy_params",
                )
            if policy_params_obj is not None:
                system_digest = policy_params_obj.get("system_bot_params_digest")
                if isinstance(system_digest, dict):
                    system_params_path, system_params_obj = _resolve_json_by_digest(
                        digest=system_digest,
                        search_paths=candidates,
                        strict_mode=strict_mode,
                        label="system_bot_params",
                    )
                    if system_params_obj is not None:
                        params = _parse_system_params(system_params_obj)

    preflop_freq_blend = max(0.0, min(1.0, float(params.get("preflop_freq_blend_bp", 0)) / 10000.0))
    if preflop_freq_blend > 0.0:
        if len(preflop_freq_refs) < 2:
            raise SystemPolicyError(
                "PREFLOP_FREQ_BLEND_MISSING",
                "preflop_freq_blend_bp set but secondary preflop_freq artifact missing",
                {"blend_bp": params.get("preflop_freq_blend_bp")},
            )
        secondary = _load_preflop_freq(resolved[preflop_freq_refs[1]], resolved=resolved, strict_mode=strict_mode)
        blended: dict[str, Any] = {}
        for pos_key, primary in freq_positions.items():
            sec = secondary.get(pos_key, {})
            blended[pos_key] = {}
            for field in ("open_pct", "call_pct", "threebet_pct", "fourbet_pct"):
                p_val = float(primary.get(field, 0.0) or 0.0)
                s_val = float(sec.get(field, p_val) or p_val)
                mix = (1.0 - preflop_freq_blend) * p_val + preflop_freq_blend * s_val
                blended[pos_key][field] = max(0.0, min(1.0, mix))
        freq_positions = blended

    preflop_ranges_enable = max(0.0, min(1.0, float(params.get("preflop_ranges_enable_bp", 0)) / 10000.0))
    preflop_ranges: dict[str, Any] = {}
    preflop_ranges_index: dict[tuple[Any, ...], dict[str, Any]] = {}
    preflop_ranges_key_fields: list[str] = []
    if preflop_ranges_enable > 0.0:
        if preflop_ranges_ref is None:
            if strict_mode:
                raise SystemPolicyError(
                    "PREFLOP_RANGES_MISSING",
                    "preflop_ranges_enable_bp set but preflop_ranges artifact missing",
                    {"enable_bp": params.get("preflop_ranges_enable_bp")},
                )
        else:
            preflop_ranges = _load_preflop_ranges(resolved[preflop_ranges_ref], resolved=resolved, strict_mode=strict_mode)
            preflop_ranges_index, preflop_ranges_key_fields = _build_preflop_ranges_index(preflop_ranges)

    safe_exploit_max = max(0.0, min(0.20, float(params.get("safe_exploit_max_bp", 500)) / 10000.0))
    safe_exploit_max = min(0.20, safe_exploit_max * 1.5)
    rake_delta_weight = max(0.0, min(2.0, float(params.get("rake_delta_weight_bp", 350)) / 10000.0))
    rake_delta_weight *= 0.80
    mw_risk_weight = max(0.0, min(1.0, float(params.get("mw_risk_weight_bp", 40)) / 10000.0))
    oop_risk_weight = max(0.0, min(1.0, float(params.get("oop_risk_weight_bp", 60)) / 10000.0))
    oop_realization_bp = params.get("oop_realization_weight_bp")
    if oop_realization_bp is None:
        oop_realization_weight = 0.0
    else:
        oop_realization_weight = max(0.0, min(0.05, float(oop_realization_bp) / 10000.0))
    oop_spr_threshold = max(1.0, min(10.0, float(params.get("oop_spr_threshold_bp", 350)) / 100.0))
    oop_facing_equity_bump_scale = max(
        0.0, min(1.0, float(params.get("oop_facing_equity_bump_scale_bp", 10000)) / 10000.0)
    )
    facing_low_price_threshold = None
    facing_low_price_defend_boost = None
    boost_bp = params.get("facing_low_price_defend_boost_bp")
    if isinstance(boost_bp, int):
        facing_low_price_defend_boost = max(0.70, min(1.30, float(boost_bp) / 10000.0))
        facing_low_price_threshold = max(0.10, min(0.50, float(params.get("facing_low_price_threshold_bp", 3300)) / 10000.0))
    facing_high_price_threshold = None
    facing_high_price_raise_cap = None
    facing_high_price_raise_scale = None
    facing_high_price_raise_penalty = None
    facing_high_price_call_penalty = None
    facing_high_price_defend_gap = None
    facing_high_price_defend_gap_oop_penalty = None
    facing_high_price_defend_gap_mw_penalty = None
    facing_high_price_defend_gap_spr_low_penalty = None
    facing_high_price_defend_gap_spr_low_price_scale = None
    facing_high_price_defend_gap_spr_low_price_turn_scale = None
    facing_high_price_defend_gap_spr_mid_penalty = None
    facing_high_price_defend_gap_spr_high_penalty = None
    facing_high_price_defend_gap_wet_penalty = None
    facing_high_price_defend_gap_turn_penalty = None
    facing_high_price_threshold2_spr_low = None
    facing_high_price_threshold2_turn_wet = None
    facing_high_price_threshold2_river_wet = None
    facing_high_price_defend_gap2_turn_wet = None
    facing_high_price_defend_gap2_river_wet = None
    facing_high_price_threshold2 = None
    facing_high_price_raise_cap2 = None
    facing_high_price_raise_scale2 = None
    facing_high_price_raise_penalty2 = None
    facing_high_price_call_penalty2 = None
    facing_high_price_defend_gap2 = None
    facing_high_price_raise_block_threshold = None
    cap_bp = params.get("facing_high_price_raise_share_cap_bp")
    cap2_bp = params.get("facing_high_price_raise_share_cap2_bp")
    scale_bp = params.get("facing_high_price_raise_share_scale_bp")
    scale2_bp = params.get("facing_high_price_raise_share_scale2_bp")
    penalty_bp = params.get("facing_high_price_raise_penalty_bp")
    penalty2_bp = params.get("facing_high_price_raise_penalty2_bp")
    call_penalty_bp = params.get("facing_high_price_call_penalty_bp")
    call_penalty2_bp = params.get("facing_high_price_call_penalty2_bp")
    defend_gap_bp = params.get("facing_high_price_defend_gap_bp")
    defend_gap2_bp = params.get("facing_high_price_defend_gap2_bp")
    defend_gap_oop_penalty_bp = params.get("facing_high_price_defend_gap_oop_penalty_bp")
    defend_gap_mw_penalty_bp = params.get("facing_high_price_defend_gap_mw_penalty_bp")
    defend_gap_spr_low_penalty_bp = params.get("facing_high_price_defend_gap_spr_low_penalty_bp")
    defend_gap_spr_low_price_scale_bp = params.get("facing_high_price_defend_gap_spr_low_price_scale_bp")
    defend_gap_spr_low_price_turn_scale_bp = params.get("facing_high_price_defend_gap_spr_low_price_turn_scale_bp")
    defend_gap_spr_mid_penalty_bp = params.get("facing_high_price_defend_gap_spr_mid_penalty_bp")
    defend_gap_spr_high_penalty_bp = params.get("facing_high_price_defend_gap_spr_high_penalty_bp")
    defend_gap_wet_penalty_bp = params.get("facing_high_price_defend_gap_wet_penalty_bp")
    defend_gap_turn_penalty_bp = params.get("facing_high_price_defend_gap_turn_penalty_bp")
    threshold2_spr_low_bp = params.get("facing_high_price_threshold2_spr_low_bp")
    threshold2_turn_wet_bp = params.get("facing_high_price_threshold2_turn_wet_bp")
    threshold2_river_wet_bp = params.get("facing_high_price_threshold2_river_wet_bp")
    defend_gap2_turn_wet_bp = params.get("facing_high_price_defend_gap2_turn_wet_bp")
    defend_gap2_river_wet_bp = params.get("facing_high_price_defend_gap2_river_wet_bp")
    if any(
        isinstance(x, int)
        for x in (
            cap_bp,
            cap2_bp,
            scale_bp,
            scale2_bp,
            penalty_bp,
            penalty2_bp,
            call_penalty_bp,
            call_penalty2_bp,
            defend_gap_bp,
            defend_gap2_bp,
            threshold2_spr_low_bp,
            threshold2_turn_wet_bp,
            threshold2_river_wet_bp,
            defend_gap2_turn_wet_bp,
            defend_gap2_river_wet_bp,
        )
    ):
        facing_high_price_threshold = max(
            0.10, min(0.80, float(params.get("facing_high_price_threshold_bp", 3300)) / 10000.0)
        )
        facing_high_price_threshold2 = max(
            0.10, min(0.90, float(params.get("facing_high_price_threshold2_bp", 5000)) / 10000.0)
        )
    if isinstance(cap_bp, int):
        facing_high_price_raise_cap = max(0.02, min(0.30, float(cap_bp) / 10000.0))
    if isinstance(cap2_bp, int):
        facing_high_price_raise_cap2 = max(0.02, min(0.30, float(cap2_bp) / 10000.0))
    if isinstance(scale_bp, int):
        facing_high_price_raise_scale = max(0.30, min(1.00, float(scale_bp) / 10000.0))
    if isinstance(scale2_bp, int):
        facing_high_price_raise_scale2 = max(0.30, min(1.00, float(scale2_bp) / 10000.0))
    if isinstance(penalty_bp, int):
        facing_high_price_raise_penalty = max(0.0, min(0.20, float(penalty_bp) / 10000.0))
    if isinstance(penalty2_bp, int):
        facing_high_price_raise_penalty2 = max(0.0, min(0.20, float(penalty2_bp) / 10000.0))
    if isinstance(call_penalty_bp, int):
        facing_high_price_call_penalty = max(0.0, min(0.30, float(call_penalty_bp) / 10000.0))
    if isinstance(call_penalty2_bp, int):
        facing_high_price_call_penalty2 = max(0.0, min(0.30, float(call_penalty2_bp) / 10000.0))
    if isinstance(defend_gap_bp, int):
        facing_high_price_defend_gap = max(0.0, min(0.20, float(defend_gap_bp) / 10000.0))
    if isinstance(defend_gap2_bp, int):
        facing_high_price_defend_gap2 = max(0.0, min(0.25, float(defend_gap2_bp) / 10000.0))
    if isinstance(defend_gap_oop_penalty_bp, int):
        facing_high_price_defend_gap_oop_penalty = max(0.0, min(0.10, float(defend_gap_oop_penalty_bp) / 10000.0))
    if isinstance(defend_gap_mw_penalty_bp, int):
        facing_high_price_defend_gap_mw_penalty = max(0.0, min(0.10, float(defend_gap_mw_penalty_bp) / 10000.0))
    if isinstance(defend_gap_spr_low_penalty_bp, int):
        facing_high_price_defend_gap_spr_low_penalty = max(
            0.0, min(0.10, float(defend_gap_spr_low_penalty_bp) / 10000.0)
        )
    if isinstance(defend_gap_spr_low_price_scale_bp, int):
        facing_high_price_defend_gap_spr_low_price_scale = max(
            0.0, min(0.10, float(defend_gap_spr_low_price_scale_bp) / 10000.0)
        )
    if isinstance(defend_gap_spr_low_price_turn_scale_bp, int):
        facing_high_price_defend_gap_spr_low_price_turn_scale = max(
            0.50, min(2.0, float(defend_gap_spr_low_price_turn_scale_bp) / 10000.0)
        )
    if isinstance(defend_gap_spr_mid_penalty_bp, int):
        facing_high_price_defend_gap_spr_mid_penalty = max(
            0.0, min(0.10, float(defend_gap_spr_mid_penalty_bp) / 10000.0)
        )
    if isinstance(defend_gap_spr_high_penalty_bp, int):
        facing_high_price_defend_gap_spr_high_penalty = max(
            0.0, min(0.15, float(defend_gap_spr_high_penalty_bp) / 10000.0)
        )
    if isinstance(defend_gap_wet_penalty_bp, int):
        facing_high_price_defend_gap_wet_penalty = max(0.0, min(0.10, float(defend_gap_wet_penalty_bp) / 10000.0))
    if isinstance(defend_gap_turn_penalty_bp, int):
        facing_high_price_defend_gap_turn_penalty = max(0.0, min(0.10, float(defend_gap_turn_penalty_bp) / 10000.0))
    if isinstance(threshold2_spr_low_bp, int):
        facing_high_price_threshold2_spr_low = max(0.10, min(0.90, float(threshold2_spr_low_bp) / 10000.0))
    if isinstance(threshold2_turn_wet_bp, int):
        facing_high_price_threshold2_turn_wet = max(0.10, min(0.90, float(threshold2_turn_wet_bp) / 10000.0))
    if isinstance(threshold2_river_wet_bp, int):
        facing_high_price_threshold2_river_wet = max(0.10, min(0.90, float(threshold2_river_wet_bp) / 10000.0))
    if isinstance(defend_gap2_turn_wet_bp, int):
        facing_high_price_defend_gap2_turn_wet = max(0.0, min(0.25, float(defend_gap2_turn_wet_bp) / 10000.0))
    if isinstance(defend_gap2_river_wet_bp, int):
        facing_high_price_defend_gap2_river_wet = max(0.0, min(0.25, float(defend_gap2_river_wet_bp) / 10000.0))
    block_bp = params.get("facing_high_price_raise_block_threshold_bp")
    if isinstance(block_bp, int):
        facing_high_price_raise_block_threshold = max(0.10, min(0.90, float(block_bp) / 10000.0))
    if (
        facing_high_price_threshold is not None
        and facing_high_price_threshold2 is not None
        and (
            facing_high_price_raise_cap is not None
            or facing_high_price_raise_cap2 is not None
            or facing_high_price_raise_scale is not None
            or facing_high_price_raise_scale2 is not None
            or facing_high_price_raise_penalty is not None
            or facing_high_price_raise_penalty2 is not None
            or facing_high_price_call_penalty is not None
            or facing_high_price_call_penalty2 is not None
            or facing_high_price_defend_gap is not None
            or facing_high_price_defend_gap2 is not None
        )
        and facing_high_price_threshold2 < facing_high_price_threshold
    ):
        facing_high_price_threshold, facing_high_price_threshold2 = (
            facing_high_price_threshold2,
            facing_high_price_threshold,
        )
        facing_high_price_raise_cap, facing_high_price_raise_cap2 = (
            facing_high_price_raise_cap2,
            facing_high_price_raise_cap,
        )
        facing_high_price_raise_scale, facing_high_price_raise_scale2 = (
            facing_high_price_raise_scale2,
            facing_high_price_raise_scale,
        )
        facing_high_price_raise_penalty, facing_high_price_raise_penalty2 = (
            facing_high_price_raise_penalty2,
            facing_high_price_raise_penalty,
        )
        facing_high_price_call_penalty, facing_high_price_call_penalty2 = (
            facing_high_price_call_penalty2,
            facing_high_price_call_penalty,
        )
        facing_high_price_defend_gap, facing_high_price_defend_gap2 = (
            facing_high_price_defend_gap2,
            facing_high_price_defend_gap,
        )
    aggressive_high_price_threshold = None
    aggressive_high_price_penalty = None
    aggressive_high_price_threshold2 = None
    aggressive_high_price_penalty2 = None
    aggr_thresh_bp = params.get("aggressive_high_price_penalty_threshold_bp")
    aggr_thresh2_bp = params.get("aggressive_high_price_penalty_threshold2_bp")
    aggr_penalty_bp = params.get("aggressive_high_price_penalty_bp")
    aggr_penalty2_bp = params.get("aggressive_high_price_penalty2_bp")
    if any(isinstance(x, int) for x in (aggr_thresh_bp, aggr_thresh2_bp, aggr_penalty_bp, aggr_penalty2_bp)):
        aggressive_high_price_threshold = max(
            0.10, min(0.90, float(params.get("aggressive_high_price_penalty_threshold_bp", 3500)) / 10000.0)
        )
        aggressive_high_price_threshold2 = max(
            0.10, min(0.95, float(params.get("aggressive_high_price_penalty_threshold2_bp", 5500)) / 10000.0)
        )
    if isinstance(aggr_penalty_bp, int):
        aggressive_high_price_penalty = max(0.0, min(0.30, float(aggr_penalty_bp) / 10000.0))
    if isinstance(aggr_penalty2_bp, int):
        aggressive_high_price_penalty2 = max(0.0, min(0.30, float(aggr_penalty2_bp) / 10000.0))
    if (
        aggressive_high_price_threshold is not None
        and aggressive_high_price_threshold2 is not None
        and aggressive_high_price_threshold2 < aggressive_high_price_threshold
    ):
        aggressive_high_price_threshold, aggressive_high_price_threshold2 = (
            aggressive_high_price_threshold2,
            aggressive_high_price_threshold,
        )
        aggressive_high_price_penalty, aggressive_high_price_penalty2 = (
            aggressive_high_price_penalty2,
            aggressive_high_price_penalty,
        )
    preflop_defend_tighten = max(0.05, min(0.50, float(params.get("preflop_defend_tighten_bp", 1800)) / 10000.0))
    mw_keypot_trigger_bb = max(0, int(params.get("mw_keypot_trigger_bb", 40)))
    retaliation_weight = max(0.0, min(1.5, float(params.get("retaliation_weight_bp", 250)) / 10000.0))
    retaliation_prior = max(0, int(params.get("retaliation_prior_count", 8)))
    opp_defense_prior = max(1.0, float(params.get("opp_defense_prior_count", 8)))
    adaptive_enable = max(0.0, min(1.0, float(params.get("adaptive_enable_bp", 0)) / 10000.0))
    adaptive_alpha_max = max(0.0, min(0.50, float(params.get("adaptive_alpha_max_bp", 2000)) / 10000.0))
    adaptive_min_samples = max(10, min(2000, int(params.get("adaptive_min_samples", 120))))
    adaptive_opp_defense_low = max(0.20, min(0.80, float(params.get("adaptive_opp_defense_low_bp", 4500)) / 10000.0))
    adaptive_opp_defense_high = max(0.20, min(0.90, float(params.get("adaptive_opp_defense_high_bp", 6200)) / 10000.0))
    adaptive_open_rate_high = max(0.05, min(0.80, float(params.get("adaptive_open_rate_high_bp", 3500)) / 10000.0))
    adaptive_prior = max(1.0, min(64.0, float(params.get("adaptive_prior_count", 8))))
    adaptive_tight_enable = max(0.0, min(1.0, float(params.get("adaptive_tight_enable_bp", 10000)) / 10000.0))
    retaliation_model = None
    retaliation_model_ref = params.get("retaliation_model_ref") or "path:artifacts/retaliation_model_v1.json"
    fixed_solver_build_id = params.get("postflop_solver_build_id") or DEFAULT_POSTFLOP_SOLVER_BUILD_ID
    retaliation_bucket_spec: dict[str, Any] | None = None
    retaliation_index: dict[str, dict[str, int]] | None = None
    retaliation_global_raise_prob: float | None = None
    if retaliation_weight > 0 and isinstance(retaliation_model_ref, str):
        model_path: Path | None = None
        if retaliation_model_ref in resolved:
            model_path = resolved[retaliation_model_ref]
        elif retaliation_model_ref.startswith("path:"):
            for entry in paths_trace.get("resolved_artifacts", []) or []:
                if entry.get("artifact_ref") == retaliation_model_ref:
                    abs_path = entry.get("abs_path_or_null")
                    if isinstance(abs_path, str) and abs_path:
                        model_path = Path(abs_path)
                        break
            if model_path is None:
                model_path = (Path(__file__).resolve().parents[2] / retaliation_model_ref.removeprefix("path:")).resolve()
        if model_path is None or not model_path.exists():
            if strict_mode:
                raise SystemPolicyError(
                    "RETALIATION_MODEL_MISSING",
                    "retaliation model ref could not be resolved",
                    {"ref": retaliation_model_ref},
                )
        else:
            retaliation_model = load_retaliation_model(model_path)
            retaliation_bucket_spec = retaliation_model.get("bucket_spec") if isinstance(retaliation_model, dict) else None
            retaliation_index = retaliation_model.get("index") if isinstance(retaliation_model, dict) else None
            global_counts = retaliation_model.get("global") if isinstance(retaliation_model, dict) else None
            if isinstance(global_counts, dict):
                g_bet = int(global_counts.get("bet_count", 0) or 0)
                g_raise = int(global_counts.get("raise_count", 0) or 0)
                if g_bet > 0:
                    retaliation_global_raise_prob = g_raise / max(1, g_bet)

    hu_range_enable = max(0.0, min(1.0, float(params.get("hu_range_enable_bp", 0)) / 10000.0))
    hu_rollout_enable = max(0.0, min(1.0, float(params.get("hu_rollout_enable_bp", 0)) / 10000.0))
    if "hu_rollout_turn_enable_bp" in params:
        hu_rollout_turn_enable = max(0.0, min(1.0, float(params.get("hu_rollout_turn_enable_bp", 0)) / 10000.0))
    else:
        hu_rollout_turn_enable = 0.0
    hu_rollout_samples = max(8, min(128, int(params.get("hu_rollout_samples", 48))))
    hu_rollout_beta = max(0.0, min(1.0, float(params.get("hu_rollout_std_beta_bp", 2500)) / 10000.0))
    opponent_pool_ref = params.get("opponent_pool_ref") or "path:specs/opponents/pools/system_bot_pool_v2.json"
    opponent_pool_cdf: list[tuple[float, float, str]] = []
    if hu_rollout_enable > 0 and isinstance(opponent_pool_ref, str):
        pool_path: Path | None = None
        if opponent_pool_ref in resolved:
            pool_path = resolved[opponent_pool_ref]
        elif opponent_pool_ref.startswith("path:"):
            for entry in paths_trace.get("resolved_artifacts", []) or []:
                if entry.get("artifact_ref") == opponent_pool_ref:
                    abs_path = entry.get("abs_path_or_null")
                    if isinstance(abs_path, str) and abs_path:
                        pool_path = Path(abs_path)
                        break
            if pool_path is None:
                pool_path = (Path(__file__).resolve().parents[2] / opponent_pool_ref.removeprefix("path:")).resolve()
        if pool_path is not None and pool_path.exists():
            opponent_pool_cdf = _load_opponent_pool(pool_path, strict_mode=False)
        if not opponent_pool_cdf:
            opponent_pool_cdf = [(1.0, 1.0, "default")]

    spot_policy_ref = params.get("spot_policy_ref")
    spot_policy_digest_obj = params.get("spot_policy_digest")
    spot_policy: dict[str, Any] | None = None
    if isinstance(spot_policy_ref, str) or isinstance(spot_policy_digest_obj, dict):
        spot_policy_path: Path | None = None
        if isinstance(spot_policy_ref, str):
            spot_policy_path = _resolve_optional_path_ref(
                artifact_ref=spot_policy_ref,
                resolved=resolved,
                paths_trace=paths_trace,
            )
            if spot_policy_path is None or not spot_policy_path.exists():
                if strict_mode:
                    raise SystemPolicyError(
                        "SPOT_POLICY_MISSING",
                        "spot policy ref could not be resolved",
                        {"ref": spot_policy_ref},
                    )
            else:
                spot_policy = load_spot_policy(spot_policy_path, strict_mode=strict_mode)
        if spot_policy is None and isinstance(spot_policy_digest_obj, dict):
            spot_root = Path(__file__).resolve().parents[2] / "specs" / "spot_policies"
            spot_candidates = sorted(spot_root.glob("*.json"))
            if spot_candidates:
                spot_policy_path, spot_policy_obj = _resolve_json_by_digest(
                    digest=spot_policy_digest_obj,
                    search_paths=spot_candidates,
                    strict_mode=strict_mode,
                    label="spot_policy",
                )
                if spot_policy_path is not None:
                    spot_policy = load_spot_policy(spot_policy_path, strict_mode=strict_mode)
                    if not isinstance(spot_policy_ref, str):
                        repo_root = Path(__file__).resolve().parents[2]
                        try:
                            rel_path = spot_policy_path.resolve().relative_to(repo_root)
                            spot_policy_ref = f"path:{rel_path.as_posix()}"
                        except Exception:
                            spot_policy_ref = None
        if spot_policy is not None:
            observed_spot_digest = spot_policy_digest(spot_policy, strict_mode=strict_mode)
            if strict_mode and isinstance(spot_policy_digest_obj, dict) and observed_spot_digest != spot_policy_digest_obj:
                raise SystemPolicyError(
                    "SPOT_POLICY_DIGEST_MISMATCH",
                    "spot policy digest mismatch",
                    {
                        "ref": spot_policy_ref,
                        "expected": spot_policy_digest_obj,
                        "observed": observed_spot_digest,
                    },
                )
            spot_policy_digest_obj = observed_spot_digest

    def _freq(pos_key: str, name: str, default: float) -> float:
        pos = freq_positions.get(pos_key) or freq_positions.get("OTHERS") or {}
        val = pos.get(name)
        if isinstance(val, (int, float)):
            return max(0.0, min(1.0, float(val)))
        return default

    def _rng_pct(salt: str) -> int:
        return int(hashlib.sha256(salt.encode()).hexdigest()[:4], 16) % 10000

    defense_state: dict[str, dict[str, int]] = {}
    defense_state_pos: dict[tuple[str, str], dict[str, int]] = {}
    opp_defense_state: dict[tuple[str, str, str], dict[str, int]] = {}
    opp_defense_state_street: dict[str, dict[str, int]] = {}
    last_aggression: dict[str, Any] | None = None
    blind_open_stats: dict[str, dict[str, int]] = {"SB": {"hands": 0, "opens": 0}, "BB": {"hands": 0, "opens": 0}}
    adaptive_profile_runtime: dict[str, Any] | None = None
    adaptive_state: dict[str, Any] = {
        "last_decision_id": None,
        "hands_seen": 0,
        "expert_counts": {"anchor": 0, "tight_defense": 0, "pressure": 0},
    }
    if adaptive_opp_defense_high < adaptive_opp_defense_low:
        adaptive_opp_defense_low, adaptive_opp_defense_high = adaptive_opp_defense_high, adaptive_opp_defense_low
    adaptation_closure = {
        "schema_id": "adaptive_profile_v1",
        "enable_bp": int(round(adaptive_enable * 10000)),
        "alpha_max_bp": int(round(adaptive_alpha_max * 10000)),
        "min_samples": int(adaptive_min_samples),
        "opp_defense_low_bp": int(round(adaptive_opp_defense_low * 10000)),
        "opp_defense_high_bp": int(round(adaptive_opp_defense_high * 10000)),
        "open_rate_high_bp": int(round(adaptive_open_rate_high * 10000)),
        "prior_count": int(round(adaptive_prior)),
        "tight_enable_bp": int(round(adaptive_tight_enable * 10000)),
    }
    adaptation_digest: str | None = None
    if adaptive_enable > 0:
        adaptation_digest = sha256_hex(canonicalize_json_bytes(adaptation_closure, strict_mode=strict_mode))

    def _adaptive_profile_for_decision(*, decision_id: int, state_hash: str | None) -> dict[str, Any]:
        if adaptive_enable <= 0:
            return {
                "enabled": False,
                "expert": "anchor",
                "alpha": 0.0,
                "conf": 0.0,
                "force_anchor": True,
                "samples": 0,
                "opp_defense_rate": 0.5,
                "open_rate": 0.0,
            }
        prev_decision_id = adaptive_state.get("last_decision_id")
        if prev_decision_id is None or decision_id <= int(prev_decision_id):
            adaptive_state["hands_seen"] = int(adaptive_state.get("hands_seen", 0)) + 1
        adaptive_state["last_decision_id"] = int(decision_id)

        opp_facing = 0
        opp_defend = 0
        for stats in opp_defense_state_street.values():
            try:
                opp_facing += int(stats.get("facing", 0) or 0)
                opp_defend += int(stats.get("defend", 0) or 0)
            except Exception:
                continue
        defend_rate = (float(opp_defend) + (0.5 * adaptive_prior)) / max(1.0, float(opp_facing) + adaptive_prior)

        sb_stats = blind_open_stats.get("SB") or {}
        bb_stats = blind_open_stats.get("BB") or {}
        open_hands = int(sb_stats.get("hands", 0) or 0) + int(bb_stats.get("hands", 0) or 0)
        open_events = int(sb_stats.get("opens", 0) or 0) + int(bb_stats.get("opens", 0) or 0)
        open_rate = (float(open_events) + (0.5 * adaptive_prior)) / max(1.0, float(open_hands) + adaptive_prior)

        pressure_score = max(0.0, adaptive_opp_defense_low - defend_rate)
        tight_score = (
            max(0.0, defend_rate - adaptive_opp_defense_high) + 0.5 * max(0.0, open_rate - adaptive_open_rate_high)
        ) * adaptive_tight_enable
        anchor_score = 0.02
        raw_scores = {
            "anchor": anchor_score,
            "tight_defense": tight_score,
            "pressure": pressure_score,
        }
        total = max(1e-9, sum(raw_scores.values()))
        probs = {k: max(0.0, float(v)) / total for k, v in raw_scores.items()}
        entropy = 0.0
        for p in probs.values():
            if p > 1e-12:
                entropy -= p * math.log(p)
        max_entropy = math.log(max(1, len(probs)))
        entropy_conf = 1.0 - (entropy / max_entropy) if max_entropy > 0 else 0.0
        samples = int(opp_facing + open_hands)
        sample_conf = min(1.0, float(samples) / max(1.0, float(adaptive_min_samples)))
        conf = max(0.0, min(1.0, sample_conf * entropy_conf))
        force_anchor = bool(samples < adaptive_min_samples)
        alpha = adaptive_alpha_max * conf
        expert = max(probs.items(), key=lambda kv: kv[1])[0]
        if force_anchor:
            expert = "anchor"
            alpha = 0.0
        counts = adaptive_state.get("expert_counts")
        if isinstance(counts, dict) and expert in counts:
            counts[expert] = int(counts.get(expert, 0) or 0) + 1
        return {
            "enabled": True,
            "expert": expert,
            "alpha": max(0.0, min(adaptive_alpha_max, alpha)),
            "conf": conf,
            "force_anchor": force_anchor,
            "samples": samples,
            "opp_defense_rate": max(0.0, min(1.0, defend_rate)),
            "open_rate": max(0.0, min(1.0, open_rate)),
            "state_hash": state_hash,
        }

    def _defense_stats_for(street: str, pos_key: str) -> tuple[dict[str, int], dict[str, int]]:
        base = defense_state.setdefault(street, {"facing": 0, "defend": 0})
        pos = defense_state_pos.setdefault((street, pos_key), {"facing": 0, "defend": 0})
        return base, pos

    def _defense_rate_for(street: str, pos_key: str, default: float) -> float:
        base, pos = _defense_stats_for(street, pos_key)
        if base["facing"] <= 0:
            return max(0.0, min(1.0, float(default)))
        base_rate = base["defend"] / max(1, base["facing"])
        if pos["facing"] <= 0:
            return max(0.0, min(1.0, base_rate))
        pos_rate = pos["defend"] / max(1, pos["facing"])
        weight = pos["facing"] / max(1, base["facing"])
        return max(0.0, min(1.0, (base_rate * (1.0 - weight)) + (pos_rate * weight)))

    def _record_defense(street: str, pos_key: str, action_kind: str) -> None:
        base, pos = _defense_stats_for(street, pos_key)
        base["facing"] += 1
        pos["facing"] += 1
        if action_kind != "FOLD":
            base["defend"] += 1
            pos["defend"] += 1

    def _size_bucket_for_ratio(ratio: float) -> str:
        if ratio <= 0.0:
            return "0"
        if ratio <= 0.33:
            return "0-0.33"
        if ratio <= 0.66:
            return "0.33-0.66"
        if ratio <= 1.0:
            return "0.66-1.0"
        if ratio <= 1.5:
            return "1.0-1.5"
        return "1.5+"

    def _record_opp_defense(
        *,
        street: str,
        size_bucket: str,
        spot: str,
        opponents: int,
        defenders: int,
    ) -> None:
        if opponents <= 0:
            return
        key = (street, size_bucket, spot)
        stats = opp_defense_state.setdefault(key, {"facing": 0, "defend": 0})
        stats["facing"] += opponents
        stats["defend"] += max(0, min(opponents, defenders))
        base = opp_defense_state_street.setdefault(street, {"facing": 0, "defend": 0})
        base["facing"] += opponents
        base["defend"] += max(0, min(opponents, defenders))

    def _opp_defense_rate(
        *,
        street: str,
        size_bucket: str,
        spot: str,
        default_rate: float,
    ) -> float:
        base = opp_defense_state_street.get(street)
        base_rate = default_rate
        if base and base["facing"] > 0:
            base_rate = base["defend"] / max(1, base["facing"])
        key = (street, size_bucket, spot)
        stats = opp_defense_state.get(key)
        if not stats or stats["facing"] <= 0:
            return max(0.0, min(1.0, base_rate))
        prior_strength = opp_defense_prior
        post_defend = stats["defend"] + prior_strength * base_rate
        post_facing = stats["facing"] + prior_strength
        return max(0.0, min(1.0, post_defend / max(1.0, post_facing)))

    def _is_new_hand(obs: dict[str, Any], street: str | None) -> bool:
        if street != "PREFLOP":
            return False
        last_raiser = obs.get("last_raiser_by_street")
        raise_count = obs.get("street_raise_count")
        if not isinstance(last_raiser, dict) or not isinstance(raise_count, dict):
            return False
        for st in ("PREFLOP", "FLOP", "TURN", "RIVER"):
            if last_raiser.get(st) is not None:
                return False
            if int(raise_count.get(st, 0) or 0) != 0:
                return False
        return True

    def _update_opp_defense_from_obs(
        *,
        obs: dict[str, Any],
        street: str | None,
        players_alive: int,
    ) -> None:
        nonlocal last_aggression
        if last_aggression is None:
            return
        # If a new hand begins without another decision, treat as all folded.
        if _is_new_hand(obs, street):
            opponents = max(0, int(last_aggression.get("players_alive", 0)) - 1)
            _record_opp_defense(
                street=str(last_aggression.get("street")),
                size_bucket=str(last_aggression.get("size_bucket")),
                spot=str(last_aggression.get("spot")),
                opponents=opponents,
                defenders=0,
            )
            last_aggression = None
            return
        last_street = last_aggression.get("street")
        if street == last_street:
            last_raiser_map = obs.get("last_raiser_by_street") or {}
            if isinstance(last_raiser_map, dict):
                last_raiser = last_raiser_map.get(last_street)
                if last_raiser is not None and last_raiser != seat_id:
                    last_aggression = None
            return
        last_raiser_map = obs.get("last_raiser_by_street") or {}
        if not isinstance(last_raiser_map, dict):
            last_aggression = None
            return
        last_raiser = last_raiser_map.get(last_street)
        if last_raiser == seat_id:
            seats_now = obs.get("seats_in_hand") or []
            if isinstance(seats_now, list):
                defenders = max(0, len([s for s in seats_now if int(s) != seat_id]))
                opponents = max(0, int(last_aggression.get("players_alive", 0)) - 1)
                _record_opp_defense(
                    street=str(last_aggression.get("street")),
                    size_bucket=str(last_aggression.get("size_bucket")),
                    spot=str(last_aggression.get("spot")),
                    opponents=opponents,
                    defenders=defenders,
                )
        last_aggression = None

    def _note_aggression(
        *,
        action: dict[str, Any],
        pot_chips: int,
        to_call: int,
        actor_commit: int,
        players_alive: int,
        street: str | None,
        obs: dict[str, Any],
    ) -> None:
        nonlocal last_aggression
        if action is None:
            return
        kind = str(action.get("kind"))
        if kind not in ("RAISE", "BET", "ALLIN"):
            return
        if street is None:
            return
        target = int(action.get("target_total_commit_chips", actor_commit))
        risk = max(0, target - actor_commit)
        pot_base = pot_chips + (to_call if to_call > 0 else 0)
        if risk <= 0 or pot_base <= 0:
            return
        ratio = float(risk) / float(pot_base)
        size_bucket = _size_bucket_for_ratio(ratio)
        spot = "HU" if players_alive <= 2 else "MW"
        last_aggression = {
            "street": street,
            "players_alive": players_alive,
            "size_bucket": size_bucket,
            "spot": spot,
        }

    def _opp_defend_rate_for_action(
        *,
        action: dict[str, Any],
        pot_chips: int,
        to_call: int,
        actor_commit: int,
        players_alive: int,
        street: str | None,
    ) -> float | None:
        kind = str(action.get("kind"))
        if kind not in ("RAISE", "BET", "ALLIN"):
            return None
        if street is None:
            return None
        target = int(action.get("target_total_commit_chips", actor_commit))
        risk = max(0, target - actor_commit)
        pot_base = pot_chips + (to_call if to_call > 0 else 0)
        if risk <= 0 or pot_base <= 0:
            return None
        rake_base = estimate_rake(
            pot_after=float(pot_base + risk),
            street=street,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )
        denom = max(1.0, float(pot_base + risk - rake_base))
        default_rate = max(0.0, min(1.0, float(pot_base) / denom))
        ratio = float(risk) / float(pot_base)
        size_bucket = _size_bucket_for_ratio(ratio)
        spot = "HU" if players_alive <= 2 else "MW"
        return _opp_defense_rate(
            street=street,
            size_bucket=size_bucket,
            spot=spot,
            default_rate=default_rate,
        )

    bb = int(ruleset["blinds"]["bb_chips"])
    rake_cfg = ruleset.get("rake") or {}
    rake_rate = (int(rake_cfg.get("pct_ppm", 0) or 0) / 1_000_000.0) if isinstance(rake_cfg, dict) else 0.0
    rake_cap = rake_cfg.get("cap_chips") if isinstance(rake_cfg, dict) else None
    no_flop_no_drop = bool(rake_cfg.get("no_flop_no_drop", False)) if isinstance(rake_cfg, dict) else False
    if oop_realization_bp is None:
        oop_realization_weight = min(0.03, 0.006 + 0.08 * float(rake_rate))
    postflop_frac = postflop_fracs[0] if postflop_fracs else Fraction(3, 5)
    try:
        digest_hex = _sha256_file_hex(resolved[postflop_ref])
        first_byte = int(digest_hex[:2], 16)
        pct = 45 + (first_byte % 41)
        postflop_frac = Fraction(pct, 100)
    except Exception:
        postflop_frac = postflop_fracs[0] if postflop_fracs else Fraction(3, 5)

    def _deterministic_rank(action: dict[str, Any], *, desired: int, state_hash: str | None) -> tuple[int, int]:
        target = int(action.get("target_total_commit_chips", 0))
        delta = abs(target - desired)
        sh = state_hash or ""
        salt = f"{target}:{desired}:{sh}:{seat_id}"
        h = int(hashlib.sha256(salt.encode()).hexdigest()[:8], 16)
        return (delta, h)

    def _blend_prior_weights(primary: dict[str, int], secondary: dict[str, int], blend: float) -> dict[str, int]:
        if blend <= 0.0:
            return dict(primary)
        if blend >= 1.0:
            return dict(secondary)
        out: dict[str, int] = {}
        keys = set(primary.keys()) | set(secondary.keys())
        for key in keys:
            p = float(primary.get(key, 0))
            s = float(secondary.get(key, 0))
            mix = (1.0 - blend) * p + blend * s
            out[key] = int(max(0.0, min(10000.0, mix)))
        return out

    equity_cache: dict[tuple, float] = {}
    equity_range_cache: dict[tuple, float] = {}
    preflop_equity_dist: dict[int, list[float]] = {}
    range_combo_cache: list[tuple[float, tuple[tuple[int, str], tuple[int, str]]]] = []

    def _combo_score(hole: tuple[tuple[int, str], tuple[int, str]]) -> float:
        (r1, s1), (r2, s2) = hole
        hi, lo = (r1, r2) if r1 >= r2 else (r2, r1)
        score = float(hi * 2 + lo)
        if r1 == r2:
            score += 30.0 + float(hi)
        if s1 == s2:
            score += 2.5
        gap = hi - lo
        if gap == 1:
            score += 1.5
        elif gap == 2:
            score += 0.5
        if hi >= 12:
            score += 1.0
        return score

    _RANK_TO_CHAR = {
        14: "A",
        13: "K",
        12: "Q",
        11: "J",
        10: "T",
        9: "9",
        8: "8",
        7: "7",
        6: "6",
        5: "5",
        4: "4",
        3: "3",
        2: "2",
    }

    def _hand_class(hole: tuple[tuple[int, str], tuple[int, str]]) -> str | None:
        (r1, s1), (r2, s2) = hole
        if r1 not in _RANK_TO_CHAR or r2 not in _RANK_TO_CHAR:
            return None
        hi, lo = (r1, r2) if r1 >= r2 else (r2, r1)
        hi_char = _RANK_TO_CHAR[hi]
        lo_char = _RANK_TO_CHAR[lo]
        if r1 == r2:
            return f"{hi_char}{lo_char}"
        suited = s1 == s2
        return f"{hi_char}{lo_char}{'s' if suited else 'o'}"

    def _hand_class_from_obs(obs: dict[str, Any], seat: int) -> str | None:
        hole_map = obs.get("hole_cards_by_seat") or {}
        hole_raw = hole_map.get(str(seat)) if isinstance(hole_map, dict) else None
        if not isinstance(hole_raw, list) or len(hole_raw) != 2:
            return None
        hole_cards = [parse_card_token(c) for c in hole_raw]
        if any(c is None for c in hole_cards):
            return None
        hole = (hole_cards[0], hole_cards[1])  # type: ignore[assignment]
        return _hand_class(hole)

    if hu_range_enable > 0:
        deck = [(r, s) for r in range(2, 15) for s in ("c", "d", "h", "s")]
        combos: list[tuple[float, tuple[tuple[int, str], tuple[int, str]]]] = []
        for i in range(len(deck)):
            for j in range(i + 1, len(deck)):
                hole = (deck[i], deck[j])
                combos.append((_combo_score(hole), hole))
        combos.sort(key=lambda x: x[0], reverse=True)
        range_combo_cache = combos

    def _preflop_equity_dist(opponents: int) -> list[float]:
        cached = preflop_equity_dist.get(opponents)
        if cached is not None:
            return cached
        rng = random.Random(seed ^ (opponents << 7))
        deck = [(r, s) for r in range(2, 15) for s in ("c", "d", "h", "s")]
        dist: list[float] = []
        sample_hands = 240 if opponents >= 4 else 320
        players_alive = opponents + 1
        base = 24 + 4 * players_alive + 6 * 5
        equity_samples = min(80, max(24, base))
        for idx in range(sample_hands):
            hero = rng.sample(deck, 2)
            eq = estimate_equity(
                hero_hole=hero,
                board=(),
                opponents=max(1, opponents),
                samples=equity_samples,
                seed=(seed ^ (opponents << 11) ^ idx),
            )
            dist.append(eq)
        dist.sort()
        preflop_equity_dist[opponents] = dist
        return dist

    def _preflop_cutoff(opponents: int, pct: float) -> float:
        pct = max(0.0, min(1.0, pct))
        if pct <= 0:
            return 1.0
        if pct >= 1:
            return 0.0
        dist = _preflop_equity_dist(opponents)
        idx = int((1.0 - pct) * max(0, len(dist) - 1))
        return dist[idx]

    def _edge_mix(equity_val: float, cutoff: float, *, width: float = 0.02) -> float:
        if equity_val >= cutoff + width:
            return 1.0
        if equity_val <= cutoff - width:
            return 0.0
        return (equity_val - (cutoff - width)) / max(1e-6, 2 * width)

    def _preflop_defend_rate(
        pot_base: int,
        bet_size: int,
        opponents: int,
        *,
        opener_pos: str | None,
        defender_pos: str | None,
    ) -> float:
        if bet_size <= 0 or pot_base <= 0:
            return 0.0
        dist = _preflop_equity_dist(1)
        price = min(0.98, max(0.0, float(bet_size) / float(pot_base + bet_size)))
        idx = bisect.bisect_left(dist, price)
        call_prob = (len(dist) - idx) / max(1, len(dist))
        # Minimum defense frequency (MDF) style floor, scaled for multiway.
        mdf = float(pot_base) / float(pot_base + bet_size)
        mdf = max(0.02, min(0.95, mdf))
        mdf_boost = 1.0 + 0.05 * max(0, opponents - 1)
        mdf = min(0.95, mdf * mdf_boost)
        if rake_rate > 0:
            mdf *= max(0.5, 1.0 - rake_rate * 2.0)
        # Tighten for more players (each defender is more selective with players behind).
        tighten = 1.0 / (1.0 + preflop_defend_tighten * max(0, opponents - 1))
        tighten = max(0.70, tighten)
        call_prob *= tighten
        if opener_pos in ("BU", "SB"):
            # Late-position opens are wider; assume lower defend density vs 3bet.
            call_prob *= 0.90
        elif opener_pos == "OTHERS":
            call_prob *= 1.05
        if defender_pos in ("SB", "BB"):
            call_prob *= 0.92
        if rake_rate > 0:
            call_prob *= max(0.5, 1.0 - rake_rate * 1.8)
        call_prob = max(call_prob, mdf)
        # Bound to avoid degenerate 0/1 folds in small samples.
        return max(0.02, min(0.95, float(call_prob)))

    def _equity_from_obs(
        *,
        obs: dict[str, Any],
        players_alive: int,
        street: str | None,
        state_hash: str | None,
        range_hint: tuple[float, float] | None = None,
        return_samples: bool = False,
    ) -> float | tuple[float, int] | None:
        hole_map = obs.get("hole_cards_by_seat") or {}
        hole_raw = hole_map.get(str(seat_id)) if isinstance(hole_map, dict) else None
        if not isinstance(hole_raw, list) or len(hole_raw) != 2:
            return None
        board_raw = obs.get("board_cards") or []
        if not isinstance(board_raw, list):
            return None
        hole_cards = [parse_card_token(c) for c in hole_raw]
        board_cards = [parse_card_token(c) for c in board_raw]
        if any(c is None for c in hole_cards) or any(c is None for c in board_cards):
            return None
        hole = tuple(hole_cards)  # type: ignore[arg-type]
        board = tuple(board_cards)  # type: ignore[arg-type]
        opponents = max(1, players_alive - 1)
        board_len = len(board)
        base = 24 + 4 * players_alive + 6 * max(0, 5 - board_len)
        samples = min(80, max(24, base))
        key = (hole, board, opponents, samples)
        cached = equity_cache.get(key)
        if cached is not None and range_hint is None:
            return cached
        seed_hex = (state_hash or "")[:16]
        try:
            seed = int(seed_hex, 16) ^ (seat_id << 4) ^ (players_alive << 8)
        except Exception:
            seed = 0xC0FFEE ^ (seat_id << 4) ^ (players_alive << 8)
        eq = estimate_equity(hero_hole=hole, board=board, opponents=opponents, samples=samples, seed=seed)
        if range_hint is not None and range_combo_cache and players_alive == 2:
            range_pct, range_conf = range_hint
            used = set(hole) | set(board)
            available = max(0, (52 - len(used)))
            total_valid = max(1, (available * (available - 1)) // 2)
            need = max(16, int(float(range_pct) * float(total_valid)))
            opp_holes: list[list[tuple[int, str]]] = []
            for _score, combo in range_combo_cache:
                if len(opp_holes) >= need:
                    break
                if set(combo) & used:
                    continue
                opp_holes.append([combo[0], combo[1]])
            range_bucket = int(max(0.0, min(1.0, float(range_pct))) * 100)
            range_key = (hole, board, range_bucket, samples)
            eq_range = equity_range_cache.get(range_key)
            if eq_range is None:
                eq_range = estimate_equity_vs_range(
                    hero_hole=hole,
                    board=board,
                    opponent_holes=opp_holes,
                    samples=min(samples, 72),
                    seed=seed ^ 0xBEEF,
                )
                if len(equity_range_cache) > 2048:
                    equity_range_cache.pop(next(iter(equity_range_cache)))
                equity_range_cache[range_key] = eq_range
            blend = max(0.0, min(1.0, float(hu_range_enable) * max(0.0, min(1.0, float(range_conf)))))
            if street in ("TURN", "RIVER") and blend > 0:
                wet_score = 0
                if len(board) >= 3:
                    try:
                        wet_score = _board_wet_score(board_texture=board_texture(board), street=street)
                    except Exception:
                        wet_score = 0
                unc = equity_uncertainty(
                    equity=eq,
                    samples=samples,
                    players_alive=players_alive,
                    wet_score=wet_score,
                )
                # Damp range blend under high uncertainty to avoid overfitting noisy estimates.
                unc_scale = max(0.0, min(1.0, 1.0 - (2.2 * float(unc))))
                blend *= unc_scale
                if unc_scale <= 0.2:
                    blend *= 0.35
            eq = float(eq) * (1.0 - blend) + float(eq_range) * blend
        if len(equity_cache) > 2048:
            equity_cache.pop(next(iter(equity_cache)))
        equity_cache[key] = eq
        if return_samples:
            return (eq, samples)
        return eq

    def _hu_range_hint_from_state(
        *,
        street: str | None,
        players_alive: int,
        facing_bet: bool,
        to_call: int,
        pot_chips: int,
        raise_count: int,
        last_raiser: Any,
        solver_gap_hint: float | None,
    ) -> tuple[float, float] | None:
        if hu_range_enable <= 0 or players_alive != 2:
            return None
        if not facing_bet or street not in ("TURN", "RIVER"):
            return None
        pot_unit = float(max(1, pot_chips + to_call))
        size_ratio = float(to_call) / pot_unit if to_call > 0 else 0.0
        base = 0.62
        if street == "TURN":
            base -= 0.05
        elif street == "RIVER":
            base -= 0.10
        if facing_bet:
            base -= 0.22 * min(1.5, size_ratio * 1.2)
            if street == "RIVER":
                # Slightly tighten opponent range on river facing bet.
                base -= 0.06 * min(1.5, size_ratio * 1.5)
            base -= 0.04 * min(3, max(0, int(raise_count)))
        else:
            base += 0.03 if raise_count <= 0 else -0.02
        if last_raiser is not None and str(last_raiser) != str(seat_id):
            base -= 0.03
        range_pct = max(0.18, min(0.85, base))
        conf = 0.25 + (0.55 * min(1.0, size_ratio * 1.2) if facing_bet else 0.08)
        if street == "TURN":
            conf *= 0.65
            if solver_gap_hint is not None:
                gap_signal = max(0.0, min(1.0, float(solver_gap_hint) * 3.0))
                gap_factor = 1.0 / (1.0 + math.exp(-8.0 * (gap_signal - 0.08)))
                conf *= 0.85 + (0.25 * gap_factor)
        elif street == "RIVER":
            # River has no future card uncertainty; raise confidence more on larger bets.
            conf *= 0.68 + (0.06 * min(1.0, size_ratio * 1.2))
            if solver_gap_hint is not None:
                gap_signal = max(0.0, min(1.0, float(solver_gap_hint) * 2.0))
                gap_factor = 1.0 / (1.0 + math.exp(-6.0 * (gap_signal - 0.06)))
                conf *= 0.90 + (0.20 * gap_factor)
        conf = max(0.15, min(0.85, conf))
        return (range_pct, conf)

    def _action_ev(
        *,
        action: dict[str, Any],
        equity: float,
        pot_chips: int,
        actor_commit: int,
        to_call: int,
        players_alive: int,
        street: str | None,
        defend_rate: float | None = None,
    ) -> float:
        return action_ev(
            action=action,
            equity=equity,
            pot_chips=pot_chips,
            actor_commit=actor_commit,
            to_call=to_call,
            players_alive=players_alive,
            street=street,
            defend_rate=defend_rate,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )

    def _expected_rake_for_action(
        *,
        action: dict[str, Any],
        pot_chips: int,
        actor_commit: int,
        to_call: int,
        players_alive: int,
        street: str | None,
        defend_rate: float | None = None,
    ) -> float:
        kind = action.get("kind")
        target = int(action.get("target_total_commit_chips", actor_commit))
        extra_commit = max(0, target - actor_commit)
        if kind == "FOLD":
            return 0.0
        if kind in ("CALL", "CHECK"):
            pot_after = pot_chips + (to_call if kind == "CALL" else 0)
            return estimate_rake(
                pot_after=float(pot_after),
                street=street,
                rake_rate=rake_rate,
                rake_cap=rake_cap,
                no_flop_no_drop=no_flop_no_drop,
            )
        if kind in ("RAISE", "BET"):
            bet_size = extra_commit
            if bet_size <= 0:
                return 0.0
            pot_base = pot_chips
            rake_base = estimate_rake(
                pot_after=float(pot_base + bet_size),
                street=street,
                rake_rate=rake_rate,
                rake_cap=rake_cap,
                no_flop_no_drop=no_flop_no_drop,
            )
            denom = max(1.0, float(pot_base + bet_size - rake_base))
            if defend_rate is None:
                defend_freq = max(0.0, min(1.0, float(pot_base) / denom))
                if defend_rate is not None:
                    obs_rate = max(0.0, min(1.0, float(defend_rate)))
                    blend = 0.35
                    if street in ("TURN", "RIVER"):
                        blend = 0.60
                    elif street == "FLOP":
                        blend = 0.45
                    if facing_bet and pos_key in ("SB", "BB"):
                        blend = min(0.75, blend + 0.15)
                    defend_freq = (1.0 - blend) * defend_freq + blend * obs_rate
            else:
                defend_freq = max(0.0, min(1.0, float(defend_rate)))
            opponents = max(1, players_alive - 1)
            exp_callers = defend_freq * opponents
            pot_after = pot_base + bet_size * (1.0 + exp_callers)
            return estimate_rake(
                pot_after=float(pot_after),
                street=street,
                rake_rate=rake_rate,
                rake_cap=rake_cap,
                no_flop_no_drop=no_flop_no_drop,
            )
        return 0.0

    def _action_pot_frac(
        *,
        action: dict[str, Any],
        pot_chips: int,
        to_call: int,
        actor_commit: int,
    ) -> float:
        target = int(action.get("target_total_commit_chips", actor_commit))
        add = max(0, target - actor_commit)
        pot_base = pot_chips + (to_call if to_call > 0 else 0)
        if add <= 0 or pot_base <= 0:
            return 0.0
        return float(add) / float(pot_base)

    def _filter_postflop_actions_by_size(
        *,
        legal_actions: list[dict[str, Any]],
        pot_chips: int,
        to_call: int,
        actor_commit: int,
        players_alive: int,
        street: str | None,
        pos_key: str | None,
        stack_chips: int | None,
        equity: float | None,
        board_texture: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if street not in ("FLOP", "TURN", "RIVER"):
            return legal_actions
        if not legal_actions:
            return legal_actions
        pot_base = pot_chips + (to_call if to_call > 0 else 0)
        if pot_base <= 0:
            return legal_actions
        price = float(to_call) / float(pot_base) if to_call > 0 else 0.0
        wet_score = _board_wet_score(board_texture=board_texture, street=street)
        if (
            facing_high_price_raise_block_threshold is not None
            and to_call > 0
            and street in ("TURN", "RIVER")
        ):
            if price >= facing_high_price_raise_block_threshold:
                filtered = [a for a in legal_actions if str(a.get("kind")) not in ("RAISE", "BET", "ALLIN")]
                if filtered:
                    return filtered
        spr = None
        if stack_chips is not None and pot_chips > 0:
            spr = float(stack_chips) / float(pot_chips)
        if (
            to_call > 0
            and street in ("TURN", "RIVER")
            and players_alive > 2
            and spr is not None
            and facing_high_price_threshold is not None
        ):
            guard_threshold = float(facing_high_price_threshold)
            if facing_high_price_threshold2 is not None:
                guard_threshold = max(guard_threshold, float(facing_high_price_threshold2))
            guard_trigger = guard_threshold
            guard_spr_cap = 2.0
            max_guard_frac = 0.70
            allin_eq_floor = 0.82
            if street == "TURN":
                # Add a bounded TURN counterpart to the river guard on the same
                # high-price + low-SPR + multiway branch where repeated stalls occur.
                guard_trigger = 0.94 * guard_threshold
                guard_spr_cap = 2.4
                max_guard_frac = 0.62
                allin_eq_floor = 0.78
            if players_alive > 3 and wet_score is not None and wet_score >= 1:
                # Escalate on the same 4-way+ wet threshold2 lane by tightening
                # raise appetite instead of widening to a new mechanism family.
                if street == "TURN":
                    guard_trigger = min(guard_trigger, 0.90 * guard_threshold)
                    max_guard_frac = min(max_guard_frac, 0.54)
                    if spr <= 2.1:
                        max_guard_frac = min(max_guard_frac, 0.50)
                    if wet_score >= 2:
                        max_guard_frac = min(max_guard_frac, 0.47)
                    allin_eq_floor = max(allin_eq_floor, 0.80)
                else:
                    guard_trigger = min(guard_trigger, 0.95 * guard_threshold)
                    max_guard_frac = min(max_guard_frac, 0.60)
                    if spr <= 2.0:
                        guard_trigger = min(guard_trigger, 0.93 * guard_threshold)
                        max_guard_frac = min(max_guard_frac, 0.56)
                    if wet_score >= 2:
                        max_guard_frac = min(max_guard_frac, 0.52)
                        allin_eq_floor = max(allin_eq_floor, 0.86)
            if spr <= guard_spr_cap and price >= guard_trigger:
                if equity is not None:
                    if street == "TURN" and float(equity) >= 0.74:
                        max_guard_frac = 0.78
                    if street == "RIVER" and float(equity) >= 0.78:
                        max_guard_frac = 0.88
                guarded_actions: list[dict[str, Any]] = []
                for act in legal_actions:
                    kind = str(act.get("kind"))
                    if kind in ("RAISE", "BET", "ALLIN"):
                        target = int(act.get("target_total_commit_chips", actor_commit))
                        add = max(0, target - actor_commit)
                        frac = float(add) / float(pot_base)
                        if kind == "ALLIN" and (equity is None or float(equity) < allin_eq_floor):
                            continue
                        if frac > max_guard_frac:
                            continue
                    guarded_actions.append(act)
                if guarded_actions and len(guarded_actions) < len(legal_actions):
                    legal_actions = guarded_actions
        max_frac = 1.5
        if players_alive >= 4:
            max_frac = 0.75
        elif players_alive == 3:
            max_frac = 1.0
        if pos_key in ("SB", "BB") and spr is not None:
            if spr >= 6.0:
                max_frac = min(max_frac, 0.75)
            elif spr >= 4.0:
                max_frac = min(max_frac, 1.0)
        if street == "RIVER" and spr is not None and spr <= 2.0:
            max_frac = max(max_frac, 1.0)
        if rake_rate >= 0.05 and players_alive >= 3:
            max_frac = min(max_frac, 0.75)
        if equity is not None and equity >= 0.70:
            max_frac = max(max_frac, 1.0)
        cap_frac = max_frac
        keep: list[dict[str, Any]] = []
        raise_actions: list[dict[str, Any]] = []
        allin_actions: list[dict[str, Any]] = []
        for act in legal_actions:
            kind = str(act.get("kind"))
            if kind == "ALLIN":
                allin_actions.append(act)
                continue
            if kind in ("RAISE", "BET"):
                raise_actions.append(act)
                continue
            keep.append(act)
        if raise_actions:
            raise_fracs: list[tuple[dict[str, Any], float]] = []
            for act in raise_actions:
                frac = _action_pot_frac(action=act, pot_chips=pot_chips, to_call=to_call, actor_commit=actor_commit)
                raise_fracs.append((act, frac))
            filtered = [pair for pair in raise_fracs if pair[1] <= cap_frac]
            if not filtered:
                filtered = [min(raise_fracs, key=lambda p: p[1])]
            eq_strength = 0.5
            if equity is not None:
                eq_strength = max(0.0, min(1.0, float(equity)))
            large_bias = 0.20 + 0.80 * max(0.0, eq_strength - 0.55)
            facing = to_call > 0
            large_bias += 0.10 if facing else 0.0
            large_bias += 0.05 if street == "RIVER" else 0.0
            large_bias -= 0.12 * max(0, players_alive - 2)
            if spr is not None:
                large_bias -= 0.05 * max(0.0, min(8.0, spr - 4.0))
            large_bias -= 0.04 * float(wet_score)
            large_bias = max(0.0, min(1.0, large_bias))
            min_frac = 0.20 + 0.13 * (1.0 - large_bias)
            max_frac = min(cap_frac, 0.50 + 1.00 * large_bias)
            if max_frac < min_frac:
                max_frac = min_frac
            mid_frac = min(max_frac, 0.45 + 0.35 * large_bias)
            filtered = [pair for pair in filtered if pair[1] <= max_frac]
            if not filtered:
                filtered = [min(raise_fracs, key=lambda p: p[1])]
            if len(filtered) > 3:
                targets = [min_frac, mid_frac, max_frac]
                keep_ids: set[int] = set()
                for tgt in targets:
                    act, _ = min(filtered, key=lambda p: abs(p[1] - tgt))
                    keep_ids.add(id(act))
                filtered = [pair for pair in filtered if id(pair[0]) in keep_ids]
            keep.extend([act for act, _ in filtered])
        keep.extend(allin_actions)
        return keep

    def _preflop_raise_gate(
        *,
        legal_actions: list[dict[str, Any]],
        equity: float,
        pot_chips: int,
        actor_commit: int,
        to_call: int,
        players_alive: int,
        pos_key: str,
    ) -> list[dict[str, Any]]:
        if to_call <= 0 or not legal_actions:
            return legal_actions
        call_ev = None
        raise_ev = None
        for act in legal_actions:
            kind = str(act.get("kind"))
            if kind == "CALL":
                ev = _action_ev(
                    action=act,
                    equity=equity,
                    pot_chips=pot_chips,
                    actor_commit=actor_commit,
                    to_call=to_call,
                    players_alive=players_alive,
                    street="PREFLOP",
                )
                call_ev = ev if call_ev is None else max(call_ev, ev)
            if kind in ("RAISE", "BET", "ALLIN"):
                ev = _action_ev(
                    action=act,
                    equity=equity,
                    pot_chips=pot_chips,
                    actor_commit=actor_commit,
                    to_call=to_call,
                    players_alive=players_alive,
                    street="PREFLOP",
                )
                raise_ev = ev if raise_ev is None else max(raise_ev, ev)
        if call_ev is None or raise_ev is None:
            return legal_actions
        pot_unit = max(1.0, float(pot_chips + to_call))
        risk_bias = rake_delta_weight + (mw_risk_weight * max(0, players_alive - 2))
        if pos_key in ("SB", "BB"):
            risk_bias += oop_risk_weight
        margin = (pot_unit * (0.015 + 0.5 * rake_rate) + float(to_call) * 0.15) * (1.0 + risk_bias)
        margin = max(1.0, margin)
        if raise_ev < (call_ev + margin):
            return [a for a in legal_actions if str(a.get("kind")) not in ("RAISE", "BET", "ALLIN")]
        return legal_actions

    def _choose_action_by_ev(
        *,
        legal_actions: list[dict[str, Any]],
        equity: float,
        pot_chips: int,
        actor_commit: int,
        to_call: int,
        stack_chips: int | None = None,
        players_alive: int,
        street: str | None,
        state_hash: str | None,
        entry: dict[str, Any] | None = None,
        facing_bet: bool = False,
        defend_rate_fn: Callable[[dict[str, Any]], float | None] | None = None,
        prior_weights: dict[str, int] | None = None,
        ev_slack: float | None = None,
        min_ev_for_priors: float | None = None,
        uncertainty: float | None = None,
        defend_target: float | None = None,
        pos_key: str | None = None,
        force_defend: bool | None = None,
        prior_street_aggressor: bool | None = None,
        oop_aggression_gate: bool | None = None,
        board_texture: tuple[str, str] | None = None,
        solver_hint_kind: str | None = None,
        solver_hint_target: int | None = None,
        solver_call_ev: float | None = None,
        solver_raise_ev: float | None = None,
        solver_edge: float | None = None,
        call_realization: float | None = None,
        effective_opponents: int | None = None,
        adaptive_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not legal_actions:
            return None
        trace_active = bool(facing_bet and to_call > 0 and pos_key in ("SB", "BB"))
        defense_trace: dict[str, Any] = {}
        adaptive_trace: dict[str, Any] = {}
        actions_pool = legal_actions
        adaptive_enabled = False
        adaptive_expert = "anchor"
        adaptive_alpha = 0.0
        adaptive_conf = 0.0
        adaptive_force_anchor = True
        adaptive_samples = 0
        adaptive_opp_defense = None
        adaptive_open_rate = None
        def _ppm_local(value: float | None, *, limit: float) -> int | None:
            if value is None:
                return None
            try:
                v = float(value)
            except Exception:
                return None
            if not math.isfinite(v):
                return None
            v = max(-limit, min(limit, v))
            return int(round(v * 1_000_000))
        if isinstance(adaptive_profile, dict):
            adaptive_enabled = bool(adaptive_profile.get("enabled"))
            expert_raw = adaptive_profile.get("expert")
            if isinstance(expert_raw, str) and expert_raw in ("anchor", "tight_defense", "pressure"):
                adaptive_expert = expert_raw
            try:
                adaptive_alpha = float(adaptive_profile.get("alpha", 0.0) or 0.0)
            except Exception:
                adaptive_alpha = 0.0
            adaptive_alpha = max(0.0, min(0.50, adaptive_alpha))
            try:
                adaptive_conf = float(adaptive_profile.get("conf", 0.0) or 0.0)
            except Exception:
                adaptive_conf = 0.0
            adaptive_conf = max(0.0, min(1.0, adaptive_conf))
            adaptive_force_anchor = bool(adaptive_profile.get("force_anchor", True))
            try:
                adaptive_samples = int(adaptive_profile.get("samples", 0) or 0)
            except Exception:
                adaptive_samples = 0
            try:
                adaptive_opp_defense = (
                    float(adaptive_profile.get("opp_defense_rate"))
                    if adaptive_profile.get("opp_defense_rate") is not None
                    else None
                )
            except Exception:
                adaptive_opp_defense = None
            try:
                adaptive_open_rate = float(adaptive_profile.get("open_rate")) if adaptive_profile.get("open_rate") is not None else None
            except Exception:
                adaptive_open_rate = None
            if adaptive_enabled:
                adaptive_trace = {
                    "adaptive_trace_schema_id": "adaptive_trace_v1",
                    "adaptive_enabled": True,
                    "adaptive_expert": adaptive_expert,
                    "adaptive_alpha_ppm": _ppm_local(adaptive_alpha, limit=1.0),
                    "adaptive_conf_ppm": _ppm_local(adaptive_conf, limit=1.0),
                    "adaptive_force_anchor": bool(adaptive_force_anchor),
                    "adaptive_samples": int(max(0, adaptive_samples)),
                    "adaptive_opp_defense_ppm": _ppm_local(adaptive_opp_defense, limit=1.0),
                    "adaptive_open_rate_ppm": _ppm_local(adaptive_open_rate, limit=1.0),
                }
        # Keep this trace field bound across all facing-bet paths. _select_from()
        # may update it later for TURN support lanes, but other streets still emit
        # the same trace key.
        turn_focus_support_raise_clamp_strength = 0.0
        if facing_bet and to_call > 0 and street in ("FLOP", "TURN", "RIVER") and pos_key is not None:
            defend_actions = [a for a in legal_actions if str(a.get("kind")) in ("CALL", "RAISE", "BET", "ALLIN")]
            fold_actions = [a for a in legal_actions if str(a.get("kind")) == "FOLD"]
            if force_defend is True:
                if defend_actions:
                    actions_pool = defend_actions
            elif force_defend is False:
                if fold_actions:
                    actions_pool = fold_actions
        if (
            facing_bet
            and to_call > 0
            and street in ("FLOP", "TURN", "RIVER")
            and facing_high_price_threshold is not None
            and equity is not None
        ):
            pot_unit_local = float(max(1, pot_chips + to_call))
            price = float(to_call) / pot_unit_local
            gap1 = facing_high_price_defend_gap
            gap2 = facing_high_price_defend_gap2
            threshold2_local = facing_high_price_threshold2
            penalty = 0.0
            spr_low_price_penalty = 0.0
            turn_river_pressure_penalty = 0.0
            turn_river_support_bridge_penalty = 0.0
            turn_river_support_deadlock_penalty = 0.0
            turn_focus_support_ramp_penalty = 0.0
            turn_focus_support_reentry_penalty = 0.0
            turn_focus_support_hit_recenter_relief = 0.0
            turn_focus_support_raise_clamp_strength = 0.0
            turn_focus_deadlock_threshold_relief = 0.0
            wet_low_spr_firewall_penalty = 0.0
            wet_low_spr_firewall_extreme_penalty = 0.0
            wet_low_spr_firewall_recenter_penalty = 0.0
            wet_low_spr_firewall_cap = 0.0
            wet_low_spr_firewall_scale = 0.0
            river_threshold_recheck_penalty = 0.0
            river_threshold_tail_penalty = 0.0
            river_wet_mw_clamp_penalty = 0.0
            river_forced_bet_guard_penalty = 0.0
            river_forced_bet_commitment_penalty = 0.0
            river_forced_bet_near_trigger_penalty = 0.0
            river_forced_bet_ultra_low_spr_penalty = 0.0
            river_forced_bet_support_floor_penalty = 0.0
            river_forced_bet_support_recenter_penalty = 0.0
            river_forced_bet_support_bridge_penalty = 0.0
            river_forced_bet_support_apron_penalty = 0.0
            river_forced_bet_support_window_expand = 0.0
            river_forced_bet_support_window_cap = None
            river_forced_bet_support_taper = 0.0
            river_forced_bet_support_taper_relief = 0.0
            river_forced_bet_support_far_tail_damp = 0.0
            river_forced_bet_support_stall_bonus = 0.0
            river_forced_bet_support_deep_stall_bonus = 0.0
            river_forced_bet_support_entry_bonus = 0.0
            river_forced_bet_support_proximity_bonus = 0.0
            river_forced_bet_support_tail_bonus = 0.0
            river_forced_bet_support_closure_bonus = 0.0
            river_forced_bet_support_saturation_bonus = 0.0
            river_forced_bet_support_cap_relief_bonus = 0.0
            river_forced_bet_support_reactivation_bonus = 0.0
            river_forced_bet_support_reactivation_floor_relief = 0.0
            river_forced_bet_support_ramp_bonus = 0.0
            river_forced_bet_support_deadlock_relief_bonus = 0.0
            river_forced_bet_support_deadlock_relief_ramp_gate = 0.0
            river_forced_bet_guard_trigger = None
            turn_commitment_ratio = None
            turn_commitment_clamp_penalty = 0.0
            river_commitment_ratio = None
            river_commitment_clamp_penalty = 0.0
            wet_score = None
            spr = None
            if (
                facing_high_price_threshold2_spr_low is not None
                or facing_high_price_defend_gap_spr_low_penalty
                or facing_high_price_defend_gap_spr_low_price_scale
                or facing_high_price_defend_gap_spr_mid_penalty
                or facing_high_price_defend_gap_spr_high_penalty
            ) and stack_chips is not None and pot_chips > 0:
                spr = float(stack_chips) / float(pot_chips)
            if (
                facing_high_price_defend_gap_wet_penalty
                or facing_high_price_defend_gap_turn_penalty
                or facing_high_price_threshold2_turn_wet is not None
                or facing_high_price_threshold2_river_wet is not None
                or facing_high_price_defend_gap2_turn_wet is not None
                or facing_high_price_defend_gap2_river_wet is not None
            ):
                wet_score = _board_wet_score(board_texture=board_texture, street=street)
            if wet_score is not None and wet_score >= 1:
                if street == "TURN":
                    if facing_high_price_threshold2_turn_wet is not None:
                        threshold2_local = facing_high_price_threshold2_turn_wet
                    if facing_high_price_defend_gap2_turn_wet is not None:
                        gap2 = facing_high_price_defend_gap2_turn_wet
                elif street == "RIVER":
                    if facing_high_price_threshold2_river_wet is not None:
                        threshold2_local = facing_high_price_threshold2_river_wet
                    if facing_high_price_defend_gap2_river_wet is not None:
                        gap2 = facing_high_price_defend_gap2_river_wet
            if spr is not None and facing_high_price_threshold2_spr_low is not None and spr <= 2.0:
                if threshold2_local is None:
                    threshold2_local = facing_high_price_threshold2_spr_low
                else:
                    threshold2_local = min(float(threshold2_local), float(facing_high_price_threshold2_spr_low))
            if threshold2_local is not None and facing_high_price_threshold is not None:
                threshold2_local = max(float(facing_high_price_threshold), float(threshold2_local))
            if (
                street == "TURN"
                and threshold2_local is not None
                and facing_high_price_threshold is not None
                and players_alive > 2
                and spr is not None
                and spr <= 2.4
                and wet_score is not None
                and wet_score >= 1
            ):
                threshold2_value = float(threshold2_local)
                if threshold2_value > 0.0:
                    near_floor = 0.86 * threshold2_value
                    if price >= near_floor and price < threshold2_value:
                        proximity = max(
                            0.0,
                            min(1.0, (price - near_floor) / max(1e-9, threshold2_value - near_floor)),
                        )
                        turn_focus_deadlock_threshold_relief = 0.010 + 0.020 * proximity
                        if wet_score >= 2:
                            turn_focus_deadlock_threshold_relief += 0.004
                        if spr <= 1.8:
                            turn_focus_deadlock_threshold_relief += 0.003
                        turn_focus_deadlock_threshold_relief = min(
                            0.035,
                            turn_focus_deadlock_threshold_relief,
                        )
                        adjusted_threshold2 = threshold2_value * (1.0 - turn_focus_deadlock_threshold_relief)
                        threshold2_local = max(float(facing_high_price_threshold), adjusted_threshold2)
            if (
                street == "TURN"
                and threshold2_local is not None
                and facing_high_price_threshold is not None
                and players_alive > 2
                and spr is not None
                and spr <= 2.0
                and wet_score is not None
                and wet_score >= 2
            ):
                threshold2_value = float(threshold2_local)
                if threshold2_value > 0.0:
                    visibility_floor = 0.76 * threshold2_value
                    if price >= visibility_floor and price < threshold2_value:
                        visibility_proximity = max(
                            0.0,
                            min(1.0, (price / threshold2_value - 0.76) / 0.24),
                        )
                        low_spr_wet_visibility_midband_unlock = (
                            street == "TURN"
                            and players_alive > 2
                            and wet_score >= 2
                            and spr <= 2.2
                        )
                        # Keep direct-hit unlock bounded to the stalled TURN visibility band.
                        # For the same low-SPR wet multiway branch that already adds support
                        # hands, extend unlock slightly into mid-band so support can register hits.
                        turn_focus_visibility_threshold_relief = 0.010 + 0.035 * visibility_proximity
                        if wet_score >= 3:
                            turn_focus_visibility_threshold_relief += 0.006
                        if spr <= 1.7:
                            turn_focus_visibility_threshold_relief += 0.004
                        if low_spr_wet_visibility_midband_unlock:
                            turn_focus_visibility_threshold_relief += 0.008
                        turn_focus_visibility_threshold_relief = min(
                            0.078 if low_spr_wet_visibility_midband_unlock else 0.065,
                            turn_focus_visibility_threshold_relief,
                        )
                        adjusted_threshold2 = threshold2_value * (
                            1.0 - turn_focus_visibility_threshold_relief
                        )
                        direct_hit_unlock_proximity = 0.55
                        if low_spr_wet_visibility_midband_unlock:
                            direct_hit_unlock_proximity = 0.38
                        if visibility_proximity >= direct_hit_unlock_proximity:
                            adjusted_threshold2 = min(adjusted_threshold2, price)
                        threshold2_local = max(float(facing_high_price_threshold), adjusted_threshold2)
            if gap1 is not None or gap2 is not None:
                if facing_high_price_defend_gap_oop_penalty and pos_key in ("SB", "BB"):
                    penalty += float(facing_high_price_defend_gap_oop_penalty)
                if facing_high_price_defend_gap_mw_penalty and players_alive > 2:
                    penalty += float(facing_high_price_defend_gap_mw_penalty)
                if facing_high_price_defend_gap_wet_penalty and wet_score is not None and wet_score >= 2:
                    penalty += float(facing_high_price_defend_gap_wet_penalty)
                if (
                    facing_high_price_defend_gap_turn_penalty
                    and street == "TURN"
                    and wet_score is not None
                    and wet_score >= 1
                ):
                    penalty += float(facing_high_price_defend_gap_turn_penalty)
                if (
                    (
                        facing_high_price_defend_gap_spr_low_penalty
                        or facing_high_price_defend_gap_spr_mid_penalty
                        or facing_high_price_defend_gap_spr_high_penalty
                    )
                    and spr is not None
                ):
                    if facing_high_price_defend_gap_spr_low_penalty and spr <= 2.0:
                        penalty += float(facing_high_price_defend_gap_spr_low_penalty)
                    if facing_high_price_defend_gap_spr_low_price_scale and spr <= 2.0:
                        scale = float(facing_high_price_defend_gap_spr_low_price_scale)
                        if facing_high_price_defend_gap_spr_low_price_turn_scale and street == "TURN":
                            scale *= float(facing_high_price_defend_gap_spr_low_price_turn_scale)
                        spr_low_price_penalty = scale * price
                        penalty += spr_low_price_penalty
                    if facing_high_price_defend_gap_spr_mid_penalty and spr >= 3.0:
                        penalty += float(facing_high_price_defend_gap_spr_mid_penalty)
                    if facing_high_price_defend_gap_spr_high_penalty and spr >= 6.0:
                        penalty += float(facing_high_price_defend_gap_spr_high_penalty)
                if street in ("TURN", "RIVER") and threshold2_local is not None:
                    threshold2_value = float(threshold2_local)
                    if threshold2_value > 0.0 and price >= (0.90 * threshold2_value):
                        # Use a smooth ramp near threshold2 to avoid cliff behavior while still
                        # hardening high-price TURN/RIVER defense in risky OOP/multiway paths.
                        proximity = max(0.0, min(1.0, (price / threshold2_value - 0.90) / 0.10))
                        risk_weight = 0.0
                        if players_alive > 2 and facing_high_price_defend_gap_mw_penalty:
                            risk_weight += float(facing_high_price_defend_gap_mw_penalty)
                        if pos_key in ("SB", "BB") and facing_high_price_defend_gap_oop_penalty:
                            risk_weight += float(facing_high_price_defend_gap_oop_penalty)
                        if spr is not None and spr <= 2.5 and facing_high_price_defend_gap_spr_low_penalty:
                            risk_weight += float(facing_high_price_defend_gap_spr_low_penalty)
                        if (
                            street == "RIVER"
                            and wet_score is not None
                            and wet_score >= 1
                            and facing_high_price_defend_gap_wet_penalty
                        ):
                            risk_weight += 0.5 * float(facing_high_price_defend_gap_wet_penalty)
                        if risk_weight > 0.0:
                            turn_river_pressure_penalty = proximity * min(0.10, 0.50 * risk_weight)
                            if gap2 is not None:
                                turn_river_pressure_penalty = min(
                                    turn_river_pressure_penalty,
                                    0.60 * float(gap2),
                                )
                            penalty += turn_river_pressure_penalty
                    if (
                        threshold2_value > 0.0
                        and spr is not None
                        and spr <= 2.6
                        and price >= (0.82 * threshold2_value)
                        and (players_alive > 2 or pos_key in ("SB", "BB"))
                    ):
                        # Bridge near-threshold TURN/RIVER support on the stalled high-price
                        # branch without widening behavior into low-price paths.
                        bridge_risk = 0.0
                        if players_alive > 2 and facing_high_price_defend_gap_mw_penalty:
                            bridge_risk += 0.75 * float(facing_high_price_defend_gap_mw_penalty)
                        if pos_key in ("SB", "BB") and facing_high_price_defend_gap_oop_penalty:
                            bridge_risk += 0.65 * float(facing_high_price_defend_gap_oop_penalty)
                        if facing_high_price_defend_gap_spr_low_penalty:
                            bridge_risk += 0.45 * float(facing_high_price_defend_gap_spr_low_penalty)
                        if wet_score is not None and wet_score >= 1 and facing_high_price_defend_gap_wet_penalty:
                            bridge_wet_scale = 0.45 if street == "TURN" else 0.60
                            bridge_risk += bridge_wet_scale * float(facing_high_price_defend_gap_wet_penalty)
                        if street == "TURN" and facing_high_price_defend_gap_turn_penalty:
                            bridge_risk += 0.25 * float(facing_high_price_defend_gap_turn_penalty)
                        if bridge_risk > 0.0:
                            bridge_entry = 0.82
                            bridge_span = 0.18
                            if (
                                street == "TURN"
                                and players_alive > 2
                                and wet_score is not None
                                and wet_score >= 1
                                and spr is not None
                                and spr <= 2.4
                            ):
                                # Narrow TURN-only bridge relief on the stalled low-support branch.
                                # Keep it bounded and near-threshold to avoid widening low-price paths.
                                bridge_entry = 0.78
                                bridge_span = 0.22
                            bridge_proximity = max(
                                0.0,
                                min(1.0, (price / threshold2_value - bridge_entry) / bridge_span),
                            )
                            bridge_cap = 0.016
                            if street == "TURN" and bridge_entry < 0.82:
                                bridge_cap += 0.002
                            if street == "RIVER":
                                bridge_cap += 0.004
                            if players_alive > 2 and wet_score is not None and wet_score >= 1:
                                bridge_cap += 0.003
                            turn_river_support_bridge_penalty = bridge_proximity * min(
                                bridge_cap,
                                0.26 * bridge_risk,
                            )
                            if gap2 is not None:
                                gap2_scale = 0.20
                                if street == "TURN" and bridge_entry < 0.82:
                                    gap2_scale = 0.24
                                turn_river_support_bridge_penalty = min(
                                    turn_river_support_bridge_penalty,
                                    gap2_scale * float(gap2),
                                )
                            penalty += turn_river_support_bridge_penalty
                            if (
                                street == "TURN"
                                and players_alive > 2
                                and wet_score is not None
                                and wet_score >= 1
                                and spr is not None
                                and spr <= 2.2
                                and price >= (max(0.74, bridge_entry - 0.04) * threshold2_value)
                                and price < (0.98 * threshold2_value)
                            ):
                                # Keep deadlock relief localized to the TURN near-threshold
                                # bridge window where focus support repeatedly stalls.
                                deadlock_entry = max(0.74, bridge_entry - 0.04)
                                deadlock_span = max(0.12, 0.98 - deadlock_entry)
                                deadlock_proximity = max(
                                    0.0,
                                    min(
                                        1.0,
                                        (price / threshold2_value - deadlock_entry) / deadlock_span,
                                    ),
                                )
                                deadlock_cap = 0.0035
                                if wet_score >= 2:
                                    deadlock_cap += 0.001
                                if spr <= 1.9:
                                    deadlock_cap += 0.001
                                turn_river_support_deadlock_penalty = deadlock_proximity * min(
                                    deadlock_cap,
                                    0.13 * bridge_risk,
                                )
                                if gap2 is not None:
                                    turn_river_support_deadlock_penalty = min(
                                        turn_river_support_deadlock_penalty,
                                        0.11 * float(gap2),
                                    )
                                penalty += turn_river_support_deadlock_penalty
                    if (
                        threshold2_value > 0.0
                        and street == "TURN"
                        and spr is not None
                        and spr <= 2.6
                        and wet_score is not None
                        and wet_score >= 1
                        and price >= (0.68 * threshold2_value)
                        and price < (0.98 * threshold2_value)
                        and (players_alive > 2 or pos_key in ("SB", "BB"))
                    ):
                        # Single-mechanism support ramp for stalled TURN near-threshold paths.
                        # Keep the adjustment bounded and localized so quick-gate can observe
                        # measurable behavior shift without widening low-price branches.
                        ramp_risk = 0.0
                        if players_alive > 2 and facing_high_price_defend_gap_mw_penalty:
                            ramp_risk += 0.60 * float(facing_high_price_defend_gap_mw_penalty)
                        if pos_key in ("SB", "BB") and facing_high_price_defend_gap_oop_penalty:
                            ramp_risk += 0.55 * float(facing_high_price_defend_gap_oop_penalty)
                        if facing_high_price_defend_gap_spr_low_penalty:
                            ramp_risk += 0.40 * float(facing_high_price_defend_gap_spr_low_penalty)
                        if facing_high_price_defend_gap_wet_penalty:
                            ramp_risk += 0.45 * float(facing_high_price_defend_gap_wet_penalty)
                        if facing_high_price_defend_gap_turn_penalty:
                            ramp_risk += 0.35 * float(facing_high_price_defend_gap_turn_penalty)
                        if ramp_risk > 0.0:
                            ramp_entry = 0.72
                            ramp_span = 0.26
                            # Broaden support coverage only on high-risk stalled branches.
                            if (
                                players_alive > 2
                                and spr <= 2.6
                                and wet_score >= 1
                                and turn_river_support_deadlock_penalty <= 0.0
                                and turn_river_support_bridge_penalty <= 0.0012
                            ):
                                ramp_entry = 0.66
                                ramp_span = 0.32
                            elif players_alive > 2 and spr <= 2.4 and wet_score >= 1:
                                ramp_entry = 0.68
                                ramp_span = 0.30
                            if players_alive > 2 and spr <= 2.2 and wet_score >= 2:
                                ramp_entry = 0.64
                                ramp_span = 0.34
                            if players_alive > 2 and spr <= 1.8 and wet_score >= 3:
                                ramp_entry = 0.60
                                ramp_span = 0.38
                            ramp_proximity = max(
                                0.0,
                                min(1.0, (price / threshold2_value - ramp_entry) / ramp_span),
                            )
                            ramp_cap = 0.007
                            if ramp_entry < 0.72:
                                ramp_cap += 0.002
                            if ramp_entry <= 0.64:
                                ramp_cap += 0.001
                            if players_alive > 2:
                                ramp_cap += 0.002
                            if spr <= 2.0:
                                ramp_cap += 0.001
                            if wet_score >= 2:
                                ramp_cap += 0.001
                            turn_focus_support_ramp_penalty = ramp_proximity * min(
                                ramp_cap,
                                0.18 * ramp_risk,
                            )
                            if gap2 is not None:
                                ramp_gap2_scale = 0.14
                                if ramp_entry <= 0.64:
                                    ramp_gap2_scale = 0.17
                                turn_focus_support_ramp_penalty = min(
                                    turn_focus_support_ramp_penalty,
                                    ramp_gap2_scale * float(gap2),
                                )
                            penalty += turn_focus_support_ramp_penalty
                            ramp_reentry_fallback_trigger = (
                                turn_focus_support_ramp_penalty >= 0.0015
                                and players_alive > 2
                                and wet_score >= 2
                                and spr <= 2.0
                                and price >= (0.76 * threshold2_value)
                            )
                            ramp_reentry_severe_trigger = (
                                turn_focus_support_ramp_penalty >= 0.0010
                                and players_alive > 2
                                and wet_score >= 3
                                and spr <= 1.8
                                and price >= (0.72 * threshold2_value)
                            )
                            ramp_reentry_support_starvation_trigger = (
                                turn_focus_support_ramp_penalty >= 0.0008
                                and turn_river_support_deadlock_penalty <= 0.0
                                and players_alive > 2
                                and wet_score >= 2
                                and spr <= 2.2
                                and price >= (0.70 * threshold2_value)
                            )
                            ramp_reentry_support_starvation_soft_trigger = (
                                turn_focus_support_ramp_penalty >= 0.0006
                                and turn_river_support_deadlock_penalty <= 0.0
                                and players_alive > 2
                                and wet_score >= 2
                                and spr <= 2.4
                                and price >= (0.66 * threshold2_value)
                            )
                            ramp_reentry_support_starvation_stall_trigger = (
                                turn_focus_support_ramp_penalty >= 0.00035
                                and turn_river_support_deadlock_penalty <= 0.0
                                and turn_river_support_bridge_penalty <= 0.00035
                                and players_alive > 2
                                and wet_score >= 1
                                and spr <= 2.8
                                and price >= (0.62 * threshold2_value)
                            )
                            ramp_reentry_support_visibility_trigger = (
                                turn_focus_support_ramp_penalty >= 0.0002
                                and turn_focus_support_ramp_penalty < 0.00035
                                and turn_river_support_deadlock_penalty <= 0.0
                                and turn_river_support_bridge_penalty <= 0.0002
                                and players_alive > 2
                                and wet_score >= 1
                                and spr <= 2.6
                                and price >= (0.60 * threshold2_value)
                            )
                            ramp_reentry_support_visibility_recovery_trigger = (
                                turn_focus_support_ramp_penalty >= 0.00012
                                and turn_focus_support_ramp_penalty < 0.00035
                                and turn_river_support_deadlock_penalty <= 0.00015
                                and turn_river_support_bridge_penalty <= 0.00015
                                and players_alive > 2
                                and wet_score >= 1
                                and spr <= 2.8
                                and price >= (0.56 * threshold2_value)
                            )
                            ramp_reentry_support_visibility_bridge_trigger = (
                                turn_focus_support_ramp_penalty >= 0.00010
                                and turn_focus_support_ramp_penalty < 0.00040
                                and turn_river_support_deadlock_penalty <= 0.00010
                                and turn_river_support_bridge_penalty > 0.00012
                                and turn_river_support_bridge_penalty <= 0.00045
                                and players_alive > 2
                                and wet_score >= 1
                                and spr <= 2.8
                                and price >= (0.58 * threshold2_value)
                            )
                            ramp_reentry_support_visibility_floor_trigger = (
                                turn_focus_support_ramp_penalty >= 0.00006
                                and turn_focus_support_ramp_penalty < 0.00012
                                and turn_river_support_deadlock_penalty <= 0.00010
                                and turn_river_support_bridge_penalty <= 0.00012
                                and players_alive > 2
                                and wet_score >= 1
                                and spr <= 3.0
                                and price >= (0.54 * threshold2_value)
                            )
                            ramp_reentry_bridge_trigger = (
                                turn_focus_support_ramp_penalty <= 0.0
                                and turn_river_support_bridge_penalty >= 0.0010
                                and players_alive > 2
                                and wet_score >= 1
                                and spr <= 2.4
                                and price >= (0.68 * threshold2_value)
                            )
                            ramp_reentry_probe_trigger = (
                                turn_focus_support_ramp_penalty >= 0.0004
                                and turn_river_support_deadlock_penalty <= 0.0
                                and turn_river_support_bridge_penalty >= 0.0004
                                and players_alive > 2
                                and wet_score >= 1
                                and spr <= 2.6
                                and price >= (0.64 * threshold2_value)
                            )
                            reentry_activation_floor = 0.74
                            reentry_spr_ceiling = 2.0
                            if ramp_reentry_support_starvation_trigger:
                                reentry_activation_floor = 0.70
                                reentry_spr_ceiling = 2.2
                            elif ramp_reentry_support_starvation_soft_trigger:
                                reentry_activation_floor = 0.66
                                reentry_spr_ceiling = 2.4
                            elif ramp_reentry_support_starvation_stall_trigger:
                                reentry_activation_floor = 0.62
                                reentry_spr_ceiling = 2.8
                            elif ramp_reentry_support_visibility_floor_trigger:
                                reentry_activation_floor = 0.54
                                reentry_spr_ceiling = 3.0
                            elif ramp_reentry_support_visibility_recovery_trigger:
                                reentry_activation_floor = 0.56
                                reentry_spr_ceiling = 2.8
                            elif ramp_reentry_support_visibility_bridge_trigger:
                                reentry_activation_floor = 0.58
                                reentry_spr_ceiling = 2.8
                            elif ramp_reentry_support_visibility_trigger:
                                reentry_activation_floor = 0.60
                                reentry_spr_ceiling = 2.6
                            elif ramp_reentry_bridge_trigger:
                                reentry_activation_floor = 0.68
                                reentry_spr_ceiling = 2.4
                            elif ramp_reentry_probe_trigger:
                                reentry_activation_floor = 0.64
                                reentry_spr_ceiling = 2.6
                            bridge_probe_relaxed_wet_branch = (
                                (
                                    ramp_reentry_bridge_trigger
                                    or ramp_reentry_probe_trigger
                                    or ramp_reentry_support_starvation_stall_trigger
                                )
                                and turn_river_support_deadlock_penalty <= 0.0
                                and turn_focus_support_ramp_penalty <= 0.0012
                                and spr <= 2.8
                            )
                            visibility_relaxed_wet_branch = (
                                (
                                    ramp_reentry_support_visibility_trigger
                                    or ramp_reentry_support_visibility_recovery_trigger
                                    or ramp_reentry_support_visibility_bridge_trigger
                                    or ramp_reentry_support_visibility_floor_trigger
                                )
                                and turn_river_support_deadlock_penalty <= 0.00015
                                and turn_river_support_bridge_penalty <= 0.00045
                                and spr <= 3.0
                            )
                            visibility_low_spr_wet_reentry_branch = (
                                street == "TURN"
                                and visibility_relaxed_wet_branch
                                and players_alive > 2
                                and wet_score >= 2
                                and spr <= 2.2
                                and turn_river_support_deadlock_penalty <= 0.00010
                            )
                            reentry_required_wet_score = (
                                1 if (bridge_probe_relaxed_wet_branch or visibility_relaxed_wet_branch) else 2
                            )
                            if (
                                players_alive > 2
                                and wet_score >= reentry_required_wet_score
                                and spr <= reentry_spr_ceiling
                                and price >= (reentry_activation_floor * threshold2_value)
                                and (
                                    turn_river_support_deadlock_penalty > 0.0
                                    or ramp_reentry_fallback_trigger
                                    or ramp_reentry_severe_trigger
                                    or ramp_reentry_support_starvation_trigger
                                    or ramp_reentry_support_starvation_soft_trigger
                                    or ramp_reentry_support_starvation_stall_trigger
                                    or ramp_reentry_support_visibility_floor_trigger
                                    or ramp_reentry_support_visibility_recovery_trigger
                                    or ramp_reentry_support_visibility_bridge_trigger
                                    or ramp_reentry_support_visibility_trigger
                                    or ramp_reentry_bridge_trigger
                                    or ramp_reentry_probe_trigger
                                )
                            ):
                                # Add a small TURN-only reentry push when the stalled high-price
                                # branch exposes deadlock/support-ramp or visibility starvation.
                                reentry_entry = 0.74
                                reentry_span = 0.22
                                reentry_cap = 0.0025
                                severe_ramp_reentry = False
                                if (
                                    turn_focus_support_ramp_penalty > 0.0
                                    and turn_river_support_deadlock_penalty >= 0.0012
                                ):
                                    # Only on persistent deadlock branches: widen the TURN
                                    # near-threshold reentry aperture to improve support hits.
                                    reentry_entry = 0.70
                                    reentry_span = 0.28
                                    reentry_cap += 0.0012
                                elif ramp_reentry_fallback_trigger or ramp_reentry_severe_trigger:
                                    # When deadlock penalty does not fire but ramp pressure is
                                    # already active on the stalled TURN branch, keep a bounded
                                    # fallback re-entry push to increase focus-support hits.
                                    severe_ramp_reentry = ramp_reentry_severe_trigger
                                    reentry_entry = 0.72
                                    reentry_span = 0.24
                                    reentry_cap += 0.0009
                                    if severe_ramp_reentry:
                                        # In low-SPR + very wet branches, allow a slightly wider
                                        # near-threshold aperture to break support-hit starvation.
                                        reentry_entry = 0.70
                                        reentry_span = 0.28
                                        reentry_cap += 0.0007
                                elif ramp_reentry_support_starvation_trigger:
                                    # If ramp pressure is active but deadlock signal stayed below
                                    # threshold, allow a bounded TURN-only reentry window to
                                    # avoid repeated zero-hit support cycles.
                                    reentry_entry = 0.70
                                    reentry_span = 0.28
                                    reentry_cap += 0.0010
                                elif ramp_reentry_bridge_trigger:
                                    # If the near-threshold bridge path is active but ramp
                                    # support did not trigger, add a bounded reentry aperture
                                    # to break support-hit starvation on stalled TURN branches.
                                    reentry_entry = 0.68
                                    reentry_span = 0.32
                                    reentry_cap += 0.0009
                                elif ramp_reentry_support_starvation_soft_trigger:
                                    # Keep a softer fallback aperture for stalled branches where
                                    # support ramp is active but hard starvation trigger misses.
                                    reentry_entry = 0.66
                                    reentry_span = 0.34
                                    reentry_cap += 0.0008
                                elif ramp_reentry_support_starvation_stall_trigger:
                                    # Stall trigger: support-ramp is active but both deadlock and
                                    # bridge signals stay too weak, so widen a bounded aperture to
                                    # avoid repeated zero-hit support cycles.
                                    reentry_entry = 0.62
                                    reentry_span = 0.38
                                    reentry_cap += 0.0006
                                elif ramp_reentry_support_visibility_floor_trigger:
                                    # Floor trigger: visibility signal exists but remains below the
                                    # existing recovery band. Add a tiny low-signal aperture so
                                    # stalled support hands can produce observable hits.
                                    reentry_entry = 0.54
                                    reentry_span = 0.46
                                    reentry_cap += 0.0004
                                elif ramp_reentry_support_visibility_recovery_trigger:
                                    # Recovery trigger: convert low-signal visibility branches
                                    # into bounded support hits when support hands grow but hits
                                    # remain at zero across consecutive cycles.
                                    reentry_entry = 0.56
                                    reentry_span = 0.44
                                    reentry_cap += 0.0007
                                elif ramp_reentry_support_visibility_bridge_trigger:
                                    # Bridge-gap trigger: keep support reentry bounded when bridge
                                    # pressure is small but still above the existing visibility
                                    # floor, a gap that currently adds support hands without hits.
                                    reentry_entry = 0.58
                                    reentry_span = 0.42
                                    reentry_cap += 0.0008
                                elif ramp_reentry_support_visibility_trigger:
                                    # Visibility trigger: ramp pressure exists but stays just below
                                    # the stall threshold, so open a very small pre-stall reentry
                                    # aperture to convert stalled support hands into observable hits.
                                    reentry_entry = 0.60
                                    reentry_span = 0.40
                                    reentry_cap += 0.0005
                                elif ramp_reentry_probe_trigger:
                                    # Probe-only fallback for stalled near-threshold TURN branches
                                    # where bridge pressure is present but existing triggers miss.
                                    reentry_entry = 0.64
                                    reentry_span = 0.36
                                    reentry_cap += 0.0007
                                if bridge_probe_relaxed_wet_branch:
                                    # Keep this narrow: bridge/probe fallback can fire with wet=1
                                    # only when deadlock/ramp signals stayed near zero.
                                    reentry_entry = min(reentry_entry, 0.66)
                                    reentry_span = max(reentry_span, 0.34)
                                    reentry_cap = min(0.0030, max(reentry_cap, 0.0022))
                                if visibility_low_spr_wet_reentry_branch:
                                    # Tight TURN-only reinforcement for low-SPR wet visibility
                                    # branches where support hands grow but still produce zero hits.
                                    reentry_entry = min(reentry_entry, 0.58)
                                    reentry_span = max(reentry_span, 0.42)
                                    reentry_cap = min(0.0032, max(reentry_cap, 0.0024))
                                reentry_proximity = max(
                                    0.0,
                                    min(1.0, (price / threshold2_value - reentry_entry) / reentry_span),
                                )
                                support_hit_recenter_branch = (
                                    street == "TURN"
                                    and players_alive > 2
                                    and wet_score >= 2
                                    and spr <= 2.0
                                    and (
                                        visibility_low_spr_wet_reentry_branch
                                        or ramp_reentry_support_visibility_floor_trigger
                                        or ramp_reentry_support_visibility_recovery_trigger
                                        or ramp_reentry_support_visibility_bridge_trigger
                                    )
                                )
                                if support_hit_recenter_branch:
                                    # Keep the hit recenter strictly inside the stalled TURN
                                    # visibility-reentry lane so repeated support hands can
                                    # register observable hits without broadening low-price paths.
                                    turn_focus_support_hit_recenter_relief = (
                                        0.016 + (0.050 * reentry_proximity)
                                    )
                                    if visibility_low_spr_wet_reentry_branch:
                                        turn_focus_support_hit_recenter_relief += 0.010
                                    if spr <= 1.8:
                                        turn_focus_support_hit_recenter_relief += 0.006
                                    if wet_score >= 3:
                                        turn_focus_support_hit_recenter_relief += 0.004
                                    turn_focus_support_hit_recenter_relief = min(
                                        0.092,
                                        turn_focus_support_hit_recenter_relief,
                                    )
                                    adjusted_reentry_threshold2 = threshold2_value * (
                                        1.0 - turn_focus_support_hit_recenter_relief
                                    )
                                    if reentry_proximity >= 0.34:
                                        adjusted_reentry_threshold2 = min(
                                            adjusted_reentry_threshold2,
                                            price,
                                        )
                                    threshold2_local = max(
                                        float(facing_high_price_threshold),
                                        adjusted_reentry_threshold2,
                                    )
                                    threshold2_value = float(threshold2_local)
                                    # Escalate repeated zero-hit support lanes by directly
                                    # clamping raise share once the TURN visibility-reentry
                                    # branch is already active, rather than widening thresholds again.
                                    turn_focus_support_raise_clamp_strength = (
                                        0.22 + (0.44 * reentry_proximity)
                                    )
                                    if visibility_low_spr_wet_reentry_branch:
                                        turn_focus_support_raise_clamp_strength += 0.14
                                    if spr <= 1.8:
                                        turn_focus_support_raise_clamp_strength += 0.08
                                    if wet_score >= 3:
                                        turn_focus_support_raise_clamp_strength += 0.05
                                    turn_focus_support_raise_clamp_strength = min(
                                        0.88,
                                        turn_focus_support_raise_clamp_strength,
                                    )
                                if spr <= 1.8:
                                    reentry_cap += 0.0008
                                if wet_score >= 3:
                                    reentry_cap += 0.0007
                                turn_focus_support_reentry_penalty = reentry_proximity * min(
                                    reentry_cap,
                                    0.08 * ramp_risk,
                                )
                                if gap2 is not None:
                                    reentry_gap2_scale = 0.07
                                    if reentry_entry < 0.74:
                                        reentry_gap2_scale = 0.09
                                    if severe_ramp_reentry:
                                        reentry_gap2_scale = 0.10
                                    if visibility_low_spr_wet_reentry_branch:
                                        reentry_gap2_scale = max(reentry_gap2_scale, 0.10)
                                    turn_focus_support_reentry_penalty = min(
                                        turn_focus_support_reentry_penalty,
                                        reentry_gap2_scale * float(gap2),
                                    )
                                penalty += turn_focus_support_reentry_penalty
                    firewall_support_hit_recenter_branch = (
                        threshold2_value > 0.0
                        and street == "TURN"
                        and players_alive > 2
                        and wet_score is not None
                        and wet_score >= 2
                        and spr is not None
                        and spr <= 1.9
                        and price >= (0.80 * threshold2_value)
                        and turn_river_support_deadlock_penalty <= 0.00015
                        and turn_river_support_bridge_penalty <= 0.00045
                        and turn_focus_support_ramp_penalty <= 0.0012
                    )
                    if (
                        threshold2_value > 0.0
                        and spr is not None
                        and spr <= 2.2
                        and wet_score is not None
                        and wet_score >= 1
                        and (
                            price >= (0.85 * threshold2_value)
                            or firewall_support_hit_recenter_branch
                        )
                    ):
                        # Extra bounded clamp for low-SPR wet boards on TURN/RIVER.
                        # This targets the recurring high-price Facing=Y leak without
                        # introducing new params or changing action legality.
                        firewall_risk = 0.0
                        if facing_high_price_defend_gap_spr_low_penalty:
                            firewall_risk += float(facing_high_price_defend_gap_spr_low_penalty)
                        if facing_high_price_defend_gap_wet_penalty:
                            wet_scale = 0.70 if street == "RIVER" else 0.45
                            firewall_risk += wet_scale * float(facing_high_price_defend_gap_wet_penalty)
                        if street == "TURN" and facing_high_price_defend_gap_turn_penalty:
                            firewall_risk += 0.35 * float(facing_high_price_defend_gap_turn_penalty)
                        firewall_low_spr_wet_escalation = (
                            street == "TURN"
                            and players_alive > 2
                            and wet_score is not None
                            and wet_score >= 2
                            and spr is not None
                            and spr <= 2.0
                            and turn_river_support_bridge_penalty <= 0.0012
                        )
                        firewall_support_hit_recenter_escalation = (
                            firewall_support_hit_recenter_branch
                            and turn_river_support_deadlock_penalty <= 0.00010
                        )
                        if firewall_risk > 0.0:
                            firewall_entry = 0.85
                            firewall_span = 0.15
                            if firewall_low_spr_wet_escalation:
                                # Escalate only on stalled TURN low-SPR wet multiway branches
                                # where bridge support remained too weak to shift behavior.
                                firewall_entry = 0.82
                                firewall_span = 0.18
                            if firewall_support_hit_recenter_branch:
                                # Keep this branch narrow: fire earlier only on the exact
                                # stalled TURN low-SPR wet lane where visibility/reentry
                                # changes still fail to produce observable support hits.
                                firewall_entry = min(firewall_entry, 0.80)
                                firewall_span = max(firewall_span, 0.20)
                            if firewall_support_hit_recenter_escalation:
                                firewall_entry = min(firewall_entry, 0.78)
                                firewall_span = max(firewall_span, 0.22)
                            firewall_proximity = max(
                                0.0,
                                min(1.0, (price / threshold2_value - firewall_entry) / firewall_span),
                            )
                            wet_low_spr_firewall_cap = 0.08
                            wet_low_spr_firewall_scale = 0.45
                            if players_alive > 2:
                                wet_low_spr_firewall_cap += 0.01
                                wet_low_spr_firewall_scale += 0.05
                            if street == "RIVER":
                                wet_low_spr_firewall_cap += 0.01
                                wet_low_spr_firewall_scale += 0.05
                            if firewall_low_spr_wet_escalation:
                                wet_low_spr_firewall_cap += 0.015
                                wet_low_spr_firewall_scale += 0.08
                            if firewall_support_hit_recenter_branch:
                                wet_low_spr_firewall_cap += 0.010
                                wet_low_spr_firewall_scale += 0.06
                            if firewall_support_hit_recenter_escalation:
                                wet_low_spr_firewall_cap += 0.006
                                wet_low_spr_firewall_scale += 0.04
                            wet_low_spr_firewall_penalty = firewall_proximity * min(
                                wet_low_spr_firewall_cap,
                                wet_low_spr_firewall_scale * firewall_risk,
                            )
                            if gap2 is not None:
                                wet_low_spr_firewall_penalty = min(
                                    wet_low_spr_firewall_penalty,
                                    0.55 * float(gap2),
                                )
                            penalty += wet_low_spr_firewall_penalty
                            if firewall_support_hit_recenter_branch:
                                firewall_recenter_entry = 0.80
                                firewall_recenter_span = 0.20
                                firewall_recenter_cap = 0.014
                                firewall_recenter_scale = 0.24
                                if firewall_support_hit_recenter_escalation:
                                    firewall_recenter_entry = 0.78
                                    firewall_recenter_span = 0.22
                                    firewall_recenter_cap = 0.018
                                    firewall_recenter_scale = 0.28
                                firewall_recenter_proximity = max(
                                    0.0,
                                    min(
                                        1.0,
                                        (
                                            price / threshold2_value
                                            - firewall_recenter_entry
                                        )
                                        / firewall_recenter_span,
                                    ),
                                )
                                wet_low_spr_firewall_recenter_penalty = (
                                    firewall_recenter_proximity
                                    * min(
                                        firewall_recenter_cap,
                                        firewall_recenter_scale * firewall_risk,
                                    )
                                )
                                if gap2 is not None:
                                    wet_low_spr_firewall_recenter_penalty = min(
                                        wet_low_spr_firewall_recenter_penalty,
                                        firewall_recenter_scale * float(gap2),
                                    )
                                penalty += wet_low_spr_firewall_recenter_penalty
                            if (
                                players_alive > 2
                                and wet_score is not None
                                and wet_score >= 2
                                and spr is not None
                                and spr <= 1.6
                                and price >= (0.92 * threshold2_value)
                            ):
                                # Single-mechanism hardening for stagnating branch:
                                # high-price + low-SPR + wet + multiway on TURN/RIVER.
                                extreme_proximity = max(
                                    0.0,
                                    min(1.0, (price / threshold2_value - 0.92) / 0.10),
                                )
                                extreme_cap = 0.02
                                if street == "RIVER":
                                    extreme_cap += 0.01
                                extreme_scale = 0.25 * firewall_risk
                                if facing_high_price_defend_gap_mw_penalty:
                                    extreme_scale += 0.20 * float(facing_high_price_defend_gap_mw_penalty)
                                wet_low_spr_firewall_extreme_penalty = extreme_proximity * min(
                                    extreme_cap,
                                    extreme_scale,
                                )
                                if gap2 is not None:
                                    wet_low_spr_firewall_extreme_penalty = min(
                                        wet_low_spr_firewall_extreme_penalty,
                                        0.30 * float(gap2),
                                    )
                                penalty += wet_low_spr_firewall_extreme_penalty
                            # Keep the TURN-only add-on branch safe when the earlier
                            # extreme clause does not fire; otherwise the quick gate can
                            # crash before the stalled firewall lane is evaluated.
                            wet_low_spr_firewall_extreme_penalty = 0.0
                            if (
                                street == "TURN"
                                and players_alive > 2
                                and wet_score is not None
                                and wet_score >= 1
                                and spr is not None
                                and spr <= 1.8
                                and price >= (0.89 * threshold2_value)
                            ):
                                # Expand low-SPR wet TURN coverage on the stalled branch so
                                # quick-gate can observe behavior change without widening to low-price paths.
                                turn_extreme_proximity = max(
                                    0.0,
                                    min(1.0, (price / threshold2_value - 0.89) / 0.14),
                                )
                                turn_extreme_cap = 0.015
                                turn_extreme_scale = 0.22 * firewall_risk
                                if facing_high_price_defend_gap_mw_penalty:
                                    turn_extreme_scale += 0.15 * float(facing_high_price_defend_gap_mw_penalty)
                                turn_extreme_penalty = turn_extreme_proximity * min(
                                    turn_extreme_cap,
                                    turn_extreme_scale,
                                )
                                if gap2 is not None:
                                    turn_extreme_penalty = min(
                                        turn_extreme_penalty,
                                        0.22 * float(gap2),
                                    )
                                wet_low_spr_firewall_extreme_penalty += turn_extreme_penalty
                                penalty += turn_extreme_penalty
                    if threshold2_value > 0.0 and street == "TURN" and price >= (0.88 * threshold2_value):
                        # Bounded TURN commitment clamp for high-price facing spots.
                        # Uses existing risk terms and only activates on costly branches.
                        if stack_chips is not None and stack_chips > 0:
                            turn_commitment_ratio = max(0.0, min(1.5, float(to_call) / float(max(1, stack_chips))))
                        turn_risk = 0.0
                        if pos_key in ("SB", "BB") and facing_high_price_defend_gap_oop_penalty:
                            turn_risk += 0.65 * float(facing_high_price_defend_gap_oop_penalty)
                        if players_alive > 2 and facing_high_price_defend_gap_mw_penalty:
                            turn_risk += 0.95 * float(facing_high_price_defend_gap_mw_penalty)
                        if wet_score is not None and wet_score >= 1 and facing_high_price_defend_gap_wet_penalty:
                            turn_risk += 0.45 * float(facing_high_price_defend_gap_wet_penalty)
                        if spr is not None and spr <= 2.8 and facing_high_price_defend_gap_spr_low_penalty:
                            turn_risk += 0.55 * float(facing_high_price_defend_gap_spr_low_penalty)
                        turn_commitment_trigger = 0.28
                        if spr is not None and spr <= 2.4:
                            turn_commitment_trigger -= 0.03
                        if wet_score is not None and wet_score >= 1:
                            turn_commitment_trigger -= 0.01
                        turn_commitment_trigger = max(0.20, turn_commitment_trigger)
                        if (
                            turn_risk > 0.0
                            and turn_commitment_ratio is not None
                            and turn_commitment_ratio >= turn_commitment_trigger
                            and (players_alive > 2 or pos_key in ("SB", "BB"))
                        ):
                            commitment_window = max(0.12, 0.58 - turn_commitment_trigger)
                            commitment_proximity = max(
                                0.0,
                                min(
                                    1.0,
                                    (turn_commitment_ratio - turn_commitment_trigger) / commitment_window,
                                ),
                            )
                            commitment_cap = 0.022
                            if wet_score is not None and wet_score >= 2:
                                commitment_cap += 0.008
                            if players_alive > 2 and spr is not None and spr <= 2.6:
                                commitment_cap += 0.004
                            turn_commitment_clamp_penalty = commitment_proximity * min(
                                commitment_cap,
                                0.34 * turn_risk,
                            )
                            if price < threshold2_value:
                                near_threshold_scale = max(
                                    0.35,
                                    min(1.0, (price / threshold2_value - 0.88) / 0.12),
                                )
                                turn_commitment_clamp_penalty *= near_threshold_scale
                            if gap2 is not None:
                                turn_commitment_clamp_penalty = min(
                                    turn_commitment_clamp_penalty,
                                    0.33 * float(gap2),
                                )
                            penalty += turn_commitment_clamp_penalty
                    if threshold2_value > 0.0 and street == "RIVER" and price >= threshold2_value:
                        # Extra bounded clamp for RIVER high-price spots. This keeps
                        # risk reduction smooth while reducing repeat over-defend in
                        # OOP/multiway/wet paths that dominate current focus leaks.
                        river_commitment_ratio: float | None = None
                        if stack_chips is not None and stack_chips > 0:
                            river_commitment_ratio = max(0.0, min(1.5, float(to_call) / float(max(1, stack_chips))))
                        river_risk = 0.0
                        if pos_key in ("SB", "BB") and facing_high_price_defend_gap_oop_penalty:
                            river_risk += 0.8 * float(facing_high_price_defend_gap_oop_penalty)
                        if players_alive > 2 and facing_high_price_defend_gap_mw_penalty:
                            river_risk += 0.8 * float(facing_high_price_defend_gap_mw_penalty)
                        if wet_score is not None and wet_score >= 1 and facing_high_price_defend_gap_wet_penalty:
                            river_risk += 0.6 * float(facing_high_price_defend_gap_wet_penalty)
                        if spr is not None and spr <= 3.0 and facing_high_price_defend_gap_spr_low_penalty:
                            river_risk += 0.4 * float(facing_high_price_defend_gap_spr_low_penalty)
                        if river_risk > 0.0:
                            recheck_proximity = max(0.0, min(1.0, (price / threshold2_value - 1.0) / 0.20))
                            base_recheck_penalty = (0.35 + 0.65 * recheck_proximity) * min(0.07, 0.45 * river_risk)
                            if price >= (1.12 * threshold2_value):
                                # Tail hardening for very high river prices to create
                                # measurable behavior shift during repeated stagnation.
                                tail_proximity = max(0.0, min(1.0, (price / threshold2_value - 1.12) / 0.18))
                                tail_risk = river_risk
                                if players_alive > 2 and facing_high_price_defend_gap_mw_penalty:
                                    tail_risk += 0.25 * float(facing_high_price_defend_gap_mw_penalty)
                                if wet_score is not None and wet_score >= 2 and facing_high_price_defend_gap_wet_penalty:
                                    tail_risk += 0.30 * float(facing_high_price_defend_gap_wet_penalty)
                                if spr is not None and spr <= 2.6 and facing_high_price_defend_gap_spr_low_penalty:
                                    tail_risk += 0.20 * float(facing_high_price_defend_gap_spr_low_penalty)
                                river_threshold_tail_penalty = tail_proximity * min(0.04, 0.30 * tail_risk)
                                base_recheck_penalty += river_threshold_tail_penalty
                            river_threshold_recheck_penalty = base_recheck_penalty
                            if gap2 is not None:
                                river_threshold_recheck_penalty = min(
                                    river_threshold_recheck_penalty,
                                    0.50 * float(gap2),
                                )
                            penalty += river_threshold_recheck_penalty
                            if (
                                street == "RIVER"
                                and players_alive > 2
                                and wet_score is not None
                                and wet_score >= 2
                                and spr is not None
                                and spr <= 2.4
                            ):
                                # Enforce extra bounded clamp on the exact stagnating
                                # branch: high-price river, multiway, wet board, low SPR.
                                clamp_strength = min(0.03, 0.32 * river_risk)
                                if threshold2_value > 0.0 and price >= threshold2_value:
                                    clamp_proximity = max(
                                        0.0,
                                        min(1.0, (price / threshold2_value - 1.0) / 0.16),
                                    )
                                    clamp_strength *= clamp_proximity
                                if gap2 is not None:
                                    clamp_strength = min(clamp_strength, 0.40 * float(gap2))
                                river_wet_mw_clamp_penalty = max(0.0, clamp_strength)
                                penalty += river_wet_mw_clamp_penalty
                            if (
                                street == "RIVER"
                                and (players_alive > 2 or pos_key in ("SB", "BB"))
                                and spr is not None
                                and spr <= 2.1
                                and threshold2_value > 0.0
                            ):
                                # High-price river forced-bet integrity guard:
                                # bounded de-risking on deep-commitment branches.
                                guard_price_trigger = 1.03
                                if wet_score is not None and wet_score >= 1:
                                    guard_price_trigger -= 0.02
                                if players_alive > 2:
                                    guard_price_trigger -= 0.01
                                if players_alive > 2 and spr <= 1.9:
                                    guard_price_trigger -= 0.02
                                if spr <= 1.6:
                                    guard_price_trigger -= 0.02
                                if wet_score is not None and wet_score >= 2:
                                    guard_price_trigger -= 0.015
                                if players_alive > 2 and wet_score is not None and wet_score >= 1 and spr <= 1.9:
                                    # Broaden support on the stalled multiway forced-bet branch
                                    # without introducing new knobs.
                                    guard_price_trigger -= 0.015
                                if river_commitment_ratio is not None and river_commitment_ratio >= 0.24:
                                    guard_price_trigger -= 0.015
                                if river_commitment_ratio is not None and river_commitment_ratio >= 0.36:
                                    guard_price_trigger -= 0.01
                                guard_price_trigger = max(0.90, guard_price_trigger)
                                river_forced_bet_guard_trigger = guard_price_trigger
                                guard_risk = river_risk
                                if facing_high_price_defend_gap_mw_penalty:
                                    guard_risk += 0.45 * float(facing_high_price_defend_gap_mw_penalty)
                                if facing_high_price_defend_gap_spr_low_penalty:
                                    guard_risk += 0.30 * float(facing_high_price_defend_gap_spr_low_penalty)
                                if (
                                    wet_score is not None
                                    and wet_score >= 1
                                    and facing_high_price_defend_gap_wet_penalty
                                ):
                                    guard_risk += 0.25 * float(facing_high_price_defend_gap_wet_penalty)
                                support_floor_trigger = max(0.88, guard_price_trigger - 0.06)
                                support_bridge_trigger = max(0.82, support_floor_trigger - 0.05)
                                support_apron_trigger = max(0.74, support_bridge_trigger - 0.06)
                                if guard_risk > 0.0:
                                    # Bounded support-window expansion on the exact
                                    # stalled forced-bet branch to improve support hits
                                    # without widening into low-price paths.
                                    if players_alive > 2:
                                        river_forced_bet_support_window_expand += 0.014
                                    if wet_score is not None and wet_score >= 1:
                                        river_forced_bet_support_window_expand += 0.007
                                    if spr is not None and spr <= 1.95:
                                        river_forced_bet_support_window_expand += 0.006
                                    if river_commitment_ratio is not None and river_commitment_ratio >= 0.24:
                                        river_forced_bet_support_window_expand += 0.007
                                    if players_alive > 2 and wet_score is not None and wet_score >= 1:
                                        # Add bounded near-threshold expansion so support penalties
                                        # trigger on more of the stalled forced-bet branch.
                                        support_proximity_anchor = 0.96
                                        support_proximity_span = 0.20
                                        if spr is not None and spr <= 2.0:
                                            support_proximity_anchor -= 0.02
                                            support_proximity_span += 0.02
                                        if river_commitment_ratio is not None and river_commitment_ratio >= 0.24:
                                            support_proximity_anchor -= 0.01
                                        if wet_score >= 2:
                                            support_proximity_anchor -= 0.005
                                        support_proximity_anchor = max(0.88, min(0.98, support_proximity_anchor))
                                        support_proximity_span = max(0.16, min(0.26, support_proximity_span))
                                        support_price_proximity = max(
                                            0.0,
                                            min(
                                                1.0,
                                                (price / threshold2_value - support_proximity_anchor)
                                                / support_proximity_span,
                                            ),
                                        )
                                        if support_price_proximity > 0.0:
                                            proximity_cap = 0.004
                                            if spr is not None and spr <= 1.9:
                                                proximity_cap += 0.002
                                            if (
                                                river_commitment_ratio is not None
                                                and river_commitment_ratio >= 0.28
                                            ):
                                                proximity_cap += 0.002
                                            if (
                                                spr is not None
                                                and spr <= 2.05
                                                and river_commitment_ratio is not None
                                                and river_commitment_ratio >= 0.24
                                            ):
                                                proximity_cap += 0.001
                                            proximity_cap = min(0.009, proximity_cap)
                                            river_forced_bet_support_proximity_bonus = (
                                                support_price_proximity * proximity_cap
                                            )
                                            river_forced_bet_support_window_expand += (
                                                river_forced_bet_support_proximity_bonus
                                            )
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 1
                                        and spr is not None
                                        and spr <= 2.1
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.24
                                    ):
                                        # Bridge-relief bonus: widen support coverage in a narrow
                                        # near-threshold band to avoid no-eligible-candidate stalls.
                                        bridge_relief_proximity = max(
                                            0.0,
                                            min(1.0, (price / threshold2_value - 0.93) / 0.12),
                                        )
                                        if bridge_relief_proximity > 0.0:
                                            bridge_relief_cap = 0.003
                                            if wet_score >= 2:
                                                bridge_relief_cap += 0.001
                                            if spr <= 1.9:
                                                bridge_relief_cap += 0.001
                                            if guard_price_trigger <= 0.95:
                                                bridge_relief_cap += 0.001
                                            river_forced_bet_support_window_expand += min(
                                                0.005,
                                                bridge_relief_proximity * bridge_relief_cap,
                                            )
                                    # Escalate only on the repeatedly stalled forced-bet
                                    # sub-branch (MW + wet + low-SPR and/or deep commitment).
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 1
                                        and spr is not None
                                        and spr <= 2.15
                                    ):
                                        river_forced_bet_support_stall_bonus += 0.009
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 2
                                    ):
                                        river_forced_bet_support_stall_bonus += 0.003
                                    if river_commitment_ratio is not None and river_commitment_ratio >= 0.30:
                                        river_forced_bet_support_stall_bonus += 0.005
                                    if guard_price_trigger <= 0.95:
                                        river_forced_bet_support_stall_bonus += 0.003
                                    river_forced_bet_support_stall_bonus = min(
                                        0.022,
                                        river_forced_bet_support_stall_bonus,
                                    )
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 2
                                        and spr is not None
                                        and spr <= 1.8
                                    ):
                                        river_forced_bet_support_deep_stall_bonus += 0.004
                                    if river_commitment_ratio is not None and river_commitment_ratio >= 0.34:
                                        river_forced_bet_support_deep_stall_bonus += 0.003
                                    if guard_price_trigger <= 0.94:
                                        river_forced_bet_support_deep_stall_bonus += 0.002
                                    river_forced_bet_support_deep_stall_bonus = min(
                                        0.010,
                                        river_forced_bet_support_deep_stall_bonus,
                                    )
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 1
                                        and spr is not None
                                        and spr <= 2.15
                                    ):
                                        river_forced_bet_support_entry_bonus += 0.005
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 2
                                    ):
                                        river_forced_bet_support_entry_bonus += 0.002
                                    if (
                                        players_alive > 2
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.26
                                    ):
                                        river_forced_bet_support_entry_bonus += 0.002
                                    if (
                                        players_alive > 2
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.34
                                    ):
                                        river_forced_bet_support_entry_bonus += 0.001
                                    if players_alive > 2 and guard_price_trigger <= 0.95:
                                        river_forced_bet_support_entry_bonus += 0.001
                                    entry_bonus_cap = 0.012
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 1
                                        and spr is not None
                                        and spr <= 2.0
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.28
                                        and price >= (0.94 * threshold2_value)
                                    ):
                                        # Add a narrow near-threshold bridge bonus on the same
                                        # stalled forced-bet branch to increase support hits and
                                        # behavior separation without widening into low-price paths.
                                        river_forced_bet_support_entry_bonus += 0.002
                                        entry_bonus_cap += 0.002
                                    river_forced_bet_support_entry_bonus = min(
                                        entry_bonus_cap,
                                        river_forced_bet_support_entry_bonus,
                                    )
                                    # Tail-bonus: raise support coverage only on the same
                                    # stalled forced-bet branch with deep commitment context.
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 1
                                        and spr is not None
                                        and spr <= 2.25
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.22
                                    ):
                                        river_forced_bet_support_tail_bonus += 0.003
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 2
                                        and spr is not None
                                        and spr <= 2.0
                                    ):
                                        river_forced_bet_support_tail_bonus += 0.002
                                    if river_commitment_ratio is not None and river_commitment_ratio >= 0.34:
                                        river_forced_bet_support_tail_bonus += 0.002
                                    river_forced_bet_support_tail_bonus = min(
                                        0.008,
                                        river_forced_bet_support_tail_bonus,
                                    )
                                    # Closure bonus: increase support coverage only on
                                    # deep-commitment, low-SPR multiway wet tails.
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 1
                                        and spr is not None
                                        and spr <= 1.85
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.36
                                        and guard_price_trigger <= 0.95
                                    ):
                                        river_forced_bet_support_closure_bonus += 0.003
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 2
                                        and spr is not None
                                        and spr <= 1.7
                                    ):
                                        river_forced_bet_support_closure_bonus += 0.002
                                    river_forced_bet_support_closure_bonus = min(
                                        0.005,
                                        river_forced_bet_support_closure_bonus,
                                    )
                                    # Saturation bonus: only on deep tails already hugging
                                    # threshold2, keeping the effect narrow and rollback-safe.
                                    saturation_bonus_cap = 0.003
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 2
                                        and spr is not None
                                        and spr <= 1.9
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.32
                                        and guard_price_trigger <= 0.95
                                    ):
                                        # Broaden only the deep-tail support window on stalled
                                        # forced-bet branches so near-threshold hands contribute
                                        # behavior/support signals without touching low-price paths.
                                        saturation_start = 0.97
                                        saturation_span = 0.05
                                        if river_commitment_ratio >= 0.36:
                                            saturation_start = 0.95
                                            saturation_span = 0.07
                                            saturation_bonus_cap = 0.004
                                        support_saturation = max(
                                            0.0,
                                            min(
                                                1.0,
                                                (price / threshold2_value - saturation_start)
                                                / saturation_span,
                                            ),
                                        )
                                        if support_saturation > 0.0:
                                            river_forced_bet_support_saturation_bonus += (
                                                saturation_bonus_cap * support_saturation
                                            )
                                    river_forced_bet_support_saturation_bonus = min(
                                        saturation_bonus_cap,
                                        river_forced_bet_support_saturation_bonus,
                                    )
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 1
                                        and spr is not None
                                        and spr <= 2.05
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.26
                                        and guard_price_trigger <= 0.95
                                    ):
                                        support_ramp_proximity = max(
                                            0.0,
                                            min(1.0, (price / threshold2_value - 0.93) / 0.10),
                                        )
                                        if support_ramp_proximity > 0.0:
                                            support_ramp_cap = 0.004
                                            if wet_score >= 2:
                                                support_ramp_cap += 0.001
                                            if spr <= 1.8:
                                                support_ramp_cap += 0.001
                                            if river_commitment_ratio >= 0.34:
                                                support_ramp_cap += 0.001
                                            river_forced_bet_support_ramp_bonus = min(
                                                0.006,
                                                support_ramp_proximity * support_ramp_cap,
                                            )
                                    # Reactivation bonus: when the branch is still under-expanded,
                                    # add a bounded near-threshold lift to improve support coverage.
                                    if (
                                        river_forced_bet_support_window_expand < 0.040
                                        and players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 1
                                        and spr is not None
                                        and spr <= 2.2
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.22
                                    ):
                                        reactivation_floor = 0.93
                                        reactivation_span = 0.12
                                        if (
                                            river_forced_bet_support_stall_bonus > 0.0
                                            and river_forced_bet_support_saturation_bonus <= 0.0
                                            and guard_price_trigger <= 0.95
                                        ):
                                            # Keep this narrow: only relax reactivation floor on
                                            # stalled branches where saturation has not engaged.
                                            reactivation_floor = 0.91
                                            reactivation_span = 0.14
                                            river_forced_bet_support_reactivation_floor_relief = max(
                                                river_forced_bet_support_reactivation_floor_relief,
                                                0.02,
                                            )
                                        reactivation_proximity = max(
                                            0.0,
                                            min(
                                                1.0,
                                                (price / threshold2_value - reactivation_floor)
                                                / reactivation_span,
                                            ),
                                        )
                                        if reactivation_proximity > 0.0:
                                            river_forced_bet_support_reactivation_bonus += (
                                                0.0045 * reactivation_proximity
                                            )
                                            if guard_price_trigger <= 0.95:
                                                river_forced_bet_support_reactivation_bonus += 0.001
                                            if reactivation_floor < 0.93:
                                                river_forced_bet_support_reactivation_bonus += 0.0008
                                                river_forced_bet_support_reactivation_floor_relief = max(
                                                    river_forced_bet_support_reactivation_floor_relief,
                                                    min(
                                                        0.04,
                                                        0.01 + 0.03 * reactivation_proximity,
                                                    ),
                                                )
                                            if (
                                                wet_score >= 2
                                                and spr <= 1.9
                                                and river_commitment_ratio >= 0.30
                                            ):
                                                river_forced_bet_support_reactivation_bonus += 0.0015
                                    reactivation_bonus_cap = 0.006
                                    if river_forced_bet_support_reactivation_floor_relief > 0.0:
                                        reactivation_bonus_cap = 0.0068
                                    river_forced_bet_support_reactivation_bonus = min(
                                        reactivation_bonus_cap,
                                        river_forced_bet_support_reactivation_bonus,
                                    )
                                    river_forced_bet_support_window_expand += (
                                        river_forced_bet_support_entry_bonus
                                    )
                                    river_forced_bet_support_window_expand += (
                                        river_forced_bet_support_stall_bonus
                                    )
                                    if river_forced_bet_support_stall_bonus > 0.0:
                                        river_forced_bet_support_window_expand += (
                                            river_forced_bet_support_deep_stall_bonus
                                        )
                                    river_forced_bet_support_window_expand += (
                                        river_forced_bet_support_tail_bonus
                                    )
                                    river_forced_bet_support_window_expand += (
                                        river_forced_bet_support_closure_bonus
                                    )
                                    river_forced_bet_support_window_expand += (
                                        river_forced_bet_support_saturation_bonus
                                    )
                                    river_forced_bet_support_window_expand += (
                                        river_forced_bet_support_ramp_bonus
                                    )
                                    river_forced_bet_support_window_expand += (
                                        river_forced_bet_support_reactivation_bonus
                                    )
                                    support_window_expand_cap = 0.064
                                    if river_forced_bet_support_tail_bonus > 0.0:
                                        support_window_expand_cap += 0.004
                                    if river_forced_bet_support_closure_bonus > 0.0:
                                        support_window_expand_cap += 0.003
                                    if river_forced_bet_support_saturation_bonus > 0.0:
                                        support_window_expand_cap += 0.002
                                    # Cap-relief bonus: keep window expansion from collapsing
                                    # into flat ties on the recurrent stalled forced-bet branch.
                                    cap_relief_active = (
                                        river_forced_bet_support_stall_bonus > 0.0
                                        and (
                                            river_forced_bet_support_saturation_bonus > 0.0
                                            or river_forced_bet_support_reactivation_bonus > 0.0
                                        )
                                    )
                                    if cap_relief_active:
                                        river_forced_bet_support_cap_relief_bonus = 0.002
                                        if river_forced_bet_support_proximity_bonus > 0.0:
                                            river_forced_bet_support_cap_relief_bonus += 0.001
                                        if (
                                            river_forced_bet_support_saturation_bonus <= 0.0
                                            and river_forced_bet_support_reactivation_bonus > 0.0
                                        ):
                                            # Keep this path narrow: only lift cap when stalled
                                            # reactivation is on but deep-tail saturation is absent.
                                            river_forced_bet_support_cap_relief_bonus += 0.001
                                            if river_forced_bet_support_reactivation_bonus >= 0.0045:
                                                river_forced_bet_support_cap_relief_bonus += 0.001
                                        if (
                                            river_commitment_ratio is not None
                                            and river_commitment_ratio >= 0.34
                                        ):
                                            river_forced_bet_support_cap_relief_bonus += 0.001
                                        river_forced_bet_support_cap_relief_bonus = min(
                                            0.005,
                                            river_forced_bet_support_cap_relief_bonus,
                                        )
                                        support_window_expand_cap += (
                                            river_forced_bet_support_cap_relief_bonus
                                        )
                                        deadlock_relief_price_floor = 0.94
                                        deadlock_relief_cap = 0.0030
                                        deadlock_relief_proximity_gate = 0.0
                                        deadlock_relief_ramp_gate = 0.0
                                        if (
                                            river_forced_bet_support_reactivation_bonus > 0.0
                                            and river_forced_bet_support_saturation_bonus <= 0.0
                                        ):
                                            # Keep this narrow: only widen near-threshold activation
                                            # when reactivation is on but saturation is still absent.
                                            deadlock_relief_price_floor = 0.93
                                            if (
                                                river_forced_bet_support_reactivation_floor_relief > 0.0
                                            ):
                                                # Stalled unsaturated branch: allow a slightly
                                                # wider near-threshold floor and bounded cap lift.
                                                deadlock_relief_price_floor = 0.92
                                                deadlock_relief_cap = 0.0035
                                                # Near-threshold deadlocks can still carry tiny
                                                # positive proximity bonus; allow a narrow gate.
                                                deadlock_relief_proximity_gate = 0.0012
                                                # Same stalled branch can emit tiny ramp bonus;
                                                # keep deadlock bridge open for near-zero ramp.
                                                deadlock_relief_ramp_gate = 0.0012
                                                if (
                                                    river_forced_bet_support_reactivation_bonus
                                                    >= 0.0045
                                                ):
                                                    # Deep stalled reactivation can still collapse
                                                    # to flat ties; widen bridge one notch.
                                                    deadlock_relief_price_floor = 0.91
                                                    deadlock_relief_cap = 0.0038
                                                    deadlock_relief_proximity_gate = 0.0015
                                                    deadlock_relief_ramp_gate = 0.0015
                                        if (
                                            river_forced_bet_support_reactivation_floor_relief > 0.0
                                            and river_forced_bet_support_reactivation_bonus >= 0.0040
                                            and river_forced_bet_support_proximity_bonus <= 0.0012
                                            and river_forced_bet_support_ramp_bonus <= 0.0012
                                        ):
                                            # If the stalled branch still has near-zero proximity/ramp
                                            # activation, widen deadlock recovery one notch to raise
                                            # support-hit coverage without touching low-price paths.
                                            deadlock_relief_price_floor = min(
                                                deadlock_relief_price_floor,
                                                0.90,
                                            )
                                            deadlock_relief_cap = max(
                                                deadlock_relief_cap,
                                                0.0042,
                                            )
                                            deadlock_relief_proximity_gate = max(
                                                deadlock_relief_proximity_gate,
                                                0.0018,
                                            )
                                            deadlock_relief_ramp_gate = max(
                                                deadlock_relief_ramp_gate,
                                                0.0018,
                                            )
                                            support_window_expand_cap = min(
                                                0.063,
                                                support_window_expand_cap + 0.0015,
                                            )
                                        river_forced_bet_support_deadlock_relief_ramp_gate = (
                                            max(
                                                river_forced_bet_support_deadlock_relief_ramp_gate,
                                                deadlock_relief_ramp_gate,
                                            )
                                        )
                                        if (
                                            river_forced_bet_support_proximity_bonus
                                            <= deadlock_relief_proximity_gate
                                            and river_forced_bet_support_ramp_bonus
                                            <= deadlock_relief_ramp_gate
                                            and players_alive > 2
                                            and wet_score is not None
                                            and wet_score >= 1
                                            and spr is not None
                                            and spr <= 2.1
                                            and price >= (
                                                deadlock_relief_price_floor * threshold2_value
                                            )
                                        ):
                                            # Deadlock-relief bonus: keep this narrow and bounded.
                                            # It only activates when stalled cap-relief is on but
                                            # no proximity/ramp lift has been triggered yet.
                                            river_forced_bet_support_deadlock_relief_bonus = 0.0015
                                            if wet_score >= 2:
                                                river_forced_bet_support_deadlock_relief_bonus += 0.0005
                                            if (
                                                river_commitment_ratio is not None
                                                and river_commitment_ratio >= 0.30
                                            ):
                                                river_forced_bet_support_deadlock_relief_bonus += 0.0005
                                            if (
                                                river_forced_bet_support_reactivation_bonus > 0.0
                                                and river_forced_bet_support_saturation_bonus <= 0.0
                                            ):
                                                river_forced_bet_support_deadlock_relief_bonus += 0.0005
                                                if (
                                                    river_forced_bet_support_reactivation_floor_relief > 0.0
                                                ):
                                                    river_forced_bet_support_deadlock_relief_bonus += 0.0005
                                            river_forced_bet_support_deadlock_relief_bonus = min(
                                                deadlock_relief_cap,
                                                river_forced_bet_support_deadlock_relief_bonus,
                                            )
                                            support_window_expand_cap += (
                                                river_forced_bet_support_deadlock_relief_bonus
                                            )
                                    if river_forced_bet_support_reactivation_bonus > 0.0:
                                        support_window_expand_cap += 0.003
                                    if river_forced_bet_support_reactivation_bonus >= 0.0045:
                                        support_window_expand_cap += 0.0015
                                    # Keep expansion concentrated on deep-stall forced-bet tails.
                                    # Outside that branch, taper cap to limit broad regressions.
                                    deep_tail_branch = (
                                        wet_score is not None
                                        and wet_score >= 2
                                        and spr is not None
                                        and spr <= 1.85
                                        and river_commitment_ratio is not None
                                        and river_commitment_ratio >= 0.30
                                    )
                                    if (
                                        players_alive > 2
                                        and wet_score is not None
                                        and wet_score >= 1
                                        and not deep_tail_branch
                                    ):
                                        river_forced_bet_support_taper = 0.006
                                        if spr is not None and spr > 1.9:
                                            river_forced_bet_support_taper += 0.002
                                        if (
                                            river_commitment_ratio is not None
                                            and river_commitment_ratio < 0.28
                                        ):
                                            river_forced_bet_support_taper += 0.002
                                        if (
                                            spr is not None
                                            and spr <= 2.05
                                            and river_commitment_ratio is not None
                                            and river_commitment_ratio >= 0.26
                                            and guard_price_trigger <= 0.95
                                        ):
                                            river_forced_bet_support_taper_relief = 0.002
                                            if wet_score is not None and wet_score >= 2:
                                                river_forced_bet_support_taper_relief += 0.001
                                            if river_commitment_ratio >= 0.32:
                                                river_forced_bet_support_taper_relief += 0.001
                                            river_forced_bet_support_taper_relief = min(
                                                0.004,
                                                river_forced_bet_support_taper_relief,
                                            )
                                            river_forced_bet_support_taper = max(
                                                0.0,
                                                river_forced_bet_support_taper
                                                - river_forced_bet_support_taper_relief,
                                            )
                                            # Keep this widening narrowly scoped to the
                                            # stalled forced-bet support branch.
                                            support_window_expand_cap = min(
                                                0.060,
                                                support_window_expand_cap
                                                + (0.004 if wet_score is not None and wet_score >= 2 else 0.003),
                                            )
                                        support_window_expand_cap = max(
                                            0.052,
                                            support_window_expand_cap - river_forced_bet_support_taper,
                                        )
                                        if threshold2_value > 0.0 and price >= (1.05 * threshold2_value):
                                            # Dampen support-window expansion on far-tail prices where
                                            # guard/recheck penalties already provide sufficient pressure.
                                            far_tail_proximity = max(
                                                0.0,
                                                min(1.0, (price / threshold2_value - 1.05) / 0.20),
                                            )
                                            river_forced_bet_support_far_tail_damp = 0.006 * far_tail_proximity
                                            support_window_expand_cap = max(
                                                0.046,
                                                support_window_expand_cap
                                                - river_forced_bet_support_far_tail_damp,
                                            )
                                    river_forced_bet_support_window_cap = support_window_expand_cap
                                    river_forced_bet_support_window_expand = min(
                                        support_window_expand_cap,
                                        river_forced_bet_support_window_expand,
                                    )
                                    if river_forced_bet_support_window_expand > 0.0:
                                        support_floor_trigger = max(
                                            0.81,
                                            support_floor_trigger - river_forced_bet_support_window_expand,
                                        )
                                        support_bridge_trigger = max(
                                            0.74,
                                            support_bridge_trigger - 0.75 * river_forced_bet_support_window_expand,
                                        )
                                        support_apron_trigger = max(
                                            0.63,
                                            support_apron_trigger - 0.55 * river_forced_bet_support_window_expand,
                                        )
                                if (
                                    guard_risk > 0.0
                                    and river_forced_bet_support_deadlock_relief_bonus > 0.0
                                    and river_forced_bet_support_reactivation_bonus > 0.0
                                    and price >= (support_bridge_trigger * threshold2_value)
                                    and price < (guard_price_trigger * threshold2_value)
                                ):
                                    # Keep deadlock recovery local to the existing support bridge:
                                    # add bounded re-entry pressure only when both deadlock-relief
                                    # and reactivation signals already fired.
                                    deadlock_reentry_cap = min(
                                        0.0038,
                                        river_forced_bet_support_deadlock_relief_bonus
                                        + 0.50 * river_forced_bet_support_reactivation_bonus,
                                    )
                                    deadlock_reentry_penalty = min(
                                        deadlock_reentry_cap,
                                        0.05 * guard_risk,
                                    )
                                    if gap2 is not None:
                                        deadlock_reentry_penalty = min(
                                            deadlock_reentry_penalty,
                                            0.08 * float(gap2),
                                        )
                                    penalty += deadlock_reentry_penalty
                                if (
                                    guard_risk > 0.0
                                    and price >= (support_apron_trigger * threshold2_value)
                                    and price < (support_bridge_trigger * threshold2_value)
                                ):
                                    # Add a narrow pre-bridge apron to increase support hits
                                    # on recurrent forced-bet edge cases without touching low-price paths.
                                    apron_window = max(0.08, support_bridge_trigger - support_apron_trigger)
                                    apron_proximity = max(
                                        0.0,
                                        min(
                                            1.0,
                                            (price / threshold2_value - support_apron_trigger) / apron_window,
                                        ),
                                    )
                                    apron_cap = 0.0035
                                    if players_alive > 2:
                                        apron_cap += 0.0015
                                    if wet_score is not None and wet_score >= 1:
                                        apron_cap += 0.001
                                    if river_commitment_ratio is not None and river_commitment_ratio >= 0.20:
                                        apron_cap += 0.001
                                    if spr is not None and spr <= 1.8:
                                        apron_cap += 0.0005
                                    river_forced_bet_support_apron_penalty = apron_proximity * min(
                                        apron_cap,
                                        0.05 * guard_risk,
                                    )
                                    if gap2 is not None:
                                        river_forced_bet_support_apron_penalty = min(
                                            river_forced_bet_support_apron_penalty,
                                            0.08 * float(gap2),
                                        )
                                    penalty += river_forced_bet_support_apron_penalty
                                if (
                                    guard_risk > 0.0
                                    and price >= (support_bridge_trigger * threshold2_value)
                                    and price < (support_floor_trigger * threshold2_value)
                                ):
                                    # Bridge near-threshold support window so behavior changes
                                    # appear on more forced-bet edge cases without touching low-price paths.
                                    bridge_window = max(0.08, support_floor_trigger - support_bridge_trigger)
                                    bridge_proximity = max(
                                        0.0,
                                        min(
                                            1.0,
                                            (price / threshold2_value - support_bridge_trigger) / bridge_window,
                                        ),
                                    )
                                    bridge_cap = 0.005
                                    if players_alive > 2:
                                        bridge_cap += 0.002
                                    if wet_score is not None and wet_score >= 1:
                                        bridge_cap += 0.001
                                    if river_commitment_ratio is not None and river_commitment_ratio >= 0.24:
                                        bridge_cap += 0.001
                                    river_forced_bet_support_bridge_penalty = bridge_proximity * min(
                                        bridge_cap,
                                        0.07 * guard_risk,
                                    )
                                    if gap2 is not None:
                                        river_forced_bet_support_bridge_penalty = min(
                                            river_forced_bet_support_bridge_penalty,
                                            0.10 * float(gap2),
                                        )
                                    penalty += river_forced_bet_support_bridge_penalty
                                if (
                                    guard_risk > 0.0
                                    and price >= (support_floor_trigger * threshold2_value)
                                    and price < (guard_price_trigger * threshold2_value)
                                ):
                                    # Add bounded pre-trigger ramp to improve support on the
                                    # recurring forced-bet integrity branch without widening
                                    # into low-price regions.
                                    support_window = max(0.08, guard_price_trigger - support_floor_trigger)
                                    support_proximity = max(
                                        0.0,
                                        min(
                                            1.0,
                                            (price / threshold2_value - support_floor_trigger) / support_window,
                                        ),
                                    )
                                    support_cap = 0.007
                                    if players_alive > 2:
                                        support_cap += 0.002
                                    if wet_score is not None and wet_score >= 2:
                                        support_cap += 0.001
                                    if river_commitment_ratio is not None and river_commitment_ratio >= 0.24:
                                        support_cap += 0.001
                                    river_forced_bet_support_floor_penalty = support_proximity * min(
                                        support_cap,
                                        0.09 * guard_risk,
                                    )
                                    if gap2 is not None:
                                        river_forced_bet_support_floor_penalty = min(
                                            river_forced_bet_support_floor_penalty,
                                            0.12 * float(gap2),
                                        )
                                    penalty += river_forced_bet_support_floor_penalty
                                if (
                                    guard_risk > 0.0
                                    and players_alive > 2
                                    and wet_score is not None
                                    and wet_score >= 1
                                    and spr is not None
                                    and spr <= 2.0
                                    and price >= (support_bridge_trigger * threshold2_value)
                                ):
                                    # Recenter near-threshold forced-bet pressure on the exact
                                    # stagnating branch (RIVER + MW + wet + low SPR).
                                    recenter_floor = max(support_floor_trigger, guard_price_trigger - 0.04)
                                    recenter_ceiling = min(1.06, guard_price_trigger + 0.05)
                                    if price < (recenter_ceiling * threshold2_value):
                                        recenter_window = max(0.08, recenter_ceiling - recenter_floor)
                                        recenter_proximity = max(
                                            0.0,
                                            min(
                                                1.0,
                                                (price / threshold2_value - recenter_floor) / recenter_window,
                                            ),
                                        )
                                        recenter_risk = guard_risk
                                        if wet_score >= 2 and facing_high_price_defend_gap_wet_penalty:
                                            recenter_risk += 0.20 * float(facing_high_price_defend_gap_wet_penalty)
                                        if river_commitment_ratio is not None and river_commitment_ratio >= 0.26:
                                            recenter_risk += 0.15 * river_commitment_ratio
                                        recenter_cap = 0.010
                                        if wet_score >= 2:
                                            recenter_cap += 0.003
                                        if spr <= 1.7:
                                            recenter_cap += 0.002
                                        river_forced_bet_support_recenter_penalty = recenter_proximity * min(
                                            recenter_cap,
                                            0.11 * recenter_risk,
                                        )
                                        if gap2 is not None:
                                            river_forced_bet_support_recenter_penalty = min(
                                                river_forced_bet_support_recenter_penalty,
                                                0.16 * float(gap2),
                                            )
                                        penalty += river_forced_bet_support_recenter_penalty
                                if price >= (guard_price_trigger * threshold2_value):
                                    if guard_risk > 0.0:
                                        guard_window = 0.22 + max(0.0, 1.04 - guard_price_trigger)
                                        if guard_price_trigger <= 0.95:
                                            guard_window += 0.03
                                        if players_alive > 2:
                                            guard_window += 0.02
                                        if spr is not None and spr <= 1.6:
                                            guard_window += 0.02
                                        if wet_score is not None and wet_score >= 2:
                                            guard_window += 0.01
                                        guard_proximity = max(
                                            0.0,
                                            min(1.0, (price / threshold2_value - guard_price_trigger) / guard_window),
                                        )
                                        guard_cap = 0.026
                                        if wet_score is not None and wet_score >= 2:
                                            guard_cap += 0.006
                                        if players_alive > 2 and spr is not None and spr <= 1.9:
                                            guard_cap += 0.006
                                        commitment_proximity = 0.0
                                        if river_commitment_ratio is not None and river_commitment_ratio >= 0.24:
                                            commitment_proximity = max(
                                                0.0,
                                                min(1.0, (river_commitment_ratio - 0.24) / 0.40),
                                            )
                                            guard_cap += 0.004 * commitment_proximity
                                            river_forced_bet_commitment_penalty = commitment_proximity * min(
                                                0.012,
                                                0.18 * guard_risk,
                                            )
                                            if gap2 is not None:
                                                river_forced_bet_commitment_penalty = min(
                                                    river_forced_bet_commitment_penalty,
                                                    0.20 * float(gap2),
                                                )
                                            penalty += river_forced_bet_commitment_penalty
                                        if guard_price_trigger < 1.04 and price < (1.04 * threshold2_value):
                                            # Near-threshold clamp to broaden support on the
                                            # repeatedly stalled forced-bet integrity branch.
                                            near_trigger_cap = 0.015
                                            near_trigger_scale = 0.16 + 0.07 * commitment_proximity
                                            if players_alive > 2:
                                                near_trigger_cap += 0.003
                                                near_trigger_scale += 0.04
                                            if wet_score is not None and wet_score >= 2:
                                                near_trigger_scale += 0.03
                                            if (
                                                players_alive > 2
                                                and wet_score is not None
                                                and wet_score >= 1
                                                and spr is not None
                                                and spr <= 1.9
                                                and river_commitment_ratio is not None
                                                and river_commitment_ratio >= 0.28
                                            ):
                                                # Add bounded extra pressure only on the
                                                # historically stalled branch (MW + wet + low-SPR
                                                # + deep commitment), keeping the change localized.
                                                near_trigger_cap += 0.002
                                                near_trigger_scale += 0.025
                                            river_forced_bet_near_trigger_penalty = guard_proximity * min(
                                                near_trigger_cap,
                                                near_trigger_scale * guard_risk,
                                            )
                                            if gap2 is not None:
                                                river_forced_bet_near_trigger_penalty = min(
                                                    river_forced_bet_near_trigger_penalty,
                                                    0.18 * float(gap2),
                                                )
                                            penalty += river_forced_bet_near_trigger_penalty
                                        river_forced_bet_guard_penalty = guard_proximity * min(
                                            guard_cap,
                                            (0.38 + 0.09 * commitment_proximity) * guard_risk,
                                        )
                                        if gap2 is not None:
                                            river_forced_bet_guard_penalty = min(
                                                river_forced_bet_guard_penalty,
                                                0.40 * float(gap2),
                                            )
                                        penalty += river_forced_bet_guard_penalty
                                        if spr is not None and spr <= 1.5:
                                            # Extra bounded pressure at ultra-low SPR to
                                            # widen support on the recurrent forced-bet leak.
                                            ultra_low_spr_scale = max(0.0, min(1.0, (1.5 - spr) / 0.45))
                                            river_forced_bet_ultra_low_spr_penalty = (
                                                guard_proximity
                                                * ultra_low_spr_scale
                                                * min(0.011, (0.13 + 0.06 * commitment_proximity) * guard_risk)
                                            )
                                            if gap2 is not None:
                                                river_forced_bet_ultra_low_spr_penalty = min(
                                                    river_forced_bet_ultra_low_spr_penalty,
                                                    0.14 * float(gap2),
                                                )
                                            penalty += river_forced_bet_ultra_low_spr_penalty
                            if (
                                river_commitment_ratio is not None
                                and river_commitment_ratio >= 0.30
                                and (players_alive > 2 or pos_key in ("SB", "BB"))
                            ):
                                commitment_proximity = max(0.0, min(1.0, (river_commitment_ratio - 0.30) / 0.35))
                                commitment_cap = 0.025
                                if wet_score is not None and wet_score >= 2:
                                    commitment_cap += 0.01
                                river_commitment_clamp_penalty = commitment_proximity * min(
                                    commitment_cap,
                                    0.30 * river_risk,
                                )
                                if gap2 is not None:
                                    river_commitment_clamp_penalty = min(
                                        river_commitment_clamp_penalty,
                                        0.35 * float(gap2),
                                    )
                                penalty += river_commitment_clamp_penalty
            if trace_active and spr is not None:
                hp_threshold = threshold2_local if threshold2_local is not None else facing_high_price_threshold
                hp_hit = bool(hp_threshold is not None and spr <= 2.0 and price >= float(hp_threshold))
                defense_trace.update(
                    {
                        "high_price_low_spr_hit": hp_hit,
                        "high_price_low_spr_spr_x100": int(round(float(spr) * 100.0)),
                        "high_price_low_spr_price_ppm": _ppm_local(price, limit=1.0),
                        "high_price_low_spr_threshold_ppm": _ppm_local(float(hp_threshold), limit=1.0)
                        if hp_threshold is not None
                        else None,
                        "high_price_low_spr_penalty_ppm": _ppm_local(spr_low_price_penalty, limit=1.0)
                        if spr_low_price_penalty > 0.0
                        else None,
                        "high_price_turn_river_pressure_penalty_ppm": _ppm_local(
                            turn_river_pressure_penalty,
                            limit=1.0,
                        )
                        if turn_river_pressure_penalty > 0.0
                        else None,
                        "high_price_turn_river_support_bridge_penalty_ppm": _ppm_local(
                            turn_river_support_bridge_penalty,
                            limit=1.0,
                        )
                        if turn_river_support_bridge_penalty > 0.0
                        else None,
                        "high_price_turn_river_support_deadlock_penalty_ppm": _ppm_local(
                            turn_river_support_deadlock_penalty,
                            limit=1.0,
                        )
                        if turn_river_support_deadlock_penalty > 0.0
                        else None,
                        "high_price_turn_focus_support_ramp_penalty_ppm": _ppm_local(
                            turn_focus_support_ramp_penalty,
                            limit=1.0,
                        )
                        if turn_focus_support_ramp_penalty > 0.0
                        else None,
                        "high_price_turn_focus_support_reentry_penalty_ppm": _ppm_local(
                            turn_focus_support_reentry_penalty,
                            limit=1.0,
                        )
                        if turn_focus_support_reentry_penalty > 0.0
                        else None,
                        "high_price_turn_focus_support_hit_recenter_relief_ppm": _ppm_local(
                            turn_focus_support_hit_recenter_relief,
                            limit=1.0,
                        )
                        if turn_focus_support_hit_recenter_relief > 0.0
                        else None,
                        "high_price_turn_focus_deadlock_threshold_relief_ppm": _ppm_local(
                            turn_focus_deadlock_threshold_relief,
                            limit=1.0,
                        )
                        if turn_focus_deadlock_threshold_relief > 0.0
                        else None,
                        "high_price_wet_low_spr_firewall_penalty_ppm": _ppm_local(
                            wet_low_spr_firewall_penalty,
                            limit=1.0,
                        )
                        if wet_low_spr_firewall_penalty > 0.0
                        else None,
                        "high_price_wet_low_spr_firewall_recenter_penalty_ppm": _ppm_local(
                            wet_low_spr_firewall_recenter_penalty,
                            limit=1.0,
                        )
                        if wet_low_spr_firewall_recenter_penalty > 0.0
                        else None,
                        "high_price_wet_low_spr_firewall_extreme_penalty_ppm": _ppm_local(
                            wet_low_spr_firewall_extreme_penalty,
                            limit=1.0,
                        )
                        if wet_low_spr_firewall_extreme_penalty > 0.0
                        else None,
                        "high_price_wet_low_spr_firewall_cap_ppm": _ppm_local(
                            wet_low_spr_firewall_cap,
                            limit=1.0,
                        )
                        if wet_low_spr_firewall_cap > 0.0
                        else None,
                        "high_price_wet_low_spr_firewall_scale_ppm": _ppm_local(
                            wet_low_spr_firewall_scale,
                            limit=1.0,
                        )
                        if wet_low_spr_firewall_scale > 0.0
                        else None,
                        "high_price_river_threshold_recheck_penalty_ppm": _ppm_local(
                            river_threshold_recheck_penalty,
                            limit=1.0,
                        )
                        if river_threshold_recheck_penalty > 0.0
                        else None,
                        "high_price_river_threshold_tail_penalty_ppm": _ppm_local(
                            river_threshold_tail_penalty,
                            limit=1.0,
                        )
                        if river_threshold_tail_penalty > 0.0
                        else None,
                        "high_price_river_commitment_ratio_ppm": _ppm_local(
                            river_commitment_ratio,
                            limit=1.0,
                        )
                        if river_commitment_ratio is not None
                        else None,
                        "high_price_river_commitment_clamp_penalty_ppm": _ppm_local(
                            river_commitment_clamp_penalty,
                            limit=1.0,
                        )
                        if river_commitment_clamp_penalty > 0.0
                        else None,
                        "high_price_turn_commitment_ratio_ppm": _ppm_local(
                            turn_commitment_ratio,
                            limit=1.0,
                        )
                        if turn_commitment_ratio is not None
                        else None,
                        "high_price_turn_commitment_clamp_penalty_ppm": _ppm_local(
                            turn_commitment_clamp_penalty,
                            limit=1.0,
                        )
                        if turn_commitment_clamp_penalty > 0.0
                        else None,
                        "high_price_river_wet_mw_clamp_penalty_ppm": _ppm_local(
                            river_wet_mw_clamp_penalty,
                            limit=1.0,
                        )
                        if river_wet_mw_clamp_penalty > 0.0
                        else None,
                        "high_price_river_forced_bet_guard_penalty_ppm": _ppm_local(
                            river_forced_bet_guard_penalty,
                            limit=1.0,
                        )
                        if river_forced_bet_guard_penalty > 0.0
                        else None,
                        "high_price_river_forced_bet_guard_trigger_ppm": _ppm_local(
                            river_forced_bet_guard_trigger,
                            limit=1.0,
                        )
                        if river_forced_bet_guard_trigger is not None
                        else None,
                        "high_price_river_forced_bet_commitment_penalty_ppm": _ppm_local(
                            river_forced_bet_commitment_penalty,
                            limit=1.0,
                        )
                        if river_forced_bet_commitment_penalty > 0.0
                        else None,
                        "high_price_river_forced_bet_near_trigger_penalty_ppm": _ppm_local(
                            river_forced_bet_near_trigger_penalty,
                            limit=1.0,
                        )
                        if river_forced_bet_near_trigger_penalty > 0.0
                        else None,
                        "high_price_river_forced_bet_ultra_low_spr_penalty_ppm": _ppm_local(
                            river_forced_bet_ultra_low_spr_penalty,
                            limit=1.0,
                        )
                        if river_forced_bet_ultra_low_spr_penalty > 0.0
                        else None,
                        "high_price_river_forced_bet_support_floor_penalty_ppm": _ppm_local(
                            river_forced_bet_support_floor_penalty,
                            limit=1.0,
                        )
                        if river_forced_bet_support_floor_penalty > 0.0
                        else None,
                        "high_price_river_forced_bet_support_recenter_penalty_ppm": _ppm_local(
                            river_forced_bet_support_recenter_penalty,
                            limit=1.0,
                        )
                        if river_forced_bet_support_recenter_penalty > 0.0
                        else None,
                        "high_price_river_forced_bet_support_bridge_penalty_ppm": _ppm_local(
                            river_forced_bet_support_bridge_penalty,
                            limit=1.0,
                        )
                        if river_forced_bet_support_bridge_penalty > 0.0
                        else None,
                        "high_price_river_forced_bet_support_apron_penalty_ppm": _ppm_local(
                            river_forced_bet_support_apron_penalty,
                            limit=1.0,
                        )
                        if river_forced_bet_support_apron_penalty > 0.0
                        else None,
                        "high_price_river_forced_bet_support_window_expand_ppm": _ppm_local(
                            river_forced_bet_support_window_expand,
                            limit=1.0,
                        )
                        if river_forced_bet_support_window_expand > 0.0
                        else None,
                        "high_price_river_forced_bet_support_window_cap_ppm": _ppm_local(
                            river_forced_bet_support_window_cap,
                            limit=1.0,
                        )
                        if river_forced_bet_support_window_cap is not None
                        else None,
                        "high_price_river_forced_bet_support_taper_ppm": _ppm_local(
                            river_forced_bet_support_taper,
                            limit=1.0,
                        )
                        if river_forced_bet_support_taper > 0.0
                        else None,
                        "high_price_river_forced_bet_support_taper_relief_ppm": _ppm_local(
                            river_forced_bet_support_taper_relief,
                            limit=1.0,
                        )
                        if river_forced_bet_support_taper_relief > 0.0
                        else None,
                        "high_price_river_forced_bet_support_far_tail_damp_ppm": _ppm_local(
                            river_forced_bet_support_far_tail_damp,
                            limit=1.0,
                        )
                        if river_forced_bet_support_far_tail_damp > 0.0
                        else None,
                        "high_price_river_forced_bet_support_stall_bonus_ppm": _ppm_local(
                            river_forced_bet_support_stall_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_stall_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_entry_bonus_ppm": _ppm_local(
                            river_forced_bet_support_entry_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_entry_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_proximity_bonus_ppm": _ppm_local(
                            river_forced_bet_support_proximity_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_proximity_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_deep_stall_bonus_ppm": _ppm_local(
                            river_forced_bet_support_deep_stall_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_deep_stall_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_tail_bonus_ppm": _ppm_local(
                            river_forced_bet_support_tail_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_tail_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_closure_bonus_ppm": _ppm_local(
                            river_forced_bet_support_closure_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_closure_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_saturation_bonus_ppm": _ppm_local(
                            river_forced_bet_support_saturation_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_saturation_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_cap_relief_bonus_ppm": _ppm_local(
                            river_forced_bet_support_cap_relief_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_cap_relief_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_deadlock_relief_bonus_ppm": _ppm_local(
                            river_forced_bet_support_deadlock_relief_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_deadlock_relief_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_deadlock_relief_ramp_gate_ppm": _ppm_local(
                            river_forced_bet_support_deadlock_relief_ramp_gate,
                            limit=1.0,
                        )
                        if river_forced_bet_support_deadlock_relief_ramp_gate > 0.0
                        else None,
                        "high_price_river_forced_bet_support_ramp_bonus_ppm": _ppm_local(
                            river_forced_bet_support_ramp_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_ramp_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_support_reactivation_bonus_ppm": _ppm_local(
                            river_forced_bet_support_reactivation_bonus,
                            limit=1.0,
                        )
                        if river_forced_bet_support_reactivation_bonus > 0.0
                        else None,
                        "high_price_river_forced_bet_reactivation_floor_relief_ppm": _ppm_local(
                            river_forced_bet_support_reactivation_floor_relief,
                            limit=1.0,
                        )
                        if river_forced_bet_support_reactivation_floor_relief > 0.0
                        else None,
                    }
                )
            if penalty > 0.0:
                if gap1 is not None:
                    gap1 = max(0.0, float(gap1) - penalty)
                if gap2 is not None:
                    gap2 = max(0.0, float(gap2) - penalty)
            if gap1 is not None and price >= facing_high_price_threshold:
                if float(equity) + float(gap1) < price:
                    reduced = [a for a in actions_pool if str(a.get("kind")) not in ("RAISE", "BET", "ALLIN")]
                    if reduced:
                        actions_pool = reduced
            if (
                gap2 is not None
                and threshold2_local is not None
                and price >= threshold2_local
                and float(equity) + float(gap2) < price
            ):
                fold_only = [a for a in actions_pool if str(a.get("kind")) == "FOLD"]
                if fold_only:
                    actions_pool = fold_only
        score_pairs: list[tuple[float, float, dict[str, Any]]] = []
        actions_pool = _filter_postflop_actions_by_size(
            legal_actions=actions_pool,
            pot_chips=pot_chips,
            to_call=to_call,
            actor_commit=actor_commit,
            players_alive=players_alive,
            street=street,
            pos_key=pos_key,
            stack_chips=stack_chips,
            equity=equity,
            board_texture=board_texture,
        )
        unc = max(0.0, float(uncertainty or 0.0))
        if unc > 0.35:
            unc = 0.35
        equity_floor = None
        if facing_bet and to_call > 0 and street in ("FLOP", "TURN", "RIVER"):
            pot_after = pot_chips + to_call
            rake_floor = estimate_rake(
                pot_after=float(pot_after),
                street=street,
                rake_rate=rake_rate,
                rake_cap=rake_cap,
                no_flop_no_drop=no_flop_no_drop,
            )
            denom = max(1.0, float(pot_after) - float(rake_floor))
            equity_floor = max(0.0, min(0.95, float(to_call) / denom))
            if pos_key in ("SB", "BB") and stack_chips is not None and pot_chips > 0:
                spr = float(stack_chips) / float(pot_chips)
                oop_bump = 0.01 * max(0, players_alive - 2)
                oop_bump += 0.01 * max(0.0, min(6.0, spr - 2.0))
                if street == "TURN":
                    oop_bump += 0.005
                elif street == "RIVER":
                    oop_bump += 0.01
                oop_bump *= oop_facing_equity_bump_scale
                equity_floor = min(0.95, equity_floor + oop_bump)
        wet_score = _board_wet_score(board_texture=board_texture, street=street)
        base_rake = estimate_rake(
            pot_after=float(pot_chips),
            street=street,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )
        action_flags: dict[int, dict[str, float | bool]] = {}
        for act in actions_pool:
            defend_rate = defend_rate_fn(act) if defend_rate_fn is not None else None
            if isinstance(defend_rate, tuple):
                defend_rate = float(defend_rate[0]) if defend_rate else None
            if defend_rate is not None:
                defend_rate = max(0.0, min(1.0, float(defend_rate)))
            target = int(act.get("target_total_commit_chips", actor_commit))
            risk = max(0, target - actor_commit)
            kind = str(act.get("kind"))
            equity_used = equity
            equity_strength = equity
            realization = None
            if (
                call_realization is not None
                and facing_bet
                and to_call > 0
                and street == "PREFLOP"
                and kind == "CALL"
            ):
                equity_used = max(0.0, float(equity_used) * float(call_realization))
                if equity_strength is not None:
                    equity_strength = max(0.0, min(1.0, float(equity_strength) * float(call_realization)))
            if equity_floor is not None and kind == "CALL":
                equity_used = max(equity_used, equity_floor)
            if equity_used is not None and kind in ("RAISE", "BET", "ALLIN") and street in ("FLOP", "TURN", "RIVER"):
                pot_unit = float(max(1, pot_chips + to_call))
                exposure = float(risk) / pot_unit
                realization = 1.0
                if players_alive >= 3:
                    realization -= 0.04 * max(0, players_alive - 2)
                if pos_key in ("SB", "BB"):
                    realization -= 0.04
                if stack_chips is not None and pot_chips > 0:
                    spr = float(stack_chips) / float(pot_chips)
                    realization -= 0.02 * max(0.0, min(6.0, spr - 3.0))
                realization -= 0.05 * min(1.5, exposure)
                if facing_bet:
                    realization -= 0.02
                realization = max(0.65, min(1.0, realization))
                equity_used = max(0.0, float(equity_used) * realization)
                if equity_strength is not None:
                    equity_strength = max(0.0, min(1.0, float(equity_strength) * realization))
            ev = _action_ev(
                action=act,
                equity=equity_used,
                pot_chips=pot_chips,
                actor_commit=actor_commit,
                to_call=to_call,
                players_alive=players_alive,
                street=street,
                defend_rate=defend_rate,
            )
            if facing_bet and to_call > 0 and pos_key in ("SB", "BB"):
                if kind == "CALL" and solver_call_ev is not None:
                    ev = float(solver_call_ev)
                elif kind in ("RAISE", "BET", "ALLIN") and solver_raise_ev is not None:
                    if solver_hint_target is not None:
                        pot_unit_local = max(1.0, float(pot_chips + to_call))
                        dist = abs(float(target) - float(solver_hint_target))
                        closeness = 1.0 / (1.0 + (dist / pot_unit_local))
                        ev = float(ev) + (float(solver_raise_ev) - float(ev)) * closeness
                    else:
                        ev = float(solver_raise_ev)
            exp_rake = _expected_rake_for_action(
                action=act,
                pot_chips=pot_chips,
                actor_commit=actor_commit,
                to_call=to_call,
                players_alive=players_alive,
                street=street,
                defend_rate=defend_rate,
            )
            delta_rake = max(0.0, float(exp_rake) - float(base_rake))
            if kind in ("RAISE", "BET", "ALLIN") and equity_strength is not None and risk > 0 and street in ("FLOP", "TURN", "RIVER"):
                pot_base = float(pot_chips)
                bet_size = float(risk)
                rake_base = estimate_rake(
                    pot_after=float(pot_base + bet_size),
                    street=street,
                    rake_rate=rake_rate,
                    rake_cap=rake_cap,
                    no_flop_no_drop=no_flop_no_drop,
                )
                denom = max(1.0, float(pot_base + bet_size - rake_base))
                defend_freq = max(0.0, min(1.0, float(pot_base) / denom))
                opponents = max(1, players_alive - 1)
                exp_callers = defend_freq * opponents
                pot_after = pot_base + bet_size * (1.0 + exp_callers)
                rake_after = estimate_rake(
                    pot_after=float(pot_after),
                    street=street,
                    rake_rate=rake_rate,
                    rake_cap=rake_cap,
                    no_flop_no_drop=no_flop_no_drop,
                )
                pot_after_rake = max(1.0, pot_after - rake_after)
                value_floor = min(0.95, float(bet_size) / float(pot_after_rake) + 0.04 * exp_callers)
                value_ok = float(equity_strength) >= value_floor
                rake_fold = estimate_rake(
                    pot_after=float(pot_base),
                    street=street,
                    rake_rate=rake_rate,
                    rake_cap=rake_cap,
                    no_flop_no_drop=no_flop_no_drop,
                )
                fold_den = max(1.0, float(pot_base) - float(rake_fold) + float(bet_size))
                fold_needed = float(bet_size) / fold_den
                fold_all = (1.0 - defend_freq) ** opponents
                pressure_ok = fold_all >= fold_needed
                value_gap = max(0.0, float(equity_strength) - value_floor)
                pressure_gap = max(0.0, float(fold_all) - float(fold_needed))
                signal = max(value_gap, pressure_gap)
                action_flags[id(act)] = {
                    "value_ok": value_ok,
                    "pressure_ok": pressure_ok,
                    "signal": float(signal),
                }
                if oop_aggression_gate:
                    if not (value_ok or pressure_ok):
                        continue
            risk_scale = 0.6 if kind in ("CALL", "CHECK") else 1.0
            pot_unit = float(max(1, pot_chips + to_call))
            if kind in ("RAISE", "BET", "ALLIN") and delta_rake > 0.0:
                rake_pressure = 1.0 + min(0.6, (float(delta_rake) / pot_unit) * 6.0)
                risk_scale *= rake_pressure
            size_ratio = float(risk) / pot_unit
            size_ratio_penalty = 1.0 + (size_ratio * size_ratio)
            # ALLIN 风险软抑制：多人/OOP/高 SPR 下降权重，避免极端爆仓。
            if kind == "ALLIN":
                allin_penalty = 1.0
                if players_alive > 2:
                    allin_penalty *= 1.6
                if pos_key in ("SB", "BB"):
                    allin_penalty *= 1.3
                if stack_chips is not None and pot_chips > 0:
                    spr_val = float(stack_chips) / float(max(1.0, pot_chips))
                    if spr_val >= 6.0:
                        allin_penalty *= 1.5
                size_ratio_penalty *= allin_penalty
                risk_scale *= 1.0 + (allin_penalty - 1.0)
            mw_penalty = 0.0
            if mw_risk_weight > 0 and players_alive >= 3:
                mw_scale = mw_risk_weight * max(0, players_alive - 2)
                mw_penalty = float(risk) * mw_scale * size_ratio_penalty
            oop_penalty = 0.0
            if oop_risk_weight > 0 and pos_key in ("SB", "BB") and street in ("FLOP", "TURN", "RIVER"):
                spr = None
                if stack_chips is not None:
                    spr = float(stack_chips) / max(1.0, float(pot_chips))
                oop_scale = oop_risk_weight
                if players_alive == 2:
                    oop_scale *= 0.60
                if spr is not None and spr >= oop_spr_threshold:
                    oop_scale *= 1.5
                oop_penalty = float(risk) * oop_scale * size_ratio_penalty
            oop_realization_penalty = 0.0
            if oop_realization_weight > 0 and pos_key in ("SB", "BB") and equity_used is not None:
                if (
                    kind == "CHECK"
                    and not facing_bet
                    and to_call <= 0
                    and street in ("FLOP", "TURN")
                ):
                    spr = None
                    if stack_chips is not None and pot_chips > 0:
                        spr = float(stack_chips) / float(pot_chips)
                    if spr is None:
                        spr = 4.0
                    pressure = _pressure_index(
                        players_alive=players_alive,
                        spr=spr,
                        wet_score=wet_score,
                        pos_key=pos_key,
                        street=street,
                    )
                    eq_strength = max(0.0, min(1.0, float(equity_used)))
                    eq_factor = eq_strength * eq_strength
                    spr_factor = 0.60 + 0.12 * max(0.0, min(8.0, spr - 2.0))
                    wet_factor = 0.60 + 0.15 * float(wet_score)
                    mw_relief = 1.0 / (1.0 + 0.5 * max(0, players_alive - 2))
                    oop_realization_penalty = float(pot_unit) * oop_realization_weight
                    oop_realization_penalty *= (spr_factor + 0.40 * pressure + 0.30 * wet_factor)
                    oop_realization_penalty *= eq_factor * mw_relief
                elif kind == "CALL" and facing_bet and to_call > 0 and street == "PREFLOP":
                    spr = None
                    if stack_chips is not None and pot_chips > 0:
                        spr = float(stack_chips) / float(pot_chips)
                    if spr is None:
                        spr = 6.0
                    preflop_opponents = max(1, min(3, players_alive - 1))
                    mw_factor = 1.0 + 0.35 * max(0, preflop_opponents - 1)
                    rake_factor = 0.6 + 8.0 * rake_rate
                    eq_strength = max(0.0, min(1.0, float(equity_used)))
                    price = float(to_call) / max(1.0, float(pot_chips + to_call))
                    eq_gap = max(0.0, price - eq_strength)
                    gap_ratio = eq_gap / max(0.05, price)
                    gap_ratio = max(0.0, min(1.0, gap_ratio))
                    eq_factor = min(1.25, 0.40 + 0.90 * gap_ratio)
                    spr_factor = 0.40 + 0.08 * max(0.0, min(12.0, spr))
                    oop_realization_penalty = float(pot_unit) * oop_realization_weight
                    oop_realization_penalty *= spr_factor * rake_factor * mw_factor * eq_factor
                    pressure = (0.12 * max(0, preflop_opponents - 1)) + (0.04 * max(0.0, min(10.0, spr - 2.0))) + (4.0 * rake_rate)
                    base_realization = 1.0 / (1.0 + pressure)
                    eq_relief = 0.6 + 0.4 * eq_strength
                    preflop_realization = max(0.50, min(0.95, base_realization * eq_relief))
                    if equity_used is not None:
                        equity_used = max(0.0, float(equity_used) * preflop_realization)
                    if equity_strength is not None:
                        equity_strength = max(0.0, min(1.0, float(equity_strength) * preflop_realization))
            oop_call_penalty = 0.0
            if (
                oop_realization_weight > 0
                and kind == "CALL"
                and facing_bet
                and to_call > 0
                and pos_key in ("SB", "BB")
                and street in ("FLOP", "TURN", "RIVER")
                and equity_used is not None
            ):
                spr = None
                if stack_chips is not None and pot_chips > 0:
                    spr = float(stack_chips) / float(pot_chips)
                if spr is None:
                    spr = 4.0
                pot_after = float(pot_chips + to_call)
                price = float(to_call) / max(1.0, pot_after)
                eq_strength = max(0.0, min(1.0, float(equity_used)))
                equity_gap = max(0.0, price - eq_strength)
                opp_factor = 1.0 + 0.25 * max(0, players_alive - 2)
                spr_factor = 0.60 + 0.10 * max(0.0, min(8.0, spr - 2.0))
                wet_factor = 0.60 + 0.10 * float(wet_score)
                oop_call_penalty = float(pot_unit) * oop_realization_weight
                oop_call_penalty *= equity_gap * opp_factor * spr_factor * wet_factor
            oop_ms_penalty = 0.0
            if (
                oop_realization_weight > 0
                and facing_bet
                and to_call > 0
                and pos_key in ("SB", "BB")
                and street in ("FLOP", "TURN")
                and equity_used is not None
            ):
                spr = None
                if stack_chips is not None and pot_chips > 0:
                    spr = float(stack_chips) / float(pot_chips)
                if spr is None:
                    spr = 5.0
                eq_strength = max(0.0, min(1.0, float(equity_used)))
                eq_factor = (1.0 - eq_strength)
                pressure = _pressure_index(
                    players_alive=players_alive,
                    spr=spr,
                    wet_score=wet_score,
                    pos_key=pos_key,
                    street=street,
                )
                pressure = max(0.0, min(1.0, 1.0 - pressure))
                spr_factor = 0.70 + 0.10 * max(0.0, min(8.0, spr - 2.0))
                wet_factor = 0.70 + 0.15 * float(wet_score)
                risk_unit = float(risk if kind in ("RAISE", "BET", "ALLIN") else to_call)
                oop_ms_penalty = risk_unit * oop_realization_weight
                oop_ms_penalty *= (1.0 + 0.40 * pressure + 0.25 * wet_factor) * spr_factor * max(0.0, eq_factor)
            rake_penalty = float(delta_rake) * (rake_delta_weight + 0.25 * unc)
            signal = 0.0
            if kind in ("RAISE", "BET", "ALLIN"):
                flags = action_flags.get(id(act))
                if flags is not None:
                    signal = max(0.0, min(0.45, float(flags.get("signal", 0.0))))
                    if signal > 0.0:
                        relief = max(0.55, 1.0 - 1.5 * signal)
                        mw_penalty *= relief
                        oop_penalty *= relief
                        rake_penalty *= relief
                        risk_scale *= relief
                        oop_ms_penalty *= relief
            if kind == "BET" and not facing_bet and equity_used is not None and street in ("FLOP", "TURN", "RIVER"):
                eq_strength = max(0.0, min(1.0, float(equity_used)))
                if eq_strength > 0.55:
                    relief = 1.0 - 0.7 * min(1.0, (eq_strength - 0.55) / 0.45)
                    relief = max(0.5, relief)
                    mw_penalty *= relief
                    oop_penalty *= relief
            retaliation_penalty = 0.0
            retaliation_mix: tuple[float, float, float, float, float | None, float | None] | None = None
            if (
                retaliation_index is not None
                and retaliation_weight > 0
                and kind in ("BET", "RAISE", "ALLIN")
                and not facing_bet
                and to_call <= 0
                and street in ("FLOP", "TURN", "RIVER")
            ):
                pot_base = int(max(1, pot_chips))
                if risk > 0 and pot_base > 0:
                    size_ratio_ppm = int((int(risk) * 1_000_000) / pot_base)
                    spr_val = float(stack_chips) / float(pot_base) if stack_chips is not None else 99.0
                    key = retaliation_bucket_key(
                        street=str(street),
                        players_alive=int(players_alive),
                        pos_key=pos_key,
                        spr=spr_val,
                        size_ratio_ppm=size_ratio_ppm,
                        bucket_spec=retaliation_bucket_spec,
                    )
                    stats = retaliation_index.get(key) if retaliation_index is not None else None
                    bet_count = float(stats.get("bet_count", 0.0) or 0.0) if isinstance(stats, dict) else 0.0
                    raise_count = float(stats.get("raise_count", 0.0) or 0.0) if isinstance(stats, dict) else 0.0
                    call_count = float(stats.get("call_count", 0.0) or 0.0) if isinstance(stats, dict) else 0.0
                    raise_profit_sum = float(stats.get("raise_profit_sum", 0.0) or 0.0) if isinstance(stats, dict) else 0.0
                    call_profit_sum = float(stats.get("call_profit_sum", 0.0) or 0.0) if isinstance(stats, dict) else 0.0
                    g_bet = g_raise = g_call = g_raise_sum = g_call_sum = 0.0
                    if bet_count <= 0 and retaliation_model is not None:
                        global_counts = retaliation_model.get("global") if isinstance(retaliation_model, dict) else None
                        if isinstance(global_counts, dict):
                            g_bet = float(global_counts.get("bet_count", 0.0) or 0.0)
                            g_raise = float(global_counts.get("raise_count", 0.0) or 0.0)
                            g_call = float(global_counts.get("call_count", 0.0) or 0.0)
                            g_raise_sum = float(global_counts.get("raise_profit_sum", 0.0) or 0.0)
                            g_call_sum = float(global_counts.get("call_profit_sum", 0.0) or 0.0)
                            bet_count = g_bet
                            raise_count = g_raise
                            call_count = g_call
                            raise_profit_sum = g_raise_sum
                            call_profit_sum = g_call_sum
                    elif retaliation_model is not None:
                        global_counts = retaliation_model.get("global") if isinstance(retaliation_model, dict) else None
                        if isinstance(global_counts, dict):
                            g_bet = float(global_counts.get("bet_count", 0.0) or 0.0)
                            g_raise = float(global_counts.get("raise_count", 0.0) or 0.0)
                            g_call = float(global_counts.get("call_count", 0.0) or 0.0)
                            g_raise_sum = float(global_counts.get("raise_profit_sum", 0.0) or 0.0)
                            g_call_sum = float(global_counts.get("call_profit_sum", 0.0) or 0.0)
                    prior = max(0.0, float(retaliation_prior))
                    if bet_count > 0:
                        fold_count = max(0, bet_count - raise_count - call_count)
                        denom = bet_count + (3.0 * prior)
                        p_raise = (raise_count + prior) / max(1e-6, denom)
                        p_call = (call_count + prior) / max(1e-6, denom)
                        p_fold = (fold_count + prior) / max(1e-6, denom)
                        p_sum = max(1e-6, p_raise + p_call + p_fold)
                        p_raise /= p_sum
                        p_call /= p_sum
                        p_fold /= p_sum
                        conf = bet_count / max(1.0, bet_count + (6.0 * prior))
                        if g_bet > 0:
                            fold_g = max(0.0, g_bet - g_raise - g_call)
                            denom_g = g_bet + (3.0 * prior)
                            p_raise_g = (g_raise + prior) / max(1e-6, denom_g)
                            p_call_g = (g_call + prior) / max(1e-6, denom_g)
                            p_fold_g = (fold_g + prior) / max(1e-6, denom_g)
                            p_sum_g = max(1e-6, p_raise_g + p_call_g + p_fold_g)
                            p_raise_g /= p_sum_g
                            p_call_g /= p_sum_g
                            p_fold_g /= p_sum_g
                            mix = max(0.0, min(1.0, float(conf)))
                            p_raise = (mix * p_raise) + ((1.0 - mix) * p_raise_g)
                            p_call = (mix * p_call) + ((1.0 - mix) * p_call_g)
                            p_fold = (mix * p_fold) + ((1.0 - mix) * p_fold_g)
                            p_sum = max(1e-6, p_raise + p_call + p_fold)
                            p_raise /= p_sum
                            p_call /= p_sum
                            p_fold /= p_sum
                            raise_profit_sum = (mix * raise_profit_sum) + ((1.0 - mix) * g_raise_sum)
                            call_profit_sum = (mix * call_profit_sum) + ((1.0 - mix) * g_call_sum)
                            raise_count = (mix * raise_count) + ((1.0 - mix) * g_raise)
                            call_count = (mix * call_count) + ((1.0 - mix) * g_call)
                        raise_avg = (raise_profit_sum / raise_count) if raise_count > 0 else None
                        call_avg = (call_profit_sum / call_count) if call_count > 0 else None
                        retaliation_mix = (p_raise, p_call, p_fold, conf, raise_avg, call_avg)
                    else:
                        p_raise = float(retaliation_global_raise_prob or 0.0)
                        retaliation_penalty = float(risk) * float(retaliation_weight) * max(0.0, min(1.0, p_raise))
            if retaliation_mix is not None and equity_used is not None:
                p_raise, p_call, p_fold, conf, raise_avg, call_avg = retaliation_mix
                ev_call = _action_ev(
                    action=act,
                    equity=equity_used,
                    pot_chips=pot_chips,
                    actor_commit=actor_commit,
                    to_call=to_call,
                    players_alive=players_alive,
                    street=street,
                    defend_rate=1.0,
                )
                if call_avg is not None:
                    ev_call = (0.6 * ev_call) + (0.4 * float(call_avg))
                ev_fold = _action_ev(
                    action=act,
                    equity=equity_used,
                    pot_chips=pot_chips,
                    actor_commit=actor_commit,
                    to_call=to_call,
                    players_alive=players_alive,
                    street=street,
                    defend_rate=0.0,
                )
                pot_unit_local = float(max(1, pot_chips + to_call))
                size_ratio_local = float(risk) / pot_unit_local
                raise_ev = ev_call - max(1.0, float(risk)) * (0.65 + 0.25 * min(1.5, size_ratio_local * 1.2))
                if raise_avg is not None:
                    raise_ev = (0.6 * raise_ev) + (0.4 * float(raise_avg))
                resp_ev = (p_fold * ev_fold) + (p_call * ev_call) + (p_raise * raise_ev)
                mix_w = min(0.75, float(retaliation_weight) * (0.5 + 1.5 * max(0.0, min(1.0, conf))))
                # Gate retaliation influence by leverage (SPR + bet size) to avoid over-penalizing small bets.
                spr_val = None
                if stack_chips is not None and pot_chips > 0:
                    spr_val = float(stack_chips) / float(pot_chips)
                spr_signal = 0.0
                if spr_val is not None:
                    spr_signal = 1.0 / (1.0 + math.exp(-1.2 * (float(spr_val) - 3.0)))
                size_signal = 1.0 / (1.0 + math.exp(-6.0 * (float(size_ratio_local) - 0.40)))
                ret_gate = (0.25 + 0.75 * spr_signal) * (0.25 + 0.75 * size_signal)
                mix_w *= ret_gate
                ev = (1.0 - mix_w) * float(ev) + mix_w * float(resp_ev)
                retaliation_penalty = 0.0
            score = (
                ev
                - (unc * ((float(risk) * risk_scale) + float(delta_rake)))
                - rake_penalty
                - mw_penalty
                - oop_penalty
                - oop_realization_penalty
                - oop_call_penalty
                - oop_ms_penalty
            )
            if retaliation_penalty > 0.0:
                score -= retaliation_penalty
            if facing_bet and kind in ("RAISE", "BET", "ALLIN"):
                raise_toll = float(delta_rake) * (0.4 + 0.2 * max(0, players_alive - 2))
                raise_toll += float(risk) * 0.02
                if signal > 0.0:
                    raise_toll *= max(0.5, 1.0 - 1.2 * signal)
                score -= raise_toll
            if (
                facing_bet
                and to_call > 0
                and street in ("TURN", "RIVER")
                and facing_high_price_threshold is not None
            ):
                pot_unit_local = float(max(1, pot_chips + to_call))
                price = float(to_call) / pot_unit_local
                penalty = None
                if kind in ("RAISE", "BET", "ALLIN") and facing_high_price_raise_penalty is not None:
                    if (
                        facing_high_price_raise_penalty2 is not None
                        and facing_high_price_threshold2 is not None
                        and price >= facing_high_price_threshold2
                    ):
                        penalty = facing_high_price_raise_penalty2
                    elif price >= facing_high_price_threshold:
                        penalty = facing_high_price_raise_penalty
                elif kind == "CALL" and facing_high_price_call_penalty is not None:
                    if (
                        facing_high_price_call_penalty2 is not None
                        and facing_high_price_threshold2 is not None
                        and price >= facing_high_price_threshold2
                    ):
                        penalty = facing_high_price_call_penalty2
                    elif price >= facing_high_price_threshold:
                        penalty = facing_high_price_call_penalty
                if penalty:
                    score -= pot_unit_local * float(penalty)
            if aggressive_high_price_threshold is not None and kind in ("RAISE", "BET", "ALLIN"):
                pot_unit_local = float(max(1, pot_chips + to_call))
                price = float(risk) / pot_unit_local
                penalty = None
                if (
                    aggressive_high_price_penalty2 is not None
                    and aggressive_high_price_threshold2 is not None
                    and price >= aggressive_high_price_threshold2
                ):
                    penalty = aggressive_high_price_penalty2
                elif aggressive_high_price_penalty is not None and price >= aggressive_high_price_threshold:
                    penalty = aggressive_high_price_penalty
                if penalty:
                    score -= pot_unit_local * float(penalty)
            if prior_weights is not None:
                prior_prob = max(0.0, min(1.0, float(prior_weights.get(kind, 0)) / 10000.0))
                prior_reg = max(0.0, 0.12 - safe_exploit_max)
                score -= float(pot_unit) * prior_reg * (1.0 - prior_prob)
            if adaptive_enabled and adaptive_alpha > 0.0:
                adaptive_shift = 0.0
                if adaptive_expert == "pressure":
                    if kind in ("RAISE", "BET", "ALLIN"):
                        adaptive_shift = float(pot_unit) * adaptive_alpha * (0.10 if to_call <= 0 else 0.06)
                    elif kind == "FOLD":
                        adaptive_shift = -float(pot_unit) * adaptive_alpha * 0.03
                    elif kind == "CHECK":
                        adaptive_shift = -float(pot_unit) * adaptive_alpha * 0.01
                elif adaptive_expert == "tight_defense":
                    if kind in ("RAISE", "BET", "ALLIN"):
                        adaptive_shift = -float(pot_unit) * adaptive_alpha * (0.08 if to_call <= 0 else 0.05)
                    elif kind in ("CALL", "CHECK"):
                        adaptive_shift = float(pot_unit) * adaptive_alpha * 0.02
                    elif kind == "FOLD" and to_call > 0:
                        adaptive_shift = float(pot_unit) * adaptive_alpha * 0.01
                if adaptive_shift != 0.0:
                    score += adaptive_shift
            score_pairs.append((score, ev, act))

        # Require meaningful EV edge before choosing aggressive lines.
        if score_pairs:
            pot_unit = max(1, pot_chips + to_call)
            risk_term = float(to_call) * (0.15 if facing_bet else 0.0)
            rake_term = float(pot_unit) * (0.5 * rake_rate)
            opp_term = float(pot_unit) * (0.01 * max(0, players_alive - 2))
            margin = max(1.0, float(pot_unit) * 0.015 + risk_term + rake_term + opp_term)
            if facing_bet and to_call > 0:
                call_score = None
                call_ev = None
                for score, ev, act in score_pairs:
                    if str(act.get("kind")) == "CALL":
                        call_score = score if call_score is None else max(call_score, score)
                        call_ev = ev if call_ev is None else max(call_ev, ev)
                if call_score is not None:
                    filtered: list[tuple[float, float, dict[str, Any]]] = []
                    for score, ev, act in score_pairs:
                        kind = str(act.get("kind"))
                        if kind in ("RAISE", "BET", "ALLIN"):
                            if call_ev is not None:
                                edge = ev - call_ev
                                if score < call_score and edge <= 0:
                                    flags = action_flags.get(id(act))
                                    value_ok = bool(flags.get("value_ok")) if flags is not None else False
                                    pressure_ok = bool(flags.get("pressure_ok")) if flags is not None else False
                                    if not (value_ok or pressure_ok):
                                        continue
                            target = int(act.get("target_total_commit_chips", actor_commit))
                            risk = max(0, target - actor_commit)
                            extra_risk = max(0, risk - int(to_call))
                            pot_unit = max(1, pot_chips + to_call)
                            size_ratio = float(extra_risk) / float(pot_unit)
                            exp_rake = _expected_rake_for_action(
                                action=act,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                street=street,
                                defend_rate=None,
                            )
                            delta_rake = max(0.0, float(exp_rake) - float(base_rake))
                            mw_factor = 1.0 + 0.6 * max(0, players_alive - 2)
                            oop_factor = 1.0
                            if pos_key in ("SB", "BB") and stack_chips is not None and pot_chips > 0:
                                spr = float(stack_chips) / float(pot_chips)
                                oop_factor += min(0.8, 0.15 * max(0.0, spr - 2.0))
                            rake_cost = float(delta_rake) * (0.9 + 0.4 * size_ratio)
                            risk_cost = float(extra_risk) * (0.02 + 0.4 * rake_rate) * mw_factor * oop_factor
                            required_margin = max(margin, rake_cost + risk_cost)
                            required_margin *= 1.0 + 0.6 * unc
                            flags = action_flags.get(id(act))
                            value_ok = bool(flags.get("value_ok")) if flags is not None else False
                            pressure_ok = bool(flags.get("pressure_ok")) if flags is not None else False
                            signal = float(flags.get("signal", 0.0)) if flags is not None else 0.0
                            if street == "RIVER" and players_alive != 2 and not value_ok:
                                continue
                            if signal > 0.0:
                                required_margin *= max(0.4, 1.0 - 0.9 * min(0.45, signal))
                            if equity is not None:
                                eq_strength = float(equity)
                                if eq_strength > 0.5:
                                    relief = 1.0 - 0.6 * min(1.0, (eq_strength - 0.5) / 0.5)
                                    required_margin *= max(0.4, relief)
                            ref_ev = call_ev if call_ev is not None else 0.0
                            if value_ok or pressure_ok:
                                floor_ev = ref_ev - max(
                                    margin,
                                    float(pot_unit) * (0.02 + 0.4 * unc) + float(delta_rake) * 0.5,
                                )
                                if ev < floor_ev and ev < 0:
                                    continue
                            elif ev < (ref_ev + required_margin):
                                continue
                        filtered.append((score, ev, act))
                    score_pairs = filtered
            else:
                check_ev = None
                bet_ev = None
                for _score, ev, act in score_pairs:
                    kind = str(act.get("kind"))
                    if kind == "CHECK":
                        check_ev = ev if check_ev is None else max(check_ev, ev)
                    if kind in ("BET", "RAISE", "ALLIN"):
                        bet_ev = ev if bet_ev is None else max(bet_ev, ev)
                if check_ev is not None and bet_ev is not None and bet_ev < (check_ev + margin):
                    retained: list[tuple[float, float, dict[str, Any]]] = []
                    for row in score_pairs:
                        kind = str(row[2].get("kind"))
                        if kind not in ("BET", "RAISE", "ALLIN"):
                            retained.append(row)
                            continue
                        flags = action_flags.get(id(row[2]))
                        if flags is not None and (flags.get("value_ok") or flags.get("pressure_ok")):
                            retained.append(row)
                    if retained:
                        score_pairs = retained
                    else:
                        score_pairs = [
                            (s, ev, act)
                            for (s, ev, act) in score_pairs
                            if str(act.get("kind")) not in ("BET", "RAISE", "ALLIN")
                        ]
            if score_pairs and street == "RIVER" and not facing_bet:
                river_filtered: list[tuple[float, float, dict[str, Any]]] = []
                pot_unit = float(max(1, pot_chips + to_call))
                for score, ev, act in score_pairs:
                    kind = str(act.get("kind"))
                    if kind in ("RAISE", "BET", "ALLIN"):
                        flags = action_flags.get(id(act))
                        value_ok = bool(flags.get("value_ok")) if flags is not None else False
                        pressure_ok = bool(flags.get("pressure_ok")) if flags is not None else False
                        signal = float(flags.get("signal", 0.0)) if flags is not None else 0.0
                        if value_ok:
                            river_filtered.append((score, ev, act))
                            continue
                        target = int(act.get("target_total_commit_chips", actor_commit))
                        risk = max(0, target - actor_commit)
                        size_ratio = float(risk) / pot_unit if pot_unit > 0 else 0.0
                        if size_ratio <= 0.33 and (pressure_ok or signal >= 0.02):
                            river_filtered.append((score, ev, act))
                        continue
                    river_filtered.append((score, ev, act))
                if river_filtered:
                    score_pairs = river_filtered
        def _select_from(score_rows: list[tuple[float, float, dict[str, Any]]]) -> dict[str, Any] | None:
            nonlocal defend_target, turn_focus_support_raise_clamp_strength
            if not score_rows:
                return None
            def _ppm(value: float | None, *, limit: float) -> int | None:
                if value is None:
                    return None
                try:
                    v = float(value)
                except Exception:
                    return None
                if not math.isfinite(v):
                    return None
                v = max(-limit, min(limit, v))
                return int(round(v * 1_000_000))

            def _chips(value: float | None) -> int | None:
                if value is None:
                    return None
                try:
                    v = float(value)
                except Exception:
                    return None
                if not math.isfinite(v):
                    return None
                return int(round(v))

            pot_unit = max(1, pot_chips + to_call)
            # EV-first selection when the top EV is meaningfully above alternatives.
            if len(score_rows) > 1:
                ev_sorted = sorted(score_rows, key=lambda x: x[1], reverse=True)
                ev_best = ev_sorted[0][1]
                ev_second = ev_sorted[1][1]
                ev_margin = max(1.0, float(pot_unit) * (0.02 + 0.5 * unc))
                if (ev_best - ev_second) >= ev_margin:
                    best_ev_candidates = [row for row in score_rows if row[1] >= (ev_best - 1e-6)]
                    best_ev_candidates.sort(key=lambda x: x[0], reverse=True)
                    return best_ev_candidates[0][2]
            best = max(score_rows, key=lambda x: x[0])[0]
            if ev_slack is None:
                slack = max(1.0, float(pot_unit) * (0.02 + 0.6 * unc))
            else:
                slack = max(0.0, float(ev_slack))
            if facing_bet and defend_target is not None:
                target = max(0.0, min(1.0, float(defend_target)))
                slack = max(slack, float(pot_unit) * (0.04 + 0.25 * target))
            if slack <= 0.0:
                candidates = [act for score, _, act in score_rows if score == best]
            else:
                candidates = [act for score, _, act in score_rows if score >= (best - slack)]
            if facing_bet and defend_target is not None:
                # Ensure both fold and defend actions are available for mixing.
                fold_best: dict[str, Any] | None = None
                fold_score = None
                defend_best: dict[str, Any] | None = None
                defend_score = None
                for score, _ev, act in score_rows:
                    kind = str(act.get("kind"))
                    if kind == "FOLD":
                        if fold_score is None or score > fold_score:
                            fold_score = score
                            fold_best = act
                    else:
                        if defend_score is None or score > defend_score:
                            defend_score = score
                            defend_best = act
                existing_ids = {id(a) for a in candidates}
                if fold_best is not None and id(fold_best) not in existing_ids:
                    candidates.append(fold_best)
                    existing_ids.add(id(fold_best))
                if defend_best is not None and id(defend_best) not in existing_ids:
                    candidates.append(defend_best)
            chosen_local: dict[str, Any] | None = None
            if len(candidates) == 1:
                chosen_local = candidates[0]
            if chosen_local is None and facing_bet and defend_target is not None and len(candidates) < 2 and score_rows:
                # ensure at least two candidates for defensive mixing
                ordered = sorted(score_rows, key=lambda x: x[0], reverse=True)
                existing_ids = {id(a) for a in candidates}
                first_kind = str(candidates[0].get("kind")) if candidates else None
                added = False
                for _score, _ev, act in ordered:
                    if id(act) in existing_ids:
                        continue
                    kind = str(act.get("kind"))
                    if first_kind and kind == first_kind:
                        continue
                    candidates.append(act)
                    added = True
                    break
                if not added:
                    for _score, _ev, act in ordered:
                        if id(act) in existing_ids:
                            continue
                        candidates.append(act)
                        break
            if chosen_local is None and facing_bet and defend_target is not None and len(candidates) > 1:
                min_score = min(score for score, _, act in score_rows if act in candidates)
                target_def = max(0.0, min(1.0, float(defend_target)))
                call_ev_best = None
                call_act_best: dict[str, Any] | None = None
                solver_ev_ready = bool(solver_call_ev is not None or solver_raise_ev is not None)
                use_solver_ev = bool(facing_bet and pos_key in ("SB", "BB") and solver_ev_ready)
                solver_ev_conf = 0.0
                if solver_call_ev is not None and solver_raise_ev is not None:
                    solver_ev_conf = 1.0
                elif solver_ev_ready:
                    solver_ev_conf = 0.6
                pot_unit = max(1, pot_chips + to_call)
                if use_solver_ev:
                    call_fallback = None
                    for _score, _ev, act in score_rows:
                        if str(act.get("kind")) == "CALL":
                            call_fallback = act
                            break
                    if call_fallback is not None and call_fallback not in candidates:
                        candidates.append(call_fallback)
                for _score, _ev, act in score_rows:
                    if act not in candidates:
                        continue
                    if str(act.get("kind")) == "CALL":
                        ev_call = _ev
                        if use_solver_ev and solver_call_ev is not None:
                            ev_call = float(solver_call_ev)
                        if call_ev_best is None or ev_call > call_ev_best:
                            call_ev_best = ev_call
                            call_act_best = act

                def _solver_ev_for_action(act: dict[str, Any], local_ev: float) -> float:
                    if not use_solver_ev:
                        return local_ev
                    kind = str(act.get("kind"))
                    if kind == "CALL" and solver_call_ev is not None:
                        return float(solver_call_ev)
                    if kind in ("RAISE", "BET", "ALLIN") and solver_raise_ev is not None:
                        if solver_hint_target is not None:
                            target = int(act.get("target_total_commit_chips", actor_commit))
                            dist = abs(float(target) - float(solver_hint_target))
                            closeness = 1.0 / (1.0 + (dist / max(1.0, float(pot_unit))))
                            return float(local_ev) + (float(solver_raise_ev) - float(local_ev)) * closeness
                        else:
                            return float(solver_raise_ev)
                    return local_ev

                def _oop_multi_street_cost(risk_unit: float, equity_used: float | None) -> float:
                    if (
                        oop_realization_weight <= 0
                        or not facing_bet
                        or to_call <= 0
                        or pos_key not in ("SB", "BB")
                        or street not in ("FLOP", "TURN")
                        or equity_used is None
                    ):
                        return 0.0
                    spr = None
                    if stack_chips is not None and pot_chips > 0:
                        spr = float(stack_chips) / float(pot_chips)
                    if spr is None:
                        spr = 5.0
                    eq_strength = max(0.0, min(1.0, float(equity_used)))
                    eq_factor = max(0.25, 1.0 - eq_strength)
                    pressure = _pressure_index(
                        players_alive=players_alive,
                        spr=spr,
                        wet_score=wet_score,
                        pos_key=pos_key,
                        street=street,
                    )
                    pressure = max(0.0, min(1.0, 1.0 - pressure))
                    spr_factor = 0.70 + 0.10 * max(0.0, min(8.0, spr - 2.0))
                    wet_factor = 0.70 + 0.15 * float(wet_score)
                    risk_base = float(risk_unit)
                    if pot_chips and pot_chips > 0:
                        risk_base = max(risk_base, 0.35 * float(pot_chips))
                    cost = float(risk_base) * oop_realization_weight
                    cost *= (1.0 + 0.55 * pressure + 0.25 * wet_factor) * spr_factor * eq_factor
                    if street in ("TURN", "RIVER") and pot_chips and pot_chips > 0:
                        price = float(to_call) / max(1.0, float(pot_chips + to_call))
                        cost *= 1.0 + 0.60 * max(0.0, min(1.0, price))
                    if solver_ev_conf > 0:
                        cost *= max(0.40, 1.0 - 0.50 * solver_ev_conf)
                    return cost

                def _retaliation_raise_prob_for_action(act: dict[str, Any]) -> tuple[float | None, float | None]:
                    if retaliation_index is None or retaliation_weight <= 0:
                        return None, None
                    target = int(act.get("target_total_commit_chips", actor_commit))
                    risk = max(0, target - actor_commit)
                    if risk <= 0:
                        return None, None
                    pot_base = int(max(1, pot_chips + to_call))
                    size_ratio_ppm = int((int(risk) * 1_000_000) / pot_base)
                    spr_val = float(stack_chips) / float(pot_base) if stack_chips is not None else 99.0
                    key = retaliation_bucket_key(
                        street=str(street),
                        players_alive=int(players_alive),
                        pos_key=pos_key,
                        spr=spr_val,
                        size_ratio_ppm=size_ratio_ppm,
                        bucket_spec=retaliation_bucket_spec,
                    )
                    stats = retaliation_index.get(key) if retaliation_index is not None else None
                    bet_count = float(stats.get("bet_count", 0.0) or 0.0) if isinstance(stats, dict) else 0.0
                    raise_count = float(stats.get("raise_count", 0.0) or 0.0) if isinstance(stats, dict) else 0.0
                    call_count = float(stats.get("call_count", 0.0) or 0.0) if isinstance(stats, dict) else 0.0
                    g_bet = g_raise = g_call = 0.0
                    if bet_count <= 0 and retaliation_model is not None:
                        global_counts = retaliation_model.get("global") if isinstance(retaliation_model, dict) else None
                        if isinstance(global_counts, dict):
                            g_bet = float(global_counts.get("bet_count", 0.0) or 0.0)
                            g_raise = float(global_counts.get("raise_count", 0.0) or 0.0)
                            g_call = float(global_counts.get("call_count", 0.0) or 0.0)
                            bet_count = g_bet
                            raise_count = g_raise
                            call_count = g_call
                    elif retaliation_model is not None:
                        global_counts = retaliation_model.get("global") if isinstance(retaliation_model, dict) else None
                        if isinstance(global_counts, dict):
                            g_bet = float(global_counts.get("bet_count", 0.0) or 0.0)
                            g_raise = float(global_counts.get("raise_count", 0.0) or 0.0)
                            g_call = float(global_counts.get("call_count", 0.0) or 0.0)
                    prior = max(0.0, float(retaliation_prior))
                    if bet_count > 0:
                        fold_count = max(0, bet_count - raise_count - call_count)
                        denom = bet_count + (3.0 * prior)
                        p_raise = (raise_count + prior) / max(1e-6, denom)
                        p_call = (call_count + prior) / max(1e-6, denom)
                        p_fold = (fold_count + prior) / max(1e-6, denom)
                        p_sum = max(1e-6, p_raise + p_call + p_fold)
                        p_raise /= p_sum
                        conf = bet_count / max(1.0, bet_count + (6.0 * prior))
                        if g_bet > 0:
                            fold_g = max(0.0, g_bet - g_raise - g_call)
                            denom_g = g_bet + (3.0 * prior)
                            p_raise_g = (g_raise + prior) / max(1e-6, denom_g)
                            p_call_g = (g_call + prior) / max(1e-6, denom_g)
                            p_fold_g = (fold_g + prior) / max(1e-6, denom_g)
                            p_sum_g = max(1e-6, p_raise_g + p_call_g + p_fold_g)
                            p_raise_g /= p_sum_g
                            mix = max(0.0, min(1.0, float(conf)))
                            p_raise = (mix * p_raise) + ((1.0 - mix) * p_raise_g)
                        return max(0.0, min(1.0, float(p_raise))), conf
                    if retaliation_global_raise_prob is not None:
                        return max(0.0, min(1.0, float(retaliation_global_raise_prob))), 0.0
                    return None, None
                weighted_rows: list[tuple[dict[str, Any], float]] = []
                call_ev_ref = call_ev_best
                if use_solver_ev and solver_call_ev is not None:
                    call_ev_ref = float(solver_call_ev)
                call_ev_net = None
                call_net_dominated = False
                ev_raise_share_cap: float | None = None
                fold_ev_ref = None
                for _score, _ev, act in score_rows:
                    if act not in candidates:
                        continue
                    if str(act.get("kind")) == "FOLD":
                        fold_ev_ref = _ev if fold_ev_ref is None else max(fold_ev_ref, _ev)
                exp_rake_call = None
                if call_ev_ref is not None:
                    if call_act_best is not None:
                        exp_rake_call = _expected_rake_for_action(
                            action=call_act_best,
                            pot_chips=pot_chips,
                            actor_commit=actor_commit,
                            to_call=to_call,
                            players_alive=players_alive,
                            street=street,
                            defend_rate=None,
                        )
                    else:
                        exp_rake_call = base_rake
                preflop_call_cost = 0.0
                preflop_call_realization = 1.0
                if (
                    oop_realization_weight > 0
                    and facing_bet
                    and to_call > 0
                    and pos_key in ("SB", "BB")
                    and street == "PREFLOP"
                ):
                    spr = None
                    if stack_chips is not None and pot_chips > 0:
                        spr = float(stack_chips) / float(pot_chips)
                    if spr is None:
                        spr = 6.0
                    pot_unit = max(1, pot_chips + to_call)
                    price = float(to_call) / max(1.0, float(pot_unit))
                    eq_strength = float(equity) if equity is not None else price
                    eq_strength = max(0.0, min(1.0, eq_strength))
                    eq_gap = max(0.0, price - eq_strength)
                    gap_ratio = eq_gap / max(0.05, price)
                    gap_ratio = max(0.0, min(1.0, gap_ratio))
                    eq_factor = min(1.25, 0.40 + 0.90 * gap_ratio)
                    spr_factor = 0.40 + 0.08 * max(0.0, min(12.0, spr))
                    rake_factor = 0.6 + 8.0 * rake_rate
                    preflop_opponents = max(1, min(3, players_alive - 1))
                    mw_factor = 1.0 + 0.35 * max(0, preflop_opponents - 1)
                    preflop_call_cost = float(pot_unit) * oop_realization_weight
                    preflop_call_cost *= spr_factor * rake_factor * mw_factor * eq_factor
                    preflop_call_cost *= 1.0 + 0.45 * price
                    pressure = (0.12 * max(0, players_alive - 2)) + (0.04 * max(0.0, min(10.0, spr - 2.0))) + (4.0 * rake_rate)
                    base_realization = 1.0 / (1.0 + pressure)
                    eq_relief = 0.6 + 0.4 * eq_strength
                    preflop_call_realization = max(0.50, min(0.95, base_realization * eq_relief))
                    preflop_call_cost *= 0.65 + 0.35 * preflop_call_realization
                call_ev_ref_raw = call_ev_ref
                if call_ev_ref_raw is not None and (preflop_call_cost > 0 or preflop_call_realization < 0.999):
                    call_ev_ref = float(call_ev_ref_raw) * float(preflop_call_realization) - float(preflop_call_cost)
                call_edge_ratio = None
                call_pref: float | None = None
                high_price_call_floor_raise_cap: float | None = None
                spot_policy_trace: dict[str, Any] | None = None
                low_spr_wet_firewall_strength: float | None = None
                # Keep the stalled high-price wet low-SPR lane runnable even when
                # earlier sub-branches do not bind their local markers.
                firewall_prearm_escalated = False
                visibility_reentry_branch_active = False
                firewall_support_hit_recenter_branch = False
                firewall_support_hit_recenter_escalation = False
                call_ev_ref_call = call_ev_ref
                call_risk_premium: float | None = None
                call_oop_cost_cache: float | None = None
                if (
                    facing_bet
                    and call_ev_ref is not None
                    and fold_ev_ref is not None
                    and exp_rake_call is not None
                ):
                    if street in ("FLOP", "TURN", "RIVER") and pos_key in ("SB", "BB"):
                        price = float(to_call) / max(1.0, float(pot_unit))
                        mw = max(0, players_alive - 2)
                        spr_local = None
                        if stack_chips is not None and pot_chips > 0:
                            spr_local = float(stack_chips) / float(pot_chips)
                        spr_factor = 1.0
                        if spr_local is not None:
                            spr_factor = 1.0 + 0.08 * max(0.0, min(8.0, spr_local - 4.0))
                        if street == "FLOP":
                            base_prem = 0.008
                            price_factor = 0.10
                            price_boost = 1.0
                        elif street == "TURN":
                            base_prem = 0.012
                            price_factor = 0.18
                            price_boost = 1.0 + 0.25 * price
                        else:
                            base_prem = 0.014
                            price_factor = 0.20
                            price_boost = 1.0 + 0.30 * price
                        # Soft-bucket adjustments (price & SPR) to capture facing-bet risk tiers.
                        price_sig_20 = 1.0 / (1.0 + math.exp(-12.0 * (price - 0.20)))
                        price_sig_33 = 1.0 / (1.0 + math.exp(-12.0 * (price - 0.33)))
                        price_sig_50 = 1.0 / (1.0 + math.exp(-12.0 * (price - 0.50)))
                        price_bucket = (0.4 * price_sig_20) + (0.35 * price_sig_33) + (0.25 * price_sig_50)
                        spr_bucket = 0.0
                        if spr_local is not None:
                            spr_sig_4 = 1.0 / (1.0 + math.exp(-1.4 * (float(spr_local) - 4.0)))
                            spr_sig_7 = 1.0 / (1.0 + math.exp(-1.2 * (float(spr_local) - 7.0)))
                            spr_sig_10 = 1.0 / (1.0 + math.exp(-1.0 * (float(spr_local) - 10.0)))
                            spr_bucket = (0.45 * spr_sig_4) + (0.35 * spr_sig_7) + (0.20 * spr_sig_10)
                        bucket_scale = 0.85 + 0.20 * price_bucket + 0.15 * spr_bucket
                        prem = float(pot_unit) * (base_prem + price_factor * price + 0.05 * mw)
                        prem *= price_boost * bucket_scale
                        prem *= (0.6 + 0.4 * unc) * spr_factor
                        call_risk_premium = prem
                        call_ev_ref_call = float(call_ev_ref) - float(prem)
                    delta_rake_call = float(exp_rake_call) - float(base_rake)
                    call_oop_cost_cache = _oop_multi_street_cost(max(1.0, float(to_call)), equity)
                    call_edge = float(call_ev_ref_call) - float(fold_ev_ref) - delta_rake_call - float(call_oop_cost_cache)
                    call_edge_ratio = call_edge / max(1.0, float(pot_unit))
                    edge_floor = 1.0 / (1.0 + math.exp(-(4.0 * call_edge_ratio - 1.0)))
                    unc_factor = max(0.15, 1.0 - 0.85 * unc)
                    edge_floor *= unc_factor
                    edge_floor = max(0.02, min(0.90, edge_floor))
                    target_def = max(target_def, edge_floor * (0.45 + 0.55 * target_def))
                    if street in ("FLOP", "TURN", "RIVER"):
                        edge_sig = 1.0 / (1.0 + math.exp(-3.2 * (call_edge_ratio - 0.02)))
                        edge_ceiling = 0.15 + 0.85 * edge_sig
                        target_def = min(target_def, max(0.05, edge_ceiling))
                    if street in ("TURN", "RIVER") and pos_key in ("SB", "BB"):
                        price = float(to_call) / max(1.0, float(pot_unit))
                        price = max(0.0, min(1.0, price))
                        price_scale = 0.95 - 0.35 * price
                        price_scale = max(0.65, min(0.95, price_scale))
                        target_def = max(0.05, target_def * price_scale)
                    if street in ("TURN", "RIVER") and pos_key in ("SB", "BB"):
                        price = float(to_call) / max(1.0, float(pot_unit))
                        edge_adj = float(call_edge_ratio) - (0.02 + 0.08 * price)
                        edge_sig = 1.0 / (1.0 + math.exp(-4.6 * edge_adj))
                        target_def *= 0.55 + 0.45 * edge_sig
                    if street in ("TURN", "RIVER"):
                        price = float(to_call) / max(1.0, float(pot_unit))
                        edge_adj = float(call_edge_ratio) - (0.03 + 0.08 * price)
                        pref_sig = 1.0 / (1.0 + math.exp(-5.0 * edge_adj))
                        call_pref = max(0.03, min(0.95, pref_sig ** 1.8))
                    if street in ("TURN", "RIVER") and pos_key in ("SB", "BB"):
                        price = float(to_call) / max(1.0, float(pot_unit))
                        price = max(0.0, min(1.0, price))
                        spr_local = None
                        if stack_chips is not None and pot_chips > 0:
                            spr_local = float(stack_chips) / float(pot_chips)
                        # Keep quick-gate runtime stable when visibility/reentry
                        # branches reach this clamp before threshold2_local binds.
                        try:
                            high_price_threshold_local = threshold2_local
                        except NameError:
                            high_price_threshold_local = facing_high_price_threshold2
                        if high_price_threshold_local is None:
                            high_price_threshold_local = facing_high_price_threshold
                        # Force stressed high-price multiway spots to defend via call first, not raise.
                        if (
                            high_price_threshold_local is not None
                            and price >= float(high_price_threshold_local)
                            and players_alive > 2
                            and wet_score is not None
                            and wet_score >= 0.45
                            and spr_local is not None
                            and spr_local <= 3.0
                        ):
                            price_excess = max(
                                0.0,
                                min(
                                    1.0,
                                    (price - float(high_price_threshold_local))
                                    / max(0.05, 1.0 - float(high_price_threshold_local)),
                                ),
                            )
                            wet_excess = max(0.0, min(1.0, (float(wet_score) - 0.45) / 0.55))
                            spr_pressure = max(0.0, min(1.0, (3.0 - float(spr_local)) / 2.0))
                            clamp_strength = max(
                                0.0,
                                min(1.0, (0.45 * price_excess) + (0.30 * wet_excess) + (0.25 * spr_pressure)),
                            )
                            call_floor = 0.56 + (0.16 * clamp_strength)
                            if street == "TURN":
                                call_floor += 0.04
                            call_pref = call_floor if call_pref is None else max(float(call_pref), call_floor)
                            raise_cap = 0.22 - (0.08 * clamp_strength)
                            if street == "TURN":
                                raise_cap -= 0.03
                            high_price_call_floor_raise_cap = max(0.08, min(0.24, raise_cap))
                            raise_edge_gap = None
                            if best_edge_ratio is not None:
                                raise_edge_gap = float(best_edge_ratio) - float(call_edge_ratio)
                            firewall_prearm_strength = 0.0
                            # Pre-arm the existing low-SPR wet firewall in 4-way+ high-price
                            # spots so the loop can break behavior deadlock without a new rule set.
                            if (
                                players_alive >= 4
                                and wet_score >= 0.58
                                and spr_local <= 2.6
                                and (call_edge_ratio is None or float(call_edge_ratio) >= -0.16)
                            ):
                                prearm_price_floor = float(high_price_threshold_local) - (
                                    0.04 if street == "TURN" else 0.03
                                )
                                if facing_high_price_threshold is not None:
                                    prearm_price_floor = max(
                                        float(facing_high_price_threshold),
                                        prearm_price_floor,
                                    )
                                prearm_price_floor = max(0.10, min(0.90, prearm_price_floor))
                                if price >= prearm_price_floor:
                                    prearm_price_pressure = max(
                                        0.0,
                                        min(
                                            1.0,
                                            (price - float(prearm_price_floor))
                                            / max(0.05, 1.0 - float(prearm_price_floor)),
                                        ),
                                    )
                                    prearm_wet_pressure = max(
                                        0.0,
                                        min(1.0, (float(wet_score) - 0.58) / 0.42),
                                    )
                                    prearm_spr_pressure = max(
                                        0.0,
                                        min(1.0, (2.6 - float(spr_local)) / 1.2),
                                    )
                                    firewall_prearm_strength = max(
                                        0.0,
                                        min(
                                            1.0,
                                            (0.40 * prearm_price_pressure)
                                            + (0.35 * prearm_wet_pressure)
                                            + (0.25 * prearm_spr_pressure),
                                        ),
                                    )
                            # Let a strong pre-arm signal escalate into the existing firewall
                            # one step earlier on TURN/RIVER 4-way+ branches without creating
                            # a separate defense rule family.
                            firewall_prearm_escalated = (
                                players_alive >= 4
                                and street in ("TURN", "RIVER")
                                and wet_score >= 0.56
                                and spr_local <= 2.45
                                and price >= float(high_price_threshold_local)
                                and firewall_prearm_strength >= 0.32
                                and (call_edge_ratio is None or float(call_edge_ratio) >= -0.10)
                            )
                            firewall_armed = (
                                (
                                    wet_score >= 0.60
                                    and spr_local <= 2.2
                                    and (
                                        price >= min(1.0, float(high_price_threshold_local) + 0.08)
                                        or clamp_strength >= 0.58
                                        or firewall_prearm_strength >= 0.22
                                    )
                                )
                                or firewall_prearm_escalated
                            )
                            if firewall_armed and (raise_edge_gap is None or raise_edge_gap <= 0.16):
                                firewall_price_pressure = max(
                                    price_excess,
                                    max(
                                        0.0,
                                        min(
                                            1.0,
                                            (price - float(high_price_threshold_local) - 0.08)
                                            / max(0.05, 1.0 - float(high_price_threshold_local) - 0.08),
                                        ),
                                    ),
                                )
                                firewall_wet_pressure = max(0.0, min(1.0, (float(wet_score) - 0.60) / 0.40))
                                firewall_spr_pressure = max(0.0, min(1.0, (2.2 - float(spr_local)) / 1.2))
                                firewall_strength = max(
                                    0.0,
                                    min(
                                        1.0,
                                        (0.40 * firewall_price_pressure)
                                        + (0.35 * firewall_wet_pressure)
                                        + (0.25 * firewall_spr_pressure),
                                    ),
                                )
                                if firewall_prearm_strength > 0.0:
                                    firewall_strength = max(
                                        firewall_strength,
                                        0.20 + (0.22 * firewall_prearm_strength),
                                    )
                                if raise_edge_gap is not None:
                                    gap_relief = max(0.0, min(1.0, float(raise_edge_gap) / 0.16))
                                    firewall_strength *= 1.0 - (0.35 * gap_relief)
                                if call_edge_ratio is not None and float(call_edge_ratio) < -0.08:
                                    call_penalty = max(0.0, min(1.0, (-0.08 - float(call_edge_ratio)) / 0.12))
                                    firewall_strength *= 1.0 - (0.50 * call_penalty)
                                if firewall_strength >= 0.18:
                                    low_spr_wet_firewall_strength = firewall_strength
                                    firewall_call_floor = 0.72 + (0.12 * firewall_strength)
                                    if street == "TURN":
                                        firewall_call_floor += 0.03
                                    call_pref = (
                                        firewall_call_floor
                                        if call_pref is None
                                        else max(float(call_pref), firewall_call_floor)
                                    )
                                    firewall_raise_cap = 0.12 - (0.05 * firewall_strength)
                                    if street == "TURN":
                                        firewall_raise_cap -= 0.02
                                    firewall_raise_cap = max(0.05, min(0.14, firewall_raise_cap))
                                    if high_price_call_floor_raise_cap is None:
                                        high_price_call_floor_raise_cap = firewall_raise_cap
                                    else:
                                        high_price_call_floor_raise_cap = min(
                                            float(high_price_call_floor_raise_cap),
                                            firewall_raise_cap,
                                        )
                            visibility_reentry_branch_active = bool(
                                locals().get("visibility_low_spr_wet_reentry_branch", False)
                            )
                            # Keep the TURN support reentry clamp runnable even if its
                            # upstream branch-scoped strength marker did not bind on this path.
                            try:
                                turn_focus_support_raise_clamp_strength_local = max(
                                    0.0,
                                    min(1.0, float(turn_focus_support_raise_clamp_strength)),
                                )
                            except Exception:
                                turn_focus_support_raise_clamp_strength_local = 0.0
                            if (
                                turn_focus_support_raise_clamp_strength_local <= 0.0
                                and street == "TURN"
                                and (
                                    firewall_support_hit_recenter_branch
                                    or firewall_prearm_escalated
                                    or visibility_reentry_branch_active
                                )
                            ):
                                # Bridge the already-computed low-SPR wet firewall signal
                                # into the existing TURN support clamp when the upstream
                                # reentry marker did not bind on this hot path.
                                fallback_firewall_strength = 0.0
                                if low_spr_wet_firewall_strength is not None:
                                    fallback_firewall_strength = max(
                                        0.0,
                                        min(1.0, float(low_spr_wet_firewall_strength)),
                                    )
                                if fallback_firewall_strength > 0.0:
                                    turn_focus_support_raise_clamp_strength_local = min(
                                        0.74,
                                        0.18
                                        + (0.34 * fallback_firewall_strength)
                                        + (
                                            0.08
                                            if firewall_support_hit_recenter_branch
                                            else 0.0
                                        )
                                        + (
                                            0.05 if firewall_prearm_escalated else 0.0
                                        )
                                        + (
                                            0.04
                                            if visibility_reentry_branch_active
                                            else 0.0
                                        ),
                                    )
                                else:
                                    # Keep the stalled TURN support clamp behaviorally
                                    # observable when the same recenter/prearm lane is active
                                    # but the firewall strength did not bind on this path.
                                    turn_focus_support_raise_clamp_strength_local = min(
                                        0.42,
                                        0.15
                                        + (
                                            0.12
                                            if firewall_support_hit_recenter_branch
                                            else 0.0
                                        )
                                        + (
                                            0.08 if firewall_prearm_escalated else 0.0
                                        )
                                        + (
                                            0.05
                                            if visibility_reentry_branch_active
                                            else 0.0
                                        ),
                                    )
                            if turn_focus_support_raise_clamp_strength_local > 0.0:
                                turn_focus_support_raise_clamp_strength = max(
                                    float(turn_focus_support_raise_clamp_strength),
                                    turn_focus_support_raise_clamp_strength_local,
                                )
                                support_raise_gap_relief = 0.0
                                if best_edge_ratio is not None and call_edge_ratio is not None:
                                    support_raise_gap_relief = max(
                                        0.0,
                                        min(
                                            1.0,
                                            (float(best_edge_ratio) - float(call_edge_ratio)) / 0.20,
                                        ),
                                    )
                                turn_focus_support_raise_clamp_strength_local *= (
                                    1.0 - (0.40 * support_raise_gap_relief)
                                )
                                support_call_floor = (
                                    0.82 + (0.10 * turn_focus_support_raise_clamp_strength_local)
                                )
                                if (
                                    call_edge_ratio is not None
                                    and float(call_edge_ratio) < -0.06
                                ):
                                    support_call_floor -= 0.04 * max(
                                        0.0,
                                        min(
                                            1.0,
                                            (-0.06 - float(call_edge_ratio)) / 0.10,
                                        ),
                                    )
                                support_call_floor = max(0.78, min(0.94, support_call_floor))
                                call_pref = (
                                    support_call_floor
                                    if call_pref is None
                                    else max(float(call_pref), support_call_floor)
                                )
                                support_raise_cap = (
                                    0.09 - (0.05 * turn_focus_support_raise_clamp_strength_local)
                                )
                                if visibility_reentry_branch_active:
                                    # Keep the reentry clamp runnable even if the outer SPR alias
                                    # or branch marker is absent on this hot path.
                                    try:
                                        reentry_proximity_local = max(
                                            0.0,
                                            min(1.0, float(reentry_proximity)),
                                        )
                                    except Exception:
                                        reentry_proximity_local = 0.0
                                    reentry_spr_bonus = (
                                        0.02
                                        if spr_local is not None and spr_local <= 1.8
                                        else 0.0
                                    )
                                    # Once the exact TURN low-SPR wet visibility-reentry lane is
                                    # active, convert the remaining support budget through call
                                    # share instead of widening thresholds again.
                                    support_call_floor = min(
                                        0.95,
                                        max(
                                            float(call_pref),
                                            support_call_floor
                                            + 0.03
                                            + (0.04 * reentry_proximity_local)
                                            + reentry_spr_bonus,
                                        ),
                                    )
                                    call_pref = max(float(call_pref), support_call_floor)
                                    support_raise_cap -= (
                                        0.015
                                        + (0.02 * reentry_proximity_local)
                                        + (0.01 if spr_local is not None and spr_local <= 1.8 else 0.0)
                                    )
                                support_raise_cap = max(0.03, min(0.08, support_raise_cap))
                                if high_price_call_floor_raise_cap is None:
                                    high_price_call_floor_raise_cap = support_raise_cap
                                else:
                                    high_price_call_floor_raise_cap = min(
                                        float(high_price_call_floor_raise_cap),
                                        support_raise_cap,
                                    )
                            if spot_policy is not None and street in ("TURN", "RIVER"):
                                spot_context = build_spot_context(
                                    street=street,
                                    facing_bet=bool(facing_bet),
                                    pos_key=pos_key,
                                    players_alive=players_alive if isinstance(players_alive, int) else None,
                                    pot_chips=int(pot_chips),
                                    to_call_chips=int(to_call),
                                    actor_stack_chips=int(stack_chips) if stack_chips is not None else None,
                                    wet_score=int(wet_score) if wet_score is not None else None,
                                )
                                spot_overlay = apply_spot_policy_overlay(
                                    spec=spot_policy,
                                    context=spot_context,
                                    defend_target=target_def,
                                    call_pref=call_pref,
                                    raise_cap_max=high_price_call_floor_raise_cap,
                                )
                                if spot_overlay.matched_rule is not None:
                                    target_def = spot_overlay.defend_target
                                    call_pref = spot_overlay.call_pref
                                    high_price_call_floor_raise_cap = spot_overlay.raise_cap_max
                                    spot_policy_trace = spot_overlay.matched_rule
                    if street in ("FLOP", "TURN", "RIVER"):
                        best_def_ev = float(call_ev_ref) - float(delta_rake_call) - float(call_oop_cost_cache)
                        for _score, _ev, act in score_rows:
                            if act not in candidates:
                                continue
                            kind = str(act.get("kind"))
                            if kind not in ("RAISE", "BET", "ALLIN"):
                                continue
                            ev_use = _solver_ev_for_action(act, _ev)
                            target = int(act.get("target_total_commit_chips", actor_commit))
                            risk = max(0, target - actor_commit)
                            exp_rake_raise = _expected_rake_for_action(
                                action=act,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                street=street,
                                defend_rate=None,
                            )
                            delta_rake = float(exp_rake_raise) - float(exp_rake_call)
                            risk_unit = max(float(to_call), float(risk))
                            oop_cost = _oop_multi_street_cost(risk_unit, equity)
                            raise_ev_net = float(ev_use) - float(delta_rake) - float(oop_cost)
                            if raise_ev_net > best_def_ev:
                                best_def_ev = raise_ev_net
                        gap = (float(best_def_ev) - float(fold_ev_ref)) / max(1.0, float(pot_unit))
                        gap_sig = 1.0 / (1.0 + math.exp(-3.2 * gap))
                        defend_ev_cap = 0.08 + 0.90 * gap_sig
                        defend_ev_cap *= 0.70 + 0.30 * max(0.0, min(1.0, 1.0 - unc))
                        defend_ev_cap = max(0.05, min(0.95, defend_ev_cap))
                        target_def = min(target_def, defend_ev_cap)
                ev_soft_weight_by_id: dict[int, float] = {}
                if facing_bet and defend_target is not None and candidates:
                    temp = 0.80 + 2.0 * max(0.0, min(1.0, unc))
                    ev_vals: list[tuple[dict[str, Any], float]] = []
                    for _score, _ev, act in score_rows:
                        if act not in candidates:
                            continue
                        if str(act.get("kind")) == "FOLD":
                            continue
                        ev_use = _solver_ev_for_action(act, _ev)
                        ev_norm = float(ev_use) / max(1.0, float(pot_unit))
                        ev_vals.append((act, ev_norm))
                    if ev_vals:
                        max_ev = max(v for _, v in ev_vals)
                        wsum = 0.0
                        for act, v in ev_vals:
                            w = math.exp((v - max_ev) / max(1e-6, temp))
                            ev_soft_weight_by_id[id(act)] = w
                            wsum += w
                        if wsum > 0:
                            for k in list(ev_soft_weight_by_id.keys()):
                                ev_soft_weight_by_id[k] /= wsum
                def _raise_edge_metrics(act: dict[str, Any], ev_use: float) -> tuple[float, float, float] | None:
                    if exp_rake_call is None:
                        return None
                    target = int(act.get("target_total_commit_chips", actor_commit))
                    risk = max(0, target - actor_commit)
                    exp_rake_raise = _expected_rake_for_action(
                        action=act,
                        pot_chips=pot_chips,
                        actor_commit=actor_commit,
                        to_call=to_call,
                        players_alive=players_alive,
                        street=street,
                        defend_rate=None,
                    )
                    delta_rake = float(exp_rake_raise) - float(exp_rake_call or 0.0)
                    risk_unit = max(float(to_call), float(risk))
                    oop_cost = _oop_multi_street_cost(risk_unit, equity)
                    ev_edge = float(ev_use)
                    if use_solver_ev and solver_raise_ev is not None:
                        ev_edge = float(solver_raise_ev)
                    base_call_ev = float(call_ev_ref)
                    if call_ev_ref_call is not None:
                        base_call_ev = float(call_ev_ref_call)
                    edge = float(ev_edge) - base_call_ev - delta_rake - oop_cost
                    risk_exposure = float(risk_unit) + max(0.0, delta_rake) + max(0.0, oop_cost)
                    if street in ("TURN", "RIVER"):
                        spr = None
                        if stack_chips is not None and pot_chips > 0:
                            spr = float(stack_chips) / float(pot_chips)
                        if spr is None:
                            spr = 4.0
                        pressure = _pressure_index(
                            players_alive=players_alive,
                            spr=spr,
                            wet_score=wet_score,
                            pos_key=pos_key,
                            street=street,
                        )
                        mw_factor = 1.0 + 0.25 * max(0, players_alive - 2)
                        spr_factor = 0.90 + 0.10 * max(0.0, min(8.0, spr - 2.0))
                        rake_ratio = float(delta_rake) / max(1.0, float(pot_unit))
                        extra_risk_cost = float(risk_unit) * (0.012 + 0.35 * rake_ratio)
                        extra_risk_cost += float(delta_rake) * 0.6
                        extra_risk_cost *= (1.0 + 0.35 * pressure) * mw_factor * spr_factor
                        edge -= extra_risk_cost
                        risk_exposure += max(0.0, float(extra_risk_cost))
                    edge_ratio = float(edge) / max(1.0, float(pot_unit))
                    edge_per_risk = float(edge) / max(1.0, float(risk_exposure))
                    return edge, edge_ratio, edge_per_risk

                def _raise_mix_cap_from_edge(
                    edge_ratio: float,
                    *,
                    unc: float,
                    players_alive: int,
                    spr: float | None,
                    price: float | None,
                    to_call_bb: float | None,
                    pos_key: str,
                    street: str | None,
                    solver_conf: float,
                ) -> float:
                    edge_ratio = max(-2.5, min(2.5, float(edge_ratio)))
                    base = 1.0 / (1.0 + math.exp(-4.2 * edge_ratio))
                    cap = 0.02 + 0.78 * base
                    conf = 0.55 + 0.45 * max(0.0, min(1.0, float(solver_conf)))
                    unc_scale = 0.65 + 0.35 * max(0.0, min(1.0, 1.0 - float(unc)))
                    cap *= conf * unc_scale
                    spr_val = spr if spr is not None else 5.0
                    spr_penalty = 1.0 / (1.0 + 0.12 * max(0.0, spr_val - 4.0))
                    mw_penalty = 1.0 / (1.0 + 0.25 * max(0, players_alive - 2))
                    oop_penalty = 1.0
                    if pos_key in ("SB", "BB") and street in ("FLOP", "TURN"):
                        oop_penalty = 0.90
                    price_penalty = 1.0
                    if price is not None:
                        p = max(0.0, min(1.0, float(price)))
                        price_penalty = 0.55 + 0.45 * (1.0 / (1.0 + 1.8 * p))
                    bb_penalty = 1.0
                    if pos_key in ("SB", "BB") and street in ("TURN", "RIVER") and to_call_bb is not None:
                        bb_ratio = max(0.0, float(to_call_bb))
                        bb_sig = 1.0 / (1.0 + math.exp(1.8 * (bb_ratio - 1.0)))
                        bb_penalty = 0.55 + 0.45 * bb_sig
                    cap *= spr_penalty * mw_penalty * oop_penalty * price_penalty * bb_penalty
                    return max(0.01, min(0.70, cap))

                raise_metrics_by_id: dict[int, tuple[float, float, float]] = {}
                raise_net_delta_by_id: dict[int, float] = {}
                hint_raise_act: dict[str, Any] | None = None
                hint_raise_local_ev: float | None = None
                if solver_hint_target is not None and solver_hint_kind == "RAISE":
                    best_dist = None
                    for _score, _ev, act in score_rows:
                        if act not in candidates:
                            continue
                        kind = str(act.get("kind"))
                        if kind not in ("RAISE", "BET", "ALLIN"):
                            continue
                        target = int(act.get("target_total_commit_chips", actor_commit))
                        dist = abs(float(target) - float(solver_hint_target))
                        if best_dist is None or dist < best_dist:
                            best_dist = dist
                            hint_raise_act = act
                            hint_raise_local_ev = float(_ev)
                for score, _ev, act in score_rows:
                    if act not in candidates:
                        continue
                    kind = str(act.get("kind"))
                    target = int(act.get("target_total_commit_chips", actor_commit))
                    risk = max(0, target - actor_commit)
                    base = max(0.01, (score - min_score) + 1.0)
                    ev_use = _solver_ev_for_action(act, _ev)
                    if solver_hint_kind is not None and kind == solver_hint_kind:
                        hint_target = solver_hint_target if solver_hint_target is not None else int(act.get("target_total_commit_chips", actor_commit))
                        act_target = int(act.get("target_total_commit_chips", actor_commit))
                        dist = abs(float(act_target) - float(hint_target)) / max(1.0, float(pot_unit))
                        solver_closeness = 1.0 / (1.0 + dist)
                        base *= 1.0 + 0.6 * solver_closeness
                    if kind in ("RAISE", "BET", "ALLIN") and solver_hint_target is not None and solver_hint_kind == "RAISE":
                        act_target = target
                        dist = abs(float(act_target) - float(solver_hint_target)) / max(1.0, float(pot_unit))
                        size_penalty = 1.0 / (1.0 + (4.5 * dist))
                        base *= 0.35 + 0.65 * size_penalty
                    if facing_bet and defend_target is not None:
                        edge_bias = 0.0
                        if solver_edge is not None and not use_solver_ev:
                            edge_bias += float(solver_edge)
                        if call_ev_ref is not None:
                            ref_ev = float(call_ev_ref)
                            call_blend = None
                            if solver_call_ev is not None and pos_key in ("SB", "BB"):
                                call_blend = (0.25 + 0.55 * max(0.0, min(1.0, solver_ev_conf))) * max(0.35, 1.0 - unc)
                                call_blend = max(0.0, min(0.70, call_blend))
                                ref_ev = (1.0 - call_blend) * ref_ev + call_blend * float(solver_call_ev)
                            if kind == "CALL" and call_ev_ref_call is not None:
                                ref_ev = float(call_ev_ref_call)
                                if call_blend is not None and solver_call_ev is not None:
                                    ref_ev = (1.0 - call_blend) * ref_ev + call_blend * float(solver_call_ev)
                            edge_bias += float(ev_use) - ref_ev
                        edge_ratio = edge_bias / max(1.0, float(pot_unit))
                        if kind in ("RAISE", "BET", "ALLIN"):
                            base *= max(0.35, min(1.7, 1.0 + 2.0 * edge_ratio))
                        elif kind == "CALL":
                            base *= max(0.6, min(1.6, 1.0 - 1.4 * edge_ratio))
                        if facing_bet and defend_target is not None:
                            if kind == "CALL":
                                base *= 1.10
                                if solver_hint_kind == "CALL":
                                    base *= 1.30
                                if call_pref is not None:
                                    exp = 1.8
                                    if street == "RIVER" and pos_key in ("SB", "BB"):
                                        exp = 2.4
                                    adj = float(call_pref) ** exp
                                    base *= 0.15 + 0.85 * adj
                                if call_edge_ratio is not None and pos_key in ("SB", "BB") and street in ("TURN", "RIVER"):
                                    price = float(to_call) / max(1.0, float(pot_unit))
                                    edge_floor = 0.02 + 0.06 * price
                                    if street == "RIVER":
                                        edge_floor = 0.03 + 0.08 * price
                                    edge_adj = float(call_edge_ratio) - edge_floor
                                    edge_sig = 1.0 / (1.0 + math.exp(-4.2 * edge_adj))
                                    base *= 0.55 + 0.45 * edge_sig
                                if call_net_dominated and street in ("TURN", "RIVER"):
                                    base *= 0.25
                            elif kind in ("RAISE", "BET", "ALLIN"):
                                if solver_hint_kind == "CALL":
                                    base *= 0.60
                                elif solver_hint_kind == "RAISE":
                                    base *= 1.10
                                if pos_key in ("SB", "BB") and street in ("TURN", "RIVER"):
                                    price = float(to_call) / max(1.0, float(pot_unit))
                                    price = max(0.0, min(1.5, price))
                                    price_penalty = 1.0 / (1.0 + 2.4 * price)
                                    gap_sig = 1.0 / (1.0 + math.exp(-3.8 * (edge_ratio - 0.02)))
                                    conf_scale = 0.70 + 0.30 * max(0.0, min(1.0, solver_ev_conf))
                                    base *= (0.65 + 0.35 * price_penalty) * (0.55 + 0.45 * gap_sig) * conf_scale
                                if street == "RIVER" and players_alive == 2 and pos_key in ("SB", "BB"):
                                    edge_boost = 1.0 / (1.0 + math.exp(-4.0 * (edge_ratio - 0.02)))
                                    base *= 0.85 + 0.45 * edge_boost
                    if kind in ("RAISE", "BET", "ALLIN"):
                        flags = action_flags.get(id(act))
                        signal = float(flags.get("signal", 0.0)) if flags is not None else 0.0
                        value_ok = bool(flags.get("value_ok")) if flags is not None else False
                        pressure_ok = bool(flags.get("pressure_ok")) if flags is not None else False
                        boost = 1.0 + 1.5 * max(0.0, min(0.45, signal))
                        if value_ok:
                            boost *= 1.05
                        if pressure_ok:
                            boost *= 1.03
                        base *= boost
                        if facing_bet and defend_target is not None and not (value_ok or pressure_ok):
                            base *= 0.55
                        if use_solver_ev and call_ev_ref is not None:
                            metrics = _raise_edge_metrics(act, ev_use)
                            if metrics is not None:
                                raise_metrics_by_id[id(act)] = metrics
                                edge_per_risk = max(-2.0, min(2.0, float(metrics[2])))
                                conf = max(0.25, min(1.0, 1.0 - 1.6 * unc))
                                if solver_call_ev is None or solver_raise_ev is None:
                                    conf *= 0.75
                                if solver_hint_kind is None:
                                    conf *= 0.90
                                sigmoid = 1.0 / (1.0 + math.exp(-3.0 * edge_per_risk))
                                sharpened = sigmoid ** 1.6
                                penalty = (1.0 - conf) + (conf * sharpened)
                                penalty = max(0.05, min(1.0, penalty))
                                base *= penalty
                        if call_edge_ratio is not None:
                            metrics = raise_metrics_by_id.get(id(act))
                            if metrics is None:
                                metrics = _raise_edge_metrics(act, ev_use)
                            if metrics is not None:
                                edge_ratio = float(metrics[1])
                                delta = edge_ratio - float(call_edge_ratio)
                                raise_bias = 1.0 / (1.0 + math.exp(-3.0 * delta))
                                base *= 0.40 + 0.60 * raise_bias
                                if street in ("TURN", "RIVER"):
                                    tr_bias = 1.0 / (1.0 + math.exp(-4.5 * delta))
                                    base *= 0.25 + 0.75 * tr_bias
                    weighted_rows.append((act, base))
                net_ev_weight_by_id: dict[int, float] = {}
                net_ev_risk_weight_by_id: dict[int, float] = {}
                defend_ev_share: float | None = None
                defend_ev_cap: float | None = None
                if (
                    facing_bet
                    and pos_key in ("SB", "BB")
                    and exp_rake_call is not None
                ):
                    net_entries: list[tuple[dict[str, Any], float]] = []
                    call_oop_cost = (
                        float(call_oop_cost_cache)
                        if call_oop_cost_cache is not None
                        else _oop_multi_street_cost(max(1.0, float(to_call)), equity)
                    )
                    if call_ev_ref is not None:
                        call_ev_net = float(call_ev_ref_call) - (float(exp_rake_call) - float(base_rake)) - float(call_oop_cost)
                        if fold_ev_ref is not None:
                            pot_unit_local = max(1.0, float(pot_unit))
                            margin = max(0.0, (0.015 + 0.5 * unc) * pot_unit_local)
                            if (
                                facing_bet
                                and pos_key in ("SB", "BB")
                                and street in ("TURN", "RIVER")
                                and to_call > 0
                            ):
                                price = float(to_call) / pot_unit_local
                                price_term = 0.02 + 0.08 * max(0.0, min(1.5, price))
                                if street == "RIVER":
                                    price_term = 0.03 + 0.12 * max(0.0, min(1.5, price))
                                margin += pot_unit_local * price_term
                                if players_alive > 2:
                                    margin += pot_unit_local * (0.02 * max(0, players_alive - 2))
                            if call_ev_net <= float(fold_ev_ref) + margin:
                                call_net_dominated = True
                    for _score, _ev, act in score_rows:
                        if act not in candidates:
                            continue
                        kind = str(act.get("kind"))
                        if kind == "CALL":
                            if call_ev_net is None:
                                continue
                            call_ev_soft = float(call_ev_net)
                            if call_net_dominated and fold_ev_ref is not None:
                                pot_unit_local = max(1.0, float(pot_unit))
                                margin = max(0.0, (0.015 + 0.5 * unc) * pot_unit_local)
                                call_ev_soft = min(call_ev_soft, float(fold_ev_ref) - margin)
                            net_entries.append((act, call_ev_soft))
                        elif kind in ("RAISE", "BET", "ALLIN"):
                            ev_use = _solver_ev_for_action(act, _ev)
                            metrics = raise_metrics_by_id.get(id(act))
                            if metrics is None:
                                metrics = _raise_edge_metrics(act, ev_use)
                            if metrics is None:
                                continue
                            edge = float(metrics[0])
                            edge_per_risk = float(metrics[2])
                            if call_ev_net is not None:
                                exp_rake_raise = _expected_rake_for_action(
                                    action=act,
                                    pot_chips=pot_chips,
                                    actor_commit=actor_commit,
                                    to_call=to_call,
                                    players_alive=players_alive,
                                    street=street,
                                    defend_rate=None,
                                )
                                risk_unit = max(float(to_call), float(max(0, int(act.get("target_total_commit_chips", actor_commit)) - actor_commit)))
                                oop_cost = _oop_multi_street_cost(risk_unit, equity)
                                raise_ev_net = float(ev_use) - (float(exp_rake_raise) - float(base_rake)) - float(oop_cost)
                                raise_net_delta_by_id[id(act)] = raise_ev_net - float(call_ev_net)
                            risk_weight = 1.0 / (1.0 + math.exp(-3.0 * edge_per_risk))
                            if pos_key in ("SB", "BB") and street in ("TURN", "RIVER"):
                                to_call_bb = float(to_call) / max(1.0, float(bb or 1))
                                size_sig = 1.0 / (1.0 + math.exp(1.6 * (to_call_bb - 1.0)))
                                risk_weight *= 0.55 + 0.45 * size_sig
                            net_ev_risk_weight_by_id[id(act)] = 0.25 + 0.75 * max(0.0, min(1.0, risk_weight))
                            base_ev = float(call_ev_ref) if call_ev_ref is not None else float(ev_use)
                            net_entries.append((act, base_ev + edge))
                    if net_entries:
                        pot_scale = max(1.0, float(pot_unit))
                        temp = 0.35 + 1.8 * max(0.0, min(1.0, unc))
                        max_ev_raw = max(ev for _act, ev in net_entries)
                        if fold_ev_ref is not None:
                            max_ev_raw = max(max_ev_raw, float(fold_ev_ref))
                        max_ev = max_ev_raw / pot_scale
                        wsum = 0.0
                        for act, ev in net_entries:
                            ev_norm = (float(ev) / pot_scale) - max_ev
                            w = math.exp(ev_norm / max(1e-6, temp))
                            risk_w = net_ev_risk_weight_by_id.get(id(act))
                            if risk_w is not None:
                                w *= float(risk_w)
                            net_ev_weight_by_id[id(act)] = w
                            wsum += w
                        if fold_ev_ref is not None:
                            max_def_ev = max((float(ev) - float(fold_ev_ref)) for _act, ev in net_entries)
                            max_def_ev = max(max_def_ev, 0.0)
                            max_def_ev_norm = max_def_ev / pot_scale
                            def_wsum = 0.0
                            for act, ev in net_entries:
                                ev_delta = float(ev) - float(fold_ev_ref)
                                ev_norm = (ev_delta / pot_scale) - max_def_ev_norm
                                w = math.exp(ev_norm / max(1e-6, temp))
                                risk_w = net_ev_risk_weight_by_id.get(id(act))
                                if risk_w is not None:
                                    w *= float(risk_w)
                                def_wsum += w
                            fold_w = math.exp((0.0 - max_def_ev_norm) / max(1e-6, temp))
                            denom = def_wsum + fold_w
                            if denom > 0:
                                defend_ev_share = def_wsum / denom
                        if wsum > 0:
                            for k in list(net_ev_weight_by_id.keys()):
                                net_ev_weight_by_id[k] /= wsum
                if net_ev_weight_by_id:
                    def_soft_sum = 0.0
                    def_current_sum = 0.0
                    for act, w in weighted_rows:
                        kind = str(act.get("kind"))
                        if kind in ("CALL", "RAISE", "BET", "ALLIN"):
                            def_current_sum += w
                            soft_w = net_ev_weight_by_id.get(id(act))
                            if soft_w is not None:
                                def_soft_sum += float(soft_w)
                    scale = (def_current_sum / def_soft_sum) if def_soft_sum > 0 else 1.0
                    # Use EV-implied share to cap raise aggression later.
                    if facing_bet and pos_key in ("SB", "BB"):
                        call_soft = 0.0
                        raise_soft = 0.0
                        for act, _w in weighted_rows:
                            soft_w = net_ev_weight_by_id.get(id(act))
                            if soft_w is None:
                                continue
                            kind = str(act.get("kind"))
                            if kind == "CALL":
                                call_soft += float(soft_w)
                            elif kind in ("RAISE", "BET", "ALLIN"):
                                raise_soft += float(soft_w)
                        if call_soft > 0 and raise_soft > 0:
                            ev_raise_share_cap = raise_soft / max(1e-9, (call_soft + raise_soft))
                        if high_price_call_floor_raise_cap is not None:
                            if ev_raise_share_cap is None:
                                ev_raise_share_cap = float(high_price_call_floor_raise_cap)
                            else:
                                ev_raise_share_cap = min(float(ev_raise_share_cap), float(high_price_call_floor_raise_cap))
                    adjusted: list[tuple[dict[str, Any], float]] = []
                    for act, w in weighted_rows:
                        kind = str(act.get("kind"))
                        soft_w = net_ev_weight_by_id.get(id(act))
                        if soft_w is not None and kind in ("CALL", "RAISE", "BET", "ALLIN"):
                            w = float(soft_w) * scale
                        adjusted.append((act, w))
                    weighted_rows = adjusted
                    if (
                        defend_ev_share is not None
                        and defend_target is not None
                        and facing_bet
                        and street in ("FLOP", "TURN", "RIVER")
                    ):
                        ev_conf = 0.0
                        if solver_call_ev is not None and solver_raise_ev is not None:
                            ev_conf = 1.0
                        elif solver_call_ev is not None or solver_raise_ev is not None:
                            ev_conf = 0.6
                        conf = (0.35 + 0.65 * ev_conf) * max(0.35, 1.0 - unc)
                        if pos_key in ("SB", "BB") and street in ("TURN", "RIVER"):
                            conf = min(0.95, conf * 1.15)
                        blended = (1.0 - conf) * float(defend_target) + conf * float(defend_ev_share)
                        defend_target = min(float(defend_target), max(0.01, min(0.99, blended)))
                elif ev_soft_weight_by_id:
                    adjusted: list[tuple[dict[str, Any], float]] = []
                    for act, w in weighted_rows:
                        kind = str(act.get("kind"))
                        soft_w = ev_soft_weight_by_id.get(id(act))
                        if soft_w is not None and kind in ("CALL", "RAISE", "BET", "ALLIN"):
                            w *= 0.80 + 0.20 * soft_w
                        adjusted.append((act, w))
                    weighted_rows = adjusted
                if call_net_dominated:
                    adjusted: list[tuple[dict[str, Any], float]] = []
                    for act, w in weighted_rows:
                        if str(act.get("kind")) == "CALL":
                            adjusted.append((act, 0.0))
                        else:
                            adjusted.append((act, w))
                    weighted_rows = adjusted
                def_sum = sum(w for act, w in weighted_rows if str(act.get("kind")) != "FOLD")
                fold_sum = sum(w for act, w in weighted_rows if str(act.get("kind")) == "FOLD")
                if def_sum > 0 and fold_sum > 0:
                    current_def = def_sum / max(1e-6, def_sum + fold_sum)
                    scale_def = target_def / max(1e-6, current_def)
                    scale_fold = (1.0 - target_def) / max(1e-6, 1.0 - current_def)
                    scaled: list[tuple[dict[str, Any], float]] = []
                    for act, w in weighted_rows:
                        if str(act.get("kind")) == "FOLD":
                            scaled.append((act, w * scale_fold))
                        else:
                            scaled.append((act, w * scale_def))
                    weighted_rows = scaled
                raise_cap = None
                raise_cap_marginal = None
                expected_edge_ratio_val: float | None = None
                best_edge_value = None
                best_edge_ratio = None
                best_edge_act: dict[str, Any] | None = None
                raise_ev_best = None
                raise_ev_best_raw = None
                expected_edge_per_risk_val: float | None = None
                if facing_bet and pos_key in ("SB", "BB") and call_ev_ref is not None:
                    best_edge = None
                    edge_ratio_vals: list[float] = []
                    edge_per_risk_vals: list[float] = []
                    net_delta_vals: list[float] = []
                    if hint_raise_act is not None:
                        ev_use = _solver_ev_for_action(hint_raise_act, float(hint_raise_local_ev or 0.0))
                        raise_ev_best_raw = ev_use
                        metrics = raise_metrics_by_id.get(id(hint_raise_act))
                        if metrics is None:
                            metrics = _raise_edge_metrics(hint_raise_act, ev_use)
                        if metrics is not None:
                            edge, edge_ratio, _edge_per_risk = metrics
                            best_edge = edge
                            best_edge_ratio = edge_ratio
                            best_edge_act = hint_raise_act
                            edge_ratio_vals.append(edge_ratio)
                            edge_per_risk_vals.append(float(_edge_per_risk))
                            net_delta = raise_net_delta_by_id.get(id(hint_raise_act))
                            if net_delta is not None:
                                net_delta_vals.append(float(net_delta))
                    if best_edge is None:
                        for _score, _ev, act in score_rows:
                            if act not in candidates:
                                continue
                            kind = str(act.get("kind"))
                            if kind not in ("RAISE", "BET", "ALLIN"):
                                continue
                            ev_use = _solver_ev_for_action(act, _ev)
                            if raise_ev_best_raw is None or ev_use > raise_ev_best_raw:
                                raise_ev_best_raw = ev_use
                            metrics = raise_metrics_by_id.get(id(act))
                            if metrics is None:
                                metrics = _raise_edge_metrics(act, ev_use)
                            if metrics is None:
                                continue
                            edge, edge_ratio, edge_per_risk = metrics
                            edge_ratio_vals.append(edge_ratio)
                            edge_per_risk_vals.append(float(edge_per_risk))
                            net_delta = raise_net_delta_by_id.get(id(act))
                            if net_delta is not None:
                                net_delta_vals.append(float(net_delta))
                            if best_edge is None or edge > best_edge:
                                best_edge = edge
                                best_edge_ratio = edge_ratio
                                best_edge_act = act
                    if best_edge is not None:
                        best_edge_value = best_edge
                        expected_edge_ratio = float(best_edge_ratio or 0.0)
                        if edge_ratio_vals:
                            maxv = max(edge_ratio_vals)
                            wsum = 0.0
                            esum = 0.0
                            for v in edge_ratio_vals:
                                w = math.exp(3.0 * (v - maxv))
                                wsum += w
                                esum += w * v
                            if wsum > 0:
                                expected_edge_ratio = esum / wsum
                        expected_edge_per_risk = expected_edge_ratio
                        if edge_per_risk_vals:
                            maxv = max(edge_per_risk_vals)
                            wsum = 0.0
                            esum = 0.0
                            for v in edge_per_risk_vals:
                                w = math.exp(3.0 * (v - maxv))
                                wsum += w
                                esum += w * v
                            if wsum > 0:
                                expected_edge_per_risk = esum / wsum
                        expected_edge_ratio_val = expected_edge_ratio
                        expected_edge_per_risk_val = expected_edge_per_risk
                        edge_signal = max(-2.0, min(2.0, float(expected_edge_per_risk)))
                        base = 1.0 / (1.0 + math.exp(-3.2 * edge_signal))
                        raise_cap = max(0.02, min(0.75, 0.05 + 0.75 * base))
                        conf = max(0.25, min(1.0, 1.0 - 1.6 * unc))
                        if solver_call_ev is None or solver_raise_ev is None:
                            conf *= 0.80
                        if solver_hint_kind is None:
                            conf *= 0.90
                        raise_cap = max(0.02, min(0.75, raise_cap * (0.55 + 0.45 * conf)))
                        neg_supp = 1.0 / (1.0 + math.exp(-(3.6 * edge_signal)))
                        raise_cap = max(0.01, min(0.75, raise_cap * (0.20 + 0.80 * neg_supp)))
                        if call_edge_ratio is not None:
                            call_supp = 1.0 / (1.0 + math.exp(3.0 * call_edge_ratio))
                            raise_cap = max(0.01, min(0.75, raise_cap * (0.55 + 0.45 * call_supp)))
                        if street in ("FLOP", "TURN", "RIVER") and pot_chips > 0:
                            spr = float(stack_chips) / float(pot_chips) if stack_chips is not None else 5.0
                            pressure = _pressure_index(
                                players_alive=players_alive,
                                spr=spr,
                                wet_score=wet_score,
                                pos_key=pos_key,
                                street=street,
                            )
                            pressure_scale = 0.55 + 0.45 * pressure
                            if pos_key in ("SB", "BB") and street in ("FLOP", "TURN"):
                                pressure_scale *= 0.85
                            if players_alive >= 4:
                                pressure_scale *= max(0.55, 1.0 - 0.08 * max(0, players_alive - 3))
                            # ALLIN 额外软 cap：多人或高 SPR 时进一步限制。
                            if spr >= 6.0 or players_alive > 2:
                                pressure_scale *= 0.85
                                raise_cap = min(raise_cap, 0.45)
                            raise_cap = max(0.01, min(0.70, raise_cap * pressure_scale))
                        edge_ratio_source = expected_edge_ratio_val if expected_edge_ratio_val is not None else best_edge_ratio
                        if edge_ratio_source is not None:
                            edge_ratio_clamped = max(-1.5, min(1.5, float(edge_ratio_source)))
                            margin_sig = 1.0 / (1.0 + math.exp(-4.5 * edge_ratio_clamped))
                            margin_cap = 0.05 + 0.75 * margin_sig
                            conf = max(0.25, min(1.0, 1.0 - 1.4 * unc))
                            margin_cap *= 0.55 + 0.45 * conf
                            spr_val = None
                            if stack_chips is not None and pot_chips not in (None, 0):
                                spr_val = float(stack_chips) / float(pot_chips)
                            if spr_val is not None:
                                margin_cap *= 1.0 / (1.0 + 0.12 * max(0.0, spr_val - 4.0))
                            margin_cap *= 1.0 / (1.0 + 0.12 * max(0, players_alive - 2))
                            margin_cap = max(0.02, min(0.75, margin_cap))
                            raise_cap = margin_cap if raise_cap is None else min(raise_cap, margin_cap)
                        edge_ratio_source = expected_edge_per_risk_val
                        if edge_ratio_source is None:
                            edge_ratio_source = expected_edge_ratio_val if expected_edge_ratio_val is not None else best_edge_ratio
                        if edge_ratio_source is not None:
                            spr_val = None
                            if stack_chips is not None and pot_chips not in (None, 0):
                                spr_val = float(stack_chips) / float(pot_chips)
                            price_val = None
                            if pot_unit is not None:
                                price_val = float(to_call) / max(1.0, float(pot_unit))
                            to_call_bb_val = float(to_call) / max(1.0, float(bb or 1))
                            raise_cap_marginal = _raise_mix_cap_from_edge(
                                float(edge_ratio_source),
                                unc=unc,
                                players_alive=players_alive,
                                spr=spr_val,
                                price=price_val,
                                to_call_bb=to_call_bb_val,
                                pos_key=pos_key,
                                street=street,
                                solver_conf=solver_ev_conf,
                            )
                            raise_cap = raise_cap_marginal
                        if net_delta_vals and street in ("TURN", "RIVER") and pos_key in ("SB", "BB"):
                            pot_scale = max(1.0, float(pot_unit))
                            maxv = max(net_delta_vals)
                            wsum = 0.0
                            esum = 0.0
                            for v in net_delta_vals:
                                w = math.exp(2.6 * ((v - maxv) / pot_scale))
                                wsum += w
                                esum += w * v
                            if wsum > 0:
                                expected_net_delta = esum / wsum
                                if expected_net_delta <= 0:
                                    net_sig = 1.0 / (1.0 + math.exp(-4.0 * (expected_net_delta / pot_scale)))
                                    net_cap = 0.10 + 0.55 * net_sig
                                    net_cap *= 0.80 + 0.20 * max(0.0, min(1.0, 1.0 - unc))
                                    if solver_call_ev is None or solver_raise_ev is None:
                                        net_cap *= 0.90
                                    raise_cap = net_cap if raise_cap is None else min(raise_cap, net_cap)
                if facing_bet and pos_key in ("SB", "BB") and call_ev_ref is not None:
                    if best_edge_value is not None:
                        raise_ev_best = float(call_ev_ref) + float(best_edge_value)
                    elif raise_ev_best_raw is not None:
                        raise_ev_best = float(raise_ev_best_raw)
                    if raise_ev_best is not None:
                        call_sum = sum(w for act, w in weighted_rows if str(act.get("kind")) == "CALL")
                        raise_sum = sum(w for act, w in weighted_rows if str(act.get("kind")) in ("RAISE", "BET", "ALLIN"))
                        if call_sum > 0 and raise_sum > 0:
                            total_def = call_sum + raise_sum
                            current_raise = raise_sum / total_def
                            target = float(ev_raise_share_cap) if ev_raise_share_cap is not None else None
                            soft_cap = 1.0
                            raise_pref = None
                            raise_pref_trace = None
                            if best_edge_ratio is not None and call_edge_ratio is not None:
                                delta_edge = float(best_edge_ratio) - float(call_edge_ratio)
                                raise_pref = 1.0 / (1.0 + math.exp(-3.0 * delta_edge))
                                if street in ("TURN", "RIVER"):
                                    raise_pref = raise_pref ** 2.6
                                raise_pref_trace = raise_pref
                            edge_ratio = (float(raise_ev_best) - float(call_ev_ref)) / max(1.0, float(pot_unit))
                            if target is None:
                                if raise_cap is not None:
                                    target = float(raise_cap)
                                if target is None:
                                    target = 1.0 / (1.0 + math.exp(-3.5 * edge_ratio))
                                if raise_pref is not None:
                                    target = (0.55 * float(target)) + (0.45 * raise_pref)
                                if call_edge_ratio is not None:
                                    call_supp = 1.0 / (1.0 + math.exp(3.0 * call_edge_ratio))
                                    target = float(target) * (0.65 + 0.35 * call_supp)
                                if expected_edge_ratio_val is not None:
                                    ref_edge = expected_edge_per_risk_val if expected_edge_per_risk_val is not None else expected_edge_ratio_val
                                    clamped_edge = max(-2.0, min(2.0, float(ref_edge)))
                                    risk_target = 1.0 / (1.0 + math.exp(-3.2 * clamped_edge))
                                    target = (0.65 * float(target)) + (0.35 * risk_target)
                                    risk_weight = max(0.05, min(1.0, risk_target))
                                    target = float(target) * risk_weight
                                # 额外风险/成本约束：多人、OOP、高 SPR 与 Δrake 需抑制激进上限。
                                if (
                                    solver_call_ev is not None
                                    and solver_raise_ev is not None
                                    and pot_unit is not None
                                    and pot_unit > 0
                                ):
                                    solver_edge_local = (float(solver_raise_ev) - float(solver_call_ev)) / float(pot_unit)
                                    solver_sig = 1.0 / (1.0 + math.exp(-5.0 * solver_edge_local))
                                    solver_cap = 0.05 + 0.65 * solver_sig
                                    target = min(float(target), solver_cap)
                                    if raise_cap is not None:
                                        raise_cap = min(float(raise_cap), solver_cap)
                                    else:
                                        raise_cap = solver_cap
                                    if raise_cap_marginal is not None:
                                        raise_cap_marginal = min(float(raise_cap_marginal), solver_cap)
                                    else:
                                        raise_cap_marginal = solver_cap
                                spr_val = None
                                if stack_chips is not None and pot_chips not in (None, 0):
                                    spr_val = float(stack_chips) / float(pot_chips)
                                risk_penalty = 1.0 / (1.0 + math.exp(1.2 * max(0, players_alive - 2)))
                                if spr_val is not None:
                                    risk_penalty *= 1.0 / (1.0 + 0.18 * max(0.0, spr_val - 4.0))
                                if pos_key in ("SB", "BB"):
                                    risk_penalty *= 0.80
                                # 将 raise 上限收敛到风险惩罚，避免极端抬升。
                                target = float(target) * max(0.15, min(1.0, risk_penalty))
                                soft_cap = 0.65 * max(0.25, risk_penalty)
                                if pos_key in ("SB", "BB") and street in ("TURN", "RIVER"):
                                    price = float(to_call) / max(1.0, float(pot_unit))
                                    price = max(0.0, min(1.0, price))
                                    price_penalty = 1.0 / (1.0 + 2.2 * price)
                                    target *= 0.65 + 0.35 * price_penalty
                                    soft_cap *= 0.75 + 0.25 * price_penalty
                            if raise_pref is not None:
                                target = min(float(target), float(raise_pref))
                            if ev_raise_share_cap is not None:
                                target = min(float(target), float(ev_raise_share_cap))
                                soft_cap = min(float(soft_cap), float(ev_raise_share_cap))
                            if raise_cap is not None:
                                soft_cap = min(soft_cap, float(raise_cap))
                            if pos_key in ("SB", "BB") and street in ("TURN", "RIVER"):
                                net_delta = None
                                if best_edge_act is not None:
                                    net_delta = raise_net_delta_by_id.get(id(best_edge_act))
                                if net_delta is not None:
                                    net_ratio = float(net_delta) / max(1.0, float(pot_unit))
                                    net_sig = 1.0 / (1.0 + math.exp(-4.0 * (net_ratio - 0.01)))
                                    net_cap = 0.05 + 0.70 * net_sig
                                    net_cap *= 0.80 + 0.20 * max(0.0, min(1.0, 1.0 - unc))
                                    soft_cap = min(float(soft_cap), float(net_cap))
                            if pos_key in ("SB", "BB") and street in ("TURN", "RIVER"):
                                price = float(to_call) / max(1.0, float(pot_unit))
                                price = max(0.0, min(1.0, price))
                                price_penalty = 1.0 / (1.0 + 2.2 * price)
                                target *= 0.70 + 0.30 * price_penalty
                                soft_cap *= 0.85 + 0.15 * price_penalty
                                if street == "RIVER":
                                    river_scale = 0.70 + 0.30 * (1.0 / (1.0 + 2.5 * price))
                                    target *= river_scale
                                    soft_cap *= river_scale
                            target = min(target, soft_cap)
                            # Soft-blend target to avoid over-correcting under uncertain estimates.
                            blend_strength = 0.20 + 0.55 * min(1.0, abs(edge_ratio) * 2.0)
                            blend_strength *= max(0.25, 1.0 - unc)
                            blended = (blend_strength * float(target)) + ((1.0 - blend_strength) * current_raise)
                            target_raise = max(0.0, min(0.75, blended))
                            if soft_cap is not None:
                                target_raise = min(float(target_raise), float(soft_cap))
                            if pos_key in ("SB", "BB") and street in ("TURN", "RIVER"):
                                price = float(to_call) / max(1.0, float(pot_unit))
                                price = max(0.0, min(1.5, price))
                                price_penalty = 1.0 / (1.0 + 2.0 * price)
                                gap_sig = 1.0 / (1.0 + math.exp(-3.6 * (edge_ratio - 0.02)))
                                to_call_bb = float(to_call) / max(1.0, float(bb or 1))
                                bb_sig = 1.0 / (1.0 + math.exp(2.2 * (to_call_bb - 1.0)))
                                bb_penalty = 0.45 + 0.55 * bb_sig
                                target_raise *= (0.60 + 0.40 * price_penalty) * (0.65 + 0.35 * gap_sig) * bb_penalty
                                if solver_call_ev is not None and solver_raise_ev is not None:
                                    solver_gap = (float(solver_raise_ev) - float(solver_call_ev)) / max(1.0, float(pot_unit))
                                    solver_sig = 1.0 / (1.0 + math.exp(-4.0 * solver_gap))
                                    target_raise *= 0.35 + 0.65 * solver_sig
                                risk_act = hint_raise_act or best_edge_act
                                raise_risk_prob, raise_risk_conf = _retaliation_raise_prob_for_action(risk_act) if risk_act else (None, None)
                                if raise_risk_prob is not None:
                                    solver_conf = max(0.0, min(1.0, float(solver_ev_conf)))
                                    conf_adj = 0.85 + 0.15 * max(0.0, min(1.0, float(raise_risk_conf or 0.0)))
                                    penalty = min(1.0, raise_risk_prob * (0.20 + 0.80 * (1.0 - solver_conf))) * conf_adj
                                    risk_weight = 0.35 + 0.65 * min(1.0, float(retaliation_weight) * 8.0)
                                    target_raise *= max(0.40, 1.0 - 0.60 * risk_weight * penalty)
                                    soft_cap *= max(0.50, 1.0 - 0.35 * risk_weight * penalty)
                                    if trace_active:
                                        defense_trace.update(
                                            {
                                                "raise_risk_prob_ppm": _ppm(raise_risk_prob, limit=1.0),
                                                "raise_risk_conf_ppm": _ppm(raise_risk_conf, limit=1.0) if raise_risk_conf is not None else None,
                                                "raise_risk_penalty_ppm": _ppm(penalty, limit=1.0),
                                            }
                                        )
                            if current_raise > 0 and current_raise < 1:
                                scale_raise = target_raise / current_raise
                                scale_call = (1.0 - target_raise) / max(1e-6, 1.0 - current_raise)
                                adjusted: list[tuple[dict[str, Any], float]] = []
                                for act, w in weighted_rows:
                                    kind = str(act.get("kind"))
                                    if kind in ("RAISE", "BET", "ALLIN"):
                                        adjusted.append((act, w * scale_raise))
                                    elif kind == "CALL":
                                        adjusted.append((act, w * scale_call))
                                    else:
                                        adjusted.append((act, w))
                                weighted_rows = adjusted
                            if trace_active:
                                defense_trace.update(
                                    {
                                        "trace_schema_id": "defense_trace_v1",
                                        "street": street,
                                        "pos_key": pos_key,
                                        "facing_bet": True,
                                        "to_call_chips": int(to_call),
                                        "pot_chips": int(pot_chips),
                                        "players_alive": int(players_alive) if isinstance(players_alive, int) else None,
                                        "call_ev_chips": _chips(call_ev_ref),
                                        "call_risk_premium_chips": _chips(call_risk_premium),
                                        "raise_ev_chips": _chips(raise_ev_best),
                                        "call_edge_ratio_ppm": _ppm(call_edge_ratio, limit=2.0),
                                        "call_pref_ppm": _ppm(call_pref, limit=1.0),
                                        "low_spr_wet_firewall_ppm": _ppm(low_spr_wet_firewall_strength, limit=1.0),
                                        "spot_policy_spot_id": spot_policy_trace.get("spot_id") if spot_policy_trace is not None else None,
                                        "spot_policy_trace_tag": spot_policy_trace.get("trace_tag") if spot_policy_trace is not None else None,
                                        "turn_focus_support_raise_clamp_ppm": _ppm(turn_focus_support_raise_clamp_strength, limit=1.0),
                                        "best_raise_edge_ratio_ppm": _ppm(best_edge_ratio, limit=2.0),
                                        "raise_cap_ppm": _ppm(raise_cap, limit=1.0),
                                        "raise_cap_marginal_ppm": _ppm(raise_cap_marginal, limit=1.0),
                                        "raise_cap_ev_share_ppm": _ppm(ev_raise_share_cap, limit=1.0),
                                        "raise_pref_ppm": _ppm(raise_pref_trace, limit=1.0),
                                        "defend_target_ppm": _ppm(defend_target, limit=1.0),
                                        "defend_ev_share_ppm": _ppm(defend_ev_share, limit=1.0),
                                        "defend_ev_cap_ppm": _ppm(defend_ev_cap, limit=1.0),
                                        "target_raise_ppm": _ppm(target_raise, limit=1.0),
                                        "current_raise_ppm": _ppm(current_raise, limit=1.0),
                                        "solver_call_ev_chips": _chips(solver_call_ev),
                                        "solver_raise_ev_chips": _chips(solver_raise_ev),
                                        "solver_hint_kind": solver_hint_kind,
                                        "solver_hint_target_chips": solver_hint_target,
                                    }
                                )
                if facing_bet and pos_key in ("SB", "BB") and call_ev_ref is not None:
                    focus_act = hint_raise_act or best_edge_act
                    focus_metrics = None
                    raise_ev_focus = None
                    if focus_act is not None:
                        local_ev = 0.0
                        for _score, _ev, act in score_rows:
                            if act is focus_act:
                                local_ev = float(_ev)
                                break
                        ev_focus = _solver_ev_for_action(focus_act, local_ev)
                        raise_ev_focus = ev_focus
                        focus_metrics = raise_metrics_by_id.get(id(focus_act))
                        if focus_metrics is None:
                            focus_metrics = _raise_edge_metrics(focus_act, ev_focus)
                    if exp_rake_call is not None and call_ev_ref is not None:
                        call_oop_cost = _oop_multi_street_cost(max(1.0, float(to_call)), equity)
                        call_ev_net = float(call_ev_ref) - (float(exp_rake_call) - float(base_rake)) - float(call_oop_cost)
                        if fold_ev_ref is not None and call_ev_net <= float(fold_ev_ref):
                            call_net_dominated = True
                            call_net_dominated = True
                    if focus_metrics is not None:
                        edge_ratio = float(focus_metrics[1])
                        base_target = 1.0 / (1.0 + math.exp(-3.5 * edge_ratio))
                        target_raise = max(0.0, min(0.85, base_target))
                        if raise_cap is not None:
                            target_raise = min(target_raise, float(raise_cap))
                        if call_edge_ratio is not None:
                            delta_edge = edge_ratio - float(call_edge_ratio)
                            raise_pref = 1.0 / (1.0 + math.exp(-3.0 * delta_edge))
                            if street in ("TURN", "RIVER"):
                                raise_pref = raise_pref ** 2.6
                            target_raise = min(target_raise, float(raise_pref))
                        adjusted: list[tuple[dict[str, Any], float]] = []
                        for act, w in weighted_rows:
                            kind = str(act.get("kind"))
                            if kind in ("RAISE", "BET", "ALLIN") and focus_act is not None and act is not focus_act:
                                w *= 0.05
                            adjusted.append((act, w))
                        weighted_rows = adjusted
                        call_sum = sum(w for act, w in weighted_rows if str(act.get("kind")) == "CALL")
                        raise_sum = sum(w for act, w in weighted_rows if str(act.get("kind")) in ("RAISE", "BET", "ALLIN"))
                        if call_sum > 0 and raise_sum > 0:
                            total_def = call_sum + raise_sum
                            current_raise = raise_sum / total_def
                            if pos_key in ("SB", "BB") and street in ("TURN", "RIVER"):
                                price = float(to_call) / max(1.0, float(pot_unit))
                                price = max(0.0, min(1.5, price))
                                price_penalty = 1.0 / (1.0 + 2.0 * price)
                                gap_sig = 1.0 / (1.0 + math.exp(-3.6 * (edge_ratio - 0.02)))
                                to_call_bb = float(to_call) / max(1.0, float(bb or 1))
                                bb_sig = 1.0 / (1.0 + math.exp(2.2 * (to_call_bb - 1.0)))
                                bb_penalty = 0.45 + 0.55 * bb_sig
                                target_raise *= (0.60 + 0.40 * price_penalty) * (0.65 + 0.35 * gap_sig) * bb_penalty
                                if solver_call_ev is not None and solver_raise_ev is not None:
                                    solver_gap = (float(solver_raise_ev) - float(solver_call_ev)) / max(1.0, float(pot_unit))
                                    solver_sig = 1.0 / (1.0 + math.exp(-4.0 * solver_gap))
                                    target_raise *= 0.35 + 0.65 * solver_sig
                            scale_raise = target_raise / max(1e-6, current_raise)
                            scale_call = (1.0 - target_raise) / max(1e-6, 1.0 - current_raise)
                            adjusted = []
                            for act, w in weighted_rows:
                                kind = str(act.get("kind"))
                                if kind in ("RAISE", "BET", "ALLIN"):
                                    adjusted.append((act, w * scale_raise))
                                elif kind == "CALL":
                                    adjusted.append((act, w * scale_call))
                                else:
                                    adjusted.append((act, w))
                            weighted_rows = adjusted
                            if trace_active:
                                defense_trace.update(
                                    {
                                        "trace_schema_id": "defense_trace_v1",
                                        "street": street,
                                        "pos_key": pos_key,
                                        "facing_bet": True,
                                        "to_call_chips": int(to_call),
                                        "pot_chips": int(pot_chips),
                                        "players_alive": int(players_alive) if isinstance(players_alive, int) else None,
                                        "call_ev_chips": _chips(call_ev_ref),
                                        "call_risk_premium_chips": _chips(call_risk_premium),
                                        "raise_ev_chips": _chips(raise_ev_focus),
                                        "call_edge_ratio_ppm": _ppm(call_edge_ratio, limit=2.0),
                                        "call_pref_ppm": _ppm(call_pref, limit=1.0),
                                        "low_spr_wet_firewall_ppm": _ppm(low_spr_wet_firewall_strength, limit=1.0),
                                        "spot_policy_spot_id": spot_policy_trace.get("spot_id") if spot_policy_trace is not None else None,
                                        "spot_policy_trace_tag": spot_policy_trace.get("trace_tag") if spot_policy_trace is not None else None,
                                        "turn_focus_support_raise_clamp_ppm": _ppm(turn_focus_support_raise_clamp_strength, limit=1.0),
                                        "best_raise_edge_ratio_ppm": _ppm(edge_ratio, limit=2.0),
                                        "raise_cap_ppm": _ppm(raise_cap, limit=1.0),
                                        "raise_cap_marginal_ppm": _ppm(raise_cap_marginal, limit=1.0),
                                        "raise_cap_ev_share_ppm": _ppm(ev_raise_share_cap, limit=1.0),
                                        "raise_pref_ppm": _ppm(raise_pref, limit=1.0),
                                        "defend_target_ppm": _ppm(defend_target, limit=1.0),
                                        "defend_ev_share_ppm": _ppm(defend_ev_share, limit=1.0),
                                        "defend_ev_cap_ppm": _ppm(defend_ev_cap, limit=1.0),
                                        "target_raise_ppm": _ppm(target_raise, limit=1.0),
                                        "current_raise_ppm": _ppm(current_raise, limit=1.0),
                                        "solver_call_ev_chips": _chips(solver_call_ev),
                                        "solver_raise_ev_chips": _chips(solver_raise_ev),
                                        "solver_hint_kind": solver_hint_kind,
                                        "solver_hint_target_chips": solver_hint_target,
                                    }
                                )
                    if street == "RIVER" and solver_call_ev is not None and solver_raise_ev is not None and pot_unit > 0:
                        solver_gap = (float(solver_raise_ev) - float(solver_call_ev)) / max(1.0, float(pot_unit))
                        gap_gate = 1.0 / (1.0 + math.exp(-8.0 * (solver_gap - 0.04)))
                        price = float(to_call) / max(1.0, float(pot_unit))
                        price = max(0.0, min(1.5, price))
                        price_pen = 1.0 / (1.0 + 2.0 * price)
                        raise_scale = 0.20 + 0.80 * (gap_gate * (0.60 + 0.40 * price_pen))
                        adjusted: list[tuple[dict[str, Any], float]] = []
                        for act, w in weighted_rows:
                            kind = str(act.get("kind"))
                            if kind in ("RAISE", "BET", "ALLIN"):
                                w *= raise_scale
                            adjusted.append((act, w))
                        weighted_rows = adjusted
                call_sum = 0.0
                raise_sum = 0.0
                if (
                    facing_bet
                    and street == "PREFLOP"
                    and pos_key in ("SB", "BB")
                    and call_ev_ref is not None
                    and fold_ev_ref is not None
                ):
                    call_sum = sum(w for act, w in weighted_rows if str(act.get("kind")) == "CALL")
                    raise_sum = sum(w for act, w in weighted_rows if str(act.get("kind")) in ("RAISE", "BET", "ALLIN"))
                if call_sum > 0 and raise_sum > 0:
                    pot_unit = max(1.0, float(pot_unit))
                    edge = (float(call_ev_ref) - float(fold_ev_ref)) / pot_unit
                    call_floor = 1.0 / (1.0 + math.exp(-4.0 * edge))
                    call_floor = 0.04 + 0.26 * call_floor
                    if street == "PREFLOP" and pos_key in ("SB", "BB"):
                        call_floor = 0.03 + 0.24 * call_floor
                    call_floor = max(0.03, min(0.40, call_floor))
                    raise_ev_best = None
                    for _score, _ev, act in score_rows:
                        if act not in candidates:
                            continue
                        if str(act.get("kind")) in ("RAISE", "BET", "ALLIN"):
                            ev_use = _solver_ev_for_action(act, _ev)
                            if raise_ev_best is None or ev_use > raise_ev_best:
                                raise_ev_best = ev_use
                    raise_sig = None
                    if raise_ev_best is not None and call_ev_ref is not None:
                        raise_adv = (float(raise_ev_best) - float(call_ev_ref)) / pot_unit
                        raise_sig = 1.0 / (1.0 + math.exp(-4.0 * raise_adv))
                        call_floor *= max(0.20, 1.0 - 0.75 * raise_sig)
                        call_floor = max(0.02, call_floor)
                    call_ceiling = 0.75
                    if raise_sig is not None:
                        if street == "PREFLOP" and pos_key in ("SB", "BB"):
                            call_ceiling = 0.20 + 0.35 * (1.0 - raise_sig)
                        else:
                            call_ceiling = 0.30 + 0.40 * (1.0 - raise_sig)
                    call_ceiling = max(call_floor, min(0.80, call_ceiling))
                    current_call = call_sum / max(1e-6, call_sum + raise_sum)
                    if current_call < call_floor:
                        scale_call = call_floor / max(1e-6, current_call)
                        scale_raise = (1.0 - call_floor) / max(1e-6, 1.0 - current_call)
                        adjusted: list[tuple[dict[str, Any], float]] = []
                        for act, w in weighted_rows:
                            kind = str(act.get("kind"))
                            if kind == "CALL":
                                adjusted.append((act, w * scale_call))
                            elif kind in ("RAISE", "BET", "ALLIN"):
                                adjusted.append((act, w * scale_raise))
                            else:
                                adjusted.append((act, w))
                        weighted_rows = adjusted
                    elif current_call > call_ceiling:
                        scale_call = call_ceiling / max(1e-6, current_call)
                        scale_raise = (1.0 - call_ceiling) / max(1e-6, 1.0 - current_call)
                        adjusted = []
                        for act, w in weighted_rows:
                            kind = str(act.get("kind"))
                            if kind == "CALL":
                                adjusted.append((act, w * scale_call))
                            elif kind in ("RAISE", "BET", "ALLIN"):
                                adjusted.append((act, w * scale_raise))
                            else:
                                adjusted.append((act, w))
                        weighted_rows = adjusted
                # Critical bucket rollout: HU, OOP, facing bet on TURN/RIVER with deep SPR.
                rollout_trace: dict[str, Any] | None = None
                rollout_weight = hu_rollout_enable
                if street == "TURN":
                    rollout_weight = hu_rollout_turn_enable
                if (
                    rollout_weight > 0
                    and facing_bet
                    and to_call > 0
                    and pos_key in ("SB", "BB")
                    and street in ("TURN", "RIVER")
                    and players_alive == 2
                    and stack_chips is not None
                    and pot_chips > 0
                ):
                    spr_val = float(stack_chips) / float(pot_chips)
                    pot_unit = max(1.0, float(pot_chips + to_call))
                    price = float(to_call) / pot_unit
                    size_ratio = float(to_call) / max(1.0, float(pot_chips))
                    size_ratio = max(0.0, min(2.0, size_ratio))
                    spr_center = 3.0
                    if street == "TURN":
                        spr_center = 2.5
                    spr_signal = 1.0 / (1.0 + math.exp(-1.4 * (float(spr_val) - spr_center)))
                    size_signal = 1.0 / (1.0 + math.exp(-6.0 * (float(size_ratio) - 0.5)))
                    rollout_gate = (0.35 + 0.65 * spr_signal) * (0.35 + 0.65 * size_signal)
                    rollout_weight = float(rollout_weight) * rollout_gate
                    if rollout_weight >= 0.08:
                        rollout_actions: list[dict[str, Any]] = []
                        for act, _w in weighted_rows:
                            kind = str(act.get("kind"))
                            if kind in ("FOLD", "CALL", "RAISE", "BET", "ALLIN"):
                                rollout_actions.append(act)
                        if len(rollout_actions) >= 2:
                            ev_by_id: dict[int, float] = {}
                            for _score, _ev, act in score_rows:
                                ev_by_id[id(act)] = float(_ev)
                            solver_conf_local = 0.0
                            if solver_call_ev is not None and solver_raise_ev is not None:
                                solver_conf_local = 1.0
                            elif solver_call_ev is not None or solver_raise_ev is not None:
                                solver_conf_local = 0.6
                            rake_factor = 1.0 + 6.0 * rake_rate
                            spr_factor = 0.80 + 0.08 * max(0.0, min(8.0, spr_val - 4.0))
                            oop_factor = 1.08
                            base_cost_by_id: dict[int, float] = {}
                            base_ev_by_id: dict[int, float] = {}
                            cost_scale = 0.75
                            rollout_samples = max(8, int(hu_rollout_samples * (0.80 + 0.90 * rollout_gate)))
                            beta = hu_rollout_beta
                            turn_scale = 1.0
                            if street == "TURN":
                                rollout_samples = max(8, int(rollout_samples * 0.5))
                                beta = hu_rollout_beta * 1.20
                                gap_signal = 0.0
                                if solver_call_ev is not None and solver_raise_ev is not None:
                                    gap_signal = abs(float(solver_raise_ev) - float(solver_call_ev)) / max(1.0, float(pot_unit))
                                gap_signal = max(0.0, min(1.0, gap_signal * 3.0))
                                gap_factor = 1.0 / (1.0 + math.exp(-8.0 * (gap_signal - 0.08)))
                                turn_scale = 0.20 + (0.50 * gap_factor)
                            if street == "RIVER" and facing_bet and pos_key in ("SB", "BB") and players_alive == 2:
                                beta = hu_rollout_beta * 1.45
                            for act in rollout_actions:
                                kind = str(act.get("kind"))
                                target = int(act.get("target_total_commit_chips", actor_commit))
                                risk = max(0, target - actor_commit)
                                risk_unit = float(to_call if kind == "CALL" else max(to_call, risk))
                                size_ratio = min(2.0, risk_unit / max(1.0, pot_unit))
                                exp_rake = _expected_rake_for_action(
                                    action=act,
                                    pot_chips=pot_chips,
                                    actor_commit=actor_commit,
                                    to_call=to_call,
                                    players_alive=players_alive,
                                    street=street,
                                    defend_rate=None,
                                )
                                delta_rake = max(0.0, float(exp_rake) - float(base_rake))
                                base = 0.02 + 0.08 * price + 0.05 * size_ratio
                                if kind in ("RAISE", "BET", "ALLIN"):
                                    base += 0.03 + 0.06 * min(1.0, size_ratio * 1.5)
                                cost = (risk_unit * base * spr_factor * rake_factor * oop_factor) + (delta_rake * (0.35 + 0.25 * price))
                                base_cost_by_id[id(act)] = max(0.0, float(cost)) * cost_scale
                                local_ev = ev_by_id.get(id(act), 0.0)
                                if kind == "CALL" and solver_call_ev is not None:
                                    base_ev_by_id[id(act)] = float(solver_call_ev)
                                elif kind in ("RAISE", "BET", "ALLIN") and solver_raise_ev is not None:
                                    base_ev_by_id[id(act)] = float(solver_raise_ev)
                                else:
                                    base_ev_by_id[id(act)] = _solver_ev_for_action(act, local_ev)
                            # Deterministic RNG seeded by state.
                            seed_salt = int(state_hash[:8], 16) if isinstance(state_hash, str) else 0
                            rng = random.Random(seed ^ seed_salt ^ int(pot_unit) ^ int(to_call << 2))
                            sums: dict[int, float] = {id(a): 0.0 for a in rollout_actions}
                            sums2: dict[int, float] = {id(a): 0.0 for a in rollout_actions}
                            for _ in range(rollout_samples):
                                r = rng.random()
                                style_factor = 1.0
                                if opponent_pool_cdf:
                                    for cutoff, factor, _label in opponent_pool_cdf:
                                        if r <= cutoff:
                                            style_factor = float(factor)
                                            break
                                for act in rollout_actions:
                                    base_ev = base_ev_by_id.get(id(act), 0.0)
                                    penalty = base_cost_by_id.get(id(act), 0.0) * style_factor
                                    ev_sample = float(base_ev) - float(penalty)
                                    sums[id(act)] += ev_sample
                                    sums2[id(act)] += ev_sample * ev_sample
                            roll_stats: dict[int, tuple[float, float]] = {}
                            for act in rollout_actions:
                                n = max(1, rollout_samples)
                                mean = sums[id(act)] / float(n)
                                var = max(0.0, (sums2[id(act)] / float(n)) - (mean * mean))
                                std = math.sqrt(var)
                                roll_stats[id(act)] = (mean, std)
                            scores = {
                                aid: (mean - beta * std)
                                for aid, (mean, std) in roll_stats.items()
                            }
                            # Confidence based on gap vs variance.
                            ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                            best_id, best_score = ordered[0]
                            second_score = ordered[1][1] if len(ordered) > 1 else best_score
                            best_std = roll_stats[best_id][1]
                            second_std = roll_stats[ordered[1][0]][1] if len(ordered) > 1 else best_std
                            gap = float(best_score) - float(second_score)
                            std_ref = max(1e-6, float(best_std) + float(second_std))
                            gap_ratio = gap / std_ref
                            conf = 1.0 / (1.0 + math.exp(-(1.2 * gap_ratio - 0.1)))
                            conf *= max(0.30, 1.0 - unc)
                            conf *= turn_scale
                            blend = max(0.0, min(1.0, float(rollout_weight) * conf * 1.2))
                            if street == "RIVER" and facing_bet and pos_key in ("SB", "BB") and players_alive == 2:
                                blend = max(blend, min(1.0, float(rollout_weight) * (0.60 + 0.40 * conf)))
                            if blend > 0:
                                max_score = max(scores.values())
                                temp = 0.10 + 0.35 * max(0.0, min(1.0, unc))
                                denom = 0.0
                                rollout_weights: dict[int, float] = {}
                                for aid, score in scores.items():
                                    score_norm = (float(score) - float(max_score)) / max(1e-6, float(pot_unit))
                                    w = math.exp(score_norm / max(1e-6, temp))
                                    rollout_weights[aid] = w
                                    denom += w
                                if denom > 0:
                                    for aid in list(rollout_weights.keys()):
                                        rollout_weights[aid] /= denom
                                if (
                                    street == "RIVER"
                                    and facing_bet
                                    and pos_key in ("SB", "BB")
                                    and players_alive == 2
                                ):
                                    override = max(0.0, min(1.0, 0.55 + 0.45 * float(conf)))
                                    for aid in list(rollout_weights.keys()):
                                        roll_w = rollout_weights[aid]
                                        if aid == best_id:
                                            roll_w = (1.0 - override) * roll_w + override
                                        else:
                                            roll_w = (1.0 - override) * roll_w
                                        rollout_weights[aid] = roll_w
                                base_total = sum(w for _act, w in weighted_rows)
                                adjusted_roll: list[tuple[dict[str, Any], float]] = []
                                for act, w in weighted_rows:
                                    roll_w = rollout_weights.get(id(act))
                                    if roll_w is not None:
                                        w = (1.0 - blend) * w + (blend * roll_w * base_total)
                                    adjusted_roll.append((act, w))
                                weighted_rows = adjusted_roll
                                rollout_trace = {
                                    "rollout_active": True,
                                    "rollout_samples": int(rollout_samples),
                                    "rollout_street": str(street),
                                    "rollout_gate_ppm": _ppm(rollout_gate, limit=1.0),
                                    "rollout_spr_ppm": _ppm(spr_val, limit=10.0),
                                    "rollout_size_ratio_ppm": _ppm(size_ratio, limit=2.0),
                                    "rollout_blend_ppm": _ppm(blend, limit=1.0),
                                    "rollout_best_kind": next(
                                        (str(a.get("kind")) for a in rollout_actions if id(a) == best_id),
                                        None,
                                    ),
                                    "rollout_best_score_ppm": _ppm(best_score / max(1.0, float(pot_unit)), limit=5.0),
                                    "rollout_best_std_ppm": _ppm(best_std / max(1.0, float(pot_unit)), limit=5.0),
                                }
                total_weight = sum(w for _act, w in weighted_rows)
                if total_weight > 0:
                    rnd_unit = _rng_pct(f"def_mix2:{state_hash}:{street}:{pot_chips}:{to_call}:{pos_key}") / 10000.0
                    acc = 0.0
                    for act, w in weighted_rows:
                        acc += w / total_weight
                        if rnd_unit <= acc:
                            chosen_local = act
                            break
                if rollout_trace and trace_active:
                    defense_trace.update(rollout_trace)
            weight_source = None
            if chosen_local is None and prior_weights is not None:
                if best >= 0 or (min_ev_for_priors is not None and best >= float(min_ev_for_priors)):
                    weight_source = "prior"
            elif chosen_local is None and best >= 0 and entry is not None:
                weight_source = "mw"
            if chosen_local is None and weight_source is not None:
                weights: list[int] = []
                total = 0
                candidate_pairs = [(score, ev, act) for score, ev, act in score_rows if act in candidates]
                for score, ev, act in candidate_pairs:
                    if slack <= 0.0:
                        closeness = 1.0
                    else:
                        closeness = max(0.0, 1.0 - ((best - score) / max(1e-6, slack)))
                    base = max(0, int(closeness * 10000))
                    kind = str(act.get("kind"))
                    if weight_source == "prior":
                        w = int(prior_weights.get(kind, 0)) if prior_weights else 0
                    else:
                        w = _mw_prior_weight(entry, action_kind=kind, facing_bet=facing_bet)
                    base = (base * max(0, w)) // 10000
                    weights.append(base)
                    total += base
                if total > 0:
                    rnd_unit = _rng_pct(f"mw_ev:{state_hash}:{players_alive}:{pot_chips}:{to_call}") / 10000.0
                    if safe_exploit_max > 0:
                        mix = max(0.0, min(0.20, safe_exploit_max))
                        n = len(weights)
                        uniform = 1.0 / max(1, n)
                        probs = [(w / total) if total > 0 else 0.0 for w in weights]
                        probs = [(1.0 - mix) * uniform + mix * p for p in probs]
                        total_prob = sum(probs)
                        acc = 0.0
                        for idx, act in enumerate([a for _, _, a in candidate_pairs]):
                            acc += (probs[idx] / total_prob) if total_prob > 0 else uniform
                            if rnd_unit < acc:
                                chosen_local = act
                                break
                    else:
                        rnd = _rng_pct(f"mw_ev:{state_hash}:{players_alive}:{pot_chips}:{to_call}") % total
                        acc = 0
                        for idx, act in enumerate([a for _, _, a in candidate_pairs]):
                            acc += weights[idx]
                            if rnd < acc:
                                chosen_local = act
                                break
            if chosen_local is None:
                chosen_local = min(
                    candidates,
                    key=lambda a: (
                        int(a.get("target_total_commit_chips", actor_commit)),
                        _deterministic_rank(a, desired=actor_commit, state_hash=state_hash),
                    ),
                )
            return chosen_local

        chosen = _select_from(score_pairs)
        if chosen is not None and facing_bet and to_call > 0 and street is not None and pos_key is not None:
            _record_defense(street, pos_key, str(chosen.get("kind")))
        if chosen is not None and (adaptive_trace or (trace_active and defense_trace)):
            action_out = dict(chosen)
            if trace_active and defense_trace:
                defense_trace["chosen_kind"] = action_out.get("kind")
                defense_trace["chosen_target_chips"] = action_out.get("target_total_commit_chips")
            if adaptive_trace:
                defense_trace.update(adaptive_trace)
            action_out["policy_trace"] = defense_trace if defense_trace else adaptive_trace
            return action_out
        return chosen

    def _raise_value_ok_for_action(
        *,
        action: dict[str, Any],
        equity_strength: float | None,
        pot_chips: int,
        actor_commit: int,
        to_call: int,
        players_alive: int,
        street: str | None,
    ) -> bool:
        if equity_strength is None or street not in ("FLOP", "TURN", "RIVER"):
            return False
        kind = str(action.get("kind"))
        if kind not in ("RAISE", "BET", "ALLIN"):
            return True
        target = int(action.get("target_total_commit_chips", actor_commit))
        risk = max(0, target - actor_commit)
        if risk <= 0:
            return False
        pot_base = float(pot_chips)
        bet_size = float(risk)
        rake_base = estimate_rake(
            pot_after=float(pot_base + bet_size),
            street=street,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )
        denom = max(1.0, float(pot_base + bet_size - rake_base))
        defend_freq = max(0.0, min(1.0, float(pot_base) / denom))
        opponents = max(1, players_alive - 1)
        exp_callers = defend_freq * opponents
        pot_after = pot_base + bet_size * (1.0 + exp_callers)
        rake_after = estimate_rake(
            pot_after=float(pot_after),
            street=street,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )
        pot_after_rake = max(1.0, pot_after - rake_after)
        value_floor = min(0.95, bet_size / pot_after_rake + 0.04 * exp_callers)
        return float(equity_strength) >= value_floor

    def _defend_target_rate(
        *,
        to_call: int,
        pot_chips: int,
        players_alive: int,
        pos_key: str,
        spr: float,
        wet_score: int,
        street: str | None,
        uncertainty: float | None,
    ) -> float:
        if to_call <= 0:
            return 0.0
        pot_base = max(1, pot_chips)
        mdf = pot_base / max(1.0, float(pot_base + to_call))
        defenders = max(1, players_alive - 1)
        if defenders <= 1:
            mdf_adj = mdf
        else:
            mdf_adj = 1.0 - (1.0 - mdf) ** (1.0 / defenders)
        pot_after = pot_base + to_call
        rake_est = estimate_rake(
            pot_after=float(pot_after),
            street=street,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )
        rake_frac = float(rake_est) / max(1.0, float(pot_after))
        target = mdf_adj * max(0.0, 1.0 - rake_frac)
        if pos_key in ("SB", "BB"):
            oop_discount = 0.04 + 0.02 * max(0, players_alive - 2)
            if spr >= 4.0:
                oop_discount += 0.03
            if wet_score >= 2:
                oop_discount += 0.02
            if street in ("TURN", "RIVER"):
                oop_discount += 0.02
            if uncertainty is not None:
                oop_discount += 0.05 * max(0.0, min(1.0, float(uncertainty)))
            target *= max(0.60, 1.0 - oop_discount)
        if (
            safe_exploit_max > 0
            and street in ("FLOP", "TURN", "RIVER")
            and pot_base > 0
            and to_call > 0
        ):
            ratio = float(to_call) / float(pot_base)
            size_bucket = _size_bucket_for_ratio(ratio)
            spot = "HU" if players_alive <= 2 else "MW"
            stats = opp_defense_state.get((str(street), size_bucket, spot))
            if stats and stats.get("facing", 0) > 0:
                prior_strength = 8.0
                base_rate = max(0.0, min(1.0, float(mdf_adj)))
                post_defend = float(stats.get("defend", 0) or 0.0) + prior_strength * base_rate
                post_facing = float(stats.get("facing", 0) or 0.0) + prior_strength
                obs_rate = post_defend / max(1.0, post_facing)
                conf = float(stats.get("facing", 0) or 0.0) / max(1.0, post_facing + prior_strength)
                delta = (obs_rate - base_rate) * conf
                max_shift = min(0.08, float(safe_exploit_max) * 0.8)
                shift = max(-max_shift, min(max_shift, float(delta)))
                target *= max(0.75, min(1.25, 1.0 + shift))
        if facing_low_price_defend_boost is not None and street in ("TURN", "RIVER"):
            price = float(to_call) / max(1.0, float(pot_base + to_call))
            if facing_low_price_threshold is not None and price <= facing_low_price_threshold:
                target *= facing_low_price_defend_boost
        return max(0.01, min(0.99, target))

    def _preflop_defend_target_rate(
        *,
        to_call: int,
        pot_chips: int,
        players_alive: int,
        pos_key: str,
    ) -> float:
        if to_call <= 0:
            return 0.0
        pot_base = max(1, pot_chips)
        mdf = pot_base / max(1.0, float(pot_base + to_call))
        mw_penalty = 1.0 / (1.0 + 0.02 * max(0, players_alive - 2))
        mdf_adj = mdf * mw_penalty
        if pos_key in ("SB", "BB"):
            tighten = preflop_defend_tighten * (0.18 + 0.02 * max(0, players_alive - 2))
            tighten = max(0.0, min(0.18, tighten))
            rake_adj = min(0.10, rake_rate * 0.9)
            base_target = mdf_adj * max(0.0, 1.0 - tighten - rake_adj)
        else:
            tighten = preflop_defend_tighten * (0.5 + 0.10 * max(0, players_alive - 2))
            if players_alive >= 5:
                tighten += 0.03 * max(0, players_alive - 4)
            tighten = max(0.0, min(0.60, tighten))
            rake_adj = min(0.22, rake_rate * 1.6)
            base_target = mdf_adj * max(0.0, 1.0 - tighten - rake_adj)
        # 防止过低，留出 call 保护线；防止过高，避免过松。
        floor = 0.06 if pos_key in ("SB", "BB") else 0.08
        cap = 0.75 if pos_key in ("SB", "BB") else 0.82
        return max(floor, min(cap, base_target))

    def _preflop_prior_gate(
        *,
        legal_actions: list[dict[str, Any]],
        prior_weights: dict[str, int] | None,
        state_hash: str | None,
        to_call: int,
        pot_chips: int,
        call_ev: float | None = None,
        raise_ev: float | None = None,
    ) -> list[dict[str, Any]]:
        if not legal_actions or not prior_weights:
            return legal_actions
        raise_actions = [a for a in legal_actions if str(a.get("kind")) in ("RAISE", "BET", "ALLIN")]
        call_actions = [a for a in legal_actions if str(a.get("kind")) == "CALL"]
        fold_actions = [a for a in legal_actions if str(a.get("kind")) in ("FOLD", "CHECK")]
        if not (raise_actions or call_actions or fold_actions):
            return legal_actions
        raise_w = int(prior_weights.get("RAISE", 0) or 0) + int(prior_weights.get("BET", 0) or 0) + int(prior_weights.get("ALLIN", 0) or 0)
        call_w = int(prior_weights.get("CALL", 0) or 0)
        fold_w = int(prior_weights.get("FOLD", 0) or 0) + int(prior_weights.get("CHECK", 0) or 0)
        if call_ev is not None and raise_ev is not None and (raise_w > 0 or call_w > 0):
            pot_unit = max(1.0, float(pot_chips + to_call))
            edge = (float(raise_ev) - float(call_ev)) / pot_unit
            edge = max(-2.0, min(2.0, edge))
            raise_boost = 1.0 / (1.0 + math.exp(-4.0 * edge))
            call_boost = 1.0 / (1.0 + math.exp(4.0 * edge))
            raise_scale = 0.55 + 0.45 * raise_boost
            call_scale = 0.55 + 0.45 * call_boost
            if raise_w > 0:
                raise_w = max(1, int(float(raise_w) * raise_scale))
            if call_w > 0:
                call_w = max(1, int(float(call_w) * call_scale))
        weights = []
        buckets: list[tuple[str, int, list[dict[str, Any]]]] = []
        if raise_actions and raise_w > 0:
            buckets.append(("RAISE", raise_w, raise_actions))
            weights.append(raise_w)
        if call_actions and call_w > 0:
            buckets.append(("CALL", call_w, call_actions))
            weights.append(call_w)
        if fold_actions and fold_w > 0:
            buckets.append(("FOLD", fold_w, fold_actions))
            weights.append(fold_w)
        if not buckets:
            # Fall back: choose any available bucket deterministically.
            if raise_actions:
                return raise_actions
            if call_actions:
                return call_actions
            return fold_actions
        total = sum(weights)
        if total <= 0:
            return legal_actions
        r = (_rng_pct(f"pf_prior_gate:{state_hash}:{seat_id}:{to_call}") / 10000.0) if state_hash is not None else 0.0
        if safe_exploit_max > 0 and r < safe_exploit_max:
            return legal_actions
        if safe_exploit_max > 0:
            r = (r - safe_exploit_max) / max(1e-6, 1.0 - safe_exploit_max)
        acc = 0.0
        for _label, w, actions in buckets:
            acc += w / total
            if r <= acc:
                return actions
        # Fallback to highest-weight bucket.
        buckets.sort(key=lambda x: x[1], reverse=True)
        return buckets[0][2]

    def _postflop_prior_weights(
        *,
        to_call: int,
        pot_chips: int,
        pos_key: str,
        prev_aggressor: int | None,
        spr: float,
        board_texture: tuple[str, str] | None,
        players_alive: int,
        street: str | None,
        uncertainty: float | None = None,
    ) -> dict[str, int]:
        wet_score = _board_wet_score(board_texture=board_texture, street=street)
        pot_base = max(1, pot_chips)
        pressure = _pressure_index(
            players_alive=players_alive,
            spr=spr,
            wet_score=wet_score,
            pos_key=pos_key,
            street=street,
        )
        if to_call <= 0:
            bet_w = 0.28
            if prev_aggressor == seat_id:
                bet_w += 0.10
            if pos_key in ("BU", "OTHERS"):
                bet_w += 0.05
            if spr < 3:
                bet_w += 0.05
            if spr > 7:
                bet_w -= 0.05
            if players_alive >= 3:
                bet_w -= 0.04
            if wet_score >= 3:
                bet_w -= 0.08
            elif wet_score == 2:
                bet_w -= 0.05
            elif wet_score == 1:
                bet_w -= 0.02
            elif wet_score == 0 and board_texture is not None:
                bet_w += 0.05
            if spr > 8 and wet_score >= 2:
                bet_w -= 0.02
            bet_w += 0.12 * pressure
            bet_w = max(0.10, min(0.60, bet_w))
            check_w = max(0.0, 1.0 - bet_w)
            return {
                "BET": int(bet_w * 10000),
                "RAISE": int(bet_w * 10000),
                "CHECK": int(check_w * 10000),
            }
        price = to_call / max(pot_base + to_call, 1)
        defend_target = _defend_target_rate(
            to_call=to_call,
            pot_chips=pot_chips,
            players_alive=players_alive,
            pos_key=pos_key,
            spr=spr,
            wet_score=wet_score,
            street=street,
            uncertainty=uncertainty,
        )
        unc = max(0.0, float(uncertainty or 0.0))

        raise_share = 0.14 + 0.20 * pressure
        if prev_aggressor == seat_id:
            raise_share += 0.03
        if wet_score >= 2:
            raise_share -= 0.03
        if players_alive >= 3:
            raise_share -= 0.02
        if pos_key in ("BU", "OTHERS"):
            raise_share += 0.02
        else:
            raise_share -= 0.02
        raise_share *= max(0.55, 1.10 - 1.30 * price)
        raise_share -= 0.35 * min(0.6, unc)
        raise_share = max(0.05, min(0.30, raise_share))

        if street in ("TURN", "RIVER"):
            low_spr_threshold = float(params.get("facing_low_spr_threshold_bp", 200)) / 100.0
            low_spr_threshold = max(0.5, min(10.0, low_spr_threshold))
            if spr <= low_spr_threshold:
                defend_scale = float(params.get("facing_low_spr_defend_scale_bp", 10000)) / 10000.0
                defend_scale = max(0.30, min(1.00, defend_scale))
                defend_target *= defend_scale
                raise_cap_bp = params.get("facing_low_spr_raise_share_cap_bp")
                if raise_cap_bp is not None:
                    raise_cap = max(0.01, min(0.30, float(raise_cap_bp) / 10000.0))
                    raise_share = min(raise_share, raise_cap)
            if facing_high_price_threshold is not None:
                scale = None
                if (
                    facing_high_price_raise_scale2 is not None
                    and facing_high_price_threshold2 is not None
                    and price >= facing_high_price_threshold2
                ):
                    scale = facing_high_price_raise_scale2
                elif facing_high_price_raise_scale is not None and price >= facing_high_price_threshold:
                    scale = facing_high_price_raise_scale
                if scale is not None:
                    raise_share *= scale
                if facing_high_price_raise_cap is not None:
                    cap = None
                    if (
                        facing_high_price_raise_cap2 is not None
                        and facing_high_price_threshold2 is not None
                        and price >= facing_high_price_threshold2
                    ):
                        cap = facing_high_price_raise_cap2
                    elif price >= facing_high_price_threshold:
                        cap = facing_high_price_raise_cap
                    if cap is not None:
                        raise_share = min(raise_share, cap)
                # Harden stressed high-price branches by converting marginal raises
                # into calls/folds in wet low-SPR multiway spots.
                if (
                    players_alive >= 3
                    and wet_score >= 2
                    and price >= facing_high_price_threshold
                    and spr <= (low_spr_threshold + 1.0)
                ):
                    # Shrink total defend share first so repeated high-price
                    # branches create an observable fold/call shift instead of
                    # only reassigning marginal defense between call and raise.
                    price_anchor = float(facing_high_price_threshold)
                    price_excess = max(
                        0.0,
                        min(1.0, (price - price_anchor) / max(0.05, 1.0 - price_anchor)),
                    )
                    wet_excess = max(0.0, min(1.0, (float(wet_score) - 2.0) / 2.0))
                    spr_pressure = max(
                        0.0,
                        min(
                            1.0,
                            ((low_spr_threshold + 1.0) - spr)
                            / max(0.5, low_spr_threshold + 0.5),
                        ),
                    )
                    defend_clamp_strength = max(
                        0.0,
                        min(
                            1.0,
                            (0.45 * price_excess)
                            + (0.30 * wet_excess)
                            + (0.25 * spr_pressure),
                        ),
                    )
                    defend_scale = 0.90 - (0.12 * defend_clamp_strength)
                    defend_cap = 0.60 - (0.10 * defend_clamp_strength)
                    if street == "RIVER":
                        defend_scale -= 0.05
                        defend_cap -= 0.04
                    if (
                        facing_high_price_threshold2 is not None
                        and price >= facing_high_price_threshold2
                    ):
                        defend_scale -= 0.05
                        defend_cap -= 0.05
                    defend_scale = max(0.62, min(0.90, defend_scale))
                    defend_cap = max(0.28, min(0.60, defend_cap))
                    defend_target = min(defend_target * defend_scale, defend_cap)
                    hard_cap = 0.08 if street == "TURN" else 0.05
                    hard_scale = 0.58 if street == "TURN" else 0.42
                    if (
                        facing_high_price_threshold2 is not None
                        and price >= facing_high_price_threshold2
                    ):
                        hard_cap = min(hard_cap, 0.06 if street == "TURN" else 0.04)
                        if street == "RIVER":
                            defend_target *= 0.92
                    raise_share = min(raise_share * hard_scale, hard_cap)

        raise_w = defend_target * raise_share
        call_w = max(0.0, defend_target - raise_w)
        raise_w = max(0.02, min(0.25, raise_w))
        call_w = max(0.05, min(0.70, call_w))
        fold_w = max(0.0, 1.0 - call_w - raise_w)
        return {
            "CALL": int(call_w * 10000),
            "RAISE": int(raise_w * 10000),
            "BET": int(raise_w * 10000),
            "FOLD": int(fold_w * 10000),
        }

    def _smallest_of_kind(kind: str) -> dict[str, Any] | None:
        candidates = [a for a in legal_actions if a.get("kind") == kind]
        if not candidates:
            return None
        return min(candidates, key=lambda a: int(a.get("target_total_commit_chips", 0)))

    def _board_wet_score(*, board_texture: tuple[str, str] | None, street: str | None) -> int:
        score = 0
        if board_texture is not None:
            suit_tex, rank_tex = board_texture
            if suit_tex == "monotone":
                score += 2
            elif suit_tex == "two-tone":
                score += 1
            if rank_tex == "connected":
                score += 2
            elif rank_tex == "semi-connected":
                score += 1
            elif rank_tex == "paired":
                score += 1
        if street == "TURN":
            score = max(0, score - 1)
        elif street == "RIVER":
            score = max(0, score - 2)
        return score

    def _equity_realization_multiplier(
        *,
        players_alive: int,
        pos_key: str,
        prev_aggressor: int | None,
        street_raise_ct: int,
        spr: float,
        board_texture: tuple[str, str] | None,
        street: str | None,
    ) -> float:
        realization = 1.0 - 0.04 * max(0, players_alive - 2)
        if pos_key in ("SB", "BB"):
            realization -= 0.05
        if prev_aggressor == seat_id:
            realization += 0.03
        if street_raise_ct >= 1:
            realization -= 0.02
        wet_score = _board_wet_score(board_texture=board_texture, street=street)
        if wet_score >= 3:
            realization -= 0.05
        elif wet_score == 2:
            realization -= 0.03
        elif wet_score == 1:
            realization -= 0.015
        elif wet_score == 0 and board_texture is not None:
            realization += 0.02
        if spr > 7 and wet_score >= 2:
            realization -= 0.02
        if players_alive >= 4 and wet_score >= 2:
            realization -= 0.02
        return max(0.60, min(1.05, realization))

    def _equity_uncertainty_for(
        *,
        equity_val: float | None,
        samples: int | None,
        players_alive: int,
        board_texture: tuple[str, str] | None,
        street: str | None,
    ) -> float | None:
        if equity_val is None or samples is None:
            return None
        wet_score = _board_wet_score(board_texture=board_texture, street=street)
        return equity_uncertainty(
            equity=equity_val,
            samples=samples,
            players_alive=players_alive,
            wet_score=wet_score,
        )

    def _pressure_index(
        *,
        players_alive: int,
        spr: float,
        wet_score: int,
        pos_key: str,
        street: str | None,
    ) -> float:
        pressure = 1.0 / (1.0 + 0.5 * max(0, players_alive - 2))
        if wet_score >= 3:
            pressure *= 0.50
        elif wet_score == 2:
            pressure *= 0.70
        elif wet_score == 1:
            pressure *= 0.85
        if spr <= 2:
            spr_factor = 1.0
        elif spr <= 4:
            spr_factor = 0.8
        elif spr <= 7:
            spr_factor = 0.6
        else:
            spr_factor = 0.4
        pressure *= spr_factor
        if pos_key in ("SB", "BB"):
            pressure *= 0.9
        if street == "RIVER":
            pressure *= 0.8
        return max(0.0, min(1.0, pressure))

    def _ppm_ratio(value_ppm: int | None) -> float | None:
        if value_ppm is None:
            return None
        return float(value_ppm) / 1_000_000.0

    def _select_mw_entry(
        *,
        entries: list[dict[str, Any]],
        rung_id: str | None,
        players_alive: int,
        street: str | None,
        facing_bet: bool,
        spr: float | None,
    ) -> dict[str, Any] | None:
        for ent in entries:
            if rung_id is not None and ent.get("rung_id") != rung_id:
                continue
            mn = ent.get("min_players")
            mx = ent.get("max_players")
            if mn is not None and players_alive < mn:
                continue
            if mx is not None and players_alive > mx:
                continue
            facing = ent.get("facing_bet")
            if facing is not None and facing != facing_bet:
                continue
            streets = ent.get("streets")
            if streets is not None and street is not None and street not in streets and "ANY" not in streets:
                continue
            spr_max_ppm = ent.get("spr_max_ppm")
            if spr_max_ppm is not None and spr is not None and spr > _ppm_ratio(spr_max_ppm):
                continue
            return ent
        return None

    def _mw_action_from_entry(
        ent: dict[str, Any] | None,
        *,
        facing_bet: bool,
        players_alive: int,
        pot_chips: int,
        to_call: int,
        actor_commit: int,
        actor_stack: int,
        call_target: int,
        spr: float | None,
        state_hash: str | None,
        legal_actions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if ent is None:
            return None
        # Optional probability-driven fields (basis points)
        fold_prob = ent.get("fold_prob_bp")
        call_prob = ent.get("call_prob_bp")
        raise_prob = ent.get("raise_prob_bp")
        bet_prob = ent.get("bet_prob_bp")
        cbet_prob = ent.get("cbet_prob_bp")

        call_over_pot = _ppm_ratio(ent.get("call_over_pot_ppm"))
        call_over_stack = _ppm_ratio(ent.get("call_over_stack_ppm"))
        raise_freq = ent.get("raise_freq_bp") or 0
        bet_freq = ent.get("bet_freq_bp") or 0
        raise_rank = max(0, int(ent.get("raise_rank") or 0))
        bet_rank = max(0, int(ent.get("bet_rank") or 0))

        stack_total = actor_commit + actor_stack
        pot_base = pot_chips if pot_chips > 0 else bb
        if pot_base <= 0:
            pot_base = bb or 1

        # Probability-first branch to avoid ad-hoc阈值
        if fold_prob is not None or call_prob is not None or raise_prob is not None or bet_prob is not None or cbet_prob is not None:
            rnd = _rng_pct(f"mw_prob:{state_hash}:{players_alive}:{pot_chips}:{to_call}") % 10000
            if facing_bet:
                cursor = 0
                fp = int(fold_prob or 0)
                rp = int(raise_prob or 0)
                cp = int(call_prob or 0)
                if rnd < fp:
                    fold_act = _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
                    if fold_act:
                        return fold_act
                cursor += fp
                if rnd < cursor + rp:
                    raise_candidates = [a for a in legal_actions if a.get("kind") in ("RAISE", "BET")]
                    raise_candidates.sort(key=lambda a: int(a.get("target_total_commit_chips", 0)))
                    if raise_candidates:
                        return raise_candidates[min(raise_rank, len(raise_candidates) - 1)]
                cursor += rp
                if rnd < cursor + cp:
                    call_act = _pick_nearest_action(legal_actions, kind="CALL", target=call_target)
                    if call_act:
                        return call_act
                # fallback
                fold_act = _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
                if fold_act:
                    return fold_act
                call_act = _pick_nearest_action(legal_actions, kind="CALL", target=call_target)
                if call_act:
                    return call_act
            else:
                bp = cbet_prob if cbet_prob is not None else bet_prob
                if bp is not None and rnd < int(bp):
                    bet_candidates = [a for a in legal_actions if a.get("kind") in ("BET", "RAISE")]
                    bet_candidates.sort(key=lambda a: int(a.get("target_total_commit_chips", 0)))
                    if bet_candidates:
                        return bet_candidates[min(bet_rank, len(bet_candidates) - 1)]
                check_act = _pick_nearest_action(legal_actions, kind="CHECK", target=actor_commit)
                if check_act:
                    return check_act
                call_act = _pick_nearest_action(legal_actions, kind="CALL", target=call_target)
                if call_act:
                    return call_act
                fold_act = _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
                if fold_act:
                    return fold_act
            return None

        # Fallback: price-based heuristics
        if facing_bet:
            # Hard guards to avoid clearly dominated calls, but allow price-taking multiway.
            if stack_total > 0 and to_call >= stack_total:
                fold = _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
                if fold:
                    return fold
            # Ultra-tight guard when 5+ 人：避免高价格挤出。
            bb_local = bb or pot_base
            if players_alive >= 5:
                hard_cap = max(bb_local * 3, int(stack_total * 0.2))
                if to_call >= hard_cap:
                    fold = _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
                    if fold:
                        return fold
            ratio_pot = to_call / pot_base if pot_base > 0 else 99.0
            ratio_stack = to_call / stack_total if stack_total > 0 else 0.0
            # Price-based auto-folds (avoid rake cap sink):
            limit_ratio_pot = 0.45 if players_alive <= 4 else 0.35
            limit_ratio_stack = 0.30 if players_alive <= 4 else 0.20
            if ratio_pot > limit_ratio_pot or ratio_stack > limit_ratio_stack:
                fold = _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
                if fold:
                    return fold
            if (call_over_pot is not None and ratio_pot > call_over_pot) or (call_over_stack is not None and ratio_stack > call_over_stack):
                fold = _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
                if fold:
                    return fold
            if pot_base > 0 and to_call > 0.8 * pot_base:
                fold = _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
                if fold:
                    return fold
            # Aggression floor: SPR 1-4.5 & to_call <=0.45 pot → 65% raise
            if spr is not None and 0.8 <= spr <= 4.5 and pot_base > 0 and to_call <= 0.45 * pot_base:
                raise_candidates = [a for a in legal_actions if a.get("kind") in ("RAISE", "BET")]
                raise_candidates.sort(key=lambda a: int(a.get("target_total_commit_chips", 0)))
                if raise_candidates:
                    rnd = _rng_pct(f"mw_floor_raise:{state_hash}:{players_alive}:{to_call}") % 100
                    if rnd < 65:
                        idx = min(max(raise_rank, 1 if len(raise_candidates) > 1 else 0), len(raise_candidates) - 1)
                        return raise_candidates[idx]
            call_act = _pick_nearest_action(legal_actions, kind="CALL", target=call_target)
            if call_act is None:
                call_act = _pick_nearest_action(legal_actions, kind="CHECK", target=actor_commit)
            # additional proactive raise when facing small bet
            if raise_candidates := [a for a in legal_actions if a.get("kind") in ("RAISE", "BET")]:
                raise_candidates.sort(key=lambda a: int(a.get("target_total_commit_chips", 0)))
                if pot_base > 0 and to_call <= 0.5 * pot_base:
                    rnd = _rng_pct(f"mw_raise_extra:{state_hash}:{players_alive}:{to_call}") % 100
                    if rnd < 55:
                        idx = min(max(raise_rank, 0), len(raise_candidates) - 1)
                        return raise_candidates[idx]
            if raise_freq > 0:
                raise_candidates = [a for a in legal_actions if a.get("kind") in ("RAISE", "BET")]
                raise_candidates.sort(key=lambda a: int(a.get("target_total_commit_chips", 0)))
                if raise_candidates:
                    pick_idx = min(raise_rank, len(raise_candidates) - 1)
                    rnd = _rng_pct(f"mw_raise:{state_hash}:{players_alive}:{to_call}") % 10000
                    if rnd < raise_freq:
                        return raise_candidates[pick_idx]
            if call_act:
                return call_act
            return _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
        else:
            check_act = _pick_nearest_action(legal_actions, kind="CHECK", target=actor_commit)
            bet_candidates = [a for a in legal_actions if a.get("kind") in ("BET", "RAISE")]
            bet_candidates.sort(key=lambda a: int(a.get("target_total_commit_chips", 0)))
            if bet_candidates:
                # Multiway场景默认“先手必打”策略：稳定输出最小尺码抢回主动权。
                # 默认 85% 下注，15% check-fold，避免全场被动。
                rnd = _rng_pct(f"mw_bet:{state_hash}:{players_alive}:{pot_chips}") % 100
                if rnd < 85:
                    idx = min(bet_rank, len(bet_candidates) - 1)
                    return bet_candidates[idx]
                chk = _pick_nearest_action(legal_actions, kind="CHECK", target=actor_commit)
                if chk:
                    return chk
                return bet_candidates[0]
            if check_act:
                return check_act
            return _pick_nearest_action(legal_actions, kind="CALL", target=call_target)

    def _mw_prior_weight(entry: dict[str, Any] | None, *, action_kind: str, facing_bet: bool) -> int:
        if entry is None:
            return 0
        if facing_bet:
            if action_kind == "FOLD":
                return int(entry.get("fold_prob_bp") or 0)
            if action_kind == "CALL":
                return int(entry.get("call_prob_bp") or 0)
            if action_kind in ("RAISE", "BET"):
                return int(entry.get("raise_prob_bp") or 0)
            return 0
        bet_prob = entry.get("cbet_prob_bp")
        if bet_prob is None:
            bet_prob = entry.get("bet_prob_bp")
        bet_prob = int(bet_prob or 0)
        if action_kind in ("BET", "RAISE"):
            return bet_prob
        if action_kind == "CHECK":
            return max(0, 10000 - bet_prob)
        return 0

    # Precompute solver build id and root for pyo3 calls.
    try:
        solver_root = postflop_solver_src_root_from_paths_trace(paths_trace)
    except Exception:
        # Fallback to in-repo pyo3 crate to avoid host-specific absolute paths.
        solver_root = Path(__file__).resolve().parents[1] / "engines" / "postflop_pyo3" / "rs"
        if not solver_root.exists() and strict_mode:
            raise
    solver_build_id = compute_postflop_solver_build_id(src_root=solver_root, strict_mode=strict_mode)

    def _policy(ctx: dict[str, Any]) -> dict[str, Any]:
        legal = ctx["legal_actions"]
        snap = ctx["snapshot"]
        obs = ctx.get("observation") or {}
        _update_opp_defense_from_obs(
            obs=obs,
            street=snap.get("street"),
            players_alive=int(snap.get("players_alive_count", 2) or 2),
        )
        to_call = int(snap.get("to_call_chips", 0))
        actor_commit = int(snap.get("actor_commit_chips", 0))
        min_raise = snap.get("min_raise_to_chips")
        max_raise = snap.get("max_raise_to_chips")
        raise_cap = snap.get("raise_cap_to_chips")
        call_target = actor_commit + to_call
        state_hash = ctx.get("state_hash")
        decision_id = int(ctx.get("decision_id", 0) or 0)
        players_alive = int(snap.get("players_alive_count", 2) or 2)
        pot_chips = int(snap.get("pot_chips", 0) or 0)
        actor_stack = int(snap.get("actor_stack_chips", 0) or 0)
        total_stack = actor_stack + actor_commit
        adaptive_profile_runtime = _adaptive_profile_for_decision(decision_id=decision_id, state_hash=state_hash)
        adaptive_expert_runtime = "anchor"
        adaptive_alpha_runtime = 0.0
        if isinstance(adaptive_profile_runtime, dict) and adaptive_profile_runtime.get("enabled"):
            expert_raw = adaptive_profile_runtime.get("expert")
            if isinstance(expert_raw, str) and expert_raw in ("anchor", "tight_defense", "pressure"):
                adaptive_expert_runtime = expert_raw
            try:
                adaptive_alpha_runtime = float(adaptive_profile_runtime.get("alpha", 0.0) or 0.0)
            except Exception:
                adaptive_alpha_runtime = 0.0
            adaptive_alpha_runtime = max(0.0, min(0.50, adaptive_alpha_runtime))
            if bool(adaptive_profile_runtime.get("force_anchor", False)):
                adaptive_expert_runtime = "anchor"
                adaptive_alpha_runtime = 0.0
        mw_rung_id = ctx.get("mw_rung_id") if players_alive >= 3 else None
        street = snap.get("street")
        raise_count_map = obs.get("street_raise_count") or {}
        last_raiser_map = obs.get("last_raiser_by_street") or {}
        raise_count = int(raise_count_map.get(street, 0) or 0) if isinstance(raise_count_map, dict) else 0
        last_raiser = last_raiser_map.get(street) if isinstance(last_raiser_map, dict) else None
        solver_gap_hint = None
        if "solver_raise_ev" in obs and "solver_call_ev" in obs:
            try:
                sev = obs.get("solver_raise_ev")
                cev = obs.get("solver_call_ev")
                if sev is not None and cev is not None:
                    solver_gap_hint = abs(float(sev) - float(cev)) / max(1.0, float(pot_chips + to_call))
            except Exception:
                solver_gap_hint = None
        range_hint = _hu_range_hint_from_state(
            street=street if isinstance(street, str) else None,
            players_alive=players_alive,
            facing_bet=bool(to_call > 0),
            to_call=to_call,
            pot_chips=pot_chips,
            raise_count=raise_count,
            last_raiser=last_raiser,
            solver_gap_hint=solver_gap_hint,
        )
        equity_pack = _equity_from_obs(
            obs=obs,
            players_alive=players_alive,
            street=street,
            state_hash=state_hash,
            range_hint=range_hint,
            return_samples=True,
        )
        equity = None
        equity_samples: int | None = None
        if isinstance(equity_pack, tuple):
            equity, equity_samples = equity_pack
        else:
            equity = equity_pack
        board_tex: tuple[str, str] | None = None
        board_raw = obs.get("board_cards") or []
        if isinstance(board_raw, list) and len(board_raw) >= 3:
            parsed = [parse_card_token(c) for c in board_raw]
            if all(c is not None for c in parsed):
                cards = [c for c in parsed if c is not None]
                board_tex = board_texture(cards)

        def _rng_bucket(p: float, salt: str) -> bool:
            if p <= 0:
                return False
            if p >= 1:
                return True
            return (_rng_pct(salt) / 10000.0) < p

        def _maybe_fold(reason: str) -> dict[str, Any] | None:
            if equity is not None:
                return None
            fold_act = _pick_nearest_action(legal, kind="FOLD", target=actor_commit)
            if fold_act is None or to_call <= 0:
                return None
            stack = total_stack if total_stack > 0 else 1
            pot = pot_chips if pot_chips > 0 else bb
            call_frac_stack = to_call / stack
            call_over_pot = to_call / pot
            spr = (actor_stack / pot) if pot > 0 else 99.0
            base = 0.0
            if call_frac_stack > 0.35:
                base += 0.6
            elif call_frac_stack > 0.22:
                base += 0.35
            elif players_alive >= 5 and call_frac_stack > 0.15:
                base += 0.2
            if call_over_pot > 0.8:
                base += 0.3
            elif call_over_pot > 0.5:
                base += 0.15
            if spr < 1.2:
                base += 0.2
            if players_alive >= 5:
                base += 0.1
                if to_call > max(bb * 4, stack * 0.18):
                    base += 0.25
            base = min(0.95, base)
            if base <= 0:
                return None
            rnd = _rng_pct(f"fold:{reason}:{state_hash}:{seat_id}:{to_call}:{stack}") / 10000.0
            if rnd < base:
                return fold_act
            return None

        def _fallback_check_call() -> dict[str, Any]:
            if to_call == 0:
                return {"kind": "CHECK", "target_total_commit_chips": actor_commit}
            return {"kind": "CALL", "target_total_commit_chips": call_target}

        def _finalize_postflop_action(
            action: dict[str, Any] | None,
            *,
            legal_actions: list[dict[str, Any]],
            equity_val: float | None,
            uncertainty_val: float | None,
            defend_target: float | None,
            pos_key: str,
            pot: int,
            to_call: int,
            players_alive: int,
            street: str | None,
            force_defend: bool | None = None,
        ) -> dict[str, Any] | None:
            if action is None:
                return None
            result = action
            if to_call > 0 and defend_target is not None and force_defend is not None:
                want_defend = bool(force_defend)
                kind = str(result.get("kind"))
                if want_defend:
                    if kind not in ("CALL", "RAISE", "BET", "ALLIN"):
                        defend_actions = [a for a in legal_actions if str(a.get("kind")) in ("CALL", "RAISE", "BET", "ALLIN")]
                        if defend_actions:
                            if equity_val is None:
                                call_act = _pick_nearest_action(
                                    defend_actions,
                                    kind="CALL",
                                    target=actor_commit + to_call,
                                )
                                result = call_act or defend_actions[0]
                            else:
                                defend_rate_fn = lambda act: _opp_defend_rate_for_action(
                                    action=act,
                                    pot_chips=pot,
                                    to_call=to_call,
                                    actor_commit=actor_commit,
                                    players_alive=players_alive,
                                    street=street,
                                )
                                chosen = _choose_action_by_ev(
                                    legal_actions=defend_actions,
                                    equity=equity_val,
                                    pot_chips=pot,
                                    actor_commit=actor_commit,
                                    to_call=to_call,
                                    stack_chips=actor_stack,
                                    players_alive=players_alive,
                                    street=street,
                                    state_hash=state_hash,
                                    entry=None,
                                    facing_bet=True,
                                    ev_slack=None,
                                    uncertainty=uncertainty_val,
                                    defend_target=None,
                                    pos_key=pos_key,
                                    force_defend=True,
                                    defend_rate_fn=defend_rate_fn,
                                    board_texture=board_tex,
                                    adaptive_profile=adaptive_profile_runtime,
                                )
                                if chosen is not None:
                                    result = chosen
                else:
                    if kind != "FOLD":
                        fold_act = _pick_nearest_action(legal_actions, kind="FOLD", target=actor_commit)
                        if fold_act:
                            result = fold_act
            _note_aggression(
                action=result,
                pot_chips=pot,
                to_call=to_call,
                actor_commit=actor_commit,
                players_alive=players_alive,
                street=street,
                obs=obs,
            )
            return result

        if snap.get("street") == "PREFLOP":
            button_seat = int(obs.get("button_seat", seat_id))
            seats_in_hand = obs.get("seats_in_hand", [])
            pos_key = position_key(seat_id, button_seat, seats_in_hand) if seats_in_hand else "OTHERS"
            street_raise_count_map = obs.get("street_raise_count") or {}
            last_raiser_map = obs.get("last_raiser_by_street") or {}
            opener_pos = None
            if isinstance(last_raiser_map, dict):
                opener_seat = last_raiser_map.get("PREFLOP")
                if isinstance(opener_seat, int) and seats_in_hand:
                    opener_pos = position_key(opener_seat, button_seat, seats_in_hand)
            street_raise_count = 0
            if isinstance(street_raise_count_map, dict):
                street_raise_count = int(street_raise_count_map.get("PREFLOP", 0) or 0)
            hand_key = _hand_class_from_obs(obs, seat_id)
            commits_by_seat = obs.get("commits_by_seat") or {}
            committed_ge = 0
            if to_call > 0 and isinstance(commits_by_seat, dict):
                for seat_key, val in commits_by_seat.items():
                    if str(seat_key) == str(seat_id):
                        continue
                    try:
                        if int(val) >= int(call_target):
                            committed_ge += 1
                    except Exception:
                        continue
            range_prior: dict[str, int] | None = None
            range_weight = 0.0
            range_weight_prior = 0.0
            range_weight_cutoff = 0.0
            range_prob_raise: float | None = None
            range_prob_call: float | None = None
            range_ev_raise: float | None = None
            range_ev_call: float | None = None
            if preflop_ranges_enable > 0.0 and hand_key and preflop_ranges_index:
                from poker2.protocol.preflop_ranges import preflop_scenario, size_bucket_from_amount

                callers = max(0, committed_ge - 1) if to_call > 0 else 0
                scenario_key = preflop_scenario(
                    raise_count=street_raise_count,
                    has_caller=callers > 0,
                    facing=to_call > 0,
                )
                size_bucket = None
                if call_target > 0 and bb > 0:
                    size_bucket = size_bucket_from_amount(int(call_target), int(bb))
                key_values = {
                    "scenario": scenario_key,
                    "actor_pos": pos_key,
                    "last_raiser_pos": opener_pos,
                    "raise_count": int(street_raise_count),
                    "size_bucket": size_bucket,
                    "has_caller": callers > 0,
                    "callers": int(callers),
                    "players": int(players_alive),
                }
                hand_map = None
                if scenario_key is not None:
                    hand_map = _lookup_preflop_ranges(
                        index=preflop_ranges_index,
                        key_fields=preflop_ranges_key_fields,
                        key_values=key_values,
                    )
                if isinstance(hand_map, dict):
                    probs = hand_map.get(hand_key)
                    if isinstance(probs, dict):
                        p_raise = float(probs.get("raise", 0.0) or 0.0)
                        p_call = float(probs.get("call", 0.0) or 0.0)
                        p_fold = float(probs.get("fold", 0.0) or 0.0)
                        ev_raise_raw = probs.get("ev_raise")
                        ev_call_raw = probs.get("ev_call")
                        if isinstance(ev_raise_raw, (int, float)):
                            range_ev_raise = float(ev_raise_raw)
                        if isinstance(ev_call_raw, (int, float)):
                            range_ev_call = float(ev_call_raw)
                        total = p_raise + p_call + p_fold
                        if total > 0:
                            inv = 1.0 / total
                            p_raise *= inv
                            p_call *= inv
                            p_fold *= inv
                            range_weight = max(0.0, min(1.0, float(preflop_ranges_enable)))
                            if to_call <= 0 or committed_ge > 1:
                                range_weight = 0.0
                            range_weight_cutoff = range_weight
                            range_weight_prior = 0.0
                            range_prob_raise = p_raise
                            range_prob_call = p_call
                            range_prior = {
                                "RAISE": int(p_raise * 10000),
                                "BET": int(p_raise * 10000),
                                "CALL": int(p_call * 10000),
                                "FOLD": int(p_fold * 10000),
                            }
                            if scenario_key == "OPEN":
                                range_prior["CHECK"] = int(p_fold * 10000)
            if pos_key in ("SB", "BB"):
                stats = blind_open_stats.setdefault(pos_key, {"hands": 0, "opens": 0})
                stats["hands"] += 1
                if to_call > 0 and opener_pos is not None and opener_pos != pos_key:
                    stats["opens"] += 1
            defend_target_pre: float | None = None
            force_defend_pre = False
            uncertainty_pre: float | None = None
            if to_call > 0 and street_raise_count >= 1:
                defend_target_pre = _preflop_defend_target_rate(
                    to_call=to_call,
                    pot_chips=pot_chips,
                    players_alive=players_alive,
                    pos_key=pos_key,
                )
                p_defend = max(0.0, min(1.0, float(defend_target_pre)))
                if safe_exploit_max > 0 and freq_positions:
                    force_defend_pre = False
                else:
                    salt = f"defend_mix:{state_hash}:PREFLOP:{pos_key}:{pot_chips}:{to_call}"
                    force_defend_pre = (_rng_pct(salt) / 10000.0) < p_defend
                if pos_key in ("SB", "BB"):
                    force_defend_pre = False
                if equity is not None:
                    uncertainty_pre = _equity_uncertainty_for(
                        equity_val=equity,
                        samples=equity_samples,
                        players_alive=players_alive,
                        board_texture=None,
                        street="PREFLOP",
                    )
                if force_defend_pre:
                    defend_actions = [a for a in legal if str(a.get("kind")) in ("CALL", "RAISE", "BET", "ALLIN")]
                    if defend_actions:
                        if equity is not None:
                            defend_action = _choose_action_by_ev(
                                legal_actions=defend_actions,
                                equity=equity,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                stack_chips=actor_stack,
                                players_alive=players_alive,
                                street="PREFLOP",
                                state_hash=state_hash,
                                entry=None,
                                facing_bet=True,
                                ev_slack=max(1.0, float(to_call) * 0.08, float(pot_chips) * 0.02),
                                uncertainty=uncertainty_pre,
                                defend_target=None,
                                pos_key=pos_key,
                                force_defend=True,
                                board_texture=None,
                                effective_opponents=committed_ge,
                                adaptive_profile=adaptive_profile_runtime,
                            )
                            if defend_action is not None:
                                return defend_action
                        call_act = _pick_nearest_action(defend_actions, kind="CALL", target=call_target)
                        if call_act:
                            return call_act
            if equity is None and to_call > 0 and street_raise_count >= 1:
                pot_unit = max(1, pot_chips + to_call)
                equity = max(0.0, min(1.0, float(to_call) / float(pot_unit)))
                if equity_samples is None:
                    equity_samples = 0
            def _open_ratio() -> float:
                base_ratio = float(open_fraction_by_pos.get(pos_key, Fraction(5, 2)))
                if pos_key in ("BU", "SB") and bb > 0 and pot_chips > 0:
                    dead_bb = pot_chips / bb
                    size_mult = 1.0
                    if dead_bb >= 1.3:
                        size_mult += min(0.14, max(0.0, dead_bb - 1.3) * 0.10)
                    if dead_bb >= 2.0:
                        size_mult += 0.10
                    if pos_key == "BU":
                        size_mult += 0.02
                    if pos_key == "SB":
                        size_mult += 0.04
                    if rake_rate > 0:
                        size_mult += min(0.06, rake_rate * 1.2)
                    base_ratio = max(base_ratio, base_ratio * size_mult)
                return base_ratio
            if equity is None and street_raise_count == 0:
                open_ratio = _open_ratio()
                bet = _pick_raise_by_bb_ratio(
                    legal,
                    bb=bb,
                    actor_commit=actor_commit,
                    target_bb_ratio=open_ratio,
                )
                if bet:
                    return bet
            if equity is not None:
                # Use fewer opponents for heads-up pots, but keep multiway pressure in larger fields.
                if street_raise_count == 1:
                    opponents = 1 if players_alive <= 4 else 2
                    if committed_ge > 0:
                        opponents = max(1, min(3, committed_ge))
                elif street_raise_count >= 2:
                    opponents = min(3, max(1, players_alive - 1))
                else:
                    opponents = max(1, players_alive - 1)
                realization = 1.0 - 0.05 * max(0, players_alive - 2)
                if pos_key in ("SB", "BB"):
                    realization -= 0.06
                if pos_key == "BU":
                    realization += 0.02
                if to_call > 0:
                    realization -= 0.05
                if street_raise_count >= 2:
                    realization -= 0.06
                realization = max(0.6, min(1.02, realization))
                equity_eff = equity * realization
                equity_gate = equity_eff if to_call > 0 else equity
                gate_eq_call = equity_gate
                call_realization = 1.0
                call_realization_pre: float | None = None
                call_ev_pre: float | None = None
                raise_ev_pre: float | None = None
                def_ev_ready = False
                pot_unit_pre = max(1.0, float(pot_chips + to_call))
                if to_call > 0 and street_raise_count >= 1 and pos_key in ("SB", "BB"):
                    spr = None
                    if actor_stack is not None and pot_chips > 0:
                        spr = float(actor_stack) / float(pot_chips)
                    if spr is None:
                        spr = 6.0
                    eq_strength_call = equity if equity is not None else equity_eff
                    eq_strength_call = max(0.0, min(1.0, float(eq_strength_call)))
                    pressure = (0.12 * max(0, opponents - 1)) + (0.04 * max(0.0, min(10.0, spr - 2.0))) + (4.0 * rake_rate)
                    base_realization = 1.0 / (1.0 + pressure)
                    eq_relief = 0.6 + 0.4 * eq_strength_call
                    call_realization = max(0.50, min(0.95, base_realization * eq_relief))
                    price = float(to_call) / max(1.0, float(pot_unit_pre))
                    call_realization *= 1.0 - 0.35 * max(0.0, min(1.0, price))
                    call_realization = max(0.40, min(0.95, call_realization))
                    if equity_gate is not None:
                        gate_eq_call = float(equity_gate) * (0.70 + 0.30 * call_realization)
                    call_realization_pre = call_realization
                open_pct = _freq(pos_key, "open_pct", 1.0)
                call_pct_vs_open = min(_freq(pos_key, "call_pct", 0.20), 0.65)
                threebet_pct = max(_freq(pos_key, "threebet_pct", 0.15), 0.10)
                fourbet_pct = max(_freq(pos_key, "fourbet_pct", 0.05), 0.03)
                open_pct_bu = _freq("BU", "open_pct", open_pct)
                open_pct_sb = _freq("SB", "open_pct", open_pct)
                open_pct_others = _freq("OTHERS", "open_pct", open_pct)
                call_shrink = 1.0
                call_shrink -= min(0.20, rake_rate * 1.2)
                call_shrink -= 0.03 * max(0, players_alive - 4)
                if pos_key in ("SB", "BB"):
                    call_shrink -= 0.00
                call_shrink = max(0.90, min(1.0, call_shrink))
                call_pct_vs_open *= call_shrink
                if adaptive_alpha_runtime > 0.0:
                    alpha = adaptive_alpha_runtime
                    if adaptive_expert_runtime == "pressure":
                        open_pct = min(1.0, max(0.0, open_pct * (1.0 + 0.25 * alpha)))
                        threebet_pct = min(1.0, max(0.0, threebet_pct * (1.0 + 0.35 * alpha)))
                        call_pct_vs_open = min(1.0, max(0.01, call_pct_vs_open * (1.0 - 0.15 * alpha)))
                    elif adaptive_expert_runtime == "tight_defense":
                        open_pct = min(1.0, max(0.0, open_pct * (1.0 - 0.15 * alpha)))
                        threebet_pct = min(1.0, max(0.01, threebet_pct * (1.0 - 0.30 * alpha)))
                        call_pct_vs_open = min(1.0, max(0.01, call_pct_vs_open * (1.0 + 0.20 * alpha)))
                if defend_target_pre is not None and to_call > 0 and street_raise_count >= 1 and pos_key in ("SB", "BB"):
                    stats = blind_open_stats.get(pos_key)
                    open_obs = None
                    open_obs_hands = 0
                    if stats and stats.get("hands", 0) > 0:
                        open_obs_hands = int(stats.get("hands", 0))
                        open_obs = float(stats.get("opens", 0)) / max(1.0, float(open_obs_hands))
                    open_rate_prior = None
                    if pos_key == "SB":
                        denom = max(1.0, float(players_alive - 2))
                        open_rate_prior = (
                            float(open_pct_others) * max(0.0, float(players_alive - 3))
                            + float(open_pct_bu)
                        ) / denom
                    else:
                        denom = max(1.0, float(players_alive - 1))
                        open_rate_prior = (
                            float(open_pct_others) * max(0.0, float(players_alive - 3))
                            + float(open_pct_bu)
                            + float(open_pct_sb)
                        ) / denom
                    if open_rate_prior is not None and open_obs is not None:
                        prior_strength = 6.0 + 1.5 * max(0, players_alive - 3)
                        obs_strength = min(80.0, float(open_obs_hands))
                        posterior = (
                            float(open_rate_prior) * prior_strength + float(open_obs) * obs_strength
                        ) / max(1e-6, prior_strength + obs_strength)
                        scale = (posterior / max(0.05, float(open_rate_prior))) ** 0.5
                        conf = min(1.0, float(open_obs_hands) / 160.0)
                        scale = 1.0 + (scale - 1.0) * conf
                        scale = max(0.75, min(1.35, scale))
                        pot_base = max(1, pot_chips)
                        mdf = float(pot_base) / max(1.0, float(pot_base + to_call))
                        defenders = max(1, players_alive - 1)
                        if defenders > 1:
                            mdf = 1.0 - (1.0 - mdf) ** (1.0 / defenders)
                        rake_est = estimate_rake(
                            pot_after=float(pot_base + to_call),
                            street="PREFLOP",
                            rake_rate=rake_rate,
                            rake_cap=rake_cap,
                            no_flop_no_drop=no_flop_no_drop,
                        )
                        rake_frac = float(rake_est) / max(1.0, float(pot_base + to_call))
                        mdf_floor = mdf * max(0.0, 1.0 - rake_frac)
                        if pos_key in ("SB", "BB"):
                            mdf_scale = 0.40 + 0.25 * scale
                            defend_target_pre = max(defend_target_pre, mdf_floor * mdf_scale)
                            defend_target_pre = min(0.70, max(0.01, defend_target_pre * (0.85 + 0.15 * scale)))
                        else:
                            defend_target_pre = max(defend_target_pre, mdf_floor * (0.60 + 0.40 * scale))
                            defend_target_pre = min(0.85, max(0.01, defend_target_pre * scale))
                if street_raise_count == 0:
                    if pos_key in ("BU", "SB"):
                        opponents_open = 2
                    elif players_alive >= 6:
                        opponents_open = 3
                    elif players_alive >= 5:
                        opponents_open = 2
                    else:
                        opponents_open = max(1, players_alive - 1)
                    open_pct_eff = open_pct
                    if bb > 0 and pot_chips > 0:
                        dead_bb = pot_chips / bb
                        if dead_bb >= 2.0:
                            boost = min(0.10, max(0.0, (dead_bb - 1.6) * 0.10))
                            open_pct_eff = min(1.0, open_pct * (1.0 + boost))
                    cutoff_base = _preflop_cutoff(opponents_open, open_pct_eff)
                    if range_weight > 0.0 and range_prob_raise is not None:
                        range_cutoff = _preflop_cutoff(opponents_open, float(range_prob_raise))
                        cutoff_base = (1.0 - range_weight_cutoff) * cutoff_base + range_weight_cutoff * range_cutoff
                    cutoff = cutoff_base
                    if pos_key == "BU":
                        behind = 2
                    elif pos_key == "SB":
                        behind = 1
                    elif pos_key == "BB":
                        behind = 0
                    else:
                        behind = max(2, min(4, players_alive - 3))
                    risk_premium = min(0.05, rake_rate * 0.25 + 0.004 * behind)
                    if pos_key in ("BU", "SB"):
                        risk_premium = min(0.07, risk_premium + 0.006)
                    cutoff = min(1.0, cutoff + risk_premium)
                    equity_open = equity_gate
                    if opponents_open != max(1, players_alive - 1):
                        equity_open = _equity_from_obs(
                            obs=obs,
                            players_alive=opponents_open + 1,
                            street=snap.get("street"),
                            state_hash=state_hash,
                        )
                    if equity_open is None:
                        equity_open = equity_gate if equity_gate is not None else equity_eff
                    open_mix = _edge_mix(equity_open, cutoff, width=0.02)
                    if range_weight_cutoff > 0.0 and range_prob_raise is not None:
                        open_mix = (1.0 - range_weight_cutoff) * open_mix + range_weight_cutoff * float(range_prob_raise)
                    if open_mix <= 0.0:
                        check_act = _pick_nearest_action(legal, kind="CHECK", target=actor_commit)
                        if check_act:
                            return check_act
                        fold_act = _pick_nearest_action(legal, kind="FOLD", target=actor_commit)
                        if fold_act:
                            return fold_act
                    elif open_mix < 1.0:
                        if (_rng_pct(f"open_mix:{state_hash}:{seat_id}:{pos_key}") / 10000.0) > open_mix:
                            check_act = _pick_nearest_action(legal, kind="CHECK", target=actor_commit)
                            if check_act:
                                return check_act
                            fold_act = _pick_nearest_action(legal, kind="FOLD", target=actor_commit)
                            if fold_act:
                                return fold_act
                gate_eq = equity_gate if equity_gate is not None else equity_eff
                call_cutoff = None
                raise_cutoff = None
                prior_weights: dict[str, int] | None = None
                legal_ev = legal
                defend_target_mix: float | None = None
                if street_raise_count == 0:
                    raise_w = max(0.0, min(1.0, open_pct))
                    call_w = 0.0
                    if pos_key == "SB" and to_call > 0:
                        call_w = min(0.25, call_pct_vs_open * 0.4)
                        raise_w = max(0.0, raise_w - call_w)
                    check_w = max(0.0, 1.0 - raise_w - call_w)
                    prior_weights = {
                        "RAISE": int(raise_w * 10000),
                        "BET": int(raise_w * 10000),
                        "CALL": int(call_w * 10000),
                        "CHECK": int(check_w * 10000),
                    }
                    if range_prior is not None and range_weight_prior > 0.0:
                        prior_weights = _blend_prior_weights(prior_weights, range_prior, range_weight_prior)
                    if call_w <= 0.0 and pos_key != "SB":
                        legal_ev = [a for a in legal if a.get("kind") != "CALL"]
                elif to_call > 0 and street_raise_count >= 1:
                    facing_open = street_raise_count == 1
                    raise_pct = threebet_pct if facing_open else fourbet_pct
                    call_pct_vs_open_eff = call_pct_vs_open
                    if facing_open and pos_key in ("SB", "BB"):
                        call_pct_vs_open_eff = call_pct_vs_open
                    if facing_open and pos_key == "BB" and opener_pos == "SB":
                        sb_open = float(open_pct_sb) if open_pct_sb is not None else 0.45
                        sb_open = max(0.20, min(0.70, sb_open))
                        sb_boost = 1.6 + 0.8 * sb_open
                        raise_pct = min(0.60, raise_pct * sb_boost)
                        call_pct_vs_open_eff *= 0.25
                    call_pct = min(1.0, raise_pct + call_pct_vs_open_eff * (1.0 if facing_open else 0.6))
                    if defend_target_pre is not None and facing_open and equity is not None:
                        call_act = _pick_nearest_action(legal, kind="CALL", target=call_target)
                        if call_act is not None:
                            if pos_key == "BB":
                                raise_ratio = float(
                                    threebet_by_pos.get("BB_VS_OTHER", threebet_by_pos.get("OOP", Fraction(33, 10)))
                                )
                            elif pos_key == "SB":
                                raise_ratio = float(
                                    threebet_by_pos.get("SB_VS_OTHER", threebet_by_pos.get("OOP", Fraction(21, 5)))
                                )
                            else:
                                raise_ratio = float(threebet_by_pos.get("IP", Fraction(33, 10)))
                            raise_act = _pick_raise_by_bb_ratio(
                                legal,
                                bb=bb,
                                actor_commit=actor_commit,
                                target_bb_ratio=raise_ratio,
                            )
                        else:
                            raise_act = None
                        if raise_act is None:
                            raise_actions = [a for a in legal if str(a.get("kind")) in ("RAISE", "BET", "ALLIN")]
                            raise_actions.sort(key=lambda a: int(a.get("target_total_commit_chips", 0)))
                            if raise_actions:
                                raise_act = raise_actions[0]
                        if call_act is not None and raise_act is not None:
                            pot_unit = max(1, pot_chips + to_call)
                            call_ev_raw = _action_ev(
                                action=call_act,
                                equity=equity,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                street="PREFLOP",
                                defend_rate=None,
                            )
                            call_ev = _action_ev(
                                action=call_act,
                                equity=equity_eff,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                street="PREFLOP",
                                defend_rate=None,
                            )
                            call_ev_pre = float(call_ev_raw)
                            raise_ev = _action_ev(
                                action=raise_act,
                                equity=equity_eff,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                street="PREFLOP",
                                defend_rate=_preflop_defend_rate(
                                    pot_chips if pot_chips > 0 else bb,
                                    max(0, int(raise_act.get("target_total_commit_chips", actor_commit)) - actor_commit),
                                    max(1, players_alive - 1),
                                    opener_pos=opener_pos,
                                    defender_pos=opener_pos if opener_pos is not None else "OTHERS",
                                ),
                            )
                            raise_ev_pre = float(raise_ev)
                            def_ev_ready = True
                            exp_rake_call = _expected_rake_for_action(
                                action=call_act,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                street="PREFLOP",
                                defend_rate=None,
                            )
                            exp_rake_raise = _expected_rake_for_action(
                                action=raise_act,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                street="PREFLOP",
                                defend_rate=_preflop_defend_rate(
                                    pot_chips if pot_chips > 0 else bb,
                                    max(0, int(raise_act.get("target_total_commit_chips", actor_commit)) - actor_commit),
                                    max(1, players_alive - 1),
                                    opener_pos=opener_pos,
                                    defender_pos=opener_pos if opener_pos is not None else "OTHERS",
                                ),
                            )
                            delta_rake = max(0.0, float(exp_rake_raise) - float(exp_rake_call))
                            oop_cost_call = float(to_call) * (1.0 - call_realization) * (
                                0.55 + 0.15 * max(0, players_alive - 2)
                            )
                            raise_size = max(
                                0,
                                int(raise_act.get("target_total_commit_chips", actor_commit)) - actor_commit,
                            )
                            raise_risk = max(float(to_call), float(raise_size))
                            raise_ratio = raise_risk / max(1.0, float(pot_unit))
                            oop_cost_raise = float(oop_cost_call) * (
                                1.0 + 0.35 * max(0.0, min(1.0, raise_ratio))
                            )
                            rake_weight = 1.0 + float(rake_delta_weight)
                            call_net = float(call_ev) - (rake_weight * float(exp_rake_call)) - float(oop_cost_call)
                            raise_net = float(raise_ev) - (rake_weight * float(exp_rake_raise)) - float(oop_cost_raise)
                            pot_scale = max(1.0, float(pot_unit))
                            best_net = max(call_net, raise_net)
                            net_ratio = best_net / pot_scale
                            net_scale = 1.0 / (1.0 + math.exp(-3.0 * net_ratio))
                            edge = float(raise_net) - float(call_net)
                            edge_ratio = edge / pot_scale
                            edge_sig = 1.0 / (1.0 + math.exp(-6.0 * edge_ratio))
                            if range_weight > 0.0 and facing_open:
                                edge_abs = abs(float(edge_ratio))
                                conf = 1.0 / (1.0 + math.exp(8.0 * (edge_abs - 0.04)))
                                range_weight_cutoff = max(0.0, min(1.0, range_weight * conf))
                            ev_raise_cap: float | None = None
                            ev_raise_pref: float | None = None
                            if facing_open and pos_key in ("SB", "BB"):
                                ev_edge_ratio = max(-1.0, min(1.0, float(edge_ratio)))
                                ev_sig = 1.0 / (1.0 + math.exp(-5.0 * ev_edge_ratio))
                                ev_raise_cap = 0.06 + 0.60 * ev_sig
                                ev_raise_cap *= 0.70 + 0.30 * call_realization
                                ev_raise_cap *= 1.0 / (1.0 + 0.12 * max(0, players_alive - 2))
                                if pos_key == "BB" and opener_pos == "SB":
                                    ev_raise_cap = max(ev_raise_cap, 0.22 + 0.28 * ev_sig)
                                ev_raise_cap = max(0.04, min(0.70, ev_raise_cap))
                                ev_raise_pref = min(ev_raise_cap, max(0.05, min(0.85, ev_sig)))
                            if defend_target_pre is not None:
                                defend_target_pre = max(0.02, min(0.85, float(defend_target_pre) * (0.55 + 0.45 * net_scale)))
                            if facing_open and pos_key == "BB" and opener_pos == "SB" and defend_target_pre is not None:
                                sb_open = float(open_pct_sb) if open_pct_sb is not None else 0.45
                                sb_open = max(0.20, min(0.70, sb_open))
                                sb_def_floor = 0.18 + 0.20 * sb_open
                                defend_target_pre = max(defend_target_pre, min(0.45, sb_def_floor))
                            mix_scale = 0.70 + 0.30 * net_scale
                            if facing_open and pos_key in ("SB", "BB"):
                                mix_scale = max(mix_scale, 0.85 + 0.25 * edge_sig)
                            call_pct = max(0.0, min(1.0, call_pct * mix_scale))
                            raise_pct = max(0.0, min(1.0, raise_pct * mix_scale))
                            if facing_open and pos_key in ("SB", "BB"):
                                call_score = float(call_net) / pot_scale
                                call_sig = 1.0 / (1.0 + math.exp(-4.0 * call_score))
                                call_scale_ev = 0.35 + 0.45 * call_sig
                                call_scale_ev *= 0.85 + 0.15 * call_realization
                                call_scale_ev *= 1.0 / (1.0 + 0.10 * max(0, players_alive - 2))
                                call_scale_ev *= 1.0 / (1.0 + 1.8 * rake_rate)
                                call_scale_ev = max(0.35, min(1.15, call_scale_ev))
                                call_pct = max(0.0, min(1.0, call_pct * call_scale_ev))
                                if defend_target_pre is not None:
                                    defend_anchor = float(defend_target_pre) * (0.70 + 0.30 * call_scale_ev)
                                    defend_anchor = max(0.04, min(0.75, defend_anchor))
                                    anchor_scale = 0.35 + 0.25 * call_realization
                                    call_pct = max(call_pct, defend_anchor * anchor_scale)
                            if facing_open and pos_key in ("SB", "BB"):
                                raise_floor = threebet_pct * (0.90 + 0.30 * edge_sig)
                                raise_pct = max(raise_pct, min(1.0, raise_floor))
                            call_score = float(call_net) / pot_scale
                            raise_score = float(raise_net) / pot_scale
                            temp = 0.35 + 0.35 * (1.0 - call_realization)
                            max_score = max(call_score, raise_score)
                            call_w = math.exp((call_score - max_score) / max(1e-6, temp))
                            raise_w = math.exp((raise_score - max_score) / max(1e-6, temp))
                            raise_bias = raise_w / max(1e-9, (call_w + raise_w))
                            call_score_sigmoid = 1.0 / (1.0 + math.exp(-4.0 * call_score))
                            call_floor = (0.08 + 0.20 * call_realization) * (0.5 + 0.5 * call_score_sigmoid)
                            call_floor = max(0.04, min(0.35, call_floor))
                            if pos_key in ("SB", "BB"):
                                edge_ratio = float(edge) / max(1.0, float(pot_scale))
                                edge_ratio = max(-0.5, min(0.5, edge_ratio))
                                edge_sig = 1.0 / (1.0 + math.exp(6.0 * edge_ratio))
                                call_floor = max(call_floor, 0.04 + 0.18 * edge_sig)
                            raise_bias = min(raise_bias, max(0.0, 1.0 - call_floor))
                            if facing_open and pos_key == "BB" and opener_pos == "SB":
                                sb_open = float(open_pct_sb) if open_pct_sb is not None else 0.45
                                sb_open = max(0.20, min(0.70, sb_open))
                                open_sig = 1.0 / (1.0 + math.exp(-6.0 * (sb_open - 0.35)))
                                raise_bias = max(raise_bias, 0.45 + 0.40 * open_sig)
                            if (
                                facing_open
                                and pos_key in ("SB", "BB")
                                and range_ev_raise is not None
                                and range_ev_call is not None
                            ):
                                ev_gap = float(range_ev_raise) - float(range_ev_call)
                                ev_scale = max(1e-6, abs(float(range_ev_raise)) + abs(float(range_ev_call)))
                                ev_sig = 1.0 / (1.0 + math.exp(-4.0 * (ev_gap / ev_scale)))
                                ev_bias = (ev_sig - 0.5) * 2.0
                                tie_conf = 1.0 / (1.0 + math.exp(8.0 * (abs(edge_ratio) - 0.03)))
                                adjust = ev_bias * tie_conf * 0.20
                                raise_bias = max(0.0, min(1.0, raise_bias + adjust))
                            best_ev = max(float(call_net), float(raise_net))
                            best_ratio = best_ev / pot_scale
                            best_scale = 1.0 / (1.0 + math.exp(-3.0 * best_ratio))
                            target_def = float(defend_target_pre) * (0.55 + 0.45 * best_scale)
                            target_def = max(0.05, min(0.70, target_def))
                            realizable_floor = float(defend_target_pre) * (0.75 + 0.25 * call_realization)
                            defend_target_mix = max(realizable_floor, target_def * (0.45 + 0.55 * best_scale))
                            defend_target_mix = max(0.02, min(0.65, defend_target_mix))
                            if call_pct < target_def and pos_key not in ("SB", "BB"):
                                call_pct = target_def
                            desired_raise = call_pct * raise_bias
                            if facing_open and pos_key == "SB":
                                desired_raise = min(1.0, desired_raise * 1.25)
                            adj_strength = 0.35 + 0.45 * (1.0 - call_realization)
                            raise_pct = raise_pct + (desired_raise - raise_pct) * adj_strength
                            raise_cap = 1.0
                            if facing_open and pos_key in ("SB", "BB"):
                                base_cap = 0.22 + 0.08 * max(0.0, min(1.0, call_realization))
                                raise_cap = max(0.20, min(0.30, base_cap))
                            if facing_open and pos_key in ("SB", "BB"):
                                edge_ratio = float(edge) / max(1.0, float(pot_scale))
                                edge_ratio = max(-0.5, min(0.5, edge_ratio))
                                edge_sig = 1.0 / (1.0 + math.exp(-6.0 * (edge_ratio - 0.02)))
                                risk_scale = 0.70 + 0.30 * call_realization
                                if pos_key == "BB" and opener_pos == "SB":
                                    raise_cap_ev = (0.10 + 0.45 * edge_sig) * risk_scale
                                    raise_cap_ev = max(0.08, min(0.55, raise_cap_ev))
                                else:
                                    raise_cap_ev = (0.04 + 0.20 * edge_sig) * risk_scale
                                    raise_cap_ev = max(0.02, min(0.25, raise_cap_ev))
                                raise_cap = min(raise_cap, raise_cap_ev)
                            if facing_open and pos_key == "BB" and opener_pos == "SB":
                                sb_open = float(open_pct_sb) if open_pct_sb is not None else 0.45
                                sb_open = max(0.20, min(0.70, sb_open))
                                open_sig = 1.0 / (1.0 + math.exp(-6.0 * (sb_open - 0.35)))
                                raise_cap = max(raise_cap, 0.30 + 0.20 * open_sig)
                            if ev_raise_cap is not None:
                                raise_cap = min(raise_cap, float(ev_raise_cap))
                            if raise_pct < desired_raise:
                                raise_pct = desired_raise
                            raise_pct = min(raise_pct, raise_cap)
                            if facing_open and pos_key in ("SB", "BB") and ev_raise_pref is not None:
                                defend_base = call_pct
                                if defend_target_mix is not None:
                                    defend_base = max(defend_base, float(defend_target_mix))
                                elif defend_target_pre is not None:
                                    defend_base = max(defend_base, float(defend_target_pre))
                                defend_base = max(0.04, min(0.75, defend_base))
                                target_raise_pct = defend_base * float(ev_raise_pref)
                                target_call_pct = max(0.0, defend_base - target_raise_pct)
                                blend = 0.35 + 0.35 * (1.0 - call_realization)
                                call_pct = call_pct + (target_call_pct - call_pct) * blend
                                raise_pct = raise_pct + (target_raise_pct - raise_pct) * blend
                            if facing_open and pos_key in ("SB", "BB"):
                                call_floor_ratio = max(0.0, min(1.0, float(call_floor)))
                                raise_cap_call = max(0.0, min(1.0, 1.0 - call_floor_ratio))
                                raise_pct = min(raise_pct, call_pct * raise_cap_call)
                            if call_pct < raise_pct:
                                call_pct = raise_pct
                            call_pct = min(1.0, max(0.0, call_pct))
                            raise_pct = min(call_pct, max(0.0, raise_pct))
                            if facing_open and pos_key in ("SB", "BB") and def_ev_ready:
                                call_share = max(0.0, call_pct - raise_pct)
                                if call_share > 0:
                                    net_gap = (float(raise_net) - float(call_net)) / max(1e-6, pot_scale)
                                    gap_sig = 1.0 / (1.0 + math.exp(-5.0 * net_gap))
                                    gap_pos = max(0.0, (gap_sig - 0.5) * 2.0)
                                    shift_strength = (0.02 + 0.50 * gap_pos) * (
                                        0.65 + 0.35 * (1.0 - float(call_realization))
                                    )
                                    shift_strength = min(0.65, max(0.0, shift_strength))
                                    shift = min(call_share, call_share * shift_strength)
                                    raise_pct += shift
                                    call_share = max(0.0, call_share - shift)
                                    call_pct = min(1.0, max(0.0, raise_pct + call_share))
                            call_share = max(0.0, call_pct - raise_pct)
                    def_premium = min(0.08, rake_rate * 0.6 + 0.01 * max(0, opponents - 1))
                    if pos_key in ("SB", "BB"):
                        def_premium += 0.01
                    if street_raise_count >= 2:
                        def_premium += 0.02
                    multiway_open = bool(facing_open and committed_ge >= 2 and players_alive >= 4)
                    skip_equity_gates = bool(def_ev_ready and facing_open and pos_key in ("SB", "BB"))
                    if range_weight_cutoff > 0.0 and range_prob_raise is not None and range_prob_call is not None:
                        range_def = min(1.0, float(range_prob_raise + range_prob_call))
                        model_def = max(0.0, min(1.0, float(call_pct)))
                        diff = abs(range_def - model_def)
                        compat = max(0.0, 1.0 - (diff / 0.35))
                        range_weight_cutoff = max(0.0, min(1.0, range_weight_cutoff * compat))
                    raise_cutoff = min(1.0, _preflop_cutoff(opponents, raise_pct) + def_premium)
                    call_cutoff = min(1.0, _preflop_cutoff(opponents, call_pct) + def_premium * 0.7)
                    if range_weight_cutoff > 0.0 and range_prob_raise is not None and range_prob_call is not None:
                        range_def = min(1.0, float(range_prob_raise + range_prob_call))
                        range_raise_cutoff = min(1.0, _preflop_cutoff(opponents, float(range_prob_raise)) + def_premium)
                        range_call_cutoff = min(1.0, _preflop_cutoff(opponents, range_def) + def_premium * 0.7)
                        raise_cutoff = (1.0 - range_weight_cutoff) * raise_cutoff + range_weight_cutoff * range_raise_cutoff
                        call_cutoff = (1.0 - range_weight_cutoff) * call_cutoff + range_weight_cutoff * range_call_cutoff
                    gate_eq = equity_gate if equity_gate is not None else equity_eff
                    pot_odds = to_call / max(pot_chips + to_call, 1)
                    hard_fold_cutoff = min(0.95, pot_odds + def_premium)
                    if gate_eq < hard_fold_cutoff:
                        bump = 0.02 * max(0.0, min(1.0, range_weight_cutoff))
                        if gate_eq + bump < hard_fold_cutoff:
                            allow_defend = False
                            if skip_equity_gates and call_ev_pre is not None:
                                unc_pen = 0.0
                                if uncertainty_pre is not None:
                                    unc_pen = max(0.0, min(1.0, float(uncertainty_pre)))
                                ev_guard = -0.02 * pot_unit_pre * (0.7 + 0.6 * unc_pen)
                                allow_defend = float(call_ev_pre) >= ev_guard
                            if not allow_defend:
                                fold_act = _pick_nearest_action(legal, kind="FOLD", target=actor_commit)
                                if fold_act:
                                    return fold_act
                    call_slack = min(0.04, 0.01 + def_premium * 0.5)
                    if not skip_equity_gates:
                        if pos_key in ("SB", "BB"):
                            pot_after = int(pot_chips + to_call)
                            rake_shadow = estimate_rake(
                                pot_after=float(pot_after),
                                street="FLOP",
                                rake_rate=rake_rate,
                                rake_cap=rake_cap,
                                no_flop_no_drop=no_flop_no_drop,
                            )
                            hazard = min(0.45, 0.18 + 0.035 * max(0, players_alive - 2))
                            effective_pot = max(
                                1.0,
                                float(pot_after)
                                - (
                                    0.0
                                    if snap.get("street") in (None, "PREFLOP")
                                    else float(rake_shadow) * hazard
                                ),
                            )
                            call_floor = min(0.90, (float(to_call) / effective_pot) * 0.52)
                            if call_cutoff is not None:
                                call_cutoff = max(call_cutoff, call_floor)
                            if pos_key == "BB":
                                rake_ratio = float(rake_shadow) / max(1.0, float(pot_after))
                                bb_floor = min(0.85, (pot_odds * 0.85) + (rake_ratio * 2.0) + 0.01 * max(0, players_alive - 2))
                                if call_cutoff is not None:
                                    call_cutoff = max(call_cutoff, bb_floor)
                            if call_cutoff is not None:
                                cap_floor = max(pot_odds + 0.02, pot_odds * 1.05)
                                call_cutoff = min(call_cutoff, cap_floor)
                        raise_slack = min(0.06, 0.02 + def_premium * 0.6)
                        bump_raise = 0.015 * max(0.0, min(1.0, range_weight_cutoff))
                        if gate_eq + bump_raise < (raise_cutoff - raise_slack):
                            legal_ev = [a for a in legal if a.get("kind") not in ("RAISE", "BET")]
                        bump_call = 0.02 * max(0.0, min(1.0, range_weight_cutoff))
                        if call_cutoff is not None and (gate_eq_call + bump_call) < (call_cutoff - call_slack):
                            call_keep = False
                            if call_ev_pre is not None:
                                call_keep = call_keep or (float(call_ev_pre) >= (-0.02 * pot_unit_pre))
                            if (
                                not call_keep
                                and facing_open
                                and pos_key in ("SB", "BB")
                                and call_pct > raise_pct
                            ):
                                call_keep = True
                            if not call_keep:
                                legal_ev = [a for a in legal_ev if a.get("kind") != "CALL"]
                    flat_pct = max(0.0, call_pct - raise_pct)
                    prior_weights = {
                        "RAISE": int(raise_pct * 10000),
                        "BET": int(raise_pct * 10000),
                        "CALL": int(flat_pct * 10000),
                        "FOLD": int(max(0.0, 1.0 - call_pct) * 10000),
                    }
                    if range_prior is not None and range_weight_prior > 0.0:
                        prior_weights = _blend_prior_weights(prior_weights, range_prior, range_weight_prior)
                    if pos_key == "BB" and multiway_open:
                        prior_weights["CALL"] = 0
                    if not def_ev_ready and pos_key == "SB" and street_raise_count >= 1 and to_call > 0:
                        sb_raise_pct = max(0.0, min(1.0, open_pct))
                        sb_call_scale = 0.30 - (0.8 * preflop_defend_tighten) - (3.5 * rake_rate) - (0.05 * max(0, players_alive - 2))
                        sb_call_scale = max(0.10, min(0.60, sb_call_scale))
                        sb_call_pct = max(0.0, min(1.0, call_pct_vs_open * sb_call_scale))
                        sb_raise_cutoff = _preflop_cutoff(opponents, sb_raise_pct)
                        sb_call_cutoff = _preflop_cutoff(opponents, min(1.0, sb_raise_pct + sb_call_pct))
                        if gate_eq_call < sb_call_cutoff:
                            fold_act = _pick_nearest_action(legal, kind="FOLD", target=actor_commit)
                            if fold_act:
                                return fold_act
                        elif gate_eq_call < sb_raise_cutoff:
                            call_act = _pick_nearest_action(legal, kind="CALL", target=call_target)
                            if call_act:
                                return call_act

                pot_base = pot_chips if pot_chips > 0 else bb
                opponents_eff = max(1, players_alive - 1)
                uncertainty_pf = _equity_uncertainty_for(
                    equity_val=equity_eff,
                    samples=equity_samples,
                    players_alive=players_alive,
                    board_texture=None,
                    street=snap.get("street"),
                )
                def _preflop_defend_rate_fn(act: dict[str, Any]) -> float:
                    if act.get("kind") in ("RAISE", "BET"):
                        target = int(act.get("target_total_commit_chips", actor_commit))
                        bet_size = max(0, target - actor_commit)
                        defender_pos = opener_pos if opener_pos is not None else "OTHERS"
                        return _preflop_defend_rate(
                            pot_base,
                            bet_size,
                            opponents_eff,
                            opener_pos=opener_pos,
                            defender_pos=defender_pos,
                        )
                    return 0.0

                ev_slack = max(1.0, float(to_call) * 0.15, float(pot_base) * 0.03)
                first_in = street_raise_count == 0 and to_call > 0
                if not first_in:
                    legal_candidates = legal_ev if legal_ev else legal
                    if street_raise_count >= 1 and to_call > 0:
                        if not def_ev_ready:
                            legal_candidates = _preflop_raise_gate(
                                legal_actions=legal_candidates,
                                equity=equity_eff,
                                pot_chips=pot_base,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                pos_key=pos_key,
                            )
                    if street_raise_count >= 1 and to_call > 0:
                        if not def_ev_ready:
                            legal_candidates = _preflop_prior_gate(
                                legal_actions=legal_candidates,
                                prior_weights=prior_weights,
                                state_hash=state_hash,
                                to_call=to_call,
                                pot_chips=pot_base,
                                call_ev=call_ev_pre,
                                raise_ev=raise_ev_pre,
                            )
                    action = _choose_action_by_ev(
                        legal_actions=legal_candidates,
                        equity=equity_eff,
                        pot_chips=pot_base,
                        actor_commit=actor_commit,
                        to_call=to_call,
                        stack_chips=actor_stack,
                        players_alive=players_alive,
                        street=snap.get("street"),
                        state_hash=state_hash,
                        entry=None,
                        facing_bet=to_call > 0,
                        defend_rate_fn=_preflop_defend_rate_fn,
                        prior_weights=prior_weights,
                        ev_slack=ev_slack,
                        min_ev_for_priors=-ev_slack,
                        uncertainty=uncertainty_pf,
                        defend_target=defend_target_mix,
                        pos_key=pos_key,
                        board_texture=None,
                        call_realization=call_realization_pre,
                        solver_call_ev=call_ev_pre,
                        solver_raise_ev=raise_ev_pre,
                        effective_opponents=committed_ge,
                        adaptive_profile=adaptive_profile_runtime,
                    )
                    if action is not None:
                        return action
                if pos_key == "BB":
                    threebet_frac = threebet_by_pos.get("BB_VS_OTHER", threebet_by_pos.get("OOP", Fraction(33, 10)))
                elif pos_key == "SB":
                    threebet_frac = threebet_by_pos.get("SB_VS_OTHER", threebet_by_pos.get("OOP", Fraction(21, 5)))
                elif pos_key == "BU":
                    threebet_frac = threebet_by_pos.get("IP", Fraction(33, 10))
                else:
                    threebet_frac = threebet_by_pos.get("IP", Fraction(33, 10))
                ip_flag = pos_key in ("BU", "OTHERS")
                fourbet_frac = fourbet_by_pos.get("IP" if ip_flag else "OOP", Fraction(23, 10 if ip_flag else 5))

                if street_raise_count == 0:
                    # Opening assumes fewer effective opponents; with antes, expand slightly.
                    if pos_key in ("BU", "SB"):
                        opponents_open = 2
                    elif players_alive >= 6:
                        opponents_open = 3
                    elif players_alive >= 5:
                        opponents_open = 2
                    else:
                        opponents_open = max(1, players_alive - 1)
                    open_pct_eff = open_pct
                    if bb > 0 and pot_chips > 0:
                        dead_bb = pot_chips / bb
                        if dead_bb >= 2.0:
                            boost = min(0.10, max(0.0, (dead_bb - 1.6) * 0.10))
                            open_pct_eff = min(1.0, open_pct * (1.0 + boost))
                    cutoff = _preflop_cutoff(opponents_open, open_pct_eff)
                    # Risk premium for opening: more players behind + rake pressure.
                    if pos_key == "BU":
                        behind = 2
                    elif pos_key == "SB":
                        behind = 1
                    elif pos_key == "BB":
                        behind = 0
                    else:
                        behind = max(2, min(4, players_alive - 3))
                    risk_premium = min(0.03, rake_rate * 0.2 + 0.003 * behind)
                    if pos_key in ("BU", "SB"):
                        risk_premium = min(0.06, risk_premium + 0.012 + min(0.003, rake_rate * 0.1))
                    cutoff = min(1.0, cutoff + risk_premium)
                    equity_open = equity_eff
                    if opponents_open != max(1, players_alive - 1):
                        equity_open = _equity_from_obs(
                            obs=obs,
                            players_alive=opponents_open + 1,
                            street=snap.get("street"),
                            state_hash=state_hash,
                        )
                        if equity_open is None:
                            equity_open = equity_eff
                    open_mix = _edge_mix(equity_open, cutoff, width=0.02)
                    if open_mix > 0.0:
                        if open_mix >= 1.0 or (_rng_pct(f"open_mix2:{state_hash}:{seat_id}:{pos_key}") / 10000.0) <= open_mix:
                            open_ratio = _open_ratio()
                            bet = _pick_raise_by_bb_ratio(
                                legal,
                                bb=bb,
                                actor_commit=actor_commit,
                                target_bb_ratio=open_ratio,
                            )
                            if bet:
                                return bet
                    chk = _pick_nearest_action(legal, kind="CHECK", target=actor_commit)
                    if chk:
                        return chk
                    fold_act = _pick_nearest_action(legal, kind="FOLD", target=actor_commit)
                    if fold_act:
                        return fold_act
                else:
                    pot_odds = to_call / max(pot_chips + to_call, 1)
                    rake_premium = min(0.05, rake_rate * 0.6 + 0.01 * max(0, opponents - 1))
                    if pos_key == "BB":
                        rake_premium += 0.04
                    if street_raise_count >= 2:
                        rake_premium += 0.05
                    eff_pot_odds = min(0.95, pot_odds + rake_premium)
                    if equity_eff < eff_pot_odds:
                        fold_act = _pick_nearest_action(legal, kind="FOLD", target=actor_commit)
                        if fold_act:
                            return fold_act
                    facing_open = street_raise_count == 1
                    raise_pct = threebet_pct if facing_open else fourbet_pct
                    call_pct_vs_open_eff = call_pct_vs_open
                    if facing_open and pos_key in ("SB", "BB"):
                        call_scale = 0.30 - (0.8 * preflop_defend_tighten) - (3.5 * rake_rate) - (0.05 * max(0, players_alive - 2))
                        call_scale = max(0.10, min(0.60, call_scale))
                        call_pct_vs_open_eff = call_pct_vs_open * call_scale
                    if facing_open and pos_key == "BB" and opener_pos == "SB":
                        sb_open = float(open_pct_sb) if open_pct_sb is not None else 0.45
                        sb_open = max(0.20, min(0.70, sb_open))
                        sb_boost = 1.6 + 0.8 * sb_open
                        raise_pct = min(0.60, raise_pct * sb_boost)
                        call_pct_vs_open_eff *= 0.25
                    call_pct = min(1.0, raise_pct + call_pct_vs_open_eff * (1.0 if facing_open else 0.6))
                    raise_cutoff = _preflop_cutoff(opponents, raise_pct)
                    call_cutoff = _preflop_cutoff(opponents, call_pct)
                    bet = None
                    if facing_open:
                        bet = _pick_raise_by_call_mult(
                            legal,
                            call_target=call_target,
                            target_mult=float(threebet_frac),
                        )
                    else:
                        bet = _pick_raise_by_call_mult(
                            legal,
                            call_target=call_target,
                            target_mult=float(fourbet_frac),
                        )
                    call_act = _pick_nearest_action(legal, kind="CALL", target=call_target)
                    fold_act = _pick_nearest_action(legal, kind="FOLD", target=actor_commit)
                    ev_raise = None
                    if equity_eff >= raise_cutoff and bet:
                        ev_raise = _action_ev(
                            action=bet,
                            equity=equity_eff,
                            pot_chips=pot_chips,
                            actor_commit=actor_commit,
                            to_call=to_call,
                            players_alive=players_alive,
                            street="PREFLOP",
                        )
                    ev_call = None
                    if equity_eff >= call_cutoff and call_act:
                        ev_call = _action_ev(
                            action=call_act,
                            equity=equity_eff,
                            pot_chips=pot_chips,
                            actor_commit=actor_commit,
                            to_call=to_call,
                            players_alive=players_alive,
                            street="PREFLOP",
                        )
                    if (ev_call is not None or ev_raise is not None) and pot_chips is not None:
                        base_rake_pre = estimate_rake(
                            pot_after=float(pot_chips),
                            street="PREFLOP",
                            rake_rate=rake_rate,
                            rake_cap=rake_cap,
                            no_flop_no_drop=no_flop_no_drop,
                        )
                        if ev_call is not None and call_act is not None:
                            exp_rake_call = _expected_rake_for_action(
                                action=call_act,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                street="PREFLOP",
                                defend_rate=None,
                            )
                            call_net = float(ev_call) - max(0.0, float(exp_rake_call) - float(base_rake_pre))
                            if pos_key in ("SB", "BB") and oop_realization_weight > 0 and equity_eff is not None:
                                pot_unit = float(max(1, pot_chips + to_call))
                                spr = None
                                if actor_stack is not None and pot_chips > 0:
                                    spr = float(actor_stack) / float(pot_chips)
                                if spr is None:
                                    spr = 6.0
                                eq_strength = max(0.0, min(1.0, float(equity_eff)))
                                eq_factor = 0.4 + 0.6 * eq_strength
                                spr_factor = 0.25 + 0.05 * max(0.0, min(12.0, spr))
                                rake_factor = 0.6 + 6.0 * rake_rate
                                mw_factor = 1.0 + 0.25 * max(0, players_alive - 2)
                                oop_penalty = pot_unit * oop_realization_weight
                                oop_penalty *= spr_factor * rake_factor * mw_factor * eq_factor
                                call_net -= float(oop_penalty)
                            ev_call = call_net
                            if pos_key in ("SB", "BB") and ev_call <= 0.0:
                                ev_call = None
                                call_act = None
                        if ev_raise is not None and bet is not None:
                            exp_rake_raise = _expected_rake_for_action(
                                action=bet,
                                pot_chips=pot_chips,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive,
                                street="PREFLOP",
                                defend_rate=None,
                            )
                            ev_raise = float(ev_raise) - max(0.0, float(exp_rake_raise) - float(base_rake_pre))
                    # Choose highest EV action (fold = 0).
                    best = ("fold", 0.0)
                    if ev_call is not None and ev_call > best[1]:
                        best = ("call", ev_call)
                    if ev_raise is not None and ev_raise > best[1]:
                        best = ("raise", ev_raise)
                    if best[0] == "raise" and bet:
                        return bet
                    if best[0] == "call" and call_act:
                        return call_act
                    if fold_act:
                        return fold_act
            # Preflop fallback: ensure a decision without legacy heuristics.
            if to_call > 0:
                fold_act = _pick_nearest_action(legal, kind="FOLD", target=actor_commit)
                if fold_act:
                    return fold_act
                call_act = _pick_nearest_action(legal, kind="CALL", target=call_target)
                if call_act:
                    return call_act
            check_act = _pick_nearest_action(legal, kind="CHECK", target=actor_commit)
            if check_act:
                return check_act
            return legal[0]

        # Postflop: call pyo3 solver if possible.
        if snap.get("street") in ("FLOP", "TURN", "RIVER"):
            pot = int(snap.get("pot_chips", 0))
            players = obs.get("seats_in_hand", [])
            players_alive_pf = players_alive
            if not players_alive_pf and isinstance(players, list) and players:
                players_alive_pf = len(players)
            equity_pf = equity if equity is not None and players_alive_pf == players_alive else _equity_from_obs(
                obs=obs,
                players_alive=players_alive_pf,
                street=snap.get("street"),
                state_hash=state_hash,
            )
            actor_stack = int(snap.get("actor_stack_chips", 0))
            spr = actor_stack / pot if pot > 0 else 99.0
            keypot_triggered = False
            if players_alive_pf == 3 and mw_keypot_trigger_bb > 0:
                keypot_threshold = mw_keypot_trigger_bb * max(1, bb)
                if pot >= keypot_threshold and snap.get("street") in ("TURN", "RIVER"):
                    keypot_triggered = True
            last_raiser_map = obs.get("last_raiser_by_street") or {}
            street_raise_count_map = obs.get("street_raise_count") or {}
            prev_street = {"FLOP": "PREFLOP", "TURN": "FLOP", "RIVER": "TURN"}.get(snap.get("street"))
            prev_aggressor = last_raiser_map.get(prev_street) if isinstance(last_raiser_map, dict) else None
            prior_street_aggressor = bool(prev_aggressor == seat_id) if prev_aggressor is not None else False
            street_raise_ct = 0
            if isinstance(street_raise_count_map, dict):
                street_raise_ct = int(street_raise_count_map.get(snap.get("street"), 0) or 0)
            button_seat = int(obs.get("button_seat", seat_id))
            pos_key_post = position_key(seat_id, button_seat, players) if isinstance(players, list) and players else "OTHERS"
            bb_oop_hu = bool(
                pos_key_post == "BB"
                and players_alive_pf == 2
                and prev_aggressor is not None
                and prev_aggressor != seat_id
            )
            oop_aggression_gate = bb_oop_hu
            gate_mw = float(params.get("oop_aggression_gate_mw_bp", 0) or 0) / 10000.0
            gate_spr_bp = params.get("oop_aggression_gate_spr_bp")
            gate_spr = None
            if gate_spr_bp is not None:
                gate_spr = float(gate_spr_bp) / 100.0
            if (
                not oop_aggression_gate
                and gate_mw > 0.0
                and pos_key_post in ("SB", "BB")
                and players_alive_pf >= 3
                and to_call <= 0
            ):
                spr_local = spr if spr is not None else 6.0
                if gate_spr is None or spr_local >= gate_spr:
                    oop_aggression_gate = True
            def _postflop_defend_rate_fn(act: dict[str, Any]) -> float | None:
                base_rate = _opp_defend_rate_for_action(
                    action=act,
                    pot_chips=pot,
                    to_call=to_call,
                    actor_commit=actor_commit,
                    players_alive=players_alive_pf,
                    street=snap.get("street"),
                )
                if base_rate is None:
                    return None
                if (
                    to_call <= 0
                    and pos_key_post in ("SB", "BB")
                    and prev_aggressor is not None
                    and prev_aggressor != seat_id
                ):
                    spr_local = spr if spr is not None else 5.0
                    wet_score = _board_wet_score(board_texture=board_tex, street=snap.get("street"))
                    pressure = _pressure_index(
                        players_alive=players_alive_pf,
                        spr=spr_local,
                        wet_score=wet_score,
                        pos_key=pos_key_post,
                        street=snap.get("street"),
                    )
                    opp_factor = 1.0 + 0.12 * pressure + 0.04 * max(0, players_alive_pf - 2)
                    spr_factor = 1.0 + 0.05 * max(0.0, min(6.0, spr_local - 2.0))
                    wet_factor = 1.0 + 0.04 * max(0, int(wet_score))
                    base_rate = min(1.0, float(base_rate) * opp_factor * spr_factor * wet_factor)
                return float(base_rate)
            equity_pf_eff = equity_pf
            if equity_pf_eff is not None:
                realization = _equity_realization_multiplier(
                    players_alive=players_alive_pf,
                    pos_key=pos_key_post,
                    prev_aggressor=prev_aggressor,
                    street_raise_ct=street_raise_ct,
                    spr=spr,
                    board_texture=board_tex,
                    street=snap.get("street"),
                )
                equity_pf_eff = equity_pf_eff * realization
            entry_pf: dict[str, Any] | None = None
            if players_alive_pf >= 3:
                rung = mw_rung_id or "reducer4p"
                entry_pf = _select_mw_entry(
                    entries=mw_strategy_entries,
                    rung_id=rung,
                    players_alive=players_alive_pf,
                    street=snap.get("street"),
                    facing_bet=to_call > 0,
                    spr=spr,
                )
            legal_pf = legal
            uncertainty_pf: float | None = None
            defend_target: float | None = None
            force_defend: bool | None = None
            if equity_pf_eff is not None:
                uncertainty_pf = _equity_uncertainty_for(
                    equity_val=equity_pf_eff,
                    samples=equity_samples,
                    players_alive=players_alive_pf,
                    board_texture=board_tex,
                    street=snap.get("street"),
                )
            if to_call > 0:
                wet_score = _board_wet_score(board_texture=board_tex, street=snap.get("street"))
                defend_target = _defend_target_rate(
                    to_call=to_call,
                    pot_chips=pot,
                    players_alive=players_alive_pf,
                    pos_key=pos_key_post,
                    spr=spr,
                    wet_score=wet_score,
                    street=snap.get("street"),
                    uncertainty=uncertainty_pf,
                )
                if defend_target is not None and snap.get("street") in ("TURN", "RIVER"):
                    low_spr_threshold = float(params.get("facing_low_spr_threshold_bp", 200)) / 100.0
                    low_spr_threshold = max(0.5, min(10.0, low_spr_threshold))
                    if spr <= low_spr_threshold:
                        defend_scale = float(params.get("facing_low_spr_defend_scale_bp", 10000)) / 10000.0
                        defend_scale = max(0.30, min(1.00, defend_scale))
                        defend_target = max(0.01, min(0.99, float(defend_target) * defend_scale))
                        if facing_high_price_threshold is not None and pot > 0:
                            pot_unit_local = float(max(1, pot + to_call))
                            price = float(to_call) / pot_unit_local
                            threshold2_local = facing_high_price_threshold2
                            if wet_score >= 1:
                                if snap.get("street") == "TURN" and facing_high_price_threshold2_turn_wet is not None:
                                    threshold2_local = facing_high_price_threshold2_turn_wet
                                elif snap.get("street") == "RIVER" and facing_high_price_threshold2_river_wet is not None:
                                    threshold2_local = facing_high_price_threshold2_river_wet
                            if threshold2_local is not None:
                                threshold2_local = max(float(facing_high_price_threshold), float(threshold2_local))
                            if price >= facing_high_price_threshold:
                                firewall_penalty = float(facing_high_price_defend_gap_spr_low_penalty or 0.0)
                                firewall_pressure_boost = 0.0
                                if players_alive_pf >= 3:
                                    firewall_penalty += float(facing_high_price_defend_gap_mw_penalty or 0.0)
                                if wet_score >= 1:
                                    firewall_penalty += float(facing_high_price_defend_gap_wet_penalty or 0.0)
                                    if snap.get("street") == "TURN":
                                        firewall_penalty += float(facing_high_price_defend_gap_turn_penalty or 0.0)
                                if threshold2_local is not None and price >= threshold2_local:
                                    if wet_score >= 1 and snap.get("street") == "TURN" and facing_high_price_defend_gap2_turn_wet is not None:
                                        firewall_penalty = max(firewall_penalty, float(facing_high_price_defend_gap2_turn_wet))
                                    elif wet_score >= 1 and snap.get("street") == "RIVER" and facing_high_price_defend_gap2_river_wet is not None:
                                        firewall_penalty = max(firewall_penalty, float(facing_high_price_defend_gap2_river_wet))
                                    elif facing_high_price_defend_gap2 is not None:
                                        firewall_penalty = max(firewall_penalty, float(facing_high_price_defend_gap2))
                                    threshold2_span = max(0.05, 1.0 - float(threshold2_local))
                                    threshold2_pressure = max(
                                        0.0,
                                        min(1.0, (price - float(threshold2_local)) / threshold2_span),
                                    )
                                    if threshold2_pressure > 0.0:
                                        firewall_pressure_boost = 0.02 + (0.04 * threshold2_pressure)
                                        if wet_score >= 1:
                                            firewall_pressure_boost += 0.01
                                        if snap.get("street") == "RIVER":
                                            firewall_pressure_boost += 0.01
                                        if players_alive_pf >= 3:
                                            firewall_pressure_boost += 0.01
                                        if players_alive_pf >= 4 and wet_score >= 1:
                                            # Pre-arm the stressed multiway TURN/RIVER support lane
                                            # once threshold2 pressure is already live, so the
                                            # existing firewall family produces a visible delta.
                                            support_probe_prearm = 0.01 + (0.03 * threshold2_pressure)
                                            if snap.get("street") == "TURN":
                                                support_probe_prearm += 0.01
                                            if wet_score >= 2:
                                                support_probe_prearm += 0.01
                                            firewall_pressure_boost += min(0.05, support_probe_prearm)
                                            oop_mw_clamp_bridge = max(
                                                0.0,
                                                min(
                                                    0.04,
                                                    (float(facing_high_price_defend_gap_mw_penalty or 0.0) * 0.45)
                                                    + (float(facing_high_price_defend_gap_oop_penalty or 0.0) * 0.45),
                                                ),
                                            )
                                            if snap.get("street") == "TURN":
                                                oop_mw_clamp_bridge += max(
                                                    0.0,
                                                    min(
                                                        0.02,
                                                        float(facing_high_price_defend_gap_spr_mid_penalty or 0.0)
                                                        * 0.30,
                                                    ),
                                                )
                                            else:
                                                oop_mw_clamp_bridge += max(
                                                    0.0,
                                                    min(
                                                        0.02,
                                                        float(facing_high_price_defend_gap_spr_high_penalty or 0.0)
                                                        * 0.25,
                                                    ),
                                                )
                                            oop_mw_clamp_bridge += max(
                                                0.0,
                                                min(0.02, float(retaliation_weight or 0.0) * 0.08),
                                            )
                                            firewall_pressure_boost += min(
                                                0.05,
                                                oop_mw_clamp_bridge * (0.50 + (0.50 * threshold2_pressure)),
                                            )
                                if firewall_penalty > 0.0 or firewall_pressure_boost > 0.0:
                                    effective_firewall_penalty = firewall_penalty + firewall_pressure_boost
                                    firewall_scale = max(0.40, 1.0 - min(0.40, effective_firewall_penalty))
                                    defend_target = max(0.01, min(0.99, float(defend_target) * firewall_scale))

            if keypot_triggered:
                defend_target = None
                force_defend = None

            if players_alive_pf >= 3:
                solver_hint_kind: str | None = None
                solver_hint_target: int | None = None
                solver_call_ev: float | None = None
                solver_raise_ev: float | None = None
                solver_edge: float | None = None
                if keypot_triggered:
                    if raise_cap is not None and min_raise is not None:
                        try:
                            if (int(raise_cap) - int(min_raise)) <= max(bb, to_call) * 2:
                                max_raise_local = None
                                min_raise_local = None
                            else:
                                max_raise_local = max_raise
                                min_raise_local = min_raise
                        except Exception:
                            max_raise_local = max_raise
                            min_raise_local = min_raise
                    else:
                        max_raise_local = max_raise
                        min_raise_local = min_raise
                    solve_payload = {
                        "solver_schema_id": "postflop_solve_v1",
                        "state_hash": state_hash,
                        "street": snap.get("street"),
                        "pot_chips": pot,
                        "to_call_chips": to_call,
                        "actor_stack_chips": int(snap.get("actor_stack_chips", 0)),
                        "actor_commit_chips": actor_commit,
                        "min_raise_to_chips": min_raise_local,
                        "max_raise_to_chips": max_raise_local,
                        "legal_actions": legal_pf,
                        "equity_ppm": int(max(0.0, min(1.0, float(equity_pf_eff))) * 1_000_000)
                        if equity_pf_eff is not None
                        else None,
                        "players_alive": int(players_alive_pf),
                        "rake_rate_ppm": int(max(0.0, min(1.0, rake_rate)) * 1_000_000),
                        "rake_cap_chips": rake_cap,
                        "no_flop_no_drop": bool(no_flop_no_drop),
                    }
                    try:
                        sol = solve_postflop_pyo3(
                            src_root=solver_root,
                            solve_payload=solve_payload,
                            solver_build_id=solver_build_id,
                            strict_mode=strict_mode,
                            timeout_seconds=0.2,
                        )
                        suggested = sol.get("suggested_action")
                        if to_call > 0 and suggested == "CALL":
                            call_act = _pick_nearest_action(legal_pf, kind="CALL", target=call_target)
                            if call_act:
                                return _finalize_postflop_action(
                                    call_act,
                                    legal_actions=legal_pf,
                                    equity_val=equity_pf_eff,
                                    uncertainty_val=uncertainty_pf,
                                    defend_target=defend_target,
                                    pos_key=pos_key_post,
                                    pot=pot,
                                    to_call=to_call,
                                    players_alive=players_alive_pf,
                                    street=snap.get("street"),
                                    force_defend=force_defend,
                                )
                        if to_call == 0 and suggested == "CHECK":
                            check_act = _pick_nearest_action(legal_pf, kind="CHECK", target=actor_commit)
                            if check_act:
                                return _finalize_postflop_action(
                                    check_act,
                                    legal_actions=legal_pf,
                                    equity_val=equity_pf_eff,
                                    uncertainty_val=uncertainty_pf,
                                    defend_target=defend_target,
                                    pos_key=pos_key_post,
                                    pot=pot,
                                    to_call=to_call,
                                    players_alive=players_alive_pf,
                                    street=snap.get("street"),
                                    force_defend=force_defend,
                                )
                        target = int(sol.get("target_total_commit_chips"))
                        bet = _pick_nearest_action(legal_pf, kind="RAISE", target=target) or _pick_nearest_action(
                            legal_pf, kind="BET", target=target
                        )
                        if bet:
                            return _finalize_postflop_action(
                                bet,
                                legal_actions=legal_pf,
                                equity_val=equity_pf_eff,
                                uncertainty_val=uncertainty_pf,
                                defend_target=defend_target,
                                pos_key=pos_key_post,
                                pot=pot,
                                to_call=to_call,
                                players_alive=players_alive_pf,
                                street=snap.get("street"),
                                force_defend=force_defend,
                            )
                    except Exception:
                        if strict_mode:
                            raise
                entry = entry_pf
                if equity_pf_eff is not None:
                    ev_slack = max(1.0, float(to_call) * 0.08, float(pot) * 0.02)
                    action = _choose_action_by_ev(
                        legal_actions=legal_pf,
                        equity=equity_pf_eff,
                        pot_chips=pot,
                        actor_commit=actor_commit,
                        to_call=to_call,
                        stack_chips=actor_stack,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        state_hash=state_hash,
                        entry=entry,
                        facing_bet=to_call > 0,
                        solver_hint_kind=solver_hint_kind,
                        solver_hint_target=solver_hint_target,
                        solver_call_ev=solver_call_ev,
                        solver_raise_ev=solver_raise_ev,
                        solver_edge=solver_edge,
                        ev_slack=ev_slack,
                        uncertainty=uncertainty_pf,
                        defend_rate_fn=_postflop_defend_rate_fn,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        prior_street_aggressor=prior_street_aggressor,
                        oop_aggression_gate=oop_aggression_gate,
                        force_defend=force_defend,
                        board_texture=board_tex,
                        adaptive_profile=adaptive_profile_runtime,
                    )
                    if action is not None:
                        return _finalize_postflop_action(
                            action,
                            legal_actions=legal_pf,
                            equity_val=equity_pf_eff,
                            uncertainty_val=uncertainty_pf,
                            defend_target=defend_target,
                            pos_key=pos_key_post,
                            pot=pot,
                            to_call=to_call,
                            players_alive=players_alive_pf,
                            street=snap.get("street"),
                            force_defend=force_defend,
                        )
                action = _mw_action_from_entry(
                    entry,
                    facing_bet=to_call > 0,
                    players_alive=players_alive_pf,
                    pot_chips=pot,
                    to_call=to_call,
                    actor_commit=actor_commit,
                    actor_stack=actor_stack,
                    call_target=call_target,
                    spr=spr,
                    state_hash=state_hash,
                    legal_actions=legal_pf,
                )
                if action is not None:
                    return _finalize_postflop_action(
                        action,
                        legal_actions=legal_pf,
                        equity_val=equity_pf_eff,
                        uncertainty_val=uncertainty_pf,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        pot=pot,
                        to_call=to_call,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        force_defend=force_defend,
                    )
                if equity_pf_eff is not None:
                    ev_slack = max(1.0, float(to_call) * 0.08, float(pot) * 0.02)
                    prior_weights = _postflop_prior_weights(
                        to_call=to_call,
                        pot_chips=pot,
                        pos_key=pos_key_post,
                        prev_aggressor=prev_aggressor,
                        spr=spr,
                        board_texture=board_tex,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        uncertainty=uncertainty_pf,
                    )
                    action = _choose_action_by_ev(
                        legal_actions=legal_pf,
                        equity=equity_pf_eff,
                        pot_chips=pot,
                        actor_commit=actor_commit,
                        to_call=to_call,
                        stack_chips=actor_stack,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        state_hash=state_hash,
                        entry=None,
                        facing_bet=to_call > 0,
                        solver_hint_kind=solver_hint_kind,
                        solver_hint_target=solver_hint_target,
                        solver_call_ev=solver_call_ev,
                        solver_raise_ev=solver_raise_ev,
                        solver_edge=solver_edge,
                        prior_weights=prior_weights,
                        ev_slack=ev_slack,
                        min_ev_for_priors=-ev_slack,
                        uncertainty=uncertainty_pf,
                        defend_rate_fn=_postflop_defend_rate_fn,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        prior_street_aggressor=prior_street_aggressor,
                        oop_aggression_gate=oop_aggression_gate,
                        force_defend=force_defend,
                        board_texture=board_tex,
                        adaptive_profile=adaptive_profile_runtime,
                    )
                    if action is not None:
                        return _finalize_postflop_action(
                            action,
                            legal_actions=legal_pf,
                            equity_val=equity_pf_eff,
                            uncertainty_val=uncertainty_pf,
                            defend_target=defend_target,
                            pos_key=pos_key_post,
                            pot=pot,
                            to_call=to_call,
                            players_alive=players_alive_pf,
                            street=snap.get("street"),
                            force_defend=force_defend,
                        )
                if to_call == 0:
                    check_act = _pick_nearest_action(legal_pf, kind="CHECK", target=actor_commit)
                    if check_act:
                        return _finalize_postflop_action(
                            check_act,
                            legal_actions=legal_pf,
                            equity_val=equity_pf_eff,
                            uncertainty_val=uncertainty_pf,
                            defend_target=defend_target,
                            pos_key=pos_key_post,
                            pot=pot,
                            to_call=to_call,
                            players_alive=players_alive_pf,
                            street=snap.get("street"),
                            force_defend=force_defend,
                        )
                call_act = _pick_nearest_action(legal_pf, kind="CALL", target=call_target)
                if call_act:
                    return _finalize_postflop_action(
                        call_act,
                        legal_actions=legal_pf,
                        equity_val=equity_pf_eff,
                        uncertainty_val=uncertainty_pf,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        pot=pot,
                        to_call=to_call,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        force_defend=force_defend,
                    )
                fold_act = _pick_nearest_action(legal_pf, kind="FOLD", target=actor_commit)
                if fold_act:
                    return _finalize_postflop_action(
                        fold_act,
                        legal_actions=legal_pf,
                        equity_val=equity_pf_eff,
                        uncertainty_val=uncertainty_pf,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        pot=pot,
                        to_call=to_call,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        force_defend=force_defend,
                    )
            else:
                # HU/short-handed: keep solver + cautious raise sizing。
                # Avoid raises when raise cap is tight relative to min raise (compressed space).
                if raise_cap is not None and min_raise is not None:
                    try:
                        if (int(raise_cap) - int(min_raise)) <= max(bb, to_call) * 2:
                            max_raise_local = None
                            min_raise_local = None
                        else:
                            max_raise_local = max_raise
                            min_raise_local = min_raise
                    except Exception:
                        max_raise_local = max_raise
                        min_raise_local = min_raise
                else:
                    max_raise_local = max_raise
                    min_raise_local = min_raise
                solve_payload = {
                    "solver_schema_id": "postflop_solve_v1",
                    "state_hash": state_hash,
                    "street": snap.get("street"),
                    "pot_chips": pot,
                    "to_call_chips": to_call,
                    "actor_stack_chips": int(snap.get("actor_stack_chips", 0)),
                    "actor_commit_chips": actor_commit,
                    "min_raise_to_chips": min_raise_local,
                    "max_raise_to_chips": max_raise_local,
                    "legal_actions": legal_pf,
                    "equity_ppm": int(max(0.0, min(1.0, float(equity_pf_eff))) * 1_000_000)
                    if equity_pf_eff is not None
                    else None,
                    "players_alive": int(players_alive_pf),
                    "rake_rate_ppm": int(max(0.0, min(1.0, rake_rate)) * 1_000_000),
                    "rake_cap_chips": rake_cap,
                    "no_flop_no_drop": bool(no_flop_no_drop),
                }
                solver_hint_kind: str | None = None
                solver_hint_target: int | None = None
                solver_call_ev: float | None = None
                solver_raise_ev: float | None = None
                solver_edge: float | None = None
                try:
                    sol = solve_postflop_pyo3(
                        src_root=solver_root,
                        solve_payload=solve_payload,
                        solver_build_id=solver_build_id,
                        strict_mode=strict_mode,
                        timeout_seconds=0.2,
                    )
                    # Expect solver to return recommended target_total_commit_chips (int)
                    target = int(sol.get("target_total_commit_chips"))
                    suggested = sol.get("suggested_action")
                    if to_call > 0 and suggested == "CALL":
                        call_act = _pick_nearest_action(legal_pf, kind="CALL", target=call_target)
                        if call_act:
                            return _finalize_postflop_action(
                                call_act,
                                legal_actions=legal_pf,
                                equity_val=equity_pf_eff,
                                uncertainty_val=uncertainty_pf,
                                defend_target=defend_target,
                                pos_key=pos_key_post,
                                pot=pot,
                                to_call=to_call,
                                players_alive=players_alive_pf,
                                street=snap.get("street"),
                                force_defend=force_defend,
                            )
                    if to_call == 0 and suggested == "CHECK":
                        check_act = _pick_nearest_action(legal_pf, kind="CHECK", target=actor_commit)
                        if check_act:
                            return _finalize_postflop_action(
                                check_act,
                                legal_actions=legal_pf,
                                equity_val=equity_pf_eff,
                                uncertainty_val=uncertainty_pf,
                                defend_target=defend_target,
                                pos_key=pos_key_post,
                                pot=pot,
                                to_call=to_call,
                                players_alive=players_alive_pf,
                                street=snap.get("street"),
                                force_defend=force_defend,
                            )
                    if equity_pf_eff is not None and isinstance(suggested, str):
                        if suggested in ("CALL", "CHECK") and to_call > 0:
                            solver_hint_kind = "CALL"
                            solver_hint_target = call_target
                        elif suggested in ("RAISE", "BET") and to_call > 0:
                            solver_hint_kind = "RAISE"
                            solver_hint_target = target
                    try:
                        if sol.get("call_ev") is not None:
                            solver_call_ev = float(sol.get("call_ev"))
                        if sol.get("raise_ev") is not None:
                            solver_raise_ev = float(sol.get("raise_ev"))
                        if sol.get("raise_edge") is not None:
                            solver_edge = float(sol.get("raise_edge"))
                    except Exception:
                        solver_call_ev = None
                        solver_raise_ev = None
                        solver_edge = None
                    bet = _pick_nearest_action(legal_pf, kind="RAISE", target=target) or _pick_nearest_action(
                        legal_pf, kind="BET", target=target
                    )
                    if bet:
                        if to_call > 0 and equity_pf_eff is not None and solver_hint_kind is None:
                            if target == call_target:
                                solver_hint_kind = "CALL"
                                solver_hint_target = call_target
                            else:
                                solver_hint_kind = "RAISE"
                                solver_hint_target = target
                        elif to_call <= 0:
                            solver_hint_kind = None
                            solver_hint_target = None
                        if (
                            solver_hint_kind is None
                            and to_call <= 0
                            and pos_key_post in ("SB", "BB")
                            and prev_aggressor is not None
                            and prev_aggressor != seat_id
                            and equity_pf_eff is not None
                        ):
                            check_act = _pick_nearest_action(legal_pf, kind="CHECK", target=actor_commit)
                            if check_act is not None:
                                try:
                                    def_rate = _postflop_defend_rate_fn(bet)
                                    bet_ev = _action_ev(
                                        action=bet,
                                        equity=equity_pf_eff,
                                        pot_chips=pot,
                                        actor_commit=actor_commit,
                                        to_call=to_call,
                                        players_alive=players_alive_pf,
                                        street=snap.get("street"),
                                        defend_rate=def_rate,
                                    )
                                    check_ev = _action_ev(
                                        action=check_act,
                                        equity=equity_pf_eff,
                                        pot_chips=pot,
                                        actor_commit=actor_commit,
                                        to_call=to_call,
                                        players_alive=players_alive_pf,
                                        street=snap.get("street"),
                                        defend_rate=None,
                                    )
                                    base_rake = estimate_rake(
                                        pot_after=float(pot),
                                        street=snap.get("street"),
                                        rake_rate=rake_rate,
                                        rake_cap=rake_cap,
                                        no_flop_no_drop=no_flop_no_drop,
                                    )
                                    exp_rake_bet = _expected_rake_for_action(
                                        action=bet,
                                        pot_chips=pot,
                                        actor_commit=actor_commit,
                                        to_call=to_call,
                                        players_alive=players_alive_pf,
                                        street=snap.get("street"),
                                        defend_rate=def_rate,
                                    )
                                    delta_rake = max(0.0, float(exp_rake_bet) - float(base_rake))
                                    pot_unit = max(1.0, float(pot))
                                    bet_size = max(1, int(bet.get("target_total_commit_chips", actor_commit)) - actor_commit)
                                    spr_local = (float(actor_stack) / float(pot)) if pot > 0 else 6.0
                                    wet_score = _board_wet_score(board_texture=board_tex, street=snap.get("street"))
                                    pressure = _pressure_index(
                                        players_alive=players_alive_pf,
                                        spr=spr_local,
                                        wet_score=wet_score,
                                        pos_key=pos_key_post,
                                        street=snap.get("street"),
                                    )
                                    risk_scale = 0.60 + 0.40 * pressure
                                    spr_scale = 1.0 + 0.10 * max(0.0, min(6.0, spr_local - 2.0))
                                    probe_cost = float(bet_size) * oop_realization_weight * risk_scale * spr_scale
                                    bet_ev_adj = float(bet_ev) - float(delta_rake) - float(probe_cost)
                                    margin = max(1.0, pot_unit * (0.02 + 0.4 * rake_rate))
                                    if bet_ev_adj < (float(check_ev) + margin):
                                        return _finalize_postflop_action(
                                            check_act,
                                            legal_actions=legal_pf,
                                            equity_val=equity_pf_eff,
                                            uncertainty_val=uncertainty_pf,
                                            defend_target=defend_target,
                                            pos_key=pos_key_post,
                                            pot=pot,
                                            to_call=to_call,
                                            players_alive=players_alive_pf,
                                            street=snap.get("street"),
                                            force_defend=force_defend,
                                        )
                                except Exception:
                                    if strict_mode:
                                        raise
                        if bb_oop_hu and snap.get("street") in ("FLOP", "TURN", "RIVER"):
                            if not _raise_value_ok_for_action(
                                action=bet,
                                equity_strength=equity_pf_eff,
                                pot_chips=pot,
                                actor_commit=actor_commit,
                                to_call=to_call,
                                players_alive=players_alive_pf,
                                street=snap.get("street"),
                            ):
                                fallback = None
                                if to_call > 0:
                                    fallback = _pick_nearest_action(legal_pf, kind="CALL", target=call_target)
                                else:
                                    fallback = _pick_nearest_action(legal_pf, kind="CHECK", target=actor_commit)
                                if fallback:
                                    return _finalize_postflop_action(
                                        fallback,
                                        legal_actions=legal_pf,
                                        equity_val=equity_pf_eff,
                                        uncertainty_val=uncertainty_pf,
                                        defend_target=defend_target,
                                        pos_key=pos_key_post,
                                        pot=pot,
                                        to_call=to_call,
                                        players_alive=players_alive_pf,
                                        street=snap.get("street"),
                                        force_defend=force_defend,
                                    )
                        if solver_hint_kind is None:
                            return _finalize_postflop_action(
                                bet,
                                legal_actions=legal_pf,
                                equity_val=equity_pf_eff,
                                uncertainty_val=uncertainty_pf,
                                defend_target=defend_target,
                                pos_key=pos_key_post,
                                pot=pot,
                                to_call=to_call,
                                players_alive=players_alive_pf,
                                street=snap.get("street"),
                                force_defend=force_defend,
                            )
                except Exception:
                    if strict_mode:
                        raise
                    # fall through to heuristic below
                if equity_pf_eff is not None:
                    ev_slack = max(1.0, float(to_call) * 0.08, float(pot) * 0.02)
                    prior_weights = _postflop_prior_weights(
                        to_call=to_call,
                        pot_chips=pot,
                        pos_key=pos_key_post,
                        prev_aggressor=prev_aggressor,
                        spr=spr,
                        board_texture=board_tex,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        uncertainty=uncertainty_pf,
                    )
                    action = _choose_action_by_ev(
                        legal_actions=legal_pf,
                        equity=equity_pf_eff,
                        pot_chips=pot,
                        actor_commit=actor_commit,
                        to_call=to_call,
                        stack_chips=actor_stack,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        state_hash=state_hash,
                        entry=None,
                        facing_bet=to_call > 0,
                        prior_weights=prior_weights,
                        ev_slack=ev_slack,
                        min_ev_for_priors=-ev_slack,
                        uncertainty=uncertainty_pf,
                        defend_rate_fn=_postflop_defend_rate_fn,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        prior_street_aggressor=prior_street_aggressor,
                        oop_aggression_gate=oop_aggression_gate,
                        force_defend=force_defend,
                        board_texture=board_tex,
                        solver_hint_kind=solver_hint_kind,
                        solver_hint_target=solver_hint_target,
                        solver_call_ev=solver_call_ev,
                        solver_raise_ev=solver_raise_ev,
                        solver_edge=solver_edge,
                        adaptive_profile=adaptive_profile_runtime,
                    )
                    if action is not None:
                        return _finalize_postflop_action(
                            action,
                            legal_actions=legal_pf,
                            equity_val=equity_pf_eff,
                            uncertainty_val=uncertainty_pf,
                            defend_target=defend_target,
                            pos_key=pos_key_post,
                            pot=pot,
                            to_call=to_call,
                            players_alive=players_alive_pf,
                            street=snap.get("street"),
                            force_defend=force_defend,
                        )
                # HU/3-way heuristic：smaller sizing and limited raises
                if spr > 6:
                    frac_num, frac_den = 2, 9  # ~0.22 pot
                elif spr > 3:
                    frac_num, frac_den = 3, 10  # 0.3 pot
                else:
                    frac_num, frac_den = 1, 2  # 0.5 pot
                candidates = _raise_candidates(legal_pf)
                # reduce raise frequency: only 35% chance to raise, else call.
                if candidates:
                    desired_frac = float(frac_num) / float(frac_den)
                    best_raise = _pick_raise_by_pot_frac(
                        candidates,
                        pot=pot,
                        call_target=call_target,
                        target_frac=desired_frac,
                    )
                    if best_raise and (_rng_pct(f"raise_pref:{state_hash}:{seat_id}:{pot}") % 100) < 55:
                        return _finalize_postflop_action(
                            best_raise,
                            legal_actions=legal_pf,
                            equity_val=equity_pf_eff,
                            uncertainty_val=uncertainty_pf,
                            defend_target=defend_target,
                            pos_key=pos_key_post,
                            pot=pot,
                            to_call=to_call,
                            players_alive=players_alive_pf,
                            street=snap.get("street"),
                            force_defend=force_defend,
                        )
                # default to call/check after limiting raises
                call_act = _pick_nearest_action(legal_pf, kind="CALL", target=call_target)
                if call_act:
                    return _finalize_postflop_action(
                        call_act,
                        legal_actions=legal_pf,
                        equity_val=equity_pf_eff,
                        uncertainty_val=uncertainty_pf,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        pot=pot,
                        to_call=to_call,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        force_defend=force_defend,
                    )
                check_act = _pick_nearest_action(legal_pf, kind="CHECK", target=actor_commit)
                if check_act:
                    return _finalize_postflop_action(
                        check_act,
                        legal_actions=legal_pf,
                        equity_val=equity_pf_eff,
                        uncertainty_val=uncertainty_pf,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        pot=pot,
                        to_call=to_call,
                        players_alive=players_alive_pf,
                        street=snap.get("street"),
                        force_defend=force_defend,
                    )

        def _finalize_postflop_fallback(action: dict[str, Any] | None) -> dict[str, Any] | None:
            if action is None:
                return None
            if snap.get("street") not in ("FLOP", "TURN", "RIVER"):
                return action
            pot = int(snap.get("pot_chips", 0))
            players = obs.get("seats_in_hand", [])
            players_alive_pf = players_alive
            if not players_alive_pf and isinstance(players, list) and players:
                players_alive_pf = len(players)
            equity_pf = equity if equity is not None and players_alive_pf == players_alive else _equity_from_obs(
                obs=obs,
                players_alive=players_alive_pf,
                street=snap.get("street"),
                state_hash=state_hash,
            )
            actor_stack = int(snap.get("actor_stack_chips", 0))
            spr = actor_stack / pot if pot > 0 else 99.0
            last_raiser_map = obs.get("last_raiser_by_street") or {}
            street_raise_count_map = obs.get("street_raise_count") or {}
            prev_street = {"FLOP": "PREFLOP", "TURN": "FLOP", "RIVER": "TURN"}.get(snap.get("street"))
            prev_aggressor = last_raiser_map.get(prev_street) if isinstance(last_raiser_map, dict) else None
            street_raise_ct = 0
            if isinstance(street_raise_count_map, dict):
                street_raise_ct = int(street_raise_count_map.get(snap.get("street"), 0) or 0)
            button_seat = int(obs.get("button_seat", seat_id))
            pos_key_post = position_key(seat_id, button_seat, players) if isinstance(players, list) and players else "OTHERS"
            equity_pf_eff = equity_pf
            if equity_pf_eff is not None:
                realization = _equity_realization_multiplier(
                    players_alive=players_alive_pf,
                    pos_key=pos_key_post,
                    prev_aggressor=prev_aggressor,
                    street_raise_ct=street_raise_ct,
                    spr=spr,
                    board_texture=board_tex,
                    street=snap.get("street"),
                )
                equity_pf_eff = equity_pf_eff * realization
            uncertainty_pf: float | None = None
            defend_target: float | None = None
            force_defend: bool | None = None
            if equity_pf_eff is not None:
                uncertainty_pf = _equity_uncertainty_for(
                    equity_val=equity_pf_eff,
                    samples=equity_samples,
                    players_alive=players_alive_pf,
                    board_texture=board_tex,
                    street=snap.get("street"),
                )
            if to_call > 0:
                wet_score = _board_wet_score(board_texture=board_tex, street=snap.get("street"))
                defend_target = _defend_target_rate(
                    to_call=to_call,
                    pot_chips=pot,
                    players_alive=players_alive_pf,
                    pos_key=pos_key_post,
                    spr=spr,
                    wet_score=wet_score,
                    street=snap.get("street"),
                    uncertainty=uncertainty_pf,
                )
                p_defend = max(0.0, min(1.0, float(defend_target)))
                salt = f"defend_mix:{state_hash}:{snap.get('street')}:{pos_key_post}:{pot}:{to_call}"
                force_defend = (_rng_pct(salt) / 10000.0) < p_defend
            return _finalize_postflop_action(
                action,
                legal_actions=legal,
                equity_val=equity_pf_eff,
                uncertainty_val=uncertainty_pf,
                defend_target=defend_target,
                pos_key=pos_key_post,
                pot=pot,
                to_call=to_call,
                players_alive=players_alive_pf,
                street=snap.get("street"),
                force_defend=force_defend,
            )

        fold_post = _finalize_postflop_fallback(_maybe_fold("postflop"))
        if fold_post:
            return fold_post

        call_act = _finalize_postflop_fallback(_pick_nearest_action(legal, kind="CALL", target=call_target))
        if call_act:
            return call_act
        check_act = _finalize_postflop_fallback(_pick_nearest_action(legal, kind="CHECK", target=actor_commit))
        if check_act:
            return check_act
        fold_act = _finalize_postflop_fallback(_pick_nearest_action(legal, kind="FOLD", target=actor_commit))
        if fold_act:
            return fold_act
        return _finalize_postflop_fallback(legal[0]) or legal[0]

    extra_meta: dict[str, Any] = {
        "postflop_ref": postflop_ref,
        "preflop_ref": preflop_ref,
        "preflop_ranges_ref": preflop_ranges_ref,
        "mw_strategy_ref": mw_strategy_ref,
        "treepath_mapping_spec_id": mapping_spec_id,
        "opponent_pool_ref": opponent_pool_ref,
        "spot_policy_ref": spot_policy_ref if isinstance(spot_policy_ref, str) else None,
        "spot_policy_digest": spot_policy_digest_obj if isinstance(spot_policy_digest_obj, dict) else None,
        "hu_rollout_enable_bp": int(round(hu_rollout_enable * 10000)),
        "hu_rollout_turn_enable_bp": int(round(hu_rollout_turn_enable * 10000)),
        "hu_rollout_samples": int(hu_rollout_samples),
        "hu_rollout_std_beta_bp": int(round(hu_rollout_beta * 10000)),
        "adaptation_digest": adaptation_digest,
    }
    # If the solver root is provided in paths_trace, compute solver_build_id for provenance.
    try:
        solver_root = postflop_solver_src_root_from_paths_trace(paths_trace)
        solver_build_id_actual = compute_postflop_solver_build_id(src_root=solver_root, strict_mode=strict_mode)  # pragma: no cover - metadata only
        extra_meta["solver_build_id"] = fixed_solver_build_id or solver_build_id_actual  # pragma: no cover - metadata only
        if fixed_solver_build_id and solver_build_id_actual != fixed_solver_build_id:
            extra_meta["solver_build_id_actual"] = solver_build_id_actual  # pragma: no cover - metadata only
    except Exception:
        # No solver root available; leave metadata minimal.
        pass

    return _policy, extra_meta
