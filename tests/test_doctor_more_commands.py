from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.contractkit import canonicalize_json_bytes
from poker2.evaluation.fixtures.pack import pack_digest
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.run_id import run_id_v1
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


def test_doctor_ruleset_pass_and_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "ruleset.json"
    good.write_text(
        json.dumps(
            {
                "game_kind": "NLHE",
                "blinds": {"sb_chips": 1, "bb_chips": 2},
                "ante": None,
                "straddle": None,
                "rake": None,
                "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": True},
            }
        ),
        encoding="utf-8",
    )
    rc = doctor.main(["ruleset", "--path", str(good)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"

    bad = tmp_path / "bad_ruleset.json"
    bad.write_text(json.dumps({"game_kind": "PLO"}), encoding="utf-8")
    rc = doctor.main(["ruleset", "--path", str(bad)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"
    assert out["check_id"] == "Protocol.RuleSet"


def test_doctor_hrc_ruleset_pass_and_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
        ["hrc-ruleset", "--settings", str(settings), "--no-reopen-on-short-allin"]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"

    rc = doctor.main(["hrc-ruleset", "--settings", str(settings)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"
    assert out["check_id"] == "Tools.HRCImport"


def test_doctor_eventstream_digest_pass_and_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    es = tmp_path / "hand.ndjson"
    _write_eventstream(
        es,
        [{"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}],
    )
    rc = doctor.main(["eventstream-digest", "--path", str(es)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"

    bad = tmp_path / "bad.ndjson"
    bad.write_bytes(b'{"a":1}')
    rc = doctor.main(["eventstream-digest", "--path", str(bad)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"
    assert out["check_id"] == "Events.EventStreamArtifact"


def test_doctor_fixtures_pack_digest_and_validate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    es = tmp_path / "hand.ndjson"
    digest_hex = _write_eventstream(
        es,
        [{"event": "HandEnd", "rake_base_pot_chips": 0, "total_rake_chips": 0}],
    )

    pack = tmp_path / "pack.json"
    pack.write_text(
        json.dumps(
            {
                "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
                "ruleset_id": "0" * 64,
                "ruleset_label": "internal_ruleset_v1",
                "checked_items_covered": ["rake", "allin_reopen"],
                "platform": "internal",
                "fixtures": [
                    {
                        "event_stream_ref": f"path:{es}",
                        "event_stream_digest": {"alg": "sha256", "hex": digest_hex},
                        "ruleset_id": "0" * 64,
                        "options_hash": "0" * 64,
                        "provenance_ref": "artifact://prov",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    expected = pack_digest(pack)["hex"]

    rc = doctor.main(["fixtures-pack-digest", "--path", str(pack)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["digest"]["hex"] == expected

    rc = doctor.main(["fixtures-pack-validate", "--path", str(pack)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"

    bad_pack = tmp_path / "bad_pack.json"
    bad_pack.write_text(json.dumps({"fixtures_pack_schema_id": "nope"}), encoding="utf-8")
    rc = doctor.main(["fixtures-pack-validate", "--path", str(bad_pack)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"
    assert out["check_id"] == "GoldenFixtures.Pack"


def test_doctor_scenario_gate_pass(capsys: pytest.CaptureFixture[str]) -> None:
    repo = Path(__file__).resolve().parents[1]
    scenario_path = repo / "specs" / "scenarios" / "internal_hu_v1.json"
    ruleset_path = repo / "specs" / "rulesets" / "internal_ruleset_v1.json"

    rc = doctor.main(["scenario-gate", "--scenario", str(scenario_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["scenario_id"] == "9c73c2e69f81fbcca8725f6892bd4aee7453df03dd059643feed73c11dccd5a3"


def test_doctor_scenario_gate_fails_on_triad_mismatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = Path(__file__).resolve().parents[1]
    src = repo / "specs" / "scenarios" / "internal_hu_v1.json"
    ruleset_path = repo / "specs" / "rulesets" / "internal_ruleset_v1.json"

    pkg = json.loads(src.read_text(encoding="utf-8"))
    pkg.pop("scenario_id", None)
    pkg.pop("scenario_family_key", None)
    pkg["triad"]["rake_id"] = "0" * 64

    bad = tmp_path / "bad_scenario.json"
    bad.write_text(json.dumps(pkg, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    rc = doctor.main(["scenario-gate", "--scenario", str(bad), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"
    reasons = {f.get("reason") for f in out.get("failures", []) if isinstance(f, dict)}
    assert "triad_mismatch" in reasons
