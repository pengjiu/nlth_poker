from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_coverage_check(
    batch_path: Path,
    *,
    keys: list[str],
    min_n: int,
) -> dict[str, Any]:
    batch = _load_json(batch_path)
    runs = batch.get("runs", [])
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"hands": 0, "profit_bb": 0.0})
    per_seed: dict[str, list[int]] = defaultdict(list)
    for run in runs:
        report_ref = run.get("report_ref")
        if not isinstance(report_ref, str) or not report_ref.startswith("path:"):
            continue
        report_path = Path(report_ref.removeprefix("path:"))
        views_path = report_path.parent / "scrimmage_views.json"
        if not views_path.exists():
            continue
        views = _load_json(views_path)
        index = views.get("index") or {}
        for key in keys:
            entry = index.get(key)
            if not isinstance(entry, dict):
                continue
            row = entry.get("row") or {}
            hands = int(row.get("hands", 0) or 0)
            profit_bb = float(row.get("profit_bb", 0.0) or 0.0)
            totals[key]["hands"] += hands
            totals[key]["profit_bb"] += profit_bb
            if hands > 0:
                per_seed[key].append(int(run.get("seed", 0)))

    coverage_rows: list[dict[str, Any]] = []
    all_pass = True
    for key in keys:
        hands = int(totals[key]["hands"])
        profit_bb = float(totals[key]["profit_bb"])
        bb100 = profit_bb * 100.0 / max(1, hands)
        ok = hands >= int(min_n)
        all_pass = all_pass and ok
        coverage_rows.append(
            {
                "bucket_key": key,
                "hands": hands,
                "profit_bb": round(profit_bb, 2),
                "bb_per_100": round(bb100, 2),
                "min_n": int(min_n),
                "pass": bool(ok),
                "seeds": sorted(set(per_seed.get(key, []))),
            }
        )

    return {
        "schema_id": "coverage_check_v1",
        "batch_ref": f"path:{batch_path.resolve()}",
        "min_n": int(min_n),
        "buckets": coverage_rows,
        "pass": bool(all_pass),
    }

