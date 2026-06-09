"""pytest configuration for wash-conformance package tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure harness package root is importable when running tests in-tree.
HARNESS_ROOT = Path(__file__).resolve().parent.parent
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))
