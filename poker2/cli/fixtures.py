from __future__ import annotations

# CLI: build/register Golden Fixtures packs (ARCHIETECTURE.md 5.1.2).

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import validate_digest_object
from poker2.evaluation.fixtures.pack import FixturesPackError, pack_digest, validate_pack
from poker2.protocol.eventstream import EventStreamError, event_stream_digest_from_file, read_ndjson


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


@dataclass
class FixturesToolError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _find_handstart(objs: list[Any]) -> dict[str, Any] | None:
    for obj in objs[1:]:
        if isinstance(obj, dict) and obj.get("event") == "HandStart":
            return obj
    return None


def _cmd_build_pack(
    *,
    out_path: Path,
    eventstreams: list[Path],
    platform: str,
    ruleset_label: str | None,
    checked_items_covered: list[str],
    strict: bool,
    ruleset_id_override: str | None,
    options_hash_override: str | None,
    provenance_ref_override: str | None,
) -> dict[str, Any]:
    fixtures: list[dict[str, Any]] = []
    pack_ruleset_id: str | None = ruleset_id_override

    for p in eventstreams:
        if not p.exists():
            raise FixturesToolError("EVENTSTREAM_MISSING", "eventstream path missing", {"path": str(p)})

        objs = read_ndjson(p, strict_mode=True)
        if not objs:
            raise FixturesToolError("EMPTY_EVENTSTREAM", "eventstream is empty", {"path": str(p)})
        if not isinstance(objs[0], dict):
            raise FixturesToolError("HEADER_NOT_OBJECT", "eventstream header must be object", {"path": str(p)})

        header: dict[str, Any] = objs[0]
        computed_hex = event_stream_digest_from_file(p, strict_mode=True)

        options_hash = options_hash_override if options_hash_override is not None else header.get("options_hash")
        provenance_ref = provenance_ref_override if provenance_ref_override is not None else header.get("provenance_ref")

        hand_start = _find_handstart(objs)
        ruleset_id = ruleset_id_override
        if ruleset_id is None and hand_start is not None:
            ruleset_id = hand_start.get("ruleset_id")

        if not isinstance(options_hash, str):
            raise FixturesToolError("MISSING_FIELDS", "options_hash missing in header and no override provided", {"path": str(p)})
        if not isinstance(provenance_ref, str):
            raise FixturesToolError(
                "MISSING_FIELDS",
                "provenance_ref missing in header and no override provided",
                {"path": str(p)},
            )
        if not isinstance(ruleset_id, str):
            raise FixturesToolError(
                "MISSING_FIELDS",
                "ruleset_id missing in HandStart and no override provided",
                {"path": str(p)},
            )

        # Validate IDs as sha256 lowercase hex.
        validate_digest_object({"alg": "sha256", "hex": ruleset_id}, strict_mode=True)
        validate_digest_object({"alg": "sha256", "hex": options_hash}, strict_mode=True)

        if pack_ruleset_id is None:
            pack_ruleset_id = ruleset_id
        elif pack_ruleset_id != ruleset_id:
            raise FixturesToolError(
                "RULESET_ID_MISMATCH",
                "eventstream ruleset_id does not match pack ruleset_id",
                {"pack_ruleset_id": pack_ruleset_id, "eventstream_ruleset_id": ruleset_id, "path": str(p)},
            )

        digest_obj = {"alg": "sha256", "hex": computed_hex}
        validate_digest_object(digest_obj, strict_mode=True)

        fixtures.append(
            {
                "event_stream_ref": f"path:{p}",
                "event_stream_digest": digest_obj,
                "ruleset_id": ruleset_id,
                "options_hash": options_hash,
                "provenance_ref": provenance_ref,
            }
        )

    pack_obj: dict[str, Any] = {
        "fixtures_pack_schema_id": "golden_fixtures_pack_v1",
        "platform": platform,
        "ruleset_id": pack_ruleset_id,
        "ruleset_label": ruleset_label,
        "checked_items_covered": checked_items_covered,
        "fixtures": fixtures,
    }
    _write_json(out_path, pack_obj)

    summary = validate_pack(
        out_path,
        strict_mode=True,
        require_non_empty=True,
        expected_ruleset_id=pack_ruleset_id,
        required_checked_items=checked_items_covered if checked_items_covered else None,
    )

    if strict:
        return {"status": "pass", **summary}
    return {"status": "pass", "degraded": False, **summary}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build-pack")
    p_build.add_argument("--out", type=Path, required=True)
    p_build.add_argument("--platform", required=True)
    p_build.add_argument("--ruleset-label", default=None)
    p_build.add_argument("--checked-item", action="append", default=[])
    p_build.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    p_build.add_argument("--eventstream", type=Path, action="append", required=True)
    p_build.add_argument("--ruleset-id", default=None)
    p_build.add_argument("--options-hash", default=None)
    p_build.add_argument("--provenance-ref", default=None)

    args = p.parse_args(argv)

    try:
        if args.cmd == "build-pack":
            out = _cmd_build_pack(
                out_path=args.out,
                eventstreams=args.eventstream,
                platform=args.platform,
                ruleset_label=args.ruleset_label,
                checked_items_covered=list(args.checked_item),
                strict=args.strict,
                ruleset_id_override=args.ruleset_id,
                options_hash_override=args.options_hash,
                provenance_ref_override=args.provenance_ref,
            )
            _print(out)
            return 0
        raise FixturesToolError("UNSUPPORTED_VALUE", f"unsupported cmd: {args.cmd!r}")
    except (FixturesToolError, FixturesPackError, EventStreamError) as e:
        code = getattr(e, "code", "FAIL")
        msg = getattr(e, "message", str(e))
        details = getattr(e, "details", None)
        _print({"status": "fail", "check_id": "Tools.Fixtures", "error": {"code": code, "message": msg, "details": details}})
        return 2

    raise SystemExit(2)  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover
