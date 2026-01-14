from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.contractkit import canonicalize_json_bytes
from poker2.evaluation.fixtures import pack as pack_mod
from poker2.evaluation.fixtures.pack import FixturesPackError, validate_pack
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.run_id import run_id_v1

RULESET_ID = "0" * 64


def _write_ndjson(path: Path, objs: list[object]) -> None:
    lines = [canonicalize_json_bytes(o, strict_mode=True) for o in objs]
    path.write_bytes(b"\n".join(lines) + b"\n")


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


def test_validate_pack_rejects_unreadable_json(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_UNREADABLE"


def test_validate_pack_rejects_non_object(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_NOT_OBJECT"


def test_validate_pack_rejects_wrong_schema_id(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text(json.dumps({"fixtures_pack_schema_id": "nope"}), encoding="utf-8")
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_SCHEMA_MISMATCH"


def test_validate_pack_requires_ruleset_id(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps({"fixtures_pack_schema_id": "golden_fixtures_pack_v1", "fixtures": []}),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_RULESET_ID_MISSING"


def test_validate_pack_checks_expected_ruleset_id(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "fixtures": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False, expected_ruleset_id="f" * 64)
    assert exc.value.code == "PACK_RULESET_ID_MISMATCH"


def test_validate_pack_requires_fixtures_array(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "fixtures": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_FIXTURES_NOT_ARRAY"


def test_validate_pack_checks_checked_items_covered(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "checked_items_covered": "not-a-list",
                "fixtures": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False, required_checked_items=["rake"])
    assert exc.value.code == "PACK_COVERAGE_INVALID"


def test_validate_pack_checks_required_checked_items(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "checked_items_covered": ["rake"],
                "fixtures": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(
            p,
            strict_mode=True,
            require_non_empty=False,
            required_checked_items=["rake", "allin_reopen"],
        )
    assert exc.value.code == "PACK_COVERAGE_MISSING"


def test_validate_pack_require_non_empty(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "fixtures": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=True)
    assert exc.value.code == "PACK_EMPTY"


def test_validate_pack_collects_fixture_failures(tmp_path: Path) -> None:
    es = tmp_path / "bad.ndjson"
    header = _header(digest_hex="0" * 64)
    digest_hex = event_stream_digest_from_objects(
        [header, {"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}],
        strict_mode=True,
    )
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(
        es,
        [header, {"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}],
    )

    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "fixtures": [
                    "not-an-object",
                    {"event_stream_ref": 123},
                    {
                        "event_stream_ref": f"path:{es}",
                        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
                        "ruleset_id": RULESET_ID,
                        "options_hash": "0" * 64,
                        "provenance_ref": "artifact://prov",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_INVALID"
    failures = exc.value.details["failures"]
    assert {f["code"] for f in failures} >= {
        "FIXTURE_NOT_OBJECT",
        "FIXTURE_MISSING_FIELDS",
        "EVENT_STREAM_DIGEST_MISMATCH",
    }


def test_validate_pack_reports_event_stream_digest_fail_for_bad_header(tmp_path: Path) -> None:
    es = tmp_path / "header_not_object.ndjson"
    header = _header(digest_hex="0" * 64)
    digest_hex = event_stream_digest_from_objects(
        [header, {"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}],
        strict_mode=True,
    )
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(es, [[], {"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}])

    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "fixtures": [
                    {
                        "event_stream_ref": f"path:{es}",
                        "event_stream_digest": {"alg": "sha256", "hex": digest_hex},
                        "ruleset_id": RULESET_ID,
                        "options_hash": "0" * 64,
                        "provenance_ref": "artifact://prov",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_INVALID"
    assert exc.value.details["failures"][0]["code"] == "EVENT_STREAM_DIGEST_FAIL"


def test_validate_pack_reports_event_stream_ref_invalid(tmp_path: Path) -> None:
    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "fixtures": [
                    {
                        "event_stream_ref": "not-a-path-ref",
                        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
                        "ruleset_id": RULESET_ID,
                        "options_hash": "0" * 64,
                        "provenance_ref": "artifact://prov",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_INVALID"
    assert exc.value.details["failures"][0]["code"] == "EVENT_STREAM_REF_INVALID"


def test_validate_pack_reports_event_stream_digest_invalid(tmp_path: Path) -> None:
    es = tmp_path / "hand.ndjson"
    header = _header(digest_hex="0" * 64)
    digest_hex = event_stream_digest_from_objects(
        [header, {"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}],
        strict_mode=True,
    )
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(
        es,
        [header, {"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}],
    )

    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "fixtures": [
                    {
                        "event_stream_ref": f"path:{es}",
                        "event_stream_digest": {"alg": "sha256"},
                        "ruleset_id": RULESET_ID,
                        "options_hash": "0" * 64,
                        "provenance_ref": "artifact://prov",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_INVALID"
    assert exc.value.details["failures"][0]["code"] == "EVENT_STREAM_DIGEST_INVALID"


def test_validate_pack_reports_event_stream_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.ndjson"
    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "fixtures": [
                    {
                        "event_stream_ref": f"path:{missing}",
                        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
                        "ruleset_id": RULESET_ID,
                        "options_hash": "0" * 64,
                        "provenance_ref": "artifact://prov",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_INVALID"
    assert exc.value.details["failures"][0]["code"] == "EVENT_STREAM_MISSING"


def test_validate_pack_reports_event_stream_header_digest_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    es = tmp_path / "hand.ndjson"
    header = _header(digest_hex="0" * 64)
    digest_hex = event_stream_digest_from_objects(
        [header, {"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}],
        strict_mode=True,
    )
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(
        es,
        [header, {"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}],
    )

    def _fake_read_ndjson(_: Path, *, strict_mode: bool) -> list[object]:
        return [[], {"event": "HandEnd"}]

    monkeypatch.setattr(pack_mod, "read_ndjson", _fake_read_ndjson)

    p = tmp_path / "pack.json"
    p.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": RULESET_ID,
                "ruleset_label": None,
                "fixtures": [
                    {
                        "event_stream_ref": f"path:{es}",
                        "event_stream_digest": {"alg": "sha256", "hex": digest_hex},
                        "ruleset_id": RULESET_ID,
                        "options_hash": "0" * 64,
                        "provenance_ref": "artifact://prov",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FixturesPackError) as exc:
        validate_pack(p, strict_mode=True, require_non_empty=False)
    assert exc.value.code == "PACK_INVALID"
    assert exc.value.details["failures"][0]["code"] == "EVENT_STREAM_HEADER_DIGEST_FAIL"
