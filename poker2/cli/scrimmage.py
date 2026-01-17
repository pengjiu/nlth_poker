from __future__ import annotations

# Lightweight scrimmage runner: system bot vs rule bots on 7-max table.

import argparse
import json
from pathlib import Path
from typing import Any

from poker2.environment.pokerkit_nlhe import run_multi_hand_eventstream_objects
from poker2.contractkit import ROUNDING_MODE_VALUES
from poker2.protocol.action_adapter import default_internal_action_adapter
from poker2.protocol.action_bins import default_internal_action_bins, action_bins_id, validate_action_bins_spec
from poker2.protocol.abstraction import abstraction_hash
from poker2.protocol.options_hash import compute_options_hash
from poker2.protocol.paths import default_paths_config, resolve_paths, validate_paths_config
from poker2.protocol.policy import load_policy_spec, policy_id
from poker2.protocol.profile import load_profile_spec, profile_id
from poker2.protocol.provenance import build_provenance_envelope_v1, provenance_id
from poker2.protocol.run_id import run_id_v1
from poker2.protocol.ruleset import ruleset_id, ruleset_rake_id, validate_ruleset
from poker2.protocol.schema_contract import schema_hash
from poker2.protocol.scenario import scenario_id as compute_scenario_id
from poker2.protocol.scenario_package import load_scenario_package, scenario_closure_from_package, validate_scenario_package
from poker2.protocol.mw_ladder import default_internal_mw_ladder
from poker2.protocol.treepath_mapping import default_internal_treepath_mapping_spec, position_key, treepath_mapping_spec_id
from poker2.protocol.placeholders import placeholder_id
from poker2.runtime.artifact_store import write_artifact_json
from poker2.runtime.policy_registry import build_policy_registry, resolve_policy_ref
from poker2.runtime.profile_registry import build_profile_registry, resolve_profile_ref
from poker2.runtime.rule_policy import make_rule_policy, make_system_policy
from poker2.runtime.opponent_registry import build_opponent_registry, resolve_opponent_suite_ref
from poker2.runtime.system_policy import build_system_policy
from poker2.runtime.hand_eval import board_texture, parse_card_token
from poker2.tools.scrimmage_views import ScrimmageReportViews
from poker2.tools.report_analyzer import ScrimmageReportAnalyzer
from poker2.tools.iteration_protocol import build_iteration_protocol, validate_iteration_protocol
from poker2.cli.hrc_import_ruleset import import_ruleset_from_hrc_settings
from poker2.engines.postflop_solver import compute_postflop_solver_build_id, postflop_solver_src_root_from_paths_trace


def _parse_stacks(raw: str | None) -> dict[int, int]:
    if raw is None:
        return {i: 10000 for i in range(1, 8)}
    obj = json.loads(raw)
    if not isinstance(obj, dict) or not obj:
        raise ValueError("starting_stacks_by_seat must be non-empty JSON object")
    out: dict[int, int] = {}
    for k, v in obj.items():
        if not isinstance(k, str) or not k.isdigit():
            raise ValueError("seat ids must be decimal strings")
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("stack values must be int")
        out[int(k)] = v
    return out


def _load_ruleset_by_id(ruleset_id_hex: str) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2] / "specs" / "rulesets"
    for p in root.glob("*.json"):
        obj = json.loads(p.read_text())
        validate_ruleset(obj, strict_mode=True)
        if ruleset_id(obj, strict_mode=True) == ruleset_id_hex:
            return obj
    raise FileNotFoundError(f"ruleset_id {ruleset_id_hex} not found under specs/rulesets")


def _load_action_bins_by_id(target_id: str) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2] / "specs" / "action_bins"
    for p in root.glob("*.json"):
        obj = json.loads(p.read_text())
        validate_action_bins_spec(obj, strict_mode=True)
        if action_bins_id(obj, strict_mode=True) == target_id:
            return obj
    raise FileNotFoundError(f"action_bins_id {target_id} not found under specs/action_bins")


def _bet_bins_from_spec(spec: dict[str, Any]) -> list[float]:
    ppm = spec.get("bet_bins_ppm") or []
    return [round(v / 1_000_000.0, 3) for v in ppm]


def _raise_bins_from_spec(spec: dict[str, Any]) -> list[float]:
    ppm = spec.get("raise_bins_ppm") or []
    return [round(v / 1_000_000.0, 3) for v in ppm]


def _format_action_mix(counts: dict[str, int]) -> str:
    total = sum(counts.values()) or 1
    parts = []
    for k in ("FOLD", "CALL", "BET", "RAISE"):
        v = counts.get(k, 0)
        parts.append(f"{k.lower()} {v/total:.2f}")
    allin = counts.get("ALLIN", 0)
    parts.append(f"allin {allin/total:.2f}")
    agg = (counts.get("BET", 0) + counts.get("RAISE", 0) + allin) / total
    parts.append(f"agg {agg:.2f}")
    return " ".join(parts)


def _fmt_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(str(c)))
    def fmt_row(r: list[str]) -> str:
        return " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(r))
    lines = [fmt_row(headers), "-+-".join("-" * w for w in widths)]
    lines.extend(fmt_row(r) for r in rows)
    return "\n".join(lines)

def _decision_key(ev: dict[str, Any]) -> tuple[int, str] | None:
    did = ev.get("decision_id")
    state_hash = ev.get("state_hash")
    if isinstance(did, int) and isinstance(state_hash, str):
        return (did, state_hash)
    return None


def _render_iteration_protocol_text(protocol: dict[str, Any] | None) -> list[str]:
    if not isinstance(protocol, dict):
        return []
    lines: list[str] = []
    baseline = protocol.get("baseline") or {}
    evidence = protocol.get("evidence") or []
    result = protocol.get("result") or {}
    lines.append("== Iteration Protocol (template) ==")
    lines.append("Baseline:")
    for key in (
        "policy_id",
        "scenario_id",
        "opponent_suite_id",
        "actionspace_id",
        "run_id",
        "options_hash",
        "event_stream_digest",
        "report_ref",
    ):
        lines.append(f"{key}: {baseline.get(key)}")
    lines.append("Evidence:")
    if evidence:
        for entry in evidence[:3]:
            lines.append(
                f"{entry.get('bucket_key')} | {entry.get('metric')} | n={entry.get('n')} | seed={entry.get('seed')} | ref={entry.get('evidence_ref')}"
            )
    else:
        lines.append("<fill: 3 evidence lines>")
    lines.append("Change:")
    lines.append("change_1: <fill>")
    lines.append("Gate:")
    lines.append("gate_id: <fill>")
    lines.append("Regression:")
    lines.append("matrix: <fill>")
    lines.append("Result:")
    lines.append(f"fix: {result.get('fix')}")
    lines.append(f"side_effect: {result.get('side_effect')}")
    return lines



