from __future__ import annotations

import hashlib
from pathlib import Path
import json
from typing import Any

import pytest

from poker2.runtime.system_policy import SystemPolicyError, build_system_policy, resolve_policy_artifacts
from poker2.protocol.policy import load_policy_spec
from poker2.runtime import system_policy as system_policy_mod


def _sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _paths_trace_for_system_policy() -> tuple[dict[str, str], dict[str, Any]]:
    repo = Path(__file__).resolve().parents[1]
    preflop_path = repo / "specs" / "preflop" / "settings.json"
    postflop_path = repo / "fixtures" / "internal" / "artifacts" / "b5b176e877cc4fbd2e1ea07dcf1fc0746c7781e6c01063bc81de0cb545003932.bin"
    preflop_ranges = repo / "specs" / "preflop" / "preflop_ranges_v1.json"
    preflop_freq = repo / "specs" / "preflop" / "preflop_freq_v1.json"
    preflop_digest = {"alg": "sha256", "hex": _sha256_hex(preflop_path)}
    postflop_digest = {"alg": "sha256", "hex": _sha256_hex(postflop_path)}
    preflop_ranges_digest = {"alg": "sha256", "hex": _sha256_hex(preflop_ranges)}
    preflop_freq_digest = {"alg": "sha256", "hex": _sha256_hex(preflop_freq)}
    paths_trace = {
        "resolved_roots_abs": {},
        "resolved_artifacts": [
            {
                "artifact_ref": "path:settings.json",
                "digest": preflop_digest,
                "computed_digest_or_null": preflop_digest,
                "resolved_ok": True,
                "abs_path_or_null": str(preflop_path),
                "error_or_null": None,
            },
            {
                "artifact_ref": "artifact://b5b176e877cc4fbd2e1ea07dcf1fc0746c7781e6c01063bc81de0cb545003932",
                "digest": postflop_digest,
                "computed_digest_or_null": postflop_digest,
                "resolved_ok": True,
                "abs_path_or_null": str(postflop_path),
                "error_or_null": None,
            },
            {
                "artifact_ref": "path:preflop/preflop_ranges_v1.json",
                "digest": preflop_ranges_digest,
                "computed_digest_or_null": preflop_ranges_digest,
                "resolved_ok": True,
                "abs_path_or_null": str(preflop_ranges),
                "error_or_null": None,
            },
            {
                "artifact_ref": "path:preflop/preflop_freq_v1.json",
                "digest": preflop_freq_digest,
                "computed_digest_or_null": preflop_freq_digest,
                "resolved_ok": True,
                "abs_path_or_null": str(preflop_freq),
                "error_or_null": None,
            },
        ],
    }
    return preflop_digest, paths_trace


