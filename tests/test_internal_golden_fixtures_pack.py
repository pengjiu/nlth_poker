from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.cli import stats
from poker2.evaluation.fixtures.pack import pack_digest, validate_pack


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_internal_golden_fixtures_pack_is_pinned_and_passes_stats(
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo_root()
    pack_path = repo / "fixtures" / "internal" / "internal_ruleset_v1_pack.json"
    ruleset_path = repo / "specs" / "rulesets" / "internal_ruleset_v1.json"

    summary = validate_pack(pack_path, strict_mode=True, require_non_empty=True)
    assert summary["fixtures_count"] >= 6

    digest = pack_digest(pack_path)
    assert digest == {"alg": "sha256", "hex": "bd556b05115e69b4c9dd3340e4924b85ac3b71bf2473bb85aaeb17308c4afa57"}

    rc = stats.main(["fixtures-pack", "--pack", str(pack_path), "--ruleset", str(ruleset_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"
    assert out["failures_count"] == 0
