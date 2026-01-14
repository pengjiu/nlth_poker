from __future__ import annotations

from pathlib import Path
from typing import Any

from poker2.gates.common import _as_obj, failure
from poker2.runtime.opponent_registry import OpponentRegistryError, build_opponent_registry


def check_opponent_suite_gate(
    *,
    header: dict[str, Any],
    hand_starts: list[dict[str, Any]],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    strict_mode: bool,
    opponents_root: Path | None = None,
    opponent_registry: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    gate_id = "Gates.OpponentSuiteGate"
    failures: list[dict[str, Any]] = []

    _SENTINEL = object()
    ruleset_id_or_none: str | None = None
    triad_or_none: dict[str, Any] | None = None
    if hand_starts:
        hs0 = hand_starts[0]
        if isinstance(hs0.get("ruleset_id"), str):
            ruleset_id_or_none = hs0["ruleset_id"]
        if isinstance(hs0.get("triad"), dict):
            triad_or_none = _as_obj(hs0.get("triad"), field="HandStart.triad")

    schema_hash_or_none = header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None

    suite_id_first: str | None | object = _SENTINEL
    artifact_id_first: str | None | object = _SENTINEL

    for hs in hand_starts:
        missing = [k for k in ("opponent_suite_id", "opponent_artifact_id_or_params_hash") if k not in hs]
        if missing:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="missing_fields",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=ruleset_id_or_none,
                    triad_or_none=triad_or_none,
                    schema_hash_or_none=schema_hash_or_none,
                    details={"missing": missing, "hand_id": hs.get("hand_id")},
                )
            )
            return failures

        suite_id = hs.get("opponent_suite_id")
        if suite_id is not None and not isinstance(suite_id, str):
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="type_error",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=ruleset_id_or_none,
                    triad_or_none=triad_or_none,
                    schema_hash_or_none=schema_hash_or_none,
                    details={"field": "HandStart.opponent_suite_id", "hand_id": hs.get("hand_id")},
                )
            )
            return failures
        if suite_id is not None and (len(suite_id) != 64 or any(c not in "0123456789abcdef" for c in suite_id)):
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="id_invalid",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=ruleset_id_or_none,
                    triad_or_none=triad_or_none,
                    schema_hash_or_none=schema_hash_or_none,
                    details={"field": "HandStart.opponent_suite_id", "hand_id": hs.get("hand_id"), "observed": suite_id},
                )
            )
            return failures

        art_id = hs.get("opponent_artifact_id_or_params_hash")
        if art_id is not None and not isinstance(art_id, str):
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="type_error",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=ruleset_id_or_none,
                    triad_or_none=triad_or_none,
                    schema_hash_or_none=schema_hash_or_none,
                    details={"field": "HandStart.opponent_artifact_id_or_params_hash", "hand_id": hs.get("hand_id")},
                )
            )
            return failures
        if art_id is not None and (len(art_id) != 64 or any(c not in "0123456789abcdef" for c in art_id)):
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="id_invalid",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=ruleset_id_or_none,
                    triad_or_none=triad_or_none,
                    schema_hash_or_none=schema_hash_or_none,
                    details={"field": "HandStart.opponent_artifact_id_or_params_hash", "hand_id": hs.get("hand_id"), "observed": art_id},
                )
            )
            return failures

        if suite_id is None and art_id is not None:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="artifact_without_suite",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=ruleset_id_or_none,
                    triad_or_none=triad_or_none,
                    schema_hash_or_none=schema_hash_or_none,
                    details={"hand_id": hs.get("hand_id")},
                )
            )
            return failures

        if suite_id_first is _SENTINEL:
            suite_id_first = suite_id
        if artifact_id_first is _SENTINEL:
            artifact_id_first = art_id
        if suite_id != suite_id_first or art_id != artifact_id_first:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="handstart_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=ruleset_id_or_none,
                    triad_or_none=triad_or_none,
                    schema_hash_or_none=schema_hash_or_none,
                    details={
                        "expected": {
                            "opponent_suite_id": suite_id_first if isinstance(suite_id_first, str) else None,
                            "opponent_artifact_id_or_params_hash": artifact_id_first if isinstance(artifact_id_first, str) else None,
                        },
                        "observed": {"opponent_suite_id": suite_id, "opponent_artifact_id_or_params_hash": art_id},
                        "hand_id": hs.get("hand_id"),
                    },
                )
            )
            return failures

    # If suite_id is null, opponents are not involved; still recorded as null per 0.1.3.
    if not isinstance(suite_id_first, str):
        return failures

    # Resolve suite + dependency population spec via registry (3.16.1/7.8).
    reg = opponent_registry
    if reg is None:
        try:
            reg = build_opponent_registry(opponents_root=opponents_root, strict_mode=True)
        except OpponentRegistryError as e:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="registry_invalid",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=ruleset_id_or_none,
                    triad_or_none=triad_or_none,
                    schema_hash_or_none=schema_hash_or_none,
                    details={"error": {"code": e.code, "message": e.message, "details": e.details}},
                )
            )
            return failures

    suites = reg.get("opponent_suites", {})
    suite_entry = suites.get(suite_id_first)
    if suite_entry is None:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="missing_ref",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash_or_none,
                details={"requested_opponent_suite_ref": f"opponent_suite://{suite_id_first}", "opponent_suite_id": suite_id_first},
            )
        )
        return failures

    pop_id = suite_entry.get("population_id")
    if not isinstance(pop_id, str):
        failures.append(
            failure(
                gate_id=gate_id,
                reason="suite_invalid",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash_or_none,
                details={"opponent_suite_id": suite_id_first, "error": "suite_entry.population_id missing/invalid"},
            )
        )
        return failures

    populations = reg.get("populations", {})
    if pop_id not in populations:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="population_missing_ref",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash_or_none,
                details={"opponent_suite_id": suite_id_first, "population_id": pop_id},
            )
        )
        return failures

    # 7.8: if suite requires calibration, opponent_artifact_id_or_params_hash must exist.
    calib_id = suite_entry.get("calibration_id")
    if calib_id is not None and not isinstance(artifact_id_first, str):
        failures.append(
            failure(
                gate_id=gate_id,
                reason="calibration_required_missing_artifact",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=ruleset_id_or_none,
                triad_or_none=triad_or_none,
                schema_hash_or_none=schema_hash_or_none,
                details={"opponent_suite_id": suite_id_first, "calibration_id": calib_id},
            )
        )
        return failures

    return failures
