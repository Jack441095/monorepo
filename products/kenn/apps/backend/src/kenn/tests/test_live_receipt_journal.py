"""Tests for bounded, non-secret Live receipt persistence."""

from __future__ import annotations

import json

from kenn.core import live_receipt_journal as journal


def test_journal_projects_receipt_without_confirmation_secrets(tmp_path, monkeypatch) -> None:
    path = tmp_path / "receipts.jsonl"
    monkeypatch.setattr(journal, "JOURNAL_PATH", path)
    receipt = {
        "schema": "kenn.ableton_recipe_receipt.v1",
        "receipt_id": "receipt-1",
        "action_id": "recipe-1",
        "action": "recipe",
        "status": "applied",
        "verified": True,
        "write_acknowledgement": "unacknowledged_write_reconciled",
        "retry_safe": "safe",
        "target": {"track_name": "4-Audio", "device_name": "EQ Eight"},
        "step_receipts": [{"action": "set_pan", "before": 0.0, "requested": 0.1, "readback": 0.1}],
        "confirmation_token": "must-not-persist",
        "confirmation_meta": {"token": "must-not-persist"},
        "reason": "free-form evidence is not needed in the journal",
    }

    assert journal.record_receipt(receipt, session_id="session-1") is True
    entries = journal.list_receipts(session_id="session-1")
    assert len(entries) == 1
    serialized = json.dumps(entries[0])
    assert "must-not-persist" not in serialized
    assert "confirmation_meta" not in serialized
    assert entries[0]["receipt"]["receipt_id"] == "receipt-1"
    assert entries[0]["receipt"]["write_acknowledgement"] == "unacknowledged_write_reconciled"
    assert entries[0]["receipt"]["retry_safe"] == "safe"


def test_journal_keeps_only_newest_bounded_records(tmp_path, monkeypatch) -> None:
    path = tmp_path / "receipts.jsonl"
    monkeypatch.setattr(journal, "JOURNAL_PATH", path)
    for index in range(journal.MAX_RECEIPTS + 3):
        assert journal.record_receipt({"receipt_id": f"receipt-{index}", "status": "failed"}, session_id="bounded") is True

    assert len(path.read_text(encoding="utf-8").splitlines()) == journal.MAX_RECEIPTS
    entries = journal.list_receipts(session_id="bounded", limit=200)
    assert len(entries) == 200
    assert entries[0]["receipt"]["receipt_id"] == f"receipt-{journal.MAX_RECEIPTS + 2}"
    assert entries[-1]["receipt"]["receipt_id"] == f"receipt-{journal.MAX_RECEIPTS - 200 + 3}"
