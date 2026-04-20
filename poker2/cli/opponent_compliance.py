from __future__ import annotations

import argparse
import json
from pathlib import Path

from poker2.tools.opponent_compliance import build_opponent_compliance


def main() -> int:
    p = argparse.ArgumentParser(description="Opponent compliance metrics from scrimmage_batch output.")
    p.add_argument("--batch", type=Path, required=True, help="Path to scrimmage_batch.json")
    p.add_argument("--out", type=Path, default=None, help="Output JSON path (default: batch dir/opponent_compliance.json)")
    p.add_argument("--jobs", type=int, default=4, help="Parallel parse workers")
    p.add_argument("--ranges", type=Path, default=None, help="Optional JSON file with metric ranges")
    args = p.parse_args()

    ranges = None
    if args.ranges:
        ranges = json.loads(args.ranges.read_text(encoding="utf-8"))
    compliance = build_opponent_compliance(args.batch, jobs=args.jobs, ranges=ranges)

    out_path = args.out
    if out_path is None:
        out_path = args.batch.parent / "opponent_compliance.json"
    out_path.write_text(json.dumps(compliance, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
