from __future__ import annotations

from pathlib import Path

import pytest

from poker2.gates.postflop_gate import check_postflop_library_gate
from poker2.gates.common import GateCheckError
from poker2.protocol.provenance import build_provenance_envelope_v1, provenance_id
from poker2.runtime import artifact_store
from poker2.runtime.artifact_store import write_artifact_json


def _minimal_header(*, provenance_ref: str) -> dict[str, object]:
    return {
        "run_id": "0" * 64,
        "options_hash": "1" * 64,
        "seed": 1,
        "scenario_id": "2" * 64,
        "schema_hash": "3" * 64,
        "event_model_id": "4" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": "5" * 64},
        "provenance_ref": provenance_ref,
        "resolved_paths_digest": "6" * 64,
        "repro_tier": "Tier-A",
    }


def test_postflop_gate_requires_solver_build_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = build_provenance_envelope_v1(
        ruleset_id="a" * 64,
        triad={"action_bins_id": "b" * 64, "obs_schema_id": "c" * 64, "rake_id": "d" * 64},
        schema_hash="e" * 64,
        options_hash="f" * 64,
        seed=1,
        action_adapter_id="1" * 64,
        mapping_spec_id=None,
        mw_ladder_id=None,
        pokerkit_version=None,
        solver_build_id=None,
        repro_tier="Tier-A",
    )
    pid = provenance_id(env, strict_mode=True)
    write_artifact_json(env, artifact_id=pid, out_root=tmp_path, strict_mode=True)
    monkeypatch.setattr(artifact_store, "runtime_artifacts_store_root", lambda: tmp_path)

    header = _minimal_header(provenance_ref=f"artifact://{pid}")
    scenario_pkg = {"postflop_ref": {"artifact_ref": "artifact://deadbeef", "digest": {"alg": "sha256", "hex": "0" * 64}}}

    failures = check_postflop_library_gate(
        header=header,
        scenario_package=scenario_pkg,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "solver_build_id_missing"

    env_ok = dict(env)
    env_ok["solver_build_id"] = "f" * 64
    pid_ok = provenance_id(env_ok, strict_mode=True)
    write_artifact_json(env_ok, artifact_id=pid_ok, out_root=tmp_path, strict_mode=True)
    header_ok = _minimal_header(provenance_ref=f"artifact://{pid_ok}")

    failures = check_postflop_library_gate(
        header=header_ok,
        scenario_package=scenario_pkg,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures == []


def test_postflop_gate_provenance_unresolvable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(artifact_store, "default_artifact_search_roots", lambda: [tmp_path])
    header = _minimal_header(provenance_ref=f"artifact://{'f' * 64}")
    scenario_pkg = {"postflop_ref": {"artifact_ref": "artifact://deadbeef", "digest": {"alg": "sha256", "hex": "0" * 64}}}

    failures = check_postflop_library_gate(
        header=header,
        scenario_package=scenario_pkg,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_ref_unresolvable"


def test_postflop_gate_invalid_postflop_ref_type() -> None:
    header = _minimal_header(provenance_ref=f"artifact://{'a' * 64}")
    with pytest.raises(GateCheckError):
        check_postflop_library_gate(
            header=header,
            scenario_package={"postflop_ref": 1},
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=True,
        )


def test_postflop_gate_missing_provenance_ref_raises() -> None:
    header = _minimal_header(provenance_ref=f"artifact://{'a' * 64}")
    header.pop("provenance_ref", None)
    with pytest.raises(GateCheckError):
        check_postflop_library_gate(
            header=header,
            scenario_package={"postflop_ref": {"artifact_ref": "artifact://deadbeef", "digest": {"alg": "sha256", "hex": "0" * 64}}},
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=True,
        )


def test_postflop_gate_none_package_returns_empty() -> None:
    header = _minimal_header(provenance_ref=f"artifact://{'a' * 64}")
    failures = check_postflop_library_gate(
        header=header,
        scenario_package=None,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures == []


def test_postflop_gate_non_strict_invalid_postflop_ref() -> None:
    header = _minimal_header(provenance_ref=f"artifact://{'a' * 64}")
    failures = check_postflop_library_gate(
        header=header,
        scenario_package={"postflop_ref": 1},
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=False,
    )
    assert failures and failures[0]["reason"] == "postflop_ref_invalid"


def test_postflop_gate_provenance_unreadable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad_id = "b" * 64
    bad_path = tmp_path / f"{bad_id}.json"
    bad_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(artifact_store, "default_artifact_search_roots", lambda: [tmp_path])

    header = _minimal_header(provenance_ref=f"artifact://{bad_id}")
    scenario_pkg = {"postflop_ref": {"artifact_ref": "artifact://deadbeef", "digest": {"alg": "sha256", "hex": "0" * 64}}}
    failures = check_postflop_library_gate(
        header=header,
        scenario_package=scenario_pkg,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_unreadable"


def test_postflop_gate_provenance_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad_id = "c" * 64
    bad_path = tmp_path / f"{bad_id}.json"
    bad_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(artifact_store, "default_artifact_search_roots", lambda: [tmp_path])

    header = _minimal_header(provenance_ref=f"artifact://{bad_id}")
    scenario_pkg = {"postflop_ref": {"artifact_ref": "artifact://deadbeef", "digest": {"alg": "sha256", "hex": "0" * 64}}}
    failures = check_postflop_library_gate(
        header=header,
        scenario_package=scenario_pkg,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_invalid"
