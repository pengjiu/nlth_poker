from __future__ import annotations

# Evaluation gates (directory layout per ARCHIETECTURE.md §8, Informative).

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from poker2.contractkit import ROUNDING_MODE_VALUES
from poker2.protocol.eventstream import read_ndjson
from poker2.protocol.rake import RakeError, compute_total_rake_chips
from poker2.protocol.enums import ACTION_KIND_VALUES, STREET_VALUES
from poker2.protocol.rounding import RoundingError, round_div_int


@dataclass(frozen=True)
class EvidenceError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise EvidenceError("TYPE_ERROR", f"{field} must be int, got bool")
    if not isinstance(value, int):
        raise EvidenceError("TYPE_ERROR", f"{field} must be int, got {type(value).__name__}")
    return value


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise EvidenceError("TYPE_ERROR", f"{field} must be str, got {type(value).__name__}")
    return value


def _load_hand_events(event_stream_path: Path, *, strict_mode: bool) -> list[dict[str, Any]]:
    objs = read_ndjson(event_stream_path, strict_mode=strict_mode)
    if strict_mode and not objs:
        raise EvidenceError("EMPTY_EVENTSTREAM", "EventStream must contain header + events")
    events: list[dict[str, Any]] = []
    for idx, obj in enumerate(objs[1:], start=1):
        if not isinstance(obj, dict):
            raise EvidenceError("EVENT_NOT_OBJECT", "event record must be object", {"index": idx})
        events.append(obj)
    return events


def _iter_events(events: Iterable[dict[str, Any]], name: str) -> Iterable[dict[str, Any]]:
    for e in events:
        if e.get("event") == name:
            yield e


