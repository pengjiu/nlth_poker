from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.opponent_profile import OpponentProfileError, load_opponent_profile_spec, opponent_profile_id, validate_opponent_profile_spec
from poker2.protocol.opponent_suite import OpponentSuiteError, load_opponent_suite_spec, opponent_suite_id, validate_opponent_suite_spec
from poker2.protocol.table_population import TablePopulationError, load_table_population_spec, population_id, validate_table_population_spec


@dataclass(frozen=True)
class OpponentRegistryError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_opponents_root() -> Path:
    return _repo_root() / "specs" / "opponents"


def _canonical_digest_sha256(obj: Any) -> dict[str, str]:
    digest_hex = sha256_hex(canonicalize_json_bytes(obj, strict_mode=True))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def _extract_label(obj: dict[str, Any], *candidates: str) -> str | None:
    for key in candidates:
        v = obj.get(key)
        if isinstance(v, str):
            return v
    return None


def _iter_json_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    paths = [p for p in root.glob("*.json") if p.is_file()]
    paths.sort(key=lambda p: str(p))
    return paths


def build_opponent_registry(
    *,
    opponents_root: Path | None = None,
    strict_mode: bool,
) -> dict[str, dict[str, dict[str, Any]]]:
    root = opponents_root or default_opponents_root()

    profiles_root = root / "profiles"
    populations_root = root / "populations"
    suites_root = root / "suites"

    profiles_by_id: dict[str, dict[str, Any]] = {}
    populations_by_id: dict[str, dict[str, Any]] = {}
    suites_by_id: dict[str, dict[str, Any]] = {}

    # OpponentProfileSpec registry.
    for path in _iter_json_paths(profiles_root):
        try:
            spec = load_opponent_profile_spec(path)
            validate_opponent_profile_spec(spec, strict_mode=strict_mode)
            oid = opponent_profile_id(spec, strict_mode=True)
        except OpponentProfileError as e:
            raise OpponentRegistryError(
                "OPPONENT_PROFILE_INVALID",
                "opponent profile spec invalid",
                {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            ) from e

        label = _extract_label(spec, "opponent_profile_label", "label")
        entry = {
            "opponent_profile_id": oid,
            "opponent_profile_ref": f"path:{path}",
            "opponent_profile_digest": _canonical_digest_sha256(spec),
            "label_or_none": label,
        }
        if oid in profiles_by_id:
            raise OpponentRegistryError(
                "AMBIGUOUS",
                "multiple opponent profile specs produce the same opponent_profile_id",
                {"opponent_profile_id": oid, "refs": [profiles_by_id[oid]["opponent_profile_ref"], entry["opponent_profile_ref"]]},
            )
        profiles_by_id[oid] = entry

    # TablePopulationSpec registry.
    for path in _iter_json_paths(populations_root):
        try:
            spec = load_table_population_spec(path)
            validate_table_population_spec(spec, strict_mode=strict_mode)
            pid = population_id(spec, strict_mode=True)
        except TablePopulationError as e:
            raise OpponentRegistryError(
                "POPULATION_INVALID",
                "table population spec invalid",
                {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            ) from e

        label = _extract_label(spec, "population_label", "label")
        entry = {
            "population_id": pid,
            "population_ref": f"path:{path}",
            "population_digest": _canonical_digest_sha256(spec),
            "label_or_none": label,
        }
        if pid in populations_by_id:
            raise OpponentRegistryError(
                "AMBIGUOUS",
                "multiple table population specs produce the same population_id",
                {"population_id": pid, "refs": [populations_by_id[pid]["population_ref"], entry["population_ref"]]},
            )
        populations_by_id[pid] = entry

    # OpponentSuiteSpec registry.
    for path in _iter_json_paths(suites_root):
        try:
            spec = load_opponent_suite_spec(path)
            validate_opponent_suite_spec(spec, strict_mode=strict_mode)
            sid = opponent_suite_id(spec, strict_mode=True)
        except OpponentSuiteError as e:
            raise OpponentRegistryError(
                "OPPONENT_SUITE_INVALID",
                "opponent suite spec invalid",
                {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            ) from e

        label = _extract_label(spec, "opponent_suite_label", "label")
        entry = {
            "opponent_suite_id": sid,
            "opponent_suite_ref": f"path:{path}",
            "opponent_suite_digest": _canonical_digest_sha256(spec),
            "population_id": spec.get("population_id"),
            "calibration_id": spec.get("calibration_id"),
            "label_or_none": label,
        }
        if sid in suites_by_id:
            raise OpponentRegistryError(
                "AMBIGUOUS",
                "multiple opponent suite specs produce the same opponent_suite_id",
                {"opponent_suite_id": sid, "refs": [suites_by_id[sid]["opponent_suite_ref"], entry["opponent_suite_ref"]]},
            )
        suites_by_id[sid] = entry

    return {"opponent_profiles": profiles_by_id, "populations": populations_by_id, "opponent_suites": suites_by_id}


def resolve_opponent_suite_ref(
    requested_opponents_ref: str,
    *,
    registry: dict[str, dict[str, dict[str, Any]]],
    strict_mode: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(requested_opponents_ref, str) or requested_opponents_ref == "":
        raise OpponentRegistryError("TYPE_ERROR", "requested_opponents_ref must be non-empty string")

    suites = registry.get("opponent_suites")
    if not isinstance(suites, dict):
        raise OpponentRegistryError("TYPE_ERROR", "registry.opponent_suites must be object")

    if requested_opponents_ref.startswith("opponent_suite://"):
        sid = requested_opponents_ref.removeprefix("opponent_suite://")
        try:
            validate_digest_object({"alg": "sha256", "hex": sid}, strict_mode=True)
        except Exception as e:
            raise OpponentRegistryError("ID_INVALID", "opponent_suite:// ref must embed sha256 id", {"error": str(e)}) from e
        entry = suites.get(sid)
        if entry is None:
            raise OpponentRegistryError("MISSING_REF", "opponent_suite_id not found in registry", {"opponent_suite_id": sid})
        trace = {"requested_opponents_ref": requested_opponents_ref, "resolved_opponents_ref": f"opponent_suite://{sid}", "candidates_or_null": None}
        return entry, trace

    # Allow selecting by label (human-friendly); must be unique in strict_mode.
    matches = [e for e in suites.values() if e.get("label_or_none") == requested_opponents_ref]
    if matches:
        if strict_mode and len(matches) != 1:
            raise OpponentRegistryError(
                "AMBIGUOUS",
                "opponent suite label matches multiple candidates",
                {"label": requested_opponents_ref, "candidates": [m["opponent_suite_ref"] for m in matches]},
            )
        matches.sort(key=lambda e: str(e.get("opponent_suite_ref")))
        entry = matches[0]
        trace = {
            "requested_opponents_ref": requested_opponents_ref,
            "resolved_opponents_ref": f"opponent_suite://{entry['opponent_suite_id']}",
            "candidates_or_null": [m["opponent_suite_ref"] for m in matches] if len(matches) > 1 else None,
        }
        return entry, trace

    raise OpponentRegistryError("MISSING_REF", "requested opponent suite not found in registry", {"requested_opponents_ref": requested_opponents_ref})
