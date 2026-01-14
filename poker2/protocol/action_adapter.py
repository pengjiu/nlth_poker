from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import ROUNDING_MODE_VALUES, canonicalize_json_bytes, sha256_hex
from poker2.protocol.enums import FALLBACK_POLICY_MODE_VALUES


@dataclass(frozen=True)
class ActionAdapterError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def load_action_adapter_spec(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ActionAdapterError("JSON_PARSE_FAIL", "action adapter JSON unreadable", {"error": str(e)}) from e
    if not isinstance(obj, dict):
        raise ActionAdapterError("TYPE_ERROR", "ActionAdapterSpec must be JSON object")
    return obj


def validate_action_adapter_spec(spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(spec, dict):
        raise ActionAdapterError("TYPE_ERROR", "ActionAdapterSpec must be JSON object")
    if strict_mode and "action_adapter_id" in spec:
        raise ActionAdapterError("DISALLOWED_FIELD", "ActionAdapterSpec hash input must not include action_adapter_id")

    schema_id = spec.get("action_adapter_schema_id")
    if schema_id != "action_adapter_spec_v1":
        raise ActionAdapterError("UNSUPPORTED_VALUE", "unsupported action_adapter_schema_id")

    rounding_mode = spec.get("rounding_mode")
    if rounding_mode is not None and rounding_mode not in ROUNDING_MODE_VALUES:
        raise ActionAdapterError("UNSUPPORTED_VALUE", "unsupported rounding_mode", {"rounding_mode": rounding_mode})

    fallback = spec.get("fallback_policy")
    if not isinstance(fallback, dict):
        raise ActionAdapterError("TYPE_ERROR", "fallback_policy must be object")
    mode = fallback.get("mode")
    if mode not in FALLBACK_POLICY_MODE_VALUES:
        raise ActionAdapterError("UNSUPPORTED_VALUE", "unsupported fallback_policy.mode", {"mode": mode})


def action_adapter_id(spec: Any, *, strict_mode: bool) -> str:
    validate_action_adapter_spec(spec, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(spec, strict_mode=strict_mode))


def default_internal_action_adapter(*, strict_mode: bool) -> tuple[dict[str, Any], str]:
    root = Path(__file__).resolve().parents[2]
    path = root / "specs" / "action_adapters" / "internal_action_adapter_v1.json"
    spec = load_action_adapter_spec(path)
    aid = action_adapter_id(spec, strict_mode=strict_mode)
    return spec, aid
