from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex
from poker2.protocol.enums import MW_RUNG_ID_VALUES


@dataclass(frozen=True)
class MWLadderError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def load_mw_ladder_spec(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise MWLadderError("JSON_PARSE_FAIL", "mw ladder JSON unreadable", {"error": str(e)}) from e
    if not isinstance(obj, dict):
        raise MWLadderError("TYPE_ERROR", "MWStrategyLadderSpec must be JSON object")
    return obj


def validate_mw_ladder_spec(spec: Any, *, strict_mode: bool) -> None:
    if not isinstance(spec, dict):
        raise MWLadderError("TYPE_ERROR", "MWStrategyLadderSpec must be JSON object")
    if strict_mode and "mw_ladder_id" in spec:
        raise MWLadderError("DISALLOWED_FIELD", "MWStrategyLadderSpec hash input must not include mw_ladder_id")

    schema_id = spec.get("mw_ladder_schema_id")
    if schema_id != "mw_strategy_ladder_spec_v1":
        raise MWLadderError("UNSUPPORTED_VALUE", "unsupported mw_ladder_schema_id")

    rungs = spec.get("rungs")
    if not isinstance(rungs, list) or not rungs:
        raise MWLadderError("TYPE_ERROR", "rungs must be non-empty array")

    seen: set[str] = set()
    for idx, rung in enumerate(rungs):
        if not isinstance(rung, dict):
            raise MWLadderError("TYPE_ERROR", "rung must be object", {"index": idx})
        rung_id = rung.get("rung_id")
        if rung_id not in MW_RUNG_ID_VALUES:
            raise MWLadderError("UNSUPPORTED_VALUE", "unsupported rung_id", {"index": idx, "rung_id": rung_id})
        if rung_id in seen:
            raise MWLadderError("VALUE_ERROR", "duplicate rung_id in ladder", {"rung_id": rung_id})
        seen.add(rung_id)

        pred = rung.get("applicability_predicate")
        if not isinstance(pred, dict):
            raise MWLadderError("TYPE_ERROR", "applicability_predicate must be object", {"index": idx})
        kind = pred.get("predicate_kind")
        allowed_predicate_kinds = {"always", "players_range"}
        if kind not in allowed_predicate_kinds:
            raise MWLadderError(
                "UNSUPPORTED_VALUE",
                "unsupported predicate_kind",
                {"index": idx, "predicate_kind": kind},
            )
        allowed_pred_keys = {"predicate_kind", "min_players", "max_players"}
        extra_pred_keys = {k for k in pred.keys() if k not in allowed_pred_keys}
        if strict_mode and extra_pred_keys:
            raise MWLadderError("EXTRA_FIELDS", "applicability_predicate has extra fields", {"index": idx, "extra": sorted(extra_pred_keys)})
        if kind == "players_range":
            min_players = pred.get("min_players")
            max_players = pred.get("max_players")
            if min_players is None and max_players is None:
                raise MWLadderError("MISSING_FIELDS", "players_range predicate requires min_players or max_players", {"index": idx})
            if min_players is not None and (not isinstance(min_players, int) or min_players < 2):
                raise MWLadderError("TYPE_ERROR", "min_players must be int>=2", {"index": idx})
            if max_players is not None and (not isinstance(max_players, int) or max_players < 2):
                raise MWLadderError("TYPE_ERROR", "max_players must be int>=2", {"index": idx})
            if min_players is not None and max_players is not None and min_players > max_players:
                raise MWLadderError("VALUE_ERROR", "min_players cannot exceed max_players", {"index": idx})
        else:
            if pred.get("min_players") is not None or pred.get("max_players") is not None:
                raise MWLadderError(
                    "UNSUPPORTED_VALUE",
                    "min_players/max_players only allowed for players_range predicate",
                    {"index": idx},
                )

        dep = rung.get("dependency_ids")
        if not isinstance(dep, dict):
            raise MWLadderError("TYPE_ERROR", "dependency_ids must be object", {"index": idx})

        guard = rung.get("assumption_guard_id")
        if guard is not None and not isinstance(guard, str):
            raise MWLadderError("TYPE_ERROR", "assumption_guard_id must be string or null", {"index": idx})

        req = rung.get("output_requirements")
        if not isinstance(req, list) or not all(isinstance(x, str) for x in req):
            raise MWLadderError("TYPE_ERROR", "output_requirements must be array of strings", {"index": idx})


def mw_ladder_id(spec: Any, *, strict_mode: bool) -> str:
    validate_mw_ladder_spec(spec, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(spec, strict_mode=strict_mode))


def default_internal_mw_ladder(*, strict_mode: bool) -> tuple[dict[str, Any], str]:
    root = Path(__file__).resolve().parents[2]
    path = root / "specs" / "mw_ladders" / "internal_mw_ladder_v1.json"
    spec = load_mw_ladder_spec(path)
    mid = mw_ladder_id(spec, strict_mode=strict_mode)
    return spec, mid
