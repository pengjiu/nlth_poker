from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex


@dataclass(frozen=True)
class AbstractionError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def abstraction_hash(
    *,
    action_bins_id: str,
    action_adapter_id: str,
    mapping_spec_id: str | None,
    strict_mode: bool,
) -> str:
    obj: dict[str, Any] = {
        "action_bins_id": action_bins_id,
        "action_adapter_id": action_adapter_id,
        "mapping_spec_id": mapping_spec_id,
    }
    return sha256_hex(canonicalize_json_bytes(obj, strict_mode=strict_mode))
