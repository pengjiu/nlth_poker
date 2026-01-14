from __future__ import annotations

from pathlib import Path

import pytest

from poker2.engines.postflop_solver import (
    PostflopSolverError,
    compute_postflop_solver_build_id,
    postflop_solver_src_root_from_paths_trace,
)


def _fake_solver_root(tmp_path: Path) -> Path:
    root = tmp_path / "solver"
    root.mkdir()
    (root / "Cargo.toml").write_text(
        "\n".join(
            [
                "[package]",
                'name = "fake_solver"',
                'version = "0.1.0"',
                'edition = "2021"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    src = root / "src"
    src.mkdir()
    (src / "lib.rs").write_text("pub fn foo() {}\n", encoding="utf-8")
    return root


def test_postflop_solver_build_id_changes_on_source_edit(tmp_path: Path) -> None:
    root = _fake_solver_root(tmp_path)
    first = compute_postflop_solver_build_id(src_root=root, binding_kind="cargo_cli", strict_mode=True)
    assert isinstance(first, str) and len(first) == 64

    (root / "src" / "lib.rs").write_text("pub fn foo() { let _x = 1; }\n", encoding="utf-8")
    second = compute_postflop_solver_build_id(src_root=root, binding_kind="cargo_cli", strict_mode=True)
    assert first != second


def test_postflop_solver_src_root_from_paths_trace(tmp_path: Path) -> None:
    root = _fake_solver_root(tmp_path)
    trace = {"resolved_roots_abs": {"postflop_solver_src_root_abs_or_null": str(root)}}
    assert postflop_solver_src_root_from_paths_trace(trace) == root

    with pytest.raises(PostflopSolverError):
        postflop_solver_src_root_from_paths_trace({"resolved_roots_abs": {}})
