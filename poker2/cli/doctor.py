from __future__ import annotations

# CLI entrypoints (ARCHIETECTURE.md §8, Informative).

import argparse
import json
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.contractkit import ROUNDING_MODE_VALUES
from poker2.contractkit.run_vectors import main as contractkit_vectors_main
from poker2.evaluation.fixtures.pack import FixturesPackError, validate_pack
from poker2.gates import GateCheckError, check_eventstream_gates
from poker2.gates.common import failure
from poker2.gates.scenario_package_gate import check_scenario_package_gate
from poker2.protocol.eventstream import EventStreamError, event_stream_digest_from_file, read_ndjson
from poker2.protocol.abstraction import abstraction_hash
from poker2.protocol.options_hash import OptionsHashError, compute_options_hash
from poker2.protocol.paths import PathsError, default_paths_config, default_resolved_paths, paths_config_id, validate_paths_config
from poker2.protocol.placeholders import placeholder_id
from poker2.protocol.action_bins import ActionBinsError, default_internal_action_bins
from poker2.protocol.action_adapter import ActionAdapterError, default_internal_action_adapter
from poker2.protocol.policy import PolicyError, default_internal_policy_spec
from poker2.protocol.ruleset import RuleSetError, ruleset_id, ruleset_rake_id, validate_ruleset
from poker2.protocol.schema_contract import SchemaContractError, schema_hash
from poker2.protocol.scenario import ScenarioError, scenario_id
from poker2.protocol.triad import TriadError, triad
from poker2.protocol.profile import ProfileError, auto_profile_spec_throughput, default_internal_profile_spec, profile_id
from poker2.cli.hrc_import_ruleset import ImportError, import_ruleset_from_hrc_settings
from poker2.protocol.scenario_package import ScenarioPackageError, load_scenario_package, validate_scenario_package
from poker2.protocol.provenance import ProvenanceError, validate_provenance_envelope
from poker2.runtime.artifact_store import resolve_artifact_path
from poker2.runtime.scenario_registry import ScenarioRegistryError, build_scenario_registry, resolve_scenario_ref


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def _cmd_contractkit_vectors() -> int:
    return contractkit_vectors_main()


def _cmd_ruleset(path: Path, *, strict: bool) -> int:
    try:
        ruleset = json.loads(path.read_text(encoding="utf-8"))
        validate_ruleset(ruleset, strict_mode=strict)
        _print(
            {
                "status": "pass",
                "ruleset_id": ruleset_id(ruleset, strict_mode=strict),
                "ruleset_rake_id": ruleset_rake_id(ruleset, strict_mode=strict),
            }
        )
        return 0
    except RuleSetError as e:
        _print({"status": "fail", "check_id": "Protocol.RuleSet", "error": {"code": e.code, "message": e.message}})
        return 2


def _cmd_hrc_ruleset(
    settings_path: Path, *, strict: bool, rounding_mode: str | None, reopen_on_short_allin: bool | None
) -> int:
    try:
        out = import_ruleset_from_hrc_settings(
            settings_path,
            rounding_mode=rounding_mode,
            reopen_on_short_allin=reopen_on_short_allin,
        )
        ruleset = out["ruleset"]
        validate_ruleset(ruleset, strict_mode=strict)
        _print({"status": "pass", **out})
        return 0
    except ImportError as e:
        _print({"status": "fail", "check_id": "Tools.HRCImport", "error": e.to_json()})
        return 2
    except RuleSetError as e:
        _print({"status": "fail", "check_id": "Protocol.RuleSet", "error": {"code": e.code, "message": e.message}})
        return 2


def _cmd_profile_auto(*, strict: bool) -> int:
    try:
        spec = auto_profile_spec_throughput()
        pid = profile_id(spec, strict_mode=strict)
        _print({"status": "pass", "profile_spec": spec, "profile_id": pid})
        return 0
    except ProfileError as e:
        _print({"status": "fail", "check_id": "Protocol.ProfileSpec", "error": {"code": e.code, "message": e.message}})
        return 2


