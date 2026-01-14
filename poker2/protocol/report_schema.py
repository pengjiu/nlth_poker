from __future__ import annotations

# ReportSchema + RuleConformanceReport contracts (ARCHIETECTURE.md 3.10 / 3.10.1).

from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex


RULE_CONFORMANCE_CHECKED_ITEM_VALUES = (
    "allin_reopen",
    "button_rotation",
    "forced_bets",
    "ledger_conservation",
    "min_raise",
    "no_flop_no_drop",
    "rake",
)


REPORT_SCHEMA_V1: dict[str, Any] = {
    "report_schema_schema_id": "report_schema_v1",
    "normative_source": "ARCHIETECTURE.md",
    "anchor": "3.10/3.10.1",
    "required_header_fields": [
        "run_manifest_ref",
        "run_manifest_digest",
        "options_hash",
        "scenario_id",
        "schema_hash",
        "event_stream_ref",
        "event_stream_digest",
        "metric_spec_id",
        "report_schema_id",
        "repro_tier",
        "provenance_ref",
    ],
    "required_subreports": ["rule_conformance"],
    "rule_conformance_checked_items": list(RULE_CONFORMANCE_CHECKED_ITEM_VALUES),
}


def report_schema_id(*, strict_mode: bool) -> str:
    return sha256_hex(canonicalize_json_bytes(REPORT_SCHEMA_V1, strict_mode=strict_mode))
