from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_standard() -> dict[str, Any]:
    path = _repo_root() / "specs" / "benchmarks" / "top_human_proxy_v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_non_negative_number(name: str, value: Any) -> None:
    assert isinstance(value, (int, float)), f"{name} must be numeric"
    assert float(value) >= 0.0, f"{name} must be non-negative"


def validate_strength_summary(
    summary: dict[str, Any],
    *,
    standard: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    if not isinstance(summary, dict):
        return ["summary must be a JSON object"]

    if summary.get("summary_schema_id") != "strength_benchmark_summary_v1":
        errors.append("summary_schema_id must be strength_benchmark_summary_v1")
        return errors

    required_top_level = {
        "paired_compare",
        "pool_eval",
        "solver_gap",
        "br_proxy",
        "calibration",
        "coverage",
    }
    missing = sorted(required_top_level - set(summary.keys()))
    if missing:
        errors.append(f"missing top-level sections: {missing}")
        return errors

    paired = summary["paired_compare"]
    if int(paired.get("hands", 0)) < int(standard["paired_compare"]["min_hands"]):
        errors.append("paired_compare.hands below threshold")
    if float(paired.get("lower_ci_bb100", -10**9)) < float(
        standard["paired_compare"]["min_lower_ci_bb100"]
    ):
        errors.append("paired_compare.lower_ci_bb100 below threshold")

    pools = summary["pool_eval"]
    required_pools = list(standard["required_pools"])
    for pool_name in required_pools:
        pool = pools.get(pool_name)
        if not isinstance(pool, dict):
            errors.append(f"pool_eval.{pool_name} missing")
            continue
        if int(pool.get("hands", 0)) < int(standard["pool_eval"]["min_hands_per_pool"]):
            errors.append(f"pool_eval.{pool_name}.hands below threshold")
        required_ci = float(standard["pool_eval"]["min_lower_ci_bb100_by_pool"][pool_name])
        if float(pool.get("lower_ci_bb100", -10**9)) < required_ci:
            errors.append(f"pool_eval.{pool_name}.lower_ci_bb100 below threshold")

    if float(summary.get("worst_case_pool_bb100", 0.0)) < -float(
        standard["pool_eval"]["max_worst_case_pool_loss_bb100"]
    ):
        errors.append("worst_case_pool_bb100 below allowable floor")

    solver_gap = summary["solver_gap"]
    if float(solver_gap.get("avg_bb100", 10**9)) > float(standard["solver_gap"]["max_avg_bb100"]):
        errors.append("solver_gap.avg_bb100 above threshold")
    if float(solver_gap.get("p95_bb100", 10**9)) > float(standard["solver_gap"]["max_p95_bb100"]):
        errors.append("solver_gap.p95_bb100 above threshold")

    br_proxy = summary["br_proxy"]
    if float(br_proxy.get("risk_of_ruin", 10**9)) > float(standard["br_proxy"]["max_risk_of_ruin"]):
        errors.append("br_proxy.risk_of_ruin above threshold")
    if float(br_proxy.get("max_drawdown_p95_buyins", 10**9)) > float(
        standard["br_proxy"]["max_drawdown_p95_buyins"]
    ):
        errors.append("br_proxy.max_drawdown_p95_buyins above threshold")

    calibration = summary["calibration"]
    if float(calibration.get("brier", 10**9)) > float(standard["calibration"]["max_brier"]):
        errors.append("calibration.brier above threshold")
    if float(calibration.get("ev_sign_accuracy", -10**9)) < float(
        standard["calibration"]["min_ev_sign_accuracy"]
    ):
        errors.append("calibration.ev_sign_accuracy below threshold")

    coverage = summary["coverage"]
    if int(coverage.get("positions", 0)) < int(standard["coverage"]["min_positions"]):
        errors.append("coverage.positions below threshold")
    if int(coverage.get("stack_buckets", 0)) < int(standard["coverage"]["min_stack_buckets"]):
        errors.append("coverage.stack_buckets below threshold")
    if int(coverage.get("rake_profiles", 0)) < int(standard["coverage"]["min_rake_profiles"]):
        errors.append("coverage.rake_profiles below threshold")

    return errors


def _passing_summary() -> dict[str, Any]:
    return {
        "summary_schema_id": "strength_benchmark_summary_v1",
        "paired_compare": {"hands": 60000, "lower_ci_bb100": 1.4},
        "pool_eval": {
            "baseline": {"hands": 60000, "bb100": 6.7, "lower_ci_bb100": 4.8},
            "realistic": {"hands": 60000, "bb100": 2.4, "lower_ci_bb100": 1.2},
            "pressure": {"hands": 60000, "bb100": 0.9, "lower_ci_bb100": 0.1},
            "exploit": {"hands": 60000, "bb100": 0.8, "lower_ci_bb100": 0.1}
        },
        "worst_case_pool_bb100": -0.7,
        "solver_gap": {"avg_bb100": 1.2, "p95_bb100": 4.6},
        "br_proxy": {"risk_of_ruin": 0.03, "max_drawdown_p95_buyins": 19.0},
        "calibration": {"brier": 0.16, "ev_sign_accuracy": 0.61},
        "coverage": {"positions": 6, "stack_buckets": 4, "rake_profiles": 2}
    }


def test_top_human_proxy_standard_is_well_formed() -> None:
    standard = _load_standard()
    assert standard["benchmark_spec_schema_id"] == "top_human_proxy_benchmark_v1"
    assert standard["label"] == "near_top_human_proxy"
    assert standard["required_pools"] == ["baseline", "realistic", "pressure", "exploit"]
    _assert_non_negative_number("paired_compare.min_hands", standard["paired_compare"]["min_hands"])
    _assert_non_negative_number(
        "paired_compare.min_lower_ci_bb100", standard["paired_compare"]["min_lower_ci_bb100"]
    )
    for pool_name, threshold in standard["pool_eval"]["min_lower_ci_bb100_by_pool"].items():
        assert pool_name in standard["required_pools"]
        _assert_non_negative_number(f"pool_eval.min_lower_ci_bb100_by_pool.{pool_name}", threshold)
    _assert_non_negative_number(
        "pool_eval.max_worst_case_pool_loss_bb100",
        standard["pool_eval"]["max_worst_case_pool_loss_bb100"],
    )
    _assert_non_negative_number("solver_gap.max_avg_bb100", standard["solver_gap"]["max_avg_bb100"])
    _assert_non_negative_number("solver_gap.max_p95_bb100", standard["solver_gap"]["max_p95_bb100"])
    _assert_non_negative_number(
        "br_proxy.max_risk_of_ruin", standard["br_proxy"]["max_risk_of_ruin"]
    )
    _assert_non_negative_number(
        "br_proxy.max_drawdown_p95_buyins",
        standard["br_proxy"]["max_drawdown_p95_buyins"],
    )
    _assert_non_negative_number("calibration.max_brier", standard["calibration"]["max_brier"])
    _assert_non_negative_number(
        "calibration.min_ev_sign_accuracy", standard["calibration"]["min_ev_sign_accuracy"]
    )
    _assert_non_negative_number("coverage.min_positions", standard["coverage"]["min_positions"])
    _assert_non_negative_number(
        "coverage.min_stack_buckets", standard["coverage"]["min_stack_buckets"]
    )
    _assert_non_negative_number(
        "coverage.min_rake_profiles", standard["coverage"]["min_rake_profiles"]
    )


def test_passing_summary_satisfies_near_top_human_proxy_gate() -> None:
    standard = _load_standard()
    assert validate_strength_summary(_passing_summary(), standard=standard) == []


def test_summary_fails_when_realistic_pool_is_not_beaten_with_confidence() -> None:
    standard = _load_standard()
    summary = _passing_summary()
    summary["pool_eval"]["realistic"]["lower_ci_bb100"] = 0.2
    errors = validate_strength_summary(summary, standard=standard)
    assert "pool_eval.realistic.lower_ci_bb100 below threshold" in errors


def test_summary_fails_when_solver_gap_is_too_large() -> None:
    standard = _load_standard()
    summary = _passing_summary()
    summary["solver_gap"]["avg_bb100"] = 2.1
    summary["solver_gap"]["p95_bb100"] = 6.2
    errors = validate_strength_summary(summary, standard=standard)
    assert "solver_gap.avg_bb100 above threshold" in errors
    assert "solver_gap.p95_bb100 above threshold" in errors


def test_summary_fails_when_coverage_is_too_narrow() -> None:
    standard = _load_standard()
    summary = _passing_summary()
    summary["coverage"] = {"positions": 4, "stack_buckets": 2, "rake_profiles": 1}
    errors = validate_strength_summary(summary, standard=standard)
    assert "coverage.positions below threshold" in errors
    assert "coverage.stack_buckets below threshold" in errors
    assert "coverage.rake_profiles below threshold" in errors
