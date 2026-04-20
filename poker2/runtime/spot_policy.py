from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from poker2.protocol.spot_policy import validate_spot_policy
from poker2.runtime.hand_eval import board_texture, parse_card_token


@dataclass(frozen=True)
class SpotPolicyOverlay:
    matched_rule: dict[str, Any] | None
    defend_target: float | None
    call_pref: float | None
    raise_cap_max: float | None


def _clamp(value: float, *, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def spot_wet_score_from_board_cards(board_cards: Sequence[str] | None, *, street: str | None) -> int | None:
    if board_cards is None:
        return None
    parsed = [parse_card_token(str(card)) for card in board_cards]
    if any(card is None for card in parsed):
        return None
    if not parsed:
        return 0
    texture = board_texture(tuple(parsed))  # type: ignore[arg-type]
    score = 0
    if texture is not None:
        suit_tex, rank_tex = texture
        if suit_tex == "monotone":
            score += 2
        elif suit_tex == "two-tone":
            score += 1
        if rank_tex == "connected":
            score += 2
        elif rank_tex == "semi-connected":
            score += 1
        elif rank_tex == "paired":
            score += 1
    if street == "TURN":
        score = max(0, score - 1)
    elif street == "RIVER":
        score = max(0, score - 2)
    return score


def build_spot_context(
    *,
    street: str | None,
    facing_bet: bool,
    pos_key: str | None,
    players_alive: int | None,
    pot_chips: int,
    to_call_chips: int,
    actor_stack_chips: int | None,
    wet_score: int | None = None,
    board_cards: Sequence[str] | None = None,
) -> dict[str, Any]:
    price_ppm = None
    pot_unit = int(max(1, int(pot_chips) + int(to_call_chips)))
    if to_call_chips >= 0:
        price_ppm = int(round(_clamp(float(to_call_chips) / float(pot_unit), lo=0.0, hi=1.0) * 1_000_000))
    spr_milli = None
    if actor_stack_chips is not None and pot_chips > 0:
        spr_milli = int(round(max(0.0, float(actor_stack_chips) / float(pot_chips)) * 1000.0))
    wet_score_local = wet_score
    if wet_score_local is None:
        wet_score_local = spot_wet_score_from_board_cards(board_cards, street=street)
    return {
        "street": street,
        "facing_bet": bool(facing_bet),
        "pos_key": pos_key,
        "players_alive": int(players_alive) if isinstance(players_alive, int) else None,
        "price_ppm": price_ppm,
        "spr_milli": spr_milli,
        "wet_score": wet_score_local,
    }


def _matches_rule(rule: dict[str, Any], context: dict[str, Any]) -> bool:
    when = rule.get("when") or {}
    street = context.get("street")
    if street not in when.get("streets", []):
        return False
    if bool(context.get("facing_bet")) is not bool(when.get("requires_facing_bet")):
        return False
    pos_keys = when.get("pos_keys")
    if pos_keys is not None and context.get("pos_key") not in pos_keys:
        return False
    players_alive = context.get("players_alive")
    players_alive_min = when.get("players_alive_min")
    if players_alive_min is not None and (players_alive is None or int(players_alive) < int(players_alive_min)):
        return False
    players_alive_max = when.get("players_alive_max")
    if players_alive_max is not None and (players_alive is None or int(players_alive) > int(players_alive_max)):
        return False
    price_ppm = context.get("price_ppm")
    price_min_ppm = when.get("price_min_ppm")
    if price_min_ppm is not None and (price_ppm is None or int(price_ppm) < int(price_min_ppm)):
        return False
    price_max_ppm = when.get("price_max_ppm")
    if price_max_ppm is not None and (price_ppm is None or int(price_ppm) > int(price_max_ppm)):
        return False
    spr_milli = context.get("spr_milli")
    spr_min_milli = when.get("spr_min_milli")
    if spr_min_milli is not None and (spr_milli is None or int(spr_milli) < int(spr_min_milli)):
        return False
    spr_max_milli = when.get("spr_max_milli")
    if spr_max_milli is not None and (spr_milli is None or int(spr_milli) > int(spr_max_milli)):
        return False
    wet_score = context.get("wet_score")
    wet_min = when.get("wet_min")
    if wet_min is not None and (wet_score is None or int(wet_score) < int(wet_min)):
        return False
    wet_max = when.get("wet_max")
    if wet_max is not None and (wet_score is None or int(wet_score) > int(wet_max)):
        return False
    return True


def _rule_specificity(rule: dict[str, Any]) -> int:
    when = rule.get("when") or {}
    score = len(when.get("streets") or [])
    for key in (
        "pos_keys",
        "players_alive_min",
        "players_alive_max",
        "price_min_ppm",
        "price_max_ppm",
        "spr_min_milli",
        "spr_max_milli",
        "wet_min",
        "wet_max",
    ):
        if when.get(key) is not None:
            score += 1
    return score


def match_spot_policy(spec: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    validate_spot_policy(spec, strict_mode=True)
    matches: list[tuple[int, int, dict[str, Any]]] = []
    for idx, rule in enumerate(spec.get("spots") or []):
        if not isinstance(rule, dict) or not bool(rule.get("enabled")):
            continue
        if _matches_rule(rule, context):
            matches.append((_rule_specificity(rule), -idx, rule))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][2]


def apply_spot_policy_overlay(
    *,
    spec: dict[str, Any],
    context: dict[str, Any],
    defend_target: float | None,
    call_pref: float | None,
    raise_cap_max: float | None,
) -> SpotPolicyOverlay:
    rule = match_spot_policy(spec, context)
    if rule is None:
        return SpotPolicyOverlay(matched_rule=None, defend_target=defend_target, call_pref=call_pref, raise_cap_max=raise_cap_max)

    adjustments = rule.get("adjustments") or {}
    defend_target_local = defend_target
    if defend_target_local is not None:
        scale_bp = adjustments.get("defend_target_scale_bp")
        if isinstance(scale_bp, int):
            defend_target_local = float(defend_target_local) * (float(scale_bp) / 10000.0)
        floor_bp = adjustments.get("defend_target_floor_bp")
        if isinstance(floor_bp, int):
            defend_target_local = max(float(defend_target_local), float(floor_bp) / 10000.0)
        max_bp = adjustments.get("defend_target_max_bp")
        if isinstance(max_bp, int):
            defend_target_local = min(float(defend_target_local), float(max_bp) / 10000.0)
        defend_target_local = _clamp(float(defend_target_local), lo=0.0, hi=1.0)

    call_pref_local = call_pref
    call_pref_floor_bp = adjustments.get("call_pref_floor_bp")
    if isinstance(call_pref_floor_bp, int):
        call_floor = _clamp(float(call_pref_floor_bp) / 10000.0, lo=0.0, hi=1.0)
        call_pref_local = call_floor if call_pref_local is None else max(float(call_pref_local), call_floor)

    raise_cap_local = raise_cap_max
    raise_cap_max_bp = adjustments.get("raise_cap_max_bp")
    if isinstance(raise_cap_max_bp, int):
        raise_cap = _clamp(float(raise_cap_max_bp) / 10000.0, lo=0.0, hi=1.0)
        raise_cap_local = raise_cap if raise_cap_local is None else min(float(raise_cap_local), raise_cap)

    matched_rule = {
        "spot_id": rule.get("spot_id"),
        "trace_tag": adjustments.get("trace_tag"),
    }
    return SpotPolicyOverlay(
        matched_rule=matched_rule,
        defend_target=defend_target_local,
        call_pref=call_pref_local,
        raise_cap_max=raise_cap_local,
    )
