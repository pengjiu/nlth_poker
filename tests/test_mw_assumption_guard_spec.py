from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.mw_assumption_guard import (
    MWAssumptionGuardError,
    load_mw_assumption_guard_spec,
    mw_assumption_guard_id,
    validate_mw_assumption_guard_spec,
)


def test_mw_assumption_guard_spec_roundtrip() -> None:
    path = Path("specs/mw_assumption_guards/internal_mw_guard_v1.json")
    spec = load_mw_assumption_guard_spec(path)
    validate_mw_assumption_guard_spec(spec, strict_mode=True)
    gid = mw_assumption_guard_id(spec, strict_mode=True)
    assert isinstance(gid, str) and len(gid) == 64


def test_mw_assumption_guard_spec_invalid_type() -> None:
    with pytest.raises(MWAssumptionGuardError) as exc:
        validate_mw_assumption_guard_spec([], strict_mode=True)
    assert exc.value.code == "TYPE_ERROR"


def test_mw_assumption_guard_spec_invalid_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"mw_assumption_guard_schema_id": "bad", "assumption": {}, "guard": {}}, sort_keys=True), encoding="utf-8")
    spec = load_mw_assumption_guard_spec(path)
    with pytest.raises(MWAssumptionGuardError) as exc:
        validate_mw_assumption_guard_spec(spec, strict_mode=True)
    assert exc.value.code == "UNSUPPORTED_VALUE"
