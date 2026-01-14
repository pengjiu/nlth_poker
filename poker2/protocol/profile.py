from __future__ import annotations

# ProfileSpec contract helpers (ARCHIETECTURE.md 3.20).

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object


@dataclass(frozen=True)
class ProfileError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def load_profile_spec(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ProfileError("JSON_PARSE_FAIL", "ProfileSpec JSON unreadable", {"path": str(path), "error": str(e)}) from e
    if not isinstance(obj, dict):
        raise ProfileError("TYPE_ERROR", "ProfileSpec must be a JSON object", {"path": str(path)})
    return obj


def _is_label_key(key: str) -> bool:
    return key.endswith("_label") or key.endswith("_alias") or key == "latest"


def _contains_none_string(value: Any) -> bool:
    if value == "none":
        return True
    if isinstance(value, dict):
        return any(_contains_none_string(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_none_string(v) for v in value)
    return False


def _strip_hash_excluded_fields(value: Any) -> Any:
    # Exclude *_label/_alias/latest everywhere from ProfileSpec hash input (ARCHIETECTURE.md 0.1.2).
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _is_label_key(k):
                continue
            out[k] = _strip_hash_excluded_fields(v)
        return out
    if isinstance(value, list):
        return [_strip_hash_excluded_fields(v) for v in value]
    return value


def profile_hash_input(profile_spec: Any, *, strict_mode: bool) -> dict[str, Any]:
    if not isinstance(profile_spec, dict):
        raise ProfileError("TYPE_ERROR", "ProfileSpec must be a JSON object")
    # profile_id is an optional derived identifier (3.20.1) and must not enter hash input.
    base = {k: v for k, v in profile_spec.items() if k != "profile_id"}
    stripped = _strip_hash_excluded_fields(base)
    if strict_mode and _contains_none_string(stripped):
        raise ProfileError("NULL_CONVENTION_VIOLATION", 'ProfileSpec hash input must not contain string "none"')
    return stripped


def validate_profile_spec(profile_spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(profile_spec, dict):
        raise ProfileError("TYPE_ERROR", "ProfileSpec must be a JSON object")

    observed_id = profile_spec.get("profile_id")
    if observed_id is not None:
        if not isinstance(observed_id, str):
            raise ProfileError("TYPE_ERROR", "profile_id must be str when present")
        try:
            validate_digest_object({"alg": "sha256", "hex": observed_id}, strict_mode=True)
        except Exception as e:
            raise ProfileError("ID_INVALID", "profile_id must be sha256 hex when present", {"error": str(e)}) from e

    hash_input = profile_hash_input(profile_spec, strict_mode=strict_mode)
    computed = sha256_hex(canonicalize_json_bytes(hash_input, strict_mode=strict_mode))
    if strict_mode and observed_id is not None and observed_id != computed:
        raise ProfileError("ID_MISMATCH", "profile_id does not match computed profile_id", {"expected": computed, "observed": observed_id})


def profile_id(profile_spec: Any, *, strict_mode: bool) -> str:
    validate_profile_spec(profile_spec, strict_mode=strict_mode)
    hash_input = profile_hash_input(profile_spec, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(hash_input, strict_mode=strict_mode))


def auto_profile_spec_throughput() -> dict[str, Any]:
    cpu_count = os.cpu_count() or 1

    if cpu_count <= 4:
        workers = 1
        mc_budget = 2_000
    elif cpu_count <= 8:
        workers = 2
        mc_budget = 5_000
    elif cpu_count <= 16:
        workers = 4
        mc_budget = 12_000
    else:
        workers = 8
        mc_budget = 25_000

    return {
        "profile_schema_id": "profile_spec_v1",
        "purpose": "throughput",
        "concurrency": {"workers": workers},
        "engine_budget": {"montecarlo_rollouts_per_decision": mc_budget},
    }


def default_internal_profile_spec(*, strict_mode: bool) -> tuple[dict[str, Any], str]:
    root = Path(__file__).resolve().parents[2]
    path = root / "specs" / "profiles" / "internal_profile_v1.json"
    spec = load_profile_spec(path)
    validate_profile_spec(spec, strict_mode=strict_mode)
    pid = profile_id(spec, strict_mode=strict_mode)
    return spec, pid
