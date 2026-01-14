from __future__ import annotations

import pytest

from poker2.environment import pokerkit_nlhe as env
from poker2.protocol.action_bins import action_bins_id
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.rake import compute_total_rake_chips
from poker2.protocol.run_id import run_id_v1
from poker2.protocol.mw_ladder import default_internal_mw_ladder


def _ruleset(*, reopen: bool, rake: dict | None) -> dict:
    return {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": None,
        "straddle": None,
        "rake": rake,
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": reopen},
    }


def _run(
    *,
    ruleset: dict,
    starting_stacks_by_seat: dict[int, int],
    button_seat: int,
    strict_mode: bool,
    fallback_mode: str,
    seed: int = 123,
    policy=None,
    mw_ladder_id: str | None = None,
) -> list[dict]:
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
        "fallback_policy": {"mode": fallback_mode},
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
        ruleset=ruleset,
        triad={"action_bins_id": bins_id, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
        action_adapter=action_adapter,
        action_bins=action_bins,
        mapping_spec_id=None,
        mw_ladder_id=mw_ladder_id,
        starting_stacks_by_seat=starting_stacks_by_seat,
        button_seat=button_seat,
        hand_seq=1,
        policy=policy,
        strict_mode=strict_mode,
    )


def _run_multi(
    *,
    ruleset: dict,
    starting_stacks_by_seat: dict[int, int],
    button_seat: int,
    strict_mode: bool,
    fallback_mode: str,
    seed: int = 123,
    hands: int = 2,
    policy=None,
    mw_ladder_id: str | None = None,
) -> list[dict]:
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
        "fallback_policy": {"mode": fallback_mode},
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
        ruleset=ruleset,
        triad={"action_bins_id": bins_id, "obs_schema_id": "5" * 64, "rake_id": "6" * 64},
        action_adapter=action_adapter,
        action_bins=action_bins,
        mapping_spec_id=None,
        mw_ladder_id=mw_ladder_id,
        starting_stacks_by_seat=starting_stacks_by_seat,
        button_seat=button_seat,
        hands=hands,
        policy=policy,
        strict_mode=strict_mode,
    )


def _first_event(objs: list[dict], name: str) -> dict:
    for obj in objs:
        if obj.get("event") == name:
            return obj
    raise AssertionError(f"missing event {name}")


def _iter_events(objs: list[dict], name: str) -> list[dict]:
    return [o for o in objs if o.get("event") == name]


def _pot_balance_from_events(objs: list[dict]) -> int:
    pot = 0
    for e in objs:
        if e.get("event") != "PotUpdate":
            continue
        pot += int(e["pot_chips_delta"]) - int(e["rake_chips_delta"])
    return pot


def test_env_run_single_hand_multiway_with_rake_and_routing() -> None:
    ruleset = _ruleset(
        reopen=False,
        rake={"pct_ppm": 50_000, "cap_chips": None, "rounding_mode": "floor", "no_flop_no_drop": False},
    )
    objs = _run(
        ruleset=ruleset,
        starting_stacks_by_seat={1: 50, 2: 50, 3: 50},
        button_seat=1,
        strict_mode=True,
        fallback_mode="fail_fast",
        mw_ladder_id=default_internal_mw_ladder(strict_mode=True)[1],
    )

    header = objs[0]
    assert header["event_stream_digest"]["hex"] == event_stream_digest_from_objects(objs, strict_mode=True)
    assert _iter_events(objs, "DecisionPoint")
    assert _iter_events(objs, "ActionChosen")
    assert _iter_events(objs, "StreetDealt")

    ac = _first_event(objs, "ActionChosen")
    assert ac["mapping_trace"]["trace_schema_id"] == "mapping_trace_v1"

    # Multi-way routing must be present in at least one ActionChosen.
    assert any(e.get("routing") is not None for e in _iter_events(objs, "ActionChosen"))

    hand_end = _first_event(objs, "HandEnd")
    assert hand_end["invariants_ok"] is True

    # Rake must follow RuleSet on the recorded base pot.
    flop_dealt = any(e.get("event") == "StreetDealt" and e.get("street") == "FLOP" for e in objs)
    expected_rake = compute_total_rake_chips(
        rake_base_pot_chips=int(hand_end["rake_base_pot_chips"]),
        flop_dealt=flop_dealt,
        ruleset=ruleset,
    )
    assert int(hand_end["total_rake_chips"]) == expected_rake

    # Pot must close by PotUpdate deltas.
    assert _pot_balance_from_events(objs) == 0


def test_env_strict_requires_mw_ladder_for_multiway() -> None:
    ruleset = _ruleset(reopen=False, rake=None)
    with pytest.raises(env.EnvironmentError) as exc:
        _run(
            ruleset=ruleset,
            starting_stacks_by_seat={1: 20, 2: 20, 3: 20},
            button_seat=1,
            strict_mode=True,
            fallback_mode="fail_fast",
            mw_ladder_id=None,
        )
    assert exc.value.code == "MISSING_FIELDS"


