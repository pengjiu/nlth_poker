from __future__ import annotations

import argparse
import errno
import json
import os
import subprocess
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _parse_seeds(value: str | None, *, seed_start: int, count: int) -> list[int]:
    if value:
        raw = value.strip()
        if raw.startswith("["):
            try:
                data = json.loads(raw)
            except Exception as e:
                raise ValueError(f"invalid seeds JSON: {e}") from e
            if not isinstance(data, list) or not data:
                raise ValueError("seeds JSON must be a non-empty list")
            seeds: list[int] = []
            for item in data:
                if isinstance(item, bool) or not isinstance(item, int):
                    raise ValueError("seeds JSON must contain ints")
                seeds.append(int(item))
            return seeds
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            raise ValueError("seeds string must not be empty")
        return [int(p) for p in parts]
    if count <= 0:
        raise ValueError("count must be > 0 when seeds not provided")
    return [int(seed_start) + i for i in range(count)]


def _build_cmd(args: argparse.Namespace, *, seed: int, out_dir: Path, extra: list[str]) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "poker2.cli.scrimmage",
        "--scenario",
        args.scenario,
        "--profile",
        args.profile,
        "--policy",
        args.policy,
        "--opponents",
        args.opponents,
        "--hands",
        str(args.hands),
        "--seed",
        str(seed),
        "--out-dir",
        str(out_dir),
    ]
    artifact_mode = getattr(args, "artifact_mode", None)
    if artifact_mode:
        cmd.extend(["--artifact-mode", str(artifact_mode)])
    if getattr(args, "quiet", False):
        cmd.append("--quiet")
    paths_config = getattr(args, "paths_config", None)
    if paths_config:
        cmd.extend(["--paths-config", str(paths_config)])
    cmd.extend(extra)
    return cmd


@dataclass
class RunResult:
    seed: int
    out_dir: str
    status: str
    returncode: int | None
    report_ref: str | None
    options_hash: str | None
    error: str | None


