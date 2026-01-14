from __future__ import annotations

from pathlib import Path

import pytest

from poker2.engines.postflop_solver import (
    PostflopSolverError,
    compute_postflop_solver_build_id,
    ensure_postflop_cli_binary,
    postflop_solver_src_root_from_paths_trace,
    solve_postflop_library,
)


SOLVER_ROOT = Path("/Users/peng/Workspace/gemini/postflop-solver")


@pytest.mark.skipif(not SOLVER_ROOT.exists(), reason="postflop-solver source not present")
def test_compute_build_id_is_stable() -> None:
    bid1 = compute_postflop_solver_build_id(src_root=SOLVER_ROOT, binding_kind=None, strict_mode=True)
    bid2 = compute_postflop_solver_build_id(src_root=SOLVER_ROOT, binding_kind=None, strict_mode=True)
    assert bid1 == bid2
    assert len(bid1) == 64


@pytest.mark.skipif(not SOLVER_ROOT.exists(), reason="postflop-solver source not present")
def test_ensure_cli_binary_cached() -> None:
    bid = compute_postflop_solver_build_id(src_root=SOLVER_ROOT, binding_kind=None, strict_mode=True)
    bin_path = ensure_postflop_cli_binary(src_root=SOLVER_ROOT, solver_build_id=bid)
    assert bin_path.exists()
    assert bin_path.is_file()


def test_solve_postflop_library_missing_config_raises(tmp_path: Path) -> None:
    with pytest.raises(PostflopSolverError) as exc:
        solve_postflop_library(
            src_root=Path("/nonexistent/solver"),
            solver_build_id="0" * 64,
            config_path=tmp_path / "missing.json",
            output_path=tmp_path / "out.bin",
        )
    assert exc.value.code == "CONFIG_MISSING"


def test_postflop_solver_src_root_from_paths_trace_success() -> None:
    paths_trace = {"resolved_roots_abs": {"postflop_solver_src_root_abs_or_null": str(SOLVER_ROOT)}}
    path = postflop_solver_src_root_from_paths_trace(paths_trace)
    assert path == SOLVER_ROOT.resolve()


def test_postflop_solver_src_root_from_paths_trace_missing() -> None:
    with pytest.raises(PostflopSolverError) as exc:
        postflop_solver_src_root_from_paths_trace({"resolved_roots_abs": {}})
    assert exc.value.code == "POSTFLOP_SOLVER_ROOT_MISSING"
