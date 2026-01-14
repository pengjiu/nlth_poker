from __future__ import annotations

from typing import Any


def _bb_per_100(profit_bb: float, hands: int) -> float:
    return profit_bb * 100.0 / max(1, int(hands))


def _pick_worst(entries: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float | None, int]:
    worst_entry: dict[str, Any] | None = None
    worst_val: float | None = None
    worst_hands = 0
    for entry in entries:
        hands = int(entry.get("hands", 0) or 0)
        if hands <= 0:
            continue
        profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
        bb100 = _bb_per_100(profit_bb, hands)
        if worst_val is None or bb100 < worst_val:
            worst_entry = entry
            worst_val = bb100
            worst_hands = hands
    return worst_entry, worst_val, worst_hands


def _evidence_bb_facing(analysis: dict[str, Any], seed: int | None) -> dict[str, Any] | None:
    data = analysis.get("bb_flat_postflop_facing_by_street") or []
    entries = data.values() if isinstance(data, dict) else data if isinstance(data, list) else []
    entry, bb100, hands = _pick_worst(list(entries))
    if not entry or bb100 is None:
        return None
    street = entry.get("street")
    facing = entry.get("facing")
    if not isinstance(street, str) or facing is None:
        return None
    ref = f"report:BBFlatPostflopFacing/{street}_{facing}"
    return {
        "bucket_key": f"BB|{street}|facing:{facing}",
        "metric": f"bb/100={bb100:.2f}",
        "n": hands,
        "seed": seed,
        "evidence_ref": ref,
    }


def _evidence_bb_spr(analysis: dict[str, Any], seed: int | None) -> dict[str, Any] | None:
    data = analysis.get("bb_flat_postflop") or []
    entries = data.values() if isinstance(data, dict) else data if isinstance(data, list) else []
    entry, bb100, hands = _pick_worst(list(entries))
    if not entry or bb100 is None:
        return None
    spr_bucket = entry.get("spr_bucket")
    oop = bool(entry.get("oop_multi_street"))
    if spr_bucket is None:
        return None
    oop_flag = "Y" if oop else "N"
    ref = f"report:BBFlatPostflop/{spr_bucket}_oop_{oop_flag}"
    return {
        "bucket_key": f"SPR:{spr_bucket}|oop_multi_street={oop_flag}",
        "metric": f"bb/100={bb100:.2f}",
        "n": hands,
        "seed": seed,
        "evidence_ref": ref,
    }


def _evidence_players(analysis: dict[str, Any], seed: int | None) -> dict[str, Any] | None:
    worst_entry: dict[str, Any] | None = None
    worst_val: float | None = None
    worst_hands = 0
    worst_stage: str | None = None
    worst_players: str | None = None
    for stage, table in (analysis.get("profit_by_players") or {}).items():
        if not isinstance(table, dict):
            continue
        for players, entry in table.items():
            hands = int(entry.get("hands", 0) or 0)
            if hands <= 0:
                continue
            profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
            bb100 = _bb_per_100(profit_bb, hands)
            if worst_val is None or bb100 < worst_val:
                worst_entry = entry
                worst_val = bb100
                worst_hands = hands
                worst_stage = str(stage)
                worst_players = str(players)
    if worst_entry is None or worst_val is None or worst_stage is None or worst_players is None:
        return None
    ref = f"report:ProfitByPlayers/{worst_stage}_{worst_players}p"
    return {
        "bucket_key": f"players:{worst_players}p|{worst_stage}",
        "metric": f"bb/100={worst_val:.2f}",
        "n": worst_hands,
        "seed": seed,
        "evidence_ref": ref,
    }


def _evidence_position(analysis: dict[str, Any], seed: int | None) -> dict[str, Any] | None:
    data = analysis.get("position_profit") or {}
    if not isinstance(data, dict):
        return None
    worst_pos: str | None = None
    worst_val: float | None = None
    worst_hands = 0
    for pos, entry in data.items():
        if not isinstance(entry, dict):
            continue
        hands = int(entry.get("hands", 0) or 0)
        if hands <= 0:
            continue
        profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
        bb100 = _bb_per_100(profit_bb, hands)
        if worst_val is None or bb100 < worst_val:
            worst_val = bb100
            worst_pos = str(pos)
            worst_hands = hands
    if worst_pos is None or worst_val is None:
        return None
    ref = f"report:PositionEV/{worst_pos}"
    return {
        "bucket_key": f"pos:{worst_pos}",
        "metric": f"bb/100={worst_val:.2f}",
        "n": worst_hands,
        "seed": seed,
        "evidence_ref": ref,
    }


