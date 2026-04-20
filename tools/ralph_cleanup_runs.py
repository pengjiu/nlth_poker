#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


CYCLE_DIR_RE = re.compile(r"^cycle_(\d+)_(\d{8}_\d{6})$")
CYCLE_LOCK_RE = re.compile(r"^cycle_(\d+)\.lock$")
EPHEMERAL_TOPLEVEL_DIRS = ("trial_quick", "bootstrap_active_full")
EPHEMERAL_FILE_GLOBS = (
    "**/scrimmage_eventstream.ndjson",
    "**/scrimmage_views.json",
    "**/scrimmage_views.txt",
    "**/scrimmage_insights.json",
    "**/scrimmage_report.txt",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _free_gb(root: Path) -> float:
    usage = shutil.disk_usage(root)
    return float(usage.free) / float(1024**3)


def _cycle_dir_from_path(raw: str, runs_root: Path) -> Path | None:
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("path:"):
        s = s.removeprefix("path:")
    p = Path(s)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    for parent in (p, *p.parents):
        if parent.parent == runs_root and CYCLE_DIR_RE.match(parent.name):
            return parent
    return None


def _collect_cycle_dirs(runs_root: Path) -> list[Path]:
    out: list[Path] = []
    if not runs_root.exists():
        return out
    for row in runs_root.iterdir():
        if row.is_dir() and CYCLE_DIR_RE.match(row.name):
            out.append(row)
    out.sort(key=_cycle_sort_key, reverse=True)
    return out


def _cycle_num(path: Path) -> int:
    m = CYCLE_DIR_RE.match(path.name)
    if not m:
        return -1
    try:
        return int(m.group(1))
    except Exception:
        return -1


def _cycle_sort_key(path: Path) -> tuple[int, str]:
    m = CYCLE_DIR_RE.match(path.name)
    if not m:
        return (-1, "")
    try:
        return (int(m.group(1)), str(m.group(2)))
    except Exception:
        return (-1, "")


def _group_by_cycle_num(rows: list[Path]) -> dict[int, list[Path]]:
    out: dict[int, list[Path]] = {}
    for row in rows:
        num = _cycle_num(row)
        out.setdefault(num, []).append(row)
    for items in out.values():
        items.sort(key=_cycle_sort_key, reverse=True)
    return out


def _walk_strings(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_walk_strings(v))
        return out
    if isinstance(obj, list):
        for v in obj:
            out.extend(_walk_strings(v))
        return out
    return out


def _preserve_from_state(
    state: dict[str, Any],
    runs_root: Path,
    *,
    max_cycle_num: int,
    preserve_recent_cycles: int,
) -> set[Path]:
    preserve: set[Path] = set()
    min_keep_num: int | None = None
    if max_cycle_num >= 0 and preserve_recent_cycles > 0:
        min_keep_num = max(0, max_cycle_num - int(preserve_recent_cycles) + 1)
    for raw in _walk_strings(state):
        if "cycle_" not in raw:
            continue
        row = _cycle_dir_from_path(raw, runs_root)
        if not isinstance(row, Path):
            continue
        if min_keep_num is not None:
            num = _cycle_num(row)
            if num >= 0 and num < min_keep_num:
                continue
        preserve.add(row)
    return preserve


def _locked_cycle_nums(runs_root: Path) -> set[int]:
    out: set[int] = set()
    if not runs_root.exists():
        return out
    for row in runs_root.glob("cycle_*.lock"):
        m = CYCLE_LOCK_RE.match(row.name)
        if not m:
            continue
        try:
            out.add(int(m.group(1)))
        except Exception:
            continue
    return out


def _remove_dir(path: Path) -> bool:
    try:
        shutil.rmtree(path)
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


def _remove_file(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


def _cleanup_parent_logs(runs_root: Path, *, keep_parent_logs: int) -> int:
    removed = 0
    logs = sorted(
        [p for p in runs_root.glob("cycle_*.parent.log") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for row in logs[max(0, int(keep_parent_logs)) :]:
        if _remove_file(row):
            removed += 1
    return removed


def _cleanup_quick_cache(cache_dir: Path, *, keep_quick_cache: int) -> int:
    if not cache_dir.exists():
        return 0
    removed = 0
    rows = sorted(
        [p for p in cache_dir.glob("*.json") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for row in rows[max(0, int(keep_quick_cache)) :]:
        if _remove_file(row):
            removed += 1
    return removed


def _compact_cycle_dir(cycle_dir: Path) -> tuple[int, int]:
    removed_dirs = 0
    removed_files = 0

    for name in EPHEMERAL_TOPLEVEL_DIRS:
        target = cycle_dir / name
        if target.exists() and _remove_dir(target):
            removed_dirs += 1

    trial_full = cycle_dir / "trial_full"
    if trial_full.exists():
        seed_dirs = [p for p in trial_full.rglob("seed*") if p.is_dir()]
        seed_dirs.sort(key=lambda p: len(p.parts), reverse=True)
        for seed_dir in seed_dirs:
            if _remove_dir(seed_dir):
                removed_dirs += 1

    for pattern in EPHEMERAL_FILE_GLOBS:
        for row in cycle_dir.glob(pattern):
            if row.is_file() and _remove_file(row):
                removed_files += 1

    return removed_dirs, removed_files


def run_cleanup(
    *,
    runs_root: Path,
    state_file: Path,
    keep_latest_global: int,
    keep_per_cycle: int,
    keep_recent_cycles: int,
    preserve_state_recent_cycles: int,
    max_remove: int,
    min_free_gb: float,
    target_free_gb: float,
    keep_parent_logs: int,
    compact_enable: bool,
    compact_keep_latest: int,
    compact_max_dirs: int,
    quick_cache_dir: Path,
    keep_quick_cache: int,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "runs_root": str(runs_root),
        "state_file": str(state_file),
        "free_gb_before": round(_free_gb(Path.cwd()), 3),
        "free_gb_after": None,
        "removed_cycle_dirs": 0,
        "removed_parent_logs": 0,
        "removed_quick_cache_files": 0,
        "compacted_cycle_dirs": 0,
        "compacted_removed_dirs": 0,
        "compacted_removed_files": 0,
        "kept_cycle_dirs": 0,
        "hard_preserve_cycle_dirs": 0,
        "locked_cycle_nums": [],
        "total_cycle_dirs_before": 0,
        "total_cycle_dirs_after": 0,
        "mode": "retention",
        "target_reached": False,
    }

    cycle_dirs = _collect_cycle_dirs(runs_root)
    summary["total_cycle_dirs_before"] = len(cycle_dirs)
    if not cycle_dirs:
        summary["removed_quick_cache_files"] = _cleanup_quick_cache(quick_cache_dir, keep_quick_cache=keep_quick_cache)
        summary["free_gb_after"] = round(_free_gb(Path.cwd()), 3)
        summary["target_reached"] = bool(summary["free_gb_after"] >= min_free_gb)
        return summary

    grouped = _group_by_cycle_num(cycle_dirs)
    valid_nums = [num for num in grouped.keys() if num >= 0]
    max_cycle_num = max(valid_nums) if valid_nums else -1

    state_obj = _load_json(state_file)
    hard_preserve = _preserve_from_state(
        state_obj,
        runs_root,
        max_cycle_num=max_cycle_num,
        preserve_recent_cycles=max(0, int(preserve_state_recent_cycles)),
    )
    locked_nums = _locked_cycle_nums(runs_root)
    locked_dirs = {row for row in cycle_dirs if _cycle_num(row) in locked_nums}
    hard_preserve.update(locked_dirs)
    summary["hard_preserve_cycle_dirs"] = len(hard_preserve)
    summary["locked_cycle_nums"] = sorted(locked_nums)

    keep_set: set[Path] = set(cycle_dirs[: max(0, int(keep_latest_global))])

    if keep_recent_cycles > 0 and valid_nums:
        min_recent_num = max(0, max(valid_nums) - int(keep_recent_cycles) + 1)
        recent_keep_count = max(1, int(keep_per_cycle))
        for num, rows in grouped.items():
            if num >= min_recent_num:
                keep_set.update(rows[:recent_keep_count])

    keep_set.update(hard_preserve)
    summary["kept_cycle_dirs"] = len(keep_set)

    deleted: set[Path] = set()
    removed_count = 0
    max_remove_eff = max(1, int(max_remove))

    for row in sorted(cycle_dirs, key=_cycle_sort_key):
        if removed_count >= max_remove_eff:
            break
        if row in keep_set or row in locked_dirs:
            continue
        if _remove_dir(row):
            deleted.add(row)
            removed_count += 1

    free_now = _free_gb(Path.cwd())
    if free_now < float(min_free_gb):
        summary["mode"] = "aggressive"
        protected: set[Path] = set(hard_preserve)
        protected.update(cycle_dirs[:1])
        protected.update(locked_dirs)
        for row in sorted(cycle_dirs, key=_cycle_sort_key):
            if removed_count >= max_remove_eff:
                break
            if row in deleted or row in protected:
                continue
            if _remove_dir(row):
                deleted.add(row)
                removed_count += 1
                free_now = _free_gb(Path.cwd())
                if free_now >= float(target_free_gb):
                    break

    compacted_cycle_dirs = 0
    compacted_removed_dirs = 0
    compacted_removed_files = 0
    if compact_enable and compact_max_dirs > 0:
        compact_candidates = [row for row in cycle_dirs if row not in deleted and row not in locked_dirs]
        compact_candidates = compact_candidates[max(0, int(compact_keep_latest)) :]
        for row in sorted(compact_candidates, key=_cycle_sort_key):
            if compacted_cycle_dirs >= int(compact_max_dirs):
                break
            removed_dirs, removed_files = _compact_cycle_dir(row)
            if removed_dirs > 0 or removed_files > 0:
                compacted_cycle_dirs += 1
                compacted_removed_dirs += removed_dirs
                compacted_removed_files += removed_files

    summary["removed_cycle_dirs"] = removed_count
    summary["compacted_cycle_dirs"] = compacted_cycle_dirs
    summary["compacted_removed_dirs"] = compacted_removed_dirs
    summary["compacted_removed_files"] = compacted_removed_files
    summary["removed_parent_logs"] = _cleanup_parent_logs(runs_root, keep_parent_logs=keep_parent_logs)
    summary["removed_quick_cache_files"] = _cleanup_quick_cache(quick_cache_dir, keep_quick_cache=keep_quick_cache)
    summary["free_gb_after"] = round(_free_gb(Path.cwd()), 3)
    summary["target_reached"] = bool(summary["free_gb_after"] >= float(min_free_gb))
    summary["total_cycle_dirs_after"] = len(_collect_cycle_dirs(runs_root))
    return summary


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cleanup ralph loop run artifacts with retention + disk guard.")
    p.add_argument("--runs-root", default="tmp/ralph_loop_runs_v2")
    p.add_argument("--state-file", default="tmp/ralph_loop_state_v2.json")
    p.add_argument("--quick-cache-dir", default="tmp/ralph_cache_v2/quick_eval")
    p.add_argument("--keep-latest-global", type=int, default=4)
    p.add_argument("--keep-per-cycle", type=int, default=1)
    p.add_argument("--keep-recent-cycles", type=int, default=3)
    p.add_argument("--preserve-state-recent-cycles", type=int, default=3)
    p.add_argument("--max-remove", type=int, default=800)
    p.add_argument("--min-free-gb", type=float, default=120.0)
    p.add_argument("--target-free-gb", type=float, default=160.0)
    p.add_argument("--keep-parent-logs", type=int, default=12)
    p.add_argument("--compact-enable", type=int, default=1)
    p.add_argument("--compact-keep-latest", type=int, default=1)
    p.add_argument("--compact-max-dirs", type=int, default=12)
    p.add_argument("--keep-quick-cache", type=int, default=120)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    runs_root = Path(args.runs_root)
    state_file = Path(args.state_file)
    quick_cache_dir = Path(args.quick_cache_dir)
    result = run_cleanup(
        runs_root=runs_root,
        state_file=state_file,
        keep_latest_global=max(0, int(args.keep_latest_global)),
        keep_per_cycle=max(0, int(args.keep_per_cycle)),
        keep_recent_cycles=max(0, int(args.keep_recent_cycles)),
        preserve_state_recent_cycles=max(0, int(args.preserve_state_recent_cycles)),
        max_remove=max(1, int(args.max_remove)),
        min_free_gb=max(1.0, float(args.min_free_gb)),
        target_free_gb=max(float(args.min_free_gb), float(args.target_free_gb)),
        keep_parent_logs=max(0, int(args.keep_parent_logs)),
        compact_enable=bool(int(args.compact_enable)),
        compact_keep_latest=max(0, int(args.compact_keep_latest)),
        compact_max_dirs=max(0, int(args.compact_max_dirs)),
        quick_cache_dir=quick_cache_dir,
        keep_quick_cache=max(0, int(args.keep_quick_cache)),
    )
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
