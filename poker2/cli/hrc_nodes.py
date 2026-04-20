from __future__ import annotations

from typing import Any, Iterable


_TYPE_KEYS = ("type", "action", "move", "name", "label", "kind")

_RAISE_TYPES = {
    "R",
    "RAISE",
    "BET",
    "B",
    "ALLIN",
    "ALL-IN",
    "AI",
    "A",
    "JAM",
    "J",
}
_CALL_TYPES = {
    "C",
    "CALL",
    "CHECK",
    "K",
    "X",
    "L",
    "LIMP",
    "COMPLETE",
}
_FOLD_TYPES = {
    "F",
    "FOLD",
}

_AMOUNT_KEYS = (
    "amount",
    "raise",
    "raise_to",
    "raiseTo",
    "to",
    "size",
    "bet",
    "chips",
    "commit",
    "total",
)


def _type_key(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip().upper()
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return str(int(val))
    return None


def _action_type(action: Any) -> str | None:
    if isinstance(action, dict):
        for key in _TYPE_KEYS:
            if key in action:
                return _type_key(action.get(key))
    return _type_key(action)


def action_amount(action: Any) -> float | None:
    if isinstance(action, (int, float)) and not isinstance(action, bool):
        return float(action)
    if not isinstance(action, dict):
        return None
    for key in _AMOUNT_KEYS:
        val = action.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return float(val)
    return None


def canonical_action_kind(action: Any) -> str | None:
    raw_type = _action_type(action)
    if raw_type in _RAISE_TYPES:
        return "raise"
    if raw_type in _CALL_TYPES:
        return "call"
    if raw_type in _FOLD_TYPES:
        return "fold"
    amt = action_amount(action)
    if isinstance(amt, (int, float)):
        if amt > 0:
            return "raise"
        if amt == 0:
            return "call"
    return None


def action_kinds(actions: Any) -> list[str | None]:
    if not isinstance(actions, list):
        return []
    return [canonical_action_kind(a) for a in actions]


def iter_hands(hands: Any) -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(hands, dict):
        for hand, info in hands.items():
            if not isinstance(hand, str) or not isinstance(info, dict):
                continue
            yield hand, info
        return
    if isinstance(hands, list):
        for entry in hands:
            if not isinstance(entry, dict):
                continue
            hand = entry.get("hand") or entry.get("cards") or entry.get("key")
            if isinstance(hand, str):
                yield hand, entry


def _kind_from_key(key: Any) -> str | None:
    if isinstance(key, str):
        return canonical_action_kind({"type": key})
    return None


def values_by_index(values: Any, kinds: list[str | None]) -> list[float | None] | None:
    if not kinds:
        return None
    out: list[float | None] = [None] * len(kinds)
    if isinstance(values, list):
        for idx, val in enumerate(values):
            if idx >= len(kinds):
                break
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                out[idx] = float(val)
        return out
    if isinstance(values, dict):
        for key, val in values.items():
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if isinstance(key, int):
                    idx = key
                elif isinstance(key, str) and key.isdigit():
                    idx = int(key)
                else:
                    idx = None
                if idx is not None:
                    if 0 <= idx < len(kinds):
                        out[idx] = float(val)
                    continue
                kind = _kind_from_key(key)
                if kind is None:
                    continue
                for i, k in enumerate(kinds):
                    if k == kind:
                        out[i] = float(val)
        return out
    return None


def played_by_index(info: dict[str, Any], kinds: list[str | None]) -> list[float] | None:
    for key in ("played", "strategy", "strat"):
        if key in info:
            values = values_by_index(info.get(key), kinds)
            if values is None:
                continue
            return [float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0 for v in values]
    return None
