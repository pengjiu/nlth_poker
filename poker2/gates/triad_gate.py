from __future__ import annotations

from typing import Any

from poker2.gates.common import GateCheckError, _as_obj, _as_str, failure
from poker2.protocol.ruleset import ruleset_id as compute_ruleset_id
from poker2.protocol.ruleset import ruleset_rake_id as compute_ruleset_rake_id


def check_triad_gate(
    *,
    header: dict[str, Any],
    hand_starts: list[dict[str, Any]],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    ruleset: dict[str, Any],
    strict_mode: bool,
) -> list[dict[str, Any]]:
    gate_id = "Gates.Triad"
    failures: list[dict[str, Any]] = []

    expected_ruleset_id = compute_ruleset_id(ruleset, strict_mode=True)
    expected_rake_id = compute_ruleset_rake_id(ruleset, strict_mode=True)

    if not hand_starts:
        raise GateCheckError("NO_HANDS", "eventstream contains no HandStart/HandEnd blocks")

    for hs in hand_starts:
        triad_obj = hs.get("triad")
        if not isinstance(triad_obj, dict):
            if strict_mode:
                raise GateCheckError("TYPE_ERROR", "HandStart.triad must be object")
            continue
        observed_rake_id = triad_obj.get("rake_id")
        if not isinstance(observed_rake_id, str):
            raise GateCheckError("MISSING_FIELDS", "triad.rake_id missing in HandStart")

        observed_ruleset_id = hs.get("ruleset_id") if isinstance(hs.get("ruleset_id"), str) else None

        if observed_rake_id != expected_rake_id:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="triad_rake_id_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=observed_ruleset_id,
                    triad_or_none=triad_obj,
                    schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                    details={
                        "triad": triad_obj,
                        "ruleset_id": observed_ruleset_id,
                        "expected": {"ruleset_id": expected_ruleset_id, "ruleset_rake_id": expected_rake_id},
                        "observed": {"ruleset_rake_id": observed_rake_id},
                    },
                )
            )
            break

        if observed_ruleset_id is not None and observed_ruleset_id != expected_ruleset_id:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="ruleset_id_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=observed_ruleset_id,
                    triad_or_none=triad_obj,
                    schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                    details={"expected_ruleset_id": expected_ruleset_id, "observed_ruleset_id": observed_ruleset_id},
                )
            )
            break

    return failures

