from pathlib import Path

import pytest

from poker2.runtime.policy_registry import PolicyRegistryError, resolve_policy_ref
from poker2.runtime.profile_registry import ProfileRegistryError, resolve_profile_ref
from poker2.runtime.artifact_store import ArtifactStoreError, write_artifact_bytes


def test_policy_registry_type_error() -> None:
    with pytest.raises(PolicyRegistryError) as e:
        resolve_policy_ref(None, registry={}, strict_mode=True)  # type: ignore[arg-type]
    assert e.value.code == "TYPE_ERROR"


def test_policy_registry_missing_label() -> None:
    registry = {
        "deadbeef": {
            "policy_id": "deadbeef",
            "policy_spec_ref": "path:dummy",
            "policy_spec_digest": {"alg": "sha256", "hex": "0" * 64},
            "label_or_none": "foo",
        }
    }
    with pytest.raises(PolicyRegistryError) as e:
        resolve_policy_ref("bar", registry=registry, strict_mode=True)
    assert e.value.code == "MISSING_REF"


def test_profile_registry_type_error() -> None:
    with pytest.raises(ProfileRegistryError) as e:
        resolve_profile_ref("", registry={}, strict_mode=True)
    assert e.value.code == "TYPE_ERROR"


def test_profile_registry_missing_label() -> None:
    registry = {
        "feedbeef": {
            "profile_id": "feedbeef",
            "profile_spec_ref": "path:dummy",
            "profile_spec_digest": {"alg": "sha256", "hex": "0" * 64},
            "label_or_none": "foo",
        }
    }
    with pytest.raises(ProfileRegistryError) as e:
        resolve_profile_ref("bar", registry=registry, strict_mode=True)
    assert e.value.code == "MISSING_REF"


def test_write_artifact_bytes_invalid_suffix(tmp_path: Path) -> None:
    with pytest.raises(ArtifactStoreError) as e:
        write_artifact_bytes(b"abc", artifact_id="0" * 64, suffix="bin", out_root=tmp_path)
    assert e.value.code == "SUFFIX_INVALID"


def test_write_artifact_bytes_invalid_id(tmp_path: Path) -> None:
    with pytest.raises(ArtifactStoreError) as e:
        write_artifact_bytes(b"abc", artifact_id="not-a-hex", suffix=".bin", out_root=tmp_path)
    assert e.value.code == "ID_INVALID"