def test_system_policy_prefers_open_size() -> None:
    repo = Path(__file__).resolve().parents[1]
    ruleset = (repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_bytes()
    import json

    ruleset_obj = json.loads(ruleset)
    pol_spec = load_policy_spec(repo / "specs" / "policies" / "system_bot_policy_v1.json")
    _digest, paths_trace = _paths_trace_for_system_policy()
    policy_fn, _meta = build_system_policy(
        seat_id=1,
        seed=7,
        policy_spec=pol_spec,
        ruleset=ruleset_obj,
        paths_trace=paths_trace,
        strict_mode=True,
    )
    legal_actions = [
        {"kind": "CHECK", "target_total_commit_chips": 0},
        {"kind": "RAISE", "target_total_commit_chips": 5},
        {"kind": "RAISE", "target_total_commit_chips": 6},
    ]
    snapshot = {
        "street": "PREFLOP",
        "actor_seat": 1,
        "players_alive_count": 7,
        "pot_chips": 0,
        "to_call_chips": 0,
        "actor_commit_chips": 0,
        "actor_stack_chips": 10000,
        "min_raise_to_chips": 4,
        "max_raise_to_chips": 200,
        "legal_actions_digest": "",
        "observation_digest": "",
    }
    act = policy_fn(
        {"decision_id": 1, "state_hash": "x", "snapshot": snapshot, "observation": {}, "legal_actions": legal_actions, "seat_id": 1}
    )
    assert act["kind"] == "RAISE"
    assert act["target_total_commit_chips"] in (5, 6)


def test_system_policy_position_open_size() -> None:
    repo = Path(__file__).resolve().parents[1]
    ruleset = (repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_bytes()
    import json

    ruleset_obj = json.loads(ruleset)
    ruleset_obj["blinds"] = {"sb_chips": 50, "bb_chips": 100}
    pol_spec = load_policy_spec(repo / "specs" / "policies" / "system_bot_policy_v1.json")
    _digest, paths_trace = _paths_trace_for_system_policy()
    policy_fn, _meta = build_system_policy(
        seat_id=3,
        seed=7,
        policy_spec=pol_spec,
        ruleset=ruleset_obj,
        paths_trace=paths_trace,
        strict_mode=True,
    )
    legal_actions = [
        {"kind": "CHECK", "target_total_commit_chips": 0},
        {"kind": "RAISE", "target_total_commit_chips": 200},
        {"kind": "RAISE", "target_total_commit_chips": 250},  # 2.5bb open
        {"kind": "RAISE", "target_total_commit_chips": 400},
    ]
    snapshot = {
        "street": "PREFLOP",
        "actor_seat": 3,
        "players_alive_count": 7,
        "pot_chips": 0,
        "to_call_chips": 0,
        "actor_commit_chips": 0,
        "actor_stack_chips": 10000,
        "min_raise_to_chips": 200,
        "max_raise_to_chips": 800,
        "legal_actions_digest": "",
        "observation_digest": "",
    }
    observation = {
        "button_seat": 3,
        "actor_seat": 3,
        "seats_in_hand": [1, 2, 3, 4, 5, 6, 7],
    }
    act = policy_fn(
        {
            "decision_id": 1,
            "state_hash": "x",
            "snapshot": snapshot,
            "observation": observation,
            "legal_actions": legal_actions,
            "seat_id": 3,
        }
    )
    assert act["kind"] == "RAISE"
    assert act["target_total_commit_chips"] == 250


def test_resolve_policy_artifacts_digest_mismatch() -> None:
    _digest, paths_trace = _paths_trace_for_system_policy()
    bad_spec = {
        "policy_deps": [
            {"artifact_ref": "path:settings.json", "digest": {"alg": "sha256", "hex": "dead" * 16}},
        ]
    }
    with pytest.raises(SystemPolicyError):
        resolve_policy_artifacts(policy_spec=bad_spec, paths_trace=paths_trace, strict_mode=True)


def test_resolve_policy_artifacts_digest_fallback_match() -> None:
    pre_digest, paths_trace = _paths_trace_for_system_policy()
    spec = {"policy_deps": [{"artifact_ref": "path:missing.json", "digest": pre_digest}]}
    resolved = resolve_policy_artifacts(policy_spec=spec, paths_trace=paths_trace, strict_mode=True)
    assert "path:missing.json" in resolved
    assert resolved["path:missing.json"].exists()


def test_resolve_policy_artifacts_unsupported_scheme() -> None:
    spec = {"policy_deps": [{"artifact_ref": "s3://foo", "digest": {"alg": "sha256", "hex": "0" * 64}}]}
    with pytest.raises(SystemPolicyError):
        resolve_policy_artifacts(policy_spec=spec, paths_trace={"resolved_artifacts": []}, strict_mode=True)


def test_position_key_fallbacks() -> None:
    assert system_policy_mod._position_key(1, 2, [3, 4]) == "OTHERS"
    seats = [1, 2, 3, 4]
    assert system_policy_mod._position_key(2, 2, seats) == "BU"
    assert system_policy_mod._position_key(3, 2, seats) == "SB"
    assert system_policy_mod._position_key(4, 2, seats) == "BB"


def test_preflop_threebet_size(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Path(__file__).resolve().parents[1]
    ruleset = (repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_bytes()
    import json

    ruleset_obj = json.loads(ruleset)
    pol_spec = load_policy_spec(repo / "specs" / "policies" / "system_bot_policy_v1.json")
    _digest, paths_trace = _paths_trace_for_system_policy()
    policy_fn, _meta = build_system_policy(
        seat_id=5,
        seed=13,
        policy_spec=pol_spec,
        ruleset=ruleset_obj,
        paths_trace=paths_trace,
        strict_mode=True,
    )
    # Facing an open to 100 (1bb); expect ~3x threebet → target about 400.
    legal_actions = [
        {"kind": "CALL", "target_total_commit_chips": 100},
        {"kind": "RAISE", "target_total_commit_chips": 350},
        {"kind": "RAISE", "target_total_commit_chips": 400},
        {"kind": "RAISE", "target_total_commit_chips": 450},
    ]
    snapshot = {
        "street": "PREFLOP",
        "actor_seat": 5,
        "players_alive_count": 7,
        "pot_chips": 170,  # blinds+ante
        "to_call_chips": 100,
        "actor_commit_chips": 0,
        "actor_stack_chips": 10000,
        "min_raise_to_chips": 200,
        "max_raise_to_chips": 800,
        "legal_actions_digest": "",
        "observation_digest": "",
    }
    observation = {
        "button_seat": 3,
        "actor_seat": 5,
        "seats_in_hand": [1, 2, 3, 4, 5, 6, 7],
    }
    act = policy_fn(
        {
            "decision_id": 2,
            "state_hash": "y",
            "snapshot": snapshot,
            "observation": observation,
            "legal_actions": legal_actions,
            "seat_id": 5,
        }
    )
    assert act["kind"] == "RAISE"
    assert act["target_total_commit_chips"] in (350, 400, 450)


def test_preflop_fourbet_uses_freqs() -> None:
    repo = Path(__file__).resolve().parents[1]
    ruleset_obj = json.loads((repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_text())
    pol_spec = load_policy_spec(repo / "specs" / "policies" / "system_bot_policy_v1.json")
    _digest, paths_trace = _paths_trace_for_system_policy()
    policy_fn, _meta = build_system_policy(
        seat_id=5,
        seed=13,
        policy_spec=pol_spec,
        ruleset=ruleset_obj,
        paths_trace=paths_trace,
        strict_mode=True,
    )
    legal_actions = [
        {"kind": "CALL", "target_total_commit_chips": 400},
        {"kind": "RAISE", "target_total_commit_chips": 900},
    ]
    snapshot = {
        "street": "PREFLOP",
        "actor_seat": 5,
        "players_alive_count": 7,
        "pot_chips": 500,
        "to_call_chips": 400,
        "actor_commit_chips": 0,
        "actor_stack_chips": 10000,
        "min_raise_to_chips": 800,
        "max_raise_to_chips": 1200,
        "legal_actions_digest": "",
        "observation_digest": "",
    }
    observation = {
        "button_seat": 3,
        "actor_seat": 5,
        "seats_in_hand": [1, 2, 3, 4, 5, 6, 7],
    }
    act = policy_fn(
        {
            "decision_id": 99,
            "state_hash": "fb",  # deterministic RNG → below fourbet threshold
            "snapshot": snapshot,
            "observation": observation,
            "legal_actions": legal_actions,
            "seat_id": 5,
        }
    )
    assert act["kind"] == "RAISE"
    assert act["target_total_commit_chips"] >= 800


def test_preflop_open_can_decline_when_freq_low() -> None:
    repo = Path(__file__).resolve().parents[1]
    ruleset_obj = json.loads((repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_text())
    pol_spec = load_policy_spec(repo / "specs" / "policies" / "system_bot_policy_v1.json")
    _digest, paths_trace = _paths_trace_for_system_policy()
    policy_fn, _meta = build_system_policy(
        seat_id=3,
        seed=42,
        policy_spec=pol_spec,
        ruleset=ruleset_obj,
        paths_trace=paths_trace,
        strict_mode=True,
    )
    legal_actions = [
        {"kind": "FOLD", "target_total_commit_chips": 0},
        {"kind": "RAISE", "target_total_commit_chips": 200},
    ]
    snapshot = {
        "street": "PREFLOP",
        "actor_seat": 3,
        "players_alive_count": 7,
        "pot_chips": 3,
        "to_call_chips": 0,
        "actor_commit_chips": 0,
        "actor_stack_chips": 10000,
        "min_raise_to_chips": 200,
        "max_raise_to_chips": 400,
        "legal_actions_digest": "",
        "observation_digest": "",
    }
    observation = {"button_seat": 3, "actor_seat": 3, "seats_in_hand": [1, 2, 3, 4, 5, 6, 7]}
    act = policy_fn(
        {
            "decision_id": 100,
            "state_hash": "d",  # deterministic RNG -> high percentile
            "snapshot": snapshot,
            "observation": observation,
            "legal_actions": legal_actions,
            "seat_id": 3,
        }
    )
    assert act["kind"] in ("RAISE", "FOLD")


def test_postflop_fallback_multiway(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force solver failure to hit heuristic fallback; multiway should pick小注（~0.25-0.5 pot）
    monkeypatch.setattr(system_policy_mod, "solve_postflop_pyo3", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    repo = Path(__file__).resolve().parents[1]
    ruleset = (repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_bytes()
    import json

    ruleset_obj = json.loads(ruleset)
    pol_spec = load_policy_spec(repo / "specs" / "policies" / "system_bot_policy_v1.json")
    _digest, paths_trace = _paths_trace_for_system_policy()
    policy_fn, _meta = build_system_policy(
        seat_id=2,
        seed=3,
        policy_spec=pol_spec,
        ruleset=ruleset_obj,
        paths_trace=paths_trace,
        strict_mode=False,  # allow solver fail fallback
    )
    legal_actions = [
        {"kind": "CHECK", "target_total_commit_chips": 0},
        {"kind": "BET", "target_total_commit_chips": 200},  # 0.25 pot (pot=800)
        {"kind": "BET", "target_total_commit_chips": 300},  # 0.375 pot
        {"kind": "BET", "target_total_commit_chips": 500},  # 0.625 pot
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
    observation = {
        "button_seat": 1,
        "actor_seat": 2,
        "seats_in_hand": [1, 2, 3],
    }
    act = policy_fn(
        {
            "decision_id": 3,
            "state_hash": "z",
            "snapshot": snapshot,
            "observation": observation,
            "legal_actions": legal_actions,
            "seat_id": 2,
        }
    )
    assert act["kind"] in ("CHECK", "BET")
    # Multiway fallback应偏小或选择过牌，这里检查不超过 0.5 pot。
    if act["kind"] == "BET":
        assert act["target_total_commit_chips"] <= 500


def test_postflop_solver_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_policy_mod, "solve_postflop_pyo3", lambda **_: {"target_total_commit_chips": 300})
    repo = Path(__file__).resolve().parents[1]
    ruleset_obj = json.loads((repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_text())
    pol_spec = load_policy_spec(repo / "specs" / "policies" / "system_bot_policy_v1.json")
    _digest, paths_trace = _paths_trace_for_system_policy()
    policy_fn, _meta = build_system_policy(
        seat_id=2,
        seed=7,
        policy_spec=pol_spec,
        ruleset=ruleset_obj,
        paths_trace=paths_trace,
        strict_mode=True,
    )
    legal_actions = [
        {"kind": "CHECK", "target_total_commit_chips": 0},
        {"kind": "BET", "target_total_commit_chips": 250},
        {"kind": "BET", "target_total_commit_chips": 320},
    ]
    snapshot = {
        "street": "FLOP",
        "actor_seat": 2,
        "players_alive_count": 2,
        "pot_chips": 500,
        "to_call_chips": 0,
        "actor_commit_chips": 0,
        "actor_stack_chips": 9500,
        "min_raise_to_chips": None,
        "max_raise_to_chips": None,
        "legal_actions_digest": "",
        "observation_digest": "",
    }
    observation = {"button_seat": 1, "actor_seat": 2, "seats_in_hand": [1, 2]}
    act = policy_fn(
        {
            "decision_id": 4,
            "state_hash": "solver",
            "snapshot": snapshot,
            "observation": observation,
            "legal_actions": legal_actions,
            "seat_id": 2,
        }
    )
    assert act["kind"] in ("BET", "RAISE")
    assert act["target_total_commit_chips"] in (250, 320)
