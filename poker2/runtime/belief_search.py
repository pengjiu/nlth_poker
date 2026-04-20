from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import itertools
import math
import random
from typing import Any, Iterable, Sequence

from poker2.runtime.ev_core import estimate_rake
from poker2.runtime.hand_eval import best_hand_rank, board_texture


Card = tuple[int, str]
_FULL_DECK: tuple[Card, ...] = tuple((r, s) for r in range(2, 15) for s in ("c", "d", "h", "s"))
_STREET_TO_BOARD_LEN = {"FLOP": 3, "TURN": 4, "RIVER": 5}


@dataclass(frozen=True)
class BeliefSearchConfig:
    enabled: bool = True
    flop_enable: bool = True
    turn_enable: bool = True
    river_enable: bool = True
    hu_only: bool = True
    world_samples: int = 72
    max_range_combos: int = 160
    max_raise_actions: int = 3
    min_pot_bb: float = 6.0
    risk_aversion: float = 0.18
    solver_blend: float = 0.20
    future_aggression_bonus: float = 0.05
    future_passive_penalty: float = 0.08

    @classmethod
    def from_mapping(cls, obj: dict[str, Any] | None) -> "BeliefSearchConfig":
        if not isinstance(obj, dict):
            return cls()

        def _b(key: str, default: bool) -> bool:
            val = obj.get(key, default)
            return bool(val)

        def _i(key: str, default: int, lo: int, hi: int) -> int:
            try:
                val = int(obj.get(key, default))
            except Exception:
                val = default
            return max(lo, min(hi, val))

        def _f(key: str, default: float, lo: float, hi: float) -> float:
            try:
                val = float(obj.get(key, default))
            except Exception:
                val = default
            return max(lo, min(hi, val))

        return cls(
            enabled=_b("enabled", True),
            flop_enable=_b("flop_enable", True),
            turn_enable=_b("turn_enable", True),
            river_enable=_b("river_enable", True),
            hu_only=_b("hu_only", True),
            world_samples=_i("world_samples", 72, 16, 384),
            max_range_combos=_i("max_range_combos", 160, 24, 512),
            max_raise_actions=_i("max_raise_actions", 3, 1, 5),
            min_pot_bb=_f("min_pot_bb", 6.0, 0.0, 100.0),
            risk_aversion=_f("risk_aversion", 0.18, 0.0, 1.0),
            solver_blend=_f("solver_blend", 0.20, 0.0, 1.0),
            future_aggression_bonus=_f("future_aggression_bonus", 0.05, 0.0, 0.30),
            future_passive_penalty=_f("future_passive_penalty", 0.08, 0.0, 0.40),
        )


@dataclass(frozen=True)
class BeliefSearchResult:
    action: dict[str, Any]
    trace: dict[str, Any]


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _ppm(v: float | None, *, limit: float = 5.0) -> int | None:
    if v is None:
        return None
    try:
        value = float(v)
    except Exception:
        return None
    if not math.isfinite(value):
        return None
    value = _clip(value, -limit, limit)
    return int(round(value * 1_000_000))


def _card_sort_key(card: Card) -> tuple[int, str]:
    return (int(card[0]), str(card[1]))


def _used_key(hero_hole: Sequence[Card], board: Sequence[Card]) -> tuple[Card, ...]:
    return tuple(sorted(tuple(hero_hole) + tuple(board), key=_card_sort_key))


@lru_cache(maxsize=4096)
def _valid_opponent_combos(used: tuple[Card, ...]) -> tuple[tuple[Card, Card], ...]:
    used_set = set(used)
    deck = [c for c in _FULL_DECK if c not in used_set]
    return tuple((a, b) for a, b in itertools.combinations(deck, 2))


@lru_cache(maxsize=4096)
def _remaining_cards(used: tuple[Card, ...]) -> tuple[Card, ...]:
    used_set = set(used)
    return tuple(c for c in _FULL_DECK if c not in used_set)


