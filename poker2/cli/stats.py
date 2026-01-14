from __future__ import annotations

# CLI: stats (ARCHIETECTURE.md 3.9/3.10/3.10.1).

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.cli.hrc_import_ruleset import ImportError, import_ruleset_from_hrc_settings
from poker2.contractkit import ROUNDING_MODE_VALUES, validate_digest_object
from poker2.evaluation.fixtures.pack import FixturesPackError, pack_digest, validate_pack
from poker2.evaluation.rule_conformance import RuleConformanceError, rule_conformance_report_from_eventstream
from poker2.protocol.metrics_spec import metric_spec_id
from poker2.protocol.report_schema import report_schema_id
from poker2.protocol.eventstream import read_ndjson
from poker2.protocol.ruleset import RuleSetError, validate_ruleset


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


@dataclass(frozen=True)
class StatsCLIError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _load_ruleset_from_path(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise StatsCLIError("RULESET_UNREADABLE", "ruleset JSON unreadable", {"error": str(e)}) from e
    if not isinstance(obj, dict):
        raise StatsCLIError("RULESET_NOT_OBJECT", "ruleset must be JSON object")
    return obj


def _load_ruleset_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.ruleset is not None:
        return _load_ruleset_from_path(args.ruleset)
    out = import_ruleset_from_hrc_settings(
        args.hrc_settings,
        rounding_mode=args.rounding_mode,
        reopen_on_short_allin=args.reopen_on_short_allin,
    )
    return out["ruleset"]


def _cmd_eventstream(args: argparse.Namespace) -> int:
    if not args.eventstream.exists():
        raise StatsCLIError("EVENTSTREAM_MISSING", "eventstream path missing", {"path": str(args.eventstream)})

    ruleset = _load_ruleset_from_args(args)
    validate_ruleset(ruleset, strict_mode=args.strict)

    rc_report = rule_conformance_report_from_eventstream(
        args.eventstream,
        event_stream_ref=f"path:{args.eventstream}",
        ruleset=ruleset,
        checked_items=None,
        strict_mode=args.strict,
    )

    header_obj = read_ndjson(args.eventstream, strict_mode=True)[0]
    if not isinstance(header_obj, dict):
        raise StatsCLIError("HEADER_NOT_OBJECT", "eventstream header must be object")

    header = rc_report.get("context", {})
    if not isinstance(header, dict):
        raise StatsCLIError("REPORT_INVALID", "rule_conformance.context invalid")

    status = "pass" if int(rc_report.get("failures_count", 0)) == 0 else "fail"

    rep = {
        "status": status,
        "metric_spec_id": metric_spec_id(strict_mode=True),
        "report_schema_id": report_schema_id(strict_mode=True),
        "run_manifest_ref": None,
        "run_manifest_digest": None,
        "provenance_ref": header.get("provenance_ref"),
        "options_hash": header.get("options_hash"),
        "scenario_id": header.get("scenario_id"),
        "schema_hash": header.get("schema_hash"),
        "event_stream_ref": header.get("event_stream_ref"),
        "event_stream_digest": header.get("event_stream_digest"),
        "repro_tier": header_obj.get("repro_tier"),
        "rule_conformance": rc_report,
    }

    es_digest = rep.get("event_stream_digest")
    if isinstance(es_digest, dict):
        validate_digest_object(es_digest, strict_mode=True)

    _print(rep)
    return 0 if status == "pass" else 2


def _cmd_fixtures_pack(args: argparse.Namespace) -> int:
    if not args.pack.exists():
        raise StatsCLIError("PACK_MISSING", "fixtures pack missing", {"path": str(args.pack)})

    ruleset = _load_ruleset_from_args(args)
    validate_ruleset(ruleset, strict_mode=args.strict)

    summary = validate_pack(args.pack, strict_mode=True, require_non_empty=True)
    pack_obj = json.loads(args.pack.read_text(encoding="utf-8"))
    fixtures = pack_obj.get("fixtures")
    if not isinstance(fixtures, list):
        raise StatsCLIError("PACK_INVALID", "fixtures must be array")

    checked_items = pack_obj.get("checked_items_covered")
    if checked_items is not None and not (isinstance(checked_items, list) and all(isinstance(x, str) for x in checked_items)):
        raise StatsCLIError("PACK_INVALID", "checked_items_covered must be array of strings or null")

    failures: list[dict[str, Any]] = []
    union_checked: set[str] = set()
    for idx, fx in enumerate(fixtures):
        if not isinstance(fx, dict):
            failures.append({"fixture_index": idx, "reason": "fixture_not_object"})
            continue
        ref = fx.get("event_stream_ref")
        if not (isinstance(ref, str) and ref.startswith("path:")):
            failures.append({"fixture_index": idx, "reason": "event_stream_ref_invalid"})
            continue
        path = Path(ref.removeprefix("path:"))
        try:
            rep = rule_conformance_report_from_eventstream(
                path,
                event_stream_ref=ref,
                ruleset=ruleset,
                checked_items=None,
                strict_mode=args.strict,
            )
        except RuleConformanceError as e:
            failures.append({"fixture_index": idx, "reason": "rule_conformance_error", "error": {"code": e.code, "message": e.message}})
            continue
        rep_checked = rep.get("checked_items")
        if isinstance(rep_checked, list) and all(isinstance(x, str) for x in rep_checked):
            union_checked.update(rep_checked)
        if int(rep.get("failures_count", 0)) != 0:
            failures.append({"fixture_index": idx, "reason": "rule_conformance_failed", "first_failure": (rep.get("failures") or [None])[0]})

    if checked_items is not None and not failures:
        missing = [x for x in checked_items if x not in union_checked]
        if missing:
            failures.append(
                {
                    "fixture_index": None,
                    "reason": "checked_items_covered_missing",
                    "missing": missing,
                    "checked_items_union": sorted(union_checked),
                }
            )

    status = "pass" if not failures else "fail"
    out = {
        "status": status,
        "pack_ref": f"path:{args.pack}",
        "pack_digest": pack_digest(args.pack),
        "metric_spec_id": metric_spec_id(strict_mode=True),
        "report_schema_id": report_schema_id(strict_mode=True),
        "fixtures_count": summary.get("fixtures_count"),
        "failures_count": len(failures),
        "failures": failures,
    }
    _print(out)
    return 0 if status == "pass" else 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_ruleset_source(sp: argparse.ArgumentParser) -> None:
        src = sp.add_mutually_exclusive_group(required=True)
        src.add_argument("--ruleset", type=Path, default=None)
        src.add_argument("--hrc-settings", type=Path, default=None)
        sp.add_argument("--rounding-mode", choices=ROUNDING_MODE_VALUES, default=None)
        sp.add_argument(
            "--reopen-on-short-allin",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="Required for --hrc-settings; no defaults allowed.",
        )

    p_es = sub.add_parser("eventstream")
    p_es.add_argument("--eventstream", type=Path, required=True)
    p_es.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    add_ruleset_source(p_es)

    p_pack = sub.add_parser("fixtures-pack")
    p_pack.add_argument("--pack", type=Path, required=True)
    p_pack.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    add_ruleset_source(p_pack)

    args = p.parse_args(argv)

    try:
        if args.cmd == "eventstream":
            return _cmd_eventstream(args)
        if args.cmd == "fixtures-pack":
            return _cmd_fixtures_pack(args)
        raise StatsCLIError("UNSUPPORTED_VALUE", f"unsupported cmd: {args.cmd!r}")  # pragma: no cover
    except (StatsCLIError, ImportError, RuleSetError, FixturesPackError, RuleConformanceError) as e:
        code = getattr(e, "code", "FAIL")
        msg = getattr(e, "message", str(e))
        details = getattr(e, "details", None)
        _print({"status": "fail", "check_id": "Tools.Stats", "error": {"code": code, "message": msg, "details": details}})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover
