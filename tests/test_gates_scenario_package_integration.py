from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.gates import GateCheckError, check_eventstream_gates
from poker2.protocol.eventstream import read_ndjson
from poker2.protocol.paths import default_paths_config
from poker2.protocol.ruleset import validate_ruleset


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_ruleset() -> dict:
    repo = _repo_root()
    return json.loads((repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_text(encoding="utf-8"))


def _load_scenario_pkg() -> dict:
    repo = _repo_root()
    return json.loads((repo / "specs" / "scenarios" / "internal_hu_v1.json").read_text(encoding="utf-8"))


def _load_eventstream() -> tuple[dict, list[dict]]:
    repo = _repo_root()
    path = repo / "fixtures" / "internal" / "eventstreams" / "internal_v1_preflop_fold.ndjson"
    objs = read_ndjson(path, strict_mode=True)
    return objs[0], [e for e in objs[1:] if isinstance(e, dict)]


def test_check_eventstream_gates_with_scenario_package() -> None:
    header, events = _load_eventstream()
    ruleset = _load_ruleset()
    validate_ruleset(ruleset, strict_mode=True)

    out = check_eventstream_gates(
        header=header,
        events=events,
        event_stream_ref=None,
        event_stream_digest=None,
        ruleset=ruleset,
        scenario_package=_load_scenario_pkg(),
        requested_scenario_ref="internal_hu_v1",
        paths_config=default_paths_config(strict_mode=True),
        strict_mode=True,
    )
    assert out["status"] == "pass"


def test_check_eventstream_gates_requires_paths_config() -> None:
    header, events = _load_eventstream()
    ruleset = _load_ruleset()
    validate_ruleset(ruleset, strict_mode=True)

    with pytest.raises(GateCheckError) as exc:
        check_eventstream_gates(
            header=header,
            events=events,
            event_stream_ref=None,
            event_stream_digest=None,
            ruleset=ruleset,
            scenario_package=_load_scenario_pkg(),
            requested_scenario_ref="internal_hu_v1",
            paths_config=None,
            strict_mode=True,
        )
    assert exc.value.code == "MISSING_FIELDS"
