from __future__ import annotations

import copy

import pytest

from poker2.protocol.stage_evidence import StageEvidenceError, validate_artifact_summary, validate_stage_evidence


def _digest(hex_str: str = "0" * 64) -> dict[str, str]:
    return {"alg": "sha256", "hex": hex_str}


def _artifact_summary(*, kind: str = "event_stream", ref: str | None = None) -> dict[str, object]:
    if ref is None:
        ref = f"run://{'0' * 64}/event_stream"
    return {
        "artifact_kind": kind,
        "artifact_ref": ref,
        "digest": _digest(),
        "counts": {"events": 1},
        "provenance_ref": "artifact://prov",
    }


def _stage_evidence(*, degraded: bool = False, status: str = "pass") -> dict[str, object]:
    resolved_paths_digest = "1" * 64
    return {
        "stage_id": "eval",
        "effective_context": {
            "scenario_id": "2" * 64,
            "ruleset_id": "3" * 64,
            "triad": {},
            "schema_hash": "4" * 64,
            "options_hash": "5" * 64,
            "resolved_paths_digest": resolved_paths_digest,
        },
        "inputs_summary": [_artifact_summary(ref=f"run://{'0' * 64}/event_stream")],
        "outputs_summary": [_artifact_summary(kind="report", ref=f"run://{'0' * 64}/report")],
        "status": status,
        "degraded": degraded,
        "degraded_reason": "other" if degraded else None,
        "degraded_counts": {"other": 1} if degraded else {},
        "evidence_ref": None,
    }


def test_artifact_summary_happy_path() -> None:
    validate_artifact_summary(_artifact_summary(), strict_mode=True)


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda a: a.update({"extra": 1}), "EXTRA_FIELDS"),
        (lambda a: a.__setitem__("artifact_kind", "nope"), "UNSUPPORTED_VALUE"),
        (lambda a: a.__setitem__("artifact_ref", "http://x"), "UNSUPPORTED_VALUE"),
        (lambda a: a.__setitem__("digest", {"alg": "md5", "hex": "0" * 64}), "DIGEST_INVALID"),
        (lambda a: a.__setitem__("counts", {"events": -1}), "VALUE_ERROR"),
    ],
)
def test_artifact_summary_validation_errors(mutate, code: str) -> None:
    art = _artifact_summary()
    mutate(art)
    with pytest.raises(StageEvidenceError) as exc:
        validate_artifact_summary(art, strict_mode=True)
    assert exc.value.code == code


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda a: a.__setitem__("provenance_ref", 1), "TYPE_ERROR"),
        (lambda a: a.__setitem__("counts", {"events": True}), "TYPE_ERROR"),
        (lambda a: a.__setitem__("counts", {1: 2}), "TYPE_ERROR"),
    ],
)
def test_artifact_summary_type_errors(mutate, code: str) -> None:
    art = _artifact_summary()
    mutate(art)
    with pytest.raises(StageEvidenceError) as exc:
        validate_artifact_summary(art, strict_mode=True)
    assert exc.value.code == code


def test_artifact_summary_missing_fields() -> None:
    with pytest.raises(StageEvidenceError) as exc:
        validate_artifact_summary({}, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    with pytest.raises(StageEvidenceError) as exc:
        validate_artifact_summary({"artifact_kind": "event_stream"}, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"


def test_stage_evidence_happy_path() -> None:
    ev = _stage_evidence()
    validate_stage_evidence(ev, strict_mode=True, run_strict_mode=True)


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda e: e.__setitem__("stage_id", "nope"), "UNSUPPORTED_VALUE"),
        (lambda e: e["effective_context"].pop("scenario_id"), "MISSING_FIELDS"),
        (lambda e: e.__setitem__("inputs_summary", {}), "TYPE_ERROR"),
        (lambda e: e.__setitem__("status", "maybe"), "UNSUPPORTED_VALUE"),
        (lambda e: e.__setitem__("degraded_reason", "other"), "VALUE_ERROR"),
        (lambda e: e.__setitem__("degraded_counts", {"other": 1}), "VALUE_ERROR"),
    ],
)
def test_stage_evidence_validation_errors(mutate, code: str) -> None:
    ev = _stage_evidence()
    mutate(ev)
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == code


def test_stage_evidence_requires_evidence_ref_on_fail() -> None:
    ev = _stage_evidence(status="fail")
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"


