from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SeatCounts:
    hands: int = 0
    vpip: int = 0
    pfr: int = 0
    threebet: int = 0
    threebet_opp: int = 0
    fourbet: int = 0
    fourbet_opp: int = 0
    postflop_agg: int = 0
    postflop_call: int = 0

    def merge(self, other: "SeatCounts") -> None:
        self.hands += other.hands
        self.vpip += other.vpip
        self.pfr += other.pfr
        self.threebet += other.threebet
        self.threebet_opp += other.threebet_opp
        self.fourbet += other.fourbet
        self.fourbet_opp += other.fourbet_opp
        self.postflop_agg += other.postflop_agg
        self.postflop_call += other.postflop_call


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_eventstream(path: Path) -> dict[int, SeatCounts]:
    counts: dict[int, SeatCounts] = {}
    decision_info: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return counts
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            ev = obj.get("event")
            if ev == "HandStart":
                seats = obj.get("seats_in_hand") or []
                for seat in seats:
                    seat_id = int(seat)
                    counts.setdefault(seat_id, SeatCounts()).hands += 1
            elif ev == "DecisionPoint":
                dec_id = obj.get("decision_id")
                if dec_id is None:
                    continue
                snap = obj.get("snapshot_payload") or {}
                obs = obj.get("observation_view_payload") or {}
                street = snap.get("street") or obs.get("street")
                actor = snap.get("actor_seat") or obs.get("actor_seat")
                if street is None or actor is None:
                    continue
                raise_count = 0
                if isinstance(obs.get("street_raise_count"), dict):
                    raise_count = int(obs["street_raise_count"].get(street, 0) or 0)
                decision_info[int(dec_id)] = {
                    "street": str(street),
                    "actor_seat": int(actor),
                    "to_call": int(snap.get("to_call_chips", 0) or 0),
                    "actor_commit": int(snap.get("actor_commit_chips", 0) or 0),
                    "raise_count": raise_count,
                }
            elif ev == "ActionChosen":
                dec_id = obj.get("decision_id")
                if dec_id is None or dec_id not in decision_info:
                    continue
                info = decision_info.get(int(dec_id)) or {}
                seat = info.get("actor_seat")
                if seat is None:
                    continue
                seat = int(seat)
                street = str(info.get("street", ""))
                to_call = int(info.get("to_call", 0) or 0)
                actor_commit = int(info.get("actor_commit", 0) or 0)
                raise_count = int(info.get("raise_count", 0) or 0)

                action = obj.get("executed_action") or obj.get("derived_action") or {}
                kind = str(action.get("kind") or "")
                target = int(action.get("target_total_commit_chips", actor_commit) or actor_commit)

                is_raise = kind in ("RAISE", "BET")
                is_call = kind == "CALL"
                if kind == "ALLIN":
                    if target > (actor_commit + to_call):
                        is_raise = True
                    else:
                        is_call = True

                seat_counts = counts.setdefault(seat, SeatCounts())

                if street == "PREFLOP":
                    if to_call > 0 and raise_count == 1:
                        seat_counts.threebet_opp += 1
                    if to_call > 0 and raise_count >= 2:
                        seat_counts.fourbet_opp += 1
                    if is_raise:
                        seat_counts.pfr += 1
                        if raise_count == 1:
                            seat_counts.threebet += 1
                        elif raise_count >= 2:
                            seat_counts.fourbet += 1
                    if is_raise or (is_call and to_call > 0):
                        seat_counts.vpip += 1
                else:
                    if is_raise or kind == "BET":
                        seat_counts.postflop_agg += 1
                    if is_call:
                        seat_counts.postflop_call += 1
    return counts


def _rate(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def _seat_metrics(counts: SeatCounts) -> dict[str, float | int]:
    return {
        "hands": counts.hands,
        "vpip": round(_rate(counts.vpip, counts.hands), 4),
        "pfr": round(_rate(counts.pfr, counts.hands), 4),
        "threebet": round(_rate(counts.threebet, max(1, counts.threebet_opp)), 4),
        "fourbet": round(_rate(counts.fourbet, max(1, counts.fourbet_opp)), 4),
        "af": round(_rate(counts.postflop_agg, max(1, counts.postflop_call)), 3),
    }


def _default_ranges() -> dict[str, dict[str, float]]:
    return {
        "vpip": {"low": 0.15, "high": 0.40},
        "pfr": {"low": 0.12, "high": 0.35},
        "threebet": {"low": 0.03, "high": 0.14},
        "fourbet": {"low": 0.005, "high": 0.08},
        "af": {"low": 1.0, "high": 6.0},
    }


def _classify(value: float, low: float, high: float) -> str:
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "ok"


def build_opponent_compliance(
    batch_path: Path,
    *,
    jobs: int = 4,
    ranges: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    batch = _load_json(batch_path)
    seeds = list(batch.get("seeds") or [])
    opponents = batch.get("opponents")
    runs = batch.get("runs") or []
    report_paths: list[Path] = []
    for run in runs:
        ref = run.get("report_ref")
        if isinstance(ref, str) and ref.startswith("path:"):
            report_paths.append(Path(ref.replace("path:", "")))
    ranges = ranges or _default_ranges()

    def _per_report(report_path: Path) -> tuple[str, dict[int, SeatCounts], list[int]]:
        report = _load_json(report_path)
        seat_results = report.get("seat_results") or []
        opponent_seats = [int(r.get("seat")) for r in seat_results if r.get("role") == "system_bot_opponent"]
        event_ref = report.get("event_stream_ref")
        event_path = None
        if isinstance(event_ref, str) and event_ref.startswith("path:"):
            event_path = Path(event_ref.replace("path:", ""))
        if event_path is None:
            return (str(report_path), {}, opponent_seats)
        counts = _parse_eventstream(event_path)
        return (str(report_path), counts, opponent_seats)

    per_seed: list[dict[str, Any]] = []
    agg_counts = SeatCounts()
    seat_totals: dict[int, SeatCounts] = {}

    jobs = max(1, int(jobs))
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(_per_report, p) for p in report_paths]
        for fut in as_completed(futures):
            report_ref, counts, opponent_seats = fut.result()
            seat_rows: dict[int, dict[str, Any]] = {}
            for seat in opponent_seats:
                seat_counts = counts.get(seat)
                if seat_counts is None:
                    continue
                seat_totals.setdefault(seat, SeatCounts()).merge(seat_counts)
                agg_counts.merge(seat_counts)
                seat_rows[seat] = _seat_metrics(seat_counts)
            per_seed.append(
                {
                    "report_ref": report_ref,
                    "opponent_seats": opponent_seats,
                    "by_seat": seat_rows,
                }
            )

    by_seat = {str(seat): _seat_metrics(counts) for seat, counts in seat_totals.items()}
    aggregate = _seat_metrics(agg_counts)

    flags = []
    for metric, band in ranges.items():
        val = float(aggregate.get(metric, 0.0) or 0.0)
        status = _classify(val, band["low"], band["high"])
        flags.append({"metric": metric, "value": val, "status": status, "range": band})

    return {
        "schema_id": "opponent_compliance_v1",
        "batch_ref": f"path:{batch_path.resolve()}",
        "suite_id": opponents,
        "seeds": seeds,
        "aggregate": aggregate,
        "by_seat": by_seat,
        "flags": flags,
        "per_seed": per_seed,
    }
