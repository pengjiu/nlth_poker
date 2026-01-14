from __future__ import annotations

import json
from typing import Any

from poker2.gates.common import GateCheckError, failure
from poker2.protocol.provenance import ProvenanceError, validate_provenance_envelope
from poker2.runtime.artifact_store import ArtifactStoreError, resolve_artifact_path


def check_postflop_library_gate(
    *,
    header: dict[str, Any],
    scenario_package: dict[str, Any] | None,
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    gate_id = "Gates.PostflopLibrary"
    failures: list[dict[str, Any]] = []

    if scenario_package is None:
        return failures
    postflop_ref = scenario_package.get("postflop_ref")
    if postflop_ref is None:
        return failures
    if not isinstance(postflop_ref, dict):
        if strict_mode:
            raise GateCheckError("TYPE_ERROR", "ScenarioPackage.postflop_ref must be object or null")
        failures.append(
            failure(
                gate_id=gate_id,
                reason="postflop_ref_invalid",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                details={"postflop_ref": postflop_ref},
            )
        )
        return failures

    prov_ref = header.get("provenance_ref")
    if not isinstance(prov_ref, str):
        raise GateCheckError("MISSING_FIELDS", "provenance_ref missing in EventStream header")

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
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
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
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
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
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                details={"provenance_ref": prov_ref, "path": str(prov_path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            )
        )
        return failures

    solver_build_id = prov_obj.get("solver_build_id")
    if solver_build_id is None:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="solver_build_id_missing",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                details={"provenance_ref": prov_ref},
            )
        )
        return failures

    return failures