def test_stage_evidence_enforces_strict_degraded_rule() -> None:
    ev = _stage_evidence(degraded=True, status="pass")
    ev["evidence_ref"] = {
        "event_stream_ref": f"run://{'0' * 64}/event_stream",
        "event_stream_digest": _digest(),
        "hand_selector": None,
    }
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "STRICT_DEGRADED_NOT_ALLOWED"


def test_stage_evidence_validates_evidence_ref_shape_and_digest() -> None:
    ev = _stage_evidence(degraded=True, status="fail")
    ev["evidence_ref"] = {}
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    ev2 = _stage_evidence(degraded=True, status="fail")
    ev2["evidence_ref"] = {
        "event_stream_ref": f"run://{'0' * 64}/event_stream",
        "event_stream_digest": {"alg": "md5", "hex": "0" * 64},
        "hand_selector": None,
    }
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev2, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "DIGEST_INVALID"


def test_stage_evidence_missing_fields_and_context_type_errors() -> None:
    ev = _stage_evidence()
    ev.pop("status")
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    ev2 = _stage_evidence()
    ev2["effective_context"]["triad"] = None
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev2, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"


def test_stage_evidence_id_validation_errors() -> None:
    ev = _stage_evidence()
    ev["effective_context"]["scenario_id"] = None
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    ev2 = _stage_evidence()
    ev2["effective_context"]["scenario_id"] = "not-hex"
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev2, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "ID_INVALID"


def test_stage_evidence_degraded_counts_errors() -> None:
    ev = _stage_evidence(degraded=True, status="fail")
    ev["evidence_ref"] = {
        "event_stream_ref": f"run://{'0' * 64}/event_stream",
        "event_stream_digest": _digest(),
        "hand_selector": None,
    }
    ev["degraded_reason"] = "nope"
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev, strict_mode=True, run_strict_mode=False)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    ev2 = _stage_evidence(degraded=True, status="fail")
    ev2["evidence_ref"] = {
        "event_stream_ref": f"run://{'0' * 64}/event_stream",
        "event_stream_digest": _digest(),
        "hand_selector": None,
    }
    ev2["degraded_counts"] = {1: 1}
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev2, strict_mode=True, run_strict_mode=False)
    assert exc.value.code == "TYPE_ERROR"

    ev3 = _stage_evidence(degraded=True, status="fail")
    ev3["evidence_ref"] = {
        "event_stream_ref": f"run://{'0' * 64}/event_stream",
        "event_stream_digest": _digest(),
        "hand_selector": None,
    }
    ev3["degraded_counts"] = {"nope": 1}
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev3, strict_mode=True, run_strict_mode=False)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    ev4 = _stage_evidence(degraded=True, status="fail")
    ev4["evidence_ref"] = {
        "event_stream_ref": f"run://{'0' * 64}/event_stream",
        "event_stream_digest": _digest(),
        "hand_selector": None,
    }
    ev4["degraded_counts"] = {"other": -1}
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev4, strict_mode=True, run_strict_mode=False)
    assert exc.value.code == "VALUE_ERROR"


def test_stage_evidence_evidence_ref_constraints() -> None:
    ev = _stage_evidence()
    ev["evidence_ref"] = {
        "event_stream_ref": f"run://{'0' * 64}/event_stream",
        "event_stream_digest": _digest(),
        "hand_selector": None,
    }
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"

    ev2 = _stage_evidence(degraded=True, status="fail")
    ev2["evidence_ref"] = {
        "event_stream_ref": f"run://{'0' * 64}/event_stream",
        "event_stream_digest": _digest(),
        "hand_selector": "nope",
    }
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev2, strict_mode=True, run_strict_mode=False)
    assert exc.value.code == "TYPE_ERROR"


def test_stage_evidence_degraded_type_error() -> None:
    ev = _stage_evidence()
    ev["degraded"] = "nope"
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"


def test_stage_evidence_strict_mode_rejects_extra_fields() -> None:
    ev = _stage_evidence()
    ev2 = copy.deepcopy(ev)
    ev2["extra"] = 1
    with pytest.raises(StageEvidenceError) as exc:
        validate_stage_evidence(ev2, strict_mode=True, run_strict_mode=True)
    assert exc.value.code == "EXTRA_FIELDS"
