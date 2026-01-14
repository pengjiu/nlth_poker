from __future__ import annotations

# CLI helper: import RuleSet from HRC settings.json (ARCHIETECTURE.md §11).

import argparse
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict

from poker2.contractkit import ROUNDING_MODE_VALUES
from poker2.protocol.ruleset import ruleset_id as compute_ruleset_id
from poker2.protocol.ruleset import ruleset_rake_id as compute_ruleset_rake_id
from poker2.protocol.paths import PathsError, validate_paths_config


class ImportErrorJSON(TypedDict):
    code: str
    message: str


@dataclass(frozen=True)
class ImportError(Exception):
    code: str
    message: str

    def to_json(self) -> ImportErrorJSON:
        return {"code": self.code, "message": self.message}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


def _sha256_file_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _require(obj: dict[str, Any], key: str) -> Any:
    if key not in obj:
        raise ImportError("MISSING_FIELD", f"missing field: {key}")
    return obj[key]


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ImportError("TYPE_ERROR", f"{field} must be int, got bool")
    if not isinstance(value, int):
        raise ImportError("TYPE_ERROR", f"{field} must be int, got {type(value).__name__}")
    return value


def _as_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ImportError("TYPE_ERROR", f"{field} must be bool, got {type(value).__name__}")
    return value


def _decimal_to_pct_ppm(value: Any, *, field: str) -> int:
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, int):
        dec = Decimal(value)
    else:
        raise ImportError("TYPE_ERROR", f"{field} must be decimal or int, got {type(value).__name__}")

    ppm = dec * Decimal(1_000_000)
    if ppm != ppm.to_integral_value():
        raise ImportError("NON_INTEGER_PPM", f"{field} cannot be represented exactly as pct_ppm int")
    ppm_int = int(ppm)
    if ppm_int < 0:
        raise ImportError("VALUE_ERROR", f"{field} must be >= 0")
    return ppm_int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_settings_path(settings_path: Path, paths_config: dict[str, Any] | None) -> Path:
    if settings_path.exists():
        return settings_path.resolve()

    if paths_config is not None:
        try:
            validate_paths_config(paths_config, strict_mode=True)
        except PathsError as e:
            raise ImportError(e.code, e.message)

        roots = paths_config.get("roots", {})
        hrc_root_val = roots.get("hrc_root")
        if isinstance(hrc_root_val, str):
            if hrc_root_val.startswith("path:"):
                rel = hrc_root_val.removeprefix("path:")
                base = (_repo_root() / rel).resolve()
            else:
                base = Path(hrc_root_val).expanduser().resolve()
            candidate = base / settings_path
            if candidate.exists():
                return candidate

    raise ImportError("SETTINGS_NOT_FOUND", f"settings.json not found at {settings_path}")


def import_ruleset_from_hrc_settings(
    settings_path: Path,
    *,
    rounding_mode: str | None,
    reopen_on_short_allin: bool | None,
    paths_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_settings = _resolve_settings_path(settings_path, paths_config)
    doc = _read_json(resolved_settings)
    if not isinstance(doc, dict):
        raise ImportError("TYPE_ERROR", "settings.json must be a JSON object")

    handdata = _require(doc, "handdata")
    if not isinstance(handdata, dict):
        raise ImportError("TYPE_ERROR", "handdata must be a JSON object")

    blinds_raw = _require(handdata, "blinds")
    if not (isinstance(blinds_raw, list) and len(blinds_raw) == 3):
        raise ImportError("TYPE_ERROR", "handdata.blinds must be [bb, sb, ante] array of length 3")

    bb_chips = _as_int(blinds_raw[0], field="handdata.blinds[0] (bb)")
    sb_chips = _as_int(blinds_raw[1], field="handdata.blinds[1] (sb)")
    ante_chips = _as_int(blinds_raw[2], field="handdata.blinds[2] (ante)")

    ante_type = _require(handdata, "anteType")
    if ante_type not in ("OFF", "REGULAR"):
        raise ImportError("UNSUPPORTED_VALUE", f"unsupported anteType: {ante_type!r}")
    ante: Any
    if ante_type == "OFF" or ante_chips == 0:
        ante = None
    else:
        ante = {"kind": "uniform", "ante_chips": ante_chips}

    straddle_type = _require(handdata, "straddleType")
    if straddle_type != "OFF":
        raise ImportError("UNSUPPORTED_VALUE", f"unsupported straddleType: {straddle_type!r}")
    straddle = None

    eqmodel = _require(doc, "eqmodel")
    if not isinstance(eqmodel, dict):
        raise ImportError("TYPE_ERROR", "eqmodel must be a JSON object")

    raked = _as_bool(_require(eqmodel, "raked"), field="eqmodel.raked")
    rake: Any
    if not raked:
        rake = None
    else:
        if rounding_mode is None:
            raise ImportError(
                "MISSING_ROUNDING_MODE",
                "rake enabled (eqmodel.raked=true) but RuleSet.rake.rounding_mode not provided",
            )
        nfnd = _as_bool(_require(eqmodel, "nfnd"), field="eqmodel.nfnd")
        rakepct = _require(eqmodel, "rakepct")
        rakecap = _require(eqmodel, "rakecap")
        pct_ppm = _decimal_to_pct_ppm(rakepct, field="eqmodel.rakepct")
        cap_chips = _as_int(rakecap, field="eqmodel.rakecap")
        rake = {
            "pct_ppm": pct_ppm,
            "cap_chips": None if cap_chips == 0 else cap_chips,
            "rounding_mode": rounding_mode,
            "no_flop_no_drop": nfnd,
        }

    if reopen_on_short_allin is None:
        raise ImportError(
            "MISSING_REOPEN_FLAG",
            "RuleSet.min_raise_rule.reopen_on_short_allin must be explicitly set (no defaults)",
        )

    ruleset = {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": sb_chips, "bb_chips": bb_chips},
        "ante": ante,
        "straddle": straddle,
        "rake": rake,
        "min_raise_rule": {
            "basis": "last_raise_increment",
            "reopen_on_short_allin": bool(reopen_on_short_allin),
        },
    }

    ruleset_id = compute_ruleset_id(ruleset, strict_mode=True)
    ruleset_rake_id = compute_ruleset_rake_id(ruleset, strict_mode=True)

    return {
        "ruleset": ruleset,
        "ruleset_id": ruleset_id,
        "ruleset_hash": ruleset_id,
        "ruleset_rake_id": ruleset_rake_id,
        "source_ref": str(resolved_settings),
        "source_digest": {"alg": "sha256", "hex": _sha256_file_hex(resolved_settings)},
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--settings", type=Path, required=True)
    p.add_argument("--rounding-mode", choices=ROUNDING_MODE_VALUES, default=None)
    p.add_argument(
        "--reopen-on-short-allin",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Required; no defaults allowed (use --reopen-on-short-allin or --no-reopen-on-short-allin).",
    )
    args = p.parse_args(argv)

    try:
        out = import_ruleset_from_hrc_settings(
            args.settings,
            rounding_mode=args.rounding_mode,
            reopen_on_short_allin=args.reopen_on_short_allin,
        )
    except ImportError as e:
        print(json.dumps({"status": "fail", "error": e.to_json()}, ensure_ascii=False, sort_keys=True))
        return 2
    except Exception as e:  # pragma: no cover
        print(
            json.dumps(
                {"status": "fail", "error": {"code": "UNEXPECTED", "message": str(e)}},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps({"status": "pass", **out}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover
