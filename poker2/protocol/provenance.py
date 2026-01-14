from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object


@dataclass(frozen=True)
class ProvenanceError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


PROVENANCE_SCHEMA_ID = "provenance_envelope_v1"


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProvenanceError("TYPE_ERROR", f"{field} must be int")
    return value


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ProvenanceError("TYPE_ERROR", f"{field} must be str")
    return value


def _as_obj(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProvenanceError("TYPE_ERROR", f"{field} must be object")
    return value


def _validate_sha256_hex_string(value: Any, *, field: str) -> None:
    if not isinstance(value, str):
        raise ProvenanceError("TYPE_ERROR", f"{field} must be sha256 hex string")
    try:
        validate_digest_object({"alg": "sha256", "hex": value}, strict_mode=True)
    except Exception as e:
        raise ProvenanceError("ID_INVALID", f"{field} must be sha256 hex string", {"error": str(e)}) from e


def python_version_major_minor() -> str:
    vi = sys.version_info
    return f"{vi.major}.{vi.minor}"


def runtime_env_id_v1(*, python_major_minor: str | None = None) -> str:
    # Machine-independent runtime "contract id" (stable across hosts).
    py = python_major_minor or python_version_major_minor()
    payload = {"runtime_env_schema_id": "runtime_env_v1", "python_major_minor": py}
    return sha256_hex(canonicalize_json_bytes(payload, strict_mode=True))


def build_provenance_envelope_v1(
    *,
    ruleset_id: str,
    triad: dict[str, Any],
    schema_hash: str,
    options_hash: str,
    seed: int,
    action_adapter_id: str,
    mapping_spec_id: str | None,
    mw_ladder_id: str | None,
    pokerkit_version: str | None,
    engine_build_id: str | None = None,
    solver_build_id: str | None = None,
    rng_lineage_id: str | None = None,
    seed_derivation_digest: dict[str, str] | None = None,
    python_version: str | None = None,
    runtime_env_id: str | None = None,
    repro_tier: str | None = None,
) -> dict[str, Any]:
    # NOTE: python_version/runtime_env_id are kept out of options_hash by policy; they still live in provenance for audit.
    return {
        "provenance_schema_id": PROVENANCE_SCHEMA_ID,
        "ruleset_id": ruleset_id,
        "triad": triad,
        "schema_hash": schema_hash,
        "options_hash": options_hash,
        "seed": seed,
        "repro_tier": repro_tier,
        "engine_build_id": engine_build_id,
        "solver_build_id": solver_build_id,
        "pokerkit_version": pokerkit_version,
        "python_version": python_version or python_version_major_minor(),
        "runtime_env_id": runtime_env_id or runtime_env_id_v1(),
        "rng_lineage_id": rng_lineage_id,
        "seed_derivation_digest": seed_derivation_digest,
        "action_adapter_id": action_adapter_id,
        "mapping_spec_id": mapping_spec_id,
        "mw_ladder_id": mw_ladder_id,
    }


def validate_provenance_envelope(envelope: Any, *, strict_mode: bool) -> None:
    obj = _as_obj(envelope, field="ProvenanceEnvelope")
    required = (
        "provenance_schema_id",
        "ruleset_id",
        "triad",
        "schema_hash",
        "options_hash",
        "seed",
        "repro_tier",
        "engine_build_id",
        "solver_build_id",
        "pokerkit_version",
        "python_version",
        "runtime_env_id",
        "rng_lineage_id",
        "seed_derivation_digest",
        "action_adapter_id",
        "mapping_spec_id",
        "mw_ladder_id",
    )
    missing = [k for k in required if k not in obj]
    if missing:
        raise ProvenanceError("MISSING_FIELDS", f"missing required fields: {missing}")
    if strict_mode:
        extra = set(obj.keys()) - set(required)
        if extra:
            raise ProvenanceError("EXTRA_FIELDS", "ProvenanceEnvelope has extra fields", {"extra": sorted(extra)})

    schema_id = _as_str(obj.get("provenance_schema_id"), field="ProvenanceEnvelope.provenance_schema_id")
    if schema_id != PROVENANCE_SCHEMA_ID:
        raise ProvenanceError("UNSUPPORTED_VALUE", f"unsupported provenance_schema_id: {schema_id!r}")

    _validate_sha256_hex_string(obj.get("ruleset_id"), field="ProvenanceEnvelope.ruleset_id")
    triad = _as_obj(obj.get("triad"), field="ProvenanceEnvelope.triad")
    triad_required = ("action_bins_id", "obs_schema_id", "rake_id")
    triad_missing = [k for k in triad_required if k not in triad]
    if triad_missing:
        raise ProvenanceError("MISSING_FIELDS", f"triad missing fields: {triad_missing}")
    _validate_sha256_hex_string(triad.get("action_bins_id"), field="Triad.action_bins_id")
    _validate_sha256_hex_string(triad.get("obs_schema_id"), field="Triad.obs_schema_id")
    _validate_sha256_hex_string(triad.get("rake_id"), field="Triad.rake_id")

    _validate_sha256_hex_string(obj.get("schema_hash"), field="ProvenanceEnvelope.schema_hash")
    _validate_sha256_hex_string(obj.get("options_hash"), field="ProvenanceEnvelope.options_hash")
    _as_int(obj.get("seed"), field="ProvenanceEnvelope.seed")

    if obj.get("repro_tier") is not None:
        _as_str(obj.get("repro_tier"), field="ProvenanceEnvelope.repro_tier")

    if obj.get("engine_build_id") is not None:
        _validate_sha256_hex_string(obj.get("engine_build_id"), field="ProvenanceEnvelope.engine_build_id")
    if obj.get("solver_build_id") is not None:
        _validate_sha256_hex_string(obj.get("solver_build_id"), field="ProvenanceEnvelope.solver_build_id")
    if obj.get("pokerkit_version") is not None:
        _as_str(obj.get("pokerkit_version"), field="ProvenanceEnvelope.pokerkit_version")

    _as_str(obj.get("python_version"), field="ProvenanceEnvelope.python_version")
    _validate_sha256_hex_string(obj.get("runtime_env_id"), field="ProvenanceEnvelope.runtime_env_id")

    if obj.get("rng_lineage_id") is not None:
        _validate_sha256_hex_string(obj.get("rng_lineage_id"), field="ProvenanceEnvelope.rng_lineage_id")

    if obj.get("seed_derivation_digest") is not None:
        try:
            validate_digest_object(obj.get("seed_derivation_digest"), strict_mode=True)
        except Exception as e:
            raise ProvenanceError("DIGEST_INVALID", "seed_derivation_digest invalid", {"error": str(e)}) from e

    _validate_sha256_hex_string(obj.get("action_adapter_id"), field="ProvenanceEnvelope.action_adapter_id")

    if obj.get("mapping_spec_id") is not None:
        _validate_sha256_hex_string(obj.get("mapping_spec_id"), field="ProvenanceEnvelope.mapping_spec_id")

    if obj.get("mw_ladder_id") is not None:
        _validate_sha256_hex_string(obj.get("mw_ladder_id"), field="ProvenanceEnvelope.mw_ladder_id")


def provenance_id(envelope: Any, *, strict_mode: bool) -> str:
    validate_provenance_envelope(envelope, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(envelope, strict_mode=strict_mode))

