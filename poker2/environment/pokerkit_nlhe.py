from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pokerkit import Automation, NoLimitTexasHoldem
from pokerkit.state import Mode, State

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.protocol.enums import (
    ACTION_KIND_VALUES,
    ACTION_SOURCE_ID_VALUES,
    FORCED_BETS_KIND_ORDERED,
    MAPPING_REASON_CODE_VALUES,
    MW_RUNG_ID_VALUES,
    STREET_DEALT_VALUES,
    STREET_ORDERED,
    STREET_VALUES,
)
from poker2.protocol.event_model import event_model_id as compute_event_model_id
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.legal_actions import LegalActionsError, legal_actions_and_digest
from poker2.protocol.mw_context import MWContextError, mw_context_digest
from poker2.protocol.rake import RakeError, compute_total_rake_chips
from poker2.protocol.rounding import RoundingError, round_div_int
from poker2.protocol.action_adapter import (
    ActionAdapterError,
    action_adapter_id as compute_action_adapter_id,
    validate_action_adapter_spec,
)
from poker2.protocol.action_bins import (
    ActionBinsError,
    action_bins_id as compute_action_bins_id,
    validate_action_bins_spec,
)
from poker2.protocol.ruleset import RuleSetError, ruleset_id, validate_ruleset
from poker2.protocol.snapshot import SnapshotError, street_from_pokerkit_street_index, validate_snapshot_min_fields
from poker2.protocol.state_hash import state_hash as compute_state_hash
from poker2.protocol.mw_ladder import load_mw_ladder_spec, validate_mw_ladder_spec
from poker2.runtime.mw_ladder_registry import MWLadderRegistryError, build_mw_ladder_registry


@dataclass
class EnvironmentError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


PolicyFn = Callable[[dict[str, Any]], dict[str, Any]]


def _hand_id(*, run_id: str, hand_seq: int, strict_mode: bool) -> str:
    return sha256_hex(
        canonicalize_json_bytes({"run_id": run_id, "hand_seq": hand_seq}, strict_mode=strict_mode)
    )


def _rotate_seats_clockwise(seats_in_hand: list[int], *, button_seat: int) -> list[int]:
    if button_seat not in seats_in_hand:
        raise EnvironmentError("BUTTON_NOT_IN_HAND", "button_seat must be included in seats_in_hand")
    idx = seats_in_hand.index(button_seat)
    return [*seats_in_hand[idx:], *seats_in_hand[:idx]]


def _rotate_button_seat(seats_in_hand: list[int], *, button_seat: int) -> int:
    if button_seat not in seats_in_hand:
        raise EnvironmentError("BUTTON_NOT_IN_HAND", "button_seat must be included in seats_in_hand")
    if len(seats_in_hand) < 2:
        raise EnvironmentError("VALUE_ERROR", "seats_in_hand must include >=2 seats")
    idx = seats_in_hand.index(button_seat)
    return seats_in_hand[(idx + 1) % len(seats_in_hand)]


def _digest(obj: Any, *, strict_mode: bool) -> dict[str, str]:
    digest_hex = sha256_hex(canonicalize_json_bytes(obj, strict_mode=strict_mode))
    digest = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest, strict_mode=True)
    return digest


def _load_mw_rungs(mw_ladder_id: str | None, *, strict_mode: bool) -> list[dict[str, Any]] | None:
    if mw_ladder_id is None:
        return None
    try:
        registry = build_mw_ladder_registry(strict_mode=strict_mode)
        entry = registry.get(mw_ladder_id)
        if entry is None:
            raise EnvironmentError("MW_LADDER_UNRESOLVABLE", "mw_ladder_id not found in registry", {"mw_ladder_id": mw_ladder_id})
        spec_path = Path(str(entry["mw_ladder_ref"]).removeprefix("path:"))
        spec = load_mw_ladder_spec(spec_path)
        validate_mw_ladder_spec(spec, strict_mode=strict_mode)
        rungs = spec.get("rungs")
        return [r for r in rungs if isinstance(r, dict)] if isinstance(rungs, list) else None
    except MWLadderRegistryError as e:
        raise EnvironmentError(e.code, e.message, e.details) from e


def _rung_matches_predicate(rung: dict[str, Any], *, players_alive_count: int) -> bool:
    pred = rung.get("applicability_predicate") or {}
    kind = pred.get("predicate_kind")
    if kind == "players_range":
        mn = pred.get("min_players")
        mx = pred.get("max_players")
        if mn is not None and players_alive_count < int(mn):
            return False
        if mx is not None and players_alive_count > int(mx):
            return False
        return True
    return True


def _select_mw_rung_id(rungs: list[dict[str, Any]] | None, *, players_alive_count: int) -> str | None:
    if rungs is None:
        return None
    for rung in rungs:
        rung_id = rung.get("rung_id")
        if rung_id not in MW_RUNG_ID_VALUES:
            continue
        if _rung_matches_predicate(rung, players_alive_count=players_alive_count):
            return rung_id
    return None


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise EnvironmentError("TYPE_ERROR", f"{field} must be int, got bool")
    if not isinstance(value, int):
        raise EnvironmentError("TYPE_ERROR", f"{field} must be int, got {type(value).__name__}")
    return value


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise EnvironmentError("TYPE_ERROR", f"{field} must be str, got {type(value).__name__}")
    return value


def _canonical_action(kind: str, target_total_commit_chips: int) -> dict[str, Any]:
    return {"kind": kind, "target_total_commit_chips": target_total_commit_chips}


def _cap_raise_bounds(
    *,
    snapshot: dict[str, Any],
    ruleset: dict[str, Any],
) -> tuple[int | None, int | None, bool, int | None]:
    """
    Apply a deterministic raise ceiling (3.1.1) to avoid runaway all‑in wars while
    keeping legality consistent with action bins. The cap is derived from stack /
    pot / blind scale and only touches canonicalize→legalize; no alternate hash
    inputs are introduced.
    """
    min_raise = snapshot.get("min_raise_to_chips")
    max_raise = snapshot.get("max_raise_to_chips")
    if min_raise is None or max_raise is None:
        return min_raise, max_raise, False, None

    street = snapshot.get("street")
    pot = _as_int(snapshot.get("pot_chips"), field="Snapshot.pot_chips")
    to_call = _as_int(snapshot.get("to_call_chips"), field="Snapshot.to_call_chips")
    actor_commit = _as_int(snapshot.get("actor_commit_chips"), field="Snapshot.actor_commit_chips")
    actor_stack = _as_int(snapshot.get("actor_stack_chips"), field="Snapshot.actor_stack_chips")
    bb = _as_int((ruleset.get("blinds") or {}).get("bb_chips"), field="ruleset.blinds.bb_chips")

    total_stack = actor_commit + actor_stack
    call_target = actor_commit + to_call

    try:
        players_alive = int(snapshot.get("players_alive_count", 0) or 0)
    except Exception:
        players_alive = 0

    # 仅在「多人 + 巨额底池」情形下收紧加注上限，其余保持原始 max_raise 以避免统计噪声。
    multiway_hot = players_alive >= 5
    pot_big = pot >= 20 * bb or to_call >= 8 * bb
    spr_low = pot > 0 and (actor_stack / pot) <= 2.0
    enable_cap = multiway_hot and pot_big and spr_low

    if not enable_cap:
        return min_raise, max_raise, False, None

    if street == "PREFLOP":
        stack_cap = (total_stack * 22) // 100  # ≤22% 总码量
        pot_cap = (pot * 70) // 100  # ≤0.7 pot
        bb_cap = 6 * bb
        mult_cap = to_call * 2 + 3 * bb
    else:
        stack_cap = (total_stack * 26) // 100  # ≤26% 总码量
        pot_cap = (pot * 75) // 100  # ≤0.75 pot
        bb_cap = 9 * bb
        mult_cap = to_call * 2 + 2 * bb

    add_cap = min(actor_stack, max(stack_cap, pot_cap, bb_cap, mult_cap))
    capped_max = min(max_raise, call_target + add_cap)
    if capped_max < min_raise:
        # Cap too tight → 禁止本轮继续加注
        return None, None, True, capped_max
    return min_raise, capped_max, capped_max != max_raise, capped_max


