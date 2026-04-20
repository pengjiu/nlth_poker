from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from poker2.protocol.retaliation_model import DEFAULT_BUCKET_SPEC, retaliation_bucket_key
from poker2.protocol.treepath_mapping import position_key


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_report_paths(batch_path: Path) -> list[Path]:
    batch = _load_json(batch_path)
    paths: list[Path] = []
    for run in batch.get("runs", []):
        ref = run.get("report_ref")
        if isinstance(ref, str) and ref.startswith("path:"):
            paths.append(Path(ref.replace("path:", "")))
    return paths


def _parse_eventstream(path: Path, weight: float) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    weight = float(weight)
    buckets: dict[str, dict[str, float]] = {}
    global_counts = {
        "bet_count": 0.0,
        "raise_count": 0.0,
        "call_count": 0.0,
        "raise_profit_sum": 0.0,
        "call_profit_sum": 0.0,
    }
    decision_info: dict[int, dict[str, Any]] = {}
    pending: list[str] = []
    raised_keys: list[str] = []
    called_keys: list[str] = []
    system_seat: int | None = None
    last_system_bet_key: str | None = None
    current_street = "PREFLOP"
    if not path.exists():
        return buckets, global_counts
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            ev = obj.get("event")
            if ev == "HandStart":
                decision_info.clear()
                pending.clear()
                raised_keys.clear()
                called_keys.clear()
                last_system_bet_key = None
                current_street = "PREFLOP"
            elif ev == "StreetDealt":
                current_street = str(obj.get("street") or current_street)
                pending.clear()
                last_system_bet_key = None
            elif ev == "DecisionPoint":
                dec_id = obj.get("decision_id")
                if dec_id is None:
                    continue
                snap = obj.get("snapshot_payload") or {}
                obs = obj.get("observation_view_payload") or {}
                street = snap.get("street") or obs.get("street") or current_street
                decision_info[int(dec_id)] = {
                    "street": str(street),
                    "actor_seat": int(snap.get("actor_seat", 0) or 0),
                    "to_call": int(snap.get("to_call_chips", 0) or 0),
                    "actor_commit": int(snap.get("actor_commit_chips", 0) or 0),
                    "pot_chips": int(snap.get("pot_chips", 0) or 0),
                    "actor_stack": int(snap.get("actor_stack_chips", 0) or 0),
                    "players_alive": int(snap.get("players_alive_count", 0) or 0),
                    "button_seat": int(obs.get("button_seat", 0) or 0),
                    "seats_in_hand": obs.get("seats_in_hand") or [],
                }
            elif ev == "ActionChosen":
                dec_id = obj.get("decision_id")
                if dec_id is None or dec_id not in decision_info:
                    continue
                info = decision_info.get(int(dec_id)) or {}
                street = str(info.get("street") or current_street)
                if street not in ("FLOP", "TURN", "RIVER"):
                    continue
                to_call = int(info.get("to_call", 0) or 0)
                actor_commit = int(info.get("actor_commit", 0) or 0)
                pot_chips = int(info.get("pot_chips", 0) or 0)
                actor_stack = int(info.get("actor_stack", 0) or 0)
                players_alive = int(info.get("players_alive", 0) or 0)
                button_seat = int(info.get("button_seat", 0) or 0)
                seats_in_hand = info.get("seats_in_hand") or []
                pos = position_key(int(info.get("actor_seat", 0) or 0), button_seat, seats_in_hand)

                action = obj.get("executed_action") or obj.get("derived_action") or {}
                kind = str(action.get("kind") or "")
                target = int(action.get("target_total_commit_chips", actor_commit) or actor_commit)

                if obj.get("action_source_id") == "system_policy":
                    if system_seat is None:
                        system_seat = int(info.get("actor_seat", 0) or 0)
                    if to_call == 0 and kind in ("BET", "RAISE", "ALLIN"):
                        add = max(0, target - actor_commit)
                        if add <= 0:
                            continue
                        pot_base = max(1, pot_chips)
                        size_ratio_ppm = int((add * 1_000_000) / pot_base)
                        spr = float(actor_stack) / float(pot_base) if pot_base > 0 else 99.0
                        key = retaliation_bucket_key(
                            street=street,
                            players_alive=players_alive,
                            pos_key=pos,
                            spr=spr,
                            size_ratio_ppm=size_ratio_ppm,
                            bucket_spec=DEFAULT_BUCKET_SPEC,
                        )
                        entry = buckets.setdefault(
                            key,
                            {
                                "bet_count": 0.0,
                                "raise_count": 0.0,
                                "call_count": 0.0,
                                "raise_profit_sum": 0.0,
                                "call_profit_sum": 0.0,
                            },
                        )
                        entry["bet_count"] += weight
                        global_counts["bet_count"] += weight
                        pending.append(key)
                        last_system_bet_key = key
                else:
                    if to_call > 0 and kind in ("RAISE", "BET", "ALLIN") and pending:
                        key = pending.pop()
                        entry = buckets.setdefault(
                            key,
                            {
                                "bet_count": 0.0,
                                "raise_count": 0.0,
                                "call_count": 0.0,
                                "raise_profit_sum": 0.0,
                                "call_profit_sum": 0.0,
                            },
                        )
                        entry["raise_count"] += weight
                        global_counts["raise_count"] += weight
                        raised_keys.append(key)
                    elif to_call > 0 and kind == "CALL" and last_system_bet_key:
                        key = last_system_bet_key
                        entry = buckets.setdefault(
                            key,
                            {
                                "bet_count": 0.0,
                                "raise_count": 0.0,
                                "call_count": 0.0,
                                "raise_profit_sum": 0.0,
                                "call_profit_sum": 0.0,
                            },
                        )
                        entry["call_count"] += weight
                        global_counts["call_count"] += weight
                        called_keys.append(key)
            elif ev == "HandEnd":
                if system_seat is not None and raised_keys:
                    deltas = obj.get("stack_deltas_by_seat") or {}
                    profit = deltas.get(str(system_seat))
                    if profit is None:
                        profit = deltas.get(system_seat, 0)
                    profit = int(profit or 0)
                    for key in raised_keys:
                        entry = buckets.setdefault(
                            key,
                            {
                                "bet_count": 0.0,
                                "raise_count": 0.0,
                                "call_count": 0.0,
                                "raise_profit_sum": 0.0,
                                "call_profit_sum": 0.0,
                            },
                        )
                        entry["raise_profit_sum"] = float(entry.get("raise_profit_sum", 0.0) or 0.0) + (float(profit) * weight)
                    global_counts["raise_profit_sum"] += float(profit) * weight * len(raised_keys)
                if system_seat is not None and called_keys:
                    deltas = obj.get("stack_deltas_by_seat") or {}
                    profit = deltas.get(str(system_seat))
                    if profit is None:
                        profit = deltas.get(system_seat, 0)
                    profit = int(profit or 0)
                    for key in called_keys:
                        entry = buckets.setdefault(
                            key,
                            {
                                "bet_count": 0.0,
                                "raise_count": 0.0,
                                "call_count": 0.0,
                                "raise_profit_sum": 0.0,
                                "call_profit_sum": 0.0,
                            },
                        )
                        entry["call_profit_sum"] = float(entry.get("call_profit_sum", 0.0) or 0.0) + (float(profit) * weight)
                    global_counts["call_profit_sum"] += float(profit) * weight * len(called_keys)
                pending.clear()
                raised_keys.clear()
                called_keys.clear()
                last_system_bet_key = None
                decision_info.clear()
    return buckets, global_counts


