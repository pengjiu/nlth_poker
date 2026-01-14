from __future__ import annotations

import pytest

from poker2.contractkit._generated import ContractKitError
from poker2.environment import pokerkit_nlhe as env
from poker2.protocol.legal_actions import LegalActionsError, legal_actions_and_digest
from poker2.protocol.action_bins import action_bins_id
from poker2.protocol.mw_context import MWContextError, mw_context_digest
from poker2.protocol import rake as rake_mod
from poker2.protocol.rake import RakeError, compute_total_rake_chips
from poker2.protocol.rounding import RoundingError, round_div_int
from poker2.protocol.snapshot import SnapshotError, street_from_pokerkit_street_index, validate_snapshot_min_fields
from poker2.protocol.run_id import run_id_v1


ACTION_BINS = {
    "action_bins_schema_id": "action_bins_spec_v1",
    "include_min_raise_to": True,
    "include_max_raise_to": True,
    "include_extra_raise_to": True,
}


def _ruleset(*, ante: dict | None = None, rake: dict | None = None, reopen: bool = False) -> dict:
    return {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": ante,
        "straddle": None,
        "rake": rake,
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": reopen},
    }


def _run_env(
    *,
    ruleset: dict,
    starting_stacks_by_seat: dict,
    button_seat,
    fallback_mode: str = "fail_fast",
    policy=None,
    strict_mode: bool = True,
    seed: int = 123,
):
    options_hash = "0" * 64
    bins_id = action_bins_id(ACTION_BINS, strict_mode=True)
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
        action_bins=ACTION_BINS,
        mapping_spec_id=None,
        mw_ladder_id=None,
        starting_stacks_by_seat=starting_stacks_by_seat,
        button_seat=button_seat,
        hand_seq=1,
        policy=policy,
        strict_mode=strict_mode,
    )


def test_round_div_int_rejects_nonpositive_denom() -> None:
    with pytest.raises(RoundingError) as exc:
        round_div_int(1, 0, rounding_mode="floor")
    assert exc.value.code == "VALUE_ERROR"


