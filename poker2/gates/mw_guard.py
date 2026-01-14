from __future__ import annotations

from pathlib import Path
from typing import Any

from poker2.gates.common import GateCheckError, _as_int, _as_obj, _as_str, failure
from poker2.protocol.mw_context import mw_context_digest
from poker2.protocol.mw_ladder import MWLadderError, load_mw_ladder_spec, validate_mw_ladder_spec
from poker2.runtime.mw_assumption_guard_registry import (
    MWAssumptionGuardRegistryError,
    build_mw_assumption_guard_registry,
)
from poker2.runtime.mw_ladder_registry import MWLadderRegistryError, build_mw_ladder_registry


def check_mw_guard_gate(
    *,
    header: dict[str, Any],
    decision_points: list[dict[str, Any]],
    action_chosen: list[dict[str, Any]],
    event_stream_ref: str | None,
    event_stream_digest: dict[str, Any] | None,
    scenario_mw_ladder_id: str | None = None,
    mw_ladder_spec: dict[str, Any] | None = None,
    enforce_mw_ladder_id: bool = False,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    gate_id = "Gates.MWAssumptionGuard"
    failures: list[dict[str, Any]] = []

    rung_map: dict[str, dict[str, Any]] | None = None
    guard_registry: dict[str, dict[str, Any]] | None = None
    if scenario_mw_ladder_id is not None:
        if mw_ladder_spec is None:
            try:
                registry = build_mw_ladder_registry(strict_mode=True)
                entry = registry.get(scenario_mw_ladder_id)
                if entry is None:
                    failures.append(
                        failure(
                            gate_id=gate_id,
                            reason="mw_ladder_missing",
                            header=header,
                            event_stream_ref=event_stream_ref,
                            event_stream_digest=event_stream_digest,
                            ruleset_id_or_none=None,
                            triad_or_none=None,
                            schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                            details={"mw_ladder_id": scenario_mw_ladder_id},
                        )
                    )
                    return failures
                spec_path = str(entry["mw_ladder_ref"]).removeprefix("path:")
                mw_ladder_spec = load_mw_ladder_spec(Path(spec_path))
                validate_mw_ladder_spec(mw_ladder_spec, strict_mode=True)
            except (MWLadderRegistryError, MWLadderError) as e:
                code = getattr(e, "code", "FAIL")
                msg = getattr(e, "message", str(e))
                details = getattr(e, "details", None)
                failures.append(
                    failure(
                        gate_id=gate_id,
                        reason="mw_ladder_unresolvable",
                        header=header,
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        ruleset_id_or_none=None,
                        triad_or_none=None,
                        schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                        details={"mw_ladder_id": scenario_mw_ladder_id, "error": {"code": code, "message": msg, "details": details}},
                    )
                )
                return failures

        if isinstance(mw_ladder_spec, dict):
            rungs = mw_ladder_spec.get("rungs")
            if isinstance(rungs, list):
                rung_map = {r.get("rung_id"): r for r in rungs if isinstance(r, dict) and isinstance(r.get("rung_id"), str)}

    dp_index: dict[tuple[int, str], dict[str, Any]] = {}
    for dp in decision_points:
        did = dp.get("decision_id")
        sh = dp.get("state_hash")
        if isinstance(did, int) and isinstance(sh, str):
            dp_index[(did, sh)] = dp

    for ac in action_chosen:
        routing = ac.get("routing")
        did = ac.get("decision_id")
        sh = ac.get("state_hash")
        decision_id = int(did) if isinstance(did, int) else None
        state_hash = sh if isinstance(sh, str) else None

        dp = dp_index.get((decision_id or -1, state_hash or "")) if decision_id is not None and state_hash is not None else None
        players_alive_count: int | None = None
        if dp is not None and isinstance(dp.get("snapshot_payload"), dict):
            players_alive_count = _as_int(dp["snapshot_payload"].get("players_alive_count"), field="Snapshot.players_alive_count")

        if routing is not None and not isinstance(routing, dict):
            raise GateCheckError("TYPE_ERROR", "ActionChosen.routing must be object or null")

        if players_alive_count is not None and players_alive_count < 3:
            if routing is not None:
                failures.append(
                    failure(
                        gate_id=gate_id,
                        reason="routing_present_for_hu",
                        header=header,
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        ruleset_id_or_none=None,
                        triad_or_none=None,
                        schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                        decision_id_or_none=decision_id,
                        state_hash_or_none=state_hash,
                        details={"players_alive_count": players_alive_count},
                    )
                )
                break
        if players_alive_count is not None and players_alive_count >= 3:
            if routing is None:
                failures.append(
                    failure(
                        gate_id=gate_id,
                        reason="routing_missing_for_mw",
                        header=header,
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        ruleset_id_or_none=None,
                        triad_or_none=None,
                        schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                        decision_id_or_none=decision_id,
                        state_hash_or_none=state_hash,
                        details={"players_alive_count": players_alive_count},
                    )
                )
                break
            if enforce_mw_ladder_id and scenario_mw_ladder_id is None:
                failures.append(
                    failure(
                        gate_id=gate_id,
                        reason="mw_ladder_id_missing",
                        header=header,
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        ruleset_id_or_none=None,
                        triad_or_none=None,
                        schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                        decision_id_or_none=decision_id,
                        state_hash_or_none=state_hash,
                        details={"players_alive_count": players_alive_count},
                    )
                )
                break

        if routing is None:
            continue

        mw_ladder_id = routing.get("mw_ladder_id")
        rung_id = routing.get("rung_id")
        mw_ctx = routing.get("mw_context_digest")
        if strict_mode:
            if not isinstance(mw_ladder_id, str):
                failures.append(
                    failure(
                        gate_id=gate_id,
                        reason="mw_ladder_id_missing",
                        header=header,
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        ruleset_id_or_none=None,
                        triad_or_none=None,
                        schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                        decision_id_or_none=decision_id,
                        state_hash_or_none=state_hash,
                        details={},
                    )
                )
                break
            if scenario_mw_ladder_id is not None and mw_ladder_id != scenario_mw_ladder_id:
                failures.append(
                    failure(
                        gate_id=gate_id,
                        reason="mw_ladder_id_mismatch",
                        header=header,
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        ruleset_id_or_none=None,
                        triad_or_none=None,
                        schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                        decision_id_or_none=decision_id,
                        state_hash_or_none=state_hash,
                        details={"expected": scenario_mw_ladder_id, "observed": mw_ladder_id},
                    )
                )
                break
        if not isinstance(rung_id, str) or not isinstance(mw_ctx, str):
            raise GateCheckError("MISSING_FIELDS", "routing must include {rung_id, mw_context_digest}")

        belief_digest = ac.get("belief_digest")
        mw_risk_spec_id = ac.get("mw_risk_spec_id")
        if rung_map is not None and isinstance(rung_id, str):
            rung = rung_map.get(rung_id)
            if rung is None:
                failures.append(
                    failure(
                        gate_id=gate_id,
                        reason="rung_id_unknown",
                        header=header,
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        ruleset_id_or_none=None,
                        triad_or_none=None,
                        schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                        decision_id_or_none=decision_id,
                        state_hash_or_none=state_hash,
                        details={"rung_id": rung_id},
                    )
                )
                break
            guard_id = rung.get("assumption_guard_id")
            if rung_id not in ("baseline", "failsafe") and guard_id is None:
                failures.append(
                    failure(
                        gate_id=gate_id,
                        reason="assumption_guard_missing",
                        header=header,
                        event_stream_ref=event_stream_ref,
                        event_stream_digest=event_stream_digest,
                        ruleset_id_or_none=None,
                        triad_or_none=None,
                        schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                        decision_id_or_none=decision_id,
                        state_hash_or_none=state_hash,
                        details={"rung_id": rung_id},
                    )
                )
                break
            if guard_id is not None:
                if guard_registry is None:
                    try:
                        guard_registry = build_mw_assumption_guard_registry(strict_mode=True)
                    except MWAssumptionGuardRegistryError as e:
                        failures.append(
                            failure(
                                gate_id=gate_id,
                                reason="assumption_guard_unresolvable",
                                header=header,
                                event_stream_ref=event_stream_ref,
                                event_stream_digest=event_stream_digest,
                                ruleset_id_or_none=None,
                                triad_or_none=None,
                                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                                decision_id_or_none=decision_id,
                                state_hash_or_none=state_hash,
                                details={"assumption_guard_id": guard_id, "error": {"code": e.code, "message": e.message, "details": e.details}},
                            )
                        )
                        break
                if guard_id not in guard_registry:
                    failures.append(
                        failure(
                            gate_id=gate_id,
                            reason="assumption_guard_unresolvable",
                            header=header,
                            event_stream_ref=event_stream_ref,
                            event_stream_digest=event_stream_digest,
                            ruleset_id_or_none=None,
                            triad_or_none=None,
                            schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                            decision_id_or_none=decision_id,
                            state_hash_or_none=state_hash,
                            details={"assumption_guard_id": guard_id},
                        )
                    )
                    break

            dep = rung.get("dependency_ids")
            if isinstance(dep, dict):
                belief_req = dep.get("belief_spec_id")
                if belief_req is not None:
                    if not isinstance(ac.get("belief_spec_id"), str) or ac.get("belief_spec_id") != belief_req:
                        failures.append(
                            failure(
                                gate_id=gate_id,
                                reason="belief_spec_id_missing",
                                header=header,
                                event_stream_ref=event_stream_ref,
                                event_stream_digest=event_stream_digest,
                                ruleset_id_or_none=None,
                                triad_or_none=None,
                                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                                decision_id_or_none=decision_id,
                                state_hash_or_none=state_hash,
                                details={"expected": belief_req, "observed": ac.get("belief_spec_id")},
                            )
                        )
                        break
                    if not isinstance(ac.get("belief_digest"), dict):
                        failures.append(
                            failure(
                                gate_id=gate_id,
                                reason="belief_digest_missing",
                                header=header,
                                event_stream_ref=event_stream_ref,
                                event_stream_digest=event_stream_digest,
                                ruleset_id_or_none=None,
                                triad_or_none=None,
                                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                                decision_id_or_none=decision_id,
                                state_hash_or_none=state_hash,
                                details={},
                            )
                        )
                        break
                mw_risk_req = dep.get("mw_risk_spec_id")
                if mw_risk_req is not None:
                    if not isinstance(ac.get("mw_risk_spec_id"), str) or ac.get("mw_risk_spec_id") != mw_risk_req:
                        failures.append(
                            failure(
                                gate_id=gate_id,
                                reason="mw_risk_spec_id_missing",
                                header=header,
                                event_stream_ref=event_stream_ref,
                                event_stream_digest=event_stream_digest,
                                ruleset_id_or_none=None,
                                triad_or_none=None,
                                schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                                decision_id_or_none=decision_id,
                                state_hash_or_none=state_hash,
                                details={"expected": mw_risk_req, "observed": ac.get("mw_risk_spec_id")},
                            )
                        )
                        break

        expected_ctx = mw_context_digest(
            state_hash=_as_str(ac.get("state_hash"), field="ActionChosen.state_hash"),
            mw_ladder_id=str(mw_ladder_id) if mw_ladder_id is not None else "0" * 64,
            rung_id=rung_id,
            belief_digest_or_none=belief_digest if isinstance(belief_digest, dict) else None,
            mw_risk_spec_id_or_none=mw_risk_spec_id if isinstance(mw_risk_spec_id, str) else None,
            strict_mode=True,
        )
        if mw_ctx != expected_ctx:
            failures.append(
                failure(
                    gate_id=gate_id,
                    reason="mw_context_digest_mismatch",
                    header=header,
                    event_stream_ref=event_stream_ref,
                    event_stream_digest=event_stream_digest,
                    ruleset_id_or_none=None,
                    triad_or_none=None,
                    schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                    decision_id_or_none=decision_id,
                    state_hash_or_none=state_hash,
                    details={"expected": expected_ctx, "observed": mw_ctx, "routing": routing},
                )
            )
            break

    return failures
