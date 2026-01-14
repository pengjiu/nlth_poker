from __future__ import annotations

import argparse
import json
from pathlib import Path

from poker2.tools.iteration_protocol import validate_iteration_protocol


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True, help="scrimmage_report.json path")
    args = p.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    protocol = report.get("iteration_protocol")
    errors = validate_iteration_protocol(protocol, strict=False)
    if errors:
        print(json.dumps({"status": "fail", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"status": "pass"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
