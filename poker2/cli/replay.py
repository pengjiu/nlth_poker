from __future__ import annotations

# CLI: replay an EventStream by hand_selector (ARCHIETECTURE.md 5.1.1).

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import validate_digest_object
from poker2.protocol.eventstream import EventStreamError, event_stream_digest_from_objects, read_ndjson


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


@dataclass
class ReplayError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _first_event(events: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for e in events:
        if e.get("event") == name:
            return e
    return None


def _split_hands_with_event_index(
    events_with_index: list[tuple[int, dict[str, Any]]],
    *,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    hands: list[dict[str, Any]] = []
    cur: list[tuple[int, dict[str, Any]]] = []
    for idx, e in events_with_index:
        if e.get("event") == "HandStart":
            if cur:
                if strict_mode:
                    raise ReplayError("HAND_BLOCK_UNTERMINATED", "previous HandStart missing HandEnd")
                cur = []
            cur = [(idx, e)]
            continue
        if not cur:
            continue
        cur.append((idx, e))
        if e.get("event") == "HandEnd":
            hands.append(
                {
                    "hand_id": cur[0][1].get("hand_id"),
                    "events_with_index": cur,
                }
            )
            cur = []
    if strict_mode and cur:
        raise ReplayError("HAND_BLOCK_UNTERMINATED", "HandStart missing HandEnd")
    return hands


def _validate_selector(
    *,
    hand_id: str | None,
    decision_id: int | None,
    state_hash: str | None,
    strict_mode: bool,
) -> dict[str, Any]:
    selector: dict[str, Any] = {
        "hand_id": hand_id,
        "decision_id": decision_id,
        "state_hash": state_hash,
        "event_seq_range": None,
    }

    if strict_mode and (decision_id is None) != (state_hash is None):
        raise ReplayError(
            "SELECTOR_INCOMPLETE",
            "when selecting a DecisionPoint/ActionChosen, decision_id and state_hash must both be provided",
        )
    if strict_mode and hand_id is None:
        raise ReplayError("SELECTOR_MISSING_HAND_ID", "hand_id is required")
    return selector


def replay_eventstream(
    *,
    event_stream_path: Path,
    strict_mode: bool,
    hand_id: str | None,
    decision_id: int | None,
    state_hash: str | None,
) -> dict[str, Any]:
    objs = read_ndjson(event_stream_path, strict_mode=strict_mode)
    if strict_mode and not objs:
        raise ReplayError("EMPTY_EVENTSTREAM", "EventStream must contain header and events")
    header_obj = objs[0] if objs else None
    if not isinstance(header_obj, dict):
        raise ReplayError("HEADER_NOT_OBJECT", "EventStream header must be a JSON object")
    header: dict[str, Any] = header_obj

    hdr_digest_obj = header.get("event_stream_digest")
    try:
        validate_digest_object(hdr_digest_obj, strict_mode=True)
    except Exception as e:
        raise ReplayError("HEADER_DIGEST_INVALID", "event_stream_digest invalid", {"error": str(e)}) from e

    computed_hex = event_stream_digest_from_objects(objs, strict_mode=strict_mode)
    if computed_hex != hdr_digest_obj["hex"]:
        raise ReplayError(
            "EVENT_STREAM_DIGEST_MISMATCH",
            "computed event_stream_digest does not match header",
            {"expected": hdr_digest_obj["hex"], "computed": computed_hex},
        )

    events_raw = objs[1:]
    events: list[dict[str, Any]] = []
    events_with_index: list[tuple[int, dict[str, Any]]] = []
    for idx, e in enumerate(events_raw, start=1):
        if not isinstance(e, dict):
            raise ReplayError("EVENT_NOT_OBJECT", "event record must be a JSON object", {"index": idx})
        events.append(e)
        events_with_index.append((idx, e))

    hands = _split_hands_with_event_index(events_with_index, strict_mode=strict_mode)
    if strict_mode and not hands:
        raise ReplayError("NO_HANDS", "eventstream contains no HandStart/HandEnd blocks")

    selected_hand_id: str | None = hand_id
    if selected_hand_id is None:
        first_hand_start = _first_event(events, "HandStart")
        if first_hand_start is None:
            raise ReplayError("HAND_START_MISSING", "HandStart event missing")
        actual_hand_id = first_hand_start.get("hand_id")
        if not isinstance(actual_hand_id, str):
            raise ReplayError("HAND_ID_INVALID", "HandStart.hand_id must be string")
        selected_hand_id = actual_hand_id

    selected = next((h for h in hands if h.get("hand_id") == selected_hand_id), None)
    if selected is None:
        raise ReplayError(
            "HAND_ID_MISMATCH",
            "hand_id does not match EventStream",
            {"expected": selected_hand_id, "available": [h.get("hand_id") for h in hands]},
        )
    selected_events_with_index = selected.get("events_with_index")
    if not isinstance(selected_events_with_index, list):
        raise ReplayError("HAND_EVENTS_INVALID", "hand events invalid", {"hand_id": selected_hand_id})

    selector = _validate_selector(
        hand_id=selected_hand_id,
        decision_id=decision_id,
        state_hash=state_hash,
        strict_mode=strict_mode,
    )

    focus: dict[str, Any] | None = None
    if decision_id is not None and state_hash is not None:
        dp: dict[str, Any] | None = None
        ac: dict[str, Any] | None = None
        dp_index: int | None = None
        ac_index: int | None = None
        for i, e in selected_events_with_index:
            if e.get("event") == "DecisionPoint" and e.get("decision_id") == decision_id and e.get("state_hash") == state_hash:
                dp = e
                dp_index = i
            if e.get("event") == "ActionChosen" and e.get("decision_id") == decision_id and e.get("state_hash") == state_hash:
                ac = e
                ac_index = i
        if dp is None or ac is None:
            raise ReplayError(
                "DECISION_NOT_FOUND",
                "DecisionPoint/ActionChosen not found for selector",
                {"decision_id": decision_id, "state_hash": state_hash, "found_decision_point": dp is not None, "found_action_chosen": ac is not None},
            )
        focus = {
            "decision_point_event_index": dp_index,
            "action_chosen_event_index": ac_index,
            "decision_point": dp,
            "action_chosen": ac,
        }

    return {
        "status": "pass",
        "event_stream_ref": f"path:{event_stream_path}",
        "event_stream_digest": {"alg": "sha256", "hex": computed_hex},
        "hand_selector": selector,
        "focus": focus,
        "events": [{"event_index": 0, "payload": header}, *[{"event_index": i, "payload": e} for i, e in selected_events_with_index]],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--eventstream", type=Path, required=True)
    p.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--hand-id", default=None)
    p.add_argument("--decision-id", type=int, default=None)
    p.add_argument("--state-hash", default=None)
    args = p.parse_args(argv)

    try:
        out = replay_eventstream(
            event_stream_path=args.eventstream,
            strict_mode=args.strict,
            hand_id=args.hand_id,
            decision_id=args.decision_id,
            state_hash=args.state_hash,
        )
        _print(out)
        return 0
    except ReplayError as e:
        _print(
            {
                "status": "fail",
                "check_id": "Tools.Replay",
                "error": {"code": e.code, "message": e.message, "details": e.details},
                "evidence_ref": {"event_stream_ref": f"path:{args.eventstream}", "hand_selector": {"hand_id": args.hand_id}},
            }
        )
        return 2
    except EventStreamError as e:
        _print(
            {
                "status": "fail",
                "check_id": "Events.EventStreamArtifact",
                "error": {"code": e.code, "message": e.message},
                "evidence_ref": {"event_stream_ref": f"path:{args.eventstream}", "hand_selector": {"hand_id": args.hand_id}},
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover
