"""Tests for client intake and project readiness helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import client_ops  # noqa: E402


def test_intake_queue_flags_missing_details(monkeypatch) -> None:
    def fake_records(table: str) -> list[dict]:
        if table == "enquiries":
            return [
                {
                    "id": "enq1",
                    "name": "Jordan",
                    "email": "jordan@example.com",
                    "service": "Other",
                    "message": "Need mix",
                    "deadline": "",
                    "status": "New",
                }
            ]
        return []

    monkeypatch.setattr(client_ops, "list_records", fake_records)

    items = client_ops.intake_queue()

    assert items[0]["readiness"] == "needs-info"
    assert "deadline" in items[0]["missing"]
    assert "project brief" in items[0]["missing"]


def test_project_readiness_blocks_unpaid_invoice(monkeypatch) -> None:
    def fake_records(table: str) -> list[dict]:
        if table == "projects":
            return [
                {
                    "id": "pr1",
                    "client": "Jordan",
                    "project": "Mix single",
                    "service": "Mixing",
                    "status": "Active",
                    "deadline": "2099-01-01",
                    "waiting_on": "",
                    "next_action": "Send upload link.",
                }
            ]
        if table == "invoices":
            return [{"id": "inv1", "client": "Jordan", "service": "Mixing", "status": "Draft"}]
        return []

    monkeypatch.setattr(client_ops, "list_records", fake_records)

    item = client_ops.project_readiness()[0]

    assert item["readiness"] == "blocked"
    assert "invoice Draft" in item["blockers"]


def test_draft_enquiry_reply_creates_pending_draft(monkeypatch) -> None:
    saved: dict = {}

    def fake_records(table: str) -> list[dict]:
        if table == "enquiries":
            return [
                {
                    "id": "enq1",
                    "name": "Jordan",
                    "email": "jordan@example.com",
                    "service": "Mixing",
                    "message": "I need a mix for one song with references and stems ready.",
                    "deadline": "Friday",
                    "status": "New",
                }
            ]
        return []

    def fake_add(table: str, record: dict) -> dict:
        saved.update(record)
        return {"id": "draft1", **record}

    monkeypatch.setattr(client_ops, "list_records", fake_records)
    monkeypatch.setattr(client_ops, "add_record", fake_add)

    result = client_ops.draft_enquiry_reply("enq1")

    assert result["ok"] is True
    assert saved["status"] == "Pending"
    assert saved["source"] == "client_intake_agent"
    assert "Jordan" in saved["body"]
