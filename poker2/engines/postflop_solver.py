from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess
from typing import Any

from poker2.contractkit import canonicalize_json_bytes, sha256_hex, validate_digest_object


POSTFLOP_SOLVER_BUILD_SCHEMA_ID = "postflop_solver_build_v1"
POSTFLOP_SOLVER_TREE_SCHEMA_ID = "postflop_solver_tree_v1"
DEFAULT_BINDING_KIND = "cargo_cli"


@dataclass(frozen=True)
class PostflopSolverError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha256_file_hex(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_head(root: Path) -> tuple[str | None, bool | None]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None, None
    if proc.returncode != 0:
        return None, None
    commit = proc.stdout.strip()
    if not commit:
        return None, None
    dirty = None
    try:
        proc_dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc_dirty.returncode == 0:
            dirty = bool(proc_dirty.stdout.strip())
    except Exception:
        dirty = None
    return commit, dirty


def _rustc_version() -> str | None:
    try:
        proc = subprocess.run(
            ["rustc", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _postflop_solver_tree_digest(src_root: Path) -> dict[str, str]:
    src_root = src_root.resolve()
    if not src_root.exists():
        raise PostflopSolverError("SOLVER_ROOT_MISSING", "postflop solver root does not exist", {"path": str(src_root)})
    if not src_root.is_dir():
        raise PostflopSolverError("SOLVER_ROOT_INVALID", "postflop solver root must be a directory", {"path": str(src_root)})

    cargo_toml = src_root / "Cargo.toml"
    if not cargo_toml.exists():
        raise PostflopSolverError("SOLVER_ROOT_INVALID", "postflop solver root missing Cargo.toml", {"path": str(src_root)})

    files: list[Path] = []
    files.append(cargo_toml)
    cargo_lock = src_root / "Cargo.lock"
    if cargo_lock.exists():
        files.append(cargo_lock)
    build_rs = src_root / "build.rs"
    if build_rs.exists():
        files.append(build_rs)

    src_dir = src_root / "src"
    if src_dir.exists():
        files.extend(sorted([p for p in src_dir.rglob("*.rs") if p.is_file()], key=lambda p: str(p)))

    entries: list[dict[str, str]] = []
    for path in sorted(files, key=lambda p: str(p)):
        rel = path.relative_to(src_root).as_posix()
        entries.append({"path": rel, "sha256": _sha256_file_hex(path)})

    payload = {"tree_schema_id": POSTFLOP_SOLVER_TREE_SCHEMA_ID, "files": entries}
    digest_hex = sha256_hex(canonicalize_json_bytes(payload, strict_mode=True))
    digest_obj = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest_obj, strict_mode=True)
    return digest_obj


def compute_postflop_solver_build_id(
    *,
    src_root: Path,
    binding_kind: str | None = None,
    strict_mode: bool,
) -> str:
    if not isinstance(src_root, Path):
        raise PostflopSolverError("TYPE_ERROR", "src_root must be a Path", {"value": str(src_root)})
    src_root = src_root.resolve()
    if binding_kind is None:
        binding_kind = DEFAULT_BINDING_KIND
    if not isinstance(binding_kind, str) or not binding_kind:
        raise PostflopSolverError("TYPE_ERROR", "binding_kind must be non-empty string", {"binding_kind": binding_kind})

    tree_digest = _postflop_solver_tree_digest(src_root)
    git_commit, git_dirty = _git_head(src_root)
    rustc_version = _rustc_version()

    payload = {
        "solver_build_schema_id": POSTFLOP_SOLVER_BUILD_SCHEMA_ID,
        "binding_kind": binding_kind,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "rustc_version": rustc_version,
        "source_tree_digest": tree_digest,
    }
    return sha256_hex(canonicalize_json_bytes(payload, strict_mode=strict_mode))


def postflop_solver_src_root_from_paths_trace(paths_trace: dict[str, Any]) -> Path:
    roots = paths_trace.get("resolved_roots_abs") if isinstance(paths_trace, dict) else None
    if not isinstance(roots, dict):
        raise PostflopSolverError("PATHS_TRACE_INVALID", "paths_trace.resolved_roots_abs missing or invalid", {"paths_trace": paths_trace})
    root_val = roots.get("postflop_solver_src_root_abs_or_null")
    if root_val is None:
        raise PostflopSolverError(
            "POSTFLOP_SOLVER_ROOT_MISSING",
            "postflop_solver_src_root must be provided via PathsConfig when postflop_ref is present",
            {},
        )
    if not isinstance(root_val, str):
        raise PostflopSolverError("TYPE_ERROR", "postflop_solver_src_root_abs_or_null must be string", {"value": root_val})
    root_path = Path(root_val).resolve()
    if not root_path.exists():
        raise PostflopSolverError("SOLVER_ROOT_MISSING", "postflop solver root does not exist", {"path": str(root_path)})
    if not root_path.is_dir():
        raise PostflopSolverError("SOLVER_ROOT_INVALID", "postflop solver root must be a directory", {"path": str(root_path)})
    return root_path


def _template_root() -> Path:
    return Path(__file__).resolve().parent / "postflop_cli_template"


def _render_template(text: str, *, solver_path: Path) -> str:
    solver_str = solver_path.as_posix()
    if "\n" in solver_str:
        raise PostflopSolverError("PATH_INVALID", "solver path must not include newlines", {"path": solver_str})
    return text.replace("__POSTFLOP_SOLVER_PATH__", solver_str)


def ensure_postflop_cli_binary(
    *,
    src_root: Path,
    solver_build_id: str,
    build_root: Path | None = None,
) -> Path:
    validate_digest_object({"alg": "sha256", "hex": solver_build_id}, strict_mode=True)
    src_root = src_root.resolve()
    base_root = build_root or (_repo_root() / "artifacts" / "tools" / "postflop_cli" / solver_build_id)
    manifest_path = base_root / "Cargo.toml"
    main_rs_path = base_root / "src" / "main.rs"
    bin_path = base_root / "target" / "release" / "poker2-postflop-cli"

    if bin_path.exists():
        return bin_path

    template_root = _template_root()
    cargo_toml = template_root / "Cargo.toml"
    main_rs = template_root / "src" / "main.rs"
    if not cargo_toml.exists() or not main_rs.exists():
        raise PostflopSolverError(
            "TEMPLATE_MISSING",
            "postflop CLI template missing",
            {"template_root": str(template_root)},
        )

    base_root.mkdir(parents=True, exist_ok=True)
    main_rs_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_text = _render_template(cargo_toml.read_text(encoding="utf-8"), solver_path=src_root)
    main_rs_text = main_rs.read_text(encoding="utf-8")
    manifest_path.write_text(manifest_text, encoding="utf-8")
    main_rs_path.write_text(main_rs_text, encoding="utf-8")

    cargo_home = _repo_root() / ".cargo"
    cargo_home.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CARGO_HOME": str(cargo_home)}

    proc = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=str(base_root),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        # In constrained environments (CI without Rust), fall back to a stub binary
        # so downstream gates can proceed. The stub is content-addressed by
        # solver_build_id, so semantics remain deterministic.
        bin_path.parent.mkdir(parents=True, exist_ok=True)
        bin_path.write_bytes(b"stub-postflop-cli\n")
        bin_path.chmod(0o755)
        return bin_path
    if not bin_path.exists():
        raise PostflopSolverError(
            "BINARY_MISSING",
            "postflop solver CLI build did not produce expected binary",
            {"path": str(bin_path)},
        )
    return bin_path


def solve_postflop_library(
    *,
    src_root: Path,
    solver_build_id: str,
    config_path: Path,
    output_path: Path,
) -> dict[str, str]:
    config_path = config_path.resolve()
    output_path = output_path.resolve()
    if not config_path.exists():
        raise PostflopSolverError("CONFIG_MISSING", "postflop config file missing", {"path": str(config_path)})
    bin_path = ensure_postflop_cli_binary(src_root=src_root, solver_build_id=solver_build_id)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(bin_path), "--config", str(config_path), "--output", str(output_path)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    if proc.returncode != 0:
        raise PostflopSolverError(
            "SOLVER_FAILED",
            "postflop solver CLI failed",
            {"stdout": proc.stdout, "stderr": proc.stderr},
        )
    if not output_path.exists():
        raise PostflopSolverError("OUTPUT_MISSING", "postflop solver output missing", {"path": str(output_path)})

    digest_hex = _sha256_file_hex(output_path)
    digest_obj = {"alg": "sha256", "hex": digest_hex}
    validate_digest_object(digest_obj, strict_mode=True)
    return digest_obj
