"""Regression checks for the repository-owned Ableton evaluation receipt."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[5]
EVAL_SCRIPT = REPO_ROOT / "tooling" / "scripts" / "eval_ableton_assistant.py"


def _contains_legacy_label(value: Any) -> bool:
    if isinstance(value, str):
        return "audio_too" in value.lower() or "audio too" in value.lower()
    if isinstance(value, dict):
        return any(_contains_legacy_label(key) or _contains_legacy_label(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_legacy_label(item) for item in value)
    return False


def test_ableton_eval_receipt_identifies_kenn_engine_without_legacy_labels() -> None:
    completed = subprocess.run(
        [sys.executable, str(EVAL_SCRIPT)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    assert report["engine"] == "KENN/apps/backend/src/kenn (repository-owned, read-only evaluation path)"
    assert report["llm_enabled"] is False
    assert not _contains_legacy_label(report)