def _bin_targets_from_action_bins(
    *,
    snapshot: dict[str, Any],
    action_bins: dict[str, Any],
    rounding_mode: str | None,
    strict_mode: bool,
) -> tuple[list[int], list[int]]:
    bet_bins = action_bins.get("bet_bins_ppm") or []
    raise_bins = action_bins.get("raise_bins_ppm") or []
    if not bet_bins and not raise_bins:
        return [], []

    if rounding_mode is None:
        if strict_mode:
            raise EnvironmentError("MISSING_ROUNDING_MODE", "action_adapter.rounding_mode required for action_bins bins")
        rounding_mode = "floor"

    pot = _as_int(snapshot.get("pot_chips"), field="Snapshot.pot_chips")
    to_call = _as_int(snapshot.get("to_call_chips"), field="Snapshot.to_call_chips")
    actor_commit = _as_int(snapshot.get("actor_commit_chips"), field="Snapshot.actor_commit_chips")
    min_raise_to = snapshot.get("min_raise_to_chips")
    max_raise_to = snapshot.get("max_raise_to_chips")
    if (min_raise_to is None) != (max_raise_to is None):
        raise EnvironmentError("VALUE_ERROR", "min_raise_to_chips and max_raise_to_chips must both be null or int")

    bet_targets: set[int] = set()
    raise_targets: set[int] = set()
    try:
        if to_call == 0:
            for ppm in bet_bins:
                if isinstance(ppm, bool) or not isinstance(ppm, int):
                    raise EnvironmentError("TYPE_ERROR", "bet_bins_ppm must contain ints")
                if ppm < 0:
                    raise EnvironmentError("VALUE_ERROR", "bet_bins_ppm must be >= 0")
                add = round_div_int(pot * ppm, 1_000_000, rounding_mode=rounding_mode)
                target = actor_commit + add
                if min_raise_to is not None and max_raise_to is not None:
                    if min_raise_to <= target <= max_raise_to:
                        bet_targets.add(target)
        else:
            call_target = actor_commit + to_call
            for ppm in raise_bins:
                if isinstance(ppm, bool) or not isinstance(ppm, int):
                    raise EnvironmentError("TYPE_ERROR", "raise_bins_ppm must contain ints")
                if ppm < 0:
                    raise EnvironmentError("VALUE_ERROR", "raise_bins_ppm must be >= 0")
                add = round_div_int(pot * ppm, 1_000_000, rounding_mode=rounding_mode)
                target = call_target + add
                if min_raise_to is not None and max_raise_to is not None:
                    if min_raise_to <= target <= max_raise_to:
                        raise_targets.add(target)
    except RoundingError as e:
        raise EnvironmentError(e.code, e.message) from e

    return sorted(bet_targets), sorted(raise_targets)


def _apply_reopen_on_short_allin_if_enabled(
    state: State,
    *,
    prev_completion_increment: int,
    prev_max_bet: int,
    player_index: int,
    new_round_bet: int,
    reopen_on_short_allin: bool,
) -> None:
    if not reopen_on_short_allin:
        return

    # Detect short all-in raise relative to the last full raise increment
    # (PokerKit keeps completion_betting_or_raising_amount as the max so far).
    increment = new_round_bet - prev_max_bet
    if increment <= 0:
        return
    if state.stacks[player_index] != 0:
        return
    if increment >= prev_completion_increment:
        return

    # Treat short all-in as a full raise (ARCHIETECTURE.md 3.2.3 when reopen_on_short_allin=true):
    # - reopen raising for previously-acted players
    # - update the "last full raise increment" to this short increment
    state.acted_player_indices.clear()
    state.acted_player_indices.add(player_index)
    state.consecutive_all_in_completion_betting_or_raising_amounts.clear()
    state.completion_betting_or_raising_amount = increment


def _derive_action_kind(
    *,
    target_total_commit_chips: int,
    actor_commit_chips: int,
    to_call_chips: int,
) -> str:
    if target_total_commit_chips < actor_commit_chips:
        raise EnvironmentError("VALUE_ERROR", "target_total_commit_chips below actor_commit_chips")

    if to_call_chips == 0:
        if target_total_commit_chips == actor_commit_chips:
            return "CHECK"
        return "BET"

    call_target = actor_commit_chips + to_call_chips
    if target_total_commit_chips == actor_commit_chips:
        return "FOLD"
    if target_total_commit_chips == call_target:
        return "CALL"
    if target_total_commit_chips > call_target:
        return "RAISE"
    raise EnvironmentError("VALUE_ERROR", "target_total_commit_chips below CALL target (illegal partial call)")


def _canonicalize_action(
    proposed_action: dict[str, Any],
    *,
    snapshot: dict[str, Any],
    strict_mode: bool,
) -> tuple[dict[str, Any], str | None]:
    # Returns (canonicalized_action, reason_code_if_changed)
    kind_in = _as_str(proposed_action.get("kind"), field="proposed_action.kind")
    target_in = _as_int(
        proposed_action.get("target_total_commit_chips"),
        field="proposed_action.target_total_commit_chips",
    )
    if kind_in not in ACTION_KIND_VALUES:
        raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported proposed_action.kind: {kind_in!r}")

    actor_commit = _as_int(snapshot.get("actor_commit_chips"), field="Snapshot.actor_commit_chips")
    to_call = _as_int(snapshot.get("to_call_chips"), field="Snapshot.to_call_chips")

    # Enforce unique targets for FOLD/CHECK/CALL.
    if kind_in in ("FOLD", "CHECK", "CALL"):
        if kind_in == "CALL":
            expected = actor_commit + to_call
            if to_call <= 0:
                raise EnvironmentError("VALUE_ERROR", "CALL proposed when to_call_chips==0")
        else:
            expected = actor_commit
            if kind_in == "CHECK" and to_call != 0:
                raise EnvironmentError("VALUE_ERROR", "CHECK proposed when to_call_chips>0")
            if kind_in == "FOLD" and to_call <= 0:
                raise EnvironmentError("VALUE_ERROR", "FOLD proposed when to_call_chips==0")

        if target_in != expected:
            if strict_mode:
                raise EnvironmentError(
                    "CANONICALIZE_TARGET_MISMATCH",
                    "FOLD/CHECK/CALL target_total_commit_chips must be uniquely derived from Snapshot",
                    {"expected": expected, "observed": target_in, "kind": kind_in},
                )
            return _canonical_action(kind_in, expected), "illegal_action"
        return _canonical_action(kind_in, expected), None

    # For BET/RAISE, the kind is redundant and must match the derived kind.
    derived_kind = _derive_action_kind(
        target_total_commit_chips=target_in,
        actor_commit_chips=actor_commit,
        to_call_chips=to_call,
    )
    if kind_in != derived_kind:
        if strict_mode:
            raise EnvironmentError(
                "CANONICALIZE_KIND_MISMATCH",
                "BET/RAISE kind must match derived kind from Snapshot and target_total_commit_chips",
                {"expected": derived_kind, "observed": kind_in, "target_total_commit_chips": target_in},
            )
        return _canonical_action(derived_kind, target_in), "kind_override"
    return _canonical_action(kind_in, target_in), None


def _action_in_set(action: dict[str, Any], actions: list[dict[str, Any]]) -> bool:
    key = (action.get("kind"), action.get("target_total_commit_chips"))
    for a in actions:
        if (a.get("kind"), a.get("target_total_commit_chips")) == key:
            return True
    return False


def _fallback_conservative_check_call(snapshot: dict[str, Any]) -> dict[str, Any]:
    actor_commit = _as_int(snapshot.get("actor_commit_chips"), field="Snapshot.actor_commit_chips")
    to_call = _as_int(snapshot.get("to_call_chips"), field="Snapshot.to_call_chips")
    if to_call == 0:
        return _canonical_action("CHECK", actor_commit)
    return _canonical_action("CALL", actor_commit + to_call)