def _evidence_pot_bucket(analysis: dict[str, Any], seed: int | None) -> dict[str, Any] | None:
    data = analysis.get("pot_bucket_profit") or {}
    if not isinstance(data, dict):
        return None
    worst_bucket: str | None = None
    worst_val: float | None = None
    worst_hands = 0
    for bucket, entry in data.items():
        if not isinstance(entry, dict):
            continue
        hands = int(entry.get("hands", 0) or 0)
        if hands <= 0:
            continue
        profit_bb = float(entry.get("profit_bb", 0.0) or 0.0)
        bb100 = _bb_per_100(profit_bb, hands)
        if worst_val is None or bb100 < worst_val:
            worst_val = bb100
            worst_bucket = str(bucket)
            worst_hands = hands
    if worst_bucket is None or worst_val is None:
        return None
    ref = f"report:PotBuckets/{worst_bucket}"
    return {
        "bucket_key": f"pot:{worst_bucket}",
        "metric": f"bb/100={worst_val:.2f}",
        "n": worst_hands,
        "seed": seed,
        "evidence_ref": ref,
    }


def build_iteration_protocol(report: dict[str, Any]) -> dict[str, Any]:
    analysis = report.get("analysis") or {}
    scene = report.get("scene") or {}
    baseline = report.get("baseline") or {}
    seed = scene.get("seed")
    evidence: list[dict[str, Any]] = []
    for builder in (
        _evidence_bb_facing,
        _evidence_bb_spr,
        _evidence_players,
        _evidence_position,
        _evidence_pot_bucket,
    ):
        entry = builder(analysis, seed)
        if entry:
            evidence.append(entry)
    return {
        "schema_id": "iteration_protocol_v1",
        "baseline": baseline,
        "evidence": evidence,
        "change": [],
        "gate": None,
        "regression": None,
        "result": {"fix": "PENDING", "side_effect": "PENDING"},
    }


def validate_iteration_protocol(protocol: dict[str, Any] | None, *, strict: bool = True) -> list[str]:
    errors: list[str] = []
    if not isinstance(protocol, dict):
        errors.append("PROTOCOL_MISSING")
        if strict:
            raise ValueError("iteration_protocol missing")
        return errors
    baseline = protocol.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("BASELINE_MISSING")
    else:
        required = ("policy_id", "scenario_id", "opponent_suite_id", "actionspace_id", "run_id", "options_hash", "event_stream_digest", "report_ref")
        for key in required:
            if key not in baseline:
                errors.append(f"BASELINE_{key}_MISSING")
            elif key != "opponent_suite_id" and baseline.get(key) in (None, ""):
                errors.append(f"BASELINE_{key}_EMPTY")
    evidence = protocol.get("evidence")
    if not isinstance(evidence, list) or len(evidence) < 3:
        errors.append("EVIDENCE_INCOMPLETE")
    else:
        for i, entry in enumerate(evidence[:3]):
            if not isinstance(entry, dict):
                errors.append(f"EVIDENCE_{i}_INVALID")
                continue
            for key in ("bucket_key", "metric", "n", "seed", "evidence_ref"):
                if entry.get(key) in (None, ""):
                    errors.append(f"EVIDENCE_{i}_{key}_MISSING")
    result = protocol.get("result")
    if not isinstance(result, dict):
        errors.append("RESULT_MISSING")
    else:
        if result.get("fix") in (None, ""):
            errors.append("RESULT_FIX_MISSING")
        if result.get("side_effect") in (None, ""):
            errors.append("RESULT_SIDE_EFFECT_MISSING")
    if errors and strict:
        raise ValueError(",".join(errors))
    return errors
