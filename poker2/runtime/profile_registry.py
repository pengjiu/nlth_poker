from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.profile import ProfileError, load_profile_spec, profile_id, validate_profile_spec


@dataclass(frozen=True)
class ProfileRegistryError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_profiles_root() -> Path:
    return _repo_root() / "specs" / "profiles"


def _canonical_digest_sha256(obj: Any) -> dict[str, str]:
    digest_hex = sha256_hex(canonicalize_json_bytes(obj, strict_mode=True))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def _iter_profile_spec_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    paths = [p for p in root.glob("*.json") if p.is_file()]
    paths.sort(key=lambda p: str(p))
    return paths


def build_profile_registry(
    *,
    profiles_root: Path | None = None,
    strict_mode: bool,
) -> dict[str, dict[str, Any]]:
    root = profiles_root or default_profiles_root()

    by_id: dict[str, dict[str, Any]] = {}
    duplicates: dict[str, list[str]] = {}

    for path in _iter_profile_spec_paths(root):
        try:
            spec = load_profile_spec(path)
            validate_profile_spec(spec, strict_mode=strict_mode)
            pid = profile_id(spec, strict_mode=strict_mode)
        except ProfileError as e:
            raise ProfileRegistryError(
                "PROFILE_SPEC_INVALID",
                "profile spec invalid",
                {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            ) from e

        label = spec.get("profile_label")
        label_or_none = label if isinstance(label, str) else None
        entry = {
            "profile_id": pid,
            "profile_spec_ref": f"path:{path}",
            "profile_spec_digest": _canonical_digest_sha256(spec),
            "label_or_none": label_or_none,
        }
        if pid in by_id:
            duplicates.setdefault(pid, [by_id[pid]["profile_spec_ref"]]).append(entry["profile_spec_ref"])
        else:
            by_id[pid] = entry

    if duplicates:
        raise ProfileRegistryError("AMBIGUOUS", "multiple profile specs produce the same profile_id", {"duplicates": duplicates})

    return by_id


def resolve_profile_ref(
    requested_profile_ref: str,
    *,
    registry: dict[str, dict[str, Any]],
    strict_mode: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(requested_profile_ref, str) or requested_profile_ref == "":
        raise ProfileRegistryError("TYPE_ERROR", "requested_profile_ref must be non-empty string")

    if requested_profile_ref.startswith("profile://"):
        pid = requested_profile_ref.removeprefix("profile://")
        try:
            validate_digest_object({"alg": "sha256", "hex": pid}, strict_mode=True)
        except Exception as e:
            raise ProfileRegistryError("ID_INVALID", "profile:// ref must embed sha256 id", {"error": str(e)}) from e
        entry = registry.get(pid)
        if entry is None:
            raise ProfileRegistryError("MISSING_REF", "profile_id not found in registry", {"profile_id": pid})
        trace = {"requested_profile_ref": requested_profile_ref, "resolved_profile_ref": f"profile://{pid}", "candidates_or_null": None}
        return entry, trace

    matches = [e for e in registry.values() if e.get("label_or_none") == requested_profile_ref]
    if matches:
        if strict_mode and len(matches) != 1:
            raise ProfileRegistryError(
                "AMBIGUOUS",
                "profile label matches multiple candidates",
                {"label": requested_profile_ref, "candidates": [m["profile_spec_ref"] for m in matches]},
            )
        matches.sort(key=lambda e: str(e.get("profile_spec_ref")))
        entry = matches[0]
        trace = {
            "requested_profile_ref": requested_profile_ref,
            "resolved_profile_ref": f"profile://{entry['profile_id']}",
            "candidates_or_null": [m["profile_spec_ref"] for m in matches] if len(matches) > 1 else None,
        }
        return entry, trace

    raise ProfileRegistryError("MISSING_REF", "requested profile not found in registry", {"requested_profile_ref": requested_profile_ref})

