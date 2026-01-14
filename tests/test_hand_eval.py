from __future__ import annotations

from poker2.runtime.hand_eval import best_hand_rank, estimate_equity, parse_card_token


def test_parse_card_token() -> None:
    assert parse_card_token("SEVEN OF SPADES (7s)") == (7, "s")
    assert parse_card_token("ACE OF CLUBS (Ac)") == (14, "c")
    assert parse_card_token("10d") == (10, "d")


def test_best_hand_rank_straight_flush() -> None:
    cards = [(14, "s"), (13, "s"), (12, "s"), (11, "s"), (10, "s"), (2, "d"), (3, "c")]
    rank = best_hand_rank(cards)
    assert rank[0] == 8


def test_best_hand_rank_full_house() -> None:
    cards = [(9, "h"), (9, "s"), (9, "c"), (3, "d"), (3, "s"), (8, "h"), (2, "c")]
    rank = best_hand_rank(cards)
    assert rank[0] == 6


def test_estimate_equity_range() -> None:
    hole = [(14, "s"), (14, "d")]
    board = [(2, "c"), (7, "h"), (9, "s")]
    eq = estimate_equity(hero_hole=hole, board=board, opponents=2, samples=50, seed=42)
    assert 0.0 <= eq <= 1.0
