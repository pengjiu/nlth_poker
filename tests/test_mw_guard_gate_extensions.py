from __future__ import annotations

from pathlib import Path

import pytest

from poker2.gates.mw_guard import check_mw_guard_gate
from poker2.protocol.mw_assumption_guard import default_internal_mw_assumption_guard
from poker2.protocol.mw_context import mw_context_digest
from poker2.protocol.mw_ladder import load_mw_ladder_spec, mw_ladder_id
from poker2.protocol.schema_contract import schema_hash as compute_schema_hash
from poker2.runtime.mw_ladder_registry import build_mw_ladder_registry


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


_INTERNAL_GUARD_ID = default_internal_mw_assumption_guard(strict_mode=True)[1]


def test_mw_ladder_registry_contains_internal() -> None:
    spec_path = Path("specs/mw_ladders/internal_mw_ladder_v1.json")
    spec = load_mw_ladder_spec(spec_path)
    mid = mw_ladder_id(spec, strict_mode=True)
    registry = build_mw_ladder_registry(strict_mode=True)
    assert mid in registry
    assert registry[mid]["mw_ladder_ref"].endswith("internal_mw_ladder_v1.json")


def test_mw_guard_requires_routing_for_multiway() -> None:
    spec_path = Path("specs/mw_ladders/internal_mw_ladder_v1.json")
    spec = load_mw_ladder_spec(spec_path)
    mid = mw_ladder_id(spec, strict_mode=True)
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="0" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")

    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 1, "state_hash": "0" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[{"event": "ActionChosen", "decision_id": 1, "state_hash": "0" * 64, "routing": None}],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id=mid,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "routing_missing_for_mw"


def test_mw_guard_detects_ladder_id_mismatch() -> None:
    spec_path = Path("specs/mw_ladders/internal_mw_ladder_v1.json")
    spec = load_mw_ladder_spec(spec_path)
    mid = mw_ladder_id(spec, strict_mode=True)
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="1" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")

    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 2, "state_hash": "1" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[
            {
                "event": "ActionChosen",
                "decision_id": 2,
                "state_hash": "1" * 64,
                "routing": {"mw_ladder_id": "f" * 64, "rung_id": "baseline", "mw_context_digest": "0" * 64},
            }
        ],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id=mid,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "mw_ladder_id_mismatch"


def test_mw_guard_dependency_missing() -> None:
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="2" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")
    mw_spec = {
        "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
        "rungs": [
            {
                "rung_id": "micro3",
                "applicability_predicate": {"predicate_kind": "always"},
                "dependency_ids": {"belief_spec_id": "c" * 64, "mw_risk_spec_id": "d" * 64},
                "assumption_guard_id": _INTERNAL_GUARD_ID,
                "output_requirements": [],
            }
        ],
    }

    routing = {
        "mw_ladder_id": "f" * 64,
        "rung_id": "micro3",
        "mw_context_digest": mw_context_digest(
            state_hash="2" * 64,
            mw_ladder_id="f" * 64,
            rung_id="micro3",
            belief_digest_or_none=None,
            mw_risk_spec_id_or_none=None,
            strict_mode=True,
        ),
    }

    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 3, "state_hash": "2" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[{"event": "ActionChosen", "decision_id": 3, "state_hash": "2" * 64, "routing": routing}],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id="f" * 64,
        mw_ladder_spec=mw_spec,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "belief_spec_id_missing"


