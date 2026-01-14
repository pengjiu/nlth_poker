from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TriadError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.message}"


_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def triad(*, action_bins_id: str, obs_schema_id: str, rake_id: str) -> dict[str, Any]:
    for field_name, value in (("action_bins_id", action_bins_id), ("obs_schema_id", obs_schema_id), ("rake_id", rake_id)):
        if not isinstance(value, str) or not _SHA256_HEX_RE.fullmatch(value):
            raise TriadError("ID_INVALID", f"{field_name} must be sha256 lowercase hex")
    return {"action_bins_id": action_bins_id, "obs_schema_id": obs_schema_id, "rake_id": rake_id}

