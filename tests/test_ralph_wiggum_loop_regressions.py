from __future__ import annotations

import json
import math
from pathlib import Path

from tools import ralph_wiggum_loop as loop


def test_worker_missing_action_ticket_does_not_create_cycle_dir(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    state_file = tmp_path / "state.json"
    state_file.write_text("{}", encoding="utf-8")
    action_path = tmp_path / "missing_next_action.json"

    monkeypatch.setattr(loop, "NEXT_ACTION_PATH", action_path)
    monkeypatch.setattr(loop, "EVENT_TRACE_LOG", tmp_path / "events.ndjson")

    parser = loop._build_parser()
    args = parser.parse_args(
        [
            "--worker",
            "--cycle",
            "77",
            "--state-file",
            str(state_file),
            "--runs-root",
            str(runs_root),
            "--quiet",
        ]
    )

    rc = loop._run_worker(args)
    assert rc == loop.LOCK_HELD_EXIT_CODE
    assert list(runs_root.glob("cycle_077_*")) == []


def test_dynamic_llm_review_policy_triggers_after_full_gate_fail_streak() -> None:
    policy = loop._llm_review_policy(
        base_require_llm_action_ticket=False,
        recent_reasons=["full_gate_fail", "full_gate_fail"],
        no_improve_streak=4,
        full_gate_fail_streak=2,
        min_no_improve_streak=2,
        fail_open=False,
    )

    assert policy["effective_required"] is True
    assert policy["dynamic_triggered"] is True
    assert policy["reason"] == "full_gate_fail_streak"
    assert policy["recent"]["trailing_full_gate_fail_streak"] == 2
    assert policy["recent"]["recent_full_gate_fail_count"] == 2


def test_action_ticket_plan_only_passes_without_patch_files() -> None:
    ticket = loop._validate_action_ticket(
        {
            "source_cycle": 76,
            "mechanism_plan": [{"mechanism": "oop_mw_defense_clamp", "scale": 1.0}],
            "knob_plan": [],
            "focus_metric": loop.FOCUS_SUPPORT_FOCUS_METRIC,
        },
        cycle=77,
    )

    assert ticket["pass"] is True
    assert ticket["reason"] == "ok_plan_only"
    assert ticket["plan_only"] is True
    assert ticket["patched_files"] == []


def test_action_ticket_rejects_shared_runtime_patch_by_default() -> None:
    ticket = loop._validate_action_ticket(
        {
            "source_cycle": 76,
            "change_applied": True,
            "patched_files": ["poker2/runtime/system_policy.py"],
            "mechanism_plan": [{"mechanism": "oop_mw_defense_clamp", "scale": 1.0}],
            "focus_metric": loop.FOCUS_SUPPORT_FOCUS_METRIC,
        },
        cycle=77,
    )

    assert ticket["pass"] is False
    assert ticket["reason"] == "shared_runtime_patch_forbidden"
    assert ticket["touched_shared_runtime_files"] == ["poker2/runtime/system_policy.py"]


def test_dynamic_llm_review_policy_ignores_non_consecutive_full_gate_fails() -> None:
    policy = loop._llm_review_policy(
        base_require_llm_action_ticket=False,
        recent_reasons=["full_gate_fail", "quick_gate_no_improvement", "full_gate_fail"],
        no_improve_streak=9,
        full_gate_fail_streak=2,
        min_no_improve_streak=2,
        fail_open=False,
    )

    assert policy["effective_required"] is False
    assert policy["dynamic_triggered"] is False
    assert policy["reason"] is None
    assert policy["recent"]["trailing_full_gate_fail_streak"] == 1
    assert policy["recent"]["recent_full_gate_fail_count"] == 2


def test_worker_dynamic_llm_review_requires_ticket_after_full_gate_fail_streak(
    tmp_path: Path, monkeypatch
) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "no_improve_streak": 5,
                "quick_gate_reason_history": ["full_gate_fail", "full_gate_fail"],
            }
        ),
        encoding="utf-8",
    )
    action_path = tmp_path / "missing_next_action.json"

    monkeypatch.setattr(loop, "NEXT_ACTION_PATH", action_path)
    monkeypatch.setattr(loop, "EVENT_TRACE_LOG", tmp_path / "events.ndjson")

    parser = loop._build_parser()
    args = parser.parse_args(
        [
            "--worker",
            "--cycle",
            "77",
            "--state-file",
            str(state_file),
            "--runs-root",
            str(runs_root),
            "--no-require-llm-action-ticket",
            "--llm-review-full-gate-fail-streak",
            "2",
            "--llm-review-min-no-improve-streak",
            "2",
            "--no-llm-review-fail-open",
            "--quiet",
        ]
    )

    rc = loop._run_worker(args)
    assert rc == loop.LOCK_HELD_EXIT_CODE
    assert list(runs_root.glob("cycle_077_*")) == []


