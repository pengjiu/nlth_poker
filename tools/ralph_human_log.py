#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


CYCLE_RE = re.compile(r"^cycle_(\d{3})_(\d{8}_\d{6})$")
DISPATCH_HANDLING_RE = re.compile(
    r"^\[(?P<ts>[0-9\-:\s]+)\]\s+dispatcher:\s+handling\s+status=(?P<status>\S+)\s+reason=(?P<reason>\S*)\s+rc=(?P<rc>\d+)\s+restart=(?P<restart>\d+)(?:\s+.*)?$"
)

METRIC_ROWS: tuple[tuple[str, str], ...] = (
    ("coinpoker.tierA_mean", "Coin TierA"),
    ("coinpoker.tierP_mean", "Coin TierP"),
    ("coinpoker.pool_weighted_mean", "Coin Pool"),
    ("coinpoker.br_worst_mean", "Coin BR Worst"),
    ("gg.tierA_mean", "GG TierA"),
    ("gg.tierP_mean", "GG TierP"),
    ("coinpoker.tierP_facingY_turnriver_worst_bb100", "Coin WeakBucket(TR FacingY)"),
)


@dataclass
class CycleItem:
    cycle: int
    ts: datetime
    name: str
    path: Path


@dataclass
class DispatchEvent:
    ts: datetime
    status: str
    reason: str
    rc: int
    restart: int


@dataclass
class HookRun:
    ts: datetime | None
    name: str
    path: Path


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        return data
    return None


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _parse_event_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            ts = datetime.strptime(raw, fmt)
            if ts.tzinfo is not None:
                return ts.astimezone().replace(tzinfo=None)
            return ts
        except Exception:
            continue
    return None


def _collect_cycles(runs_root: Path) -> list[CycleItem]:
    out: list[CycleItem] = []
    if not runs_root.exists():
        return out
    for p in runs_root.iterdir():
        if not p.is_dir():
            continue
        m = CYCLE_RE.match(p.name)
        if not m:
            continue
        c = int(m.group(1))
        ts = datetime.strptime(m.group(2), "%Y%m%d_%H%M%S")
        out.append(CycleItem(cycle=c, ts=ts, name=p.name, path=p))
    out.sort(key=lambda x: (x.ts, x.cycle))
    return out


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return int(v)
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return None


