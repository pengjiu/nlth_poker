from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.runtime.scenario_registry import ScenarioRegistryError, build_scenario_registry, resolve_scenario_ref


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_build_scenario_registry_returns_empty_for_missing_root(tmp_path: Path) -> None:
    missing_root = tmp_path / "does_not_exist"
    registry = build_scenario_registry(scenarios_root=missing_root, strict_mode=True)
    assert registry == {}


def test_build_scenario_registry_raises_on_invalid_scenario_package(tmp_path: Path) -> None:
    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "bad.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ScenarioRegistryError) as ei:
        build_scenario_registry(scenarios_root=root, strict_mode=True)
    assert ei.value.code == "SCENARIO_PACKAGE_INVALID"
    assert isinstance(ei.value.details, dict)
    assert ei.value.details.get("path", "").endswith("bad.json")


def test_build_scenario_registry_raises_on_duplicate_scenario_id(tmp_path: Path) -> None:
    repo = _repo_root()
    src = repo / "specs" / "scenarios" / "internal_hu_v1.json"
    payload = json.loads(src.read_text(encoding="utf-8"))

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "a.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (root / "b.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ScenarioRegistryError) as ei:
        build_scenario_registry(scenarios_root=root, strict_mode=True)
    assert ei.value.code == "AMBIGUOUS"
    assert isinstance(ei.value.details, dict)
    assert "duplicates" in ei.value.details


def test_resolve_scenario_ref_by_id_and_label() -> None:
    repo = _repo_root()
    pkg = json.loads((repo / "specs" / "scenarios" / "internal_hu_v1.json").read_text(encoding="utf-8"))
    scen_id = pkg["scenario_id"]

    registry = build_scenario_registry(strict_mode=True)

    entry_by_id, trace_by_id = resolve_scenario_ref(f"scenario://{scen_id}", registry=registry, strict_mode=True)
    assert entry_by_id["scenario_id"] == scen_id
    assert trace_by_id["resolved_scenario_ref"] == f"scenario://{scen_id}"

    entry_by_label, trace_by_label = resolve_scenario_ref("internal_hu_v1", registry=registry, strict_mode=True)
    assert entry_by_label["scenario_id"] == scen_id
    assert trace_by_label["resolved_scenario_ref"] == f"scenario://{scen_id}"


def test_resolve_scenario_ref_rejects_empty_string() -> None:
    with pytest.raises(ScenarioRegistryError) as ei:
        resolve_scenario_ref("", registry={}, strict_mode=True)
    assert ei.value.code == "TYPE_ERROR"


def test_resolve_scenario_ref_rejects_invalid_scenario_uri() -> None:
    with pytest.raises(ScenarioRegistryError) as ei:
        resolve_scenario_ref("scenario://not_sha256", registry={}, strict_mode=True)
    assert ei.value.code == "ID_INVALID"


def test_resolve_scenario_ref_missing_id() -> None:
    with pytest.raises(ScenarioRegistryError) as ei:
        resolve_scenario_ref(f"scenario://{'1' * 64}", registry={}, strict_mode=True)
    assert ei.value.code == "MISSING_REF"


def test_resolve_scenario_ref_ambiguous_label_strict_mode() -> None:
    registry = {
        "a" * 64: {"scenario_id": "a" * 64, "label_or_none": "x", "scenario_package_ref": "path:1.json"},
        "b" * 64: {"scenario_id": "b" * 64, "label_or_none": "x", "scenario_package_ref": "path:2.json"},
    }
    with pytest.raises(ScenarioRegistryError) as ei:
        resolve_scenario_ref("x", registry=registry, strict_mode=True)
    assert ei.value.code == "AMBIGUOUS"


def test_resolve_scenario_ref_label_non_strict_mode_picks_first() -> None:
    registry = {
        "b" * 64: {"scenario_id": "b" * 64, "label_or_none": "x", "scenario_package_ref": "path:b.json"},
        "a" * 64: {"scenario_id": "a" * 64, "label_or_none": "x", "scenario_package_ref": "path:a.json"},
    }
    entry, trace = resolve_scenario_ref("x", registry=registry, strict_mode=False)
    assert entry["scenario_id"] == "a" * 64
    assert isinstance(trace.get("candidates_or_null"), list)


def test_resolve_scenario_ref_missing_label() -> None:
    with pytest.raises(ScenarioRegistryError) as ei:
        resolve_scenario_ref("missing", registry={}, strict_mode=True)
    assert ei.value.code == "MISSING_REF"

