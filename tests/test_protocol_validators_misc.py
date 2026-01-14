from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.action_adapter import ActionAdapterError, load_action_adapter_spec, validate_action_adapter_spec
from poker2.protocol.action_bins import ActionBinsError, load_action_bins_spec, validate_action_bins_spec
from poker2.protocol.mw_ladder import MWLadderError, load_mw_ladder_spec, validate_mw_ladder_spec


def test_empty_packages_are_importable() -> None:
    import poker2.data  # noqa: F401
    import poker2.engines  # noqa: F401
    import poker2.policy  # noqa: F401


def test_action_bins_load_and_validate_error_paths(tmp_path: Path) -> None:
    with pytest.raises(ActionBinsError) as exc:
        validate_action_bins_spec(None, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(ActionBinsError) as exc:
        validate_action_bins_spec({"action_bins_id": "0" * 64}, strict_mode=True)
    assert exc.value.code == "DISALLOWED_FIELD"

    with pytest.raises(ActionBinsError) as exc:
        validate_action_bins_spec({"action_bins_schema_id": "nope"}, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(ActionBinsError) as exc:
        validate_action_bins_spec(
            {
                "action_bins_schema_id": "action_bins_spec_v1",
                "include_min_raise_to": 1,
                "include_max_raise_to": True,
                "include_extra_raise_to": False,
            },
            strict_mode=True,
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(ActionBinsError) as exc:
        validate_action_bins_spec(
            {
                "action_bins_schema_id": "action_bins_spec_v1",
                "include_min_raise_to": False,
                "include_max_raise_to": True,
                "include_extra_raise_to": True,
            },
            strict_mode=True,
        )
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(ActionBinsError) as exc:
        validate_action_bins_spec(
            {
                "action_bins_schema_id": "action_bins_spec_v1",
                "include_min_raise_to": False,
                "include_max_raise_to": False,
                "include_extra_raise_to": False,
            },
            strict_mode=True,
        )
    assert exc.value.code == "VALUE_ERROR"

    bad_json = tmp_path / "bins.json"
    bad_json.write_text("{", encoding="utf-8")
    with pytest.raises(ActionBinsError) as exc:
        load_action_bins_spec(bad_json)
    assert exc.value.code == "JSON_PARSE_FAIL"

    not_obj = tmp_path / "bins2.json"
    not_obj.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ActionBinsError) as exc:
        load_action_bins_spec(not_obj)
    assert exc.value.code == "TYPE_ERROR"


def test_action_adapter_load_and_validate_error_paths(tmp_path: Path) -> None:
    with pytest.raises(ActionAdapterError) as exc:
        validate_action_adapter_spec(None, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(ActionAdapterError) as exc:
        validate_action_adapter_spec({"action_adapter_id": "0" * 64}, strict_mode=True)
    assert exc.value.code == "DISALLOWED_FIELD"

    with pytest.raises(ActionAdapterError) as exc:
        validate_action_adapter_spec({"action_adapter_schema_id": "nope"}, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(ActionAdapterError) as exc:
        validate_action_adapter_spec(
            {"action_adapter_schema_id": "action_adapter_spec_v1", "rounding_mode": "nope", "fallback_policy": {"mode": "fail_fast"}},
            strict_mode=True,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(ActionAdapterError) as exc:
        validate_action_adapter_spec(
            {"action_adapter_schema_id": "action_adapter_spec_v1", "rounding_mode": None, "fallback_policy": []},
            strict_mode=True,
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(ActionAdapterError) as exc:
        validate_action_adapter_spec(
            {"action_adapter_schema_id": "action_adapter_spec_v1", "rounding_mode": None, "fallback_policy": {"mode": "nope"}},
            strict_mode=True,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"

    bad_json = tmp_path / "adapter.json"
    bad_json.write_text("{", encoding="utf-8")
    with pytest.raises(ActionAdapterError) as exc:
        load_action_adapter_spec(bad_json)
    assert exc.value.code == "JSON_PARSE_FAIL"

    not_obj = tmp_path / "adapter2.json"
    not_obj.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ActionAdapterError) as exc:
        load_action_adapter_spec(not_obj)
    assert exc.value.code == "TYPE_ERROR"


def test_mw_ladder_load_and_validate_error_paths(tmp_path: Path) -> None:
    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec(None, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec({"mw_ladder_id": "0" * 64}, strict_mode=True)
    assert exc.value.code == "DISALLOWED_FIELD"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec({"mw_ladder_schema_id": "nope"}, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec({"mw_ladder_schema_id": "mw_strategy_ladder_spec_v1", "rungs": []}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec({"mw_ladder_schema_id": "mw_strategy_ladder_spec_v1", "rungs": [1]}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec(
            {
                "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
                "rungs": [{"rung_id": "nope"}],
            },
            strict_mode=True,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec(
            {
                "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
                "rungs": [
                    {"rung_id": "baseline", "applicability_predicate": {"predicate_kind": "always"}, "dependency_ids": {}, "assumption_guard_id": None, "output_requirements": []},
                    {"rung_id": "baseline", "applicability_predicate": {"predicate_kind": "always"}, "dependency_ids": {}, "assumption_guard_id": None, "output_requirements": []},
                ],
            },
            strict_mode=True,
        )
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec(
            {
                "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
                "rungs": [{"rung_id": "baseline", "applicability_predicate": [], "dependency_ids": {}, "assumption_guard_id": None, "output_requirements": []}],
            },
            strict_mode=True,
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec(
            {
                "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
                "rungs": [{"rung_id": "baseline", "applicability_predicate": {"predicate_kind": "nope"}, "dependency_ids": {}, "assumption_guard_id": None, "output_requirements": []}],
            },
            strict_mode=True,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec(
            {
                "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
                "rungs": [{"rung_id": "baseline", "applicability_predicate": {"predicate_kind": "always"}, "dependency_ids": [], "assumption_guard_id": None, "output_requirements": []}],
            },
            strict_mode=True,
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec(
            {
                "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
                "rungs": [{"rung_id": "baseline", "applicability_predicate": {"predicate_kind": "always"}, "dependency_ids": {}, "assumption_guard_id": 1, "output_requirements": []}],
            },
            strict_mode=True,
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(MWLadderError) as exc:
        validate_mw_ladder_spec(
            {
                "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
                "rungs": [{"rung_id": "baseline", "applicability_predicate": {"predicate_kind": "always"}, "dependency_ids": {}, "assumption_guard_id": None, "output_requirements": [1]}],
            },
            strict_mode=True,
        )
    assert exc.value.code == "TYPE_ERROR"

    # players_range predicate is supported
    validate_mw_ladder_spec(
        {
            "mw_ladder_schema_id": "mw_strategy_ladder_spec_v1",
            "rungs": [
                {
                    "rung_id": "micro3",
                    "applicability_predicate": {"predicate_kind": "players_range", "min_players": 3, "max_players": 3},
                    "dependency_ids": {},
                    "assumption_guard_id": "a" * 64,
                    "output_requirements": [],
                },
                {
                    "rung_id": "baseline",
                    "applicability_predicate": {"predicate_kind": "always"},
                    "dependency_ids": {},
                    "assumption_guard_id": None,
                    "output_requirements": [],
                },
            ],
        },
        strict_mode=True,
    )

    bad_json = tmp_path / "mw.json"
    bad_json.write_text("{", encoding="utf-8")
    with pytest.raises(MWLadderError) as exc:
        load_mw_ladder_spec(bad_json)
    assert exc.value.code == "JSON_PARSE_FAIL"

    not_obj = tmp_path / "mw2.json"
    not_obj.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(MWLadderError) as exc:
        load_mw_ladder_spec(not_obj)
    assert exc.value.code == "TYPE_ERROR"