def test_compute_total_rake_chips_validates_inputs() -> None:
    with pytest.raises(RakeError) as exc:
        compute_total_rake_chips(rake_base_pot_chips=10, flop_dealt=True, ruleset={"rake": "bad"})
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(RakeError) as exc:
        compute_total_rake_chips(
            rake_base_pot_chips=10,
            flop_dealt=True,
            ruleset={"rake": {"pct_ppm": True, "cap_chips": None, "rounding_mode": "floor", "no_flop_no_drop": False}},
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(RakeError) as exc:
        compute_total_rake_chips(
            rake_base_pot_chips=10,
            flop_dealt=True,
            ruleset={"rake": {"pct_ppm": 2_000_000, "cap_chips": None, "rounding_mode": "floor", "no_flop_no_drop": False}},
        )
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(RakeError) as exc:
        compute_total_rake_chips(
            rake_base_pot_chips=10,
            flop_dealt=True,
            ruleset={"rake": {"pct_ppm": 10_000, "cap_chips": -1, "rounding_mode": "floor", "no_flop_no_drop": False}},
        )
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(RakeError) as exc:
        compute_total_rake_chips(
            rake_base_pot_chips=10,
            flop_dealt=True,
            ruleset={"rake": {"pct_ppm": 10_000, "cap_chips": None, "rounding_mode": None, "no_flop_no_drop": False}},
        )
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(RakeError) as exc:
        compute_total_rake_chips(
            rake_base_pot_chips=10,
            flop_dealt=True,
            ruleset={"rake": {"pct_ppm": 10_000, "cap_chips": None, "rounding_mode": "bogus", "no_flop_no_drop": False}},
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"


def test_compute_total_rake_chips_rejects_non_int_pct_ppm() -> None:
    with pytest.raises(RakeError) as exc:
        compute_total_rake_chips(
            rake_base_pot_chips=10,
            flop_dealt=True,
            ruleset={"rake": {"pct_ppm": "nope", "cap_chips": None, "rounding_mode": "floor", "no_flop_no_drop": False}},
        )
    assert exc.value.code == "TYPE_ERROR"


def test_compute_total_rake_chips_rejects_negative_result() -> None:
    with pytest.raises(RakeError) as exc:
        compute_total_rake_chips(
            rake_base_pot_chips=-10,
            flop_dealt=True,
            ruleset={"rake": {"pct_ppm": 10_000, "cap_chips": None, "rounding_mode": "floor", "no_flop_no_drop": False}},
        )
    assert exc.value.code == "VALUE_ERROR"


def test_compute_total_rake_chips_clamps_to_pot(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_round_div_int(*_args: object, **_kwargs: object) -> int:
        return 999

    monkeypatch.setattr(rake_mod, "round_div_int", _fake_round_div_int)
    out = compute_total_rake_chips(
        rake_base_pot_chips=10,
        flop_dealt=True,
        ruleset={"rake": {"pct_ppm": 10_000, "cap_chips": None, "rounding_mode": "floor", "no_flop_no_drop": False}},
    )
    assert out == 10


def test_snapshot_helpers_validate_edges() -> None:
    with pytest.raises(SnapshotError) as exc:
        street_from_pokerkit_street_index(None)
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(SnapshotError) as exc:
        street_from_pokerkit_street_index(99)
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(SnapshotError) as exc:
        validate_snapshot_min_fields("bad", strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(SnapshotError) as exc:
        validate_snapshot_min_fields({}, strict_mode=True)
    assert exc.value.code == "MISSING_FIELDS"

    bad_street = {
        "street": "X",
        "actor_seat": 1,
        "players_alive_count": 2,
        "pot_chips": 0,
        "to_call_chips": 0,
        "actor_commit_chips": 0,
        "actor_stack_chips": 10,
        "min_raise_to_chips": None,
        "max_raise_to_chips": None,
        "legal_actions_digest": {"alg": "sha256", "hex": "0" * 64},
        "observation_digest": {"alg": "sha256", "hex": "0" * 64},
    }
    with pytest.raises(SnapshotError) as exc:
        validate_snapshot_min_fields(bad_street, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    bad_types = dict(bad_street, street="PREFLOP", actor_seat=True)
    with pytest.raises(SnapshotError) as exc:
        validate_snapshot_min_fields(bad_types, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad_minmax = dict(bad_street, street="PREFLOP", min_raise_to_chips=4, max_raise_to_chips=None)
    with pytest.raises(SnapshotError) as exc:
        validate_snapshot_min_fields(bad_minmax, strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"

    bad_minmax2 = dict(bad_street, street="PREFLOP", min_raise_to_chips=True, max_raise_to_chips=4)
    with pytest.raises(SnapshotError) as exc:
        validate_snapshot_min_fields(bad_minmax2, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    bad_min_gt_max = dict(bad_street, street="PREFLOP", min_raise_to_chips=10, max_raise_to_chips=4)
    with pytest.raises(SnapshotError) as exc:
        validate_snapshot_min_fields(bad_min_gt_max, strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"


def test_mw_context_digest_rejects_unsupported_rung() -> None:
    with pytest.raises(MWContextError) as exc:
        mw_context_digest(
            state_hash="0" * 64,
            mw_ladder_id="1" * 64,
            rung_id="not-a-rung",
            belief_digest_or_none=None,
            mw_risk_spec_id_or_none=None,
            strict_mode=True,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"


def test_legal_actions_and_digest_rejects_invalid_snapshot_types() -> None:
    base = {
        "to_call_chips": 0,
        "actor_commit_chips": 0,
        "min_raise_to_chips": None,
        "max_raise_to_chips": None,
    }

    with pytest.raises(LegalActionsError) as exc:
        legal_actions_and_digest(dict(base, to_call_chips=True), action_bins=ACTION_BINS, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(LegalActionsError) as exc:
        legal_actions_and_digest(dict(base, to_call_chips="0"), action_bins=ACTION_BINS, strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(LegalActionsError) as exc:
        legal_actions_and_digest(dict(base, min_raise_to_chips=4, max_raise_to_chips=None), action_bins=ACTION_BINS, strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(LegalActionsError) as exc:
        legal_actions_and_digest(dict(base, min_raise_to_chips=10, max_raise_to_chips=4), action_bins=ACTION_BINS, strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"


def test_env_internal_helpers_cover_errors_and_branches() -> None:
    with pytest.raises(env.EnvironmentError) as exc:
        env._rotate_seats_clockwise([1, 2], button_seat=3)
    assert exc.value.code == "BUTTON_NOT_IN_HAND"

    with pytest.raises(env.EnvironmentError) as exc:
        env._as_int(True, field="x")
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(env.EnvironmentError) as exc:
        env._as_str(1, field="x")
    assert exc.value.code == "TYPE_ERROR"

    assert env._derive_action_kind(target_total_commit_chips=10, actor_commit_chips=10, to_call_chips=0) == "CHECK"
    assert env._derive_action_kind(target_total_commit_chips=12, actor_commit_chips=10, to_call_chips=0) == "BET"
    assert env._derive_action_kind(target_total_commit_chips=10, actor_commit_chips=10, to_call_chips=2) == "FOLD"
    assert env._derive_action_kind(target_total_commit_chips=12, actor_commit_chips=10, to_call_chips=2) == "CALL"
    assert env._derive_action_kind(target_total_commit_chips=13, actor_commit_chips=10, to_call_chips=2) == "RAISE"

    with pytest.raises(env.EnvironmentError) as exc:
        env._derive_action_kind(target_total_commit_chips=11, actor_commit_chips=10, to_call_chips=2)
    assert exc.value.code == "VALUE_ERROR"

    snap_call = {"actor_commit_chips": 10, "to_call_chips": 2}
    with pytest.raises(env.EnvironmentError) as exc:
        env._canonicalize_action({"kind": "BAD", "target_total_commit_chips": 10}, snapshot=snap_call, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(env.EnvironmentError) as exc:
        env._canonicalize_action({"kind": "CALL", "target_total_commit_chips": 10}, snapshot={"actor_commit_chips": 10, "to_call_chips": 0}, strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(env.EnvironmentError) as exc:
        env._canonicalize_action({"kind": "CHECK", "target_total_commit_chips": 10}, snapshot=snap_call, strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(env.EnvironmentError) as exc:
        env._canonicalize_action({"kind": "FOLD", "target_total_commit_chips": 10}, snapshot={"actor_commit_chips": 10, "to_call_chips": 0}, strict_mode=True)
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(env.EnvironmentError) as exc:
        env._canonicalize_action({"kind": "CALL", "target_total_commit_chips": 11}, snapshot=snap_call, strict_mode=True)
    assert exc.value.code == "CANONICALIZE_TARGET_MISMATCH"

    canonical, reason = env._canonicalize_action({"kind": "CALL", "target_total_commit_chips": 11}, snapshot=snap_call, strict_mode=False)
    assert canonical == {"kind": "CALL", "target_total_commit_chips": 12}
    assert reason == "illegal_action"

    with pytest.raises(env.EnvironmentError) as exc:
        env._canonicalize_action({"kind": "RAISE", "target_total_commit_chips": 12}, snapshot={"actor_commit_chips": 10, "to_call_chips": 0}, strict_mode=True)
    assert exc.value.code == "CANONICALIZE_KIND_MISMATCH"

    canonical2, reason2 = env._canonicalize_action(
        {"kind": "RAISE", "target_total_commit_chips": 12},
        snapshot={"actor_commit_chips": 10, "to_call_chips": 0},
        strict_mode=False,
    )
    assert canonical2 == {"kind": "BET", "target_total_commit_chips": 12}
    assert reason2 == "kind_override"

    with pytest.raises(env.EnvironmentError) as exc:
        env._mapping_trace(
            action_adapter_id="a" * 64,
            mapping_spec_id=None,
            proposed_action={"kind": "CHECK", "target_total_commit_chips": 0},
            executed_action={"kind": "CHECK", "target_total_commit_chips": 0},
            reason_code="bad_reason",
            fallback_mode_or_none=None,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(env.EnvironmentError) as exc:
        env._derived_action(
            executed_action={"kind": "BAD", "target_total_commit_chips": 0},
            snapshot={"actor_commit_chips": 0, "actor_stack_chips": 0, "max_raise_to_chips": None},
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"


def test_env_run_validations_and_ante_paths() -> None:
    with pytest.raises(env.EnvironmentError) as exc:
        _run_env(
            ruleset=_ruleset(),
            starting_stacks_by_seat={1: 10, 2: 10},
            button_seat=1,
            fallback_mode="nope",
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(env.EnvironmentError) as exc:
        _run_env(
            ruleset=dict(_ruleset(), game_kind="OOPS"),
            starting_stacks_by_seat={1: 10, 2: 10},
            button_seat=1,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"

    with pytest.raises(env.EnvironmentError) as exc:
        _run_env(ruleset=_ruleset(), starting_stacks_by_seat={}, button_seat=1)
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(env.EnvironmentError) as exc:
        _run_env(ruleset=_ruleset(), starting_stacks_by_seat={1: 10}, button_seat=1)
    assert exc.value.code == "VALUE_ERROR"

    with pytest.raises(env.EnvironmentError) as exc:
        _run_env(ruleset=_ruleset(), starting_stacks_by_seat={"1": 10, "2": 10}, button_seat="1")
    assert exc.value.code == "TYPE_ERROR"

    def check_call_policy(ctx: dict) -> dict:
        snap = ctx["snapshot"]
        if int(snap["to_call_chips"]) == 0:
            return {"kind": "CHECK", "target_total_commit_chips": int(snap["actor_commit_chips"])}
        return {"kind": "CALL", "target_total_commit_chips": int(snap["actor_commit_chips"]) + int(snap["to_call_chips"])}

    objs = _run_env(
        ruleset=_ruleset(ante={"kind": "uniform", "ante_chips": 1}),
        starting_stacks_by_seat={1: 20, 2: 20},
        button_seat=1,
        policy=check_call_policy,
    )
    assert any(o.get("event") == "ForcedBets" and o.get("kind") == "ante" for o in objs)

    objs2 = _run_env(
        ruleset=_ruleset(ante={"kind": "by_seat", "by_seat_ante_chips": {"1": 1, "2": 2}}),
        starting_stacks_by_seat={1: 30, 2: 30},
        button_seat=1,
        policy=check_call_policy,
    )
    assert any(o.get("event") == "ForcedBets" and o.get("kind") == "ante" for o in objs2)

    with pytest.raises(ContractKitError) as exc:
        _run_env(
            ruleset=_ruleset(ante={"kind": "by_seat", "by_seat_ante_chips": {"x": 1}}),
            starting_stacks_by_seat={1: 20, 2: 20},
            button_seat=1,
            policy=check_call_policy,
        )
    assert exc.value.code == "SEAT_KEY_NOT_DECIMAL"


def test_env_policy_contract_enforced() -> None:
    with pytest.raises(env.EnvironmentError) as exc:
        _run_env(ruleset=_ruleset(), starting_stacks_by_seat={1: 20, 2: 20}, button_seat=1, policy=lambda _ctx: "bad")
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(env.EnvironmentError) as exc:
        _run_env(
            ruleset=_ruleset(),
            starting_stacks_by_seat={1: 20, 2: 20},
            button_seat=1,
            policy=lambda _ctx: {"kind": "BAD", "target_total_commit_chips": 0},
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"
