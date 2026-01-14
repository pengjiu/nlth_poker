from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.protocol.scenario import ScenarioError, scenario_family_key, scenario_id


@dataclass(frozen=True)
class ScenarioPackageError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


_CLOSURE_KEYS = (
    "scenario_schema_id",
    "ruleset_id",
    "triad",
    "schema_hash",
    "abstraction_hash",
    "preflop_ref",
    "postflop_ref",
    "opponent_suite_id",
    "population_id",
    "mw_ladder_id",
)


def load_scenario_package(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ScenarioPackageError("JSON_PARSE_FAIL", "ScenarioPackage JSON unreadable", {"error": str(e), "path": str(path)}) from e
    if not isinstance(obj, dict):
        raise ScenarioPackageError("TYPE_ERROR", "ScenarioPackage must be JSON object", {"path": str(path)})
    return obj


def scenario_closure_from_package(pkg: Any, *, strict_mode: bool) -> dict[str, Any]:
    if not isinstance(pkg, dict):
        raise ScenarioPackageError("TYPE_ERROR", "ScenarioPackage must be JSON object")
    missing = [k for k in _CLOSURE_KEYS if k not in pkg]
    if missing:
        raise ScenarioPackageError("MISSING_FIELDS", "ScenarioPackage missing required closure fields", {"missing": missing})
    return {k: pkg[k] for k in _CLOSURE_KEYS}


def validate_scenario_package(pkg: Any, *, strict_mode: bool) -> dict[str, str]:
    closure = scenario_closure_from_package(pkg, strict_mode=strict_mode)
    try:
        scen_id = scenario_id(closure, strict_mode=strict_mode)
    except ScenarioError as e:
        raise ScenarioPackageError("SCENARIO_CLOSURE_INVALID", "ScenarioPackage closure invalid", {"error": {"code": e.code, "message": e.message, "details": e.details}}) from e

    fam_key = scenario_family_key(
        scenario_id_hex=scen_id,
        ruleset_id=closure["ruleset_id"],
        abstraction_hash=closure["abstraction_hash"],
        strict_mode=strict_mode,
    )

    # If file includes derived identifiers, they must match.
    if "scenario_id" in pkg:
        observed = pkg.get("scenario_id")
        if not isinstance(observed, str):
            raise ScenarioPackageError("TYPE_ERROR", "scenario_id must be string when present")
        if observed != scen_id:
            raise ScenarioPackageError(
                "SCENARIO_ID_MISMATCH",
                "scenario_id does not match computed scenario_id",
                {"expected": scen_id, "observed": observed},
            )

    if "scenario_family_key" in pkg:
        observed = pkg.get("scenario_family_key")
        if not isinstance(observed, str):
            raise ScenarioPackageError("TYPE_ERROR", "scenario_family_key must be string when present")
        if observed != fam_key:
            raise ScenarioPackageError(
                "SCENARIO_FAMILY_KEY_MISMATCH",
                "scenario_family_key does not match computed scenario_family_key",
                {"expected": fam_key, "observed": observed},
            )

    return {"scenario_id": scen_id, "scenario_family_key": fam_key}

