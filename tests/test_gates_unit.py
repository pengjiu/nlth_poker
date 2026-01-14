from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.gates.common import GateCheckError
from poker2.gates.leakage_gate import check_leakage_gate
from poker2.gates.mw_guard import check_mw_guard_gate
from poker2.gates.provenance_gate import check_provenance_gate
from poker2.gates.scenario_gate import check_scenario_gate_minimal
from poker2.gates.schema_gate import check_schema_gate
from poker2.gates.triad_gate import check_triad_gate
from poker2.protocol.mw_context import mw_context_digest
from poker2.protocol.provenance import (
    PROVENANCE_SCHEMA_ID,
    ProvenanceError,
    build_provenance_envelope_v1,
    provenance_id,
    runtime_env_id_v1,
    validate_provenance_envelope,
)
from poker2.protocol.ruleset import validate_ruleset
from poker2.protocol.schema_contract import schema_hash as compute_schema_hash
from poker2.runtime.artifact_store import ArtifactStoreError, resolve_artifact_path, write_artifact_bytes, write_artifact_json


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _internal_ruleset() -> dict[str, object]:
    ruleset_path = _repo_root() / "specs" / "rulesets" / "internal_ruleset_v1.json"
    ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
    validate_ruleset(ruleset, strict_mode=True)
    return ruleset


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


def test_artifact_store_resolve_and_errors(tmp_path: Path) -> None:
    artifact_id = "a" * 64
    ref = f"artifact://{artifact_id}"

    out_root = tmp_path / "store"
    written = write_artifact_json({"k": 1}, artifact_id=artifact_id, out_root=out_root, strict_mode=True)
    assert written.exists()

    resolved = resolve_artifact_path(ref, search_roots=[out_root])
    assert resolved == written

    with pytest.raises(ArtifactStoreError):
        resolve_artifact_path("path:bad")
    with pytest.raises(ArtifactStoreError):
        resolve_artifact_path("artifact://nothex")
    with pytest.raises(ArtifactStoreError):
        resolve_artifact_path(f"artifact://{'b' * 64}", search_roots=[out_root])


def test_artifact_store_write_bytes_and_resolve(tmp_path: Path) -> None:
    artifact_id = "c" * 64
    ref = f"artifact://{artifact_id}"
    out_root = tmp_path / "store"
    data = b"postflop"

    written = write_artifact_bytes(data, artifact_id=artifact_id, out_root=out_root, suffix=".bin")
    assert written.exists()

    resolved = resolve_artifact_path(ref, search_roots=[out_root])
    assert resolved == written


def test_provenance_envelope_validation_and_id() -> None:
    triad = {"action_bins_id": "0" * 64, "obs_schema_id": "1" * 64, "rake_id": "2" * 64}
    env = build_provenance_envelope_v1(
        ruleset_id="3" * 64,
        triad=triad,
        schema_hash="4" * 64,
        options_hash="5" * 64,
        seed=123,
        action_adapter_id="6" * 64,
        mapping_spec_id=None,
        mw_ladder_id=None,
        pokerkit_version=None,
        repro_tier="Tier-A",
    )
    assert env["provenance_schema_id"] == PROVENANCE_SCHEMA_ID
    validate_provenance_envelope(env, strict_mode=True)
    pid = provenance_id(env, strict_mode=True)
    assert isinstance(pid, str) and len(pid) == 64

    # runtime_env_id_v1 is stable for same python major.minor.
    assert runtime_env_id_v1() == runtime_env_id_v1()

    bad = dict(env)
    bad["provenance_schema_id"] = "bad_schema"
    with pytest.raises(ProvenanceError):
        validate_provenance_envelope(bad, strict_mode=True)


