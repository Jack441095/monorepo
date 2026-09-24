"""Re-export of ``kenn.core.abletonosc_bundle`` for the tooling scripts.

The implementation lives in the KENN package so the packaged app's first-run
setup computes exactly the same file list and hash as the deploy tool.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend" / "src"))

from kenn.core.abletonosc_bundle import (  # noqa: E402,F401
    HOT_RELOADABLE,
    SOURCE_DIR,
    STAMP_NAME,
    STAMP_RELATIVE,
    bundle_files,
    bundle_hash,
)

__all__ = ["HOT_RELOADABLE", "SOURCE_DIR", "STAMP_NAME", "STAMP_RELATIVE", "bundle_files", "bundle_hash"]
