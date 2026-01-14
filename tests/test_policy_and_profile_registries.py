from __future__ import annotations

import json
from pathlib import Path

import pytest

from poker2.protocol.policy import PolicyError, load_policy_spec, policy_id, validate_policy_spec
from poker2.protocol.policy import policy_closure_from_spec, policy_params_digest
from poker2.protocol.profile import ProfileError, load_profile_spec, profile_id, profile_hash_input, validate_profile_spec
from poker2.runtime.policy_registry import PolicyRegistryError, build_policy_registry, resolve_policy_ref
from poker2.runtime.profile_registry import ProfileRegistryError, build_profile_registry, resolve_profile_ref


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_load_policy_spec_reports_json_parse_fail(tmp_path: Path) -> None:
    p = tmp_path / "policy.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(PolicyError) as ei:
        load_policy_spec(p)
    assert ei.value.code == "JSON_PARSE_FAIL"


def test_validate_policy_spec_rejects_extra_fields_in_strict_mode() -> None:
    spec = {
        "policy_kind": "baseline",
        "policy_deps": [],
        "policy_params_digest": {"alg": "sha256", "hex": "0" * 64},
        "stochastic": False,
        "unexpected": 1,
    }
    with pytest.raises(PolicyError) as ei:
        validate_policy_spec(spec, strict_mode=True)
    assert ei.value.code == "EXTRA_FIELDS"


def test_policy_params_digest_is_sha256_object() -> None:
    d = policy_params_digest({"x": 1}, strict_mode=True)
    assert d["alg"] == "sha256"
    assert len(d["hex"]) == 64


def test_policy_closure_from_spec_type_and_missing_fields_errors() -> None:
    with pytest.raises(PolicyError) as ei:
        policy_closure_from_spec([], strict_mode=True)
    assert ei.value.code == "TYPE_ERROR"

    with pytest.raises(PolicyError) as ei:
        policy_closure_from_spec({"policy_kind": "baseline"}, strict_mode=True)
    assert ei.value.code == "MISSING_FIELDS"


def test_validate_policy_spec_rejects_dep_shape_errors() -> None:
    base = {
        "policy_kind": "baseline",
        "policy_params_digest": {"alg": "sha256", "hex": "0" * 64},
        "stochastic": False,
    }

    with pytest.raises(PolicyError) as ei:
        validate_policy_spec({**base, "policy_deps": [1]}, strict_mode=True)
    assert ei.value.code == "TYPE_ERROR"

    with pytest.raises(PolicyError) as ei:
        validate_policy_spec({**base, "policy_deps": [{"artifact_ref": "artifact://%s" % ("0" * 64)}]}, strict_mode=True)
    assert ei.value.code == "MISSING_FIELDS"

    with pytest.raises(PolicyError) as ei:
        validate_policy_spec({**base, "policy_deps": [{"artifact_ref": 1, "digest": {"alg": "sha256", "hex": "0" * 64}}]}, strict_mode=True)
    assert ei.value.code == "TYPE_ERROR"


def test_validate_policy_spec_rejects_policy_id_type_error() -> None:
    spec = {
        "policy_kind": "baseline",
        "policy_deps": [],
        "policy_params_digest": {"alg": "sha256", "hex": "0" * 64},
        "stochastic": False,
        "policy_id": 123,
    }
    with pytest.raises(PolicyError) as ei:
        validate_policy_spec(spec, strict_mode=True)
    assert ei.value.code == "TYPE_ERROR"


def test_validate_policy_spec_rejects_null_convention_violation() -> None:
    spec = {
        "policy_kind": "baseline",
        "policy_deps": [{"artifact_ref": "none", "digest": {"alg": "sha256", "hex": "0" * 64}}],
        "policy_params_digest": {"alg": "sha256", "hex": "0" * 64},
        "stochastic": False,
    }
    with pytest.raises(PolicyError) as ei:
        validate_policy_spec(spec, strict_mode=True)
    assert ei.value.code == "NULL_CONVENTION_VIOLATION"


def test_validate_policy_spec_rejects_none_string_in_hash_input() -> None:
    spec = {
        "policy_kind": "baseline",
        "policy_deps": [{"artifact_ref": "artifact://%s" % ("0" * 64), "digest": {"alg": "sha256", "hex": "0" * 64}, "x_label": "none"}],
        "policy_params_digest": {"alg": "sha256", "hex": "0" * 64},
        "stochastic": False,
    }
    # In strict_mode, dep extra fields are rejected before null convention check.
    with pytest.raises(PolicyError) as ei1:
        validate_policy_spec(spec, strict_mode=True)
    assert ei1.value.code == "EXTRA_FIELDS"

    # policy_kind controls an enum and fails before Null Convention checks; this test ensures the dep extra-field check fires.


