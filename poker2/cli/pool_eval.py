from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


def _load_pool(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_mean_std(out_dir: Path) -> tuple[float | None, float | None, list[float]]:
    vals: list[float] = []
    batch_path = out_dir / "scrimmage_batch.json"
    report_paths: list[Path] = []
    if batch_path.exists():
        try:
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
            for run in batch.get("runs", []):
                ref = run.get("report_ref")
                if isinstance(ref, str) and ref.startswith("path:"):
                    report_paths.append(Path(ref.replace("path:", "")))
        except Exception:
            report_paths = []
    if not report_paths:
        report_paths = sorted(out_dir.glob("seed*/scrimmage_report.json"))
    for report_path in report_paths:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            val = float(report.get("analysis", {}).get("bb_per_100", 0.0) or 0.0)
            vals.append(val)
        except Exception:
            continue
    if not vals:
        return None, None, []
    mean = sum(vals) / len(vals)
    if len(vals) > 1:
        var = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
        std = math.sqrt(var)
    else:
        std = 0.0
    return mean, std, vals


def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)


def _run_suite(
    suite: str,
    *,
    args: argparse.Namespace,
    out_root: Path,
    seeds: list[int],
    jobs_per_run: int,
) -> dict[str, Any]:
    out_dir = out_root / _sanitize(suite)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "poker2.cli.scrimmage_batch",
        "--scenario",
        args.scenario,
        "--profile",
        args.profile,
        "--policy",
        args.policy,
        "--opponents",
        suite,
        "--hands",
        str(args.hands),
        "--seeds",
        json.dumps(seeds),
        "--jobs",
        str(jobs_per_run),
        "--out-dir",
        str(out_dir),
    ]
    if getattr(args, "quiet", False):
        cmd.append("--quiet")
    if args.paths_config:
        cmd.extend(["--paths-config", str(args.paths_config)])
    if getattr(args, "timeout_sec", None):
        cmd.extend(["--timeout-sec", str(args.timeout_sec)])
    if getattr(args, "heartbeat_sec", None):
        cmd.extend(["--heartbeat-sec", str(args.heartbeat_sec)])
    if args.opponent_compliance:
        cmd.append("--opponent-compliance")
        cmd.extend(["--opponent-compliance-jobs", str(args.opponent_compliance_jobs)])
    log_path = out_dir / "pool_eval_run.log"
    proc = subprocess.run(cmd, stdout=log_path.open("w", encoding="utf-8"), stderr=subprocess.STDOUT)
    mean, std, vals = _read_mean_std(out_dir)
    return {
        "suite": suite,
        "out_dir": str(out_dir),
        "status": "pass" if proc.returncode == 0 else "fail",
        "returncode": proc.returncode,
        "mean_bb100": mean,
        "std_bb100": std,
        "seed_vals": vals,
        "opponent_compliance_ref": f"path:{(out_dir / 'opponent_compliance.json').resolve()}"
        if (out_dir / "opponent_compliance.json").exists()
        else None,
    }


def _weighted_mean_std(items: list[dict[str, Any]], weights: dict[str, float]) -> tuple[float | None, float | None]:
    total = 0.0
    acc = 0.0
    for row in items:
        suite = row["suite"]
        mean = row.get("mean_bb100")
        if mean is None:
            continue
        w = float(weights.get(suite, 0.0) or 0.0)
        acc += w * float(mean)
        total += w
    if total <= 0:
        return None, None
    mean = acc / total
    var_acc = 0.0
    for row in items:
        suite = row["suite"]
        m = row.get("mean_bb100")
        if m is None:
            continue
        w = float(weights.get(suite, 0.0) or 0.0)
        var_acc += w * (float(m) - mean) ** 2
    std = math.sqrt(var_acc / total) if total > 0 else None
    return mean, std


def _suggest_weights(
    items: list[dict[str, Any]],
    base: dict[str, float],
    *,
    alpha: float,
    scale: float,
) -> dict[str, float]:
    raw: dict[str, float] = {}
    for row in items:
        suite = row["suite"]
        mean = row.get("mean_bb100")
        base_w = float(base.get(suite, 1.0) or 1.0)
        if mean is None:
            raw[suite] = base_w
            continue
        penalty = max(0.0, -float(mean))
        raw[suite] = base_w * math.exp(alpha * (penalty / max(1e-6, scale)))
    total = sum(raw.values())
    if total <= 0:
        return base
    return {k: v / total for k, v in raw.items()}


