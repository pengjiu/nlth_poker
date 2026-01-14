from __future__ import annotations

import argparse
import json
from pathlib import Path

from poker2.tools.scrimmage_views import ScrimmageReportViews


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True, help="scrimmage_report.json path")
    p.add_argument("--out", type=Path, default=None, help="optional output path")
    p.add_argument("--text", action=argparse.BooleanOptionalAction, default=False, help="emit table text instead of json")
    args = p.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    builder = ScrimmageReportViews(report)
    if args.text:
        payload = builder.render_text()
    else:
        payload = json.dumps(builder.build(), ensure_ascii=False, indent=2)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
