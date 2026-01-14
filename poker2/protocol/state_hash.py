from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex


@dataclass(frozen=True)
class StateHashError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def state_hash(
    *,
    ruleset_id: str,
    triad: dict[str, Any],
    schema_hash: str,
    snapshot_min_fields: dict[str, Any],
    strict_mode: bool,
) -> str:
    obj: dict[str, Any] = {
        "ruleset_id": ruleset_id,
        "triad": triad,
        "schema_hash": schema_hash,
        "snapshot_min_fields": snapshot_min_fields,
    }
    return sha256_hex(canonicalize_json_bytes(obj, strict_mode=strict_mode))

