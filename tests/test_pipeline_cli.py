from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.cli import pipeline
from poker2.protocol.run_manifest import validate_run_manifest


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pipeline_init_eval_doctor_stats_happy_path(tmp_path: Path) -> None:
    out_init = pipeline.pipeline_init(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    assert out_init["status"] == "pass"
    run_id = out_init["run_id"]

    run_dir = tmp_path / run_id
    runspec_path = run_dir / "manifest" / "runspec.json"
    manifest_path = run_dir / "manifest" / "run_manifest.json"
    assert runspec_path.exists()
    assert manifest_path.exists()

    out_eval = pipeline.pipeline_eval(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    assert out_eval["status"] == "pass"
    event_path = run_dir / "eventstream" / "eventstream.ndjson"
    assert event_path.exists()

    out_doctor = pipeline.pipeline_doctor(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    assert out_doctor["status"] == "pass"
    doctor_report_path = run_dir / "report" / "doctor_report.json"
    assert doctor_report_path.exists()

    out_stats = pipeline.pipeline_stats(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    assert out_stats["status"] == "pass"
    report_path = run_dir / "report" / "report.json"
    assert report_path.exists()

    manifest = _read_json(manifest_path)
    validate_run_manifest(manifest, strict_mode=True)


def test_pipeline_eval_missing_fixture_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_eval(
            scenario_ref="internal_hu_v1",
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=None,
            seed=123,
            strict_mode=True,
            artifacts_root=tmp_path,
        )
    assert e.value.code == "MISSING_FIXTURE"


def test_pipeline_eval_opponents_ref_missing(tmp_path: Path) -> None:
    with pytest.raises(Exception) as e:
        pipeline.pipeline_eval(
            scenario_ref="internal_hu_v1",
            profile_ref=None,
            policy_ref=None,
            opponents_ref="baseline_hu_v1",
            runspec_path=None,
            seed=1001,
            strict_mode=True,
            artifacts_root=tmp_path,
        )
    assert getattr(e.value, "code", None) == "MISSING_REF"


def test_pipeline_eval_detects_header_digest_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Use a known-good run_id to make pipeline_eval deterministic.
    out = pipeline.pipeline_eval(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path / "good",
    )
    run_id = out["run_id"]

    # Create a broken fixture copy with a wrong header digest.
    fixture = pipeline._find_internal_fixture_eventstream(run_id=run_id)
    assert fixture is not None
    bad = tmp_path / "bad.ndjson"
    bad.write_bytes(fixture.read_bytes())
    lines = bad.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["event_stream_digest"]["hex"] = "0" * 64
    lines[0] = json.dumps(header, sort_keys=True)
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")

    monkeypatch.setattr(pipeline, "_find_internal_fixture_eventstream", lambda *, run_id: bad)
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_eval(
            scenario_ref="internal_hu_v1",
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=None,
            seed=1001,
            strict_mode=True,
            artifacts_root=tmp_path / "out",
        )
    assert e.value.code == "EVENT_STREAM_HEADER_DIGEST_MISMATCH"


def test_pipeline_eval_runspec_happy_path(tmp_path: Path) -> None:
    out_init = pipeline.pipeline_init(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    run_id = out_init["run_id"]
    runspec_path = tmp_path / run_id / "manifest" / "runspec.json"

    out = pipeline.pipeline_eval(
        scenario_ref=None,
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=runspec_path,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    assert out["status"] == "pass"


def test_pipeline_eval_runspec_seed_mismatch(tmp_path: Path) -> None:
    out_init = pipeline.pipeline_init(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    run_id = out_init["run_id"]
    runspec_path = tmp_path / run_id / "manifest" / "runspec.json"
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_eval(
            scenario_ref=None,
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=runspec_path,
            seed=1002,
            strict_mode=True,
            artifacts_root=tmp_path,
        )
    assert e.value.code == "RUNSPEC_SEED_MISMATCH"


def test_pipeline_eval_runspec_strict_mismatch(tmp_path: Path) -> None:
    out_init = pipeline.pipeline_init(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    run_id = out_init["run_id"]
    runspec_path = tmp_path / run_id / "manifest" / "runspec.json"
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_eval(
            scenario_ref=None,
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=runspec_path,
            seed=1001,
            strict_mode=False,
            artifacts_root=tmp_path,
        )
    assert e.value.code == "RUNSPEC_STRICT_MISMATCH"


def test_pipeline_doctor_requires_eventstream(tmp_path: Path) -> None:
    pipeline.pipeline_init(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_doctor(
            scenario_ref="internal_hu_v1",
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=None,
            seed=1001,
            strict_mode=True,
            artifacts_root=tmp_path,
        )
    assert e.value.code == "MISSING_EVENTSTREAM"


def test_pipeline_eval_runspec_invalid_missing_fields(tmp_path: Path) -> None:
    bad = tmp_path / "runspec.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_eval(
            scenario_ref=None,
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=bad,
            seed=1001,
            strict_mode=True,
            artifacts_root=tmp_path,
        )
    assert e.value.code == "RUNSPEC_INVALID"


def test_pipeline_eval_runspec_options_hash_mismatch(tmp_path: Path) -> None:
    out_init = pipeline.pipeline_init(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    run_id = out_init["run_id"]
    runspec_path = tmp_path / run_id / "manifest" / "runspec.json"
    runspec_obj = _read_json(runspec_path)
    runspec_obj["options_hash"] = "0" * 64
    runspec_path.write_text(json.dumps(runspec_obj, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_eval(
            scenario_ref=None,
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=runspec_path,
            seed=1001,
            strict_mode=True,
            artifacts_root=tmp_path,
        )
    assert e.value.code == "OPTIONS_HASH_MISMATCH"


def test_pipeline_eval_runspec_run_id_mismatch(tmp_path: Path) -> None:
    out_init = pipeline.pipeline_init(
        scenario_ref="internal_hu_v1",
        profile_ref=None,
        policy_ref=None,
        opponents_ref=None,
        runspec_path=None,
        seed=1001,
        strict_mode=True,
        artifacts_root=tmp_path,
    )
    run_id = out_init["run_id"]
    runspec_path = tmp_path / run_id / "manifest" / "runspec.json"
    runspec_obj = _read_json(runspec_path)
    runspec_obj["run_id"] = "0" * 64
    runspec_path.write_text(json.dumps(runspec_obj, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_eval(
            scenario_ref=None,
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=runspec_path,
            seed=1001,
            strict_mode=True,
            artifacts_root=tmp_path,
        )
    assert e.value.code == "RUN_ID_MISMATCH"


def test_pipeline_main_argument_rules(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    # --runspec mutual exclusion.
    runspec_path = tmp_path / "runspec.json"
    runspec_path.write_text("{}", encoding="utf-8")
    rc = pipeline.main(["eval", "--runspec", str(runspec_path), "--scenario", "internal_hu_v1"])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "ARGUMENT_ERROR"


def test_pipeline_main_stages_with_temp_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def _fake_artifacts_root_from_paths(*, paths_trace: dict, artifacts_root_override: Path | None) -> tuple[Path, str | None]:
        return tmp_path, str(tmp_path)

    monkeypatch.setattr(pipeline, "_artifacts_root_from_paths", _fake_artifacts_root_from_paths)

    rc = pipeline.main(["init", "--scenario", "internal_hu_v1", "--seed", "1001"])
    assert rc == 0
    json.loads(capsys.readouterr().out)

    rc = pipeline.main(["eval", "--scenario", "internal_hu_v1", "--seed", "1001"])
    assert rc == 0
    json.loads(capsys.readouterr().out)

    rc = pipeline.main(["doctor", "--scenario", "internal_hu_v1", "--seed", "1001"])
    assert rc == 0
    json.loads(capsys.readouterr().out)

    rc = pipeline.main(["stats", "--scenario", "internal_hu_v1", "--seed", "1001"])
    assert rc == 0
    json.loads(capsys.readouterr().out)


def test_pipeline_main_not_implemented_stage(capsys: pytest.CaptureFixture[str]) -> None:
    rc = pipeline.main(["import-preflop", "--scenario", "internal_hu_v1"])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "NOT_IMPLEMENTED"

    # --scenario required when not using --runspec.
    rc = pipeline.main(["eval"])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "ARGUMENT_ERROR"
