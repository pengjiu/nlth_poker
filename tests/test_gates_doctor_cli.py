from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.cli import doctor
from poker2.protocol.eventstream import event_stream_digest_from_objects, read_ndjson
from poker2.protocol.provenance import provenance_id, validate_provenance_envelope
from poker2.runtime.artifacts import write_canonical_ndjson


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_doctor_fixtures_pack_gates_pass(capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_root()
    pack_path = repo / "fixtures" / "internal" / "internal_ruleset_v1_pack.json"
    ruleset_path = repo / "specs" / "rulesets" / "internal_ruleset_v1.json"

    rc = doctor.main(["fixtures-pack-gates", "--pack", str(pack_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["failures_count"] == 0


def test_doctor_eventstream_gates_fails_on_unresolvable_provenance_ref(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo_root()
    ruleset_path = repo / "specs" / "rulesets" / "internal_ruleset_v1.json"
    src = repo / "fixtures" / "internal" / "eventstreams" / "internal_v1_preflop_fold.ndjson"

    objs = read_ndjson(src, strict_mode=True)
    header = objs[0]
    events = [e for e in objs[1:] if isinstance(e, dict)]

    bad_ref = f"artifact://{'1' * 64}"
    header["provenance_ref"] = bad_ref
    for e in events:
        if e.get("event") == "HandStart":
            e["provenance_ref"] = bad_ref

    header["event_stream_digest"] = {"alg": "sha256", "hex": "0" * 64}
    header["event_stream_digest"]["hex"] = event_stream_digest_from_objects([header, *events], strict_mode=True)

    out_path = tmp_path / "bad_prov.ndjson"
    write_canonical_ndjson(out_path, [header, *events], strict_mode=True)

    rc = doctor.main(["eventstream-gates", "--eventstream", str(out_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["status"] == "fail"

    reasons = {
        f.get("reason")
        for f in out.get("failures", [])
        if isinstance(f, dict) and f.get("gate_id") == "Gates.Provenance"
    }
    assert "provenance_ref_unresolvable" in reasons


def test_doctor_eventstream_gates_with_scenario_pass(capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_root()
    ruleset_path = repo / "specs" / "rulesets" / "internal_ruleset_v1.json"
    eventstream_path = repo / "fixtures" / "internal" / "eventstreams" / "internal_v1_preflop_fold.ndjson"

    rc = doctor.main(
        [
            "eventstream-gates",
            "--eventstream",
            str(eventstream_path),
            "--ruleset",
            str(ruleset_path),
            "--scenario",
            "internal_hu_v1",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"


def test_internal_provenance_artifacts_are_content_addressed() -> None:
    repo = _repo_root()
    artifacts_dir = repo / "fixtures" / "internal" / "artifacts"
    paths = sorted(artifacts_dir.glob("*.json"))
    assert paths, "expected internal provenance artifacts to exist"

    for path in paths:
        obj = json.loads(path.read_text(encoding="utf-8"))
        validate_provenance_envelope(obj, strict_mode=True)
        pid = provenance_id(obj, strict_mode=True)
        assert path.stem == pid
