from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import sha256_hex, validate_digest_object


@dataclass(frozen=True)
class PreflopFreqError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _sha256_file(path: Path) -> str:
    h = sha256_hex(path.read_bytes())
    return h


def _combined_hash(entries: list[dict[str, Any]]) -> str:
    # Deterministic combined hash over sorted entries.
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
        raise PreflopFreqError("NODES_DIR_MISSING", "nodes_dir must exist and be a directory", {"path": str(nodes_dir)})
    entries: list[dict[str, Any]] = []
    for path in sorted(nodes_dir.glob("*.json"), key=lambda p: p.name):
        size = path.stat().st_size
        entries.append({"name": path.name, "sha256": _sha256_file(path), "size": size})
    if not entries:
        raise PreflopFreqError("NODES_EMPTY", "nodes_dir contains no .json node files", {"path": str(nodes_dir)})
    combined_sha256 = _combined_hash(entries)
    return {
        "manifest_schema": "preflop_nodes_manifest_v1",
        "file_count": len(entries),
        "combined_sha256": combined_sha256,
        "entries": entries,
    }


def validate_preflop_freq(
    obj: Any,
    *,
    strict_mode: bool,
    manifest_path: Path | None = None,
) -> None:
    if not isinstance(obj, dict):
        raise PreflopFreqError("TYPE_ERROR", "preflop_freq must be JSON object")
    if obj.get("schema_id") != "preflop_freq_v1":
        raise PreflopFreqError("SCHEMA_MISMATCH", "preflop_freq schema_id must be preflop_freq_v1")
    positions = obj.get("positions")
    if not isinstance(positions, dict):
        raise PreflopFreqError("TYPE_ERROR", "preflop_freq.positions must be object")
    required_pos = ("BU", "SB", "BB", "OTHERS")
    for pos in required_pos:
        if pos not in positions:
            raise PreflopFreqError("MISSING_FIELDS", "preflop_freq missing position", {"position": pos})
        pos_obj = positions.get(pos)
        if not isinstance(pos_obj, dict):
            raise PreflopFreqError("TYPE_ERROR", "preflop_freq position entry must be object", {"position": pos})
        for key in ("open_pct", "call_pct", "threebet_pct", "fourbet_pct"):
            val = pos_obj.get(key)
            if not isinstance(val, (int, float)):
                raise PreflopFreqError("TYPE_ERROR", "preflop_freq position pct must be number", {"position": pos, "field": key})
            if not 0.0 <= float(val) <= 1.0:
                raise PreflopFreqError("VALUE_ERROR", "preflop_freq position pct out of range", {"position": pos, "field": key, "value": val})

    node_count = obj.get("node_count")
    if node_count is None:
        raise PreflopFreqError("MISSING_FIELDS", "preflop_freq.node_count missing")
    if isinstance(node_count, bool) or not isinstance(node_count, int) or node_count <= 0:
        raise PreflopFreqError("TYPE_ERROR", "preflop_freq.node_count must be positive int", {"node_count": node_count})

    if strict_mode:
        ref = obj.get("manifest_ref")
        dig = obj.get("manifest_digest")
        if not isinstance(ref, str):
            raise PreflopFreqError("TYPE_ERROR", "preflop_freq.manifest_ref must be str in strict_mode")
        try:
            validate_digest_object(dig, strict_mode=True)
        except Exception as e:  # pragma: no cover - wrapped error
            raise PreflopFreqError("DIGEST_INVALID", "preflop_freq.manifest_digest invalid", {"error": str(e)}) from e

        if manifest_path is not None:
            if not manifest_path.exists():
                raise PreflopFreqError("MANIFEST_MISSING", "manifest_path does not exist", {"path": str(manifest_path)})
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise PreflopFreqError("MANIFEST_READ_FAIL", "failed to read manifest", {"path": str(manifest_path), "error": str(e)}) from e
            combined = manifest.get("combined_sha256")
            if not isinstance(combined, str):
                raise PreflopFreqError("MANIFEST_SHAPE", "manifest missing combined_sha256", {"path": str(manifest_path)})
            if combined != dig.get("hex"):
                raise PreflopFreqError(
                    "MANIFEST_DIGEST_MISMATCH",
                    "manifest combined_sha256 does not match manifest_digest",
                    {"expected": combined, "observed": dig.get("hex")},
                )
            manifest_count = manifest.get("file_count")
            if isinstance(manifest_count, int) and manifest_count != node_count:
                raise PreflopFreqError(
                    "NODE_COUNT_MISMATCH",
                    "node_count does not match manifest file_count",
                    {"node_count": node_count, "manifest_file_count": manifest_count},
                )

