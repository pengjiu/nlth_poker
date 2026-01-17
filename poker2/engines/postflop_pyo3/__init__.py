from __future__ import annotations

import json
import pathlib
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object
from poker2.engines.postflop_solver import _sha256_file_hex


BindingKind = Literal["pyo3", "cli"]


@dataclass(frozen=True)
class PostflopRuntimeError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3]


def _solver_project_root() -> pathlib.Path:
    # Default to in-repo lightweight pyo3 binding crate
    return _repo_root() / "poker2" / "engines" / "postflop_pyo3" / "rs"


def _build_dir(build_id: str) -> pathlib.Path:
    return _repo_root() / "artifacts" / "tools" / "postflop_pyo3" / build_id


def _cargo_env() -> dict[str, str]:
    env = os.environ.copy()
    env["CARGO_HOME"] = str(_repo_root() / ".cargo")
    env.pop("CONDA_PREFIX", None)
    return env


def compute_pyo3_build_id(src_root: pathlib.Path, *, strict_mode: bool) -> str:
    src_root = src_root.resolve()
    cargo_toml = src_root / "Cargo.toml"
    if not cargo_toml.exists():
        raise PostflopRuntimeError("SOLVER_ROOT_INVALID", "missing Cargo.toml", {"path": str(src_root)})
    digest = _sha256_file_hex(cargo_toml)
    payload = {"solver_build_schema_id": "postflop_solver_build_pyo3_v1", "cargo_toml_sha256": digest}
    return sha256_hex(canonicalize_json_bytes(payload, strict_mode=strict_mode))


@lru_cache(maxsize=1)
def _ensure_pyo3_module(build_id: str, src_root: pathlib.Path) -> Any:
    build_dir = _build_dir(build_id)
    build_dir.mkdir(parents=True, exist_ok=True)
    env = _cargo_env()
    target_py = build_dir / "py"
    if target_py.exists():
        if str(target_py) not in sys.path:
            sys.path.insert(0, str(target_py))
        try:
            import postflop_solver  # type: ignore
            return postflop_solver
        except Exception:
            pass
    wheels_dir = build_dir / "target" / "wheels"
    cmd_build = [
        "maturin",
        "build",
        "--release",
        "--manifest-path",
        str(src_root / "Cargo.toml"),
        "--target-dir",
        str(build_dir / "target"),
        "--interpreter",
        sys.executable,
    ]
    try:
        proc = subprocess.run(cmd_build, cwd=str(src_root), check=False, capture_output=True, text=True, env=env)
    except FileNotFoundError:
        cmd_build = [
            sys.executable,
            "-m",
            "maturin",
            "build",
            "--release",
            "--manifest-path",
            str(src_root / "Cargo.toml"),
            "--target-dir",
            str(build_dir / "target"),
            "--interpreter",
            sys.executable,
        ]
        proc = subprocess.run(cmd_build, cwd=str(src_root), check=False, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise PostflopRuntimeError("BUILD_FAILED", "maturin build failed", {"stdout": proc.stdout, "stderr": proc.stderr})

    wheel_files = list(wheels_dir.glob("postflop_solver-*.whl"))
    # maturin may emit wheels under source target/wheels; include as fallback
    fallback_wheels_dir = src_root / "target" / "wheels"
    if not wheel_files and fallback_wheels_dir.exists():
        wheel_files = list(fallback_wheels_dir.glob("postflop_solver-*.whl"))
    if not wheel_files:
        raise PostflopRuntimeError("WHEEL_MISSING", "wheel not produced", {"wheels_dir": str(wheels_dir), "stdout": proc.stdout, "stderr": proc.stderr})
    wheel_path = max(wheel_files, key=lambda p: p.stat().st_mtime)

    target_py.mkdir(parents=True, exist_ok=True)
    cmd_pip = [
        sys.executable,
        "-m",
        "pip",
        "--disable-pip-version-check",
        "install",
        "--no-deps",
        "--force-reinstall",
        "--target",
        str(target_py),
        str(wheel_path),
    ]
    proc_pip = subprocess.run(cmd_pip, check=False, capture_output=True, text=True, env=env)
    if proc_pip.returncode != 0:
        if str(target_py) not in sys.path:
            sys.path.insert(0, str(target_py))
        try:
            import postflop_solver  # type: ignore
            return postflop_solver
        except Exception:
            raise PostflopRuntimeError(
                "PIP_INSTALL_FAILED",
                "pip install of solver wheel failed",
                {"stdout": proc_pip.stdout, "stderr": proc_pip.stderr},
            )
    if str(target_py) not in sys.path:
        sys.path.insert(0, str(target_py))
    try:
        import postflop_solver  # type: ignore
    except Exception as e:  # pragma: no cover
        raise PostflopRuntimeError("IMPORT_FAILED", "cannot import built pyo3 module", {"error": str(e)})
    return postflop_solver


def _canonical_state_key(payload: dict[str, Any], *, strict_mode: bool) -> str:
    return sha256_hex(canonicalize_json_bytes(payload, strict_mode=strict_mode))


_cache_lock = threading.Lock()
_solve_cache: dict[str, dict[str, Any]] = {}


def solve_postflop_pyo3(
    *,
    src_root: pathlib.Path,
    solve_payload: dict[str, Any],
    solver_build_id: str,
    strict_mode: bool,
    timeout_seconds: float = 0.15,
) -> dict[str, Any]:
    key = _canonical_state_key({"solver_build_id": solver_build_id, "payload": solve_payload}, strict_mode=strict_mode)
    with _cache_lock:
        if key in _solve_cache:
            return _solve_cache[key]

    mod = _ensure_pyo3_module(solver_build_id, src_root)
    # Guard against hangs
    result_container: dict[str, Any] = {}
    exc_container: list[Exception] = []

    def _worker() -> None:
        try:
            result_container["out"] = mod.solve_json(json.dumps(solve_payload))
        except Exception as e:  # pragma: no cover
            exc_container.append(e)

    t = threading.Thread(target=_worker)
    t.daemon = True
    t.start()
    t.join(timeout_seconds)
    if t.is_alive():
        raise PostflopRuntimeError("TIMEOUT", "postflop solver timed out", {"timeout_seconds": timeout_seconds})
    if exc_container:
        raise PostflopRuntimeError("SOLVE_FAILED", "pyo3 solver raised", {"error": str(exc_container[0])})

    try:
        raw = result_container["out"]
        obj = json.loads(raw)
    except Exception as e:
        raise PostflopRuntimeError("PARSE_FAILED", "solver output not valid JSON", {"error": str(e)})

    validate_digest_object({"alg": "sha256", "hex": solver_build_id}, strict_mode=True)
    with _cache_lock:
        _solve_cache[key] = obj
    return obj
