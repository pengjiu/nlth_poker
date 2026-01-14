from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from poker2.contractkit import canonicalize_json_bytes, validate_digest_object


@dataclass(frozen=True)
class ArtifactsError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_artifacts_root() -> Path:
    # Repo-local, gitignored by policy.
    return _repo_root() / "artifacts"


def _validate_sha256_hex_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ArtifactsError("TYPE_ERROR", f"{field} must be sha256 hex string")
    try:
        validate_digest_object({"alg": "sha256", "hex": value}, strict_mode=True)
    except Exception as e:
        raise ArtifactsError("ID_INVALID", f"{field} must be sha256 hex string: {e}") from e
    return value


def run_output_dir(
    *,
    run_id: str,
    artifacts_root: Path | None = None,
    run_instance_uuid: str | None = None,
) -> Path:
    _validate_sha256_hex_string(run_id, field="run_id")
    root = artifacts_root or default_artifacts_root()
    base = root / run_id
    if run_instance_uuid is None:
        return base
    if not isinstance(run_instance_uuid, str):
        raise ArtifactsError("TYPE_ERROR", "run_instance_uuid must be str or null")
    return base / run_instance_uuid


def run_artifact_paths(
    *,
    run_id: str,
    artifacts_root: Path | None = None,
    run_instance_uuid: str | None = None,
) -> dict[str, Path]:
    out_dir = run_output_dir(run_id=run_id, artifacts_root=artifacts_root, run_instance_uuid=run_instance_uuid)
    manifest_dir = out_dir / "manifest"
    eventstream_dir = out_dir / "eventstream"
    report_dir = out_dir / "report"
    return {
        "run_dir": out_dir,
        "manifest_dir": manifest_dir,
        "eventstream_dir": eventstream_dir,
        "report_dir": report_dir,
        "run_manifest_path": manifest_dir / "run_manifest.json",
        "eventstream_path": eventstream_dir / "eventstream.ndjson",
        "report_path": report_dir / "report.json",
    }


def write_canonical_json(path: Path, obj: Any, *, strict_mode: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonicalize_json_bytes(obj, strict_mode=strict_mode) + b"\n")


def write_canonical_ndjson(path: Path, objs: Iterable[Any], *, strict_mode: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [canonicalize_json_bytes(obj, strict_mode=strict_mode) for obj in objs]
    # NDJSON is LF-delimited regardless of platform.
    path.write_bytes(b"\n".join(lines) + b"\n")
