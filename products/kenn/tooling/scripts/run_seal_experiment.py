#!/usr/bin/env python3
"""Run the offline pilot without importing KENN's application startup or connecting to Live."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tooling"), str(ROOT / "apps/backend/src")]

from seal_experiment.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
