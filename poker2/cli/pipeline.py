from __future__ import annotations

# Pipeline CLI (ARCHIETECTURE.md §3.21).
#
# Minimal, gate-enforced pipeline for internal fixtures:
# it resolves {scenario/profile/policy/opponents}+{seed/strict} into {options_hash, run_id},
# locates a pinned internal fixture EventStream by run_id, and emits:
#   ./artifacts/<run_id>/{manifest,eventstream,report}/...

import argparse
import importlib.metadata
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.engines.postflop_solver import (
    DEFAULT_BINDING_KIND,
    PostflopSolverError,
    compute_postflop_solver_build_id,
    postflop_solver_src_root_from_paths_trace,
    solve_postflop_library,
)
from poker2.evaluation.rule_conformance import RuleConformanceError, rule_conformance_report_from_eventstream
from poker2.gates import GateCheckError, check_eventstream_gates
from poker2.gates.scenario_package_gate import check_scenario_package_gate
from poker2.protocol.action_adapter import default_internal_action_adapter
from poker2.protocol.enums import STAGE_ID_ORDERED
from poker2.protocol.eventstream import EventStreamError, event_stream_digest_from_file, read_ndjson
from poker2.protocol.metrics_spec import metric_spec_id
from poker2.protocol.options_hash import OptionsHashError, compute_options_hash
from poker2.protocol.paths import default_paths_config, resolve_paths, validate_paths_config
from poker2.protocol.policy import PolicyError, load_policy_spec, policy_id
from poker2.protocol.provenance import build_provenance_envelope_v1, provenance_id
from poker2.protocol.profile import ProfileError, load_profile_spec, profile_id
from poker2.protocol.report_schema import report_schema_id
from poker2.protocol.ruleset import RuleSetError, ruleset_id as compute_ruleset_id, validate_ruleset
from poker2.protocol.run_id import run_id_v1
from poker2.protocol.run_manifest import RunManifestError, finalize_run_manifest, validate_run_manifest
from poker2.protocol.scenario_package import ScenarioPackageError, load_scenario_package, scenario_closure_from_package, validate_scenario_package
from poker2.runtime.artifacts import run_artifact_paths, write_canonical_json, write_canonical_ndjson
from poker2.runtime.artifact_store import runtime_artifacts_store_root, write_artifact_json
from poker2.runtime.opponent_registry import OpponentRegistryError, build_opponent_registry, resolve_opponent_suite_ref
from poker2.runtime.policy_registry import PolicyRegistryError, build_policy_registry, resolve_policy_ref
from poker2.runtime.profile_registry import ProfileRegistryError, build_profile_registry, resolve_profile_ref
from poker2.runtime.scenario_registry import ScenarioRegistryError, build_scenario_registry, resolve_scenario_ref


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


