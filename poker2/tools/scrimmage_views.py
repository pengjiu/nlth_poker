from __future__ import annotations

from typing import Any

from poker2.protocol.forced_bets import ante_display_value


def _rate(num: float, denom: float) -> float:
    return float(num) / max(1.0, float(denom))


def _fmt_table(headers: list[str], rows: list[dict[str, Any]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, key in enumerate(headers):
            widths[i] = max(widths[i], len(str(row.get(key, ""))))

    def fmt_row(values: list[Any]) -> str:
        return " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(values))

    lines = [fmt_row(headers), "-+-".join("-" * w for w in widths)]
    for row in rows:
        lines.append(fmt_row([row.get(h, "") for h in headers]))
    return "\n".join(lines)


class ScrimmageReportViews:
    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report if isinstance(report, dict) else {}
        self.analysis = self.report.get("analysis") or {}
        self.scene = self.report.get("scene") or {}

    def _env(self) -> dict[str, Any]:
        blinds = self.scene.get("blinds") or {}
        ante_cfg = self.scene.get("ante") or {}
        rake_cfg = self.scene.get("rake") or {}
        action_bins = self.scene.get("action_bins") or {}
        bet_bins = action_bins.get("bet_bins") or []
        raise_bins = action_bins.get("raise_bins") or []
        seats = self.report.get("seat_results") or []
        seats_in_hand = [int(row.get("seat")) for row in seats if isinstance(row, dict) and isinstance(row.get("seat"), int)]
        if seats_in_hand:
            ante_display = ante_display_value(
                ruleset={"ante": ante_cfg},
                seats_in_hand=seats_in_hand,
                strict_mode=False,
            )
        else:
            ante_display = "0"
        ante_uniform = ante_cfg.get("ante_chips") if isinstance(ante_cfg, dict) else None
        return {
            "players": len(seats),
            "sb": int(blinds.get("sb_chips", 0) or 0),
            "bb": int(blinds.get("bb_chips", self.report.get("bb_chips", 0)) or 0),
            "ante": int(ante_uniform or 0),
            "ante_display": ante_display,
            "stack_bb": float(self.analysis.get("starting_stack_bb", 0.0) or 0.0),
            "rake_rate": (rake_cfg.get("pct_ppm", 0) or 0) / 1_000_000.0,
            "rake_cap": int(rake_cfg.get("cap_chips", 0) or 0),
            "no_flop_no_drop": bool(rake_cfg.get("no_flop_no_drop", False)),
            "ruleset_id": self.scene.get("ruleset_id"),
            "scenario_id": self.scene.get("scenario_id"),
            "action_bins_id": self.scene.get("action_bins_id"),
            "bet_bins": bet_bins,
            "raise_bins": raise_bins,
            "mapping_spec_id": self.scene.get("mapping_spec_id"),
            "seed": self.scene.get("seed"),
        }

    def _summary(self) -> dict[str, Any]:
        a = self.analysis
        hands = int(a.get("hands", self.report.get("hands", 0)) or 0)
        win_hands = int(a.get("win_hands", 0) or 0)
        tie_hands = int(a.get("tie_hands", 0) or 0)
        loss_hands = int(a.get("loss_hands", 0) or 0)
        return {
            "hands": hands,
            "wins": win_hands,
            "ties": tie_hands,
            "losses": loss_hands,
            "winrate": float(a.get("winrate", 0.0) or 0.0),
            "profit_bb_net": float(a.get("profit_bb", 0.0) or 0.0),
            "profit_bb_gross": float(a.get("profit_bb_gross", 0.0) or 0.0),
            "bb_per_100_net": float(a.get("bb_per_100", 0.0) or 0.0),
            "bb_per_100_gross": float(a.get("profit_bb_gross", 0.0) or 0.0) * 100 / max(1, hands),
            "rake_bb_per_100": float(a.get("rake_bb_per_100", 0.0) or 0.0),
            "avg_pot_bb": float(a.get("avg_pot_bb", 0.0) or 0.0),
            "vpip": float(a.get("vpip_pct", 0.0) or 0.0),
            "pfr": float(a.get("pfr_pct", 0.0) or 0.0),
            "wtsd": float(a.get("wtsd", 0.0) or 0.0),
            "wwsf": float(a.get("wwsf", 0.0) or 0.0),
            "wsd": float(a.get("wsd", 0.0) or 0.0),
        }

    @staticmethod
    def _defense_rows(entry: dict[str, Any], label: str) -> dict[str, Any]:
        fold = int(entry.get("fold", 0) or 0)
        call = int(entry.get("call", 0) or 0)
        raise_ct = int(entry.get("raise", 0) or 0)
        total = max(1, fold + call + raise_ct)
        return {
            "vs": label,
            "fold": fold,
            "call": call,
            "raise": raise_ct,
            "fold_pct": round(fold / total, 3),
            "call_pct": round(call / total, 3),
            "raise_pct": round(raise_ct / total, 3),
        }

    def _table_preflop_defense(self) -> list[dict[str, Any]]:
        a = self.analysis
        return [
            self._defense_rows(a.get("defend_vs_open") or {}, "open"),
            self._defense_rows(a.get("defend_vs_3bet") or {}, "3bet"),
            self._defense_rows(a.get("defend_vs_4bet") or {}, "4bet+"),
        ]

    @staticmethod
    def _table_pos_defense(data: dict[str, Any], *, key_name: str, raise_key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pos, entry in sorted(data.items()):
            fold = int(entry.get("fold", 0) or 0)
            call = int(entry.get("call", 0) or 0)
            raise_ct = int(entry.get(raise_key, entry.get("raise", 0)) or 0)
            total = max(1, fold + call + raise_ct)
            rows.append(
                {
                    key_name: pos,
                    "fold": fold,
                    "call": call,
                    raise_key: raise_ct,
                    "fold_pct": round(fold / total, 3),
                    "call_pct": round(call / total, 3),
                    f"{raise_key}_pct": round(raise_ct / total, 3),
                }
            )
        return rows

    def _table_position_profit(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pos, entry in sorted((self.analysis.get("position_profit") or {}).items()):
            hands = int(entry.get("hands", 0) or 0)
            profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
            rows.append(
                {
                    "pos": pos,
                    "hands": hands,
                    "profit_bb": round(profit_bb, 2),
                    "bb_per_100": round(_rate(profit_bb * 100, hands), 2),
                    "vpip": round(_rate(entry.get("vpip_hands", 0), hands), 3),
                    "pfr": round(_rate(entry.get("pfr_hands", 0), hands), 3),
                }
            )
        return rows

    def _table_position_preflop(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pos, entry in sorted((self.analysis.get("position_preflop") or {}).items()):
            hands = int(entry.get("hands", 0) or 0)
            open_ct = int(entry.get("open", 0) or 0)
            flat_ct = int(entry.get("flat", 0) or 0)
            threebet_ct = int(entry.get("3bet", 0) or 0)
            fourbet_ct = int(entry.get("4bet", 0) or 0)
            fold_ct = int(entry.get("fold", 0) or 0)
            rows.append(
                {
                    "pos": pos,
                    "hands": hands,
                    "vpip": round(_rate(open_ct + flat_ct + threebet_ct + fourbet_ct, hands), 3),
                    "pfr": round(_rate(open_ct + threebet_ct + fourbet_ct, hands), 3),
                    "open_pct": round(_rate(open_ct, hands), 3),
                    "flat_pct": round(_rate(flat_ct, hands), 3),
                    "3bet_pct": round(_rate(threebet_ct, hands), 3),
                    "4bet_pct": round(_rate(fourbet_ct, hands), 3),
                    "fold_pct": round(_rate(fold_ct, hands), 3),
                }
            )
        return rows

    def _table_open_by_pos(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pos, entry in sorted((self.analysis.get("open_by_pos") or {}).items()):
            open_ct = int(entry.get("open", 0) or 0)
            steal_ct = int(entry.get("steal", 0) or 0)
            rows.append(
                {
                    "pos": pos,
                    "open": open_ct,
                    "steal": steal_ct,
                    "steal_rate": round(_rate(steal_ct, open_ct), 3),
                }
            )
        return rows

    def _table_first_in_by_pos(self) -> list[dict[str, Any]]:
        first_in = self.analysis.get("first_in_by_pos") or {}
        open_first = self.analysis.get("open_first_in_by_pos") or {}
        facing_open = self.analysis.get("facing_open_by_pos") or {}
        rows: list[dict[str, Any]] = []
        for pos in sorted(set(first_in.keys()) | set(open_first.keys()) | set(facing_open.keys())):
            fi = int(first_in.get(pos, 0) or 0)
            ofi = int(open_first.get(pos, 0) or 0)
            fo = int(facing_open.get(pos, 0) or 0)
            rows.append(
                {
                    "pos": pos,
                    "first_in": fi,
                    "open_first_in": ofi,
                    "open_rate": round(_rate(ofi, fi), 3),
                    "facing_open": fo,
                }
            )
        return rows

    def _table_open_sizes(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for bucket, count in sorted((self.analysis.get("open_size_buckets") or {}).items()):
            rows.append({"open_size_bb": bucket, "count": int(count or 0)})
        return rows

    def _table_open_size_by_pos(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pos, entry in sorted((self.analysis.get("open_size_by_pos") or {}).items()):
            count = int(entry.get("count", 0) or 0)
            avg = float(entry.get("avg_bb", 0.0) or 0.0)
            rows.append({"pos": pos, "count": count, "avg_open_bb": round(avg, 2)})
        return rows

    def _table_cbet_split(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cbet_split = self.analysis.get("cbet_split") or {}
        for street in ("flop", "turn", "river"):
            hu = (cbet_split.get("hu") or {}).get(street, (0, 0))
            mw = (cbet_split.get("mw") or {}).get(street, (0, 0))
            rows.append(
                {
                    "street": street.upper(),
                    "hu_made": int(hu[0] or 0),
                    "hu_opp": int(hu[1] or 0),
                    "hu_rate": round(_rate(hu[0], hu[1]), 3),
                    "mw_made": int(mw[0] or 0),
                    "mw_opp": int(mw[1] or 0),
                    "mw_rate": round(_rate(mw[0], mw[1]), 3),
                }
            )
        return rows

    def _table_bet_sizes(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        buckets = self.analysis.get("bet_size_buckets") or {}
        for street, table in (buckets or {}).items():
            for bucket, count in sorted((table or {}).items()):
                rows.append({"street": street, "bucket": bucket, "count": int(count or 0)})
        return rows

    def _table_bet_size_avg(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        bet_avg = self.analysis.get("bet_size_avg") or {}
        raise_avg = self.analysis.get("raise_add_avg") or {}
        for street in ("FLOP", "TURN", "RIVER"):
            if street not in bet_avg and street not in raise_avg:
                continue
            rows.append(
                {
                    "street": street,
                    "avg_bet_frac": round(float(bet_avg.get(street, 0.0) or 0.0), 3),
                    "avg_raise_add": round(float(raise_avg.get(street, 0.0) or 0.0), 3),
                }
            )
        return rows

    def _table_rake_forced(self) -> list[dict[str, Any]]:
        a = self.analysis
        return [
            {"metric": "total_rake_bb", "value": round(float(a.get("total_rake_bb", 0.0) or 0.0), 2)},
            {"metric": "rake_bb_per_100", "value": round(float(a.get("rake_bb_per_100", 0.0) or 0.0), 2)},
            {"metric": "rake_frac_avg", "value": round(float(a.get("rake_frac_avg", 0.0) or 0.0), 3)},
            {"metric": "rake_frac_overall", "value": round(float(a.get("rake_frac_overall", 0.0) or 0.0), 3)},
            {"metric": "rake_cap_hits", "value": int(a.get("rake_cap_hits", 0) or 0)},
            {"metric": "forced_posted_bb", "value": round(float(a.get("forced_posted_bb", 0.0) or 0.0), 2)},
            {"metric": "forced_expected_bb", "value": round(float(a.get("forced_expected_bb", 0.0) or 0.0), 2)},
            {"metric": "forced_mismatch_bb", "value": round(float(a.get("forced_mismatch_bb", 0.0) or 0.0), 2)},
            {"metric": "forced_mismatch_count", "value": int(a.get("forced_mismatch_count", 0) or 0)},
            {"metric": "forced_mismatch_max_bb", "value": round(float(a.get("forced_mismatch_max_bb", 0.0) or 0.0), 2)},
            {"metric": "ante_total_bb", "value": round(float(a.get("ante_total_bb", 0.0) or 0.0), 2)},
            {"metric": "model_ante_bb", "value": round(float(a.get("model_ante_bb", 0.0) or 0.0), 2)},
            {"metric": "ante_expected_bb", "value": round(float(a.get("ante_expected_bb", 0.0) or 0.0), 2)},
        ]

    def _table_check_donk(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        check_raise = self.analysis.get("check_raise_counts") or {}
        donk = self.analysis.get("donk_counts") or {}
        for street in ("FLOP", "TURN", "RIVER"):
            rows.append(
                {
                    "street": street,
                    "check_raise": int(check_raise.get(street, 0) or 0),
                    "donk_bet": int(donk.get(street, 0) or 0),
                }
            )
        return rows

    def _table_action_mix(self) -> list[dict[str, Any]]:
        st = self.analysis.get("street_stats") or {}
        fold = sum(int(v.get("fold", 0) or 0) for v in st.values())
        call = sum(int(v.get("call", 0) or 0) for v in st.values())
        bet = sum(int(v.get("bet", 0) or 0) for v in st.values())
        raise_ct = sum(int(v.get("raise", 0) or 0) for v in st.values())
        allin = sum(int(v.get("allin", 0) or 0) for v in st.values())
        total = max(1, fold + call + bet + raise_ct + allin)
        return [
            {"action": "fold", "count": fold, "rate": round(fold / total, 3)},
            {"action": "call", "count": call, "rate": round(call / total, 3)},
            {"action": "bet", "count": bet, "rate": round(bet / total, 3)},
            {"action": "raise", "count": raise_ct, "rate": round(raise_ct / total, 3)},
            {"action": "allin", "count": allin, "rate": round(allin / total, 3)},
            {"action": "agg", "count": bet + raise_ct + allin, "rate": round((bet + raise_ct + allin) / total, 3)},
        ]

    def _table_street_stats(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for street, entry in (self.analysis.get("street_stats") or {}).items():
            dec = int(entry.get("dec", 0) or 0)
            rows.append(
                {
                    "street": street,
                    "decisions": dec,
                    "agg_pct": round(_rate(entry.get("agg", 0), dec), 3),
                    "fold_pct": round(_rate(entry.get("fold", 0), dec), 3),
                    "call_pct": round(_rate(entry.get("call", 0), dec), 3),
                    "bet_pct": round(_rate(entry.get("bet", 0), dec), 3),
                    "raise_pct": round(_rate(entry.get("raise", 0), dec), 3),
                    "allin_pct": round(_rate(entry.get("allin", 0), dec), 3),
                    "fold_to_bet": round(_rate(entry.get("fold_when_facing", 0), entry.get("facing", 0)), 3),
                }
            )
        return rows

    def _table_street_value(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for street, entry in (self.analysis.get("street_value_stats") or {}).items():
            dec = int(entry.get("dec", 0) or 0)
            rows.append(
                {
                    "street": street,
                    "decisions": dec,
                    "avg_players": round(_rate(entry.get("players_sum", 0), dec), 2),
                    "avg_pot_bb": round(_rate(entry.get("pot_bb_sum", 0.0), dec), 2),
                    "avg_stack_bb": round(_rate(entry.get("stack_bb_sum", 0.0), dec), 2),
                    "avg_spr": round(_rate(entry.get("spr_sum", 0.0), entry.get("spr_count", 0)), 2),
                    "avg_facing_bb": round(_rate(entry.get("facing_bb_sum", 0.0), entry.get("facing_count", 0)), 2),
                    "avg_call_bb": round(_rate(entry.get("call_bb_sum", 0.0), entry.get("call_count", 0)), 2),
                    "avg_bet_frac": round(_rate(entry.get("bet_frac_sum", 0.0), entry.get("bet_count", 0)), 2),
                    "avg_raise_add": round(_rate(entry.get("raise_add_frac_sum", 0.0), entry.get("raise_count", 0)), 2),
                }
            )
        return rows

    def _table_profit_by_players(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for stage, table in (self.analysis.get("profit_by_players") or {}).items():
            for players, entry in sorted((table or {}).items(), key=lambda x: int(x[0])):
                hands = int(entry.get("hands", 0) or 0)
                profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
                ref = f"report:ProfitByPlayers/{stage}_{players}p"
                rows.append(
                    {
                        "stage": stage,
                        "players": players,
                        "hands": hands,
                        "profit_bb": round(profit_bb, 2),
                        "bb_per_100": round(_rate(profit_bb * 100, hands), 2),
                        "ref": ref,
                    }
                )
        return rows

    def _table_bucket_profit(self, key: str, label: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        ref_prefix = "SPRBuckets" if key == "spr_buckets" else "PotBuckets"
        for bucket, entry in sorted((self.analysis.get(key) or {}).items()):
            hands = int(entry.get("hands", 0) or 0)
            profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
            rows.append(
                {
                    label: bucket,
                    "hands": hands,
                    "profit_bb": round(profit_bb, 2),
                    "bb_per_100": round(_rate(profit_bb * 100, hands), 2),
                    "ref": f"report:{ref_prefix}/{bucket}",
                }
            )
        return rows

    def _table_bb_flat_postflop(self) -> list[dict[str, Any]]:
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
            spr_bucket = entry.get("spr_bucket")
            oop_flag = "Y" if bool(entry.get("oop_multi_street", False)) else "N"
            rows.append(
                {
                    "spr_bucket": spr_bucket,
                    "oop_multi_street": bool(entry.get("oop_multi_street", False)),
                    "hands": hands,
                    "profit_bb": round(profit_bb, 2),
                    "bb_per_100": round(_rate(profit_bb * 100, hands), 2),
                    "ref": f"report:BBFlatPostflop/{spr_bucket}_oop_{oop_flag}",
                }
            )
        return rows

    def _table_bb_flat_postflop_facing_by_street(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        data = self.analysis.get("bb_flat_postflop_facing_by_street") or []
        if isinstance(data, dict):
            entries = list(data.values())
        elif isinstance(data, list):
            entries = data
        else:
            entries = []
        for entry in sorted(entries, key=lambda e: (str(e.get("street")), str(e.get("facing")))):
            hands = int(entry.get("hands", 0) or 0)
            profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
            street = entry.get("street")
            facing = entry.get("facing")
            ref = f"report:BBFlatPostflopFacing/{street}_{facing}"
            rows.append(
                {
                    "street": street,
                    "facing": facing,
                    "hands": hands,
                    "profit_bb": round(profit_bb, 2),
                    "bb_per_100": round(_rate(profit_bb * 100, hands), 2),
                    "ref": ref,
                }
            )
        return rows

    def _table_bb_sb_facing_edge(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        data = self.analysis.get("bb_sb_facing_edge") or []
        if isinstance(data, dict):
            entries = list(data.values())
        elif isinstance(data, list):
            entries = data
        else:
            entries = []

        def _ppm_to_ratio(val: Any) -> float | None:
            if val is None:
                return None
            try:
                v = float(val)
            except Exception:
                return None
            return round(v / 1_000_000.0, 3)

        for entry in sorted(entries, key=lambda e: (str(e.get("pos")), str(e.get("street")), str(e.get("price_bucket")))):
            hands = int(entry.get("hands", 0) or 0)
            rows.append(
                {
                    "pos": entry.get("pos"),
                    "street": entry.get("street"),
                    "price_bucket": entry.get("price_bucket"),
                    "hands": hands,
                    "edge_ratio": _ppm_to_ratio(entry.get("edge_ratio_ppm")),
                    "call_edge_ratio": _ppm_to_ratio(entry.get("call_edge_ratio_ppm")),
                    "raise_cap": _ppm_to_ratio(entry.get("raise_cap_ppm")),
                    "raise_cap_marginal": _ppm_to_ratio(entry.get("raise_cap_marginal_ppm")),
                    "target_raise": _ppm_to_ratio(entry.get("target_raise_ppm")),
                    "current_raise": _ppm_to_ratio(entry.get("current_raise_ppm")),
                    "ref": entry.get("ref"),
                }
            )
        return rows

    def _table_players_dist(self, label: str, data: dict[str, int]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        total = sum(int(v or 0) for v in data.values()) or 1
        for players, count in sorted(data.items(), key=lambda x: int(x[0])):
            rows.append({"stage": label, "players": int(players), "hands": int(count or 0), "pct": round(count / total, 3)})
        return rows

    def _table_mdf_stats(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for street, entry in (self.analysis.get("mdf_stats") or {}).items():
            facing = int(entry.get("facing", 0) or 0)
            defend = int(entry.get("defend", 0) or 0)
            rows.append(
                {
                    "street": street,
                    "facing": facing,
                    "mdf_avg": round(_rate(entry.get("mdf_sum", 0.0), facing), 3),
                    "mdf_adj": round(_rate(entry.get("mdf_adj_sum", 0.0), facing), 3),
                    "defend_rate": round(_rate(defend, facing), 3),
                    "gap_adj": round(_rate(defend, facing) - _rate(entry.get("mdf_adj_sum", 0.0), facing), 3),
                }
            )
        return rows

    def _table_facing_price(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for bucket, entry in sorted(data.items()):
            facing = int(entry.get("facing", 0) or 0)
            defend = int(entry.get("defend", 0) or 0)
            rows.append(
                {
                    "bucket": bucket,
                    "facing": facing,
                    "mdf_avg": round(_rate(entry.get("mdf_sum", 0.0), facing), 3),
                    "mdf_adj": round(_rate(entry.get("mdf_adj_sum", 0.0), facing), 3),
                    "defend_rate": round(_rate(defend, facing), 3),
                    "gap_adj": round(_rate(defend, facing) - _rate(entry.get("mdf_adj_sum", 0.0), facing), 3),
                }
            )
        return rows

    def _table_facing_outcomes(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for bucket, entry in sorted(data.items()):
            fold = int(entry.get("fold", 0) or 0)
            call = int(entry.get("call", 0) or 0)
            raise_ct = int(entry.get("raise", 0) or 0)
            total = max(1, fold + call + raise_ct + int(entry.get("other", 0) or 0))
            rows.append(
                {
                    "bucket": bucket,
                    "fold": fold,
                    "call": call,
                    "raise": raise_ct,
                    "fold_pct": round(fold / total, 3),
                    "call_pct": round(call / total, 3),
                    "raise_pct": round(raise_ct / total, 3),
                }
            )
        return rows

    def _table_rung_stats(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for rung, entry in sorted((self.analysis.get("rung_stats") or {}).items()):
            dec = int(entry.get("dec", 0) or 0)
            rows.append(
                {
                    "rung": rung,
                    "dec": dec,
                    "fold_pct": round(_rate(entry.get("fold", 0), dec), 3),
                    "call_pct": round(_rate(entry.get("call", 0), dec), 3),
                    "bet_pct": round(_rate(entry.get("bet", 0), dec), 3),
                    "raise_pct": round(_rate(entry.get("raise", 0), dec), 3),
                    "fold_to_bet": round(_rate(entry.get("fold_when_facing", 0), entry.get("facing", 0)), 3),
                }
            )
        return rows

    def _table_board_texture(self, key: str, label: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for bucket, entry in sorted((self.analysis.get(key) or {}).items()):
            hands = int(entry.get("hands", 0) or 0)
            profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
            rows.append(
                {
                    label: bucket,
                    "hands": hands,
                    "profit_bb": round(profit_bb, 2),
                    "bb_per_100": round(_rate(profit_bb * 100, hands), 2),
                }
            )
        return rows

    def build(self) -> dict[str, Any]:
        tables: dict[str, Any] = {
            "action_mix": self._table_action_mix(),
            "preflop_defense": self._table_preflop_defense(),
            "defend_vs_open_by_pos": self._table_pos_defense(self.analysis.get("defend_vs_open_by_pos") or {}, key_name="pos", raise_key="raise"),
            "defend_vs_open_by_opener_pos": self._table_pos_defense(self.analysis.get("defend_vs_open_by_opener_pos") or {}, key_name="opener_pos", raise_key="raise"),
            "bb_vs_open_by_pos": self._table_pos_defense(self.analysis.get("bb_vs_open_by_pos") or {}, key_name="opener_pos", raise_key="3bet"),
            "bb_vs_open_by_size": self._table_pos_defense(self.analysis.get("bb_vs_open_by_size") or {}, key_name="open_size_bb", raise_key="3bet"),
            "position_profit": self._table_position_profit(),
            "position_preflop": self._table_position_preflop(),
            "open_by_pos": self._table_open_by_pos(),
            "first_in_by_pos": self._table_first_in_by_pos(),
            "open_size_buckets": self._table_open_sizes(),
            "open_size_by_pos": self._table_open_size_by_pos(),
            "cbet_split": self._table_cbet_split(),
            "bet_size_avg": self._table_bet_size_avg(),
            "bet_size_buckets": self._table_bet_sizes(),
            "check_raise_donk": self._table_check_donk(),
            "street_stats": self._table_street_stats(),
            "street_value": self._table_street_value(),
            "profit_by_players": self._table_profit_by_players(),
            "pot_bucket_profit": self._table_bucket_profit("pot_bucket_profit", "pot_bucket_bb"),
            "spr_buckets": self._table_bucket_profit("spr_buckets", "spr_bucket"),
            "bb_flat_postflop": self._table_bb_flat_postflop(),
            "bb_flat_postflop_facing_by_street": self._table_bb_flat_postflop_facing_by_street(),
            "bb_sb_facing_edge": self._table_bb_sb_facing_edge(),
            "flop_suit_texture": self._table_board_texture("flop_suit_texture", "suit_bucket"),
            "flop_rank_texture": self._table_board_texture("flop_rank_texture", "rank_bucket"),
            "flop_players_dist": self._table_players_dist("FLOP", self.analysis.get("flop_players_dist") or {}),
            "turn_players_dist": self._table_players_dist("TURN", self.analysis.get("turn_players_dist") or {}),
            "river_players_dist": self._table_players_dist("RIVER", self.analysis.get("river_players_dist") or {}),
            "mdf_stats": self._table_mdf_stats(),
            "facing_price_stats": self._table_facing_price(self.analysis.get("facing_price_stats") or {}),
            "facing_outcomes": self._table_facing_outcomes(self.analysis.get("facing_bet_outcomes") or {}),
            "rake_forced": self._table_rake_forced(),
            "rung_stats": self._table_rung_stats(),
        }
        index: dict[str, Any] = {}
        for name, rows in tables.items():
            for row in rows or []:
                ref = row.get("ref")
                if isinstance(ref, str):
                    index[ref] = {"table": name, "row": row}
        return {
            "schema_id": "scrimmage_views_v1",
            "source_report_ref": self.report.get("event_stream_ref"),
            "environment": self._env(),
            "summary": self._summary(),
            "tables": tables,
            "index": index,
        }

    def render_text(self) -> str:
        views = self.build()
        env = views.get("environment", {})
        summary = views.get("summary", {})
        tables = views.get("tables", {})
        lines: list[str] = []
        lines.append("== Environment ==")
        lines.append(
            _fmt_table(
                ["metric", "value"],
                [
                    {"metric": "players", "value": env.get("players")},
                    {"metric": "sb", "value": env.get("sb")},
                    {"metric": "bb", "value": env.get("bb")},
                    {"metric": "ante", "value": env.get("ante")},
                    {"metric": "stack_bb", "value": env.get("stack_bb")},
                    {"metric": "rake_rate", "value": f"{env.get('rake_rate', 0.0):.3f}"},
                    {"metric": "rake_cap", "value": env.get("rake_cap")},
                    {"metric": "no_flop_no_drop", "value": env.get("no_flop_no_drop")},
                    {"metric": "ruleset_id", "value": env.get("ruleset_id")},
                    {"metric": "scenario_id", "value": env.get("scenario_id")},
                    {"metric": "action_bins_id", "value": env.get("action_bins_id")},
                    {"metric": "bet_bins", "value": env.get("bet_bins")},
                    {"metric": "raise_bins", "value": env.get("raise_bins")},
                ],
            )
        )
        lines.append("== Summary ==")
        lines.append(
            _fmt_table(
                ["metric", "value"],
                [
                    {"metric": "hands", "value": summary.get("hands")},
                    {"metric": "wins", "value": summary.get("wins")},
                    {"metric": "ties", "value": summary.get("ties")},
                    {"metric": "losses", "value": summary.get("losses")},
                    {"metric": "winrate", "value": f"{summary.get('winrate', 0.0):.3f}"},
                    {"metric": "profit_bb_net", "value": f"{summary.get('profit_bb_net', 0.0):.2f}"},
                    {"metric": "profit_bb_gross", "value": f"{summary.get('profit_bb_gross', 0.0):.2f}"},
                    {"metric": "bb_per_100_net", "value": f"{summary.get('bb_per_100_net', 0.0):.2f}"},
                    {"metric": "bb_per_100_gross", "value": f"{summary.get('bb_per_100_gross', 0.0):.2f}"},
                    {"metric": "rake_bb_per_100", "value": f"{summary.get('rake_bb_per_100', 0.0):.2f}"},
                    {"metric": "avg_pot_bb", "value": f"{summary.get('avg_pot_bb', 0.0):.2f}"},
                    {"metric": "vpip", "value": f"{summary.get('vpip', 0.0):.3f}"},
                    {"metric": "pfr", "value": f"{summary.get('pfr', 0.0):.3f}"},
                ],
            )
        )
        for name, table in tables.items():
            rows = table or []
            if not rows:
                continue
            lines.append(f"== {name} ==")
            headers = list(rows[0].keys())
            lines.append(_fmt_table(headers, rows))
        return "\n".join(lines)
