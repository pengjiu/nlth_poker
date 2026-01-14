from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.cli import pipeline


def _base_runspec() -> dict[str, object]:
    return {
        "runspec_schema_id": "runspec_v1",
        "run_id_schema": "run_id_v1",
        "run_id": "0" * 64,
        "options_hash": "1" * 64,
        "seed": 1,
        "strict_mode": True,
        "scenario_id": "2" * 64,
        "profile_id": "3" * 64,
        "policy_id": "4" * 64,
        "opponent_suite_id": None,
        "execution_hint": None,
        "resolved_paths_digest": "5" * 64,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("runspec_schema_id", "runspec_v0"),
        ("run_id_schema", "run_id_v0"),
        ("seed", "not-int"),
        ("strict_mode", "not-bool"),
        ("execution_hint", "not-object"),
    ],
)
def test_runspec_validation_errors(tmp_path: Path, field: str, value: object) -> None:
    obj = _base_runspec()
    obj[field] = value
    path = tmp_path / "runspec.json"
    path.write_text(json.dumps(obj, sort_keys=True), encoding="utf-8")
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_eval(
            scenario_ref=None,
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=path,
            seed=1,
            strict_mode=True,
            artifacts_root=tmp_path,
        )
    assert e.value.code == "RUNSPEC_INVALID"


def test_load_ruleset_by_id_missing() -> None:
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._load_ruleset_by_id(ruleset_id="0" * 64)
    assert e.value.code == "MISSING_REF"


def test_load_ruleset_by_id_ambiguous(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ruleset_path = Path("specs/rulesets/internal_ruleset_v1.json")
    ruleset_obj = json.loads(ruleset_path.read_text(encoding="utf-8"))
    ruleset_id = pipeline.compute_ruleset_id(ruleset_obj, strict_mode=True)
    root = tmp_path / "specs" / "rulesets"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.json").write_text(json.dumps(ruleset_obj, sort_keys=True), encoding="utf-8")
    (root / "b.json").write_text(json.dumps(ruleset_obj, sort_keys=True), encoding="utf-8")

    monkeypatch.setattr(pipeline, "_repo_root", lambda: tmp_path)
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._load_ruleset_by_id(ruleset_id=ruleset_id)
    assert e.value.code == "AMBIGUOUS"


def test_find_internal_fixture_eventstream_ambiguous(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "fixtures" / "internal" / "eventstreams"
    root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"run_id": "abc"}, sort_keys=True)
    (root / "a.ndjson").write_text(payload + "\n", encoding="utf-8")
    (root / "b.ndjson").write_text(payload + "\n", encoding="utf-8")

    monkeypatch.setattr(pipeline, "_repo_root", lambda: tmp_path)
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._find_internal_fixture_eventstream(run_id="abc")
    assert e.value.code == "AMBIGUOUS"


def test_runspec_unreadable_json(tmp_path: Path) -> None:
    bad = tmp_path / "runspec.json"
    bad.write_text("{bad-json", encoding="utf-8")
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline.pipeline_eval(
            scenario_ref=None,
            profile_ref=None,
            policy_ref=None,
            opponents_ref=None,
            runspec_path=bad,
            seed=1,
            strict_mode=True,
            artifacts_root=tmp_path,
        )
    assert e.value.code == "RUNSPEC_UNREADABLE"


def test_load_runspec_non_object(tmp_path: Path) -> None:
    path = tmp_path / "runspec.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(pipeline.PipelineError) as e:
        pipeline._load_runspec(path)
    assert e.value.code == "RUNSPEC_INVALID"


def test_load_runspec_accepts_opponent_suite_id(tmp_path: Path) -> None:
    obj = _base_runspec()
    obj["opponent_suite_id"] = "a" * 64
    path = tmp_path / "runspec.json"
    path.write_text(json.dumps(obj, sort_keys=True), encoding="utf-8")
    loaded = pipeline._load_runspec(path)
    assert loaded["opponent_suite_id"] == "a" * 64
