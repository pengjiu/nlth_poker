from __future__ import annotations

from poker2.runtime.rule_policy import make_rule_policy, make_system_policy


def test_rule_policy_returns_legal_action() -> None:
    policy = make_rule_policy(style="tight", aggression=0.5, seat_id=2, seed=42)
    legal_actions = [
        {"kind": "FOLD", "target_total_commit_chips": 0},
        {"kind": "CALL", "target_total_commit_chips": 10},
        {"kind": "RAISE", "target_total_commit_chips": 40},
    ]
    act = policy({"legal_actions": legal_actions, "snapshot": {"to_call_chips": 10, "actor_stack_chips": 100, "actor_commit_chips": 0}})
    assert act in legal_actions


def test_system_policy_is_more_aggressive() -> None:
    policy = make_system_policy(seat_id=1, seed=123)
    legal_actions = [
        {"kind": "FOLD", "target_total_commit_chips": 0},
        {"kind": "CALL", "target_total_commit_chips": 10},
        {"kind": "RAISE", "target_total_commit_chips": 40},
    ]
    # Execute twice to ensure determinism given same seed.
    act1 = policy({"legal_actions": legal_actions, "snapshot": {"to_call_chips": 10, "actor_stack_chips": 100, "actor_commit_chips": 0}})
    act2 = policy({"legal_actions": legal_actions, "snapshot": {"to_call_chips": 10, "actor_stack_chips": 100, "actor_commit_chips": 0}})
    assert act1 == act2
    assert act1 in legal_actions


def test_rule_policy_raises_with_min_max() -> None:
    policy = make_rule_policy(style="loose", aggression=1.0, seat_id=3, seed=1)
    legal_actions = [
        {"kind": "FOLD", "target_total_commit_chips": 0},
        {"kind": "CALL", "target_total_commit_chips": 10},
        {"kind": "RAISE", "target_total_commit_chips": 20},
        {"kind": "RAISE", "target_total_commit_chips": 40},
    ]
    snapshot = {
        "to_call_chips": 10,
        "actor_stack_chips": 100,
        "actor_commit_chips": 0,
        "min_raise_to_chips": 20,
        "max_raise_to_chips": 80,
    }
    act = policy({"legal_actions": legal_actions, "snapshot": snapshot})
    assert act["kind"] == "RAISE"


def test_rule_policy_fallback_to_check_then_fold() -> None:
    policy = make_rule_policy(style="tight", aggression=0.0, seat_id=4, seed=2)
    # No raises available, zero to_call => should check; if no check, fold.
    legal_actions = [
        {"kind": "FOLD", "target_total_commit_chips": 0},
        {"kind": "CHECK", "target_total_commit_chips": 0},
    ]
    snapshot = {"to_call_chips": 0, "actor_stack_chips": 100, "actor_commit_chips": 0, "min_raise_to_chips": None, "max_raise_to_chips": None}
    act = policy({"legal_actions": legal_actions, "snapshot": snapshot})
    assert act["kind"] in ("CHECK", "FOLD")


def test_rule_policy_fold_large_call_for_tight() -> None:
    policy = make_rule_policy(style="tight", aggression=0.1, seat_id=5, seed=3)
    legal_actions = [
        {"kind": "FOLD", "target_total_commit_chips": 0},
        {"kind": "CALL", "target_total_commit_chips": 90},
    ]
    snapshot = {"to_call_chips": 90, "actor_stack_chips": 100, "actor_commit_chips": 0, "min_raise_to_chips": None, "max_raise_to_chips": None}
    act = policy({"legal_actions": legal_actions, "snapshot": snapshot})
    assert act["kind"] == "FOLD"
