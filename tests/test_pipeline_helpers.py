from __future__ import annotations

from pathlib import Path
import hashlib
import json

import pytest

from poker2.cli import pipeline
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.scenario import scenario_family_key, scenario_id
from poker2.protocol.scenario_package import scenario_closure_from_package
from poker2.runtime.artifacts import write_canonical_ndjson
from poker2.runtime import artifact_store


def _base_header() -> dict[str, object]:
    return {
        "run_id": "0" * 64,
        "options_hash": "1" * 64,
        "seed": 1,
        "scenario_id": "2" * 64,
        "schema_hash": "3" * 64,
        "event_model_id": "4" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
        "provenance_ref": f"artifact://{'5' * 64}",
        "resolved_paths_digest": "6" * 64,
        "repro_tier": "Tier-A",
    }


def _compute_digest(header: dict[str, object], events: list[object]) -> str:
    hdr = dict(header)
    hdr["event_stream_digest"] = {"alg": "sha256", "hex": "0" * 64}
    return event_stream_digest_from_objects([hdr, *events], strict_mode=True)


def _sha256_hex_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def test_find_internal_fixture_eventstream_skips_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "fixtures" / "internal" / "eventstreams"
    root.mkdir(parents=True, exist_ok=True)
    (root / "bad.ndjson").write_text("{bad-json\n", encoding="utf-8")
    (root / "nondict.ndjson").write_text("1\n", encoding="utf-8")
    (root / "other.ndjson").write_text('{"run_id":"other"}\n', encoding="utf-8")

    monkeypatch.setattr(pipeline, "_repo_root", lambda: tmp_path)
    assert pipeline._find_internal_fixture_eventstream(run_id="target") is None


def test_read_eventstream_header_digest_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "eventstream.ndjson"
    header = _base_header()
    events = [{"event": "HandStart"}]
    digest = _compute_digest(header, events)
    wrong = "1" * 64 if digest != "1" * 64 else "2" * 64
    header["event_stream_digest"] = {"alg": "sha256", "hex": wrong}
    write_canonical_ndjson(path, [header, *events], strict_mode=True)

    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._read_eventstream_with_digest(path, strict_mode=True)
    assert e.value.code == "EVENT_STREAM_HEADER_DIGEST_MISMATCH"


def test_read_eventstream_event_not_object(tmp_path: Path) -> None:
    path = tmp_path / "eventstream.ndjson"
    header = _base_header()
    events: list[object] = [1]
    digest = _compute_digest(header, events)
    header["event_stream_digest"] = {"alg": "sha256", "hex": digest}
    write_canonical_ndjson(path, [header, *events], strict_mode=True)

    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._read_eventstream_with_digest(path, strict_mode=True)
    assert e.value.code == "EVENT_NOT_OBJECT"


def test_read_eventstream_header_not_object_relaxed(tmp_path: Path) -> None:
    path = tmp_path / "eventstream.ndjson"
    path.write_text("1\n", encoding="utf-8")
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._read_eventstream_with_digest(path, strict_mode=False)
    assert e.value.code == "HEADER_NOT_OBJECT"


def test_resolve_run_context_requires_scenario_or_runspec() -> None:
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._resolve_run_context(
            scenario_ref=None,
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=None,
            paths_config_path=None,
            postflop_solver_src_root=None,
            seed=1,
            strict_mode=True,
        )
    assert e.value.code == "ARGUMENT_ERROR"


def test_pipeline_requires_policy_deps_for_postflop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = b'{"postflop_library_schema_id":"postflop_library_v1"}\n'
    digest = _sha256_hex_bytes(payload)
    artifact_path = tmp_path / f"{digest}.json"
    artifact_path.write_bytes(payload)

    monkeypatch.setattr(artifact_store, "runtime_artifacts_store_root", lambda: tmp_path)

    repo = Path(__file__).resolve().parents[1]
    base_pkg = json.loads((repo / "specs" / "scenarios" / "internal_hu_v1.json").read_text(encoding="utf-8"))
    base_pkg["postflop_ref"] = {"artifact_ref": f"artifact://{digest}", "digest": {"alg": "sha256", "hex": digest}}
    base_pkg.pop("scenario_id", None)
    base_pkg.pop("scenario_family_key", None)

    closure = scenario_closure_from_package(base_pkg, strict_mode=True)
    scen_id = scenario_id(closure, strict_mode=True)
    fam_key = scenario_family_key(
        scenario_id_hex=scen_id,
        ruleset_id=closure["ruleset_id"],
        abstraction_hash=closure["abstraction_hash"],
        strict_mode=True,
    )
    base_pkg["scenario_id"] = scen_id
    base_pkg["scenario_family_key"] = fam_key
    scen_path = tmp_path / "scenario.json"
    scen_path.write_text(json.dumps(base_pkg), encoding="utf-8")

    def _registry(*_args: object, **_kwargs: object) -> dict[str, dict[str, object]]:
        return {
            scen_id: {
                "scenario_id": scen_id,
                "scenario_family_key": fam_key,
                "scenario_package_ref": f"path:{scen_path}",
                "scenario_package_digest": {"alg": "sha256", "hex": "0" * 64},
                "label_or_none": None,
            }
        }

    monkeypatch.setattr(pipeline, "build_scenario_registry", lambda strict_mode=True: _registry())
    monkeypatch.setattr(pipeline, "postflop_solver_src_root_from_paths_trace", lambda _trace: tmp_path)
    monkeypatch.setattr(pipeline, "compute_postflop_solver_build_id", lambda **_kw: "f" * 64)

    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._resolve_run_context_from_refs(
            scenario_ref=f"scenario://{scen_id}",
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            paths_config_path=None,
            postflop_solver_src_root="path:postflop",
            seed=1,
            strict_mode=True,
        )
    assert e.value.code == "POLICY_DEPS_MISSING_POSTFLOP"


def test_policy_deps_contains_ref() -> None:
    ref = {"artifact_ref": "artifact://x", "digest": {"alg": "sha256", "hex": "0" * 64}}
    spec = {"policy_deps": [ref]}
    assert pipeline._policy_deps_contains_ref(spec, ref) is True
    assert pipeline._policy_deps_contains_ref({"policy_deps": []}, ref) is False


def test_artifacts_root_from_paths_missing_default() -> None:
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._artifacts_root_from_paths(paths_trace={}, artifacts_root_override=None)
    assert e.value.code == "ARTIFACTS_ROOT_MISSING"


def test_artifacts_root_from_paths_default(tmp_path: Path) -> None:
    base, override = pipeline._artifacts_root_from_paths(
        paths_trace={"resolved_roots_abs": {"artifacts_root_abs_or_null": str(tmp_path)}},
        artifacts_root_override=None,
    )
    assert base == tmp_path
    assert override is None


def test_build_runspec_obj_validates_opponent_suite_id() -> None:
    obj = pipeline._build_runspec_obj(
        run_id="0" * 64,
        options_hash="1" * 64,
        seed=1,
        strict_mode=True,
        scenario_id="2" * 64,
        profile_id="3" * 64,
        policy_id="4" * 64,
        opponent_suite_id="5" * 64,
        resolved_paths_digest="6" * 64,
    )
    assert obj["opponent_suite_id"] == "5" * 64
