from __future__ import annotations

from pathlib import Path

import pytest

from poker2.contractkit import canonicalize_json_bytes
from poker2.runtime.artifacts import (
    ArtifactsError,
    default_artifacts_root,
    run_artifact_paths,
    run_output_dir,
    write_canonical_json,
    write_canonical_ndjson,
)


def test_run_output_dir_validation_errors(tmp_path: Path) -> None:
    with pytest.raises(ArtifactsError) as exc:
        run_output_dir(run_id=123, artifacts_root=tmp_path)  # type: ignore[arg-type]
    assert exc.value.code == "TYPE_ERROR"

    with pytest.raises(ArtifactsError) as exc:
        run_output_dir(run_id="not-hex", artifacts_root=tmp_path)
    assert exc.value.code == "ID_INVALID"

    with pytest.raises(ArtifactsError) as exc:
        run_output_dir(run_id="0" * 64, artifacts_root=tmp_path, run_instance_uuid=1)  # type: ignore[arg-type]
    assert exc.value.code == "TYPE_ERROR"


def test_default_artifacts_root_is_repo_local() -> None:
    root = default_artifacts_root()
    assert root.name == "artifacts"


def test_run_artifact_paths_layout(tmp_path: Path) -> None:
    paths = run_artifact_paths(run_id="0" * 64, artifacts_root=tmp_path)
    assert paths["run_dir"] == tmp_path / ("0" * 64)
    assert paths["run_manifest_path"].name == "run_manifest.json"
    assert paths["eventstream_path"].name == "eventstream.ndjson"
    assert paths["report_path"].name == "report.json"

    paths2 = run_artifact_paths(run_id="0" * 64, artifacts_root=tmp_path, run_instance_uuid="u")
    assert paths2["run_dir"] == tmp_path / ("0" * 64) / "u"


def test_write_canonical_json_adds_trailing_lf(tmp_path: Path) -> None:
    p = tmp_path / "a.json"
    obj = {"b": 1, "a": 2}
    write_canonical_json(p, obj, strict_mode=True)
    raw = p.read_bytes()
    assert raw.endswith(b"\n")
    assert raw == canonicalize_json_bytes(obj, strict_mode=True) + b"\n"


def test_write_canonical_ndjson_is_lf_only_and_has_trailing_lf(tmp_path: Path) -> None:
    p = tmp_path / "s.ndjson"
    objs = [{"a": 1}, {"b": 2}]
    write_canonical_ndjson(p, objs, strict_mode=True)
    raw = p.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
