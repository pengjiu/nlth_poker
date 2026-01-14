from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.contractkit import canonicalize_json_bytes
from poker2.evaluation import rule_conformance as rc
from poker2.evaluation.rule_conformance import RuleConformanceError, rule_conformance_report_from_eventstream
from poker2.environment import pokerkit_nlhe as env
from poker2.protocol.action_bins import action_bins_id
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.run_id import run_id_v1
from poker2.protocol.ruleset import ruleset_id


OPTIONS_HASH = "0" * 64
ACTION_BINS = {
    "action_bins_schema_id": "action_bins_spec_v1",
    "include_min_raise_to": True,
    "include_max_raise_to": True,
    "include_extra_raise_to": True,
}
ACTION_BINS_ID = action_bins_id(ACTION_BINS, strict_mode=True)
ACTION_ADAPTER_FAIL_FAST = {
    "action_adapter_schema_id": "action_adapter_spec_v1",
    "rounding_mode": None,
    "fallback_policy": {"mode": "fail_fast"},
}


def _run_id(*, seed: int) -> str:
    return run_id_v1(options_hash=OPTIONS_HASH, seed=seed, strict_mode=True)


def _write_ndjson(path: Path, objs: list[object]) -> None:
    lines = [canonicalize_json_bytes(o, strict_mode=True) for o in objs]
    path.write_bytes(b"\n".join(lines) + b"\n")


def _header(*, digest_hex: str) -> dict:
    seed = 0
    return {
        "run_id": _run_id(seed=seed),
        "options_hash": OPTIONS_HASH,
        "seed": seed,
        "scenario_id": "1" * 64,
        "schema_hash": "2" * 64,
        "event_model_id": "3" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": digest_hex},
        "provenance_ref": "artifact://prov",
        "resolved_paths_digest": "4" * 64,
        "repro_tier": "Tier-A",
    }


def _write_eventstream(path: Path, events: list[object]) -> str:
    header = _header(digest_hex="0" * 64)
    digest_hex = event_stream_digest_from_objects([header, *events], strict_mode=True)
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(path, [header, *events])
    return digest_hex


def _ruleset(*, rake: dict | None = None, reopen: bool = False) -> dict:
    return {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": None,
        "straddle": None,
        "rake": rake,
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": reopen},
    }


