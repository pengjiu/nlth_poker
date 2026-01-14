from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Leak:
    leak_id: str
    severity: str
    metric: str
    value: float
    threshold: float
    context: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "leak_id": self.leak_id,
            "severity": self.severity,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "context": self.context,
        }


class ScrimmageReportAnalyzer:
    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        self.analysis = report.get("analysis") or {}

    @staticmethod
    def _rate(num: float, den: float) -> float:
        return float(num) / float(den) if den else 0.0

    def summary(self) -> dict[str, Any]:
        a = self.analysis
        hands = int(a.get("hands", self.report.get("hands", 0)) or 0)
        return {
            "hands": hands,
            "bb_per_100_net": float(a.get("bb_per_100", 0.0) or 0.0),
            "bb_per_100_gross": float(a.get("profit_bb_gross", 0.0) or 0.0) * 100 / max(1, hands),
            "profit_bb_net": float(a.get("profit_bb", 0.0) or 0.0),
            "profit_bb_gross": float(a.get("profit_bb_gross", 0.0) or 0.0),
            "rake_bb_per_100": float(a.get("rake_bb_per_100", 0.0) or 0.0),
            "avg_pot_bb": float(a.get("avg_pot_bb", 0.0) or 0.0),
            "vpip": float(a.get("vpip_pct", 0.0) or 0.0),
            "pfr": float(a.get("pfr_pct", 0.0) or 0.0),
            "wtsd": float(a.get("wtsd", 0.0) or 0.0),
            "wwsf": float(a.get("wwsf", 0.0) or 0.0),
            "wsd": float(a.get("wsd", 0.0) or 0.0),
            "flop_reach": self._rate(a.get("saw_flop_hands", 0), hands),
            "turn_reach": self._rate(a.get("saw_turn_hands", 0), hands),
            "river_reach": self._rate(a.get("saw_river_hands", 0), hands),
            "showdown_rate": self._rate(a.get("showdown_hands", 0), hands),
            "open": int(a.get("open", 0) or 0),
            "threebet": int(a.get("threebet", 0) or 0),
            "fourbet": int(a.get("fourbet", 0) or 0),
            "open_steal_rate": self._rate(a.get("open_steal_success", 0), max(1, a.get("open", 0))),
            "open_steal_rate_late": self._rate(a.get("open_steal_success_late", 0), max(1, a.get("open_late", 0))),
            "threebet_success_rate": self._rate(a.get("threebet_success", 0), max(1, a.get("threebet", 0))),
        }

    def _collect_mdf_gaps(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for street, st in (self.analysis.get("mdf_stats") or {}).items():
            facing = int(st.get("facing", 0) or 0)
            defend = int(st.get("defend", 0) or 0)
            if facing <= 0:
                continue
            mdf_adj = float(st.get("mdf_adj_sum", 0.0) or 0.0) / max(1, facing)
            defend_rate = defend / max(1, facing)
            rows.append(
                {
                    "street": street,
                    "facing": facing,
                    "defend_rate": defend_rate,
                    "mdf_adj": mdf_adj,
                    "gap_adj": defend_rate - mdf_adj,
                }
            )
        return rows

    def _collect_price_gaps(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for bucket, st in (self.analysis.get("facing_price_stats") or {}).items():
            facing = int(st.get("facing", 0) or 0)
            defend = int(st.get("defend", 0) or 0)
            if facing <= 0:
                continue
            mdf_adj = float(st.get("mdf_adj_sum", 0.0) or 0.0) / max(1, facing)
            defend_rate = defend / max(1, facing)
            rows.append(
                {
                    "bucket": bucket,
                    "facing": facing,
                    "defend_rate": defend_rate,
                    "mdf_adj": mdf_adj,
                    "gap_adj": defend_rate - mdf_adj,
                }
            )
        return rows

    def _collect_position_ev(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pos, st in (self.analysis.get("position_profit") or {}).items():
            hands = int(st.get("hands", 0) or 0)
            prof = float(st.get("profit_bb", 0.0) or 0.0)
            rows.append(
                {
                    "pos": pos,
                    "hands": hands,
                    "bb_per_100": prof * 100 / max(1, hands),
                    "vpip": self._rate(st.get("vpip_hands", 0), hands),
                    "pfr": self._rate(st.get("pfr_hands", 0), hands),
                }
            )
        return rows

    def _collect_role_ev(self, key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for role, st in (self.analysis.get(key) or {}).items():
            hands = int(st.get("hands", 0) or 0)
            prof = float(st.get("profit_bb", 0.0) or 0.0)
            rows.append(
                {
                    "role": role,
                    "hands": hands,
                    "bb_per_100": prof * 100 / max(1, hands),
                }
            )
        return rows

    def _collect_bb_vs_open_by_pos(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        order = {"BU": 0, "SB": 1, "BB": 2, "OTHERS": 3}
        data = self.analysis.get("bb_vs_open_by_pos") or {}
        for pos, st in sorted(data.items(), key=lambda x: order.get(x[0], 9)):
            fold = int(st.get("fold", 0) or 0)
            call = int(st.get("call", 0) or 0)
            threebet = int(st.get("3bet", 0) or 0)
            total = max(1, fold + call + threebet)
            rows.append(
                {
                    "opener_pos": pos,
                    "fold": fold,
                    "call": call,
                    "3bet": threebet,
                    "defend_rate": self._rate(call + threebet, total),
                    "fold_rate": self._rate(fold, total),
                }
            )
        return rows

    def _collect_bb_vs_open_by_size(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        order = {"2.0-2.5": 0, "2.5-3.0": 1, "3.0-3.5": 2, "3.5-4.5": 3, "4.5+": 4}
        data = self.analysis.get("bb_vs_open_by_size") or {}
        for size, st in sorted(data.items(), key=lambda x: order.get(x[0], 9)):
            fold = int(st.get("fold", 0) or 0)
            call = int(st.get("call", 0) or 0)
            threebet = int(st.get("3bet", 0) or 0)
            total = max(1, fold + call + threebet)
            rows.append(
                {
                    "open_size_bb": size,
                    "fold": fold,
                    "call": call,
                    "3bet": threebet,
                    "defend_rate": self._rate(call + threebet, total),
                    "fold_rate": self._rate(fold, total),
                }
            )
        return rows

    def _collect_bb_flat_postflop(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        data = self.analysis.get("bb_flat_postflop") or []
        if isinstance(data, dict):
            entries = list(data.values())
        elif isinstance(data, list):
            entries = data
        else:
            entries = []
        for entry in sorted(entries, key=lambda e: (str(e.get("spr_bucket")), bool(e.get("oop_multi_street")))):
            hands = int(entry.get("hands", 0) or 0)
            profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
            rows.append(
                {
                    "spr_bucket": entry.get("spr_bucket"),
                    "oop_multi_street": bool(entry.get("oop_multi_street", False)),
                    "hands": hands,
                    "profit_bb": round(profit_bb, 2),
                    "bb_per_100": round(self._rate(profit_bb * 100, hands), 2),
                }
            )
        return rows

    def _collect_open_by_pos(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        order = {"BU": 0, "SB": 1, "BB": 2, "OTHERS": 3}
        data = self.analysis.get("open_by_pos") or {}
        for pos, st in sorted(data.items(), key=lambda x: order.get(x[0], 9)):
            open_ct = int(st.get("open", 0) or 0)
            steal_ct = int(st.get("steal", 0) or 0)
            rows.append(
                {
                    "pos": pos,
                    "open": open_ct,
                    "steal": steal_ct,
                    "steal_rate": self._rate(steal_ct, max(1, open_ct)),
                }
            )
        return rows

    def detect_leaks(self, *, min_severity: str = "low") -> list[dict[str, Any]]:
        severity_order = {"low": 0, "medium": 1, "high": 2}
        min_rank = severity_order.get(min_severity, 0)
        leaks: list[Leak] = []
        a = self.analysis
        hands = int(a.get("hands", self.report.get("hands", 0)) or 0)

        def add(leak: Leak) -> None:
            if severity_order.get(leak.severity, 0) >= min_rank:
                leaks.append(leak)

        # Rake pressure
        rake_bb_100 = float(a.get("rake_bb_per_100", 0.0) or 0.0)
        if rake_bb_100 >= 90:
            add(
                Leak(
                    "rake_pressure_high",
                    "medium",
                    "rake_bb_per_100",
                    rake_bb_100,
                    90.0,
                    {"hands": hands},
                )
            )

        # MDF gaps by street
        for row in self._collect_mdf_gaps():
            facing = row["facing"]
            gap = row["gap_adj"]
            if facing >= 25 and gap <= -0.25:
                add(Leak("mdf_underdefend", "high", "gap_adj", gap, -0.25, row))
            elif facing >= 25 and gap <= -0.15:
                add(Leak("mdf_underdefend", "medium", "gap_adj", gap, -0.15, row))

        # Defense vs price buckets (all streets)
        for row in self._collect_price_gaps():
            facing = row["facing"]
            gap = row["gap_adj"]
            if facing >= 40 and gap <= -0.25 and row["bucket"] in ("0.20-0.33", "0.33-0.50"):
                add(Leak("price_underdefend", "high", "gap_adj", gap, -0.25, row))

        # Non-showdown / showdown imbalance
        nsd = float(a.get("non_showdown_profit_bb", 0.0) or 0.0)
        sd = float(a.get("showdown_profit_bb", 0.0) or 0.0)
        nsd_100 = nsd * 100 / max(1, hands)
        if nsd_100 <= -30:
            add(Leak("non_showdown_leak", "medium", "bb_per_100", nsd_100, -30.0, {"hands": hands}))
        if sd < 0 and abs(sd) > abs(nsd) * 0.4 and hands >= 300:
            add(Leak("showdown_leak", "low", "profit_bb", sd, 0.0, {"hands": hands}))

        # Position EV
        for row in self._collect_position_ev():
            if row["hands"] >= 100 and row["bb_per_100"] <= -25:
                add(Leak("position_ev_negative", "medium", "bb_per_100", row["bb_per_100"], -25.0, row))

        # Preflop / Postflop role EV
        for row in self._collect_role_ev("preflop_role_profit"):
            if row["hands"] >= 30 and row["bb_per_100"] <= -50:
                add(Leak("preflop_role_ev", "medium", "bb_per_100", row["bb_per_100"], -50.0, row))
        for row in self._collect_role_ev("postflop_role_profit"):
            if row["hands"] >= 30 and row["bb_per_100"] <= -50:
                add(Leak("postflop_role_ev", "medium", "bb_per_100", row["bb_per_100"], -50.0, row))

        # Steal / 3bet success
        open_ct = int(a.get("open", 0) or 0)
        open_rate = self._rate(a.get("open_steal_success", 0), max(1, open_ct))
        if open_ct >= 40 and open_rate < 0.10:
            add(Leak("steal_success_low", "medium", "open_steal_rate", open_rate, 0.10, {"open": open_ct}))
        threebet_ct = int(a.get("threebet", 0) or 0)
        threebet_succ = self._rate(a.get("threebet_success", 0), max(1, threebet_ct))
        if threebet_ct >= 30 and threebet_succ < 0.05:
            add(Leak("threebet_success_low", "low", "threebet_success_rate", threebet_succ, 0.05, {"threebet": threebet_ct}))

        # BB defend vs open (by opener position)
        bb_by_pos = self._collect_bb_vs_open_by_pos()
        for row in bb_by_pos:
            total = int(row.get("fold", 0) or 0) + int(row.get("call", 0) or 0) + int(row.get("3bet", 0) or 0)
            if total < 25:
                continue
            defend = float(row.get("defend_rate", 0.0) or 0.0)
            opener_pos = row.get("opener_pos")
            if opener_pos in ("BU", "SB") and defend < 0.12:
                add(Leak("bb_underdefend_vs_late", "high", "defend_rate", defend, 0.12, row))
            elif defend < 0.08:
                add(Leak("bb_underdefend_vs_open", "medium", "defend_rate", defend, 0.08, row))

        # BB flat postflop EV (SPR/OOP multi-street)
        for row in self._collect_bb_flat_postflop():
            hands_ct = int(row.get("hands", 0) or 0)
            bb100 = float(row.get("bb_per_100", 0.0) or 0.0)
            if hands_ct >= 20 and bb100 <= -120:
                add(Leak("bb_flat_postflop_ev", "medium", "bb_per_100", bb100, -120.0, row))

        return [l.as_dict() for l in leaks]

    def to_structured(self, *, min_severity: str = "low", include_tables: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_id": "scrimmage_insights_v1",
            "source_report_ref": self.report.get("event_stream_ref"),
            "summary": self.summary(),
            "leaks": self.detect_leaks(min_severity=min_severity),
        }
        if include_tables:
            payload["tables"] = {
                "mdf_gaps": self._collect_mdf_gaps(),
                "price_gaps": self._collect_price_gaps(),
                "position_ev": self._collect_position_ev(),
                "preflop_role_ev": self._collect_role_ev("preflop_role_profit"),
                "postflop_role_ev": self._collect_role_ev("postflop_role_profit"),
                "bb_vs_open_by_pos": self._collect_bb_vs_open_by_pos(),
                "bb_vs_open_by_size": self._collect_bb_vs_open_by_size(),
                "bb_flat_postflop": self._collect_bb_flat_postflop(),
                "open_by_pos": self._collect_open_by_pos(),
            }
        return payload
