from __future__ import annotations

import json

import pytest

from poker2.contractkit import ROUNDING_MODE_VALUES, canonicalize_json_bytes, validate_digest_object
from poker2.contractkit.run_vectors import main as run_vectors_main


def test_contractkit_vectors_runner_passes(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run_vectors_main()
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "pass"


def test_rounding_mode_enum_single_source() -> None:
    assert ROUNDING_MODE_VALUES == ("floor", "ceil", "nearest_ties_up")


def test_canonicalize_seatmap_rejects_leading_zero() -> None:
    with pytest.raises(Exception) as exc:
        canonicalize_json_bytes({"by_seat_amount_chips": {"01": 1}}, strict_mode=True)
    assert getattr(exc.value, "code", None) == "SEAT_KEY_LEADING_ZERO"


def test_canonicalize_seatmap_allows_zero_key() -> None:
    b = canonicalize_json_bytes({"by_seat_amount_chips": {"1": 7, "0": 9}}, strict_mode=True)
    assert b.decode("utf-8") == "{\"by_seat_amount_chips\":{\"0\":9,\"1\":7}}"


def test_canonicalize_seatmap_rejects_non_decimal_key() -> None:
    with pytest.raises(Exception) as exc:
        canonicalize_json_bytes({"by_seat_amount_chips": {"x": 1}}, strict_mode=True)
    assert getattr(exc.value, "code", None) == "SEAT_KEY_NOT_DECIMAL"


def test_canonicalize_escapes_all_control_chars() -> None:
    s = "quote:\" backslash:\\ b:\b f:\f r:\r t:\t ctrl:\x1f"
    b = canonicalize_json_bytes({"s": s}, strict_mode=True)
    assert (
        b.decode("utf-8")
        == "{\"s\":\"quote:\\\" backslash:\\\\ b:\\b f:\\f r:\\r t:\\t ctrl:\\u001f\"}"
    )


def test_canonicalize_seatmap_rejects_empty_object_in_strict() -> None:
    with pytest.raises(Exception) as exc:
        canonicalize_json_bytes({"by_seat_amount_chips": {}}, strict_mode=True)
    assert getattr(exc.value, "code", None) == "SEATMAP_EMPTY"


def test_canonicalize_rejects_non_string_object_keys() -> None:
    with pytest.raises(Exception) as exc:
        canonicalize_json_bytes({1: "x"}, strict_mode=True)
    assert getattr(exc.value, "code", None) == "OBJECT_KEY_NOT_STRING"


def test_canonicalize_rejects_unsupported_types() -> None:
    with pytest.raises(Exception) as exc:
        canonicalize_json_bytes({"b": b"bytes"}, strict_mode=True)
    assert getattr(exc.value, "code", None) == "UNSUPPORTED_TYPE"


def test_validate_digest_object_rejects_extra_fields() -> None:
    with pytest.raises(Exception) as exc:
        validate_digest_object(
            {
                "alg": "sha256",
                "hex": "0" * 64,
                "extra": 1,
            },
            strict_mode=True,
        )
    assert getattr(exc.value, "code", None) == "DIGEST_EXTRA_FIELDS"


def test_validate_digest_object_rejects_non_object() -> None:
    with pytest.raises(Exception) as exc:
        validate_digest_object(["not", "an", "object"], strict_mode=True)
    assert getattr(exc.value, "code", None) == "DIGEST_NOT_OBJECT"


def test_validate_digest_object_rejects_hex_not_string() -> None:
    with pytest.raises(Exception) as exc:
        validate_digest_object({"alg": "sha256", "hex": 123}, strict_mode=True)
    assert getattr(exc.value, "code", None) == "DIGEST_HEX_NOT_STRING"


def test_validate_digest_object_rejects_non_hex_string() -> None:
    with pytest.raises(Exception) as exc:
        validate_digest_object({"alg": "sha256", "hex": "g" * 64}, strict_mode=True)
    assert getattr(exc.value, "code", None) == "DIGEST_HEX_NOT_HEX"
