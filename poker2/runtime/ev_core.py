from __future__ import annotations

from typing import Any
import math


def estimate_rake(
    *,
    pot_after: float,
    street: str | None,
    rake_rate: float,
    rake_cap: int | None,
    no_flop_no_drop: bool,
) -> float:
    if not street or street == "PREFLOP":
        if no_flop_no_drop:
            return 0.0
        cap = float(rake_cap) if rake_cap is not None else float(pot_after)
        return min(pot_after * rake_rate, cap)
    rake = pot_after * rake_rate
    if rake_cap is not None:
        rake = min(rake, float(rake_cap))
    return max(0.0, rake)


def action_ev(
    *,
    action: dict[str, Any],
    equity: float,
    pot_chips: int,
    actor_commit: int,
    to_call: int,
    players_alive: int,
    street: str | None,
    rake_rate: float = 0.0,
    rake_cap: int | None = None,
    no_flop_no_drop: bool = False,
    defend_rate: float | None = None,
) -> float:
    kind = action.get("kind")
    target = int(action.get("target_total_commit_chips", actor_commit))
    extra_commit = max(0, target - actor_commit)
    if kind == "FOLD":
        return 0.0
    if kind in ("CALL", "CHECK"):
        pot_after = pot_chips + to_call
        rake = estimate_rake(
            pot_after=float(pot_after),
            street=street,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )
        return (equity * max(0.0, pot_after - rake)) - float(to_call)
    if kind in ("RAISE", "BET"):
        bet_size = extra_commit
        if bet_size <= 0:
            return 0.0
        pot_base = pot_chips
        rake_base = estimate_rake(
            pot_after=float(pot_base + bet_size),
            street=street,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )
        denom = max(1.0, float(pot_base + bet_size - rake_base))
        if defend_rate is None:
            defend_freq = max(0.0, min(1.0, float(pot_base) / denom))
        else:
            defend_freq = max(0.0, min(1.0, float(defend_rate)))
        opponents = max(1, players_alive - 1)
        fold_all = (1.0 - defend_freq) ** opponents
        exp_callers = defend_freq * opponents
        pot_after = pot_base + bet_size * (1.0 + exp_callers)
        rake = estimate_rake(
            pot_after=float(pot_after),
            street=street,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )
        ev_called = (equity * max(0.0, pot_after - rake)) - float(bet_size)
        rake_fold = estimate_rake(
            pot_after=float(pot_base),
            street=street,
            rake_rate=rake_rate,
            rake_cap=rake_cap,
            no_flop_no_drop=no_flop_no_drop,
        )
        ev_fold = max(0.0, float(pot_base) - float(rake_fold))
        return fold_all * ev_fold + (1.0 - fold_all) * ev_called
    return 0.0


def equity_uncertainty(
    *,
    equity: float,
    samples: int,
    players_alive: int,
    wet_score: int | None = None,
) -> float:
    """
    Dimensionless uncertainty proxy for risk-adjusted action selection.
    Uses variance of a Bernoulli equity estimate scaled by sample count,
    with mild inflation for multiway and wet boards.
    """
    eq = max(0.0, min(1.0, float(equity)))
    base = math.sqrt(max(0.0, eq * (1.0 - eq)))
    sample_term = 1.0 / max(1.0, math.sqrt(max(1, int(samples))))
    multi_term = 1.0 + 0.15 * max(0, int(players_alive) - 2)
    wet_term = 1.0 + 0.08 * max(0, int(wet_score or 0))
    return base * sample_term * multi_term * wet_term
