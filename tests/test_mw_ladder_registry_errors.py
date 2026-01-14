from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.mw_ladder import load_mw_ladder_spec
from poker2.runtime.mw_ladder_registry import MWLadderRegistryError, build_mw_ladder_registry


def test_build_mw_ladder_registry_empty_root(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    out = build_mw_ladder_registry(mw_ladders_root=root, strict_mode=True)
    assert out == {}


def test_build_mw_ladder_registry_invalid_spec(tmp_path: Path) -> None:
    root = tmp_path / "mw"
    root.mkdir(parents=True, exist_ok=True)
    bad = {"mw_ladder_schema_id": "bad", "rungs": []}
    (root / "bad.json").write_text(json.dumps(bad, sort_keys=True), encoding="utf-8")

    with pytest.raises(MWLadderRegistryError) as exc:
        build_mw_ladder_registry(mw_ladders_root=root, strict_mode=True)
    assert exc.value.code == "MW_LADDER_INVALID"


def test_build_mw_ladder_registry_ambiguous(tmp_path: Path) -> None:
    root = tmp_path / "mw"
    root.mkdir(parents=True, exist_ok=True)
    spec = load_mw_ladder_spec(Path("specs/mw_ladders/internal_mw_ladder_v1.json"))
    payload = json.dumps(spec, sort_keys=True)
    (root / "a.json").write_text(payload, encoding="utf-8")
    (root / "b.json").write_text(payload, encoding="utf-8")

    with pytest.raises(MWLadderRegistryError) as exc:
        build_mw_ladder_registry(mw_ladders_root=root, strict_mode=True)
    assert exc.value.code == "AMBIGUOUS"
