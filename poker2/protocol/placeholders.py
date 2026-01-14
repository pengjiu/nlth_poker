from __future__ import annotations

from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex


def placeholder_id(name: str, *, strict_mode: bool) -> str:
    obj: dict[str, Any] = {"placeholder_schema_id": name}
    return sha256_hex(canonicalize_json_bytes(obj, strict_mode=strict_mode))

