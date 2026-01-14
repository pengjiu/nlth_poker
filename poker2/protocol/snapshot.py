from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.protocol.enums import STREET_VALUES


@dataclass(frozen=True)
class SnapshotError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def street_from_pokerkit_street_index(street_index: int | None) -> str:
    if street_index is None:
        raise SnapshotError("VALUE_ERROR", "street_index is None (hand is not in a decision street)")
    mapping = {0: "PREFLOP", 1: "FLOP", 2: "TURN", 3: "RIVER"}
    street = mapping.get(street_index)
    if street is None:
        raise SnapshotError("VALUE_ERROR", f"unsupported street_index: {street_index}")
    return street


def validate_snapshot_min_fields(snapshot: Any, *, strict_mode: bool) -> None:
    if not isinstance(snapshot, dict):
        raise SnapshotError("TYPE_ERROR", "SnapshotMinFields must be a JSON object")

    required = (
        "street",
        "actor_seat",
        "players_alive_count",
        "pot_chips",
        "to_call_chips",
        "actor_commit_chips",
        "actor_stack_chips",
        "min_raise_to_chips",
        "max_raise_to_chips",
        "legal_actions_digest",
        "observation_digest",
    )
    missing = [k for k in required if k not in snapshot]
    if missing:
        raise SnapshotError("MISSING_FIELDS", f"missing Snapshot fields: {missing}")

    street = snapshot.get("street")
    if street not in STREET_VALUES:
        raise SnapshotError("UNSUPPORTED_VALUE", f"unsupported street: {street!r}")

    for k in ("actor_seat", "players_alive_count", "pot_chips", "to_call_chips", "actor_commit_chips", "actor_stack_chips"):
        v = snapshot.get(k)
        if isinstance(v, bool) or not isinstance(v, int):
            raise SnapshotError("TYPE_ERROR", f"{k} must be int")

    min_raise = snapshot.get("min_raise_to_chips")
    max_raise = snapshot.get("max_raise_to_chips")
    if (min_raise is None) != (max_raise is None):
        raise SnapshotError("VALUE_ERROR", "min_raise_to_chips and max_raise_to_chips must both be null or int")
    if min_raise is not None:
        if isinstance(min_raise, bool) or not isinstance(min_raise, int):
            raise SnapshotError("TYPE_ERROR", "min_raise_to_chips must be int or null")
        if isinstance(max_raise, bool) or not isinstance(max_raise, int):
            raise SnapshotError("TYPE_ERROR", "max_raise_to_chips must be int or null")
        if strict_mode and min_raise > max_raise:
            raise SnapshotError("VALUE_ERROR", "min_raise_to_chips must be <= max_raise_to_chips")

