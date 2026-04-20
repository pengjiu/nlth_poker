from __future__ import annotations

import argparse
import json
from pathlib import Path

from poker2.tools.paired_compare import build_paired_compare


def main() -> int:
    p = argparse.ArgumentParser(description="Paired compare between two scrimmage_batch outputs.")
    p.add_argument("--baseline", type=Path, required=True, help="Path to baseline scrimmage_batch.json")
    p.add_argument("--candidate", type=Path, required=True, help="Path to candidate scrimmage_batch.json")
    p.add_argument("--metric", type=str, default="bb_per_100", help="Metric key in scrimmage_report.analysis")
    p.add_argument("--bootstrap", type=int, default=0, help="Bootstrap samples for CI (0 disables)")
    p.add_argument("--alpha", type=float, default=0.05, help="Bootstrap alpha (default 0.05)")
    p.add_argument("--seed", type=int, default=0, help="Bootstrap RNG seed")
    p.add_argument("--out", type=Path, default=None, help="Output JSON path (default: candidate dir/paired_compare.json)")
    p.add_argument("--strict", action="store_true", help="Exit non-zero on seed/options mismatch")
    args = p.parse_args()

    result = build_paired_compare(
        baseline_batch=args.baseline,
        candidate_batch=args.candidate,
        metric_key=args.metric,
        bootstrap_samples=args.bootstrap if args.bootstrap > 0 else None,
        bootstrap_alpha=args.alpha,
        bootstrap_seed=args.seed,
    )
    out_path = args.out
    if out_path is None:
        out_path = args.candidate.parent / "paired_compare.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict:
        if result["missing_in_candidate"] or result["missing_in_baseline"] or result["options_hash_mismatch"]:
            return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
