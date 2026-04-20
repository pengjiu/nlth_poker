from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from poker2.cli.hrc_nodes import action_amount, action_kinds, canonical_action_kind, iter_hands, played_by_index, values_by_index
from poker2.protocol.preflop_ranges import (
    build_nodes_manifest,
    preflop_scenario,
    size_bucket_from_amount,
    size_ratio_x100,
    validate_preflop_ranges,
)


def _seat_to_pos(seat: int) -> str:
    # Hand2/HRC export uses seats: 0=UTG,1=UTG+1,2=MP,3=CO,4=BU,5=SB,6=BB.
    if seat == 4:
        return "BU"
    if seat == 5:
        return "SB"
    if seat == 6:
        return "BB"
    return "OTHERS"


def _classify_node(node: dict[str, Any]) -> tuple[str, str | None] | None:
    if int(node.get("street", -1)) != 0:
        return None
    seq = node.get("sequence") or []
    if not isinstance(seq, list):
        return None
    raise_actions: list[dict[str, Any]] = []
    call_seen = False
    for act in seq:
        kind = canonical_action_kind(act)
        if kind == "raise" and isinstance(act, dict):
            raise_actions.append(act)
        elif kind == "call":
            call_seen = True
    raise_count = len(raise_actions)
    if raise_count == 0:
        # Only pure fold sequence treated as first-in open.
        for act in seq:
            kind = canonical_action_kind(act)
            if kind not in (None, "fold"):
                return None
        if call_seen:
            return None
        return ("OPEN", None)
    if raise_count == 1:
        opener = raise_actions[0].get("player")
        if isinstance(opener, bool) or not isinstance(opener, int):
            return None
        return ("VS_OPEN", _seat_to_pos(opener))
    return None


def _sanitize_metric_name(name: str) -> str:
    cleaned = "".join(ch if ("a" <= ch <= "z" or "0" <= ch <= "9" or ch == "_") else "_" for ch in name.lower())
    cleaned = cleaned.strip("_")
    return cleaned or "metric"


def _metric_prefix(name: str) -> str:
    lowered = name.lower()
    if lowered in ("evs", "ev", "ev_bb", "ev_chips"):
        return "ev"
    if lowered in ("eqs", "equity", "eq"):
        return "eq"
    if lowered in ("icm", "icm_ev"):
        return "icm"
    return f"hrc_{_sanitize_metric_name(lowered)}"


def _scalar_key(name: str) -> str:
    lowered = _sanitize_metric_name(name)
    if lowered in ("raise", "call", "fold") or lowered.endswith("_raise") or lowered.endswith("_call") or lowered.endswith("_fold"):
        lowered = f"{lowered}_scalar"
    if name == "weight":
        return "weight"
    return f"hrc_{lowered}"


def _extract_hand_probs(node: dict[str, Any]) -> dict[str, tuple[float, float, float]]:
    stats = _extract_hand_stats(node)
    out: dict[str, tuple[float, float, float]] = {}
    for hand, info in stats.items():
        p_raise = float(info.get("raise", 0.0) or 0.0)
        p_call = float(info.get("call", 0.0) or 0.0)
        p_fold = float(info.get("fold", 0.0) or 0.0)
        out[hand] = (p_raise, p_call, p_fold)
    return out


