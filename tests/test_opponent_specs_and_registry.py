from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.opponent_profile import (
    OpponentProfileError,
    load_opponent_profile_spec,
    opponent_profile_id,
    validate_opponent_profile_spec,
)
from poker2.protocol.opponent_suite import OpponentSuiteError, opponent_suite_id
from poker2.protocol.opponent_suite import (
    load_opponent_suite_spec,
    opponent_suite_hash_input,
    validate_opponent_suite_spec,
)
from poker2.protocol.table_population import (
    TablePopulationError,
    load_table_population_spec,
    table_population_hash_input,
    population_id,
    validate_table_population_spec,
)
from poker2.runtime.opponent_registry import OpponentRegistryError, build_opponent_registry, resolve_opponent_suite_ref
from poker2.protocol.opponent_profile import opponent_profile_hash_input


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def test_opponent_suite_id_excludes_purpose() -> None:
    pop_id = "0" * 64
    a = {"population_id": pop_id, "purpose": "baseline", "k": 1}
    b = {"population_id": pop_id, "purpose": "realistic", "k": 1}
    assert opponent_suite_id(a, strict_mode=True) == opponent_suite_id(b, strict_mode=True)


def test_opponent_suite_id_mismatch_strict_mode() -> None:
    pop_id = "0" * 64
    spec = {"population_id": pop_id, "k": 1, "opponent_suite_id": "1" * 64}
    with pytest.raises(OpponentSuiteError) as e:
        opponent_suite_id(spec, strict_mode=True)
    assert e.value.code == "ID_MISMATCH"


def test_opponent_suite_null_convention_violation() -> None:
    pop_id = "0" * 64
    spec = {"population_id": pop_id, "k": "none"}
    with pytest.raises(OpponentSuiteError) as e:
        opponent_suite_id(spec, strict_mode=True)
    assert e.value.code == "NULL_CONVENTION_VIOLATION"


def test_opponent_profile_and_population_id_mismatch_strict_mode() -> None:
    prof = {"opponent_profile_id": "1" * 64, "style": {"vpip_target": 10}}
    with pytest.raises(OpponentProfileError) as e1:
        opponent_profile_id(prof, strict_mode=True)
    assert e1.value.code == "ID_MISMATCH"

    pop = {"population_id": "1" * 64, "seats": {"1": "0" * 64, "2": "0" * 64}}
    with pytest.raises(TablePopulationError) as e2:
        population_id(pop, strict_mode=True)
    assert e2.value.code == "ID_MISMATCH"


def test_opponent_registry_build_and_resolve(tmp_path: Path) -> None:
    root = tmp_path / "specs" / "opponents"
    profiles = root / "profiles"
    pops = root / "populations"
    suites = root / "suites"

    prof_spec = {"opponent_profile_label": "nit_v1", "style": {"vpip_target": 10}}
    _write_json(profiles / "nit.json", prof_spec)
    validate_opponent_profile_spec(prof_spec, strict_mode=True)
    prof_id = opponent_profile_id(prof_spec, strict_mode=True)

    pop_spec = {"population_label": "hu_nit_v1", "seats": {"1": prof_id, "2": prof_id}}
    _write_json(pops / "hu_nit.json", pop_spec)
    validate_table_population_spec(pop_spec, strict_mode=True)
    pop_id = population_id(pop_spec, strict_mode=True)

    suite_spec = {"opponent_suite_label": "baseline_hu_v1", "purpose": "baseline", "population_id": pop_id, "calibration_id": None}
    _write_json(suites / "baseline_hu.json", suite_spec)

    reg = build_opponent_registry(opponents_root=root, strict_mode=True)
    suite_id = reg["opponent_suites"][next(iter(reg["opponent_suites"]))]["opponent_suite_id"]
    assert suite_id == opponent_suite_id(suite_spec, strict_mode=True)

    entry, trace = resolve_opponent_suite_ref("baseline_hu_v1", registry=reg, strict_mode=True)
    assert entry["opponent_suite_id"] == suite_id
    assert trace["resolved_opponents_ref"] == f"opponent_suite://{suite_id}"

    entry2, _ = resolve_opponent_suite_ref(f"opponent_suite://{suite_id}", registry=reg, strict_mode=True)
    assert entry2["opponent_suite_id"] == suite_id


