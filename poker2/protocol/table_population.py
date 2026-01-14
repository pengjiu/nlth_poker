from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object


@dataclass(frozen=True)
class TablePopulationError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def load_table_population_spec(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise TablePopulationError(
            "JSON_PARSE_FAIL",
            "TablePopulationSpec JSON unreadable",
            {"path": str(path), "error": str(e)},
        ) from e
    if not isinstance(obj, dict):
        raise TablePopulationError("TYPE_ERROR", "TablePopulationSpec must be a JSON object", {"path": str(path)})
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


def table_population_hash_input(spec: Any, *, strict_mode: bool) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise TablePopulationError("TYPE_ERROR", "TablePopulationSpec must be a JSON object")

    def _strip(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if not isinstance(k, str):
                    continue
                if k == "population_id" or _is_label_key(k):
                    continue
                out[k] = _strip(v)
            return out
        if isinstance(obj, list):
            return [_strip(v) for v in obj]
        return obj

    return _strip(spec)


def validate_table_population_spec(spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(spec, dict):
        raise TablePopulationError("TYPE_ERROR", "TablePopulationSpec must be a JSON object")

    observed_id = spec.get("population_id")
    if observed_id is not None:
        if not isinstance(observed_id, str):
            raise TablePopulationError("TYPE_ERROR", "population_id must be str when present")
        validate_digest_object({"alg": "sha256", "hex": observed_id}, strict_mode=True)

    hash_input = table_population_hash_input(spec, strict_mode=strict_mode)
    if strict_mode and _contains_none_string(hash_input):
        raise TablePopulationError("NULL_CONVENTION_VIOLATION", 'TablePopulationSpec hash input must not contain string "none"')

    computed = sha256_hex(canonicalize_json_bytes(hash_input, strict_mode=strict_mode))
    if strict_mode and observed_id is not None and observed_id != computed:
        raise TablePopulationError(
            "ID_MISMATCH",
            "population_id does not match computed population_id",
            {"expected": computed, "observed": observed_id},
        )


def population_id(spec: Any, *, strict_mode: bool) -> str:
    validate_table_population_spec(spec, strict_mode=strict_mode)
    hash_input = table_population_hash_input(spec, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(hash_input, strict_mode=strict_mode))