def _run_log_finished(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    return "\nEND rc=" in text


def _collect_in_progress_candidate_rows(cycle_path: Path) -> list[dict[str, Any]]:
    trial_root = cycle_path / "trial_quick"
    if not trial_root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for cand in sorted([p for p in trial_root.iterdir() if p.is_dir()], key=lambda x: x.name):
        seed_logs = list(cand.rglob("seed*/run.log"))
        seed_total = len(seed_logs)
        seed_done = 0
        latest_mtime = cand.stat().st_mtime
        for log in seed_logs:
            try:
                latest_mtime = max(latest_mtime, log.stat().st_mtime)
            except Exception:
                pass
            if _run_log_finished(log):
                seed_done += 1
        rows.append(
            {
                "candidate": cand.name,
                "seed_total": seed_total,
                "seed_done": seed_done,
                "latest_mtime": latest_mtime,
            }
        )
    rows.sort(key=lambda r: str(r.get("candidate", "")))
    return rows


def _trace_events_for_cycle(events: list[dict[str, Any]], cycle: int, limit: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for evt in events:
        if str(evt.get("status")) != "trace":
            continue
        evt_cycle = _as_int(evt.get("cycle"))
        if evt_cycle != cycle:
            continue
        rows.append(evt)
    if len(rows) <= limit:
        return rows
    return rows[-limit:]


def _collect_dispatch_events(dispatch_log: Path) -> list[DispatchEvent]:
    events: list[DispatchEvent] = []
    if not dispatch_log.exists():
        return events
    for line in dispatch_log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = DISPATCH_HANDLING_RE.match(line.strip())
        if not m:
            continue
        ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
        events.append(
            DispatchEvent(
                ts=ts,
                status=m.group("status"),
                reason=m.group("reason"),
                rc=int(m.group("rc")),
                restart=int(m.group("restart")),
            )
        )
    events.sort(key=lambda x: x.ts)
    return events


def _parse_hook_run_ts(name: str) -> datetime | None:
    parts = name.split("_", 2)
    if len(parts) < 2:
        return None
    raw = f"{parts[0]}_{parts[1]}"
    try:
        return datetime.strptime(raw, "%Y%m%d_%H%M%S")
    except Exception:
        return None


def _collect_hook_runs(hook_runs_root: Path) -> list[HookRun]:
    if not hook_runs_root.exists():
        return []
    out = [HookRun(ts=_parse_hook_run_ts(p.name), name=p.name, path=p) for p in hook_runs_root.iterdir() if p.is_dir()]
    out.sort(key=lambda x: (x.ts is None, x.ts or datetime.min, x.name))
    return out


def _current_runtime_start(events: list[dict[str, Any]]) -> datetime | None:
    parsed: list[tuple[datetime, dict[str, Any]]] = []
    for e in events:
        ts = _parse_event_ts(e.get("ts"))
        if ts is None:
            continue
        parsed.append((ts, e))
    if not parsed:
        return None
    last_boundary = -1
    for idx, (_, e) in enumerate(parsed):
        status = str(e.get("status", ""))
        reason = str(e.get("reason", ""))
        if status == "restart" or (status == "stopped" and reason != "target_achieved"):
            last_boundary = idx
    for idx in range(last_boundary + 1, len(parsed)):
        ts, e = parsed[idx]
        if str(e.get("status", "")) == "heartbeat":
            return ts
    return parsed[-1][0]


def _events_for_window(events: list[DispatchEvent], start: datetime, end: datetime | None) -> list[DispatchEvent]:
    out: list[DispatchEvent] = []
    for e in events:
        if e.ts < start:
            continue
        if end is not None and e.ts >= end:
            continue
        out.append(e)
    return out


def _hooks_for_window(hooks: list[HookRun], start: datetime, end: datetime | None) -> list[HookRun]:
    out: list[HookRun] = []
    for h in hooks:
        if h.ts is None:
            continue
        if h.ts < start:
            continue
        if end is not None and h.ts >= end:
            continue
        out.append(h)
    return out


def _select_best_hook_run(hooks: list[HookRun]) -> HookRun | None:
    if not hooks:
        return None
    for h in reversed(hooks):
        if (h.path / "final_message.txt").exists():
            return h
    return hooks[-1]


def _fmt_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def _fmt_float(v: Any) -> str:
    if isinstance(v, (int, float)):
        return f"{float(v):.3f}"
    return "null"


def _fmt_pass_fail(v: Any) -> str:
    if isinstance(v, bool):
        return "PASS" if v else "FAIL"
    return "-"


def _safe_float(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _metric_get(metrics: dict[str, Any], path: str) -> float | None:
    cur: Any = metrics
    for tok in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(tok)
    return _safe_float(cur)


def _extract_metrics(full_obj: dict[str, Any] | None) -> dict[str, float | None]:
    if not isinstance(full_obj, dict):
        return {}
    coin = full_obj.get("coinpoker") if isinstance(full_obj.get("coinpoker"), dict) else {}
    gg = full_obj.get("gg") if isinstance(full_obj.get("gg"), dict) else {}
    return {
        "coinpoker.tierA_mean": _safe_float(coin.get("tierA_mean")),
        "coinpoker.tierP_mean": _safe_float(coin.get("tierP_mean")),
        "coinpoker.pool_weighted_mean": _safe_float(coin.get("pool_weighted_mean")),
        "coinpoker.br_worst_mean": _safe_float(coin.get("br_worst_mean")),
        "coinpoker.tierP_facingY_turnriver_worst_bb100": _safe_float(coin.get("tierP_facingY_turnriver_worst_bb100")),
        "gg.tierA_mean": _safe_float(gg.get("tierA_mean")),
        "gg.tierP_mean": _safe_float(gg.get("tierP_mean")),
    }


def _quick_gate_obj(review: dict[str, Any], cycle_result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(review, dict):
        qg = review.get("quick_gate")
        if isinstance(qg, dict):
            return qg
    if isinstance(cycle_result, dict):
        qg = cycle_result.get("quick_gate")
        if isinstance(qg, dict):
            return qg
    return {}


def _runtime_baseline_from_state(state: dict[str, Any] | None) -> dict[str, Any]:
    baseline_obj = (state or {}).get("baseline") if isinstance(state, dict) else None
    if isinstance(baseline_obj, dict):
        metrics = baseline_obj.get("metrics")
        if not isinstance(metrics, dict):
            full = baseline_obj.get("full_metrics") if isinstance(baseline_obj.get("full_metrics"), dict) else None
            metrics = _extract_metrics(full)
        return {
            "policy_label": baseline_obj.get("policy_label"),
            "policy_options_hash": baseline_obj.get("policy_options_hash"),
            "source": baseline_obj.get("source"),
            "adopted_cycle": baseline_obj.get("adopted_cycle"),
            "updated_at": baseline_obj.get("updated_at"),
            "metrics": metrics if isinstance(metrics, dict) else {},
        }
    full = (state or {}).get("active_full_metrics") if isinstance(state, dict) else None
    return {
        "policy_label": (state or {}).get("active_policy_label") if isinstance(state, dict) else None,
        "policy_options_hash": None,
        "source": "legacy_active_full_metrics",
        "adopted_cycle": (state or {}).get("last_cycle") if isinstance(state, dict) else None,
        "updated_at": (state or {}).get("updated_at") if isinstance(state, dict) else None,
        "metrics": _extract_metrics(full if isinstance(full, dict) else None),
    }


def _load_cycle_summary(cycle: CycleItem, state: dict[str, Any] | None, runtime_baseline: dict[str, Any]) -> dict[str, Any]:
    cycle_result = _load_json(cycle.path / "cycle_result.json")
    review = _load_json(cycle.path / "review.json")
    baseline_metrics_default = (
        runtime_baseline.get("metrics")
        if isinstance(runtime_baseline, dict) and isinstance(runtime_baseline.get("metrics"), dict)
        else {}
    )
    baseline_meta_default = runtime_baseline if isinstance(runtime_baseline, dict) else {}
    if not isinstance(cycle_result, dict):
        return {
            "decision": "IN_PROGRESS",
            "note": "-",
            "metrics": _extract_metrics(((state or {}).get("active_full_metrics") if isinstance(state, dict) else None)),
            "metrics_source": "state.active_full_metrics",
            "baseline_metrics": baseline_metrics_default,
            "baseline_meta": baseline_meta_default,
            "review": review if isinstance(review, dict) else {},
            "cycle_result": {},
        }
    decision = str(cycle_result.get("decision", "IN_PROGRESS"))
    note = str(cycle_result.get("note", "-"))
    trial_full = cycle_result.get("trial_full")
    active_full = cycle_result.get("active_full_metrics")
    if decision == "ADOPT" and isinstance(trial_full, dict):
        metrics = _extract_metrics(trial_full)
        source = "trial_full"
    elif isinstance(active_full, dict):
        metrics = _extract_metrics(active_full)
        source = "active_full_metrics"
    else:
        metrics = _extract_metrics(((state or {}).get("active_full_metrics") if isinstance(state, dict) else None))
        source = "state.active_full_metrics"

    baseline_before = (
        cycle_result.get("baseline", {}).get("before")
        if isinstance(cycle_result.get("baseline"), dict)
        else None
    )
    if isinstance(baseline_before, dict):
        baseline_metrics = baseline_before.get("metrics") if isinstance(baseline_before.get("metrics"), dict) else baseline_metrics_default
        baseline_meta = baseline_before
    else:
        baseline_metrics = baseline_metrics_default
        baseline_meta = baseline_meta_default
    return {
        "decision": decision,
        "note": note,
        "metrics": metrics,
        "metrics_source": source,
        "baseline_metrics": baseline_metrics if isinstance(baseline_metrics, dict) else {},
        "baseline_meta": baseline_meta if isinstance(baseline_meta, dict) else {},
        "review": review if isinstance(review, dict) else {},
        "cycle_result": cycle_result,
    }


def _gate_map(review: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    rows = ((review.get("target_eval_active") or {}).get("gates")) if isinstance(review, dict) else None
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        metric_path = row.get("metric_path")
        passed = row.get("pass")
        if not isinstance(metric_path, str):
            continue
        if isinstance(passed, bool):
            out[metric_path] = "PASS" if passed else "FAIL"
    return out


def _read_hook_message(path: Path) -> str:
    p = path / "final_message.txt"
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace").strip()


def _short(text: str, limit: int = 160) -> str:
    t = " ".join(text.split())
    if len(t) <= limit:
        return t
    return t[: limit - 3] + "..."


def _parse_model_plan_lines(msg: str) -> list[str]:
    if not msg:
        return ["- (无模型输出内容)"]
    try:
        obj = json.loads(msg)
    except Exception:
        lines = [ln.strip() for ln in msg.splitlines() if ln.strip()]
        if not lines:
            return ["- (空输出)"]
        return [f"- {_short(lines[0])}"]

    if not isinstance(obj, dict):
        return [f"- {_short(msg)}"]
    next_action = obj.get("next_action")
    out: list[str] = []
    change_applied = obj.get("change_applied")
    if isinstance(change_applied, bool):
        out.append(f"- change_applied: {change_applied}")
    if isinstance(next_action, dict):
        out.append(f"- focus_metric: {next_action.get('focus_metric')}")
        knob_plan = next_action.get("knob_plan")
        if isinstance(knob_plan, list) and knob_plan:
            parts: list[str] = []
            for row in knob_plan[:5]:
                if not isinstance(row, dict):
                    continue
                key = row.get("key")
                delta = row.get("delta")
                if isinstance(key, str):
                    parts.append(f"{key}:{delta}")
            if parts:
                out.append("- knob_plan: " + ", ".join(parts))
        hints = next_action.get("quick_gate_hints")
        if isinstance(hints, dict):
            out.append(
                "- quick_gate_hints: "
                f"hands={hints.get('focus_support_min_hands')} "
                f"hits={hints.get('focus_support_min_hits')} "
                f"behavior_delta_min={hints.get('behavior_delta_min')}"
            )
        note = next_action.get("note")
        if isinstance(note, str) and note.strip():
            out.append("- note: " + _short(note))
    if not out:
        out.append("- " + _short(msg))
    return out


def _read_hook_changed_files(path: Path) -> list[str]:
    candidates = sorted(path.glob("code_patch_changed_files_attempt*.txt"))
    if not candidates:
        p = path / "code_patch_changed_files.txt"
        if p.exists():
            candidates = [p]
    if not candidates:
        return []
    raw = candidates[-1].read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def build_report(
    repo_root: Path,
    runs_root: Path,
    events_log: Path,
    dispatch_log: Path,
    state_file: Path,
    supervisor_health_file: Path,
    output: Path,
    hook_runs_root: Path,
    max_cycles: int,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    events = _load_ndjson(events_log)
    cycles = _collect_cycles(runs_root)
    dispatch_events = _collect_dispatch_events(dispatch_log)
    hook_runs = _collect_hook_runs(hook_runs_root)
    state = _load_json(state_file)
    supervisor_health = _load_json(supervisor_health_file)
    runtime_start = _current_runtime_start(events)
    runtime_baseline = _runtime_baseline_from_state(state)
    baseline_metrics = runtime_baseline.get("metrics") if isinstance(runtime_baseline.get("metrics"), dict) else {}

    last_event = events[-1] if events else {}
    last_cycle = cycles[-1] if cycles else None
    health_status = "-"
    if last_event and str(last_event.get("status")) == "heartbeat" and str(last_event.get("reason")) == "running":
        health_status = "RUNNING"
    elif isinstance(supervisor_health, dict) and str(supervisor_health.get("status")) == "running":
        health_status = "RUNNING"
    else:
        health_status = "ATTENTION"

    lines: list[str] = []
    lines.append(f"# Ralph Iteration Dashboard ({now})")
    lines.append("")
    lines.append(f"- 运行状态: {health_status}")
    lines.append(f"- 最新事件: ts={last_event.get('ts')} status={last_event.get('status')} reason={last_event.get('reason')}")
    if runtime_start is not None:
        lines.append(f"- 当前运行期起点: {runtime_start.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        lines.append("- 当前运行期起点: unknown")
    lines.append(f"- 当前cycle目录: {last_cycle.name if last_cycle is not None else 'none'}")
    lines.append(
        "- 当前运行时基线: "
        f"policy={runtime_baseline.get('policy_label') or 'null'} "
        f"adopted_cycle={runtime_baseline.get('adopted_cycle') if runtime_baseline.get('adopted_cycle') is not None else 'null'} "
        f"source={runtime_baseline.get('source') or 'null'}"
    )
    lines.append("")

    runtime_cycles = [c for c in cycles if c.ts >= runtime_start] if isinstance(runtime_start, datetime) else list(cycles)
    # A cycle can start before a restart boundary and continue writing in the current runtime.
    if cycles:
        latest_cycle = cycles[-1]
        if latest_cycle not in runtime_cycles and not (latest_cycle.path / "cycle_result.json").exists():
            runtime_cycles.append(latest_cycle)

    completed_runtime_cycles = [c for c in runtime_cycles if (c.path / "cycle_result.json").exists()]
    in_progress_cycle = next((c for c in reversed(runtime_cycles) if not (c.path / "cycle_result.json").exists()), None)
    recent = completed_runtime_cycles[-max_cycles:] if completed_runtime_cycles else []
    if not recent and in_progress_cycle is None:
        lines.append("## 当前运行期无周期数据")
        if cycles:
            lines.append(f"- 历史周期总数: {len(cycles)}（已按当前运行期过滤）")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    if isinstance(in_progress_cycle, CycleItem):
        in_progress_rows = _collect_in_progress_candidate_rows(in_progress_cycle.path)
        started_candidates = sum(1 for r in in_progress_rows if int(r.get("seed_total", 0)) > 0)
        completed_candidates = sum(
            1
            for r in in_progress_rows
            if int(r.get("seed_total", 0)) > 0 and int(r.get("seed_done", 0)) >= int(r.get("seed_total", 0))
        )
        running_rows = [
            r
            for r in in_progress_rows
            if int(r.get("seed_total", 0)) > 0 and int(r.get("seed_done", 0)) < int(r.get("seed_total", 0))
        ]
        running_rows.sort(key=lambda r: float(r.get("latest_mtime", 0.0)), reverse=True)
        active_candidate = running_rows[0].get("candidate") if running_rows else "-"
        active_cache_hit = in_progress_cycle.path / "active_quick" / "quick_eval_cache_hit.json"
        active_cache_miss = in_progress_cycle.path / "active_quick" / "quick_eval_cache_miss.json"
        if active_cache_hit.exists():
            active_cache = "hit"
        elif active_cache_miss.exists():
            active_cache = "miss"
        else:
            active_cache = "-"

        lines.append(f"## 当前进行中周期: {in_progress_cycle.name}")
        lines.append(
            f"- 候选进度: started={started_candidates}/{len(in_progress_rows)} | completed={completed_candidates}/{len(in_progress_rows)}"
        )
        lines.append(f"- 当前活跃候选: {active_candidate}")
        lines.append(f"- active_quick_cache: {active_cache}")
        lines.append("")
        if in_progress_rows:
            lines.append("| candidate | seeds_done | seeds_total | progress |")
            lines.append("|---|---:|---:|---:|")
            for row in in_progress_rows:
                done = int(row.get("seed_done", 0))
                total = int(row.get("seed_total", 0))
                pct = (100.0 * done / total) if total > 0 else 0.0
                lines.append(f"| {row.get('candidate')} | {done} | {total} | {pct:.1f}% |")
            lines.append("")
        trace_rows = _trace_events_for_cycle(events, in_progress_cycle.cycle, limit=8)
        if trace_rows:
            lines.append("- 最近 trace 事件:")
            for evt in trace_rows:
                lines.append(
                    f"  - ts={evt.get('ts')} reason={evt.get('reason')} candidate={evt.get('candidate')} decision={evt.get('decision')}"
                )
            lines.append("")

    for idx, c in enumerate(recent):
        next_ts = recent[idx + 1].ts if idx + 1 < len(recent) else None
        dispatch_window = _events_for_window(dispatch_events, c.ts, next_ts)
        hook_window = _hooks_for_window(hook_runs, c.ts, next_ts)
        hook_run = _select_best_hook_run(hook_window)
        model_called = "yes" if hook_run else ("no")
        trigger = ",".join(sorted({e.reason for e in dispatch_window})) if dispatch_window else "-"

        cyc = _load_cycle_summary(c, state, runtime_baseline)
        decision = cyc["decision"]
        note = cyc["note"]
        review = cyc["review"] if isinstance(cyc["review"], dict) else {}
        cycle_baseline_metrics = cyc["baseline_metrics"] if isinstance(cyc.get("baseline_metrics"), dict) else baseline_metrics
        cycle_baseline_meta = cyc["baseline_meta"] if isinstance(cyc.get("baseline_meta"), dict) else runtime_baseline
        gate_map = _gate_map(review)
        focus_metric = ((review.get("next_hypothesis") or {}).get("focus_metric") if isinstance(review, dict) else None) or "-"
        focus_reason = ((review.get("next_hypothesis") or {}).get("reason") if isinstance(review, dict) else None) or "-"
        quick_gate = _quick_gate_obj(review, cyc["cycle_result"] if isinstance(cyc["cycle_result"], dict) else {})
        quick_gate_reason = quick_gate.get("reason") if isinstance(quick_gate.get("reason"), str) else None
        thresholds = quick_gate.get("thresholds") if isinstance(quick_gate.get("thresholds"), dict) else {}
        hint_overrides = quick_gate.get("hint_overrides") if isinstance(quick_gate.get("hint_overrides"), dict) else {}
        stage1 = quick_gate.get("stage1_coverage") if isinstance(quick_gate.get("stage1_coverage"), dict) else {}
        stage2 = quick_gate.get("stage2_effect") if isinstance(quick_gate.get("stage2_effect"), dict) else {}
        stage1_candidates = stage1.get("candidates") if isinstance(stage1.get("candidates"), dict) else {}
        stage2_candidates = stage2.get("candidates") if isinstance(stage2.get("candidates"), dict) else {}
        targeted_attempted = _as_int(quick_gate.get("targeted_focus_attempted_count"))
        targeted_merged = _as_int(quick_gate.get("targeted_focus_merged_count"))
        targeted_delta_hands = _as_int(quick_gate.get("targeted_focus_support_hands_delta_total"))
        targeted_delta_hits = _as_int(quick_gate.get("targeted_focus_support_hits_delta_total"))
        llm_required = (
            ((cyc["cycle_result"].get("execution_controls") or {}).get("require_llm_action_ticket"))
            if isinstance(cyc["cycle_result"], dict)
            else None
        )
        baseline_integrity_pass = (
            ((cyc["cycle_result"].get("baseline_integrity") or {}).get("pass"))
            if isinstance(cyc["cycle_result"], dict)
            else None
        )

        lines.append(f"## Cycle {c.name}")
        lines.append(f"状态: {decision}")
        lines.append("本轮类型: 自动迭代轮")
        lines.append(
            f"模型参与: {model_called} | trigger={trigger} | hook_run={hook_run.name if isinstance(hook_run, HookRun) else '-'}"
        )
        lines.append("")
        lines.append("### 1) 本轮改进思路")
        lines.append(f"- 核心问题: focus_metric={focus_metric}")
        lines.append(f"- 改进假设: {focus_reason}")
        lines.append(f"- 执行门禁反馈: quick_gate={quick_gate_reason if isinstance(quick_gate_reason, str) else '-'}")
        lines.append(
            "- 两阶段门禁: "
            f"stage1={_fmt_pass_fail(stage1.get('pass'))} "
            f"stage2={_fmt_pass_fail(stage2.get('pass'))}"
        )
        lines.append(
            "- stage1计数: "
            f"runtime={stage1_candidates.get('runtime_pass_count', '-')} "
            f"ante={stage1_candidates.get('ante_integrity_pass_count', '-')} "
            f"support={stage1_candidates.get('focus_support_pass_count', '-')} "
            f"stage1_pass={stage1_candidates.get('stage1_coverage_pass_count', '-')}"
        )
        lines.append(
            "- stage2计数: "
            f"behavior={stage2_candidates.get('behavior_pass_count', '-')} "
            f"qreg={stage2_candidates.get('quick_regression_pass_count', '-')} "
            f"stage2_pass={stage2_candidates.get('stage2_effect_pass_count', '-')}"
        )
        lines.append(
            "- targeted增益: "
            f"attempted={targeted_attempted if isinstance(targeted_attempted, int) else '-'} "
            f"merged={targeted_merged if isinstance(targeted_merged, int) else '-'} "
            f"Δhands={targeted_delta_hands if isinstance(targeted_delta_hands, int) else '-'} "
            f"Δhits={targeted_delta_hits if isinstance(targeted_delta_hits, int) else '-'}"
        )
        lines.append(
            "- 门槛参数: "
            f"support_hands={thresholds.get('focus_support_min_hands', '-')} "
            f"support_hits={thresholds.get('focus_support_min_hits', '-')} "
            f"behavior_min={thresholds.get('behavior_delta_min', '-')} "
            f"qreg_tol={thresholds.get('quick_regression_tolerance', '-')}"
        )
        if hint_overrides:
            lines.append(
                "- 门槛覆写: "
                f"policy={hint_overrides.get('policy', '-')} "
                f"applied={bool(hint_overrides.get('applied'))} "
                f"ignored={bool(hint_overrides.get('ignored'))}"
            )
        lines.append("")

        lines.append("### 2) 大模型改进计划")
        if isinstance(hook_run, HookRun):
            msg_path = hook_run.path / "final_message.txt"
            if msg_path.exists():
                msg = _read_hook_message(hook_run.path)
                lines.extend(_parse_model_plan_lines(msg))
                changed_files = _read_hook_changed_files(hook_run.path)
                if changed_files:
                    lines.append("- code_patch_files: " + ", ".join(changed_files))
            else:
                lines.append("- (模型执行中，结果尚未落盘)")
        else:
            lines.append("- (本轮无模型输出)")
        lines.append("")

        lines.append("### 3) 与基线关键对比")
        lines.append(
            f"- baseline_used: policy={cycle_baseline_meta.get('policy_label') or 'null'} "
            f"adopted_cycle={cycle_baseline_meta.get('adopted_cycle') if cycle_baseline_meta.get('adopted_cycle') is not None else 'null'}"
        )
        lines.append("| 维度 | baseline | current | delta | gate |")
        lines.append("|---|---:|---:|---:|---|")
        metrics = cyc["metrics"] if isinstance(cyc["metrics"], dict) else {}
        for key, label in METRIC_ROWS:
            b = cycle_baseline_metrics.get(key) if isinstance(cycle_baseline_metrics, dict) else None
            cur = metrics.get(key) if isinstance(metrics, dict) else None
            b_f = _safe_float(b)
            c_f = _safe_float(cur)
            d_f = (c_f - b_f) if isinstance(c_f, float) and isinstance(b_f, float) else None
            gate = gate_map.get(key, "-")
            lines.append(
                f"| {label} | {_fmt_float(b_f)} | {_fmt_float(c_f)} | {_fmt_float(d_f)} | {gate} |"
            )
        lines.append("")

        lines.append("### 4) 本轮结论")
        lines.append(f"- 晋级决策: {decision}")
        lines.append(f"- 结论原因: {_short(str(note), 220)}")
        lines.append(f"- 关键弱点: {focus_metric}")
        lines.append(f"- 基线完整性: {baseline_integrity_pass if isinstance(baseline_integrity_pass, bool) else 'unknown'}")
        lines.append(f"- LLM硬门禁: {llm_required if isinstance(llm_required, bool) else 'unknown'}")
        lines.append("- evidence_ref:")
        lines.append(f"  - `{_fmt_path(c.path / 'review.json', repo_root)}`")
        lines.append(f"  - `{_fmt_path(c.path / 'cycle_result.json', repo_root)}`")
        if isinstance(hook_run, HookRun):
            lines.append(f"  - `{_fmt_path(hook_run.path / 'final_message.txt', repo_root)}`")
        lines.append("")

    lines.append("## 说明")
    lines.append("- 本日志按“每轮卡片”输出，聚焦：改进思路、模型计划、是否晋级、与基线对比。")
    lines.append("- 历史原始事件和详细运行噪音请看：`tmp/ralph_loop_events.ndjson`、`tmp/ralph_loop_supervisor.log`。")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Ralph 循环的人类可读摘要日志（每轮卡片）。")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--runs-root", default="tmp/ralph_loop_runs_v2")
    parser.add_argument("--events-log", default="tmp/ralph_loop_events.ndjson")
    parser.add_argument("--dispatch-log", default="tmp/ralph_hook_dispatcher.log")
    parser.add_argument("--state-file", default="tmp/ralph_loop_state_v2.json")
    parser.add_argument("--supervisor-health-file", default="tmp/ralph_health/supervisor_heartbeat.json")
    parser.add_argument("--hook-runs-root", default="tmp/ralph_hook_runs")
    parser.add_argument("--output", default="tmp/ralph_loop_human_log.md")
    parser.add_argument("--max-cycles", type=int, default=8)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    build_report(
        repo_root=repo_root,
        runs_root=repo_root / args.runs_root,
        events_log=repo_root / args.events_log,
        dispatch_log=repo_root / args.dispatch_log,
        state_file=repo_root / args.state_file,
        supervisor_health_file=repo_root / args.supervisor_health_file,
        output=repo_root / args.output,
        hook_runs_root=repo_root / args.hook_runs_root,
        max_cycles=max(1, int(args.max_cycles)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
