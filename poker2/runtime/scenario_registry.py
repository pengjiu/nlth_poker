from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.scenario_package import ScenarioPackageError, load_scenario_package, validate_scenario_package


@dataclass(frozen=True)
class ScenarioRegistryError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_scenarios_root() -> Path:
    return _repo_root() / "specs" / "scenarios"


def _canonical_digest_sha256(obj: Any) -> dict[str, str]:
    digest_hex = sha256_hex(canonicalize_json_bytes(obj, strict_mode=True))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def _iter_scenario_package_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    paths = [p for p in root.glob("*.json") if p.is_file()]
    paths.sort(key=lambda p: str(p))
    return paths


def build_scenario_registry(
    *,
    scenarios_root: Path | None = None,
    strict_mode: bool,
) -> dict[str, dict[str, Any]]:
    root = scenarios_root or default_scenarios_root()

    by_id: dict[str, dict[str, Any]] = {}
    duplicates: dict[str, list[str]] = {}

    for path in _iter_scenario_package_paths(root):
        try:
            pkg = load_scenario_package(path)
            ids = validate_scenario_package(pkg, strict_mode=strict_mode)
        except ScenarioPackageError as e:
            raise ScenarioRegistryError(
                "SCENARIO_PACKAGE_INVALID",
                "scenario package invalid",
                {"path": str(path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            ) from e

        scen_id = ids["scenario_id"]
        label = pkg.get("label")
        label_or_none = label if isinstance(label, str) else None
        entry = {
            "scenario_id": scen_id,
            "scenario_family_key": ids["scenario_family_key"],
            "scenario_package_ref": f"path:{path}",
            "scenario_package_digest": _canonical_digest_sha256(pkg),
            "label_or_none": label_or_none,
        }
        if scen_id in by_id:
            duplicates.setdefault(scen_id, [by_id[scen_id]["scenario_package_ref"]]).append(entry["scenario_package_ref"])
        else:
            by_id[scen_id] = entry

    if duplicates:
        raise ScenarioRegistryError(
            "AMBIGUOUS",
            "multiple scenario packages produce the same scenario_id",
            {"duplicates": duplicates},
        )

    return by_id


def resolve_scenario_ref(
    requested_scenario_ref: str,
    *,
    registry: dict[str, dict[str, Any]],
    strict_mode: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Deterministic resolution per 7.4: unique and auditable; input ref does not enter options_hash.
    if not isinstance(requested_scenario_ref, str) or requested_scenario_ref == "":
        raise ScenarioRegistryError("TYPE_ERROR", "requested_scenario_ref must be non-empty string")

    if requested_scenario_ref.startswith("scenario://"):
        scen_id = requested_scenario_ref.removeprefix("scenario://")
        try:
            validate_digest_object({"alg": "sha256", "hex": scen_id}, strict_mode=True)
        except Exception as e:
            raise ScenarioRegistryError("ID_INVALID", "scenario:// ref must embed sha256 id", {"error": str(e)}) from e
        entry = registry.get(scen_id)
        if entry is None:
            raise ScenarioRegistryError("MISSING_REF", "scenario_id not found in registry", {"scenario_id": scen_id})
        trace = {"requested_scenario_ref": requested_scenario_ref, "resolved_scenario_ref": f"scenario://{scen_id}", "candidates_or_null": None}
        return entry, trace

    # Allow selecting by label (human-friendly); must be unique in strict_mode.
    matches = [e for e in registry.values() if e.get("label_or_none") == requested_scenario_ref]
    if matches:
        if strict_mode and len(matches) != 1:
            raise ScenarioRegistryError(
                "AMBIGUOUS",
                "scenario label matches multiple candidates",
                {"label": requested_scenario_ref, "candidates": [m["scenario_package_ref"] for m in matches]},
            )
        matches.sort(key=lambda e: str(e.get("scenario_package_ref")))
        entry = matches[0]
        trace = {"requested_scenario_ref": requested_scenario_ref, "resolved_scenario_ref": f"scenario://{entry['scenario_id']}", "candidates_or_null": [m["scenario_package_ref"] for m in matches] if len(matches) > 1 else None}
        return entry, trace

    raise ScenarioRegistryError("MISSING_REF", "requested scenario not found in registry", {"requested_scenario_ref": requested_scenario_ref})

