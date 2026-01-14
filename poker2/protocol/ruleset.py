from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import ROUNDING_MODE_VALUES, canonicalize_json_bytes, sha256_hex


@dataclass(frozen=True)
class RuleSetError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _require(obj: dict[str, Any], key: str) -> Any:
    if key not in obj:
        raise RuleSetError("MISSING_FIELD", f"missing field: {key}")
    return obj[key]


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise RuleSetError("TYPE_ERROR", f"{field} must be int, got bool")
    if not isinstance(value, int):
        raise RuleSetError("TYPE_ERROR", f"{field} must be int, got {type(value).__name__}")
    return value


def _as_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise RuleSetError("TYPE_ERROR", f"{field} must be bool, got {type(value).__name__}")
    return value


def validate_ruleset(ruleset: Any, *, strict_mode: bool) -> None:
    if not isinstance(ruleset, dict):
        raise RuleSetError("TYPE_ERROR", "RuleSet must be a JSON object")

    game_kind = _require(ruleset, "game_kind")
    if game_kind != "NLHE":
        raise RuleSetError("UNSUPPORTED_VALUE", f"unsupported game_kind: {game_kind!r}")

    blinds = _require(ruleset, "blinds")
    if not isinstance(blinds, dict):
        raise RuleSetError("TYPE_ERROR", "blinds must be object")
    sb = _as_int(_require(blinds, "sb_chips"), field="blinds.sb_chips")
    bb = _as_int(_require(blinds, "bb_chips"), field="blinds.bb_chips")
    if sb < 0 or bb <= 0 or sb >= bb:
        raise RuleSetError("VALUE_ERROR", "invalid blinds: require 0<=sb<bb and bb>0")

    ante = _require(ruleset, "ante")
    if ante is not None:
        if not isinstance(ante, dict):
            raise RuleSetError("TYPE_ERROR", "ante must be null or object")
        kind = _require(ante, "kind")
        if kind == "uniform":
            ante_chips = _as_int(_require(ante, "ante_chips"), field="ante.ante_chips")
            if ante_chips <= 0:
                raise RuleSetError("VALUE_ERROR", "ante.ante_chips must be > 0 for uniform ante")
        elif kind == "by_seat":
            by_seat = _require(ante, "by_seat_ante_chips")
            if not isinstance(by_seat, dict):
                raise RuleSetError("TYPE_ERROR", "ante.by_seat_ante_chips must be object")
            if strict_mode and len(by_seat) == 0:
                raise RuleSetError("VALUE_ERROR", "by-seat ante map must not be empty in strict_mode (use null)")
        else:
            raise RuleSetError("UNSUPPORTED_VALUE", f"unsupported ante.kind: {kind!r}")

    straddle = _require(ruleset, "straddle")
    if straddle is not None:
        if not isinstance(straddle, dict):
            raise RuleSetError("TYPE_ERROR", "straddle must be null or object")
        kind = _require(straddle, "kind")
        if kind not in ("button", "utg", "by_seat", "custom"):
            raise RuleSetError("UNSUPPORTED_VALUE", f"unsupported straddle.kind: {kind!r}")
        amount = _as_int(_require(straddle, "amount_chips"), field="straddle.amount_chips")
        if amount <= 0:
            raise RuleSetError("VALUE_ERROR", "straddle.amount_chips must be > 0")

    rake = _require(ruleset, "rake")
    if rake is not None:
        if not isinstance(rake, dict):
            raise RuleSetError("TYPE_ERROR", "rake must be null or object")
        pct_ppm = _as_int(_require(rake, "pct_ppm"), field="rake.pct_ppm")
        cap_chips = rake.get("cap_chips")
        if cap_chips is not None:
            cap_chips = _as_int(cap_chips, field="rake.cap_chips")
        rounding_mode = _require(rake, "rounding_mode")
        if rounding_mode not in ROUNDING_MODE_VALUES:
            raise RuleSetError("UNSUPPORTED_VALUE", f"unsupported rake.rounding_mode: {rounding_mode!r}")
        no_flop_no_drop = _as_bool(_require(rake, "no_flop_no_drop"), field="rake.no_flop_no_drop")
        _ = no_flop_no_drop
        if pct_ppm < 0 or pct_ppm > 1_000_000:
            raise RuleSetError("VALUE_ERROR", "rake.pct_ppm must be in [0, 1_000_000]")
        if cap_chips is not None and cap_chips < 0:
            raise RuleSetError("VALUE_ERROR", "rake.cap_chips must be >= 0 or null")

    min_raise_rule = _require(ruleset, "min_raise_rule")
    if not isinstance(min_raise_rule, dict):
        raise RuleSetError("TYPE_ERROR", "min_raise_rule must be object")
    basis = _require(min_raise_rule, "basis")
    if basis != "last_raise_increment":
        raise RuleSetError("UNSUPPORTED_VALUE", f"unsupported min_raise_rule.basis: {basis!r}")
    _as_bool(
        _require(min_raise_rule, "reopen_on_short_allin"),
        field="min_raise_rule.reopen_on_short_allin",
    )



def ruleset_id(ruleset: Any, *, strict_mode: bool) -> str:
    validate_ruleset(ruleset, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(ruleset, strict_mode=strict_mode))


def ruleset_rake_id(ruleset: Any, *, strict_mode: bool) -> str:
    validate_ruleset(ruleset, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes({"rake": ruleset["rake"]}, strict_mode=strict_mode))
