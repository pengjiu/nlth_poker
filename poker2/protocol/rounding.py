from __future__ import annotations

from dataclasses import dataclass

from poker2.contractkit import ROUNDING_MODE_VALUES


@dataclass(frozen=True)
class RoundingError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def round_div_int(numer: int, denom: int, *, rounding_mode: str) -> int:
    if denom <= 0:
        raise RoundingError("VALUE_ERROR", "denom must be > 0")
    if rounding_mode not in ROUNDING_MODE_VALUES:
        raise RoundingError("UNSUPPORTED_VALUE", f"unsupported rounding_mode: {rounding_mode!r}")

    if rounding_mode == "floor":
        return numer // denom
    if rounding_mode == "ceil":
        return (numer + denom - 1) // denom

    # nearest_ties_up
    q, r = divmod(numer, denom)
    if r * 2 >= denom:
        return q + 1
    return q

