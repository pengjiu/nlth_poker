from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.cli import doctor


def test_doctor_contractkit_vectors(capsys: pytest.CaptureFixture[str]) -> None:
    rc = doctor.main(["contractkit-vectors"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"


def test_doctor_profile_auto(capsys: pytest.CaptureFixture[str]) -> None:
    rc = doctor.main(["profile-auto"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert len(out["profile_id"]) == 64


def test_doctor_options_hash_from_hrc(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "handdata": {"blinds": [2, 1, 0], "anteType": "OFF", "straddleType": "OFF"},
                "eqmodel": {"raked": False, "nfnd": False, "rakepct": 0.0, "rakecap": 0},
            }
        ),
        encoding="utf-8",
    )
    rc = doctor.main(
        [
            "options-hash-from-hrc",
            "--settings",
            str(settings),
            "--no-reopen-on-short-allin",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert len(out["options_hash"]) == 64

