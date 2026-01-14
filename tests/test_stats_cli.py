from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.cli import stats
from poker2.contractkit import canonicalize_json_bytes
from poker2.environment import pokerkit_nlhe as env
from poker2.protocol.action_bins import action_bins_id
from poker2.protocol.eventstream import event_stream_digest_from_file, read_ndjson
from poker2.protocol.run_id import run_id_v1


def _ruleset(*, reopen: bool) -> dict:
    return {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": None,
        "straddle": None,
        "rake": None,
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": reopen},
    }


def _write_ndjson(path: Path, objs: list[dict]) -> None:
    lines = [canonicalize_json_bytes(o, strict_mode=True) for o in objs]
    path.write_bytes(b"\n".join(lines) + b"\n")


def _run_hand(*, reopen: bool) -> list[dict]:
    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        if int(snap["to_call_chips"]) == 0:
            return {"kind": "CHECK", "target_total_commit_chips": int(snap["actor_commit_chips"])}
        return {"kind": "CALL", "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"])}

    options_hash = "0" * 64
    seed = 123
    action_bins = {
        "action_bins_schema_id": "action_bins_spec_v1",
        "include_min_raise_to": True,
        "include_max_raise_to": True,
        "include_extra_raise_to": True,
    }
    bins_id = action_bins_id(action_bins, strict_mode=True)
    action_adapter = {
        "action_adapter_schema_id": "action_adapter_spec_v1",
        "rounding_mode": None,
        "fallback_policy": {"mode": "fail_fast"},
    }
    return env.run_single_hand_eventstream_objects(
        run_id=run_id_v1(options_hash=options_hash, seed=seed, strict_mode=True),
        options_hash=options_hash,
        seed=123,
        scenario_id="1" * 64,
        schema_hash="2" * 64,
        provenance_ref="artifact://prov",
        resolved_paths_digest="3" * 64,
        repro_tier="Tier-A",
        ruleset=_ruleset(reopen=reopen),
        triad={"action_bins_id": bins_id, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
        action_adapter=action_adapter,
        action_bins=action_bins,
        mapping_spec_id=None,
        mw_ladder_id=None,
        starting_stacks_by_seat={1: 50, 2: 50},
        button_seat=1,
        hand_seq=1,
        policy=policy,
        strict_mode=True,
    )


def test_stats_cli_passes_for_valid_hand(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)

    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text(json.dumps(_ruleset(reopen=False)), encoding="utf-8")

    rc = stats.main(["eventstream", "--eventstream", str(es_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["status"] == "pass"
    assert len(out["metric_spec_id"]) == 64
    assert len(out["report_schema_id"]) == 64
    assert out["event_stream_ref"].startswith("path:")
    assert out["rule_conformance"]["failures_count"] == 0


def test_stats_cli_rejects_ruleset_id_mismatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)

    mismatched_ruleset_path = tmp_path / "ruleset.json"
    mismatched_ruleset_path.write_text(json.dumps(_ruleset(reopen=True)), encoding="utf-8")

    rc = stats.main(
        ["eventstream", "--eventstream", str(es_path), "--ruleset", str(mismatched_ruleset_path), "--strict"]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "RULESET_ID_MISMATCH"


def test_stats_fixtures_pack_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)

    header = read_ndjson(es_path, strict_mode=True)[0]
    assert isinstance(header, dict)
    hand_start = next(o for o in objs if o.get("event") == "HandStart")

    pack_path = tmp_path / "pack.json"
    pack_obj = {
        "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
        "platform": "test",
        "ruleset_id": hand_start["ruleset_id"],
        "ruleset_label": "test_ruleset_v1",
        "checked_items_covered": ["rake"],
        "fixtures": [
            {
                "event_stream_ref": f"path:{es_path}",
                "event_stream_digest": {"alg": "sha256", "hex": event_stream_digest_from_file(es_path, strict_mode=True)},
                "ruleset_id": hand_start["ruleset_id"],
                "options_hash": header["options_hash"],
                "provenance_ref": header["provenance_ref"],
            }
        ],
    }
    pack_path.write_text(json.dumps(pack_obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text(json.dumps(_ruleset(reopen=False)), encoding="utf-8")

    rc = stats.main(["fixtures-pack", "--pack", str(pack_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["failures_count"] == 0


def test_stats_cli_reports_missing_eventstream(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text(json.dumps(_ruleset(reopen=False)), encoding="utf-8")

    missing = tmp_path / "nope.ndjson"
    rc = stats.main(["eventstream", "--eventstream", str(missing), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "EVENTSTREAM_MISSING"


def test_stats_cli_supports_hrc_settings_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "handdata": {"blinds": [2, 1, 0], "anteType": "OFF", "straddleType": "OFF"},
                "eqmodel": {"raked": False},
            }
        ),
        encoding="utf-8",
    )

    rc = stats.main(
        ["eventstream", "--eventstream", str(es_path), "--hrc-settings", str(settings_path), "--no-reopen-on-short-allin"]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"


def test_stats_fixtures_pack_reports_invalid_pack(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": "0" * 64,
                "ruleset_label": None,
                "fixtures": [1],
            }
        ),
        encoding="utf-8",
    )

    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text(json.dumps(_ruleset(reopen=False)), encoding="utf-8")

    rc = stats.main(["fixtures-pack", "--pack", str(pack_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "PACK_INVALID"


def test_stats_cli_reports_ruleset_unreadable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)

    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text("{", encoding="utf-8")

    rc = stats.main(["eventstream", "--eventstream", str(es_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "RULESET_UNREADABLE"


def test_stats_cli_reports_ruleset_not_object(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)

    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    rc = stats.main(["eventstream", "--eventstream", str(es_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "RULESET_NOT_OBJECT"


def test_stats_fixtures_pack_reports_missing_pack(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text(json.dumps(_ruleset(reopen=False)), encoding="utf-8")

    missing = tmp_path / "missing_pack.json"
    rc = stats.main(["fixtures-pack", "--pack", str(missing), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "PACK_MISSING"


def test_stats_fixtures_pack_reports_checked_items_type_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)
    header = read_ndjson(es_path, strict_mode=True)[0]
    assert isinstance(header, dict)
    hand_start = next(o for o in objs if o.get("event") == "HandStart")

    pack_path = tmp_path / "pack.json"
    pack_obj = {
        "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
        "platform": "test",
        "ruleset_id": hand_start["ruleset_id"],
        "ruleset_label": "test_ruleset_v1",
        "checked_items_covered": 123,
        "fixtures": [
            {
                "event_stream_ref": f"path:{es_path}",
                "event_stream_digest": {"alg": "sha256", "hex": event_stream_digest_from_file(es_path, strict_mode=True)},
                "ruleset_id": hand_start["ruleset_id"],
                "options_hash": header["options_hash"],
                "provenance_ref": header["provenance_ref"],
            }
        ],
    }
    pack_path.write_text(json.dumps(pack_obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text(json.dumps(_ruleset(reopen=False)), encoding="utf-8")

    rc = stats.main(["fixtures-pack", "--pack", str(pack_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "PACK_INVALID"


def test_stats_fixtures_pack_records_rule_conformance_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)
    header = read_ndjson(es_path, strict_mode=True)[0]
    assert isinstance(header, dict)
    hand_start = next(o for o in objs if o.get("event") == "HandStart")

    pack_path = tmp_path / "pack.json"
    pack_obj = {
        "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
        "platform": "test",
        "ruleset_id": hand_start["ruleset_id"],
        "ruleset_label": "test_ruleset_v1",
        "checked_items_covered": ["rake"],
        "fixtures": [
            {
                "event_stream_ref": f"path:{es_path}",
                "event_stream_digest": {"alg": "sha256", "hex": event_stream_digest_from_file(es_path, strict_mode=True)},
                "ruleset_id": hand_start["ruleset_id"],
                "options_hash": header["options_hash"],
                "provenance_ref": header["provenance_ref"],
            }
        ],
    }
    pack_path.write_text(json.dumps(pack_obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    mismatched_ruleset_path = tmp_path / "ruleset.json"
    mismatched_ruleset_path.write_text(json.dumps(_ruleset(reopen=True)), encoding="utf-8")

    rc = stats.main(["fixtures-pack", "--pack", str(pack_path), "--ruleset", str(mismatched_ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"
    assert out["failures_count"] == 1
    assert out["failures"][0]["reason"] == "rule_conformance_error"


def test_stats_fixtures_pack_records_rule_conformance_failed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Create an eventstream that will fail a rake check while still passing pack validation.
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)
    header = read_ndjson(es_path, strict_mode=True)[0]
    assert isinstance(header, dict)
    hand_start = next(o for o in objs if o.get("event") == "HandStart")

    records = [json.loads(line) for line in es_path.read_text(encoding="utf-8").splitlines()]
    mutated = records
    hand_end = next(o for o in mutated if isinstance(o, dict) and o.get("event") == "HandEnd")
    hand_end["total_rake_chips"] = int(hand_end.get("total_rake_chips", 0)) + 1
    _write_ndjson(es_path, mutated)
    mutated[0]["event_stream_digest"]["hex"] = event_stream_digest_from_file(es_path, strict_mode=True)
    _write_ndjson(es_path, mutated)

    pack_path = tmp_path / "pack.json"
    pack_obj = {
        "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
        "platform": "test",
        "ruleset_id": hand_start["ruleset_id"],
        "ruleset_label": "test_ruleset_v1",
        "checked_items_covered": ["rake"],
        "fixtures": [
            {
                "event_stream_ref": f"path:{es_path}",
                "event_stream_digest": {"alg": "sha256", "hex": event_stream_digest_from_file(es_path, strict_mode=True)},
                "ruleset_id": hand_start["ruleset_id"],
                "options_hash": header["options_hash"],
                "provenance_ref": header["provenance_ref"],
            }
        ],
    }
    pack_path.write_text(json.dumps(pack_obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text(
        json.dumps(
            {
                "game_kind": "NLHE",
                "blinds": {"sb_chips": 1, "bb_chips": 2},
                "ante": None,
                "straddle": None,
                "rake": None,
                "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": False},
            }
        ),
        encoding="utf-8",
    )

    rc = stats.main(["fixtures-pack", "--pack", str(pack_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["failures"][0]["reason"] == "rule_conformance_failed"


def test_stats_fixtures_pack_fails_when_coverage_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand(reopen=False)
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, objs)
    header = read_ndjson(es_path, strict_mode=True)[0]
    assert isinstance(header, dict)
    hand_start = next(o for o in objs if o.get("event") == "HandStart")

    pack_path = tmp_path / "pack.json"
    pack_obj = {
        "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
        "platform": "test",
        "ruleset_id": hand_start["ruleset_id"],
        "ruleset_label": "test_ruleset_v1",
        "checked_items_covered": ["button_rotation"],
        "fixtures": [
            {
                "event_stream_ref": f"path:{es_path}",
                "event_stream_digest": {"alg": "sha256", "hex": event_stream_digest_from_file(es_path, strict_mode=True)},
                "ruleset_id": hand_start["ruleset_id"],
                "options_hash": header["options_hash"],
                "provenance_ref": header["provenance_ref"],
            }
        ],
    }
    pack_path.write_text(json.dumps(pack_obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    ruleset_path = tmp_path / "ruleset.json"
    ruleset_path.write_text(json.dumps(_ruleset(reopen=False)), encoding="utf-8")

    rc = stats.main(["fixtures-pack", "--pack", str(pack_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"
    assert out["failures"][0]["reason"] == "checked_items_covered_missing"
