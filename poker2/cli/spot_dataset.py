from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes
from poker2.protocol.eventstream import EventStreamError, read_ndjson
from poker2.protocol.spot_policy import SpotPolicyError, load_spot_policy
from poker2.protocol.treepath_mapping import position_key
from poker2.runtime.spot_policy import build_spot_context, match_spot_policy


class SpotDatasetError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def build_spot_dataset(
    *,
    eventstreams: list[Path],
    spot_policy_path: Path | None,
    strict_mode: bool,
) -> dict[str, Any]:
    spec = load_spot_policy(spot_policy_path, strict_mode=True) if spot_policy_path is not None else None
    rows: list[dict[str, Any]] = []
    scanned_decisions = 0
    matched_decisions = 0
    for eventstream_path in eventstreams:
        if not eventstream_path.exists():
            raise SpotDatasetError("EVENTSTREAM_MISSING", "eventstream path missing", {"path": str(eventstream_path)})
        objs = read_ndjson(eventstream_path, strict_mode=strict_mode)
        if len(objs) < 2:
            raise SpotDatasetError("EMPTY_EVENTSTREAM", "eventstream must contain header + events", {"path": str(eventstream_path)})
        current_hand_id: str | None = None
        decision_points: dict[tuple[int, str], dict[str, Any]] = {}
        for obj in objs[1:]:
            if not isinstance(obj, dict):
                continue
            event = obj.get("event")
            if event == "HandStart":
                hand_id = obj.get("hand_id")
                current_hand_id = hand_id if isinstance(hand_id, str) else None
                continue
            if event == "DecisionPoint":
                decision_id = obj.get("decision_id")
                state_hash = obj.get("state_hash")
                if not isinstance(decision_id, int) or not isinstance(state_hash, str):
                    continue
                decision_points[(decision_id, state_hash)] = {
                    "hand_id": current_hand_id,
                    "snapshot": obj.get("snapshot_payload") if isinstance(obj.get("snapshot_payload"), dict) else {},
                    "observation": obj.get("observation_view_payload") if isinstance(obj.get("observation_view_payload"), dict) else {},
                }
                continue
            if event != "ActionChosen":
                continue
            decision_id = obj.get("decision_id")
            state_hash = obj.get("state_hash")
            if not isinstance(decision_id, int) or not isinstance(state_hash, str):
                continue
            payload = decision_points.get((decision_id, state_hash))
            if payload is None:
                continue
            snap = payload["snapshot"]
            obs = payload["observation"]
            scanned_decisions += 1
            actor_seat = obs.get("actor_seat")
            button_seat = obs.get("button_seat")
            seats_in_hand = obs.get("seats_in_hand")
            pos_key = None
            if isinstance(actor_seat, int) and isinstance(button_seat, int) and isinstance(seats_in_hand, list):
                try:
                    pos_key = position_key(actor_seat, button_seat, [int(seat) for seat in seats_in_hand])
                except Exception:
                    pos_key = None
            context = build_spot_context(
                street=snap.get("street") if isinstance(snap.get("street"), str) else None,
                facing_bet=int(snap.get("to_call_chips", 0) or 0) > 0,
                pos_key=pos_key,
                players_alive=int(snap.get("players_alive_count", 0) or 0) if snap.get("players_alive_count") is not None else None,
                pot_chips=int(snap.get("pot_chips", 0) or 0),
                to_call_chips=int(snap.get("to_call_chips", 0) or 0),
                actor_stack_chips=int(snap.get("actor_stack_chips", 0) or 0) if snap.get("actor_stack_chips") is not None else None,
                board_cards=obs.get("board_cards") if isinstance(obs.get("board_cards"), list) else None,
            )
            matched_rule = match_spot_policy(spec, context) if spec is not None else None
            if spec is not None and matched_rule is None:
                continue
            matched_decisions += 1
            hand_id = payload.get("hand_id")
            rows.append(
                {
                    "eventstream_ref": f"path:{eventstream_path}",
                    "hand_selector": {
                        "hand_id": hand_id,
                        "decision_id": decision_id,
                        "state_hash": state_hash,
                    },
                    "spot_context": context,
                    "matched_spot_id": matched_rule.get("spot_id") if isinstance(matched_rule, dict) else None,
                    "proposed_action": obj.get("proposed_action"),
                    "executed_action": obj.get("executed_action"),
                }
            )
    return {
        "schema_id": "spot_dataset_v1",
        "spot_policy_ref": f"path:{spot_policy_path}" if spot_policy_path is not None else None,
        "eventstream_count": len(eventstreams),
        "decision_points_scanned": scanned_decisions,
        "matched_rows": matched_decisions,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a replayable spot dataset from EventStream files.")
    parser.add_argument("--eventstream", type=Path, action="append", required=True)
    parser.add_argument("--spot-policy", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        dataset = build_spot_dataset(
            eventstreams=args.eventstream,
            spot_policy_path=args.spot_policy,
            strict_mode=bool(args.strict),
        )
        if args.out is not None:
            args.out.write_bytes(canonicalize_json_bytes(dataset, strict_mode=True) + b"\n")
            _print({"status": "pass", "artifact_ref": f"path:{args.out}", "matched_rows": dataset["matched_rows"]})
        else:
            _print({"status": "pass", **dataset})
        return 0
    except (SpotDatasetError, SpotPolicyError, EventStreamError) as exc:
        _print(
            {
                "status": "fail",
                "check_id": "Tools.SpotDataset",
                "error": {
                    "code": getattr(exc, "code", "FAIL"),
                    "message": getattr(exc, "message", str(exc)),
                    "details": getattr(exc, "details", None),
                },
            }
        )
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
