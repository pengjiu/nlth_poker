from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.contractkit import canonicalize_json_bytes
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.run_id import run_id_v1
from poker2.protocol.ruleset import RuleSetError
from poker2.cli import doctor


def _write_ndjson(path: Path, objs: list[dict]) -> None:
    lines = [canonicalize_json_bytes(o, strict_mode=True) for o in objs]
    path.write_bytes(b"\n".join(lines) + b"\n")


def _header(*, digest_hex: str) -> dict:
    options_hash = "0" * 64
    seed = 0
    return {
        "run_id": run_id_v1(options_hash=options_hash, seed=seed, strict_mode=True),
        "options_hash": options_hash,
        "seed": seed,
        "scenario_id": "0" * 64,
        "schema_hash": "0" * 64,
        "event_model_id": "0" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": digest_hex},
        "provenance_ref": "artifact://prov",
        "resolved_paths_digest": "0" * 64,
        "repro_tier": "Tier-A",
    }


def _write_eventstream(path: Path, events: list[dict]) -> str:
    header = _header(digest_hex="0" * 64)
    digest_hex = event_stream_digest_from_objects([header, *events], strict_mode=True)
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(path, [header, *events])
    return digest_hex


def _write_settings(path: Path, *, raked: bool) -> None:
    path.write_text(
        json.dumps(
            {
                "handdata": {"blinds": [2, 1, 0], "anteType": "OFF", "straddleType": "OFF"},
                "eqmodel": {"raked": bool(raked), "nfnd": False, "rakepct": 0.05, "rakecap": 0},
            }
        ),
        encoding="utf-8",
    )


def test_doctor_profile_auto_reports_profile_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(doctor, "auto_profile_spec_throughput", lambda: {"profile_id": "0" * 64})
    rc = doctor.main(["profile-auto"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["check_id"] == "Protocol.ProfileSpec"
    assert out["error"]["code"] == "ID_MISMATCH"


def test_doctor_fixtures_pack_validate_reports_invalid_pack(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "pack.json"
    bad.write_text(json.dumps({"fixtures_pack_schema_id": "golden_fixtures_pack_v1"}), encoding="utf-8")
    rc = doctor.main(["fixtures-pack-validate", "--path", str(bad)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["check_id"] == "GoldenFixtures.Pack"
    assert out["error"]["code"] == "PACK_RULESET_ID_MISSING"


def test_doctor_fixtures_pack_digest_reports_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "pack.json"
    bad.write_text("{", encoding="utf-8")
    rc = doctor.main(["fixtures-pack-digest", "--path", str(bad)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["check_id"] == "Fixtures.PackDigest"


def test_doctor_eventstream_digest_reports_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.ndjson"
    bad.write_bytes(b'{"a":1}')
    rc = doctor.main(["eventstream-digest", "--path", str(bad)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["check_id"] == "Events.EventStreamArtifact"


def test_doctor_options_hash_from_hrc_reports_failure_without_reopen_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=False)

    rc = doctor.main(["options-hash-from-hrc", "--settings", str(settings)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"
    assert out["check_id"] == "Protocol.RunSpec"
    assert out["error"]["code"] == "MISSING_REOPEN_FLAG"


def test_doctor_hrc_ruleset_reports_ruleset_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = tmp_path / "settings.json"
    _write_settings(settings, raked=False)

    def _boom(_: object, *, strict_mode: bool) -> None:
        raise RuleSetError("BOOM", "nope")

    monkeypatch.setattr(doctor, "validate_ruleset", _boom)

    rc = doctor.main(["hrc-ruleset", "--settings", str(settings), "--no-reopen-on-short-allin"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"
    assert out["check_id"] == "Protocol.RuleSet"