@dataclass
class PipelineError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_paths_config(*, paths_config_path: Path | None, strict_mode: bool) -> dict[str, Any]:
    if paths_config_path is None:
        return default_paths_config(strict_mode=strict_mode)
    try:
        obj = json.loads(paths_config_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise PipelineError("PATHS_CONFIG_UNREADABLE", "paths_config JSON unreadable", {"path": str(paths_config_path), "error": str(e)}) from e
    validate_paths_config(obj, strict_mode=strict_mode)
    return obj


def _apply_postflop_solver_root(
    *,
    paths_config: dict[str, Any],
    postflop_solver_src_root: str | None,
) -> dict[str, Any]:
    if postflop_solver_src_root is None:
        return paths_config
    roots = dict(paths_config.get("roots", {}))
    if "postflop_solver_src_root" not in roots:
        roots["postflop_solver_src_root"] = postflop_solver_src_root
    return {**paths_config, "roots": roots}


def _binding_kind_from_profile(profile_spec: dict[str, Any]) -> str:
    if isinstance(profile_spec.get("solver_binding_kind"), str):
        return profile_spec["solver_binding_kind"]
    return DEFAULT_BINDING_KIND


def _digest_for_obj(obj: dict[str, Any]) -> dict[str, str]:
    digest = {"alg": "sha256", "hex": sha256_hex(canonicalize_json_bytes(obj, strict_mode=True))}
    validate_digest_object(digest, strict_mode=True)
    return digest


def _artifact_summary(
    *,
    artifact_kind: str,
    artifact_ref: str,
    digest: dict[str, str],
    counts: dict[str, int],
    provenance_ref: str,
) -> dict[str, Any]:
    validate_digest_object(digest, strict_mode=True)
    return {
        "artifact_kind": artifact_kind,
        "artifact_ref": artifact_ref,
        "digest": digest,
        "counts": counts,
        "provenance_ref": provenance_ref,
    }


def _policy_deps_contains_ref(policy_spec: dict[str, Any], ref: dict[str, Any]) -> bool:
    deps = policy_spec.get("policy_deps")
    if not isinstance(deps, list):
        return False
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        if dep.get("artifact_ref") == ref.get("artifact_ref") and dep.get("digest") == ref.get("digest"):
            return True
    return False


def _enforce_postflop_deps(
    *,
    scenario_closure: dict[str, Any],
    policy_spec: dict[str, Any],
    solver_build_id: str | None,
    strict_mode: bool,
) -> None:
    postflop_ref = scenario_closure.get("postflop_ref")
    if not strict_mode or postflop_ref is None:
        return
    if not isinstance(postflop_ref, dict):
        raise PipelineError("POSTFLOP_REF_INVALID", "postflop_ref must be object when present", {"postflop_ref": postflop_ref})
    if not _policy_deps_contains_ref(policy_spec, postflop_ref):
        raise PipelineError(
            "POLICY_DEPS_MISSING_POSTFLOP",
            "policy_deps must include ScenarioPackage.postflop_ref when present",
            {"postflop_ref": postflop_ref},
        )
    if solver_build_id is None:
        raise PipelineError(
            "SOLVER_BUILD_ID_REQUIRED",
            "solver_build_id required when postflop_ref is present",
            {},
        )


def _load_ruleset_by_id(*, ruleset_id: str) -> tuple[dict[str, Any], str]:
    root = _repo_root() / "specs" / "rulesets"
    candidates = sorted([p for p in root.glob("*.json") if p.is_file()], key=lambda p: str(p))
    matches: list[Path] = []
    for p in candidates:
        obj = json.loads(p.read_text(encoding="utf-8"))
        validate_ruleset(obj, strict_mode=True)
        if compute_ruleset_id(obj, strict_mode=True) == ruleset_id:
            matches.append(p)
    if not matches:
        raise PipelineError("MISSING_REF", "ruleset_id not found in specs/rulesets", {"ruleset_id": ruleset_id})
    if len(matches) != 1:
        raise PipelineError(
            "AMBIGUOUS",
            "multiple RuleSet specs match ruleset_id",
            {"ruleset_id": ruleset_id, "candidates": [str(p) for p in matches]},
        )
    path = matches[0]
    return json.loads(path.read_text(encoding="utf-8")), f"path:{path}"


def _find_internal_fixture_eventstream(*, run_id: str) -> Path | None:
    # Internal-only, committed fixtures (no private fetch).
    root = _repo_root() / "fixtures" / "internal" / "eventstreams"
    candidates = sorted([p for p in root.glob("*.ndjson") if p.is_file()], key=lambda p: str(p))
    found: list[Path] = []
    for p in candidates:
        try:
            objs = read_ndjson(p, strict_mode=True)
        except Exception:
            continue
        if not objs or not isinstance(objs[0], dict):
            continue
        if objs[0].get("run_id") == run_id:
            found.append(p)
    if not found:
        return None
    found.sort(key=lambda p: str(p))
    if len(found) != 1:
        raise PipelineError("AMBIGUOUS", "multiple internal fixtures match run_id", {"run_id": run_id, "candidates": [str(p) for p in found]})
    return found[0]


def _load_runspec(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise PipelineError("RUNSPEC_UNREADABLE", "runspec JSON unreadable", {"path": str(path), "error": str(e)}) from e
    if not isinstance(obj, dict):
        raise PipelineError("RUNSPEC_INVALID", "runspec must be JSON object", {"path": str(path)})

    required = (
        "runspec_schema_id",
        "run_id_schema",
        "run_id",
        "options_hash",
        "seed",
        "strict_mode",
        "scenario_id",
        "profile_id",
        "policy_id",
        "opponent_suite_id",
        "execution_hint",
        "resolved_paths_digest",
    )
    missing = [k for k in required if k not in obj]
    if missing:
        raise PipelineError("RUNSPEC_INVALID", "runspec missing required fields", {"missing": missing})

    if obj.get("runspec_schema_id") != "runspec_v1":
        raise PipelineError("RUNSPEC_INVALID", "unsupported runspec_schema_id", {"observed": obj.get("runspec_schema_id")})
    if obj.get("run_id_schema") != "run_id_v1":
        raise PipelineError("RUNSPEC_INVALID", "unsupported run_id_schema", {"observed": obj.get("run_id_schema")})

    for field in ("run_id", "options_hash", "scenario_id", "profile_id", "policy_id", "resolved_paths_digest"):
        validate_digest_object({"alg": "sha256", "hex": obj.get(field)}, strict_mode=True)

    if isinstance(obj.get("seed"), bool) or not isinstance(obj.get("seed"), int):
        raise PipelineError("RUNSPEC_INVALID", "runspec.seed must be int", {"seed": obj.get("seed")})
    if not isinstance(obj.get("strict_mode"), bool):
        raise PipelineError("RUNSPEC_INVALID", "runspec.strict_mode must be bool", {"strict_mode": obj.get("strict_mode")})

    opp_id = obj.get("opponent_suite_id")
    if opp_id is not None:
        validate_digest_object({"alg": "sha256", "hex": opp_id}, strict_mode=True)

    exec_hint = obj.get("execution_hint")
    if exec_hint is not None and not isinstance(exec_hint, dict):
        raise PipelineError("RUNSPEC_INVALID", "runspec.execution_hint must be object or null", {"execution_hint": exec_hint})

    return obj


def _build_runspec_obj(
    *,
    run_id: str,
    options_hash: str,
    seed: int,
    strict_mode: bool,
    scenario_id: str,
    profile_id: str,
    policy_id: str,
    opponent_suite_id: str | None,
    resolved_paths_digest: str,
) -> dict[str, Any]:
    # Minimal RunSpec serialization used as an init-stage artifact.
    obj = {
        "runspec_schema_id": "runspec_v1",
        "run_id_schema": "run_id_v1",
        "run_id": run_id,
        "options_hash": options_hash,
        "seed": seed,
        "strict_mode": bool(strict_mode),
        "scenario_id": scenario_id,
        "profile_id": profile_id,
        "policy_id": policy_id,
        "opponent_suite_id": opponent_suite_id,
        "execution_hint": None,
        "resolved_paths_digest": resolved_paths_digest,
    }
    validate_digest_object({"alg": "sha256", "hex": run_id}, strict_mode=True)
    validate_digest_object({"alg": "sha256", "hex": options_hash}, strict_mode=True)
    validate_digest_object({"alg": "sha256", "hex": scenario_id}, strict_mode=True)
    validate_digest_object({"alg": "sha256", "hex": profile_id}, strict_mode=True)
    validate_digest_object({"alg": "sha256", "hex": policy_id}, strict_mode=True)
    validate_digest_object({"alg": "sha256", "hex": resolved_paths_digest}, strict_mode=True)
    if opponent_suite_id is not None:
        validate_digest_object({"alg": "sha256", "hex": opponent_suite_id}, strict_mode=True)
    return obj


def _effective_context(
    *,
    scenario_id: str,
    ruleset_id: str,
    triad: dict[str, Any],
    schema_hash: str,
    options_hash: str,
    resolved_paths_digest: str,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "ruleset_id": ruleset_id,
        "triad": triad,
        "schema_hash": schema_hash,
        "options_hash": options_hash,
        "resolved_paths_digest": resolved_paths_digest,
    }


def _upsert_stage(stages: list[dict[str, Any]], stage: dict[str, Any]) -> list[dict[str, Any]]:
    stage_id = stage.get("stage_id")
    out = [s for s in stages if s.get("stage_id") != stage_id]
    out.append(stage)
    order = {sid: i for i, sid in enumerate(STAGE_ID_ORDERED)}
    out.sort(key=lambda s: order.get(s.get("stage_id"), 999))
    return out


def _read_eventstream_with_digest(path: Path, *, strict_mode: bool) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    computed_hex = event_stream_digest_from_file(path, strict_mode=strict_mode)
    digest_obj = {"alg": "sha256", "hex": computed_hex}
    validate_digest_object(digest_obj, strict_mode=True)

    objs = read_ndjson(path, strict_mode=strict_mode)
    if not objs or not isinstance(objs[0], dict):
        raise PipelineError("HEADER_NOT_OBJECT", "EventStream header must be object")
    header: dict[str, Any] = objs[0]
    hdr_digest = header.get("event_stream_digest")
    validate_digest_object(hdr_digest, strict_mode=True)
    if hdr_digest.get("hex") != computed_hex:
        raise PipelineError(
            "EVENT_STREAM_HEADER_DIGEST_MISMATCH",
            "event_stream_digest in header does not match computed digest",
            {"expected": computed_hex, "observed": hdr_digest.get("hex")},
        )

    events: list[dict[str, Any]] = []
    for idx, e in enumerate(objs[1:], start=1):
        if not isinstance(e, dict):
            raise PipelineError("EVENT_NOT_OBJECT", "EventStream event must be object", {"index": idx})
        events.append(e)

    return header, events, digest_obj, objs


def _resolve_run_context_from_refs(
    *,
    scenario_ref: str,
    profile_ref: str | None,
    policy_ref: str | None,
    opponents_ref: str | None,
    paths_config_path: Path | None,
    postflop_solver_src_root: str | None,
    seed: int,
    strict_mode: bool,
) -> dict[str, Any]:
    scenario_registry = build_scenario_registry(strict_mode=True)
    scen_entry, scen_trace = resolve_scenario_ref(scenario_ref, registry=scenario_registry, strict_mode=bool(strict_mode))
    pkg_ref = scen_entry.get("scenario_package_ref")
    if not (isinstance(pkg_ref, str) and pkg_ref.startswith("path:")):
        raise PipelineError("VALUE_ERROR", "scenario registry entry has invalid scenario_package_ref", {"scenario_package_ref": pkg_ref})
    pkg_path = Path(pkg_ref.removeprefix("path:"))
    pkg = load_scenario_package(pkg_path)
    pkg_ids = validate_scenario_package(pkg, strict_mode=strict_mode)
    closure = scenario_closure_from_package(pkg, strict_mode=strict_mode)

    paths_config = _load_paths_config(paths_config_path=paths_config_path, strict_mode=strict_mode)
    if closure.get("postflop_ref") is not None:
        paths_config = _apply_postflop_solver_root(paths_config=paths_config, postflop_solver_src_root=postflop_solver_src_root)
        validate_paths_config(paths_config, strict_mode=strict_mode)
    resolved_paths, resolved_paths_digest, paths_trace = resolve_paths(
        paths_config=paths_config,
        scenario_package_closure=closure,
        strict_mode=strict_mode,
    )

    profile_registry = build_profile_registry(strict_mode=True)
    prof_req = profile_ref or "internal_profile_v1"
    prof_entry, prof_trace = resolve_profile_ref(prof_req, registry=profile_registry, strict_mode=bool(strict_mode))
    prof_spec_path = Path(str(prof_entry["profile_spec_ref"]).removeprefix("path:"))
    prof_spec = load_profile_spec(prof_spec_path)
    prof_id = profile_id(prof_spec, strict_mode=True)

    policy_registry = build_policy_registry(strict_mode=True)
    pol_req = policy_ref or "internal_baseline_policy_v1"
    pol_entry, pol_trace = resolve_policy_ref(pol_req, registry=policy_registry, strict_mode=bool(strict_mode))
    pol_spec_path = Path(str(pol_entry["policy_spec_ref"]).removeprefix("path:"))
    pol_spec = load_policy_spec(pol_spec_path)
    pol_id = policy_id(pol_spec, strict_mode=True)

    opponent_suite_id: str | None = closure.get("opponent_suite_id")
    opponent_artifact_id_or_params_hash: str | None = None
    opp_entry: dict[str, Any] | None = None
    opp_trace: dict[str, Any] | None = None
    if opponents_ref is not None:
        opp_reg = build_opponent_registry(strict_mode=True)
        opp_entry, opp_trace = resolve_opponent_suite_ref(opponents_ref, registry=opp_reg, strict_mode=bool(strict_mode))
        resolved_suite_id = opp_entry.get("opponent_suite_id")
        if resolved_suite_id != opponent_suite_id:
            raise PipelineError(
                "OPPONENT_SUITE_MISMATCH",
                "opponents_ref does not match ScenarioPackage opponent_suite_id",
                {"scenario_opponent_suite_id": opponent_suite_id, "resolved_opponent_suite_id": resolved_suite_id},
            )
    elif opponent_suite_id is not None:
        opp_reg = build_opponent_registry(strict_mode=True)
        opp_entry = opp_reg.get("opponent_suites", {}).get(opponent_suite_id)
        if opp_entry is None:
            raise PipelineError(
                "MISSING_REF",
                "opponent_suite_id from ScenarioPackage not found in registry",
                {"opponent_suite_id": opponent_suite_id},
            )

    if opp_entry is not None and opp_entry.get("calibration_id") is not None and opponent_artifact_id_or_params_hash is None:
        raise PipelineError(
            "CALIBRATION_REQUIRED",
            "opponent suite requires calibration artifact/params hash",
            {"opponent_suite_id": opponent_suite_id, "calibration_id": opp_entry.get("calibration_id")},
        )

    try:
        pokerkit_version = importlib.metadata.version("pokerkit")
    except Exception:  # pragma: no cover
        pokerkit_version = None
    solver_build_id: str | None = None
    if closure.get("postflop_ref") is not None:
        binding_kind = _binding_kind_from_profile(prof_spec)
        try:
            solver_root = postflop_solver_src_root_from_paths_trace(paths_trace)
            solver_build_id = compute_postflop_solver_build_id(
                src_root=solver_root, binding_kind=binding_kind, strict_mode=True
            )
        except PostflopSolverError as e:
            raise PipelineError(e.code, e.message, e.details) from e
    _enforce_postflop_deps(
        scenario_closure=closure,
        policy_spec=pol_spec,
        solver_build_id=solver_build_id,
        strict_mode=bool(strict_mode),
    )

    run_closure = {
        "scenario_id": pkg_ids["scenario_id"],
        "ruleset_id": closure["ruleset_id"],
        "triad": closure["triad"],
        "schema_hash": closure["schema_hash"],
        "resolved_paths_digest": resolved_paths_digest,
        "abstraction_hash": closure["abstraction_hash"],
        "policy_id": pol_id,
        "profile_id": prof_id,
        "opponent_suite_id": opponent_suite_id,
        "opponent_artifact_id_or_params_hash": opponent_artifact_id_or_params_hash,
        "mw_ladder_id": closure["mw_ladder_id"],
        "belief_spec_id": None,
        "mw_risk_spec_id": None,
        "adaptation_digest": None,
        "engine_build_id": None,
        "solver_build_id": solver_build_id,
        "pokerkit_version": pokerkit_version,
        "strict_mode": bool(strict_mode),
    }
    options_hash = compute_options_hash(run_closure, strict_mode=True)
    run_id = run_id_v1(options_hash=options_hash, seed=seed, strict_mode=True)

    runspec_obj = _build_runspec_obj(
        run_id=run_id,
        options_hash=options_hash,
        seed=seed,
        strict_mode=bool(strict_mode),
        scenario_id=pkg_ids["scenario_id"],
        profile_id=prof_id,
        policy_id=pol_id,
        opponent_suite_id=opponent_suite_id,
        resolved_paths_digest=resolved_paths_digest,
    )
    runspec_digest = _digest_for_obj(runspec_obj)

    return {
        "scenario_entry": scen_entry,
        "scenario_trace": scen_trace,
        "scenario_package_ref": pkg_ref,
        "scenario_package": pkg,
        "scenario_ids": pkg_ids,
        "scenario_closure": closure,
        "paths_config": paths_config,
        "resolved_paths": resolved_paths,
        "resolved_paths_digest": resolved_paths_digest,
        "paths_trace": paths_trace,
        "profile_entry": prof_entry,
        "profile_trace": prof_trace,
        "profile_spec": prof_spec,
        "profile_id": prof_id,
        "policy_entry": pol_entry,
        "policy_trace": pol_trace,
        "policy_spec": pol_spec,
        "policy_id": pol_id,
        "opponent_entry": opp_entry,
        "opponent_trace": opp_trace,
        "opponent_suite_id": opponent_suite_id,
        "opponent_artifact_id_or_params_hash": opponent_artifact_id_or_params_hash,
        "run_closure": run_closure,
        "options_hash": options_hash,
        "run_id": run_id,
        "runspec_obj": runspec_obj,
        "runspec_digest": runspec_digest,
        "seed": seed,
        "strict_mode": bool(strict_mode),
        "pokerkit_version": pokerkit_version,
    }


def _resolve_run_context_from_runspec(
    *,
    runspec_path: Path,
    paths_config_path: Path | None,
    postflop_solver_src_root: str | None,
    seed: int,
    strict_mode: bool,
) -> dict[str, Any]:
    runspec_obj = _load_runspec(runspec_path)
    if int(runspec_obj["seed"]) != int(seed):
        raise PipelineError(
            "RUNSPEC_SEED_MISMATCH",
            "seed must match runspec.seed when using --runspec",
            {"runspec_seed": runspec_obj["seed"], "requested_seed": seed},
        )
    if bool(runspec_obj["strict_mode"]) != bool(strict_mode):
        raise PipelineError(
            "RUNSPEC_STRICT_MISMATCH",
            "strict_mode must match runspec.strict_mode when using --runspec",
            {"runspec_strict_mode": runspec_obj["strict_mode"], "requested_strict_mode": strict_mode},
        )

    scenario_id = runspec_obj["scenario_id"]
    profile_id_hex = runspec_obj["profile_id"]
    policy_id_hex = runspec_obj["policy_id"]
    opponent_suite_id = runspec_obj.get("opponent_suite_id")
    resolved_paths_digest = runspec_obj["resolved_paths_digest"]

    scenario_registry = build_scenario_registry(strict_mode=True)
    scen_entry = scenario_registry.get(scenario_id)
    if scen_entry is None:
        raise PipelineError("MISSING_REF", "scenario_id not found in registry", {"scenario_id": scenario_id})
    scen_trace = {"requested_scenario_ref": f"scenario://{scenario_id}", "resolved_scenario_ref": f"scenario://{scenario_id}", "candidates_or_null": None}

    pkg_ref = scen_entry.get("scenario_package_ref")
    if not (isinstance(pkg_ref, str) and pkg_ref.startswith("path:")):
        raise PipelineError("VALUE_ERROR", "scenario registry entry has invalid scenario_package_ref", {"scenario_package_ref": pkg_ref})
    pkg_path = Path(pkg_ref.removeprefix("path:"))
    pkg = load_scenario_package(pkg_path)
    pkg_ids = validate_scenario_package(pkg, strict_mode=strict_mode)
    closure = scenario_closure_from_package(pkg, strict_mode=strict_mode)

    if pkg_ids.get("scenario_id") != scenario_id:
        raise PipelineError(
            "SCENARIO_ID_MISMATCH",
            "runspec.scenario_id does not match ScenarioPackage",
            {"runspec_scenario_id": scenario_id, "package_scenario_id": pkg_ids.get("scenario_id")},
        )

    if closure.get("opponent_suite_id") != opponent_suite_id:
        raise PipelineError(
            "OPPONENT_SUITE_MISMATCH",
            "runspec.opponent_suite_id does not match ScenarioPackage",
            {"runspec_opponent_suite_id": opponent_suite_id, "package_opponent_suite_id": closure.get("opponent_suite_id")},
        )

    paths_config = _load_paths_config(paths_config_path=paths_config_path, strict_mode=strict_mode)
    if closure.get("postflop_ref") is not None:
        paths_config = _apply_postflop_solver_root(paths_config=paths_config, postflop_solver_src_root=postflop_solver_src_root)
        validate_paths_config(paths_config, strict_mode=strict_mode)
    resolved_paths, computed_digest, paths_trace = resolve_paths(
        paths_config=paths_config,
        scenario_package_closure=closure,
        strict_mode=strict_mode,
    )
    if computed_digest != resolved_paths_digest:
        raise PipelineError(
            "RESOLVED_PATHS_DIGEST_MISMATCH",
            "runspec.resolved_paths_digest does not match computed digest",
            {"expected": resolved_paths_digest, "observed": computed_digest},
        )

    profile_registry = build_profile_registry(strict_mode=True)
    prof_entry = profile_registry.get(profile_id_hex)
    if prof_entry is None:
        raise PipelineError("MISSING_REF", "profile_id not found in registry", {"profile_id": profile_id_hex})
    prof_spec_path = Path(str(prof_entry["profile_spec_ref"]).removeprefix("path:"))
    prof_spec = load_profile_spec(prof_spec_path)
    prof_id = profile_id(prof_spec, strict_mode=True)
    if prof_id != profile_id_hex:
        raise PipelineError("PROFILE_ID_MISMATCH", "profile_id does not match computed spec id", {"expected": prof_id_hex, "observed": prof_id})

    policy_registry = build_policy_registry(strict_mode=True)
    pol_entry = policy_registry.get(policy_id_hex)
    if pol_entry is None:
        raise PipelineError("MISSING_REF", "policy_id not found in registry", {"policy_id": policy_id_hex})
    pol_spec_path = Path(str(pol_entry["policy_spec_ref"]).removeprefix("path:"))
    pol_spec = load_policy_spec(pol_spec_path)
    pol_id = policy_id(pol_spec, strict_mode=True)
    if pol_id != policy_id_hex:
        raise PipelineError("POLICY_ID_MISMATCH", "policy_id does not match computed spec id", {"expected": policy_id_hex, "observed": pol_id})

    opp_entry: dict[str, Any] | None = None
    opp_trace: dict[str, Any] | None = None
    opponent_artifact_id_or_params_hash: str | None = None
    if opponent_suite_id is not None:
        opp_reg = build_opponent_registry(strict_mode=True)
        opp_entry = opp_reg.get("opponent_suites", {}).get(opponent_suite_id)
        if opp_entry is None:
            raise PipelineError("MISSING_REF", "opponent_suite_id not found in registry", {"opponent_suite_id": opponent_suite_id})
        opp_trace = {"requested_opponents_ref": f"opponent_suite://{opponent_suite_id}", "resolved_opponents_ref": f"opponent_suite://{opponent_suite_id}", "candidates_or_null": None}
        if opp_entry.get("calibration_id") is not None and opponent_artifact_id_or_params_hash is None:
            raise PipelineError(
                "CALIBRATION_REQUIRED",
                "opponent suite requires calibration artifact/params hash",
                {"opponent_suite_id": opponent_suite_id, "calibration_id": opp_entry.get("calibration_id")},
            )

    try:
        pokerkit_version = importlib.metadata.version("pokerkit")
    except Exception:  # pragma: no cover
        pokerkit_version = None
    solver_build_id: str | None = None
    if closure.get("postflop_ref") is not None:
        binding_kind = _binding_kind_from_profile(prof_spec)
        try:
            solver_root = postflop_solver_src_root_from_paths_trace(paths_trace)
            solver_build_id = compute_postflop_solver_build_id(
                src_root=solver_root, binding_kind=binding_kind, strict_mode=True
            )
        except PostflopSolverError as e:
            raise PipelineError(e.code, e.message, e.details) from e
    _enforce_postflop_deps(
        scenario_closure=closure,
        policy_spec=pol_spec,
        solver_build_id=solver_build_id,
        strict_mode=bool(strict_mode),
    )

    run_closure = {
        "scenario_id": scenario_id,
        "ruleset_id": closure["ruleset_id"],
        "triad": closure["triad"],
        "schema_hash": closure["schema_hash"],
        "resolved_paths_digest": resolved_paths_digest,
        "abstraction_hash": closure["abstraction_hash"],
        "policy_id": pol_id,
        "profile_id": prof_id,
        "opponent_suite_id": opponent_suite_id,
        "opponent_artifact_id_or_params_hash": opponent_artifact_id_or_params_hash,
        "mw_ladder_id": closure["mw_ladder_id"],
        "belief_spec_id": None,
        "mw_risk_spec_id": None,
        "adaptation_digest": None,
        "engine_build_id": None,
        "solver_build_id": solver_build_id,
        "pokerkit_version": pokerkit_version,
        "strict_mode": bool(strict_mode),
    }
    options_hash = compute_options_hash(run_closure, strict_mode=True)
    if options_hash != runspec_obj["options_hash"]:
        raise PipelineError(
            "OPTIONS_HASH_MISMATCH",
            "runspec.options_hash does not match computed options_hash",
            {"expected": runspec_obj["options_hash"], "observed": options_hash},
        )

    run_id = run_id_v1(options_hash=options_hash, seed=seed, strict_mode=True)
    if run_id != runspec_obj["run_id"]:
        raise PipelineError(
            "RUN_ID_MISMATCH",
            "runspec.run_id does not match computed run_id",
            {"expected": runspec_obj["run_id"], "observed": run_id},
        )

    runspec_digest = _digest_for_obj(runspec_obj)

    return {
        "scenario_entry": scen_entry,
        "scenario_trace": scen_trace,
        "scenario_package_ref": pkg_ref,
        "scenario_package": pkg,
        "scenario_ids": pkg_ids,
        "scenario_closure": closure,
        "paths_config": paths_config,
        "resolved_paths": resolved_paths,
        "resolved_paths_digest": resolved_paths_digest,
        "paths_trace": paths_trace,
        "profile_entry": prof_entry,
        "profile_trace": {"requested_profile_ref": f"profile://{profile_id_hex}", "resolved_profile_ref": f"profile://{profile_id_hex}", "candidates_or_null": None},
        "profile_spec": prof_spec,
        "profile_id": prof_id,
        "policy_entry": pol_entry,
        "policy_trace": {"requested_policy_ref": f"policy://{policy_id_hex}", "resolved_policy_ref": f"policy://{policy_id_hex}", "candidates_or_null": None},
        "policy_spec": pol_spec,
        "policy_id": pol_id,
        "opponent_entry": opp_entry,
        "opponent_trace": opp_trace,
        "opponent_suite_id": opponent_suite_id,
        "opponent_artifact_id_or_params_hash": opponent_artifact_id_or_params_hash,
        "run_closure": run_closure,
        "options_hash": options_hash,
        "run_id": run_id,
        "runspec_obj": runspec_obj,
        "runspec_digest": runspec_digest,
        "seed": seed,
        "strict_mode": bool(strict_mode),
        "pokerkit_version": pokerkit_version,
    }


def _resolve_run_context(
    *,
    scenario_ref: str | None,
    profile_ref: str | None,
    policy_ref: str | None,
    opponents_ref: str | None,
    runspec_path: Path | None,
    paths_config_path: Path | None,
    postflop_solver_src_root: str | None,
    seed: int,
    strict_mode: bool,
) -> dict[str, Any]:
    if runspec_path is not None:
        return _resolve_run_context_from_runspec(
            runspec_path=runspec_path,
            paths_config_path=paths_config_path,
            postflop_solver_src_root=postflop_solver_src_root,
            seed=seed,
            strict_mode=strict_mode,
        )
    if scenario_ref is None:
        raise PipelineError("ARGUMENT_ERROR", "--scenario is required when --runspec is not provided")
    return _resolve_run_context_from_refs(
        scenario_ref=scenario_ref,
        profile_ref=profile_ref,
        policy_ref=policy_ref,
        opponents_ref=opponents_ref,
        paths_config_path=paths_config_path,
        postflop_solver_src_root=postflop_solver_src_root,
        seed=seed,
        strict_mode=strict_mode,
    )


def _artifact_refs(*, run_id: str) -> dict[str, str]:
    return {
        "runspec_ref": f"run://{run_id}/runspec",
        "run_manifest_ref": f"run://{run_id}/manifest",
        "event_stream_ref": f"run://{run_id}/event_stream",
        "report_ref": f"run://{run_id}/report",
        "doctor_report_ref": f"run://{run_id}/report/doctor",
    }


def _report_digest_for_stage(report_obj: dict[str, Any]) -> dict[str, str]:
    hash_input = {k: v for k, v in report_obj.items() if k not in ("run_manifest_ref", "run_manifest_digest", "event_stream_ref")}
    return {"alg": "sha256", "hex": sha256_hex(canonicalize_json_bytes(hash_input, strict_mode=True))}


def _artifacts_root_from_paths(
    *,
    paths_trace: dict[str, Any],
    artifacts_root_override: Path | None,
) -> tuple[Path, str | None]:
    roots = paths_trace.get("resolved_roots_abs") if isinstance(paths_trace, dict) else None
    default_abs = None
    if isinstance(roots, dict):
        default_abs = roots.get("artifacts_root_abs_or_null")
    if default_abs is None:
        raise PipelineError("ARTIFACTS_ROOT_MISSING", "resolved artifacts_root_abs missing from paths_trace", {"paths_trace": paths_trace})
    base = Path(default_abs)
    if artifacts_root_override is not None:
        return artifacts_root_override, str(artifacts_root_override.resolve())
    return base, None


def pipeline_init(
    *,
    scenario_ref: str | None,
    profile_ref: str | None,
    policy_ref: str | None,
    opponents_ref: str | None,
    runspec_path: Path | None,
    seed: int,
    strict_mode: bool,
    artifacts_root: Path | None = None,
    paths_config_path: Path | None = None,
    postflop_solver_src_root: str | None = None,
) -> dict[str, Any]:
    ctx = _resolve_run_context(
        scenario_ref=scenario_ref,
        profile_ref=profile_ref,
        policy_ref=policy_ref,
        opponents_ref=opponents_ref,
        runspec_path=runspec_path,
        paths_config_path=paths_config_path,
        postflop_solver_src_root=postflop_solver_src_root,
        seed=seed,
        strict_mode=strict_mode,
    )

    run_id = ctx["run_id"]
    options_hash = ctx["options_hash"]
    scenario_id = ctx["scenario_ids"]["scenario_id"]

    artifact_root, override_abs = _artifacts_root_from_paths(paths_trace=ctx["paths_trace"], artifacts_root_override=artifacts_root)
    artifact_paths = run_artifact_paths(run_id=run_id, artifacts_root=artifact_root)
    refs = _artifact_refs(run_id=run_id)
    doctor_report_path = artifact_paths["report_dir"] / "doctor_report.json"

    fixture_path = _find_internal_fixture_eventstream(run_id=run_id)
    if fixture_path is None:
        raise PipelineError(
            "MISSING_FIXTURE",
            "no internal fixture eventstream matches run_id",
            {"run_id": run_id, "options_hash": options_hash, "scenario_id": scenario_id},
        )

    header, _events, _digest_obj, _objs = _read_eventstream_with_digest(fixture_path, strict_mode=True)
    if header.get("run_id") != run_id:
        raise PipelineError("RUN_ID_MISMATCH", "eventstream header run_id mismatch", {"expected": run_id, "observed": header.get("run_id")})
    if header.get("options_hash") != options_hash:
        raise PipelineError(
            "OPTIONS_HASH_MISMATCH",
            "eventstream header options_hash mismatch",
            {"expected": options_hash, "observed": header.get("options_hash")},
        )
    if header.get("scenario_id") != scenario_id:
        raise PipelineError(
            "SCENARIO_ID_MISMATCH",
            "eventstream header scenario_id mismatch",
            {"expected": scenario_id, "observed": header.get("scenario_id")},
        )
    if header.get("resolved_paths_digest") != ctx["resolved_paths_digest"]:
        raise PipelineError(
            "RESOLVED_PATHS_DIGEST_MISMATCH",
            "eventstream header resolved_paths_digest mismatch",
            {"expected": ctx["resolved_paths_digest"], "observed": header.get("resolved_paths_digest")},
        )

    provenance_ref = header.get("provenance_ref")
    if not isinstance(provenance_ref, str):
        raise PipelineError("PROVENANCE_REF_MISSING", "eventstream header provenance_ref missing or invalid")
    repro_tier = header.get("repro_tier")
    if not isinstance(repro_tier, str):
        raise PipelineError("REPRO_TIER_MISSING", "eventstream header repro_tier missing or invalid")

    expected_context = {
        "ruleset_id": ctx["scenario_closure"]["ruleset_id"],
        "triad": ctx["scenario_closure"]["triad"],
        "schema_hash": ctx["scenario_closure"]["schema_hash"],
        "abstraction_hash": ctx["scenario_closure"]["abstraction_hash"],
        "resolved_paths_digest": ctx["resolved_paths_digest"],
    }
    failures, gate_out = check_scenario_package_gate(
        requested_scenario_ref=scenario_ref,
        header=header,
        scenario_package=ctx["scenario_package"],
        expected_context=expected_context,
        paths_config=ctx["paths_config"],
        event_stream_ref=refs["event_stream_ref"],
        event_stream_digest=None,
        strict_mode=bool(strict_mode),
    )
    if failures:
        raise PipelineError("SCENARIO_GATE_FAIL", "scenario package gate failed", {"failures": failures})

    runspec_path_out = artifact_paths["manifest_dir"] / "runspec.json"
    write_canonical_json(runspec_path_out, ctx["runspec_obj"], strict_mode=True)

    runspec_summary = _artifact_summary(
        artifact_kind="runspec",
        artifact_ref=refs["runspec_ref"],
        digest=ctx["runspec_digest"],
        counts={"keys": len(ctx["runspec_obj"])},
        provenance_ref=provenance_ref,
    )
    scen_digest = ctx["scenario_entry"].get("scenario_package_digest")
    if not isinstance(scen_digest, dict):
        scen_digest = _digest_for_obj(ctx["scenario_package"])
    scenario_summary = _artifact_summary(
        artifact_kind="scenario_package",
        artifact_ref=ctx["scenario_package_ref"],
        digest=scen_digest,
        counts={"keys": len(ctx["scenario_package"])},
        provenance_ref=provenance_ref,
    )

    stages = [
        {
            "stage_id": "init",
            "effective_context": _effective_context(
                scenario_id=scenario_id,
                ruleset_id=ctx["scenario_closure"]["ruleset_id"],
                triad=ctx["scenario_closure"]["triad"],
                schema_hash=ctx["scenario_closure"]["schema_hash"],
                options_hash=options_hash,
                resolved_paths_digest=ctx["resolved_paths_digest"],
            ),
            "inputs_summary": [],
            "outputs_summary": [runspec_summary, scenario_summary],
            "status": "pass",
            "degraded": False,
            "degraded_reason": None,
            "degraded_counts": {},
            "evidence_ref": None,
        }
    ]

    resolution_trace = {
        "artifacts_root_abs": str(artifact_root.resolve()),
        "artifacts_root_override_abs_or_null": override_abs,
        "artifact_locations": [
            {"artifact_ref": refs["runspec_ref"], "abs_path": str(runspec_path_out.resolve())},
            {"artifact_ref": refs["event_stream_ref"], "abs_path": str(artifact_paths["eventstream_path"].resolve())},
            {"artifact_ref": refs["doctor_report_ref"], "abs_path": str(doctor_report_path.resolve())},
            {"artifact_ref": refs["report_ref"], "abs_path": str(artifact_paths["report_path"].resolve())},
            {"artifact_ref": refs["run_manifest_ref"], "abs_path": str(artifact_paths["run_manifest_path"].resolve())},
        ],
        "scenario_resolution": ctx["scenario_trace"],
        "scenario_package": {"ref": ctx["scenario_package_ref"], "digest": scen_digest},
        "paths_resolution": {"paths_config": ctx["paths_config"], "resolved_paths_trace": ctx["paths_trace"]},
        "profile_resolution": {**ctx["profile_trace"], "profile_spec_ref": ctx["profile_entry"]["profile_spec_ref"], "profile_spec_digest": ctx["profile_entry"]["profile_spec_digest"]},
        "policy_resolution": {**ctx["policy_trace"], "policy_spec_ref": ctx["policy_entry"]["policy_spec_ref"], "policy_spec_digest": ctx["policy_entry"]["policy_spec_digest"]},
        "opponents_resolution_or_null": ctx["opponent_trace"],
    }
    if runspec_path is not None:
        resolution_trace["runspec_input_ref"] = f"path:{runspec_path}"

    manifest = finalize_run_manifest(
        {
            "run_manifest_schema_id": "run_manifest_v1",
            "run_id_schema": "run_id_v1",
            "run_id": run_id,
            "options_hash": options_hash,
            "seed": seed,
            "strict_mode": bool(strict_mode),
            "repro_tier": repro_tier,
            "run_instance_uuid": None,
            "scenario_id": scenario_id,
            "ruleset_id": ctx["scenario_closure"]["ruleset_id"],
            "triad": ctx["scenario_closure"]["triad"],
            "schema_hash": ctx["scenario_closure"]["schema_hash"],
            "profile_id": ctx["profile_id"],
            "policy_id": ctx["policy_id"],
            "opponent_suite_id": ctx["opponent_suite_id"],
            "execution_hint": None,
            "provenance_ref": provenance_ref,
            "rng_lineage_id": None,
            "resolved_paths": ctx["resolved_paths"],
            "resolved_paths_digest": ctx["resolved_paths_digest"],
            "stages": stages,
            "resolution_trace": resolution_trace,
        },
        strict_mode=True,
    )
    validate_run_manifest(manifest, strict_mode=True)
    write_canonical_json(artifact_paths["run_manifest_path"], manifest, strict_mode=True)

    return {
        "status": "pass",
        "run_id": run_id,
        "options_hash": options_hash,
        "scenario_id": scenario_id,
        "runspec_ref": refs["runspec_ref"],
        "runspec_digest": ctx["runspec_digest"],
        "run_manifest_ref": refs["run_manifest_ref"],
        "run_manifest_digest": manifest["run_manifest_digest"],
    }


def pipeline_solve_postflop(
    *,
    scenario_ref: str | None,
    profile_ref: str | None,
    policy_ref: str | None,
    opponents_ref: str | None,
    runspec_path: Path | None,
    postflop_config_path: Path | None,
    seed: int,
    strict_mode: bool,
    artifacts_root: Path | None = None,
    paths_config_path: Path | None = None,
    postflop_solver_src_root: str | None = None,
) -> dict[str, Any]:
    if postflop_config_path is None:
        raise PipelineError("POSTFLOP_CONFIG_MISSING", "--postflop-config is required for solve-postflop stage")

    ctx = _resolve_run_context(
        scenario_ref=scenario_ref,
        profile_ref=profile_ref,
        policy_ref=policy_ref,
        opponents_ref=opponents_ref,
        runspec_path=runspec_path,
        paths_config_path=paths_config_path,
        postflop_solver_src_root=postflop_solver_src_root,
        seed=seed,
        strict_mode=strict_mode,
    )

    run_id = ctx["run_id"]
    options_hash = ctx["options_hash"]
    scenario_id = ctx["scenario_ids"]["scenario_id"]

    artifact_root, override_abs = _artifacts_root_from_paths(paths_trace=ctx["paths_trace"], artifacts_root_override=artifacts_root)
    artifact_paths = run_artifact_paths(run_id=run_id, artifacts_root=artifact_root)
    refs = _artifact_refs(run_id=run_id)

    manifest: dict[str, Any] | None = None
    if artifact_paths["run_manifest_path"].exists():
        manifest = json.loads(artifact_paths["run_manifest_path"].read_text(encoding="utf-8"))
        validate_run_manifest(manifest, strict_mode=True)

    try:
        config_bytes_raw = postflop_config_path.read_bytes()
        config_obj = json.loads(config_bytes_raw.decode("utf-8"))
    except Exception as e:
        raise PipelineError("POSTFLOP_CONFIG_INVALID", "postflop config must be valid JSON", {"path": str(postflop_config_path), "error": str(e)}) from e
    config_digest = {"alg": "sha256", "hex": sha256_hex(config_bytes_raw)}
    validate_digest_object(config_digest, strict_mode=True)
    config_counts: dict[str, int] = {"bytes": len(config_bytes_raw)}
    if isinstance(config_obj, dict):
        config_counts["keys"] = len(config_obj)
    elif isinstance(config_obj, list):
        config_counts["items"] = len(config_obj)

    postflop_ref = ctx["scenario_package"].get("postflop_ref")
    if postflop_ref is None:
        raise PipelineError("POSTFLOP_REF_MISSING", "ScenarioPackage.postflop_ref is required for solve-postflop stage", {})
    if not isinstance(postflop_ref, dict):
        raise PipelineError("POSTFLOP_REF_INVALID", "ScenarioPackage.postflop_ref must be object", {"postflop_ref": postflop_ref})
    artifact_ref = postflop_ref.get("artifact_ref")
    digest = postflop_ref.get("digest")
    if not isinstance(artifact_ref, str):
        raise PipelineError("POSTFLOP_REF_INVALID", "postflop_ref.artifact_ref must be string", {"postflop_ref": postflop_ref})
    validate_digest_object(digest, strict_mode=True)

    if not artifact_ref.startswith("artifact://"):
        raise PipelineError(
            "POSTFLOP_REF_UNSUPPORTED",
            "solve-postflop currently requires artifact:// refs for postflop_ref",
            {"artifact_ref": artifact_ref},
        )
    artifact_id = artifact_ref.removeprefix("artifact://")
    validate_digest_object({"alg": "sha256", "hex": artifact_id}, strict_mode=True)
    if digest.get("hex") != artifact_id:
        raise PipelineError(
            "POSTFLOP_DIGEST_MISMATCH",
            "postflop_ref.digest must match artifact_ref id",
            {"artifact_ref": artifact_ref, "digest": digest},
        )

    solver_build_id = ctx["run_closure"].get("solver_build_id")
    if solver_build_id is None:
        raise PipelineError("SOLVER_BUILD_ID_MISSING", "solver_build_id missing for solve-postflop stage", {})

    _action_adapter_spec, action_adapter_id = default_internal_action_adapter(strict_mode=True)
    provenance_env = build_provenance_envelope_v1(
        ruleset_id=ctx["scenario_closure"]["ruleset_id"],
        triad=ctx["scenario_closure"]["triad"],
        schema_hash=ctx["scenario_closure"]["schema_hash"],
        options_hash=options_hash,
        seed=seed,
        action_adapter_id=action_adapter_id,
        mapping_spec_id=None,
        mw_ladder_id=ctx["scenario_closure"]["mw_ladder_id"],
        pokerkit_version=ctx["pokerkit_version"],
        engine_build_id=None,
        solver_build_id=solver_build_id,
        rng_lineage_id=None,
        seed_derivation_digest=None,
        repro_tier="Tier-A",
    )
    prov_id = provenance_id(provenance_env, strict_mode=True)
    provenance_ref = f"artifact://{prov_id}"
    _ = write_artifact_json(provenance_env, artifact_id=prov_id, strict_mode=True)

    if manifest is None:
        runspec_obj = _build_runspec_obj(
            run_id=run_id,
            options_hash=options_hash,
            seed=seed,
            strict_mode=bool(strict_mode),
            scenario_id=scenario_id,
            profile_id=ctx["profile_id"],
            policy_id=ctx["policy_id"],
            opponent_suite_id=ctx["opponent_suite_id"],
            resolved_paths_digest=ctx["resolved_paths_digest"],
        )
        runspec_digest = _digest_for_obj(runspec_obj)
        runspec_path_out = artifact_paths["manifest_dir"] / "runspec.json"
        write_canonical_json(runspec_path_out, runspec_obj, strict_mode=True)

        runspec_summary = _artifact_summary(
            artifact_kind="runspec",
            artifact_ref=refs["runspec_ref"],
            digest=runspec_digest,
            counts={"keys": len(runspec_obj)},
            provenance_ref=provenance_ref,
        )
        scen_digest = ctx["scenario_entry"].get("scenario_package_digest")
        if not isinstance(scen_digest, dict):
            scen_digest = _digest_for_obj(ctx["scenario_package"])
        scenario_summary = _artifact_summary(
            artifact_kind="scenario_package",
            artifact_ref=ctx["scenario_package_ref"],
            digest=scen_digest,
            counts={"keys": len(ctx["scenario_package"])},
            provenance_ref=provenance_ref,
        )

        stages = [
            {
                "stage_id": "init",
                "effective_context": _effective_context(
                    scenario_id=scenario_id,
                    ruleset_id=ctx["scenario_closure"]["ruleset_id"],
                    triad=ctx["scenario_closure"]["triad"],
                    schema_hash=ctx["scenario_closure"]["schema_hash"],
                    options_hash=options_hash,
                    resolved_paths_digest=ctx["resolved_paths_digest"],
                ),
                "inputs_summary": [],
                "outputs_summary": [runspec_summary, scenario_summary],
                "status": "pass",
                "degraded": False,
                "degraded_reason": None,
                "degraded_counts": {},
                "evidence_ref": None,
            }
        ]

        resolution_trace = {
            "artifacts_root_abs": str(artifact_root.resolve()),
            "artifacts_root_override_abs_or_null": override_abs,
            "artifact_locations": [
                {"artifact_ref": refs["runspec_ref"], "abs_path": str(runspec_path_out.resolve())},
                {"artifact_ref": refs["event_stream_ref"], "abs_path": str(artifact_paths["eventstream_path"].resolve())},
                {"artifact_ref": refs["doctor_report_ref"], "abs_path": str((artifact_paths["report_dir"] / "doctor_report.json").resolve())},
                {"artifact_ref": refs["report_ref"], "abs_path": str(artifact_paths["report_path"].resolve())},
                {"artifact_ref": refs["run_manifest_ref"], "abs_path": str(artifact_paths["run_manifest_path"].resolve())},
            ],
            "scenario_resolution": ctx["scenario_trace"],
            "scenario_package": {"ref": ctx["scenario_package_ref"], "digest": scen_digest},
            "paths_resolution": {"paths_config": ctx["paths_config"], "resolved_paths_trace": ctx["paths_trace"]},
            "profile_resolution": {**ctx["profile_trace"], "profile_spec_ref": ctx["profile_entry"]["profile_spec_ref"], "profile_spec_digest": ctx["profile_entry"]["profile_spec_digest"]},
            "policy_resolution": {**ctx["policy_trace"], "policy_spec_ref": ctx["policy_entry"]["policy_spec_ref"], "policy_spec_digest": ctx["policy_entry"]["policy_spec_digest"]},
            "opponents_resolution_or_null": ctx["opponent_trace"],
        }
        if runspec_path is not None:
            resolution_trace["runspec_input_ref"] = f"path:{runspec_path}"

        manifest = finalize_run_manifest(
            {
                "run_manifest_schema_id": "run_manifest_v1",
                "run_id_schema": "run_id_v1",
                "run_id": run_id,
                "options_hash": options_hash,
                "seed": seed,
                "strict_mode": bool(strict_mode),
                "repro_tier": "Tier-A",
                "run_instance_uuid": None,
                "scenario_id": scenario_id,
                "ruleset_id": ctx["scenario_closure"]["ruleset_id"],
                "triad": ctx["scenario_closure"]["triad"],
                "schema_hash": ctx["scenario_closure"]["schema_hash"],
                "profile_id": ctx["profile_id"],
                "policy_id": ctx["policy_id"],
                "opponent_suite_id": ctx["opponent_suite_id"],
                "execution_hint": None,
                "provenance_ref": provenance_ref,
                "rng_lineage_id": None,
                "resolved_paths": ctx["resolved_paths"],
                "resolved_paths_digest": ctx["resolved_paths_digest"],
                "stages": stages,
                "resolution_trace": resolution_trace,
            },
            strict_mode=True,
        )
        validate_run_manifest(manifest, strict_mode=True)
        write_canonical_json(artifact_paths["run_manifest_path"], manifest, strict_mode=True)

    resolution_trace = manifest.get("resolution_trace") if manifest is not None else None
    if isinstance(resolution_trace, dict):
        resolution_trace["postflop_config_ref"] = f"path:{postflop_config_path}"
        manifest["resolution_trace"] = resolution_trace
    try:
        solver_root = postflop_solver_src_root_from_paths_trace(ctx["paths_trace"])
        out_root = runtime_artifacts_store_root()
        out_path = out_root / f"{artifact_id}.bin"
        tmp_path = out_root / f"{artifact_id}.tmp"
        if tmp_path.exists():
            tmp_path.unlink()
        digest_obj = solve_postflop_library(
            src_root=solver_root,
            solver_build_id=solver_build_id,
            config_path=postflop_config_path,
            output_path=tmp_path,
        )
    except PostflopSolverError as e:
        raise PipelineError(e.code, e.message, e.details) from e

    if digest_obj.get("hex") != digest.get("hex"):
        if tmp_path.exists():
            tmp_path.unlink()
        raise PipelineError(
            "POSTFLOP_DIGEST_MISMATCH",
            "postflop solver output digest does not match ScenarioPackage.postflop_ref",
            {"expected": digest.get("hex"), "observed": digest_obj.get("hex")},
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.replace(out_path)

    scen_digest = ctx["scenario_entry"].get("scenario_package_digest")
    if not isinstance(scen_digest, dict):
        scen_digest = _digest_for_obj(ctx["scenario_package"])

    input_provenance_ref = manifest.get("provenance_ref")
    if not isinstance(input_provenance_ref, str):
        input_provenance_ref = provenance_ref

    input_summary = _artifact_summary(
        artifact_kind="scenario_package",
        artifact_ref=ctx["scenario_package_ref"],
        digest=scen_digest,
        counts={"keys": len(ctx["scenario_package"])},
        provenance_ref=input_provenance_ref,
    )
    config_summary = _artifact_summary(
        artifact_kind="dataset",
        artifact_ref=f"path:{postflop_config_path}",
        digest=config_digest,
        counts=config_counts,
        provenance_ref=input_provenance_ref,
    )

    output_summary = _artifact_summary(
        artifact_kind="dataset",
        artifact_ref=artifact_ref,
        digest=digest_obj,
        counts={"bytes": out_path.stat().st_size},
        provenance_ref=provenance_ref,
    )

    stage_solve = {
        "stage_id": "solve-postflop",
        "effective_context": _effective_context(
            scenario_id=scenario_id,
            ruleset_id=ctx["scenario_closure"]["ruleset_id"],
            triad=ctx["scenario_closure"]["triad"],
            schema_hash=ctx["scenario_closure"]["schema_hash"],
            options_hash=options_hash,
            resolved_paths_digest=ctx["resolved_paths_digest"],
        ),
        "inputs_summary": [input_summary, config_summary],
        "outputs_summary": [output_summary],
        "status": "pass",
        "degraded": False,
        "degraded_reason": None,
        "degraded_counts": {},
        "evidence_ref": None,
    }

    manifest["stages"] = _upsert_stage(manifest.get("stages", []), stage_solve)
    manifest = finalize_run_manifest(manifest, strict_mode=True)
    validate_run_manifest(manifest, strict_mode=True)
    write_canonical_json(artifact_paths["run_manifest_path"], manifest, strict_mode=True)

    return {
        "status": "pass",
        "run_id": run_id,
        "options_hash": options_hash,
        "scenario_id": scenario_id,
        "postflop_ref": postflop_ref,
        "provenance_ref": provenance_ref,
        "run_manifest_ref": refs["run_manifest_ref"],
        "run_manifest_digest": manifest["run_manifest_digest"],
    }


def pipeline_eval(
    *,
    scenario_ref: str | None,
    profile_ref: str | None,
    policy_ref: str | None,
    opponents_ref: str | None,
    runspec_path: Path | None,
    seed: int,
    strict_mode: bool,
    artifacts_root: Path | None = None,
    paths_config_path: Path | None = None,
    postflop_solver_src_root: str | None = None,
) -> dict[str, Any]:
    ctx = _resolve_run_context(
        scenario_ref=scenario_ref,
        profile_ref=profile_ref,
        policy_ref=policy_ref,
        opponents_ref=opponents_ref,
        runspec_path=runspec_path,
        paths_config_path=paths_config_path,
        postflop_solver_src_root=postflop_solver_src_root,
        seed=seed,
        strict_mode=strict_mode,
    )
    run_id = ctx["run_id"]
    options_hash = ctx["options_hash"]
    scenario_id = ctx["scenario_ids"]["scenario_id"]

    artifact_root, override_abs = _artifacts_root_from_paths(paths_trace=ctx["paths_trace"], artifacts_root_override=artifacts_root)
    artifact_paths = run_artifact_paths(run_id=run_id, artifacts_root=artifact_root)
    refs = _artifact_refs(run_id=run_id)

    if not artifact_paths["run_manifest_path"].exists():
        pipeline_init(
            scenario_ref=scenario_ref,
            profile_ref=profile_ref,
            policy_ref=policy_ref,
            opponents_ref=opponents_ref,
            runspec_path=runspec_path,
            seed=seed,
            strict_mode=strict_mode,
            artifacts_root=artifact_root if override_abs is not None else None,
            paths_config_path=paths_config_path,
            postflop_solver_src_root=postflop_solver_src_root,
        )

    manifest = json.loads(artifact_paths["run_manifest_path"].read_text(encoding="utf-8"))
    validate_run_manifest(manifest, strict_mode=True)
    if manifest.get("run_id") != run_id:
        raise PipelineError("RUN_ID_MISMATCH", "run_manifest run_id mismatch", {"expected": run_id, "observed": manifest.get("run_id")})
    if manifest.get("options_hash") != options_hash:
        raise PipelineError("OPTIONS_HASH_MISMATCH", "run_manifest options_hash mismatch", {"expected": options_hash, "observed": manifest.get("options_hash")})

    if manifest.get("run_id") != run_id:
        raise PipelineError("RUN_ID_MISMATCH", "run_manifest run_id mismatch", {"expected": run_id, "observed": manifest.get("run_id")})
    if manifest.get("options_hash") != options_hash:
        raise PipelineError("OPTIONS_HASH_MISMATCH", "run_manifest options_hash mismatch", {"expected": options_hash, "observed": manifest.get("options_hash")})
    if manifest.get("scenario_id") != scenario_id:
        raise PipelineError("SCENARIO_ID_MISMATCH", "run_manifest scenario_id mismatch", {"expected": scenario_id, "observed": manifest.get("scenario_id")})
    if manifest.get("resolved_paths_digest") != ctx["resolved_paths_digest"]:
        raise PipelineError(
            "RESOLVED_PATHS_DIGEST_MISMATCH",
            "run_manifest resolved_paths_digest mismatch",
            {"expected": ctx["resolved_paths_digest"], "observed": manifest.get("resolved_paths_digest")},
        )

    fixture_path = _find_internal_fixture_eventstream(run_id=run_id)
    if fixture_path is None:
        raise PipelineError(
            "MISSING_FIXTURE",
            "no internal fixture eventstream matches run_id",
            {"run_id": run_id, "options_hash": options_hash, "scenario_id": scenario_id},
        )

    out_eventstream_path = artifact_paths["eventstream_path"]
    out_eventstream_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture_path, out_eventstream_path)

    header, events, digest_obj, objs = _read_eventstream_with_digest(out_eventstream_path, strict_mode=True)
    if header.get("run_id") != run_id:
        raise PipelineError("RUN_ID_MISMATCH", "eventstream header run_id mismatch", {"expected": run_id, "observed": header.get("run_id")})
    if header.get("options_hash") != options_hash:
        raise PipelineError(
            "OPTIONS_HASH_MISMATCH",
            "eventstream header options_hash mismatch",
            {"expected": options_hash, "observed": header.get("options_hash")},
        )
    if header.get("scenario_id") != scenario_id:
        raise PipelineError(
            "SCENARIO_ID_MISMATCH",
            "eventstream header scenario_id mismatch",
            {"expected": scenario_id, "observed": header.get("scenario_id")},
        )
    if header.get("resolved_paths_digest") != ctx["resolved_paths_digest"]:
        raise PipelineError(
            "RESOLVED_PATHS_DIGEST_MISMATCH",
            "eventstream header resolved_paths_digest mismatch",
            {"expected": ctx["resolved_paths_digest"], "observed": header.get("resolved_paths_digest")},
        )
    if header.get("provenance_ref") != manifest.get("provenance_ref"):
        raise PipelineError(
            "PROVENANCE_REF_MISMATCH",
            "eventstream header provenance_ref mismatch",
            {"expected": manifest.get("provenance_ref"), "observed": header.get("provenance_ref")},
        )

    write_canonical_ndjson(out_eventstream_path, [header, *events], strict_mode=True)

    runspec_summary = _artifact_summary(
        artifact_kind="runspec",
        artifact_ref=refs["runspec_ref"],
        digest=ctx["runspec_digest"],
        counts={"keys": len(ctx["runspec_obj"])},
        provenance_ref=header.get("provenance_ref"),
    )
    hands_count = sum(1 for e in events if e.get("event") == "HandStart")
    event_summary = _artifact_summary(
        artifact_kind="event_stream",
        artifact_ref=refs["event_stream_ref"],
        digest=digest_obj,
        counts={"hands": hands_count, "events": len(objs)},
        provenance_ref=header.get("provenance_ref"),
    )

    stage_eval = {
        "stage_id": "eval",
        "effective_context": _effective_context(
            scenario_id=scenario_id,
            ruleset_id=ctx["scenario_closure"]["ruleset_id"],
            triad=ctx["scenario_closure"]["triad"],
            schema_hash=ctx["scenario_closure"]["schema_hash"],
            options_hash=options_hash,
            resolved_paths_digest=ctx["resolved_paths_digest"],
        ),
        "inputs_summary": [runspec_summary],
        "outputs_summary": [event_summary],
        "status": "pass",
        "degraded": False,
        "degraded_reason": None,
        "degraded_counts": {},
        "evidence_ref": None,
    }

    manifest["stages"] = _upsert_stage(manifest.get("stages", []), stage_eval)
    if isinstance(header.get("repro_tier"), str) and header.get("repro_tier") != manifest.get("repro_tier"):
        manifest["repro_tier"] = header.get("repro_tier")

    manifest = finalize_run_manifest(manifest, strict_mode=True)
    validate_run_manifest(manifest, strict_mode=True)
    write_canonical_json(artifact_paths["run_manifest_path"], manifest, strict_mode=True)

    return {
        "status": "pass",
        "run_id": run_id,
        "options_hash": options_hash,
        "scenario_id": scenario_id,
        "event_stream_ref": refs["event_stream_ref"],
        "event_stream_digest": digest_obj,
        "run_manifest_ref": refs["run_manifest_ref"],
        "run_manifest_digest": manifest["run_manifest_digest"],
        "artifacts_root_override_abs_or_null": override_abs,
    }


def pipeline_doctor(
    *,
    scenario_ref: str | None,
    profile_ref: str | None,
    policy_ref: str | None,
    opponents_ref: str | None,
    runspec_path: Path | None,
    seed: int,
    strict_mode: bool,
    artifacts_root: Path | None = None,
    paths_config_path: Path | None = None,
    postflop_solver_src_root: str | None = None,
) -> dict[str, Any]:
    ctx = _resolve_run_context(
        scenario_ref=scenario_ref,
        profile_ref=profile_ref,
        policy_ref=policy_ref,
        opponents_ref=opponents_ref,
        runspec_path=runspec_path,
        paths_config_path=paths_config_path,
        postflop_solver_src_root=postflop_solver_src_root,
        seed=seed,
        strict_mode=strict_mode,
    )
    run_id = ctx["run_id"]
    scenario_id = ctx["scenario_ids"]["scenario_id"]
    options_hash = ctx["options_hash"]

    artifact_root, override_abs = _artifacts_root_from_paths(paths_trace=ctx["paths_trace"], artifacts_root_override=artifacts_root)
    artifact_paths = run_artifact_paths(run_id=run_id, artifacts_root=artifact_root)
    refs = _artifact_refs(run_id=run_id)
    doctor_report_path = artifact_paths["report_dir"] / "doctor_report.json"

    if not artifact_paths["eventstream_path"].exists():
        raise PipelineError("MISSING_EVENTSTREAM", "eventstream missing; run eval stage first", {"path": str(artifact_paths["eventstream_path"])})

    manifest = json.loads(artifact_paths["run_manifest_path"].read_text(encoding="utf-8"))
    validate_run_manifest(manifest, strict_mode=True)
    if manifest.get("run_id") != run_id:
        raise PipelineError("RUN_ID_MISMATCH", "run_manifest run_id mismatch", {"expected": run_id, "observed": manifest.get("run_id")})
    if manifest.get("options_hash") != options_hash:
        raise PipelineError("OPTIONS_HASH_MISMATCH", "run_manifest options_hash mismatch", {"expected": options_hash, "observed": manifest.get("options_hash")})

    header, events, digest_obj, _objs = _read_eventstream_with_digest(artifact_paths["eventstream_path"], strict_mode=True)
    ruleset, _ruleset_ref = _load_ruleset_by_id(ruleset_id=ctx["scenario_closure"]["ruleset_id"])
    validate_ruleset(ruleset, strict_mode=True)

    gates_out = check_eventstream_gates(
        header=header,
        events=events,
        event_stream_ref=refs["event_stream_ref"],
        event_stream_digest=digest_obj,
        ruleset=ruleset,
        scenario_package=ctx.get("scenario_package"),
        requested_scenario_ref=scenario_ref or f"scenario://{scenario_id}",
        paths_config=ctx.get("paths_config"),
        strict_mode=bool(strict_mode),
    )

    rc_report = rule_conformance_report_from_eventstream(
        artifact_paths["eventstream_path"],
        event_stream_ref=refs["event_stream_ref"],
        ruleset=ruleset,
        checked_items=None,
        strict_mode=bool(strict_mode),
    )
    failures_count = int(rc_report.get("failures_count", 0))
    report_status = "pass" if gates_out.get("status") == "pass" and failures_count == 0 else "fail"

    report: dict[str, Any] = {
        "status": report_status,
        "metric_spec_id": metric_spec_id(strict_mode=True),
        "report_schema_id": report_schema_id(strict_mode=True),
        "run_manifest_ref": refs["run_manifest_ref"],
        "run_manifest_digest": None,
        "provenance_ref": header.get("provenance_ref"),
        "options_hash": header.get("options_hash"),
        "scenario_id": header.get("scenario_id"),
        "schema_hash": header.get("schema_hash"),
        "event_stream_ref": refs["event_stream_ref"],
        "event_stream_digest": digest_obj,
        "repro_tier": header.get("repro_tier"),
        "rule_conformance": rc_report,
    }

    report_digest_for_stage = _report_digest_for_stage(report)
    validate_digest_object(report_digest_for_stage, strict_mode=True)

    stage_doctor = {
        "stage_id": "doctor",
        "effective_context": _effective_context(
            scenario_id=scenario_id,
            ruleset_id=ctx["scenario_closure"]["ruleset_id"],
            triad=ctx["scenario_closure"]["triad"],
            schema_hash=ctx["scenario_closure"]["schema_hash"],
            options_hash=options_hash,
            resolved_paths_digest=ctx["resolved_paths_digest"],
        ),
        "inputs_summary": [
            _artifact_summary(
                artifact_kind="event_stream",
                artifact_ref=refs["event_stream_ref"],
                digest=digest_obj,
                counts={"hands": sum(1 for e in events if e.get("event") == "HandStart"), "events": len(events) + 1},
                provenance_ref=header.get("provenance_ref"),
            )
        ],
        "outputs_summary": [
            _artifact_summary(
                artifact_kind="report",
                artifact_ref=refs["doctor_report_ref"],
                digest=report_digest_for_stage,
                counts={"hands": int(rc_report.get("sampled_hands_count", 0)), "failures": failures_count},
                provenance_ref=header.get("provenance_ref"),
            )
        ],
        "status": report_status,
        "degraded": False,
        "degraded_reason": None,
        "degraded_counts": {},
        "evidence_ref": None if report_status == "pass" else {"event_stream_ref": refs["event_stream_ref"], "event_stream_digest": digest_obj, "hand_selector": None},
    }

    manifest["stages"] = _upsert_stage(manifest.get("stages", []), stage_doctor)
    manifest = finalize_run_manifest(manifest, strict_mode=True)
    validate_run_manifest(manifest, strict_mode=True)
    write_canonical_json(artifact_paths["run_manifest_path"], manifest, strict_mode=True)

    report["run_manifest_digest"] = manifest["run_manifest_digest"]
    write_canonical_json(doctor_report_path, report, strict_mode=True)

    return {
        "status": report_status,
        "run_id": run_id,
        "options_hash": options_hash,
        "scenario_id": scenario_id,
        "report_ref": refs["doctor_report_ref"],
        "report_digest": report_digest_for_stage,
        "run_manifest_ref": refs["run_manifest_ref"],
        "run_manifest_digest": manifest["run_manifest_digest"],
        "artifacts_root_override_abs_or_null": override_abs,
    }


def pipeline_stats(
    *,
    scenario_ref: str | None,
    profile_ref: str | None,
    policy_ref: str | None,
    opponents_ref: str | None,
    runspec_path: Path | None,
    seed: int,
    strict_mode: bool,
    artifacts_root: Path | None = None,
    paths_config_path: Path | None = None,
    postflop_solver_src_root: str | None = None,
) -> dict[str, Any]:
    ctx = _resolve_run_context(
        scenario_ref=scenario_ref,
        profile_ref=profile_ref,
        policy_ref=policy_ref,
        opponents_ref=opponents_ref,
        runspec_path=runspec_path,
        paths_config_path=paths_config_path,
        postflop_solver_src_root=postflop_solver_src_root,
        seed=seed,
        strict_mode=strict_mode,
    )
    run_id = ctx["run_id"]
    scenario_id = ctx["scenario_ids"]["scenario_id"]
    options_hash = ctx["options_hash"]

    artifact_root, override_abs = _artifacts_root_from_paths(paths_trace=ctx["paths_trace"], artifacts_root_override=artifacts_root)
    artifact_paths = run_artifact_paths(run_id=run_id, artifacts_root=artifact_root)
    refs = _artifact_refs(run_id=run_id)

    if not artifact_paths["eventstream_path"].exists():
        raise PipelineError("MISSING_EVENTSTREAM", "eventstream missing; run eval stage first", {"path": str(artifact_paths["eventstream_path"])})

    manifest = json.loads(artifact_paths["run_manifest_path"].read_text(encoding="utf-8"))
    validate_run_manifest(manifest, strict_mode=True)

    header, events, digest_obj, _objs = _read_eventstream_with_digest(artifact_paths["eventstream_path"], strict_mode=True)
    ruleset, _ruleset_ref = _load_ruleset_by_id(ruleset_id=ctx["scenario_closure"]["ruleset_id"])
    validate_ruleset(ruleset, strict_mode=True)

    rc_report = rule_conformance_report_from_eventstream(
        artifact_paths["eventstream_path"],
        event_stream_ref=refs["event_stream_ref"],
        ruleset=ruleset,
        checked_items=None,
        strict_mode=bool(strict_mode),
    )
    failures_count = int(rc_report.get("failures_count", 0))
    report_status = "pass" if failures_count == 0 else "fail"

    report: dict[str, Any] = {
        "status": report_status,
        "metric_spec_id": metric_spec_id(strict_mode=True),
        "report_schema_id": report_schema_id(strict_mode=True),
        "run_manifest_ref": refs["run_manifest_ref"],
        "run_manifest_digest": None,
        "provenance_ref": header.get("provenance_ref"),
        "options_hash": header.get("options_hash"),
        "scenario_id": header.get("scenario_id"),
        "schema_hash": header.get("schema_hash"),
        "event_stream_ref": refs["event_stream_ref"],
        "event_stream_digest": digest_obj,
        "repro_tier": header.get("repro_tier"),
        "rule_conformance": rc_report,
    }

    report_digest_for_stage = _report_digest_for_stage(report)
    validate_digest_object(report_digest_for_stage, strict_mode=True)

    stage_stats = {
        "stage_id": "stats",
        "effective_context": _effective_context(
            scenario_id=scenario_id,
            ruleset_id=ctx["scenario_closure"]["ruleset_id"],
            triad=ctx["scenario_closure"]["triad"],
            schema_hash=ctx["scenario_closure"]["schema_hash"],
            options_hash=options_hash,
            resolved_paths_digest=ctx["resolved_paths_digest"],
        ),
        "inputs_summary": [
            _artifact_summary(
                artifact_kind="event_stream",
                artifact_ref=refs["event_stream_ref"],
                digest=digest_obj,
                counts={"hands": sum(1 for e in events if e.get("event") == "HandStart"), "events": len(events) + 1},
                provenance_ref=header.get("provenance_ref"),
            )
        ],
        "outputs_summary": [
            _artifact_summary(
                artifact_kind="report",
                artifact_ref=refs["report_ref"],
                digest=report_digest_for_stage,
                counts={"hands": int(rc_report.get("sampled_hands_count", 0)), "failures": failures_count},
                provenance_ref=header.get("provenance_ref"),
            )
        ],
        "status": report_status,
        "degraded": False,
        "degraded_reason": None,
        "degraded_counts": {},
        "evidence_ref": None if report_status == "pass" else {"event_stream_ref": refs["event_stream_ref"], "event_stream_digest": digest_obj, "hand_selector": None},
    }

    manifest["stages"] = _upsert_stage(manifest.get("stages", []), stage_stats)
    manifest = finalize_run_manifest(manifest, strict_mode=True)
    validate_run_manifest(manifest, strict_mode=True)
    write_canonical_json(artifact_paths["run_manifest_path"], manifest, strict_mode=True)

    report["run_manifest_digest"] = manifest["run_manifest_digest"]
    write_canonical_json(artifact_paths["report_path"], report, strict_mode=True)

    return {
        "status": report_status,
        "run_id": run_id,
        "options_hash": options_hash,
        "scenario_id": scenario_id,
        "report_ref": refs["report_ref"],
        "report_digest": report_digest_for_stage,
        "run_manifest_ref": refs["run_manifest_ref"],
        "run_manifest_digest": manifest["run_manifest_digest"],
        "artifacts_root_override_abs_or_null": override_abs,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="stage_id", required=True)
    for stage_id in STAGE_ID_ORDERED:
        sp = sub.add_parser(stage_id)
        sp.add_argument("--runspec", type=Path, default=None)
        sp.add_argument("--scenario", default=None)
        sp.add_argument("--profile", default=None)
        sp.add_argument("--policy", default=None)
        sp.add_argument("--opponents", default=None)
        sp.add_argument("--paths-config", type=Path, default=None)
        sp.add_argument("--postflop-solver-src-root", default="/Users/peng/Workspace/gemini/postflop-solver")
        sp.add_argument("--seed", type=int, default=123)
        sp.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
        if stage_id == "solve-postflop":
            sp.add_argument("--postflop-config", type=Path, default=None)

    args = p.parse_args(argv)

    try:
        # 3.21: --runspec is mutually exclusive with --scenario/--profile/--policy/--opponents.
        if args.runspec is not None and any(getattr(args, k) is not None for k in ("scenario", "profile", "policy", "opponents")):
            raise PipelineError("ARGUMENT_ERROR", "--runspec is mutually exclusive with --scenario/--profile/--policy/--opponents")
        if args.stage_id in ("import-preflop", "train"):
            raise PipelineError("NOT_IMPLEMENTED", "stage not implemented in this phase", {"stage_id": args.stage_id})

        if args.runspec is None and args.scenario is None:
            raise PipelineError("ARGUMENT_ERROR", "--scenario is required when --runspec is not provided")

        if args.stage_id == "init":
            out = pipeline_init(
                scenario_ref=args.scenario,
                profile_ref=args.profile,
                policy_ref=args.policy,
                opponents_ref=args.opponents,
                runspec_path=args.runspec,
                seed=args.seed,
                strict_mode=bool(args.strict),
                artifacts_root=None,
                paths_config_path=args.paths_config,
                postflop_solver_src_root=args.postflop_solver_src_root,
            )
        elif args.stage_id == "solve-postflop":
            out = pipeline_solve_postflop(
                scenario_ref=args.scenario,
                profile_ref=args.profile,
                policy_ref=args.policy,
                opponents_ref=args.opponents,
                runspec_path=args.runspec,
                postflop_config_path=args.postflop_config,
                seed=args.seed,
                strict_mode=bool(args.strict),
                artifacts_root=None,
                paths_config_path=args.paths_config,
                postflop_solver_src_root=args.postflop_solver_src_root,
            )
        elif args.stage_id == "eval":
            out = pipeline_eval(
                scenario_ref=args.scenario,
                profile_ref=args.profile,
                policy_ref=args.policy,
                opponents_ref=args.opponents,
                runspec_path=args.runspec,
                seed=args.seed,
                strict_mode=bool(args.strict),
                artifacts_root=None,
                paths_config_path=args.paths_config,
                postflop_solver_src_root=args.postflop_solver_src_root,
            )
        elif args.stage_id == "doctor":
            out = pipeline_doctor(
                scenario_ref=args.scenario,
                profile_ref=args.profile,
                policy_ref=args.policy,
                opponents_ref=args.opponents,
                runspec_path=args.runspec,
                seed=args.seed,
                strict_mode=bool(args.strict),
                artifacts_root=None,
                paths_config_path=args.paths_config,
                postflop_solver_src_root=args.postflop_solver_src_root,
            )
        elif args.stage_id == "stats":
            out = pipeline_stats(
                scenario_ref=args.scenario,
                profile_ref=args.profile,
                policy_ref=args.policy,
                opponents_ref=args.opponents,
                runspec_path=args.runspec,
                seed=args.seed,
                strict_mode=bool(args.strict),
                artifacts_root=None,
                paths_config_path=args.paths_config,
                postflop_solver_src_root=args.postflop_solver_src_root,
            )
        else:  # pragma: no cover
            raise PipelineError("NOT_IMPLEMENTED", "stage not implemented in this phase", {"stage_id": args.stage_id})

        _print(out)
        return 0 if out.get("status") == "pass" else 2
    except (
        PipelineError,
        ScenarioRegistryError,
        ScenarioPackageError,
        ProfileRegistryError,
        PolicyRegistryError,
        OpponentRegistryError,
        RuleSetError,
        OptionsHashError,
        RunManifestError,
        EventStreamError,
        GateCheckError,
        RuleConformanceError,
    ) as e:
        code = getattr(e, "code", "FAIL")
        msg = getattr(e, "message", str(e))
        details = getattr(e, "details", None)
        _print({"status": "fail", "check_id": "PipelineCLI", "error": {"code": code, "message": msg, "details": details}})
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
