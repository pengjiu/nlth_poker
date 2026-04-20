from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ForcedBetsSpecError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ForcedBetsSpecError("TYPE_ERROR", f"{field} must be int, got bool")
    if not isinstance(value, int):
        raise ForcedBetsSpecError("TYPE_ERROR", f"{field} must be int, got {type(value).__name__}")
    return value


def _normalize_seats(seats_in_hand: Any) -> list[int]:
    if not isinstance(seats_in_hand, list) or not seats_in_hand:
        raise ForcedBetsSpecError("TYPE_ERROR", "seats_in_hand must be non-empty int array")
    out: list[int] = []
    seen: set[int] = set()
    for i, seat in enumerate(seats_in_hand):
        if isinstance(seat, bool) or not isinstance(seat, int):
            raise ForcedBetsSpecError("TYPE_ERROR", f"seats_in_hand[{i}] must be int")
        if seat in seen:
            raise ForcedBetsSpecError("VALUE_ERROR", f"duplicate seat in seats_in_hand: {seat}")
        seen.add(seat)
        out.append(seat)
    return out


def blind_seats_for_hand(*, seats_in_hand: list[int], button_seat: int) -> tuple[int, int]:
    seats = _normalize_seats(seats_in_hand)
    if button_seat not in seats:
        raise ForcedBetsSpecError("VALUE_ERROR", "button_seat must be in seats_in_hand")
    if len(seats) < 2:
        raise ForcedBetsSpecError("VALUE_ERROR", "seats_in_hand must contain >=2 seats")
    if len(seats) == 2:
        sb_seat = button_seat
        bb_seat = seats[0] if seats[1] == button_seat else seats[1]
        return sb_seat, bb_seat
    idx = seats.index(button_seat)
    sb_seat = seats[(idx + 1) % len(seats)]
    bb_seat = seats[(idx + 2) % len(seats)]
    return sb_seat, bb_seat


def ante_chips_by_seat_from_ruleset(
    *,
    ruleset: dict[str, Any],
    seats_in_hand: list[int],
    strict_mode: bool,
) -> dict[int, int]:
    seats = _normalize_seats(seats_in_hand)
    out: dict[int, int] = {seat: 0 for seat in seats}
    ante = ruleset.get("ante")
    if ante is None:
        return out
    if not isinstance(ante, dict):
        raise ForcedBetsSpecError("TYPE_ERROR", "ruleset.ante must be null or object")
    kind = ante.get("kind")
    if kind == "uniform":
        amt = _as_int(ante.get("ante_chips"), field="ruleset.ante.ante_chips")
        if amt < 0:
            raise ForcedBetsSpecError("VALUE_ERROR", "ruleset.ante.ante_chips must be >= 0")
        for seat in seats:
            out[seat] = amt
        return out
    if kind == "by_seat":
        by_seat = ante.get("by_seat_ante_chips")
        if not isinstance(by_seat, dict):
            raise ForcedBetsSpecError("TYPE_ERROR", "ruleset.ante.by_seat_ante_chips must be object")
        for seat_key, amt in by_seat.items():
            if not isinstance(seat_key, str) or not seat_key.isdigit():
                raise ForcedBetsSpecError("TYPE_ERROR", "by_seat_ante_chips keys must be decimal strings")
            seat = int(seat_key)
            parsed = _as_int(amt, field=f"ruleset.ante.by_seat_ante_chips[{seat_key}]")
            if parsed < 0:
                raise ForcedBetsSpecError("VALUE_ERROR", f"ruleset.ante.by_seat_ante_chips[{seat_key}] must be >= 0")
            if seat not in out:
                if strict_mode:
                    raise ForcedBetsSpecError(
                        "VALUE_ERROR",
                        f"ruleset.ante.by_seat_ante_chips includes seat not in seats_in_hand: {seat}",
                    )
                continue
            out[seat] = parsed
        return out
    raise ForcedBetsSpecError("UNSUPPORTED_VALUE", f"unsupported ruleset.ante.kind: {kind!r}")


