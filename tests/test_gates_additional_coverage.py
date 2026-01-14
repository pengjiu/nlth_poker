from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.gates.common import (
    GateCheckError,
    _as_int,
    _as_list,
    _as_obj,
    _as_str,
    _digest_obj,
    _sha256_hex,
)
from poker2.gates.leakage_gate import check_leakage_gate
from poker2.gates.provenance_gate import check_provenance_gate
from poker2.gates.scenario_gate import check_scenario_gate_minimal
from poker2.gates.schema_gate import check_schema_gate
from poker2.gates.triad_gate import check_triad_gate
from poker2.protocol.provenance import ProvenanceError, build_provenance_envelope_v1, provenance_id, validate_provenance_envelope
from poker2.protocol.ruleset import validate_ruleset
from poker2.protocol.schema_contract import schema_hash as compute_schema_hash
from poker2.runtime.artifact_store import runtime_artifacts_store_root, write_artifact_json
from poker2.runtime.artifact_store import ArtifactStoreError, resolve_artifact_path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _internal_ruleset() -> dict[str, object]:
    ruleset_path = _repo_root() / "specs" / "rulesets" / "internal_ruleset_v1.json"
    ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
    validate_ruleset(ruleset, strict_mode=True)
    return ruleset


def _minimal_header() -> dict[str, object]:
    return {
        "run_id": "0" * 64,
        "options_hash": "1" * 64,
        "seed": 1,
        "scenario_id": "2" * 64,
        "schema_hash": compute_schema_hash(strict_mode=True),
        "event_model_id": "3" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": "4" * 64},
        "provenance_ref": f"artifact://{'5' * 64}",
        "resolved_paths_digest": "6" * 64,
        "repro_tier": "Tier-A",
    }


def test_gates_common_type_errors_and_digest_validation() -> None:
    with pytest.raises(GateCheckError):
        _as_obj(1, field="x")
    with pytest.raises(GateCheckError):
        _as_list("x", field="x")
    with pytest.raises(GateCheckError):
        _as_int(True, field="x")
    with pytest.raises(GateCheckError):
        _as_str(1, field="x")
    with pytest.raises(GateCheckError):
        _sha256_hex("nothex", field="x")
    with pytest.raises(GateCheckError):
        _digest_obj({"alg": "sha1", "hex": "0" * 40}, field="x")