def test_opponent_registry_resolve_ambiguity_and_errors(tmp_path: Path) -> None:
    root = tmp_path / "specs" / "opponents"
    suites = root / "suites"
    pops = root / "populations"

    pop_spec = {"population_label": "p", "k": 1}
    _write_json(pops / "p.json", pop_spec)
    pop_id = population_id(pop_spec, strict_mode=True)

    _write_json(suites / "a.json", {"opponent_suite_label": "dup", "population_id": pop_id, "purpose": "baseline"})
    _write_json(suites / "b.json", {"opponent_suite_label": "dup", "population_id": pop_id, "purpose": "baseline", "k": 2})
    reg = build_opponent_registry(opponents_root=root, strict_mode=True)

    with pytest.raises(OpponentRegistryError) as e:
        resolve_opponent_suite_ref("dup", registry=reg, strict_mode=True)
    assert e.value.code == "AMBIGUOUS"

    with pytest.raises(OpponentRegistryError) as e2:
        resolve_opponent_suite_ref("missing", registry=reg, strict_mode=True)
    assert e2.value.code == "MISSING_REF"

    with pytest.raises(OpponentRegistryError) as e3:
        resolve_opponent_suite_ref("opponent_suite://nothex", registry=reg, strict_mode=True)
    assert e3.value.code == "ID_INVALID"


def test_opponent_profile_and_population_load_errors(tmp_path: Path) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")
    with pytest.raises(OpponentProfileError) as e1:
        load_opponent_profile_spec(bad_json)
    assert e1.value.code == "JSON_PARSE_FAIL"

    not_obj = tmp_path / "arr.json"
    not_obj.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(OpponentProfileError) as e2:
        load_opponent_profile_spec(not_obj)
    assert e2.value.code == "TYPE_ERROR"

    bad_json2 = tmp_path / "bad2.json"
    bad_json2.write_text("{", encoding="utf-8")
    with pytest.raises(TablePopulationError) as e3:
        load_table_population_spec(bad_json2)
    assert e3.value.code == "JSON_PARSE_FAIL"

    not_obj2 = tmp_path / "arr2.json"
    not_obj2.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(TablePopulationError) as e4:
        load_table_population_spec(not_obj2)
    assert e4.value.code == "TYPE_ERROR"


def test_opponent_profile_and_population_hash_input_edges() -> None:
    with pytest.raises(OpponentProfileError) as e1:
        opponent_profile_hash_input([], strict_mode=True)
    assert e1.value.code == "TYPE_ERROR"

    with pytest.raises(TablePopulationError) as e2:
        table_population_hash_input([], strict_mode=True)
    assert e2.value.code == "TYPE_ERROR"

    # Non-str keys must be ignored during hash input construction (0.1.2); should not crash hashing.
    prof_id = opponent_profile_id({1: "x", "segments": [1, 2, 3]}, strict_mode=True)
    assert isinstance(prof_id, str) and len(prof_id) == 64


def test_opponent_profile_and_population_null_convention_and_type_errors() -> None:
    with pytest.raises(OpponentProfileError) as e1:
        validate_opponent_profile_spec({"segments": ["none"]}, strict_mode=True)
    assert e1.value.code == "NULL_CONVENTION_VIOLATION"

    with pytest.raises(OpponentProfileError) as e2:
        validate_opponent_profile_spec({"opponent_profile_id": 123}, strict_mode=True)
    assert e2.value.code == "TYPE_ERROR"

    with pytest.raises(TablePopulationError) as e3:
        validate_table_population_spec({"seats": ["none"]}, strict_mode=True)
    assert e3.value.code == "NULL_CONVENTION_VIOLATION"

    with pytest.raises(TablePopulationError) as e4:
        validate_table_population_spec({"population_id": 123}, strict_mode=True)
    assert e4.value.code == "TYPE_ERROR"


def test_opponent_suite_validation_edges(tmp_path: Path) -> None:
    with pytest.raises(OpponentSuiteError) as e1:
        opponent_suite_hash_input([], strict_mode=True)
    assert e1.value.code == "TYPE_ERROR"

    # calibration_id/opponent_suite_id type errors.
    with pytest.raises(OpponentSuiteError) as e2:
        validate_opponent_suite_spec({"population_id": "0" * 64, "calibration_id": 123}, strict_mode=True)
    assert e2.value.code == "TYPE_ERROR"

    with pytest.raises(OpponentSuiteError) as e3:
        validate_opponent_suite_spec({"population_id": "0" * 64, "opponent_suite_id": 123}, strict_mode=True)
    assert e3.value.code == "TYPE_ERROR"

    # Load errors.
    bad_json = tmp_path / "bad_suite.json"
    bad_json.write_text("{", encoding="utf-8")
    with pytest.raises(OpponentSuiteError) as e4:
        load_opponent_suite_spec(bad_json)
    assert e4.value.code == "JSON_PARSE_FAIL"

    not_obj = tmp_path / "arr_suite.json"
    not_obj.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(OpponentSuiteError) as e5:
        load_opponent_suite_spec(not_obj)
    assert e5.value.code == "TYPE_ERROR"

    # Null Convention in list form.
    with pytest.raises(OpponentSuiteError) as e6:
        opponent_suite_id({"population_id": "0" * 64, "k": ["none"]}, strict_mode=True)
    assert e6.value.code == "NULL_CONVENTION_VIOLATION"
