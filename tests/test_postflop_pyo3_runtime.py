from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import builtins
import poker2.engines.postflop_pyo3 as pyo3


def test_compute_pyo3_build_id(tmp_path: Path) -> None:
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text("[package]\nname=\"dummy\"\nversion=\"0.1.0\"\n", encoding="utf-8")
    bid = pyo3.compute_pyo3_build_id(tmp_path, strict_mode=True)
    assert len(bid) == 64


def test_compute_pyo3_build_id_missing(tmp_path: Path) -> None:
    with pytest.raises(pyo3.PostflopRuntimeError) as e:
        pyo3.compute_pyo3_build_id(tmp_path, strict_mode=True)
    assert e.value.code == "SOLVER_ROOT_INVALID"


def test_solve_postflop_pyo3_mock(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class MockMod:
        @staticmethod
        def solve_json(payload: str) -> str:
            calls.append(json.loads(payload))
            return json.dumps({"target_total_commit_chips": 123})

    # Bypass actual build/import
    monkeypatch.setattr(pyo3, "_ensure_pyo3_module", lambda build_id, src_root: MockMod)
    # Use deterministic payload and build id
    solve_payload = {"foo": "bar"}
    out = pyo3.solve_postflop_pyo3(
        src_root=Path("."),
        solve_payload=solve_payload,
        solver_build_id="0" * 64,
        strict_mode=True,
        timeout_seconds=1.0,
    )
    assert out["target_total_commit_chips"] == 123
    assert calls and calls[0]["foo"] == "bar"


def test_solve_postflop_pyo3_cache(monkeypatch) -> None:
    calls = {"n": 0}

    class MockMod:
        @staticmethod
        def solve_json(payload: str) -> str:
            calls["n"] += 1
            return json.dumps({"target_total_commit_chips": 5})

    monkeypatch.setattr(pyo3, "_ensure_pyo3_module", lambda build_id, src_root: MockMod)
    monkeypatch.setattr(pyo3, "_solve_cache", {})
    payload = {"x": 1}
    out1 = pyo3.solve_postflop_pyo3(
        src_root=Path("."),
        solve_payload=payload,
        solver_build_id="0" * 64,
        strict_mode=True,
        timeout_seconds=1.0,
    )
    out2 = pyo3.solve_postflop_pyo3(
        src_root=Path("."),
        solve_payload=payload,
        solver_build_id="0" * 64,
        strict_mode=True,
        timeout_seconds=1.0,
    )
    assert out1 == out2
    assert calls["n"] == 1  # second call hits cache


def test_solve_postflop_pyo3_timeout(monkeypatch) -> None:
    class MockThread:
        def __init__(self, target=None):
            self._target = target

        def start(self):
            # do not run target to simulate hang
            pass

        def join(self, timeout=None):
            pass

        def is_alive(self):
            return True

    monkeypatch.setattr(pyo3, "threading", pyo3.threading)
    monkeypatch.setattr(pyo3.threading, "Thread", MockThread)
    monkeypatch.setattr(pyo3, "_ensure_pyo3_module", lambda build_id, src_root: None)
    with pytest.raises(pyo3.PostflopRuntimeError) as e:
        pyo3.solve_postflop_pyo3(
            src_root=Path("."),
            solve_payload={},
            solver_build_id="0" * 64,
            strict_mode=True,
            timeout_seconds=0.01,
        )
    assert e.value.code == "TIMEOUT"


def test_solve_postflop_pyo3_parse_fail(monkeypatch) -> None:
    class MockMod:
        @staticmethod
        def solve_json(payload: str) -> str:
            return "not-json"

    monkeypatch.setattr(pyo3, "_ensure_pyo3_module", lambda build_id, src_root: MockMod)
    with pytest.raises(pyo3.PostflopRuntimeError) as e:
        pyo3.solve_postflop_pyo3(
            src_root=Path("."),
            solve_payload={},
            solver_build_id="0" * 64,
            strict_mode=True,
            timeout_seconds=1.0,
    )
    assert e.value.code == "PARSE_FAILED"


def test_solve_postflop_pyo3_raise(monkeypatch) -> None:
    class MockMod:
        @staticmethod
        def solve_json(payload: str) -> str:
            raise RuntimeError("boom")

    monkeypatch.setattr(pyo3, "_ensure_pyo3_module", lambda build_id, src_root: MockMod)
    with pytest.raises(pyo3.PostflopRuntimeError) as e:
        pyo3.solve_postflop_pyo3(
            src_root=Path("."),
            solve_payload={},
            solver_build_id="0" * 64,
            strict_mode=True,
            timeout_seconds=1.0,
        )
    assert e.value.code == "SOLVE_FAILED"


def test_solver_project_root_callable() -> None:
    # Touch default path function for coverage.
    p = pyo3._solver_project_root()
    assert isinstance(p, Path)

def test_ensure_pyo3_module_build_fail(monkeypatch, tmp_path: Path) -> None:
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text("[package]\nname=\"dummy\"\nversion=\"0.1.0\"\n", encoding="utf-8")

    class MockCompleted:
        returncode = 1
        stdout = "out"
        stderr = "err"

    monkeypatch.setattr(pyo3, "subprocess", pyo3.subprocess)
    monkeypatch.setattr(pyo3.subprocess, "run", lambda *a, **k: MockCompleted())
    with pytest.raises(pyo3.PostflopRuntimeError) as e:
        pyo3._ensure_pyo3_module("0" * 64, tmp_path)
    assert e.value.code == "BUILD_FAILED"


def test_ensure_pyo3_module_import_fail(monkeypatch, tmp_path: Path) -> None:
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text("[package]\nname=\"dummy\"\nversion=\"0.1.0\"\n", encoding="utf-8")

    class MockCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(pyo3.subprocess, "run", lambda *a, **k: MockCompleted())

    real_import = builtins.__import__

    def _fake_import(name, *a, **k):
        if name == "postflop_solver":
            raise ImportError("no module")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    with pytest.raises(pyo3.PostflopRuntimeError) as e:
        pyo3._ensure_pyo3_module("0" * 64, tmp_path)
    assert e.value.code == "IMPORT_FAILED"