def _render_text_report(
    *,
    ruleset: dict[str, Any],
    action_bins: dict[str, Any],
    seats: list[int],
    hands: int,
    seat_results: dict[int, int],
    total_rake_chips: int,
    model_wins: int,
    model_ties: int,
    dp_info: dict[int, tuple[str, int]] | None,
    actions: list[dict[str, Any]],
    analysis: dict[str, Any],
    seat_meta: dict[int, dict[str, Any]] | None = None,
    iteration_protocol: dict[str, Any] | None = None,
) -> str:
    sb = ruleset["blinds"]["sb_chips"]
    bb = ruleset["blinds"]["bb_chips"]
    ante_cfg = (ruleset.get("ante") or {})
    ante = ante_cfg.get("amount_chips") or ante_cfg.get("ante_chips") or 0
    rake = ruleset.get("rake", {})
    rake_rate = (rake.get("pct_ppm", 0) or 0) / 1_000_000.0
    rake_cap = rake.get("cap_chips")
    no_flop_no_drop = bool(rake.get("no_flop_no_drop", False))

    model_seat = seats[0] if seats else 1
    profit_chips = seat_results.get(model_seat, 0)
    profit_bb = analysis.get("profit_bb", profit_chips / bb if bb else 0.0)
    profit_bb_gross = analysis.get("profit_bb_gross", profit_bb)
    total_rake_bb = analysis.get("total_rake_bb", total_rake_chips / bb if bb else 0.0)
    bb_per_100 = analysis.get("bb_per_100", profit_bb * 100 / max(1, hands))
    bb_per_100_gross = profit_bb_gross * 100 / max(1, hands)
    ties = model_ties
    model_wins = model_wins
    rule_wins = max(0, hands - model_wins - ties)
    winrate = analysis.get("winrate", model_wins / max(1, hands))

    # Use analysis-derived vpip/pfr (per-hand) to avoid double counting forced bets.
    action_counts: dict[str, int] = {}
    for a in actions:
        if a.get("seat") != model_seat:
            continue
        kind = a.get("kind")
        if isinstance(kind, str):
            action_counts[kind] = action_counts.get(kind, 0) + 1

    action_mix_str = _format_action_mix(action_counts)
    vpip_pct = analysis.get("vpip_pct", 0.0)
    pfr_pct = analysis.get("pfr_pct", 0.0)

    bet_bins = _bet_bins_from_spec(action_bins)
    raise_bins = _raise_bins_from_spec(action_bins)

    lines = []
    lines.append("== Environment ==")
    stack_bb = float(analysis.get("starting_stack_bb", 0.0) or 0.0)
    lines.append(
        f"players {len(seats)} sb {sb:.1f} bb {bb:.1f} ante {ante:.1f} stack_bb {stack_bb:.2f} "
        f"rake_rate {rake_rate:.3f} rake_cap {float(rake_cap) if rake_cap is not None else 0.0} no_flop_no_drop {no_flop_no_drop}"
    )
    lines.append(
        _fmt_table(
            ["setting", "value"],
            [
                ["players", len(seats)],
                ["sb", f"{sb:.1f}"],
                ["bb", f"{bb:.1f}"],
                ["ante", f"{ante:.1f}"],
                ["stack_bb", f"{stack_bb:.2f}"],
                ["rake_rate", f"{rake_rate:.3f}"],
                ["rake_cap", f"{float(rake_cap) if rake_cap is not None else 0.0:.1f}"],
                ["no_flop_no_drop", str(no_flop_no_drop)],
            ],
        )
    )
    lines.append(f"bet_bins {bet_bins}")
    lines.append(f"raise_bins {raise_bins}")

    lines.append("== Results ==")
    lines.append(
        _fmt_table(
            ["metric", "value"],
            [
                ["hands", hands],
                ["winrate", f"{winrate:.3f}"],
                ["model_wins / ties / rule_wins", f"{model_wins} / {ties} / {rule_wins}"],
                ["profit_bb_net", f"{profit_bb:.2f}"],
                ["profit_bb_gross", f"{profit_bb_gross:.2f}"],
                ["bb_per_100_net", f"{bb_per_100:.2f}"],
                ["bb_per_100_gross", f"{bb_per_100_gross:.2f}"],
                ["avg_pot_bb", f"{analysis.get('avg_pot_bb', 0):.2f}"],
            ],
        )
    )

    lines.append("== Rake / Forced / Ante ==")
    lines.append(
        _fmt_table(
            ["metric", "value"],
            [
                ["total_rake_bb", f"{total_rake_bb:.2f}"],
                ["model_rake_bb_est", f"{analysis.get('model_rake_bb', 0.0):.2f}"],
                ["rake_bb_per_100", f"{analysis.get('rake_bb_per_100', 0.0):.2f}"],
                ["rake_frac_avg / overall", f"{analysis.get('rake_frac_avg', 0.0):.3f} / {analysis.get('rake_frac_overall', 0.0):.3f}"],
                ["rake_cap_hits", f"{analysis.get('rake_cap_hits', 0)}"],
                ["raise_cap_hits", f"{analysis.get('raise_cap_hits', 0)}"],
                ["forced_posted_bb / expected_bb", f"{analysis.get('forced_posted_bb', 0):.2f} / {analysis.get('forced_expected_bb', 0):.2f}"],
                [
                    "forced_mismatch_bb (count/max)",
                    f"{analysis.get('forced_mismatch_bb', 0):.2f} ({analysis.get('forced_mismatch_count', 0)}/{analysis.get('forced_mismatch_max_bb', 0):.2f})",
                ],
                ["ante_total_bb", f"{analysis.get('ante_total_bb', 0):.2f}"],
                ["model_ante_bb / expected", f"{analysis.get('model_ante_bb', 0):.2f} / {analysis.get('ante_expected_bb', 0):.2f}"],
            ],
        )
    )

    lines.append("== Behavior ==")
    lines.append(f"action_mix {action_mix_str}")
    lines.append(
        _fmt_table(
            ["metric", "value"],
            [
                ["vpip_pct", f"{vpip_pct:.3f}"],
                ["pfr_pct", f"{pfr_pct:.3f}"],
                ["open/3bet/4bet", f"{analysis.get('open',0)}/{analysis.get('threebet',0)}/{analysis.get('fourbet',0)}"],
                ["open_size_avg_bb", f"{analysis.get('open_size_avg',0):.2f}"],
                [
                    "cbet flop/turn/river",
                    f"{analysis['cbet']['flop'][0]}/{max(1, analysis['cbet']['flop'][1])} | "
                    f"{analysis['cbet']['turn'][0]}/{max(1, analysis['cbet']['turn'][1])} | "
                    f"{analysis['cbet']['river'][0]}/{max(1, analysis['cbet']['river'][1])}",
                ],
                ["avg_win_bb / avg_loss_bb", f"{analysis.get('avg_win_bb',0):.2f} / {analysis.get('avg_loss_bb',0):.2f}"],
                ["wtsd / wwsf / wsd", f"{analysis.get('wtsd',0):.3f} / {analysis.get('wwsf',0):.3f} / {analysis.get('wsd',0):.3f}"],
                [
                    "fold_to_bet flop/turn/river",
                    f"{analysis.get('fold_to_flop_bet',0):.3f} / {analysis.get('fold_to_turn_bet',0):.3f} / {analysis.get('fold_to_river_bet',0):.3f}",
                ],
                ["raise_cap_hits", f"{analysis.get('raise_cap_hits',0)}"],
            ],
        )
    )

    if analysis.get("cbet_split"):
        lines.append("== Cbet Split ==")
        rows = []
        for st in ("flop", "turn", "river"):
            hu = analysis["cbet_split"]["hu"].get(st, (0, 0))
            mw = analysis["cbet_split"]["mw"].get(st, (0, 0))
            rows.append(
                [
                    st.upper(),
                    f"{hu[0]}/{max(1, hu[1])}",
                    f"{mw[0]}/{max(1, mw[1])}",
                ]
            )
        lines.append(_fmt_table(["street", "HU made/opp", "MW made/opp"], rows))

    lines.append("== Table Flow ==")
    open_ct = analysis.get("open", 0)
    open_late = analysis.get("open_late", 0)
    threebet_ct = analysis.get("threebet", 0)
    fourbet_ct = analysis.get("fourbet", 0)
    lines.append(
        _fmt_table(
            ["metric", "value"],
            [
                ["open_steal_success", f"{analysis.get('open_steal_success',0)}/{open_ct}"],
                ["open_steal_success_late", f"{analysis.get('open_steal_success_late',0)}/{open_late}"],
                ["3bet_success", f"{analysis.get('threebet_success',0)}/{threebet_ct}"],
                ["4bet_success", f"{analysis.get('fourbet_success',0)}/{fourbet_ct}"],
                ["check_raise (F/T/R)", f"{analysis.get('check_raise_counts',{}).get('FLOP',0)}/"
                 f"{analysis.get('check_raise_counts',{}).get('TURN',0)}/"
                 f"{analysis.get('check_raise_counts',{}).get('RIVER',0)}"],
                ["donk_bet (F/T/R)", f"{analysis.get('donk_counts',{}).get('FLOP',0)}/"
                 f"{analysis.get('donk_counts',{}).get('TURN',0)}/"
                 f"{analysis.get('donk_counts',{}).get('RIVER',0)}"],
            ],
        )
    )

    if analysis.get("flop_players_dist"):
        lines.append("Flop players distribution:")
        rows = []
        total = sum(analysis.get("flop_players_dist", {}).values()) or 1
        for k, v in sorted((analysis.get("flop_players_dist") or {}).items(), key=lambda x: int(x[0])):
            rows.append([k, v, f"{v/total:.3f}"])
        lines.append(_fmt_table(["players", "hands", "pct"], rows))
    if analysis.get("turn_players_dist"):
        lines.append("Turn players distribution:")
        rows = []
        total = sum(analysis.get("turn_players_dist", {}).values()) or 1
        for k, v in sorted((analysis.get("turn_players_dist") or {}).items(), key=lambda x: int(x[0])):
            rows.append([k, v, f"{v/total:.3f}"])
        lines.append(_fmt_table(["players", "hands", "pct"], rows))
    if analysis.get("river_players_dist"):
        lines.append("River players distribution:")
        rows = []
        total = sum(analysis.get("river_players_dist", {}).values()) or 1
        for k, v in sorted((analysis.get("river_players_dist") or {}).items(), key=lambda x: int(x[0])):
            rows.append([k, v, f"{v/total:.3f}"])
        lines.append(_fmt_table(["players", "hands", "pct"], rows))

    lines.append("== Profit Breakdown ==")
    lines.append(
        _fmt_table(
            ["metric", "value"],
            [
                ["showdown / non_showdown bb", f"{analysis.get('showdown_profit_bb',0):.2f} / {analysis.get('non_showdown_profit_bb',0):.2f}"],
                ["vpip / non_vpip bb", f"{analysis.get('vpip_profit_bb',0):.2f} / {analysis.get('non_vpip_profit_bb',0):.2f}"],
                ["saw_flop / no_flop bb", f"{analysis.get('saw_flop_profit_bb',0):.2f} / {analysis.get('no_flop_profit_bb',0):.2f}"],
                ["saw_turn / saw_river bb", f"{analysis.get('saw_turn_profit_bb',0):.2f} / {analysis.get('saw_river_profit_bb',0):.2f}"],
            ],
        )
    )

    lines.append("== Participation ==")
    vpip_hands = int(analysis.get("vpip_hands", 0) or 0)
    saw_flop_hands = int(analysis.get("saw_flop_hands", 0) or 0)
    saw_turn_hands = int(analysis.get("saw_turn_hands", 0) or 0)
    saw_river_hands = int(analysis.get("saw_river_hands", 0) or 0)
    showdown_hands = int(analysis.get("showdown_hands", 0) or 0)
    showdown_after_flop = int(analysis.get("showdown_after_flop", 0) or 0)
    showdown_after_turn = int(analysis.get("showdown_after_turn", 0) or 0)
    showdown_after_river = int(analysis.get("showdown_after_river", 0) or 0)
    lines.append(
        _fmt_table(
            ["metric", "hands", "profit_bb"],
            [
                ["vpip", vpip_hands, f"{analysis.get('vpip_profit_bb',0):.2f}"],
                ["non_vpip", hands - vpip_hands, f"{analysis.get('non_vpip_profit_bb',0):.2f}"],
                ["saw_flop", saw_flop_hands, f"{analysis.get('saw_flop_profit_bb',0):.2f}"],
                ["no_flop", hands - saw_flop_hands, f"{analysis.get('no_flop_profit_bb',0):.2f}"],
                ["saw_turn", saw_turn_hands, f"{analysis.get('saw_turn_profit_bb',0):.2f}"],
                ["saw_river", saw_river_hands, f"{analysis.get('saw_river_profit_bb',0):.2f}"],
                ["showdown", showdown_hands, f"{analysis.get('showdown_profit_bb',0):.2f}"],
            ],
        )
    )
    lines.append("== Street Reach ==")
    lines.append(
        _fmt_table(
            ["metric", "rate", "hands"],
            [
                ["flop_reach", f"{saw_flop_hands / max(1, hands):.3f}", saw_flop_hands],
                ["turn_reach", f"{saw_turn_hands / max(1, hands):.3f}", saw_turn_hands],
                ["river_reach", f"{saw_river_hands / max(1, hands):.3f}", saw_river_hands],
                ["showdown_rate", f"{showdown_hands / max(1, hands):.3f}", showdown_hands],
                ["wtsd_from_flop", f"{showdown_after_flop / max(1, saw_flop_hands):.3f}", showdown_after_flop],
                ["wtsd_from_turn", f"{showdown_after_turn / max(1, saw_turn_hands):.3f}", showdown_after_turn],
                ["wtsd_from_river", f"{showdown_after_river / max(1, saw_river_hands):.3f}", showdown_after_river],
            ],
        )
    )
    lines.append("== Loss-Only ==")
    lines.append(
        _fmt_table(
            ["metric", "hands", "loss_bb"],
            [
                ["loss_no_vpip", analysis.get("loss_no_vpip", 0), f"{analysis.get('loss_no_vpip_bb',0):.2f}"],
                ["loss_with_vpip", analysis.get("loss_with_vpip", 0), f"{analysis.get('loss_with_vpip_bb',0):.2f}"],
                ["loss_saw_flop", analysis.get("loss_saw_flop", 0), f"{analysis.get('loss_saw_flop_bb',0):.2f}"],
                ["loss_saw_turn", analysis.get("loss_saw_turn", 0), f"{analysis.get('loss_saw_turn_bb',0):.2f}"],
                ["loss_saw_river", analysis.get("loss_saw_river", 0), f"{analysis.get('loss_saw_river_bb',0):.2f}"],
            ],
        )
    )

    def _def_row(label: str, entry: dict[str, int]) -> list[str]:
        fold = int(entry.get("fold", 0))
        call = int(entry.get("call", 0))
        raise_ct = int(entry.get("raise", 0))
        total = max(1, fold + call + raise_ct)
        return [
            label,
            fold,
            call,
            raise_ct,
            f"{fold/total:.3f}",
            f"{call/total:.3f}",
            f"{raise_ct/total:.3f}",
        ]

    lines.append("== Preflop Defense ==")
    lines.append(
        _fmt_table(
            ["vs", "fold", "call", "raise", "fold%", "call%", "raise%"],
            [
                _def_row("open", analysis.get("defend_vs_open") or {}),
                _def_row("3bet", analysis.get("defend_vs_3bet") or {}),
                _def_row("4bet+", analysis.get("defend_vs_4bet") or {}),
            ],
        )
    )
    if analysis.get("open_size_buckets"):
        lines.append("== Open Size (bb) ==")
        rows_open = []
        for bucket, count in sorted((analysis.get("open_size_buckets") or {}).items()):
            rows_open.append([bucket, count])
        lines.append(_fmt_table(["open_size_bb", "count"], rows_open))
    if analysis.get("open_size_by_pos"):
        lines.append("== Open Size by Position ==")
        rows_pos_open = []
        for pos, entry in sorted((analysis.get("open_size_by_pos") or {}).items()):
            rows_pos_open.append([pos, entry.get("count", 0), f"{entry.get('avg_bb', 0.0):.2f}"])
        lines.append(_fmt_table(["pos", "count", "avg_open_bb"], rows_pos_open))
    if analysis.get("defend_vs_open_by_pos"):
        pos_order = {"BU": 0, "SB": 1, "BB": 2, "OTHERS": 3}
        rows = []
        for pos, entry in sorted(analysis.get("defend_vs_open_by_pos", {}).items(), key=lambda x: pos_order.get(x[0], 9)):
            fold = int(entry.get("fold", 0))
            call = int(entry.get("call", 0))
            raise_ct = int(entry.get("raise", 0))
            total = max(1, fold + call + raise_ct)
            rows.append([pos, fold, call, raise_ct, f"{fold/total:.3f}", f"{call/total:.3f}", f"{raise_ct/total:.3f}"])
        lines.append("== Defend vs Open by Position ==")
        lines.append(_fmt_table(["pos", "fold", "call", "raise", "fold%", "call%", "raise%"], rows))
    if analysis.get("bb_vs_open_by_pos"):
        pos_order = {"BU": 0, "SB": 1, "BB": 2, "OTHERS": 3}
        rows = []
        for pos, entry in sorted(analysis.get("bb_vs_open_by_pos", {}).items(), key=lambda x: pos_order.get(x[0], 9)):
            fold = int(entry.get("fold", 0))
            call = int(entry.get("call", 0))
            threebet = int(entry.get("3bet", 0))
            total = max(1, fold + call + threebet)
            rows.append([pos, fold, call, threebet, f"{fold/total:.3f}", f"{call/total:.3f}", f"{threebet/total:.3f}"])
        lines.append("== BB vs Open by Position ==")
        lines.append(_fmt_table(["opener_pos", "fold", "call", "3bet", "fold%", "call%", "3bet%"], rows))
    if analysis.get("defend_vs_open_by_opener_pos"):
        pos_order = {"BU": 0, "SB": 1, "BB": 2, "OTHERS": 3}
        rows = []
        for pos, entry in sorted(analysis.get("defend_vs_open_by_opener_pos", {}).items(), key=lambda x: pos_order.get(x[0], 9)):
            fold = int(entry.get("fold", 0))
            call = int(entry.get("call", 0))
            raise_ct = int(entry.get("raise", 0))
            total = max(1, fold + call + raise_ct)
            rows.append([pos, fold, call, raise_ct, f"{fold/total:.3f}", f"{call/total:.3f}", f"{raise_ct/total:.3f}"])
        lines.append("== Defend vs Open by Opener Position ==")
        lines.append(_fmt_table(["opener_pos", "fold", "call", "raise", "fold%", "call%", "raise%"], rows))
    if analysis.get("bb_vs_open_by_size"):
        size_order = {"2.0-2.5": 0, "2.5-3.0": 1, "3.0-3.5": 2, "3.5-4.5": 3, "4.5+": 4}
        rows = []
        for size, entry in sorted(analysis.get("bb_vs_open_by_size", {}).items(), key=lambda x: size_order.get(x[0], 9)):
            fold = int(entry.get("fold", 0))
            call = int(entry.get("call", 0))
            threebet = int(entry.get("3bet", 0))
            total = max(1, fold + call + threebet)
            rows.append([size, fold, call, threebet, f"{fold/total:.3f}", f"{call/total:.3f}", f"{threebet/total:.3f}"])
        lines.append("== BB vs Open by Size ==")
        lines.append(_fmt_table(["open_size_bb", "fold", "call", "3bet", "fold%", "call%", "3bet%"], rows))

    if analysis.get("position_preflop"):
        lines.append("== Preflop Mix by Position ==")
        rows_pp = []
        for pos, data in sorted((analysis.get("position_preflop") or {}).items()):
            hands_p = data.get("hands", 0)
            rows_pp.append(
                [
                    pos,
                    hands_p,
                    data.get("open", 0),
                    data.get("flat", 0),
                    data.get("3bet", 0),
                    data.get("4bet", 0),
                    data.get("fold", 0),
                    data.get("check", 0),
                ]
            )
        lines.append(_fmt_table(["pos", "hands", "open", "flat", "3bet", "4bet", "fold", "check"], rows_pp))
        lines.append("== Preflop Rates by Position ==")
        rows_rates = []
        for pos, data in sorted((analysis.get("position_preflop") or {}).items()):
            hands_p = data.get("hands", 0) or 0
            open_ct = data.get("open", 0)
            flat_ct = data.get("flat", 0)
            threebet_ct = data.get("3bet", 0)
            fourbet_ct = data.get("4bet", 0)
            fold_ct = data.get("fold", 0)
            denom = max(1, hands_p)
            vpip_rate = (open_ct + flat_ct + threebet_ct + fourbet_ct) / denom
            pfr_rate = (open_ct + threebet_ct + fourbet_ct) / denom
            rows_rates.append(
                [
                    pos,
                    f"{vpip_rate:.3f}",
                    f"{pfr_rate:.3f}",
                    f"{open_ct/denom:.3f}",
                    f"{flat_ct/denom:.3f}",
                    f"{threebet_ct/denom:.3f}",
                    f"{fourbet_ct/denom:.3f}",
                    f"{fold_ct/denom:.3f}",
                ]
            )
        lines.append(_fmt_table(["pos", "vpip", "pfr", "open%", "flat%", "3bet%", "4bet%", "fold%"], rows_rates))
    if analysis.get("open_by_pos"):
        pos_order = {"BU": 0, "SB": 1, "BB": 2, "OTHERS": 3}
        rows_op = []
        for pos, data in sorted((analysis.get("open_by_pos") or {}).items(), key=lambda x: pos_order.get(x[0], 9)):
            open_ct = data.get("open", 0)
            steal_ct = data.get("steal", 0)
            rate = steal_ct / max(1, open_ct)
            rows_op.append([pos, open_ct, steal_ct, f"{rate:.3f}"])
        lines.append("== Steal Success by Position ==")
        lines.append(_fmt_table(["pos", "open", "steal", "rate"], rows_op))
    if analysis.get("first_in_by_pos"):
        pos_order = {"BU": 0, "SB": 1, "BB": 2, "OTHERS": 3}
        rows_fi = []
        first_in = analysis.get("first_in_by_pos") or {}
        open_first = analysis.get("open_first_in_by_pos") or {}
        facing_open = analysis.get("facing_open_by_pos") or {}
        for pos in sorted(set(first_in.keys()) | set(open_first.keys()) | set(facing_open.keys()), key=lambda x: pos_order.get(x, 9)):
            fi = int(first_in.get(pos, 0) or 0)
            ofi = int(open_first.get(pos, 0) or 0)
            fo = int(facing_open.get(pos, 0) or 0)
            rows_fi.append([pos, fi, ofi, f"{ofi / max(1, fi):.3f}", fo])
        lines.append("== First-In Opportunities ==")
        lines.append(_fmt_table(["pos", "first_in", "open_first_in", "open_rate", "facing_open"], rows_fi))
    if analysis.get("preflop_responses"):
        pf_resp = analysis.get("preflop_responses") or {}
        lines.append("== Preflop Responses ==")
        lines.append(
            _fmt_table(
                ["metric", "count"],
                [
                    ["open -> fold to 3bet", pf_resp.get("open_fold_3bet", 0)],
                    ["open -> call 3bet", pf_resp.get("open_call_3bet", 0)],
                    ["3bet -> fold to 4bet", pf_resp.get("3bet_fold_4bet", 0)],
                    ["3bet -> call 4bet", pf_resp.get("3bet_call_4bet", 0)],
                    ["flat vs open", pf_resp.get("flat_vs_open", 0)],
                ],
            )
        )
    if analysis.get("preflop_role_profit"):
        lines.append("== Preflop Role EV ==")
        role_order = {"open": 0, "3bet": 1, "4bet": 2, "flat": 3, "check": 4, "fold": 5, "other": 6}
        rows_role = []
        for role, data in sorted((analysis.get("preflop_role_profit") or {}).items(), key=lambda x: role_order.get(x[0], 9)):
            hands_r = int(data.get("hands", 0) or 0)
            prof_r = float(data.get("profit_bb", 0.0) or 0.0)
            rows_role.append([role, hands_r, f"{prof_r:.2f}", f"{prof_r * 100 / max(1, hands_r):.2f}"])
        lines.append(_fmt_table(["role", "hands", "profit_bb", "bb/100"], rows_role))
    if analysis.get("postflop_role_profit"):
        lines.append("== Postflop Role EV (saw flop) ==")
        role_order = {"aggressor": 0, "defender": 1, "checker": 2, "other": 3}
        rows_role = []
        for role, data in sorted((analysis.get("postflop_role_profit") or {}).items(), key=lambda x: role_order.get(x[0], 9)):
            hands_r = int(data.get("hands", 0) or 0)
            prof_r = float(data.get("profit_bb", 0.0) or 0.0)
            rows_role.append([role, hands_r, f"{prof_r:.2f}", f"{prof_r * 100 / max(1, hands_r):.2f}"])
        lines.append(_fmt_table(["role", "hands", "profit_bb", "bb/100"], rows_role))

    lines.append("== Buckets ==")
    lines.append("Pot buckets (bb):")
    pot_profit = analysis.get("pot_bucket_profit") or {}
    if pot_profit:
        rows_pb = []
        for key in ("0-5", "5-10", "10-20", "20+"):
            entry = pot_profit.get(key, {"hands": 0, "profit_bb": 0.0})
            hands_b = int(entry.get("hands", 0) or 0)
            prof_b = float(entry.get("profit_bb", 0.0) or 0.0)
            rows_pb.append([key, hands_b, f"{prof_b:.2f}", f"{prof_b * 100 / max(1, hands_b):.2f}"])
        lines.append(_fmt_table(["bucket_bb", "hands", "profit_bb", "bb/100"], rows_pb))
    else:
        lines.append(_fmt_table(["bucket_bb", "hands"], [[k, v] for k, v in (analysis.get("pot_buckets") or {}).items()]))
    lines.append("Facing bet buckets (to_call / bb):")
    lines.append(_fmt_table(["bucket", "count"], [[k, v] for k, v in sorted((analysis.get("facing_bet_buckets") or {}).items())]))
    lines.append("Facing bet buckets by street:")
    for st, table in sorted((analysis.get("facing_bet_by_street") or {}).items()):
        rows_fb = [[k.split("_", 1)[1] if "_" in k else k, v] for k, v in sorted(table.items())]
        lines.append(f"{st}:")
        lines.append(_fmt_table(["bucket", "count"], rows_fb))
    if analysis.get("facing_bet_outcomes"):
        lines.append("Facing bet outcomes (all streets):")
        rows_out = []
        for bucket, out in sorted((analysis.get("facing_bet_outcomes") or {}).items()):
            total = sum(out.values()) or 1
            rows_out.append([bucket, f"{out.get('fold',0)/total:.2f}", f"{out.get('call',0)/total:.2f}", f"{out.get('raise',0)/total:.2f}"])
        lines.append(_fmt_table(["bucket", "fold%", "call%", "raise%"], rows_out))
    if analysis.get("facing_bet_outcomes_by_street"):
        lines.append("Facing bet outcomes by street:")
        for st, table in sorted((analysis.get("facing_bet_outcomes_by_street") or {}).items()):
            rows_out = []
            for bucket, out in sorted((table or {}).items()):
                total = sum(out.values()) or 1
                rows_out.append([bucket, f"{out.get('fold',0)/total:.2f}", f"{out.get('call',0)/total:.2f}", f"{out.get('raise',0)/total:.2f}"])
            lines.append(f"{st}:")
            lines.append(_fmt_table(["bucket", "fold%", "call%", "raise%"], rows_out))
    if analysis.get("spr_buckets"):
        lines.append("SPR buckets (postflop):")
        rows_spr = []
        for b, data in sorted((analysis.get("spr_buckets") or {}).items()):
            hands_b = data.get("hands", 0)
            prof_b = data.get("profit_bb", 0.0)
            rows_spr.append([b, hands_b, f"{prof_b:.2f}", f"{prof_b * 100 / max(1, hands_b):.2f}"])
        lines.append(_fmt_table(["spr_bucket", "hands", "profit_bb", "bb/100"], rows_spr))
    if (analysis.get("flop_suit_texture") or analysis.get("flop_rank_texture")):
        lines.append("== Board Texture ==")
        suit_order = {"monotone": 0, "two-tone": 1, "rainbow": 2}
        rank_order = {"paired": 0, "connected": 1, "semi-connected": 2, "disconnected": 3}
        if analysis.get("flop_suit_texture"):
            rows = []
            for key, data in sorted((analysis.get("flop_suit_texture") or {}).items(), key=lambda x: suit_order.get(x[0], 9)):
                hands_b = int(data.get("hands", 0) or 0)
                prof_b = float(data.get("profit_bb", 0.0) or 0.0)
                rows.append([key, hands_b, f"{prof_b:.2f}", f"{prof_b * 100 / max(1, hands_b):.2f}"])
            lines.append("Flop suit texture:")
            lines.append(_fmt_table(["bucket", "hands", "profit_bb", "bb/100"], rows))
        if analysis.get("flop_rank_texture"):
            rows = []
            for key, data in sorted((analysis.get("flop_rank_texture") or {}).items(), key=lambda x: rank_order.get(x[0], 9)):
                hands_b = int(data.get("hands", 0) or 0)
                prof_b = float(data.get("profit_bb", 0.0) or 0.0)
                rows.append([key, hands_b, f"{prof_b:.2f}", f"{prof_b * 100 / max(1, hands_b):.2f}"])
            lines.append("Flop rank texture:")
            lines.append(_fmt_table(["bucket", "hands", "profit_bb", "bb/100"], rows))
    if analysis.get("bb_flat_postflop"):
        lines.append("== BB Flat Postflop EV ==")
        rows_bb = []
        spr_order = {"<1": 0, "1-2": 1, "2-4": 2, "4-7": 3, "7+": 4}
        for entry in sorted(
            analysis.get("bb_flat_postflop", []),
            key=lambda e: (spr_order.get(e.get("spr_bucket"), 9), 1 if e.get("oop_multi_street") else 0),
        ):
            hands_b = int(entry.get("hands", 0) or 0)
            prof_b = float(entry.get("profit_bb", 0.0) or 0.0)
            rows_bb.append(
                [
                    entry.get("spr_bucket"),
                    "Y" if entry.get("oop_multi_street") else "N",
                    hands_b,
                    f"{prof_b:.2f}",
                    f"{prof_b * 100 / max(1, hands_b):.2f}",
                ]
            )
        lines.append(_fmt_table(["spr_bucket", "oop_multi_street", "hands", "profit_bb", "bb/100"], rows_bb))
    if analysis.get("bb_flat_postflop_by_street"):
        lines.append("== BB Flat Postflop EV by Street ==")
        order = {"FLOP": 0, "TURN": 1, "RIVER": 2}
        rows_st = []
        for entry in sorted(analysis.get("bb_flat_postflop_by_street", []), key=lambda e: order.get(e.get("street"), 9)):
            hands_b = int(entry.get("hands", 0) or 0)
            prof_b = float(entry.get("profit_bb", 0.0) or 0.0)
            rows_st.append([entry.get("street"), hands_b, f"{prof_b:.2f}", f"{prof_b * 100 / max(1, hands_b):.2f}"])
        lines.append(_fmt_table(["street", "hands", "profit_bb", "bb/100"], rows_st))
    if analysis.get("bb_flat_postflop_spr_by_street"):
        lines.append("== BB Flat Postflop EV by Street+SPR ==")
        order = {"FLOP": 0, "TURN": 1, "RIVER": 2}
        spr_order = {"<1": 0, "1-2": 1, "2-4": 2, "4-7": 3, "7+": 4}
        rows_spr = []
        for entry in sorted(
            analysis.get("bb_flat_postflop_spr_by_street", []),
            key=lambda e: (order.get(e.get("street"), 9), spr_order.get(e.get("spr_bucket"), 9)),
        ):
            hands_b = int(entry.get("hands", 0) or 0)
            prof_b = float(entry.get("profit_bb", 0.0) or 0.0)
            rows_spr.append(
                [entry.get("street"), entry.get("spr_bucket"), hands_b, f"{prof_b:.2f}", f"{prof_b * 100 / max(1, hands_b):.2f}"]
            )
        lines.append(_fmt_table(["street", "spr_bucket", "hands", "profit_bb", "bb/100"], rows_spr))
    if analysis.get("bb_flat_postflop_pot_by_street"):
        lines.append("== BB Flat Postflop EV by Street+Pot ==")
        order = {"FLOP": 0, "TURN": 1, "RIVER": 2}
        pot_order = {"0-5": 0, "5-10": 1, "10-20": 2, "20+": 3}
        rows_pot = []
        for entry in sorted(
            analysis.get("bb_flat_postflop_pot_by_street", []),
            key=lambda e: (order.get(e.get("street"), 9), pot_order.get(e.get("pot_bucket"), 9)),
        ):
            hands_b = int(entry.get("hands", 0) or 0)
            prof_b = float(entry.get("profit_bb", 0.0) or 0.0)
            rows_pot.append(
                [entry.get("street"), entry.get("pot_bucket"), hands_b, f"{prof_b:.2f}", f"{prof_b * 100 / max(1, hands_b):.2f}"]
            )
        lines.append(_fmt_table(["street", "pot_bucket", "hands", "profit_bb", "bb/100"], rows_pot))
    if analysis.get("bb_flat_postflop_facing_by_street"):
        lines.append("== BB Flat Postflop EV by Street+Facing ==")
        order = {"FLOP": 0, "TURN": 1, "RIVER": 2}
        rows_face = []
        for entry in sorted(
            analysis.get("bb_flat_postflop_facing_by_street", []),
            key=lambda e: (order.get(e.get("street"), 9), str(e.get("facing"))),
        ):
            hands_b = int(entry.get("hands", 0) or 0)
            prof_b = float(entry.get("profit_bb", 0.0) or 0.0)
            rows_face.append(
                [entry.get("street"), entry.get("facing"), hands_b, f"{prof_b:.2f}", f"{prof_b * 100 / max(1, hands_b):.2f}"]
            )
        lines.append(_fmt_table(["street", "facing", "hands", "profit_bb", "bb/100"], rows_face))
    if analysis.get("bb_sb_facing_edge"):
        lines.append("== BB/SB Facing Bet Edge ==")
        rows_edge = []
        order = {"FLOP": 0, "TURN": 1, "RIVER": 2}

        def _ppm_ratio(val: Any) -> str:
            if val is None:
                return "-"
            try:
                return f"{float(val) / 1_000_000.0:.3f}"
            except Exception:
                return "-"

        for entry in sorted(
            analysis.get("bb_sb_facing_edge", []),
            key=lambda e: (str(e.get("pos")), order.get(e.get("street"), 9), str(e.get("price_bucket"))),
        ):
            rows_edge.append(
                [
                    entry.get("pos"),
                    entry.get("street"),
                    entry.get("price_bucket"),
                    int(entry.get("hands", 0) or 0),
                    _ppm_ratio(entry.get("edge_ratio_ppm")),
                    _ppm_ratio(entry.get("call_edge_ratio_ppm")),
                    _ppm_ratio(entry.get("raise_cap_ppm")),
                    _ppm_ratio(entry.get("raise_cap_marginal_ppm")),
                    _ppm_ratio(entry.get("target_raise_ppm")),
                    _ppm_ratio(entry.get("current_raise_ppm")),
                ]
            )
        lines.append(
            _fmt_table(
                [
                    "pos",
                    "street",
                    "price_bucket",
                    "hands",
                    "edge_ratio",
                    "call_edge_ratio",
                    "raise_cap",
                    "raise_cap_marginal",
                    "target_raise",
                    "current_raise",
                ],
                rows_edge,
            )
        )
    if analysis.get("position_profit"):
        lines.append("== Position EV ==")
        rows_pos = []
        for pos, data in sorted((analysis.get("position_profit") or {}).items()):
            hands_p = data.get("hands", 0)
            prof_p = data.get("profit_bb", 0.0)
            vpip_h = data.get("vpip_hands", 0)
            pfr_h = data.get("pfr_hands", 0)
            rows_pos.append(
                [
                    pos,
                    hands_p,
                    f"{prof_p:.2f}",
                    f"{prof_p * 100 / max(1, hands_p):.2f}",
                    f"{vpip_h / max(1, hands_p):.3f}",
                    f"{pfr_h / max(1, hands_p):.3f}",
                ]
            )
        lines.append(_fmt_table(["pos", "hands", "profit_bb", "bb/100", "vpip%", "pfr%"], rows_pos))

    if analysis.get("bet_size_buckets"):
        lines.append("== Bet Sizing (pot frac) ==")
        bet_avg = analysis.get("bet_size_avg") or {}
        raise_avg = analysis.get("raise_add_avg") or {}
        rows_avg = []
        for st in ("FLOP", "TURN", "RIVER"):
            if st not in bet_avg:
                continue
            rows_avg.append([st, f"{bet_avg.get(st,0.0):.2f}", f"{raise_avg.get(st,0.0):.2f}"])
        if rows_avg:
            lines.append(_fmt_table(["street", "avg_bet_frac", "avg_raise_add_frac"], rows_avg))
        for st, table in sorted((analysis.get("bet_size_buckets") or {}).items()):
            rows_b = [[bucket, count] for bucket, count in sorted(table.items())]
            lines.append(f"{st}:")
            lines.append(_fmt_table(["bucket", "count"], rows_b))

    if analysis.get("rung_stats"):
        lines.append("== MW Rung Summary ==")
        rows_rung = []
        for rung, st in sorted((analysis.get("rung_stats") or {}).items()):
            dec = max(1, st.get("dec", 0))
            rows_rung.append(
                [
                    rung,
                    st.get("dec", 0),
                    f"{st.get('fold',0)/dec:.2f}",
                    f"{st.get('call',0)/dec:.2f}",
                    f"{st.get('bet',0)/dec:.2f}",
                    f"{st.get('raise',0)/dec:.2f}",
                    f"{(st.get('fold_when_facing',0)/max(1, st.get('facing',0))):.2f}",
                ]
            )
        lines.append(_fmt_table(["rung", "dec", "fold%", "call%", "bet%", "raise%", "fold_to_bet"], rows_rung))

    lines.append("== Street Summary ==")
    rows_street = []
    for street, st in (analysis.get("street_stats") or {}).items():
        dec = max(1, st["dec"])
        rows_street.append(
            [
                street,
                st["dec"],
                f"{st['agg']/dec:.2f}",
                f"{st['fold']/dec:.2f}",
                f"{st['call']/dec:.2f}",
                f"{st['bet']/dec:.2f}",
                f"{st['raise']/dec:.2f}",
                f"{st['allin']/dec:.2f}",
                f"{st['fold_when_facing']}/{max(1, st['facing'])}",
            ]
        )
    lines.append(_fmt_table(["street", "dec", "agg%", "fold%", "call%", "bet%", "raise%", "allin%", "fold_to_bet"], rows_street))
    if analysis.get("mdf_stats"):
        lines.append("== MDF vs Defense ==")
        rows_mdf = []
        for street, st in (analysis.get("mdf_stats") or {}).items():
            facing = int(st.get("facing", 0) or 0)
            defend = int(st.get("defend", 0) or 0)
            mdf_avg = (st.get("mdf_sum", 0.0) or 0.0) / max(1, facing)
            mdf_adj_avg = (st.get("mdf_adj_sum", 0.0) or 0.0) / max(1, facing)
            defend_rate = defend / max(1, facing)
            rows_mdf.append(
                [
                    street,
                    facing,
                    f"{mdf_avg:.3f}",
                    f"{mdf_adj_avg:.3f}",
                    f"{defend_rate:.3f}",
                    f"{defend_rate - mdf_adj_avg:+.3f}",
                ]
            )
        lines.append(_fmt_table(["street", "facing", "mdf_avg", "mdf_adj", "defend_rate", "gap_adj"], rows_mdf))
    if analysis.get("facing_price_stats"):
        lines.append("== Defense vs Price ==")
        order = {"0-0.20": 0, "0.20-0.33": 1, "0.33-0.50": 2, ">0.50": 3}
        rows_price = []
        for bucket, st in sorted((analysis.get("facing_price_stats") or {}).items(), key=lambda x: order.get(x[0], 9)):
            facing = int(st.get("facing", 0) or 0)
            defend = int(st.get("defend", 0) or 0)
            mdf_avg = (st.get("mdf_sum", 0.0) or 0.0) / max(1, facing)
            mdf_adj_avg = (st.get("mdf_adj_sum", 0.0) or 0.0) / max(1, facing)
            defend_rate = defend / max(1, facing)
            rows_price.append(
                [bucket, facing, f"{mdf_avg:.3f}", f"{mdf_adj_avg:.3f}", f"{defend_rate:.3f}", f"{defend_rate - mdf_adj_avg:+.3f}"]
            )
        lines.append(_fmt_table(["price_bucket", "facing", "mdf_avg", "mdf_adj", "defend_rate", "gap_adj"], rows_price))
    if analysis.get("facing_price_stats_by_street"):
        lines.append("Defense vs Price by street:")
        order = {"0-0.20": 0, "0.20-0.33": 1, "0.33-0.50": 2, ">0.50": 3}
        for st_name, table in sorted((analysis.get("facing_price_stats_by_street") or {}).items()):
            rows_price = []
            for bucket, st in sorted((table or {}).items(), key=lambda x: order.get(x[0], 9)):
                facing = int(st.get("facing", 0) or 0)
                defend = int(st.get("defend", 0) or 0)
                mdf_avg = (st.get("mdf_sum", 0.0) or 0.0) / max(1, facing)
                mdf_adj_avg = (st.get("mdf_adj_sum", 0.0) or 0.0) / max(1, facing)
                defend_rate = defend / max(1, facing)
                rows_price.append(
                    [bucket, facing, f"{mdf_avg:.3f}", f"{mdf_adj_avg:.3f}", f"{defend_rate:.3f}", f"{defend_rate - mdf_adj_avg:+.3f}"]
                )
            lines.append(f"{st_name}:")
            lines.append(_fmt_table(["price_bucket", "facing", "mdf_avg", "mdf_adj", "defend_rate", "gap_adj"], rows_price))
    if analysis.get("facing_bet_outcomes"):
        lines.append("== Facing Bet Outcomes ==")
        rows_out = []
        for bucket, entry in sorted((analysis.get("facing_bet_outcomes") or {}).items()):
            fold = int(entry.get("fold", 0) or 0)
            call = int(entry.get("call", 0) or 0)
            raise_ct = int(entry.get("raise", 0) or 0)
            total = max(1, fold + call + raise_ct + int(entry.get("other", 0) or 0))
            rows_out.append([bucket, fold, call, raise_ct, f"{fold/total:.3f}", f"{call/total:.3f}", f"{raise_ct/total:.3f}"])
        lines.append(_fmt_table(["price_bucket", "fold", "call", "raise", "fold%", "call%", "raise%"], rows_out))
    if analysis.get("facing_bet_outcomes_by_street"):
        lines.append("Facing Bet Outcomes by street:")
        for st_name, table in sorted((analysis.get("facing_bet_outcomes_by_street") or {}).items()):
            rows_out = []
            for bucket, entry in sorted((table or {}).items()):
                fold = int(entry.get("fold", 0) or 0)
                call = int(entry.get("call", 0) or 0)
                raise_ct = int(entry.get("raise", 0) or 0)
                total = max(1, fold + call + raise_ct + int(entry.get("other", 0) or 0))
                rows_out.append([bucket, fold, call, raise_ct, f"{fold/total:.3f}", f"{call/total:.3f}", f"{raise_ct/total:.3f}"])
            lines.append(f"{st_name}:")
            lines.append(_fmt_table(["price_bucket", "fold", "call", "raise", "fold%", "call%", "raise%"], rows_out))
    lines.append("== Aggression Factor ==")
    rows_af = []
    for street, st in (analysis.get("street_stats") or {}).items():
        calls = int(st.get("call", 0) or 0)
        agg = int(st.get("bet", 0) or 0) + int(st.get("raise", 0) or 0)
        af = agg / max(1, calls)
        rows_af.append([street, f"{agg}/{calls}", f"{af:.2f}"])
    lines.append(_fmt_table(["street", "agg/call", "af"], rows_af))
    if analysis.get("street_value_stats"):
        lines.append("== Street Averages ==")
        rows_avg = []
        for street, st in (analysis.get("street_value_stats") or {}).items():
            dec = max(1, int(st.get("dec", 0) or 0))
            players_avg = (st.get("players_sum", 0) or 0) / dec
            pot_avg = (st.get("pot_bb_sum", 0.0) or 0.0) / dec
            stack_avg = (st.get("stack_bb_sum", 0.0) or 0.0) / dec
            spr_avg = (st.get("spr_sum", 0.0) or 0.0) / max(1, int(st.get("spr_count", 0) or 0))
            facing_avg = (st.get("facing_bb_sum", 0.0) or 0.0) / max(1, int(st.get("facing_count", 0) or 0))
            call_avg = (st.get("call_bb_sum", 0.0) or 0.0) / max(1, int(st.get("call_count", 0) or 0))
            bet_frac_avg = (st.get("bet_frac_sum", 0.0) or 0.0) / max(1, int(st.get("bet_count", 0) or 0))
            raise_add_avg = (st.get("raise_add_frac_sum", 0.0) or 0.0) / max(1, int(st.get("raise_count", 0) or 0))
            rows_avg.append(
                [
                    street,
                    dec,
                    f"{players_avg:.2f}",
                    f"{pot_avg:.2f}",
                    f"{stack_avg:.2f}",
                    f"{spr_avg:.2f}",
                    f"{facing_avg:.2f}",
                    f"{call_avg:.2f}",
                    f"{bet_frac_avg:.2f}",
                    f"{raise_add_avg:.2f}",
                ]
            )
        lines.append(
            _fmt_table(
                [
                    "street",
                    "dec",
                    "avg_players",
                    "avg_pot_bb",
                    "avg_stack_bb",
                    "avg_spr",
                    "avg_facing_bb",
                    "avg_call_bb",
                    "avg_bet_frac",
                    "avg_raise_add",
                ],
                rows_avg,
            )
        )

    lines.append("== Profit By Players ==")
    rows_pb = []
    for stage, table in (analysis.get("profit_by_players") or {}).items():
        for players, data in sorted(table.items()):
            hands_p = data.get("hands", 0)
            prof = data.get("profit_bb", 0.0)
            bb100 = prof * 100 / max(1, hands_p)
            rows_pb.append([stage, players, hands_p, f"{prof:.2f}", f"{bb100:.2f}"])
    lines.append(_fmt_table(["stage", "players", "hands", "profit_bb", "bb/100"], rows_pb))

    lines.append("== Analysis Table ==")
    open_ct = analysis.get("open", 0)
    open_steal_rate = analysis.get("open_steal_success", 0) / max(1, open_ct)
    open_late = analysis.get("open_late", 0)
    open_steal_rate_late = analysis.get("open_steal_success_late", 0) / max(1, open_late)
    threebet_ct = analysis.get("threebet", 0)
    threebet_succ_rate = analysis.get("threebet_success", 0) / max(1, threebet_ct)
    def_trace_total = analysis.get("defense_trace_total", 0)
    solver_ev_hits = analysis.get("solver_ev_trace_hits", 0)
    raise_cap_marginal_hits = analysis.get("raise_cap_marginal_hits", 0)
    raise_cap_marginal_total = analysis.get("raise_cap_marginal_total", 0)
    lines.append(
        _fmt_table(
            ["metric", "value"],
            [
                ["bb/100_net", f"{bb_per_100:.2f}"],
                ["vpip", f"{vpip_pct:.3f}"],
                ["pfr", f"{pfr_pct:.3f}"],
                ["wtsd", f"{analysis.get('wtsd',0):.3f}"],
                ["wwsf", f"{analysis.get('wwsf',0):.3f}"],
                ["wsd", f"{analysis.get('wsd',0):.3f}"],
                ["cbet_flop/turn/river", f"{analysis['cbet']['flop'][0]}/{max(1, analysis['cbet']['flop'][1])} | {analysis['cbet']['turn'][0]}/{max(1, analysis['cbet']['turn'][1])} | {analysis['cbet']['river'][0]}/{max(1, analysis['cbet']['river'][1])}"],
                ["fold_to_bet f/t/r", f"{analysis.get('fold_to_flop_bet',0):.3f}/{analysis.get('fold_to_turn_bet',0):.3f}/{analysis.get('fold_to_river_bet',0):.3f}"],
                ["avg_pot_bb", f"{analysis.get('avg_pot_bb',0):.2f}"],
                ["open_steal_rate", f"{open_steal_rate:.3f}"],
                ["open_steal_rate_late", f"{open_steal_rate_late:.3f}"],
                ["3bet_success_rate", f"{threebet_succ_rate:.3f}"],
                ["mw_decisions", f"{analysis.get('mw_decisions',0)}"],
                ["raise_cap_hits", f"{analysis.get('raise_cap_hits',0)}"],
                ["solver_ev_coverage", f"{solver_ev_hits}/{def_trace_total}"],
                ["raise_cap_marginal_hits", f"{raise_cap_marginal_hits}/{raise_cap_marginal_total}"],
            ],
        )
    )

    if seat_meta:
        lines.append("== Opponents ==")
        opp_rows = []
        for seat in sorted(seat_meta):
            meta = seat_meta[seat]
            opp_rows.append(
                [
                    seat,
                    meta.get("role"),
                    meta.get("style"),
                    f"{meta.get('aggression', '')}",
                    f"{(seat_results.get(seat,0)/bb):.2f}",
                ]
            )
        lines.append(_fmt_table(["seat", "role", "style", "agg", "profit_bb"], opp_rows))

    lines.extend(_render_iteration_protocol_text(iteration_protocol))

    return "\n".join(lines)


