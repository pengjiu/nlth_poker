from __future__ import annotations

from typing import Any

from poker2.gates.common import GateCheckError, _as_int, _as_obj, _as_str, failure


def check_scenario_gate_minimal(
    *,
    header: dict[str, Any],
    hand_starts: list[dict[str, Any]],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    # Minimal Scenario Gate (full ScenarioPackage/registry comes next phase).
    gate_id = "Gates.Scenario"
    failures: list[dict[str, Any]] = []

    header_scenario_id = header.get("scenario_id")
    if not isinstance(header_scenario_id, str):
        raise GateCheckError("MISSING_FIELDS", "scenario_id missing in EventStream header")

    header_schema_hash = header.get("schema_hash")
    if not isinstance(header_schema_hash, str):
        raise GateCheckError("MISSING_FIELDS", "schema_hash missing in EventStream header")

    header_options_hash = header.get("options_hash")
    if not isinstance(header_options_hash, str):
        raise GateCheckError("MISSING_FIELDS", "options_hash missing in EventStream header")

    if strict_mode and not hand_starts:
        raise GateCheckError("NO_HANDS", "eventstream contains no HandStart/HandEnd blocks")

    prev_hand_seq: int | None = None
    for hs in hand_starts:
        hs_schema = hs.get("schema_hash")
        if isinstance(hs_schema, str) and hs_schema != header_schema_hash:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="schema_hash_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=hs.get("ruleset_id") if isinstance(hs.get("ruleset_id"), str) else None,
                    triad_or_none=_as_obj(hs.get("triad"), field="HandStart.triad") if isinstance(hs.get("triad"), dict) else None,
                    schema_hash_or_none=header_schema_hash,
                    details={"hand_id": hs.get("hand_id"), "expected": header_schema_hash, "observed": hs_schema},
                )
            )
            break

        hs_opts = hs.get("options_hash")
        if isinstance(hs_opts, str) and hs_opts != header_options_hash:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="options_hash_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=hs.get("ruleset_id") if isinstance(hs.get("ruleset_id"), str) else None,
                    triad_or_none=_as_obj(hs.get("triad"), field="HandStart.triad") if isinstance(hs.get("triad"), dict) else None,
                    schema_hash_or_none=header_schema_hash,
                    details={"hand_id": hs.get("hand_id"), "expected": header_options_hash, "observed": hs_opts},
                )
            )
            break

        hs_seq = hs.get("hand_seq")
        if hs_seq is not None:
            seq = _as_int(hs_seq, field="HandStart.hand_seq")
            if prev_hand_seq is not None and seq != prev_hand_seq + 1:
                failures.append(
                    failure(
                        gate_id=gate_id,
                        reason="hand_seq_not_monotonic",
                        header=header,
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        ruleset_id_or_none=hs.get("ruleset_id") if isinstance(hs.get("ruleset_id"), str) else None,
                        triad_or_none=_as_obj(hs.get("triad"), field="HandStart.triad") if isinstance(hs.get("triad"), dict) else None,
                        schema_hash_or_none=header_schema_hash,
                        details={"expected_next": prev_hand_seq + 1, "observed": seq},
                    )
                )
                break
            prev_hand_seq = seq

    return failures