def test_rule_conformance_rejects_unknown_checked_item(tmp_path: Path) -> None:
    objs = env.run_single_hand_eventstream_objects(
        run_id=_run_id(seed=1),
        options_hash=OPTIONS_HASH,
        seed=1,
        scenario_id="1" * 64,
        schema_hash="2" * 64,
        provenance_ref="artifact://prov",
        resolved_paths_digest="3" * 64,
        repro_tier="Tier-A",
        ruleset=_ruleset(),
        triad={"action_bins_id": ACTION_BINS_ID, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
        action_adapter=ACTION_ADAPTER_FAIL_FAST,
        action_bins=ACTION_BINS,
        mapping_spec_id=None,
        mw_ladder_id=None,
        starting_stacks_by_seat={1: 10, 2: 10},
        button_seat=1,
        hand_seq=1,
        policy=lambda ctx: {"kind": "FOLD", "target_total_commit_chips": int(ctx["snapshot"]["actor_commit_chips"])},
        strict_mode=True,
    )
    path = tmp_path / "hand.ndjson"
    _write_ndjson(path, objs)

    with pytest.raises(RuleConformanceError) as exc:
        rule_conformance_report_from_eventstream(
            path,
            event_stream_ref=f"path:{path}",
            ruleset=_ruleset(),
            checked_items=["not-a-real-item"],
            strict_mode=True,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"


def test_rule_conformance_detects_ledger_delta_mismatch(tmp_path: Path) -> None:
    objs = env.run_single_hand_eventstream_objects(
        run_id=_run_id(seed=2),
        options_hash=OPTIONS_HASH,
        seed=2,
        scenario_id="1" * 64,
        schema_hash="2" * 64,
        provenance_ref="artifact://prov",
        resolved_paths_digest="3" * 64,
        repro_tier="Tier-A",
        ruleset=_ruleset(),
        triad={"action_bins_id": ACTION_BINS_ID, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
        action_adapter=ACTION_ADAPTER_FAIL_FAST,
        action_bins=ACTION_BINS,
        mapping_spec_id=None,
        mw_ladder_id=None,
        starting_stacks_by_seat={1: 10, 2: 10},
        button_seat=1,
        hand_seq=1,
        policy=lambda ctx: {"kind": "FOLD", "target_total_commit_chips": int(ctx["snapshot"]["actor_commit_chips"])},
        strict_mode=True,
    )

    # Mutate stack_deltas_by_seat and re-digest.
    header = dict(objs[0])
    events = [dict(o) for o in objs[1:]]
    hand_end = next(e for e in events if e.get("event") == "HandEnd")
    deltas = dict(hand_end["stack_deltas_by_seat"])
    first_seat = next(iter(deltas.keys()))
    deltas[first_seat] = int(deltas[first_seat]) + 1
    hand_end["stack_deltas_by_seat"] = deltas
    header["event_stream_digest"] = {"alg": "sha256", "hex": "0" * 64}
    header["event_stream_digest"]["hex"] = event_stream_digest_from_objects([header, *events], strict_mode=True)

    path = tmp_path / "mutated.ndjson"
    _write_ndjson(path, [header, *events])

    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=_ruleset(),
        checked_items=["ledger_conservation"],
        strict_mode=True,
    )
    assert rep["failures_count"] >= 1
    assert rep["failures"][0]["item"] == "ledger_conservation"
    assert rep["failures"][0]["decision_id_or_state_hash"] == {"decision_id": None, "state_hash": None}


def test_rule_conformance_detects_button_rotation_failure(tmp_path: Path) -> None:
    ruleset = _ruleset()
    # Two-hand stream, with wrong button rotation in 2nd hand.
    events: list[object] = []
    rid = ruleset_id(ruleset, strict_mode=True)
    for hand_seq, hand_id, button in [(1, "h1", 1), (2, "h2", 1)]:
        events.append(
            {
                "event": "HandStart",
                "hand_id": hand_id,
                "hand_seq": hand_seq,
                "button_seat": button,
                "seats_in_hand": [1, 2, 3],
                "ruleset_id": rid,
                "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
                "schema_hash": "2" * 64,
                "options_hash": "0" * 64,
                "provenance_ref": "artifact://prov",
            }
        )
        events.append({"event": "HandEnd", "initial_stacks_by_seat": {"1": 10, "2": 10, "3": 10}})

    path = tmp_path / "two_hands.ndjson"
    _write_eventstream(path, events)

    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["button_rotation"],
        strict_mode=True,
    )
    assert rep["failures_count"] == 1
    assert rep["failures"][0]["item"] == "button_rotation"


def test_rule_conformance_records_allin_reopen_failure_with_decision_locator(tmp_path: Path) -> None:
    ruleset = _ruleset(reopen=False)
    rid = ruleset_id(ruleset, strict_mode=True)

    # Construct a short all-in raise that should NOT reopen, then assert a later DecisionPoint
    # incorrectly exposes raise options for a previously-acted player.
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2, 3],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {
            "event": "DecisionPoint",
            "decision_id": 1,
            "state_hash": "s1",
            "snapshot_payload": {
                "street": "PREFLOP",
                "actor_seat": 3,
                "to_call_chips": 2,
                "actor_commit_chips": 0,
                "actor_stack_chips": 100,
                "min_raise_to_chips": 6,
                "max_raise_to_chips": 100,
            },
        },
        {
            "event": "ActionChosen",
            "decision_id": 1,
            "state_hash": "s1",
            "executed_action": {"kind": "RAISE", "target_total_commit_chips": 6},
        },
        {
            "event": "DecisionPoint",
            "decision_id": 2,
            "state_hash": "s2",
            "snapshot_payload": {
                "street": "PREFLOP",
                "actor_seat": 1,
                "to_call_chips": 6,
                "actor_commit_chips": 0,
                "actor_stack_chips": 100,
                "min_raise_to_chips": 10,
                "max_raise_to_chips": 100,
            },
        },
        {
            "event": "ActionChosen",
            "decision_id": 2,
            "state_hash": "s2",
            "executed_action": {"kind": "CALL", "target_total_commit_chips": 6},
        },
        # Short all-in raise: increment=3 is below last full raise increment=4.
        {
            "event": "DecisionPoint",
            "decision_id": 3,
            "state_hash": "s3",
            "snapshot_payload": {
                "street": "PREFLOP",
                "actor_seat": 2,
                "to_call_chips": 4,
                "actor_commit_chips": 2,
                "actor_stack_chips": 7,
                "min_raise_to_chips": 9,
                "max_raise_to_chips": 9,
            },
        },
        {
            "event": "ActionChosen",
            "decision_id": 3,
            "state_hash": "s3",
            "executed_action": {"kind": "RAISE", "target_total_commit_chips": 9},
        },
        # Previously-acted player 3 should not have raise options when reopen_on_short_allin=false.
        {
            "event": "DecisionPoint",
            "decision_id": 4,
            "state_hash": "s4",
            "snapshot_payload": {
                "street": "PREFLOP",
                "actor_seat": 3,
                "to_call_chips": 3,
                "actor_commit_chips": 6,
                "actor_stack_chips": 94,
                "min_raise_to_chips": 12,
                "max_raise_to_chips": 100,
            },
        },
        {
            "event": "ActionChosen",
            "decision_id": 4,
            "state_hash": "s4",
            "executed_action": {"kind": "CALL", "target_total_commit_chips": 9},
        },
        {"event": "HandEnd", "initial_stacks_by_seat": {"1": 100, "2": 9, "3": 100}},
    ]

    path = tmp_path / "reopen_fail.ndjson"
    _write_eventstream(path, events)

    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["allin_reopen"],
        strict_mode=True,
    )
    assert rep["failures_count"] == 1
    failure = rep["failures"][0]
    assert failure["item"] == "allin_reopen"
    loc = failure["decision_id_or_state_hash"]
    assert loc["decision_id"] is not None
    assert loc["state_hash"] is not None


def test_rule_conformance_no_flop_no_drop_failure(tmp_path: Path) -> None:
    rake = {"pct_ppm": 100_000, "cap_chips": None, "rounding_mode": "floor", "no_flop_no_drop": True}
    ruleset = _ruleset(rake=rake)

    objs = env.run_single_hand_eventstream_objects(
        run_id=_run_id(seed=3),
        options_hash=OPTIONS_HASH,
        seed=3,
        scenario_id="1" * 64,
        schema_hash="2" * 64,
        provenance_ref="artifact://prov",
        resolved_paths_digest="3" * 64,
        repro_tier="Tier-A",
        ruleset=ruleset,
        triad={"action_bins_id": ACTION_BINS_ID, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
        action_adapter=ACTION_ADAPTER_FAIL_FAST,
        action_bins=ACTION_BINS,
        mapping_spec_id=None,
        mw_ladder_id=None,
        starting_stacks_by_seat={1: 10, 2: 10},
        button_seat=1,
        hand_seq=1,
        policy=lambda ctx: {"kind": "FOLD", "target_total_commit_chips": int(ctx["snapshot"]["actor_commit_chips"])},
        strict_mode=True,
    )

    # Force a non-zero total rake in a no-flop hand.
    header = dict(objs[0])
    events = [dict(o) for o in objs[1:]]
    hand_end = next(e for e in events if e.get("event") == "HandEnd")
    hand_end["total_rake_chips"] = 1
    header["event_stream_digest"] = {"alg": "sha256", "hex": "0" * 64}
    header["event_stream_digest"]["hex"] = event_stream_digest_from_objects([header, *events], strict_mode=True)

    path = tmp_path / "nfnd.ndjson"
    _write_ndjson(path, [header, *events])

    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["no_flop_no_drop"],
        strict_mode=True,
    )
    assert rep["failures_count"] == 1
    assert rep["failures"][0]["item"] == "no_flop_no_drop"


def test_rule_conformance_rake_mismatch_failure(tmp_path: Path) -> None:
    rake = {"pct_ppm": 200_000, "cap_chips": None, "rounding_mode": "ceil", "no_flop_no_drop": False}
    ruleset = _ruleset(rake=rake)

    objs = env.run_single_hand_eventstream_objects(
        run_id=_run_id(seed=4),
        options_hash=OPTIONS_HASH,
        seed=4,
        scenario_id="1" * 64,
        schema_hash="2" * 64,
        provenance_ref="artifact://prov",
        resolved_paths_digest="3" * 64,
        repro_tier="Tier-A",
        ruleset=ruleset,
        triad={"action_bins_id": ACTION_BINS_ID, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
        action_adapter=ACTION_ADAPTER_FAIL_FAST,
        action_bins=ACTION_BINS,
        mapping_spec_id=None,
        mw_ladder_id=None,
        starting_stacks_by_seat={1: 50, 2: 50},
        button_seat=1,
        hand_seq=1,
        policy=lambda ctx: {"kind": "FOLD", "target_total_commit_chips": int(ctx["snapshot"]["actor_commit_chips"])},
        strict_mode=True,
    )

    header = dict(objs[0])
    events = [dict(o) for o in objs[1:]]
    hand_end = next(e for e in events if e.get("event") == "HandEnd")
    hand_end["total_rake_chips"] = int(hand_end["total_rake_chips"]) + 1
    header["event_stream_digest"] = {"alg": "sha256", "hex": "0" * 64}
    header["event_stream_digest"]["hex"] = event_stream_digest_from_objects([header, *events], strict_mode=True)

    path = tmp_path / "rake_mismatch.ndjson"
    _write_ndjson(path, [header, *events])

    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["rake"],
        strict_mode=True,
    )
    assert rep["failures_count"] == 1
    assert rep["failures"][0]["item"] == "rake"


