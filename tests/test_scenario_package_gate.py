from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.gates.scenario_package_gate import check_scenario_package_gate
from poker2.protocol.paths import default_paths_config


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_internal_hu_pkg() -> dict:
    repo = _repo_root()
    return json.loads((repo / "specs" / "scenarios" / "internal_hu_v1.json").read_text(encoding="utf-8"))


def test_scenario_package_gate_invalid_package() -> None:
    failures, out = check_scenario_package_gate(
        requested_scenario_ref="bad",
        header={"run_id": None, "options_hash": None, "seed": None, "scenario_id": None, "schema_hash": None},
        scenario_package={},
        expected_context={},
        paths_config=default_paths_config(strict_mode=True),
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert out == {}
    assert failures and failures[0]["reason"] == "scenario_package_invalid"


def test_scenario_package_gate_detects_context_mismatch() -> None:
    pkg = _load_internal_hu_pkg()
    pkg.pop("scenario_id", None)
    pkg.pop("scenario_family_key", None)

    failures, out = check_scenario_package_gate(
        requested_scenario_ref="internal_hu",
        header={"run_id": None, "options_hash": None, "seed": None, "scenario_id": None, "schema_hash": pkg["schema_hash"]},
        scenario_package=pkg,
        expected_context={"ruleset_id": "0" * 64},
        paths_config=default_paths_config(strict_mode=True),
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert out == {}
    assert failures and failures[0]["reason"] == "ruleset_id_mismatch"


def test_scenario_package_gate_resolved_paths_digest_mismatch() -> None:
    pkg = _load_internal_hu_pkg()
    pkg.pop("scenario_id", None)
    pkg.pop("scenario_family_key", None)

    failures, out = check_scenario_package_gate(
        requested_scenario_ref="internal_hu",
        header={"run_id": None, "options_hash": None, "seed": None, "scenario_id": None, "schema_hash": pkg["schema_hash"]},
        scenario_package=pkg,
        expected_context={"resolved_paths_digest": "f" * 64},
        paths_config=default_paths_config(strict_mode=True),
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert out == {}
    assert failures and failures[0]["reason"] == "resolved_paths_digest_mismatch"


def test_scenario_package_gate_resolved_paths_failed() -> None:
    pkg = _load_internal_hu_pkg()
    pkg.pop("scenario_id", None)
    pkg.pop("scenario_family_key", None)

    # Invalid PathsConfig triggers PathsError inside the gate.
    bad_paths_config = {"roots": {}, "search_order": [], "allow_symlink": True}

    failures, out = check_scenario_package_gate(
        requested_scenario_ref="internal_hu",
        header={"run_id": None, "options_hash": None, "seed": None, "scenario_id": None, "schema_hash": pkg["schema_hash"]},
        scenario_package=pkg,
        expected_context={},
        paths_config=bad_paths_config,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert out == {}
    assert failures and failures[0]["reason"] == "resolved_paths_failed"


def test_scenario_package_gate_pass_returns_ids_and_resolved_paths() -> None:
    pkg = _load_internal_hu_pkg()
    pkg.pop("scenario_id", None)
    pkg.pop("scenario_family_key", None)

    failures, out = check_scenario_package_gate(
        requested_scenario_ref="internal_hu",
        header={"run_id": None, "options_hash": None, "seed": None, "scenario_id": None, "schema_hash": pkg["schema_hash"]},
        scenario_package=pkg,
        expected_context={},
        paths_config=default_paths_config(strict_mode=True),
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures == []
    assert out["scenario_id"] == "9c73c2e69f81fbcca8725f6892bd4aee7453df03dd059643feed73c11dccd5a3"
    assert "resolved_paths_digest" in out


def test_scenario_package_gate_header_scenario_id_mismatch() -> None:
    pkg = _load_internal_hu_pkg()
    pkg.pop("scenario_id", None)
    pkg.pop("scenario_family_key", None)

    failures, out = check_scenario_package_gate(
        requested_scenario_ref="internal_hu",
        header={"run_id": None, "options_hash": None, "seed": None, "scenario_id": "0" * 64, "schema_hash": pkg["schema_hash"]},
        scenario_package=pkg,
        expected_context={},
        paths_config=default_paths_config(strict_mode=True),
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert out == {}
    assert failures and failures[0]["reason"] == "scenario_id_mismatch"


def test_scenario_package_gate_header_resolved_paths_digest_mismatch() -> None:
    pkg = _load_internal_hu_pkg()
    pkg.pop("scenario_id", None)
    pkg.pop("scenario_family_key", None)

    failures, out = check_scenario_package_gate(
        requested_scenario_ref="internal_hu",
        header={
            "run_id": None,
            "options_hash": None,
            "seed": None,
            "scenario_id": "9c73c2e69f81fbcca8725f6892bd4aee7453df03dd059643feed73c11dccd5a3",
            "schema_hash": pkg["schema_hash"],
            "resolved_paths_digest": "f" * 64,
        },
        scenario_package=pkg,
        expected_context={},
        paths_config=default_paths_config(strict_mode=True),
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert out == {}
    assert failures and failures[0]["reason"] == "resolved_paths_digest_mismatch"
