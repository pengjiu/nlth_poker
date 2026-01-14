from __future__ import annotations

from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex


EVENT_MODEL_SCHEMA_V1: dict[str, Any] = {
    "event_model_schema_id": "event_model_v1",
    "normative_source": "ARCHIETECTURE.md",
    "anchor": "5.1/5.1.1",
    "events_min_required": [
        {
            "event": "HandStart",
            "required_fields": [
                "hand_id",
                "hand_seq",
                "button_seat",
                "seats_in_hand",
                "ruleset_id",
                "triad",
                "schema_hash",
                "options_hash",
                "provenance_ref",
                "opponent_suite_id",
                "opponent_artifact_id_or_params_hash",
            ],
        },
        {
            "event": "ForcedBets",
            "required_fields": [
                "kind",
                "by_seat_amount_chips",
            ],
        },
        {
            "event": "DecisionPoint",
            "required_fields": [
                "decision_id",
                "state_hash",
                "legal_actions_digest",
                "snapshot_payload",
                "observation_view_payload",
            ],
        },
        {
            "event": "ActionChosen",
            "required_fields": [
                "decision_id",
                "state_hash",
                "action_source_id",
                "proposed_action",
                "executed_action",
                "mapping_trace",
                "derived_action",
                "routing",
                "belief_spec_id",
                "belief_digest",
                "mw_risk_spec_id",
            ],
        },
        {
            "event": "StreetDealt",
            "required_fields": [
                "street",
            ],
        },
        {
            "event": "PotUpdate",
            "required_fields": [
                "pot_chips_delta",
                "rake_chips_delta",
            ],
        },
        {
            "event": "HandEnd",
            "required_fields": [
                "initial_stacks_by_seat",
                "final_stacks_by_seat",
                "stack_deltas_by_seat",
                "total_rake_chips",
                "rake_base_pot_chips",
                "invariants_ok",
            ],
        },
    ],
}


def event_model_id(*, strict_mode: bool) -> str:
    return sha256_hex(canonicalize_json_bytes(EVENT_MODEL_SCHEMA_V1, strict_mode=strict_mode))
