from __future__ import annotations

import argparse
import json
from pathlib import Path

from poker2.tools.report_analyzer import ScrimmageReportAnalyzer


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True, help="scrimmage_report.json path")
    p.add_argument("--out", type=Path, default=None, help="optional output path for insights json")
    p.add_argument("--min-severity", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--include-tables", action=argparse.BooleanOptionalAction, default=False)
    args = p.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    analyzer = ScrimmageReportAnalyzer(report)
    payload = analyzer.to_structured(min_severity=args.min_severity, include_tables=args.include_tables)
    out_text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out is not None:
        args.out.write_text(out_text, encoding="utf-8")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