def test_rule_conformance_forced_bets_reports_sb_bb_missing_and_unexpected_ante(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {"event": "ForcedBets", "kind": "ante", "by_seat_amount_chips": {"1": 1}},
        {"event": "HandEnd", "initial_stacks_by_seat": {"1": 10, "2": 10}},
    ]
    path = tmp_path / "forced_bets_missing.ndjson"
    _write_eventstream(path, events)

    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["forced_bets"],
        strict_mode=True,
    )
    reasons = {f["reason"] for f in rep["failures"]}
    assert "sb_missing" in reasons
    assert "bb_missing" in reasons
    assert "unexpected_ante" in reasons


def test_rule_conformance_forced_bets_uniform_ante_invalid(tmp_path: Path) -> None:
    ruleset = {
        **_ruleset(),
        "ante": {"kind": "uniform", "ante_chips": 1},
    }
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {"event": "ForcedBets", "kind": "sb", "by_seat_amount_chips": {"1": 1}},
        {"event": "ForcedBets", "kind": "bb", "by_seat_amount_chips": {"2": 2}},
        {"event": "ForcedBets", "kind": "ante", "by_seat_amount_chips": {"1": 2}},
        {"event": "HandEnd", "initial_stacks_by_seat": {"1": 10, "2": 10}},
    ]
    path = tmp_path / "ante_invalid.ndjson"
    _write_eventstream(path, events)

    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["forced_bets"],
        strict_mode=True,
    )
    assert any(f["reason"] == "ante_amount_invalid" for f in rep["failures"])


def test_rule_conformance_rake_fields_missing_strict(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {"event": "HandEnd", "initial_stacks_by_seat": {"1": 10, "2": 10}},
    ]
    path = tmp_path / "rake_fields_missing.ndjson"
    _write_eventstream(path, events)

    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["rake"],
        strict_mode=True,
    )
    assert rep["failures_count"] == 1
    assert rep["failures"][0]["reason"] == "rake_fields_missing"


def test_rule_conformance_digest_mismatch_is_error(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {"event": "HandEnd", "initial_stacks_by_seat": {"1": 10, "2": 10}},
    ]
    path = tmp_path / "digest_mismatch.ndjson"
    _write_eventstream(path, events)

    # Corrupt header digest without re-hashing.
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["event_stream_digest"]["hex"] = "0" * 64
    _write_ndjson(path, [header, *[json.loads(line) for line in lines[1:]]])

    with pytest.raises(RuleConformanceError) as exc:
        rule_conformance_report_from_eventstream(
            path,
            event_stream_ref=None,
            ruleset=ruleset,
            checked_items=["button_rotation"],
            strict_mode=True,
        )
    assert exc.value.code == "EVENTSTREAM_DIGEST_MISMATCH"


def test_rule_conformance_no_hands_is_error(tmp_path: Path) -> None:
    header = _header(digest_hex="0" * 64)
    header["event_stream_digest"]["hex"] = event_stream_digest_from_objects([header], strict_mode=True)
    path = tmp_path / "no_hands.ndjson"
    _write_ndjson(path, [header])

    with pytest.raises(RuleConformanceError) as exc:
        rule_conformance_report_from_eventstream(
            path,
            event_stream_ref=None,
            ruleset=_ruleset(),
            checked_items=["ledger_conservation"],
            strict_mode=True,
        )
    assert exc.value.code == "NO_HANDS"