def _extract_hand_stats(node: dict[str, Any]) -> dict[str, dict[str, float]]:
    actions = node.get("actions") or []
    kinds = action_kinds(actions)
    if not kinds:
        return {}
    hands = node.get("hands") or {}
    out: dict[str, dict[str, float]] = {}
    for hand, info in iter_hands(hands):
        probs = played_by_index(info, kinds)
        if not probs:
            continue
        p_raise = 0.0
        p_call = 0.0
        p_fold = 0.0
        unknown_mass = 0.0
        for idx, prob in enumerate(probs):
            try:
                p = float(prob)
            except Exception:
                continue
            kind = kinds[idx]
            if kind == "raise":
                p_raise += p
            elif kind == "call":
                p_call += p
            elif kind == "fold":
                p_fold += p
            else:
                unknown_mass += p
        total = p_raise + p_call + p_fold
        if total <= 0:
            continue
        inv = 1.0 / total
        p_raise *= inv
        p_call *= inv
        p_fold *= inv
        probs_scaled = [float(p) * inv if kinds[i] in ("raise", "call", "fold") else 0.0 for i, p in enumerate(probs)]
        stats: dict[str, float] = {
            "raise": p_raise,
            "call": p_call,
            "fold": p_fold,
        }
        if unknown_mass > 0:
            stats["hrc_unknown_prob"] = float(unknown_mass)
        for key, val in info.items():
            if key in ("played", "strategy", "strat"):
                continue
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                stats[_scalar_key(key)] = float(val)
                continue
            values = values_by_index(val, kinds)
            if values is None:
                continue
            metric = _metric_prefix(key)
            sums = {"raise": 0.0, "call": 0.0, "fold": 0.0}
            weights = {"raise": 0.0, "call": 0.0, "fold": 0.0}
            for idx, mval in enumerate(values):
                if mval is None:
                    continue
                kind = kinds[idx]
                if kind not in ("raise", "call", "fold"):
                    continue
                p = probs_scaled[idx]
                if p <= 0:
                    continue
                sums[kind] += float(mval) * p
                weights[kind] += p
            for kind in ("raise", "call", "fold"):
                w = weights[kind]
                if w > 0:
                    stats[f"{metric}_{kind}"] = sums[kind] / w
        out[hand] = stats
    return out


def _accumulate_hand_stats(acc_map: dict[str, dict[str, Any]], hand_stats: dict[str, dict[str, float]]) -> None:
    for hand, stats in hand_stats.items():
        entry = acc_map.setdefault(
            hand,
            {
                "count": 0.0,
                "p_raise": 0.0,
                "p_call": 0.0,
                "p_fold": 0.0,
                "metric_sums": {},
                "metric_weights": {},
                "scalar_sums": {},
            },
        )
        try:
            p_raise = float(stats.get("raise", 0.0) or 0.0)
            p_call = float(stats.get("call", 0.0) or 0.0)
            p_fold = float(stats.get("fold", 0.0) or 0.0)
        except Exception:
            continue
        entry["count"] += 1.0
        entry["p_raise"] += p_raise
        entry["p_call"] += p_call
        entry["p_fold"] += p_fold
        metric_sums = entry["metric_sums"]
        metric_weights = entry["metric_weights"]
        scalar_sums = entry["scalar_sums"]
        for key, val in stats.items():
            if key in ("raise", "call", "fold"):
                continue
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                continue
            weight = None
            if key.endswith("_raise"):
                weight = p_raise
            elif key.endswith("_call"):
                weight = p_call
            elif key.endswith("_fold"):
                weight = p_fold
            if weight is None:
                scalar_sums[key] = float(scalar_sums.get(key, 0.0)) + float(val)
                continue
            metric_sums[key] = float(metric_sums.get(key, 0.0)) + float(val) * float(weight)
            metric_weights[key] = float(metric_weights.get(key, 0.0)) + float(weight)


def _load_settings(settings_path: Path | None) -> tuple[int | None, int | None, int | None, int | None]:
    if settings_path is None or not settings_path.exists():
        return None, None, None, None
    try:
        doc = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None, None, None
    handdata = doc.get("handdata", {}) if isinstance(doc, dict) else {}
    stacks = handdata.get("stacks") if isinstance(handdata, dict) else None
    blinds = handdata.get("blinds") if isinstance(handdata, dict) else None
    players = len(stacks) if isinstance(stacks, list) else None
    bb = None
    sb = None
    ante = None
    if isinstance(blinds, list) and blinds:
        try:
            bb = int(blinds[0])
        except Exception:
            bb = None
        if len(blinds) > 1:
            try:
                sb = int(blinds[1])
            except Exception:
                sb = None
        if len(blinds) > 2:
            try:
                ante = int(blinds[2])
            except Exception:
                ante = None
    return bb, sb, ante, players


def _raise_amounts_from_actions(actions: Any) -> list[int]:
    if not isinstance(actions, list):
        return []
    amounts: list[int] = []
    for act in actions:
        if canonical_action_kind(act) != "raise":
            continue
        amt = action_amount(act)
        if isinstance(amt, bool) or not isinstance(amt, (int, float)):
            continue
        amounts.append(int(amt))
    return amounts


def _action_player(action: Any) -> int | None:
    if not isinstance(action, dict):
        return None
    player = action.get("player")
    if isinstance(player, bool) or not isinstance(player, int):
        return None
    return player


def _analyze_sequence(seq: Any) -> tuple[int, int, int | None, int | None, int, int]:
    if not isinstance(seq, list):
        return 0, 0, None, None, 0, 0
    raise_actions: list[Any] = []
    call_actions: list[Any] = []
    for act in seq:
        kind = canonical_action_kind(act)
        if kind == "raise":
            raise_actions.append(act)
        elif kind == "call":
            call_actions.append(act)
    raise_count = len(raise_actions)
    call_count = len(call_actions)
    opener = _action_player(raise_actions[0]) if raise_count > 0 else None
    last_raiser = _action_player(raise_actions[-1]) if raise_count > 0 else None
    last_raise_amount = action_amount(raise_actions[-1]) if raise_count > 0 else None
    last_raise_amount = int(last_raise_amount) if isinstance(last_raise_amount, (int, float)) else None
    last_raise_idx = None
    if raise_count > 0:
        for idx, act in enumerate(seq):
            if canonical_action_kind(act) == "raise":
                last_raise_idx = idx
    callers_after = 0
    if last_raise_idx is not None:
        for act in seq[last_raise_idx + 1 :]:
            if canonical_action_kind(act) == "call":
                callers_after += 1
    return raise_count, call_count, opener if isinstance(opener, int) else None, last_raiser if isinstance(last_raiser, int) else None, callers_after, last_raise_amount or 0


def build_preflop_ranges_from_nodes(nodes_dir: Path, *, manifest_ref: str, manifest_digest: dict[str, str]) -> dict[str, Any]:
    node_files = sorted(nodes_dir.glob("*.json"), key=lambda p: p.name)
    if not node_files:
        raise ValueError(f"no nodes found under {nodes_dir}")

    # Accumulators: scenario -> pos -> opener -> hand -> (sum_raise, sum_call, sum_fold, count)
    acc: dict[str, dict[str, dict[str, dict[str, list[float]]]]] = {}

    for path in node_files:
        node = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(node, dict):
            continue
        player = node.get("player")
        if isinstance(player, bool) or not isinstance(player, int):
            continue
        scenario = _classify_node(node)
        if scenario is None:
            continue
        scenario_key, opener_pos = scenario
        if scenario_key == "VS_OPEN":
            seq = node.get("sequence") or []
            if isinstance(seq, list) and seq:
                opener = None
                for act in seq:
                    if canonical_action_kind(act) == "raise":
                        opener = _action_player(act)
                        break
                if opener is not None and opener == player:
                    continue
        pos_key = _seat_to_pos(player)
        hand_probs = _extract_hand_probs(node)
        if not hand_probs:
            continue

        opener_key = opener_pos if opener_pos is not None else "ANY"
        scenario_map = acc.setdefault(scenario_key, {})
        pos_map = scenario_map.setdefault(pos_key, {})
        opener_map = pos_map.setdefault(opener_key, {})
        for hand, (p_raise, p_call, p_fold) in hand_probs.items():
            entry = opener_map.setdefault(hand, [0.0, 0.0, 0.0, 0.0])
            entry[0] += p_raise
            entry[1] += p_call
            entry[2] += p_fold
            entry[3] += 1.0

    scenarios: dict[str, Any] = {}
    for scenario_key, scenario_map in acc.items():
        if scenario_key == "OPEN":
            out_pos: dict[str, Any] = {}
            for pos_key, opener_map in scenario_map.items():
                hand_map = opener_map.get("ANY", {})
                hands_out: dict[str, dict[str, float]] = {}
                for hand, stats in hand_map.items():
                    if stats[3] <= 0:
                        continue
                    inv = 1.0 / stats[3]
                    hands_out[hand] = {
                        "raise": float(stats[0] * inv),
                        "call": float(stats[1] * inv),
                        "fold": float(stats[2] * inv),
                    }
                out_pos[pos_key] = {"hands": hands_out}
            scenarios[scenario_key] = out_pos
        else:
            out_pos: dict[str, Any] = {}
            for pos_key, opener_map in scenario_map.items():
                opener_out: dict[str, Any] = {}
                for opener_key, hand_map in opener_map.items():
                    hands_out: dict[str, dict[str, float]] = {}
                    for hand, stats in hand_map.items():
                        if stats[3] <= 0:
                            continue
                        inv = 1.0 / stats[3]
                        hands_out[hand] = {
                            "raise": float(stats[0] * inv),
                            "call": float(stats[1] * inv),
                            "fold": float(stats[2] * inv),
                        }
                    opener_out[opener_key] = {"hands": hands_out}
                out_pos[pos_key] = opener_out
            scenarios[scenario_key] = out_pos

    out = {
        "schema_id": "preflop_ranges_v2",
        "source": "hrc_nodes_manifest_v1",
        "manifest_ref": manifest_ref,
        "manifest_digest": manifest_digest,
        "node_count": len(node_files),
        "scenarios": scenarios,
    }
    validate_preflop_ranges(out, strict_mode=True)
    return out


def build_preflop_ranges_v3_from_nodes(
    nodes_dir: Path,
    *,
    manifest_ref: str,
    manifest_digest: dict[str, str],
    settings_path: Path | None,
) -> dict[str, Any]:
    node_files = sorted(nodes_dir.glob("*.json"), key=lambda p: p.name)
    if not node_files:
        raise ValueError(f"no nodes found under {nodes_dir}")

    bb, sb, ante, players = _load_settings(settings_path)

    key_fields = [
        "scenario",
        "actor_pos",
        "last_raiser_pos",
        "raise_count",
        "size_bucket",
        "has_caller",
        "callers",
        "players",
    ]

    acc: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
    meta: dict[tuple[Any, ...], dict[str, Any]] = {}

    for path in node_files:
        node = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(node, dict):
            continue
        if int(node.get("street", -1)) != 0:
            continue
        player = node.get("player")
        if isinstance(player, bool) or not isinstance(player, int):
            continue
        pos_key = _seat_to_pos(player)

        seq = node.get("sequence") or []
        raise_count, call_count, opener, last_raiser, callers_after, last_raise_amt = _analyze_sequence(seq)
        facing = raise_count > 0
        scenario = preflop_scenario(raise_count=raise_count, has_caller=callers_after > 0 or call_count > 0, facing=facing)
        if scenario is None:
            continue
        if scenario == "VS_OPEN" and opener == player:
            continue

        actions = node.get("actions") or []
        raise_amounts = _raise_amounts_from_actions(actions)
        open_amt = None
        if raise_count == 0:
            if len(set(raise_amounts)) == 1:
                open_amt = raise_amounts[0]
        else:
            if opener is not None:
                for act in seq:
                    if canonical_action_kind(act) == "raise":
                        amt = action_amount(act)
                        if isinstance(amt, (int, float)):
                            open_amt = int(amt)
                        break

        size_bucket = None
        open_bucket = None
        size_x100 = None
        open_x100 = None
        if bb:
            if last_raise_amt:
                size_bucket = size_bucket_from_amount(int(last_raise_amt), bb)
                size_x100 = size_ratio_x100(int(last_raise_amt), bb)
            if open_amt:
                open_bucket = size_bucket_from_amount(int(open_amt), bb)
                open_x100 = size_ratio_x100(int(open_amt), bb)

        last_raiser_pos = _seat_to_pos(last_raiser) if last_raiser is not None else None
        has_caller = callers_after > 0 if raise_count > 0 else call_count > 0
        callers = callers_after if raise_count > 0 else call_count

        key = {
            "scenario": scenario,
            "actor_pos": pos_key,
            "last_raiser_pos": last_raiser_pos,
            "raise_count": int(raise_count),
            "size_bucket": size_bucket,
            "has_caller": bool(has_caller),
            "callers": int(callers),
            "players": int(players) if isinstance(players, int) else None,
        }
        key_tuple = tuple(key.get(field) for field in key_fields)

        hand_stats = _extract_hand_stats(node)
        if not hand_stats:
            continue

        meta.setdefault(
            key_tuple,
            {
                "open_size_bucket": open_bucket,
                "open_size_x100": open_x100,
                "face_size_x100": size_x100,
                "bb": bb,
                "sb": sb,
                "ante": ante,
            },
        )

        acc_map = acc.setdefault(key_tuple, {})
        _accumulate_hand_stats(acc_map, hand_stats)

    entries: list[dict[str, Any]] = []
    for key_tuple, hand_map in acc.items():
        hands_out: dict[str, dict[str, float]] = {}
        for hand, stats in hand_map.items():
            count = float(stats.get("count", 0.0) or 0.0)
            if count <= 0:
                continue
            inv = 1.0 / count
            entry = {
                "raise": float(stats.get("p_raise", 0.0) or 0.0) * inv,
                "call": float(stats.get("p_call", 0.0) or 0.0) * inv,
                "fold": float(stats.get("p_fold", 0.0) or 0.0) * inv,
            }
            for key, scalar_sum in (stats.get("scalar_sums") or {}).items():
                if isinstance(scalar_sum, (int, float)) and not isinstance(scalar_sum, bool):
                    entry[key] = float(scalar_sum) * inv
            metric_sums = stats.get("metric_sums") or {}
            metric_weights = stats.get("metric_weights") or {}
            for key, metric_sum in metric_sums.items():
                if not isinstance(metric_sum, (int, float)) or isinstance(metric_sum, bool):
                    continue
                w = metric_weights.get(key)
                if isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0:
                    entry[key] = float(metric_sum) / float(w)
            hands_out[hand] = entry
        key = {field: key_tuple[idx] for idx, field in enumerate(key_fields)}
        entry = {"key": key, "hands": hands_out}
        meta_entry = meta.get(key_tuple)
        if meta_entry:
            entry["meta"] = meta_entry
        entries.append(entry)

    entries.sort(key=lambda e: json.dumps(e.get("key", {}), sort_keys=True))
    out = {
        "schema_id": "preflop_ranges_v3",
        "source": "hrc_nodes_manifest_v1",
        "manifest_ref": manifest_ref,
        "manifest_digest": manifest_digest,
        "node_count": len(node_files),
        "key_fields": key_fields,
        "entries": entries,
    }
    validate_preflop_ranges(out, strict_mode=True)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Build preflop_ranges from HRC nodes.")
    p.add_argument("--nodes-dir", type=Path, required=True)
    p.add_argument("--out-manifest", type=Path, required=True)
    p.add_argument("--out-ranges", type=Path, required=True)
    p.add_argument("--manifest-ref", type=str, required=True)
    p.add_argument("--schema", type=str, choices=["v2", "v3"], default="v3")
    p.add_argument("--settings", type=Path, default=None)
    args = p.parse_args()

    nodes_dir = args.nodes_dir.resolve()
    manifest = build_nodes_manifest(nodes_dir)
    args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_digest = {"alg": "sha256", "hex": manifest["combined_sha256"]}
    if args.schema == "v2":
        out = build_preflop_ranges_from_nodes(nodes_dir, manifest_ref=args.manifest_ref, manifest_digest=manifest_digest)
    else:
        settings_path = args.settings or (nodes_dir.parent / "settings.json")
        out = build_preflop_ranges_v3_from_nodes(
            nodes_dir,
            manifest_ref=args.manifest_ref,
            manifest_digest=manifest_digest,
            settings_path=settings_path,
        )
    args.out_ranges.parent.mkdir(parents=True, exist_ok=True)
    args.out_ranges.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
