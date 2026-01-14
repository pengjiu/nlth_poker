from __future__ import annotations

from typing import Any

from poker2.gates.common import _as_obj, failure
from poker2.protocol.paths import PathsError, resolve_paths
from poker2.protocol.scenario_package import ScenarioPackageError, scenario_closure_from_package, validate_scenario_package


def check_scenario_package_gate(
    *,
    requested_scenario_ref: str | None,
    header: dict[str, Any],
    scenario_package: dict[str, Any],
    expected_context: dict[str, Any],
    paths_config: dict[str, Any],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    strict_mode: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gate_id = "Gates.Scenario"
    failures: list[dict[str, Any]] = []

    try:
        pkg_ids = validate_scenario_package(scenario_package, strict_mode=strict_mode)
        closure = scenario_closure_from_package(scenario_package, strict_mode=strict_mode)
    except ScenarioPackageError as e:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="scenario_package_invalid",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                details={
                    "requested_scenario_ref": requested_scenario_ref,
                    "error": {"code": e.code, "message": e.message, "details": e.details},
                },
            )
        )
        return failures, {}

    header_scenario_id = header.get("scenario_id")
    if isinstance(header_scenario_id, str) and header_scenario_id != pkg_ids.get("scenario_id"):
        failures.append(
            failure(
                gate_id=gate_id,
                reason="scenario_id_mismatch",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=closure.get("ruleset_id") if isinstance(closure.get("ruleset_id"), str) else None,
                triad_or_none=_as_obj(closure.get("triad"), field="ScenarioSpecClosure.triad") if isinstance(closure.get("triad"), dict) else None,
                schema_hash_or_none=closure.get("schema_hash") if isinstance(closure.get("schema_hash"), str) else None,
                details={
                    "requested_scenario_ref": requested_scenario_ref,
                    "expected": pkg_ids.get("scenario_id"),
                    "observed": header_scenario_id,
                    "scenario_family_key": pkg_ids.get("scenario_family_key"),
                },
            )
        )
        return failures, {}

    # Compare semantic closure against expected run context (7.4 mismatch rule).
    for k in ("ruleset_id", "schema_hash", "abstraction_hash"):
        expected_val = expected_context.get(k)
        if expected_val is None:
            continue
        if closure.get(k) != expected_val:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason=f"{k}_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=closure.get("ruleset_id") if isinstance(closure.get("ruleset_id"), str) else None,
                    triad_or_none=_as_obj(closure.get("triad"), field="ScenarioSpecClosure.triad") if isinstance(closure.get("triad"), dict) else None,
                    schema_hash_or_none=closure.get("schema_hash") if isinstance(closure.get("schema_hash"), str) else None,
                    details={
                        "requested_scenario_ref": requested_scenario_ref,
                        "expected": expected_val,
                        "observed": closure.get(k),
                        "scenario_id": pkg_ids.get("scenario_id"),
                        "scenario_family_key": pkg_ids.get("scenario_family_key"),
                    },
                )
            )
            return failures, {}

    if "triad" in expected_context and isinstance(expected_context.get("triad"), dict):
        if closure.get("triad") != expected_context.get("triad"):
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="triad_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=closure.get("ruleset_id") if isinstance(closure.get("ruleset_id"), str) else None,
                    triad_or_none=_as_obj(closure.get("triad"), field="ScenarioSpecClosure.triad") if isinstance(closure.get("triad"), dict) else None,
                    schema_hash_or_none=closure.get("schema_hash") if isinstance(closure.get("schema_hash"), str) else None,
                    details={
                        "requested_scenario_ref": requested_scenario_ref,
                        "expected": expected_context.get("triad"),
                        "observed": closure.get("triad"),
                        "scenario_id": pkg_ids.get("scenario_id"),
                        "scenario_family_key": pkg_ids.get("scenario_family_key"),
                    },
                )
            )
            return failures, {}

    try:
        resolved_paths, resolved_paths_digest, resolution_trace = resolve_paths(
            paths_config=paths_config,
            scenario_package_closure=closure,
            strict_mode=strict_mode,
        )
    except PathsError as e:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="resolved_paths_failed",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=closure.get("ruleset_id") if isinstance(closure.get("ruleset_id"), str) else None,
                triad_or_none=_as_obj(closure.get("triad"), field="ScenarioSpecClosure.triad") if isinstance(closure.get("triad"), dict) else None,
                schema_hash_or_none=closure.get("schema_hash") if isinstance(closure.get("schema_hash"), str) else None,
                details={
                    "requested_scenario_ref": requested_scenario_ref,
                    "scenario_id": pkg_ids.get("scenario_id"),
                    "scenario_family_key": pkg_ids.get("scenario_family_key"),
                    "paths_error": {"code": e.code, "message": e.message, "details": e.details},
                },
            )
        )
        return failures, {}

    expected_resolved_paths_digest = expected_context.get("resolved_paths_digest")
    if expected_resolved_paths_digest is not None and resolved_paths_digest != expected_resolved_paths_digest:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="resolved_paths_digest_mismatch",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=closure.get("ruleset_id") if isinstance(closure.get("ruleset_id"), str) else None,
                triad_or_none=_as_obj(closure.get("triad"), field="ScenarioSpecClosure.triad") if isinstance(closure.get("triad"), dict) else None,
                schema_hash_or_none=closure.get("schema_hash") if isinstance(closure.get("schema_hash"), str) else None,
                details={
                    "requested_scenario_ref": requested_scenario_ref,
                    "expected": expected_resolved_paths_digest,
                    "observed": resolved_paths_digest,
                },
            )
        )
        return failures, {}

    header_resolved_paths_digest = header.get("resolved_paths_digest")
    if isinstance(header_resolved_paths_digest, str) and resolved_paths_digest != header_resolved_paths_digest:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="resolved_paths_digest_mismatch",
                header=header,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                ruleset_id_or_none=closure.get("ruleset_id") if isinstance(closure.get("ruleset_id"), str) else None,
                triad_or_none=_as_obj(closure.get("triad"), field="ScenarioSpecClosure.triad") if isinstance(closure.get("triad"), dict) else None,
                schema_hash_or_none=closure.get("schema_hash") if isinstance(closure.get("schema_hash"), str) else None,
                details={
                    "requested_scenario_ref": requested_scenario_ref,
                    "expected": resolved_paths_digest,
                    "observed": header_resolved_paths_digest,
                },
            )
        )
        return failures, {}

    out = {
        "scenario_id": pkg_ids["scenario_id"],
        "scenario_family_key": pkg_ids["scenario_family_key"],
        "resolved_paths": resolved_paths,
        "resolved_paths_digest": resolved_paths_digest,
        "resolution_trace": resolution_trace,
    }
    return failures, out
