from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.gates.cache_gate import check_cache_entry_provenance_gate
from poker2.protocol.cache_key import CacheKeyError, cache_key_id, cache_key_v1, validate_cache_key
from poker2.protocol.eventstream import read_ndjson


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_cache_key_v1_is_hashable_and_valid() -> None:
    ck = cache_key_v1(
        state_hash="0" * 64,
        scenario_id="1" * 64,
        schema_hash="2" * 64,
        engine_build_id=None,
        options_hash="3" * 64,
        strict_mode=True,
    )
    validate_cache_key(ck, strict_mode=True)
    cid = cache_key_id(ck, strict_mode=True)
    assert isinstance(cid, str) and len(cid) == 64


def test_cache_key_validation_errors() -> None:
    with pytest.raises(CacheKeyError) as exc:
        validate_cache_key(None, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(CacheKeyError) as exc:
        validate_cache_key({"state_hash": "0" * 64}, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    with pytest.raises(CacheKeyError) as exc:
        validate_cache_key(
            {
                "state_hash": "0" * 64,
                "scenario_id": "0" * 64,
                "schema_hash": "0" * 64,
                "engine_build_id": None,
                "options_hash": "0" * 64,
                "extra": 1,
            },
            strict_mode=True,
        )
    assert exc.value.code == "EXTRA_FIELDS"

    with pytest.raises(CacheKeyError) as exc:
        validate_cache_key(
            {
                "state_hash": "0" * 64,
                "scenario_id": "0" * 64,
                "schema_hash": "0" * 64,
                "engine_build_id": 123,
                "options_hash": "0" * 64,
            },
            strict_mode=True,
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(CacheKeyError) as exc:
        validate_cache_key(
            {
                "state_hash": "0" * 64,
                "scenario_id": "0" * 64,
                "schema_hash": "0" * 64,
                "engine_build_id": "not_sha256",
                "options_hash": "0" * 64,
            },
            strict_mode=True,
        )
    assert exc.value.code == "ID_INVALID"


def test_cache_entry_provenance_gate_passes_for_internal_fixture() -> None:
    repo = _repo_root()
    es_path = repo / "fixtures" / "internal" / "eventstreams" / "internal_v1_button_rotation_3hands.ndjson"
    objs = read_ndjson(es_path, strict_mode=True)
    header = objs[0]
    events = [e for e in objs[1:] if isinstance(e, dict)]
    hs = next(e for e in events if e.get("event") == "HandStart")

    failures = check_cache_entry_provenance_gate(
        header=header,
        cached_provenance_ref=header.get("provenance_ref") if isinstance(header.get("provenance_ref"), str) else None,
        expected_ruleset_id=hs["ruleset_id"],
        expected_triad=hs["triad"],
        expected_schema_hash=header["schema_hash"],
        expected_options_hash=header["options_hash"],
        event_stream_ref=f"path:{es_path}",
        event_stream_digest=header.get("event_stream_digest") if isinstance(header.get("event_stream_digest"), dict) else None,
        strict_mode=True,
    )
    assert failures == []


def test_cache_entry_provenance_gate_fails_on_options_hash_mismatch() -> None:
    repo = _repo_root()
    es_path = repo / "fixtures" / "internal" / "eventstreams" / "internal_v1_button_rotation_3hands.ndjson"
    objs = read_ndjson(es_path, strict_mode=True)
    header = objs[0]
    events = [e for e in objs[1:] if isinstance(e, dict)]
    hs = next(e for e in events if e.get("event") == "HandStart")

    failures = check_cache_entry_provenance_gate(
        header=header,
        cached_provenance_ref=header["provenance_ref"],
        expected_ruleset_id=hs["ruleset_id"],
        expected_triad=hs["triad"],
        expected_schema_hash=header["schema_hash"],
        expected_options_hash="0" * 64,
        event_stream_ref=f"path:{es_path}",
        event_stream_digest=header["event_stream_digest"],
        strict_mode=True,
    )
    assert failures and failures[0]["gate_id"] == "Gates.CacheCorrectness"
    assert failures[0]["reason"] == "provenance_mismatch"
    assert failures[0]["details"]["mismatches"]["options_hash"]["expected"] == "0" * 64


def test_cache_entry_provenance_gate_reports_missing_provenance_ref() -> None:
    header = json.loads(
        json.dumps(
            {
                "run_id": "0" * 64,
                "options_hash": "0" * 64,
                "seed": 0,
                "scenario_id": "0" * 64,
                "schema_hash": "0" * 64,
            }
        )
    )
    failures = check_cache_entry_provenance_gate(
        header=header,
        cached_provenance_ref=None,
        expected_ruleset_id="0" * 64,
        expected_triad={"action_bins_id": "0" * 64, "obs_schema_id": "0" * 64, "rake_id": "0" * 64},
        expected_schema_hash="0" * 64,
        expected_options_hash="0" * 64,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_ref_missing"


def test_cache_entry_provenance_gate_reports_unresolvable_provenance_ref() -> None:
    header = {"run_id": "0" * 64, "options_hash": "0" * 64, "seed": 0, "scenario_id": "0" * 64, "schema_hash": "0" * 64}
    failures = check_cache_entry_provenance_gate(
        header=header,
        cached_provenance_ref=f"artifact://{'1' * 64}",
        expected_ruleset_id="0" * 64,
        expected_triad={"action_bins_id": "0" * 64, "obs_schema_id": "0" * 64, "rake_id": "0" * 64},
        expected_schema_hash="0" * 64,
        expected_options_hash="0" * 64,
        event_stream_ref=None,
        event_stream_digest=None,
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_ref_unresolvable"


def test_cache_entry_provenance_gate_reports_unreadable_provenance(tmp_path: Path) -> None:
    artifact_id = "a" * 64
    (tmp_path / f"{artifact_id}.json").write_text("{", encoding="utf-8")

    header = {"run_id": "0" * 64, "options_hash": "0" * 64, "seed": 0, "scenario_id": "0" * 64, "schema_hash": "0" * 64}
    failures = check_cache_entry_provenance_gate(
        header=header,
        cached_provenance_ref=f"artifact://{artifact_id}",
        expected_ruleset_id="0" * 64,
        expected_triad={"action_bins_id": "0" * 64, "obs_schema_id": "0" * 64, "rake_id": "0" * 64},
        expected_schema_hash="0" * 64,
        expected_options_hash="0" * 64,
        event_stream_ref=None,
        event_stream_digest=None,
        provenance_search_roots=[tmp_path],
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_unreadable"


def test_cache_entry_provenance_gate_reports_invalid_provenance(tmp_path: Path) -> None:
    artifact_id = "b" * 64
    (tmp_path / f"{artifact_id}.json").write_text("{}", encoding="utf-8")

    header = {"run_id": "0" * 64, "options_hash": "0" * 64, "seed": 0, "scenario_id": "0" * 64, "schema_hash": "0" * 64}
    failures = check_cache_entry_provenance_gate(
        header=header,
        cached_provenance_ref=f"artifact://{artifact_id}",
        expected_ruleset_id="0" * 64,
        expected_triad={"action_bins_id": "0" * 64, "obs_schema_id": "0" * 64, "rake_id": "0" * 64},
        expected_schema_hash="0" * 64,
        expected_options_hash="0" * 64,
        event_stream_ref=None,
        event_stream_digest=None,
        provenance_search_roots=[tmp_path],
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_invalid"


def test_cache_entry_provenance_gate_reports_provenance_id_mismatch(tmp_path: Path) -> None:
    repo = _repo_root()
    src = repo / "fixtures" / "internal" / "artifacts" / "fecbde8e24dd44d2db7eef897f936ee1907880a522744a5b8f2a37c9a4dc76d3.json"
    prov_obj = json.loads(src.read_text(encoding="utf-8"))
    prov_obj["python_version"] = "3.11.99"

    artifact_id = "c" * 64
    (tmp_path / f"{artifact_id}.json").write_text(json.dumps(prov_obj, ensure_ascii=False), encoding="utf-8")

    header = {"run_id": "0" * 64, "options_hash": prov_obj["options_hash"], "seed": prov_obj["seed"], "scenario_id": "0" * 64, "schema_hash": prov_obj["schema_hash"]}
    failures = check_cache_entry_provenance_gate(
        header=header,
        cached_provenance_ref=f"artifact://{artifact_id}",
        expected_ruleset_id=prov_obj["ruleset_id"],
        expected_triad=prov_obj["triad"],
        expected_schema_hash=prov_obj["schema_hash"],
        expected_options_hash=prov_obj["options_hash"],
        event_stream_ref=None,
        event_stream_digest=None,
        provenance_search_roots=[tmp_path],
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_id_mismatch"


def test_cache_entry_provenance_gate_fails_on_ruleset_triad_schema_mismatch() -> None:
    repo = _repo_root()
    es_path = repo / "fixtures" / "internal" / "eventstreams" / "internal_v1_button_rotation_3hands.ndjson"
    objs = read_ndjson(es_path, strict_mode=True)
    header = objs[0]
    events = [e for e in objs[1:] if isinstance(e, dict)]
    hs = next(e for e in events if e.get("event") == "HandStart")

    bad_triad = dict(hs["triad"])
    bad_triad["rake_id"] = "0" * 64

    failures = check_cache_entry_provenance_gate(
        header=header,
        cached_provenance_ref=header["provenance_ref"],
        expected_ruleset_id="0" * 64,
        expected_triad=bad_triad,
        expected_schema_hash="0" * 64,
        expected_options_hash=header["options_hash"],
        event_stream_ref=f"path:{es_path}",
        event_stream_digest=header["event_stream_digest"],
        strict_mode=True,
    )
    assert failures and failures[0]["reason"] == "provenance_mismatch"
    mismatches = failures[0]["details"]["mismatches"]
    assert "ruleset_id" in mismatches
    assert "triad" in mismatches
    assert "schema_hash" in mismatches
