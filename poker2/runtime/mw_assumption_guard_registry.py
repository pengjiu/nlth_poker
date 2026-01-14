from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.mw_assumption_guard import (
    MWAssumptionGuardError,
    load_mw_assumption_guard_spec,
    mw_assumption_guard_id,
    validate_mw_assumption_guard_spec,
)


@dataclass(frozen=True)
class MWAssumptionGuardRegistryError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_mw_assumption_guards_root() -> Path:
    return _repo_root() / "specs" / "mw_assumption_guards"


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


def build_mw_assumption_guard_registry(
    *,
    mw_assumption_guards_root: Path | None = None,
    strict_mode: bool,
) -> dict[str, dict[str, Any]]:
    root = mw_assumption_guards_root or default_mw_assumption_guards_root()
    by_id: dict[str, dict[str, Any]] = {}

    for path in _iter_json_paths(root):
        try:
            spec = load_mw_assumption_guard_spec(path)
            validate_mw_assumption_guard_spec(spec, strict_mode=strict_mode)
            gid = mw_assumption_guard_id(spec, strict_mode=True)
        except MWAssumptionGuardError as e:
            raise MWAssumptionGuardRegistryError(
                "ASSUMPTION_GUARD_INVALID",
                "mw assumption guard spec invalid",
                {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            ) from e

        label = spec.get("label") if isinstance(spec.get("label"), str) else None
        entry = {
            "assumption_guard_id": gid,
            "assumption_guard_ref": f"path:{path}",
            "assumption_guard_digest": _canonical_digest_sha256(spec),
            "label_or_none": label,
        }
        if gid in by_id:
            raise MWAssumptionGuardRegistryError(
                "AMBIGUOUS",
                "multiple mw assumption guard specs produce the same assumption_guard_id",
                {"assumption_guard_id": gid, "refs": [by_id[gid]["assumption_guard_ref"], entry["assumption_guard_ref"]]},
            )
        by_id[gid] = entry

    return by_id
