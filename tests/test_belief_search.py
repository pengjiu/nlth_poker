from __future__ import annotations

from poker2.runtime.belief_search import BeliefSearchConfig, choose_action_with_belief_search


def test_belief_search_raises_value_on_river_nuts() -> None:
    hero = ((12, "h"), (11, "h"))
    board = ((14, "h"), (9, "h"), (4, "c"), (2, "d"), (3, "h"))
    legal = [
        {"kind": "FOLD", "target_total_commit_chips": 100},
        {"kind": "CALL", "target_total_commit_chips": 200},
        {"kind": "RAISE", "target_total_commit_chips": 380},
        {"kind": "RAISE", "target_total_commit_chips": 520},
    ]
    result = choose_action_with_belief_search(
        legal_actions=legal,
        hero_hole=hero,
        board=board,
        pot_chips=300,
        actor_commit=100,
        to_call=100,
        stack_chips=900,
        players_alive=2,
        street="RIVER",
        state_hash="river-nuts-case",
        bb=50,
        pos_key="BB",
    )
    assert result is not None
    assert result.action["kind"] == "RAISE"
    rows = result.trace["belief_search_rows"]
    assert rows[0]["kind"] == "RAISE"


def test_belief_search_folds_weak_bluffcatcher_vs_big_river_bet() -> None:
    hero = ((12, "d"), (8, "c"))
    board = ((14, "s"), (13, "d"), (8, "h"), (4, "c"), (2, "s"))
    legal = [
        {"kind": "FOLD", "target_total_commit_chips": 100},
        {"kind": "CALL", "target_total_commit_chips": 300},
        {"kind": "RAISE", "target_total_commit_chips": 750},
    ]
    result = choose_action_with_belief_search(
        legal_actions=legal,
        hero_hole=hero,
        board=board,
        pot_chips=400,
        actor_commit=100,
        to_call=200,
        stack_chips=1200,
        players_alive=2,
        street="RIVER",
        state_hash="river-bluffcatch-case",
        bb=50,
        pos_key="BB",
    )
    assert result is not None
    assert result.action["kind"] == "FOLD"
    rows = result.trace["belief_search_rows"]
    assert rows[0]["kind"] == "FOLD"


def test_belief_search_bets_combo_draw_when_checked_to() -> None:
    hero = ((14, "h"), (13, "h"))
    board = ((12, "h"), (11, "h"), (2, "c"))
    legal = [
        {"kind": "CHECK", "target_total_commit_chips": 0},
        {"kind": "BET", "target_total_commit_chips": 80},
        {"kind": "BET", "target_total_commit_chips": 160},
    ]
    result = choose_action_with_belief_search(
        legal_actions=legal,
        hero_hole=hero,
        board=board,
        pot_chips=120,
        actor_commit=0,
        to_call=0,
        stack_chips=1000,
        players_alive=2,
        street="FLOP",
        state_hash="flop-combo-draw-case",
        bb=20,
        pos_key="BU",
    )
    assert result is not None
    assert result.action["kind"] == "BET"


def test_belief_search_hu_guard_returns_none_multiway() -> None:
    hero = ((14, "h"), (13, "h"))
    board = ((12, "h"), (11, "h"), (2, "c"))
    legal = [
        {"kind": "CHECK", "target_total_commit_chips": 0},
        {"kind": "BET", "target_total_commit_chips": 80},
    ]
    result = choose_action_with_belief_search(
        legal_actions=legal,
        hero_hole=hero,
        board=board,
        pot_chips=120,
        actor_commit=0,
        to_call=0,
        stack_chips=1000,
        players_alive=3,
        street="FLOP",
        state_hash="multiway-guard-case",
        bb=20,
        pos_key="BU",
        config=BeliefSearchConfig(),
    )
    assert result is None
