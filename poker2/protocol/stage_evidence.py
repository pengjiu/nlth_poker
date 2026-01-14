from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import validate_digest_object
from poker2.protocol.enums import (
    ARTIFACT_KIND_VALUES,
    STAGE_DEGRADED_REASON_VALUES,
    STAGE_ID_VALUES,
    STAGE_STATUS_VALUES,
)


@dataclass(frozen=True)
class StageEvidenceError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


_ARTIFACT_REF_PREFIXES = ("run://", "scenario://", "artifact://", "path:")


def _as_obj(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StageEvidenceError("TYPE_ERROR", f"{field} must be object")
    return value


def _as_list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise StageEvidenceError("TYPE_ERROR", f"{field} must be array")
    return value


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise StageEvidenceError("TYPE_ERROR", f"{field} must be str")
    return value


def _as_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise StageEvidenceError("TYPE_ERROR", f"{field} must be bool")
    return value


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StageEvidenceError("TYPE_ERROR", f"{field} must be int")
    return value


def _validate_sha256_hex_string(value: Any, *, field: str) -> None:
    if not isinstance(value, str):
        raise StageEvidenceError("TYPE_ERROR", f"{field} must be sha256 hex string")
    try:
        validate_digest_object({"alg": "sha256", "hex": value}, strict_mode=True)
    except Exception as e:
        raise StageEvidenceError("ID_INVALID", f"{field} must be sha256 hex string", {"error": str(e)}) from e


def validate_artifact_summary(value: Any, *, strict_mode: bool) -> None:
    obj = _as_obj(value, field="artifact_summary")
    required = ("artifact_kind", "artifact_ref", "digest", "counts", "provenance_ref")
    missing = [k for k in required if k not in obj]
    if missing:
        raise StageEvidenceError("MISSING_FIELDS", f"artifact_summary missing fields: {missing}")
    if strict_mode:
        extra = set(obj.keys()) - set(required)
        if extra:
            raise StageEvidenceError("EXTRA_FIELDS", "artifact_summary has extra fields", {"extra": sorted(extra)})

    kind = _as_str(obj.get("artifact_kind"), field="artifact_summary.artifact_kind")
    if kind not in ARTIFACT_KIND_VALUES:
        raise StageEvidenceError("UNSUPPORTED_VALUE", f"unsupported artifact_kind: {kind!r}")

    ref = _as_str(obj.get("artifact_ref"), field="artifact_summary.artifact_ref")
    if not any(ref.startswith(p) for p in _ARTIFACT_REF_PREFIXES):
        raise StageEvidenceError(
            "UNSUPPORTED_VALUE",
            "artifact_ref must use a controlled prefix",
            {"artifact_ref": ref, "allowed_prefixes": list(_ARTIFACT_REF_PREFIXES)},
        )

    digest = _as_obj(obj.get("digest"), field="artifact_summary.digest")
    try:
        validate_digest_object(digest, strict_mode=True)
    except Exception as e:
        raise StageEvidenceError("DIGEST_INVALID", "artifact_summary.digest invalid", {"error": str(e)}) from e

    counts = _as_obj(obj.get("counts"), field="artifact_summary.counts")
    for k, v in counts.items():
        if not isinstance(k, str):
            raise StageEvidenceError("TYPE_ERROR", "counts keys must be str")
        n = _as_int(v, field=f"counts[{k!r}]")
        if n < 0:
            raise StageEvidenceError("VALUE_ERROR", "counts values must be >= 0", {"key": k, "value": n})

    _as_str(obj.get("provenance_ref"), field="artifact_summary.provenance_ref")


def validate_stage_evidence(value: Any, *, strict_mode: bool, run_strict_mode: bool) -> None:
    obj = _as_obj(value, field="stage_evidence")
    required = (
        "stage_id",
        "effective_context",
        "inputs_summary",
        "outputs_summary",
        "status",
        "degraded",
        "degraded_reason",
        "degraded_counts",
        "evidence_ref",
    )
    missing = [k for k in required if k not in obj]
    if missing:
        raise StageEvidenceError("MISSING_FIELDS", f"stage_evidence missing fields: {missing}")
    if strict_mode:
        extra = set(obj.keys()) - set(required)
        if extra:
            raise StageEvidenceError("EXTRA_FIELDS", "stage_evidence has extra fields", {"extra": sorted(extra)})

    stage_id = _as_str(obj.get("stage_id"), field="stage_evidence.stage_id")
    if stage_id not in STAGE_ID_VALUES:
        raise StageEvidenceError("UNSUPPORTED_VALUE", f"unsupported stage_id: {stage_id!r}")

    effective_context = _as_obj(obj.get("effective_context"), field="stage_evidence.effective_context")
    ctx_required = ("scenario_id", "ruleset_id", "triad", "schema_hash", "options_hash", "resolved_paths_digest")
    ctx_missing = [k for k in ctx_required if k not in effective_context]
    if ctx_missing:
        raise StageEvidenceError("MISSING_FIELDS", f"effective_context missing fields: {ctx_missing}")
    _validate_sha256_hex_string(effective_context.get("scenario_id"), field="effective_context.scenario_id")
    _validate_sha256_hex_string(effective_context.get("ruleset_id"), field="effective_context.ruleset_id")
    if not isinstance(effective_context.get("triad"), dict):
        raise StageEvidenceError("TYPE_ERROR", "effective_context.triad must be object")
    _validate_sha256_hex_string(effective_context.get("schema_hash"), field="effective_context.schema_hash")
    _validate_sha256_hex_string(effective_context.get("options_hash"), field="effective_context.options_hash")
    _validate_sha256_hex_string(
        effective_context.get("resolved_paths_digest"),
        field="effective_context.resolved_paths_digest",
    )

    inputs = _as_list(obj.get("inputs_summary"), field="stage_evidence.inputs_summary")
    outputs = _as_list(obj.get("outputs_summary"), field="stage_evidence.outputs_summary")
    for item in inputs:
        validate_artifact_summary(item, strict_mode=strict_mode)
    for item in outputs:
        validate_artifact_summary(item, strict_mode=strict_mode)

    status = _as_str(obj.get("status"), field="stage_evidence.status")
    if status not in STAGE_STATUS_VALUES:
        raise StageEvidenceError("UNSUPPORTED_VALUE", f"unsupported status: {status!r}")

    degraded = _as_bool(obj.get("degraded"), field="stage_evidence.degraded")
    degraded_reason = obj.get("degraded_reason")
    degraded_counts = _as_obj(obj.get("degraded_counts"), field="stage_evidence.degraded_counts")

    if not degraded:
        if degraded_reason is not None:
            raise StageEvidenceError("VALUE_ERROR", "degraded_reason must be null when degraded=false")
        if degraded_counts:
            raise StageEvidenceError("VALUE_ERROR", "degraded_counts must be {} when degraded=false")
    else:
        reason_str = _as_str(degraded_reason, field="stage_evidence.degraded_reason")
        if reason_str not in STAGE_DEGRADED_REASON_VALUES:
            raise StageEvidenceError("UNSUPPORTED_VALUE", f"unsupported degraded_reason: {reason_str!r}")
        for k, v in degraded_counts.items():
            if not isinstance(k, str):
                raise StageEvidenceError("TYPE_ERROR", "degraded_counts keys must be str")
            if k not in STAGE_DEGRADED_REASON_VALUES:
                raise StageEvidenceError(
                    "UNSUPPORTED_VALUE",
                    "degraded_counts keys must be degraded_reason values",
                    {"key": k},
                )
            n = _as_int(v, field=f"degraded_counts[{k!r}]")
            if n < 0:
                raise StageEvidenceError("VALUE_ERROR", "degraded_counts values must be >= 0", {"key": k, "value": n})

        if run_strict_mode and status != "fail":
            raise StageEvidenceError(
                "STRICT_DEGRADED_NOT_ALLOWED",
                "strict_mode run cannot mark degraded stage as pass",
            )

    evidence_ref = obj.get("evidence_ref")
    if status == "pass" and not degraded:
        if evidence_ref is not None:
            raise StageEvidenceError("VALUE_ERROR", "evidence_ref must be null when status=pass and degraded=false")
    else:
        ev = _as_obj(evidence_ref, field="stage_evidence.evidence_ref")
        ev_required = ("event_stream_ref", "event_stream_digest", "hand_selector")
        missing_ev = [k for k in ev_required if k not in ev]
        if missing_ev:
            raise StageEvidenceError("MISSING_FIELDS", f"evidence_ref missing fields: {missing_ev}")
        _as_str(ev.get("event_stream_ref"), field="evidence_ref.event_stream_ref")
        try:
            validate_digest_object(ev.get("event_stream_digest"), strict_mode=True)
        except Exception as e:
            raise StageEvidenceError("DIGEST_INVALID", "evidence_ref.event_stream_digest invalid", {"error": str(e)}) from e
        if ev.get("hand_selector") is not None and not isinstance(ev.get("hand_selector"), dict):
            raise StageEvidenceError("TYPE_ERROR", "evidence_ref.hand_selector must be object or null")

