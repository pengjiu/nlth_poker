from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object


@dataclass(frozen=True)
class SchemaContractError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _contractkit_spec_digest(*, strict_mode: bool) -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    spec_path = root / "contractkit" / "spec" / "contractkit_spec_v1.json"
    spec_obj = json.loads(spec_path.read_text(encoding="utf-8"))
    digest_hex = sha256_hex(canonicalize_json_bytes(spec_obj, strict_mode=strict_mode))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def schema_hash(*, strict_mode: bool) -> str:
    contract: dict[str, Any] = {
        "schema_contract_id": "schema_contract_v1",
        "contractkit_spec_digest": _contractkit_spec_digest(strict_mode=strict_mode),
    }
    return sha256_hex(canonicalize_json_bytes(contract, strict_mode=strict_mode))

