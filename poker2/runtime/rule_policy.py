from __future__ import annotations

from typing import Any, Callable
import json
from pathlib import Path
import hashlib
import random

from poker2.runtime.ev_core import action_ev, equity_uncertainty
from poker2.runtime.hand_eval import estimate_equity, parse_card_token, board_texture

from poker2.protocol.treepath_mapping import position_key

PolicyFn = Callable[[dict[str, Any]], dict[str, Any]]


def _pick_action_of_kind(legal_actions: list[dict[str, Any]], *, kind: str, prefer_max: bool) -> dict[str, Any] | None:
    candidates = [a for a in legal_actions if a.get("kind") == kind]
    if not candidates:
        return None
    key = (lambda a: a.get("target_total_commit_chips", 0))
    return (max if prefer_max else min)(candidates, key=key)


def _stable_hash_int(label: str) -> int:
    return int(hashlib.sha256(label.encode()).hexdigest()[:8], 16)


def _score_from_ctx(ctx: dict[str, Any], seed: int, seat_id: int) -> int:
    snap = ctx.get("snapshot", {})
    to_call = int(snap.get("to_call_chips", 0))
    actor_commit = int(snap.get("actor_commit_chips", 0))
    actor_stack = int(snap.get("actor_stack_chips", 0))
    key = f"{seed}|{seat_id}|{to_call}|{actor_commit}|{actor_stack}"
    return _stable_hash_int(key)


def _pick_nearest_raise(legal_actions: list[dict[str, Any]], target: int) -> dict[str, Any] | None:
    raises = [a for a in legal_actions if a.get("kind") in ("RAISE", "BET")]
    if not raises:
        return None
    return min(raises, key=lambda a: (abs(int(a.get("target_total_commit_chips", 0)) - target), a.get("target_total_commit_chips", 0)))


