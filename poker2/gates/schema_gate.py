from __future__ import annotations

from typing import Any

from poker2.gates.common import GateCheckError, _as_obj, _as_str, failure
from poker2.protocol.schema_contract import schema_hash as compute_schema_hash


def check_schema_gate(
    *,
    header: dict[str, Any],
    hand_starts: list[dict[str, Any]],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    gate_id = "Gates.Schema"
    failures: list[dict[str, Any]] = []

    expected = compute_schema_hash(strict_mode=True)
    observed = header.get("schema_hash")
    if not isinstance(observed, str):
        raise GateCheckError("MISSING_FIELDS", "schema_hash missing in EventStream header")
    if observed != expected:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="schema_hash_mismatch",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=observed,
                details={"expected": expected, "observed": observed},
            )
        )
        return failures

    # Ensure all HandStart.schema_hash matches header (prevents mixed-schema streams).
    for hs in hand_starts:
        hs_schema = hs.get("schema_hash")
        if hs_schema is None:
            continue
        if not isinstance(hs_schema, str):
            if strict_mode:
                raise GateCheckError("TYPE_ERROR", "HandStart.schema_hash must be str or null")
            continue
        if hs_schema != observed:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="handstart_schema_hash_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=hs.get("ruleset_id") if isinstance(hs.get("ruleset_id"), str) else None,
                    triad_or_none=_as_obj(hs.get("triad"), field="HandStart.triad") if isinstance(hs.get("triad"), dict) else None,
                    schema_hash_or_none=observed,
                    details={
                        "hand_id": hs.get("hand_id"),
                        "expected": observed,
                        "observed": hs_schema,
                    },
                )
            )
            break

    return failures

