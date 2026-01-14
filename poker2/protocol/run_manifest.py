from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.stage_evidence import StageEvidenceError, validate_stage_evidence


@dataclass(frozen=True)
class RunManifestError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


RUN_MANIFEST_SCHEMA_ID = "run_manifest_v1"
RUN_ID_SCHEMA = "run_id_v1"


def _as_obj(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RunManifestError("TYPE_ERROR", f"{field} must be object")
    return value


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise RunManifestError("TYPE_ERROR", f"{field} must be str")
    return value


def _as_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise RunManifestError("TYPE_ERROR", f"{field} must be bool")
    return value


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RunManifestError("TYPE_ERROR", f"{field} must be int")
    return value


def _validate_sha256_hex_string(value: Any, *, field: str) -> None:
    if not isinstance(value, str):
        raise RunManifestError("TYPE_ERROR", f"{field} must be sha256 hex string")
    try:
        validate_digest_object({"alg": "sha256", "hex": value}, strict_mode=True)
    except Exception as e:
        raise RunManifestError("ID_INVALID", f"{field} must be sha256 hex string", {"error": str(e)}) from e


def run_manifest_digest_hex(manifest: Any, *, strict_mode: bool) -> str:
    if not isinstance(manifest, dict):
        raise RunManifestError("TYPE_ERROR", "RunManifest must be a JSON object")
    # Digest must be stable across machines; exclude execution-only fields.
    obj_for_hash = {
        k: v
        for k, v in manifest.items()
        if k not in ("run_manifest_digest", "resolution_trace", "run_instance_uuid")
    }
    return sha256_hex(canonicalize_json_bytes(obj_for_hash, strict_mode=strict_mode))


def finalize_run_manifest(manifest: dict[str, Any], *, strict_mode: bool) -> dict[str, Any]:
    digest_hex = run_manifest_digest_hex(manifest, strict_mode=strict_mode)
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return {**manifest, "run_manifest_digest": digest}


def validate_run_manifest(manifest: Any, *, strict_mode: bool) -> None:
    obj = _as_obj(manifest, field="RunManifest")
    required = (
        "run_manifest_schema_id",
        "run_id_schema",
        "run_id",
        "options_hash",
        "seed",
        "strict_mode",
        "repro_tier",
        "run_instance_uuid",
        "scenario_id",
        "ruleset_id",
        "triad",
        "schema_hash",
        "profile_id",
        "policy_id",
        "opponent_suite_id",
        "execution_hint",
        "provenance_ref",
        "rng_lineage_id",
        "resolved_paths",
        "resolved_paths_digest",
        "stages",
        "resolution_trace",
        "run_manifest_digest",
    )
    missing = [k for k in required if k not in obj]
    if missing:
        raise RunManifestError("MISSING_FIELDS", f"missing required fields: {missing}")
    if strict_mode:
        extra = set(obj.keys()) - set(required)
        if extra:
            raise RunManifestError("EXTRA_FIELDS", "RunManifest has extra fields", {"extra": sorted(extra)})

    schema_id = _as_str(obj.get("run_manifest_schema_id"), field="RunManifest.run_manifest_schema_id")
    if schema_id != RUN_MANIFEST_SCHEMA_ID:
        raise RunManifestError("UNSUPPORTED_VALUE", f"unsupported run_manifest_schema_id: {schema_id!r}")

    run_id_schema = _as_str(obj.get("run_id_schema"), field="RunManifest.run_id_schema")
    if run_id_schema != RUN_ID_SCHEMA:
        raise RunManifestError("UNSUPPORTED_VALUE", f"unsupported run_id_schema: {run_id_schema!r}")

    _validate_sha256_hex_string(obj.get("run_id"), field="RunManifest.run_id")
    _validate_sha256_hex_string(obj.get("options_hash"), field="RunManifest.options_hash")
    _as_int(obj.get("seed"), field="RunManifest.seed")
    run_strict_mode = _as_bool(obj.get("strict_mode"), field="RunManifest.strict_mode")
    _as_str(obj.get("repro_tier"), field="RunManifest.repro_tier")
    if obj.get("run_instance_uuid") is not None and not isinstance(obj.get("run_instance_uuid"), str):
        raise RunManifestError("TYPE_ERROR", "RunManifest.run_instance_uuid must be str or null")

    _validate_sha256_hex_string(obj.get("scenario_id"), field="RunManifest.scenario_id")
    _validate_sha256_hex_string(obj.get("ruleset_id"), field="RunManifest.ruleset_id")
    if not isinstance(obj.get("triad"), dict):
        raise RunManifestError("TYPE_ERROR", "RunManifest.triad must be object")
    _validate_sha256_hex_string(obj.get("schema_hash"), field="RunManifest.schema_hash")
    _validate_sha256_hex_string(obj.get("profile_id"), field="RunManifest.profile_id")
    _validate_sha256_hex_string(obj.get("policy_id"), field="RunManifest.policy_id")

    if obj.get("opponent_suite_id") is not None:
        _validate_sha256_hex_string(obj.get("opponent_suite_id"), field="RunManifest.opponent_suite_id")

    if obj.get("execution_hint") is not None and not isinstance(obj.get("execution_hint"), dict):
        raise RunManifestError("TYPE_ERROR", "RunManifest.execution_hint must be object or null")

    _as_str(obj.get("provenance_ref"), field="RunManifest.provenance_ref")

    if obj.get("rng_lineage_id") is not None:
        _validate_sha256_hex_string(obj.get("rng_lineage_id"), field="RunManifest.rng_lineage_id")

    resolved_paths = _as_obj(obj.get("resolved_paths"), field="RunManifest.resolved_paths")
    if "resolved_paths_digest" not in resolved_paths:
        raise RunManifestError("MISSING_FIELDS", "resolved_paths must include resolved_paths_digest")
    _validate_sha256_hex_string(
        resolved_paths.get("resolved_paths_digest"),
        field="RunManifest.resolved_paths.resolved_paths_digest",
    )
    _validate_sha256_hex_string(obj.get("resolved_paths_digest"), field="RunManifest.resolved_paths_digest")
    if resolved_paths.get("resolved_paths_digest") != obj.get("resolved_paths_digest"):
        raise RunManifestError("VALUE_ERROR", "resolved_paths_digest mismatch between top-level and resolved_paths")

    stages = obj.get("stages")
    if not isinstance(stages, list):
        raise RunManifestError("TYPE_ERROR", "RunManifest.stages must be array")
    for idx, stage in enumerate(stages):
        try:
            validate_stage_evidence(stage, strict_mode=strict_mode, run_strict_mode=run_strict_mode)
        except StageEvidenceError as e:
            raise RunManifestError(
                "STAGE_EVIDENCE_INVALID",
                f"invalid stage evidence at index {idx}",
                {"error": {"code": e.code, "message": e.message, "details": e.details}},
            ) from e

    if not isinstance(obj.get("resolution_trace"), dict):
        raise RunManifestError("TYPE_ERROR", "RunManifest.resolution_trace must be object")

    digest = obj.get("run_manifest_digest")
    try:
        validate_digest_object(digest, strict_mode=True)
    except Exception as e:
        raise RunManifestError("DIGEST_INVALID", "run_manifest_digest invalid", {"error": str(e)}) from e

    expected_hex = run_manifest_digest_hex(obj, strict_mode=strict_mode)
    if digest.get("hex") != expected_hex:
        raise RunManifestError(
            "DIGEST_MISMATCH",
            "run_manifest_digest does not match computed digest",
            {"expected": expected_hex, "observed": digest.get("hex")},
        )
