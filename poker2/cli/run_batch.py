from __future__ import annotations

# CLI: run N hands and emit per-hand EventStreams (ARCHIETECTURE.md 5.1.1).

import argparse
import importlib.metadata
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, validate_digest_object
from poker2.environment.pokerkit_nlhe import EnvironmentError, run_single_hand_eventstream_objects
from poker2.protocol.abstraction import AbstractionError, abstraction_hash
from poker2.protocol.options_hash import OptionsHashError, compute_options_hash
from poker2.protocol.paths import PathsError, default_resolved_paths
from poker2.protocol.placeholders import placeholder_id
from poker2.protocol.action_adapter import ActionAdapterError, default_internal_action_adapter
from poker2.protocol.action_bins import ActionBinsError, default_internal_action_bins
from poker2.protocol.policy import PolicyError, load_policy_spec, policy_id
from poker2.protocol.ruleset import RuleSetError, ruleset_rake_id, validate_ruleset
from poker2.protocol.scenario import ScenarioError, scenario_id
from poker2.protocol.schema_contract import SchemaContractError, schema_hash
from poker2.protocol.triad import TriadError, triad
from poker2.protocol.profile import ProfileError, load_profile_spec, profile_id
from poker2.cli.hrc_import_ruleset import ImportError, import_ruleset_from_hrc_settings
from poker2.protocol.run_id import run_id_v1
from poker2.protocol.mw_ladder import MWLadderError, default_internal_mw_ladder
from poker2.protocol.provenance import build_provenance_envelope_v1, provenance_id
from poker2.runtime.artifact_store import write_artifact_json
from poker2.runtime.policy_registry import build_policy_registry, resolve_policy_ref
from poker2.runtime.profile_registry import build_profile_registry, resolve_profile_ref


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