def _hand_class_strength(hole: Sequence[Card]) -> float:
    a, b = hole
    r1, r2 = sorted((int(a[0]), int(b[0])), reverse=True)
    suited = a[1] == b[1]
    gap = r1 - r2
    broadways = int(r1 >= 10) + int(r2 >= 10)
    ace_bonus = 0.08 if (r1 == 14 or r2 == 14) else 0.0
    if r1 == r2:
        return 0.48 + 0.05 * (r1 - 2)
    score = 0.16 + 0.018 * r1 + 0.012 * r2
    if suited:
        score += 0.07
    if gap <= 1:
        score += 0.06
    elif gap == 2:
        score += 0.035
    elif gap == 3:
        score += 0.015
    score += 0.02 * broadways + ace_bonus
    if suited and r1 >= 10 and r2 >= 9:
        score += 0.04
    if suited and r1 == 14:
        score += 0.02
    return score


def _best_rank_class(cards: Sequence[Card]) -> int:
    rank = best_hand_rank(cards)
    if not rank:
        return 0
    try:
        return int(rank[0])
    except Exception:
        return 0


def _pair_context(hole: Sequence[Card], board: Sequence[Card], hand_rank: tuple) -> dict[str, float]:
    if not board or not hand_rank:
        return {"top_pair": 0.0, "overpair": 0.0, "pair_score": 0.0}
    board_ranks = sorted((int(r) for r, _ in board), reverse=True)
    uniq_board = sorted(set(board_ranks), reverse=True)
    top = uniq_board[0]
    second = uniq_board[1] if len(uniq_board) >= 2 else uniq_board[0]
    pair_rank = int(hand_rank[1]) if len(hand_rank) >= 2 else 0
    r1, r2 = sorted((int(hole[0][0]), int(hole[1][0])), reverse=True)
    pocket = r1 == r2
    overpair = 1.0 if pocket and r1 > top else 0.0
    top_pair = 1.0 if pair_rank == top else 0.0
    if overpair > 0:
        pair_score = 0.74 + 0.015 * max(0, r1 - top)
    elif top_pair > 0:
        kicker = max(r1, r2)
        pair_score = 0.59 + 0.02 * max(0, kicker - 10)
    elif pair_rank >= second:
        pair_score = 0.48
    elif pair_rank > 0:
        pair_score = 0.34
    else:
        pair_score = 0.0
    return {"top_pair": top_pair, "overpair": overpair, "pair_score": pair_score}


def _flush_draw_strength(hole: Sequence[Card], board: Sequence[Card], class_rank: int) -> float:
    if len(board) >= 5 or class_rank >= 5:
        return 0.0
    suit_counts: dict[str, int] = {}
    for _r, s in tuple(hole) + tuple(board):
        suit_counts[s] = suit_counts.get(s, 0) + 1
    max_suit = max(suit_counts.values(), default=0)
    if max_suit >= 4:
        return 0.62
    if max_suit == 3 and len(board) == 3 and hole[0][1] == hole[1][1]:
        return 0.24
    return 0.0


def _straight_out_ranks(cards: Sequence[Card]) -> int:
    current_class = _best_rank_class(cards)
    if current_class >= 4:
        return 0
    outs = 0
    for r in range(2, 15):
        dummy = (r, "z")
        if _best_rank_class(tuple(cards) + (dummy,)) >= 4:
            outs += 1
    return outs


def _straight_draw_strength(hole: Sequence[Card], board: Sequence[Card], class_rank: int) -> float:
    if len(board) >= 5 or class_rank >= 4:
        return 0.0
    outs = _straight_out_ranks(tuple(hole) + tuple(board))
    if outs >= 2:
        return 0.52
    if outs == 1:
        return 0.28
    return 0.0


def _made_hand_score(hole: Sequence[Card], board: Sequence[Card]) -> tuple[float, dict[str, float]]:
    rank = best_hand_rank(tuple(hole) + tuple(board))
    class_rank = int(rank[0]) if rank else 0
    pair_ctx = _pair_context(hole, board, rank)
    if class_rank >= 8:
        score = 1.08
    elif class_rank == 7:
        score = 1.05
    elif class_rank == 6:
        score = 1.00
    elif class_rank == 5:
        score = 0.95
    elif class_rank == 4:
        score = 0.90
    elif class_rank == 3:
        score = 0.84
    elif class_rank == 2:
        score = 0.76
    elif class_rank == 1:
        score = pair_ctx["pair_score"]
    else:
        high_cards = sorted((int(r) for r, _ in hole), reverse=True)
        overcards = 0
        if board:
            top = max(int(r) for r, _ in board)
            overcards = sum(1 for r in high_cards if r > top)
        score = 0.10 + 0.06 * overcards + 0.01 * max(high_cards)
    feats = {
        "class_rank": float(class_rank),
        "made_score": score,
        **pair_ctx,
    }
    return score, feats


