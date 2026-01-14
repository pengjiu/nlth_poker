from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.protocol.rounding import RoundingError, round_div_int


@dataclass(frozen=True)
class RakeError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise RakeError("TYPE_ERROR", f"{field} must be int, got bool")
    if not isinstance(value, int):
        raise RakeError("TYPE_ERROR", f"{field} must be int, got {type(value).__name__}")
    return value


def _as_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise RakeError("TYPE_ERROR", f"{field} must be bool, got {type(value).__name__}")
    return value


def compute_total_rake_chips(
    *,
    rake_base_pot_chips: int,
    flop_dealt: bool,
    ruleset: dict[str, Any],
    rounding_mode_override: str | None = None,
) -> int:
    rake_obj = ruleset.get("rake")
    if rake_obj is None:
        return 0
    if not isinstance(rake_obj, dict):
        raise RakeError("TYPE_ERROR", "ruleset.rake must be null or object")

    pct_ppm = _as_int(rake_obj.get("pct_ppm"), field="ruleset.rake.pct_ppm")
    if pct_ppm < 0 or pct_ppm > 1_000_000:
        raise RakeError("VALUE_ERROR", "ruleset.rake.pct_ppm must be in [0, 1_000_000]")

    cap = rake_obj.get("cap_chips")
    if cap is not None:
        cap = _as_int(cap, field="ruleset.rake.cap_chips")
        if cap < 0:
            raise RakeError("VALUE_ERROR", "ruleset.rake.cap_chips must be >=0 or null")

    nfnd = _as_bool(rake_obj.get("no_flop_no_drop"), field="ruleset.rake.no_flop_no_drop")
    if nfnd and not flop_dealt:
        return 0

    rounding_mode = rounding_mode_override if rounding_mode_override is not None else rake_obj.get("rounding_mode")
    if not isinstance(rounding_mode, str):
        raise RakeError("TYPE_ERROR", "ruleset.rake.rounding_mode must be string")

    numer = rake_base_pot_chips * pct_ppm
    try:
        rake_chips = round_div_int(numer, 1_000_000, rounding_mode=rounding_mode)
    except RoundingError as e:
        raise RakeError(e.code, e.message) from e

    if cap is not None:
        rake_chips = min(rake_chips, cap)
    if rake_chips < 0:
        raise RakeError("VALUE_ERROR", "computed rake must be >= 0")
    if rake_chips > rake_base_pot_chips:
        rake_chips = rake_base_pot_chips
    return rake_chips