def test_provenance_gate_pass_and_failures() -> None:
    triad = {"action_bins_id": "0" * 64, "obs_schema_id": "1" * 64, "rake_id": "2" * 64}
    options_hash = "a" * 64
    schema_hash = "b" * 64
    seed = 9

    env = build_provenance_envelope_v1(
        ruleset_id="c" * 64,
        triad=triad,
        schema_hash=schema_hash,
        options_hash=options_hash,
        seed=seed,
        action_adapter_id="d" * 64,
        mapping_spec_id=None,
        mw_ladder_id=None,
        pokerkit_version=None,
        repro_tier="Tier-A",
    )
    pid = provenance_id(env, strict_mode=True)
    write_artifact_json(env, artifact_id=pid, strict_mode=True)

    header = _minimal_header(schema_hash=schema_hash, options_hash=options_hash, seed=seed, provenance_ref=f"artifact://{pid}")
    hand_starts = [{"event": "HandStart", "ruleset_id": env["ruleset_id"], "triad": triad, "provenance_ref": f"artifact://{pid}"}]
    assert check_provenance_gate(header=header, hand_starts=hand_starts, event_stream_ref=None, event_stream_digest=None, strict_mode=True) == []

    # ID mismatch: file name does not match content hash.
    wrong_id = "e" * 64
    write_artifact_json(env, artifact_id=wrong_id, strict_mode=True)
    header_bad = dict(header)
    header_bad["provenance_ref"] = f"artifact://{wrong_id}"
    failures = check_provenance_gate(header=header_bad, hand_starts=hand_starts, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "provenance_id_mismatch"

    # Header mismatch.
    header_mismatch = dict(header)
    header_mismatch["options_hash"] = "f" * 64
    failures = check_provenance_gate(
        header=header_mismatch,
        hand_starts=hand_starts,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_header_mismatch"

    # HandStart mismatch.
    bad_hand_starts = [{"event": "HandStart", "ruleset_id": env["ruleset_id"], "triad": triad, "provenance_ref": f"artifact://{'1' * 64}"}]
    failures = check_provenance_gate(
        header=header,
        hand_starts=bad_hand_starts,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "handstart_provenance_ref_mismatch"


def test_schema_gate_mismatch_and_handstart_mismatch() -> None:
    expected = compute_schema_hash(strict_mode=True)
    header = _minimal_header(schema_hash="0" * 64, options_hash="1" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")
    failures = check_schema_gate(header=header, hand_starts=[], event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "schema_hash_mismatch"

    header_ok = _minimal_header(schema_hash=expected, options_hash="1" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")
    hs = [{"event": "HandStart", "schema_hash": "3" * 64, "ruleset_id": "4" * 64, "triad": {"action_bins_id": "5" * 64, "obs_schema_id": "6" * 64, "rake_id": "7" * 64}}]
    failures = check_schema_gate(header=header_ok, hand_starts=hs, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "handstart_schema_hash_mismatch"


def test_triad_gate_rake_id_and_ruleset_id_mismatch() -> None:
    ruleset = _internal_ruleset()
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="1" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")

    # triad.rake_id mismatch
    hs_bad_rake = [{"event": "HandStart", "triad": {"rake_id": "0" * 64}, "ruleset_id": "3" * 64}]
    failures = check_triad_gate(header=header, hand_starts=hs_bad_rake, event_stream_ref=None, event_stream_digest=None, ruleset=ruleset, strict_mode=True)
    assert failures and failures[0]["reason"] == "triad_rake_id_mismatch"

    # ruleset_id mismatch (rake ok)
    from poker2.protocol.ruleset import ruleset_id as compute_ruleset_id
    from poker2.protocol.ruleset import ruleset_rake_id as compute_ruleset_rake_id

    hs_bad_ruleset = [
        {"event": "HandStart", "triad": {"rake_id": compute_ruleset_rake_id(ruleset, strict_mode=True)}, "ruleset_id": "f" * 64}
    ]
    failures = check_triad_gate(header=header, hand_starts=hs_bad_ruleset, event_stream_ref=None, event_stream_digest=None, ruleset=ruleset, strict_mode=True)
    assert failures and failures[0]["reason"] == "ruleset_id_mismatch"

    assert compute_ruleset_id(ruleset, strict_mode=True) != "f" * 64


def test_scenario_gate_minimal_failures() -> None:
    header = _minimal_header(schema_hash="0" * 64, options_hash="1" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")
    header["scenario_id"] = "3" * 64

    hs_opts_mismatch = [{"event": "HandStart", "options_hash": "9" * 64, "hand_id": "h"}]
    failures = check_scenario_gate_minimal(header=header, hand_starts=hs_opts_mismatch, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "options_hash_mismatch"

    hs_seq = [{"event": "HandStart", "hand_seq": 1}, {"event": "HandStart", "hand_seq": 3}]
    failures = check_scenario_gate_minimal(header=header, hand_starts=hs_seq, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "hand_seq_not_monotonic"


def test_leakage_gate_detects_non_actor_hole_cards() -> None:
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="1" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")
    dps = [
        {
            "event": "DecisionPoint",
            "decision_id": 1,
            "state_hash": "0" * 64,
            "snapshot_payload": {"actor_seat": 1},
            "observation_view_payload": {"hole_cards_by_seat": {"1": ["Ah", "As"], "2": ["Kd", "Ks"]}},
        }
    ]
    failures = check_leakage_gate(header=header, decision_points=dps, event_stream_ref=None, event_stream_digest=None, strict_mode=True)
    assert failures and failures[0]["reason"] == "non_actor_hole_cards_non_null"


def test_mw_guard_detects_hu_routing_and_ctx_mismatch() -> None:
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="1" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")

    decision_points = [
        {
            "event": "DecisionPoint",
            "decision_id": 1,
            "state_hash": "0" * 64,
            "snapshot_payload": {"players_alive_count": 2},
        }
    ]
    action_chosen = [
        {
            "event": "ActionChosen",
            "decision_id": 1,
            "state_hash": "0" * 64,
            "routing": {"mw_ladder_id": "0" * 64, "rung_id": "baseline", "mw_context_digest": "0" * 64},
        }
    ]
    failures = check_mw_guard_gate(
        header=header,
        decision_points=decision_points,
        action_chosen=action_chosen,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "routing_present_for_hu"

    # MW context mismatch case.
    decision_points = [
        {
            "event": "DecisionPoint",
            "decision_id": 2,
            "state_hash": "1" * 64,
            "snapshot_payload": {"players_alive_count": 3},
        }
    ]
    expected = mw_context_digest(
        state_hash="1" * 64,
        mw_ladder_id="2" * 64,
        rung_id="baseline",
        belief_digest_or_none=None,
        mw_risk_spec_id_or_none=None,
        strict_mode=True,
    )
    bad = expected[:-1] + ("0" if expected[-1] != "0" else "1")
    action_chosen = [
        {
            "event": "ActionChosen",
            "decision_id": 2,
            "state_hash": "1" * 64,
            "routing": {"mw_ladder_id": "2" * 64, "rung_id": "baseline", "mw_context_digest": bad},
            "belief_digest": None,
            "mw_risk_spec_id": None,
        }
    ]
    failures = check_mw_guard_gate(
        header=header,
        decision_points=decision_points,
        action_chosen=action_chosen,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "mw_context_digest_mismatch"


def test_schema_gate_raises_on_missing_fields() -> None:
    with pytest.raises(GateCheckError):
        check_schema_gate(header={}, hand_starts=[], event_stream_ref=None, event_stream_digest=None, strict_mode=True)
