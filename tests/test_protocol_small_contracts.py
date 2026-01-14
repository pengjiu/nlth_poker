from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.eventstream import EventStreamError, event_stream_digest_from_objects, read_ndjson
from poker2.protocol.paths import PathsError, resolved_paths_digest
from poker2.protocol.policy import PolicyError, baseline_policy_spec, policy_id, validate_policy_spec
from poker2.protocol.scenario import ScenarioError, scenario_id
from poker2.protocol.triad import TriadError, triad
from poker2.protocol.profile import ProfileError, auto_profile_spec_throughput, profile_id
from poker2.protocol.run_id import run_id_v1


def test_paths_digest_rejects_non_object() -> None:
    with pytest.raises(PathsError) as exc:
        resolved_paths_digest([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"


def test_policy_validation_errors() -> None:
    with pytest.raises(PolicyError) as exc:
        validate_policy_spec([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(PolicyError) as exc:
        validate_policy_spec({"policy_kind": "nope"}, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(PolicyError) as exc:
        validate_policy_spec(
            {
                "policy_kind": "baseline",
                "policy_deps": "not-a-list",
                "policy_params_digest": {"alg": "sha256", "hex": "0" * 64},
                "stochastic": False,
            },
            strict_mode=True,
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(PolicyError) as exc:
        validate_policy_spec(
            {
                "policy_kind": "baseline",
                "policy_deps": [],
                "policy_params_digest": {"alg": "sha256", "hex": "0" * 64},
                "stochastic": "no",
            },
            strict_mode=True,
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(PolicyError) as exc:
        validate_policy_spec(
            {
                "policy_kind": "baseline",
                "policy_deps": [],
                "policy_params_digest": {"alg": "sha256", "hex": "0" * 64},
                "stochastic": False,
                "policy_id": "0" * 64,
            },
            strict_mode=True,
        )
    assert exc.value.code == "ID_MISMATCH"


def test_baseline_policy_spec_is_hashable() -> None:
    spec = baseline_policy_spec(strict_mode=True)
    pid = policy_id(spec, strict_mode=True)
    assert isinstance(pid, str) and len(pid) == 64


def test_scenario_id_requires_fields() -> None:
    with pytest.raises(ScenarioError) as exc:
        scenario_id([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(ScenarioError) as exc:
        scenario_id({"scenario_schema_id": "scenario_spec_v1"}, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"


def test_triad_rejects_invalid_ids() -> None:
    with pytest.raises(TriadError) as exc:
        triad(action_bins_id="x", obs_schema_id="0" * 64, rake_id="0" * 64)
    assert exc.value.code == "ID_INVALID"


def test_profile_id_validation_errors() -> None:
    with pytest.raises(ProfileError) as exc:
        profile_id([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(ProfileError) as exc:
        profile_id({"profile_id": "0" * 64}, strict_mode=True)
    assert exc.value.code == "ID_MISMATCH"


@pytest.mark.parametrize("cpu_count,workers", [(1, 1), (4, 1), (8, 2), (16, 4), (32, 8)])
def test_auto_profile_spec_throughput_branches(monkeypatch: pytest.MonkeyPatch, cpu_count: int, workers: int) -> None:
    monkeypatch.setattr("poker2.protocol.profile.os.cpu_count", lambda: cpu_count)
    spec = auto_profile_spec_throughput()
    assert spec["concurrency"]["workers"] == workers


def test_eventstream_header_validation_errors(tmp_path: Path) -> None:
    header_missing = {
        "run_id": "0" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
    }
    with pytest.raises(EventStreamError) as exc:
        event_stream_digest_from_objects([header_missing], strict_mode=True)
    assert exc.value.code == "HEADER_MISSING_FIELDS"

    header_bad_digest = {
        "options_hash": "0" * 64,
        "seed": 0,
        "run_id": run_id_v1(options_hash="0" * 64, seed=0, strict_mode=True),
        "scenario_id": "0" * 64,
        "schema_hash": "0" * 64,
        "event_model_id": "0" * 64,
        "event_stream_digest": {"alg": "md5", "hex": "0" * 64},
        "provenance_ref": "artifact://prov",
        "resolved_paths_digest": "0" * 64,
        "repro_tier": "Tier-A",
    }
    with pytest.raises(EventStreamError) as exc:
        event_stream_digest_from_objects([header_bad_digest], strict_mode=True)
    assert exc.value.code == "HEADER_DIGEST_INVALID"

    header_bad_run_id_type = {
        "run_id": None,
        "options_hash": "0" * 64,
        "seed": 0,
        "scenario_id": "0" * 64,
        "schema_hash": "0" * 64,
        "event_model_id": "0" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
        "provenance_ref": "artifact://prov",
        "resolved_paths_digest": "0" * 64,
        "repro_tier": "Tier-A",
    }
    with pytest.raises(EventStreamError) as exc:
        event_stream_digest_from_objects([header_bad_run_id_type], strict_mode=True)
    assert exc.value.code == "HEADER_RUN_ID_INVALID"

    header_bad_run_id_hex = {
        "run_id": "not-a-digest",
        "options_hash": "0" * 64,
        "seed": 0,
        "scenario_id": "0" * 64,
        "schema_hash": "0" * 64,
        "event_model_id": "0" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
        "provenance_ref": "artifact://prov",
        "resolved_paths_digest": "0" * 64,
        "repro_tier": "Tier-A",
    }
    with pytest.raises(EventStreamError) as exc:
        event_stream_digest_from_objects([header_bad_run_id_hex], strict_mode=True)
    assert exc.value.code == "HEADER_RUN_ID_INVALID"

    header_bad_seed = {
        "run_id": run_id_v1(options_hash="0" * 64, seed=0, strict_mode=True),
        "options_hash": "0" * 64,
        "seed": True,
        "scenario_id": "0" * 64,
        "schema_hash": "0" * 64,
        "event_model_id": "0" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
        "provenance_ref": "artifact://prov",
        "resolved_paths_digest": "0" * 64,
        "repro_tier": "Tier-A",
    }
    with pytest.raises(EventStreamError) as exc:
        event_stream_digest_from_objects([header_bad_seed], strict_mode=True)
    assert exc.value.code == "HEADER_SEED_INVALID"


def test_run_id_v1_validation_errors() -> None:
    with pytest.raises(Exception) as exc:
        run_id_v1(options_hash="x", seed=0, strict_mode=True)
    assert "OPTIONS_HASH_INVALID" in str(exc.value)

    with pytest.raises(Exception) as exc:
        run_id_v1(options_hash="0" * 64, seed=True, strict_mode=True)
    assert "TYPE_ERROR" in str(exc.value)


def test_read_ndjson_allows_empty_lines_in_non_strict(tmp_path: Path) -> None:
    p = tmp_path / "s.ndjson"
    p.write_bytes(b"{\"a\":1}\n\n")
    objs = read_ndjson(p, strict_mode=False)
    assert objs == [{"a": 1}]


def test_read_ndjson_reports_json_parse_fail(tmp_path: Path) -> None:
    p = tmp_path / "s.ndjson"
    p.write_bytes(b"{not-json}\n")
    with pytest.raises(EventStreamError) as exc:
        read_ndjson(p, strict_mode=True)
    assert exc.value.code == "JSON_PARSE_FAIL"