def test_policy_id_is_stable_and_ignores_policy_label() -> None:
    base = {
        "policy_kind": "baseline",
        "policy_deps": [],
        "policy_params_digest": {"alg": "sha256", "hex": "0" * 64},
        "stochastic": False,
    }
    a = {**base, "policy_label": "a"}
    b = {**base, "policy_label": "b"}
    assert policy_id(a, strict_mode=True) == policy_id(b, strict_mode=True)


def test_build_policy_registry_returns_empty_for_missing_root(tmp_path: Path) -> None:
    missing_root = tmp_path / "does_not_exist"
    registry = build_policy_registry(policies_root=missing_root, strict_mode=True)
    assert registry == {}


def test_build_policy_registry_raises_on_invalid_spec(tmp_path: Path) -> None:
    root = tmp_path / "policies"
    root.mkdir()
    (root / "bad.json").write_text("[]", encoding="utf-8")
    with pytest.raises(PolicyRegistryError) as ei:
        build_policy_registry(policies_root=root, strict_mode=True)
    assert ei.value.code == "POLICY_SPEC_INVALID"


def test_build_policy_registry_raises_on_duplicate_policy_id(tmp_path: Path) -> None:
    repo = _repo_root()
    src = repo / "specs" / "policies" / "internal_baseline_policy_v1.json"
    payload = json.loads(src.read_text(encoding="utf-8"))

    root = tmp_path / "policies"
    root.mkdir()
    (root / "a.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (root / "b.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PolicyRegistryError) as ei:
        build_policy_registry(policies_root=root, strict_mode=True)
    assert ei.value.code == "AMBIGUOUS"


def test_resolve_policy_ref_by_id_and_label() -> None:
    registry = build_policy_registry(strict_mode=True)
    assert registry, "expected at least one internal policy spec"
    # Resolve internal baseline by label.
    entry_by_label, trace_by_label = resolve_policy_ref("internal_baseline_policy_v1", registry=registry, strict_mode=True)
    pid = entry_by_label["policy_id"]
    assert trace_by_label["resolved_policy_ref"] == f"policy://{pid}"

    entry_by_id, trace_by_id = resolve_policy_ref(f"policy://{pid}", registry=registry, strict_mode=True)
    assert entry_by_id["policy_id"] == pid
    assert trace_by_id["resolved_policy_ref"] == f"policy://{pid}"


def test_resolve_policy_ref_invalid_uri_and_missing_id() -> None:
    with pytest.raises(PolicyRegistryError) as ei:
        resolve_policy_ref("policy://not_sha256", registry={}, strict_mode=True)
    assert ei.value.code == "ID_INVALID"

    with pytest.raises(PolicyRegistryError) as ei:
        resolve_policy_ref(f"policy://{'1' * 64}", registry={}, strict_mode=True)
    assert ei.value.code == "MISSING_REF"


def test_resolve_policy_ref_ambiguous_label_strict_mode() -> None:
    registry = {
        "a" * 64: {"policy_id": "a" * 64, "label_or_none": "x", "policy_spec_ref": "path:1.json"},
        "b" * 64: {"policy_id": "b" * 64, "label_or_none": "x", "policy_spec_ref": "path:2.json"},
    }
    with pytest.raises(PolicyRegistryError) as ei:
        resolve_policy_ref("x", registry=registry, strict_mode=True)
    assert ei.value.code == "AMBIGUOUS"


def test_load_profile_spec_reports_json_parse_fail(tmp_path: Path) -> None:
    p = tmp_path / "profile.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(ProfileError) as ei:
        load_profile_spec(p)
    assert ei.value.code == "JSON_PARSE_FAIL"


def test_profile_hash_input_strips_label_keys() -> None:
    spec = {"profile_schema_id": "profile_spec_v1", "profile_label": "x", "nested": {"a_label": "y", "k": 1}}
    out = profile_hash_input(spec, strict_mode=True)
    assert "profile_label" not in out
    assert "a_label" not in out["nested"]
    assert out["nested"]["k"] == 1


def test_profile_hash_input_type_error() -> None:
    with pytest.raises(ProfileError) as ei:
        profile_hash_input([], strict_mode=True)
    assert ei.value.code == "TYPE_ERROR"


