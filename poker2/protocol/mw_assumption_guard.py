from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex


@dataclass(frozen=True)
class MWAssumptionGuardError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


MW_ASSUMPTION_GUARD_SCHEMA_ID = "mw_assumption_guard_spec_v1"


def load_mw_assumption_guard_spec(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise MWAssumptionGuardError("JSON_PARSE_FAIL", "mw assumption guard JSON unreadable", {"error": str(e)}) from e
    if not isinstance(obj, dict):
        raise MWAssumptionGuardError("TYPE_ERROR", "MWAssumptionGuardSpec must be JSON object")
    return obj


def validate_mw_assumption_guard_spec(spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(spec, dict):
        raise MWAssumptionGuardError("TYPE_ERROR", "MWAssumptionGuardSpec must be JSON object")
    if strict_mode and "assumption_guard_id" in spec:
        raise MWAssumptionGuardError("DISALLOWED_FIELD", "MWAssumptionGuardSpec hash input must not include assumption_guard_id")

    schema_id = spec.get("mw_assumption_guard_schema_id")
    if schema_id != MW_ASSUMPTION_GUARD_SCHEMA_ID:
        raise MWAssumptionGuardError("UNSUPPORTED_VALUE", "unsupported mw_assumption_guard_schema_id")

    if not isinstance(spec.get("assumption"), dict):
        raise MWAssumptionGuardError("TYPE_ERROR", "assumption must be object")
    if not isinstance(spec.get("guard"), dict):
        raise MWAssumptionGuardError("TYPE_ERROR", "guard must be object")


def mw_assumption_guard_id(spec: Any, *, strict_mode: bool) -> str:
    validate_mw_assumption_guard_spec(spec, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(spec, strict_mode=strict_mode))


def default_internal_mw_assumption_guard(*, strict_mode: bool) -> tuple[dict[str, Any], str]:
    root = Path(__file__).resolve().parents[2]
    path = root / "specs" / "mw_assumption_guards" / "internal_mw_guard_v1.json"
    spec = load_mw_assumption_guard_spec(path)
    gid = mw_assumption_guard_id(spec, strict_mode=strict_mode)
    return spec, gid
