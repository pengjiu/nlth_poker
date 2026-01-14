from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.eventstream import event_stream_digest_from_file, read_ndjson
from poker2.cli import run_batch


def _write_settings(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "handdata": {"blinds": [2, 1, 0], "anteType": "OFF", "straddleType": "OFF"},
                "eqmodel": {"raked": False, "nfnd": False, "rakepct": 0.0, "rakecap": 0},
            }
        ),
        encoding="utf-8",
    )


def test_run_batch_writes_multiple_eventstreams(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings)
    out_dir = tmp_path / "outs"

    rc = run_batch.main(
        [
            "--settings",
            str(settings),
            "--out-dir",
            str(out_dir),
            "--hands",
            "3",
            "--starting-stacks-by-seat",
            json.dumps({"1": 50, "2": 50}),
            "--button-seat",
            "1",
            "--no-reopen-on-short-allin",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["hands"] == 3
    assert out_dir.exists()

    files = sorted(out_dir.glob("hand_*.ndjson"))
    assert len(files) == 3
    for f in files:
        computed = event_stream_digest_from_file(f, strict_mode=True)
        header = read_ndjson(f, strict_mode=True)[0]
        assert header["event_stream_digest"]["hex"] == computed


def test_run_batch_rejects_nonpositive_hands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings)
    out_dir = tmp_path / "outs"

    rc = run_batch.main(
        [
            "--settings",
            str(settings),
            "--out-dir",
            str(out_dir),
            "--hands",
            "0",
            "--starting-stacks-by-seat",
            json.dumps({"1": 50, "2": 50}),
            "--button-seat",
            "1",
            "--no-reopen-on-short-allin",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "VALUE_ERROR"


def test_run_batch_rejects_invalid_starting_stacks_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings)
    out_dir = tmp_path / "outs"

    rc = run_batch.main(
        [
            "--settings",
            str(settings),
            "--out-dir",
            str(out_dir),
            "--hands",
            "1",
            "--starting-stacks-by-seat",
            "not-json",
            "--button-seat",
            "1",
            "--no-reopen-on-short-allin",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["error"]["code"] == "JSON_PARSE_FAIL"
