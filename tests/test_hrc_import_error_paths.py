from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from poker2.cli import hrc_import_ruleset


def test_hrc_import_require_missing_field_raises() -> None:
    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset._require({}, "handdata")
    assert exc.value.code == "MISSING_FIELD"


def test_hrc_import_as_int_rejects_bool_and_non_int() -> None:
    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset._as_int(True, field="x")
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset._as_int("1", field="x")
    assert exc.value.code == "TYPE_ERROR"


def test_hrc_import_as_bool_rejects_non_bool() -> None:
    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset._as_bool("nope", field="x")
    assert exc.value.code == "TYPE_ERROR"


def test_hrc_import_decimal_to_pct_ppm_errors() -> None:
    assert hrc_import_ruleset._decimal_to_pct_ppm(0, field="x") == 0

    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset._decimal_to_pct_ppm("0.05", field="x")
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset._decimal_to_pct_ppm(Decimal("0.0000015"), field="x")
    assert exc.value.code == "NON_INTEGER_PPM"

    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset._decimal_to_pct_ppm(Decimal("-0.1"), field="x")
    assert exc.value.code == "VALUE_ERROR"


def test_hrc_import_rejects_non_object_settings(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset.import_ruleset_from_hrc_settings(
            p,
            rounding_mode=None,
            reopen_on_short_allin=True,
        )
    assert exc.value.code == "TYPE_ERROR"


def test_hrc_import_rejects_handdata_not_object(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"handdata": [], "eqmodel": {}}), encoding="utf-8")
    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset.import_ruleset_from_hrc_settings(
            p,
            rounding_mode=None,
            reopen_on_short_allin=True,
        )
    assert exc.value.code == "TYPE_ERROR"


def test_hrc_import_rejects_blinds_wrong_shape(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"handdata": {"blinds": [2, 1]}, "eqmodel": {}}), encoding="utf-8")
    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset.import_ruleset_from_hrc_settings(
            p,
            rounding_mode=None,
            reopen_on_short_allin=True,
        )
    assert exc.value.code == "TYPE_ERROR"


def test_hrc_import_rejects_unsupported_ante_and_straddle_types(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(
        json.dumps(
            {
                "handdata": {"blinds": [2, 1, 0], "anteType": "WEIRD", "straddleType": "OFF"},
                "eqmodel": {"raked": False, "nfnd": False, "rakepct": 0.0, "rakecap": 0},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset.import_ruleset_from_hrc_settings(
            p,
            rounding_mode=None,
            reopen_on_short_allin=True,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"

    p.write_text(
        json.dumps(
            {
                "handdata": {"blinds": [2, 1, 0], "anteType": "OFF", "straddleType": "UTG"},
                "eqmodel": {"raked": False, "nfnd": False, "rakepct": 0.0, "rakecap": 0},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset.import_ruleset_from_hrc_settings(
            p,
            rounding_mode=None,
            reopen_on_short_allin=True,
        )
    assert exc.value.code == "UNSUPPORTED_VALUE"


def test_hrc_import_rejects_eqmodel_not_object(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"handdata": {"blinds": [2, 1, 0], "anteType": "OFF", "straddleType": "OFF"}, "eqmodel": []}), encoding="utf-8")
    with pytest.raises(hrc_import_ruleset.ImportError) as exc:
        hrc_import_ruleset.import_ruleset_from_hrc_settings(
            p,
            rounding_mode=None,
            reopen_on_short_allin=True,
        )
    assert exc.value.code == "TYPE_ERROR"


def test_hrc_import_outputs_uniform_ante_when_regular(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(
        json.dumps(
            {
                "handdata": {"blinds": [2, 1, 1], "anteType": "REGULAR", "straddleType": "OFF"},
                "eqmodel": {"raked": False, "nfnd": False, "rakepct": 0.0, "rakecap": 0},
            }
        ),
        encoding="utf-8",
    )
    out = hrc_import_ruleset.import_ruleset_from_hrc_settings(
        p,
        rounding_mode=None,
        reopen_on_short_allin=False,
    )
    assert out["ruleset"]["ante"] == {"kind": "uniform", "ante_chips": 1}