def _bluff_component(hole: Sequence[Card], board: Sequence[Card], class_rank: int, draw_score: float) -> float:
    if len(board) < 5:
        return 0.0
    if class_rank >= 1:
        return 0.0
    suit_counts: dict[str, int] = {}
    for _r, s in tuple(hole) + tuple(board):
        suit_counts[s] = suit_counts.get(s, 0) + 1
    flush_miss = 1.0 if max(suit_counts.values(), default=0) == 4 else 0.0
    straight_potential = 1.0 if _straight_out_ranks(tuple(hole) + tuple(board)) >= 1 else 0.0
    broadway_high = max(int(hole[0][0]), int(hole[1][0])) >= 12
    return 0.34 * flush_miss + 0.22 * straight_potential + (0.10 if broadway_high else 0.0) + 0.10 * draw_score


def _combo_features(hole: Sequence[Card], board: Sequence[Card]) -> dict[str, float]:
    made_score, feats = _made_hand_score(hole, board)
    class_rank = int(feats["class_rank"])
    flush_draw = _flush_draw_strength(hole, board, class_rank)
    straight_draw = _straight_draw_strength(hole, board, class_rank)
    draw_score = max(flush_draw, straight_draw, 0.6 * flush_draw + 0.5 * straight_draw)
    showdown = made_score if class_rank >= 1 else 0.12 + 0.04 * max(int(hole[0][0]), int(hole[1][0]))
    bluff_score = _bluff_component(hole, board, class_rank, draw_score)
    feats.update(
        {
            "draw_score": draw_score,
            "showdown_score": showdown,
            "bluff_score": bluff_score,
        }
    )
    return feats


def _board_wetness(board: Sequence[Card]) -> float:
    tex = board_texture(board)
    if tex is None:
        return 0.0
    suit_tex, rank_tex = tex
    wet = 0.0
    if suit_tex == "monotone":
        wet += 0.35
    elif suit_tex == "two-tone":
        wet += 0.18
    if rank_tex == "connected":
        wet += 0.30
    elif rank_tex == "semi-connected":
        wet += 0.16
    if rank_tex == "paired":
        wet += 0.08
    return wet


def _line_weight(
    *,
    feats: dict[str, float],
    street: str,
    to_call: int,
    pot_chips: int,
    board: Sequence[Card],
) -> float:
    made = float(feats["made_score"])
    draw = float(feats["draw_score"])
    showdown = float(feats["showdown_score"])
    bluff = float(feats["bluff_score"])
    class_rank = int(feats["class_rank"])
    wet = _board_wetness(board)
    price = float(to_call) / max(1.0, float(pot_chips + to_call)) if to_call > 0 else 0.0
    size_ratio = float(to_call) / max(1.0, float(pot_chips)) if pot_chips > 0 else 0.0
    if to_call > 0:
        if street == "RIVER":
            polar = 0.95 + 0.35 * min(1.5, size_ratio)
            strong = 0.16 + 1.55 * (made ** 1.35)
            medium = 0.20 * showdown * (1.0 - 0.85 * min(1.0, size_ratio))
            bluff_part = (0.05 + 0.35 * min(1.0, size_ratio)) * bluff
            score = strong * polar + medium + bluff_part
            if class_rank <= 1 and made < 0.60:
                score *= max(0.12, 1.0 - 1.25 * min(1.0, size_ratio))
            return max(1e-6, score)
        strong = 0.16 + 1.30 * (made ** 1.25)
        draw_part = (0.12 + 0.55 * wet + 0.30 * min(1.0, size_ratio)) * draw
        medium = 0.16 * showdown
        bluff_part = (0.03 + 0.10 * wet) * bluff
        score = strong + draw_part + medium + bluff_part
        if price > 0.38 and class_rank <= 1 and draw < 0.30:
            score *= 0.75
        return max(1e-6, score)

    # Checked to us -> capped/wider range.
    if street == "RIVER":
        score = 0.10 + 0.60 * showdown + 0.10 * draw
        if class_rank >= 2:
            score += 0.10
        if class_rank >= 5:
            score *= 0.85  # some slowplays remain but not dominant
        return max(1e-6, score)

    score = 0.12 + 0.58 * showdown + 0.42 * draw + 0.08 * bluff
    if class_rank >= 5:
        score *= 0.92
    return max(1e-6, score)