def test_env_run_multi_hand_rotates_button_and_has_single_header() -> None:
    ruleset = _ruleset(reopen=False, rake=None)
    objs = _run_multi(
        ruleset=ruleset,
        starting_stacks_by_seat={1: 50, 2: 50},
        button_seat=1,
        strict_mode=True,
        fallback_mode="fail_fast",
        hands=3,
    )

    header = objs[0]
    assert header["seed"] == 123
    assert header["event_stream_digest"]["hex"] == event_stream_digest_from_objects(objs, strict_mode=True)

    starts = [o for o in objs if o.get("event") == "HandStart"]
    assert [int(s["hand_seq"]) for s in starts] == [1, 2, 3]
    assert [int(s["button_seat"]) for s in starts] == [1, 2, 1]


def test_env_fallback_snap_nearest() -> None:
    ruleset = _ruleset(reopen=False, rake=None)

    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        if int(ctx["decision_id"]) != 1 or snap["min_raise_to_chips"] is None:
            return {
                "kind": "CHECK" if int(snap["to_call_chips"]) == 0 else "CALL",
                "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"]),
            }
        snap = ctx["snapshot"]
        # Force an illegal raise target not in {min,max} so snap_nearest must replace it.
        t = int(snap["min_raise_to_chips"]) + 1
        return {"kind": "RAISE", "target_total_commit_chips": t}

    objs = _run(
        ruleset=ruleset,
        starting_stacks_by_seat={1: 100, 2: 100},
        button_seat=1,
        strict_mode=False,
        fallback_mode="snap_nearest",
        policy=policy,
    )
    first_ac = _first_event(objs, "ActionChosen")
    mt = first_ac["mapping_trace"]
    assert mt["reason_code"] == "snap_to_bin"
    assert mt["fallback_mode"] == "snap_nearest"
    assert first_ac["proposed_action"] != first_ac["executed_action"]


def test_env_fallback_clamp_then_snap() -> None:
    ruleset = _ruleset(reopen=False, rake=None)

    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        if int(ctx["decision_id"]) != 1 or snap["min_raise_to_chips"] is None:
            return {
                "kind": "CHECK" if int(snap["to_call_chips"]) == 0 else "CALL",
                "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"]),
            }
        return {"kind": "RAISE", "target_total_commit_chips": int(snap["min_raise_to_chips"]) - 1}

    objs = _run(
        ruleset=ruleset,
        starting_stacks_by_seat={1: 100, 2: 100},
        button_seat=1,
        strict_mode=False,
        fallback_mode="clamp_then_snap",
        policy=policy,
    )
    first_ac = _first_event(objs, "ActionChosen")
    mt = first_ac["mapping_trace"]
    assert mt["reason_code"] == "clamp"
    assert mt["fallback_mode"] == "clamp_then_snap"


def test_env_fallback_conservative_check_call() -> None:
    ruleset = _ruleset(reopen=False, rake=None)

    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        # Force an illegal raise above max.
        return {"kind": "RAISE", "target_total_commit_chips": int(snap["max_raise_to_chips"]) + 1}

    objs = _run(
        ruleset=ruleset,
        starting_stacks_by_seat={1: 100, 2: 100},
        button_seat=1,
        strict_mode=False,
        fallback_mode="conservative_check_call",
        policy=policy,
    )
    first_ac = _first_event(objs, "ActionChosen")
    assert first_ac["executed_action"]["kind"] in ("CHECK", "CALL")
    assert first_ac["mapping_trace"]["reason_code"] == "conservative_fallback"


def test_env_canonicalize_kind_override_non_strict() -> None:
    ruleset = _ruleset(reopen=False, rake=None)

    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        # Target implies FOLD (no additional commit), but kind says RAISE.
        return {"kind": "RAISE", "target_total_commit_chips": int(snap["actor_commit_chips"])}

    objs = _run(
        ruleset=ruleset,
        starting_stacks_by_seat={1: 10, 2: 10},
        button_seat=1,
        strict_mode=False,
        fallback_mode="fail_fast",
        policy=policy,
    )
    first_ac = _first_event(objs, "ActionChosen")
    assert first_ac["executed_action"]["kind"] == "FOLD"
    assert first_ac["mapping_trace"]["reason_code"] == "kind_override"


def test_env_canonicalize_call_target_override_non_strict() -> None:
    ruleset = _ruleset(reopen=False, rake=None)

    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        if int(ctx["decision_id"]) != 1:
            return {
                "kind": "CHECK" if int(snap["to_call_chips"]) == 0 else "CALL",
                "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"]),
            }
        # CALL target must be unique (actor_commit + to_call); provide an incorrect target.
        return {"kind": "CALL", "target_total_commit_chips": 999}

    objs = _run(
        ruleset=ruleset,
        starting_stacks_by_seat={1: 10, 2: 10},
        button_seat=1,
        strict_mode=False,
        fallback_mode="fail_fast",
        policy=policy,
    )
    first_ac = _first_event(objs, "ActionChosen")
    assert first_ac["executed_action"]["kind"] == "CALL"
    assert first_ac["mapping_trace"]["reason_code"] == "illegal_action"


