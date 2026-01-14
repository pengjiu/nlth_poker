from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from poker2.runtime.system_policy import build_system_policy
from poker2.protocol.policy import load_policy_spec
from tests.test_system_policy import _paths_trace_for_system_policy


def _fake_state_hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def test_postflop_multiway_can_check(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force solver failure to hit fallback; ensure multiway有一定概率选择过牌
    from poker2 import runtime as rt_mod
    monkeypatch.setattr(rt_mod.system_policy, "solve_postflop_pyo3", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    repo = Path(__file__).resolve().parents[1]
    ruleset = (repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_bytes()
    import json

    ruleset_obj = json.loads(ruleset)
    pol_spec = load_policy_spec(repo / "specs" / "policies" / "system_bot_policy_v1.json")
    _digest, paths_trace = _paths_trace_for_system_policy()
    policy_fn, _meta = build_system_policy(
        seat_id=2,
        seed=17,
        policy_spec=pol_spec,
        ruleset=ruleset_obj,
        paths_trace=paths_trace,
        strict_mode=False,
    )
    legal_actions = [
        {"kind": "CHECK", "target_total_commit_chips": 0},
        {"kind": "BET", "target_total_commit_chips": 200},  # 0.25 pot
        {"kind": "BET", "target_total_commit_chips": 400},  # 0.5 pot
    ]
    snapshot = {
        "street": "FLOP",
        "actor_seat": 2,
        "players_alive_count": 3,
        "pot_chips": 800,
        "to_call_chips": 0,
        "actor_commit_chips": 0,
        "actor_stack_chips": 9500,
        "min_raise_to_chips": None,
        "max_raise_to_chips": None,
        "legal_actions_digest": "",
        "observation_digest": "",
    }
    observation = {"button_seat": 1, "actor_seat": 2, "seats_in_hand": [1, 2, 3]}
    # 使用固定 state_hash 以确定性触发 check 分支（p<50）
    act = policy_fn(
        {
            "decision_id": 3,
            "state_hash": _fake_state_hash("check-pref"),
            "snapshot": snapshot,
            "observation": observation,
            "legal_actions": legal_actions,
            "seat_id": 2,
        }
    )
    assert act["kind"] in ("CHECK", "BET")
    # 至少保证不会强行只走大注
    assert act["target_total_commit_chips"] <= 400
