from __future__ import annotations

from pathlib import Path

import pytest

from poker2.contractkit import canonicalize_json_bytes
from poker2.evaluation.gates import coinpoker_alignment as align
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.run_id import run_id_v1


def _write_ndjson(path: Path, objs: list[object]) -> None:
    lines = [canonicalize_json_bytes(o, strict_mode=True) for o in objs]
    path.write_bytes(b"\n".join(lines) + b"\n")


def _header(*, digest_hex: str) -> dict:
    options_hash = "0" * 64
    seed = 0
    return {
        "run_id": run_id_v1(options_hash=options_hash, seed=seed, strict_mode=True),
        "options_hash": options_hash,
        "seed": seed,
        "scenario_id": "0" * 64,
        "schema_hash": "0" * 64,
        "event_model_id": "0" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": digest_hex},
        "provenance_ref": "artifact://prov",
        "resolved_paths_digest": "0" * 64,
        "repro_tier": "Tier-A",
    }


def _write_eventstream(path: Path, events: list[object]) -> str:
    header = _header(digest_hex="0" * 64)
    digest_hex = event_stream_digest_from_objects([header, *events], strict_mode=True)
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(path, [header, *events])
    return digest_hex


def _dp(decision_id: int, *, actor_seat: int, street: str = "PREFLOP") -> dict:
    state_hash = f"s{decision_id}"
    return {
        "event": "DecisionPoint",
        "decision_id": decision_id,
        "state_hash": state_hash,
        "snapshot_payload": {"street": street, "actor_seat": actor_seat},
    }


def _ac(decision_id: int, *, kind: str, target: int) -> dict:
    state_hash = f"s{decision_id}"
    return {
        "event": "ActionChosen",
        "decision_id": decision_id,
        "state_hash": state_hash,
        "executed_action": {"kind": kind, "target_total_commit_chips": target},
    }


def _make_stream(
    tmp_path: Path,
    *,
    initial_stacks_by_seat: dict[str, int],
    forced_bets: list[dict] | None = None,
    actions: list[tuple[int, int, str, int, str]] | None = None,
) -> Path:
    events: list[object] = []
    for fb in forced_bets or []:
        events.append({"event": "ForcedBets", "by_seat_amount_chips": fb})
    for decision_id, actor, kind, target, street in actions or []:
        events.append(_dp(decision_id, actor_seat=actor, street=street))
        events.append(_ac(decision_id, kind=kind, target=target))
    events.append({"event": "HandEnd", "initial_stacks_by_seat": initial_stacks_by_seat})
    path = tmp_path / "hand.ndjson"
    _write_eventstream(path, events)
    return path


def test_alignment_helpers_type_errors() -> None:
    with pytest.raises(align.EvidenceError) as exc:
        align._as_int(True, field="x")
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(align.EvidenceError) as exc:
        align._as_int("1", field="x")
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(align.EvidenceError) as exc:
        align._as_str(1, field="x")
    assert exc.value.code == "TYPE_ERROR"


def test_alignment_round_rake_rejects_unknown_mode() -> None:
    with pytest.raises(align.EvidenceError) as exc:
        align._round_rake(1, 1, rounding_mode="nope")
    assert exc.value.code == "UNSUPPORTED_VALUE"


def test_alignment_expected_total_rake_chips_null_rake_and_cap_and_nfnd() -> None:
    assert (
        align._expected_total_rake_chips(
            rake_base_pot_chips=100,
            flop_dealt=True,
            ruleset={"rake": None},
            rounding_mode="floor",
        )
        == 0
    )

    with pytest.raises(align.EvidenceError) as exc:
        align._expected_total_rake_chips(
            rake_base_pot_chips=100,
            flop_dealt=True,
            ruleset={"rake": {"pct_ppm": 10, "cap_chips": None, "no_flop_no_drop": None}},
            rounding_mode="floor",
        )
    assert exc.value.code == "TYPE_ERROR"

    assert (
        align._expected_total_rake_chips(
            rake_base_pot_chips=100,
            flop_dealt=False,
            ruleset={"rake": {"pct_ppm": 100_000, "cap_chips": None, "no_flop_no_drop": True}},
            rounding_mode="floor",
        )
        == 0
    )

    assert (
        align._expected_total_rake_chips(
            rake_base_pot_chips=100,
            flop_dealt=True,
            ruleset={"rake": {"pct_ppm": 100_000, "cap_chips": 1, "no_flop_no_drop": False}},
            rounding_mode="ceil",
        )
        == 1
    )


