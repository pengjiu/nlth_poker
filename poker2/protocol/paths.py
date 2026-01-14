from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.runtime.artifact_store import ArtifactStoreError, resolve_artifact_path


@dataclass(frozen=True)
class PathsError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


_ROOT_REQUIRED = ("scenario_root", "artifacts_root", "data_root")
_ROOT_OPTIONAL = ("postflop_solver_src_root", "hrc_root")
_ROOT_KEYS = _ROOT_REQUIRED + _ROOT_OPTIONAL


def resolved_paths_digest(resolved: Any, *, strict_mode: bool) -> str:
    if not isinstance(resolved, dict):
        raise PathsError("TYPE_ERROR", "ResolvedPaths must be a JSON object")
    obj_for_hash = {k: v for k, v in resolved.items() if k != "resolved_paths_digest"}
    return sha256_hex(canonicalize_json_bytes(obj_for_hash, strict_mode=strict_mode))


def validate_paths_config(paths_config: Any, *, strict_mode: bool) -> None:
    if not isinstance(paths_config, dict):
        raise PathsError("TYPE_ERROR", "PathsConfig must be a JSON object")
    required = ("roots", "search_order", "allow_symlink")
    missing = [k for k in required if k not in paths_config]
    if missing:
        raise PathsError("MISSING_FIELDS", "PathsConfig missing required fields", {"missing": missing})
    if strict_mode:
        extra = set(paths_config.keys()) - set(required)
        if extra:
            raise PathsError("EXTRA_FIELDS", "PathsConfig has extra fields", {"extra": sorted(extra)})

    roots = paths_config.get("roots")
    if not isinstance(roots, dict):
        raise PathsError("TYPE_ERROR", "PathsConfig.roots must be object")
    missing_roots = [k for k in _ROOT_REQUIRED if k not in roots]
    if missing_roots:
        raise PathsError("MISSING_FIELDS", "PathsConfig.roots missing required fields", {"missing": missing_roots})
    if strict_mode:
        extra_roots = set(roots.keys()) - set(_ROOT_KEYS)
        if extra_roots:
            raise PathsError("EXTRA_FIELDS", "PathsConfig.roots has extra fields", {"extra": sorted(extra_roots)})

    for k in _ROOT_KEYS:
        v = roots.get(k)
        if v is None:
            continue
        if not isinstance(v, str):
            raise PathsError("TYPE_ERROR", f"roots.{k} must be string or null")

    search_order = paths_config.get("search_order")
    if not isinstance(search_order, list) or not all(isinstance(x, str) for x in search_order):
        raise PathsError("TYPE_ERROR", "PathsConfig.search_order must be array of strings")
    if strict_mode:
        if len(search_order) != len(set(search_order)):
            raise PathsError("VALUE_ERROR", "PathsConfig.search_order must not contain duplicates")
        unknown = [x for x in search_order if x not in _ROOT_KEYS]
        if unknown:
            raise PathsError("UNSUPPORTED_VALUE", "PathsConfig.search_order contains unknown root key(s)", {"unknown": unknown})

    allow_symlink = paths_config.get("allow_symlink")
    if not isinstance(allow_symlink, bool):
        raise PathsError("TYPE_ERROR", "PathsConfig.allow_symlink must be bool")


def paths_config_id(paths_config: Any, *, strict_mode: bool) -> str:
    validate_paths_config(paths_config, strict_mode=strict_mode)
    return sha256_hex(canonicalize_json_bytes(paths_config, strict_mode=strict_mode))


def default_paths_config(*, strict_mode: bool) -> dict[str, Any]:
    # Defaults are repo-local and machine-independent; host absolute paths belong in resolution_trace.
    cfg = {
        "roots": {"scenario_root": "path:specs", "artifacts_root": "path:artifacts", "data_root": "path:data"},
        "search_order": ["scenario_root", "artifacts_root", "data_root"],
        "allow_symlink": True,
    }
    validate_paths_config(cfg, strict_mode=strict_mode)
    return cfg


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _root_value_to_abs_path(value: Any, *, root_key: str, strict_mode: bool) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PathsError("TYPE_ERROR", f"roots.{root_key} must be string or null")
    if value.startswith("path:"):
        rel = value.removeprefix("path:")
        if rel.startswith(("/", "\\")) or rel.startswith("~"):
            raise PathsError("PATH_REF_NOT_RELATIVE", f"roots.{root_key} must be relative for path:", {"root_value": value})
        return (_repo_root() / rel).resolve()
    p = Path(value)
    if strict_mode and not p.is_absolute():
        raise PathsError("ROOT_NOT_ABSOLUTE", f"roots.{root_key} must be absolute path when not using path:", {"root_value": value})
    return p.resolve()


