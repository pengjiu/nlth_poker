from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _rate(num: float, denom: float) -> float:
    return float(num) / max(1.0, float(denom))


def _bb_per_100(profit_bb: float, hands: int) -> float:
    return float(profit_bb) * 100.0 / max(1, int(hands))


@dataclass(frozen=True)
class WeaknessSignal:
    signal_id: str
    severity: str
    summary: str
    evidence: dict[str, Any]


class ScrimmageInspector:
    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        self.analysis = report.get("analysis", {}) if isinstance(report, dict) else {}

    def build(self) -> dict[str, Any]:
        analysis = self.analysis
        hands = int(analysis.get("hands", 0) or 0)
        bb_per_100 = float(analysis.get("bb_per_100", 0.0) or 0.0)
        rake_bb_per_100 = float(analysis.get("rake_bb_per_100", 0.0) or 0.0)
        wtsd = float(analysis.get("wtsd", 0.0) or 0.0)
        wwsf = float(analysis.get("wwsf", 0.0) or 0.0)
        wsd = float(analysis.get("wsd", 0.0) or 0.0)
        non_showdown_bb = float(analysis.get("non_showdown_profit_bb", 0.0) or 0.0)
        showdown_bb = float(analysis.get("showdown_profit_bb", 0.0) or 0.0)

        weaknesses: list[WeaknessSignal] = []

        def _add(signal_id: str, severity: str, summary: str, evidence: dict[str, Any]) -> None:
            weaknesses.append(WeaknessSignal(signal_id, severity, summary, evidence))

        # Overall performance
        if bb_per_100 <= -50:
            _add("net_bb_per_100", "critical", "净胜率严重为负", {"bb_per_100": bb_per_100, "hands": hands})
        elif bb_per_100 <= -20:
            _add("net_bb_per_100", "high", "净胜率显著为负", {"bb_per_100": bb_per_100, "hands": hands})
        elif bb_per_100 <= -10:
            _add("net_bb_per_100", "medium", "净胜率为负", {"bb_per_100": bb_per_100, "hands": hands})

        # Rake pressure
        if rake_bb_per_100 >= 20:
            _add("rake_pressure", "medium", "抽水压力高", {"rake_bb_per_100": rake_bb_per_100})

        # Showdown / non-showdown imbalance
        if non_showdown_bb < 0 and abs(non_showdown_bb) > max(100.0, abs(showdown_bb) * 0.5):
            _add(
                "non_showdown_leak",
                "high",
                "非摊牌损失偏大",
                {"non_showdown_profit_bb": non_showdown_bb, "showdown_profit_bb": showdown_bb},
            )

        # MDF gaps
        mdf_stats = analysis.get("mdf_stats") or {}
        if isinstance(mdf_stats, dict):
            for street, st in mdf_stats.items():
                facing = int(st.get("facing", 0) or 0)
                if facing <= 0:
                    continue
                defend = int(st.get("defend", 0) or 0)
                mdf_adj = _rate(float(st.get("mdf_adj_sum", 0.0) or 0.0), facing)
                defend_rate = _rate(defend, facing)
                gap = defend_rate - mdf_adj
                if gap <= -0.1:
                    severity = "high" if gap <= -0.2 else "medium"
                    _add(
                        f"under_defend_{street.lower()}",
                        severity,
                        f"{street} 明显低于 MDF",
                        {"defend_rate": defend_rate, "mdf_adj": mdf_adj, "gap": gap, "facing": facing},
                    )
                elif gap >= 0.1:
                    severity = "medium"
                    _add(
                        f"over_defend_{street.lower()}",
                        severity,
                        f"{street} 防守偏过度",
                        {"defend_rate": defend_rate, "mdf_adj": mdf_adj, "gap": gap, "facing": facing},
                    )

        # Steal success
        steal = analysis.get("open_steal_success") or {}
        if isinstance(steal, dict):
            tries = int(steal.get("open", 0) or 0)
            wins = int(steal.get("steal", 0) or 0)
            if tries >= 20:
                rate = _rate(wins, tries)
                if rate <= 0.15:
                    _add("steal_fail", "medium", "偷盲成功率偏低", {"open": tries, "steal": wins, "rate": rate})

        # Preflop role EV
        preflop_roles = analysis.get("preflop_role_profit") or {}
        if isinstance(preflop_roles, dict):
            for role, entry in preflop_roles.items():
                if not isinstance(entry, dict):
                    continue
                hands_r = int(entry.get("hands", 0) or 0)
                profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
                if hands_r >= 20:
                    bb100 = _bb_per_100(profit_bb, hands_r)
                    if bb100 <= -50:
                        _add(
                            f"preflop_role_{role}",
                            "medium",
                            f"Preflop {role} EV 过低",
                            {"bb_per_100": bb100, "hands": hands_r},
                        )

        # Postflop role EV
        post_roles = analysis.get("postflop_role_profit") or {}
        if isinstance(post_roles, dict):
            for role, entry in post_roles.items():
                if not isinstance(entry, dict):
                    continue
                hands_r = int(entry.get("hands", 0) or 0)
                profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
                if hands_r >= 20:
                    bb100 = _bb_per_100(profit_bb, hands_r)
                    if bb100 <= -50:
                        _add(
                            f"postflop_role_{role}",
                            "medium",
                            f"Postflop {role} EV 过低",
                            {"bb_per_100": bb100, "hands": hands_r},
                        )

        # Position EV
        pos_profit = analysis.get("position_profit") or {}
        if isinstance(pos_profit, dict):
            for pos, entry in pos_profit.items():
                if not isinstance(entry, dict):
                    continue
                hands_p = int(entry.get("hands", 0) or 0)
                profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
                if hands_p >= 30:
                    bb100 = _bb_per_100(profit_bb, hands_p)
                    if bb100 <= -50:
                        _add(
                            f"pos_{pos.lower()}",
                            "medium",
                            f"{pos} 位置 EV 过低",
                            {"bb_per_100": bb100, "hands": hands_p},
                        )

        # WTS/WWFS heuristics
        if wtsd < 0.18 and wsd > 0.6:
            _add(
                "overfold_showdown",
                "medium",
                "摊牌过少但摊牌胜率偏高，疑似过度弃牌",
                {"wtsd": wtsd, "wsd": wsd},
            )
        if wwsf < 0.35 and wtsd < 0.25:
            _add(
                "low_wwsf",
                "medium",
                "争夺底池能力偏低",
                {"wwsf": wwsf, "wtsd": wtsd},
            )

        summary = {
            "bb_per_100": bb_per_100,
            "rake_bb_per_100": rake_bb_per_100,
            "vpip": float(analysis.get("vpip_pct", 0.0) or 0.0),
            "pfr": float(analysis.get("pfr_pct", 0.0) or 0.0),
            "wtsd": wtsd,
            "wwsf": wwsf,
            "wsd": wsd,
            "hands": hands,
        }

        return {
            "summary": summary,
            "weaknesses": [w.__dict__ for w in weaknesses],
        }

    @staticmethod
    def render_weakness_table(weaknesses: list[dict[str, Any]]) -> str:
        if not weaknesses:
            return "no_weakness_detected"
        headers = ["severity", "signal_id", "summary"]
        rows: list[list[str]] = []
        for w in weaknesses:
            rows.append([w.get("severity", ""), w.get("signal_id", ""), w.get("summary", "")])
        widths = [len(h) for h in headers]
        for r in rows:
            for i, c in enumerate(r):
                widths[i] = max(widths[i], len(str(c)))
        def fmt_row(r: list[str]) -> str:
            return " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(r))
        lines = [fmt_row(headers), "-+-".join("-" * w for w in widths)]
        lines.extend(fmt_row(r) for r in rows)
        return "\n".join(lines)
