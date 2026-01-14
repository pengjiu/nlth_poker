from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.gates.common import (
    GateCheckError,
    _as_list,
    _digest_obj,
    _sha256_hex,
)
from poker2.gates.leakage_gate import check_leakage_gate
from poker2.gates.mw_guard import check_mw_guard_gate
from poker2.gates.provenance_gate import check_provenance_gate
from poker2.gates.scenario_gate import check_scenario_gate_minimal
from poker2.gates.schema_gate import check_schema_gate
from poker2.gates.triad_gate import check_triad_gate
from poker2.protocol.provenance import (
    ProvenanceError,
    build_provenance_envelope_v1,
    provenance_id,
    validate_provenance_envelope,
)
from poker2.protocol.ruleset import validate_ruleset
from poker2.protocol.schema_contract import schema_hash as compute_schema_hash
from poker2.runtime.artifact_store import write_artifact_json


def _minimal_header(*, schema_hash: str, options_hash: str, seed: int, provenance_ref: str) -> dict[str, object]:
    return {
        "run_id": "0" * 64,
        "options_hash": options_hash,
        "seed": seed,
        "scenario_id": "1" * 64,
        "schema_hash": schema_hash,
        "event_model_id": "2" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": "3" * 64},
        "provenance_ref": provenance_ref,
        "resolved_paths_digest": "4" * 64,
        "repro_tier": "Tier-A",
    }


def _make_valid_provenance_ref() -> tuple[str, dict[str, object]]:
    triad = {"action_bins_id": "0" * 64, "obs_schema_id": "1" * 64, "rake_id": "2" * 64}
    env = build_provenance_envelope_v1(
        ruleset_id="3" * 64,
        triad=triad,
        schema_hash="4" * 64,
        options_hash="5" * 64,
        seed=6,
        action_adapter_id="6" * 64,
        mapping_spec_id="7" * 64,
        mw_ladder_id=None,
        pokerkit_version=None,
        rng_lineage_id="8" * 64,
        seed_derivation_digest=None,
        repro_tier="Tier-A",
    )
    pid = provenance_id(env, strict_mode=True)
    write_artifact_json(env, artifact_id=pid, strict_mode=True)
    return f"artifact://{pid}", env


def test_gates_common_success_paths() -> None:
    assert _as_list([1, 2], field="x") == [1, 2]
    assert _sha256_hex("0" * 64, field="x") == "0" * 64
    assert _digest_obj({"alg": "sha256", "hex": "1" * 64}, field="x") == {"alg": "sha256", "hex": "1" * 64}


def test_leakage_gate_strict_type_error_and_actor_invalid() -> None:
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="0" * 64, seed=1, provenance_ref="artifact://0" * 8)

    with pytest.raises(GateCheckError):
        check_leakage_gate(
            header=header,
            decision_points=[{"event": "DecisionPoint", "snapshot_payload": None, "observation_view_payload": {}}],
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=True,
        )

    failures = check_leakage_gate(
        header=header,
        decision_points=[
            {
                "event": "DecisionPoint",
                "decision_id": 1,
                "state_hash": "0" * 64,
                "snapshot_payload": {"actor_seat": 1},
                "observation_view_payload": {"hole_cards_by_seat": {"1": [1]}},
            }
        ],
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "actor_hole_cards_invalid"


def test_mw_guard_additional_branches() -> None:
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="0" * 64, seed=1, provenance_ref="artifact://0" * 8)

    # routing must be object or null
    with pytest.raises(GateCheckError):
        check_mw_guard_gate(
            header=header,
            decision_points=[{"event": "DecisionPoint", "decision_id": 1, "state_hash": "0" * 64, "snapshot_payload": {"players_alive_count": 3}}],
            action_chosen=[{"event": "ActionChosen", "decision_id": 1, "state_hash": "0" * 64, "routing": "bad"}],
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=True,
        )

    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 2, "state_hash": "1" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[
            {
                "event": "ActionChosen",
                "decision_id": 2,
                "state_hash": "1" * 64,
                "routing": {"mw_ladder_id": None, "rung_id": "baseline", "mw_context_digest": "0" * 64},
            }
        ],
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "mw_ladder_id_missing"

    with pytest.raises(GateCheckError):
        check_mw_guard_gate(
            header=header,
            decision_points=[{"event": "DecisionPoint", "decision_id": 3, "state_hash": "2" * 64, "snapshot_payload": {"players_alive_count": 3}}],
            action_chosen=[{"event": "ActionChosen", "decision_id": 3, "state_hash": "2" * 64, "routing": {"mw_ladder_id": "0" * 64}}],
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=True,
        )


