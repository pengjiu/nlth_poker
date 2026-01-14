from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _fmt_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(str(c)))
    def fmt_row(r: list[str]) -> str:
        return " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(r))
    lines = [fmt_row(headers), "-+-".join("-" * w for w in widths)]
    lines.extend(fmt_row(r) for r in rows)
    return "\n".join(lines)


def _run_scrimmage(*, args: argparse.Namespace, extra: list[str], out_dir: Path, seed: int) -> None:
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
        str(args.hands_per_batch),
        "--seed",
        str(seed),
        "--out-dir",
        str(out_dir),
    ]
    if args.bench_bb_flat:
        cmd.append("--bench-bb-flat")
    cmd.extend(extra)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "run.log"
    with log_path.open("w", encoding="utf-8") as f:
        subprocess.run(cmd, check=True, stdout=f, stderr=subprocess.STDOUT)


def _accumulate_report(
    report: dict[str, Any],
    *,
    total: dict[str, Any],
    facing: dict[tuple[str, str], dict[str, float]],
    pos_profit: dict[str, float],
) -> None:
    analysis = report.get("analysis") or {}
    total["hands"] += int(analysis.get("hands", 0) or 0)
    total["profit_bb"] += float(analysis.get("profit_bb", 0.0) or 0.0)
    pos = analysis.get("position_profit") or {}
    if isinstance(pos, dict):
        for k, v in pos.items():
            if isinstance(v, dict):
                pos_profit[k] += float(v.get("profit_bb", 0.0) or 0.0)
    rows = analysis.get("bb_flat_postflop_facing_by_street") or []
    entries = rows.values() if isinstance(rows, dict) else rows
    for row in entries:
        if not isinstance(row, dict):
            continue
        street = row.get("street")
        facing_flag = row.get("facing")
        if not isinstance(street, str) or facing_flag not in ("Y", "N"):
            continue
        key = (street, facing_flag)
        facing[key]["hands"] += int(row.get("hands", 0) or 0)
        facing[key]["profit_bb"] += float(row.get("profit_bb", 0.0) or 0.0)


def _coverage_met(
    facing: dict[tuple[str, str], dict[str, float]],
    *,
    target_n: int,
) -> bool:
    for street in ("FLOP", "TURN", "RIVER"):
        key = (street, "Y")
        if facing.get(key, {}).get("hands", 0) < target_n:
            return False
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Microbench: run batches until BB facing-bet coverage met.")
    p.add_argument("--scenario", default="coinpoker_7max_mw_v3_actionspace")
    p.add_argument("--profile", default="internal_profile_v1")
    p.add_argument("--policy", default="system_bot_policy_v3")
    p.add_argument("--opponents", default="system_bot_league_7max_frozen_v1")
    p.add_argument("--hands-per-batch", type=int, default=200)
    p.add_argument("--target-n", type=int, default=20, help="Min hands per street for facing=Y")
    p.add_argument("--max-batches", type=int, default=30)
    p.add_argument("--seed-start", type=int, default=2000)
    p.add_argument("--bench-bb-flat", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--out-dir", type=Path, required=True)
    args, extra = p.parse_known_args()

    out_root = args.out_dir
    out_root.mkdir(parents=True, exist_ok=True)
    total = {"hands": 0, "profit_bb": 0.0}
    facing: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"hands": 0, "profit_bb": 0.0})
    pos_profit: dict[str, float] = defaultdict(float)
    seeds: list[int] = []
    batches_run = 0

    for i in range(args.max_batches):
        seed = int(args.seed_start) + i
        out_dir = out_root / f"seed{seed}"
        _run_scrimmage(args=args, extra=extra, out_dir=out_dir, seed=seed)
        report_path = out_dir / "scrimmage_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        _accumulate_report(report, total=total, facing=facing, pos_profit=pos_profit)
        seeds.append(seed)
        batches_run += 1
        if _coverage_met(facing, target_n=args.target_n):
            break

    bb100 = total["profit_bb"] * 100.0 / max(1, total["hands"])
    summary = {
        "schema_id": "microbench_bb_facing_v1",
        "scenario": args.scenario,
        "profile": args.profile,
        "policy": args.policy,
        "opponents": args.opponents,
        "hands_per_batch": args.hands_per_batch,
        "target_n": args.target_n,
        "max_batches": args.max_batches,
        "batches_run": batches_run,
        "seeds": seeds,
        "bench_bb_flat": args.bench_bb_flat,
        "total_hands": total["hands"],
        "profit_bb": total["profit_bb"],
        "bb_per_100": bb100,
        "position_profit_bb": dict(pos_profit),
        "bb_flat_postflop_facing_by_street": [],
        "coverage_met": _coverage_met(facing, target_n=args.target_n),
    }
    for street in ("FLOP", "TURN", "RIVER"):
        for facing_flag in ("N", "Y"):
            key = (street, facing_flag)
            entry = facing.get(key, {"hands": 0, "profit_bb": 0.0})
            hands = int(entry.get("hands", 0))
            profit_bb = float(entry.get("profit_bb", 0.0))
            bb100 = profit_bb * 100.0 / max(1, hands)
            summary["bb_flat_postflop_facing_by_street"].append(
                {
                    "street": street,
                    "facing": facing_flag,
                    "hands": hands,
                    "profit_bb": profit_bb,
                    "bb_per_100": bb100,
                }
            )

    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines: list[str] = []
    lines.append("== Microbench Summary ==")
    lines.append(f"hands={summary['total_hands']} bb/100={summary['bb_per_100']:.2f}")
    lines.append(f"BB_profit_bb={pos_profit.get('BB',0.0):.2f} SB_profit_bb={pos_profit.get('SB',0.0):.2f}")
    lines.append(f"coverage_met={summary['coverage_met']} batches_run={batches_run}")
    rows = []
    for row in summary["bb_flat_postflop_facing_by_street"]:
        rows.append(
            [
                row["street"],
                row["facing"],
                str(row["hands"]),
                f"{row['profit_bb']:.2f}",
                f"{row['bb_per_100']:.2f}",
            ]
        )
    lines.append("== BB Flat Postflop Facing ==")
    lines.append(_fmt_table(["street", "facing", "hands", "profit_bb", "bb/100"], rows))
    (out_root / "summary.txt").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n" + "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
