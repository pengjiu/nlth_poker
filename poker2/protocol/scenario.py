from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object


@dataclass(frozen=True)
class ScenarioError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def scenario_id(closure: Any, *, strict_mode: bool) -> str:
    if not isinstance(closure, dict):
        raise ScenarioError("TYPE_ERROR", "ScenarioSpecClosure must be a JSON object")
    required = (
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
    missing = [k for k in required if k not in closure]
    if missing:
        raise ScenarioError("MISSING_FIELDS", f"missing required fields: {missing}")

    schema_id = closure.get("scenario_schema_id")
    if schema_id != "scenario_spec_v1":
        raise ScenarioError("UNSUPPORTED_VALUE", "unsupported scenario_schema_id")

    for field_name in ("ruleset_id", "schema_hash", "abstraction_hash"):
        v = closure.get(field_name)
        if not isinstance(v, str):
            raise ScenarioError("TYPE_ERROR", f"{field_name} must be sha256 hex string")
        try:
            validate_digest_object({"alg": "sha256", "hex": v}, strict_mode=True)
        except Exception as e:
            raise ScenarioError("ID_INVALID", f"{field_name} must be sha256 hex: {e}") from e

    triad_obj = closure.get("triad")
    if not isinstance(triad_obj, dict):
        raise ScenarioError("TYPE_ERROR", "triad must be object")
    for field_name in ("action_bins_id", "obs_schema_id", "rake_id"):
        v = triad_obj.get(field_name)
        if not isinstance(v, str):
            raise ScenarioError("TYPE_ERROR", f"triad.{field_name} must be sha256 hex string")
        try:
            validate_digest_object({"alg": "sha256", "hex": v}, strict_mode=True)
        except Exception as e:
            raise ScenarioError("ID_INVALID", f"triad.{field_name} must be sha256 hex: {e}") from e

    for nullable_id_field in ("opponent_suite_id", "population_id", "mw_ladder_id"):
        v = closure.get(nullable_id_field)
        if v is None:
            continue
        if not isinstance(v, str):
            raise ScenarioError("TYPE_ERROR", f"{nullable_id_field} must be sha256 hex string or null")
        try:
            validate_digest_object({"alg": "sha256", "hex": v}, strict_mode=True)
        except Exception as e:
            raise ScenarioError("ID_INVALID", f"{nullable_id_field} must be sha256 hex: {e}") from e

    def _validate_asset_ref(value: Any, *, field: str) -> None:
        if value is None:
            return
        if not isinstance(value, dict):
            raise ScenarioError("TYPE_ERROR", f"{field} must be object or null")
        if "artifact_ref" not in value or "digest" not in value:
            raise ScenarioError("MISSING_FIELDS", f"{field} must include {{artifact_ref,digest}}")
        if strict_mode:
            extra = set(value.keys()) - {"artifact_ref", "digest"}
            if extra:
                raise ScenarioError("EXTRA_FIELDS", f"{field} has extra fields", {"extra": sorted(extra)})
        ref = value.get("artifact_ref")
        if not isinstance(ref, str):
            raise ScenarioError("TYPE_ERROR", f"{field}.artifact_ref must be string")
        dig = value.get("digest")
        try:
            validate_digest_object(dig, strict_mode=True)
        except Exception as e:
            raise ScenarioError("DIGEST_INVALID", f"{field}.digest invalid: {e}") from e

        if ref.startswith("path:"):
            rel = ref.removeprefix("path:")
            # Must be relative (no host absolute path leakage).
            if rel.startswith(("/", "\\", "~")) or (len(rel) >= 2 and rel[1] == ":" and rel[0].isalpha()):
                raise ScenarioError("PATH_REF_NOT_RELATIVE", f"{field}.artifact_ref must be relative for path:", {"artifact_ref": ref})

    _validate_asset_ref(closure.get("preflop_ref"), field="preflop_ref")
    _validate_asset_ref(closure.get("postflop_ref"), field="postflop_ref")

    return sha256_hex(canonicalize_json_bytes(closure, strict_mode=strict_mode))


def scenario_family_key(
    *,
    scenario_id_hex: str,
    ruleset_id: str,
    abstraction_hash: str,
    strict_mode: bool,
) -> str:
    # scenario_family_key := hash(canonicalized {scenario_id, ruleset_id, abstraction_hash})
    for field_name, value in (("scenario_id", scenario_id_hex), ("ruleset_id", ruleset_id), ("abstraction_hash", abstraction_hash)):
        try:
            validate_digest_object({"alg": "sha256", "hex": value}, strict_mode=True)
        except Exception as e:
            raise ScenarioError("ID_INVALID", f"{field_name} must be sha256 hex: {e}") from e
    obj: dict[str, Any] = {
        "scenario_id": scenario_id_hex,
        "ruleset_id": ruleset_id,
        "abstraction_hash": abstraction_hash,
    }
    return sha256_hex(canonicalize_json_bytes(obj, strict_mode=strict_mode))