def test_infer_rake_rounding_modes_rejects_bad_fixture_ref() -> None:
    ruleset = {"rake": {"pct_ppm": 0, "cap_chips": None, "no_flop_no_drop": False}}
    with pytest.raises(align.EvidenceError) as exc:
        align.infer_rake_rounding_modes(
            [{"event_stream_ref": "not-a-path"}],
            ruleset=ruleset,
            strict_mode=True,
        )
    assert exc.value.code == "FIXTURE_REF_INVALID"


def test_infer_rake_rounding_modes_requires_both_rake_fields(tmp_path: Path) -> None:
    ruleset = {"rake": {"pct_ppm": 0, "cap_chips": None, "no_flop_no_drop": False}}
    p = tmp_path / "rake_missing_field.ndjson"
    _write_eventstream(p, [{"event": "HandEnd", "rake_base_pot_chips": 10}])

    with pytest.raises(align.EvidenceError) as exc:
        align.infer_rake_rounding_modes(
            [{"event_stream_ref": f"path:{p}"}],
            ruleset=ruleset,
            strict_mode=True,
        )
    assert exc.value.code == "RAKE_FIELDS_MISSING"


def test_load_hand_events_rejects_non_object_event(tmp_path: Path) -> None:
    p = tmp_path / "bad_event.ndjson"
    _write_eventstream(p, [[], {"event": "HandEnd"}])
    with pytest.raises(align.EvidenceError) as exc:
        align._load_hand_events(p, strict_mode=True)
    assert exc.value.code == "EVENT_NOT_OBJECT"


def test_get_single_event_requires_exactly_one() -> None:
    with pytest.raises(align.EvidenceError) as exc:
        align._get_single_event([], "HandEnd")
    assert exc.value.code == "EVENT_COUNT_MISMATCH"


def test_seatmap_to_int_map_rejects_invalid_shapes() -> None:
    with pytest.raises(align.EvidenceError) as exc:
        align._seatmap_to_int_map([], field="x")
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(align.EvidenceError) as exc:
        align._seatmap_to_int_map({"x": 1}, field="x")
    assert exc.value.code == "TYPE_ERROR"


def test_iter_decision_actions_structural_errors() -> None:
    with pytest.raises(align.EvidenceError) as exc:
        align._iter_decision_actions(
            [
                {"event": "ActionChosen", "decision_id": 1, "state_hash": "s1", "executed_action": {"kind": "CALL", "target_total_commit_chips": 0}},
            ]
        )
    assert exc.value.code == "DECISIONPOINT_MISSING"

    with pytest.raises(align.EvidenceError) as exc:
        align._iter_decision_actions(
            [
                {"event": "DecisionPoint", "decision_id": 1, "state_hash": "s1", "snapshot_payload": None},
                {"event": "ActionChosen", "decision_id": 1, "state_hash": "s1", "executed_action": {"kind": "CALL", "target_total_commit_chips": 0}},
            ]
        )
    assert exc.value.code == "SNAPSHOT_MISSING"

    with pytest.raises(align.EvidenceError) as exc:
        align._iter_decision_actions(
            [
                {"event": "DecisionPoint", "decision_id": 1, "state_hash": "s1", "snapshot_payload": {"street": "PREFLOP", "actor_seat": 1}},
                {"event": "ActionChosen", "decision_id": 1, "state_hash": "s1", "executed_action": None},
            ]
        )
    assert exc.value.code == "ACTION_MISSING"


