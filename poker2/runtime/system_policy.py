from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import bisect
import hashlib
import math
from pathlib import Path
import random
from typing import Any, Callable

from poker2.contractkit import validate_digest_object
from poker2.engines.postflop_solver import compute_postflop_solver_build_id, postflop_solver_src_root_from_paths_trace
from poker2.engines.postflop_pyo3 import solve_postflop_pyo3
from poker2.runtime.artifact_store import ArtifactStoreError, resolve_artifact_path
from poker2.runtime.ev_core import action_ev, equity_uncertainty, estimate_rake
from poker2.runtime.hand_eval import board_texture, estimate_equity, parse_card_token
from poker2.protocol.treepath_mapping import (
    default_internal_treepath_mapping_spec,
    position_key,
    pot_fracs,
    preflop_size_plan,
    parse_size_fraction,
)

PolicyFn = Callable[[dict[str, Any]], dict[str, Any]]


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


def _load_preflop_freq(path: Path) -> dict[str, Any]:
    import json

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover - IO/parse errors
        raise SystemPolicyError("PREFLOP_FREQ_READ_FAIL", "failed to read preflop freq artifact", {"path": str(path), "error": str(e)})
    if not isinstance(obj, dict) or obj.get("schema_id") != "preflop_freq_v1":
        raise SystemPolicyError("PREFLOP_FREQ_SCHEMA", "preflop freq schema_id mismatch", {"path": str(path)})
    positions = obj.get("positions")
    if not isinstance(positions, dict):
        raise SystemPolicyError("PREFLOP_FREQ_SHAPE", "preflop freq positions must be object", {"path": str(path)})
    return positions


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


