from __future__ import annotations

# Golden fixtures pack utilities (directory layout per ARCHIETECTURE.md §8, Informative).

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, validate_digest_object
from poker2.protocol.eventstream import EventStreamError, event_stream_digest_from_file, read_ndjson


@dataclass(frozen=True)
class FixturesPackError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pack_digest(path: Path) -> dict[str, str]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    digest_hex = _sha256_hex(canonicalize_json_bytes(obj, strict_mode=True))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def validate_pack(
    path: Path,
    *,
    strict_mode: bool,
    require_non_empty: bool,
    expected_ruleset_id: str | None = None,
    required_checked_items: list[str] | None = None,
) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise FixturesPackError("PACK_UNREADABLE", "pack JSON unreadable", {"error": str(e)}) from e

    if not isinstance(obj, dict):
        raise FixturesPackError("PACK_NOT_OBJECT", "pack must be JSON object")

    if obj.get("fixtures_pack_schema_id") != "golden_fixtures_pack_v1":
        raise FixturesPackError("PACK_SCHEMA_MISMATCH", "unexpected fixtures_pack_schema_id")

    ruleset_id = obj.get("ruleset_id")
    if not isinstance(ruleset_id, str):
        raise FixturesPackError("PACK_RULESET_ID_MISSING", "ruleset_id must be sha256 hex string")
    try:
        validate_digest_object({"alg": "sha256", "hex": ruleset_id}, strict_mode=True)
    except Exception as e:
        raise FixturesPackError("PACK_RULESET_ID_INVALID", f"ruleset_id invalid: {e}") from e

    if expected_ruleset_id is not None and ruleset_id != expected_ruleset_id:
        raise FixturesPackError(
            "PACK_RULESET_ID_MISMATCH",
            f"pack ruleset_id mismatch: got={ruleset_id!r}",
            {"expected": expected_ruleset_id},
        )

    ruleset_label = obj.get("ruleset_label")
    if ruleset_label is not None and not isinstance(ruleset_label, str):
        raise FixturesPackError("PACK_RULESET_LABEL_INVALID", "ruleset_label must be string or null")

    fixtures = obj.get("fixtures")
    if not isinstance(fixtures, list):
        raise FixturesPackError("PACK_FIXTURES_NOT_ARRAY", "fixtures must be array")

    if required_checked_items is not None:
        covered = obj.get("checked_items_covered")
        if not isinstance(covered, list) or not all(isinstance(x, str) for x in covered):
            raise FixturesPackError("PACK_COVERAGE_INVALID", "checked_items_covered must be array of strings")
        missing = [x for x in required_checked_items if x not in covered]
        if missing:
            raise FixturesPackError("PACK_COVERAGE_MISSING", "missing required checked_items_covered", {"missing": missing})

    if require_non_empty and len(fixtures) == 0:
        raise FixturesPackError("PACK_EMPTY", "fixtures pack must be non-empty")

    failures: list[dict[str, Any]] = []
    for idx, fixture in enumerate(fixtures):
        if not isinstance(fixture, dict):
            failures.append({"index": idx, "code": "FIXTURE_NOT_OBJECT"})
            continue

        missing = [k for k in ("event_stream_ref", "event_stream_digest", "ruleset_id", "options_hash", "provenance_ref") if k not in fixture]
        if missing:
            failures.append({"index": idx, "code": "FIXTURE_MISSING_FIELDS", "missing": missing})
            continue

        event_stream_ref = fixture["event_stream_ref"]
        if not (isinstance(event_stream_ref, str) and event_stream_ref.startswith("path:")):
            failures.append({"index": idx, "code": "EVENT_STREAM_REF_INVALID"})
            continue

        event_stream_digest = fixture["event_stream_digest"]
        try:
            validate_digest_object(event_stream_digest, strict_mode=True)
        except Exception as e:
            failures.append({"index": idx, "code": "EVENT_STREAM_DIGEST_INVALID", "message": str(e)})
            continue

        es_path = Path(event_stream_ref.removeprefix("path:"))
        if not es_path.exists():
            failures.append({"index": idx, "code": "EVENT_STREAM_MISSING", "path": str(es_path)})
            continue

        try:
            computed_hex = event_stream_digest_from_file(es_path, strict_mode=strict_mode)
        except Exception as e:
            failures.append({"index": idx, "code": "EVENT_STREAM_DIGEST_FAIL", "message": str(e)})
            continue

        if computed_hex != event_stream_digest["hex"]:
            failures.append(
                {
                    "index": idx,
                    "code": "EVENT_STREAM_DIGEST_MISMATCH",
                    "expected": event_stream_digest["hex"],
                    "computed": computed_hex,
                }
            )
            continue

        if fixture.get("ruleset_id") != ruleset_id:
            failures.append(
                {
                    "index": idx,
                    "code": "FIXTURE_RULESET_ID_MISMATCH",
                    "pack_ruleset_id": ruleset_id,
                    "fixture_ruleset_id": fixture.get("ruleset_id"),
                }
            )
            continue

        if strict_mode:
            try:
                header = read_ndjson(es_path, strict_mode=True)[0]
                if not isinstance(header, dict):
                    raise EventStreamError("HEADER_NOT_OBJECT", "EventStream header must be a JSON object")
                hdr_digest = header.get("event_stream_digest")
                validate_digest_object(hdr_digest, strict_mode=True)
                if hdr_digest["hex"] != computed_hex:
                    failures.append(
                        {
                            "index": idx,
                            "code": "EVENT_STREAM_HEADER_DIGEST_MISMATCH",
                            "expected": computed_hex,
                            "header": hdr_digest["hex"],
                        }
                    )
                    continue
            except Exception as e:
                failures.append({"index": idx, "code": "EVENT_STREAM_HEADER_DIGEST_FAIL", "message": str(e)})
                continue

    if failures:
        raise FixturesPackError("PACK_INVALID", "fixtures pack invalid", {"failures": failures})

    return {
        "pack_ref": f"path:{path}",
        "pack_digest": pack_digest(path),
        "ruleset_id": ruleset_id,
        "ruleset_label": ruleset_label,
        "fixtures_count": len(fixtures),
    }
