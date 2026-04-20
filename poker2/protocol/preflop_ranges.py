from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import sha256_hex, validate_digest_object


PREFLOP_SIZE_BUCKETS_X100 = (
    150,
    200,
    225,
    250,
    275,
    300,
    325,
    350,
    400,
    500,
    600,
    700,
    800,
    900,
    1000,
    1200,
    1500,
    2000,
    3000,
    4000,
    6000,
    8000,
    12000,
    20000,
    40000,
)


def preflop_scenario(*, raise_count: int, has_caller: bool, facing: bool) -> str | None:
    if raise_count <= 0:
        return "LIMPED" if has_caller else "OPEN"
    if not facing:
        return None
    if raise_count == 1:
        return "VS_OPEN"
    if raise_count == 2:
        return "VS_3BET"
    if raise_count == 3:
        return "VS_4BET"
    return "VS_5BET_PLUS"


def size_ratio_x100(amount: int, bb: int) -> int | None:
    if amount <= 0 or bb <= 0:
        return None
    return (amount * 100 + bb // 2) // bb


def size_bucket_from_amount(amount: int, bb: int) -> int | None:
    ratio = size_ratio_x100(amount, bb)
    if ratio is None:
        return None
    for idx, edge in enumerate(PREFLOP_SIZE_BUCKETS_X100):
        if ratio <= edge:
            return idx
    return len(PREFLOP_SIZE_BUCKETS_X100)


@dataclass(frozen=True)
class PreflopRangesError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _sha256_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _combined_hash(entries: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for entry in entries:
        name = entry.get("name")
        sha = entry.get("sha256")
        size = entry.get("size")
        parts.append(f"{name}\t{sha}\t{size}")
    payload = "\n".join(parts) + "\n"
    return sha256_hex(payload.encode("utf-8"))


def build_nodes_manifest(nodes_dir: Path) -> dict[str, Any]:
    if not nodes_dir.exists() or not nodes_dir.is_dir():
        raise PreflopRangesError("NODES_DIR_MISSING", "nodes_dir must exist and be a directory", {"path": str(nodes_dir)})
    entries: list[dict[str, Any]] = []
    for path in sorted(nodes_dir.glob("*.json"), key=lambda p: p.name):
        size = path.stat().st_size
        entries.append({"name": path.name, "sha256": _sha256_file(path), "size": size})
    if not entries:
        raise PreflopRangesError("NODES_EMPTY", "nodes_dir contains no .json node files", {"path": str(nodes_dir)})
    combined_sha256 = _combined_hash(entries)
    return {
        "manifest_schema": "preflop_nodes_manifest_v1",
        "file_count": len(entries),
        "combined_sha256": combined_sha256,
        "entries": entries,
    }


def _validate_hand_probs(hand: str, probs: dict[str, Any], *, context: dict[str, Any]) -> None:
    if not isinstance(probs, dict):
        raise PreflopRangesError("TYPE_ERROR", "hand entry must be object", {"hand": hand, **context})
    vals = {}
    for key in ("raise", "call", "fold"):
        val = probs.get(key, 0.0)
        if not isinstance(val, (int, float)):
            raise PreflopRangesError("TYPE_ERROR", "hand prob must be number", {"hand": hand, "field": key, **context})
        if not 0.0 <= float(val) <= 1.0:
            raise PreflopRangesError("VALUE_ERROR", "hand prob out of range", {"hand": hand, "field": key, "value": val, **context})
        vals[key] = float(val)
    total = vals["raise"] + vals["call"] + vals["fold"]
    if total > 1.001:
        raise PreflopRangesError("VALUE_ERROR", "hand probs sum above 1", {"hand": hand, "total": total, **context})


def _extract_hands(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, dict) and "hands" in entry:
        hands = entry.get("hands")
        if isinstance(hands, dict):
            return hands
        return None
    if isinstance(entry, dict):
        # allow direct hand map without wrapper
        if entry and all(isinstance(v, dict) for v in entry.values()):
            return entry
    return None


def validate_preflop_ranges(
    obj: Any,
    *,
    strict_mode: bool,
    manifest_path: Path | None = None,
) -> None:
    if not isinstance(obj, dict):
        raise PreflopRangesError("TYPE_ERROR", "preflop_ranges must be JSON object")
    schema_id = obj.get("schema_id")
    if schema_id not in ("preflop_ranges_v2", "preflop_ranges_v3"):
        raise PreflopRangesError("SCHEMA_MISMATCH", "preflop_ranges schema_id must be preflop_ranges_v2 or preflop_ranges_v3")

    if schema_id == "preflop_ranges_v2":
        scenarios = obj.get("scenarios")
        if not isinstance(scenarios, dict) or not scenarios:
            raise PreflopRangesError("TYPE_ERROR", "preflop_ranges.scenarios must be non-empty object")

        for scenario_key, scenario_entry in scenarios.items():
            if not isinstance(scenario_entry, dict):
                raise PreflopRangesError("TYPE_ERROR", "scenario entry must be object", {"scenario": scenario_key})
            for pos_key, pos_entry in scenario_entry.items():
                if not isinstance(pos_entry, dict):
                    raise PreflopRangesError("TYPE_ERROR", "position entry must be object", {"scenario": scenario_key, "pos": pos_key})
                if scenario_key == "VS_OPEN":
                    # pos_entry maps opener_pos -> hands
                    for opener_key, opener_entry in pos_entry.items():
                        hands = _extract_hands(opener_entry)
                        if hands is None:
                            raise PreflopRangesError(
                                "TYPE_ERROR",
                                "opener entry must contain hands map",
                                {"scenario": scenario_key, "pos": pos_key, "opener": opener_key},
                            )
                        for hand, probs in hands.items():
                            if not isinstance(hand, str):
                                raise PreflopRangesError(
                                    "TYPE_ERROR",
                                    "hand key must be string",
                                    {"scenario": scenario_key, "pos": pos_key, "opener": opener_key},
                                )
                            _validate_hand_probs(hand, probs, context={"scenario": scenario_key, "pos": pos_key, "opener": opener_key})
                else:
                    hands = _extract_hands(pos_entry)
                    if hands is None:
                        raise PreflopRangesError(
                            "TYPE_ERROR",
                            "position entry must contain hands map",
                            {"scenario": scenario_key, "pos": pos_key},
                        )
                    for hand, probs in hands.items():
                        if not isinstance(hand, str):
                            raise PreflopRangesError(
                                "TYPE_ERROR",
                                "hand key must be string",
                                {"scenario": scenario_key, "pos": pos_key},
                            )
                        _validate_hand_probs(hand, probs, context={"scenario": scenario_key, "pos": pos_key})
    else:
        entries = obj.get("entries")
        if not isinstance(entries, list) or not entries:
            raise PreflopRangesError("TYPE_ERROR", "preflop_ranges.entries must be non-empty array")
        key_fields = obj.get("key_fields")
        if key_fields is not None:
            if not isinstance(key_fields, list) or not all(isinstance(k, str) for k in key_fields):
                raise PreflopRangesError("TYPE_ERROR", "preflop_ranges.key_fields must be list[str]")
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise PreflopRangesError("TYPE_ERROR", "entry must be object", {"index": idx})
            key = entry.get("key")
            hands = entry.get("hands")
            if not isinstance(key, dict):
                raise PreflopRangesError("TYPE_ERROR", "entry.key must be object", {"index": idx})
            for k, v in key.items():
                if not isinstance(k, str):
                    raise PreflopRangesError("TYPE_ERROR", "entry.key fields must be string", {"index": idx})
                if not isinstance(v, (str, int, bool)) and v is not None:
                    raise PreflopRangesError("TYPE_ERROR", "entry.key values must be str/int/bool/null", {"index": idx, "field": k})
            if not isinstance(hands, dict):
                raise PreflopRangesError("TYPE_ERROR", "entry.hands must be object", {"index": idx})
            for hand, probs in hands.items():
                if not isinstance(hand, str):
                    raise PreflopRangesError("TYPE_ERROR", "hand key must be string", {"index": idx})
                _validate_hand_probs(hand, probs, context={"index": idx})

    node_count = obj.get("node_count")
    if node_count is None:
        raise PreflopRangesError("MISSING_FIELDS", "preflop_ranges.node_count missing")
    if isinstance(node_count, bool) or not isinstance(node_count, int) or node_count <= 0:
        raise PreflopRangesError("TYPE_ERROR", "preflop_ranges.node_count must be positive int", {"node_count": node_count})

    if strict_mode:
        ref = obj.get("manifest_ref")
        dig = obj.get("manifest_digest")
        if not isinstance(ref, str):
            raise PreflopRangesError("TYPE_ERROR", "preflop_ranges.manifest_ref must be str in strict_mode")
        try:
            validate_digest_object(dig, strict_mode=True)
        except Exception as e:  # pragma: no cover
            raise PreflopRangesError("DIGEST_INVALID", "preflop_ranges.manifest_digest invalid", {"error": str(e)}) from e

        if manifest_path is not None:
            if not manifest_path.exists():
                raise PreflopRangesError("MANIFEST_MISSING", "manifest_path does not exist", {"path": str(manifest_path)})
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise PreflopRangesError("MANIFEST_READ_FAIL", "failed to read manifest", {"path": str(manifest_path), "error": str(e)}) from e
            combined = manifest.get("combined_sha256")
            if not isinstance(combined, str):
                raise PreflopRangesError("MANIFEST_SHAPE", "manifest missing combined_sha256", {"path": str(manifest_path)})
            if combined != dig.get("hex"):
                raise PreflopRangesError(
                    "MANIFEST_DIGEST_MISMATCH",
                    "manifest combined_sha256 does not match manifest_digest",
                    {"expected": combined, "observed": dig.get("hex")},
                )
            manifest_count = manifest.get("file_count")
            if isinstance(manifest_count, int) and manifest_count != node_count:
                raise PreflopRangesError(
                    "NODE_COUNT_MISMATCH",
                    "node_count does not match manifest file_count",
                    {"node_count": node_count, "manifest_file_count": manifest_count},
                )