def test_env_strict_rejects_illegal_action() -> None:
    ruleset = _ruleset(reopen=False, rake=None)

    def policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        return {"kind": "RAISE", "target_total_commit_chips": int(snap["max_raise_to_chips"]) + 1}

    with pytest.raises(env.EnvironmentError) as exc:
        _run(
            ruleset=ruleset,
            starting_stacks_by_seat={1: 50, 2: 50},
            button_seat=1,
            strict_mode=True,
            fallback_mode="fail_fast",
            policy=policy,
        )
    assert exc.value.code == "ILLEGAL_ACTION"


def test_env_reopen_on_short_allin_allows_reraise() -> None:
    # 3-handed: button makes a *bigger-than-min* full raise; SB makes a *short* all-in raise;
    # with reopen enabled, the button must retain raise rights afterwards
    # (Snapshot.min_raise_to_chips becomes non-null).
    #
    # Important: keep at least one opponent *not* all-in, otherwise PokerKit forbids further
    # raises as “no reason to raise”.
    #
    # Sequence:
    # - BTN raises to the deterministic extra target (min + last_full_raise_increment).
    # - SB goes all-in to max_raise_to (a short all-in raise vs the last full raise increment).
    # - BB CALLs (not all-in), keeping a reason to raise.
    # - BTN should be allowed to re-raise only when reopen_on_short_allin=true.
    stacks = {1: 100, 2: 8, 3: 100}

    def policy(ctx: dict) -> dict:
        did = int(ctx["decision_id"])
        snap = ctx["snapshot"]
        if did == 1:
            # Raise to the deterministic extra target produced by our legal-action spec:
            # extra = min_raise_to + (min_raise_to - current_bet_to_total).
            min_raise_to = int(snap["min_raise_to_chips"])
            current_bet_to_total = int(snap["actor_commit_chips"]) + int(snap["to_call_chips"])
            last_full_raise_increment = min_raise_to - current_bet_to_total
            extra = min_raise_to + last_full_raise_increment
            return {"kind": "RAISE", "target_total_commit_chips": int(extra)}
        if did == 2:
            return {"kind": "RAISE", "target_total_commit_chips": int(snap["max_raise_to_chips"])}
        if did == 3:
            return {"kind": "CALL", "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"])}
        if did == 4:
            if snap["min_raise_to_chips"] is not None:
                return {"kind": "RAISE", "target_total_commit_chips": int(snap["min_raise_to_chips"])}
            return {"kind": "CALL", "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"])}
        return {"kind": "CHECK" if int(snap["to_call_chips"]) == 0 else "CALL", "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"])}

    ruleset_reopen = _ruleset(reopen=True, rake=None)
    objs_reopen = _run(
        ruleset=ruleset_reopen,
        starting_stacks_by_seat=stacks,
        button_seat=1,
        strict_mode=True,
        fallback_mode="fail_fast",
        policy=policy,
        mw_ladder_id="b" * 64,
    )
    dps = _iter_events(objs_reopen, "DecisionPoint")
    dp4 = next(dp for dp in dps if int(dp["decision_id"]) == 4)
    assert dp4["snapshot_payload"]["min_raise_to_chips"] is not None

    ruleset_closed = _ruleset(reopen=False, rake=None)
    objs_closed = _run(
        ruleset=ruleset_closed,
        starting_stacks_by_seat=stacks,
        button_seat=1,
        strict_mode=True,
        fallback_mode="fail_fast",
        policy=policy,
        mw_ladder_id="b" * 64,
    )
    dps2 = _iter_events(objs_closed, "DecisionPoint")
    dp4_closed = next(dp for dp in dps2 if int(dp["decision_id"]) == 4)
    assert dp4_closed["snapshot_payload"]["min_raise_to_chips"] is None


def test_env_rake_allocation_on_tie_uses_pot_payouts() -> None:
    # If the pot is split (net payoffs can be 0), rake must still be applied by reducing
    # pot payouts, not by looking for positive net payoffs.
    ruleset = _ruleset(
        reopen=False,
        rake={"pct_ppm": 37_000, "cap_chips": None, "rounding_mode": "floor", "no_flop_no_drop": False},
    )

    def policy(ctx: dict) -> dict:
        did = int(ctx["decision_id"])
        snap = ctx["snapshot"]
        if did == 1:
            return {"kind": "RAISE", "target_total_commit_chips": int(snap["max_raise_to_chips"])}
        if int(snap["to_call_chips"]) == 0:
            return {"kind": "CHECK", "target_total_commit_chips": int(snap["actor_commit_chips"])}
        return {"kind": "CALL", "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"])}

    objs = _run(
        ruleset=ruleset,
        starting_stacks_by_seat={1: 100, 2: 100},
        button_seat=1,
        strict_mode=True,
        fallback_mode="fail_fast",
        seed=65,  # deterministic split pot for this policy in PokerKit 0.7.1
        policy=policy,
    )

    hand_end = _first_event(objs, "HandEnd")
    assert int(hand_end["total_rake_chips"]) == 7
    assert hand_end["final_stacks_by_seat"] == {"1": 96, "2": 97}
    assert hand_end["invariants_ok"] is True
