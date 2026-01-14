from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.contractkit import run_vectors


def test_run_vectors_reports_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vectors = {
        "vector_schema_id": "contractkit_vectors_v1",
        "spec_ref": {"path": "contractkit/spec/contractkit_spec_v1.json"},
        "cases": [
            {
                "name": "canonical_mismatch",
                "op": "canonical_sha256",
                "input": {"a": 1},
                "expected": {"canonical_json": "{\"a\":2}", "sha256_hex": "0" * 64},
            },
            {"name": "unknown_op", "op": "nope", "input": {}},
            {
                "name": "expected_error_but_succeeded",
                "op": "validate_digest_object",
                "input": {"alg": "sha256", "hex": "0" * 64},
                "expect_error": {"code": "SOME_ERROR"},
            },
        ],
    }
    path = tmp_path / "vectors.json"
    path.write_text(json.dumps(vectors, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(run_vectors, "VECTORS_PATH", path)
    rc = run_vectors.main()
    out = json.loads(capsys.readouterr().out)

    assert rc == 2
    assert out["status"] == "fail"
    assert len(out["failures"]) == 3


def test_run_vectors_reports_sha_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical = run_vectors.canonicalize_json_bytes({"a": 1}, strict_mode=True).decode("utf-8")
    vectors = {
        "vector_schema_id": "contractkit_vectors_v1",
        "spec_ref": {"path": "contractkit/spec/contractkit_spec_v1.json"},
        "cases": [
            {
                "name": "sha_mismatch",
                "op": "canonical_sha256",
                "input": {"a": 1},
                "expected": {"canonical_json": canonical, "sha256_hex": "0" * 64},
            }
        ],
    }
    path = tmp_path / "vectors.json"
    path.write_text(json.dumps(vectors, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(run_vectors, "VECTORS_PATH", path)
    rc = run_vectors.main()
    out = json.loads(capsys.readouterr().out)

    assert rc == 2
    assert out["status"] == "fail"
    assert out["failures"][0]["name"] == "sha_mismatch"
