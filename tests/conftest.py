"""Pytest bootstrap: put the repo root on sys.path.

Tests import top-level packages like `helpers.*` and `servers.*`. Pytest's
rootdir isn't automatically importable, so add the repo root (the parent of
this tests/ dir) to sys.path before collection.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