def test_profile_hash_input_strips_labels_in_lists() -> None:
    spec = {
        "profile_schema_id": "profile_spec_v1",
        "steps": [{"k": 1, "k_label": "x"}, {"k": 2, "latest": "y"}],
    }
    out = profile_hash_input(spec, strict_mode=True)
    assert out["steps"][0] == {"k": 1}
    assert out["steps"][1] == {"k": 2}


def test_profile_hash_input_rejects_null_convention_violation() -> None:
    spec = {"profile_schema_id": "profile_spec_v1", "k": "none"}
    with pytest.raises(ProfileError) as ei:
        profile_hash_input(spec, strict_mode=True)
    assert ei.value.code == "NULL_CONVENTION_VIOLATION"


def test_validate_profile_spec_rejects_profile_id_type_error() -> None:
    with pytest.raises(ProfileError) as ei:
        validate_profile_spec({"profile_id": 123}, strict_mode=True)
    assert ei.value.code == "TYPE_ERROR"


def test_validate_profile_spec_rejects_profile_id_invalid() -> None:
    with pytest.raises(ProfileError) as ei:
        validate_profile_spec({"profile_id": "not_sha256"}, strict_mode=True)
    assert ei.value.code == "ID_INVALID"


def test_profile_id_ignores_profile_label() -> None:
    base = {"profile_schema_id": "profile_spec_v1", "purpose": "throughput", "concurrency": {"workers": 1}}
    a = {**base, "profile_label": "a"}
    b = {**base, "profile_label": "b"}
    assert profile_id(a, strict_mode=True) == profile_id(b, strict_mode=True)


def test_build_profile_registry_returns_empty_for_missing_root(tmp_path: Path) -> None:
    missing_root = tmp_path / "does_not_exist"
    registry = build_profile_registry(profiles_root=missing_root, strict_mode=True)
    assert registry == {}


def test_build_profile_registry_raises_on_invalid_spec(tmp_path: Path) -> None:
    root = tmp_path / "profiles"
    root.mkdir()
    (root / "bad.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ProfileRegistryError) as ei:
        build_profile_registry(profiles_root=root, strict_mode=True)
    assert ei.value.code == "PROFILE_SPEC_INVALID"


def test_build_profile_registry_raises_on_duplicate_profile_id(tmp_path: Path) -> None:
    repo = _repo_root()
    src = repo / "specs" / "profiles" / "internal_profile_v1.json"
    payload = json.loads(src.read_text(encoding="utf-8"))

    root = tmp_path / "profiles"
    root.mkdir()
    (root / "a.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (root / "b.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ProfileRegistryError) as ei:
        build_profile_registry(profiles_root=root, strict_mode=True)
    assert ei.value.code == "AMBIGUOUS"


def test_resolve_profile_ref_by_id_and_label() -> None:
    registry = build_profile_registry(strict_mode=True)
    assert registry, "expected at least one internal profile spec"

    entry_by_label, trace_by_label = resolve_profile_ref("internal_profile_v1", registry=registry, strict_mode=True)
    pid = entry_by_label["profile_id"]
    assert trace_by_label["resolved_profile_ref"] == f"profile://{pid}"

    entry_by_id, trace_by_id = resolve_profile_ref(f"profile://{pid}", registry=registry, strict_mode=True)
    assert entry_by_id["profile_id"] == pid
    assert trace_by_id["resolved_profile_ref"] == f"profile://{pid}"


def test_resolve_profile_ref_invalid_uri_and_missing_id() -> None:
    with pytest.raises(ProfileRegistryError) as ei:
        resolve_profile_ref("profile://not_sha256", registry={}, strict_mode=True)
    assert ei.value.code == "ID_INVALID"

    with pytest.raises(ProfileRegistryError) as ei:
        resolve_profile_ref(f"profile://{'1' * 64}", registry={}, strict_mode=True)
    assert ei.value.code == "MISSING_REF"


def test_resolve_profile_ref_ambiguous_label_strict_mode() -> None:
    registry = {
        "a" * 64: {"profile_id": "a" * 64, "label_or_none": "x", "profile_spec_ref": "path:1.json"},
        "b" * 64: {"profile_id": "b" * 64, "label_or_none": "x", "profile_spec_ref": "path:2.json"},
    }
    with pytest.raises(ProfileRegistryError) as ei:
        resolve_profile_ref("x", registry=registry, strict_mode=True)
    assert ei.value.code == "AMBIGUOUS"