def _weighted_sample_without_replacement(
    items: Sequence[tuple[Card, Card]],
    weights: Sequence[float],
    k: int,
    rng: random.Random,
) -> list[tuple[Card, Card]]:
    if not items:
        return []
    if k >= len(items):
        return list(items)
    # Efraimidis-Spirakis weighted sampling without replacement.
    keys: list[tuple[float, int]] = []
    for idx, w in enumerate(weights):
        wv = max(1e-12, float(w))
        u = max(1e-12, rng.random())
        key = u ** (1.0 / wv)
        keys.append((key, idx))
    keys.sort(reverse=True)
    return [items[idx] for _key, idx in keys[:k]]


def _hero_share(hero_hole: Sequence[Card], opp_hole: Sequence[Card], board: Sequence[Card]) -> float:
    hero_rank = best_hand_rank(tuple(hero_hole) + tuple(board))
    opp_rank = best_hand_rank(tuple(opp_hole) + tuple(board))
    if hero_rank > opp_rank:
        return 1.0
    if hero_rank == opp_rank:
        return 0.5
    return 0.0


def _future_realization(
    *,
    street: str,
    pos_key: str | None,
    passive: bool,
    aggressive: bool,
    feats: dict[str, float],
    to_call: int,
    pot_chips: int,
    cfg: BeliefSearchConfig,
) -> float:
    if street == "RIVER":
        return 1.0
    base = 0.82 if street == "TURN" else 0.74
    if pos_key in ("BU", "OTHERS"):
        base += 0.04
    elif pos_key in ("SB", "BB"):
        base -= 0.03
    if aggressive:
        base += cfg.future_aggression_bonus
    if passive:
        base -= cfg.future_passive_penalty
    base += 0.08 * float(feats["made_score"])
    base += 0.06 * float(feats["draw_score"])
    price = float(to_call) / max(1.0, float(pot_chips + to_call)) if to_call > 0 else 0.0
    base -= 0.08 * price
    return _clip(base, 0.55, 1.03)


def _response_continue_prob(
    *,
    opp_feats: dict[str, float],
    street: str,
    size_ratio: float,
    price_to_continue: float,
    facing_raise: bool,
) -> float:
    made = float(opp_feats["made_score"])
    draw = float(opp_feats["draw_score"])
    showdown = float(opp_feats["showdown_score"])
    bluff = float(opp_feats["bluff_score"])
    class_rank = int(opp_feats["class_rank"])

    if street == "RIVER":
        strength = max(made, 0.75 * showdown + 0.20 * made)
        if class_rank <= 1:
            strength -= 0.10 * min(1.5, size_ratio)
        threshold = 0.22 + 0.70 * price_to_continue + 0.12 * min(1.5, size_ratio)
        if facing_raise:
            threshold += 0.08
        p = _sigmoid(6.0 * (strength - threshold))
        if class_rank >= 5:
            p = max(p, 0.97)
        elif class_rank >= 3:
            p = max(p, 0.88)
        elif class_rank == 2:
            p = max(p, 0.72 - 0.08 * min(1.0, size_ratio))
        elif class_rank == 1 and made >= 0.60:
            p = max(p, 0.48 - 0.12 * min(1.0, size_ratio))
        if bluff > 0.25 and class_rank == 0:
            p *= 0.10
        return _clip(p, 0.01, 0.995)

    strength = max(made, 0.92 * made + 0.58 * draw + 0.10 * showdown)
    threshold = 0.18 + 0.54 * price_to_continue + 0.12 * min(1.5, size_ratio)
    if facing_raise:
        threshold += 0.05
    p = _sigmoid(5.6 * (strength - threshold))
    if class_rank >= 5:
        p = max(p, 0.96)
    elif class_rank >= 3:
        p = max(p, 0.82)
    elif draw >= 0.55:
        p = max(p, 0.52)
    elif draw >= 0.28:
        p = max(p, 0.34)
    if class_rank == 0 and bluff > 0.25:
        p *= 0.25
    return _clip(p, 0.01, 0.99)


