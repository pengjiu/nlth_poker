from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.cli import hrc_import_ruleset
from poker2.protocol.paths import validate_paths_config


def _write_settings(path: Path, *, raked: bool) -> None:
    path.write_text(
        json.dumps(
            {
                "handdata": {"blinds": [2, 1, 0], "anteType": "OFF", "straddleType": "OFF"},
                "eqmodel": {"raked": raked, "nfnd": False, "rakepct": 0.05, "rakecap": 0},
            }
        ),
        encoding="utf-8",
    )


def test_hrc_import_main_missing_reopen_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=False)

    rc = hrc_import_ruleset.main(["--settings", str(settings)])
    out = json.loads(capsys.readouterr().out)

    assert rc == 2
    assert out["status"] == "fail"
    assert out["error"]["code"] == "MISSING_REOPEN_FLAG"


def test_hrc_import_main_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=True)

    rc = hrc_import_ruleset.main(
        [
            "--settings",
            str(settings),
            "--rounding-mode",
            "floor",
            "--no-reopen-on-short-allin",
        ]
    )
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["status"] == "pass"
    assert len(out["ruleset_id"]) == 64


def test_hrc_import_via_paths_config(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=True)

    paths_config = {
        "roots": {
            "scenario_root": "path:specs",
            "artifacts_root": "path:artifacts",
            "data_root": "path:data",
            "hrc_root": str(tmp_path),
        },
        "search_order": ["scenario_root", "artifacts_root", "data_root", "hrc_root"],
        "allow_symlink": True,
    }
    validate_paths_config(paths_config, strict_mode=True)

    out = hrc_import_ruleset.import_ruleset_from_hrc_settings(
        Path("settings.json"),
        rounding_mode="floor",
        reopen_on_short_allin=False,
        paths_config=paths_config,
    )

    assert out["ruleset_id"] and len(out["ruleset_id"]) == 64