def _analyze_events(
    *,
    objs: list[dict[str, Any]],
    model_seat: int,
    bb: int,
    ruleset: dict[str, Any],
    seats_count: int,
) -> dict[str, Any]:
    blinds = ruleset.get("blinds") or {}
    sb = int(blinds.get("sb_chips", 0) or 0)
    bb_chips = int(bb or blinds.get("bb_chips", 0) or 0)
    ante_cfg = (ruleset.get("ante") or {})
    ante_amt = int(ante_cfg.get("amount_chips") or ante_cfg.get("ante_chips") or 0)
    rake_cfg = (ruleset.get("rake") or {}) if isinstance(ruleset, dict) else {}
    rake_cap = rake_cfg.get("cap_chips")

    decision_snap: dict[tuple[int, str], dict[str, Any]] = {}
    decision_obs: dict[tuple[int, str], dict[str, Any]] = {}
    hands = 0
    hand_profit: list[int] = []
    total_rake = 0
    total_rake_base = 0
    rake_frac_samples: list[float] = []
    rake_cap_hits_count = 0
    avg_pot_samples: list[float] = []
    win_hands = loss_hands = tie_hands = 0
    pot_buckets: dict[str, int] = {"0-5": 0, "5-10": 0, "10-20": 0, "20+": 0}
    pot_bucket_profit: dict[str, dict[str, float | int]] = {
        "0-5": {"hands": 0, "profit_bb": 0.0},
        "5-10": {"hands": 0, "profit_bb": 0.0},
        "10-20": {"hands": 0, "profit_bb": 0.0},
        "20+": {"hands": 0, "profit_bb": 0.0},
    }

    street_stats: dict[str, dict[str, float | int]] = {
        street: {"dec": 0, "agg": 0, "fold": 0, "call": 0, "bet": 0, "raise": 0, "allin": 0, "facing": 0, "fold_when_facing": 0}
        for street in ("PREFLOP", "FLOP", "TURN", "RIVER")
    }
    mdf_stats: dict[str, dict[str, float | int]] = {
        street: {"facing": 0, "defend": 0, "mdf_sum": 0.0, "mdf_adj_sum": 0.0}
        for street in ("PREFLOP", "FLOP", "TURN", "RIVER")
    }
    street_value_stats: dict[str, dict[str, float | int]] = {
        street: {
            "dec": 0,
            "players_sum": 0,
            "pot_bb_sum": 0.0,
            "stack_bb_sum": 0.0,
            "spr_sum": 0.0,
            "spr_count": 0,
            "facing_bb_sum": 0.0,
            "facing_count": 0,
            "call_bb_sum": 0.0,
            "call_count": 0,
            "bet_frac_sum": 0.0,
            "bet_count": 0,
            "raise_add_frac_sum": 0.0,
            "raise_count": 0,
        }
        for street in ("PREFLOP", "FLOP", "TURN", "RIVER")
    }

    preflop_vpip_hands = 0
    preflop_pfr_hands = 0
    open_count = threebet_count = fourbet_count = 0
    open_count_late = 0
    defend_vs_open = {"fold": 0, "call": 0, "raise": 0}
    defend_vs_3bet = {"fold": 0, "call": 0, "raise": 0}
    defend_vs_4bet = {"fold": 0, "call": 0, "raise": 0}
    vpip_profit_chips = 0
    non_vpip_profit_chips = 0
    loss_no_vpip = 0
    loss_with_vpip = 0
    loss_no_vpip_chips = 0
    loss_with_vpip_chips = 0
    saw_flop_profit = 0
    no_flop_profit = 0
    saw_turn_profit = 0
    saw_river_profit = 0
    loss_saw_flop = 0
    loss_saw_turn = 0
    loss_saw_river = 0
    loss_saw_flop_chips = 0
    loss_saw_turn_chips = 0
    loss_saw_river_chips = 0

    cbet_flop_attempt = cbet_flop_success = 0
    cbet_turn_attempt = cbet_turn_success = 0
    cbet_river_attempt = cbet_river_success = 0
    cbet_flop_hu_attempt = cbet_flop_hu_success = 0
    cbet_flop_mw_attempt = cbet_flop_mw_success = 0
    cbet_turn_hu_attempt = cbet_turn_hu_success = 0
    cbet_turn_mw_attempt = cbet_turn_mw_success = 0
    cbet_river_hu_attempt = cbet_river_hu_success = 0
    cbet_river_mw_attempt = cbet_river_mw_success = 0

    facing_bet_buckets: dict[str, int] = {}
    facing_bet_by_street: dict[str, dict[str, int]] = {s: {} for s in ("PREFLOP", "FLOP", "TURN", "RIVER")}
    facing_bet_outcomes: dict[str, dict[str, int]] = {}
    facing_bet_outcomes_by_street: dict[str, dict[str, dict[str, int]]] = {s: {} for s in ("PREFLOP", "FLOP", "TURN", "RIVER")}
    facing_price_stats: dict[str, dict[str, float | int]] = {}
    facing_price_stats_by_street: dict[str, dict[str, dict[str, float | int]]] = {s: {} for s in ("PREFLOP", "FLOP", "TURN", "RIVER")}
    profit_by_players = {"FLOP": {}, "TURN": {}, "RIVER": {}}
    spr_buckets: dict[str, dict[str, float | int]] = {}
    position_profit: dict[str, dict[str, float | int]] = {}
    raise_cap_hits = 0
    defense_trace_total = 0
    solver_ev_trace_hits = 0
    solver_ev_trace_by_street: dict[str, int] = {s: 0 for s in ("PREFLOP", "FLOP", "TURN", "RIVER")}
    raise_cap_marginal_total = 0
    raise_cap_marginal_hits = 0
    raise_cap_marginal_by_street: dict[str, dict[str, int]] = {s: {"total": 0, "hits": 0} for s in ("PREFLOP", "FLOP", "TURN", "RIVER")}
    rung_stats: dict[str, dict[str, int]] = {}

    flop_players_dist: dict[str, int] = {}
    turn_players_dist: dict[str, int] = {}
    river_players_dist: dict[str, int] = {}

    open_steal_success = 0
    open_steal_success_late = 0
    threebet_success = 0
    fourbet_success = 0
    check_raise_counts: dict[str, int] = {"FLOP": 0, "TURN": 0, "RIVER": 0}
    donk_counts: dict[str, int] = {"FLOP": 0, "TURN": 0, "RIVER": 0}

    position_preflop: dict[str, dict[str, int]] = {}
    open_by_pos: dict[str, dict[str, int]] = {}
    open_size_buckets: dict[str, int] = {}
    open_size_by_pos: dict[str, dict[str, float | int]] = {}
    open_size_sum = 0.0
    open_size_count = 0
    first_in_by_pos: dict[str, int] = {}
    open_first_in_by_pos: dict[str, int] = {}
    facing_open_by_pos: dict[str, int] = {}
    defend_vs_open_by_pos: dict[str, dict[str, int]] = {}
    defend_vs_open_by_opener_pos: dict[str, dict[str, int]] = {}
    bb_vs_open_by_pos: dict[str, dict[str, int]] = {}
    bb_vs_open_by_size: dict[str, dict[str, int]] = {}
    bb_flat_postflop: dict[str, dict[str, float | int | str | bool]] = {}
    bb_flat_postflop_by_street: dict[str, dict[str, float | int | str]] = {}
    bb_flat_postflop_spr_by_street: dict[str, dict[str, float | int | str]] = {}
    bb_flat_postflop_pot_by_street: dict[str, dict[str, float | int | str]] = {}
    bb_flat_postflop_facing_by_street: dict[str, dict[str, float | int | str]] = {}
    bb_sb_facing_edge: dict[str, dict[str, int]] = {}
    preflop_responses: dict[str, int] = {
        "open_fold_3bet": 0,
        "open_call_3bet": 0,
        "3bet_fold_4bet": 0,
        "3bet_call_4bet": 0,
        "flat_vs_open": 0,
    }
    preflop_role_profit: dict[str, dict[str, float | int]] = {}
    postflop_role_profit: dict[str, dict[str, float | int]] = {}
    bet_size_buckets: dict[str, dict[str, int]] = {s: {} for s in ("FLOP", "TURN", "RIVER")}
    bet_size_sum: dict[str, float] = {s: 0.0 for s in ("FLOP", "TURN", "RIVER")}
    bet_size_count: dict[str, int] = {s: 0 for s in ("FLOP", "TURN", "RIVER")}
    raise_add_sum: dict[str, float] = {s: 0.0 for s in ("FLOP", "TURN", "RIVER")}
    raise_add_count: dict[str, int] = {s: 0 for s in ("FLOP", "TURN", "RIVER")}
    flop_suit_texture: dict[str, dict[str, float | int]] = {}
    flop_rank_texture: dict[str, dict[str, float | int]] = {}

    action_records: list[dict[str, Any]] = []

    showdown_hands = showdown_wins = 0
    showdown_after_flop = 0
    showdown_after_turn = 0
    showdown_after_river = 0
    wwsf_hands = wwsf_wins = 0
    saw_flop_hands = saw_turn_hands = saw_river_hands = 0
    showdown_profit_chips = 0
    non_showdown_profit_chips = 0

    sb_count = bb_count = 0
    model_forced_total = 0
    model_forced_expected_total = 0
    forced_mismatch_count = 0
    forced_mismatch_max = 0
    starting_stack_bb = None

    current_hand = None

    def bucket_ratio(street: str, ratio: float) -> None:
        if ratio <= 0.5:
            bucket = f"{street}_0-0.5"
        elif ratio <= 1.0:
            bucket = f"{street}_0.5-1.0"
        elif ratio <= 2.0:
            bucket = f"{street}_1-2"
        else:
            bucket = f"{street}_>2"
        facing_bet_buckets[bucket] = facing_bet_buckets.get(bucket, 0) + 1
        fb = facing_bet_by_street.setdefault(street, {})
        fb[bucket] = fb.get(bucket, 0) + 1

    def bucket_outcome(street: str, ratio: float, kind: str | None) -> None:
        if kind is None:
            return
        if ratio <= 0.5:
            bucket = f"{street}_0-0.5"
        elif ratio <= 1.0:
            bucket = f"{street}_0.5-1.0"
        elif ratio <= 2.0:
            bucket = f"{street}_1-2"
        else:
            bucket = f"{street}_>2"
        label = "fold" if kind == "FOLD" else "call" if kind == "CALL" else "raise" if kind in ("BET", "RAISE") else "other"
        out = facing_bet_outcomes.setdefault(bucket, {"fold": 0, "call": 0, "raise": 0, "other": 0})
        out[label] = out.get(label, 0) + 1
        street_out = facing_bet_outcomes_by_street.setdefault(street, {})
        row = street_out.setdefault(bucket, {"fold": 0, "call": 0, "raise": 0, "other": 0})
        row[label] = row.get(label, 0) + 1

    def _pos_key(pos: str | None) -> str:
        if pos in ("BU", "SB", "BB", "OTHERS"):
            return pos
        return "OTHERS"

    def _inc_open_by_pos(pos: str | None, key: str) -> None:
        pos_key = _pos_key(pos)
        entry = open_by_pos.setdefault(pos_key, {"open": 0, "steal": 0})
        entry[key] = entry.get(key, 0) + 1

    def _inc_defend_open_by_pos(pos: str | None, key: str) -> None:
        pos_key = _pos_key(pos)
        entry = defend_vs_open_by_pos.setdefault(pos_key, {"fold": 0, "call": 0, "raise": 0})
        entry[key] = entry.get(key, 0) + 1

    def add_profit_bucket(stage: str, players: int | None, delta_bb: float) -> None:
        if stage not in profit_by_players or players is None:
            return
        stage_map = profit_by_players[stage]
        entry = stage_map.get(players, {"hands": 0, "profit_bb": 0.0})
        entry["hands"] += 1
        entry["profit_bb"] += delta_bb
        stage_map[players] = entry

    def _spr_bucket(spr: float) -> str:
        if spr < 1:
            return "<1"
        if spr < 2:
            return "1-2"
        if spr < 4:
            return "2-4"
        if spr < 7:
            return "4-7"
        return "7+"

    def _pot_bucket(pot_bb: float) -> str:
        if pot_bb <= 5:
            return "0-5"
        if pot_bb <= 10:
            return "5-10"
        if pot_bb <= 20:
            return "10-20"
        return "20+"

    def _open_size_bucket(open_size_bb: float) -> str:
        if open_size_bb <= 2.5:
            return "2.0-2.5"
        if open_size_bb <= 3.0:
            return "2.5-3.0"
        if open_size_bb <= 3.5:
            return "3.0-3.5"
        if open_size_bb <= 4.5:
            return "3.5-4.5"
        return "4.5+"

    def _size_bucket(ratio: float) -> str:
        if ratio <= 0.33:
            return "0-0.33"
        if ratio <= 0.66:
            return "0.33-0.66"
        if ratio <= 1.0:
            return "0.66-1.0"
        if ratio <= 1.5:
            return "1.0-1.5"
        return ">1.5"

    def _price_bucket(price: float) -> str:
        if price <= 0.20:
            return "0-0.20"
        if price <= 0.33:
            return "0.20-0.33"
        if price <= 0.50:
            return "0.33-0.50"
        return ">0.50"

    def _acc_trace_metric(entry: dict[str, int], key: str, value: int | None) -> None:
        if value is None:
            return
        entry[f"{key}_sum"] = int(entry.get(f"{key}_sum", 0)) + int(value)
        entry[f"{key}_count"] = int(entry.get(f"{key}_count", 0)) + 1

    for e in objs:
        if not isinstance(e, dict):
            continue
        ev = e.get("event")

        if ev == "HandStart":
            # finalize previous hand
            current_hand = {
                "vpip": False,
                "pfr": False,
                "model_folded": False,
                "raise_level": 0,
                "stage_players": {},
                "last_raiser": {"PREFLOP": None, "FLOP": None, "TURN": None},
                "model_first_action_on": set(),
                "saw_flop": False,
                "saw_turn": False,
                "saw_river": False,
                "button_seat": e.get("button_seat"),
                "seats_in_hand": e.get("seats_in_hand") or [],
                "position": None,
                "spr_buckets": set(),
                "model_opened": False,
                "model_opened_late": False,
                "open_pos": None,
                "model_3bet": False,
                "model_4bet": False,
                "checked_by_street": set(),
                "check_raised": set(),
                "bb_flat": False,
                "bb_flat_spr_bucket": None,
                "bb_flat_street_info": {},
                "flop_suit_texture": None,
                "flop_rank_texture": None,
            }
            if isinstance(current_hand["button_seat"], int) and isinstance(model_seat, int):
                try:
                    current_hand["position"] = position_key(model_seat, current_hand["button_seat"], current_hand["seats_in_hand"])
                except Exception:
                    current_hand["position"] = "OTHERS"
            decision_snap.clear()
            decision_obs.clear()

        elif ev == "DecisionPoint":
            key = _decision_key(e)
            snap = e.get("snapshot_payload") or {}
            obs_view = e.get("observation_view_payload") or {}
            if key is not None:
                decision_snap[key] = snap
                decision_obs[key] = obs_view
            street = snap.get("street")
            pac = snap.get("players_alive_count")
            if isinstance(street, str) and street not in (current_hand or {}).get("stage_players", {}):
                if current_hand is not None and isinstance(pac, int):
                    current_hand["stage_players"][street] = pac
                if current_hand is not None and not current_hand.get("model_folded", False):
                    if street == "FLOP":
                        current_hand["saw_flop"] = True
                    elif street == "TURN":
                        current_hand["saw_turn"] = True
                    elif street == "RIVER":
                        current_hand["saw_river"] = True
            if (
                current_hand is not None
                and current_hand.get("bb_flat")
                and current_hand.get("bb_flat_spr_bucket") is None
                and street == "FLOP"
                and snap.get("actor_seat") == model_seat
            ):
                pot_chips = int(snap.get("pot_chips", 0) or 0)
                actor_stack = int(snap.get("actor_stack_chips", 0) or 0)
                spr = actor_stack / pot_chips if pot_chips > 0 else 99.0
                current_hand["bb_flat_spr_bucket"] = _spr_bucket(spr)
            if (
                current_hand is not None
                and current_hand.get("bb_flat")
                and street in ("FLOP", "TURN", "RIVER")
                and snap.get("actor_seat") == model_seat
            ):
                info = current_hand.setdefault("bb_flat_street_info", {})
                if street not in info:
                    pot_chips = int(snap.get("pot_chips", 0) or 0)
                    actor_stack = int(snap.get("actor_stack_chips", 0) or 0)
                    spr = actor_stack / pot_chips if pot_chips > 0 else 99.0
                    pot_bb = pot_chips / bb_chips if bb_chips else 0.0
                    to_call_local = int(snap.get("to_call_chips", 0) or 0)
                    info[street] = {
                        "spr_bucket": _spr_bucket(spr),
                        "pot_bucket": _pot_bucket(pot_bb),
                        "facing": bool(to_call_local > 0),
                    }

            if (
                current_hand is not None
                and street == "FLOP"
                and current_hand.get("flop_suit_texture") is None
            ):
                board_raw = obs_view.get("board_cards") or []
                if isinstance(board_raw, list) and len(board_raw) >= 3:
                    flop_cards = [parse_card_token(c) for c in board_raw[:3]]
                    if all(c is not None for c in flop_cards):
                        cards = [c for c in flop_cards if c is not None]
                        texture = board_texture(cards)
                        if texture:
                            current_hand["flop_suit_texture"] = texture[0]
                            current_hand["flop_rank_texture"] = texture[1]

        elif ev == "ActionChosen":
            key = _decision_key(e)
            snap = decision_snap.get(key, {})
            obs = decision_obs.get(key, {})
            street = snap.get("street")
            actor = snap.get("actor_seat")
            prev_raise_level = current_hand["raise_level"] if current_hand is not None else 0
            if street not in street_stats or actor is None:
                continue

            executed = e.get("executed_action") or {}
            derived = e.get("derived_action") or {}
            kind = executed.get("kind")
            to_call = snap.get("to_call_chips") or 0
            actor_commit_local = int(snap.get("actor_commit_chips", 0) or 0)
            players_alive = snap.get("players_alive_count")
            if snap.get("raise_cap_to_chips") is not None:
                raise_cap_hits += 1

            # track raises for aggression hierarchy (all actors)
            if kind in ("BET", "RAISE") and current_hand is not None:
                current_hand["last_raiser"][street] = actor
                if street == "PREFLOP":
                    current_hand["raise_level"] += 1
                    if actor == model_seat:
                        if current_hand["raise_level"] == 1:
                            open_count += 1
                            current_hand["model_opened"] = True
                            current_hand["open_pos"] = current_hand.get("position")
                            _inc_open_by_pos(current_hand.get("open_pos"), "open")
                            if bb_chips:
                                target_commit = int(executed.get("target_total_commit_chips", 0) or 0)
                                if target_commit > 0:
                                    open_size_bb = target_commit / bb_chips
                                    open_size_sum += open_size_bb
                                    open_size_count += 1
                                    size_bucket = _open_size_bucket(open_size_bb)
                                    open_size_buckets[size_bucket] = open_size_buckets.get(size_bucket, 0) + 1
                                    pos_key = _pos_key(current_hand.get("open_pos"))
                                    entry = open_size_by_pos.setdefault(pos_key, {"count": 0, "sum_bb": 0.0})
                                    entry["count"] = int(entry.get("count", 0)) + 1
                                    entry["sum_bb"] = float(entry.get("sum_bb", 0.0)) + open_size_bb
                            if current_hand.get("position") in ("BU", "SB"):
                                open_count_late += 1
                                current_hand["model_opened_late"] = True
                        elif current_hand["raise_level"] == 2:
                            threebet_count += 1
                            current_hand["model_3bet"] = True
                        elif current_hand["raise_level"] >= 3:
                            fourbet_count += 1
                            current_hand["model_4bet"] = True

            if actor == model_seat:
                st = street_stats[street]
                st["dec"] += 1
                stv = street_value_stats[street]
                stv["dec"] += 1
                if isinstance(players_alive, int):
                    stv["players_sum"] += players_alive
                pot_chips = int(snap.get("pot_chips", 0) or 0)
                stack_chips = int(snap.get("actor_stack_chips", 0) or 0)
                if bb_chips:
                    stv["pot_bb_sum"] += pot_chips / bb_chips
                    stv["stack_bb_sum"] += stack_chips / bb_chips
                    if pot_chips > 0:
                        stv["spr_sum"] += stack_chips / pot_chips
                        stv["spr_count"] += 1
                    if to_call > 0:
                        stv["facing_bb_sum"] += to_call / bb_chips
                        stv["facing_count"] += 1
                        if kind == "CALL":
                            stv["call_bb_sum"] += to_call / bb_chips
                            stv["call_count"] += 1
                if kind == "FOLD":
                    st["fold"] += 1
                    if current_hand is not None:
                        current_hand["model_folded"] = True
                elif kind == "CALL":
                    st["call"] += 1
                elif kind == "BET":
                    st["bet"] += 1
                    st["agg"] += 1
                elif kind == "RAISE":
                    st["raise"] += 1
                    st["agg"] += 1
                if derived.get("is_allin"):
                    st["allin"] += 1

                if current_hand is not None and street == "PREFLOP":
                    sr_val = 0
                    sr_map = obs.get("street_raise_count") or {}
                    if isinstance(sr_map, dict):
                        sr_val = int(sr_map.get("PREFLOP", 0) or 0)
                    pos_key = current_hand.get("position") or "OTHERS"
                    if sr_val == 0 and to_call > 0:
                        first_in_by_pos[pos_key] = first_in_by_pos.get(pos_key, 0) + 1
                        if kind in ("RAISE", "BET"):
                            open_first_in_by_pos[pos_key] = open_first_in_by_pos.get(pos_key, 0) + 1
                    elif sr_val >= 1 and to_call > 0:
                        facing_open_by_pos[pos_key] = facing_open_by_pos.get(pos_key, 0) + 1

                if current_hand is not None and kind == "CHECK" and street in ("FLOP", "TURN", "RIVER"):
                    current_hand["checked_by_street"].add(street)

                if current_hand is not None and street == "PREFLOP" and current_hand.get("preflop_action") is None:
                    if kind in ("RAISE", "BET"):
                        if prev_raise_level <= 0:
                            current_hand["preflop_action"] = "open"
                        elif prev_raise_level == 1:
                            current_hand["preflop_action"] = "3bet"
                        else:
                            current_hand["preflop_action"] = "4bet"
                    elif kind == "CALL":
                        current_hand["preflop_action"] = "flat"
                    elif kind == "FOLD":
                        current_hand["preflop_action"] = "fold"
                    elif kind == "CHECK":
                        current_hand["preflop_action"] = "check"

                if to_call > 0:
                    st["facing"] += 1
                    if kind == "FOLD":
                        st["fold_when_facing"] += 1
                    pot_for_mdf = int(snap.get("pot_chips", 0) or 0)
                    if pot_for_mdf < 0:
                        pot_for_mdf = 0
                    denom = max(1.0, float(pot_for_mdf + to_call))
                    mdf = float(pot_for_mdf) / denom
                    defenders = max(1, int(players_alive or 2) - 1)
                    if defenders <= 1:
                        mdf_adj = mdf
                    else:
                        mdf_adj = 1.0 - (1.0 - mdf) ** (1.0 / defenders)
                    ms = mdf_stats.get(street)
                    if ms is not None:
                        ms["facing"] += 1
                        if kind in ("CALL", "RAISE", "ALLIN"):
                            ms["defend"] += 1
                        ms["mdf_sum"] += mdf
                        ms["mdf_adj_sum"] += mdf_adj
                    price = to_call / max(1.0, float(pot_for_mdf + to_call))
                    price_bucket = _price_bucket(price)
                    trace = None
                    try:
                        trace = (e.get("proposed_action") or {}).get("policy_trace")
                    except Exception:
                        trace = None
                    if isinstance(trace, dict) and trace.get("trace_schema_id") == "defense_trace_v1":
                        pos_trace = trace.get("pos_key")
                        pos_use = pos_trace if pos_trace in ("SB", "BB") else (current_hand or {}).get("position")
                        if pos_use in ("SB", "BB"):
                            defense_trace_total += 1
                            solver_ev_present = (
                                trace.get("solver_call_ev_chips") is not None
                                or trace.get("solver_raise_ev_chips") is not None
                            )
                            if solver_ev_present:
                                solver_ev_trace_hits += 1
                                if street in solver_ev_trace_by_street:
                                    solver_ev_trace_by_street[street] += 1
                            cap_marginal_ppm = trace.get("raise_cap_marginal_ppm")
                            if cap_marginal_ppm is not None:
                                raise_cap_marginal_total += 1
                                if street in raise_cap_marginal_by_street:
                                    raise_cap_marginal_by_street[street]["total"] += 1
                                try:
                                    cap_val = int(cap_marginal_ppm)
                                except Exception:
                                    cap_val = None
                                target_ppm = trace.get("target_raise_ppm")
                                try:
                                    target_val = int(target_ppm) if target_ppm is not None else None
                                except Exception:
                                    target_val = None
                                if cap_val is not None and target_val is not None:
                                    # consider cap binding if target within 2% of cap
                                    if target_val >= cap_val - 20000:
                                        raise_cap_marginal_hits += 1
                                        if street in raise_cap_marginal_by_street:
                                            raise_cap_marginal_by_street[street]["hits"] += 1
                            key = f"{pos_use}|{street}|{price_bucket}"
                            entry_edge = bb_sb_facing_edge.setdefault(
                                key,
                                {"hands": 0},
                            )
                            entry_edge["hands"] = int(entry_edge.get("hands", 0)) + 1
                            _acc_trace_metric(entry_edge, "edge_ratio_ppm", trace.get("best_raise_edge_ratio_ppm"))
                            _acc_trace_metric(entry_edge, "call_edge_ratio_ppm", trace.get("call_edge_ratio_ppm"))
                            _acc_trace_metric(entry_edge, "raise_cap_ppm", trace.get("raise_cap_ppm"))
                            _acc_trace_metric(entry_edge, "raise_cap_marginal_ppm", trace.get("raise_cap_marginal_ppm"))
                            _acc_trace_metric(entry_edge, "target_raise_ppm", trace.get("target_raise_ppm"))
                            _acc_trace_metric(entry_edge, "current_raise_ppm", trace.get("current_raise_ppm"))
                    entry = facing_price_stats.setdefault(
                        price_bucket,
                        {"facing": 0, "defend": 0, "mdf_sum": 0.0, "mdf_adj_sum": 0.0},
                    )
                    entry["facing"] += 1
                    if kind in ("CALL", "RAISE", "ALLIN"):
                        entry["defend"] += 1
                    entry["mdf_sum"] += mdf
                    entry["mdf_adj_sum"] += mdf_adj
                    st_stats = facing_price_stats_by_street.setdefault(street or "UNK", {})
                    entry_st = st_stats.setdefault(
                        price_bucket,
                        {"facing": 0, "defend": 0, "mdf_sum": 0.0, "mdf_adj_sum": 0.0},
                    )
                    entry_st["facing"] += 1
                    if kind in ("CALL", "RAISE", "ALLIN"):
                        entry_st["defend"] += 1
                    entry_st["mdf_sum"] += mdf
                    entry_st["mdf_adj_sum"] += mdf_adj
                    bucket_ratio(street or "UNK", to_call / bb if bb else 0.0)
                    bucket_outcome(street or "UNK", to_call / bb if bb else 0.0, kind)
                    if current_hand is not None and street == "PREFLOP":
                        if current_hand.get("model_opened") and current_hand.get("raise_level", 0) >= 2:
                            key = "open_call_3bet" if kind == "CALL" else "open_fold_3bet" if kind == "FOLD" else None
                            if key:
                                preflop_responses[key] += 1
                        if current_hand.get("model_3bet") and current_hand.get("raise_level", 0) >= 3:
                            key = "3bet_call_4bet" if kind == "CALL" else "3bet_fold_4bet" if kind == "FOLD" else None
                            if key:
                                preflop_responses[key] += 1
                        if current_hand.get("raise_level", 0) == 1 and kind == "CALL":
                            preflop_responses["flat_vs_open"] += 1
                    if current_hand is not None and street == "PREFLOP":
                        lvl = current_hand["raise_level"]
                        target = defend_vs_open if lvl == 1 else defend_vs_3bet if lvl == 2 else defend_vs_4bet
                        if kind == "FOLD":
                            target["fold"] += 1
                        elif kind == "CALL":
                            target["call"] += 1
                        else:
                            target["raise"] += 1
                        if sr_val == 1:
                            if kind == "FOLD":
                                _inc_defend_open_by_pos(current_hand.get("position"), "fold")
                            elif kind == "CALL":
                                _inc_defend_open_by_pos(current_hand.get("position"), "call")
                            else:
                                _inc_defend_open_by_pos(current_hand.get("position"), "raise")
                            opener_pos = None
                            last_raiser_map = obs.get("last_raiser_by_street") or {}
                            if isinstance(last_raiser_map, dict):
                                opener_seat = last_raiser_map.get("PREFLOP")
                                if isinstance(opener_seat, int):
                                    try:
                                        opener_pos = position_key(opener_seat, current_hand.get("button_seat"), current_hand.get("seats_in_hand"))
                                    except Exception:
                                        opener_pos = "OTHERS"
                            opener_key = opener_pos if opener_pos in ("BU", "SB", "BB", "OTHERS") else "OTHERS"
                            entry_by_opener = defend_vs_open_by_opener_pos.setdefault(opener_key, {"fold": 0, "call": 0, "raise": 0})
                            if kind == "FOLD":
                                entry_by_opener["fold"] += 1
                            elif kind == "CALL":
                                entry_by_opener["call"] += 1
                            else:
                                entry_by_opener["raise"] += 1
                            if current_hand.get("position") == "BB":
                                entry = bb_vs_open_by_pos.setdefault(opener_key, {"fold": 0, "call": 0, "3bet": 0})
                                if kind == "FOLD":
                                    entry["fold"] += 1
                                elif kind == "CALL":
                                    entry["call"] += 1
                                    current_hand["bb_flat"] = True
                                else:
                                    entry["3bet"] += 1
                                if bb_chips > 0:
                                    open_size_bb = (to_call + bb_chips) / bb_chips
                                    size_bucket = _open_size_bucket(open_size_bb)
                                    entry_size = bb_vs_open_by_size.setdefault(size_bucket, {"fold": 0, "call": 0, "3bet": 0})
                                    if kind == "FOLD":
                                        entry_size["fold"] += 1
                                    elif kind == "CALL":
                                        entry_size["call"] += 1
                                    else:
                                        entry_size["3bet"] += 1
                    if current_hand is not None and street in ("FLOP", "TURN", "RIVER"):
                        if street in current_hand.get("checked_by_street", set()) and street not in current_hand.get("check_raised", set()):
                            check_raise_counts[street] = check_raise_counts.get(street, 0) + 1
                            current_hand["check_raised"].add(street)

                if current_hand is not None:
                    # vpip / pfr flags
                    if street == "PREFLOP" and kind in ("CALL", "BET", "RAISE"):
                        current_hand["vpip"] = True
                    if street == "PREFLOP" and kind in ("BET", "RAISE"):
                        current_hand["pfr"] = True

                    # c-bet attempt detection (first action on street after being last aggressor previous street)
                    palive = int(players_alive) if isinstance(players_alive, int) else 0
                    if street == "FLOP" and current_hand["last_raiser"].get("PREFLOP") == model_seat:
                        if street not in current_hand["model_first_action_on"]:
                            cbet_flop_attempt += 1
                            if palive <= 2:
                                cbet_flop_hu_attempt += 1
                            else:
                                cbet_flop_mw_attempt += 1
                            if kind in ("BET", "RAISE"):
                                cbet_flop_success += 1
                                if palive <= 2:
                                    cbet_flop_hu_success += 1
                                else:
                                    cbet_flop_mw_success += 1
                            current_hand["model_first_action_on"].add(street)
                    if street == "TURN" and current_hand["last_raiser"].get("FLOP") == model_seat:
                        if street not in current_hand["model_first_action_on"]:
                            cbet_turn_attempt += 1
                            if palive <= 2:
                                cbet_turn_hu_attempt += 1
                            else:
                                cbet_turn_mw_attempt += 1
                            if kind in ("BET", "RAISE"):
                                cbet_turn_success += 1
                                if palive <= 2:
                                    cbet_turn_hu_success += 1
                                else:
                                    cbet_turn_mw_success += 1
                            current_hand["model_first_action_on"].add(street)
                    if street == "RIVER" and current_hand["last_raiser"].get("TURN") == model_seat:
                        if street not in current_hand["model_first_action_on"]:
                            cbet_river_attempt += 1
                            if palive <= 2:
                                cbet_river_hu_attempt += 1
                            else:
                                cbet_river_mw_attempt += 1
                            if kind in ("BET", "RAISE"):
                                cbet_river_success += 1
                                if palive <= 2:
                                    cbet_river_hu_success += 1
                                else:
                                    cbet_river_mw_success += 1
                            current_hand["model_first_action_on"].add(street)

                    # Donk bet detection (betting into previous street aggressor)
                    if street in ("FLOP", "TURN", "RIVER") and kind in ("BET", "RAISE") and to_call == 0:
                        last_raiser_map = obs.get("last_raiser_by_street") or {}
                        prev_street = {"FLOP": "PREFLOP", "TURN": "FLOP", "RIVER": "TURN"}.get(street)
                        prev_aggressor = last_raiser_map.get(prev_street) if isinstance(last_raiser_map, dict) else None
                        if prev_aggressor is not None and prev_aggressor != model_seat:
                            donk_counts[street] = donk_counts.get(street, 0) + 1

                    # SPR bucket (postflop) for weakness localization
                    if street in ("FLOP", "TURN", "RIVER"):
                        pot_chips = snap.get("pot_chips") or 0
                        stack_chips = snap.get("actor_stack_chips") or 0
                        if pot_chips > 0:
                            spr_val = stack_chips / pot_chips
                            bucket = _spr_bucket(spr_val)
                            current_hand.setdefault("spr_buckets", set()).add(bucket)

                if kind in ("BET", "RAISE") and street in ("FLOP", "TURN", "RIVER"):
                    target = int(executed.get("target_total_commit_chips", actor_commit_local) or actor_commit_local)
                    bet_size = max(0, target - actor_commit_local)
                    pot_base = max(1, int(snap.get("pot_chips", 0) or 0))
                    ratio = bet_size / pot_base
                    stv = street_value_stats[street]
                    stv["bet_frac_sum"] += ratio
                    stv["bet_count"] += 1
                    bucket = _size_bucket(ratio)
                    table = bet_size_buckets.setdefault(street, {})
                    table[bucket] = table.get(bucket, 0) + 1
                    bet_size_sum[street] += ratio
                    bet_size_count[street] += 1
                    if kind == "RAISE":
                        raise_add = max(0, bet_size - int(to_call))
                        raise_ratio = raise_add / pot_base
                        stv["raise_add_frac_sum"] += raise_ratio
                        stv["raise_count"] += 1
                        raise_add_sum[street] += raise_ratio
                        raise_add_count[street] += 1

                routing = e.get("routing") if isinstance(e.get("routing"), dict) else None
                rung_id = routing.get("rung_id") if routing else None
                if rung_id:
                    rs = rung_stats.setdefault(
                        rung_id,
                        {"dec": 0, "fold": 0, "call": 0, "bet": 0, "raise": 0, "allin": 0, "facing": 0, "fold_when_facing": 0},
                    )
                    rs["dec"] += 1
                    if to_call > 0:
                        rs["facing"] += 1
                        if kind == "FOLD":
                            rs["fold_when_facing"] += 1
                    if kind == "FOLD":
                        rs["fold"] += 1
                    elif kind == "CALL":
                        rs["call"] += 1
                    elif kind == "BET":
                        rs["bet"] += 1
                    elif kind == "RAISE":
                        rs["raise"] += 1
                    if derived.get("is_allin"):
                        rs["allin"] += 1

            action_records.append({"seat": actor, "kind": kind, "street": street})

            # stage players for profit buckets
            if isinstance(players_alive, int) and current_hand is not None and street in ("FLOP", "TURN", "RIVER"):
                current_hand["stage_players"].setdefault(street, players_alive)

        elif ev == "HandEnd" and current_hand is not None:
            hands += 1
            seats_this = current_hand.get("seats_in_hand") or []
            btn = current_hand.get("button_seat")
            sb_seat = bb_seat = None
            if btn in seats_this and len(seats_this) >= 2:
                try:
                    idx = seats_this.index(btn)
                    sb_seat = seats_this[(idx + 1) % len(seats_this)]
                    bb_seat = seats_this[(idx + 2) % len(seats_this)]
                except Exception:
                    sb_seat = bb_seat = None

            initial_stacks = e.get("initial_stacks_by_seat") or {}
            if starting_stack_bb is None and str(model_seat) in initial_stacks:
                starting_stack_bb = int(initial_stacks.get(str(model_seat), 0) or 0) / max(1, bb_chips)

            delta = int(e.get("stack_deltas_by_seat", {}).get(str(model_seat), 0) or 0)
            delta_bb = delta / bb_chips if bb_chips else 0.0
            hand_profit.append(delta)
            role = current_hand.get("preflop_action")
            if isinstance(role, str) and role:
                entry_role = preflop_role_profit.setdefault(role, {"hands": 0, "profit_bb": 0.0})
                entry_role["hands"] = int(entry_role.get("hands", 0)) + 1
                entry_role["profit_bb"] = float(entry_role.get("profit_bb", 0.0)) + delta_bb
            if current_hand.get("saw_flop"):
                if current_hand.get("model_opened") or current_hand.get("model_3bet") or current_hand.get("model_4bet"):
                    role_post = "aggressor"
                elif role == "flat":
                    role_post = "defender"
                elif role == "check":
                    role_post = "checker"
                else:
                    role_post = "other"
                entry_post = postflop_role_profit.setdefault(role_post, {"hands": 0, "profit_bb": 0.0})
                entry_post["hands"] = int(entry_post.get("hands", 0)) + 1
                entry_post["profit_bb"] = float(entry_post.get("profit_bb", 0.0)) + delta_bb
            if current_hand.get("bb_flat") and current_hand.get("saw_flop") and current_hand.get("bb_flat_spr_bucket"):
                spr_bucket = current_hand.get("bb_flat_spr_bucket")
                oop = current_hand.get("position") in ("SB", "BB")
                multi_street = bool(current_hand.get("saw_turn") or current_hand.get("saw_river"))
                oop_multi = bool(oop and multi_street)
                key = f"{spr_bucket}|{oop_multi}"
                entry = bb_flat_postflop.setdefault(
                    key,
                    {"spr_bucket": spr_bucket, "oop_multi_street": oop_multi, "hands": 0, "profit_bb": 0.0},
                )
                entry["hands"] = int(entry.get("hands", 0)) + 1
                entry["profit_bb"] = float(entry.get("profit_bb", 0.0)) + delta_bb
                for st in ("FLOP", "TURN", "RIVER"):
                    if current_hand.get(f"saw_{st.lower()}"):
                        entry_st = bb_flat_postflop_by_street.setdefault(
                            st, {"street": st, "hands": 0, "profit_bb": 0.0}
                        )
                        entry_st["hands"] = int(entry_st.get("hands", 0)) + 1
                        entry_st["profit_bb"] = float(entry_st.get("profit_bb", 0.0)) + delta_bb
                for st, st_info in (current_hand.get("bb_flat_street_info") or {}).items():
                    spr_b = st_info.get("spr_bucket")
                    pot_b = st_info.get("pot_bucket")
                    facing_b = bool(st_info.get("facing"))
                    if spr_b:
                        key_spr = f"{st}|{spr_b}"
                        entry_spr = bb_flat_postflop_spr_by_street.setdefault(
                            key_spr,
                            {"street": st, "spr_bucket": spr_b, "hands": 0, "profit_bb": 0.0},
                        )
                        entry_spr["hands"] = int(entry_spr.get("hands", 0)) + 1
                        entry_spr["profit_bb"] = float(entry_spr.get("profit_bb", 0.0)) + delta_bb
                    if pot_b:
                        key_pot = f"{st}|{pot_b}"
                        entry_pot = bb_flat_postflop_pot_by_street.setdefault(
                            key_pot,
                            {"street": st, "pot_bucket": pot_b, "hands": 0, "profit_bb": 0.0},
                        )
                        entry_pot["hands"] = int(entry_pot.get("hands", 0)) + 1
                        entry_pot["profit_bb"] = float(entry_pot.get("profit_bb", 0.0)) + delta_bb
                    key_face = f"{st}|{'Y' if facing_b else 'N'}"
                    entry_face = bb_flat_postflop_facing_by_street.setdefault(
                        key_face,
                        {"street": st, "facing": "Y" if facing_b else "N", "hands": 0, "profit_bb": 0.0},
                    )
                    entry_face["hands"] = int(entry_face.get("hands", 0)) + 1
                    entry_face["profit_bb"] = float(entry_face.get("profit_bb", 0.0)) + delta_bb

            flop_suit = current_hand.get("flop_suit_texture")
            flop_rank = current_hand.get("flop_rank_texture")
            if flop_suit:
                entry = flop_suit_texture.setdefault(flop_suit, {"hands": 0, "profit_bb": 0.0})
                entry["hands"] = int(entry.get("hands", 0)) + 1
                entry["profit_bb"] = float(entry.get("profit_bb", 0.0)) + delta_bb
            if flop_rank:
                entry = flop_rank_texture.setdefault(flop_rank, {"hands": 0, "profit_bb": 0.0})
                entry["hands"] = int(entry.get("hands", 0)) + 1
                entry["profit_bb"] = float(entry.get("profit_bb", 0.0)) + delta_bb

            # Track stage player distributions for realism checks
            stage_players = current_hand.get("stage_players", {})
            flop_p = stage_players.get("FLOP")
            turn_p = stage_players.get("TURN")
            river_p = stage_players.get("RIVER")
            if isinstance(flop_p, int):
                flop_players_dist[str(flop_p)] = flop_players_dist.get(str(flop_p), 0) + 1
            if isinstance(turn_p, int):
                turn_players_dist[str(turn_p)] = turn_players_dist.get(str(turn_p), 0) + 1
            if isinstance(river_p, int):
                river_players_dist[str(river_p)] = river_players_dist.get(str(river_p), 0) + 1

            # Steal / 3bet / 4bet success (preflop win)
            if not current_hand.get("saw_flop", False) and delta > 0:
                if current_hand.get("model_opened"):
                    open_steal_success += 1
                    _inc_open_by_pos(current_hand.get("open_pos"), "steal")
                if current_hand.get("model_opened_late"):
                    open_steal_success_late += 1
                if current_hand.get("model_3bet"):
                    threebet_success += 1
                if current_hand.get("model_4bet"):
                    fourbet_success += 1
            rake_chips = int(e.get("total_rake_chips", 0) or 0)
            rake_base = int(e.get("rake_base_pot_chips", 0) or 0)
            total_rake += rake_chips
            if rake_base > 0:
                total_rake_base += rake_base
                rake_frac_samples.append(rake_chips / rake_base)
            if rake_cap is not None and int(rake_cap or 0) > 0 and rake_chips >= int(rake_cap or 0):
                rake_cap_hits_count += 1

            if current_hand.get("saw_flop"):
                saw_flop_hands += 1
                wwsf_hands += 1
                if delta > 0:
                    wwsf_wins += 1
                saw_flop_profit += delta
            else:
                no_flop_profit += delta
            if current_hand.get("saw_turn"):
                saw_turn_hands += 1
                saw_turn_profit += delta
            if current_hand.get("saw_river"):
                saw_river_hands += 1
                saw_river_profit += delta
            if delta < 0:
                if current_hand.get("vpip"):
                    loss_with_vpip += 1
                    loss_with_vpip_chips += delta
                else:
                    loss_no_vpip += 1
                    loss_no_vpip_chips += delta
                if current_hand.get("saw_flop"):
                    loss_saw_flop += 1
                    loss_saw_flop_chips += delta
                if current_hand.get("saw_turn"):
                    loss_saw_turn += 1
                    loss_saw_turn_chips += delta
                if current_hand.get("saw_river"):
                    loss_saw_river += 1
                    loss_saw_river_chips += delta
            if not current_hand.get("model_folded", False):
                showdown_hands += 1
                if current_hand.get("saw_flop"):
                    showdown_after_flop += 1
                if current_hand.get("saw_turn"):
                    showdown_after_turn += 1
                if current_hand.get("saw_river"):
                    showdown_after_river += 1
                if delta > 0:
                    showdown_wins += 1
                showdown_profit_chips += delta
            else:
                non_showdown_profit_chips += delta

            forced_map = e.get("forced_bets_total_by_seat") or {}
            actual_forced = int(forced_map.get(str(model_seat), 0) or 0)
            expected_forced = 0
            if model_seat in seats_this:
                expected_forced += ante_amt
                if model_seat == sb_seat:
                    expected_forced += sb
                    sb_count += 1
                if model_seat == bb_seat:
                    expected_forced += bb_chips
                    bb_count += 1
            model_forced_total += actual_forced
            model_forced_expected_total += expected_forced
            diff_forced = actual_forced - expected_forced
            if diff_forced != 0:
                forced_mismatch_count += 1
                forced_mismatch_max = max(forced_mismatch_max, abs(diff_forced))

            pot_chips = rake_base if rake_base is not None else e.get("rake_base_pot_chips")
            if pot_chips is not None:
                pot_bb = float(pot_chips) / bb_chips if bb_chips else 0.0
                avg_pot_samples.append(pot_bb)
                if pot_bb < 5:
                    bucket_key = "0-5"
                elif pot_bb < 10:
                    bucket_key = "5-10"
                elif pot_bb < 20:
                    bucket_key = "10-20"
                else:
                    bucket_key = "20+"
                pot_buckets[bucket_key] += 1
                entry = pot_bucket_profit.setdefault(bucket_key, {"hands": 0, "profit_bb": 0.0})
                entry["hands"] = int(entry.get("hands", 0)) + 1
                entry["profit_bb"] = float(entry.get("profit_bb", 0.0)) + delta_bb

            if delta > 0:
                win_hands += 1
            elif delta < 0:
                loss_hands += 1
            else:
                tie_hands += 1

            add_profit_bucket("FLOP", current_hand["stage_players"].get("FLOP"), delta_bb)
            add_profit_bucket("TURN", current_hand["stage_players"].get("TURN"), delta_bb)
            add_profit_bucket("RIVER", current_hand["stage_players"].get("RIVER"), delta_bb)

            pos = current_hand.get("position") or "OTHERS"
            entry = position_profit.get(pos, {"hands": 0, "profit_bb": 0.0, "vpip_hands": 0, "pfr_hands": 0})
            entry["hands"] += 1
            entry["profit_bb"] += delta_bb
            if current_hand["vpip"]:
                entry["vpip_hands"] += 1
            if current_hand["pfr"]:
                entry["pfr_hands"] += 1
            position_profit[pos] = entry

            pos_entry = position_preflop.get(
                pos,
                {"hands": 0, "open": 0, "flat": 0, "3bet": 0, "4bet": 0, "fold": 0, "check": 0},
            )
            pos_entry["hands"] += 1
            pre_act = current_hand.get("preflop_action")
            if isinstance(pre_act, str) and pre_act in pos_entry:
                pos_entry[pre_act] += 1
            position_preflop[pos] = pos_entry

            for b in current_hand.get("spr_buckets", []):
                spr_entry = spr_buckets.get(b, {"hands": 0, "profit_bb": 0.0})
                spr_entry["hands"] += 1
                spr_entry["profit_bb"] += delta_bb
                spr_buckets[b] = spr_entry

            # vpip/pfr tallies
            if current_hand["vpip"]:
                preflop_vpip_hands += 1
                vpip_profit_chips += delta
            if current_hand["pfr"]:
                preflop_pfr_hands += 1
            if not current_hand["vpip"]:
                non_vpip_profit_chips += delta

            current_hand = None

    profit_total = sum(hand_profit)
    profit_bb = profit_total / bb_chips if bb_chips else 0.0
    bb_per_100 = profit_bb * 100 / max(1, hands)
    total_rake_bb = total_rake / bb_chips if bb_chips else 0.0
    rake_bb_per_100 = total_rake_bb * 100 / max(1, hands)
    rake_frac_avg = sum(rake_frac_samples) / len(rake_frac_samples) if rake_frac_samples else 0.0
    rake_frac_overall = (total_rake / total_rake_base) if total_rake_base > 0 else 0.0
    model_rake_bb = ((total_rake * (preflop_vpip_hands / max(1, hands))) / bb_chips) if bb_chips else 0.0
    profit_bb_gross = profit_bb + model_rake_bb
    showdown_profit_bb = showdown_profit_chips / bb_chips if bb_chips else 0.0
    non_showdown_profit_bb = non_showdown_profit_chips / bb_chips if bb_chips else 0.0
    vpip_profit_bb = vpip_profit_chips / bb_chips if bb_chips else 0.0
    non_vpip_profit_bb = non_vpip_profit_chips / bb_chips if bb_chips else 0.0
    saw_flop_profit_bb = saw_flop_profit / bb_chips if bb_chips else 0.0
    no_flop_profit_bb = no_flop_profit / bb_chips if bb_chips else 0.0
    saw_turn_profit_bb = saw_turn_profit / bb_chips if bb_chips else 0.0
    saw_river_profit_bb = saw_river_profit / bb_chips if bb_chips else 0.0
    loss_no_vpip_bb = loss_no_vpip_chips / bb_chips if bb_chips else 0.0
    loss_with_vpip_bb = loss_with_vpip_chips / bb_chips if bb_chips else 0.0
    loss_saw_flop_bb = loss_saw_flop_chips / bb_chips if bb_chips else 0.0
    loss_saw_turn_bb = loss_saw_turn_chips / bb_chips if bb_chips else 0.0
    loss_saw_river_bb = loss_saw_river_chips / bb_chips if bb_chips else 0.0

    bb_sb_facing_edge_rows: list[dict[str, Any]] = []
    for key, entry in bb_sb_facing_edge.items():
        try:
            pos_key, street_key, price_bucket = key.split("|", 2)
        except ValueError:
            continue
        hands_count = int(entry.get("hands", 0) or 0)

        def _avg_ppm(metric: str) -> int | None:
            total = entry.get(f"{metric}_sum")
            count = entry.get(f"{metric}_count")
            if not isinstance(total, int) or not isinstance(count, int) or count <= 0:
                return None
            return int(round(total / count))

        bb_sb_facing_edge_rows.append(
            {
                "pos": pos_key,
                "street": street_key,
                "price_bucket": price_bucket,
                "hands": hands_count,
                "edge_ratio_ppm": _avg_ppm("edge_ratio_ppm"),
                "call_edge_ratio_ppm": _avg_ppm("call_edge_ratio_ppm"),
                "raise_cap_ppm": _avg_ppm("raise_cap_ppm"),
                "raise_cap_marginal_ppm": _avg_ppm("raise_cap_marginal_ppm"),
                "target_raise_ppm": _avg_ppm("target_raise_ppm"),
                "current_raise_ppm": _avg_ppm("current_raise_ppm"),
                "ref": f"report:BBDefendEdge/{pos_key}_{street_key}_{price_bucket}",
            }
        )

    forced_posted_bb = model_forced_total / bb_chips if bb_chips else 0.0
    forced_expected_bb = model_forced_expected_total / bb_chips if bb_chips else 0.0
    forced_mismatch_bb = (model_forced_total - model_forced_expected_total) / bb_chips if bb_chips else 0.0
    forced_mismatch_max_bb = forced_mismatch_max / bb_chips if bb_chips else 0.0
    model_ante_chips = model_forced_total - sb_count * sb - bb_count * bb_chips
    model_ante_bb = model_ante_chips / bb_chips if bb_chips else 0.0
    ante_expected_bb = (ante_amt * hands) / bb_chips if bb_chips else 0.0
    ante_total_bb = (ante_amt * seats_count * hands) / bb_chips if bb_chips else 0.0

    winrate = win_hands / max(1, hands)

    def _fold_to(street: str) -> float:
        st = street_stats.get(street, {})
        return (st.get("fold_when_facing", 0) / max(1, st.get("facing", 0)))

    bet_size_avg = {
        st: (bet_size_sum[st] / max(1, bet_size_count[st])) if st in bet_size_sum else 0.0 for st in bet_size_sum
    }
    raise_add_avg = {
        st: (raise_add_sum[st] / max(1, raise_add_count[st])) if st in raise_add_sum else 0.0 for st in raise_add_sum
    }
    open_size_by_pos_out: dict[str, dict[str, float | int]] = {}
    for pos, entry in open_size_by_pos.items():
        count = int(entry.get("count", 0) or 0)
        sum_bb = float(entry.get("sum_bb", 0.0) or 0.0)
        open_size_by_pos_out[pos] = {
            "count": count,
            "avg_bb": (sum_bb / max(1, count)) if count else 0.0,
        }

    return {
        "hands": hands,
        "profit_chips": profit_total,
        "profit_bb": profit_bb,
        "profit_bb_gross": profit_bb_gross,
        "total_rake_chips": total_rake,
        "total_rake_bb": total_rake_bb,
        "rake_bb_per_100": rake_bb_per_100,
        "hand_profit": hand_profit,
        "avg_pot_bb": sum(avg_pot_samples) / len(avg_pot_samples) if avg_pot_samples else 0.0,
        "pot_buckets": pot_buckets,
        "pot_bucket_profit": pot_bucket_profit,
        "win_hands": win_hands,
        "loss_hands": loss_hands,
        "tie_hands": tie_hands,
        "street_stats": street_stats,
        "mdf_stats": mdf_stats,
        "street_value_stats": street_value_stats,
        "vpip_hands": preflop_vpip_hands,
        "vpip_pct": preflop_vpip_hands / hands if hands else 0.0,
        "pfr_pct": preflop_pfr_hands / hands if hands else 0.0,
        "winrate": winrate,
        "actions": action_records,
        "cbet": {
            "flop": (cbet_flop_success, cbet_flop_attempt),
            "turn": (cbet_turn_success, cbet_turn_attempt),
            "river": (cbet_river_success, cbet_river_attempt),
        },
        "cbet_split": {
            "hu": {
                "flop": (cbet_flop_hu_success, cbet_flop_hu_attempt),
                "turn": (cbet_turn_hu_success, cbet_turn_hu_attempt),
                "river": (cbet_river_hu_success, cbet_river_hu_attempt),
            },
            "mw": {
                "flop": (cbet_flop_mw_success, cbet_flop_mw_attempt),
                "turn": (cbet_turn_mw_success, cbet_turn_mw_attempt),
                "river": (cbet_river_mw_success, cbet_river_mw_attempt),
            },
        },
        "facing_bet_buckets": facing_bet_buckets,
        "facing_bet_by_street": facing_bet_by_street,
        "facing_bet_outcomes": facing_bet_outcomes,
        "facing_bet_outcomes_by_street": facing_bet_outcomes_by_street,
        "facing_price_stats": facing_price_stats,
        "facing_price_stats_by_street": facing_price_stats_by_street,
        "profit_by_players": profit_by_players,
        "spr_buckets": spr_buckets,
        "position_profit": position_profit,
        "raise_cap_hits": raise_cap_hits,
        "defense_trace_total": defense_trace_total,
        "solver_ev_trace_hits": solver_ev_trace_hits,
        "solver_ev_trace_rate": solver_ev_trace_hits / max(1, defense_trace_total),
        "solver_ev_trace_by_street": solver_ev_trace_by_street,
        "raise_cap_marginal_total": raise_cap_marginal_total,
        "raise_cap_marginal_hits": raise_cap_marginal_hits,
        "raise_cap_marginal_rate": raise_cap_marginal_hits / max(1, raise_cap_marginal_total),
        "raise_cap_marginal_by_street": raise_cap_marginal_by_street,
        "open": open_count,
        "open_late": open_count_late,
        "open_size_avg": (open_size_sum / max(1, open_size_count)) if open_size_count else 0.0,
        "open_size_buckets": open_size_buckets,
        "open_size_by_pos": open_size_by_pos_out,
        "first_in_by_pos": first_in_by_pos,
        "open_first_in_by_pos": open_first_in_by_pos,
        "facing_open_by_pos": facing_open_by_pos,
        "threebet": threebet_count,
        "fourbet": fourbet_count,
        "open_steal_success": open_steal_success,
        "open_steal_success_late": open_steal_success_late,
        "open_by_pos": open_by_pos,
        "threebet_success": threebet_success,
        "fourbet_success": fourbet_success,
        "flop_players_dist": flop_players_dist,
        "turn_players_dist": turn_players_dist,
        "river_players_dist": river_players_dist,
        "check_raise_counts": check_raise_counts,
        "donk_counts": donk_counts,
        "defend_vs_open": defend_vs_open,
        "defend_vs_open_by_pos": defend_vs_open_by_pos,
        "defend_vs_open_by_opener_pos": defend_vs_open_by_opener_pos,
        "bb_vs_open_by_pos": bb_vs_open_by_pos,
        "bb_vs_open_by_size": bb_vs_open_by_size,
        "defend_vs_3bet": defend_vs_3bet,
        "defend_vs_4bet": defend_vs_4bet,
        "avg_win_bb": (sum(h for h in hand_profit if h > 0) / bb_chips) / max(1, win_hands) if bb_chips else 0,
        "avg_loss_bb": (sum(abs(h) for h in hand_profit if h < 0) / bb_chips) / max(1, loss_hands) if bb_chips else 0,
        "showdown_profit_bb": showdown_profit_bb,
        "non_showdown_profit_bb": non_showdown_profit_bb,
        "vpip_profit_bb": vpip_profit_bb,
        "non_vpip_profit_bb": non_vpip_profit_bb,
        "loss_no_vpip": loss_no_vpip,
        "loss_no_vpip_bb": loss_no_vpip_bb,
        "loss_with_vpip": loss_with_vpip,
        "loss_with_vpip_bb": loss_with_vpip_bb,
        "saw_flop_profit_bb": saw_flop_profit_bb,
        "no_flop_profit_bb": no_flop_profit_bb,
        "saw_turn_profit_bb": saw_turn_profit_bb,
        "saw_river_profit_bb": saw_river_profit_bb,
        "loss_saw_flop": loss_saw_flop,
        "loss_saw_flop_bb": loss_saw_flop_bb,
        "loss_saw_turn": loss_saw_turn,
        "loss_saw_turn_bb": loss_saw_turn_bb,
        "loss_saw_river": loss_saw_river,
        "loss_saw_river_bb": loss_saw_river_bb,
        "rake_frac_avg": rake_frac_avg,
        "rake_frac_overall": rake_frac_overall,
        "rake_cap_hits": rake_cap_hits_count,
        "wtsd": showdown_hands / max(1, hands),
        "wwsf": wwsf_wins / max(1, wwsf_hands),
        "wsd": showdown_wins / max(1, showdown_hands),
        "showdown_after_flop": showdown_after_flop,
        "showdown_after_turn": showdown_after_turn,
        "showdown_after_river": showdown_after_river,
        "showdown_hands": showdown_hands,
        "showdown_wins": showdown_wins,
        "saw_flop_hands": saw_flop_hands,
        "saw_turn_hands": saw_turn_hands,
        "saw_river_hands": saw_river_hands,
        "fold_to_flop_bet": _fold_to("FLOP"),
        "fold_to_turn_bet": _fold_to("TURN"),
        "fold_to_river_bet": _fold_to("RIVER"),
        "rung_stats": rung_stats,
        "mw_decisions": sum(v.get("dec", 0) for v in rung_stats.values()),
        "forced_posted_bb": forced_posted_bb,
        "forced_expected_bb": forced_expected_bb,
        "forced_mismatch_bb": forced_mismatch_bb,
        "forced_mismatch_count": forced_mismatch_count,
        "forced_mismatch_max_bb": forced_mismatch_max_bb,
        "model_ante_bb": model_ante_bb,
        "ante_expected_bb": ante_expected_bb,
        "ante_total_bb": ante_total_bb,
        "starting_stack_bb": starting_stack_bb,
        "model_rake_bb": model_rake_bb,
        "total_rake_base_bb": total_rake_base / bb_chips if bb_chips else 0.0,
        "bb_per_100": bb_per_100,
        "position_preflop": position_preflop,
        "preflop_responses": preflop_responses,
        "bb_flat_postflop": list(bb_flat_postflop.values()),
        "bb_flat_postflop_by_street": list(bb_flat_postflop_by_street.values()),
        "bb_flat_postflop_spr_by_street": list(bb_flat_postflop_spr_by_street.values()),
        "bb_flat_postflop_pot_by_street": list(bb_flat_postflop_pot_by_street.values()),
        "bb_flat_postflop_facing_by_street": list(bb_flat_postflop_facing_by_street.values()),
        "bb_sb_facing_edge": bb_sb_facing_edge_rows,
        "preflop_role_profit": preflop_role_profit,
        "postflop_role_profit": postflop_role_profit,
        "bet_size_buckets": bet_size_buckets,
        "bet_size_avg": bet_size_avg,
        "raise_add_avg": raise_add_avg,
        "flop_suit_texture": flop_suit_texture,
        "flop_rank_texture": flop_rank_texture,
        "starting_stack_bb": starting_stack_bb,
    }


