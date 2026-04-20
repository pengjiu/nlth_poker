from __future__ import annotations

import argparse
import json
from pathlib import Path

from poker2.tools.coverage_check import build_coverage_check


def main() -> int:
    p = argparse.ArgumentParser(description="Coverage check for key buckets from scrimmage_batch output.")
    p.add_argument("--batch", type=Path, required=True, help="Path to scrimmage_batch.json")
    p.add_argument(
        "--keys",
        default="report:BBFlatPostflopFacing/TURN_Y,report:BBFlatPostflopFacing/RIVER_Y,report:BBFlatPostflop/7+_oop_Y",
        help="Comma list of bucket keys to check",
    )
    p.add_argument("--min-n", type=int, default=20, help="Minimum hands per bucket across seeds")
    p.add_argument("--out", type=Path, default=None, help="Output JSON path (default: batch dir/coverage_check.json)")
    args = p.parse_args()

    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    result = build_coverage_check(args.batch, keys=keys, min_n=args.min_n)
    out_path = args.out
    if out_path is None:
        out_path = args.batch.parent / "coverage_check.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

