"""Tests for repeatable KENN tester probes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

from kenn_tester_probe import row_passed, write_report  # noqa: E402


def test_tester_probe_row_pass_logic() -> None:
    assert row_passed({"expected_confidence": "high"}, {"confidence": "high", "weak_match": False}) is True
    assert row_passed({"expected_confidence": "high"}, {"confidence": "low", "weak_match": True}) is False
    assert row_passed({"expected_confidence": "low"}, {"confidence": "low", "weak_match": True}) is True


def test_tester_probe_write_report(tmp_path: Path) -> None:
    path = write_report({"total": 1, "passed": 1, "failed": 0, "rows": []}, tmp_path)

    assert path.name.startswith("kenn_tester_probe_")
    assert path.read_text(encoding="utf-8").strip().startswith("{")