def _root_value_to_digest_ref(value: Any, *, root_key: str) -> str | None:
    # Machine-independent: "path:" roots are stable; host absolute roots are normalized to a stable token.
    if value is None:
        return None
    if isinstance(value, str) and value.startswith("path:"):
        return value
    return f"path:{root_key}"


def _sha256_file_hex(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def resolve_paths(
    *,
    paths_config: dict[str, Any],
    scenario_package_closure: dict[str, Any],
    strict_mode: bool,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    validate_paths_config(paths_config, strict_mode=strict_mode)

    roots = paths_config["roots"]
    scenario_root_abs = _root_value_to_abs_path(roots.get("scenario_root"), root_key="scenario_root", strict_mode=strict_mode)
    artifacts_root_abs = _root_value_to_abs_path(roots.get("artifacts_root"), root_key="artifacts_root", strict_mode=strict_mode)
    data_root_abs = _root_value_to_abs_path(roots.get("data_root"), root_key="data_root", strict_mode=strict_mode)
    postflop_solver_src_root_abs = _root_value_to_abs_path(
        roots.get("postflop_solver_src_root"), root_key="postflop_solver_src_root", strict_mode=strict_mode
    )
    hrc_root_abs = _root_value_to_abs_path(roots.get("hrc_root"), root_key="hrc_root", strict_mode=strict_mode)

    resolved_roots_for_hash: dict[str, Any] = {}
    if "scenario_root" in roots:
        resolved_roots_for_hash["scenario_root_abs"] = _root_value_to_digest_ref(roots.get("scenario_root"), root_key="scenario_root")
    if "artifacts_root" in roots:
        resolved_roots_for_hash["artifacts_root_abs"] = _root_value_to_digest_ref(roots.get("artifacts_root"), root_key="artifacts_root")
    if "data_root" in roots:
        resolved_roots_for_hash["data_root_abs"] = _root_value_to_digest_ref(roots.get("data_root"), root_key="data_root")
    if "postflop_solver_src_root" in roots:
        resolved_roots_for_hash["postflop_solver_src_root_abs"] = _root_value_to_digest_ref(
            roots.get("postflop_solver_src_root"), root_key="postflop_solver_src_root"
        )
    if "hrc_root" in roots:
        resolved_roots_for_hash["hrc_root_abs"] = _root_value_to_digest_ref(roots.get("hrc_root"), root_key="hrc_root")

    # Collect artifact refs from ScenarioSpecClosure (3.6.2).
    asset_refs: list[dict[str, Any]] = []
    for key in ("preflop_ref", "postflop_ref"):
        v = scenario_package_closure.get(key)
        if v is None:
            continue
        if not isinstance(v, dict):
            raise PathsError("TYPE_ERROR", f"ScenarioSpecClosure.{key} must be object or null")
        asset_refs.append(v)

    resolved_artifacts_for_hash: list[dict[str, Any]] = []
    resolved_artifacts_trace: list[dict[str, Any]] = []

    for asset in asset_refs:
        ref = asset.get("artifact_ref")
        digest = asset.get("digest")
        if not isinstance(ref, str):
            raise PathsError("TYPE_ERROR", "artifact_ref must be string")
        try:
            validate_digest_object(digest, strict_mode=True)
        except Exception as e:
            raise PathsError("DIGEST_INVALID", "asset digest invalid", {"artifact_ref": ref, "error": str(e)}) from e

        abs_path: Path | None = None
        resolved_ok = False
        error: str | None = None

        if ref.startswith("artifact://"):
            try:
                abs_path = resolve_artifact_path(ref)
            except ArtifactStoreError as e:
                error = f"{e.code}:{e.message}"
            else:
                resolved_ok = True
                # Content-addressed refs are already machine-independent.
                resolved_artifacts_for_hash.append({"artifact_ref": ref, "abs_path": ref})

        elif ref.startswith("path:"):
            rel = ref.removeprefix("path:")
            candidates: list[tuple[str, Path]] = []
            base_roots = {
                "scenario_root": scenario_root_abs,
                "artifacts_root": artifacts_root_abs,
                "data_root": data_root_abs,
                "postflop_solver_src_root": postflop_solver_src_root_abs,
                "hrc_root": hrc_root_abs,
            }
            for root_key in paths_config["search_order"]:
                base = base_roots[root_key]
                if base is None:
                    continue
                candidates.append((root_key, base / rel))

            existing = [(rk, p) for (rk, p) in candidates if p.exists()]
            if strict_mode and len(existing) > 1:
                raise PathsError(
                    "AMBIGUOUS_REF",
                    "artifact_ref resolves to multiple existing paths under search_order",
                    {"artifact_ref": ref, "candidates": [{"root_key": rk, "abs_path": str(p)} for rk, p in existing]},
                )
            if not existing:
                error = "not_found"
            else:
                root_key, abs_path = existing[0]
                resolved_ok = True
                # Machine-independent "abs_path" token for hashing (do not leak host abs path).
                resolved_artifacts_for_hash.append({"artifact_ref": ref, "abs_path": f"path:{root_key}/{rel}"})
        else:
            error = "unsupported_ref_scheme"

        computed_digest: dict[str, str] | None = None
        if abs_path is not None and resolved_ok:
            try:
                computed_hex = _sha256_file_hex(abs_path)
                computed_digest = {"alg": "sha256", "hex": computed_hex}
                if computed_hex != digest.get("hex"):
                    resolved_ok = False
                    error = "digest_mismatch"
            except Exception as e:  # pragma: no cover - rare IO errors
                resolved_ok = False
                error = f"digest_error:{e}"

        resolved_artifacts_trace.append(
            {
                "artifact_ref": ref,
                "digest": digest,
                "computed_digest_or_null": computed_digest,
                "resolved_ok": resolved_ok,
                "abs_path_or_null": str(abs_path) if abs_path is not None else None,
                "error_or_null": error,
            }
        )

        if strict_mode and not resolved_ok:
            raise PathsError("RESOLUTION_FAILED", "artifact_ref resolution failed in strict_mode", {"artifact_ref": ref, "error": error})

    resolved = {"resolved_roots": resolved_roots_for_hash, "resolved_artifacts": resolved_artifacts_for_hash}
    digest_hex = resolved_paths_digest(resolved, strict_mode=strict_mode)
    resolved_with_digest = {**resolved, "resolved_paths_digest": digest_hex}

    trace = {
        "resolved_roots_abs": {
            "scenario_root_abs_or_null": str(scenario_root_abs) if scenario_root_abs is not None else None,
            "artifacts_root_abs_or_null": str(artifacts_root_abs) if artifacts_root_abs is not None else None,
            "data_root_abs_or_null": str(data_root_abs) if data_root_abs is not None else None,
            **(
                {
                    "postflop_solver_src_root_abs_or_null": str(postflop_solver_src_root_abs)
                    if postflop_solver_src_root_abs is not None
                    else None
                }
                if "postflop_solver_src_root" in roots
                else {}
            ),
            **(
                {"hrc_root_abs_or_null": str(hrc_root_abs) if hrc_root_abs is not None else None}
                if "hrc_root" in roots
                else {}
            ),
        },
        "resolved_artifacts": resolved_artifacts_trace,
    }

    return resolved_with_digest, digest_hex, trace


def default_resolved_paths(*, strict_mode: bool) -> tuple[dict[str, Any], str]:
    # Compatibility helper: stable default roots, no scenario-bound artifacts.
    paths_config = default_paths_config(strict_mode=strict_mode)
    resolved, digest, _trace = resolve_paths(
        paths_config=paths_config,
        scenario_package_closure={"preflop_ref": None, "postflop_ref": None},
        strict_mode=strict_mode,
    )
    return resolved, digest
