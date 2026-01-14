from __future__ import annotations

import json
from pathlib import Path
import hashlib

import pytest

from poker2.protocol.paths import (
    PathsError,
    _root_value_to_abs_path,
    default_paths_config,
    default_resolved_paths,
    paths_config_id,
    resolve_paths,
    validate_paths_config,
)
from poker2.protocol.scenario import ScenarioError, scenario_family_key, scenario_id
from poker2.protocol.scenario_package import (
    ScenarioPackageError,
    load_scenario_package,
    scenario_closure_from_package,
    validate_scenario_package,
)


def _sha256_file_hex(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def test_scenario_id_validation_branches() -> None:
    base = {
        "scenario_schema_id": "scenario_spec_v1",
        "ruleset_id": "0" * 64,
        "triad": {"action_bins_id": "1" * 64, "obs_schema_id": "2" * 64, "rake_id": "3" * 64},
        "schema_hash": "4" * 64,
        "abstraction_hash": "5" * 64,
        "preflop_ref": None,
        "postflop_ref": None,
        "opponent_suite_id": None,
        "population_id": None,
        "mw_ladder_id": None,
    }

    assert isinstance(scenario_id(base, strict_mode=True), str)

    bad = dict(base)
    bad["ruleset_id"] = 1
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad = dict(base)
    bad["scenario_schema_id"] = "nope"
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    bad = dict(base)
    bad["ruleset_id"] = "nothex"
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "ID_INVALID"

    bad = dict(base)
    bad["triad"] = dict(base["triad"])
    bad["triad"]["rake_id"] = 1
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad = dict(base)
    bad["triad"] = dict(base["triad"])
    bad["triad"]["rake_id"] = "nothex"
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "ID_INVALID"

    bad = dict(base)
    bad["triad"] = "nope"
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad = dict(base)
    bad["mw_ladder_id"] = 123
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad = dict(base)
    bad["mw_ladder_id"] = "nothex"
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "ID_INVALID"

    bad = dict(base)
    bad["preflop_ref"] = "nope"
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad = dict(base)
    bad["preflop_ref"] = {"digest": {"alg": "sha256", "hex": "0" * 64}}
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    bad = dict(base)
    bad["preflop_ref"] = {"artifact_ref": 1, "digest": {"alg": "sha256", "hex": "0" * 64}}
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad = dict(base)
    bad["preflop_ref"] = {"artifact_ref": "path:/abs.json", "digest": {"alg": "sha256", "hex": "0" * 64}}
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "PATH_REF_NOT_RELATIVE"

    bad = dict(base)
    bad["preflop_ref"] = {"artifact_ref": "path:rel.json", "digest": {"alg": "sha256", "hex": "0" * 64}, "x": 1}
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "EXTRA_FIELDS"

    bad = dict(base)
    bad["preflop_ref"] = {"artifact_ref": "path:rel.json", "digest": {"alg": "sha256", "hex": "nothex"}}
    with pytest.raises(ScenarioError) as exc:
        scenario_id(bad, strict_mode=True)
    assert exc.value.code == "DIGEST_INVALID"


def test_scenario_family_key_validation() -> None:
    key = scenario_family_key(
        scenario_id_hex="0" * 64,
        ruleset_id="1" * 64,
        abstraction_hash="2" * 64,
        strict_mode=True,
    )
    assert isinstance(key, str) and len(key) == 64

    with pytest.raises(ScenarioError):
        scenario_family_key(scenario_id_hex="nothex", ruleset_id="1" * 64, abstraction_hash="2" * 64, strict_mode=True)


def test_scenario_package_load_and_validate(tmp_path: Path) -> None:
    good = tmp_path / "scenario.json"
    good.write_text(json.dumps([1]), encoding="utf-8")
    with pytest.raises(ScenarioPackageError) as exc:
        load_scenario_package(good)
    assert exc.value.code == "TYPE_ERROR"

    bad_json = tmp_path / "bad.json"
    bad_json.write_bytes(b"{not json")
    with pytest.raises(ScenarioPackageError) as exc:
        load_scenario_package(bad_json)
    assert exc.value.code == "JSON_PARSE_FAIL"

    repo = Path(__file__).resolve().parents[1]
    src = repo / "specs" / "scenarios" / "internal_hu_v1.json"
    pkg = json.loads(src.read_text(encoding="utf-8"))
    ids = validate_scenario_package(pkg, strict_mode=True)
    assert "scenario_id" in ids and "scenario_family_key" in ids

    with pytest.raises(ScenarioPackageError) as exc:
        scenario_closure_from_package([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    closure = scenario_closure_from_package(pkg, strict_mode=True)
    assert closure["scenario_schema_id"] == "scenario_spec_v1"

    bad = dict(pkg)
    bad.pop("scenario_id", None)
    bad.pop("scenario_family_key", None)
    bad["scenario_schema_id"] = "nope"
    with pytest.raises(ScenarioPackageError) as exc:
        validate_scenario_package(bad, strict_mode=True)
    assert exc.value.code == "SCENARIO_CLOSURE_INVALID"

    bad = dict(pkg)
    bad["scenario_id"] = "0" * 64
    with pytest.raises(ScenarioPackageError) as exc:
        validate_scenario_package(bad, strict_mode=True)
    assert exc.value.code == "SCENARIO_ID_MISMATCH"

    bad = dict(pkg)
    bad["scenario_id"] = None
    with pytest.raises(ScenarioPackageError) as exc:
        validate_scenario_package(bad, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad = dict(pkg)
    bad["scenario_family_key"] = None
    with pytest.raises(ScenarioPackageError) as exc:
        validate_scenario_package(bad, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad = dict(pkg)
    bad["scenario_family_key"] = "0" * 64
    with pytest.raises(ScenarioPackageError) as exc:
        validate_scenario_package(bad, strict_mode=True)
    assert exc.value.code == "SCENARIO_FAMILY_KEY_MISMATCH"


def test_paths_config_validation_and_resolution(tmp_path: Path) -> None:
    cfg = default_paths_config(strict_mode=True)
    validate_paths_config(cfg, strict_mode=True)
    assert isinstance(paths_config_id(cfg, strict_mode=True), str)

    with pytest.raises(PathsError) as exc:
        validate_paths_config([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": {}, "search_order": [], "allow_symlink": True, "x": 1}, strict_mode=True)
    assert exc.value.code == "EXTRA_FIELDS"

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": {}, "search_order": [], "allow_symlink": True}, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": {}, "allow_symlink": True}, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": [], "search_order": [], "allow_symlink": True}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": {"scenario_root": None, "artifacts_root": None, "data_root": None, "x": 1}, "search_order": [], "allow_symlink": True}, strict_mode=True)
    assert exc.value.code == "EXTRA_FIELDS"

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": {"scenario_root": 1, "artifacts_root": None, "data_root": None}, "search_order": [], "allow_symlink": True}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": {"scenario_root": None, "artifacts_root": None, "data_root": None}, "search_order": "nope", "allow_symlink": True}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    # Optional roots are allowed when present.
    cfg_optional = {
        "roots": {"scenario_root": None, "artifacts_root": None, "data_root": None, "postflop_solver_src_root": None},
        "search_order": ["scenario_root", "postflop_solver_src_root"],
        "allow_symlink": True,
    }
    validate_paths_config(cfg_optional, strict_mode=True)

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": {"scenario_root": None, "artifacts_root": None, "data_root": None}, "search_order": ["scenario_root", "scenario_root"], "allow_symlink": True}, strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": {"scenario_root": None, "artifacts_root": None, "data_root": None}, "search_order": ["nope"], "allow_symlink": True}, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(PathsError) as exc:
        validate_paths_config({"roots": {"scenario_root": None, "artifacts_root": None, "data_root": None}, "search_order": [], "allow_symlink": "nope"}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    base = tmp_path / "root"
    base.mkdir()
    (base / "a.json").write_text("{}", encoding="utf-8")
    a_digest = _sha256_file_hex(base / "a.json")
    paths_config = {
        "roots": {"scenario_root": str(base), "artifacts_root": None, "data_root": None},
        "search_order": ["scenario_root"],
        "allow_symlink": True,
    }
    closure = {
        "preflop_ref": {"artifact_ref": "path:a.json", "digest": {"alg": "sha256", "hex": a_digest}},
        "postflop_ref": None,
    }
    resolved, digest, trace = resolve_paths(paths_config=paths_config, scenario_package_closure=closure, strict_mode=True)
    assert resolved["resolved_paths_digest"] == digest
    assert trace["resolved_artifacts"][0]["resolved_ok"] is True

    cfg_with_solver_root = {
        "roots": {"scenario_root": str(base), "artifacts_root": None, "data_root": None, "postflop_solver_src_root": str(base)},
        "search_order": ["scenario_root"],
        "allow_symlink": True,
    }
    resolved_pf, _, _ = resolve_paths(paths_config=cfg_with_solver_root, scenario_package_closure=closure, strict_mode=True)
    assert "postflop_solver_src_root_abs" in resolved_pf["resolved_roots"]

    # Skip None roots in search_order.
    cfg_skip = {
        "roots": {"scenario_root": str(base), "artifacts_root": None, "data_root": None},
        "search_order": ["artifacts_root", "scenario_root"],
        "allow_symlink": True,
    }
    _resolved, _digest, _trace = resolve_paths(paths_config=cfg_skip, scenario_package_closure=closure, strict_mode=True)
    assert _trace["resolved_artifacts"][0]["resolved_ok"] is True

    # Ambiguous path across roots should fail in strict_mode.
    (base / "dup.json").write_text("{}", encoding="utf-8")
    dup_digest = _sha256_file_hex(base / "dup.json")
    other = tmp_path / "other"
    other.mkdir()
    (other / "dup.json").write_text("{}", encoding="utf-8")
    amb_cfg = {
        "roots": {"scenario_root": str(base), "artifacts_root": str(other), "data_root": None},
        "search_order": ["scenario_root", "artifacts_root"],
        "allow_symlink": True,
    }
    amb_closure = {"preflop_ref": {"artifact_ref": "path:dup.json", "digest": {"alg": "sha256", "hex": dup_digest}}, "postflop_ref": None}
    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=amb_cfg, scenario_package_closure=amb_closure, strict_mode=True)
    assert exc.value.code == "AMBIGUOUS_REF"

    # Missing file should raise RESOLUTION_FAILED in strict_mode.
    missing_closure = {"preflop_ref": {"artifact_ref": "path:missing.json", "digest": {"alg": "sha256", "hex": "0" * 64}}, "postflop_ref": None}
    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=paths_config, scenario_package_closure=missing_closure, strict_mode=True)
    assert exc.value.code == "RESOLUTION_FAILED"

    # Unsupported ref scheme should fail in strict_mode.
    unsupported_closure = {"preflop_ref": {"artifact_ref": "http://x", "digest": {"alg": "sha256", "hex": "0" * 64}}, "postflop_ref": None}
    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=paths_config, scenario_package_closure=unsupported_closure, strict_mode=True)
    assert exc.value.code == "RESOLUTION_FAILED"

    # roots.{k} path: must not be host-absolute.
    bad_root_cfg = {
        "roots": {"scenario_root": "path:/abs", "artifacts_root": None, "data_root": None},
        "search_order": ["scenario_root"],
        "allow_symlink": True,
    }
    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=bad_root_cfg, scenario_package_closure={"preflop_ref": None, "postflop_ref": None}, strict_mode=True)
    assert exc.value.code == "PATH_REF_NOT_RELATIVE"

    # roots.{k} non-path: strings must be absolute in strict_mode.
    bad_root_cfg2 = {
        "roots": {"scenario_root": "relative", "artifacts_root": None, "data_root": None},
        "search_order": ["scenario_root"],
        "allow_symlink": True,
    }
    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=bad_root_cfg2, scenario_package_closure={"preflop_ref": None, "postflop_ref": None}, strict_mode=True)
    assert exc.value.code == "ROOT_NOT_ABSOLUTE"

    # ScenarioSpecClosure asset value must be object or null.
    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=paths_config, scenario_package_closure={"preflop_ref": 1, "postflop_ref": None}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=paths_config, scenario_package_closure={"preflop_ref": {"artifact_ref": 1, "digest": {"alg": "sha256", "hex": "0" * 64}}, "postflop_ref": None}, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=paths_config, scenario_package_closure={"preflop_ref": {"artifact_ref": "path:a.json", "digest": {"alg": "sha256", "hex": "nothex"}}, "postflop_ref": None}, strict_mode=True)
    assert exc.value.code == "DIGEST_INVALID"

    # artifact:// refs resolve via CAS search roots (use internal provenance artifact as fixture).
    artifact_id = "618bc35b973d796d64c476a6ffbfb4828f636abedb9e3e9fb18b56ff92c91d83"
    repo = Path(__file__).resolve().parents[1]
    artifact_path = repo / "fixtures" / "internal" / "artifacts" / f"{artifact_id}.json"
    artifact_digest = _sha256_file_hex(artifact_path)
    cas_closure = {
        "preflop_ref": {"artifact_ref": f"artifact://{artifact_id}", "digest": {"alg": "sha256", "hex": artifact_digest}},
        "postflop_ref": None,
    }
    resolved2, _, trace2 = resolve_paths(paths_config=cfg, scenario_package_closure=cas_closure, strict_mode=True)
    assert resolved2["resolved_artifacts"][0]["artifact_ref"].startswith("artifact://")
    assert trace2["resolved_artifacts"][0]["resolved_ok"] is True

    # artifact:// missing should record and fail in strict_mode.
    repo = Path(__file__).resolve().parents[1]
    candidates = ["c" * 64, "d" * 64, "e" * 64, "f" * 64, "0" * 64, "1" * 64]
    missing_id = next(
        hid
        for hid in candidates
        if not (repo / "fixtures" / "internal" / "artifacts" / f"{hid}.json").exists()
        and not (repo / "artifacts" / "store" / f"{hid}.json").exists()
    )
    missing_artifact = {"preflop_ref": {"artifact_ref": f"artifact://{missing_id}", "digest": {"alg": "sha256", "hex": "0" * 64}}, "postflop_ref": None}
    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=cfg, scenario_package_closure=missing_artifact, strict_mode=True)
    assert exc.value.code == "RESOLUTION_FAILED"

    # Digest mismatch should fail in strict_mode.
    bad_digest = {"preflop_ref": {"artifact_ref": "path:a.json", "digest": {"alg": "sha256", "hex": "f" * 64}}, "postflop_ref": None}
    with pytest.raises(PathsError) as exc:
        resolve_paths(paths_config=paths_config, scenario_package_closure=bad_digest, strict_mode=True)
    assert exc.value.code == "RESOLUTION_FAILED"

    # Default resolved_paths remains stable for empty closures.
    _, default_digest = default_resolved_paths(strict_mode=True)
    assert isinstance(default_digest, str) and len(default_digest) == 64


def test_root_value_to_abs_path_type_error() -> None:
    with pytest.raises(PathsError) as exc:
        _root_value_to_abs_path(1, root_key="scenario_root", strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"
