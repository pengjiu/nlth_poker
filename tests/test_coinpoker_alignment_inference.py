from __future__ import annotations

from pathlib import Path

from poker2.contractkit import canonicalize_json_bytes
from poker2.evaluation.gates.coinpoker_alignment import (
    infer_rake_rounding_modes,
    infer_reopen_on_short_allin_flags,
)
from poker2.protocol.eventstream import event_stream_digest_from_objects
from poker2.protocol.run_id import run_id_v1


def _header(*, digest_hex: str) -> dict:
    options_hash = "0" * 64
    seed = 0
    return {
        "run_id": run_id_v1(options_hash=options_hash, seed=seed, strict_mode=True),
        "options_hash": options_hash,
        "seed": seed,
        "scenario_id": "0" * 64,
        "schema_hash": "0" * 64,
        "event_model_id": "0" * 64,
        "event_stream_digest": {"alg": "sha256", "hex": digest_hex},
        "provenance_ref": "artifact://prov",
        "resolved_paths_digest": "0" * 64,
        "repro_tier": "Tier-A",
    }


def _write_ndjson(path: Path, objs: list[dict]) -> None:
    lines = [canonicalize_json_bytes(o, strict_mode=True) for o in objs]
    path.write_bytes(b"\n".join(lines) + b"\n")


def _write_eventstream(path: Path, events: list[dict]) -> str:
    header = _header(digest_hex="0" * 64)
    digest_hex = event_stream_digest_from_objects([header, *events], strict_mode=True)
    header["event_stream_digest"]["hex"] = digest_hex
    _write_ndjson(path, [header, *events])
    return digest_hex


def test_infer_rake_rounding_mode_unique_nearest_ties_up(tmp_path: Path) -> None:
    ruleset = {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": None,
        "straddle": None,
        "rake": {
            "pct_ppm": 50_000,
            "cap_chips": None,
            "rounding_mode": "nearest_ties_up",
            "no_flop_no_drop": False,
        },
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": True},
    }

    p1 = tmp_path / "rake_tie.ndjson"
    _write_eventstream(
        p1,
        [
            {"event": "StreetDealt", "street": "FLOP"},
            {"event": "HandEnd", "rake_base_pot_chips": 10, "total_rake_chips": 1},
        ],
    )

    p2 = tmp_path / "rake_non_tie.ndjson"
    _write_eventstream(
        p2,
        [
            {"event": "StreetDealt", "street": "FLOP"},
            {"event": "HandEnd", "rake_base_pot_chips": 101, "total_rake_chips": 5},
        ],
    )

    possible, _ = infer_rake_rounding_modes(
        [
            {"event_stream_ref": f"path:{p1}"},
            {"event_stream_ref": f"path:{p2}"},
        ],
        ruleset=ruleset,
        strict_mode=True,
    )
    assert possible == ["nearest_ties_up"]


def test_infer_reopen_on_short_allin_unique_true(tmp_path: Path) -> None:
    ruleset = {
        "game_kind": "NLHE",
        "blinds": {"sb_chips": 1, "bb_chips": 2},
        "ante": None,
        "straddle": None,
        "rake": None,
        "min_raise_rule": {"basis": "last_raise_increment", "reopen_on_short_allin": True},
    }

    stream = tmp_path / "reopen.ndjson"
    events = [
        {"event": "ForcedBets", "kind": "sb", "by_seat_amount_chips": {"1": 1}},
        {"event": "ForcedBets", "kind": "bb", "by_seat_amount_chips": {"2": 2}},
        {
            "event": "DecisionPoint",
            "decision_id": 1,
            "state_hash": "s1",
            "legal_actions_digest": {"alg": "sha256", "hex": "0" * 64},
            "snapshot_payload": {"street": "PREFLOP", "actor_seat": 3},
        },
        {
            "event": "ActionChosen",
            "decision_id": 1,
            "state_hash": "s1",
            "executed_action": {"kind": "CALL", "target_total_commit_chips": 2},
        },
        {
            "event": "DecisionPoint",
            "decision_id": 2,
            "state_hash": "s2",
            "legal_actions_digest": {"alg": "sha256", "hex": "0" * 64},
            "snapshot_payload": {"street": "PREFLOP", "actor_seat": 1},
        },
        {
            "event": "ActionChosen",
            "decision_id": 2,
            "state_hash": "s2",
            "executed_action": {"kind": "CALL", "target_total_commit_chips": 2},
        },
        {
            "event": "DecisionPoint",
            "decision_id": 3,
            "state_hash": "s3",
            "legal_actions_digest": {"alg": "sha256", "hex": "0" * 64},
            "snapshot_payload": {"street": "PREFLOP", "actor_seat": 2},
        },
        {
            "event": "ActionChosen",
            "decision_id": 3,
            "state_hash": "s3",
            "executed_action": {"kind": "BET", "target_total_commit_chips": 6},
        },
        {
            "event": "DecisionPoint",
            "decision_id": 4,
            "state_hash": "s4",
            "legal_actions_digest": {"alg": "sha256", "hex": "0" * 64},
            "snapshot_payload": {"street": "PREFLOP", "actor_seat": 3},
        },
        {
            "event": "ActionChosen",
            "decision_id": 4,
            "state_hash": "s4",
            "executed_action": {"kind": "RAISE", "target_total_commit_chips": 9},
        },
        {
            "event": "DecisionPoint",
            "decision_id": 5,
            "state_hash": "s5",
            "legal_actions_digest": {"alg": "sha256", "hex": "0" * 64},
            "snapshot_payload": {"street": "PREFLOP", "actor_seat": 1},
        },
        {
            "event": "ActionChosen",
            "decision_id": 5,
            "state_hash": "s5",
            "executed_action": {"kind": "CALL", "target_total_commit_chips": 9},
        },
        {
            "event": "DecisionPoint",
            "decision_id": 6,
            "state_hash": "s6",
            "legal_actions_digest": {"alg": "sha256", "hex": "0" * 64},
            "snapshot_payload": {"street": "PREFLOP", "actor_seat": 2},
        },
        {
            "event": "ActionChosen",
            "decision_id": 6,
            "state_hash": "s6",
            "executed_action": {"kind": "RAISE", "target_total_commit_chips": 12},
        },
        {
            "event": "HandEnd",
            "initial_stacks_by_seat": {"1": 50, "2": 50, "3": 9},
            "total_rake_chips": 0,
            "rake_base_pot_chips": 0,
        },
    ]
    _write_eventstream(stream, events)

    possible, _ = infer_reopen_on_short_allin_flags(
        [{"event_stream_ref": f"path:{stream}"}],
        ruleset=ruleset,
        strict_mode=True,
    )
    assert possible == [True]
