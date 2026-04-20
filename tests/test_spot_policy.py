from __future__ import annotations

import pytest

from poker2.protocol.spot_policy import spot_policy_digest, validate_spot_policy
from poker2.runtime.spot_policy import apply_spot_policy_overlay, build_spot_context


def _spot_policy_spec() -> dict:
    return {
        "schema_id": "spot_policy_v1",
        "spots": [
            {
                "spot_id": "oop_mw_turnriver",
                "enabled": True,
                "when": {
                    "streets": ["TURN", "RIVER"],
                    "requires_facing_bet": True,
                    "pos_keys": ["SB", "BB"],
                    "players_alive_min": 3,
                    "players_alive_max": None,
                    "price_min_ppm": 220000,
                    "price_max_ppm": None,
                    "spr_min_milli": None,
                    "spr_max_milli": 3500,
                    "wet_min": 1,
                    "wet_max": None,
                },
                "adjustments": {
                    "defend_target_scale_bp": 8800,
                    "defend_target_floor_bp": None,
                    "defend_target_max_bp": 5200,
                    "call_pref_floor_bp": 8400,
                    "raise_cap_max_bp": 700,
                    "trace_tag": "turnriver_high_price_call_first_v1",
                },
            }
        ],
    }


def test_spot_policy_digest_is_sha256_object() -> None:
    digest = spot_policy_digest(_spot_policy_spec(), strict_mode=True)
    assert digest["alg"] == "sha256"
    assert len(digest["hex"]) == 64


def test_spot_policy_overlay_matches_and_clamps() -> None:
    spec = _spot_policy_spec()
    validate_spot_policy(spec, strict_mode=True)
    context = build_spot_context(
        street="TURN",
        facing_bet=True,
        pos_key="BB",
        players_alive=4,
        pot_chips=1000,
        to_call_chips=320,
        actor_stack_chips=2800,
        wet_score=2,
    )
    overlay = apply_spot_policy_overlay(
        spec=spec,
        context=context,
        defend_target=0.60,
        call_pref=0.55,
        raise_cap_max=0.16,
    )
    assert overlay.matched_rule == {
        "spot_id": "oop_mw_turnriver",
        "trace_tag": "turnriver_high_price_call_first_v1",
    }
    assert overlay.defend_target == pytest.approx(0.52)
    assert overlay.call_pref == pytest.approx(0.84)
    assert overlay.raise_cap_max == pytest.approx(0.07)


def test_spot_policy_overlay_skips_non_matching_context() -> None:
    spec = _spot_policy_spec()
    context = build_spot_context(
        street="FLOP",
        facing_bet=True,
        pos_key="CO",
        players_alive=2,
        pot_chips=1000,
        to_call_chips=120,
        actor_stack_chips=6000,
        wet_score=0,
    )
    overlay = apply_spot_policy_overlay(
        spec=spec,
        context=context,
        defend_target=0.48,
        call_pref=0.52,
        raise_cap_max=0.15,
    )
    assert overlay.matched_rule is None
    assert overlay.defend_target == pytest.approx(0.48)
    assert overlay.call_pref == pytest.approx(0.52)
    assert overlay.raise_cap_max == pytest.approx(0.15)