@pytest.mark.parametrize(
    "forced_bets,initial_stacks,actions,expected_reason,reopen",
    [
        ( [{"1": -1}], {"1": 10}, None, "forced_bets_negative", True ),
        ( [{"1": 6}], {"1": 5}, None, "forced_bets_exceed_stack", True ),
        ( [{"1": 2}], {"1": 10}, [(1, 2, "CHECK", 0, "PREFLOP")], "actor_not_alive", True ),
        ( None, {"1": 0, "2": 10}, [(1, 1, "CHECK", 0, "PREFLOP")], "actor_allin_acted", True ),
        ( None, {"1": 10}, [(1, 1, "JAM", 0, "PREFLOP")], "unsupported_action_kind", True ),
        ( [{"1": 2}], {"1": 10}, [(1, 1, "CHECK", 1, "PREFLOP")], "target_below_commit", True ),
        ( None, {"1": 10}, [(1, 1, "BET", 11, "PREFLOP")], "target_exceeds_stack", True ),
        ( None, {"1": 10, "2": 10}, [(1, 1, "FOLD", 0, "PREFLOP")], "fold_when_no_to_call", True ),
        ( [{"2": 2}], {"1": 10, "2": 10}, [(1, 1, "FOLD", 1, "PREFLOP")], "fold_changes_commit", True ),
        ( [{"1": 2}], {"1": 10, "2": 10}, [(1, 2, "CHECK", 0, "PREFLOP")], "check_when_to_call", True ),
        ( None, {"1": 10}, [(1, 1, "CHECK", 1, "PREFLOP")], "check_changes_commit", True ),
        ( None, {"1": 10}, [(1, 1, "CALL", 0, "PREFLOP")], "call_when_no_to_call", True ),
        ( [{"1": 2}], {"1": 10, "2": 10}, [(1, 2, "CALL", 1, "PREFLOP")], "call_target_mismatch", True ),
        ( [{"1": 2}], {"1": 10, "2": 10}, [(1, 2, "BET", 4, "PREFLOP")], "bet_when_to_call", True ),
        ( None, {"1": 10}, [(1, 1, "BET", 0, "PREFLOP")], "bet_non_positive", True ),
        ( None, {"1": 10}, [(1, 1, "BET", 1, "PREFLOP")], "bet_below_min", True ),
        ( None, {"1": 10}, [(1, 1, "RAISE", 1, "PREFLOP")], "raise_when_no_to_call", True ),
        ( [{"1": 5}], {"1": 10, "2": 2}, [(1, 2, "RAISE", 2, "PREFLOP")], "raise_without_stack_space", True ),
        ( [{"1": 5}], {"1": 10, "2": 10}, [(1, 2, "RAISE", 5, "PREFLOP")], "raise_not_above_call", True ),
    ],
)
def test_check_actions_legality_common_failure_reasons(
    tmp_path: Path,
    forced_bets: list[dict[str, int]] | None,
    initial_stacks: dict[str, int],
    actions: list[tuple[int, int, str, int, str]] | None,
    expected_reason: str,
    reopen: bool,
) -> None:
    ruleset = {"blinds": {"bb_chips": 2}}
    path = _make_stream(
        tmp_path,
        forced_bets=forced_bets,
        initial_stacks_by_seat=initial_stacks,
        actions=actions,
    )
    events = align._load_hand_events(path, strict_mode=True)
    ok, fail = align.check_action_sequence_legality(
        events,
        ruleset=ruleset,
        reopen_on_short_allin=reopen,
        strict_mode=True,
    )
    assert ok is False
    assert fail is not None
    assert fail["reason"] == expected_reason


def test_check_actions_legality_handles_forced_bet_unknown_seat_and_allin_marking(tmp_path: Path) -> None:
    ruleset = {"blinds": {"bb_chips": 2}}
    path = _make_stream(
        tmp_path,
        forced_bets=[{"9": 1}, {"1": 1}],
        initial_stacks_by_seat={"1": 1},
        actions=None,
    )
    events = align._load_hand_events(path, strict_mode=True)
    ok, fail = align.check_action_sequence_legality(
        events,
        ruleset=ruleset,
        reopen_on_short_allin=True,
        strict_mode=True,
    )
    assert ok is True
    assert fail is None


def test_check_actions_legality_sets_flop_opening_increment_to_bb(tmp_path: Path) -> None:
    ruleset = {"blinds": {"bb_chips": 2}}
    path = _make_stream(
        tmp_path,
        forced_bets=None,
        initial_stacks_by_seat={"1": 10, "2": 10},
        actions=[(1, 1, "CHECK", 0, "FLOP")],
    )
    events = align._load_hand_events(path, strict_mode=True)
    ok, fail = align.check_action_sequence_legality(
        events,
        ruleset=ruleset,
        reopen_on_short_allin=True,
        strict_mode=True,
    )
    assert ok is True
    assert fail is None


