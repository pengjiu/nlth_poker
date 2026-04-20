from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from poker2.cli.hrc_nodes import action_kinds, canonical_action_kind, iter_hands, played_by_index
from poker2.contractkit import sha256_hex
from poker2.protocol.preflop_freq import build_nodes_manifest, validate_preflop_freq


def _seat_to_pos(seat: int) -> str:
    # Hand2/HRC export uses seats: 0=UTG,1=UTG+1,2=MP,3=CO,4=BU,5=SB,6=BB.
    if seat == 4:
        return "BU"
    if seat == 5:
        return "SB"
    if seat == 6:
        return "BB"
    return "OTHERS"


def _node_action_weights(node: dict[str, Any]) -> tuple[float, dict[str, float]]:
    actions = node.get("actions") or []
    kinds = action_kinds(actions)
    if not kinds:
        return 0.0, {}
    totals = {"F": 0.0, "C": 0.0, "R": 0.0}
    total_weight = 0.0
    for _, info in iter_hands(node.get("hands") or {}):
        weight = float(info.get("weight", 0.0) or 0.0)
        if weight <= 0.0:
            continue
        played = played_by_index(info, kinds)
        if not played:
            continue
        total_weight += weight
        for idx, prob in enumerate(played):
            if idx >= len(kinds):
                break
            try:
                p = float(prob)
            except Exception:
                continue
            kind = kinds[idx]
            if kind == "raise":
                totals["R"] += weight * max(0.0, min(1.0, p))
            elif kind == "call":
                totals["C"] += weight * max(0.0, min(1.0, p))
            elif kind == "fold":
                totals["F"] += weight * max(0.0, min(1.0, p))
    return total_weight, totals


def build_preflop_freq_from_nodes(nodes_dir: Path, *, manifest_ref: str, manifest_digest: dict[str, str]) -> dict[str, Any]:
    totals: dict[str, dict[str, float]] = {}
    counts: dict[str, dict[str, float]] = {}
    node_files = sorted(nodes_dir.glob("*.json"), key=lambda p: p.name)
    if not node_files:
        raise ValueError(f"no nodes found under {nodes_dir}")
    for path in node_files:
        node = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(node, dict):
            continue
        if int(node.get("street", -1)) != 0:
            continue
        player = node.get("player")
        if isinstance(player, bool) or not isinstance(player, int):
            continue
        seq = node.get("sequence") or []
        raise_count = 0
        for act in seq:
            if canonical_action_kind(act) == "raise":
                raise_count += 1

        total_weight, action_weights = _node_action_weights(node)
        if total_weight <= 0.0:
            continue

        pos = _seat_to_pos(player)
        totals.setdefault(pos, {"open": 0.0, "vs_open": 0.0, "vs_3bet": 0.0})
        counts.setdefault(pos, {"open_raise": 0.0, "call_vs_open": 0.0, "threebet": 0.0, "fourbet": 0.0})

        if raise_count == 0:
            totals[pos]["open"] += total_weight
            counts[pos]["open_raise"] += action_weights.get("R", 0.0)
        elif raise_count == 1:
            totals[pos]["vs_open"] += total_weight
            counts[pos]["call_vs_open"] += action_weights.get("C", 0.0)
            counts[pos]["threebet"] += action_weights.get("R", 0.0)
        else:
            totals[pos]["vs_3bet"] += total_weight
            counts[pos]["fourbet"] += action_weights.get("R", 0.0)

    positions: dict[str, dict[str, float]] = {}
    for pos in ("BU", "SB", "BB", "OTHERS"):
        t = totals.get(pos, {})
        c = counts.get(pos, {})
        open_total = t.get("open", 0.0)
        open_pct = (c.get("open_raise", 0.0) / open_total) if open_total > 0 else 0.0
        vs_open_total = t.get("vs_open", 0.0)
        call_pct = (c.get("call_vs_open", 0.0) / vs_open_total) if vs_open_total > 0 else 0.0
        threebet_pct = (c.get("threebet", 0.0) / vs_open_total) if vs_open_total > 0 else 0.0
        vs_3bet_total = t.get("vs_3bet", 0.0)
        fourbet_pct = (c.get("fourbet", 0.0) / vs_3bet_total) if vs_3bet_total > 0 else 0.0
        positions[pos] = {
            "open_pct": float(max(0.0, min(1.0, open_pct))),
            "call_pct": float(max(0.0, min(1.0, call_pct))),
            "threebet_pct": float(max(0.0, min(1.0, threebet_pct))),
            "fourbet_pct": float(max(0.0, min(1.0, fourbet_pct))),
        }

    out = {
        "schema_id": "preflop_freq_v1",
        "source": "hrc_nodes_manifest_v1",
        "manifest_ref": manifest_ref,
        "manifest_digest": manifest_digest,
        "node_count": len(node_files),
        "positions": positions,
    }
    validate_preflop_freq(out, strict_mode=True)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Build preflop_freq_v1 from HRC nodes.")
    p.add_argument("--nodes-dir", type=Path, required=True)
    p.add_argument("--out-manifest", type=Path, required=True)
    p.add_argument("--out-freq", type=Path, required=True)
    p.add_argument("--manifest-ref", type=str, required=True)
    args = p.parse_args()

    nodes_dir = args.nodes_dir.resolve()
    manifest = build_nodes_manifest(nodes_dir)
    args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_digest = {"alg": "sha256", "hex": manifest["combined_sha256"]}
    out = build_preflop_freq_from_nodes(nodes_dir, manifest_ref=args.manifest_ref, manifest_digest=manifest_digest)
    args.out_freq.parent.mkdir(parents=True, exist_ok=True)
    args.out_freq.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
