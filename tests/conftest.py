from __future__ import annotations

import sys
from pathlib import Path


sys.dont_write_bytecode = True

# Ensure repo-local `poker2/` is importable even when invoking the `pytest` console script.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
