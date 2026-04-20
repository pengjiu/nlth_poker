from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SeedResult:
    seed: int
    metric: float
    options_hash: str | None
    report_path: str | None


def _load_seed_results(batch_path: Path, metric_key: str) -> dict[int, SeedResult]:
    data = json.loads(batch_path.read_text())
    runs = data.get("runs") or []
    results: dict[int, SeedResult] = {}
    for run in runs:
        seed = int(run.get("seed"))
        report_ref = run.get("report_ref") or ""
        report_path = None
        if isinstance(report_ref, str) and report_ref.startswith("path:"):
            report_path = report_ref.split("path:", 1)[1]
        metric_val = None
        if report_path:
            report = json.loads(Path(report_path).read_text())
            metric_val = float(report.get("analysis", {}).get(metric_key, 0.0))
        options_hash = run.get("options_hash")
        results[seed] = SeedResult(
            seed=seed,
            metric=float(metric_val) if metric_val is not None else 0.0,
            options_hash=str(options_hash) if options_hash is not None else None,
            report_path=report_path,
        )
    return results


def build_paired_compare(
    *,
    baseline_batch: Path,
    candidate_batch: Path,
    metric_key: str = "bb_per_100",
    bootstrap_samples: int | None = None,
    bootstrap_alpha: float = 0.05,
    bootstrap_seed: int = 0,
) -> dict[str, Any]:
    baseline = _load_seed_results(baseline_batch, metric_key)
    candidate = _load_seed_results(candidate_batch, metric_key)
    baseline_seeds = set(baseline.keys())
    candidate_seeds = set(candidate.keys())
    missing_in_candidate = sorted(baseline_seeds - candidate_seeds)
    missing_in_baseline = sorted(candidate_seeds - baseline_seeds)
    common = sorted(baseline_seeds & candidate_seeds)
    deltas: list[float] = []
    mismatched_options: list[dict[str, Any]] = []
    for seed in common:
        base = baseline[seed]
        cand = candidate[seed]
        deltas.append(cand.metric - base.metric)
        if base.options_hash != cand.options_hash:
            mismatched_options.append(
                {
                    "seed": seed,
                    "baseline": base.options_hash,
                    "candidate": cand.options_hash,
                }
            )
    n = len(deltas)
    mean = sum(deltas) / n if n else 0.0
    if n > 1:
        var = sum((d - mean) ** 2 for d in deltas) / (n - 1)
        std = math.sqrt(var)
    else:
        std = 0.0
    se = std / math.sqrt(n) if n > 1 else 0.0
    bootstrap = None
    if bootstrap_samples and n > 0:
        samples = max(1, int(bootstrap_samples))
        alpha = max(0.0, min(0.49, float(bootstrap_alpha)))
        rng = random.Random(int(bootstrap_seed))
        means: list[float] = []
        for _ in range(samples):
            total = 0.0
            for _ in range(n):
                total += deltas[rng.randrange(n)]
            means.append(total / n)
        means.sort()
        lo_idx = int(math.floor((alpha / 2.0) * (samples - 1)))
        hi_idx = int(math.floor((1.0 - alpha / 2.0) * (samples - 1)))
        med_idx = int(math.floor(0.5 * (samples - 1)))
        bootstrap = {
            "samples": samples,
            "alpha": alpha,
            "seed": int(bootstrap_seed),
            "mean": sum(means) / len(means),
            "median": means[med_idx],
            "ci_low": means[lo_idx],
            "ci_high": means[hi_idx],
        }
    return {
        "schema_id": "paired_compare_v1",
        "baseline_batch": f"path:{baseline_batch}",
        "candidate_batch": f"path:{candidate_batch}",
        "metric_key": metric_key,
        "seeds": common,
        "missing_in_candidate": missing_in_candidate,
        "missing_in_baseline": missing_in_baseline,
        "options_hash_mismatch": mismatched_options,
        "bootstrap": bootstrap,
        "delta": {
            "mean": mean,
            "std": std,
            "se": se,
            "min": min(deltas) if deltas else 0.0,
            "max": max(deltas) if deltas else 0.0,
        },
    }
