from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object


@dataclass(frozen=True)
class RunIdError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def run_id_v1(*, options_hash: str, seed: int, strict_mode: bool) -> str:
    # run_id = sha256(canonicalized {run_id_schema:"run_id_v1", options_hash, seed})
    try:
        validate_digest_object({"alg": "sha256", "hex": options_hash}, strict_mode=True)
    except Exception as e:
        raise RunIdError("OPTIONS_HASH_INVALID", f"options_hash must be sha256 hex: {e}") from e

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise RunIdError("TYPE_ERROR", f"seed must be int, got {type(seed).__name__}")

    payload: dict[str, Any] = {"run_id_schema": "run_id_v1", "options_hash": options_hash, "seed": seed}
    return sha256_hex(canonicalize_json_bytes(payload, strict_mode=strict_mode))

