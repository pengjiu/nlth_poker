from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.enums import POLICY_KIND_VALUES


@dataclass(frozen=True)
class PolicyError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def policy_params_digest(params: Any, *, strict_mode: bool) -> dict[str, str]:
    digest_hex = sha256_hex(canonicalize_json_bytes(params, strict_mode=strict_mode))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def load_policy_spec(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise PolicyError("JSON_PARSE_FAIL", "PolicySpec JSON unreadable", {"path": str(path), "error": str(e)}) from e
    if not isinstance(obj, dict):
        raise PolicyError("TYPE_ERROR", "PolicySpec must be a JSON object", {"path": str(path)})
    return obj


def _contains_none_string(value: Any) -> bool:
    # Null Convention (ARCHIETECTURE.md 0.1.3): forbid using string "none" to represent null in any hash input.
    if value == "none":
        return True
    if isinstance(value, dict):
        return any(_contains_none_string(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_none_string(v) for v in value)
    return False


def _is_label_key(key: str) -> bool:
    return key.endswith("_label") or key.endswith("_alias") or key == "latest"


def policy_closure_from_spec(spec: Any, *, strict_mode: bool) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise PolicyError("TYPE_ERROR", "PolicySpec must be a JSON object")
    required = ("policy_kind", "policy_deps", "policy_params_digest", "stochastic")
    missing = [k for k in required if k not in spec]
    if missing:
        raise PolicyError("MISSING_FIELDS", f"missing required fields: {missing}")
    return {k: spec[k] for k in required}


def validate_policy_spec(spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(spec, dict):
        raise PolicyError("TYPE_ERROR", "PolicySpec must be a JSON object")

    kind = spec.get("policy_kind")
    if kind not in POLICY_KIND_VALUES:
        raise PolicyError("UNSUPPORTED_VALUE", f"unsupported policy_kind: {kind!r}")

    deps = spec.get("policy_deps")
    if not isinstance(deps, list):
        raise PolicyError("TYPE_ERROR", "policy_deps must be array")
    for idx, dep in enumerate(deps):
        if not isinstance(dep, dict):
            raise PolicyError("TYPE_ERROR", "policy_deps items must be objects", {"index": idx})
        if "artifact_ref" not in dep or "digest" not in dep:
            raise PolicyError("MISSING_FIELDS", "policy_deps items must include {artifact_ref,digest}", {"index": idx})
        if strict_mode:
            extra = set(dep.keys()) - {"artifact_ref", "digest"}
            if extra:
                raise PolicyError("EXTRA_FIELDS", "policy_deps item has extra fields", {"index": idx, "extra": sorted(extra)})
        if not isinstance(dep.get("artifact_ref"), str):
            raise PolicyError("TYPE_ERROR", "policy_deps.artifact_ref must be str", {"index": idx})
        validate_digest_object(dep.get("digest"), strict_mode=True)

    pd = spec.get("policy_params_digest")
    validate_digest_object(pd, strict_mode=True)

    stoch = spec.get("stochastic")
    if not isinstance(stoch, bool):
        raise PolicyError("TYPE_ERROR", "stochastic must be bool")

    # Optional derived identifier field (3.19.3.1): when present, it must match computed policy_id.
    observed_id = spec.get("policy_id")
    if observed_id is not None:
        if not isinstance(observed_id, str):
            raise PolicyError("TYPE_ERROR", "policy_id must be str when present")
        validate_digest_object({"alg": "sha256", "hex": observed_id}, strict_mode=True)

    if strict_mode:
        allowed = {"policy_kind", "policy_deps", "policy_params_digest", "stochastic", "policy_id"}
        extra = {k for k in spec.keys() if k not in allowed and not (isinstance(k, str) and _is_label_key(k))}
        if extra:
            raise PolicyError("EXTRA_FIELDS", "PolicySpec has extra fields in strict_mode", {"extra": sorted(extra)})

    closure = policy_closure_from_spec(spec, strict_mode=strict_mode)
    if strict_mode and _contains_none_string(closure):
        raise PolicyError("NULL_CONVENTION_VIOLATION", 'PolicySpec hash input must not contain string "none"')

    computed = sha256_hex(canonicalize_json_bytes(closure, strict_mode=strict_mode))
    if strict_mode and observed_id is not None and observed_id != computed:
        raise PolicyError("ID_MISMATCH", "policy_id does not match computed policy_id", {"expected": computed, "observed": observed_id})


def policy_id(spec: Any, *, strict_mode: bool) -> str:
    validate_policy_spec(spec, strict_mode=strict_mode)
    closure = policy_closure_from_spec(spec, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(closure, strict_mode=strict_mode))


def baseline_policy_spec(*, strict_mode: bool) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    path = root / "specs" / "policies" / "internal_baseline_policy_v1.json"
    spec = load_policy_spec(path)
    validate_policy_spec(spec, strict_mode=strict_mode)
    return spec


def default_internal_policy_spec(*, strict_mode: bool) -> tuple[dict[str, Any], str]:
    spec = baseline_policy_spec(strict_mode=strict_mode)
    return spec, policy_id(spec, strict_mode=strict_mode)