@dataclass
class RunBatchError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _write_eventstream(path: Path, objs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [canonicalize_json_bytes(o, strict_mode=True) for o in objs]
    path.write_bytes(b"\n".join(lines) + b"\n")


def _parse_starting_stacks(value: str) -> dict[int, int]:
    try:
        raw = json.loads(value)
    except Exception as e:
        raise RunBatchError("JSON_PARSE_FAIL", "starting_stacks_by_seat must be valid JSON object", {"error": str(e)}) from e
    if not isinstance(raw, dict) or not raw:
        raise RunBatchError("TYPE_ERROR", "starting_stacks_by_seat must be non-empty JSON object")
    out: dict[int, int] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.isdigit():
            raise RunBatchError("TYPE_ERROR", "starting_stacks_by_seat keys must be decimal strings")
        if isinstance(v, bool) or not isinstance(v, int):
            raise RunBatchError("TYPE_ERROR", "starting_stacks_by_seat values must be int")
        out[int(k)] = v
    return out


def run_batch_from_hrc_settings(
    *,
    settings_path: Path,
    out_dir: Path,
    seed: int,
    hands: int,
    strict_mode: bool,
    rounding_mode: str | None,
    reopen_on_short_allin: bool | None,
    starting_stacks_by_seat: dict[int, int],
    button_seat: int,
    mw_ladder_id: str | None,
    requested_profile_ref: str | None = None,
    requested_policy_ref: str | None = None,
) -> dict[str, Any]:
    if hands <= 0:
        raise RunBatchError("VALUE_ERROR", "hands must be > 0")

    ruleset_out = import_ruleset_from_hrc_settings(
        settings_path,
        rounding_mode=rounding_mode,
        reopen_on_short_allin=reopen_on_short_allin,
    )
    ruleset = ruleset_out["ruleset"]
    validate_ruleset(ruleset, strict_mode=strict_mode)

    if strict_mode and len(starting_stacks_by_seat) >= 3 and mw_ladder_id is None:
        _, mw_ladder_id = default_internal_mw_ladder(strict_mode=True)

    action_bins_spec, action_bins_id = default_internal_action_bins(strict_mode=True)
    obs_schema_id = placeholder_id("obs_schema_placeholder_v1", strict_mode=True)
    rake_id = ruleset_rake_id(ruleset, strict_mode=True)
    t = triad(action_bins_id=action_bins_id, obs_schema_id=obs_schema_id, rake_id=rake_id)

    s_hash = schema_hash(strict_mode=True)

    action_adapter_spec, action_adapter_id = default_internal_action_adapter(strict_mode=True)
    mapping_spec_id = None
    abs_hash = abstraction_hash(
        action_bins_id=action_bins_id,
        action_adapter_id=action_adapter_id,
        mapping_spec_id=mapping_spec_id,
        strict_mode=True,
    )

    scen_closure = {
        "scenario_schema_id": "scenario_spec_v1",
        "ruleset_id": ruleset_out["ruleset_id"],
        "triad": t,
        "schema_hash": s_hash,
        "abstraction_hash": abs_hash,
        "preflop_ref": None,
        "postflop_ref": None,
        "opponent_suite_id": None,
        "population_id": None,
        "mw_ladder_id": mw_ladder_id,
    }
    scen_id = scenario_id(scen_closure, strict_mode=True)

    _, resolved_paths_digest = default_resolved_paths(strict_mode=True)

    profile_registry = build_profile_registry(strict_mode=True)
    prof_req = requested_profile_ref or "internal_profile_v1"
    prof_entry, _prof_trace = resolve_profile_ref(prof_req, registry=profile_registry, strict_mode=bool(strict_mode))
    prof_spec_path = Path(str(prof_entry["profile_spec_ref"]).removeprefix("path:"))
    prof_spec = load_profile_spec(prof_spec_path)
    prof_id = profile_id(prof_spec, strict_mode=True)

    policy_registry = build_policy_registry(strict_mode=True)
    pol_req = requested_policy_ref or "internal_baseline_policy_v1"
    pol_entry, _pol_trace = resolve_policy_ref(pol_req, registry=policy_registry, strict_mode=bool(strict_mode))
    pol_spec_path = Path(str(pol_entry["policy_spec_ref"]).removeprefix("path:"))
    pol_spec = load_policy_spec(pol_spec_path)
    pol_id = policy_id(pol_spec, strict_mode=True)

    try:
        pokerkit_version = importlib.metadata.version("pokerkit")
    except Exception:  # pragma: no cover
        pokerkit_version = None

    run_closure = {
        "scenario_id": scen_id,
        "ruleset_id": ruleset_out["ruleset_id"],
        "triad": t,
        "schema_hash": s_hash,
        "resolved_paths_digest": resolved_paths_digest,
        "abstraction_hash": abs_hash,
        "policy_id": pol_id,
        "profile_id": prof_id,
        "opponent_suite_id": None,
        "opponent_artifact_id_or_params_hash": None,
        "mw_ladder_id": mw_ladder_id,
        "belief_spec_id": None,
        "mw_risk_spec_id": None,
        "adaptation_digest": None,
        "engine_build_id": None,
        "solver_build_id": None,
        "pokerkit_version": pokerkit_version,
        "strict_mode": bool(strict_mode),
    }
    options_hash = compute_options_hash(run_closure, strict_mode=True)

    out_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for hand_seq in range(1, hands + 1):
        hand_seed = seed + (hand_seq - 1)
        run_id = run_id_v1(options_hash=options_hash, seed=hand_seed, strict_mode=True)

        provenance_env = build_provenance_envelope_v1(
            ruleset_id=ruleset_out["ruleset_id"],
            triad=t,
            schema_hash=s_hash,
            options_hash=options_hash,
            seed=hand_seed,
            action_adapter_id=action_adapter_id,
            mapping_spec_id=mapping_spec_id,
            mw_ladder_id=mw_ladder_id,
            pokerkit_version=pokerkit_version,
            engine_build_id=None,
            solver_build_id=None,
            rng_lineage_id=None,
            seed_derivation_digest=None,
            repro_tier="Tier-A",
        )
        prov_id = provenance_id(provenance_env, strict_mode=True)
        provenance_ref = f"artifact://{prov_id}"
        _ = write_artifact_json(provenance_env, artifact_id=prov_id, strict_mode=True)

        objs = run_single_hand_eventstream_objects(
            run_id=run_id,
            options_hash=options_hash,
            seed=hand_seed,
            scenario_id=scen_id,
            schema_hash=s_hash,
            provenance_ref=provenance_ref,
            resolved_paths_digest=resolved_paths_digest,
            repro_tier="Tier-A",
        ruleset=ruleset,
        triad=t,
        action_adapter=action_adapter_spec,
        action_bins=action_bins_spec,
        mapping_spec_id=None,
        mw_ladder_id=mw_ladder_id,
        starting_stacks_by_seat=starting_stacks_by_seat,
        button_seat=button_seat,
        hand_seq=1,
            policy=None,
            strict_mode=strict_mode,
        )

        header = objs[0]
        validate_digest_object(header["event_stream_digest"], strict_mode=True)

        out_path = out_dir / f"hand_{hand_seq:06d}.ndjson"
        _write_eventstream(out_path, objs)
        outputs.append(
            {
                "hand_seq": hand_seq,
                "seed": hand_seed,
                "run_id": run_id,
                "event_stream_ref": f"path:{out_path}",
                "event_stream_digest": header["event_stream_digest"],
            }
        )

    elapsed_s = time.perf_counter() - t0
    return {
        "status": "pass",
        "hands": hands,
        "elapsed_s": elapsed_s,
        "hands_per_sec": (hands / elapsed_s) if elapsed_s > 0 else None,
        "out_dir_ref": f"path:{out_dir}",
        "outputs": outputs,
        "ruleset": ruleset_out,
        "triad": t,
        "schema_hash": s_hash,
        "abstraction_hash": abs_hash,
        "scenario_id": scen_id,
        "resolved_paths_digest": resolved_paths_digest,
        "profile_spec": prof_spec,
        "profile_id": prof_id,
        "policy_spec": pol_spec,
        "policy_id": pol_id,
        "options_hash": options_hash,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--settings", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--seed", type=int, default=123)
    p.add_argument("--hands", type=int, default=100)
    p.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--profile", default="internal_profile_v1")
    p.add_argument("--policy", default="internal_baseline_policy_v1")
    p.add_argument("--rounding-mode", default=None)
    p.add_argument("--reopen-on-short-allin", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--starting-stacks-by-seat", required=True)
    p.add_argument("--button-seat", type=int, required=True)
    p.add_argument("--mw-ladder-id", default=None)
    args = p.parse_args(argv)

    try:
        out = run_batch_from_hrc_settings(
            settings_path=args.settings,
            out_dir=args.out_dir,
            seed=args.seed,
            hands=args.hands,
            strict_mode=args.strict,
            rounding_mode=args.rounding_mode,
            reopen_on_short_allin=args.reopen_on_short_allin,
            starting_stacks_by_seat=_parse_starting_stacks(args.starting_stacks_by_seat),
            button_seat=args.button_seat,
            mw_ladder_id=args.mw_ladder_id,
            requested_profile_ref=args.profile,
            requested_policy_ref=args.policy,
        )
        _print(out)
        return 0
    except (
        RunBatchError,
        ImportError,
        RuleSetError,
        TriadError,
        SchemaContractError,
        ScenarioError,
        PolicyError,
        ProfileError,
        OptionsHashError,
        AbstractionError,
        PathsError,
        EnvironmentError,
        MWLadderError,
        ActionAdapterError,
        ActionBinsError,
    ) as e:
        code = getattr(e, "code", "FAIL")
        msg = getattr(e, "message", str(e))
        details = getattr(e, "details", None)
        _print({"status": "fail", "check_id": "Tools.RunBatch", "error": {"code": code, "message": msg, "details": details}})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover
