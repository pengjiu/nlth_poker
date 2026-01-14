from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poker2.gates.cache_gate import check_cache_correctness_gate
from poker2.gates.common import GateCheckError
from poker2.gates.leakage_gate import check_leakage_gate
from poker2.gates.mw_guard import check_mw_guard_gate
from poker2.gates.opponent_suite_gate import check_opponent_suite_gate
from poker2.gates.postflop_gate import check_postflop_library_gate
from poker2.gates.provenance_gate import check_provenance_gate
from poker2.gates.scenario_gate import check_scenario_gate_minimal
from poker2.gates.scenario_package_gate import check_scenario_package_gate
from poker2.gates.schema_gate import check_schema_gate
from poker2.gates.triad_gate import check_triad_gate


def _split_by_event(events: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [e for e in events if isinstance(e, dict) and e.get("event") == name]


def check_eventstream_gates(
    *,
    header: dict[str, Any],
    events: list[dict[str, Any]],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    ruleset: dict[str, Any],
    scenario_package: dict[str, Any] | None = None,
    requested_scenario_ref: str | None = None,
    paths_config: dict[str, Any] | None = None,
    strict_mode: bool,
) -> dict[str, Any]:
    hand_starts = _split_by_event(events, "HandStart")
    decision_points = _split_by_event(events, "DecisionPoint")
    action_chosen = _split_by_event(events, "ActionChosen")

    failures: list[dict[str, Any]] = []
    failures.extend(
        check_schema_gate(
            header=header,
            hand_starts=hand_starts,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            strict_mode=strict_mode,
        )
    )
    failures.extend(
        check_triad_gate(
            header=header,
            hand_starts=hand_starts,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            ruleset=ruleset,
            strict_mode=strict_mode,
        )
    )
    failures.extend(
        check_provenance_gate(
            header=header,
            hand_starts=hand_starts,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            strict_mode=strict_mode,
        )
    )
    failures.extend(
        check_scenario_gate_minimal(
            header=header,
            hand_starts=hand_starts,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            strict_mode=strict_mode,
        )
    )
    if scenario_package is not None:
        if paths_config is None:
            raise GateCheckError("MISSING_FIELDS", "paths_config required when scenario_package is provided")
        expected_context: dict[str, Any] = {}
        if isinstance(header.get("schema_hash"), str):
            expected_context["schema_hash"] = header.get("schema_hash")
        if isinstance(header.get("resolved_paths_digest"), str):
            expected_context["resolved_paths_digest"] = header.get("resolved_paths_digest")
        if hand_starts:
            hs0 = hand_starts[0]
            if isinstance(hs0.get("ruleset_id"), str):
                expected_context["ruleset_id"] = hs0.get("ruleset_id")
            if isinstance(hs0.get("triad"), dict):
                expected_context["triad"] = hs0.get("triad")

        scen_failures, _ = check_scenario_package_gate(
            requested_scenario_ref=requested_scenario_ref,
            header=header,
            scenario_package=scenario_package,
            expected_context=expected_context,
            paths_config=paths_config,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            strict_mode=strict_mode,
        )
        failures.extend(scen_failures)
        failures.extend(
            check_postflop_library_gate(
                header=header,
                scenario_package=scenario_package,
                event_stream_ref=event_stream_ref,
                event_stream_digest=event_stream_digest,
                strict_mode=strict_mode,
            )
        )
    failures.extend(
        check_leakage_gate(
            header=header,
            decision_points=decision_points,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            strict_mode=strict_mode,
        )
    )
    scenario_mw_ladder_id = None
    enforce_mw_ladder_id = False
    if isinstance(scenario_package, dict):
        scenario_mw_ladder_id = scenario_package.get("mw_ladder_id")
        enforce_mw_ladder_id = True

    failures.extend(
        check_mw_guard_gate(
            header=header,
            decision_points=decision_points,
            action_chosen=action_chosen,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            scenario_mw_ladder_id=scenario_mw_ladder_id if isinstance(scenario_mw_ladder_id, str) else None,
            enforce_mw_ladder_id=enforce_mw_ladder_id,
            strict_mode=strict_mode,
        )
    )
    failures.extend(
        check_opponent_suite_gate(
            header=header,
            hand_starts=hand_starts,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            strict_mode=strict_mode,
        )
    )
    failures.extend(
        check_cache_correctness_gate(
            header=header,
            hand_starts=hand_starts,
            event_stream_ref=event_stream_ref,
            event_stream_digest=event_stream_digest,
            strict_mode=strict_mode,
        )
    )

    return {
        "status": "pass" if not failures else "fail",
        "failures_count": len(failures),
        "failures": failures,
    }