def _ensure_policy_deps_in_paths_trace(
    *,
    policy_spec: dict[str, Any],
    paths_trace: dict[str, Any],
    paths_config: dict[str, Any],
) -> None:
    resolved_list = list(paths_trace.get("resolved_artifacts", []))
    resolved_refs = {e.get("artifact_ref") for e in resolved_list if isinstance(e, dict)}
    roots_trace = paths_trace.get("resolved_roots_abs", {}) or {}
    for dep in policy_spec.get("policy_deps", []):
        if not isinstance(dep, dict):
            continue
        ref = dep.get("artifact_ref")
        dig = dep.get("digest")
        if not isinstance(ref, str) or not isinstance(dig, dict):
            continue
        if ref.startswith("path:") and ref not in resolved_refs:
            rel = ref.removeprefix("path:")
            abs_path = None
            for root_key in paths_config["search_order"]:
                root_abs = roots_trace.get(f"{root_key}_abs_or_null")
                if isinstance(root_abs, str) and root_abs:
                    candidate = Path(root_abs) / rel
                    if candidate.exists():
                        abs_path = candidate.resolve()
                        break
            if abs_path is None:
                abs_path = (Path(__file__).resolve().parents[2] / rel).resolve()
            resolved_list.append(
                {
                    "artifact_ref": ref,
                    "abs_path_or_null": str(abs_path),
                    "digest": dig,
                    "resolved_ok": abs_path.exists(),
                    "error_or_null": None if abs_path.exists() else "PATH_NOT_FOUND",
                }
            )
            resolved_refs.add(ref)
    paths_trace["resolved_artifacts"] = resolved_list


