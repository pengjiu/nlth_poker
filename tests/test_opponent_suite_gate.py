from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.gates.opponent_suite_gate import check_opponent_suite_gate
from poker2.protocol.opponent_suite import opponent_suite_id


def _header() -> dict[str, object]:
    return {
        "run_id": "0" * 64,
        "options_hash": "1" * 64,
        "seed": 1,
        "scenario_id": "2" * 64,
        "schema_hash": "3" * 64,
    }


def test_opponent_suite_gate_missing_fields() -> None:
    hs = [{"event": "HandStart", "hand_id": "h"}]
    failures = check_opponent_suite_gate(header=_header(), hand_starts=hs, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "missing_fields"


def test_opponent_suite_gate_type_and_id_errors() -> None:
    hs = [
        {"event": "HandStart", "hand_id": "h1", "opponent_suite_id": 123, "opponent_artifact_id_or_params_hash": None},
    ]
    failures = check_opponent_suite_gate(header=_header(), hand_starts=hs, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "type_error"

    hs = [
        {"event": "HandStart", "hand_id": "h1", "opponent_suite_id": "Z" * 64, "opponent_artifact_id_or_params_hash": None},
    ]
    failures = check_opponent_suite_gate(header=_header(), hand_starts=hs, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "id_invalid"

    hs = [
        {"event": "HandStart", "hand_id": "h1", "opponent_suite_id": None, "opponent_artifact_id_or_params_hash": 123},
    ]
    failures = check_opponent_suite_gate(header=_header(), hand_starts=hs, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "type_error"

    hs = [
        {"event": "HandStart", "hand_id": "h1", "opponent_suite_id": None, "opponent_artifact_id_or_params_hash": "Z" * 64},
    ]
    failures = check_opponent_suite_gate(header=_header(), hand_starts=hs, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "id_invalid"


def test_opponent_suite_gate_artifact_without_suite_and_mismatch() -> None:
    hs = [
        {"event": "HandStart", "hand_id": "h1", "opponent_suite_id": None, "opponent_artifact_id_or_params_hash": "a" * 64},
    ]
    failures = check_opponent_suite_gate(header=_header(), hand_starts=hs, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "artifact_without_suite"

    hs = [
        {"event": "HandStart", "hand_id": "h1", "opponent_suite_id": None, "opponent_artifact_id_or_params_hash": None},
        {"event": "HandStart", "hand_id": "h2", "opponent_suite_id": "a" * 64, "opponent_artifact_id_or_params_hash": None},
    ]
    failures = check_opponent_suite_gate(header=_header(), hand_starts=hs, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "handstart_mismatch"


def test_opponent_suite_gate_null_suite_ok() -> None:
    hs = [{"event": "HandStart", "hand_id": "h1", "opponent_suite_id": None, "opponent_artifact_id_or_params_hash": None}]
    assert check_opponent_suite_gate(header=_header(), hand_starts=hs, event_stream_ref=None, event_stream_digest=None, strict_mode=True) == []


def test_opponent_suite_gate_registry_and_dependency_failures(tmp_path: Path) -> None:
    suite_id = "a" * 64
    hs = [{"event": "HandStart", "hand_id": "h1", "opponent_suite_id": suite_id, "opponent_artifact_id_or_params_hash": None}]

    # Missing suite ref.
    failures = check_opponent_suite_gate(
        header=_header(),
        hand_starts=hs,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
        opponent_registry={"opponent_suites": {}, "populations": {}, "opponent_profiles": {}},
    )
    assert failures and failures[0]["reason"] == "missing_ref"

    # Suite entry invalid (missing population_id).
    failures = check_opponent_suite_gate(
        header=_header(),
        hand_starts=hs,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
        opponent_registry={
            "opponent_suites": {suite_id: {"opponent_suite_id": suite_id, "population_id": None, "calibration_id": None}},
            "populations": {},
            "opponent_profiles": {},
        },
    )
    assert failures and failures[0]["reason"] == "suite_invalid"

    # Missing population ref.
    failures = check_opponent_suite_gate(
        header=_header(),
        hand_starts=hs,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
        opponent_registry={
            "opponent_suites": {suite_id: {"opponent_suite_id": suite_id, "population_id": "0" * 64, "calibration_id": None}},
            "populations": {},
            "opponent_profiles": {},
        },
    )
    assert failures and failures[0]["reason"] == "population_missing_ref"

    # Calibration required but missing artifact id.
    failures = check_opponent_suite_gate(
        header=_header(),
        hand_starts=hs,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
        opponent_registry={
            "opponent_suites": {suite_id: {"opponent_suite_id": suite_id, "population_id": "0" * 64, "calibration_id": "1" * 64}},
            "populations": {"0" * 64: {"population_id": "0" * 64}},
            "opponent_profiles": {},
        },
    )
    assert failures and failures[0]["reason"] == "calibration_required_missing_artifact"


def test_opponent_suite_gate_registry_invalid_via_bad_specs(tmp_path: Path) -> None:
    root = tmp_path / "specs" / "opponents"
    (root / "suites").mkdir(parents=True, exist_ok=True)
    # Invalid suite spec: missing population_id.
    (root / "suites" / "bad.json").write_text(json.dumps({"opponent_suite_label": "bad"}), encoding="utf-8")

    hs = [{"event": "HandStart", "hand_id": "h1", "opponent_suite_id": "a" * 64, "opponent_artifact_id_or_params_hash": None}]
    failures = check_opponent_suite_gate(
        header=_header(),
        hand_starts=hs,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
        opponents_root=root,
    )
    assert failures and failures[0]["reason"] == "registry_invalid"


def test_opponent_suite_gate_passes_when_suite_and_population_present() -> None:
    pop_id = "0" * 64
    suite_spec = {"population_id": pop_id, "purpose": "baseline", "k": 1}
    suite_id = opponent_suite_id(suite_spec, strict_mode=True)

    hs = [{"event": "HandStart", "hand_id": "h1", "opponent_suite_id": suite_id, "opponent_artifact_id_or_params_hash": None}]
    failures = check_opponent_suite_gate(
        header=_header(),
        hand_starts=hs,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
        opponent_registry={
            "opponent_suites": {suite_id: {"opponent_suite_id": suite_id, "population_id": pop_id, "calibration_id": None}},
            "populations": {pop_id: {"population_id": pop_id}},
            "opponent_profiles": {},
        },
    )
    assert failures == []