def _canonical_file_digest_sha256(path: Path) -> dict[str, str]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    digest_hex = sha256_hex(canonicalize_json_bytes(obj, strict_mode=True))
    return {"alg": "sha256", "hex": digest_hex}


def _cmd_fixtures_pack_digest(path: Path) -> int:
    try:
        digest = _canonical_file_digest_sha256(path)
        validate_digest_object(digest, strict_mode=True)
        _print({"status": "pass", "artifact_ref": f"path:{path}", "digest": digest})
        return 0
    except Exception as e:
        _print({"status": "fail", "check_id": "Fixtures.PackDigest", "error": {"code": "FAIL", "message": str(e)}})
        return 2


def _cmd_fixtures_pack_validate(path: Path, *, strict: bool) -> int:
    try:
        summary = validate_pack(path, strict_mode=strict, require_non_empty=False)
        _print({"status": "pass", **summary})
        return 0
    except FixturesPackError as e:
        _print({"status": "fail", "check_id": "GoldenFixtures.Pack", "error": {"code": e.code, "message": e.message, "details": e.details}})
        return 2


def _cmd_eventstream_digest(path: Path, *, strict: bool) -> int:
    try:
        digest_hex = event_stream_digest_from_file(path, strict_mode=strict)
        _print({"status": "pass", "artifact_ref": f"path:{path}", "digest": {"alg": "sha256", "hex": digest_hex}})
        return 0
    except EventStreamError as e:
        _print({"status": "fail", "check_id": "Events.EventStreamArtifact", "error": {"code": e.code, "message": e.message}})
        return 2


def _load_ruleset_file(path: Path, *, strict_mode: bool) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    validate_ruleset(obj, strict_mode=strict_mode)
    return obj


def _cmd_eventstream_gates(
    eventstream_path: Path,
    *,
    ruleset_path: Path,
    scenario_ref: str | None,
    paths_config_path: Path | None,
    strict: bool,
) -> int:
    try:
        ruleset = _load_ruleset_file(ruleset_path, strict_mode=strict)

        objs = read_ndjson(eventstream_path, strict_mode=strict)
        if strict and len(objs) < 2:
            raise EventStreamError("EMPTY_EVENTSTREAM", "EventStream must contain header + events")
        if not objs or not isinstance(objs[0], dict):
            raise EventStreamError("HEADER_NOT_OBJECT", "EventStream header must be JSON object")
        header: dict[str, Any] = objs[0]

        events: list[dict[str, Any]] = []
        for idx, e in enumerate(objs[1:], start=1):
            if not isinstance(e, dict):
                raise GateCheckError("EVENT_NOT_OBJECT", "EventStream event must be JSON object", {"index": idx})
            events.append(e)

        digest_hex = event_stream_digest_from_file(eventstream_path, strict_mode=strict)
        digest_obj = {"alg": "sha256", "hex": digest_hex}
        validate_digest_object(digest_obj, strict_mode=True)

        scenario_package = None
        paths_config = None
        if scenario_ref is not None:
            scenario_registry = build_scenario_registry(strict_mode=strict)
            scen_entry, _trace = resolve_scenario_ref(scenario_ref, registry=scenario_registry, strict_mode=bool(strict))
            pkg_ref = scen_entry.get("scenario_package_ref")
            if not (isinstance(pkg_ref, str) and pkg_ref.startswith("path:")):
                raise ScenarioRegistryError("VALUE_ERROR", "scenario registry entry has invalid scenario_package_ref", {"scenario_package_ref": pkg_ref})
            pkg_path = Path(pkg_ref.removeprefix("path:"))
            scenario_package = load_scenario_package(pkg_path)
            validate_scenario_package(scenario_package, strict_mode=strict)

            paths_config = default_paths_config(strict_mode=strict)
            if paths_config_path is not None:
                paths_config = _load_json_file(paths_config_path)
                validate_paths_config(paths_config, strict_mode=strict)

        out = check_eventstream_gates(
            header=header,
            events=events,
            event_stream_ref=f"path:{eventstream_path}",
            event_stream_digest=digest_obj,
            ruleset=ruleset,
            scenario_package=scenario_package,
            requested_scenario_ref=scenario_ref,
            paths_config=paths_config,
            strict_mode=strict,
        )
        _print(out)
        return 0 if out.get("status") == "pass" else 2
    except (RuleSetError, EventStreamError, GateCheckError, ScenarioRegistryError, ScenarioPackageError, PathsError) as e:
        code = getattr(e, "code", "FAIL")
        msg = getattr(e, "message", str(e))
        details = getattr(e, "details", None)
        _print({"status": "fail", "check_id": "Doctor.EventStreamGates", "error": {"code": code, "message": msg, "details": details}})
        return 2


