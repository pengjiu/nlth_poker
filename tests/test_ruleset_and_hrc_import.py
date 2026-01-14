from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.ruleset import ruleset_id, ruleset_rake_id, validate_ruleset
from poker2.cli.hrc_import_ruleset import ImportError, import_ruleset_from_hrc_settings


def _write_settings(path: Path, *, raked: bool) -> None:
    doc = {
        "handdata": {
            "blinds": [2, 1, 0],
            "anteType": "OFF",
            "straddleType": "OFF",
        },
        "eqmodel": {
            "raked": raked,
            "nfnd": False,
            "rakepct": 0.05,
            "rakecap": 0,
        },
    }
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def test_ruleset_id_is_canonicalization_stable() -> None:
    r1 = {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": None,
        "straddle": None,
        "rake": None,
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": True},
    }
    r2 = {
        "min_raise_rule": {"reopen_on_short_allin": True, "basis": "last_raise_increment"},
        "rake": None,
        "straddle": None,
        "ante": None,
        "blinds": {"bb_chips": 2, "sb_chips": 1},
        "game_kind": "NLHE",
    }
    assert ruleset_id(r1, strict_mode=True) == ruleset_id(r2, strict_mode=True)


def test_ruleset_rake_id_only_depends_on_rake() -> None:
    r1 = {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": None,
        "straddle": None,
        "rake": {
            "pct_ppm": 50_000,
            "cap_chips": None,
            "rounding_mode": "floor",
            "no_flop_no_drop": False,
        },
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": True},
    }
    r2 = {**r1, "blinds": {"sb_chips": 2, "bb_chips": 4}}
    assert ruleset_rake_id(r1, strict_mode=True) == ruleset_rake_id(r2, strict_mode=True)


def test_hrc_import_requires_explicit_reopen_flag(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=False)
    with pytest.raises(ImportError) as exc:
        import_ruleset_from_hrc_settings(settings, rounding_mode=None, reopen_on_short_allin=None)
    assert exc.value.code == "MISSING_REOPEN_FLAG"


def test_hrc_import_requires_rounding_mode_when_raked(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=True)
    with pytest.raises(ImportError) as exc:
        import_ruleset_from_hrc_settings(settings, rounding_mode=None, reopen_on_short_allin=True)
    assert exc.value.code == "MISSING_ROUNDING_MODE"


def test_hrc_import_outputs_ruleset_and_ids(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=True)
    out = import_ruleset_from_hrc_settings(
        settings,
        rounding_mode="nearest_ties_up",
        reopen_on_short_allin=False,
    )
    validate_ruleset(out["ruleset"], strict_mode=True)
    assert out["ruleset"]["rake"]["pct_ppm"] == 50_000
    assert out["ruleset"]["rake"]["cap_chips"] is None
    assert out["ruleset"]["rake"]["rounding_mode"] == "nearest_ties_up"
    assert out["ruleset"]["min_raise_rule"]["reopen_on_short_allin"] is False
    assert isinstance(out["ruleset_id"], str) and len(out["ruleset_id"]) == 64
    assert isinstance(out["ruleset_rake_id"], str) and len(out["ruleset_rake_id"]) == 64
    assert out["ruleset_hash"] == out["ruleset_id"]
