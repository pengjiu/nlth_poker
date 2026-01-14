from __future__ import annotations

from typing import Any

import pytest

from poker2.protocol.paths import default_resolved_paths
from poker2.protocol.run_manifest import (
    RunManifestError,
    run_manifest_digest_hex,
    finalize_run_manifest,
    validate_run_manifest,
)


def _stage_evidence(
    *,
    resolved_paths_digest: str,
    degraded: bool = False,
    status: str = "pass",
    evidence_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "stage_id": "init",
        "effective_context": {
            "scenario_id": "2" * 64,
            "ruleset_id": "3" * 64,
            "triad": {},
            "schema_hash": "4" * 64,
            "options_hash": "1" * 64,
            "resolved_paths_digest": resolved_paths_digest,
        },
        "inputs_summary": [],
        "outputs_summary": [],
        "status": status,
        "degraded": degraded,
        "degraded_reason": "other" if degraded else None,
        "degraded_counts": {"other": 1} if degraded else {},
        "evidence_ref": evidence_ref,
    }


def _manifest_base(*, resolved_paths: dict[str, Any], resolved_paths_digest: str) -> dict[str, Any]:
    return {
        "run_manifest_schema_id": "run_manifest_v1",
        "run_id_schema": "run_id_v1",
        "run_id": "0" * 64,
        "options_hash": "1" * 64,
        "seed": 123,
        "strict_mode": True,
        "repro_tier": "Tier-A",
        "run_instance_uuid": None,
        "scenario_id": "2" * 64,
        "ruleset_id": "3" * 64,
        "triad": {},
        "schema_hash": "4" * 64,
        "profile_id": "5" * 64,
        "policy_id": "6" * 64,
        "opponent_suite_id": None,
        "execution_hint": None,
        "provenance_ref": "artifact://prov",
        "rng_lineage_id": None,
        "resolved_paths": resolved_paths,
        "resolved_paths_digest": resolved_paths_digest,
        "stages": [_stage_evidence(resolved_paths_digest=resolved_paths_digest)],
        "resolution_trace": {"note": "execution-only"},
    }


def test_run_manifest_finalize_and_validate() -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    finalized = finalize_run_manifest(base, strict_mode=True)
    validate_run_manifest(finalized, strict_mode=True)


def test_run_manifest_digest_excludes_resolution_trace_and_instance_uuid() -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)

    m1 = finalize_run_manifest(base, strict_mode=True)
    m2 = finalize_run_manifest(
        {
            **base,
            "run_instance_uuid": "2b0e4d37-7b3c-4ced-9130-9e6d1564ad62",
            "resolution_trace": {"host_paths": {"artifacts_root_abs": "/tmp/a"}},
        },
        strict_mode=True,
    )
    assert m1["run_manifest_digest"]["hex"] == m2["run_manifest_digest"]["hex"]


def test_run_manifest_rejects_degraded_pass_in_strict_mode() -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    degraded = {
        "event_stream_ref": "run://0" * 1 + "0" * 63 + "/event_stream",
        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
        "hand_selector": None,
    }
    base["stages"] = [
        _stage_evidence(
            resolved_paths_digest=resolved_paths_digest,
            degraded=True,
            status="pass",
            evidence_ref=degraded,
        )
    ]
    finalized = finalize_run_manifest(base, strict_mode=True)
    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest(finalized, strict_mode=True)
    assert exc.value.code == "STAGE_EVIDENCE_INVALID"


def test_run_manifest_rejects_schema_id_mismatch() -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    finalized = finalize_run_manifest(base, strict_mode=True)
    finalized2 = {**finalized, "run_manifest_schema_id": "nope"}
    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest(finalized2, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"


def test_run_manifest_rejects_digest_mismatch() -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    finalized = finalize_run_manifest(base, strict_mode=True)
    mutated = {**finalized, "seed": 124}
    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest(mutated, strict_mode=True)
    assert exc.value.code == "DIGEST_MISMATCH"


def test_run_manifest_rejects_invalid_digest_object() -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    finalized = finalize_run_manifest(base, strict_mode=True)
    bad = {**finalized, "run_manifest_digest": {"alg": "md5", "hex": "0" * 64}}
    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest(bad, strict_mode=True)
    assert exc.value.code == "DIGEST_INVALID"


def test_run_manifest_rejects_resolved_paths_digest_mismatch() -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    finalized = finalize_run_manifest(base, strict_mode=True)
    mismatched = {
        **finalized,
        "resolved_paths_digest": "9" * 64,
    }
    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest(mismatched, strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"


def test_run_manifest_validation_errors_cover_branches() -> None:
    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_manifest_schema_id", 1),
        ("strict_mode", "nope"),
        ("seed", "nope"),
    ],
)
def test_run_manifest_type_errors(field: str, value: object) -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    finalized = finalize_run_manifest(base, strict_mode=True)
    mutated = {**finalized, field: value}
    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest(mutated, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"


@pytest.mark.parametrize(
    ("run_id", "code"),
    [
        (1, "TYPE_ERROR"),
        ("nothex", "ID_INVALID"),
    ],
)
def test_run_manifest_run_id_errors(run_id: object, code: str) -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    finalized = finalize_run_manifest(base, strict_mode=True)
    mutated = {**finalized, "run_id": run_id}
    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest(mutated, strict_mode=True)
    assert exc.value.code == code

    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest({}, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    with pytest.raises(RunManifestError) as exc:
        run_manifest_digest_hex([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    finalized = finalize_run_manifest(base, strict_mode=True)

    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest({**finalized, "extra": 1}, strict_mode=True)
    assert exc.value.code == "EXTRA_FIELDS"

    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest({**finalized, "run_id_schema": "nope"}, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest({**finalized, "run_instance_uuid": 123}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest({**finalized, "triad": None}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest({**finalized, "execution_hint": "nope"}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest({**finalized, "resolved_paths": {}}, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest({**finalized, "stages": {}}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(RunManifestError) as exc:
        validate_run_manifest({**finalized, "resolution_trace": None}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"


def test_run_manifest_optional_fields_are_validated_when_present() -> None:
    resolved_paths, resolved_paths_digest = default_resolved_paths(strict_mode=True)
    base = _manifest_base(resolved_paths=resolved_paths, resolved_paths_digest=resolved_paths_digest)
    base["opponent_suite_id"] = "7" * 64
    base["rng_lineage_id"] = "8" * 64
    finalized = finalize_run_manifest(base, strict_mode=True)
    validate_run_manifest(finalized, strict_mode=True)
