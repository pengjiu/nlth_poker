from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import canonicalize_json_bytes, sha256_hex, validate_digest_object


ROOT = Path(__file__).resolve().parents[2]
VECTORS_PATH = ROOT / "contractkit" / "vectors" / "contractkit_vectors_v1.json"


def _as_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        return code
    return exc.__class__.__name__


def main() -> int:
    doc = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = doc["cases"]

    failures: list[dict[str, Any]] = []
    for case in cases:
        name = case["name"]
        op = case["op"]
        input_value = case.get("input")
        expect_error = case.get("expect_error")

        try:
            if op == "canonical_sha256":
                canonical = canonicalize_json_bytes(input_value, strict_mode=True).decode("utf-8")
                digest = sha256_hex(canonical.encode("utf-8"))
                expected = case["expected"]
                if canonical != expected["canonical_json"]:
                    raise AssertionError(
                        f"canonical mismatch: got={canonical!r} expected={expected['canonical_json']!r}"
                    )
                if digest != expected["sha256_hex"]:
                    raise AssertionError(
                        f"sha256 mismatch: got={digest!r} expected={expected['sha256_hex']!r}"
                    )
            elif op == "validate_digest_object":
                validate_digest_object(input_value, strict_mode=True)
            else:
                raise AssertionError(f"unknown op: {op!r}")

            if expect_error is not None:
                raise AssertionError(f"expected error {expect_error}, but succeeded")
        except Exception as exc:
            if expect_error is None:
                failures.append({"name": name, "op": op, "error": _as_error_code(exc), "message": str(exc)})
                continue
            expected_code = expect_error.get("code")
            got_code = _as_error_code(exc)
            if expected_code != got_code:
                failures.append(
                    {
                        "name": name,
                        "op": op,
                        "expected_error": expected_code,
                        "got_error": got_code,
                        "message": str(exc),
                    }
                )

    if failures:
        print(json.dumps({"status": "fail", "failures": failures}, ensure_ascii=False, sort_keys=True))
        return 2

    print(json.dumps({"status": "pass", "cases": len(cases)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover
