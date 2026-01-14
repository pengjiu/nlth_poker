from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from poker2.gates.common import failure
from poker2.protocol.provenance import ProvenanceError, provenance_id, validate_provenance_envelope
from poker2.runtime.artifact_store import ArtifactStoreError, resolve_artifact_path


def check_cache_correctness_gate(
    *,
    header: dict[str, Any],
    hand_starts: list[dict[str, Any]],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    # Cache Correctness Gate (ARCHIETECTURE.md §7.5): validate cached entry provenance matches run closure.
    gate_id = "Gates.CacheCorrectness"
    failures: list[dict[str, Any]] = []

    cached_prov_ref = header.get("cache_entry_provenance_ref")
    if cached_prov_ref is None:
        return failures
    if not isinstance(cached_prov_ref, str):
        failures.append(
            failure(
                gate_id=gate_id,
                reason="cache_entry_provenance_ref_invalid",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                details={"cache_entry_provenance_ref": cached_prov_ref},
            )
        )
        return failures

    if strict_mode and not hand_starts:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="cache_entry_no_handstart",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                details={},
            )
        )
        return failures

    ruleset_id_or_none: str | None = None
    triad_or_none: dict[str, Any] | None = None
    if hand_starts:
        hs0 = hand_starts[0]
        if isinstance(hs0.get("ruleset_id"), str):
            ruleset_id_or_none = hs0["ruleset_id"]
        if isinstance(hs0.get("triad"), dict):
            triad_or_none = hs0.get("triad")

    schema_hash = header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None
    options_hash = header.get("options_hash") if isinstance(header.get("options_hash"), str) else None
    if schema_hash is None or options_hash is None:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="cache_entry_header_missing",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash,
                details={"missing": [k for k in ("schema_hash", "options_hash") if header.get(k) is None]},
            )
        )
        return failures

    failures.extend(
        check_cache_entry_provenance_gate(
            header=header,
            cached_provenance_ref=cached_prov_ref,
            expected_ruleset_id=ruleset_id_or_none or "",
            expected_triad=triad_or_none or {},
            expected_schema_hash=schema_hash,
            expected_options_hash=options_hash,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            strict_mode=strict_mode,
        )
    )

    return failures


def check_cache_entry_provenance_gate(
    *,
    header: dict[str, Any],
    cached_provenance_ref: str | None,
    expected_ruleset_id: str,
    expected_triad: dict[str, Any],
    expected_schema_hash: str,
    expected_options_hash: str,
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    provenance_search_roots: list[Path] | None = None,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    # Cache Correctness Gate (ARCHIETECTURE.md §7.5): validate cached entry provenance matches current run closure.
    gate_id = "Gates.CacheCorrectness"
    failures: list[dict[str, Any]] = []

    if not isinstance(cached_provenance_ref, str):
        failures.append(
            failure(
                gate_id=gate_id,
                reason="provenance_ref_missing",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=expected_ruleset_id,
                triad_or_none=expected_triad,
                schema_hash_or_none=expected_schema_hash,
                details={},
            )
        )
        return failures

    try:
        prov_path = resolve_artifact_path(cached_provenance_ref, search_roots=provenance_search_roots, suffixes=(".json",))
    except ArtifactStoreError as e:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="provenance_ref_unresolvable",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=expected_ruleset_id,
                triad_or_none=expected_triad,
                schema_hash_or_none=expected_schema_hash,
                details={"provenance_ref": cached_provenance_ref, "error": {"code": e.code, "message": e.message, "details": e.details}},
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
                ruleset_id_or_none=expected_ruleset_id,
                triad_or_none=expected_triad,
                schema_hash_or_none=expected_schema_hash,
                details={"provenance_ref": cached_provenance_ref, "path": str(prov_path), "error": str(e)},
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
                ruleset_id_or_none=expected_ruleset_id,
                triad_or_none=expected_triad,
                schema_hash_or_none=expected_schema_hash,
                details={"provenance_ref": cached_provenance_ref, "path": str(prov_path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            )
        )
        return failures

    observed_id = cached_provenance_ref.removeprefix("artifact://")
    expected_id = provenance_id(prov_obj, strict_mode=True)
    if observed_id != expected_id:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="provenance_id_mismatch",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=expected_ruleset_id,
                triad_or_none=expected_triad,
                schema_hash_or_none=expected_schema_hash,
                details={"provenance_ref": cached_provenance_ref, "path": str(prov_path), "expected": expected_id, "observed": observed_id},
            )
        )
        return failures

    mismatches: dict[str, Any] = {}
    if prov_obj.get("ruleset_id") != expected_ruleset_id:
        mismatches["ruleset_id"] = {"expected": expected_ruleset_id, "observed": prov_obj.get("ruleset_id")}
    if prov_obj.get("triad") != expected_triad:
        mismatches["triad"] = {"expected": expected_triad, "observed": prov_obj.get("triad")}
    if prov_obj.get("schema_hash") != expected_schema_hash:
        mismatches["schema_hash"] = {"expected": expected_schema_hash, "observed": prov_obj.get("schema_hash")}
    if prov_obj.get("options_hash") != expected_options_hash:
        mismatches["options_hash"] = {"expected": expected_options_hash, "observed": prov_obj.get("options_hash")}

    if mismatches:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="provenance_mismatch",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=expected_ruleset_id,
                triad_or_none=expected_triad,
                schema_hash_or_none=expected_schema_hash,
                details={"provenance_ref": cached_provenance_ref, "mismatches": mismatches},
            )
        )
        return failures

    return failures
