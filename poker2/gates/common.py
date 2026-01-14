from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from poker2.contractkit import validate_digest_object


@dataclass(frozen=True)
class GateCheckError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _as_obj(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateCheckError("TYPE_ERROR", f"{field} must be object")
    return value


def _as_list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise GateCheckError("TYPE_ERROR", f"{field} must be array")
    return value


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GateCheckError("TYPE_ERROR", f"{field} must be int")
    return value


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise GateCheckError("TYPE_ERROR", f"{field} must be str")
    return value


def _sha256_hex(value: Any, *, field: str) -> str:
    s = _as_str(value, field=field)
    if not _SHA256_HEX_RE.fullmatch(s):
        raise GateCheckError("ID_INVALID", f"{field} must be sha256 lowercase hex")
    return s


def _digest_obj(value: Any, *, field: str) -> dict[str, Any]:
    obj = _as_obj(value, field=field)
    try:
        validate_digest_object(obj, strict_mode=True)
    except Exception as e:
        raise GateCheckError("DIGEST_INVALID", f"{field} invalid", {"error": str(e)}) from e
    return obj


def evidence_ref(
    *,
    gate_id: str,
    header: dict[str, Any],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    ruleset_id_or_none: str | None,
    triad_or_none: dict[str, Any] | None,
    schema_hash_or_none: str | None,
    hand_selector_or_none: dict[str, Any] | None,
    decision_id_or_none: int | None,
    state_hash_or_none: str | None,
) -> dict[str, Any]:
    # Minimal evidence closure per ARCHIETECTURE.md §6.2.
    return {
        "gate_id": gate_id,
        "run_id": header.get("run_id"),
        "options_hash": header.get("options_hash"),
        "seed": header.get("seed"),
        "context": {
            "scenario_id_or_null": header.get("scenario_id"),
            "ruleset_id_or_null": ruleset_id_or_none,
            "triad_or_null": triad_or_none,
            "schema_hash_or_null": schema_hash_or_none,
        },
        "hand_selector_or_null": hand_selector_or_none,
        "decision_id_or_null": decision_id_or_none,
        "state_hash_or_null": state_hash_or_none,
        "event_stream_ref_or_null": event_stream_ref,
        "event_stream_digest_or_null": event_stream_digest,
    }


def failure(
    *,
    gate_id: str,
    reason: str,
    header: dict[str, Any],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    ruleset_id_or_none: str | None,
    triad_or_none: dict[str, Any] | None,
    schema_hash_or_none: str | None,
    hand_selector_or_none: dict[str, Any] | None = None,
    decision_id_or_none: int | None = None,
    state_hash_or_none: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "status": "fail",
        "reason": reason,
        "details": details or {},
        "evidence_ref": evidence_ref(
            gate_id=gate_id,
            header=header,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            ruleset_id_or_none=ruleset_id_or_none,
            triad_or_none=triad_or_none,
            schema_hash_or_none=schema_hash_or_none,
            hand_selector_or_none=hand_selector_or_none,
            decision_id_or_none=decision_id_or_none,
            state_hash_or_none=state_hash_or_none,
        ),
    }

