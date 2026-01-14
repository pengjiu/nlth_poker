from __future__ import annotations

import itertools
import random
from collections import Counter
from typing import Sequence


_RANK_MAP = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "10": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}

_FULL_DECK = [(r, s) for r in range(2, 15) for s in ("c", "d", "h", "s")]


def parse_card_token(card_text: str | None) -> tuple[int, str] | None:
    if not isinstance(card_text, str) or card_text == "":
        return None
    token = card_text.strip()
    if "(" in token and ")" in token:
        token = token.split("(", 1)[-1].split(")", 1)[0].strip()
    if len(token) < 2:
        return None
    rank_part = token[:-1].upper()
    suit = token[-1].lower()
    rank = _RANK_MAP.get(rank_part)
    if rank is None:
        return None
    return (rank, suit)


def board_texture(cards: Sequence[tuple[int, str]]) -> tuple[str, str] | None:
    if len(cards) < 3:
        return None
    suits = [s for _, s in cards]
    uniq_suits = len(set(suits))
    if uniq_suits == 1:
        suit_texture = "monotone"
    elif uniq_suits == 2:
        suit_texture = "two-tone"
    else:
        suit_texture = "rainbow"

    ranks = sorted((r for r, _ in cards))
    if len(set(ranks)) < len(ranks):
        rank_texture = "paired"
    else:
        gaps = [ranks[i + 1] - ranks[i] for i in range(len(ranks) - 1)]
        max_gap = max(gaps) if gaps else 0
        if max_gap <= 2:
            rank_texture = "connected"
        elif max_gap <= 4:
            rank_texture = "semi-connected"
        else:
            rank_texture = "disconnected"
    return (suit_texture, rank_texture)


def _is_straight(ranks: list[int]) -> tuple[bool, int]:
    unique = sorted(set(ranks), reverse=True)
    if len(unique) != 5:
        return (False, 0)
    high = unique[0]
    if high - unique[-1] == 4:
        return (True, high)
    if unique == [14, 5, 4, 3, 2]:
        return (True, 5)
    return (False, 0)


def _rank_five(cards: Sequence[tuple[int, str]]) -> tuple:
    ranks = sorted((r for r, _ in cards), reverse=True)
    suits = [s for _, s in cards]
    counts = Counter(ranks)
    counts_sorted = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    is_flush = len(set(suits)) == 1
    is_straight, straight_high = _is_straight(ranks)

    if is_straight and is_flush:
        return (8, straight_high)
    if counts_sorted[0][1] == 4:
        quad = counts_sorted[0][0]
        kicker = max(r for r in ranks if r != quad)
        return (7, quad, kicker)
    if counts_sorted[0][1] == 3 and counts_sorted[1][1] == 2:
        return (6, counts_sorted[0][0], counts_sorted[1][0])
    if is_flush:
        return (5, *ranks)
    if is_straight:
        return (4, straight_high)
    if counts_sorted[0][1] == 3:
        trips = counts_sorted[0][0]
        kickers = [r for r in ranks if r != trips]
        return (3, trips, *kickers)
    if counts_sorted[0][1] == 2 and counts_sorted[1][1] == 2:
        high_pair = max(counts_sorted[0][0], counts_sorted[1][0])
        low_pair = min(counts_sorted[0][0], counts_sorted[1][0])
        kicker = max(r for r in ranks if r not in (high_pair, low_pair))
        return (2, high_pair, low_pair, kicker)
    if counts_sorted[0][1] == 2:
        pair = counts_sorted[0][0]
        kickers = [r for r in ranks if r != pair]
        return (1, pair, *kickers)
    return (0, *ranks)


def best_hand_rank(cards: Sequence[tuple[int, str]]) -> tuple:
    if len(cards) < 5:
        return (0,)
    best = None
    for combo in itertools.combinations(cards, 5):
        rank = _rank_five(combo)
        if best is None or rank > best:
            best = rank
    return best if best is not None else (0,)


def estimate_equity(
    *,
    hero_hole: Sequence[tuple[int, str]],
    board: Sequence[tuple[int, str]],
    opponents: int,
    samples: int,
    seed: int,
) -> float:
    if opponents <= 0:
        return 1.0
    if samples <= 0:
        return 0.0

    used = set(hero_hole) | set(board)
    deck = [c for c in _FULL_DECK if c not in used]

    rng = random.Random(seed)
    wins = 0.0
    for _ in range(samples):
        draw_cnt = (5 - len(board)) + (2 * opponents)
        picks = rng.sample(deck, draw_cnt)
        board_fill = list(board) + picks[: max(0, 5 - len(board))]
        offset = max(0, 5 - len(board))
        opp_holes = []
        for i in range(opponents):
            opp_holes.append(picks[offset + i * 2 : offset + (i + 1) * 2])

        hero_rank = best_hand_rank(list(hero_hole) + board_fill)
        best_rank = hero_rank
        tie_count = 0
        for opp in opp_holes:
            rank = best_hand_rank(list(opp) + board_fill)
            if rank > best_rank:
                best_rank = rank
                tie_count = 0
            elif rank == best_rank:
                if best_rank == hero_rank:
                    tie_count += 1
        if hero_rank > best_rank:
            wins += 1.0
        elif hero_rank == best_rank:
            wins += 1.0 / (1.0 + tie_count)

    return wins / float(samples)