def _load_system_params(path: Path) -> dict[str, int]:
    import json

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover - IO/parse errors
        raise SystemPolicyError("PARAMS_READ_FAIL", "failed to read system bot params", {"path": str(path), "error": str(e)})
    if not isinstance(obj, dict):
        raise SystemPolicyError("PARAMS_SHAPE", "system bot params must be object", {"path": str(path)})
    params: dict[str, int] = {}
    for key in (
        "safe_exploit_max_bp",
        "rake_delta_weight_bp",
        "mw_risk_weight_bp",
        "oop_risk_weight_bp",
        "oop_realization_weight_bp",
        "oop_spr_threshold_bp",
        "preflop_defend_tighten_bp",
        "mw_keypot_trigger_bb",
    ):
        val = obj.get(key)
        if isinstance(val, int):
            params[key] = val
    return params


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
    preflop_freq_ref = next((ref for ref in resolved if ref.startswith("path:") and "preflop_freq" in ref), None)
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
        freq_positions = _load_preflop_freq(resolved[preflop_freq_ref])

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
    params: dict[str, int] = {}
    if params_ref is not None:
        params = _load_system_params(resolved[params_ref])

    safe_exploit_max = max(0.0, min(0.20, float(params.get("safe_exploit_max_bp", 500)) / 10000.0))
    rake_delta_weight = max(0.0, min(2.0, float(params.get("rake_delta_weight_bp", 350)) / 10000.0))
    mw_risk_weight = max(0.0, min(1.0, float(params.get("mw_risk_weight_bp", 40)) / 10000.0))
    oop_risk_weight = max(0.0, min(1.0, float(params.get("oop_risk_weight_bp", 60)) / 10000.0))
    oop_realization_bp = params.get("oop_realization_weight_bp")
    if oop_realization_bp is None:
        oop_realization_weight = 0.0
    else:
        oop_realization_weight = max(0.0, min(0.05, float(oop_realization_bp) / 10000.0))
    oop_spr_threshold = max(1.0, min(10.0, float(params.get("oop_spr_threshold_bp", 350)) / 100.0))
    preflop_defend_tighten = max(0.05, min(0.50, float(params.get("preflop_defend_tighten_bp", 1800)) / 10000.0))
    mw_keypot_trigger_bb = max(0, int(params.get("mw_keypot_trigger_bb", 40)))

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
        prior_strength = 8.0
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

    equity_cache: dict[tuple, float] = {}
    preflop_equity_dist: dict[int, list[float]] = {}

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
        if cached is not None:
            return cached
        seed_hex = (state_hash or "")[:16]
        try:
            seed = int(seed_hex, 16) ^ (seat_id << 4) ^ (players_alive << 8)
        except Exception:
            seed = 0xC0FFEE ^ (seat_id << 4) ^ (players_alive << 8)
        eq = estimate_equity(hero_hole=hole, board=board, opponents=opponents, samples=samples, seed=seed)
        if len(equity_cache) > 2048:
            equity_cache.pop(next(iter(equity_cache)))
        equity_cache[key] = eq
        if return_samples:
            return (eq, samples)
        return eq

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
        spr = None
        if stack_chips is not None and pot_chips > 0:
            spr = float(stack_chips) / float(pot_chips)
        wet_score = _board_wet_score(board_texture=board_texture, street=street)
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
            facing = to_call > 0
            large_bias = 0.20 + 0.80 * max(0.0, eq_strength - 0.55)
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
    ) -> dict[str, Any] | None:
        if not legal_actions:
            return None
        trace_active = bool(facing_bet and to_call > 0 and pos_key in ("SB", "BB"))
        defense_trace: dict[str, Any] = {}
        actions_pool = legal_actions
        if facing_bet and to_call > 0 and street in ("FLOP", "TURN", "RIVER") and pos_key is not None:
            defend_actions = [a for a in legal_actions if str(a.get("kind")) in ("CALL", "RAISE", "BET", "ALLIN")]
            fold_actions = [a for a in legal_actions if str(a.get("kind")) == "FOLD"]
            if force_defend is True:
                if defend_actions:
                    actions_pool = defend_actions
            elif force_defend is False:
                if fold_actions:
                    actions_pool = fold_actions
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
            score = ev - (unc * ((float(risk) * risk_scale) + float(delta_rake))) - rake_penalty - mw_penalty - oop_penalty - oop_realization_penalty - oop_call_penalty - oop_ms_penalty
            if facing_bet and kind in ("RAISE", "BET", "ALLIN"):
                raise_toll = float(delta_rake) * (0.4 + 0.2 * max(0, players_alive - 2))
                raise_toll += float(risk) * 0.02
                if signal > 0.0:
                    raise_toll *= max(0.5, 1.0 - 1.2 * signal)
                score -= raise_toll
            if prior_weights is not None:
                prior_prob = max(0.0, min(1.0, float(prior_weights.get(kind, 0)) / 10000.0))
                prior_reg = max(0.0, 0.12 - safe_exploit_max)
                score -= float(pot_unit) * prior_reg * (1.0 - prior_prob)
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
                            if street == "RIVER" and not value_ok:
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
            nonlocal defend_target
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
                        else:
                            base_prem = 0.015
                            price_factor = 0.18
                        prem = float(pot_unit) * (base_prem + price_factor * price + 0.05 * mw)
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
                    if street in ("TURN", "RIVER"):
                        price = float(to_call) / max(1.0, float(pot_unit))
                        edge_adj = float(call_edge_ratio) - (0.03 + 0.08 * price)
                        pref_sig = 1.0 / (1.0 + math.exp(-5.0 * edge_adj))
                        call_pref = max(0.03, min(0.95, pref_sig ** 1.8))
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
                    edge = float(ev_edge) - float(call_ev_ref) - delta_rake - oop_cost
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
                    cap *= spr_penalty * mw_penalty * oop_penalty
                    return max(0.01, min(0.70, cap))

                raise_metrics_by_id: dict[int, tuple[float, float, float]] = {}
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
                    base = max(0.01, (score - min_score) + 1.0)
                    ev_use = _solver_ev_for_action(act, _ev)
                    if solver_hint_kind is not None and kind == solver_hint_kind:
                        hint_target = solver_hint_target if solver_hint_target is not None else int(act.get("target_total_commit_chips", actor_commit))
                        act_target = int(act.get("target_total_commit_chips", actor_commit))
                        dist = abs(float(act_target) - float(hint_target)) / max(1.0, float(pot_unit))
                        solver_closeness = 1.0 / (1.0 + dist)
                        base *= 1.0 + 0.6 * solver_closeness
                    if kind in ("RAISE", "BET", "ALLIN") and solver_hint_target is not None and solver_hint_kind == "RAISE":
                        act_target = int(act.get("target_total_commit_chips", actor_commit))
                        dist = abs(float(act_target) - float(solver_hint_target)) / max(1.0, float(pot_unit))
                        size_penalty = 1.0 / (1.0 + (4.5 * dist))
                        base *= 0.35 + 0.65 * size_penalty
                    if facing_bet and defend_target is not None:
                        edge_bias = 0.0
                        if solver_edge is not None and not use_solver_ev:
                            edge_bias += float(solver_edge)
                        if call_ev_ref is not None:
                            edge_bias += float(ev_use) - float(call_ev_ref)
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
                                    adj = float(call_pref) ** 1.8
                                    base *= 0.15 + 0.85 * adj
                                if call_net_dominated and street in ("TURN", "RIVER"):
                                    base *= 0.25
                            elif kind in ("RAISE", "BET", "ALLIN"):
                                if solver_hint_kind == "CALL":
                                    base *= 0.60
                                elif solver_hint_kind == "RAISE":
                                    base *= 1.10
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
                            risk_weight = 1.0 / (1.0 + math.exp(-3.0 * edge_per_risk))
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
                            raise_cap_marginal = _raise_mix_cap_from_edge(
                                float(edge_ratio_source),
                                unc=unc,
                                players_alive=players_alive,
                                spr=spr_val,
                                pos_key=pos_key,
                                street=street,
                                solver_conf=solver_ev_conf,
                            )
                            raise_cap = raise_cap_marginal
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
                                    raise_pref = raise_pref ** 1.6
                                raise_pref_trace = raise_pref
                            if target is None:
                                if raise_cap is not None:
                                    target = float(raise_cap)
                                edge_ratio = (float(raise_ev_best) - float(call_ev_ref)) / max(1.0, float(pot_unit))
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
                            if raise_pref is not None:
                                target = min(float(target), float(raise_pref))
                            if ev_raise_share_cap is not None:
                                target = min(float(target), float(ev_raise_share_cap))
                                soft_cap = min(float(soft_cap), float(ev_raise_share_cap))
                            if raise_cap is not None:
                                soft_cap = min(soft_cap, float(raise_cap))
                            target = min(target, soft_cap)
                            # Soft-blend target to avoid over-correcting under uncertain estimates.
                            blend_strength = 0.20 + 0.55 * min(1.0, abs(edge_ratio) * 2.0)
                            blend_strength *= max(0.25, 1.0 - unc)
                            blended = (blend_strength * float(target)) + ((1.0 - blend_strength) * current_raise)
                            target_raise = max(0.0, min(0.75, blended))
                            if soft_cap is not None:
                                target_raise = min(float(target_raise), float(soft_cap))
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
                                raise_pref = raise_pref ** 1.6
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
                total_weight = sum(w for _act, w in weighted_rows)
                if total_weight > 0:
                    rnd_unit = _rng_pct(f"def_mix2:{state_hash}:{street}:{pot_chips}:{to_call}:{pos_key}") / 10000.0
                    acc = 0.0
                    for act, w in weighted_rows:
                        acc += w / total_weight
                        if rnd_unit <= acc:
                            chosen_local = act
                            break
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
        if chosen is not None and trace_active and defense_trace:
            action_out = dict(chosen)
            defense_trace["chosen_kind"] = action_out.get("kind")
            defense_trace["chosen_target_chips"] = action_out.get("target_total_commit_chips")
            action_out["policy_trace"] = defense_trace
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
        players_alive = int(snap.get("players_alive_count", 2) or 2)
        pot_chips = int(snap.get("pot_chips", 0) or 0)
        actor_stack = int(snap.get("actor_stack_chips", 0) or 0)
        total_stack = actor_stack + actor_commit
        mw_rung_id = ctx.get("mw_rung_id") if players_alive >= 3 else None
        equity_pack = _equity_from_obs(
            obs=obs,
            players_alive=players_alive,
            street=snap.get("street"),
            state_hash=state_hash,
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
            if pos_key in ("SB", "BB"):
                stats = blind_open_stats.setdefault(pos_key, {"hands": 0, "opens": 0})
                stats["hands"] += 1
                if to_call > 0 and opener_pos is not None and opener_pos != pos_key:
                    stats["opens"] += 1
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
                    cutoff = _preflop_cutoff(opponents_open, open_pct_eff)
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
                    defend_target_mix: float | None = None
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
                    raise_cutoff = min(1.0, _preflop_cutoff(opponents, raise_pct) + def_premium)
                    call_cutoff = min(1.0, _preflop_cutoff(opponents, call_pct) + def_premium * 0.7)
                    gate_eq = equity_gate if equity_gate is not None else equity_eff
                    pot_odds = to_call / max(pot_chips + to_call, 1)
                    hard_fold_cutoff = min(0.95, pot_odds + def_premium)
                    if gate_eq < hard_fold_cutoff:
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
                        if gate_eq < (raise_cutoff - raise_slack):
                            legal_ev = [a for a in legal if a.get("kind") not in ("RAISE", "BET")]
                        if call_cutoff is not None and gate_eq_call < (call_cutoff - call_slack):
                            call_keep = False
                            if call_ev_pre is not None:
                                call_keep = float(call_ev_pre) >= (-0.02 * pot_unit_pre)
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

            if keypot_triggered:
                defend_target = None
                force_defend = None

            if players_alive_pf >= 3:
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
                        ev_slack=ev_slack,
                        uncertainty=uncertainty_pf,
                        defend_rate_fn=_postflop_defend_rate_fn,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        prior_street_aggressor=prior_street_aggressor,
                        oop_aggression_gate=bb_oop_hu,
                        force_defend=force_defend,
                        board_texture=board_tex,
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
                        prior_weights=prior_weights,
                        ev_slack=ev_slack,
                        min_ev_for_priors=-ev_slack,
                        uncertainty=uncertainty_pf,
                        defend_rate_fn=_postflop_defend_rate_fn,
                        defend_target=defend_target,
                        pos_key=pos_key_post,
                        prior_street_aggressor=prior_street_aggressor,
                        oop_aggression_gate=bb_oop_hu,
                        force_defend=force_defend,
                        board_texture=board_tex,
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
                        oop_aggression_gate=bb_oop_hu,
                        force_defend=force_defend,
                        board_texture=board_tex,
                        solver_hint_kind=solver_hint_kind,
                        solver_hint_target=solver_hint_target,
                        solver_call_ev=solver_call_ev,
                        solver_raise_ev=solver_raise_ev,
                        solver_edge=solver_edge,
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
        "mw_strategy_ref": mw_strategy_ref,
        "treepath_mapping_spec_id": mapping_spec_id,
    }
    # If the solver root is provided in paths_trace, compute solver_build_id for provenance.
    try:
        solver_root = postflop_solver_src_root_from_paths_trace(paths_trace)
        solver_build_id = compute_postflop_solver_build_id(src_root=solver_root, strict_mode=strict_mode)  # pragma: no cover - metadata only
        extra_meta["solver_build_id"] = solver_build_id  # pragma: no cover - metadata only
    except Exception:
        # No solver root available; leave metadata minimal.
        pass

    return _policy, extra_meta
