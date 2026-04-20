#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


DEFAULT_TMP_KEEP = (
    "ralph_baseline_snapshot.json",
    "ralph_cache_v2",
    "ralph_front_monitor.log",
    "ralph_health",
    "ralph_hook_dispatcher.lock",
    "ralph_hook_dispatcher.log",
    "ralph_hook_fail_streak.txt",
    "ralph_hook_last_hash.txt",
    "ralph_hook_runs",
    "ralph_hook_stats.json",
    "ralph_loop_events.ndjson",
    "ralph_loop_human_log.md",
    "ralph_loop_runs_v2",
    "ralph_loop_state_v2.json",
    "ralph_loop_state_v2.json.parent.lock",
    "ralph_loop_supervisor.lock",
    "ralph_loop_supervisor.log",
    "ralph_next_action.json",
    "ralph_next_plan.md",
    "ralph_pids",
    "ralph_time_hook.lock",
    "ralph_time_hook.log",
)

DEFAULT_TMP_DROP = (
    "ralph_log_archive",
    "ralph_loop_runs",
    "ralph_loop_runs_resume_test",
    "ralph_loop_runs_target_test",
    "ralph_loop_state_resume_test.json",
    "ralph_loop_state_target_test.json",
)


def _free_gb(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return float(usage.free) / float(1024**3)


def _remove_path(path: Path) -> bool:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


def _iter_entries(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.iterdir(), key=lambda p: p.name)


def _prune_tmp_root(tmp_root: Path, keep_entries: set[str], drop_entries: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "tmp_root": str(tmp_root),
        "removed": 0,
        "failed": 0,
        "kept": 0,
        "removed_entries": [],
        "failed_entries": [],
    }
    for entry in _iter_entries(tmp_root):
        if entry.name in drop_entries:
            pass
        elif entry.name in keep_entries or entry.name.startswith("ralph_"):
            out["kept"] += 1
            continue
        ok = _remove_path(entry)
        if ok:
            out["removed"] += 1
            out["removed_entries"].append(entry.name)
        else:
            out["failed"] += 1
            out["failed_entries"].append(entry.name)
    return out


def _prune_eval_root(eval_root: Path, keep_latest_dirs: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "eval_root": str(eval_root),
        "keep_latest_dirs": int(keep_latest_dirs),
        "removed": 0,
        "failed": 0,
        "kept": 0,
        "removed_entries": [],
        "failed_entries": [],
    }
    if not eval_root.exists():
        return out

    rows = [p for p in eval_root.iterdir() if p.is_dir()]
    rows.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    keep = set(rows[: max(0, int(keep_latest_dirs))])
    out["kept"] = len(keep)

    for row in rows:
        if row in keep:
            continue
        ok = _remove_path(row)
        if ok:
            out["removed"] += 1
            out["removed_entries"].append(row.name)
        else:
            out["failed"] += 1
            out["failed_entries"].append(row.name)
    return out


def _prune_baselines(baselines_root: Path, keep_latest_dirs: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "baselines_root": str(baselines_root),
        "keep_latest_dirs": int(keep_latest_dirs),
        "removed": 0,
        "failed": 0,
        "kept_dirs": 0,
        "kept_files": 0,
        "removed_entries": [],
        "failed_entries": [],
    }
    if not baselines_root.exists():
        return out

    entries = _iter_entries(baselines_root)
    files = [p for p in entries if p.is_file()]
    dirs = [p for p in entries if p.is_dir()]
    out["kept_files"] = len(files)

    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    keep = set(dirs[: max(0, int(keep_latest_dirs))])
    out["kept_dirs"] = len(keep)

    for row in dirs:
        if row in keep:
            continue
        ok = _remove_path(row)
        if ok:
            out["removed"] += 1
            out["removed_entries"].append(row.name)
        else:
            out["failed"] += 1
            out["failed_entries"].append(row.name)
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Prune historical temp/eval artifacts while keeping recent baselines.")
    p.add_argument("--tmp-root", default="tmp")
    p.add_argument("--artifacts-eval-root", default="artifacts/eval")
    p.add_argument("--artifacts-baselines-root", default="artifacts/baselines")
    p.add_argument("--keep-baseline-dirs", type=int, default=4)
    p.add_argument("--keep-eval-dirs", type=int, default=0)
    p.add_argument("--keep-tmp-entry", action="append", default=[])
    return p


def main() -> int:
    args = _build_parser().parse_args()
    cwd = Path.cwd()
    free_before = _free_gb(cwd)

    keep_entries = set(DEFAULT_TMP_KEEP)
    keep_entries.update(str(x) for x in (args.keep_tmp_entry or []) if str(x).strip())
    drop_entries = set(DEFAULT_TMP_DROP)

    tmp_root = Path(args.tmp_root)
    eval_root = Path(args.artifacts_eval_root)
    baselines_root = Path(args.artifacts_baselines_root)

    tmp_result = _prune_tmp_root(tmp_root, keep_entries, drop_entries)
    eval_result = _prune_eval_root(eval_root, keep_latest_dirs=max(0, int(args.keep_eval_dirs)))
    baselines_result = _prune_baselines(
        baselines_root,
        keep_latest_dirs=max(0, int(args.keep_baseline_dirs)),
    )

    free_after = _free_gb(cwd)
    out = {
        "free_gb_before": round(free_before, 3),
        "free_gb_after": round(free_after, 3),
        "free_gb_reclaimed": round(max(0.0, free_after - free_before), 3),
        "tmp": tmp_result,
        "artifacts_eval": eval_result,
        "artifacts_baselines": baselines_result,
    }
    print(json.dumps(out, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
