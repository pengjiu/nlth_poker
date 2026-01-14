from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.mw_ladder import MWLadderError, load_mw_ladder_spec, mw_ladder_id, validate_mw_ladder_spec


@dataclass(frozen=True)
class MWLadderRegistryError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_mw_ladders_root() -> Path:
    return _repo_root() / "specs" / "mw_ladders"


def _canonical_digest_sha256(obj: Any) -> dict[str, str]:
    digest_hex = sha256_hex(canonicalize_json_bytes(obj, strict_mode=True))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def _iter_json_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    paths = [p for p in root.glob("*.json") if p.is_file()]
    paths.sort(key=lambda p: str(p))
    return paths


def build_mw_ladder_registry(
    *,
    mw_ladders_root: Path | None = None,
    strict_mode: bool,
) -> dict[str, dict[str, Any]]:
    root = mw_ladders_root or default_mw_ladders_root()
    by_id: dict[str, dict[str, Any]] = {}

    for path in _iter_json_paths(root):
        try:
            spec = load_mw_ladder_spec(path)
            validate_mw_ladder_spec(spec, strict_mode=strict_mode)
            mid = mw_ladder_id(spec, strict_mode=True)
        except MWLadderError as e:
            raise MWLadderRegistryError(
                "MW_LADDER_INVALID",
                "mw ladder spec invalid",
                {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            ) from e

        label = spec.get("label") if isinstance(spec.get("label"), str) else None
        entry = {
            "mw_ladder_id": mid,
            "mw_ladder_ref": f"path:{path}",
            "mw_ladder_digest": _canonical_digest_sha256(spec),
            "label_or_none": label,
        }
        if mid in by_id:
            raise MWLadderRegistryError(
                "AMBIGUOUS",
                "multiple mw ladder specs produce the same mw_ladder_id",
                {"mw_ladder_id": mid, "refs": [by_id[mid]["mw_ladder_ref"], entry["mw_ladder_ref"]]},
            )
        by_id[mid] = entry

    return by_id
