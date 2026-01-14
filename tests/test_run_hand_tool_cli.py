from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.eventstream import event_stream_digest_from_file, read_ndjson
from poker2.cli import run_hand
from poker2.protocol.run_manifest import validate_run_manifest
from poker2.protocol.mw_ladder import default_internal_mw_ladder


def _write_settings(path: Path, *, raked: bool) -> None:
    path.write_text(
        json.dumps(
            {
                "handdata": {"blinds": [2, 1, 0], "anteType": "OFF", "straddleType": "OFF"},
                "eqmodel": {"raked": bool(raked), "nfnd": False, "rakepct": 0.0, "rakecap": 0},
            }
        ),
        encoding="utf-8",
    )


def test_run_hand_from_hrc_writes_eventstream_and_reports_digest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=False)
    out_path = tmp_path / "hand.ndjson"

    rc = run_hand.main(
        [
            "--settings",
            str(settings),
            "--out",
            str(out_path),
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
    assert out_path.exists()

    computed = event_stream_digest_from_file(out_path, strict_mode=True)
    assert out["event_stream_digest"]["hex"] == computed

    header = read_ndjson(out_path, strict_mode=True)[0]
    assert header["event_stream_digest"]["hex"] == computed


def test_run_hand_multiway_defaults_internal_mw_ladder_in_strict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=False)
    out_path = tmp_path / "hand.ndjson"

    rc = run_hand.main(
        [
            "--settings",
            str(settings),
            "--out",
            str(out_path),
            "--starting-stacks-by-seat",
            json.dumps({"1": 50, "2": 50, "3": 50}),
            "--button-seat",
            "1",
            "--no-reopen-on-short-allin",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"

    _, mw_ladder_id = default_internal_mw_ladder(strict_mode=True)
    events = read_ndjson(out_path, strict_mode=True)[1:]
    routed = [e for e in events if isinstance(e, dict) and e.get("event") == "ActionChosen" and e.get("routing")]
    assert routed, "expected at least one routed ActionChosen in multi-way hand"
    assert all(e["routing"]["mw_ladder_id"] == mw_ladder_id for e in routed)


def test_run_hand_rejects_invalid_starting_stacks_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=False)
    out_path = tmp_path / "hand.ndjson"

    rc = run_hand.main(
        [
            "--settings",
            str(settings),
            "--out",
            str(out_path),
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


def test_run_hand_pipeline_writes_manifest_and_report(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=False)

    artifacts_root = tmp_path / "artifacts"
    out = run_hand.run_hand_from_hrc_settings(
        settings_path=settings,
        out_path=None,
        seed=123,
        strict_mode=True,
        rounding_mode=None,
        reopen_on_short_allin=False,
        starting_stacks_by_seat={1: 50, 2: 50},
        button_seat=1,
        mw_ladder_id=None,
        artifacts_root=artifacts_root,
    )
    assert out["status"] == "pass"
    run_id = out["run_id"]
    run_dir = artifacts_root / run_id
    eventstream_path = run_dir / "eventstream" / "eventstream.ndjson"
    manifest_path = run_dir / "manifest" / "run_manifest.json"
    runspec_path = run_dir / "manifest" / "runspec.json"
    report_path = run_dir / "report" / "report.json"
    assert eventstream_path.exists()
    assert manifest_path.exists()
    assert runspec_path.exists()
    assert report_path.exists()

    digest = event_stream_digest_from_file(eventstream_path, strict_mode=True)
    assert out["event_stream_digest"]["hex"] == digest

    manifest_obj = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_run_manifest(manifest_obj, strict_mode=True)

    report_obj = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_obj["run_manifest_digest"]["hex"] == out["run_manifest_digest"]["hex"]
