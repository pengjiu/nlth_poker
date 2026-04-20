from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


def _parse_seeds(value: str | None, *, seed_start: int, count: int) -> list[int]:
    if value:
        raw = value.strip()
        if raw.startswith("["):
            data = json.loads(raw)
            if not isinstance(data, list) or not data:
                raise ValueError("seeds JSON must be a non-empty list")
            return [int(x) for x in data]
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            raise ValueError("seeds string must not be empty")
        return [int(p) for p in parts]
    if count <= 0:
        raise ValueError("count must be > 0 when seeds not provided")
    return [int(seed_start) + i for i in range(count)]


def _run_cmd(cmd: list[str], *, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    return int(proc.returncode)


def _read_mean_std(batch_path: Path) -> tuple[float | None, float | None, list[float]]:
    if not batch_path.exists():
        return None, None, []
    data = json.loads(batch_path.read_text(encoding="utf-8"))
    vals: list[float] = []
    for run in data.get("runs", []):
        ref = run.get("report_ref")
        if isinstance(ref, str) and ref.startswith("path:"):
            report = json.loads(Path(ref.replace("path:", "")).read_text(encoding="utf-8"))
            vals.append(float(report.get("analysis", {}).get("bb_per_100", 0.0) or 0.0))
    if not vals:
        return None, None, []
    mean = sum(vals) / len(vals)
    if len(vals) > 1:
        var = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
        std = var ** 0.5
    else:
        std = 0.0
    return mean, std, vals


def _scrimmage_batch_cmd(
    *,
    scenario: str,
    profile: str,
    policy: str,
    opponents: str,
    hands: int,
    seeds: list[int],
    jobs: int,
    out_dir: Path,
    opponent_compliance: bool,
    opponent_compliance_jobs: int,
    quiet: bool,
    timeout_sec: float | None,
    heartbeat_sec: float | None,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "poker2.cli.scrimmage_batch",
        "--scenario",
        scenario,
        "--profile",
        profile,
        "--policy",
        policy,
        "--opponents",
        opponents,
        "--hands",
        str(hands),
        "--seeds",
        json.dumps(seeds),
        "--jobs",
        str(jobs),
        "--out-dir",
        str(out_dir),
    ]
    if opponent_compliance:
        cmd.append("--opponent-compliance")
        cmd.extend(["--opponent-compliance-jobs", str(opponent_compliance_jobs)])
    if quiet:
        cmd.append("--quiet")
    if timeout_sec:
        cmd.extend(["--timeout-sec", str(timeout_sec)])
    if heartbeat_sec:
        cmd.extend(["--heartbeat-sec", str(heartbeat_sec)])
    return cmd


def _load_pool_suites(pool_path: Path, *, include_holdout: bool) -> list[str]:
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    suites = [str(c.get("suite")) for c in pool.get("candidates", []) if c.get("suite")]
    if include_holdout:
        suites.extend(str(h.get("suite")) for h in pool.get("holdout", []) if h.get("suite"))
    # dedupe preserving order
    seen = set()
    out = []
    for s in suites:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Full evaluation runner (Tier-A/Tier-P + Pool + BR + dual baseline).")
    p.add_argument("--scenario", default="coinpoker_7max_mw_v3_actionspace_v2")
    p.add_argument("--profile", default="internal_profile_v1")
    p.add_argument("--policy", default="system_bot_policy_v3")
    p.add_argument("--tierA-opponents", default="system_bot_league_7max_frozen_v1")
    p.add_argument("--tierP-opponents", default="system_bot_league_7max_frozen_v3")
    p.add_argument("--pool", type=Path, default=Path("specs/opponents/pools/system_bot_pool_v2.json"))
    p.add_argument("--hands", type=int, default=2000)
    p.add_argument("--seeds", default=None)
    p.add_argument("--seed-start", type=int, default=2000)
    p.add_argument("--count", type=int, default=6)
    p.add_argument("--confirm-seeds", default=None)
    p.add_argument("--confirm-seed-start", type=int, default=2010)
    p.add_argument("--confirm-count", type=int, default=6)
    p.add_argument("--baseline-batch", type=Path, default=None, help="Optional baseline scrimmage_batch.json for paired compare")
    p.add_argument("--bootstrap", type=int, default=5000, help="Bootstrap samples for paired compare")
    p.add_argument("--alpha", type=float, default=0.05, help="Bootstrap alpha")
    p.add_argument("--seed", type=int, default=42, help="Bootstrap RNG seed")
    p.add_argument("--jobs", type=int, default=None, help="Total parallel jobs (default: CPU-1)")
    p.add_argument("--opponent-compliance", action="store_true")
    p.add_argument("--opponent-compliance-jobs", type=int, default=4)
    p.add_argument("--pool-suite-jobs", type=int, default=2)
    p.add_argument("--pool-jobs-per-run", type=int, default=None)
    p.add_argument("--br-suite-jobs", type=int, default=2)
    p.add_argument("--br-jobs-per-run", type=int, default=None)
    p.add_argument("--quiet", action="store_true", help="Suppress scrimmage stdout")
    p.add_argument("--timeout-sec", type=float, default=None, help="Fail a run if it exceeds this many seconds")
    p.add_argument("--heartbeat-sec", type=float, default=None, help="Write periodic heartbeat lines to run.log")
    p.add_argument("--br-from-pool", action="store_true", help="Use pool candidates (and holdout) as BR candidates")
    p.add_argument("--br-include-holdout", action="store_true")
    p.add_argument("--br-candidates", default=None, help="Comma list of opponent suites for BR proxy")
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    if args.timeout_sec is not None and args.timeout_sec <= 0:
        args.timeout_sec = None
    if args.heartbeat_sec is not None and args.heartbeat_sec <= 0:
        args.heartbeat_sec = None

    seeds_main = _parse_seeds(args.seeds, seed_start=args.seed_start, count=args.count)
    seeds_confirm = _parse_seeds(args.confirm_seeds, seed_start=args.confirm_seed_start, count=args.confirm_count)

    out_root = args.out_dir
    out_root.mkdir(parents=True, exist_ok=True)

    cpu_count = os.cpu_count() or 2
    total_jobs = int(args.jobs) if args.jobs else max(1, cpu_count - 1)
    jobs_pair = max(1, total_jobs // 2)

    tierA_dir = out_root / "tierA"
    tierP_dir = out_root / "tierP"
    tierA_confirm_dir = out_root / "tierA_confirm"

    # Run Tier-A and Tier-P in parallel.
    batch_cmds = {
        "tierA": _scrimmage_batch_cmd(
            scenario=args.scenario,
            profile=args.profile,
            policy=args.policy,
            opponents=args.tierA_opponents,
            hands=args.hands,
            seeds=seeds_main,
            jobs=jobs_pair,
            out_dir=tierA_dir,
            opponent_compliance=args.opponent_compliance,
            opponent_compliance_jobs=args.opponent_compliance_jobs,
            quiet=args.quiet,
            timeout_sec=args.timeout_sec,
            heartbeat_sec=args.heartbeat_sec,
        ),
        "tierP": _scrimmage_batch_cmd(
            scenario=args.scenario,
            profile=args.profile,
            policy=args.policy,
            opponents=args.tierP_opponents,
            hands=args.hands,
            seeds=seeds_main,
            jobs=jobs_pair,
            out_dir=tierP_dir,
            opponent_compliance=args.opponent_compliance,
            opponent_compliance_jobs=args.opponent_compliance_jobs,
            quiet=args.quiet,
            timeout_sec=args.timeout_sec,
            heartbeat_sec=args.heartbeat_sec,
        ),
    }
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_run_cmd, cmd, log_path=out_root / f"{label}.log"): label
            for label, cmd in batch_cmds.items()
        }
        for fut in as_completed(futures):
            label = futures[fut]
            rc = fut.result()
            results[label] = {"returncode": rc, "out_dir": str((tierA_dir if label == "tierA" else tierP_dir))}

    # Confirm baseline (Tier-A only) using second seed set.
    confirm_cmd = _scrimmage_batch_cmd(
        scenario=args.scenario,
        profile=args.profile,
        policy=args.policy,
        opponents=args.tierA_opponents,
        hands=args.hands,
        seeds=seeds_confirm,
        jobs=total_jobs,
        out_dir=tierA_confirm_dir,
        opponent_compliance=args.opponent_compliance,
        opponent_compliance_jobs=args.opponent_compliance_jobs,
        quiet=args.quiet,
        timeout_sec=args.timeout_sec,
        heartbeat_sec=args.heartbeat_sec,
    )
    rc_confirm = _run_cmd(confirm_cmd, log_path=out_root / "tierA_confirm.log")
    results["tierA_confirm"] = {"returncode": rc_confirm, "out_dir": str(tierA_confirm_dir)}

    # Paired compare vs baseline if provided.
    paired_ref = None
    if args.baseline_batch:
        paired_out = tierA_dir / "paired_compare.json"
        paired_cmd = [
            sys.executable,
            "-m",
            "poker2.cli.paired_compare",
            "--baseline",
            str(args.baseline_batch),
            "--candidate",
            str(tierA_dir / "scrimmage_batch.json"),
            "--metric",
            "bb_per_100",
            "--bootstrap",
            str(int(args.bootstrap)),
            "--alpha",
            str(float(args.alpha)),
            "--seed",
            str(int(args.seed)),
            "--out",
            str(paired_out),
            "--strict",
        ]
        rc_pair = _run_cmd(paired_cmd, log_path=out_root / "paired_compare.log")
        paired_ref = f"path:{paired_out.resolve()}"
        results["paired_compare"] = {"returncode": rc_pair, "out_ref": paired_ref}

    # OpponentPool eval (PSRO-lite).
    pool_out = out_root / "pool_eval"
    pool_cmd = [
        sys.executable,
        "-m",
        "poker2.cli.pool_eval",
        "--pool",
        str(args.pool),
        "--scenario",
        args.scenario,
        "--profile",
        args.profile,
        "--policy",
        args.policy,
        "--hands",
        str(args.hands),
        "--seeds",
        json.dumps(seeds_main),
        "--suite-jobs",
        str(int(args.pool_suite_jobs)),
        "--out-dir",
        str(pool_out),
    ]
    if args.quiet:
        pool_cmd.append("--quiet")
    if args.pool_jobs_per_run:
        pool_cmd.extend(["--jobs", str(int(args.pool_jobs_per_run))])
    if args.timeout_sec:
        pool_cmd.extend(["--timeout-sec", str(args.timeout_sec)])
    if args.heartbeat_sec:
        pool_cmd.extend(["--heartbeat-sec", str(args.heartbeat_sec)])
    if args.opponent_compliance:
        pool_cmd.append("--opponent-compliance")
        pool_cmd.extend(["--opponent-compliance-jobs", str(int(args.opponent_compliance_jobs))])
    rc_pool = _run_cmd(pool_cmd, log_path=out_root / "pool_eval.log")
    results["pool_eval"] = {"returncode": rc_pool, "out_dir": str(pool_out)}

    # BR(π) proxy eval.
    br_out = out_root / "br_proxy"
    br_candidates = []
    if args.br_from_pool:
        br_candidates = _load_pool_suites(args.pool, include_holdout=args.br_include_holdout)
    elif args.br_candidates:
        br_candidates = [s.strip() for s in args.br_candidates.split(",") if s.strip()]
    br_cmd = [
        sys.executable,
        "-m",
        "poker2.cli.br_proxy",
        "--scenario",
        args.scenario,
        "--profile",
        args.profile,
        "--policy",
        args.policy,
        "--hands",
        str(args.hands),
        "--seeds",
        json.dumps(seeds_main),
        "--suite-jobs",
        str(int(args.br_suite_jobs)),
        "--out-dir",
        str(br_out),
    ]
    if args.quiet:
        br_cmd.append("--quiet")
    if br_candidates:
        br_cmd.extend(["--candidates", json.dumps(br_candidates)])
    if args.br_jobs_per_run:
        br_cmd.extend(["--jobs", str(int(args.br_jobs_per_run))])
    if args.timeout_sec:
        br_cmd.extend(["--timeout-sec", str(args.timeout_sec)])
    if args.heartbeat_sec:
        br_cmd.extend(["--heartbeat-sec", str(args.heartbeat_sec)])
    if args.opponent_compliance:
        br_cmd.append("--opponent-compliance")
        br_cmd.extend(["--opponent-compliance-jobs", str(int(args.opponent_compliance_jobs))])
    rc_br = _run_cmd(br_cmd, log_path=out_root / "br_proxy.log")
    results["br_proxy"] = {"returncode": rc_br, "out_dir": str(br_out)}

    tierA_mean, tierA_std, _ = _read_mean_std(tierA_dir / "scrimmage_batch.json")
    tierP_mean, tierP_std, _ = _read_mean_std(tierP_dir / "scrimmage_batch.json")
    tierA_confirm_mean, tierA_confirm_std, _ = _read_mean_std(tierA_confirm_dir / "scrimmage_batch.json")

    summary = {
        "schema_id": "eval_full_v1",
        "scenario": args.scenario,
        "profile": args.profile,
        "policy": args.policy,
        "tierA_opponents": args.tierA_opponents,
        "tierP_opponents": args.tierP_opponents,
        "pool_ref": f"path:{args.pool.resolve()}",
        "hands": args.hands,
        "seeds": seeds_main,
        "confirm_seeds": seeds_confirm,
        "jobs_total": total_jobs,
        "timeout_sec": args.timeout_sec,
        "heartbeat_sec": args.heartbeat_sec,
        "results": results,
        "metrics": {
            "tierA_mean": tierA_mean,
            "tierA_std": tierA_std,
            "tierP_mean": tierP_mean,
            "tierP_std": tierP_std,
            "tierA_confirm_mean": tierA_confirm_mean,
            "tierA_confirm_std": tierA_confirm_std,
        },
        "paired_compare_ref": paired_ref,
    }
    summary_path = out_root / "eval_full_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