def _build_seat_policies(
    *,
    seats: list[int],
    seed: int,
    opponent_suite_ref: str,
    system_policy_fn: Any,
    strong_rule_bots: bool,
    ruleset: dict[str, Any],
    paths_trace: dict[str, Any],
    paths_config: dict[str, Any],
) -> tuple[dict[int, Any], dict[int, dict[str, Any]]]:
    seat_policies: dict[int, Any] = {}
    seat_meta: dict[int, dict[str, Any]] = {}
    seat_policies[seats[0]] = system_policy_fn
    seat_meta[seats[0]] = {"role": "system_bot", "style": "blueprint", "aggression": None}

    opp_reg = build_opponent_registry(strict_mode=True)
    suite_entry, _ = resolve_opponent_suite_ref(opponent_suite_ref, registry=opp_reg, strict_mode=True)
    suite_path = Path(str(suite_entry["opponent_suite_ref"]).removeprefix("path:"))
    suite_spec = json.loads(suite_path.read_text())
    opponents = suite_spec.get("opponents") or []
    for seat, opp_ref in zip(seats[1:], opponents):
        ref = opp_ref.get("opponent_ref") if isinstance(opp_ref, dict) else None
        if not isinstance(ref, str):
            raise ValueError("opponent_ref missing in suite")
        opp_path = Path(ref.removeprefix("path:"))
        opp_spec = json.loads(opp_path.read_text())
        params = opp_spec.get("params", {})
        kind = opp_spec.get("opponent_kind")
        if kind == "system_policy":
            policy_ref = params.get("policy_ref")
            if not isinstance(policy_ref, str) or not policy_ref.startswith("path:"):
                raise ValueError("system_policy opponent requires params.policy_ref path:")
            pol_path = Path(policy_ref.removeprefix("path:"))
            pol_spec = load_policy_spec(pol_path)
            _ensure_policy_deps_in_paths_trace(policy_spec=pol_spec, paths_trace=paths_trace, paths_config=paths_config)
            opp_policy_fn, opp_meta = build_system_policy(
                seat_id=seat,
                seed=seed,
                policy_spec=pol_spec,
                ruleset=ruleset,
                paths_trace=paths_trace,
                strict_mode=True,
            )
            seat_policies[seat] = opp_policy_fn
            seat_meta[seat] = {
                "role": "system_bot_opponent",
                "style": params.get("style"),
                "policy_id": opp_meta.get("policy_id"),
            }
        else:
            style = params.get("style", "balanced")
            aggression = float(params.get("aggression", 0.5))
            if strong_rule_bots:
                aggression = min(1.0, max(aggression, 0.5))
            seat_policies[seat] = make_rule_policy(style=style, aggression=aggression, seat_id=seat, seed=seed)
            seat_meta[seat] = {"role": "rule_bot", "style": style, "aggression": aggression}
    return seat_policies, seat_meta


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="coinpoker_7max_mw_v3_actionspace_v2")
    p.add_argument("--profile", default="internal_profile_v1")
    p.add_argument("--policy", default="system_bot_policy_v3")
    p.add_argument("--opponents", default="system_bot_league_7max_frozen_v1")
    p.add_argument("--settings", type=Path, default=None, help="HRC settings.json; overrides scenario ruleset")
    p.add_argument("--rounding-mode", choices=ROUNDING_MODE_VALUES, default=None, help="Required when --settings is used")
    p.add_argument(
        "--reopen-on-short-allin",
        dest="reopen_on_short_allin",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Required when --settings is used",
    )
    p.add_argument("--hands", type=int, default=200)
    p.add_argument("--seed", type=int, default=2000)
    p.add_argument("--button-seat", type=int, default=1)
    p.add_argument("--starting-stacks-by-seat", dest="stacks", default=None, help='JSON object, e.g. {"1":10000,...}')
    p.add_argument("--paths-config", type=Path, default=None)
    p.add_argument("--hrc-root", type=Path, default=Path("/Users/peng/Documents/Hand2"))
    default_solver_root = Path(__file__).resolve().parents[1] / "engines" / "postflop_pyo3" / "rs"
    p.add_argument("--postflop-solver-root", type=Path, default=default_solver_root)
    p.add_argument("--strong-rule-bots", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args(argv)

    starting_stacks = _parse_stacks(args.stacks)
    seats = sorted(starting_stacks.keys())

    use_hrc = args.settings is not None

    action_adapter, action_adapter_id = default_internal_action_adapter(strict_mode=True)
    # action_bins will be resolved after loading scenario/closure (below); initialize with defaults.
    action_bins, action_bins_id = default_internal_action_bins(strict_mode=True)
    mw_ladder_default = default_internal_mw_ladder(strict_mode=True)[1]
    obs_schema_id = placeholder_id("obs_schema_placeholder_v1", strict_mode=True)
    # Preload mapping spec (treepath) for abstraction + policy.
    mapping_spec, mapping_spec_id = default_internal_treepath_mapping_spec(strict_mode=True)

    prof_registry = build_profile_registry(strict_mode=True)
    prof_entry, _ = resolve_profile_ref(args.profile, registry=prof_registry, strict_mode=True)
    prof_spec = load_profile_spec(Path(str(prof_entry["profile_spec_ref"]).removeprefix("path:")))
    prof_id = profile_id(prof_spec, strict_mode=True)

    pol_registry = build_policy_registry(strict_mode=True)
    pol_entry, _ = resolve_policy_ref(args.policy, registry=pol_registry, strict_mode=True)
    pol_spec = load_policy_spec(Path(str(pol_entry["policy_spec_ref"]).removeprefix("path:")))
    pol_id = policy_id(pol_spec, strict_mode=True)

    paths_config = default_paths_config(strict_mode=True)
    if args.paths_config:
        paths_config = json.loads(args.paths_config.read_text())
    roots = paths_config.get("roots", {})
    if args.postflop_solver_root:
        roots["postflop_solver_src_root"] = str(args.postflop_solver_root)
    if use_hrc:
        roots["hrc_root"] = str(args.hrc_root)
    paths_config["roots"] = roots
    search_order = list(paths_config.get("search_order", []))
    for opt in (use_hrc and "hrc_root" or None, "postflop_solver_src_root"):
        if opt and opt not in search_order:
            search_order.append(opt)
    # deduplicate while preserving order
    seen: set[str] = set()
    deduped = []
    for key in search_order:
        if key in seen or key is None:
            continue
        seen.add(key)
        deduped.append(key)
    paths_config["search_order"] = deduped
    validate_paths_config(paths_config, strict_mode=True)

    if use_hrc:
        if args.rounding_mode is None or args.reopen_on_short_allin is None:
            raise ValueError("--rounding-mode and --reopen-on-short-allin are required when --settings is provided")
        ruleset_out = import_ruleset_from_hrc_settings(
            args.settings,
            rounding_mode=args.rounding_mode,
            reopen_on_short_allin=args.reopen_on_short_allin,
            paths_config=paths_config,
        )
        ruleset = ruleset_out["ruleset"]
        validate_ruleset(ruleset, strict_mode=True)
        ruleset_id_hex = ruleset_out["ruleset_id"]
        rake_id = ruleset_rake_id(ruleset, strict_mode=True)
        triad = {"action_bins_id": action_bins_id, "obs_schema_id": obs_schema_id, "rake_id": rake_id}
        schema_hash_val = schema_hash(strict_mode=True)
        abs_hash = abstraction_hash(
            action_bins_id=action_bins_id,
            action_adapter_id=action_adapter_id,
            mapping_spec_id=mapping_spec_id,
            strict_mode=True,
        )
        settings_abs = Path(ruleset_out["source_ref"]).resolve()
        try:
            rel_settings = settings_abs.relative_to(args.hrc_root.resolve()).as_posix()
        except Exception:
            rel_settings = settings_abs.name
        preflop_ref = {"artifact_ref": f"path:{rel_settings}", "digest": ruleset_out["source_digest"]}
        postflop_dep = next(
            (d for d in pol_spec.get("policy_deps", []) if isinstance(d, dict) and str(d.get("artifact_ref", "")).startswith("artifact://")),
            None,
        )
        closure = {
            "scenario_schema_id": "scenario_spec_v1",
            "ruleset_id": ruleset_id_hex,
            "triad": triad,
            "schema_hash": schema_hash_val,
            "abstraction_hash": abs_hash,
            "preflop_ref": preflop_ref,
            "postflop_ref": postflop_dep,
            "opponent_suite_id": None,
            "population_id": None,
            "mw_ladder_id": mw_ladder_default,
        }
        scenario_id_hex = compute_scenario_id(closure, strict_mode=True)
        resolved_paths, resolved_paths_digest, paths_trace = resolve_paths(
            paths_config=paths_config, scenario_package_closure=closure, strict_mode=True
        )
    else:
        scenario_path = Path("specs/scenarios") / f"{args.scenario}.json"
        scenario_pkg = load_scenario_package(scenario_path)
        validate_scenario_package(scenario_pkg, strict_mode=True)
        closure = scenario_closure_from_package(scenario_pkg, strict_mode=True)
        scenario_id_hex = compute_scenario_id(closure, strict_mode=True)
        resolved_paths, resolved_paths_digest, paths_trace = resolve_paths(
            paths_config=paths_config, scenario_package_closure=closure, strict_mode=True
        )
        ruleset = _load_ruleset_by_id(closure["ruleset_id"])

    # Align action_bins with scenario triad if available
    try:
        triad_bins_id = closure.get("triad", {}).get("action_bins_id")
        if isinstance(triad_bins_id, str):
            action_bins = _load_action_bins_by_id(triad_bins_id)
            action_bins_id = triad_bins_id
    except Exception:
        pass

    # Guard: triad.action_bins_id must match the loaded action_bins_id (single source of truth).
    triad_bins = closure.get("triad", {}).get("action_bins_id")
    if triad_bins and triad_bins != action_bins_id:
        raise ValueError(f"triad.action_bins_id mismatch: triad={triad_bins}, loaded={action_bins_id}")

    abs_expected = abstraction_hash(
        action_bins_id=action_bins_id,
        action_adapter_id=action_adapter_id,
        mapping_spec_id=mapping_spec_id,
        strict_mode=True,
    )
    abs_declared = closure.get("abstraction_hash")
    if abs_declared is not None and abs_declared != abs_expected:
        raise ValueError(f"abstraction_hash mismatch: declared={abs_declared} expected={abs_expected}")

    # Ensure policy deps that use path: are present in paths_trace.resolved_artifacts
    # so build_system_policy can resolve them (resolve_paths only covers scenario assets).
    _ensure_policy_deps_in_paths_trace(policy_spec=pol_spec, paths_trace=paths_trace, paths_config=paths_config)

    solver_build_id: str | None = None
    if closure.get("postflop_ref") is not None:
        try:
            solver_root = postflop_solver_src_root_from_paths_trace(paths_trace)
            solver_build_id = compute_postflop_solver_build_id(src_root=solver_root, strict_mode=True)
        except Exception:
            solver_build_id = None

    system_policy_fn, system_meta = build_system_policy(
        seat_id=seats[0],
        seed=args.seed,
        policy_spec=pol_spec,
        ruleset=ruleset,
        paths_trace=paths_trace,
        strict_mode=True,
    )
    if solver_build_id is None:
        solver_build_id = system_meta.get("solver_build_id")

    run_closure = {
        "scenario_id": scenario_id_hex,
        "ruleset_id": closure["ruleset_id"],
        "triad": closure["triad"],
        "schema_hash": closure["schema_hash"],
        "resolved_paths_digest": resolved_paths_digest,
        "abstraction_hash": closure["abstraction_hash"],
        "policy_id": pol_id,
        "profile_id": prof_id,
        "opponent_suite_id": closure.get("opponent_suite_id"),
        "opponent_artifact_id_or_params_hash": None,
        "mw_ladder_id": closure.get("mw_ladder_id"),
        "belief_spec_id": None,
        "mw_risk_spec_id": None,
        "adaptation_digest": None,
        "engine_build_id": None,
        "solver_build_id": solver_build_id,
        "pokerkit_version": None,
        "strict_mode": True,
    }
    options_hash = compute_options_hash(run_closure, strict_mode=True)
    run_id = run_id_v1(options_hash=options_hash, seed=args.seed, strict_mode=True)

    seat_policies, seat_meta = _build_seat_policies(
        seats=seats,
        seed=args.seed,
        opponent_suite_ref=args.opponents,
        system_policy_fn=system_policy_fn,
        strong_rule_bots=bool(args.strong_rule_bots),
        ruleset=ruleset,
        paths_trace=paths_trace,
        paths_config=paths_config,
    )

    prov_env = build_provenance_envelope_v1(
        ruleset_id=closure["ruleset_id"],
        triad=closure["triad"],
        schema_hash=closure["schema_hash"],
        options_hash=options_hash,
        seed=args.seed,
        action_adapter_id=action_adapter_id,
        mapping_spec_id=mapping_spec_id,
        mw_ladder_id=closure.get("mw_ladder_id"),
        pokerkit_version=None,
        engine_build_id=None,
        solver_build_id=solver_build_id,
        rng_lineage_id=None,
        seed_derivation_digest=None,
        repro_tier="Tier-A",
    )
    prov_id = provenance_id(prov_env, strict_mode=True)
    prov_ref = f"artifact://{prov_id}"
    write_artifact_json(prov_env, artifact_id=prov_id, strict_mode=True)

    objs = run_multi_hand_eventstream_objects(
        run_id=run_id,
        options_hash=options_hash,
        seed=args.seed,
        scenario_id=scenario_id_hex,
        schema_hash=closure["schema_hash"],
        provenance_ref=prov_ref,
        resolved_paths_digest=resolved_paths_digest,
        repro_tier="Tier-A",
        ruleset=ruleset,
        triad=closure["triad"],
        action_adapter=action_adapter,
        action_bins=action_bins,
        mapping_spec_id=mapping_spec_id,
        mw_ladder_id=closure.get("mw_ladder_id"),
        starting_stacks_by_seat=starting_stacks,
        button_seat=args.button_seat,
        hands=args.hands,
        opponent_suite_id=closure.get("opponent_suite_id"),
        seat_policies=seat_policies,
        policy=system_policy_fn,
        system_seat_id=seats[0],
        strict_mode=True,
    )

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ev_path = out_dir / "scrimmage_eventstream.ndjson"
    ev_path.write_text("\n".join(json.dumps(o, ensure_ascii=False, separators=(",", ":")) for o in objs) + "\n", encoding="utf-8")

    # Aggregate winnings from HandEnd events.
    delta_by_seat: dict[int, int] = {s: 0 for s in seats}
    hands_played = 0
    total_rake = 0
    model_hand_wins = 0
    model_hand_ties = 0
    for e in objs:
        if isinstance(e, dict) and e.get("event") == "HandEnd":
            hands_played += 1
            total_rake += int(e.get("total_rake_chips", 0) or 0)
            for s_str, delta in e.get("stack_deltas_by_seat", {}).items():
                s = int(s_str)
                delta_by_seat[s] = delta_by_seat.get(s, 0) + int(delta)
            delta_model = e.get("stack_deltas_by_seat", {}).get(str(seats[0]), 0)
            if delta_model > 0:
                model_hand_wins += 1
            elif delta_model == 0:
                model_hand_ties += 1

    bb = ruleset["blinds"]["bb_chips"]
    # Map (decision_id, state_hash) -> street for action mix.
    decision_meta: dict[tuple[int, str], tuple[str | None, int | None]] = {}
    for e in objs:
        if isinstance(e, dict) and e.get("event") == "DecisionPoint":
            key = _decision_key(e)
            street = (e.get("snapshot_payload") or {}).get("street")
            actor_seat = (e.get("snapshot_payload") or {}).get("actor_seat")
            if key is not None:
                decision_meta[key] = (street if isinstance(street, str) else None, actor_seat if isinstance(actor_seat, int) else None)
    action_records: list[dict[str, Any]] = []
    for e in objs:
        if isinstance(e, dict) and e.get("event") == "ActionChosen":
            key = _decision_key(e)
            street, actor_seat = decision_meta.get(key, (None, None))
            kind = (e.get("executed_action") or {}).get("kind")
            derived = e.get("derived_action") or {}
            if derived.get("is_allin"):
                kind = "ALLIN"
            action_records.append(
                {
                    "seat": actor_seat,
                    "kind": kind,
                    "street": street,
                }
            )
    analysis = _analyze_events(objs=objs, model_seat=seats[0], bb=bb, ruleset=ruleset, seats_count=len(seats))

    event_stream_digest = None
    if objs and isinstance(objs[0], dict):
        event_stream_digest = objs[0].get("event_stream_digest")

    report_ref = f"path:{(out_dir / 'scrimmage_report.json').resolve()}"
    baseline = {
        "policy_id": pol_id,
        "scenario_id": scenario_id_hex,
        "opponent_suite_id": closure.get("opponent_suite_id"),
        "actionspace_id": action_bins_id,
        "run_id": run_id,
        "options_hash": options_hash,
        "event_stream_digest": event_stream_digest,
        "report_ref": report_ref,
    }

    report = {
        "status": "pass",
        "run_id": run_id,
        "options_hash": options_hash,
        "event_stream_digest": event_stream_digest,
        "hands": hands_played,
        "bb_chips": bb,
        "seat_results": [
            {
                "seat": s,
                "role": (seat_meta.get(s) or {}).get("role") or ("system_bot" if s == seats[0] else "rule_bot"),
                "chips": delta_by_seat[s],
                "bb_per_100": (delta_by_seat[s] / bb) * (100.0 / max(1, hands_played)),
            }
            for s in seats
        ],
        "total_rake_chips": total_rake,
        "scene": {
            "ruleset_id": closure["ruleset_id"],
            "scenario_id": scenario_id_hex,
            "abstraction_hash": closure["abstraction_hash"],
            "schema_hash": closure["schema_hash"],
            "triad": closure["triad"],
            "action_bins_id": action_bins_id,
            "action_bins": {
                "bet_bins": _bet_bins_from_spec(action_bins),
                "raise_bins": _raise_bins_from_spec(action_bins),
            },
            "mapping_spec_id": mapping_spec_id,
            "rake": ruleset.get("rake"),
            "min_raise_rule": ruleset.get("min_raise_rule"),
            "blinds": ruleset.get("blinds"),
            "ante": ruleset.get("ante"),
            "straddle": ruleset.get("straddle"),
            "seed": args.seed,
            "button_seat": args.button_seat,
            "starting_stacks_by_seat": starting_stacks,
            "resolved_paths_digest": resolved_paths_digest,
            "adaptation_digest": None,
            "bench_overrides": None,
            "paths_config_roots": paths_config.get("roots"),
            "settings_ref": str(args.settings) if use_hrc else None,
        },
        "event_stream_ref": f"path:{ev_path}",
        "report_ref": report_ref,
        "analysis": analysis,
        "baseline": baseline,
    }

    views_builder = ScrimmageReportViews(report)
    views = views_builder.build()
    report["report_index"] = views.get("index") or {}
    iteration_protocol = build_iteration_protocol(report)
    report["iteration_protocol"] = iteration_protocol
    protocol_errors = validate_iteration_protocol(iteration_protocol, strict=False)
    report["iteration_protocol_errors"] = protocol_errors

    (out_dir / "scrimmage_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "scrimmage_views.json").write_text(json.dumps(views, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "scrimmage_views.txt").write_text(views_builder.render_text(), encoding="utf-8")
    analyzer = ScrimmageReportAnalyzer(report)
    insights = analyzer.to_structured(min_severity="low", include_tables=True)
    (out_dir / "scrimmage_insights.json").write_text(json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")
    text_report = _render_text_report(
        ruleset=ruleset,
        action_bins=action_bins,
        seats=seats,
        hands=hands_played,
        seat_results=delta_by_seat,
        total_rake_chips=total_rake,
        model_wins=model_hand_wins,
        model_ties=model_hand_ties,
        dp_info={},  # simplified
        actions=action_records,
        analysis=analysis,
        seat_meta=seat_meta,
        iteration_protocol=iteration_protocol,
    )
    (out_dir / "scrimmage_report.txt").write_text(text_report, encoding="utf-8")
    if protocol_errors:
        raise ValueError(f"Iteration protocol validation failed: {protocol_errors}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n" + text_report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
