from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from poker2.contractkit import canonicalize_json_bytes, validate_digest_object


@dataclass(frozen=True)
class EventStreamError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def canonical_ndjson_line(obj: Any, *, strict_mode: bool) -> bytes:
    return canonicalize_json_bytes(obj, strict_mode=strict_mode)


_HEADER_REQUIRED_FIELDS = (
    "run_id",
    "options_hash",
    "seed",
    "scenario_id",
    "schema_hash",
    "event_model_id",
    "event_stream_digest",
    "provenance_ref",
    "resolved_paths_digest",
    "repro_tier",
)


def _validate_header(obj: Any, *, strict_mode: bool) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise EventStreamError("HEADER_NOT_OBJECT", "EventStream header must be a JSON object")
    missing = [k for k in _HEADER_REQUIRED_FIELDS if k not in obj]
    if missing:
        raise EventStreamError("HEADER_MISSING_FIELDS", f"EventStream header missing fields: {missing}")
    run_id = obj.get("run_id")
    if not isinstance(run_id, str):
        raise EventStreamError("HEADER_RUN_ID_INVALID", "run_id must be sha256 hex string")
    try:
        validate_digest_object({"alg": "sha256", "hex": run_id}, strict_mode=True)
    except Exception as e:
        raise EventStreamError("HEADER_RUN_ID_INVALID", f"run_id must be sha256 hex string: {e}") from e

    seed = obj.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise EventStreamError("HEADER_SEED_INVALID", "seed must be int")
    try:
        validate_digest_object(obj["event_stream_digest"], strict_mode=True)
    except Exception as e:
        raise EventStreamError("HEADER_DIGEST_INVALID", f"event_stream_digest invalid: {e}") from e
    return obj


def event_stream_digest_from_objects(objs: Iterable[Any], *, strict_mode: bool) -> str:
    seq = list(objs)
    if strict_mode:
        if not seq:
            raise EventStreamError("EMPTY_EVENTSTREAM", "EventStream must contain header and events")
        _validate_header(seq[0], strict_mode=True)

    h = hashlib.sha256()
    for idx, obj in enumerate(seq):
        obj_for_hash: Any = obj
        if idx == 0 and isinstance(obj, dict) and "event_stream_digest" in obj:
            obj_for_hash = {k: v for k, v in obj.items() if k != "event_stream_digest"}

        line = canonical_ndjson_line(obj_for_hash, strict_mode=strict_mode)
        if idx:
            h.update(b"\n")
        h.update(line)
    h.update(b"\n")
    return h.hexdigest()


def read_ndjson(path: Path, *, strict_mode: bool) -> list[Any]:
    raw = path.read_bytes()
    if b"\r" in raw:
        raise EventStreamError("CRLF_NOT_ALLOWED", "EventStream must be LF-only (no CRLF)")
    if not raw.endswith(b"\n"):
        raise EventStreamError("MISSING_TRAILING_LF", "EventStream must end with LF")

    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines = lines[:-1]

    if strict_mode:
        if any(line == b"" for line in lines):
            raise EventStreamError("EMPTY_LINE_NOT_ALLOWED", "EventStream must not contain empty lines")

    out: list[Any] = []
    for i, line in enumerate(lines, start=1):
        if line == b"":
            continue
        try:
            obj = json.loads(line.decode("utf-8"))
        except Exception as e:
            raise EventStreamError("JSON_PARSE_FAIL", f"line {i} JSON parse failed: {e}") from e
        out.append(obj)
    return out


def event_stream_digest_from_file(path: Path, *, strict_mode: bool) -> str:
    objs = read_ndjson(path, strict_mode=strict_mode)
    return event_stream_digest_from_objects(objs, strict_mode=strict_mode)
