from __future__ import annotations

from pathlib import Path

import pytest

from poker2.contractkit import canonicalize_json_bytes
from poker2.protocol.run_id import run_id_v1
from poker2.protocol.eventstream import (
    EventStreamError,
    event_stream_digest_from_file,
    event_stream_digest_from_objects,
    read_ndjson,
)


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


def test_event_stream_digest_excludes_header_event_stream_digest_field() -> None:
    header = _header(digest_hex="0" * 64)
    event = {"event": "HandEnd", "rake_base_pot_chips": 10, "total_rake_chips": 1}
    d1 = event_stream_digest_from_objects([header, event], strict_mode=True)

    header2 = _header(digest_hex="f" * 64)
    d2 = event_stream_digest_from_objects([header2, event], strict_mode=True)
    assert d1 == d2


def test_event_stream_digest_from_file_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "stream.ndjson"
    header = _header(digest_hex="0" * 64)
    event = {"event": "HandEnd", "rake_base_pot_chips": 10, "total_rake_chips": 1}
    digest = event_stream_digest_from_objects([header, event], strict_mode=True)

    header["event_stream_digest"]["hex"] = digest
    _write_ndjson(p, [header, event])
    assert event_stream_digest_from_file(p, strict_mode=True) == digest

    # Tamper header field: digest should stay stable (it is excluded from hash input).
    objs = read_ndjson(p, strict_mode=True)
    objs[0]["event_stream_digest"]["hex"] = "f" * 64
    _write_ndjson(p, objs)
    assert event_stream_digest_from_file(p, strict_mode=True) == digest


def test_read_ndjson_requires_trailing_lf(tmp_path: Path) -> None:
    p = tmp_path / "bad.ndjson"
    p.write_bytes(b'{"a":1}')
    with pytest.raises(EventStreamError) as exc:
        read_ndjson(p, strict_mode=True)
    assert exc.value.code == "MISSING_TRAILING_LF"


def test_read_ndjson_rejects_crlf(tmp_path: Path) -> None:
    p = tmp_path / "bad.ndjson"
    p.write_bytes(b'{"a":1}\r\n')
    with pytest.raises(EventStreamError) as exc:
        read_ndjson(p, strict_mode=True)
    assert exc.value.code == "CRLF_NOT_ALLOWED"


def test_read_ndjson_rejects_empty_lines_in_strict(tmp_path: Path) -> None:
    p = tmp_path / "bad.ndjson"
    p.write_bytes(b'{"a":1}\n\n')
    with pytest.raises(EventStreamError) as exc:
        read_ndjson(p, strict_mode=True)
    assert exc.value.code == "EMPTY_LINE_NOT_ALLOWED"


def test_event_stream_digest_requires_header(tmp_path: Path) -> None:
    with pytest.raises(EventStreamError) as exc:
        event_stream_digest_from_objects([], strict_mode=True)
    assert exc.value.code == "EMPTY_EVENTSTREAM"
