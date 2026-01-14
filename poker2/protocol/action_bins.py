from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex


@dataclass(frozen=True)
class ActionBinsError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def load_action_bins_spec(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ActionBinsError("JSON_PARSE_FAIL", "action bins JSON unreadable", {"error": str(e)}) from e
    if not isinstance(obj, dict):
        raise ActionBinsError("TYPE_ERROR", "ActionBinsSpec must be JSON object")
    return obj


def validate_action_bins_spec(spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(spec, dict):
        raise ActionBinsError("TYPE_ERROR", "ActionBinsSpec must be JSON object")
    if strict_mode and "action_bins_id" in spec:
        raise ActionBinsError("DISALLOWED_FIELD", "ActionBinsSpec hash input must not include action_bins_id")

    schema_id = spec.get("action_bins_schema_id")
    if schema_id != "action_bins_spec_v1":
        raise ActionBinsError("UNSUPPORTED_VALUE", "unsupported action_bins_schema_id")

    for k in ("include_min_raise_to", "include_max_raise_to", "include_extra_raise_to"):
        v = spec.get(k)
        if not isinstance(v, bool):
            raise ActionBinsError("TYPE_ERROR", f"{k} must be bool")

    if spec["include_extra_raise_to"] and not spec["include_min_raise_to"]:
        raise ActionBinsError("VALUE_ERROR", "include_extra_raise_to requires include_min_raise_to=true")

    if strict_mode and not (spec["include_min_raise_to"] or spec["include_max_raise_to"]):
        raise ActionBinsError("VALUE_ERROR", "at least one of include_min_raise_to/include_max_raise_to must be true")

    def _validate_ppm_list(name: str, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, list):
            raise ActionBinsError("TYPE_ERROR", f"{name} must be list")
        if not value:
            return
        prev: int | None = None
        seen: set[int] = set()
        for idx, v in enumerate(value):
            if isinstance(v, bool) or not isinstance(v, int):
                raise ActionBinsError("TYPE_ERROR", f"{name}[{idx}] must be int")
            if v < 0:
                raise ActionBinsError("VALUE_ERROR", f"{name}[{idx}] must be >= 0")
            if strict_mode:
                if prev is not None and v < prev:
                    raise ActionBinsError("VALUE_ERROR", f"{name} must be non-decreasing in strict_mode")
                if v in seen:
                    raise ActionBinsError("VALUE_ERROR", f"{name} must not contain duplicates in strict_mode")
            prev = v
            seen.add(v)

    _validate_ppm_list("bet_bins_ppm", spec.get("bet_bins_ppm"))
    _validate_ppm_list("raise_bins_ppm", spec.get("raise_bins_ppm"))


def action_bins_id(spec: Any, *, strict_mode: bool) -> str:
    validate_action_bins_spec(spec, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(spec, strict_mode=strict_mode))


def default_internal_action_bins(*, strict_mode: bool) -> tuple[dict[str, Any], str]:
    root = Path(__file__).resolve().parents[2]
    path = root / "specs" / "action_bins" / "internal_action_bins_v1.json"
    spec = load_action_bins_spec(path)
    bid = action_bins_id(spec, strict_mode=strict_mode)
    return spec, bid
