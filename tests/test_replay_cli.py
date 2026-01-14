from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.cli import replay
from poker2.contractkit import canonicalize_json_bytes
from poker2.environment import pokerkit_nlhe as env
from poker2.protocol.action_bins import action_bins_id
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.run_id import run_id_v1


def _ruleset() -> dict:
    return {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": None,
        "straddle": None,
        "rake": None,
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": False},
    }


def _write_ndjson(path: Path, objs: list[object]) -> None:
    lines = [canonicalize_json_bytes(o, strict_mode=True) for o in objs]
    path.write_bytes(b"\n".join(lines) + b"\n")


def _run_hand(*, seed: int = 123) -> list[dict]:
    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        if int(snap["to_call_chips"]) == 0:
            return {"kind": "CHECK", "target_total_commit_chips": int(snap["actor_commit_chips"])}
        return {
            "kind": "CALL",
            "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"]),
        }

    options_hash = "0" * 64
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
        seed=seed,
        scenario_id="1" * 64,
        schema_hash="2" * 64,
        provenance_ref="artifact://prov",
        resolved_paths_digest="3" * 64,
        repro_tier="Tier-A",
        ruleset=_ruleset(),
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


def _run_multi_hand(*, seed: int = 123, hands: int = 2) -> list[dict]:
    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        if int(snap["to_call_chips"]) == 0:
            return {"kind": "CHECK", "target_total_commit_chips": int(snap["actor_commit_chips"])}
        return {
            "kind": "CALL",
            "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"]),
        }

    options_hash = "0" * 64
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
    return env.run_multi_hand_eventstream_objects(
        run_id=run_id_v1(options_hash=options_hash, seed=seed, strict_mode=True),
        options_hash=options_hash,
        seed=seed,
        scenario_id="1" * 64,
        schema_hash="2" * 64,
        provenance_ref="artifact://prov",
        resolved_paths_digest="3" * 64,
        repro_tier="Tier-A",
        ruleset=_ruleset(),
        triad={"action_bins_id": bins_id, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
        action_adapter=action_adapter,
        action_bins=action_bins,
        mapping_spec_id=None,
        mw_ladder_id=None,
        starting_stacks_by_seat={1: 50, 2: 50},
        button_seat=1,
        hands=hands,
        policy=policy,
        strict_mode=True,
    )


def test_replay_cli_passes_and_returns_events(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand()
    path = tmp_path / "hand.ndjson"
    _write_ndjson(path, objs)

    rc = replay.main(["--eventstream", str(path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["event_stream_ref"].startswith("path:")
    assert out["hand_selector"]["hand_id"]
    assert out["events"]


def test_replay_cli_focus_requires_both_decision_and_state_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    objs = _run_hand()
    path = tmp_path / "hand.ndjson"
    _write_ndjson(path, objs)

    dp = next(o for o in objs if o.get("event") == "DecisionPoint")
    rc = replay.main(["--eventstream", str(path), "--decision-id", str(int(dp["decision_id"]))])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "SELECTOR_INCOMPLETE"


def test_replay_cli_focus_finds_matching_decision(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand()
    path = tmp_path / "hand.ndjson"
    _write_ndjson(path, objs)

    dp = next(o for o in objs if o.get("event") == "DecisionPoint")
    rc = replay.main(
        [
            "--eventstream",
            str(path),
            "--decision-id",
            str(int(dp["decision_id"])),
            "--state-hash",
            str(dp["state_hash"]),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["focus"]["decision_point"]["decision_id"] == int(dp["decision_id"])
    assert out["focus"]["decision_point"]["state_hash"] == dp["state_hash"]


def test_replay_cli_detects_digest_mismatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand()
    path = tmp_path / "hand.ndjson"
    _write_ndjson(path, objs)

    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["event_stream_digest"]["hex"] = "0" * 64
    mutated = [header, *[json.loads(line) for line in lines[1:]]]
    _write_ndjson(path, mutated)

    rc = replay.main(["--eventstream", str(path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "EVENT_STREAM_DIGEST_MISMATCH"


def test_replay_cli_rejects_hand_id_mismatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_hand()
    path = tmp_path / "hand.ndjson"
    _write_ndjson(path, objs)

    rc = replay.main(["--eventstream", str(path), "--hand-id", "wrong-hand-id"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "HAND_ID_MISMATCH"


def test_replay_cli_supports_multi_hand_selection(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    objs = _run_multi_hand(hands=3)
    path = tmp_path / "multi.ndjson"
    _write_ndjson(path, objs)

    starts = [o for o in objs if o.get("event") == "HandStart"]
    assert len(starts) == 3
    second_hand_id = starts[1]["hand_id"]
    assert isinstance(second_hand_id, str)

    rc = replay.main(["--eventstream", str(path), "--hand-id", second_hand_id])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["hand_selector"]["hand_id"] == second_hand_id
    assert out["events"][1]["payload"]["event"] == "HandStart"
    assert out["events"][1]["payload"]["hand_id"] == second_hand_id


def test_replay_cli_reports_eventstream_error_on_crlf(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.ndjson"
    path.write_bytes(b"{}\r\n")

    rc = replay.main(["--eventstream", str(path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["check_id"] == "Events.EventStreamArtifact"
    assert out["error"]["code"] == "CRLF_NOT_ALLOWED"


def test_replay_cli_reports_event_not_object(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    records: list[object] = [*(_run_hand())]
    records[2] = []

    header = records[0]
    assert isinstance(header, dict)
    header["event_stream_digest"]["hex"] = event_stream_digest_from_objects(records, strict_mode=True)

    path = tmp_path / "bad_event.ndjson"
    _write_ndjson(path, records)

    rc = replay.main(["--eventstream", str(path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "EVENT_NOT_OBJECT"


def test_replay_cli_reports_no_hands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    header = {
        "run_id": run_id_v1(options_hash="0" * 64, seed=0, strict_mode=True),
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
    objs: list[object] = [header, {"event": "PotUpdate", "pot_chips_delta": 0, "rake_chips_delta": 0}]
    header["event_stream_digest"]["hex"] = event_stream_digest_from_objects(objs, strict_mode=True)

    path = tmp_path / "no_hands.ndjson"
    _write_ndjson(path, objs)

    rc = replay.main(["--eventstream", str(path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "NO_HANDS"