def test_provenance_gate_handles_unreadable_and_invalid(tmp_path: Path) -> None:
    triad = {"action_bins_id": "0" * 64, "obs_schema_id": "1" * 64, "rake_id": "2" * 64}
    env = build_provenance_envelope_v1(
        ruleset_id="3" * 64,
        triad=triad,
        schema_hash="4" * 64,
        options_hash="5" * 64,
        seed=7,
        action_adapter_id="6" * 64,
        mapping_spec_id=None,
        mw_ladder_id=None,
        pokerkit_version=None,
        repro_tier="Tier-A",
        engine_build_id="7" * 64,
        solver_build_id="8" * 64,
        seed_derivation_digest={"alg": "sha256", "hex": "9" * 64},
    )
    validate_provenance_envelope(env, strict_mode=True)

    # Unreadable: file exists but not valid JSON.
    bad_id = "a" * 64
    store = runtime_artifacts_store_root()
    store.mkdir(parents=True, exist_ok=True)
    (store / f"{bad_id}.json").write_text("{not json", encoding="utf-8")
    header = {
        **_minimal_header(),
        "options_hash": env["options_hash"],
        "schema_hash": env["schema_hash"],
        "seed": env["seed"],
        "provenance_ref": f"artifact://{bad_id}",
    }
    failures = check_provenance_gate(header=header, hand_starts=[{"ruleset_id": env["ruleset_id"], "triad": triad}], event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "provenance_unreadable"

    # Invalid: readable JSON but fails schema validation.
    invalid_obj = {"provenance_schema_id": "provenance_envelope_v1"}
    invalid_id = "b" * 64
    (store / f"{invalid_id}.json").write_text(json.dumps(invalid_obj), encoding="utf-8")
    header["provenance_ref"] = f"artifact://{invalid_id}"
    failures = check_provenance_gate(header=header, hand_starts=[{"ruleset_id": env["ruleset_id"], "triad": triad}], event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "provenance_invalid"


def test_provenance_gate_raises_on_missing_ref_and_handstart_type_error() -> None:
    with pytest.raises(GateCheckError):
        check_provenance_gate(header={}, hand_starts=[], event_stream_ref=None, event_stream_digest=None, strict_mode=True)

    env = build_provenance_envelope_v1(
        ruleset_id="0" * 64,
        triad={"action_bins_id": "0" * 64, "obs_schema_id": "1" * 64, "rake_id": "2" * 64},
        schema_hash="3" * 64,
        options_hash="4" * 64,
        seed=1,
        action_adapter_id="5" * 64,
        mapping_spec_id=None,
        mw_ladder_id=None,
        pokerkit_version=None,
        repro_tier="Tier-A",
    )
    pid = provenance_id(env, strict_mode=True)
    write_artifact_json(env, artifact_id=pid, strict_mode=True)
    header = _minimal_header()
    header["options_hash"] = env["options_hash"]
    header["schema_hash"] = env["schema_hash"]
    header["seed"] = env["seed"]
    header["provenance_ref"] = f"artifact://{pid}"

    with pytest.raises(GateCheckError):
        check_provenance_gate(
            header=header,
            hand_starts=[{"ruleset_id": env["ruleset_id"], "triad": env["triad"], "provenance_ref": 123}],
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=True,
        )


def test_scenario_gate_strict_no_hands_and_missing_fields() -> None:
    header = _minimal_header()
    with pytest.raises(GateCheckError):
        check_scenario_gate_minimal(header={}, hand_starts=[], event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    with pytest.raises(GateCheckError):
        check_scenario_gate_minimal(header=header, hand_starts=[], event_stream_ref=None, event_stream_digest=None, strict_mode=True)


def test_schema_gate_type_error_on_handstart_schema_hash() -> None:
    header = _minimal_header()
    header["schema_hash"] = compute_schema_hash(strict_mode=True)
    with pytest.raises(GateCheckError):
        check_schema_gate(
            header=header,
            hand_starts=[{"event": "HandStart", "schema_hash": 123}],
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=True,
        )


def test_triad_gate_raises_on_no_hands_and_bad_triad_type() -> None:
    ruleset = _internal_ruleset()
    header = _minimal_header()
    with pytest.raises(GateCheckError):
        check_triad_gate(header=header, hand_starts=[], event_stream_ref=None, event_stream_digest=None, ruleset=ruleset, strict_mode=True)

    with pytest.raises(GateCheckError):
        check_triad_gate(
            header=header,
            hand_starts=[{"event": "HandStart", "triad": None}],
            event_stream_ref=None,
            event_stream_digest=None,
            ruleset=ruleset,
            strict_mode=True,
        )


def test_leakage_gate_actor_hole_cards_null_and_missing_hole_map() -> None:
    header = _minimal_header()

    failures = check_leakage_gate(
        header=header,
        decision_points=[
            {
                "event": "DecisionPoint",
                "decision_id": 1,
                "state_hash": "0" * 64,
                "snapshot_payload": {"actor_seat": 1},
                "observation_view_payload": {"hole_cards_by_seat": {"1": None}},
            }
        ],
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "actor_hole_cards_null"

    failures = check_leakage_gate(
        header=header,
        decision_points=[
            {
                "event": "DecisionPoint",
                "decision_id": 1,
                "state_hash": "0" * 64,
                "snapshot_payload": {"actor_seat": 1},
                "observation_view_payload": {},
            }
        ],
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "hole_cards_by_seat_missing"


def test_write_artifact_json_rejects_invalid_id() -> None:
    with pytest.raises(ArtifactStoreError):
        write_artifact_json({}, artifact_id="not_sha256", strict_mode=True)

    with pytest.raises(ArtifactStoreError):
        resolve_artifact_path(123)  # type: ignore[arg-type]
