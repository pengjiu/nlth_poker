from __future__ import annotations

import pytest

from poker2.protocol.options_hash import OptionsHashError, compute_options_hash


def _minimal_run_closure() -> dict:
    return {
        "scenario_id": "0" * 64,
        "ruleset_id": "0" * 64,
        "triad": {"action_bins_id": "0" * 64, "obs_schema_id": "0" * 64, "rake_id": "0" * 64},
        "schema_hash": "0" * 64,
        "resolved_paths_digest": "0" * 64,
        "abstraction_hash": "0" * 64,
        "policy_id": "0" * 64,
        "profile_id": "0" * 64,
        "opponent_suite_id": None,
        "opponent_artifact_id_or_params_hash": None,
        "mw_ladder_id": None,
        "belief_spec_id": None,
        "mw_risk_spec_id": None,
        "adaptation_digest": None,
        "engine_build_id": None,
        "solver_build_id": None,
        "pokerkit_version": None,
        "strict_mode": True,
    }


def test_compute_options_hash_ok() -> None:
    h = compute_options_hash(_minimal_run_closure(), strict_mode=True)
    assert isinstance(h, str) and len(h) == 64


def test_compute_options_hash_rejects_label_fields() -> None:
    c = _minimal_run_closure()
    c["policy_label"] = "baseline"
    with pytest.raises(OptionsHashError) as exc:
        compute_options_hash(c, strict_mode=True)
    assert exc.value.code == "LABEL_IN_HASH_INPUT"


def test_compute_options_hash_rejects_missing_fields() -> None:
    c = _minimal_run_closure()
    c.pop("schema_hash")
    with pytest.raises(OptionsHashError) as exc:
        compute_options_hash(c, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"


def test_compute_options_hash_rejects_non_object() -> None:
    with pytest.raises(OptionsHashError) as exc:
        compute_options_hash([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"


def test_compute_options_hash_scans_lists_for_labels() -> None:
    c = _minimal_run_closure()
    c["extra_list"] = [{"bad_label": "x"}]
    with pytest.raises(OptionsHashError) as exc:
        compute_options_hash(c, strict_mode=True)
    assert exc.value.code == "LABEL_IN_HASH_INPUT"