def main() -> int:
    p = argparse.ArgumentParser(description="Build retaliation model from scrimmage batches.")
    p.add_argument("--batches", required=True, help="Comma list or JSON list of scrimmage_batch.json paths")
    p.add_argument("--out", type=Path, required=True, help="Output JSON path")
    p.add_argument("--jobs", type=int, default=4, help="Parallel parse workers")
    p.add_argument("--decay", type=float, default=1.0, help="Per-batch decay factor for recency weighting (0-1]")
    args = p.parse_args()

    raw = args.batches.strip()
    if raw.startswith("["):
        batch_paths = [Path(p) for p in json.loads(raw)]
    else:
        batch_paths = [Path(p.strip()) for p in raw.split(",") if p.strip()]

    decay = float(args.decay)
    if decay <= 0:
        decay = 0.0
    if decay > 1.0:
        decay = 1.0
    report_paths: list[tuple[Path, float]] = []
    if batch_paths:
        total = len(batch_paths)
        for idx, batch_path in enumerate(batch_paths):
            weight = 1.0
            if decay > 0 and decay < 1.0:
                weight = decay ** max(0, (total - 1 - idx))
            for rp in _iter_report_paths(batch_path):
                report_paths.append((rp, float(weight)))

    event_paths: list[tuple[Path, float]] = []
    for report_path, weight in report_paths:
        report = _load_json(report_path)
        ref = report.get("event_stream_ref")
        if isinstance(ref, str) and ref.startswith("path:"):
            event_paths.append((Path(ref.replace("path:", "")), weight))

    buckets: dict[str, dict[str, float]] = {}
    global_counts = {
        "bet_count": 0.0,
        "raise_count": 0.0,
        "call_count": 0.0,
        "raise_profit_sum": 0.0,
        "call_profit_sum": 0.0,
    }

    jobs = max(1, int(args.jobs))
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(_parse_eventstream, p, w) for p, w in event_paths]
        for fut in as_completed(futures):
            b, g = fut.result()
            for key, counts in b.items():
                entry = buckets.setdefault(
                    key,
                    {
                        "bet_count": 0.0,
                        "raise_count": 0.0,
                        "call_count": 0.0,
                        "raise_profit_sum": 0.0,
                        "call_profit_sum": 0.0,
                    },
                )
                entry["bet_count"] += float(counts.get("bet_count", 0.0) or 0.0)
                entry["raise_count"] += float(counts.get("raise_count", 0.0) or 0.0)
                entry["call_count"] += float(counts.get("call_count", 0.0) or 0.0)
                entry["raise_profit_sum"] += float(counts.get("raise_profit_sum", 0.0) or 0.0)
                entry["call_profit_sum"] += float(counts.get("call_profit_sum", 0.0) or 0.0)
            global_counts["bet_count"] += float(g.get("bet_count", 0.0) or 0.0)
            global_counts["raise_count"] += float(g.get("raise_count", 0.0) or 0.0)
            global_counts["call_count"] += float(g.get("call_count", 0.0) or 0.0)
            global_counts["raise_profit_sum"] += float(g.get("raise_profit_sum", 0.0) or 0.0)
            global_counts["call_profit_sum"] += float(g.get("call_profit_sum", 0.0) or 0.0)

    bucket_rows = []
    for key, counts in buckets.items():
        street, players_bucket, pos_bucket, spr_bucket, size_bucket = key.split("|")
        bucket_rows.append(
            {
                "street": street,
                "players_bucket": players_bucket,
                "pos_bucket": pos_bucket,
                "spr_bucket": spr_bucket,
                "size_bucket": size_bucket,
                "bet_count": float(counts.get("bet_count", 0.0) or 0.0),
                "raise_count": float(counts.get("raise_count", 0.0) or 0.0),
                "call_count": float(counts.get("call_count", 0.0) or 0.0),
                "raise_profit_sum": float(counts.get("raise_profit_sum", 0.0) or 0.0),
                "call_profit_sum": float(counts.get("call_profit_sum", 0.0) or 0.0),
            }
        )

    batch_weights = []
    if batch_paths:
        total = len(batch_paths)
        for idx, p in enumerate(batch_paths):
            weight = 1.0
            if decay > 0 and decay < 1.0:
                weight = decay ** max(0, (total - 1 - idx))
            batch_weights.append({"batch_ref": f"path:{p.resolve()}", "weight": float(weight)})

    model = {
        "schema_id": "retaliation_model_v2",
        "bucket_spec": DEFAULT_BUCKET_SPEC,
        "global": global_counts,
        "decay": decay,
        "batch_weights": batch_weights,
        "source_batches": [f"path:{p.resolve()}" for p in batch_paths],
        "buckets": bucket_rows,
    }
    args.out.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
