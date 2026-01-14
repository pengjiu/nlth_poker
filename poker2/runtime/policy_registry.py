from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.policy import PolicyError, load_policy_spec, policy_id, validate_policy_spec


@dataclass(frozen=True)
class PolicyRegistryError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_policies_root() -> Path:
    return _repo_root() / "specs" / "policies"


def _canonical_digest_sha256(obj: Any) -> dict[str, str]:
    digest_hex = sha256_hex(canonicalize_json_bytes(obj, strict_mode=True))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def _iter_policy_spec_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    paths = [p for p in root.glob("*.json") if p.is_file()]
    paths.sort(key=lambda p: str(p))
    return paths


def build_policy_registry(
    *,
    policies_root: Path | None = None,
    strict_mode: bool,
) -> dict[str, dict[str, Any]]:
    root = policies_root or default_policies_root()

    by_id: dict[str, dict[str, Any]] = {}
    duplicates: dict[str, list[str]] = {}

    for path in _iter_policy_spec_paths(root):
        try:
            spec = load_policy_spec(path)
            validate_policy_spec(spec, strict_mode=strict_mode)
            pid = policy_id(spec, strict_mode=strict_mode)
        except PolicyError as e:
            raise PolicyRegistryError(
                "POLICY_SPEC_INVALID",
                "policy spec invalid",
                {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            ) from e

        label = spec.get("policy_label")
        label_or_none = label if isinstance(label, str) else None
        entry = {
            "policy_id": pid,
            "policy_spec_ref": f"path:{path}",
            "policy_spec_digest": _canonical_digest_sha256(spec),
            "label_or_none": label_or_none,
        }
        if pid in by_id:
            duplicates.setdefault(pid, [by_id[pid]["policy_spec_ref"]]).append(entry["policy_spec_ref"])
        else:
            by_id[pid] = entry

    if duplicates:
        raise PolicyRegistryError("AMBIGUOUS", "multiple policy specs produce the same policy_id", {"duplicates": duplicates})

    return by_id


def resolve_policy_ref(
    requested_policy_ref: str,
    *,
    registry: dict[str, dict[str, Any]],
    strict_mode: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Deterministic resolution: requested ref must resolve uniquely; input ref does not enter options_hash.
    if not isinstance(requested_policy_ref, str) or requested_policy_ref == "":
        raise PolicyRegistryError("TYPE_ERROR", "requested_policy_ref must be non-empty string")

    if requested_policy_ref.startswith("policy://"):
        pid = requested_policy_ref.removeprefix("policy://")
        try:
            validate_digest_object({"alg": "sha256", "hex": pid}, strict_mode=True)
        except Exception as e:
            raise PolicyRegistryError("ID_INVALID", "policy:// ref must embed sha256 id", {"error": str(e)}) from e
        entry = registry.get(pid)
        if entry is None:
            raise PolicyRegistryError("MISSING_REF", "policy_id not found in registry", {"policy_id": pid})
        trace = {"requested_policy_ref": requested_policy_ref, "resolved_policy_ref": f"policy://{pid}", "candidates_or_null": None}
        return entry, trace

    matches = [e for e in registry.values() if e.get("label_or_none") == requested_policy_ref]
    if matches:
        if strict_mode and len(matches) != 1:
            raise PolicyRegistryError(
                "AMBIGUOUS",
                "policy label matches multiple candidates",
                {"label": requested_policy_ref, "candidates": [m["policy_spec_ref"] for m in matches]},
            )
        matches.sort(key=lambda e: str(e.get("policy_spec_ref")))
        entry = matches[0]
        trace = {
            "requested_policy_ref": requested_policy_ref,
            "resolved_policy_ref": f"policy://{entry['policy_id']}",
            "candidates_or_null": [m["policy_spec_ref"] for m in matches] if len(matches) > 1 else None,
        }
        return entry, trace

    raise PolicyRegistryError("MISSING_REF", "requested policy not found in registry", {"requested_policy_ref": requested_policy_ref})