def _sample_worlds(
    *,
    hero_hole: Sequence[Card],
    board: Sequence[Card],
    street: str,
    weighted_combos: Sequence[tuple[tuple[Card, Card], float]],
    samples: int,
    rng: random.Random,
) -> list[tuple[tuple[Card, Card], tuple[Card, ...]]]:
    if not weighted_combos or samples <= 0:
        return []
    combos, weights = zip(*weighted_combos)
    worlds: list[tuple[tuple[Card, Card], tuple[Card, ...]]] = []
    board_need = max(0, 5 - len(board))
    used_base = set(hero_hole) | set(board)
    for _ in range(samples):
        # Weighted with replacement gives better coverage at low budgets.
        combo = rng.choices(combos, weights=weights, k=1)[0]
        used = used_base | set(combo)
        deck = [c for c in _FULL_DECK if c not in used]
        fill: tuple[Card, ...]
        if board_need > 0:
            fill = tuple(rng.sample(deck, board_need))
        else:
            fill = ()
        worlds.append((combo, fill))
    return worlds


def _action_target(action: dict[str, Any], actor_commit: int) -> int:
    try:
        return int(action.get("target_total_commit_chips", actor_commit))
    except Exception:
        return actor_commit


def _action_label(action: dict[str, Any], actor_commit: int) -> str:
    kind = str(action.get("kind"))
    return f"{kind}:{_action_target(action, actor_commit)}"


