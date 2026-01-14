from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from poker2.contractkit import canonicalize_json_bytes, validate_digest_object


@dataclass(frozen=True)
class ArtifactStoreError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def internal_fixture_artifacts_root() -> Path:
    return _repo_root() / "fixtures" / "internal" / "artifacts"


def runtime_artifacts_store_root() -> Path:
    # Repo-local, gitignored by policy.
    return _repo_root() / "artifacts" / "store"


def default_artifact_search_roots() -> list[Path]:
    # Deterministic search order; paths are execution-only and must not affect options_hash.
    return [internal_fixture_artifacts_root(), runtime_artifacts_store_root()]


def _artifact_id_from_ref(ref: Any) -> str:
    if not isinstance(ref, str):
        raise ArtifactStoreError("TYPE_ERROR", "artifact_ref must be string")
    if not ref.startswith("artifact://"):
        raise ArtifactStoreError("UNSUPPORTED_VALUE", "unsupported artifact_ref scheme (expected artifact://{sha256})", {"artifact_ref": ref})
    hex_id = ref.removeprefix("artifact://")
    try:
        validate_digest_object({"alg": "sha256", "hex": hex_id}, strict_mode=True)
    except Exception as e:
        raise ArtifactStoreError("ID_INVALID", "artifact_ref must embed sha256 hex id", {"artifact_ref": ref, "error": str(e)}) from e
    return hex_id


def resolve_artifact_path(
    artifact_ref: str,
    *,
    search_roots: Iterable[Path] | None = None,
    suffixes: tuple[str, ...] = (".json", ".bin"),
) -> Path:
    artifact_id = _artifact_id_from_ref(artifact_ref)
    roots = list(search_roots) if search_roots is not None else default_artifact_search_roots()
    candidates: list[Path] = []
    for root in roots:
        for suf in suffixes:
            p = root / f"{artifact_id}{suf}"
            if p.exists():
                candidates.append(p)
    if not candidates:
        raise ArtifactStoreError(
            "ARTIFACT_NOT_FOUND",
            "artifact_ref not found in search roots",
            {"artifact_ref": artifact_ref, "searched": [str(r) for r in roots]},
        )
    candidates.sort(key=lambda p: str(p))
    return candidates[0]


def write_artifact_json(
    obj: Any,
    *,
    artifact_id: str,
    out_root: Path | None = None,
    strict_mode: bool = True,
) -> Path:
    try:
        validate_digest_object({"alg": "sha256", "hex": artifact_id}, strict_mode=True)
    except Exception as e:
        raise ArtifactStoreError("ID_INVALID", "artifact_id must be sha256 hex", {"error": str(e)}) from e

    root = out_root or runtime_artifacts_store_root()
    path = root / f"{artifact_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonicalize_json_bytes(obj, strict_mode=strict_mode) + b"\n")
    return path


def write_artifact_bytes(
    data: bytes,
    *,
    artifact_id: str,
    suffix: str = ".bin",
    out_root: Path | None = None,
) -> Path:
    try:
        validate_digest_object({"alg": "sha256", "hex": artifact_id}, strict_mode=True)
    except Exception as e:
        raise ArtifactStoreError("ID_INVALID", "artifact_id must be sha256 hex", {"error": str(e)}) from e
    if not isinstance(suffix, str) or not suffix.startswith("."):
        raise ArtifactStoreError("SUFFIX_INVALID", "suffix must start with '.'", {"suffix": suffix})

    root = out_root or runtime_artifacts_store_root()
    path = root / f"{artifact_id}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