def make_rule_policy(*, style: str, aggression: float, seat_id: int, seed: int) -> PolicyFn:
    """
    轻量常客档 rulebot：
    - 位置感知的开局/3bet/4bet/平跟频率
    - 翻后基于价格与人数的 cbet / stab / 防守
    - 仅整数筹码操作（不引入新的筹码换算途径），可复现、低算力
    """
    style_norm = style if style in ("tight", "loose", "balanced", "reg") else "balanced"
    style_factor = {"tight": 0.85, "balanced": 1.0, "reg": 1.05, "loose": 1.15}[style_norm]
    base_agg = max(0.05, min(1.0, aggression)) * style_factor

    # 位置基线：7max 常客档经验值
    open_freq_map = {"BU": 0.55, "SB": 0.50, "BB": 0.08, "OTHERS": 0.23}
    threebet_freq_map = {"BU": 0.10, "SB": 0.12, "BB": 0.15, "OTHERS": 0.07}
    fourbet_freq = 0.035
    preflop_prior: dict[str, Any] = {}
    try:
        spec_path = Path(__file__).resolve().parents[2] / "specs" / "preflop" / "preflop_freq_v1.json"
        if spec_path.exists():
            preflop_prior = json.loads(spec_path.read_text(encoding="utf-8")).get("positions", {}) or {}
    except Exception:
        preflop_prior = {}
    preflop_equity_dist: dict[int, list[float]] = {}

    def _preflop_equity_dist(opponents: int) -> list[float]:
        cached = preflop_equity_dist.get(opponents)
        if cached is not None:
            return cached
        rng = random.Random(seed ^ (opponents << 7))
        deck = [(r, s) for r in range(2, 15) for s in ("c", "d", "h", "s")]
        dist: list[float] = []
        sample_hands = 220 if opponents >= 4 else 280
        players_alive = opponents + 1
        base = 24 + 4 * players_alive + 6 * 5
        equity_samples = min(80, max(24, base))
        for idx in range(sample_hands):
            hero = rng.sample(deck, 2)
            eq = estimate_equity(
                hero_hole=hero,
                board=(),
                opponents=max(1, opponents),
                samples=equity_samples,
                seed=(seed ^ (opponents << 11) ^ idx),
            )
            dist.append(eq)
        dist.sort()
        preflop_equity_dist[opponents] = dist
        return dist

    def _preflop_cutoff(opponents: int, pct: float) -> float:
        pct = max(0.0, min(1.0, pct))
        if pct <= 0:
            return 1.0
        if pct >= 1:
            return 0.0
        dist = _preflop_equity_dist(opponents)
        idx = int((1.0 - pct) * max(0, len(dist) - 1))
        return dist[idx]

    def _edge_mix(equity: float, cutoff: float, width: float = 0.02) -> float:
        if equity >= cutoff + width:
            return 1.0
        if equity <= cutoff - width:
            return 0.0
        return (equity - (cutoff - width)) / max(1e-6, 2 * width)

    def _call_freq(price_frac: float) -> float:
        # 简单价格分段：越贵越少平跟
        if price_frac <= 0.18:
            return 0.45
        if price_frac <= 0.30:
            return 0.25
        if price_frac <= 0.45:
            return 0.12
        if price_frac <= 0.65:
            return 0.06
        return 0.02

    def _policy(ctx: dict[str, Any]) -> dict[str, Any]:
        nonlocal base_agg

        def _rng_pct(label: str) -> int:
            # 0..9999
            return (_score_from_ctx(ctx, seed, seat_id) ^ _stable_hash_int(label)) % 10000

        def _rng_unit(label: str) -> float:
            return _rng_pct(label) / 10000.0
        legal = ctx["legal_actions"]
        snapshot = ctx["snapshot"]
        to_call = int(snapshot.get("to_call_chips", 0))
        min_raise = snapshot.get("min_raise_to_chips")
        max_raise = snapshot.get("max_raise_to_chips")
        actor_commit = int(snapshot.get("actor_commit_chips", 0))
        actor_stack = int(snapshot.get("actor_stack_chips", 0))
        call_target = actor_commit + to_call
        pot_chips = int(snapshot.get("pot_chips", 0))
        players_alive = int(snapshot.get("players_alive_count", 0) or 0)
        street = snapshot.get("street") or "PREFLOP"
        total_stack = actor_commit + actor_stack

        obs = ctx.get("observation") or {}
        ruleset = ctx.get("ruleset") if isinstance(ctx.get("ruleset"), dict) else {}
        rake_cfg = ruleset.get("rake") if isinstance(ruleset, dict) else {}
        rake_rate = (int(rake_cfg.get("pct_ppm", 0) or 0) / 1_000_000.0) if isinstance(rake_cfg, dict) else 0.0
        rake_cap = rake_cfg.get("cap_chips") if isinstance(rake_cfg, dict) else None
        no_flop_no_drop = bool(rake_cfg.get("no_flop_no_drop", False)) if isinstance(rake_cfg, dict) else False
        btn = obs.get("button_seat", seat_id)
        seats_in_hand = obs.get("seats_in_hand", [])
        pos = position_key(seat_id, btn, seats_in_hand) if isinstance(seats_in_hand, list) and seats_in_hand else "OTHERS"
        last_raiser_map = obs.get("last_raiser_by_street") or {}
        opener_pos = None
        if isinstance(last_raiser_map, dict):
            opener_seat = last_raiser_map.get("PREFLOP")
            if isinstance(opener_seat, int):
                opener_pos = position_key(opener_seat, btn, seats_in_hand)
        street_raise_count_map = obs.get("street_raise_count") or {}
        street_raise_count = 0
        if isinstance(street_raise_count_map, dict):
            street_raise_count = int(street_raise_count_map.get(street, 0) or 0)

        def _equity_from_obs(*, return_samples: bool = False) -> float | tuple[float, int] | None:
            hole_map = obs.get("hole_cards_by_seat") or {}
            hole_raw = hole_map.get(str(seat_id)) if isinstance(hole_map, dict) else None
            if not isinstance(hole_raw, list) or len(hole_raw) != 2:
                return None
            board_raw = obs.get("board_cards") or []
            if not isinstance(board_raw, list):
                return None
            hole_cards = [parse_card_token(c) for c in hole_raw]
            board_cards = [parse_card_token(c) for c in board_raw]
            if any(c is None for c in hole_cards) or any(c is None for c in board_cards):
                return None
            opponents = max(1, players_alive - 1)
            board_len = len(board_cards)
            samples = min(48, max(16, 20 + 3 * opponents + 4 * max(0, 5 - board_len)))
            seed_hex = (ctx.get("state_hash") or "")[:16]
            try:
                seed_val = int(seed_hex, 16) ^ (seat_id << 4) ^ (players_alive << 8)
            except Exception:
                seed_val = seed ^ (seat_id << 4) ^ (players_alive << 8)
            eq = estimate_equity(
                hero_hole=hole_cards,  # type: ignore[arg-type]
                board=board_cards,  # type: ignore[arg-type]
                opponents=opponents,
                samples=samples,
                seed=seed_val,
            )
            if return_samples:
                return (eq, samples)
            return eq

        equity_pack = _equity_from_obs(return_samples=True)
        equity = None
        equity_samples: int | None = None
        if isinstance(equity_pack, tuple):
            equity, equity_samples = equity_pack
        else:
            equity = equity_pack
        board_tex: tuple[str, str] | None = None
        board_raw = obs.get("board_cards") or []
        if isinstance(board_raw, list) and len(board_raw) >= 3:
            parsed = [parse_card_token(c) for c in board_raw]
            if all(c is not None for c in parsed):
                cards = [c for c in parsed if c is not None]
                board_tex = board_texture(cards)

        def _board_wet_score(board_tex: tuple[str, str] | None, street_val: str | None) -> int:
            score = 0
            if board_tex is not None:
                suit_tex, rank_tex = board_tex
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
            if street_val == "TURN":
                score = max(0, score - 1)
            elif street_val == "RIVER":
                score = max(0, score - 2)
            return score

        def _uncertainty_for(equity_val: float) -> float:
            if equity_samples is None:
                return 0.0
            wet_score = _board_wet_score(board_tex, street)
            return equity_uncertainty(
                equity=equity_val,
                samples=equity_samples,
                players_alive=players_alive,
                wet_score=wet_score,
            )
        equity_eff_pre = equity
        if equity_eff_pre is not None:
            realization = 1.0
            if players_alive >= 3:
                realization -= 0.06 * max(0, players_alive - 2)
            if pos in ("SB", "BB"):
                realization -= 0.07
            realization = max(0.60, min(1.0, realization))
            equity_eff_pre = equity_eff_pre * realization

        call_act = _pick_action_of_kind(legal, kind="CALL", prefer_max=False)
        fold_act = _pick_action_of_kind(legal, kind="FOLD", prefer_max=False)
        check_act = _pick_action_of_kind(legal, kind="CHECK", prefer_max=False)

        def _pick_raise_min(prefer_max: bool = False) -> dict[str, Any] | None:
            if min_raise is not None:
                act = _pick_nearest_raise(legal, int(min_raise))
                if act:
                    return act
            return _pick_action_of_kind(legal, kind="RAISE", prefer_max=prefer_max) or _pick_action_of_kind(legal, kind="BET", prefer_max=prefer_max)

        def _bounded_target(target: int) -> int:
            if max_raise is not None:
                target = min(target, int(max_raise))
            if min_raise is not None:
                target = max(target, int(min_raise))
            return target

        def _raise_to_mult(mult: int) -> dict[str, Any] | None:
            if to_call <= 0:
                return _pick_raise_min(prefer_max=False)
            target = _bounded_target(max(call_target + max(1, to_call), call_target * mult))
            return _pick_nearest_raise(legal, target) or _pick_raise_min(prefer_max=False)

        def _action_ev(
            action: dict[str, Any],
            equity_val: float,
            pot_chips: int,
            actor_commit: int,
            to_call_chips: int,
            players: int,
        ) -> float:
            defend_rate = None
            if action.get("kind") in ("RAISE", "BET"):
                target = int(action.get("target_total_commit_chips", actor_commit))
                bet_size = max(0, target - actor_commit)
                pot_base = max(0, int(pot_chips))
                denom = max(1.0, float(pot_base + bet_size))
                base = float(pot_base) / denom
                min_defend = 0.25 if players <= 2 else 0.35
                defend_rate = max(base, min_defend)
            return action_ev(
                action=action,
                equity=equity_val,
                pot_chips=pot_chips,
                actor_commit=actor_commit,
                to_call=to_call_chips,
                players_alive=players,
                street=snapshot.get("street"),
                defend_rate=defend_rate,
                rake_rate=rake_rate,
                rake_cap=rake_cap,
                no_flop_no_drop=no_flop_no_drop,
            )

        def _action_score(action: dict[str, Any], equity_val: float) -> float:
            ev_val = _action_ev(action, equity_val, pot_chips, actor_commit, to_call, players_alive)
            target = int(action.get("target_total_commit_chips", actor_commit))
            risk = max(0, target - actor_commit)
            pot_unit = float(max(1, pot_chips + to_call))
            size_ratio = float(risk) / pot_unit
            stack_unit = float(max(1, actor_stack + actor_commit))
            commit_ratio = float(risk) / stack_unit
            penalty = _uncertainty_for(equity_val) * float(risk) * (1.0 + size_ratio + 2.0 * commit_ratio)
            mw_penalty = 0.0
            if players_alive >= 5 and action.get("kind") in ("CALL", "RAISE", "BET"):
                base = 0.12 + 0.04 * max(0, players_alive - 5)
                mw_penalty = float(risk) * base
                if action.get("kind") == "CALL" and pos in ("SB", "BB"):
                    mw_penalty *= 1.35
            return ev_val - penalty - mw_penalty

        def _ev_pairs(equity_val: float) -> list[tuple[float, dict[str, Any]]]:
            return [
                (
                    _action_score(act, equity_val),
                    act,
                )
                for act in legal
            ]

        def _best_ev_pair(
            ev_pairs: list[tuple[float, dict[str, Any]]], *, kinds: set[str] | None = None
        ) -> tuple[dict[str, Any] | None, float]:
            best_act = None
            best_ev = -1e9
            for ev, act in ev_pairs:
                kind = str(act.get("kind"))
                if kinds is not None and kind not in kinds:
                    continue
                if best_act is None or ev > best_ev:
                    best_act = act
                    best_ev = ev
            return best_act, best_ev

        def _maybe_floor_action(
            *,
            act: dict[str, Any] | None,
            ev_val: float,
            best_ev: float,
            floor_prob: float,
            label: str,
            slack_mult: float,
            min_ev_mult: float,
        ) -> dict[str, Any] | None:
            if act is None or floor_prob <= 0:
                return None
            pot_unit = max(1, pot_chips + to_call)
            slack = slack_mult * float(pot_unit)
            min_ev = min_ev_mult * float(pot_unit)
            if (best_ev - ev_val) > slack or ev_val < min_ev:
                return None
            if _rng_pct(label) < int(floor_prob * 10000):
                return act
            return None

        def _choose_action_ev_floor(
            *,
            equity_val: float,
            street: str,
            to_call: int,
            pos: str,
            prev_aggressor: int | None,
            open_floor: float,
            call_floor: float,
            raise_floor: float,
        ) -> dict[str, Any] | None:
            if equity_val <= 0 or not legal:
                return None
            ev_pairs = _ev_pairs(equity_val)
            best_act, best_ev = _best_ev_pair(ev_pairs)
            if best_act is None:
                return None
            best_raise, raise_ev = _best_ev_pair(ev_pairs, kinds={"RAISE", "BET"})
            best_call, call_ev = _best_ev_pair(ev_pairs, kinds={"CALL", "CHECK"})

            if to_call == 0:
                floor_act = _maybe_floor_action(
                    act=best_raise,
                    ev_val=raise_ev,
                    best_ev=best_ev,
                    floor_prob=open_floor,
                    label=f"floor_open:{seat_id}:{street}:{pos}",
                    slack_mult=0.10,
                    min_ev_mult=-0.08,
                )
                if floor_act is not None:
                    return floor_act
            else:
                floor_raise = _maybe_floor_action(
                    act=best_raise,
                    ev_val=raise_ev,
                    best_ev=best_ev,
                    floor_prob=raise_floor,
                    label=f"floor_raise:{seat_id}:{street}:{pos}",
                    slack_mult=0.12,
                    min_ev_mult=-0.08,
                )
                if floor_raise is not None:
                    return floor_raise
                floor_call = _maybe_floor_action(
                    act=best_call,
                    ev_val=call_ev,
                    best_ev=best_ev,
                    floor_prob=call_floor,
                    label=f"floor_call:{seat_id}:{street}:{pos}",
                    slack_mult=0.10,
                    min_ev_mult=-0.10,
                )
                if floor_call is not None:
                    return floor_call
            return best_act

        def _best_action_by_ev(
            legal_actions: list[dict[str, Any]],
            equity_val: float,
            *,
            kinds: set[str] | None = None,
        ) -> tuple[dict[str, Any] | None, float]:
            best_act = None
            best_score = -1e9
            for act in legal_actions:
                kind = str(act.get("kind"))
                if kinds is not None and kind not in kinds:
                    continue
                score = _action_score(act, equity_val)
                if best_act is None or score > best_score:
                    best_act = act
                    best_score = score
            return best_act, best_score

        def _choose_action_by_ev(equity_val: float, *, slack: float = 0.6) -> dict[str, Any] | None:
            if equity_val <= 0 or not legal:
                return None
            score_pairs: list[tuple[float, dict[str, Any]]] = []
            for act in legal:
                score = _action_score(act, equity_val)
                score_pairs.append((score, act))
            best_score = max(score_pairs, key=lambda x: x[0])[0] if score_pairs else -1e9
            candidates = [(score, act) for score, act in score_pairs if score >= (best_score - slack)]
            if not candidates:
                return None
            candidates.sort(
                key=lambda ea: (-ea[0], int(ea[1].get("target_total_commit_chips", actor_commit)))
            )
            return candidates[0][1]

        def _realize_equity(equity_val: float) -> float:
            realization = 1.0
            if players_alive >= 3:
                realization -= 0.07 * max(0, players_alive - 2)
            if pos in ("SB", "BB"):
                realization -= 0.08
            if to_call > 0:
                realization -= 0.04
                if street == "PREFLOP" and street_raise_count >= 1:
                    realization -= 0.03
            if rake_rate > 0:
                realization -= min(0.08, rake_rate * 2.0)
            return max(0.55, min(1.0, equity_val * realization))

        def _choose_action_ev_mixed(equity_val: float, *, prior: dict[str, float] | None = None) -> dict[str, Any] | None:
            if equity_val <= 0 or not legal:
                return None
            scores: list[tuple[float, dict[str, Any]]] = []
            for act in legal:
                scores.append((_action_score(act, equity_val), act))
            if not scores:
                return None
            best_score = max(scores, key=lambda x: x[0])[0]
            pot_unit = float(max(1, pot_chips + to_call))
            uncertainty = _uncertainty_for(equity_val)
            tol = max(1.0, pot_unit * uncertainty)
            candidates = [(s, a) for (s, a) in scores if s >= (best_score - tol)]
            if not candidates:
                candidates = scores
            max_score = max(candidates, key=lambda x: x[0])[0]
            temp = max(1.0, tol)
            weights: list[float] = []
            for score, _ in candidates:
                weights.append(float(pow(2.718281828459045, (score - max_score) / temp)))
            if prior:
                for i, (_, act) in enumerate(candidates):
                    kind = str(act.get("kind"))
                    if kind in prior:
                        p = max(0.0, min(1.0, float(prior[kind])))
                        weights[i] *= (0.05 + 3.0 * p)
            nonfold_idx = [i for i, (_, a) in enumerate(candidates) if a.get("kind") != "FOLD"]
            fold_idx = [i for i, (_, a) in enumerate(candidates) if a.get("kind") == "FOLD"]
            total = sum(weights)
            if total <= 0:
                return max(candidates, key=lambda x: x[0])[1]
            # Frequency floor among non-fold actions when near-indifferent.
            if nonfold_idx and len(nonfold_idx) >= 2:
                floor = max(0.02, min(0.20, uncertainty * 1.2))
                sum_nonfold = sum(weights[i] for i in nonfold_idx)
                sum_fold = sum(weights[i] for i in fold_idx)
                total = sum_nonfold + sum_fold
                if total <= 0:
                    return max(candidates, key=lambda x: x[0])[1]
                p_fold = (sum_fold / total) if sum_fold > 0 else 0.0
                p_nonfold = 1.0 - p_fold
                for i in nonfold_idx:
                    base = (weights[i] / sum_nonfold) if sum_nonfold > 0 else (1.0 / len(nonfold_idx))
                    weights[i] = p_nonfold * ((1.0 - floor) * base + floor * (1.0 / len(nonfold_idx)))
                for i in fold_idx:
                    weights[i] = p_fold * (weights[i] / sum_fold) if sum_fold > 0 else 0.0
            # Normalize
            total = sum(weights)
            if total <= 0:
                return max(candidates, key=lambda x: x[0])[1]
            r = _rng_unit(f"evmix:{seat_id}:{street}:{ctx.get('state_hash','')}")
            acc = 0.0
            for (score, act), w in zip(candidates, weights):
                acc += w / total
                if r <= acc:
                    return act
            return max(candidates, key=lambda x: x[0])[1]

        # --- Preflop ---
        if street == "PREFLOP":
            if opener_pos is None and isinstance(last_raiser_map, dict):
                opener_seat = last_raiser_map.get("PREFLOP")
                if isinstance(opener_seat, int):
                    opener_pos = position_key(opener_seat, btn, seats_in_hand) if seats_in_hand else "OTHERS"
            if street_raise_count == 0 and to_call > 0 and pos not in ("SB", "BB"):
                legal = [a for a in legal if a.get("kind") != "CALL"]
                call_act = _pick_action_of_kind(legal, kind="CALL", prefer_max=False)
                fold_act = _pick_action_of_kind(legal, kind="FOLD", prefer_max=False)
                check_act = _pick_action_of_kind(legal, kind="CHECK", prefer_max=False)
            if style_norm == "reg":
                if equity is not None:
                    eq = _realize_equity(equity)
                    prior = None
                    if preflop_prior:
                        pos_prior = preflop_prior.get(pos) or preflop_prior.get("OTHERS") or {}
                        open_pct = float(pos_prior.get("open_pct", 0.30) or 0.30)
                        call_pct = float(pos_prior.get("call_pct", 0.25) or 0.25)
                        threebet_pct = float(pos_prior.get("threebet_pct", 0.12) or 0.12)
                        fourbet_pct = float(pos_prior.get("fourbet_pct", 0.04) or 0.04)
                        behind = max(0, players_alive - 3)
                        rake_press = min(0.24, (rake_rate * 2.2) + (0.03 * behind))
                        if pos in ("SB", "BB"):
                            rake_press = min(0.28, rake_press + 0.03)
                        open_pct = max(0.0, open_pct * (1.0 - rake_press))
                        call_pct = max(0.0, call_pct * (1.0 - rake_press * 1.25))
                        threebet_pct = max(0.0, threebet_pct * (1.0 - rake_press * 0.6))
                        fourbet_pct = max(0.0, fourbet_pct * (1.0 - rake_press * 0.4))
                        if players_alive >= 5:
                            mw_factor = max(0.35, 1.0 - 0.12 * max(0, players_alive - 4))
                            call_pct = max(0.0, call_pct * mw_factor)
                            open_pct = max(0.0, open_pct * (0.85 - 0.04 * max(0, players_alive - 5)))
                            if pos == "OTHERS":
                                open_pct = max(0.0, open_pct * 0.6)
                        if street_raise_count >= 1:
                            if pos == "SB":
                                call_shrink = 0.08
                            elif pos == "BB":
                                call_shrink = 0.15
                            else:
                                call_shrink = 0.25
                            call_pct = max(0.0, call_pct * call_shrink)
                            threebet_pct = max(0.0, threebet_pct * 1.15)
                            if pos == "SB":
                                call_pct = 0.0
                            elif pos == "BB":
                                call_pct = min(call_pct, 0.25)
                            else:
                                call_pct = min(call_pct, 0.12)
                        if street_raise_count == 1 and to_call > 0:
                            if pos == "BB":
                                call_pct *= 0.55
                                threebet_pct *= 0.85
                            elif pos == "SB":
                                call_pct *= 0.45
                                threebet_pct *= 0.90
                            if opener_pos in ("BU", "SB"):
                                call_pct *= 0.70
                                threebet_pct *= 0.85
                            if opener_pos == "BU" and pos == "SB":
                                call_pct *= 0.30
                                threebet_pct = min(threebet_pct, 0.10)
                            if opener_pos == "BU" and pos == "BB":
                                call_pct *= 0.50
                                threebet_pct = min(threebet_pct, 0.06)
                            if opener_pos == "SB" and pos == "BB":
                                threebet_pct = min(threebet_pct, 0.08)
                        if pos == "SB":
                            call_pct = max(0.0, call_pct * 0.12)
                        elif pos == "BB":
                            call_pct = max(0.0, call_pct * 0.35)
                        committed_ge = 0
                        commits_by_seat = obs.get("commits_by_seat") or {}
                        if isinstance(commits_by_seat, dict):
                            for seat_key, val in commits_by_seat.items():
                                if str(seat_key) == str(seat_id):
                                    continue
                                try:
                                    if int(val) >= int(call_target):
                                        committed_ge += 1
                                except Exception:
                                    continue
                        multiway_pressure = committed_ge >= 2 and players_alive >= 4
                        if multiway_pressure:
                            call_pct = max(0.0, call_pct * 0.45)
                            open_pct = max(0.0, open_pct * 0.80)
                            threebet_pct = max(0.0, threebet_pct * 0.85)
                        # Defend budget: rake + players behind reduce total defend frequency.
                        facing_open = street_raise_count == 1
                        if pos == "BU":
                            behind = 2
                        elif pos == "SB":
                            behind = 1
                        elif pos == "BB":
                            behind = 0
                        else:
                            behind = max(2, min(4, players_alive - 3))
                        if facing_open:
                            defend_budget = 0.42 - (0.04 * behind) - (0.8 * rake_rate) - (0.05 * max(0, players_alive - 4))
                            defend_budget = max(0.10, min(0.55, defend_budget))
                            call_pct = min(call_pct, defend_budget * 0.55)
                            threebet_pct = min(threebet_pct, defend_budget * 0.45)
                        else:
                            defend_budget = 0.22 - (0.05 * behind) - (0.7 * rake_rate) - (0.04 * max(0, players_alive - 4))
                            defend_budget = max(0.05, min(0.35, defend_budget))
                            call_pct = min(call_pct, defend_budget * 0.60)
                            fourbet_pct = min(fourbet_pct, defend_budget * 0.40)
                        if street_raise_count == 1 and to_call > 0:
                            if opener_pos in ("BU", "SB"):
                                steal_cap = 0.25 if pos == "SB" else 0.35
                            else:
                                steal_cap = 0.40 if pos == "SB" else 0.50
                            total_def = max(0.0, call_pct + threebet_pct)
                            if total_def > steal_cap and total_def > 0:
                                scale = steal_cap / total_def
                                call_pct *= scale
                                threebet_pct *= scale
                            if pos == "BB":
                                if opener_pos == "SB":
                                    threebet_pct = min(threebet_pct, 0.14)
                                elif opener_pos == "BU":
                                    threebet_pct = min(threebet_pct, 0.10)
                                else:
                                    threebet_pct = min(threebet_pct, 0.12)
                        if street_raise_count >= 1 and to_call > 0 and pos not in ("SB", "BB"):
                            opponents = max(1, players_alive - 1)
                            call_pct *= 0.40
                            threebet_pct *= 0.90
                            call_pct = min(call_pct, 0.06)
                            base_call_limit = 0.08 if players_alive >= 6 else 0.10
                            call_limit = min(call_pct, base_call_limit)
                            call_cutoff = _preflop_cutoff(opponents, call_limit)
                            if eq < call_cutoff:
                                legal = [a for a in legal if a.get("kind") != "CALL"]
                                call_act = _pick_action_of_kind(legal, kind="CALL", prefer_max=False)
                        if street_raise_count >= 1 and to_call > 0:
                            opponents = max(1, players_alive - 1)
                            if street_raise_count == 1:
                                call_cut = _preflop_cutoff(opponents, call_pct)
                                raise_cut = _preflop_cutoff(opponents, threebet_pct)
                                call_pct = max(0.0, call_pct * _edge_mix(eq, call_cut, width=0.03))
                                threebet_pct = max(0.0, threebet_pct * _edge_mix(eq, raise_cut, width=0.02))
                            else:
                                call_cut = _preflop_cutoff(opponents, call_pct)
                                raise_cut = _preflop_cutoff(opponents, fourbet_pct)
                                call_pct = max(0.0, call_pct * _edge_mix(eq, call_cut, width=0.03))
                                fourbet_pct = max(0.0, fourbet_pct * _edge_mix(eq, raise_cut, width=0.02))
                        if street_raise_count == 0 and to_call > 0:
                            opponents = max(1, players_alive - 1)
                            cutoff = _preflop_cutoff(opponents, open_pct)
                            mix = _edge_mix(eq, cutoff)
                            open_prob = max(0.0, min(1.0, open_pct * mix))
                            if pos == "SB":
                                call_prob = max(0.0, min(0.20, call_pct * 0.5))
                                r = _rng_pct(f"pf_open_sb:{seat_id}:{pos}:{ctx.get('state_hash','')}")
                                if r < int(open_prob * 10000):
                                    act = _pick_raise_min(prefer_max=False)
                                    if act:
                                        return act
                                if call_act and r < int((open_prob + call_prob) * 10000):
                                    return call_act
                                if fold_act:
                                    return fold_act
                            elif pos not in ("SB", "BB"):
                                if _rng_pct(f"pf_open_prior:{seat_id}:{pos}:{ctx.get('state_hash','')}") < int(
                                    open_prob * 10000
                                ):
                                    act = _pick_raise_min(prefer_max=False)
                                    if act:
                                        return act
                                if fold_act:
                                    return fold_act
                        if street_raise_count == 0:
                            raise_w = max(0.0, min(1.0, open_pct))
                            if to_call > 0:
                                fold_w = max(0.0, 1.0 - raise_w)
                                prior = {"RAISE": raise_w, "FOLD": fold_w}
                            else:
                                check_w = max(0.0, 1.0 - raise_w)
                                prior = {"RAISE": raise_w, "BET": raise_w, "CHECK": check_w}
                        elif street_raise_count == 1:
                            raise_w = max(0.0, min(1.0, threebet_pct))
                            call_w = max(0.0, min(1.0, call_pct))
                            fold_w = max(0.0, 1.0 - raise_w - call_w)
                            prior = {"RAISE": raise_w, "CALL": call_w, "FOLD": fold_w}
                        else:
                            raise_w = max(0.0, min(1.0, fourbet_pct))
                            call_w = max(0.0, min(1.0, call_pct * 0.5))
                            fold_w = max(0.0, 1.0 - raise_w - call_w)
                            prior = {"RAISE": raise_w, "CALL": call_w, "FOLD": fold_w}
                        act = _choose_action_ev_mixed(eq, prior=prior)
                        if act is not None:
                            return act
                    if to_call == 0 and check_act:
                        return check_act
                    if to_call > 0:
                        if call_act is not None and eq is not None:
                            pot_odds = to_call / max(pot_chips + to_call, 1)
                            if eq >= pot_odds + 0.06:
                                return call_act
                        if fold_act:
                            return fold_act
                        if call_act is not None:
                            return call_act
                    if fold_act:
                        return fold_act
                open_freq = open_freq_map.get(pos, open_freq_map["OTHERS"]) * style_factor * (0.9 + 0.2 * base_agg)
                threebet_freq = threebet_freq_map.get(pos, threebet_freq_map["OTHERS"]) * (0.7 + 0.6 * base_agg)
                fourbet_freq_eff = fourbet_freq * (0.6 + 0.7 * base_agg)
                price_frac = to_call / max(pot_chips + to_call, 1)
                stack_frac = to_call / max(total_stack, 1) if total_stack > 0 else 0.0
                rake_guard = 1.0
                if rake_rate > 0:
                    rake_guard = max(0.65, 1.0 - rake_rate * 2.2)
                facing_raise = to_call > 0 and street_raise_count >= 1
                steal_def_factor = 1.0
                if street_raise_count == 1:
                    if opener_pos in ("BU", "SB"):
                        steal_def_factor = 0.65
                    elif opener_pos == "BB":
                        steal_def_factor = 0.90
                    else:
                        steal_def_factor = 0.90
                    if pos in ("SB", "BB"):
                        steal_def_factor *= 0.9
                equity_pre = equity_eff_pre
                equity_def = equity_eff_pre
                if equity_def is not None and facing_raise:
                    def_factor = 0.84
                    if pos in ("SB", "BB"):
                        def_factor *= 0.75
                    if players_alive >= 4:
                        def_factor *= max(0.65, 1.0 - 0.07 * (players_alive - 3))
                    equity_def = equity_def * def_factor
                if equity_def is not None:
                    pos_defense_factor = (0.85 if pos in ("SB", "BB") else 1.0) * steal_def_factor
                    open_floor = max(0.02, min(0.55, open_freq * (0.75 + 0.35 * base_agg)))
                    if street_raise_count == 0 and to_call > 0:
                        raise_floor = min(0.06, open_freq * 0.35 * (0.7 + 0.6 * base_agg))
                    elif street_raise_count == 1:
                        raise_floor = min(0.10, threebet_freq * 0.6)
                    else:
                        raise_floor = min(0.08, fourbet_freq_eff * 0.7)
                    call_floor = _call_freq(price_frac) * rake_guard * style_factor * pos_defense_factor
                    if street_raise_count >= 2:
                        call_floor *= 0.75
                    action_choice = _choose_action_ev_floor(
                        equity_val=equity_def,
                        street=street,
                        to_call=to_call,
                        pos=pos,
                        prev_aggressor=None,
                        open_floor=open_floor,
                        call_floor=call_floor,
                        raise_floor=raise_floor,
                    )
                    if action_choice is not None:
                        return action_choice
                    if to_call > 0:
                        pot_odds = to_call / max(pot_chips + to_call, 1)
                        premium = 0.0
                        if facing_raise:
                            premium += 0.03
                            if pos in ("SB", "BB"):
                                premium += 0.04
                            if players_alive >= 3:
                                premium += min(0.06, 0.02 * max(0, players_alive - 2))
                            if price_frac >= 0.33:
                                premium += 0.02
                            premium = min(0.15, premium)
                        if equity_def < pot_odds + premium:
                            if fold_act:
                                return fold_act
                    ev_act = _choose_action_by_ev(equity_def, slack=0.6)
                    if ev_act is not None:
                        best_raise, _ = _best_action_by_ev(legal, equity_def, kinds={"RAISE", "BET"})
                        if to_call == 0 and ev_act.get("kind") in ("FOLD", "CHECK"):
                            open_floor = max(0.05, min(0.40, open_freq * 0.55))
                            if _rng_pct(f"open_floor:{seat_id}:{pos}") < int(open_floor * 10000):
                                if best_raise is not None:
                                    return best_raise
                        elif to_call > 0 and ev_act.get("kind") == "FOLD" and price_frac <= 0.45:
                            call_floor = 0.10 if price_frac <= 0.25 else 0.07 if price_frac <= 0.33 else 0.04
                            call_floor *= style_factor * (0.9 if pos in ("SB", "BB") else 1.0)
                            raise_floor = min(0.06, threebet_freq * 0.6) if facing_raise else min(0.04, fourbet_freq_eff * 0.6)
                            if best_raise is not None and price_frac <= 0.33:
                                if _rng_pct(f"pf_raise_floor:{seat_id}:{pos}:{price_frac}") < int(raise_floor * 10000):
                                    return best_raise
                            if call_act is not None and _rng_pct(f"pf_call_floor:{seat_id}:{pos}:{price_frac}") < int(call_floor * 10000):
                                return call_act
                        elif to_call > 0 and ev_act.get("kind") == "CALL":
                            raise_floor = min(0.05, threebet_freq * 0.5) if facing_raise else min(0.03, fourbet_freq_eff * 0.5)
                            if best_raise is not None and price_frac <= 0.25:
                                if _rng_pct(f"pf_raise_floor2:{seat_id}:{pos}:{price_frac}") < int(raise_floor * 10000):
                                    return best_raise
                        return ev_act
                    if to_call == 0 and check_act:
                        return check_act
                    if fold_act:
                        return fold_act
                if equity_def is None:
                    opponents = max(1, players_alive - 1)
                    open_freq = max(0.0, min(1.0, open_freq))
                    threebet_freq = max(0.0, min(1.0, threebet_freq * steal_def_factor))
                    fourbet_freq_eff = max(0.0, min(1.0, fourbet_freq_eff))
    
                    # 首进
                    if to_call == 0:
                        if equity_pre is not None and street_raise_count == 0:
                            cutoff = _preflop_cutoff(opponents, open_freq)
                            mix = _edge_mix(equity_pre, cutoff)
                            if _rng_pct(f"open_eq:{seat_id}:{pos}") < int(mix * 10000):
                                act = _pick_raise_min(prefer_max=False)
                                if act:
                                    return act
                        elif _rng_pct(f"open:{seat_id}:{pos}") < int(open_freq * 10000):
                            act = _pick_raise_min(prefer_max=False)
                            if act:
                                return act
                        if check_act:
                            return check_act
                        if fold_act:
                            return fold_act
    
                    # 面对开局/再加注
                    if stack_frac > 0.45:
                        # 大额压力直接弃牌（保守，不爆栈）
                        if fold_act:
                            return fold_act
                    # 轻度 / 中等价位
                    pos_defense_factor = (0.85 if pos in ("SB", "BB") else 1.0) * steal_def_factor
                    if price_frac <= 0.33:
                        if equity_def is not None:
                            raise_cut = _preflop_cutoff(opponents, threebet_freq)
                            call_freq = min(1.0, threebet_freq + _call_freq(price_frac) * rake_guard * style_factor * pos_defense_factor)
                            call_cut = _preflop_cutoff(opponents, call_freq)
                            if equity_def >= raise_cut:
                                act = _raise_to_mult(2)
                                if act:
                                    return act
                            if equity_def >= call_cut and call_act:
                                return call_act
                        if _rng_pct(f"3bet:{seat_id}:{price_frac}") < int(threebet_freq * 10000):
                            act = _raise_to_mult(2)
                            if act:
                                return act
                        call_freq = _call_freq(price_frac) * rake_guard * style_factor * pos_defense_factor
                        if call_act and _rng_pct(f"flat:{seat_id}:{price_frac}") < int(call_freq * 10000):
                            return call_act
                    elif price_frac <= 0.55:
                        if equity_def is not None:
                            raise_cut = _preflop_cutoff(opponents, threebet_freq * 0.55)
                            call_freq = min(1.0, threebet_freq * 0.55 + _call_freq(price_frac) * rake_guard * style_factor * 0.8 * pos_defense_factor)
                            call_cut = _preflop_cutoff(opponents, call_freq)
                            if equity_def >= raise_cut:
                                act = _raise_to_mult(2)
                                if act:
                                    return act
                            if equity_def >= call_cut and call_act:
                                return call_act
                        if _rng_pct(f"3bet_mid:{seat_id}:{price_frac}") < int(threebet_freq * 0.55 * 10000):
                            act = _raise_to_mult(2)
                            if act:
                                return act
                        call_freq = _call_freq(price_frac) * rake_guard * style_factor * 0.8 * pos_defense_factor
                        if call_act and _rng_pct(f"flat_mid:{seat_id}:{price_frac}") < int(call_freq * 10000):
                            return call_act
                    else:
                        # 可能是 3bet/4bet 场景：偶尔 4bet，否则弃牌
                        pricey_small = price_frac > 0.55 and to_call <= max(total_stack // 8, 40)
                        if equity_def is not None:
                            raise_cut = _preflop_cutoff(opponents, fourbet_freq_eff)
                            call_freq = min(1.0, fourbet_freq_eff + _call_freq(price_frac) * rake_guard * 0.4 * style_factor)
                            if street_raise_count >= 2:
                                call_freq *= 0.6
                            call_cut = _preflop_cutoff(opponents, call_freq)
                            if equity_def >= raise_cut:
                                act = _raise_to_mult(2)
                                if act:
                                    return act
                            if equity_def >= call_cut and call_act:
                                return call_act
                        if pricey_small and _rng_pct(f"force_raise:{seat_id}") < int((0.4 + 0.4 * base_agg) * 10000):
                            act = _raise_to_mult(2)
                            if act:
                                return act
                        if _rng_pct(f"4bet:{seat_id}:{price_frac}") < int(fourbet_freq_eff * 10000):
                            act = _raise_to_mult(2)
                            if act:
                                return act
                        if style_norm == "loose" and base_agg >= 0.8:
                            act = _raise_to_mult(2)
                            if act:
                                return act
                        if fold_act:
                            return fold_act
    
                    # 默认：小额可平跟，否则弃牌
                    if call_act and price_frac <= 0.25 and _rng_pct(f"flat_def:{seat_id}") < 6500:
                        return call_act
                    if fold_act:
                        return fold_act
    
        # --- Postflop ---
        if style_norm == "reg":
            if equity is not None:
                eq = _realize_equity(equity)
                act = _choose_action_ev_mixed(eq)
                if act is not None:
                    return act
            if to_call == 0 and check_act:
                return check_act
            if to_call > 0:
                if call_act is not None and equity is not None:
                    pot_odds = to_call / max(pot_chips + to_call, 1)
                    if eq >= pot_odds + 0.04:
                        return call_act
                if fold_act:
                    return fold_act
                if call_act is not None:
                    return call_act
            if fold_act:
                return fold_act
        if street in ("FLOP", "TURN", "RIVER"):
            last_raiser_map = obs.get("last_raiser_by_street") or {}
            prev_street = {"FLOP": "PREFLOP", "TURN": "FLOP", "RIVER": "TURN"}.get(street)
            prev_aggressor = last_raiser_map.get(prev_street) if isinstance(last_raiser_map, dict) else None
            players = max(2, players_alive or 2)
            equity_eff = equity
            if equity_eff is not None and players >= 3:
                equity_eff = equity_eff * max(0.7, 1.0 - 0.05 * (players - 2))

            if equity_eff is not None:
                if to_call == 0:
                    base_floor = {"FLOP": 0.22, "TURN": 0.16, "RIVER": 0.10}.get(street, 0.14)
                    if prev_aggressor == seat_id:
                        open_floor = base_floor * 1.25
                    else:
                        open_floor = base_floor * 0.7
                    open_floor *= style_factor * (2.4 / max(2, players)) * (0.85 + 0.4 * base_agg)
                    open_floor = max(0.05, min(0.40, open_floor))
                    action_choice = _choose_action_ev_floor(
                        equity_val=equity_eff,
                        street=street,
                        to_call=to_call,
                        pos=pos,
                        prev_aggressor=prev_aggressor if isinstance(prev_aggressor, int) else None,
                        open_floor=open_floor,
                        call_floor=0.0,
                        raise_floor=0.0,
                    )
                else:
                    pot_den = max(pot_chips + to_call, 1)
                    pot_odds = to_call / pot_den
                    mdf = max(0.0, min(1.0, 1.0 - pot_odds))
                    call_floor = mdf * 0.55 * style_factor * (2.2 / max(2, players))
                    if pos in ("SB", "BB"):
                        call_floor *= 0.9
                    raise_floor = min(0.10, call_floor * (0.28 + 0.35 * base_agg))
                    action_choice = _choose_action_ev_floor(
                        equity_val=equity_eff,
                        street=street,
                        to_call=to_call,
                        pos=pos,
                        prev_aggressor=prev_aggressor if isinstance(prev_aggressor, int) else None,
                        open_floor=0.0,
                        call_floor=call_floor,
                        raise_floor=raise_floor,
                    )
                if action_choice is not None:
                    return action_choice
                ev_act = _choose_action_by_ev(equity_eff, slack=0.8)
                if ev_act is not None:
                    return ev_act
                if to_call == 0 and check_act:
                    return check_act
                if fold_act:
                    return fold_act

            if equity_eff is None:
                # 无下注：cbet 或 stab
                if to_call == 0:
                    base_cbet_map = {"FLOP": 0.62, "TURN": 0.45, "RIVER": 0.32}
                    if prev_aggressor == seat_id:
                        prob = base_cbet_map.get(street, 0.45) * style_factor * (2.2 / players) * (0.75 + 0.5 * base_agg)
                        prob = max(0.20, min(0.78, prob))
                        if _rng_pct(f"cbet:{seat_id}:{street}:{players}") < int(prob * 10000):
                            act = _pick_action_of_kind(legal, kind="BET", prefer_max=False) or _pick_action_of_kind(legal, kind="RAISE", prefer_max=False)
                            if act:
                                return act
                    else:
                        stab_prob = (0.22 * style_factor) * (3.0 / max(3, players))
                        if _rng_pct(f"stab:{seat_id}:{street}:{players}") < int(stab_prob * 10000):
                            act = _pick_action_of_kind(legal, kind="BET", prefer_max=False) or _pick_action_of_kind(legal, kind="RAISE", prefer_max=False)
                            if act:
                                return act
                    if check_act:
                        return check_act
                    if fold_act:
                        return fold_act

                # 面对下注：基于价格与栈比例
                if to_call > 0:
                    pot_den = max(pot_chips + to_call, 1)
                    price_frac = to_call / max(pot_chips, to_call, 1)
                    pot_odds = to_call / pot_den
                    stack_frac = to_call / max(total_stack, 1) if total_stack > 0 else 0.0
                    eq_thresh = {"FLOP": 0.32, "TURN": 0.30, "RIVER": 0.28}.get(street, 0.30)

                    if stack_frac > 0.45 or pot_odds > eq_thresh + 0.18:
                        if fold_act:
                            return fold_act

                    raise_act = _pick_action_of_kind(legal, kind="RAISE", prefer_max=False)
                    if price_frac <= 0.25 and raise_act and _rng_pct(f"raise_small:{seat_id}:{street}") < int((0.12 + 0.15 * base_agg) * 10000):
                        return raise_act
                    if price_frac <= 0.45 and raise_act and _rng_pct(f"raise_probe:{seat_id}:{street}") < int((0.06 + 0.10 * base_agg) * 10000):
                        return raise_act

                    # 调用概率基于 pot odds
                    if pot_odds <= eq_thresh - 0.05:
                        call_prob = 0.80
                    elif pot_odds <= eq_thresh + 0.02:
                        call_prob = 0.60
                    elif pot_odds <= eq_thresh + 0.10:
                        call_prob = 0.42
                    elif pot_odds <= eq_thresh + 0.18:
                        call_prob = 0.28
                    else:
                        call_prob = 0.12
                    call_prob *= style_factor

                    if call_act and _rng_pct(f"call_post:{seat_id}:{street}:{pot_odds}") < int(call_prob * 10000):
                        return call_act
                    if fold_act:
                        return fold_act

        # 通用兜底
        if call_act is not None:
            # 紧凶在巨大代价时直接弃牌
            if total_stack > 0 and ((style_norm == "tight" and to_call > total_stack * 0.12) or (style_norm != "tight" and to_call > total_stack * 0.3)):
                if fold_act:
                    return fold_act
            return call_act

        if check_act is not None:
            return check_act
        if fold_act is not None:
            return fold_act

        return legal[0]

    return _policy


def make_system_policy(*, seat_id: int, seed: int) -> PolicyFn:
    # Slightly more aggressive balanced profile.
    return make_rule_policy(style="balanced", aggression=0.7, seat_id=seat_id, seed=seed)