def test_mw_guard_missing_ladder_ref() -> None:
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="3" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")
    failures = check_mw_guard_gate(
        header=header,
        decision_points=[],
        action_chosen=[],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id="a" * 64,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "mw_ladder_missing"


def test_mw_guard_unknown_rung_and_missing_assumption_guard() -> None:
    spec_path = Path("specs/mw_ladders/internal_mw_ladder_v1.json")
    spec = load_mw_ladder_spec(spec_path)
    mid = mw_ladder_id(spec, strict_mode=True)
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="4" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")

    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 4, "state_hash": "3" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[
            {
                "event": "ActionChosen",
                "decision_id": 4,
                "state_hash": "3" * 64,
                "routing": {"mw_ladder_id": mid, "rung_id": "micro3", "mw_context_digest": "0" * 64},
            }
        ],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id=mid,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "rung_id_unknown"

    mw_spec = {
        "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
        "rungs": [
            {
                "rung_id": "micro3",
                "applicability_predicate": {"predicate_kind": "always"},
                "dependency_ids": {},
                "assumption_guard_id": None,
                "output_requirements": [],
            }
        ],
    }
    routing = {
        "mw_ladder_id": "f" * 64,
        "rung_id": "micro3",
        "mw_context_digest": mw_context_digest(
            state_hash="4" * 64,
            mw_ladder_id="f" * 64,
            rung_id="micro3",
            belief_digest_or_none=None,
            mw_risk_spec_id_or_none=None,
            strict_mode=True,
        ),
    }
    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 5, "state_hash": "4" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[{"event": "ActionChosen", "decision_id": 5, "state_hash": "4" * 64, "routing": routing}],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id="f" * 64,
        mw_ladder_spec=mw_spec,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "assumption_guard_missing"


def test_mw_guard_assumption_guard_unresolvable() -> None:
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="7" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")
    mw_spec = {
        "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
        "rungs": [
            {
                "rung_id": "micro3",
                "applicability_predicate": {"predicate_kind": "always"},
                "dependency_ids": {},
                "assumption_guard_id": "f" * 64,
                "output_requirements": [],
            }
        ],
    }
    routing = {
        "mw_ladder_id": "f" * 64,
        "rung_id": "micro3",
        "mw_context_digest": "0" * 64,
    }
    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 9, "state_hash": "8" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[{"event": "ActionChosen", "decision_id": 9, "state_hash": "8" * 64, "routing": routing}],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id="f" * 64,
        mw_ladder_spec=mw_spec,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "assumption_guard_unresolvable"


def test_mw_guard_belief_digest_and_risk_missing() -> None:
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="5" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")
    mw_spec = {
        "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
        "rungs": [
            {
                "rung_id": "micro3",
                "applicability_predicate": {"predicate_kind": "always"},
                "dependency_ids": {"belief_spec_id": "c" * 64, "mw_risk_spec_id": "d" * 64},
                "assumption_guard_id": _INTERNAL_GUARD_ID,
                "output_requirements": [],
            }
        ],
    }
    routing = {
        "mw_ladder_id": "f" * 64,
        "rung_id": "micro3",
        "mw_context_digest": "0" * 64,
    }
    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 6, "state_hash": "5" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[
            {
                "event": "ActionChosen",
                "decision_id": 6,
                "state_hash": "5" * 64,
                "routing": routing,
                "belief_spec_id": "c" * 64,
                "belief_digest": None,
                "mw_risk_spec_id": None,
            }
        ],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id="f" * 64,
        mw_ladder_spec=mw_spec,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "belief_digest_missing"

    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 7, "state_hash": "6" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[
            {
                "event": "ActionChosen",
                "decision_id": 7,
                "state_hash": "6" * 64,
                "routing": routing,
                "belief_spec_id": "c" * 64,
                "belief_digest": {"alg": "sha256", "hex": "0" * 64},
                "mw_risk_spec_id": None,
            }
        ],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id="f" * 64,
        mw_ladder_spec=mw_spec,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "mw_risk_spec_id_missing"


def test_mw_guard_unresolvable_ladder_and_enforce_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    header = _minimal_header(schema_hash=compute_schema_hash(strict_mode=True), options_hash="6" * 64, seed=1, provenance_ref=f"artifact://{'2'*64}")

    def _boom(*_args: object, **_kwargs: object) -> dict:
        from poker2.runtime.mw_ladder_registry import MWLadderRegistryError

        raise MWLadderRegistryError("BOOM", "boom")

    import poker2.gates.mw_guard as mw_guard_mod

    monkeypatch.setattr(mw_guard_mod, "build_mw_ladder_registry", _boom)

    failures = check_mw_guard_gate(
        header=header,
        decision_points=[],
        action_chosen=[],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id="a" * 64,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "mw_ladder_unresolvable"

    routing = {"mw_ladder_id": "f" * 64, "rung_id": "baseline", "mw_context_digest": "0" * 64}
    failures = check_mw_guard_gate(
        header=header,
        decision_points=[{"event": "DecisionPoint", "decision_id": 8, "state_hash": "7" * 64, "snapshot_payload": {"players_alive_count": 3}}],
        action_chosen=[{"event": "ActionChosen", "decision_id": 8, "state_hash": "7" * 64, "routing": routing}],
        event_stream_ref=None,
        event_stream_digest=None,
        scenario_mw_ladder_id=None,
        enforce_mw_ladder_id=True,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "mw_ladder_id_missing"