def test_dynamic_llm_review_policy_can_fail_open() -> None:
    policy = loop._llm_review_policy(
        base_require_llm_action_ticket=False,
        recent_reasons=["full_gate_fail", "full_gate_fail"],
        no_improve_streak=4,
        full_gate_fail_streak=2,
        min_no_improve_streak=2,
        fail_open=True,
    )

    assert policy["effective_required"] is True
    assert policy["dynamic_triggered"] is True
    assert policy["fail_open_enabled"] is True


def test_propose_candidates_adds_robustness_recovery_lane_after_full_gate_fail_streak() -> None:
    base_params = {
        key: low + max(1, (high - low) // 2)
        for key, _delta, low, high in loop.KNOB_SPECS
    }
    mechanism_policy = loop._mechanism_priority_policy(
        no_improve_streak=6,
        recent_reasons=["full_gate_fail", "full_gate_fail"],
        action_plan=None,
        mechanism_min_share=loop.DEFAULT_MECHANISM_MIN_SHARE,
        mechanism_priority_streak=loop.DEFAULT_MECHANISM_PRIORITY_STREAK,
        mechanism_only_streak=loop.DEFAULT_MECHANISM_ONLY_STREAK,
    )

    candidates = loop._propose_candidates(
        base_params,
        cycle=154,
        focus_metric=loop.FOCUS_SUPPORT_FOCUS_METRIC,
        action_plan=None,
        no_improve_streak=6,
        max_candidates=6,
        mechanism_policy=mechanism_policy,
    )

    recovery = [
        row
        for row in candidates
        if row.get("origin") == "robustness_recovery" and row.get("mechanism") == "counter_aggression_stability"
    ]
    assert recovery


def test_propose_candidates_adds_spot_policy_variants_for_focus_metric() -> None:
    base_params = {
        key: low + max(1, (high - low) // 2)
        for key, _delta, low, high in loop.KNOB_SPECS
    }
    mechanism_policy = loop._mechanism_priority_policy(
        no_improve_streak=4,
        recent_reasons=["full_gate_fail", "full_gate_fail"],
        action_plan=None,
        mechanism_min_share=loop.DEFAULT_MECHANISM_MIN_SHARE,
        mechanism_priority_streak=loop.DEFAULT_MECHANISM_PRIORITY_STREAK,
        mechanism_only_streak=loop.DEFAULT_MECHANISM_ONLY_STREAK,
    )

    candidates = loop._propose_candidates(
        base_params,
        cycle=193,
        focus_metric=loop.FOCUS_SUPPORT_FOCUS_METRIC,
        action_plan=None,
        no_improve_streak=4,
        max_candidates=6,
        mechanism_policy=mechanism_policy,
    )

    spot_candidates = [row for row in candidates if bool(row.get("spot_policy_variant"))]
    assert spot_candidates
    first = spot_candidates[0]
    assert isinstance(first.get("spot_policy"), dict)
    assert str(first.get("spot_policy_ref")).startswith("path:specs/spot_policies/generated/")
    params = first.get("params")
    assert isinstance(params, dict)
    assert params.get("spot_policy_ref") == first.get("spot_policy_ref")
    assert params.get("spot_policy_digest") == first.get("spot_policy_digest")


def test_spot_gate_blocks_spot_candidate_without_local_evidence() -> None:
    gate = loop._spot_gate_eval(
        focus_metric=loop.FOCUS_SUPPORT_FOCUS_METRIC,
        spot_policy_variant=True,
        focus_metric_delta=0.0,
        support_hits_delta=0,
        support_hands_delta=0,
    )

    assert gate["applicable"] is True
    assert gate["pass"] is False
    assert gate["reason"] == "no_spot_effect"


def test_materialize_policy_writes_generated_spot_policy_artifact(tmp_path: Path, monkeypatch) -> None:
    bundle = loop._resolve_policy_bundle(loop.DEFAULT_TRIAL_LABEL)
    policies_dir = tmp_path / "specs" / "policies"
    policy_params_dir = tmp_path / "specs" / "policy_params"
    spot_dir = tmp_path / "specs" / "spot_policies"
    generated_dir = spot_dir / "generated"
    policies_dir.mkdir(parents=True, exist_ok=True)
    policy_params_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(loop, "ROOT", tmp_path)
    monkeypatch.setattr(loop, "POLICIES_DIR", policies_dir)
    monkeypatch.setattr(loop, "POLICY_PARAMS_DIR", policy_params_dir)
    monkeypatch.setattr(loop, "SPOT_POLICIES_DIR", spot_dir)
    monkeypatch.setattr(loop, "GENERATED_SPOT_POLICIES_DIR", generated_dir)

    spot_policy = json.loads(
        (Path(__file__).resolve().parents[1] / "specs" / "spot_policies" / "facing_y_turnriver_high_price_v1.json").read_text(
            encoding="utf-8"
        )
    )
    effective_params, spot_ref, spot_digest = loop._candidate_system_params(
        bundle["system_params"],
        spot_policy=spot_policy,
    )

    out = loop._materialize_policy(
        policy_label="tmp_loop_trial_spot",
        template_policy_spec=bundle["policy_spec"],
        template_policy_params=bundle["policy_params"],
        system_params=effective_params,
        note_tag="test spot materialize",
        spot_policy=spot_policy,
    )

    assert isinstance(spot_ref, str)
    spot_path = tmp_path / spot_ref.removeprefix("path:")
    assert spot_path.exists()
    assert json.loads(spot_path.read_text(encoding="utf-8")) == spot_policy

    sys_obj = json.loads(Path(out["system_params_path"]).read_text(encoding="utf-8"))
    assert sys_obj["spot_policy_ref"] == spot_ref
    assert sys_obj["spot_policy_digest"] == spot_digest


def test_relative_promotion_gate_accepts_small_step_upgrade_with_better_stability() -> None:
    baseline_metrics = {
        "coinpoker": {
            "tierA_mean": 20.9,
            "tierP_mean": 16.5,
            "pool_weighted_mean": 15.2,
            "br_worst_mean": 9.9,
            "tierA_seed_min": -5.9,
            "tierP_seed_min": -5.7,
            "tierA_std": 24.1,
            "tierP_std": 15.8,
            "tierP_facingY_turnriver_worst_bb100": -1505.0,
        },
        "gg": {
            "tierA_mean": 6.5,
            "tierP_mean": -1.4,
            "tierA_seed_min": -10.4,
            "tierP_seed_min": -19.7,
            "tierA_std": 14.0,
            "tierP_std": 13.7,
        },
    }
    candidate_metrics = {
        "coinpoker": {
            "tierA_mean": 21.1,
            "tierP_mean": 17.9,
            "pool_weighted_mean": 16.1,
            "br_worst_mean": 11.1,
            "tierA_seed_min": -2.0,
            "tierP_seed_min": -1.5,
            "tierA_std": 22.0,
            "tierP_std": 14.4,
            "tierP_facingY_turnriver_worst_bb100": -780.0,
        },
        "gg": {
            "tierA_mean": 9.4,
            "tierP_mean": 2.6,
            "tierA_seed_min": -6.0,
            "tierP_seed_min": -8.0,
            "tierA_std": 12.0,
            "tierP_std": 11.0,
        },
    }

    gate = loop._relative_promotion_gate(
        candidate_metrics=candidate_metrics,
        baseline_metrics=baseline_metrics,
        score_improved=True,
        no_regression_pass=True,
        focus_pass=True,
        candidate_holdout_phase1_mean=-92.0,
        baseline_holdout_phase1_mean=-105.0,
        holdout_required=True,
        holdout_regress_tolerance=0.1,
    )

    assert gate["pass"] is True
    assert gate["strength_pass"] is True
    assert gate["stability_pass"] is True
    assert gate["promotion_score_pass"] is True
    assert gate["scores"]["stability_delta"] > 0.0


def test_relative_promotion_gate_rejects_when_holdout_floor_regresses() -> None:
    gate = loop._relative_promotion_gate(
        candidate_metrics={"coinpoker": {"tierA_mean": 21.0}, "gg": {"tierA_mean": 8.0}},
        baseline_metrics={"coinpoker": {"tierA_mean": 20.0}, "gg": {"tierA_mean": 7.0}},
        score_improved=True,
        no_regression_pass=True,
        focus_pass=True,
        candidate_holdout_phase1_mean=-110.0,
        baseline_holdout_phase1_mean=-105.0,
        holdout_required=True,
        holdout_regress_tolerance=0.1,
    )

    assert gate["pass"] is False
    assert gate["hard_floor_pass"] is False
    holdout_row = next(row for row in gate["hard_floor_rows"] if row["gate"] == "holdout_floor")
    assert holdout_row["pass"] is False


def test_provisional_confirmation_gate_accepts_independent_confirm_sample() -> None:
    baseline_metrics = {
        "coinpoker": {
            "tierA_mean": 20.9,
            "tierP_mean": 16.5,
            "pool_weighted_mean": 15.2,
            "br_worst_mean": 9.9,
            "tierA_seed_min": -5.9,
            "tierP_seed_min": -5.7,
            "tierA_std": 24.1,
            "tierP_std": 15.8,
            "tierP_facingY_turnriver_worst_bb100": -1505.0,
        },
        "gg": {
            "tierA_mean": 6.5,
            "tierP_mean": -1.4,
            "tierA_seed_min": -10.4,
            "tierP_seed_min": -19.7,
            "tierA_std": 14.0,
            "tierP_std": 13.7,
        },
    }
    confirm_metrics = {
        "coinpoker": {
            "tierA_mean": 21.0,
            "tierP_mean": 17.4,
            "pool_weighted_mean": 15.9,
            "br_worst_mean": 10.9,
            "tierA_seed_min": -3.0,
            "tierP_seed_min": -2.2,
            "tierA_std": 22.7,
            "tierP_std": 14.6,
            "tierP_facingY_turnriver_worst_bb100": -920.0,
        },
        "gg": {
            "tierA_mean": 8.1,
            "tierP_mean": 1.3,
            "tierA_seed_min": -7.0,
            "tierP_seed_min": -11.0,
            "tierA_std": 12.2,
            "tierP_std": 11.8,
        },
    }

    gate = loop._provisional_confirmation_gate(
        candidate_metrics=confirm_metrics,
        baseline_metrics=baseline_metrics,
        candidate_holdout_phase1_mean=-94.0,
        baseline_holdout_phase1_mean=-105.0,
        candidate_holdout_phase2_mean=-88.0,
        baseline_holdout_phase2_mean=-97.0,
        holdout_phase1_required=True,
        holdout_phase2_required=True,
        holdout_regress_tolerance=0.1,
    )

    assert gate["pass"] is True
    assert gate["phase2_pass"] is True
    assert gate["relative_promotion"]["pass"] is True


def test_provisional_confirmation_gate_rejects_phase2_regression() -> None:
    gate = loop._provisional_confirmation_gate(
        candidate_metrics={"coinpoker": {"tierA_mean": 21.0}, "gg": {"tierA_mean": 8.0}},
        baseline_metrics={"coinpoker": {"tierA_mean": 20.0}, "gg": {"tierA_mean": 7.0}},
        candidate_holdout_phase1_mean=-100.0,
        baseline_holdout_phase1_mean=-105.0,
        candidate_holdout_phase2_mean=-103.0,
        baseline_holdout_phase2_mean=-97.0,
        holdout_phase1_required=True,
        holdout_phase2_required=True,
        holdout_regress_tolerance=0.1,
    )

    assert gate["pass"] is False
    assert gate["phase2_pass"] is False
    assert gate["holdout_phase2_required"] is True


def test_quick_eval_cache_miss_after_core_file_change(tmp_path: Path, monkeypatch) -> None:
    cache_dir = tmp_path / "quick_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    core_file = tmp_path / "core_patch_probe.txt"
    core_file.write_text("v1\n", encoding="utf-8")

    monkeypatch.setattr(loop, "ROOT", tmp_path)
    monkeypatch.setattr(loop, "QUICK_EVAL_CACHE_DIR", cache_dir)
    monkeypatch.setattr(loop, "CORE_PATCH_FILES", {"core_patch_probe.txt"})

    calls: list[dict[str, object]] = []

    def _fake_quick_eval(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "policy": kwargs.get("policy_label"),
            "score": 1.0,
            "metrics": {},
            "focus_probe": {},
            "ante_integrity": {"pass": True},
            "execution_plan": {},
        }

    monkeypatch.setattr(loop, "_quick_eval", _fake_quick_eval)

    common = {
        "policy_label": "policy_x",
        "profile": "profile_x",
        "quick_scenarios": ["scenario_x"],
        "tier_a_opponents": "tier_a",
        "tier_p_opponents": "tier_p",
        "hands": 100,
        "seeds_json": "[3000,3001]",
        "jobs": 1,
        "quiet": True,
        "timeout_sec": None,
        "heartbeat_sec": None,
        "policy_fingerprint": "fingerprint_x",
    }

    run1 = tmp_path / "run1"
    out1 = loop._quick_eval_cached(run_root=run1, **common)
    assert out1.get("score") == 1.0
    assert len(calls) == 1
    miss1 = json.loads((run1 / "quick_eval_cache_miss.json").read_text(encoding="utf-8"))
    key1 = miss1["cache_key"]

    run2 = tmp_path / "run2"
    out2 = loop._quick_eval_cached(run_root=run2, **common)
    assert out2.get("score") == 1.0
    assert len(calls) == 1
    assert (run2 / "quick_eval_cache_hit.json").exists()

    core_file.write_text("v2\n", encoding="utf-8")

    run3 = tmp_path / "run3"
    out3 = loop._quick_eval_cached(run_root=run3, **common)
    assert out3.get("score") == 1.0
    assert len(calls) == 2
    miss3 = json.loads((run3 / "quick_eval_cache_miss.json").read_text(encoding="utf-8"))
    key3 = miss3["cache_key"]

    assert key3 != key1


def test_quick_gate_hints_block_tightening() -> None:
    hands, hits, behavior, regression, diag = loop._apply_quick_gate_hints(
        base_focus_support_min_hands=12,
        base_focus_support_min_hits=1,
        base_behavior_delta_min=0.03,
        base_quick_regression_tolerance=1.1,
        hints={
            "focus_support_min_hands": 120,
            "focus_support_min_hits": 8,
            "behavior_delta_min": 0.20,
            "quick_regression_tolerance": 0.30,
        },
    )
    assert hands == 12
    assert hits == 1
    assert behavior == 0.03
    assert regression == 1.1
    assert diag["policy"] == "bounded_relaxation_only_v1"
    assert diag["ignored"]["focus_support_min_hands"] == "tightening_blocked_or_noop"
    assert diag["ignored"]["focus_support_min_hits"] == "tightening_blocked_or_noop"


def test_quick_gate_hints_allow_bounded_relaxation() -> None:
    hands, hits, behavior, regression, diag = loop._apply_quick_gate_hints(
        base_focus_support_min_hands=12,
        base_focus_support_min_hits=1,
        base_behavior_delta_min=0.03,
        base_quick_regression_tolerance=1.1,
        hints={
            "focus_support_min_hands": 6,
            "focus_support_min_hits": 1,
            "behavior_delta_min": 0.01,
            "quick_regression_tolerance": 2.4,
        },
    )
    assert hands == 6
    assert hits == 1
    assert behavior == 0.01
    assert math.isclose(regression, 1.7, rel_tol=0.0, abs_tol=1e-9)
    assert diag["applied"]["focus_support_min_hands"]["effective"] == 6
    assert diag["applied"]["behavior_delta_min"]["effective"] == 0.01
    assert math.isclose(
        float(diag["applied"]["quick_regression_tolerance"]["effective"]),
        1.7,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