def test_rule_conformance_failure_locator_normalizes_partial_decision_fields() -> None:
    out = rc._failure(
        event_stream_ref="path:x",
        event_stream_digest={"alg": "sha256", "hex": "0" * 64},
        hand_id="h1",
        item="min_raise",
        reason="x",
        decision_id=1,
        state_hash=None,
    )
    assert out["decision_id_or_state_hash"] == {"decision_id": None, "state_hash": None}


def test_rule_conformance_sets_event_stream_ref_when_none(tmp_path: Path) -> None:
    objs = env.run_single_hand_eventstream_objects(
        run_id=_run_id(seed=5),
        options_hash=OPTIONS_HASH,
        seed=5,
        scenario_id="1" * 64,
        schema_hash="2" * 64,
        provenance_ref="artifact://prov",
        resolved_paths_digest="3" * 64,
        repro_tier="Tier-A",
        ruleset=_ruleset(),
        triad={"action_bins_id": ACTION_BINS_ID, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
        action_adapter=ACTION_ADAPTER_FAIL_FAST,
        action_bins=ACTION_BINS,
        mapping_spec_id=None,
        mw_ladder_id=None,
        starting_stacks_by_seat={1: 10, 2: 10},
        button_seat=1,
        hand_seq=1,
        policy=lambda ctx: {"kind": "FOLD", "target_total_commit_chips": int(ctx["snapshot"]["actor_commit_chips"])},
        strict_mode=True,
    )
    path = tmp_path / "hand.ndjson"
    _write_ndjson(path, objs)

    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=None,
        ruleset=_ruleset(),
        checked_items=["rake"],
        strict_mode=True,
    )
    assert rep["context"]["event_stream_ref"].startswith("path:")


def test_rule_conformance_ledger_reports_missing_hand_end(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        }
    ]
    path = tmp_path / "no_hand_end.ndjson"
    _write_eventstream(path, events)
    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["ledger_conservation"],
        strict_mode=True,
    )
    assert rep["failures_count"] == 1
    assert rep["failures"][0]["reason"] == "missing_hand_end"


def test_rule_conformance_ledger_reports_schema_invalid_invariants_type(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {
            "event": "HandEnd",
            "initial_stacks_by_seat": {"1": 10, "2": 10},
            "final_stacks_by_seat": {"1": 10, "2": 10},
            "stack_deltas_by_seat": {"1": 0, "2": 0},
            "total_rake_chips": 0,
            "rake_base_pot_chips": 0,
            "invariants_ok": "yes",
        },
    ]
    path = tmp_path / "bad_invariants.ndjson"
    _write_eventstream(path, events)
    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["ledger_conservation"],
        strict_mode=True,
    )
    assert rep["failures_count"] == 1
    assert rep["failures"][0]["reason"] == "handend_schema_invalid"


def test_rule_conformance_ledger_invariants_ok_false(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {
            "event": "HandEnd",
            "initial_stacks_by_seat": {"1": 10, "2": 10},
            "final_stacks_by_seat": {"1": 10, "2": 10},
            "stack_deltas_by_seat": {"1": 0, "2": 0},
            "total_rake_chips": 0,
            "rake_base_pot_chips": 0,
            "invariants_ok": False,
        },
    ]
    path = tmp_path / "invariants_false.ndjson"
    _write_eventstream(path, events)
    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["ledger_conservation"],
        strict_mode=True,
    )
    assert rep["failures_count"] == 1
    assert rep["failures"][0]["reason"] == "invariants_ok_false"


def test_rule_conformance_ledger_seat_domain_mismatch(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {
            "event": "HandEnd",
            "initial_stacks_by_seat": {"1": 10, "2": 10},
            "final_stacks_by_seat": {"1": 10},
            "stack_deltas_by_seat": {"1": 0, "2": 0},
            "total_rake_chips": 0,
            "rake_base_pot_chips": 0,
            "invariants_ok": True,
        },
    ]
    path = tmp_path / "seat_domain_mismatch.ndjson"
    _write_eventstream(path, events)
    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["ledger_conservation"],
        strict_mode=True,
    )
    assert rep["failures_count"] == 1
    assert rep["failures"][0]["reason"] == "seat_domain_mismatch"


def test_rule_conformance_ledger_pot_balance_delta_not_zero(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {"event": "PotUpdate", "pot_chips_delta": 1, "rake_chips_delta": 0},
        {
            "event": "HandEnd",
            "initial_stacks_by_seat": {"1": 10, "2": 10},
            "final_stacks_by_seat": {"1": 10, "2": 10},
            "stack_deltas_by_seat": {"1": 0, "2": 0},
            "total_rake_chips": 0,
            "rake_base_pot_chips": 0,
            "invariants_ok": True,
        },
    ]
    path = tmp_path / "pot_balance_delta.ndjson"
    _write_eventstream(path, events)
    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["ledger_conservation"],
        strict_mode=True,
    )
    assert any(f["reason"] == "pot_balance_delta_not_zero" for f in rep["failures"])


