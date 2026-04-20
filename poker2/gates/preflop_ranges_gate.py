from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from poker2.gates.common import failure
from poker2.protocol.preflop_ranges import PreflopRangesError, validate_preflop_ranges


def check_preflop_ranges_gate(
    *,
    preflop_ranges_path: Path,
    strict_mode: bool,
) -> list[dict[str, Any]]:
    gate_id = "Gates.PreflopRanges"
    failures: list[dict[str, Any]] = []
    try:
        obj = json.loads(preflop_ranges_path.read_text(encoding="utf-8"))
    except Exception as e:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="preflop_ranges_read_fail",
                header={},
                event_stream_ref=None,
                event_stream_digest=None,
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=None,
                details={"path": str(preflop_ranges_path), "error": str(e)},
            )
        )
        return failures

    manifest_path: Path | None = None
    if isinstance(obj, dict):
        ref = obj.get("manifest_ref")
        if isinstance(ref, str) and ref.startswith("path:"):
            root = Path(__file__).resolve().parents[2]
            rel = ref.removeprefix("path:")
            candidate = (root / rel).resolve()
            if not candidate.exists():
                candidate = (root / "specs" / rel).resolve()
            manifest_path = candidate

    try:
        validate_preflop_ranges(obj, strict_mode=strict_mode, manifest_path=manifest_path)
    except PreflopRangesError as e:
        failures.append(
            failure(
                gate_id=gate_id,
                reason="preflop_ranges_invalid",
                header={},
                event_stream_ref=None,
                event_stream_digest=None,
                ruleset_id_or_none=None,
                triad_or_none=None,
                schema_hash_or_none=None,
                details={"path": str(preflop_ranges_path), "error": {"code": e.code, "message": e.message, "details": e.details}},
            )
        )
    return failures