def _run_one(seed: int, *, args: argparse.Namespace, out_root: Path, extra: list[str]) -> RunResult:
    out_dir = out_root / f"{args.prefix}{seed}"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = _build_cmd(args, seed=seed, out_dir=out_dir, extra=extra)
        log_path = out_dir / "run.log"
        env = os.environ.copy()
        env.setdefault("PYTHONHASHSEED", "0")
        started = time.time()
        timeout_sec = getattr(args, "timeout_sec", None)
        heartbeat_sec = getattr(args, "heartbeat_sec", None)
        next_heartbeat = started + heartbeat_sec if heartbeat_sec else None
        with log_path.open("w", encoding="utf-8") as f:
            f.write(f"START seed={seed} cmd={' '.join(cmd)} at={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.flush()
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
            timed_out = False
            while True:
                rc = proc.poll()
                now = time.time()
                if rc is not None:
                    break
                if timeout_sec and (now - started) > float(timeout_sec):
                    timed_out = True
                    f.write(f"\nTIMEOUT elapsed_sec={now - started:.2f}\n")
                    f.flush()
                    proc.kill()
                    rc = proc.wait()
                    break
                if heartbeat_sec and next_heartbeat and now >= next_heartbeat:
                    f.write(f"\nHEARTBEAT elapsed_sec={now - started:.2f}\n")
                    f.flush()
                    next_heartbeat = now + float(heartbeat_sec)
                time.sleep(0.5)
            elapsed = time.time() - started
            f.write(f"\nEND rc={rc} elapsed_sec={elapsed:.2f}\n")
        report_path = out_dir / "scrimmage_report.json"
        report_ref = None
        options_hash = None
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                report_ref = f"path:{report_path.resolve()}"
                options_hash = report.get("options_hash")
            except Exception:
                report_ref = f"path:{report_path.resolve()}"
        status = "pass" if rc == 0 else "fail"
        error = None if status == "pass" else f"exit {rc}"
        if timed_out:
            status = "fail"
            error = "timeout"
        if not report_path.exists():
            if status == "pass":
                status = "fail"
                error = "missing report"
        return RunResult(
            seed=seed,
            out_dir=str(out_dir),
            status=status,
            returncode=rc,
            report_ref=report_ref,
            options_hash=options_hash,
            error=error,
        )
    except OSError as e:
        if e.errno == errno.ENOSPC:
            err_msg = (
                f"no_space_left_on_device: out_dir={out_dir} "
                "(free disk space before running scrimmage_batch)"
            )
        else:
            err_msg = str(e)
        return RunResult(
            seed=seed,
            out_dir=str(out_dir),
            status="error",
            returncode=None,
            report_ref=None,
            options_hash=None,
            error=err_msg,
        )
    except Exception as e:
        return RunResult(
            seed=seed,
            out_dir=str(out_dir),
            status="error",
            returncode=None,
            report_ref=None,
            options_hash=None,
            error=str(e),
        )


def main() -> int:
    p = argparse.ArgumentParser(description="Batch scrimmage runner (parallel, reproducible).")
    p.add_argument("--scenario", default="coinpoker_7max_mw_v3_actionspace_v2")
    p.add_argument("--profile", default="internal_profile_v1")
    p.add_argument("--policy", default="system_bot_policy_v3")
    p.add_argument("--opponents", default="system_bot_league_7max_frozen_v3")
    p.add_argument("--hands", type=int, default=2000)
    p.add_argument("--seeds", default=None, help="Comma list or JSON list, e.g. 2000,2001 or [2000,2001]")
    p.add_argument("--seed-start", type=int, default=2000)
    p.add_argument("--count", type=int, default=5)
    default_jobs = max(1, (os.cpu_count() or 2) - 1)
    p.add_argument("--jobs", type=int, default=default_jobs)
    p.add_argument("--prefix", default="seed")
    p.add_argument("--paths-config", type=Path, default=None, help="PathsConfig JSON for solver roots")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument(
        "--artifact-mode",
        choices=("full", "lean"),
        default=os.environ.get("SCRIMMAGE_ARTIFACT_MODE", "full"),
        help="full keeps all files; lean keeps only scrimmage_report.json",
    )
    p.add_argument("--quiet", action="store_true", help="Suppress scrimmage stdout")
    p.add_argument("--timeout-sec", type=float, default=None, help="Fail a run if it exceeds this many seconds")
    p.add_argument("--heartbeat-sec", type=float, default=None, help="Write periodic heartbeat lines to run.log")
    p.add_argument("--opponent-compliance", action="store_true", help="Compute opponent compliance summary")
    p.add_argument("--opponent-compliance-jobs", type=int, default=4)
    args, extra = p.parse_known_args()
    if args.timeout_sec is not None and args.timeout_sec <= 0:
        args.timeout_sec = None
    if args.heartbeat_sec is not None and args.heartbeat_sec <= 0:
        args.heartbeat_sec = None

    seeds = _parse_seeds(args.seeds, seed_start=args.seed_start, count=args.count)
    out_root = args.out_dir
    out_root.mkdir(parents=True, exist_ok=True)

    jobs = max(1, int(args.jobs))
    results: list[RunResult] = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        future_map = {
            pool.submit(_run_one, seed, args=args, out_root=out_root, extra=extra): seed
            for seed in seeds
        }
        for future in as_completed(future_map):
            seed = future_map[future]
            try:
                results.append(future.result())
            except Exception as e:
                results.append(
                    RunResult(
                        seed=seed,
                        out_dir=str(out_root / f"{args.prefix}{seed}"),
                        status="error",
                        returncode=None,
                        report_ref=None,
                        options_hash=None,
                        error=f"worker_exception: {e}",
                    )
                )

    results.sort(key=lambda r: r.seed)
    summary = {
        "schema_id": "scrimmage_batch_v1",
        "scenario": args.scenario,
        "profile": args.profile,
        "policy": args.policy,
        "opponents": args.opponents,
        "hands": args.hands,
        "seeds": seeds,
        "jobs": jobs,
        "prefix": args.prefix,
        "out_dir": str(out_root),
        "artifact_mode": args.artifact_mode,
        "runs": [r.__dict__ for r in results],
    }
    summary_path = out_root / "scrimmage_batch.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.opponent_compliance:
        try:
            from poker2.tools.opponent_compliance import build_opponent_compliance

            compliance = build_opponent_compliance(summary_path, jobs=args.opponent_compliance_jobs)
            comp_path = out_root / "opponent_compliance.json"
            comp_path.write_text(json.dumps(compliance, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            # do not fail main batch run on compliance errors
            err_path = out_root / "opponent_compliance_error.txt"
            err_path.write_text(str(e), encoding="utf-8")

    failures = [r for r in results if r.status != "pass"]
    if failures:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
