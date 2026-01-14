from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.contractkit import canonicalize_json_bytes
from poker2.environment import pokerkit_nlhe as env
from poker2.evaluation.fixtures.pack import validate_pack
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.action_bins import action_bins_id
from poker2.protocol.run_id import run_id_v1
from poker2.cli import fixtures


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


def _write_minimal_eventstream(
    path: Path,
    *,
    options_hash: object,
    provenance_ref: object,
    ruleset_id: str | None,
) -> None:
    header_options_hash = "0" * 64
    seed = 0
    header: dict = {
        "run_id": run_id_v1(options_hash=header_options_hash, seed=seed, strict_mode=True),
        "options_hash": options_hash,
        "seed": seed,
        "scenario_id": "0" * 64,
        "schema_hash": "0" * 64,
        "event_model_id": "0" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
        "provenance_ref": provenance_ref,
        "resolved_paths_digest": "0" * 64,
        "repro_tier": "Tier-A",
    }
    events: list[object] = []
    if ruleset_id is not None:
        events.append({"event": "HandStart", "ruleset_id": ruleset_id})
    events.append({"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0})

    digest_hex = event_stream_digest_from_objects([header, *events], strict_mode=True)
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(path, [header, *events])


def _run_hand(*, seed: int = 1) -> list[dict]:
    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        if int(snap["to_call_chips"]) == 0:
            return {"kind": "CHECK", "target_total_commit_chips": int(snap["actor_commit_chips"])}
        return {"kind": "CALL", "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"])}

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


def test_fixtures_tool_build_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, _run_hand())

    pack_path = tmp_path / "pack.json"
    rc = fixtures.main(
        [
            "build-pack",
            "--out",
            str(pack_path),
            "--platform",
            "internal",
            "--ruleset-label",
            "internal_ruleset_v1",
            "--checked-item",
            "rake",
            "--checked-item",
            "allin_reopen",
            "--eventstream",
            str(es_path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["fixtures_count"] == 1
    assert pack_path.exists()
    validate_pack(
        pack_path,
        strict_mode=True,
        require_non_empty=True,
        required_checked_items=["rake", "allin_reopen"],
    )


def test_fixtures_tool_build_pack_fails_when_eventstream_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pack_path = tmp_path / "pack.json"
    missing = tmp_path / "nope.ndjson"

    rc = fixtures.main(
        [
            "build-pack",
            "--out",
            str(pack_path),
            "--platform",
            "internal",
            "--ruleset-label",
            "internal_ruleset_v1",
            "--eventstream",
            str(missing),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "EVENTSTREAM_MISSING"


def test_fixtures_tool_build_pack_reports_empty_eventstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, _run_hand())

    monkeypatch.setattr(fixtures, "read_ndjson", lambda *_a, **_k: [])

    pack_path = tmp_path / "pack.json"
    rc = fixtures.main(
        [
            "build-pack",
            "--out",
            str(pack_path),
            "--platform",
            "internal",
            "--ruleset-label",
            "internal_ruleset_v1",
            "--eventstream",
            str(es_path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "EMPTY_EVENTSTREAM"


def test_fixtures_tool_build_pack_reports_header_not_object(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, [[], {"event": "HandEnd"}])

    pack_path = tmp_path / "pack.json"
    rc = fixtures.main(
        [
            "build-pack",
            "--out",
            str(pack_path),
            "--platform",
            "internal",
            "--ruleset-label",
            "internal_ruleset_v1",
            "--eventstream",
            str(es_path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "HEADER_NOT_OBJECT"


def test_fixtures_tool_build_pack_reports_missing_ruleset_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    es_path = tmp_path / "hand.ndjson"
    _write_minimal_eventstream(es_path, options_hash="0" * 64, provenance_ref="artifact://prov", ruleset_id=None)

    pack_path = tmp_path / "pack.json"
    rc = fixtures.main(
        [
            "build-pack",
            "--out",
            str(pack_path),
            "--platform",
            "internal",
            "--ruleset-label",
            "internal_ruleset_v1",
            "--eventstream",
            str(es_path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "MISSING_FIELDS"
    assert "ruleset_id" in out["error"]["message"]


def test_fixtures_tool_build_pack_reports_missing_options_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    es_path = tmp_path / "hand.ndjson"
    _write_minimal_eventstream(es_path, options_hash=None, provenance_ref="artifact://prov", ruleset_id="0" * 64)

    pack_path = tmp_path / "pack.json"
    rc = fixtures.main(
        [
            "build-pack",
            "--out",
            str(pack_path),
            "--platform",
            "internal",
            "--ruleset-label",
            "internal_ruleset_v1",
            "--eventstream",
            str(es_path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "MISSING_FIELDS"
    assert "options_hash" in out["error"]["message"]


def test_fixtures_tool_build_pack_reports_missing_provenance_ref(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    es_path = tmp_path / "hand.ndjson"
    _write_minimal_eventstream(es_path, options_hash="0" * 64, provenance_ref=None, ruleset_id="0" * 64)

    pack_path = tmp_path / "pack.json"
    rc = fixtures.main(
        [
            "build-pack",
            "--out",
            str(pack_path),
            "--platform",
            "internal",
            "--ruleset-label",
            "internal_ruleset_v1",
            "--eventstream",
            str(es_path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "MISSING_FIELDS"
    assert "provenance_ref" in out["error"]["message"]


def test_fixtures_tool_build_pack_reports_ruleset_id_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    es1 = tmp_path / "h1.ndjson"
    es2 = tmp_path / "h2.ndjson"
    _write_minimal_eventstream(es1, options_hash="0" * 64, provenance_ref="artifact://prov", ruleset_id="0" * 64)
    _write_minimal_eventstream(es2, options_hash="0" * 64, provenance_ref="artifact://prov", ruleset_id="1" * 64)

    pack_path = tmp_path / "pack.json"
    rc = fixtures.main(
        [
            "build-pack",
            "--out",
            str(pack_path),
            "--platform",
            "internal",
            "--ruleset-label",
            "internal_ruleset_v1",
            "--eventstream",
            str(es1),
            "--eventstream",
            str(es2),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "RULESET_ID_MISMATCH"


def test_fixtures_tool_build_pack_supports_non_strict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    es_path = tmp_path / "hand.ndjson"
    _write_ndjson(es_path, _run_hand())

    pack_path = tmp_path / "pack.json"
    rc = fixtures.main(
        [
            "build-pack",
            "--no-strict",
            "--out",
            str(pack_path),
            "--platform",
            "internal",
            "--ruleset-label",
            "internal_ruleset_v1",
            "--eventstream",
            str(es_path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["degraded"] is False