def test_scenario_gate_missing_fields_and_schema_mismatch() -> None:
    header = _minimal_header(schema_hash="0" * 64, options_hash="1" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")

    with pytest.raises(GateCheckError):
        check_scenario_gate_minimal(
            header={"scenario_id": "0" * 64},
            hand_starts=[{"event": "HandStart"}],
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=False,
        )
    with pytest.raises(GateCheckError):
        check_scenario_gate_minimal(
            header={"scenario_id": "0" * 64, "schema_hash": "1" * 64},
            hand_starts=[{"event": "HandStart"}],
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=False,
        )

    failures = check_scenario_gate_minimal(
        header=header,
        hand_starts=[{"event": "HandStart", "schema_hash": "9" * 64, "hand_id": "h"}],
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "schema_hash_mismatch"


def test_schema_gate_continue_branches() -> None:
    expected = compute_schema_hash(strict_mode=True)
    header = _minimal_header(schema_hash=expected, options_hash="0" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")

    # hs_schema None -> continue
    assert check_schema_gate(header=header, hand_starts=[{"event": "HandStart", "schema_hash": None}], event_stream_ref=None, event_stream_digest=None, strict_mode=True) == []

    # strict_mode False, hs_schema wrong type -> continue (no raise)
    assert check_schema_gate(header=header, hand_starts=[{"event": "HandStart", "schema_hash": 123}], event_stream_ref=None, event_stream_digest=None, strict_mode=False) == []


def test_triad_gate_continue_and_missing_rake_id() -> None:
    repo = Path(__file__).resolve().parents[1]
    ruleset_path = repo / "specs" / "rulesets" / "internal_ruleset_v1.json"
    ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
    validate_ruleset(ruleset, strict_mode=True)
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="0" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")

    # strict_mode False, non-object triad -> continue
    assert check_triad_gate(header=header, hand_starts=[{"event": "HandStart", "triad": None}], event_stream_ref=None, event_stream_digest=None, ruleset=ruleset, strict_mode=False) == []

    # triad.rake_id missing -> raises
    with pytest.raises(GateCheckError):
        check_triad_gate(header=header, hand_starts=[{"event": "HandStart", "triad": {}}], event_stream_ref=None, event_stream_digest=None, ruleset=ruleset, strict_mode=True)


def test_provenance_protocol_error_branches() -> None:
    triad = {"action_bins_id": "0" * 64, "obs_schema_id": "1" * 64, "rake_id": "2" * 64}
    base = build_provenance_envelope_v1(
        ruleset_id="3" * 64,
        triad=triad,
        schema_hash="4" * 64,
        options_hash="5" * 64,
        seed=1,
        action_adapter_id="6" * 64,
        mapping_spec_id=None,
        mw_ladder_id=None,
        pokerkit_version=None,
        repro_tier=None,
    )

    with pytest.raises(ProvenanceError):
        validate_provenance_envelope([], strict_mode=True)
    bad = dict(base)
    bad["seed"] = True
    with pytest.raises(ProvenanceError):
        validate_provenance_envelope(bad, strict_mode=True)

    bad = dict(base)
    bad["python_version"] = 123
    with pytest.raises(ProvenanceError):
        validate_provenance_envelope(bad, strict_mode=True)

    bad = dict(base)
    bad["runtime_env_id"] = 123
    with pytest.raises(ProvenanceError):
        validate_provenance_envelope(bad, strict_mode=True)

    bad = dict(base)
    bad["runtime_env_id"] = "nothex"
    with pytest.raises(ProvenanceError):
        validate_provenance_envelope(bad, strict_mode=True)

    bad = dict(base)
    bad["extra"] = 1
    with pytest.raises(ProvenanceError):
        validate_provenance_envelope(bad, strict_mode=True)

    bad = dict(base)
    bad["triad"] = {}
    with pytest.raises(ProvenanceError):
        validate_provenance_envelope(bad, strict_mode=True)

    bad = dict(base)
    bad["seed_derivation_digest"] = {"alg": "sha1", "hex": "0" * 40}
    with pytest.raises(ProvenanceError):
        validate_provenance_envelope(bad, strict_mode=True)


def test_provenance_gate_remaining_branches() -> None:
    prov_ref, env = _make_valid_provenance_ref()
    header = _minimal_header(schema_hash=env["schema_hash"], options_hash=env["options_hash"], seed=env["seed"], provenance_ref=prov_ref)

    # Missing header keys triggers GateCheckError.
    with pytest.raises(GateCheckError):
        check_provenance_gate(header={"provenance_ref": prov_ref}, hand_starts=[], event_stream_ref=None, event_stream_digest=None, strict_mode=True)

    # hs_ref None -> continue
    assert check_provenance_gate(
        header=header,
        hand_starts=[{"event": "HandStart", "ruleset_id": env["ruleset_id"], "triad": env["triad"], "provenance_ref": None}],
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    ) == []

    # strict_mode False: bad hs_ref type -> continue
    assert check_provenance_gate(
        header=header,
        hand_starts=[{"event": "HandStart", "ruleset_id": env["ruleset_id"], "triad": env["triad"], "provenance_ref": 123}],
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=False,
    ) == []
