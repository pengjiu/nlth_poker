from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex


@dataclass(frozen=True)
class OptionsHashError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


_REQUIRED_KEYS = (
    "scenario_id",
    "ruleset_id",
    "triad",
    "schema_hash",
    "resolved_paths_digest",
    "abstraction_hash",
    "policy_id",
    "profile_id",
    "opponent_suite_id",
    "opponent_artifact_id_or_params_hash",
    "mw_ladder_id",
    "belief_spec_id",
    "mw_risk_spec_id",
    "adaptation_digest",
    "engine_build_id",
    "solver_build_id",
    "pokerkit_version",
    "strict_mode",
)


def compute_options_hash(run_semantic_closure: Any, *, strict_mode: bool) -> str:
    if not isinstance(run_semantic_closure, dict):
        raise OptionsHashError("TYPE_ERROR", "run_semantic_closure must be a JSON object")

    missing = [k for k in _REQUIRED_KEYS if k not in run_semantic_closure]
    if missing:
        raise OptionsHashError("MISSING_FIELDS", f"missing required fields: {missing}")

    def _scan_no_labels(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and (k.endswith("_label") or k.endswith("_alias") or k == "latest"):
                    raise OptionsHashError("LABEL_IN_HASH_INPUT", f"disallowed label/alias field in options hash input: {k}")
                _scan_no_labels(v)
        elif isinstance(obj, list):
            for v in obj:
                _scan_no_labels(v)

    _scan_no_labels(run_semantic_closure)
    return sha256_hex(canonicalize_json_bytes(run_semantic_closure, strict_mode=strict_mode))

