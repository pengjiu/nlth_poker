from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex
from poker2.protocol.enums import MW_RUNG_ID_VALUES


@dataclass(frozen=True)
class MWContextError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def mw_context_digest(
    *,
    state_hash: str,
    mw_ladder_id: str,
    rung_id: str,
    belief_digest_or_none: dict[str, Any] | None,
    mw_risk_spec_id_or_none: str | None,
    strict_mode: bool,
) -> str:
    if rung_id not in MW_RUNG_ID_VALUES:
        raise MWContextError("UNSUPPORTED_VALUE", f"unsupported rung_id: {rung_id!r}")

    obj: dict[str, Any] = {
        "state_hash": state_hash,
        "mw_ladder_id": mw_ladder_id,
        "rung_id": rung_id,
        "belief_digest_or_none": belief_digest_or_none,
        "mw_risk_spec_id_or_none": mw_risk_spec_id_or_none,
    }
    return sha256_hex(canonicalize_json_bytes(obj, strict_mode=strict_mode))

