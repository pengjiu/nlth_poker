from __future__ import annotations

import json
from pathlib import Path

from poker2.gates.cache_gate import check_cache_correctness_gate


def _load_internal_provenance() -> tuple[str, dict[str, object]]:
    prov_path = Path("fixtures/internal/artifacts/7e35c6b0265e2f8db15b7b0585aff53ccd40e63fc1f33c8657bf800b9517ec25.json")
    obj = json.loads(prov_path.read_text(encoding="utf-8"))
    return prov_path.stem, obj


def test_cache_gate_passes_for_matching_cached_entry() -> None:
    prov_id, prov = _load_internal_provenance()
    header = {
        "run_id": "0" * 64,
        "scenario_id": "0" * 64,
        "seed": prov["seed"],
        "options_hash": prov["options_hash"],
        "schema_hash": prov["schema_hash"],
        "cache_entry_provenance_ref": f"artifact://{prov_id}",
    }
    hand_starts = [{"ruleset_id": prov["ruleset_id"], "triad": prov["triad"]}]
    failures = check_cache_correctness_gate(
        header=header,
        hand_starts=hand_starts,
        event_stream_ref="path:dummy",
        event_stream_digest={"alg": "sha256", "hex": "0" * 64},
        strict_mode=True,
    )
    assert failures == []


def test_cache_gate_detects_mismatched_options_hash() -> None:
    prov_id, prov = _load_internal_provenance()
    header = {
        "run_id": "0" * 64,
        "scenario_id": "0" * 64,
        "seed": prov["seed"],
        "options_hash": "1" * 64,
        "schema_hash": prov["schema_hash"],
        "cache_entry_provenance_ref": f"artifact://{prov_id}",
    }
    hand_starts = [{"ruleset_id": prov["ruleset_id"], "triad": prov["triad"]}]
    failures = check_cache_correctness_gate(
        header=header,
        hand_starts=hand_starts,
        event_stream_ref="path:dummy",
        event_stream_digest={"alg": "sha256", "hex": "0" * 64},
        strict_mode=True,
    )
    assert failures
    assert failures[0]["reason"] in {"provenance_mismatch", "provenance_header_mismatch"}