def _get_single_event(events: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = list(_iter_events(events, name))
    if len(matches) != 1:
        raise EvidenceError(
            "EVENT_COUNT_MISMATCH",
            f"expected exactly 1 {name} event, got {len(matches)}",
        )
    return matches[0]


def _flop_dealt(events: list[dict[str, Any]]) -> bool:
    for e in _iter_events(events, "StreetDealt"):
        if e.get("street") == "FLOP":
            return True
    return False


def _round_rake(numer: int, denom: int, *, rounding_mode: str) -> int:
    try:
        return round_div_int(numer, denom, rounding_mode=rounding_mode)
    except RoundingError as e:
        raise EvidenceError(e.code, e.message) from e


def _expected_total_rake_chips(
    *,
    rake_base_pot_chips: int,
    flop_dealt: bool,
    ruleset: dict[str, Any],
    rounding_mode: str,
) -> int:
    try:
        return compute_total_rake_chips(
            rake_base_pot_chips=rake_base_pot_chips,
            flop_dealt=flop_dealt,
            ruleset=ruleset,
            rounding_mode_override=rounding_mode,
        )
    except RakeError as e:
        raise EvidenceError(e.code, e.message) from e


def infer_rake_rounding_modes(
    fixtures: list[dict[str, Any]],
    *,
    ruleset: dict[str, Any],
    strict_mode: bool,
) -> tuple[list[str], list[dict[str, Any]]]:
    possible = set(ROUNDING_MODE_VALUES)
    reasons: list[dict[str, Any]] = []

    for idx, fx in enumerate(fixtures):
        ref = fx.get("event_stream_ref")
        if not (isinstance(ref, str) and ref.startswith("path:")):
            raise EvidenceError(
                "FIXTURE_REF_INVALID",
                "fixture.event_stream_ref must be path:*",
                {"index": idx},
            )
        path = Path(ref.removeprefix("path:"))
        events = _load_hand_events(path, strict_mode=strict_mode)

        flop = _flop_dealt(events)
        hand_end = _get_single_event(events, "HandEnd")
        if "rake_base_pot_chips" not in hand_end and "total_rake_chips" not in hand_end:
            continue
        if "rake_base_pot_chips" not in hand_end or "total_rake_chips" not in hand_end:
            raise EvidenceError(
                "RAKE_FIELDS_MISSING",
                "HandEnd must include both rake_base_pot_chips and total_rake_chips for rake fixtures",
                {"event_stream_ref": ref},
            )
        rake_base = _as_int(
            hand_end.get("rake_base_pot_chips"),
            field="HandEnd.rake_base_pot_chips",
        )
        observed_total = _as_int(
            hand_end.get("total_rake_chips"),
            field="HandEnd.total_rake_chips",
        )

        eliminated: list[str] = []
        for mode in list(possible):
            expected = _expected_total_rake_chips(
                rake_base_pot_chips=rake_base,
                flop_dealt=flop,
                ruleset=ruleset,
                rounding_mode=mode,
            )
            if expected != observed_total:
                eliminated.append(mode)
                possible.discard(mode)

        if eliminated:
            reasons.append(
                {
                    "fixture_index": idx,
                    "event_stream_ref": ref,
                    "observed_total_rake_chips": observed_total,
                    "rake_base_pot_chips": rake_base,
                    "flop_dealt": flop,
                    "eliminated_modes": sorted(eliminated),
                }
            )

    return sorted(possible), reasons


def _seatmap_to_int_map(value: Any, *, field: str) -> dict[int, int]:
    if not isinstance(value, dict):
        raise EvidenceError("TYPE_ERROR", f"{field} must be object")
    out: dict[int, int] = {}
    for k, v in value.items():
        if not isinstance(k, str) or not k.isdigit():
            raise EvidenceError("TYPE_ERROR", f"{field} keys must be decimal strings")
        out[int(k)] = _as_int(v, field=f"{field}[{k}]")
    return out


def _iter_decision_actions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dp_by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for e in _iter_events(events, "DecisionPoint"):
        decision_id = _as_int(e.get("decision_id"), field="DecisionPoint.decision_id")
        state_hash = _as_str(e.get("state_hash"), field="DecisionPoint.state_hash")
        dp_by_key[(decision_id, state_hash)] = e

    actions: list[dict[str, Any]] = []
    for e in _iter_events(events, "ActionChosen"):
        decision_id = _as_int(e.get("decision_id"), field="ActionChosen.decision_id")
        state_hash = _as_str(e.get("state_hash"), field="ActionChosen.state_hash")
        dp = dp_by_key.get((decision_id, state_hash))
        if dp is None:
            raise EvidenceError(
                "DECISIONPOINT_MISSING",
                "ActionChosen has no matching DecisionPoint",
                {"decision_id": decision_id, "state_hash": state_hash},
            )

        snap = dp.get("snapshot_payload")
        if not isinstance(snap, dict):
            raise EvidenceError("SNAPSHOT_MISSING", "DecisionPoint.snapshot_payload must be object")

        actor_seat = _as_int(snap.get("actor_seat"), field="Snapshot.actor_seat")
        street = _as_str(snap.get("street"), field="Snapshot.street")
        if street not in STREET_VALUES:
            raise EvidenceError("UNSUPPORTED_VALUE", f"unsupported street: {street!r}")
        executed = e.get("executed_action")
        if not isinstance(executed, dict):
            raise EvidenceError("ACTION_MISSING", "ActionChosen.executed_action must be object")
        kind = _as_str(executed.get("kind"), field="ExecutedAction.kind")
        target = _as_int(
            executed.get("target_total_commit_chips"),
            field="ExecutedAction.target_total_commit_chips",
        )

        actions.append(
            {
                "decision_id": decision_id,
                "state_hash": state_hash,
                "street": street,
                "actor_seat": actor_seat,
                "kind": kind,
                "target_total_commit_chips": target,
            }
        )

    actions.sort(key=lambda x: x["decision_id"])
    return actions


def check_action_sequence_legality(
    events: list[dict[str, Any]],
    *,
    ruleset: dict[str, Any],
    reopen_on_short_allin: bool,
    strict_mode: bool,
) -> tuple[bool, dict[str, Any] | None]:
    hand_end = _get_single_event(events, "HandEnd")
    initial_stacks_by_seat = _seatmap_to_int_map(
        hand_end.get("initial_stacks_by_seat"),
        field="HandEnd.initial_stacks_by_seat",
    )

    seats = sorted(initial_stacks_by_seat.keys())
    commit: dict[int, int] = {s: 0 for s in seats}
    stack: dict[int, int] = {s: initial_stacks_by_seat[s] for s in seats}
    alive: set[int] = set(seats)
    allin: set[int] = {s for s in seats if stack[s] == 0}

    for e in _iter_events(events, "ForcedBets"):
        by_seat = e.get("by_seat_amount_chips")
        fb = _seatmap_to_int_map(by_seat, field="ForcedBets.by_seat_amount_chips")
        for s, amt in fb.items():
            if s not in stack:
                continue
            if amt < 0:
                return False, {"reason": "forced_bets_negative", "seat": s, "amount_chips": amt}
            if amt > stack[s]:
                return False, {
                    "reason": "forced_bets_exceed_stack",
                    "seat": s,
                    "amount_chips": amt,
                    "stack": stack[s],
                }
            commit[s] += amt
            stack[s] -= amt
            if stack[s] == 0:
                allin.add(s)

    actions = _iter_decision_actions(events)

    bb_chips = _as_int(
        ruleset.get("blinds", {}).get("bb_chips"),
        field="ruleset.blinds.bb_chips",
    )

    current_street: str | None = None
    last_full_raise_increment: int | None = None
    acted_since_last_full_raise: set[int] = set()
    raise_closed_for: set[int] | None = None

    for a in actions:
        decision_id = a["decision_id"]
        state_hash = a["state_hash"]
        street = a["street"]
        actor = a["actor_seat"]
        kind = a["kind"]
        target = a["target_total_commit_chips"]

        if actor not in alive:
            return False, {
                "reason": "actor_not_alive",
                "decision_id": decision_id,
                "state_hash": state_hash,
                "actor_seat": actor,
            }
        if actor in allin:
            return False, {
                "reason": "actor_allin_acted",
                "decision_id": decision_id,
                "state_hash": state_hash,
                "actor_seat": actor,
            }

        highest_commit = max(commit[s] for s in alive)
        required_to_call = highest_commit - commit[actor]
        if required_to_call < 0:
            return False, {
                "reason": "negative_to_call",
                "decision_id": decision_id,
                "state_hash": state_hash,
            }

        actor_stack = stack[actor]
        to_call = min(required_to_call, actor_stack)

        if street != current_street:
            current_street = street
            if street == "PREFLOP":
                street_opening_increment = highest_commit
            else:
                street_opening_increment = bb_chips
            last_full_raise_increment = street_opening_increment
            acted_since_last_full_raise = set()
            raise_closed_for = None

        assert last_full_raise_increment is not None

        if kind not in ACTION_KIND_VALUES:
            return False, {
                "reason": "unsupported_action_kind",
                "kind": kind,
                "decision_id": decision_id,
                "state_hash": state_hash,
            }

        if kind in ("BET", "RAISE") and raise_closed_for is not None and actor in raise_closed_for:
            return False, {
                "reason": "raise_not_reopened",
                "decision_id": decision_id,
                "state_hash": state_hash,
                "actor_seat": actor,
            }

        if target < commit[actor]:
            return False, {
                "reason": "target_below_commit",
                "decision_id": decision_id,
                "state_hash": state_hash,
            }

        delta = target - commit[actor]
        if delta > actor_stack:
            return False, {
                "reason": "target_exceeds_stack",
                "decision_id": decision_id,
                "state_hash": state_hash,
            }

        is_allin = (delta == actor_stack) and (delta > 0)

        if kind == "FOLD":
            if required_to_call <= 0:
                return False, {
                    "reason": "fold_when_no_to_call",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }
            if delta != 0:
                return False, {
                    "reason": "fold_changes_commit",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }
            alive.remove(actor)
            acted_since_last_full_raise.add(actor)
            continue

        if kind == "CHECK":
            if required_to_call != 0:
                return False, {
                    "reason": "check_when_to_call",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                    "required_to_call": required_to_call,
                }
            if delta != 0:
                return False, {
                    "reason": "check_changes_commit",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }
            acted_since_last_full_raise.add(actor)
            continue

        if kind == "CALL":
            if required_to_call <= 0:
                return False, {
                    "reason": "call_when_no_to_call",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }
            if target != commit[actor] + to_call:
                return False, {
                    "reason": "call_target_mismatch",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                    "expected": commit[actor] + to_call,
                    "observed": target,
                }
            if delta == 0:
                return False, {
                    "reason": "call_zero_delta",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }
            commit[actor] += delta
            stack[actor] -= delta
            if stack[actor] == 0:
                allin.add(actor)
            acted_since_last_full_raise.add(actor)
            continue

        if kind == "BET":
            if required_to_call != 0:
                return False, {
                    "reason": "bet_when_to_call",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }
            if delta <= 0:
                return False, {
                    "reason": "bet_non_positive",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }
            min_target = commit[actor] + bb_chips
            if target < min_target and not is_allin:
                return False, {
                    "reason": "bet_below_min",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                    "min_target": min_target,
                    "observed": target,
                }
            raise_increment = target - highest_commit
            if raise_increment < last_full_raise_increment and not is_allin:
                return False, {
                    "reason": "bet_increment_below_min",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }

            commit[actor] += delta
            stack[actor] -= delta
            if stack[actor] == 0:
                allin.add(actor)

            if raise_increment >= last_full_raise_increment:
                last_full_raise_increment = raise_increment
                acted_since_last_full_raise = {actor}
                raise_closed_for = None
            else:
                acted_since_last_full_raise.add(actor)
            continue

        if kind == "RAISE":
            if required_to_call <= 0:
                return False, {
                    "reason": "raise_when_no_to_call",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }
            if actor_stack <= to_call:
                return False, {
                    "reason": "raise_without_stack_space",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }
            if target <= highest_commit:
                return False, {
                    "reason": "raise_not_above_call",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                }

            raise_increment = target - highest_commit
            min_raise_to = highest_commit + last_full_raise_increment
            is_short = target < min_raise_to

            if is_short and not is_allin:
                return False, {
                    "reason": "raise_below_min_not_allin",
                    "decision_id": decision_id,
                    "state_hash": state_hash,
                    "min_raise_to": min_raise_to,
                    "observed": target,
                }

            commit[actor] += delta
            stack[actor] -= delta
            if stack[actor] == 0:
                allin.add(actor)

            if not is_short or (is_allin and reopen_on_short_allin):
                last_full_raise_increment = raise_increment
                acted_since_last_full_raise = {actor}
                raise_closed_for = None
            else:
                raise_closed_for = set(acted_since_last_full_raise)
                acted_since_last_full_raise.add(actor)
            continue

    return True, None


def infer_reopen_on_short_allin_flags(
    fixtures: list[dict[str, Any]],
    *,
    ruleset: dict[str, Any],
    strict_mode: bool,
) -> tuple[list[bool], list[dict[str, Any]]]:
    possible = {False, True}
    reasons: list[dict[str, Any]] = []

    for idx, fx in enumerate(fixtures):
        ref = fx.get("event_stream_ref")
        if not (isinstance(ref, str) and ref.startswith("path:")):
            raise EvidenceError(
                "FIXTURE_REF_INVALID",
                "fixture.event_stream_ref must be path:*",
                {"index": idx},
            )
        path = Path(ref.removeprefix("path:"))

        events = _load_hand_events(path, strict_mode=strict_mode)
        has_action = any(e.get("event") == "ActionChosen" for e in events)
        has_dp = any(e.get("event") == "DecisionPoint" for e in events)
        if not has_action and not has_dp:
            continue
        if has_action != has_dp:
            raise EvidenceError(
                "DECISION_EVENTS_INCOMPLETE",
                "DecisionPoint/ActionChosen must both exist for decision fixtures",
                {"event_stream_ref": ref},
            )

        eliminated: list[bool] = []
        for flag in list(possible):
            ok, fail = check_action_sequence_legality(
                events,
                ruleset=ruleset,
                reopen_on_short_allin=flag,
                strict_mode=strict_mode,
            )
            if not ok:
                eliminated.append(flag)
                possible.discard(flag)
                reasons.append(
                    {
                        "fixture_index": idx,
                        "event_stream_ref": ref,
                        "reopen_on_short_allin": flag,
                        "failure": fail,
                    }
                )

        if eliminated:
            continue

    return sorted(possible), reasons
