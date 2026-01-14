from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object


@dataclass(frozen=True)
class OpponentSuiteError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def load_opponent_suite_spec(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise OpponentSuiteError(
            "JSON_PARSE_FAIL",
            "OpponentSuiteSpec JSON unreadable",
            {"path": str(path), "error": str(e)},
        ) from e
    if not isinstance(obj, dict):
        raise OpponentSuiteError("TYPE_ERROR", "OpponentSuiteSpec must be a JSON object", {"path": str(path)})
    return obj


def _contains_none_string(value: Any) -> bool:
    if value == "none":
        return True
    if isinstance(value, dict):
        return any(_contains_none_string(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_none_string(v) for v in value)
    return False


def _is_label_key(key: str) -> bool:
    return key.endswith("_label") or key.endswith("_alias") or key == "latest"


def opponent_suite_hash_input(spec: Any, *, strict_mode: bool) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise OpponentSuiteError("TYPE_ERROR", "OpponentSuiteSpec must be a JSON object")

    def _strip(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if not isinstance(k, str):
                    continue
                # 0.1.2: labels/aliases/latest are execution-only.
                if _is_label_key(k):
                    continue
                # 3.16: purpose is for display/filtering only; MUST NOT enter any *_hash input.
                if k == "purpose":
                    continue
                # 3.16.1: derived identifier fields must not enter hash input.
                if k == "opponent_suite_id":
                    continue
                out[k] = _strip(v)
            return out
        if isinstance(obj, list):
            return [_strip(v) for v in obj]
        return obj

    return _strip(spec)


def validate_opponent_suite_spec(spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(spec, dict):
        raise OpponentSuiteError("TYPE_ERROR", "OpponentSuiteSpec must be a JSON object")

    # 3.16: MUST reference a TablePopulationSpec (3.15).
    pop_id = spec.get("population_id")
    if not isinstance(pop_id, str):
        raise OpponentSuiteError("MISSING_FIELDS", "population_id missing or not string")
    validate_digest_object({"alg": "sha256", "hex": pop_id}, strict_mode=True)

    # Optional "needs calibration" signal: when present, it must be content-hash id (3.17).
    calib_id = spec.get("calibration_id")
    if calib_id is not None:
        if not isinstance(calib_id, str):
            raise OpponentSuiteError("TYPE_ERROR", "calibration_id must be str or null")
        validate_digest_object({"alg": "sha256", "hex": calib_id}, strict_mode=True)

    observed_id = spec.get("opponent_suite_id")
    if observed_id is not None:
        if not isinstance(observed_id, str):
            raise OpponentSuiteError("TYPE_ERROR", "opponent_suite_id must be str when present")
        validate_digest_object({"alg": "sha256", "hex": observed_id}, strict_mode=True)

    hash_input = opponent_suite_hash_input(spec, strict_mode=strict_mode)
    if strict_mode and _contains_none_string(hash_input):
        raise OpponentSuiteError("NULL_CONVENTION_VIOLATION", 'OpponentSuiteSpec hash input must not contain string "none"')

    computed = sha256_hex(canonicalize_json_bytes(hash_input, strict_mode=strict_mode))
    if strict_mode and observed_id is not None and observed_id != computed:
        raise OpponentSuiteError(
            "ID_MISMATCH",
            "opponent_suite_id does not match computed opponent_suite_id",
            {"expected": computed, "observed": observed_id},
        )


def opponent_suite_id(spec: Any, *, strict_mode: bool) -> str:
    validate_opponent_suite_spec(spec, strict_mode=strict_mode)
    hash_input = opponent_suite_hash_input(spec, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(hash_input, strict_mode=strict_mode))

