from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


def _parse_list(value: str | None, *, required: bool = False) -> list[str]:
    if value is None:
        if required:
            raise ValueError("candidates must be provided")
        return []
    raw = value.strip()
    if raw.startswith("["):
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("candidates JSON must be a list")
        return [str(x) for x in data]
    return [p.strip() for p in raw.split(",") if p.strip()]


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
        std = var ** 0.5
    else:
        std = 0.0
    return mean, std, vals


def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)


def _run_one(
    suite: str,
    *,
    args: argparse.Namespace,
    out_root: Path,
    jobs_per_run: int,
    seeds: list[int],
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
    log_path = out_dir / "br_proxy_run.log"
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
    }


def main() -> int:
    p = argparse.ArgumentParser(description="BR(π) proxy runner over opponent suites.")
    p.add_argument("--scenario", default="coinpoker_7max_mw_v3_actionspace_v2")
    p.add_argument("--profile", default="internal_profile_v1")
    p.add_argument("--policy", default="system_bot_policy_v3")
    p.add_argument("--hands", type=int, default=2000)
    p.add_argument("--seeds", default=None)
    p.add_argument("--seed-start", type=int, default=2000)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--paths-config", type=Path, default=None, help="PathsConfig JSON for solver roots")
    p.add_argument("--candidates", default=None, help="Comma list or JSON list of opponent suites")
    p.add_argument("--candidates-file", type=Path, default=None, help="JSON list of opponent suites")
    p.add_argument("--suite-jobs", type=int, default=2)
    p.add_argument("--jobs", type=int, default=None, help="Jobs per scrimmage_batch run")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--quiet", action="store_true", help="Suppress scrimmage stdout")
    p.add_argument("--timeout-sec", type=float, default=None, help="Fail a suite if it exceeds this many seconds")
    p.add_argument("--heartbeat-sec", type=float, default=None, help="Write periodic heartbeat lines to run.log")
    p.add_argument("--opponent-compliance", action="store_true")
    p.add_argument("--opponent-compliance-jobs", type=int, default=4)
    args = p.parse_args()

    suites: list[str] = []
    suites.extend(_parse_list(args.candidates))
    if args.candidates_file:
        suites.extend(json.loads(args.candidates_file.read_text(encoding="utf-8")))
    if not suites:
        raise SystemExit("candidates required")

    if args.seeds:
        seeds = json.loads(args.seeds) if args.seeds.strip().startswith("[") else [int(s) for s in args.seeds.split(",")]
    else:
        seeds = [int(args.seed_start) + i for i in range(int(args.count))]

    suite_jobs = max(1, int(args.suite_jobs))
    if args.timeout_sec is not None and args.timeout_sec <= 0:
        args.timeout_sec = None
    if args.heartbeat_sec is not None and args.heartbeat_sec <= 0:
        args.heartbeat_sec = None
    cpu_count = os.cpu_count() or 2
    jobs_per_run = int(args.jobs) if args.jobs else max(1, cpu_count // suite_jobs)
    out_root = args.out_dir
    out_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=suite_jobs) as pool:
        futures = [
            pool.submit(
                _run_one,
                suite,
                args=args,
                out_root=out_root,
                jobs_per_run=jobs_per_run,
                seeds=seeds,
            )
            for suite in suites
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    # pick worst (min mean)
    worst = None
    for row in results:
        mean = row.get("mean_bb100")
        if mean is None:
            continue
        if worst is None or mean < worst.get("mean_bb100"):
            worst = row

    summary = {
        "schema_id": "br_proxy_v1",
        "scenario": args.scenario,
        "profile": args.profile,
        "policy": args.policy,
        "hands": args.hands,
        "seeds": seeds,
        "suite_jobs": suite_jobs,
        "jobs_per_run": jobs_per_run,
        "timeout_sec": args.timeout_sec,
        "heartbeat_sec": args.heartbeat_sec,
        "results": results,
        "worst_case": worst,
    }
    summary_path = out_root / "br_proxy_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
