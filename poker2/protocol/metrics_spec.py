from __future__ import annotations

# MetricsSpec contract (ARCHIETECTURE.md 3.9).

from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex


METRICS_SPEC_V1: dict[str, Any] = {
    "metric_spec_schema_id": "metric_spec_v1",
    "normative_source": "ARCHIETECTURE.md",
    "anchor": "3.9",
    # Minimal, stable placeholder: this project currently focuses on RuleConformanceReport and throughput.
    "metrics": [],
}


def metric_spec_id(*, strict_mode: bool) -> str:
    return sha256_hex(canonicalize_json_bytes(METRICS_SPEC_V1, strict_mode=strict_mode))

