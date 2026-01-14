from __future__ import annotations

import pytest

from poker2.protocol.ruleset import RuleSetError, validate_ruleset


def _base_ruleset() -> dict:
    return {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": None,
        "straddle": None,
        "rake": None,
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": True},
    }


@pytest.mark.parametrize(
    "ruleset,code",
    [
        ([], "TYPE_ERROR"),
        ({}, "MISSING_FIELD"),
        ({**_base_ruleset(), "game_kind": "PLO"}, "UNSUPPORTED_VALUE"),
        ({**_base_ruleset(), "blinds": "x"}, "TYPE_ERROR"),
        ({**_base_ruleset(), "blinds": {"sb_chips": True, "bb_chips": 2}}, "TYPE_ERROR"),
        ({**_base_ruleset(), "blinds": {"sb_chips": "1", "bb_chips": 2}}, "TYPE_ERROR"),
        ({**_base_ruleset(), "blinds": {"sb_chips": 2, "bb_chips": 2}}, "VALUE_ERROR"),
        ({**_base_ruleset(), "ante": []}, "TYPE_ERROR"),
        ({**_base_ruleset(), "ante": {"kind": "uniform", "ante_chips": 0}}, "VALUE_ERROR"),
        ({**_base_ruleset(), "ante": {"kind": "by_seat", "by_seat_ante_chips": []}}, "TYPE_ERROR"),
        ({**_base_ruleset(), "ante": {"kind": "by_seat", "by_seat_ante_chips": {}}}, "VALUE_ERROR"),
        ({**_base_ruleset(), "ante": {"kind": "weird"}}, "UNSUPPORTED_VALUE"),
        ({**_base_ruleset(), "straddle": []}, "TYPE_ERROR"),
        ({**_base_ruleset(), "straddle": {"kind": "utg", "amount_chips": 0}}, "VALUE_ERROR"),
        ({**_base_ruleset(), "straddle": {"kind": "nope", "amount_chips": 2}}, "UNSUPPORTED_VALUE"),
        ({**_base_ruleset(), "rake": []}, "TYPE_ERROR"),
        (
            {
                **_base_ruleset(),
                "rake": {
                    "pct_ppm": 0,
                    "cap_chips": True,
                    "rounding_mode": "floor",
                    "no_flop_no_drop": False,
                },
            },
            "TYPE_ERROR",
        ),
        (
            {
                **_base_ruleset(),
                "rake": {
                    "pct_ppm": 0,
                    "cap_chips": None,
                    "rounding_mode": "nope",
                    "no_flop_no_drop": False,
                },
            },
            "UNSUPPORTED_VALUE",
        ),
        (
            {
                **_base_ruleset(),
                "rake": {
                    "pct_ppm": 1_000_001,
                    "cap_chips": None,
                    "rounding_mode": "floor",
                    "no_flop_no_drop": False,
                },
            },
            "VALUE_ERROR",
        ),
        (
            {
                **_base_ruleset(),
                "rake": {
                    "pct_ppm": 0,
                    "cap_chips": -1,
                    "rounding_mode": "floor",
                    "no_flop_no_drop": False,
                },
            },
            "VALUE_ERROR",
        ),
        ({**_base_ruleset(), "min_raise_rule": []}, "TYPE_ERROR"),
        (
            {
                **_base_ruleset(),
                "min_raise_rule": {"basis": "to_call", "reopen_on_short_allin": True},
            },
            "UNSUPPORTED_VALUE",
        ),
        (
            {
                **_base_ruleset(),
                "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": "no"},
            },
            "TYPE_ERROR",
        ),
    ],
)
def test_validate_ruleset_errors(ruleset: object, code: str) -> None:
    with pytest.raises(RuleSetError) as exc:
        validate_ruleset(ruleset, strict_mode=True)
    assert exc.value.code == code
