from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.mw_assumption_guard import load_mw_assumption_guard_spec, mw_assumption_guard_id
from poker2.runtime.mw_assumption_guard_registry import MWAssumptionGuardRegistryError, build_mw_assumption_guard_registry


def test_mw_assumption_guard_registry_contains_internal() -> None:
    spec = load_mw_assumption_guard_spec(Path("specs/mw_assumption_guards/internal_mw_guard_v1.json"))
    gid = mw_assumption_guard_id(spec, strict_mode=True)
    reg = build_mw_assumption_guard_registry(strict_mode=True)
    assert gid in reg


def test_mw_assumption_guard_registry_empty_root(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    out = build_mw_assumption_guard_registry(mw_assumption_guards_root=root, strict_mode=True)
    assert out == {}


def test_mw_assumption_guard_registry_ambiguous(tmp_path: Path) -> None:
    root = tmp_path / "guards"
    root.mkdir(parents=True, exist_ok=True)
    spec = load_mw_assumption_guard_spec(Path("specs/mw_assumption_guards/internal_mw_guard_v1.json"))
    payload = json.dumps(spec, sort_keys=True)
    (root / "a.json").write_text(payload, encoding="utf-8")
    (root / "b.json").write_text(payload, encoding="utf-8")

    with pytest.raises(MWAssumptionGuardRegistryError) as exc:
        build_mw_assumption_guard_registry(mw_assumption_guards_root=root, strict_mode=True)
    assert exc.value.code == "AMBIGUOUS"
