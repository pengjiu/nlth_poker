from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.runtime.system_policy import SystemPolicyError, build_system_policy
from poker2.protocol.policy import load_policy_spec


def test_system_policy_requires_postflop_dep() -> None:
    repo = Path(__file__).resolve().parents[1]
    pol_path = repo / "specs" / "policies" / "system_bot_policy_v1.json"
    pol = load_policy_spec(pol_path)
    # remove postflop dep
    pol = {**pol, "policy_deps": [d for d in pol.get("policy_deps", []) if "artifact://" not in str(d.get("artifact_ref", ""))]}
    ruleset = json.loads((repo / "specs" / "rulesets" / "internal_ruleset_v1.json").read_text())
    preflop_ranges = repo / "specs" / "preflop" / "preflop_ranges_v1.json"
    preflop_freq = repo / "specs" / "preflop" / "preflop_freq_v1.json"
    import hashlib

    def _sha256_hex(path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    paths_trace = {
        "resolved_artifacts": [
            {
                "artifact_ref": "path:preflop/settings.json",
                "digest": {"alg": "sha256", "hex": _sha256_hex(repo / "specs" / "preflop" / "settings.json")},
                "computed_digest_or_null": {"alg": "sha256", "hex": _sha256_hex(repo / "specs" / "preflop" / "settings.json")},
                "resolved_ok": True,
                "abs_path_or_null": str(repo / "specs" / "preflop" / "settings.json"),
                "error_or_null": None,
            },
            {
                "artifact_ref": "path:preflop/preflop_ranges_v1.json",
                "digest": {"alg": "sha256", "hex": _sha256_hex(preflop_ranges)},
                "computed_digest_or_null": {"alg": "sha256", "hex": _sha256_hex(preflop_ranges)},
                "resolved_ok": True,
                "abs_path_or_null": str(preflop_ranges),
                "error_or_null": None,
            },
            {
                "artifact_ref": "path:preflop/preflop_freq_v1.json",
                "digest": {"alg": "sha256", "hex": _sha256_hex(preflop_freq)},
                "computed_digest_or_null": {"alg": "sha256", "hex": _sha256_hex(preflop_freq)},
                "resolved_ok": True,
                "abs_path_or_null": str(preflop_freq),
                "error_or_null": None,
            },
        ]
    }
    with pytest.raises(SystemPolicyError) as e:
        build_system_policy(
            seat_id=1,
            seed=1,
            policy_spec=pol,
            ruleset=ruleset,
            paths_trace=paths_trace,
            strict_mode=True,
        )
    assert e.value.code == "POSTFLOP_MISSING"
