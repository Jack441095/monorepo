"""Tests for LM gap logging."""

from __future__ import annotations

import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))

from tips_gaps import dismiss_gap, list_gaps, record_gap, should_record  # noqa: E402


def test_should_record_low_confidence() -> None:
    assert should_record({"confidence": "low", "sources": []}) is True


def test_should_record_medium_without_note() -> None:
    assert should_record({"confidence": "medium", "sources": [{"kind": "manual"}]}) is True


def test_should_not_record_high_with_note() -> None:
    assert should_record({"confidence": "high", "sources": [{"kind": "note"}]}) is False


def test_record_and_dismiss_roundtrip() -> None:
    row = record_gap(
        "xyzzy unknown topic test",
        {"confidence": "low", "sources": [], "topics": ["bass"]},
        channel="test",
    )
    assert row is not None
    items = list_gaps()
    assert any(item["id"] == row["id"] for item in items)
    assert dismiss_gap(row["id"]) is True
    assert not any(item["id"] == row["id"] for item in list_gaps())