def _representative_raise_indices(length: int, count: int) -> list[int]:
    if length <= 0:
        return []
    if count <= 1:
        return [length // 2]
    if count >= length:
        return list(range(length))
    positions = {0, length - 1}
    if count > 2:
        for slot in range(1, count - 1):
            idx = int(round(slot * (length - 1) / float(count - 1)))
            positions.add(max(0, min(length - 1, idx)))
    return sorted(positions)


def _select_candidate_actions(
    *,
    legal_actions: Sequence[dict[str, Any]],
    actor_commit: int,
    call_target: int,
    max_raise_actions: int,
    solver_hint_target: int | None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    def _add(action: dict[str, Any] | None) -> None:
        if action is None:
            return
        key = (str(action.get("kind")), _action_target(action, actor_commit))
        if key in seen:
            return
        selected.append(action)
        seen.add(key)

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for act in legal_actions:
        by_kind.setdefault(str(act.get("kind")), []).append(act)

    for kind in ("FOLD", "CHECK", "CALL"):
        acts = by_kind.get(kind) or []
        if not acts:
            continue
        if kind == "CALL":
            _add(min(acts, key=lambda a: abs(_action_target(a, actor_commit) - call_target)))
        else:
            _add(min(acts, key=lambda a: _action_target(a, actor_commit)))

    raises = [a for a in legal_actions if str(a.get("kind")) in ("RAISE", "BET", "ALLIN")]
    if not raises:
        return selected

    raises = sorted(raises, key=lambda a: (_action_target(a, actor_commit), str(a.get("kind"))))

    def _nearest(target: int) -> dict[str, Any] | None:
        if not raises:
            return None
        return min(raises, key=lambda a: (abs(_action_target(a, actor_commit) - target), _action_target(a, actor_commit)))

    if solver_hint_target is not None:
        _add(_nearest(int(solver_hint_target)))

    for idx in _representative_raise_indices(len(raises), max_raise_actions):
        _add(raises[idx])
    return selected


def choose_action_with_belief_search(
    *,
    legal_actions: Sequence[dict[str, Any]],
    hero_hole: Sequence[Card],
    board: Sequence[Card],
    pot_chips: int,
    actor_commit: int,
    to_call: int,
    stack_chips: int,
    players_alive: int,
    street: str | None,
    state_hash: str | None,
    bb: int | None = None,
    pos_key: str | None = None,
    prior_street_aggressor: bool | None = None,
    uncertainty: float | None = None,
    rake_rate: float = 0.0,
    rake_cap: int | None = None,
    no_flop_no_drop: bool = False,
    solver_call_ev: float | None = None,
    solver_raise_ev: float | None = None,
    solver_hint_kind: str | None = None,
    solver_hint_target: int | None = None,
    config: BeliefSearchConfig | dict[str, Any] | None = None,
) -> BeliefSearchResult | None:
    cfg = config if isinstance(config, BeliefSearchConfig) else BeliefSearchConfig.from_mapping(config)
    if not cfg.enabled:
        return None
    if street not in ("FLOP", "TURN", "RIVER"):
        return None
    if cfg.hu_only and players_alive != 2:
        return None
    if street == "FLOP" and not cfg.flop_enable:
        return None
    if street == "TURN" and not cfg.turn_enable:
        return None
    if street == "RIVER" and not cfg.river_enable:
        return None
    if len(hero_hole) != 2:
        return None
    if len(board) != _STREET_TO_BOARD_LEN.get(street, len(board)):
        # Be tolerant to partial snapshots, but only search with consistent public state.
        return None
    if len(legal_actions) < 2:
        return None
    bb_unit = max(1, int(bb or 1))
    if float(pot_chips) / float(bb_unit) < cfg.min_pot_bb and to_call <= 0 and street == "FLOP":
        return None

    call_target = actor_commit + max(0, int(to_call))
    candidates = _select_candidate_actions(
        legal_actions=legal_actions,
        actor_commit=actor_commit,
        call_target=call_target,
        max_raise_actions=cfg.max_raise_actions,
        solver_hint_target=solver_hint_target,
    )
    if len(candidates) < 2:
        return None

    used = _used_key(hero_hole, board)
    combos = list(_valid_opponent_combos(used))
    if not combos:
        return None

    weights: list[float] = []
    combo_feats: dict[tuple[Card, Card], dict[str, float]] = {}
    for combo in combos:
        feats = _combo_features(combo, board)
        combo_feats[combo] = feats
        prior = _hand_class_strength(combo)
        line = _line_weight(feats=feats, street=street, to_call=to_call, pot_chips=pot_chips, board=board)
        weights.append(max(1e-9, prior * line))

    seed_material = f"belief:{state_hash or ''}:{street}:{pot_chips}:{to_call}:{actor_commit}:{stack_chips}:{players_alive}"
    seed = 0
    for ch in seed_material.encode("utf-8", errors="ignore"):
        seed = ((seed * 131) + ch) & 0xFFFFFFFF
    rng = random.Random(seed)

    if len(combos) > cfg.max_range_combos:
        sample_combos = _weighted_sample_without_replacement(combos, weights, cfg.max_range_combos, rng)
        sample_set = {id_: True for id_ in []}
        keep = set(sample_combos)
        combos = [c for c in combos if c in keep]
        weights = [w for c, w in zip(_valid_opponent_combos(used), weights) if c in keep]

    total_w = sum(weights)
    if total_w <= 0:
        return None
    weighted_combos = list(zip(combos, [w / total_w for w in weights]))
    worlds = _sample_worlds(
        hero_hole=hero_hole,
        board=board,
        street=street,
        weighted_combos=weighted_combos,
        samples=cfg.world_samples,
        rng=rng,
    )
    if not worlds:
        return None

    hero_feats = _combo_features(hero_hole, board)
    unc = _clip(float(uncertainty or 0.0), 0.0, 1.0)
    risk_lambda = cfg.risk_aversion * (1.0 + 1.4 * unc)
    solver_blend = cfg.solver_blend * (0.35 + 0.65 * (1.0 - unc))

    scores: dict[str, tuple[float, float, float, float]] = {}
    action_objs: dict[str, dict[str, Any]] = {}

    base_rake = estimate_rake(
        pot_after=float(max(0, pot_chips)),
        street=street,
        rake_rate=rake_rate,
        rake_cap=rake_cap,
        no_flop_no_drop=no_flop_no_drop,
    )

    for action in candidates:
        kind = str(action.get("kind"))
        target = _action_target(action, actor_commit)
        label = _action_label(action, actor_commit)
        action_objs[label] = action
        values: list[float] = []
        fold_rate = 0.0

        if kind == "FOLD":
            values = [0.0 for _ in worlds]
            scores[label] = (0.0, 0.0, 0.0, 0.0)
            continue

        for combo, fill in worlds:
            full_board = tuple(board) + tuple(fill)
            if kind in ("CALL", "CHECK"):
                pot_after = pot_chips + (to_call if kind == "CALL" else 0)
                rake = estimate_rake(
                    pot_after=float(pot_after),
                    street=street,
                    rake_rate=rake_rate,
                    rake_cap=rake_cap,
                    no_flop_no_drop=no_flop_no_drop,
                )
                share = _hero_share(hero_hole, combo, full_board)
                if kind == "CALL":
                    realize = _future_realization(
                        street=street,
                        pos_key=pos_key,
                        passive=True,
                        aggressive=False,
                        feats=hero_feats,
                        to_call=to_call,
                        pot_chips=pot_chips,
                        cfg=cfg,
                    )
                    value = share * max(0.0, float(pot_after) - rake) * realize - float(to_call)
                else:
                    realize = _future_realization(
                        street=street,
                        pos_key=pos_key,
                        passive=True,
                        aggressive=False,
                        feats=hero_feats,
                        to_call=0,
                        pot_chips=pot_chips,
                        cfg=cfg,
                    )
                    value = share * max(0.0, float(pot_after) - rake) * realize
                values.append(value)
                continue

            # Aggressive action: opponent can fold or continue.
            hero_extra = max(0, target - actor_commit)
            if to_call > 0:
                opp_extra = max(0, target - call_target)
                facing_raise = True
            else:
                opp_extra = hero_extra
                facing_raise = False
            price_to_continue = float(opp_extra) / max(1.0, float(pot_chips + hero_extra + opp_extra)) if opp_extra > 0 else 0.0
            size_ratio = float(hero_extra) / max(1.0, float(pot_chips)) if pot_chips > 0 else 0.0
            p_continue = _response_continue_prob(
                opp_feats=combo_feats[combo],
                street=street,
                size_ratio=size_ratio,
                price_to_continue=price_to_continue,
                facing_raise=facing_raise,
            )
            fold_rate += (1.0 - p_continue)
            rake_fold = estimate_rake(
                pot_after=float(max(0, pot_chips)),
                street=street,
                rake_rate=rake_rate,
                rake_cap=rake_cap,
                no_flop_no_drop=no_flop_no_drop,
            )
            ev_fold = max(0.0, float(pot_chips) - float(rake_fold))
            pot_after_called = pot_chips + hero_extra + opp_extra
            rake_called = estimate_rake(
                pot_after=float(max(0, pot_after_called)),
                street=street,
                rake_rate=rake_rate,
                rake_cap=rake_cap,
                no_flop_no_drop=no_flop_no_drop,
            )
            share = _hero_share(hero_hole, combo, full_board)
            realize = _future_realization(
                street=street,
                pos_key=pos_key,
                passive=False,
                aggressive=True,
                feats=hero_feats,
                to_call=to_call,
                pot_chips=pot_chips,
                cfg=cfg,
            )
            ev_called = share * max(0.0, float(pot_after_called) - rake_called) * realize - float(hero_extra)
            value = (1.0 - p_continue) * ev_fold + p_continue * ev_called
            values.append(value)

        if not values:
            continue
        mean = sum(values) / float(len(values))
        var = max(0.0, sum(v * v for v in values) / float(len(values)) - mean * mean)
        std = math.sqrt(var)
        if kind == "CALL" and solver_call_ev is not None:
            mean = (1.0 - solver_blend) * mean + solver_blend * float(solver_call_ev)
        elif kind in ("RAISE", "BET", "ALLIN") and solver_raise_ev is not None:
            mean = (1.0 - solver_blend) * mean + solver_blend * float(solver_raise_ev)
            if solver_hint_kind in ("RAISE", "BET") and solver_hint_target is not None:
                tgt_gap = abs(float(target) - float(solver_hint_target)) / max(1.0, float(pot_chips))
                mean += max(0.0, 0.02 - 0.01 * tgt_gap) * float(pot_chips)
        score = mean - risk_lambda * std
        if kind in ("RAISE", "BET", "ALLIN") and street != "RIVER" and to_call > 0 and hero_feats["made_score"] < 0.48 and hero_feats["draw_score"] < 0.32:
            score -= 0.03 * float(pot_chips)
        scores[label] = (score, mean, std, fold_rate / float(len(values)))

    if len(scores) < 2:
        return None

    ordered = sorted(scores.items(), key=lambda item: (item[1][0], item[1][1]), reverse=True)
    best_label, best_tuple = ordered[0]
    second_tuple = ordered[1][1] if len(ordered) > 1 else best_tuple
    best_action = action_objs[best_label]

    # Conservative tie-breakers: avoid thin river raises / flop spew.
    best_kind = str(best_action.get("kind"))
    best_score, best_mean, best_std, _best_fold_rate = best_tuple
    second_score = float(second_tuple[0])
    margin = best_score - second_score
    if best_kind in ("RAISE", "BET", "ALLIN"):
        if street == "RIVER" and margin < 0.015 * float(max(1, pot_chips)):
            call_or_check = next((a for a in candidates if str(a.get("kind")) in ("CALL", "CHECK")), None)
            if call_or_check is not None:
                best_action = call_or_check
                best_label = _action_label(call_or_check, actor_commit)
                best_tuple = scores[best_label]
                best_kind = str(best_action.get("kind"))
        elif street == "FLOP" and hero_feats["made_score"] < 0.42 and hero_feats["draw_score"] < 0.40 and margin < 0.02 * float(max(1, pot_chips)):
            call_or_check = next((a for a in candidates if str(a.get("kind")) in ("CALL", "CHECK")), None)
            if call_or_check is not None:
                best_action = call_or_check
                best_label = _action_label(call_or_check, actor_commit)
                best_tuple = scores[best_label]
                best_kind = str(best_action.get("kind"))

    score_rows = []
    for label, (score, mean, std, fold_rate) in ordered:
        act = action_objs[label]
        score_rows.append(
            {
                "kind": str(act.get("kind")),
                "target_total_commit_chips": _action_target(act, actor_commit),
                "score_ppm": _ppm(score / max(1.0, float(pot_chips)), limit=5.0),
                "mean_ev_ppm": _ppm(mean / max(1.0, float(pot_chips)), limit=5.0),
                "std_ev_ppm": _ppm(std / max(1.0, float(pot_chips)), limit=5.0),
                "fold_rate_ppm": _ppm(fold_rate, limit=1.0),
            }
        )

    gap = float(best_tuple[0]) - float(second_tuple[0])
    gap_scale = max(1.0, float(best_tuple[2]) + float(second_tuple[2]) + 0.02 * float(pot_chips))
    confidence = _sigmoid(3.5 * gap / gap_scale)
    confidence *= 0.55 + 0.45 * (1.0 - unc)

    trace = {
        "belief_search_active": True,
        "belief_search_street": street,
        "belief_search_samples": int(len(worlds)),
        "belief_search_range_combos": int(len(combos)),
        "belief_search_confidence_ppm": _ppm(confidence, limit=1.0),
        "belief_search_uncertainty_ppm": _ppm(unc, limit=1.0),
        "belief_search_best_kind": best_kind,
        "belief_search_best_target_total_commit_chips": _action_target(best_action, actor_commit),
        "belief_search_gap_ppm": _ppm(gap / max(1.0, float(pot_chips)), limit=5.0),
        "belief_search_rows": score_rows,
        "belief_search_solver_blend_ppm": _ppm(solver_blend, limit=1.0),
        "belief_search_hero_made_ppm": _ppm(float(hero_feats["made_score"]), limit=2.0),
        "belief_search_hero_draw_ppm": _ppm(float(hero_feats["draw_score"]), limit=2.0),
    }
    return BeliefSearchResult(action=best_action, trace=trace)