def main() -> int:
    p = argparse.ArgumentParser(description="OpponentPool evaluation (PSRO-lite).")
    p.add_argument("--pool", type=Path, required=True, help="OpponentPool JSON path")
    p.add_argument("--scenario", default="coinpoker_7max_mw_v3_actionspace_v2")
    p.add_argument("--profile", default="internal_profile_v1")
    p.add_argument("--policy", default="system_bot_policy_v3")
    p.add_argument("--hands", type=int, default=2000)
    p.add_argument("--seeds", default=None)
    p.add_argument("--seed-start", type=int, default=2000)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--paths-config", type=Path, default=None, help="PathsConfig JSON for solver roots")
    p.add_argument("--suite-jobs", type=int, default=2)
    p.add_argument("--jobs", type=int, default=None, help="Jobs per scrimmage_batch run")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--quiet", action="store_true", help="Suppress scrimmage stdout")
    p.add_argument("--timeout-sec", type=float, default=None, help="Fail a run if it exceeds this many seconds")
    p.add_argument("--heartbeat-sec", type=float, default=None, help="Write periodic heartbeat lines to run.log")
    p.add_argument("--alpha", type=float, default=0.5, help="Weight update strength")
    p.add_argument("--scale", type=float, default=10.0, help="Scale for EV penalty")
    p.add_argument("--opponent-compliance", action="store_true")
    p.add_argument("--opponent-compliance-jobs", type=int, default=4)
    args = p.parse_args()
    if args.timeout_sec is not None and args.timeout_sec <= 0:
        args.timeout_sec = None
    if args.heartbeat_sec is not None and args.heartbeat_sec <= 0:
        args.heartbeat_sec = None

    pool = _load_pool(args.pool)
    candidates = pool.get("candidates") or []
    holdout = pool.get("holdout") or []
    cand_suites = [str(c.get("suite")) for c in candidates if c.get("suite")]
    hold_suites = [str(h.get("suite")) for h in holdout if h.get("suite")]
    suites = sorted({*cand_suites, *hold_suites})
    if not suites:
        raise SystemExit("pool has no suites")

    if args.seeds:
        seeds = json.loads(args.seeds) if args.seeds.strip().startswith("[") else [int(s) for s in args.seeds.split(",")]
    else:
        seeds = [int(args.seed_start) + i for i in range(int(args.count))]

    suite_jobs = max(1, int(args.suite_jobs))
    cpu_count = os.cpu_count() or 2
    jobs_per_run = int(args.jobs) if args.jobs else max(1, cpu_count // suite_jobs)
    out_root = args.out_dir
    out_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=suite_jobs) as pool_exec:
        futures = [
            pool_exec.submit(
                _run_suite,
                suite,
                args=args,
                out_root=out_root,
                seeds=seeds,
                jobs_per_run=jobs_per_run,
            )
            for suite in suites
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    base_weights = {str(c.get("suite")): float(c.get("weight", 1.0) or 1.0) for c in candidates if c.get("suite")}
    cand_results = [r for r in results if r["suite"] in cand_suites]
    hold_results = [r for r in results if r["suite"] in hold_suites]

    weighted_mean, weighted_std = _weighted_mean_std(cand_results, base_weights)
    suggested_weights = _suggest_weights(cand_results, base_weights, alpha=float(args.alpha), scale=float(args.scale))

    summary = {
        "schema_id": "pool_eval_v1",
        "pool_ref": f"path:{args.pool.resolve()}",
        "scenario": args.scenario,
        "profile": args.profile,
        "policy": args.policy,
        "hands": args.hands,
        "seeds": seeds,
        "suite_jobs": suite_jobs,
        "jobs_per_run": jobs_per_run,
        "candidate_weights": base_weights,
        "weighted_mean_bb100": weighted_mean,
        "weighted_std_bb100": weighted_std,
        "suggested_weights": suggested_weights,
        "candidates": cand_results,
        "holdout": hold_results,
    }
    summary_path = out_root / "pool_eval_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