def _cmd_fixtures_pack_gates(pack_path: Path, *, ruleset_path: Path, strict: bool) -> int:
    try:
        summary = validate_pack(pack_path, strict_mode=True, require_non_empty=True)
        ruleset = _load_ruleset_file(ruleset_path, strict_mode=strict)
        expected_ruleset_id = ruleset_id(ruleset, strict_mode=True)
        base_paths_config = default_paths_config(strict_mode=strict)
        scenario_registry = build_scenario_registry(strict_mode=strict)
        pack_obj = json.loads(pack_path.read_text(encoding="utf-8"))
        fixtures = pack_obj.get("fixtures")
        if not isinstance(fixtures, list):
            raise FixturesPackError("PACK_FIXTURES_NOT_ARRAY", "fixtures must be array")

        failures: list[dict[str, Any]] = []
        checked = 0
        for idx, fx in enumerate(fixtures):
            if not isinstance(fx, dict):
                failures.append(
                    {
                        "gate_id": "Doctor.FixturesPack",
                        "status": "fail",
                        "reason": "fixture_not_object",
                        "details": {"index": idx},
                        "evidence_ref": None,
                    }
                )
                continue
            ref = fx.get("event_stream_ref")
            if not (isinstance(ref, str) and ref.startswith("path:")):
                failures.append(
                    {
                        "gate_id": "Doctor.FixturesPack",
                        "status": "fail",
                        "reason": "fixture_ref_invalid",
                        "details": {"index": idx, "event_stream_ref": ref},
                        "evidence_ref": None,
                    }
                )
                continue

            es_path = Path(ref.removeprefix("path:"))
            checked += 1

            objs = read_ndjson(es_path, strict_mode=strict)
            if not objs or not isinstance(objs[0], dict):
                raise EventStreamError("HEADER_NOT_OBJECT", "EventStream header must be JSON object")
            header: dict[str, Any] = objs[0]

            events: list[dict[str, Any]] = []
            for eidx, e in enumerate(objs[1:], start=1):
                if not isinstance(e, dict):
                    raise GateCheckError(
                        "EVENT_NOT_OBJECT",
                        "EventStream event must be JSON object",
                        {"index": eidx, "event_stream_ref": ref},
                    )
                events.append(e)

            digest_hex = event_stream_digest_from_file(es_path, strict_mode=strict)
            digest_obj = {"alg": "sha256", "hex": digest_hex}
            validate_digest_object(digest_obj, strict_mode=True)

            scenario_pkg = None
            requested_ref = None
            scen_id = header.get("scenario_id")
            if isinstance(scen_id, str):
                requested_ref = f"scenario://{scen_id}"
                reg_entry = scenario_registry.get(scen_id)
                if reg_entry is None:
                    failures.append(
                        failure(
                            gate_id="Gates.Scenario",
                            reason="missing_ref",
                            header=header,
                            event_stream_ref=ref,
                            event_stream_digest=digest_obj,
                            ruleset_id_or_none=None,
                            triad_or_none=None,
                            schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                            details={"requested_scenario_ref": requested_ref, "scenario_id": scen_id},
                        )
                    )
                else:
                    pkg_ref = reg_entry.get("scenario_package_ref")
                    if not (isinstance(pkg_ref, str) and pkg_ref.startswith("path:")):
                        raise ScenarioRegistryError("VALUE_ERROR", "registry entry has invalid scenario_package_ref", {"scenario_package_ref": pkg_ref})
                    pkg_path = Path(pkg_ref.removeprefix("path:"))
                    scenario_pkg = load_scenario_package(pkg_path)
                    validate_scenario_package(scenario_pkg, strict_mode=strict)

            paths_config = base_paths_config
            if isinstance(scenario_pkg, dict) and scenario_pkg.get("postflop_ref") is not None:
                # Postflop solver is injected via PathsConfig; use a stable placeholder root so
                # resolved_paths_digest matches fixture headers without leaking host paths.
                roots = dict(paths_config["roots"])
                roots["postflop_solver_src_root"] = "path:postflop_solver_src_root"
                paths_config = {**paths_config, "roots": roots}

            result = check_eventstream_gates(
                header=header,
                events=events,
                event_stream_ref=ref,
                event_stream_digest=digest_obj,
                ruleset=ruleset,
                scenario_package=scenario_pkg,
                requested_scenario_ref=requested_ref,
                paths_config=paths_config if scenario_pkg is not None else None,
                strict_mode=strict,
            )
            if result.get("status") != "pass":
                failures.extend(result.get("failures", []))

            # Extra Scenario Gate checks for fixtures: verify abstraction_hash (not present in EventStream header).
            try:
                if scenario_pkg is None:
                    continue

                hs = next((e for e in events if e.get("event") == "HandStart"), None)
                if not isinstance(hs, dict):
                    raise GateCheckError("NO_HANDS", "eventstream contains no HandStart/HandEnd blocks")
                triad_obj = hs.get("triad")
                if not isinstance(triad_obj, dict):
                    raise GateCheckError("TYPE_ERROR", "HandStart.triad must be object")

                prov_ref = header.get("provenance_ref")
                if not isinstance(prov_ref, str):
                    raise ProvenanceError("MISSING_FIELDS", "provenance_ref missing in header")
                prov_path = resolve_artifact_path(prov_ref)
                prov_env = json.loads(prov_path.read_text(encoding="utf-8"))
                validate_provenance_envelope(prov_env, strict_mode=True)

                abs_hash = abstraction_hash(
                    action_bins_id=triad_obj.get("action_bins_id"),
                    action_adapter_id=prov_env.get("action_adapter_id"),
                    mapping_spec_id=prov_env.get("mapping_spec_id"),
                    strict_mode=True,
                )

                expected_ctx = {
                    "ruleset_id": expected_ruleset_id,
                    "triad": triad_obj,
                    "schema_hash": header.get("schema_hash"),
                    "abstraction_hash": abs_hash,
                    "resolved_paths_digest": header.get("resolved_paths_digest"),
                }

                scen_failures, out_scen = check_scenario_package_gate(
                    requested_scenario_ref=requested_ref or "scenario://unknown",
                    header=header,
                    scenario_package=scenario_pkg,
                    expected_context=expected_ctx,
                    paths_config=paths_config,
                    event_stream_ref=ref,
                    event_stream_digest=digest_obj,
                    strict_mode=strict,
                )
                failures.extend(scen_failures)
                if out_scen and out_scen.get("scenario_id") != scen_id:
                    failures.append(
                        failure(
                            gate_id="Gates.Scenario",
                            reason="scenario_id_mismatch",
                            header=header,
                            event_stream_ref=ref,
                            event_stream_digest=digest_obj,
                            ruleset_id_or_none=expected_ruleset_id,
                            triad_or_none=triad_obj,
                            schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                            details={"expected": scen_id, "observed": out_scen.get("scenario_id")},
                        )
                    )
            except (ScenarioRegistryError, ScenarioPackageError, PathsError, ProvenanceError, GateCheckError) as e:
                code = getattr(e, "code", "FAIL")
                msg = getattr(e, "message", str(e))
                details = getattr(e, "details", None)
                failures.append(
                    failure(
                        gate_id="Gates.Scenario",
                        reason="other",
                        header=header,
                        event_stream_ref=ref,
                        event_stream_digest=digest_obj,
                        ruleset_id_or_none=expected_ruleset_id,
                        triad_or_none=None,
                        schema_hash_or_none=header.get("schema_hash") if isinstance(header.get("schema_hash"), str) else None,
                        details={"error": {"code": code, "message": msg, "details": details}},
                    )
                )

        out = {
            "status": "pass" if not failures else "fail",
            "pack_ref": summary["pack_ref"],
            "pack_digest": summary["pack_digest"],
            "fixtures_checked": checked,
            "failures_count": len(failures),
            "failures": failures,
        }
        _print(out)
        return 0 if out["status"] == "pass" else 2
    except (FixturesPackError, RuleSetError, EventStreamError, GateCheckError) as e:
        code = getattr(e, "code", "FAIL")
        msg = getattr(e, "message", str(e))
        details = getattr(e, "details", None)
        _print({"status": "fail", "check_id": "Doctor.FixturesPackGates", "error": {"code": code, "message": msg, "details": details}})
        return 2


