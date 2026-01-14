from __future__ import annotations

from typing import Any

from poker2.gates.common import GateCheckError, _as_int, _as_obj, _as_str, failure


def check_leakage_gate(
    *,
    header: dict[str, Any],
    decision_points: list[dict[str, Any]],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    gate_id = "Gates.Leakage"
    failures: list[dict[str, Any]] = []

    for dp in decision_points:
        decision_id = dp.get("decision_id")
        state_hash = dp.get("state_hash")

        snap = dp.get("snapshot_payload")
        obs = dp.get("observation_view_payload")
        if not isinstance(snap, dict) or not isinstance(obs, dict):
            if strict_mode:
                raise GateCheckError("TYPE_ERROR", "DecisionPoint.snapshot_payload/observation_view_payload must be objects")
            continue

        actor_seat = _as_int(snap.get("actor_seat"), field="Snapshot.actor_seat")

        hole = obs.get("hole_cards_by_seat")
        if not isinstance(hole, dict):
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="hole_cards_by_seat_missing",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=None,
                    triad_or_none=None,
                    schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                    decision_id_or_none=int(decision_id) if isinstance(decision_id, int) else None,
                    state_hash_or_none=state_hash if isinstance(state_hash, str) else None,
                    details={"actor_seat": actor_seat},
                )
            )
            break

        actor_key = str(actor_seat)
        for seat_key, v in hole.items():
            if seat_key == actor_key:
                if v is None:
                    failures.append(
                        failure(
                            gate_id=gate_id,
                            reason="actor_hole_cards_null",
                            header=header,
                            event_stream_ref=event_stream_ref,
                            event_stream_digest=event_stream_digest,
                            ruleset_id_or_none=None,
                            triad_or_none=None,
                            schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                            decision_id_or_none=int(decision_id) if isinstance(decision_id, int) else None,
                            state_hash_or_none=state_hash if isinstance(state_hash, str) else None,
                            details={"actor_seat": actor_seat},
                        )
                    )
                    break
                if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
                    failures.append(
                        failure(
                            gate_id=gate_id,
                            reason="actor_hole_cards_invalid",
                            header=header,
                            event_stream_ref=event_stream_ref,
                            event_stream_digest=event_stream_digest,
                            ruleset_id_or_none=None,
                            triad_or_none=None,
                            schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                            decision_id_or_none=int(decision_id) if isinstance(decision_id, int) else None,
                            state_hash_or_none=state_hash if isinstance(state_hash, str) else None,
                            details={"actor_seat": actor_seat, "value": v},
                        )
                    )
                    break
            else:
                if v is not None:
                    failures.append(
                        failure(
                            gate_id=gate_id,
                            reason="non_actor_hole_cards_non_null",
                            header=header,
                            event_stream_ref=event_stream_ref,
                            event_stream_digest=event_stream_digest,
                            ruleset_id_or_none=None,
                            triad_or_none=None,
                            schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                            decision_id_or_none=int(decision_id) if isinstance(decision_id, int) else None,
                            state_hash_or_none=state_hash if isinstance(state_hash, str) else None,
                            details={"actor_seat": actor_seat, "leaked_seat_key": seat_key, "value": v},
                        )
                    )
                    break
        if failures:
            break

    return failures

