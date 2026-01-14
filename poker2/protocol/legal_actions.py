from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.action_bins import ActionBinsError, validate_action_bins_spec
from poker2.protocol.enums import ACTION_KIND_ORDER, ACTION_KIND_VALUES


@dataclass(frozen=True)
class LegalActionsError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise LegalActionsError("TYPE_ERROR", f"{field} must be int, got bool")
    if not isinstance(value, int):
        raise LegalActionsError("TYPE_ERROR", f"{field} must be int, got {type(value).__name__}")
    return value


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise LegalActionsError("TYPE_ERROR", f"{field} must be str, got {type(value).__name__}")
    return value


def _canonical_action(kind: str, target_total_commit_chips: int) -> dict[str, Any]:
    return {"kind": kind, "target_total_commit_chips": target_total_commit_chips}


def legal_actions_and_digest(
    snapshot: dict[str, Any],
    *,
    action_bins: dict[str, Any],
    bet_targets: list[int] | None = None,
    raise_targets: list[int] | None = None,
    strict_mode: bool,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    try:
        validate_action_bins_spec(action_bins, strict_mode=strict_mode)
    except ActionBinsError as e:
        raise LegalActionsError(e.code, e.message) from e

    include_min = bool(action_bins["include_min_raise_to"])
    include_max = bool(action_bins["include_max_raise_to"])
    include_extra = bool(action_bins["include_extra_raise_to"])

    to_call = _as_int(snapshot.get("to_call_chips"), field="Snapshot.to_call_chips")
    actor_commit = _as_int(snapshot.get("actor_commit_chips"), field="Snapshot.actor_commit_chips")
    min_raise_to = snapshot.get("min_raise_to_chips")
    max_raise_to = snapshot.get("max_raise_to_chips")

    if (min_raise_to is None) != (max_raise_to is None):
        raise LegalActionsError("VALUE_ERROR", "min_raise_to_chips and max_raise_to_chips must both be null or int")
    if min_raise_to is not None:
        min_raise_to = _as_int(min_raise_to, field="Snapshot.min_raise_to_chips")
        max_raise_to = _as_int(max_raise_to, field="Snapshot.max_raise_to_chips")
        if strict_mode and min_raise_to > max_raise_to:
            raise LegalActionsError("VALUE_ERROR", "min_raise_to_chips must be <= max_raise_to_chips")

    bet_targets = bet_targets or []
    raise_targets = raise_targets or []

    actions: list[dict[str, Any]] = []
    if to_call > 0:
        actions.append(_canonical_action("FOLD", actor_commit))
        actions.append(_canonical_action("CALL", actor_commit + to_call))
        if min_raise_to is not None:
            current_bet_to_total = actor_commit + to_call
            targets: set[int] = set()
            if include_min:
                targets.add(min_raise_to)
            if include_max:
                targets.add(max_raise_to)
            if include_extra:
                last_full_raise_increment = min_raise_to - current_bet_to_total
                extra = min_raise_to + last_full_raise_increment
                if last_full_raise_increment > 0 and extra <= max_raise_to:
                    targets.add(extra)
            for t in raise_targets:
                targets.add(_as_int(t, field="ActionBins.raise_targets"))
            for t in targets:
                actions.append(_canonical_action("RAISE", t))
    else:
        actions.append(_canonical_action("CHECK", actor_commit))
        if min_raise_to is not None:
            targets2: set[int] = set()
            if include_min:
                targets2.add(min_raise_to)
            if include_max:
                targets2.add(max_raise_to)
            if include_extra:
                last_full_raise_increment = min_raise_to - actor_commit
                extra = min_raise_to + last_full_raise_increment
                if last_full_raise_increment > 0 and extra <= max_raise_to:
                    targets2.add(extra)
            for t in bet_targets:
                targets2.add(_as_int(t, field="ActionBins.bet_targets"))
            for t in targets2:
                actions.append(_canonical_action("BET", t))

    # Validate kinds and stable sort.
    for a in actions:
        kind = _as_str(a.get("kind"), field="CanonicalAction.kind")
        if kind not in ACTION_KIND_VALUES:
            raise LegalActionsError("UNSUPPORTED_VALUE", f"unsupported action kind: {kind!r}")
        _ = _as_int(a.get("target_total_commit_chips"), field="CanonicalAction.target_total_commit_chips")

    actions.sort(key=lambda a: (ACTION_KIND_ORDER[a["kind"]], a["target_total_commit_chips"]))

    # De-dup and enforce strict uniqueness.
    seen: set[tuple[str, int]] = set()
    deduped: list[dict[str, Any]] = []
    dups: list[tuple[str, int]] = []
    for a in actions:
        key = (a["kind"], a["target_total_commit_chips"])
        if key in seen:
            dups.append(key)
            continue
        seen.add(key)
        deduped.append(a)

    if dups and strict_mode:
        raise LegalActionsError("DUPLICATE_ACTIONS", f"duplicate legal actions: {sorted(set(dups))}")
    actions = deduped

    # 3.11.3 self-check.
    kinds = {a["kind"] for a in actions}
    if to_call == 0:
        if "CHECK" not in kinds or "CALL" in kinds:
            raise LegalActionsError("SELF_CHECK_FAIL", "to_call_chips==0 must allow CHECK and forbid CALL")
        if "FOLD" in kinds:
            raise LegalActionsError("SELF_CHECK_FAIL", "to_call_chips==0 must forbid FOLD")
    else:
        if "CALL" not in kinds or "CHECK" in kinds:
            raise LegalActionsError("SELF_CHECK_FAIL", "to_call_chips>0 must allow CALL and forbid CHECK")
        if "FOLD" not in kinds:
            raise LegalActionsError("SELF_CHECK_FAIL", "to_call_chips>0 must allow FOLD")

    if min_raise_to is None:
        if "BET" in kinds or "RAISE" in kinds:
            raise LegalActionsError("SELF_CHECK_FAIL", "min/max null must forbid BET/RAISE")
    else:
        for a in actions:
            if a["kind"] in ("BET", "RAISE"):
                if not (min_raise_to <= a["target_total_commit_chips"] <= max_raise_to):  # type: ignore[operator]
                    raise LegalActionsError("SELF_CHECK_FAIL", "BET/RAISE target out of [min,max]")

    digest_hex = sha256_hex(canonicalize_json_bytes(actions, strict_mode=strict_mode))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return actions, digest