def _cmd_options_hash_from_hrc(
    settings_path: Path,
    *,
    run_strict_mode: bool,
    rounding_mode: str | None,
    reopen_on_short_allin: bool | None,
) -> int:
    try:
        ruleset_out = import_ruleset_from_hrc_settings(
            settings_path,
            rounding_mode=rounding_mode,
            reopen_on_short_allin=reopen_on_short_allin,
        )
        r_id = ruleset_out["ruleset_id"]
        r_rake_id = ruleset_out["ruleset_rake_id"]

        _, action_bins_id = default_internal_action_bins(strict_mode=True)
        obs_schema_id = placeholder_id("obs_schema_placeholder_v1", strict_mode=True)
        t = triad(action_bins_id=action_bins_id, obs_schema_id=obs_schema_id, rake_id=r_rake_id)

        s_hash = schema_hash(strict_mode=True)

        _, action_adapter_id = default_internal_action_adapter(strict_mode=True)
        mapping_spec_id = None
        abs_hash = abstraction_hash(
            action_bins_id=action_bins_id,
            action_adapter_id=action_adapter_id,
            mapping_spec_id=mapping_spec_id,
            strict_mode=True,
        )

        scen_closure = {
            "scenario_schema_id": "scenario_spec_v1",
            "ruleset_id": r_id,
            "triad": t,
            "schema_hash": s_hash,
            "abstraction_hash": abs_hash,
            "preflop_ref": None,
            "postflop_ref": None,
            "opponent_suite_id": None,
            "population_id": None,
            "mw_ladder_id": None,
        }
        scen_id = scenario_id(scen_closure, strict_mode=True)

        _, resolved_paths_digest = default_resolved_paths(strict_mode=True)

        prof_spec, prof_id = default_internal_profile_spec(strict_mode=True)
        pol_spec, pol_id = default_internal_policy_spec(strict_mode=True)

        run_closure = {
            "scenario_id": scen_id,
            "ruleset_id": r_id,
            "triad": t,
            "schema_hash": s_hash,
            "resolved_paths_digest": resolved_paths_digest,
            "abstraction_hash": abs_hash,
            "policy_id": pol_id,
            "profile_id": prof_id,
            "opponent_suite_id": None,
            "opponent_artifact_id_or_params_hash": None,
            "mw_ladder_id": None,
            "belief_spec_id": None,
            "mw_risk_spec_id": None,
            "adaptation_digest": None,
            "engine_build_id": None,
            "solver_build_id": None,
            "pokerkit_version": None,
            "strict_mode": run_strict_mode,
        }
        o_hash = compute_options_hash(run_closure, strict_mode=True)

        _print(
            {
                "status": "pass",
                "ruleset_id": r_id,
                "ruleset_rake_id": r_rake_id,
                "triad": t,
                "schema_hash": s_hash,
                "abstraction_hash": abs_hash,
                "scenario_id": scen_id,
                "resolved_paths_digest": resolved_paths_digest,
                "profile_id": prof_id,
                "policy_id": pol_id,
                "options_hash": o_hash,
            }
        )
        return 0
    except (
        ImportError,
        RuleSetError,
        TriadError,
        SchemaContractError,
        ScenarioError,
        PolicyError,
        ProfileError,
        OptionsHashError,
        ActionBinsError,
        ActionAdapterError,
    ) as e:
        code = getattr(e, "code", "FAIL")
        msg = getattr(e, "message", str(e))
        _print({"status": "fail", "check_id": "Protocol.RunSpec", "error": {"code": code, "message": msg}})
        return 2


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _cmd_scenario_gate(
    scenario_path: Path,
    *,
    ruleset_path: Path,
    paths_config_path: Path | None,
    strict: bool,
) -> int:
    try:
        scenario_pkg = load_scenario_package(scenario_path)
        pkg_ids = validate_scenario_package(scenario_pkg, strict_mode=strict)

        ruleset = _load_ruleset_file(ruleset_path, strict_mode=strict)
        expected_ruleset_id = ruleset_id(ruleset, strict_mode=True)
        expected_rake_id = ruleset_rake_id(ruleset, strict_mode=True)

        _, action_bins_id = default_internal_action_bins(strict_mode=True)
        obs_schema_id = placeholder_id("obs_schema_placeholder_v1", strict_mode=True)
        expected_triad = triad(action_bins_id=action_bins_id, obs_schema_id=obs_schema_id, rake_id=expected_rake_id)

        expected_schema_hash = schema_hash(strict_mode=True)

        _, action_adapter_id = default_internal_action_adapter(strict_mode=True)
        expected_abs_hash = abstraction_hash(
            action_bins_id=action_bins_id,
            action_adapter_id=action_adapter_id,
            mapping_spec_id=None,
            strict_mode=True,
        )

        paths_config = default_paths_config(strict_mode=strict)
        if paths_config_path is not None:
            paths_config = _load_json_file(paths_config_path)
            validate_paths_config(paths_config, strict_mode=strict)

        # Run-level gate uses a synthetic header (no run_id/options_hash yet).
        header = {
            "run_id": None,
            "options_hash": None,
            "seed": None,
            "scenario_id": pkg_ids["scenario_id"],
            "schema_hash": scenario_pkg.get("schema_hash"),
        }

        failures, out = check_scenario_package_gate(
            requested_scenario_ref=str(scenario_path),
            header=header,
            scenario_package=scenario_pkg,
            expected_context={
                "ruleset_id": expected_ruleset_id,
                "triad": expected_triad,
                "schema_hash": expected_schema_hash,
                "abstraction_hash": expected_abs_hash,
            },
            paths_config=paths_config,
            event_stream_ref=None,
            event_stream_digest=None,
            strict_mode=strict,
        )

        if failures:
            _print({"status": "fail", "failures_count": len(failures), "failures": failures})
            return 2

        _print(
            {
                "status": "pass",
                "requested_scenario_ref": str(scenario_path),
                "scenario_id": out["scenario_id"],
                "scenario_family_key": out["scenario_family_key"],
                "paths_config_id": paths_config_id(paths_config, strict_mode=strict),
                "resolved_paths_digest": out["resolved_paths_digest"],
            }
        )
        return 0
    except (ScenarioPackageError, RuleSetError, TriadError, SchemaContractError, PathsError, ActionBinsError, ActionAdapterError) as e:
        code = getattr(e, "code", "FAIL")
        msg = getattr(e, "message", str(e))
        details = getattr(e, "details", None)
        _print({"status": "fail", "check_id": "Gates.Scenario", "error": {"code": code, "message": msg, "details": details}})
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("contractkit-vectors")
    p_profile_auto = sub.add_parser("profile-auto")
    p_profile_auto.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)

    p_ruleset = sub.add_parser("ruleset")
    p_ruleset.add_argument("--path", type=Path, required=True)
    p_ruleset.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)

    p_hrc = sub.add_parser("hrc-ruleset")
    p_hrc.add_argument("--settings", type=Path, required=True)
    p_hrc.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    p_hrc.add_argument("--rounding-mode", choices=ROUNDING_MODE_VALUES, default=None)
    p_hrc.add_argument(
        "--reopen-on-short-allin",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Required; no defaults allowed (use --reopen-on-short-allin or --no-reopen-on-short-allin).",
    )

    p_pack = sub.add_parser("fixtures-pack-digest")
    p_pack.add_argument("--path", type=Path, required=True)

    p_pack_val = sub.add_parser("fixtures-pack-validate")
    p_pack_val.add_argument("--path", type=Path, required=True)
    p_pack_val.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)

    p_es = sub.add_parser("eventstream-digest")
    p_es.add_argument("--path", type=Path, required=True)
    p_es.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)

    p_es_gates = sub.add_parser("eventstream-gates")
    p_es_gates.add_argument("--eventstream", type=Path, required=True)
    p_es_gates.add_argument("--ruleset", type=Path, required=True)
    p_es_gates.add_argument("--scenario", type=str, default=None)
    p_es_gates.add_argument("--paths-config", type=Path, default=None)
    p_es_gates.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)

    p_pack_gates = sub.add_parser("fixtures-pack-gates")
    p_pack_gates.add_argument("--pack", type=Path, required=True)
    p_pack_gates.add_argument("--ruleset", type=Path, required=True)
    p_pack_gates.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)

    p_scenario_gate = sub.add_parser("scenario-gate")
    p_scenario_gate.add_argument("--scenario", type=Path, required=True)
    p_scenario_gate.add_argument("--ruleset", type=Path, required=True)
    p_scenario_gate.add_argument("--paths-config", type=Path, default=None)
    p_scenario_gate.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)

    p_opt = sub.add_parser("options-hash-from-hrc")
    p_opt.add_argument("--settings", type=Path, required=True)
    p_opt.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True, help="RunSpec strict_mode")
    p_opt.add_argument("--rounding-mode", choices=ROUNDING_MODE_VALUES, default=None)
    p_opt.add_argument(
        "--reopen-on-short-allin",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Required; no defaults allowed (use --reopen-on-short-allin or --no-reopen-on-short-allin).",
    )

    args = parser.parse_args(argv)
    if args.cmd == "contractkit-vectors":
        return _cmd_contractkit_vectors()
    if args.cmd == "profile-auto":
        return _cmd_profile_auto(strict=args.strict)
    if args.cmd == "ruleset":
        return _cmd_ruleset(args.path, strict=args.strict)
    if args.cmd == "hrc-ruleset":
        return _cmd_hrc_ruleset(
            args.settings,
            strict=args.strict,
            rounding_mode=args.rounding_mode,
            reopen_on_short_allin=args.reopen_on_short_allin,
        )
    if args.cmd == "fixtures-pack-digest":
        return _cmd_fixtures_pack_digest(args.path)
    if args.cmd == "fixtures-pack-validate":
        return _cmd_fixtures_pack_validate(args.path, strict=args.strict)
    if args.cmd == "eventstream-digest":
        return _cmd_eventstream_digest(args.path, strict=args.strict)
    if args.cmd == "eventstream-gates":
        return _cmd_eventstream_gates(
            args.eventstream,
            ruleset_path=args.ruleset,
            scenario_ref=args.scenario,
            paths_config_path=args.paths_config,
            strict=args.strict,
        )
    if args.cmd == "fixtures-pack-gates":
        return _cmd_fixtures_pack_gates(args.pack, ruleset_path=args.ruleset, strict=args.strict)
    if args.cmd == "scenario-gate":
        return _cmd_scenario_gate(args.scenario, ruleset_path=args.ruleset, paths_config_path=args.paths_config, strict=args.strict)
    if args.cmd == "options-hash-from-hrc":
        return _cmd_options_hash_from_hrc(
            args.settings,
            run_strict_mode=args.strict,
            rounding_mode=args.rounding_mode,
            reopen_on_short_allin=args.reopen_on_short_allin,
        )
    raise SystemExit(2)  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover
