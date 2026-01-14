from __future__ import annotations

"""
TreePathMappingSpec (ARCHIETECTURE.md §3.13)

This module centralizes any "size/pot-fraction/ratio → target_total_commit_chips"
conversion so that no runtime/policy module carries its own copy of the math.
Only helpers are exposed; callers remain responsible for selecting a legal action
using the Environment’s legal action set.
"""

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex
from poker2.protocol.rounding import round_div_int


DEFAULT_SCHEMA_ID = "treepath_mapping_spec_v1"


@dataclass(frozen=True)
class TreePathMappingSpecError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _fraction_from_size(value: Any) -> Fraction:
    """
    Parse strings such as "2.5bb" / "3.3x" / numbers into Fraction for integer math.
    Falls back to Fraction(5, 2) == 2.5 when parsing fails.
    """
    from decimal import Decimal

    if isinstance(value, (int, float, Decimal, str)):
        s = str(value).strip().lower()
        suffixes = ("bb", "x")
        for suf in suffixes:
            if s.endswith(suf):
                s = s[: -len(suf)]
                break
        try:
            dec = Decimal(s)
            return Fraction(dec).limit_denominator()
        except Exception:
            return Fraction(5, 2)
    return Fraction(5, 2)


def parse_size_fraction(value: Any) -> Fraction:
    """Public helper to parse size strings into Fraction (used by policies/tools)."""
    return _fraction_from_size(value)


def validate_treepath_mapping_spec(spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(spec, dict):
        raise TreePathMappingSpecError("TYPE_ERROR", "TreePathMappingSpec must be JSON object")
    schema_id = spec.get("treepath_mapping_schema_id")
    if schema_id != DEFAULT_SCHEMA_ID:
        raise TreePathMappingSpecError("UNSUPPORTED_VALUE", f"unsupported treepath_mapping_schema_id: {schema_id!r}")
    pre = spec.get("preflop")
    post = spec.get("postflop")
    if not isinstance(pre, dict) or not isinstance(post, dict):
        raise TreePathMappingSpecError("MISSING_FIELDS", "preflop/postflop sections are required")
    if strict_mode and "treepath_mapping_spec_id" in spec:
        raise TreePathMappingSpecError("DISALLOWED_FIELD", "hash input must not include treepath_mapping_spec_id")

    def _check_pos_map(name: str, obj: Any) -> None:
        if not isinstance(obj, dict):
            raise TreePathMappingSpecError("TYPE_ERROR", f"{name} must be object")
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TreePathMappingSpecError("TYPE_ERROR", f"{name} keys must be str")
            _ = _fraction_from_size(v)

    _check_pos_map("preflop.open_frac_by_pos", pre.get("open_frac_by_pos", {}))
    _check_pos_map("preflop.threebet_mult_by_pos", pre.get("threebet_mult_by_pos", {}))
    _check_pos_map("preflop.fourbet_mult_by_pos", pre.get("fourbet_mult_by_pos", {}))

    pot_fracs = post.get("pot_fracs")
    if not isinstance(pot_fracs, list) or not pot_fracs:
        raise TreePathMappingSpecError("TYPE_ERROR", "postflop.pot_fracs must be non-empty array")
    for v in pot_fracs:
        _ = _fraction_from_size(v)

    rounding_mode = post.get("rounding_mode", "floor")
    if rounding_mode not in ("floor", "ceil", "nearest_ties_up"):
        raise TreePathMappingSpecError("UNSUPPORTED_VALUE", f"unsupported rounding_mode: {rounding_mode!r}")


def treepath_mapping_spec_id(spec: Any, *, strict_mode: bool) -> str:
    validate_treepath_mapping_spec(spec, strict_mode=strict_mode)
    obj_for_hash = {k: v for k, v in spec.items() if k != "treepath_mapping_spec_id"}
    return sha256_hex(canonicalize_json_bytes(obj_for_hash, strict_mode=strict_mode))


def default_internal_treepath_mapping_spec(*, strict_mode: bool) -> tuple[dict[str, Any], str]:
    root = Path(__file__).resolve().parents[2]
    path = root / "specs" / "treepath_mapping" / "internal_treepath_mapping_v1.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    mid = treepath_mapping_spec_id(spec, strict_mode=strict_mode)
    return spec, mid


def position_key(actor_seat: int, button_seat: int, seats_in_hand: list[int]) -> str:
    seats = list(seats_in_hand)
    if actor_seat not in seats or button_seat not in seats:
        return "OTHERS"
    start = seats.index(button_seat)
    ordered = seats[start:] + seats[:start]
    if ordered[0] == actor_seat:
        return "BU"
    if len(ordered) > 1 and ordered[1] == actor_seat:
        return "SB"
    if len(ordered) > 2 and ordered[2] == actor_seat:
        return "BB"
    return "OTHERS"


def preflop_size_plan(spec: dict[str, Any]) -> tuple[dict[str, Fraction], dict[str, Fraction], dict[str, Fraction]]:
    pre = spec.get("preflop", {})
    open_frac_by_pos = {k: _fraction_from_size(v) for k, v in (pre.get("open_frac_by_pos") or {}).items()}
    threebet_mult_by_pos = {k: _fraction_from_size(v) for k, v in (pre.get("threebet_mult_by_pos") or {}).items()}
    fourbet_mult_by_pos = {k: _fraction_from_size(v) for k, v in (pre.get("fourbet_mult_by_pos") or {}).items()}
    return open_frac_by_pos, threebet_mult_by_pos, fourbet_mult_by_pos


def pot_fracs(spec: dict[str, Any]) -> tuple[list[Fraction], str]:
    post = spec.get("postflop", {})
    fracs = [_fraction_from_size(v) for v in post.get("pot_fracs", [])]
    rounding_mode = post.get("rounding_mode", "floor")
    return fracs, rounding_mode


def apply_rounding(numer: int, denom: int, *, rounding_mode: str) -> int:
    return round_div_int(numer, denom, rounding_mode=rounding_mode)
