from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object

SPOT_POLICY_SCHEMA_ID = "spot_policy_v1"
_ALLOWED_TOP_LEVEL = {"schema_id", "spots"}
_ALLOWED_WHEN_KEYS = {
    "streets",
    "requires_facing_bet",
    "pos_keys",
    "players_alive_min",
    "players_alive_max",
    "price_min_ppm",
    "price_max_ppm",
    "spr_min_milli",
    "spr_max_milli",
    "wet_min",
    "wet_max",
}
_ALLOWED_ADJUSTMENT_KEYS = {
    "defend_target_scale_bp",
    "defend_target_floor_bp",
    "defend_target_max_bp",
    "call_pref_floor_bp",
    "raise_cap_max_bp",
    "trace_tag",
}
_ALLOWED_STREETS = {"PREFLOP", "FLOP", "TURN", "RIVER"}


@dataclass(frozen=True)
class SpotPolicyError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def load_spot_policy(path: Path, *, strict_mode: bool) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SpotPolicyError(
            "JSON_PARSE_FAIL",
            "spot policy JSON unreadable",
            {"path": str(path), "error": str(exc)},
        ) from exc
    validate_spot_policy(obj, strict_mode=strict_mode)
    return obj


def _contains_none_string(value: Any) -> bool:
    if value == "none":
        return True
    if isinstance(value, dict):
        return any(_contains_none_string(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_none_string(v) for v in value)
    return False


def _validate_opt_int(value: Any, *, field: str, minimum: int | None = None, maximum: int | None = None) -> None:
    if value is None:
        return
    if not isinstance(value, int):
        raise SpotPolicyError("TYPE_ERROR", f"{field} must be int or null")
    if minimum is not None and value < minimum:
        raise SpotPolicyError("VALUE_ERROR", f"{field} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise SpotPolicyError("VALUE_ERROR", f"{field} must be <= {maximum}")


def validate_spot_policy(spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(spec, dict):
        raise SpotPolicyError("TYPE_ERROR", "SpotPolicy must be JSON object")
    if strict_mode:
        extra = set(spec.keys()) - _ALLOWED_TOP_LEVEL
        if extra:
            raise SpotPolicyError("EXTRA_FIELDS", "spot policy has extra top-level fields", {"extra": sorted(extra)})
    schema_id = spec.get("schema_id")
    if schema_id != SPOT_POLICY_SCHEMA_ID:
        raise SpotPolicyError("SCHEMA_MISMATCH", "unsupported spot policy schema_id", {"schema_id": schema_id})
    spots = spec.get("spots")
    if not isinstance(spots, list) or not spots:
        raise SpotPolicyError("TYPE_ERROR", "spots must be non-empty array")
    seen_spot_ids: set[str] = set()
    for idx, spot in enumerate(spots):
        if not isinstance(spot, dict):
            raise SpotPolicyError("TYPE_ERROR", "spot entry must be object", {"index": idx})
        if strict_mode:
            extra = set(spot.keys()) - {"spot_id", "enabled", "when", "adjustments"}
            if extra:
                raise SpotPolicyError("EXTRA_FIELDS", "spot entry has extra fields", {"index": idx, "extra": sorted(extra)})
        spot_id = spot.get("spot_id")
        if not isinstance(spot_id, str) or not spot_id:
            raise SpotPolicyError("TYPE_ERROR", "spot_id must be non-empty string", {"index": idx})
        if spot_id in seen_spot_ids:
            raise SpotPolicyError("VALUE_ERROR", "duplicate spot_id", {"spot_id": spot_id})
        seen_spot_ids.add(spot_id)
        enabled = spot.get("enabled")
        if not isinstance(enabled, bool):
            raise SpotPolicyError("TYPE_ERROR", "enabled must be bool", {"index": idx})

        when = spot.get("when")
        if not isinstance(when, dict):
            raise SpotPolicyError("TYPE_ERROR", "when must be object", {"index": idx})
        if strict_mode:
            extra = set(when.keys()) - _ALLOWED_WHEN_KEYS
            if extra:
                raise SpotPolicyError("EXTRA_FIELDS", "when has extra fields", {"index": idx, "extra": sorted(extra)})
        streets = when.get("streets")
        if not isinstance(streets, list) or not streets or not all(isinstance(v, str) for v in streets):
            raise SpotPolicyError("TYPE_ERROR", "when.streets must be non-empty string array", {"index": idx})
        bad_streets = [street for street in streets if street not in _ALLOWED_STREETS]
        if bad_streets:
            raise SpotPolicyError("UNSUPPORTED_VALUE", "when.streets contains unsupported value", {"index": idx, "streets": bad_streets})
        requires_facing_bet = when.get("requires_facing_bet")
        if not isinstance(requires_facing_bet, bool):
            raise SpotPolicyError("TYPE_ERROR", "when.requires_facing_bet must be bool", {"index": idx})
        pos_keys = when.get("pos_keys")
        if pos_keys is not None:
            if not isinstance(pos_keys, list) or not pos_keys or not all(isinstance(v, str) for v in pos_keys):
                raise SpotPolicyError("TYPE_ERROR", "when.pos_keys must be string array or null", {"index": idx})

        _validate_opt_int(when.get("players_alive_min"), field="when.players_alive_min", minimum=2)
        _validate_opt_int(when.get("players_alive_max"), field="when.players_alive_max", minimum=2)
        players_alive_min = when.get("players_alive_min")
        players_alive_max = when.get("players_alive_max")
        if isinstance(players_alive_min, int) and isinstance(players_alive_max, int) and players_alive_min > players_alive_max:
            raise SpotPolicyError("VALUE_ERROR", "players_alive_min cannot exceed players_alive_max", {"index": idx})

        _validate_opt_int(when.get("price_min_ppm"), field="when.price_min_ppm", minimum=0, maximum=1_000_000)
        _validate_opt_int(when.get("price_max_ppm"), field="when.price_max_ppm", minimum=0, maximum=1_000_000)
        price_min_ppm = when.get("price_min_ppm")
        price_max_ppm = when.get("price_max_ppm")
        if isinstance(price_min_ppm, int) and isinstance(price_max_ppm, int) and price_min_ppm > price_max_ppm:
            raise SpotPolicyError("VALUE_ERROR", "price_min_ppm cannot exceed price_max_ppm", {"index": idx})

        _validate_opt_int(when.get("spr_min_milli"), field="when.spr_min_milli", minimum=0)
        _validate_opt_int(when.get("spr_max_milli"), field="when.spr_max_milli", minimum=0)
        spr_min_milli = when.get("spr_min_milli")
        spr_max_milli = when.get("spr_max_milli")
        if isinstance(spr_min_milli, int) and isinstance(spr_max_milli, int) and spr_min_milli > spr_max_milli:
            raise SpotPolicyError("VALUE_ERROR", "spr_min_milli cannot exceed spr_max_milli", {"index": idx})

        _validate_opt_int(when.get("wet_min"), field="when.wet_min", minimum=0, maximum=4)
        _validate_opt_int(when.get("wet_max"), field="when.wet_max", minimum=0, maximum=4)
        wet_min = when.get("wet_min")
        wet_max = when.get("wet_max")
        if isinstance(wet_min, int) and isinstance(wet_max, int) and wet_min > wet_max:
            raise SpotPolicyError("VALUE_ERROR", "wet_min cannot exceed wet_max", {"index": idx})

        adjustments = spot.get("adjustments")
        if not isinstance(adjustments, dict):
            raise SpotPolicyError("TYPE_ERROR", "adjustments must be object", {"index": idx})
        if strict_mode:
            extra = set(adjustments.keys()) - _ALLOWED_ADJUSTMENT_KEYS
            if extra:
                raise SpotPolicyError("EXTRA_FIELDS", "adjustments has extra fields", {"index": idx, "extra": sorted(extra)})
        _validate_opt_int(adjustments.get("defend_target_scale_bp"), field="adjustments.defend_target_scale_bp", minimum=0, maximum=20000)
        _validate_opt_int(adjustments.get("defend_target_floor_bp"), field="adjustments.defend_target_floor_bp", minimum=0, maximum=10000)
        _validate_opt_int(adjustments.get("defend_target_max_bp"), field="adjustments.defend_target_max_bp", minimum=0, maximum=10000)
        _validate_opt_int(adjustments.get("call_pref_floor_bp"), field="adjustments.call_pref_floor_bp", minimum=0, maximum=10000)
        _validate_opt_int(adjustments.get("raise_cap_max_bp"), field="adjustments.raise_cap_max_bp", minimum=0, maximum=10000)
        defend_target_floor_bp = adjustments.get("defend_target_floor_bp")
        defend_target_max_bp = adjustments.get("defend_target_max_bp")
        if isinstance(defend_target_floor_bp, int) and isinstance(defend_target_max_bp, int) and defend_target_floor_bp > defend_target_max_bp:
            raise SpotPolicyError("VALUE_ERROR", "defend_target_floor_bp cannot exceed defend_target_max_bp", {"index": idx})
        trace_tag = adjustments.get("trace_tag")
        if trace_tag is not None and not isinstance(trace_tag, str):
            raise SpotPolicyError("TYPE_ERROR", "adjustments.trace_tag must be string or null", {"index": idx})
        if not any(
            adjustments.get(key) is not None
            for key in (
                "defend_target_scale_bp",
                "defend_target_floor_bp",
                "defend_target_max_bp",
                "call_pref_floor_bp",
                "raise_cap_max_bp",
            )
        ):
            raise SpotPolicyError("MISSING_FIELDS", "adjustments must set at least one numeric control", {"index": idx})

    if strict_mode and _contains_none_string(spec):
        raise SpotPolicyError("NULL_CONVENTION_VIOLATION", 'spot policy must not contain string "none"')


def spot_policy_digest(spec: Any, *, strict_mode: bool) -> dict[str, str]:
    validate_spot_policy(spec, strict_mode=strict_mode)
    digest_hex = sha256_hex(canonicalize_json_bytes(spec, strict_mode=strict_mode))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest
