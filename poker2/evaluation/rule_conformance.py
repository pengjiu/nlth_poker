from __future__ import annotations

# RuleConformanceReport generator (ARCHIETECTURE.md 3.10.1).
#
# Important: this module must consume only EventStream + RuleSet facts; it must not
# depend on Environment engine internals.

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from poker2.contractkit import validate_digest_object
from poker2.protocol.eventstream import EventStreamError, event_stream_digest_from_file, read_ndjson
from poker2.protocol.rake import RakeError, compute_total_rake_chips
from poker2.protocol.report_schema import RULE_CONFORMANCE_CHECKED_ITEM_VALUES
from poker2.protocol.ruleset import RuleSetError, ruleset_id, validate_ruleset


@dataclass(frozen=True)
class RuleConformanceError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise RuleConformanceError("TYPE_ERROR", f"{field} must be int, got bool")
    if not isinstance(value, int):
        raise RuleConformanceError("TYPE_ERROR", f"{field} must be int, got {type(value).__name__}")
    return value


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise RuleConformanceError("TYPE_ERROR", f"{field} must be str, got {type(value).__name__}")
    return value


def _as_obj(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuleConformanceError("TYPE_ERROR", f"{field} must be object")
    return value


def _seatmap(value: Any, *, field: str) -> dict[int, int]:
    obj = _as_obj(value, field=field)
    out: dict[int, int] = {}
    for k, v in obj.items():
        if not isinstance(k, str) or not k.isdigit():
            raise RuleConformanceError("TYPE_ERROR", f"{field} keys must be decimal strings")
        out[int(k)] = _as_int(v, field=f"{field}[{k}]")
    return out


def _split_hands(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hands: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for e in events:
        if e.get("event") == "HandStart":
            if cur is not None:
                hands.append(cur)
            cur = {"hand_id": e.get("hand_id"), "events": [e]}
            continue
        if cur is None:
            continue
        cur["events"].append(e)
        if e.get("event") == "HandEnd":
            hands.append(cur)
            cur = None
    if cur is not None:
        hands.append(cur)
    return hands


def _hand_selector(hand_id: str, *, decision_id: int | None, state_hash: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {"hand_id": hand_id}
    if decision_id is not None or state_hash is not None:
        out["decision_id"] = decision_id
        out["state_hash"] = state_hash
    return out


def _failure(
    *,
    event_stream_ref: str,
    event_stream_digest: dict[str, Any],
    hand_id: str,
    item: str,
    reason: str,
    decision_id: int | None = None,
    state_hash: str | None = None,
    expected: Any | None = None,
    observed: Any | None = None,
) -> dict[str, Any]:
    if (decision_id is None) != (state_hash is None):
        decision_id = None
        state_hash = None
    selector = _hand_selector(hand_id, decision_id=decision_id, state_hash=state_hash)
    loc = {"decision_id": decision_id, "state_hash": state_hash}
    return {
        "hand_selector": selector,
        "item": item,
        "reason": reason,
        "decision_id_or_state_hash": loc,
        "expected_or_null": expected,
        "observed_or_null": observed,
        "evidence_ref": {
            "event_stream_ref": event_stream_ref,
            "event_stream_digest": event_stream_digest,
            "hand_selector": selector,
        },
    }


def _checked_items_sorted(values: Iterable[str]) -> list[str]:
    uniq = sorted(set(values))
    allowed = set(RULE_CONFORMANCE_CHECKED_ITEM_VALUES)
    unknown = [v for v in uniq if v not in allowed]
    if unknown:
        raise RuleConformanceError("UNSUPPORTED_VALUE", "unknown checked_items token(s)", {"unknown": unknown})
    return uniq


def _event_stream_ref_for_path(path: Path) -> str:
    return f"path:{path}"


def _event_stream_digest_obj(path: Path, *, strict_mode: bool) -> dict[str, Any]:
    digest_hex = event_stream_digest_from_file(path, strict_mode=strict_mode)
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def _find_single_event(hand_events: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None
    for e in hand_events:
        if e.get("event") != name:
            continue
        if found is not None:
            raise RuleConformanceError("EVENT_COUNT_MISMATCH", f"expected <=1 {name} per hand")
        found = e
    return found


def _iter_events(hand_events: list[dict[str, Any]], name: str) -> Iterable[dict[str, Any]]:
    for e in hand_events:
        if e.get("event") == name:
            yield e


def _flop_dealt(hand_events: list[dict[str, Any]]) -> bool:
    for e in _iter_events(hand_events, "StreetDealt"):
        if e.get("street") == "FLOP":
            return True
    return False


def _check_ledger(
    *,
    hand_id: str,
    hand_events: list[dict[str, Any]],
    event_stream_ref: str,
    event_stream_digest: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    hand_end = _find_single_event(hand_events, "HandEnd")
    if hand_end is None:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="ledger_conservation",
                reason="missing_hand_end",
            )
        )
        return failures

    try:
        initial = _seatmap(hand_end.get("initial_stacks_by_seat"), field="HandEnd.initial_stacks_by_seat")
        final = _seatmap(hand_end.get("final_stacks_by_seat"), field="HandEnd.final_stacks_by_seat")
        deltas = _seatmap(hand_end.get("stack_deltas_by_seat"), field="HandEnd.stack_deltas_by_seat")
        total_rake = _as_int(hand_end.get("total_rake_chips"), field="HandEnd.total_rake_chips")
        invariants_ok = hand_end.get("invariants_ok")
        if not isinstance(invariants_ok, bool):
            raise RuleConformanceError("TYPE_ERROR", "HandEnd.invariants_ok must be bool")
    except RuleConformanceError as e:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="ledger_conservation",
                reason="handend_schema_invalid",
                expected=None,
                observed={"error": {"code": e.code, "message": e.message, "details": e.details}},
            )
        )
        return failures

    if not invariants_ok:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="ledger_conservation",
                reason="invariants_ok_false",
                expected=True,
                observed=False,
            )
        )

    seats = sorted(initial.keys())
    if sorted(final.keys()) != seats or sorted(deltas.keys()) != seats:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="ledger_conservation",
                reason="seat_domain_mismatch",
                expected={"seats": seats},
                observed={"initial": sorted(initial.keys()), "final": sorted(final.keys()), "deltas": sorted(deltas.keys())},
            )
        )
        return failures

    for s in seats:
        if deltas[s] != final[s] - initial[s]:
            failures.append(
                _failure(
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    hand_id=hand_id,
                    item="ledger_conservation",
                    reason="delta_mismatch",
                    expected=final[s] - initial[s],
                    observed=deltas[s],
                )
            )
            break

    sum_deltas = sum(deltas.values())
    if sum_deltas + total_rake != 0:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="ledger_conservation",
                reason="sum_deltas_plus_rake_not_zero",
                expected=0,
                observed=sum_deltas + total_rake,
            )
        )

    pot_balance_delta = 0
    pot_rake_sum = 0
    for e in _iter_events(hand_events, "PotUpdate"):
        pot_delta = _as_int(e.get("pot_chips_delta"), field="PotUpdate.pot_chips_delta")
        rake_delta = _as_int(e.get("rake_chips_delta"), field="PotUpdate.rake_chips_delta")
        pot_balance_delta += pot_delta - rake_delta
        pot_rake_sum += rake_delta

    if pot_balance_delta != 0:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="ledger_conservation",
                reason="pot_balance_delta_not_zero",
                expected=0,
                observed=pot_balance_delta,
            )
        )

    if pot_rake_sum != total_rake:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="ledger_conservation",
                reason="potupdate_rake_sum_mismatch",
                expected=total_rake,
                observed=pot_rake_sum,
            )
        )

    return failures


def _rotate_next_seat(seats: list[int], current: int) -> int | None:
    if not seats or current not in seats:
        return None
    idx = seats.index(current)
    return seats[(idx + 1) % len(seats)]


def _check_button_rotation(
    *,
    hands: list[dict[str, Any]],
    event_stream_ref: str,
    event_stream_digest: dict[str, Any],
) -> list[dict[str, Any]]:
    starts: list[dict[str, Any]] = []
    for h in hands:
        evs = h.get("events")
        if not isinstance(evs, list):
            continue
        hs = _find_single_event(evs, "HandStart")
        if hs is None:
            continue
        starts.append(hs)

    if len(starts) < 2:
        return []

    starts.sort(key=lambda e: _as_int(e.get("hand_seq"), field="HandStart.hand_seq"))
    failures: list[dict[str, Any]] = []
    for prev, cur in zip(starts, starts[1:]):
        hand_id = _as_str(cur.get("hand_id"), field="HandStart.hand_id")
        seats_prev = prev.get("seats_in_hand")
        seats_cur = cur.get("seats_in_hand")
        if not (isinstance(seats_prev, list) and all(isinstance(x, int) for x in seats_prev)):
            continue
        if seats_prev != seats_cur:
            continue
        prev_btn = _as_int(prev.get("button_seat"), field="HandStart.button_seat")
        cur_btn = _as_int(cur.get("button_seat"), field="HandStart.button_seat")
        expected = _rotate_next_seat(seats_prev, prev_btn)
        if expected is None:
            continue
        if cur_btn != expected:
            failures.append(
                _failure(
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    hand_id=hand_id,
                    item="button_rotation",
                    reason="button_seat_not_rotated",
                    expected=expected,
                    observed=cur_btn,
                )
            )
            break

    return failures


def _check_rake(
    *,
    hand_id: str,
    hand_events: list[dict[str, Any]],
    ruleset: dict[str, Any],
    check_rake: bool,
    check_no_flop_no_drop: bool,
    strict_mode: bool,
    event_stream_ref: str,
    event_stream_digest: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    hand_end = _find_single_event(hand_events, "HandEnd")
    if hand_end is None:
        return failures

    rake_base = hand_end.get("rake_base_pot_chips")
    total_rake = hand_end.get("total_rake_chips")
    if rake_base is None or total_rake is None:
        if strict_mode:
            failures.append(
                _failure(
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    hand_id=hand_id,
                    item="rake",
                    reason="rake_fields_missing",
                )
            )
        return failures

    rake_base_i = _as_int(rake_base, field="HandEnd.rake_base_pot_chips")
    total_rake_i = _as_int(total_rake, field="HandEnd.total_rake_chips")
    flop = _flop_dealt(hand_events)

    if check_rake:
        try:
            expected = compute_total_rake_chips(
                rake_base_pot_chips=rake_base_i,
                flop_dealt=flop,
                ruleset=ruleset,
            )
        except RakeError as e:
            failures.append(
                _failure(
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    hand_id=hand_id,
                    item="rake",
                    reason="rake_compute_error",
                    expected=None,
                    observed={"error": {"code": e.code, "message": e.message}},
                )
            )
            return failures

        if expected != total_rake_i:
            failures.append(
                _failure(
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    hand_id=hand_id,
                    item="rake",
                    reason="total_rake_mismatch",
                    expected=expected,
                    observed=total_rake_i,
                )
            )

    rake_obj = ruleset.get("rake")
    if (
        check_no_flop_no_drop
        and isinstance(rake_obj, dict)
        and rake_obj.get("no_flop_no_drop") is True
        and not flop
        and total_rake_i != 0
    ):
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="no_flop_no_drop",
                reason="rake_taken_without_flop",
                expected=0,
                observed=total_rake_i,
            )
        )

    return failures


def _check_forced_bets(
    *,
    hand_id: str,
    hand_events: list[dict[str, Any]],
    ruleset: dict[str, Any],
    event_stream_ref: str,
    event_stream_digest: dict[str, Any],
) -> list[dict[str, Any]]:
    hand_start = _find_single_event(hand_events, "HandStart")
    if hand_start is None:
        return [
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="forced_bets",
                reason="missing_hand_start",
            )
        ]

    seats = hand_start.get("seats_in_hand")
    if not (isinstance(seats, list) and all(isinstance(x, int) for x in seats)):
        return [
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="forced_bets",
                reason="seats_in_hand_invalid",
            )
        ]

    button_seat = _as_int(hand_start.get("button_seat"), field="HandStart.button_seat")
    if button_seat not in seats:
        return [
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="forced_bets",
                reason="button_not_in_seats",
                expected={"seats_in_hand": seats},
                observed=button_seat,
            )
        ]

    # Aggregate ForcedBets amounts by kind.
    forced_by_kind: dict[str, dict[int, int]] = {}
    for e in _iter_events(hand_events, "ForcedBets"):
        kind = _as_str(e.get("kind"), field="ForcedBets.kind")
        by_seat = _seatmap(e.get("by_seat_amount_chips"), field="ForcedBets.by_seat_amount_chips")
        forced_by_kind[kind] = by_seat

    failures: list[dict[str, Any]] = []

    blinds = ruleset.get("blinds", {})
    sb = _as_int(blinds.get("sb_chips"), field="ruleset.blinds.sb_chips")
    bb = _as_int(blinds.get("bb_chips"), field="ruleset.blinds.bb_chips")

    if len(seats) == 2:
        sb_seat = button_seat
        bb_seat = next(s for s in seats if s != button_seat)
    else:
        sb_seat = _rotate_next_seat(seats, button_seat)
        bb_seat = _rotate_next_seat(seats, sb_seat) if sb_seat is not None else None
    if sb_seat is None or bb_seat is None:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="forced_bets",
                reason="cannot_locate_blinds",
            )
        )
        return failures

    sb_evt = forced_by_kind.get("sb", {})
    bb_evt = forced_by_kind.get("bb", {})

    if sb_seat not in sb_evt:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="forced_bets",
                reason="sb_missing",
                expected={"seat": sb_seat, "amount_max": sb},
                observed=sb_evt,
            )
        )
    else:
        amt = sb_evt[sb_seat]
        if amt < 0 or amt > sb:
            failures.append(
                _failure(
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    hand_id=hand_id,
                    item="forced_bets",
                    reason="sb_amount_invalid",
                    expected={"seat": sb_seat, "amount_max": sb},
                    observed={"seat": sb_seat, "amount": amt},
                )
            )

    if bb_seat not in bb_evt:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="forced_bets",
                reason="bb_missing",
                expected={"seat": bb_seat, "amount_max": bb},
                observed=bb_evt,
            )
        )
    else:
        amt = bb_evt[bb_seat]
        if amt < 0 or amt > bb:
            failures.append(
                _failure(
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    hand_id=hand_id,
                    item="forced_bets",
                    reason="bb_amount_invalid",
                    expected={"seat": bb_seat, "amount_max": bb},
                    observed={"seat": bb_seat, "amount": amt},
                )
            )

    ante = ruleset.get("ante")
    ante_evt = forced_by_kind.get("ante", {})
    if ante is None:
        if ante_evt:
            failures.append(
                _failure(
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    hand_id=hand_id,
                    item="forced_bets",
                    reason="unexpected_ante",
                    expected=None,
                    observed=ante_evt,
                )
            )
    elif isinstance(ante, dict):
        kind = ante.get("kind")
        if kind == "uniform":
            ante_amt = _as_int(ante.get("ante_chips"), field="ruleset.ante.ante_chips")
            for s in seats:
                observed = ante_evt.get(s, 0)
                if observed < 0 or observed > ante_amt:
                    failures.append(
                        _failure(
                            event_stream_ref=event_stream_ref,
                            event_stream_digest=event_stream_digest,
                            hand_id=hand_id,
                            item="forced_bets",
                            reason="ante_amount_invalid",
                            expected={"seat": s, "amount_max": ante_amt},
                            observed={"seat": s, "amount": observed},
                        )
                    )
                    break
        elif kind == "by_seat":
            by_seat = _as_obj(ante.get("by_seat_ante_chips"), field="ruleset.ante.by_seat_ante_chips")
            for s in seats:
                key = str(s)
                expected_amt = _as_int(by_seat.get(key, 0), field=f"ruleset.ante.by_seat_ante_chips[{key}]")
                observed = ante_evt.get(s, 0)
                if observed < 0 or observed > expected_amt:
                    failures.append(
                        _failure(
                            event_stream_ref=event_stream_ref,
                            event_stream_digest=event_stream_digest,
                            hand_id=hand_id,
                            item="forced_bets",
                            reason="ante_amount_invalid",
                            expected={"seat": s, "amount_max": expected_amt},
                            observed={"seat": s, "amount": observed},
                        )
                    )
                    break
        else:
            failures.append(
                _failure(
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    hand_id=hand_id,
                    item="forced_bets",
                    reason="unsupported_ante_kind",
                    expected={"kind": "uniform|by_seat"},
                    observed=kind,
                )
            )
    else:
        failures.append(
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="forced_bets",
                reason="ante_not_object_or_null",
            )
        )

    return failures


def _check_min_raise_and_reopen(
    *,
    hand_id: str,
    hand_events: list[dict[str, Any]],
    ruleset: dict[str, Any],
    check_min_raise: bool,
    check_allin_reopen: bool,
    strict_mode: bool,
    event_stream_ref: str,
    event_stream_digest: dict[str, Any],
) -> list[dict[str, Any]]:
    reopen = ruleset.get("min_raise_rule", {}).get("reopen_on_short_allin")
    if not isinstance(reopen, bool):
        if not strict_mode:
            return []
        return [
            _failure(
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                hand_id=hand_id,
                item="allin_reopen" if check_allin_reopen else "min_raise",
                reason="ruleset_missing_reopen_flag",
            )
        ]

    # Index DecisionPoint snapshot_payload by (decision_id, state_hash) for replayable linkage.
    dp_by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for e in hand_events:
        if e.get("event") != "DecisionPoint":
            continue
        did = e.get("decision_id")
        sh = e.get("state_hash")
        snap = e.get("snapshot_payload")
        if isinstance(did, int) and isinstance(sh, str) and isinstance(snap, dict):
            dp_by_key[(did, sh)] = snap

    def _snapshot_for_action(action_evt: dict[str, Any]) -> tuple[int | None, str | None, dict[str, Any] | None]:
        did = action_evt.get("decision_id")
        sh = action_evt.get("state_hash")
        did_i = did if isinstance(did, int) else None
        sh_s = sh if isinstance(sh, str) else None
        if did_i is None or sh_s is None:
            return did_i, sh_s, None
        return did_i, sh_s, dp_by_key.get((did_i, sh_s))

    def _as_int_or_none(v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, int):
            return None
        return v

    failures: list[dict[str, Any]] = []

    folded: set[int] = set()
    allin: set[int] = set()

    current_street: str | None = None
    acted_since_last_full_raise: set[int] = set()
    pending_no_reopen: set[int] = set()
    pending_must_reopen: set[int] = set()
    last_full_raise_increment: int | None = None

    for e in hand_events:
        if e.get("event") != "ActionChosen":
            continue

        decision_id, state_hash, snap = _snapshot_for_action(e)
        if not isinstance(snap, dict):
            if strict_mode:
                failures.append(
                    _failure(
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        hand_id=hand_id,
                        item="allin_reopen" if check_allin_reopen else "min_raise",
                        reason="decisionpoint_missing",
                        decision_id=decision_id,
                        state_hash=state_hash,
                        expected=None,
                        observed={"event": "ActionChosen", "decision_id": decision_id, "state_hash": state_hash},
                    )
                )
            continue

        street = snap.get("street")
        actor_seat = _as_int_or_none(snap.get("actor_seat"))
        to_call = _as_int_or_none(snap.get("to_call_chips"))
        actor_commit = _as_int_or_none(snap.get("actor_commit_chips"))
        actor_stack = _as_int_or_none(snap.get("actor_stack_chips"))
        min_raise_to = _as_int_or_none(snap.get("min_raise_to_chips"))
        max_raise_to = _as_int_or_none(snap.get("max_raise_to_chips"))

        if not isinstance(street, str) or actor_seat is None or to_call is None or actor_commit is None or actor_stack is None:
            if strict_mode:
                failures.append(
                    _failure(
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        hand_id=hand_id,
                        item="allin_reopen" if check_allin_reopen else "min_raise",
                        reason="snapshot_missing_fields",
                        decision_id=decision_id,
                        state_hash=state_hash,
                        expected=None,
                        observed={"snapshot_payload": snap},
                    )
                )
            continue

        if current_street != street:
            current_street = street
            acted_since_last_full_raise = set()
            pending_no_reopen = set()
            pending_must_reopen = set()
            last_full_raise_increment = None

        executed = e.get("executed_action")
        if not isinstance(executed, dict):
            if strict_mode:
                failures.append(
                    _failure(
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        hand_id=hand_id,
                        item="allin_reopen" if check_allin_reopen else "min_raise",
                        reason="executed_action_missing",
                        decision_id=decision_id,
                        state_hash=state_hash,
                        expected=None,
                        observed={"ActionChosen": e},
                    )
                )
            continue

        kind = executed.get("kind")
        target = _as_int_or_none(executed.get("target_total_commit_chips"))
        if not isinstance(kind, str) or target is None:
            if strict_mode:
                failures.append(
                    _failure(
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        hand_id=hand_id,
                        item="allin_reopen" if check_allin_reopen else "min_raise",
                        reason="executed_action_invalid",
                        decision_id=decision_id,
                        state_hash=state_hash,
                        expected=None,
                        observed={"executed_action": executed},
                    )
                )
            continue

        call_target = actor_commit + to_call
        is_allin_action = (target == actor_commit + actor_stack) or (max_raise_to is not None and target == max_raise_to)
        can_raise_capacity = actor_stack > to_call and max_raise_to is not None

        if check_allin_reopen and actor_seat in pending_no_reopen:
            if can_raise_capacity and min_raise_to is not None:
                failures.append(
                    _failure(
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        hand_id=hand_id,
                        item="allin_reopen",
                        reason="raise_reopened",
                        decision_id=decision_id,
                        state_hash=state_hash,
                        expected={"min_raise_to_chips": None},
                        observed={"min_raise_to_chips": min_raise_to, "max_raise_to_chips": max_raise_to},
                    )
                )
            pending_no_reopen.discard(actor_seat)

        if check_allin_reopen and actor_seat in pending_must_reopen:
            if can_raise_capacity and min_raise_to is None:
                failures.append(
                    _failure(
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        hand_id=hand_id,
                        item="allin_reopen",
                        reason="raise_not_reopened",
                        decision_id=decision_id,
                        state_hash=state_hash,
                        expected={"min_raise_to_chips": "non-null"},
                        observed={"min_raise_to_chips": None, "max_raise_to_chips": max_raise_to},
                    )
                )
            pending_must_reopen.discard(actor_seat)

        if check_min_raise and kind in ("BET", "RAISE"):
            if min_raise_to is None or max_raise_to is None:
                failures.append(
                    _failure(
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        hand_id=hand_id,
                        item="min_raise",
                        reason="raise_not_allowed",
                        decision_id=decision_id,
                        state_hash=state_hash,
                        expected={"min_raise_to_chips": "non-null", "max_raise_to_chips": "non-null"},
                        observed={"min_raise_to_chips": min_raise_to, "max_raise_to_chips": max_raise_to},
                    )
                )
            elif target < min_raise_to or target > max_raise_to:
                failures.append(
                    _failure(
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        hand_id=hand_id,
                        item="min_raise",
                        reason="raise_target_out_of_bounds",
                        decision_id=decision_id,
                        state_hash=state_hash,
                        expected={"min_raise_to_chips": min_raise_to, "max_raise_to_chips": max_raise_to},
                        observed={"target_total_commit_chips": target},
                    )
                )

        # Track fold/all-in for the "previously acted" seat set.
        if kind == "FOLD":
            folded.add(actor_seat)
            pending_no_reopen.discard(actor_seat)
            pending_must_reopen.discard(actor_seat)
        elif is_allin_action:
            allin.add(actor_seat)
            pending_no_reopen.discard(actor_seat)
            pending_must_reopen.discard(actor_seat)

        if kind in ("BET", "RAISE"):
            increment = target - call_target
            if increment > 0:
                if last_full_raise_increment is None:
                    last_full_raise_increment = increment
                    acted_since_last_full_raise = {actor_seat}
                    pending_no_reopen = set()
                    pending_must_reopen = set()
                else:
                    if increment < last_full_raise_increment and is_allin_action:
                        prev_acted = {
                            s
                            for s in acted_since_last_full_raise
                            if s != actor_seat and s not in folded and s not in allin
                        }
                        if reopen:
                            pending_must_reopen |= prev_acted
                            last_full_raise_increment = increment
                            acted_since_last_full_raise = {actor_seat}
                        else:
                            pending_no_reopen |= prev_acted
                            acted_since_last_full_raise.add(actor_seat)
                    elif increment < last_full_raise_increment and not is_allin_action and check_min_raise:
                        failures.append(
                            _failure(
                                event_stream_ref=event_stream_ref,
                                event_stream_digest=event_stream_digest,
                                hand_id=hand_id,
                                item="min_raise",
                                reason="raise_below_min_increment",
                                decision_id=decision_id,
                                state_hash=state_hash,
                                expected={"min_increment": last_full_raise_increment},
                                observed={"raise_increment": increment},
                            )
                        )
                        acted_since_last_full_raise.add(actor_seat)
                    else:
                        last_full_raise_increment = increment
                        acted_since_last_full_raise = {actor_seat}
                        pending_no_reopen = set()
                        pending_must_reopen = set()
            else:
                acted_since_last_full_raise.add(actor_seat)
        else:
            acted_since_last_full_raise.add(actor_seat)

    return failures


def rule_conformance_report_from_eventstream(
    event_stream_path: Path,
    *,
    event_stream_ref: str | None,
    ruleset: dict[str, Any],
    checked_items: Iterable[str] | None,
    strict_mode: bool,
) -> dict[str, Any]:
    try:
        validate_ruleset(ruleset, strict_mode=strict_mode)
    except RuleSetError as e:
        raise RuleConformanceError(e.code, e.message) from e

    objs = read_ndjson(event_stream_path, strict_mode=True)
    if not objs:
        raise RuleConformanceError("EMPTY_EVENTSTREAM", "eventstream is empty")
    header = _as_obj(objs[0], field="EventStream.header")

    try:
        digest = _event_stream_digest_obj(event_stream_path, strict_mode=True)
        header_digest = header.get("event_stream_digest")
        validate_digest_object(header_digest, strict_mode=True)
        if header_digest["hex"] != digest["hex"]:
            raise RuleConformanceError("EVENTSTREAM_DIGEST_MISMATCH", "header digest does not match computed", {"computed": digest, "header": header_digest})
    except (EventStreamError, RuleConformanceError) as e:
        if isinstance(e, EventStreamError):
            raise RuleConformanceError(e.code, e.message) from e
        raise

    events: list[dict[str, Any]] = []
    for idx, obj in enumerate(objs[1:], start=1):
        if not isinstance(obj, dict):
            raise RuleConformanceError("EVENT_NOT_OBJECT", "event record must be object", {"index": idx})
        events.append(obj)

    hands = _split_hands(events)
    if strict_mode and not hands:
        raise RuleConformanceError("NO_HANDS", "eventstream contains no HandStart/HandEnd blocks")

    es_ref = event_stream_ref if event_stream_ref is not None else _event_stream_ref_for_path(event_stream_path)
    es_digest = digest

    default_items = set(RULE_CONFORMANCE_CHECKED_ITEM_VALUES)
    if len(hands) < 2:
        default_items.discard("button_rotation")
    items = _checked_items_sorted(checked_items if checked_items is not None else default_items)

    failures: list[dict[str, Any]] = []

    # Cross-hand checks.
    if "button_rotation" in items:
        failures.extend(_check_button_rotation(hands=hands, event_stream_ref=es_ref, event_stream_digest=es_digest))

    # Hand-level checks.
    for h in hands:
        raw_hand_id = h.get("hand_id")
        if not isinstance(raw_hand_id, str):
            if strict_mode:
                raise RuleConformanceError("HAND_ID_MISSING", "HandStart.hand_id missing or not string")
            continue
        hand_id = raw_hand_id
        hand_events = h.get("events")
        if not isinstance(hand_events, list) or not all(isinstance(e, dict) for e in hand_events):
            if strict_mode:
                raise RuleConformanceError("HAND_EVENTS_INVALID", "hand events invalid", {"hand_id": hand_id})
            continue
        he = [e for e in hand_events if isinstance(e, dict)]

        if "ledger_conservation" in items:
            failures.extend(_check_ledger(hand_id=hand_id, hand_events=he, event_stream_ref=es_ref, event_stream_digest=es_digest))

        if "forced_bets" in items:
            failures.extend(_check_forced_bets(hand_id=hand_id, hand_events=he, ruleset=ruleset, event_stream_ref=es_ref, event_stream_digest=es_digest))

        if "rake" in items or "no_flop_no_drop" in items:
            failures.extend(
                _check_rake(
                    hand_id=hand_id,
                    hand_events=he,
                    ruleset=ruleset,
                    check_rake=("rake" in items),
                    check_no_flop_no_drop=("no_flop_no_drop" in items),
                    strict_mode=strict_mode,
                    event_stream_ref=es_ref,
                    event_stream_digest=es_digest,
                )
            )

        if "min_raise" in items or "allin_reopen" in items:
            failures.extend(
                _check_min_raise_and_reopen(
                    hand_id=hand_id,
                    hand_events=he,
                    ruleset=ruleset,
                    check_min_raise=("min_raise" in items),
                    check_allin_reopen=("allin_reopen" in items),
                    strict_mode=strict_mode,
                    event_stream_ref=es_ref,
                    event_stream_digest=es_digest,
                )
            )

    # Report context uses explicit IDs (hashes).
    rid = ruleset_id(ruleset, strict_mode=True)
    opts = header.get("options_hash")
    triad = None
    schema_hash = header.get("schema_hash")
    scenario_id = header.get("scenario_id")
    provenance_ref = header.get("provenance_ref")
    event_ruleset_id: str | None = None
    for e in events:
        if e.get("event") == "HandStart":
            event_ruleset_id = e.get("ruleset_id") if isinstance(e.get("ruleset_id"), str) else None
            triad = e.get("triad")
            schema_hash = e.get("schema_hash", schema_hash)
            scenario_id = header.get("scenario_id", scenario_id)
            opts = e.get("options_hash", opts)
            provenance_ref = e.get("provenance_ref", provenance_ref)
            break
    if strict_mode and event_ruleset_id is not None and event_ruleset_id != rid:
        raise RuleConformanceError(
            "RULESET_ID_MISMATCH",
            "ruleset_id in EventStream does not match supplied RuleSet",
            {"event": event_ruleset_id, "supplied": rid},
        )

    context = {
        "scenario_id": scenario_id,
        "ruleset_id": rid,
        "triad": triad,
        "schema_hash": schema_hash,
        "options_hash": opts,
        "provenance_ref": provenance_ref,
        "event_stream_ref": es_ref,
        "event_stream_digest": es_digest,
    }

    sampled_hands_count = len([h for h in hands if isinstance(h.get("hand_id"), str)])

    return {
        "context": context,
        "sampled_hands_count": sampled_hands_count,
        "checked_items": items,
        "failures_count": len(failures),
        "failures": failures,
    }