def test_rule_conformance_forced_bets_by_seat_ante_invalid(tmp_path: Path) -> None:
    ruleset = {
        **_ruleset(),
        "ante": {"kind": "by_seat", "by_seat_ante_chips": {"1": 1}},
    }
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {"event": "ForcedBets", "kind": "sb", "by_seat_amount_chips": {"1": 1}},
        {"event": "ForcedBets", "kind": "bb", "by_seat_amount_chips": {"2": 2}},
        {"event": "ForcedBets", "kind": "ante", "by_seat_amount_chips": {"1": 2}},
        {"event": "HandEnd", "initial_stacks_by_seat": {"1": 10, "2": 10}},
    ]
    path = tmp_path / "ante_by_seat_invalid.ndjson"
    _write_eventstream(path, events)
    rep = rule_conformance_report_from_eventstream(
        path,
        event_stream_ref=f"path:{path}",
        ruleset=ruleset,
        checked_items=["forced_bets"],
        strict_mode=True,
    )
    assert any(f["reason"] == "ante_amount_invalid" for f in rep["failures"])


def test_rule_conformance_raises_on_hand_id_not_string(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        {
            "event": "HandStart",
            "hand_id": 123,
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {"event": "HandEnd", "initial_stacks_by_seat": {"1": 10, "2": 10}},
    ]
    path = tmp_path / "hand_id_bad.ndjson"
    _write_eventstream(path, events)
    with pytest.raises(RuleConformanceError) as exc:
        rule_conformance_report_from_eventstream(
            path,
            event_stream_ref=f"path:{path}",
            ruleset=ruleset,
            checked_items=["rake"],
            strict_mode=True,
        )
    assert exc.value.code == "HAND_ID_MISSING"


def test_rule_conformance_helpers_raise_on_duplicate_event() -> None:
    with pytest.raises(RuleConformanceError) as exc:
        rc._find_single_event([{"event": "HandEnd"}, {"event": "HandEnd"}], "HandEnd")
    assert exc.value.code == "EVENT_COUNT_MISMATCH"


def test_rule_conformance_helper_type_errors_and_split_helpers() -> None:
    with pytest.raises(RuleConformanceError):
        rc._as_int(True, field="x")
    with pytest.raises(RuleConformanceError):
        rc._as_int("1", field="x")
    with pytest.raises(RuleConformanceError):
        rc._as_str(1, field="x")
    with pytest.raises(RuleConformanceError):
        rc._as_obj([], field="x")
    with pytest.raises(RuleConformanceError):
        rc._seatmap({"x": 1}, field="x")

    assert rc._rotate_next_seat([1, 2], 3) is None

    hands = rc._split_hands(
        [
            {"event": "X"},
            {"event": "HandStart", "hand_id": "h1"},
            {"event": "HandStart", "hand_id": "h2"},
            {"event": "HandEnd"},
        ]
    )
    assert len(hands) == 2


def test_rule_conformance_rejects_non_object_event_record(tmp_path: Path) -> None:
    ruleset = _ruleset()
    rid = ruleset_id(ruleset, strict_mode=True)
    events: list[object] = [
        [],
        {
            "event": "HandStart",
            "hand_id": "h1",
            "hand_seq": 1,
            "button_seat": 1,
            "seats_in_hand": [1, 2],
            "ruleset_id": rid,
            "triad": {"action_bins_id": "4" * 64, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
            "schema_hash": "2" * 64,
            "options_hash": "0" * 64,
            "provenance_ref": "artifact://prov",
        },
        {"event": "HandEnd", "initial_stacks_by_seat": {"1": 10, "2": 10}},
    ]
    path = tmp_path / "non_object_event.ndjson"
    _write_eventstream(path, events)

    with pytest.raises(RuleConformanceError) as exc:
        rule_conformance_report_from_eventstream(
            path,
            event_stream_ref=f"path:{path}",
            ruleset=ruleset,
            checked_items=["rake"],
            strict_mode=True,
        )
    assert exc.value.code == "EVENT_NOT_OBJECT"