def _fallback_snap_nearest(
    proposed: dict[str, Any],
    *,
    legal_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    kind = _as_str(proposed.get("kind"), field="proposed.kind")
    target = _as_int(proposed.get("target_total_commit_chips"), field="proposed.target_total_commit_chips")
    candidates = [a for a in legal_actions if a.get("kind") == kind]
    if not candidates:
        return {}
    best = min(candidates, key=lambda a: (abs(a["target_total_commit_chips"] - target), a["target_total_commit_chips"]))
    return _canonical_action(best["kind"], best["target_total_commit_chips"])


def _fallback_clamp_then_snap(
    proposed: dict[str, Any],
    *,
    snapshot: dict[str, Any],
    legal_actions: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    kind = _as_str(proposed.get("kind"), field="proposed.kind")
    target = _as_int(proposed.get("target_total_commit_chips"), field="proposed.target_total_commit_chips")
    if kind not in ("BET", "RAISE"):
        snapped = _fallback_snap_nearest(proposed, legal_actions=legal_actions)
        return snapped, False

    min_raise = snapshot.get("min_raise_to_chips")
    max_raise = snapshot.get("max_raise_to_chips")
    if min_raise is None or max_raise is None:
        snapped = _fallback_snap_nearest(proposed, legal_actions=legal_actions)
        return snapped, False

    min_raise_i = _as_int(min_raise, field="Snapshot.min_raise_to_chips")
    max_raise_i = _as_int(max_raise, field="Snapshot.max_raise_to_chips")
    clamped = min(max(target, min_raise_i), max_raise_i)
    proposed2 = _canonical_action(kind, clamped)
    snapped = _fallback_snap_nearest(proposed2, legal_actions=legal_actions)
    return snapped, clamped != target


def _legalize_action(
    proposed_action: dict[str, Any],
    canonicalized_action: dict[str, Any],
    *,
    snapshot: dict[str, Any],
    legal_actions: list[dict[str, Any]],
    fallback_mode: str,
    strict_mode: bool,
) -> tuple[dict[str, Any], str | None]:
    if _action_in_set(canonicalized_action, legal_actions):
        return canonicalized_action, None

    if strict_mode or fallback_mode == "fail_fast":
        raise EnvironmentError(
            "ILLEGAL_ACTION",
            "canonicalized_action not in legal action set",
            {"canonicalized_action": canonicalized_action},
        )

    if fallback_mode == "conservative_check_call":
        executed = _fallback_conservative_check_call(snapshot)
        if not _action_in_set(executed, legal_actions):
            raise EnvironmentError("FALLBACK_NOT_IN_SET", "conservative fallback action not in legal set")
        return executed, "conservative_fallback"

    if fallback_mode == "snap_nearest":
        executed = _fallback_snap_nearest(canonicalized_action, legal_actions=legal_actions)
        if not executed:
            executed = _fallback_conservative_check_call(snapshot)
            return executed, "conservative_fallback"
        return executed, "snap_to_bin"

    if fallback_mode == "clamp_then_snap":
        executed, clamped = _fallback_clamp_then_snap(
            canonicalized_action,
            snapshot=snapshot,
            legal_actions=legal_actions,
        )
        if not executed:
            executed = _fallback_conservative_check_call(snapshot)
            return executed, "conservative_fallback"
        return executed, "clamp" if clamped else "snap_to_bin"

    raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported fallback_mode: {fallback_mode!r}")


def _mapping_trace(
    *,
    action_adapter_id: str,
    mapping_spec_id: str | None,
    rounding_mode: str | None,
    proposed_action: dict[str, Any],
    executed_action: dict[str, Any],
    reason_code: str,
    fallback_mode_or_none: str | None,
) -> dict[str, Any]:
    if reason_code not in MAPPING_REASON_CODE_VALUES:
        raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported mapping_trace.reason_code: {reason_code!r}")

    if proposed_action == executed_action:
        reason_code = "none"
        fallback_mode_or_none = None

    delta: int | None
    if proposed_action.get("target_total_commit_chips") is None or executed_action.get("target_total_commit_chips") is None:
        delta = None
    else:
        delta = _as_int(executed_action["target_total_commit_chips"], field="executed.target_total_commit_chips") - _as_int(
            proposed_action["target_total_commit_chips"], field="proposed.target_total_commit_chips"
        )

    trace = {
        "trace_schema_id": "mapping_trace_v1",
        "action_adapter_id": action_adapter_id,
        "mapping_spec_id": mapping_spec_id,
        "rounding_mode": rounding_mode,
        "reason_code": reason_code,
        "lossy": proposed_action != executed_action,
        "delta_target_total_commit_chips": 0 if proposed_action == executed_action else delta,
        "fallback_mode": fallback_mode_or_none,
    }
    return trace


def _derived_action(*, executed_action: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    kind = _as_str(executed_action.get("kind"), field="executed_action.kind")
    if kind not in ACTION_KIND_VALUES:
        raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported executed_action.kind: {kind!r}")
    target = _as_int(executed_action.get("target_total_commit_chips"), field="executed_action.target_total_commit_chips")

    actor_commit = _as_int(snapshot.get("actor_commit_chips"), field="Snapshot.actor_commit_chips")
    actor_stack = _as_int(snapshot.get("actor_stack_chips"), field="Snapshot.actor_stack_chips")
    max_raise_to = snapshot.get("max_raise_to_chips")

    is_allin = (target == actor_commit + actor_stack) or (max_raise_to is not None and target == max_raise_to)
    return {"kind": kind, "is_allin": bool(is_allin), "target_total_commit_chips": target}


def run_single_hand_eventstream_objects(
    *,
    run_id: str,
    options_hash: str,
    seed: int,
    system_seat_id: int | None = None,
    scenario_id: str,
    schema_hash: str,
    provenance_ref: str,
    resolved_paths_digest: str,
    repro_tier: str,
    ruleset: dict[str, Any],
    triad: dict[str, Any],
    action_adapter: dict[str, Any],
    action_bins: dict[str, Any],
    mapping_spec_id: str | None,
    mw_ladder_id: str | None,
    starting_stacks_by_seat: dict[int, int],
    button_seat: int,
    opponent_suite_id: str | None = None,
    opponent_artifact_id_or_params_hash: str | None = None,
    hand_seq: int = 1,
    seat_policies: dict[int, PolicyFn] | None = None,
    policy: PolicyFn | None = None,
    strict_mode: bool = True,
) -> list[dict[str, Any]]:
    try:
        validate_action_adapter_spec(action_adapter, strict_mode=strict_mode)
        action_adapter_id = compute_action_adapter_id(action_adapter, strict_mode=strict_mode)
    except ActionAdapterError as e:
        raise EnvironmentError(e.code, e.message, e.details) from e

    fallback_mode = action_adapter["fallback_policy"]["mode"]
    if not isinstance(fallback_mode, str):  # pragma: no cover
        raise EnvironmentError("TYPE_ERROR", "fallback_policy.mode must be string")

    try:
        validate_action_bins_spec(action_bins, strict_mode=strict_mode)
        action_bins_id = compute_action_bins_id(action_bins, strict_mode=strict_mode)
    except ActionBinsError as e:
        raise EnvironmentError(e.code, e.message, e.details) from e

    triad_bins = triad.get("action_bins_id") if isinstance(triad, dict) else None
    if triad_bins != action_bins_id:
        raise EnvironmentError(
            "ID_MISMATCH",
            "triad.action_bins_id does not match action_bins_id",
            {"triad_action_bins_id": triad_bins, "action_bins_id": action_bins_id},
        )

    if system_seat_id is None:
        try:
            system_seat_id = min(starting_stacks_by_seat.keys())
        except Exception:
            system_seat_id = None

    if policy is None:
        policy = lambda ctx: _fallback_conservative_check_call(ctx["snapshot"])
    seat_policies = seat_policies or {}

    try:
        validate_ruleset(ruleset, strict_mode=strict_mode)
    except RuleSetError as e:
        raise EnvironmentError(e.code, e.message) from e

    r_id = ruleset_id(ruleset, strict_mode=strict_mode)

    mw_rungs = _load_mw_rungs(mw_ladder_id, strict_mode=strict_mode) if mw_ladder_id is not None else None

    if not isinstance(starting_stacks_by_seat, dict) or not starting_stacks_by_seat:
        raise EnvironmentError("TYPE_ERROR", "starting_stacks_by_seat must be non-empty object")

    seats_in_hand = sorted(starting_stacks_by_seat.keys())
    if strict_mode and (sorted(set(seats_in_hand)) != seats_in_hand):
        raise EnvironmentError("VALUE_ERROR", "seats_in_hand must be unique and sorted")
    if strict_mode and not all(isinstance(s, int) for s in seats_in_hand):
        raise EnvironmentError("TYPE_ERROR", "seat ids must be int")

    seats_clockwise = _rotate_seats_clockwise(seats_in_hand, button_seat=button_seat)
    seat_to_index = {s: i for i, s in enumerate(seats_clockwise)}
    index_to_seat = {i: s for s, i in seat_to_index.items()}

    starting_stacks_by_index = tuple(starting_stacks_by_seat[index_to_seat[i]] for i in range(len(seats_clockwise)))

    blinds = ruleset["blinds"]
    sb = _as_int(blinds["sb_chips"], field="ruleset.blinds.sb_chips")
    bb = _as_int(blinds["bb_chips"], field="ruleset.blinds.bb_chips")

    player_count = len(seats_clockwise)
    if player_count < 2:
        raise EnvironmentError("VALUE_ERROR", "player_count must be >= 2")
    if player_count >= 3 and strict_mode and mw_ladder_id is None:
        raise EnvironmentError("MISSING_FIELDS", "mw_ladder_id is required when multi-way may occur", {})
    if player_count >= 3 and strict_mode and mw_rungs is None:
        raise EnvironmentError("MW_LADDER_UNRESOLVABLE", "mw ladder rungs could not be loaded", {"mw_ladder_id": mw_ladder_id})

    if player_count == 2:
        sb_index = seat_to_index[button_seat]
        other_seat = next(s for s in seats_in_hand if s != button_seat)
        bb_index = seat_to_index[other_seat]
        # PokerKit reverses blinds-or-straddles order for HU opener logic; swap values to keep
        # our seat-to-index mapping stable (button posts SB and acts first preflop).
        raw_blinds_or_straddles: Any = {sb_index: bb, bb_index: sb}
    else:
        sb_index = 1
        bb_index = 2
        raw_blinds_or_straddles = {sb_index: sb, bb_index: bb}

    ante = ruleset.get("ante")
    raw_antes: Any = 0
    if ante is None:
        raw_antes = 0
    elif isinstance(ante, dict):
        kind = ante.get("kind")
        if kind == "uniform":
            raw_antes = _as_int(ante.get("ante_chips"), field="ruleset.ante.ante_chips")
        elif kind == "by_seat":
            by_seat = ante.get("by_seat_ante_chips")
            if not isinstance(by_seat, dict):
                raise EnvironmentError("TYPE_ERROR", "ruleset.ante.by_seat_ante_chips must be object")
            vec = [0 for _ in range(player_count)]
            for seat_key, amt in by_seat.items():
                if not isinstance(seat_key, str) or not seat_key.isdigit():
                    raise EnvironmentError("TYPE_ERROR", "by_seat_ante_chips keys must be decimal strings")
                seat = int(seat_key)
                if seat not in seat_to_index:
                    continue
                vec[seat_to_index[seat]] = _as_int(amt, field=f"ruleset.ante.by_seat_ante_chips[{seat_key}]")
            raw_antes = tuple(vec)
        else:
            raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported ruleset.ante.kind: {kind!r}")
    else:
        raise EnvironmentError("TYPE_ERROR", "ruleset.ante must be null or object")

    # PokerKit uses global random.shuffle; isolate RNG state for determinism.
    rnd_state = random.getstate()
    random.seed(seed)
    try:
        state = NoLimitTexasHoldem.create_state(
            automations=(
                Automation.ANTE_POSTING,
                Automation.BET_COLLECTION,
                Automation.BLIND_OR_STRADDLE_POSTING,
                Automation.CARD_BURNING,
                Automation.HOLE_DEALING,
                Automation.BOARD_DEALING,
                Automation.RUNOUT_COUNT_SELECTION,
                Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
                Automation.HAND_KILLING,
                Automation.CHIPS_PUSHING,
                Automation.CHIPS_PULLING,
            ),
            ante_trimming_status=False,
            raw_antes=raw_antes,
            raw_blinds_or_straddles=raw_blinds_or_straddles,
            min_bet=bb,
            raw_starting_stacks=starting_stacks_by_index,
            player_count=player_count,
            mode=Mode.CASH_GAME,
            rake=lambda amount, _state: (0, amount),
        )
    finally:
        random.setstate(rnd_state)

    events: list[dict[str, Any]] = []
    pot_updates: list[dict[str, Any]] = []

    hid = _hand_id(run_id=run_id, hand_seq=hand_seq, strict_mode=strict_mode)
    events.append(
        {
            "event": "HandStart",
            "hand_id": hid,
            "hand_seq": hand_seq,
            "button_seat": button_seat,
            "seats_in_hand": seats_in_hand,
            "ruleset_id": r_id,
            "triad": triad,
            "schema_hash": schema_hash,
            "options_hash": options_hash,
            "provenance_ref": provenance_ref,
            "opponent_suite_id": opponent_suite_id,
            "opponent_artifact_id_or_params_hash": opponent_artifact_id_or_params_hash,
        }
    )

    forced_bets: dict[str, dict[int, int]] = {k: {} for k in FORCED_BETS_KIND_ORDERED}
    forced_total_by_seat: dict[int, int] = {s: 0 for s in seats_in_hand}

    bets_round = [0 for _ in range(player_count)]
    rake_base_pot_chips = 0
    streets_dealt: set[str] = set()
    pushed_from_pot_by_index = [0 for _ in range(player_count)]

    pending_initial_pot_updates: list[dict[str, Any]] = []

    def emit_pot_update(
        *,
        pot_chips_delta: int,
        rake_chips_delta: int,
        buffer: list[dict[str, Any]] | None = None,
    ) -> None:
        evt = {
            "event": "PotUpdate",
            "pot_chips_delta": pot_chips_delta,
            "rake_chips_delta": rake_chips_delta,
        }
        pot_updates.append(evt)
        if buffer is None:
            events.append(evt)
        else:
            buffer.append(evt)

    def process_op(op: Any, *, buffer_pot_updates: list[dict[str, Any]] | None = None) -> None:
        nonlocal rake_base_pot_chips

        name = op.__class__.__name__
        if name == "BlindOrStraddlePosting":
            idx = op.player_index
            amt = int(op.amount)
            seat = index_to_seat[idx]
            kind = "straddle"
            if idx == sb_index:
                kind = "sb"
            elif idx == bb_index:
                kind = "bb"
            forced_bets[kind][seat] = forced_bets[kind].get(seat, 0) + amt
            forced_total_by_seat[seat] = forced_total_by_seat.get(seat, 0) + amt
            bets_round[idx] += amt
            emit_pot_update(pot_chips_delta=amt, rake_chips_delta=0, buffer=buffer_pot_updates)
            return

        if name == "AntePosting":
            idx = op.player_index
            amt = int(op.amount)
            seat = index_to_seat[idx]
            forced_bets["ante"][seat] = forced_bets["ante"].get(seat, 0) + amt
            forced_total_by_seat[seat] = forced_total_by_seat.get(seat, 0) + amt
            bets_round[idx] += amt
            emit_pot_update(pot_chips_delta=amt, rake_chips_delta=0, buffer=buffer_pot_updates)
            return

        if name == "CheckingOrCalling":
            idx = op.player_index
            amt = int(op.amount)
            if amt:
                bets_round[idx] += amt
                emit_pot_update(pot_chips_delta=amt, rake_chips_delta=0, buffer=buffer_pot_updates)
            return

        if name == "CompletionBettingOrRaisingTo":
            idx = op.player_index
            new_bet = int(op.amount)
            delta = new_bet - bets_round[idx]
            if delta < 0:
                raise EnvironmentError("LEDGER_ERROR", "CompletionBettingOrRaisingTo decreased round bet")
            bets_round[idx] = new_bet
            if delta:
                emit_pot_update(pot_chips_delta=delta, rake_chips_delta=0, buffer=buffer_pot_updates)
            return

        if name == "BetCollection":
            collected = tuple(int(x) for x in op.bets)
            if len(collected) != player_count:
                raise EnvironmentError("LEDGER_ERROR", "BetCollection.bets length mismatch")
            returned = sum(bets_round) - sum(collected)
            if returned < 0:
                raise EnvironmentError("LEDGER_ERROR", "negative returned chips in BetCollection")
            if returned:
                emit_pot_update(pot_chips_delta=-returned, rake_chips_delta=0, buffer=buffer_pot_updates)
            rake_base_pot_chips += sum(collected)
            for i in range(player_count):
                bets_round[i] = 0
            return

        if name == "BoardDealing":
            cards_len = len(op.cards)
            street: str | None = None
            if cards_len == 3:
                street = "FLOP"
            elif cards_len == 1 and "FLOP" in streets_dealt and "TURN" not in streets_dealt:
                street = "TURN"
            elif cards_len == 1 and "TURN" in streets_dealt and "RIVER" not in streets_dealt:
                street = "RIVER"
            if street and street not in streets_dealt:
                streets_dealt.add(street)
                if street not in STREET_DEALT_VALUES:
                    raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported StreetDealt.street: {street!r}")
                events.append({"event": "StreetDealt", "street": street})
            return

        if name == "ChipsPushing":
            amounts = tuple(int(x) for x in op.amounts)
            if len(amounts) != player_count:
                raise EnvironmentError("LEDGER_ERROR", "ChipsPushing.amounts length mismatch")
            for i, amt in enumerate(amounts):
                if amt:
                    pushed_from_pot_by_index[i] += amt
            return

        # Ignore other operations for the event model; they are reflected via
        # higher-level events and HandEnd closure.
        return

    # Process all operations up-front (forced bets + hole dealing).
    op_idx = 0
    while op_idx < len(state.operations):
        process_op(state.operations[op_idx], buffer_pot_updates=pending_initial_pot_updates)
        op_idx += 1

    # Emit ForcedBets events in stable kind order.
    for kind in FORCED_BETS_KIND_ORDERED:
        by_seat = forced_bets.get(kind) or {}
        by_seat_pos = {str(seat): amt for seat, amt in by_seat.items() if amt > 0}
        if strict_mode and not by_seat_pos:
            continue
        if not by_seat_pos:
            continue
        events.append({"event": "ForcedBets", "kind": kind, "by_seat_amount_chips": by_seat_pos})

    # Initial pot updates must appear after ForcedBets and before the first DecisionPoint.
    events.extend(pending_initial_pot_updates)

    # Decision loop.
    decision_id = 0
    current_street_index = state.street_index
    raise_count_in_street = 0
    last_raiser_by_street: dict[str, int | None] = {s: None for s in STREET_ORDERED}
    street_raise_count: dict[str, int] = {s: 0 for s in STREET_ORDERED}
    max_raise_levels = ruleset.get("max_raise_levels")
    try:
        max_raise_levels = int(max_raise_levels) if max_raise_levels is not None else 4
    except Exception:
        max_raise_levels = 4
    if max_raise_levels < 0:
        max_raise_levels = 4
    while state.actor_index is not None:
        actor_index = state.actor_index
        if actor_index is None:  # pragma: no cover
            break
        actor_seat = index_to_seat[actor_index]

        street = street_from_pokerkit_street_index(state.street_index)
        if street not in STREET_VALUES:
            raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported street: {street!r}")
        if state.street_index != current_street_index:
            current_street_index = state.street_index
            raise_count_in_street = 0

        players_alive_count = sum(1 for s in state.statuses if s)
        pot_chips = int(state.total_pot_amount)
        to_call = state.checking_or_calling_amount
        if to_call is None:
            raise EnvironmentError("ENGINE_ERROR", "missing checking_or_calling_amount at DecisionPoint")
        to_call_chips = int(to_call)

        actor_stack = int(state.stacks[actor_index])
        actor_commit = int(starting_stacks_by_index[actor_index]) - actor_stack
        if actor_commit < 0:
            raise EnvironmentError("LEDGER_ERROR", "actor_commit_chips negative")

        min_completion = state.min_completion_betting_or_raising_to_amount
        max_completion = state.max_completion_betting_or_raising_to_amount

        min_raise_to_chips: int | None = None
        max_raise_to_chips: int | None = None

        # Limit raise levels dynamically for deep multiway pots to avoid rake-cap blowups.
        effective_max_raise_levels = max_raise_levels
        if state.street_index == 0 and players_alive_count >= 5:
            effective_max_raise_levels = min(effective_max_raise_levels, 2)
        elif state.street_index >= 1 and players_alive_count >= 5:
            effective_max_raise_levels = min(effective_max_raise_levels, 1)

        if actor_stack > to_call_chips and min_completion is not None and max_completion is not None:
            round_bet = int(state.bets[actor_index])
            min_raise_to_chips = actor_commit + (int(min_completion) - round_bet)
            max_raise_to_chips = actor_commit + (int(max_completion) - round_bet)
            if max_raise_to_chips != actor_commit + actor_stack:
                max_raise_to_chips = actor_commit + actor_stack

        if raise_count_in_street >= effective_max_raise_levels:
            min_raise_to_chips = None
            max_raise_to_chips = None

        snapshot: dict[str, Any] = {
            "street": street,
            "actor_seat": actor_seat,
            "players_alive_count": players_alive_count,
            "pot_chips": pot_chips,
            "to_call_chips": to_call_chips,
            "actor_commit_chips": actor_commit,
            "actor_stack_chips": actor_stack,
            "min_raise_to_chips": min_raise_to_chips,
            "max_raise_to_chips": max_raise_to_chips,
        }

        # 3.1.1 canonicalize→legalize: apply deterministic raise ceiling to avoid runaway jams.
        min_raise_to_chips, max_raise_to_chips, capped, cap_to = _cap_raise_bounds(snapshot=snapshot, ruleset=ruleset)
        snapshot["min_raise_to_chips"] = min_raise_to_chips
        snapshot["max_raise_to_chips"] = max_raise_to_chips
        if capped:
            snapshot["raise_cap_to_chips"] = cap_to

        bet_targets, raise_targets = _bin_targets_from_action_bins(
            snapshot=snapshot,
            action_bins=action_bins,
            rounding_mode=action_adapter.get("rounding_mode") if isinstance(action_adapter, dict) else None,
            strict_mode=strict_mode,
        )

        try:
            legal_actions, legal_digest = legal_actions_and_digest(
                snapshot,
                action_bins=action_bins,
                bet_targets=bet_targets,
                raise_targets=raise_targets,
                strict_mode=strict_mode,
            )
        except LegalActionsError as e:
            raise EnvironmentError(e.code, e.message) from e

        observation_view: dict[str, Any] = {
            "observation_schema_id": "observation_view_v1",
            "street": street,
            "button_seat": button_seat,
            "actor_seat": actor_seat,
            "seats_in_hand": seats_in_hand,
            "stacks_by_seat": {str(index_to_seat[i]): int(state.stacks[i]) for i in range(player_count)},
            "commits_by_seat": {
                str(index_to_seat[i]): int(starting_stacks_by_index[i]) - int(state.stacks[i])
                for i in range(player_count)
            },
            "board_cards": [str(c) for board in state.board_cards for c in board],
            "hole_cards_by_seat": {
                str(index_to_seat[i]): ([str(c) for c in state.hole_cards[i]] if i == actor_index else None)
                for i in range(player_count)
            },
            "last_raiser_by_street": {k: v for k, v in last_raiser_by_street.items()},
            "street_raise_count": {k: int(v) for k, v in street_raise_count.items()},
        }
        obs_digest = _digest(observation_view, strict_mode=strict_mode)

        snapshot["legal_actions_digest"] = legal_digest
        snapshot["observation_digest"] = obs_digest

        try:
            validate_snapshot_min_fields(snapshot, strict_mode=strict_mode)
        except SnapshotError as e:
            raise EnvironmentError(e.code, e.message) from e

        state_hash = compute_state_hash(
            ruleset_id=r_id,
            triad=triad,
            schema_hash=schema_hash,
            snapshot_min_fields=snapshot,
            strict_mode=strict_mode,
        )

        mw_rung_id: str | None = None
        if players_alive_count >= 3:
            mw_rung_id = _select_mw_rung_id(mw_rungs, players_alive_count=players_alive_count)
            if mw_rung_id is None:
                if strict_mode:
                    raise EnvironmentError(
                        "MW_RUNG_UNSELECTABLE", "no mw rung matched players_alive_count", {"players_alive_count": players_alive_count}
                    )
                mw_rung_id = "baseline"
            if mw_rung_id not in MW_RUNG_ID_VALUES:
                raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported rung_id: {mw_rung_id!r}")

        decision_id += 1
        events.append(
            {
                "event": "DecisionPoint",
                "decision_id": decision_id,
                "state_hash": state_hash,
                "legal_actions_digest": legal_digest,
                "snapshot_payload": snapshot,
                "observation_view_payload": observation_view,
            }
        )

        seat_id = index_to_seat[actor_index]
        policy_fn = seat_policies.get(seat_id, policy)
        proposed_action = policy_fn(
            {
                "decision_id": decision_id,
                "state_hash": state_hash,
                "snapshot": snapshot,
                "observation": observation_view,
                "legal_actions": legal_actions,
                "seat_id": seat_id,
                "mw_rung_id": mw_rung_id,
                "ruleset": ruleset,
            }
        )
        if not isinstance(proposed_action, dict):
            raise EnvironmentError("TYPE_ERROR", "policy must return a CanonicalAction object")
        if proposed_action.get("kind") not in ACTION_KIND_VALUES:
            raise EnvironmentError("UNSUPPORTED_VALUE", f"policy returned unsupported kind: {proposed_action.get('kind')!r}")

        canonicalized_action, canon_reason = _canonicalize_action(
            proposed_action,
            snapshot=snapshot,
            strict_mode=strict_mode,
        )

        executed_action, legalize_reason = _legalize_action(
            proposed_action,
            canonicalized_action,
            snapshot=snapshot,
            legal_actions=legal_actions,
            fallback_mode=fallback_mode,
            strict_mode=strict_mode,
        )

        if canon_reason and legalize_reason:
            reason_code = legalize_reason
            fallback_mode_or_none = fallback_mode
        elif legalize_reason:
            reason_code = legalize_reason
            fallback_mode_or_none = fallback_mode
        elif canon_reason:
            reason_code = canon_reason
            fallback_mode_or_none = None
        else:
            reason_code = "none"
            fallback_mode_or_none = None

        mapping_trace = _mapping_trace(
            action_adapter_id=action_adapter_id,
            mapping_spec_id=mapping_spec_id,
            rounding_mode=action_adapter.get("rounding_mode") if isinstance(action_adapter, dict) else None,
            proposed_action=proposed_action,
            executed_action=executed_action,
            reason_code=reason_code,
            fallback_mode_or_none=fallback_mode_or_none,
        )

        derived = _derived_action(executed_action=executed_action, snapshot=snapshot)

        routing: dict[str, Any] | None = None
        if players_alive_count >= 3:
            if mw_ladder_id is None and strict_mode:
                raise EnvironmentError("MISSING_FIELDS", "mw_ladder_id is required for multi-way DecisionPoints")
            rung_id = mw_rung_id or "baseline"
            if rung_id not in MW_RUNG_ID_VALUES:
                raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported rung_id: {rung_id!r}")
            try:
                mw_ctx = mw_context_digest(
                    state_hash=state_hash,
                    mw_ladder_id=mw_ladder_id or "0" * 64,
                    rung_id=rung_id,
                    belief_digest_or_none=None,
                    mw_risk_spec_id_or_none=None,
                    strict_mode=strict_mode,
                )
            except MWContextError as e:
                raise EnvironmentError(e.code, e.message) from e
            routing = {"mw_ladder_id": mw_ladder_id, "rung_id": rung_id, "mw_context_digest": mw_ctx}

        action_source_id = "system_policy" if (system_seat_id is not None and seat_id == system_seat_id) else "opponent_policy"
        if action_source_id not in ACTION_SOURCE_ID_VALUES:
            raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported action_source_id: {action_source_id!r}")

        events.append(
            {
                "event": "ActionChosen",
                "decision_id": decision_id,
                "state_hash": state_hash,
                "action_source_id": action_source_id,
                "proposed_action": proposed_action,
                "executed_action": executed_action,
                "mapping_trace": mapping_trace,
                "derived_action": derived,
                "routing": routing,
                "belief_spec_id": None,
                "belief_digest": None,
                "mw_risk_spec_id": None,
            }
        )

        # Execute.
        prev_completion_increment = int(state.completion_betting_or_raising_amount)
        prev_max_bet = int(max(state.bets))

        k = executed_action["kind"]
        if k in ("BET", "RAISE"):
            last_raiser_by_street[street] = actor_seat
            street_raise_count[street] = street_raise_count.get(street, 0) + 1
        if k == "FOLD":
            state.fold()
        elif k in ("CHECK", "CALL"):
            state.check_or_call()
        elif k in ("BET", "RAISE"):
            target_total = int(executed_action["target_total_commit_chips"])
            delta_total = target_total - actor_commit
            if delta_total <= 0:
                raise EnvironmentError("VALUE_ERROR", "BET/RAISE must increase actor_commit_chips")
            round_bet = int(state.bets[actor_index])
            raise_to_amount = round_bet + delta_total
            op = state.complete_bet_or_raise_to(raise_to_amount)
            reopen_flag = bool(ruleset["min_raise_rule"]["reopen_on_short_allin"])
            _apply_reopen_on_short_allin_if_enabled(
                state,
                prev_completion_increment=prev_completion_increment,
                prev_max_bet=prev_max_bet,
                player_index=op.player_index,
                new_round_bet=raise_to_amount,
                reopen_on_short_allin=reopen_flag,
            )
            raise_count_in_street += 1
        else:  # pragma: no cover
            raise EnvironmentError("UNSUPPORTED_VALUE", f"unsupported executed kind: {k!r}")

        # Consume new engine operations.
        while op_idx < len(state.operations):
            process_op(state.operations[op_idx])
            op_idx += 1

    # Flush remaining operations (all-in runout, etc.).
    while op_idx < len(state.operations):
        process_op(state.operations[op_idx])
        op_idx += 1

    flop_dealt = "FLOP" in streets_dealt
    try:
        total_rake_chips = compute_total_rake_chips(
            rake_base_pot_chips=rake_base_pot_chips,
            flop_dealt=flop_dealt,
            ruleset=ruleset,
        )
    except RakeError as e:
        raise EnvironmentError(e.code, e.message) from e

    # Apply rake by reducing winners' payoffs (pot reduction prior to distribution).
    payoffs_by_seat: dict[int, int] = {index_to_seat[i]: int(state.payoffs[i]) for i in range(player_count)}
    pushed_from_pot_by_seat: dict[int, int] = {
        index_to_seat[i]: int(pushed_from_pot_by_index[i]) for i in range(player_count)
    }
    recipients = [s for s, amt in pushed_from_pot_by_seat.items() if amt > 0]
    total_pushed = sum(pushed_from_pot_by_seat[s] for s in recipients)

    rake_alloc: dict[int, int] = {s: 0 for s in recipients}
    if total_rake_chips:
        if total_pushed <= 0:
            raise EnvironmentError("LEDGER_ERROR", "rake>0 but no pot payout recipients")
        remainders: list[tuple[int, int]] = []
        for s in recipients:
            numer = pushed_from_pot_by_seat[s] * total_rake_chips
            q, r = divmod(numer, total_pushed)
            rake_alloc[s] = q
            remainders.append((r, s))
        used = sum(rake_alloc.values())
        rem = total_rake_chips - used
        if rem:
            remainders.sort(key=lambda rs: (-rs[0], rs[1]))
            for _, s in remainders[:rem]:
                rake_alloc[s] += 1

    adjusted_payoffs_by_seat = dict(payoffs_by_seat)
    for s, a in rake_alloc.items():
        adjusted_payoffs_by_seat[s] -= a

    initial_stacks_by_seat_json = {str(s): _as_int(v, field=f"initial_stacks_by_seat[{s}]") for s, v in starting_stacks_by_seat.items()}
    final_stacks_by_seat_json: dict[str, int] = {}
    deltas_by_seat_json: dict[str, int] = {}
    for seat in seats_in_hand:
        init_stack = _as_int(starting_stacks_by_seat[seat], field=f"starting_stacks_by_seat[{seat}]")
        delta = adjusted_payoffs_by_seat[seat]
        final_stack = init_stack + delta
        if final_stack < 0:
            raise EnvironmentError("LEDGER_ERROR", "final_stack negative after rake adjustment", {"seat": seat})
        final_stacks_by_seat_json[str(seat)] = final_stack
        deltas_by_seat_json[str(seat)] = delta

    # Close pot with rake + payout PotUpdate events.
    if total_rake_chips:
        emit_pot_update(pot_chips_delta=0, rake_chips_delta=total_rake_chips)
    payout_from_pot = rake_base_pot_chips - total_rake_chips
    if payout_from_pot:
        emit_pot_update(pot_chips_delta=-payout_from_pot, rake_chips_delta=0)

    pot_balance_delta = sum(int(e["pot_chips_delta"]) - int(e["rake_chips_delta"]) for e in pot_updates)
    invariants_ok = (sum(deltas_by_seat_json.values()) + total_rake_chips == 0) and (pot_balance_delta == 0)

    events.append(
        {
            "event": "HandEnd",
            "initial_stacks_by_seat": initial_stacks_by_seat_json,
            "final_stacks_by_seat": final_stacks_by_seat_json,
            "stack_deltas_by_seat": deltas_by_seat_json,
            "total_rake_chips": total_rake_chips,
            "rake_base_pot_chips": rake_base_pot_chips,
            "forced_bets_total_by_seat": {str(s): forced_total_by_seat.get(s, 0) for s in seats_in_hand},
            "invariants_ok": bool(invariants_ok),
        }
    )

    if strict_mode and not invariants_ok:
        raise EnvironmentError("LEDGER_INVARIANT_FAIL", "ledger invariants failed", {"pot_balance_delta": pot_balance_delta})

    event_model_id = compute_event_model_id(strict_mode=strict_mode)

    header = {
        "run_id": run_id,
        "options_hash": options_hash,
        "seed": seed,
        "scenario_id": scenario_id,
        "schema_hash": schema_hash,
        "event_model_id": event_model_id,
        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
        "provenance_ref": provenance_ref,
        "resolved_paths_digest": resolved_paths_digest,
        "repro_tier": repro_tier,
    }

    digest_hex = event_stream_digest_from_objects([header, *events], strict_mode=strict_mode)
    header["event_stream_digest"]["hex"] = digest_hex
    return [header, *events]


def run_multi_hand_eventstream_objects(
    *,
    run_id: str,
    options_hash: str,
    seed: int,
    system_seat_id: int | None = None,
    scenario_id: str,
    schema_hash: str,
    provenance_ref: str,
    resolved_paths_digest: str,
    repro_tier: str,
    ruleset: dict[str, Any],
    triad: dict[str, Any],
    action_adapter: dict[str, Any],
    action_bins: dict[str, Any],
    mapping_spec_id: str | None,
    mw_ladder_id: str | None,
    starting_stacks_by_seat: dict[int, int],
    button_seat: int,
    hands: int,
    opponent_suite_id: str | None = None,
    opponent_artifact_id_or_params_hash: str | None = None,
    seat_policies: dict[int, PolicyFn] | None = None,
    policy: PolicyFn | None = None,
    strict_mode: bool = True,
) -> list[dict[str, Any]]:
    if hands <= 0:
        raise EnvironmentError("VALUE_ERROR", "hands must be > 0")

    if not isinstance(starting_stacks_by_seat, dict) or not starting_stacks_by_seat:
        raise EnvironmentError("TYPE_ERROR", "starting_stacks_by_seat must be non-empty object")
    seats_in_hand = sorted(starting_stacks_by_seat.keys())

    events: list[dict[str, Any]] = []
    cur_button = button_seat

    for hand_seq in range(1, hands + 1):
        hand_seed = seed + (hand_seq - 1)
        single = run_single_hand_eventstream_objects(
            run_id=run_id,
            options_hash=options_hash,
            seed=hand_seed,
            system_seat_id=system_seat_id,
            scenario_id=scenario_id,
            schema_hash=schema_hash,
            provenance_ref=provenance_ref,
            resolved_paths_digest=resolved_paths_digest,
            repro_tier=repro_tier,
            ruleset=ruleset,
            triad=triad,
            action_adapter=action_adapter,
            action_bins=action_bins,
            mapping_spec_id=mapping_spec_id,
            mw_ladder_id=mw_ladder_id,
            opponent_suite_id=opponent_suite_id,
            opponent_artifact_id_or_params_hash=opponent_artifact_id_or_params_hash,
            starting_stacks_by_seat=starting_stacks_by_seat,
            button_seat=cur_button,
            hand_seq=hand_seq,
            seat_policies=seat_policies,
            policy=policy,
            strict_mode=strict_mode,
        )
        events.extend(single[1:])
        if hand_seq != hands:
            cur_button = _rotate_button_seat(seats_in_hand, button_seat=cur_button)

    event_model_id = compute_event_model_id(strict_mode=strict_mode)
    header = {
        "run_id": run_id,
        "options_hash": options_hash,
        "seed": seed,
        "scenario_id": scenario_id,
        "schema_hash": schema_hash,
        "event_model_id": event_model_id,
        "event_stream_digest": {"alg": "sha256", "hex": "0" * 64},
        "provenance_ref": provenance_ref,
        "resolved_paths_digest": resolved_paths_digest,
        "repro_tier": repro_tier,
    }

    digest_hex = event_stream_digest_from_objects([header, *events], strict_mode=strict_mode)
    header["event_stream_digest"]["hex"] = digest_hex
    return [header, *events]
