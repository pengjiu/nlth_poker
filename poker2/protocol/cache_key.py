from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object


@dataclass(frozen=True)
class CacheKeyError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _validate_sha256_hex_string(value: Any, *, field: str) -> None:
    if not isinstance(value, str):
        raise CacheKeyError("TYPE_ERROR", f"{field} must be sha256 hex string")
    try:
        validate_digest_object({"alg": "sha256", "hex": value}, strict_mode=True)
    except Exception as e:
        raise CacheKeyError("ID_INVALID", f"{field} must be sha256 hex string", {"error": str(e)}) from e


def validate_cache_key(cache_key: Any, *, strict_mode: bool) -> None:
    if not isinstance(cache_key, dict):
        raise CacheKeyError("TYPE_ERROR", "CacheKey must be a JSON object")

    required = ("state_hash", "scenario_id", "schema_hash", "engine_build_id", "options_hash")
    missing = [k for k in required if k not in cache_key]
    if missing:
        raise CacheKeyError("MISSING_FIELDS", f"missing required fields: {missing}")
    if strict_mode:
        extra = set(cache_key.keys()) - set(required)
        if extra:
            raise CacheKeyError("EXTRA_FIELDS", "CacheKey has extra fields", {"extra": sorted(extra)})

    _validate_sha256_hex_string(cache_key.get("state_hash"), field="CacheKey.state_hash")
    _validate_sha256_hex_string(cache_key.get("scenario_id"), field="CacheKey.scenario_id")
    _validate_sha256_hex_string(cache_key.get("schema_hash"), field="CacheKey.schema_hash")

    engine_build_id = cache_key.get("engine_build_id")
    if engine_build_id is not None:
        _validate_sha256_hex_string(engine_build_id, field="CacheKey.engine_build_id")

    _validate_sha256_hex_string(cache_key.get("options_hash"), field="CacheKey.options_hash")


def cache_key_id(cache_key: Any, *, strict_mode: bool) -> str:
    validate_cache_key(cache_key, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(cache_key, strict_mode=strict_mode))


def cache_key_v1(
    *,
    state_hash: str,
    scenario_id: str,
    schema_hash: str,
    engine_build_id: str | None,
    options_hash: str,
    strict_mode: bool,
) -> dict[str, Any]:
    # Minimal CacheKey closure per ARCHIETECTURE.md §3.7.
    obj: dict[str, Any] = {
        "state_hash": state_hash,
        "scenario_id": scenario_id,
        "schema_hash": schema_hash,
        "engine_build_id": engine_build_id,
        "options_hash": options_hash,
    }
    validate_cache_key(obj, strict_mode=strict_mode)
    return obj