def test_check_actions_legality_records_allin_on_call_and_bet(tmp_path: Path) -> None:
    ruleset = {"blinds": {"bb_chips": 2}}

    call_allin = _make_stream(
        tmp_path,
        forced_bets=[{"1": 2}],
        initial_stacks_by_seat={"1": 10, "2": 2},
        actions=[(1, 2, "CALL", 2, "PREFLOP")],
    )
    events = align._load_hand_events(call_allin, strict_mode=True)
    ok, fail = align.check_action_sequence_legality(
        events,
        ruleset=ruleset,
        reopen_on_short_allin=True,
        strict_mode=True,
    )
    assert ok is True
    assert fail is None

    bet_allin = _make_stream(
        tmp_path,
        forced_bets=None,
        initial_stacks_by_seat={"1": 1},
        actions=[(1, 1, "BET", 1, "PREFLOP")],
    )
    events = align._load_hand_events(bet_allin, strict_mode=True)
    ok, fail = align.check_action_sequence_legality(
        events,
        ruleset=ruleset,
        reopen_on_short_allin=True,
        strict_mode=True,
    )
    assert ok is True
    assert fail is None


def test_check_actions_legality_detects_short_raise_not_allin(tmp_path: Path) -> None:
    ruleset = {"blinds": {"bb_chips": 2}}
    path = _make_stream(
        tmp_path,
        forced_bets=[{"1": 2}],
        initial_stacks_by_seat={"1": 100, "2": 100, "3": 100},
        actions=[
            (1, 2, "RAISE", 10, "PREFLOP"),
            (2, 1, "CALL", 10, "PREFLOP"),
            (3, 3, "RAISE", 15, "PREFLOP"),
        ],
    )
    events = align._load_hand_events(path, strict_mode=True)
    ok, fail = align.check_action_sequence_legality(
        events,
        ruleset=ruleset,
        reopen_on_short_allin=True,
        strict_mode=True,
    )
    assert ok is False
    assert fail is not None
    assert fail["reason"] == "raise_below_min_not_allin"


def test_check_actions_legality_detects_bet_increment_below_min(tmp_path: Path) -> None:
    ruleset = {"blinds": {"bb_chips": 2}}
    path = _make_stream(
        tmp_path,
        forced_bets=[{"1": 2}],
        initial_stacks_by_seat={"1": 50, "2": 50},
        actions=[
            (1, 2, "RAISE", 10, "PREFLOP"),
            (2, 1, "CALL", 10, "PREFLOP"),
            (3, 2, "BET", 15, "PREFLOP"),
        ],
    )
    events = align._load_hand_events(path, strict_mode=True)
    ok, fail = align.check_action_sequence_legality(
        events,
        ruleset=ruleset,
        reopen_on_short_allin=True,
        strict_mode=True,
    )
    assert ok is False
    assert fail is not None
    assert fail["reason"] == "bet_increment_below_min"


def test_check_actions_legality_allows_fold_with_to_call(tmp_path: Path) -> None:
    ruleset = {"blinds": {"bb_chips": 2}}
    path = _make_stream(
        tmp_path,
        forced_bets=[{"2": 2}],
        initial_stacks_by_seat={"1": 10, "2": 10},
        actions=[(1, 1, "FOLD", 0, "PREFLOP")],
    )
    events = align._load_hand_events(path, strict_mode=True)
    ok, fail = align.check_action_sequence_legality(
        events,
        ruleset=ruleset,
        reopen_on_short_allin=True,
        strict_mode=True,
    )
    assert ok is True
    assert fail is None


def test_check_actions_legality_allows_short_allin_bet_increment(tmp_path: Path) -> None:
    ruleset = {"blinds": {"bb_chips": 2}}
    path = _make_stream(
        tmp_path,
        forced_bets=[{"1": 2}],
        initial_stacks_by_seat={"1": 50, "2": 15},
        actions=[
            (1, 2, "RAISE", 10, "PREFLOP"),
            (2, 1, "CALL", 10, "PREFLOP"),
            (3, 2, "BET", 15, "PREFLOP"),
        ],
    )
    events = align._load_hand_events(path, strict_mode=True)
    ok, fail = align.check_action_sequence_legality(
        events,
        ruleset=ruleset,
        reopen_on_short_allin=True,
        strict_mode=True,
    )
    assert ok is True
    assert fail is None


def test_infer_reopen_on_short_allin_flags_rejects_bad_fixture_ref() -> None:
    with pytest.raises(align.EvidenceError) as exc:
        align.infer_reopen_on_short_allin_flags(
            [{"event_stream_ref": 123}],
            ruleset={"blinds": {"bb_chips": 2}},
            strict_mode=True,
        )
    assert exc.value.code == "FIXTURE_REF_INVALID"
