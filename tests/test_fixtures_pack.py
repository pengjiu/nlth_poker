from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.contractkit import canonicalize_json_bytes
from poker2.evaluation.fixtures.pack import FixturesPackError, pack_digest, validate_pack
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.run_id import run_id_v1


def _header(*, digest_hex: str) -> dict:
    options_hash = "0" * 64
    seed = 0
    return {
        "run_id": run_id_v1(options_hash=options_hash, seed=seed, strict_mode=True),
        "options_hash": options_hash,
        "seed": seed,
        "scenario_id": "0" * 64,
        "schema_hash": "0" * 64,
        "event_model_id": "0" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": digest_hex},
        "provenance_ref": "artifact://prov",
        "resolved_paths_digest": "0" * 64,
        "repro_tier": "Tier-A",
    }


def _write_ndjson(path: Path, objs: list[dict]) -> None:
    lines = [canonicalize_json_bytes(o, strict_mode=True) for o in objs]
    path.write_bytes(b"\n".join(lines) + b"\n")


def test_validate_pack_checks_event_stream_digest_and_header_digest(tmp_path: Path) -> None:
    es = tmp_path / "hand.ndjson"
    header = _header(digest_hex="0" * 64)
    event = {"event": "HandEnd", "rake_base_pot_chips": 10, "total_rake_chips": 1}
    digest_hex = event_stream_digest_from_objects([header, event], strict_mode=True)
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(es, [header, event])

    pack = tmp_path / "pack.json"
    pack_obj = {
        "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
        "ruleset_id": "0" * 64,
        "ruleset_label": "internal_ruleset_v1",
        "checked_items_covered": ["rake", "allin_reopen"],
        "platform": "coinpoker",
        "fixtures": [
            {
                "event_stream_ref": f"path:{es}",
                "event_stream_digest": {"alg": "sha256", "hex": digest_hex},
                "ruleset_id": "0" * 64,
                "options_hash": "0" * 64,
                "provenance_ref": "artifact://prov",
            }
        ],
    }
    pack.write_text(json.dumps(pack_obj, ensure_ascii=False), encoding="utf-8")

    summary = validate_pack(
        pack,
        strict_mode=True,
        require_non_empty=True,
        expected_ruleset_id="0" * 64,
        required_checked_items=["rake", "allin_reopen"],
    )
    assert summary["fixtures_count"] == 1
    d = pack_digest(pack)
    assert d["alg"] == "sha256" and len(d["hex"]) == 64

    # Tamper the header's declared digest: validate_pack should now fail in strict_mode.
    objs = [json.loads(line) for line in es.read_text(encoding="utf-8").splitlines()]
    objs[0]["event_stream_digest"]["hex"] = "f" * 64
    _write_ndjson(es, objs)

    with pytest.raises(FixturesPackError) as exc:
        validate_pack(pack, strict_mode=True, require_non_empty=True)
    assert exc.value.code == "PACK_INVALID"
