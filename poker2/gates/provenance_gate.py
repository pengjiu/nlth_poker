from __future__ import annotations

import json
from typing import Any

from poker2.gates.common import GateCheckError, _as_obj, failure
from poker2.protocol.provenance import ProvenanceError, provenance_id, validate_provenance_envelope
from poker2.runtime.artifact_store import ArtifactStoreError, resolve_artifact_path


def check_provenance_gate(
    *,
    header: dict[str, Any],
    hand_starts: list[dict[str, Any]],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    gate_id = "Gates.Provenance"
    failures: list[dict[str, Any]] = []

    prov_ref = header.get("provenance_ref")
    if not isinstance(prov_ref, str):
        raise GateCheckError("MISSING_FIELDS", "provenance_ref missing in EventStream header")

    ruleset_id_or_none: str | None = None
    triad_or_none: dict[str, Any] | None = None
    if hand_starts:
        hs0 = hand_starts[0]
        if isinstance(hs0.get("ruleset_id"), str):
            ruleset_id_or_none = hs0["ruleset_id"]
        if isinstance(hs0.get("triad"), dict):
            triad_or_none = _as_obj(hs0.get("triad"), field="HandStart.triad")

    schema_hash_or_none = header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None

    try:
        prov_path = resolve_artifact_path(prov_ref, suffixes=(".json",))
    except ArtifactStoreError as e:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="provenance_ref_unresolvable",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash_or_none,
                details={"provenance_ref": prov_ref, "error": {"code": e.code, "message": e.message, "details": e.details}},
            )
        )
        return failures

    try:
        prov_obj = json.loads(prov_path.read_text(encoding="utf-8"))
    except Exception as e:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="provenance_unreadable",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash_or_none,
                details={"provenance_ref": prov_ref, "path": str(prov_path), "error": str(e)},
            )
        )
        return failures

    try:
        validate_provenance_envelope(prov_obj, strict_mode=True)
    except ProvenanceError as e:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="provenance_invalid",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash_or_none,
                details={"provenance_ref": prov_ref, "path": str(prov_path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            )
        )
        return failures

    observed_id = prov_ref.removeprefix("artifact://")
    expected_id = provenance_id(prov_obj, strict_mode=True)
    if observed_id != expected_id:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="provenance_id_mismatch",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash_or_none,
                details={"provenance_ref": prov_ref, "path": str(prov_path), "expected": expected_id, "observed": observed_id},
            )
        )
        return failures

    # Header ↔ provenance semantic closure consistency.
    mismatches: dict[str, Any] = {}
    for k in ("options_hash", "schema_hash", "seed"):
        if k not in header:
            raise GateCheckError("MISSING_FIELDS", f"{k} missing in EventStream header")
        if prov_obj.get(k) != header.get(k):
            mismatches[k] = {"expected": header.get(k), "observed": prov_obj.get(k)}
    if mismatches:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="provenance_header_mismatch",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash_or_none,
                details={"mismatches": mismatches},
            )
        )
        return failures

    # Ensure all HandStart.provenance_ref (if present) matches header.provenance_ref.
    for hs in hand_starts:
        hs_ref = hs.get("provenance_ref")
        if hs_ref is None:
            continue
        if not isinstance(hs_ref, str):
            if strict_mode:
                raise GateCheckError("TYPE_ERROR", "HandStart.provenance_ref must be str or null")
            continue
        if hs_ref != prov_ref:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="handstart_provenance_ref_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=ruleset_id_or_none,
                    triad_or_none=triad_or_none,
                    schema_hash_or_none=schema_hash_or_none,
                    details={"hand_id": hs.get("hand_id"), "expected": prov_ref, "observed": hs_ref},
                )
            )
            break

    return failures