def expected_forced_bets_by_seat(
    *,
    ruleset: dict[str, Any],
    seats_in_hand: list[int],
    button_seat: int,
    starting_stacks_by_seat: dict[int, int] | None,
    strict_mode: bool,
) -> dict[str, Any]:
    seats = _normalize_seats(seats_in_hand)
    blinds = ruleset.get("blinds")
    if not isinstance(blinds, dict):
        raise ForcedBetsSpecError("TYPE_ERROR", "ruleset.blinds must be object")
    sb_amt = _as_int(blinds.get("sb_chips"), field="ruleset.blinds.sb_chips")
    bb_amt = _as_int(blinds.get("bb_chips"), field="ruleset.blinds.bb_chips")
    if sb_amt < 0 or bb_amt < 0:
        raise ForcedBetsSpecError("VALUE_ERROR", "blind amounts must be >= 0")

    sb_seat, bb_seat = blind_seats_for_hand(seats_in_hand=seats, button_seat=button_seat)
    blind_req: dict[int, int] = {seat: 0 for seat in seats}
    blind_req[sb_seat] = sb_amt
    blind_req[bb_seat] = bb_amt
    ante_req = ante_chips_by_seat_from_ruleset(
        ruleset=ruleset,
        seats_in_hand=seats,
        strict_mode=strict_mode,
    )

    stack_map: dict[int, int] | None = None
    if starting_stacks_by_seat is not None:
        stack_map = {}
        for seat in seats:
            if seat not in starting_stacks_by_seat:
                raise ForcedBetsSpecError("MISSING_FIELD", f"missing starting stack for seat={seat}")
            stack = _as_int(starting_stacks_by_seat[seat], field=f"starting_stacks_by_seat[{seat}]")
            if stack < 0:
                raise ForcedBetsSpecError("VALUE_ERROR", f"starting_stacks_by_seat[{seat}] must be >= 0")
            stack_map[seat] = stack

    ante_by_seat: dict[int, int] = {}
    blind_by_seat: dict[int, int] = {}
    total_by_seat: dict[int, int] = {}
    for seat in seats:
        ante_target = int(ante_req.get(seat, 0))
        blind_target = int(blind_req.get(seat, 0))
        if stack_map is None:
            ante_post = ante_target
            blind_post = blind_target
        else:
            remain = int(stack_map.get(seat, 0))
            ante_post = min(remain, ante_target)
            remain -= ante_post
            blind_post = min(remain, blind_target)
        ante_by_seat[seat] = ante_post
        blind_by_seat[seat] = blind_post
        total_by_seat[seat] = ante_post + blind_post

    return {
        "sb_seat": sb_seat,
        "bb_seat": bb_seat,
        "ante_by_seat": ante_by_seat,
        "blind_by_seat": blind_by_seat,
        "total_by_seat": total_by_seat,
    }


def ante_display_value(*, ruleset: dict[str, Any], seats_in_hand: list[int], strict_mode: bool) -> str:
    ante = ruleset.get("ante")
    if ante is None:
        return "0"
    if not isinstance(ante, dict):
        return "invalid"
    kind = ante.get("kind")
    if kind == "uniform":
        try:
            return str(_as_int(ante.get("ante_chips"), field="ruleset.ante.ante_chips"))
        except ForcedBetsSpecError:
            return "invalid"
    if kind == "by_seat":
        try:
            by_seat = ante_chips_by_seat_from_ruleset(
                ruleset=ruleset,
                seats_in_hand=seats_in_hand,
                strict_mode=strict_mode,
            )
        except ForcedBetsSpecError:
            return "invalid"
        vals = sorted(set(int(v) for v in by_seat.values()))
        if not vals:
            return "by-seat:0"
        if len(vals) == 1:
            return f"by-seat:{vals[0]}"
        return f"by-seat:{vals[0]}..{vals[-1]}"
    return "invalid"
