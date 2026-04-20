from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RetaliationModelError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


DEFAULT_BUCKET_SPEC = {
    "spr_edges": [1, 2, 4, 7],
    "size_edges_ppm": [330000, 660000, 1000000, 1500000],
    "players_edges": [2, 3, 4],
    "pos_keys": ["OOP", "IP"],
    "street_keys": ["FLOP", "TURN", "RIVER"],
}


def _bucket_spr(spr: float, edges: list[int]) -> str:
    if spr < edges[0]:
        return "<1"
    if spr < edges[1]:
        return "1-2"
    if spr < edges[2]:
        return "2-4"
    if spr < edges[3]:
        return "4-7"
    return "7+"


def _bucket_size_ppm(size_ppm: int, edges: list[int]) -> str:
    if size_ppm <= 0:
        return "0"
    if size_ppm <= edges[0]:
        return "0-0.33"
    if size_ppm <= edges[1]:
        return "0.33-0.66"
    if size_ppm <= edges[2]:
        return "0.66-1.0"
    if size_ppm <= edges[3]:
        return "1.0-1.5"
    return "1.5+"


def _bucket_players(players: int, edges: list[int]) -> str:
    if players <= edges[0]:
        return "2"
    if players <= edges[1]:
        return "3"
    if players <= edges[2]:
        return "4"
    return "5+"


def retaliation_bucket_key(
    *,
    street: str,
    players_alive: int,
    pos_key: str | None,
    spr: float,
    size_ratio_ppm: int,
    bucket_spec: dict[str, Any] | None = None,
) -> str:
    spec = dict(DEFAULT_BUCKET_SPEC)
    if bucket_spec:
        spec.update(bucket_spec)
    spr_edges = [int(x) for x in spec.get("spr_edges", DEFAULT_BUCKET_SPEC["spr_edges"])]
    size_edges_ppm = [int(x) for x in spec.get("size_edges_ppm", DEFAULT_BUCKET_SPEC["size_edges_ppm"])]
    players_edges = [int(x) for x in spec.get("players_edges", DEFAULT_BUCKET_SPEC["players_edges"])]
    pos_bucket = "OOP" if pos_key in ("SB", "BB") else "IP"
    return "|".join(
        [
            str(street),
            _bucket_players(int(players_alive), players_edges),
            pos_bucket,
            _bucket_spr(float(spr), spr_edges),
            _bucket_size_ppm(int(size_ratio_ppm), size_edges_ppm),
        ]
    )


def load_retaliation_model(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RetaliationModelError("JSON_PARSE_FAIL", "retaliation model JSON unreadable", {"path": str(path), "error": str(e)}) from e
    if not isinstance(obj, dict):
        raise RetaliationModelError("TYPE_ERROR", "retaliation model must be object", {"path": str(path)})
    schema_id = obj.get("schema_id")
    if schema_id not in ("retaliation_model_v1", "retaliation_model_v2"):
        raise RetaliationModelError("SCHEMA_MISMATCH", "retaliation model schema_id mismatch", {"path": str(path)})

    bucket_spec = obj.get("bucket_spec") or DEFAULT_BUCKET_SPEC
    global_counts = obj.get("global") or {}
    buckets = obj.get("buckets") or []
    if not isinstance(buckets, list):
        raise RetaliationModelError("TYPE_ERROR", "retaliation model buckets must be list", {"path": str(path)})
    index: dict[str, dict[str, float]] = {}
    for row in buckets:
        if not isinstance(row, dict):
            continue
        key = "|".join(
            [
                str(row.get("street")),
                str(row.get("players_bucket")),
                str(row.get("pos_bucket")),
                str(row.get("spr_bucket")),
                str(row.get("size_bucket")),
            ]
        )
        bet_count = float(row.get("bet_count", 0) or 0.0)
        raise_count = float(row.get("raise_count", 0) or 0.0)
        raise_profit_sum = float(row.get("raise_profit_sum", 0) or 0.0)
        call_count = float(row.get("call_count", 0) or 0.0)
        call_profit_sum = float(row.get("call_profit_sum", 0) or 0.0)
        if bet_count <= 0:
            continue
        index[key] = {
            "bet_count": bet_count,
            "raise_count": raise_count,
            "call_count": call_count,
            "raise_profit_sum": raise_profit_sum,
            "call_profit_sum": call_profit_sum,
        }
    return {
        "schema_id": schema_id,
        "bucket_spec": bucket_spec,
        "global": {
            "bet_count": float(global_counts.get("bet_count", 0) or 0.0),
            "raise_count": float(global_counts.get("raise_count", 0) or 0.0),
            "call_count": float(global_counts.get("call_count", 0) or 0.0),
            "raise_profit_sum": float(global_counts.get("raise_profit_sum", 0) or 0.0),
            "call_profit_sum": float(global_counts.get("call_profit_sum", 0) or 0.0),
        },
        "index": index,
    }
