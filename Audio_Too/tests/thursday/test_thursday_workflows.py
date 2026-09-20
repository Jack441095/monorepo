from __future__ import annotations

import pytest

from thursday.phase3_handlers import (
    handle_audiogen_job,
    handle_audiogen_render,
    handle_creative_lab_repairs,
)
from thursday.registry import _handle_agent_workflow_chain, _handle_audio_storage
from agents.Shared.draft_sender import send_draft


def test_invoice_draft_send_uses_shared_transactional_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def service(request):
        calls.append(request.draft_id)
        return 200, {
            "ok": True,
            "draft": {
                "id": request.draft_id,
                "status": "Sent",
                "type": "invoice",
                "recipient": "Jordan",
                "subject": "Mix invoice",
            },
            "followup": {"id": "followup-1", "due": "2026-07-07"},
            "already_sent": False,
        }

    monkeypatch.setattr("agents.Shared.draft_sender.send_draft_service", service)
    result = send_draft(lambda _table: [], lambda *_args: {}, lambda *_args: {}, "abcd1234")

    assert calls == ["abcd1234"]
    assert "Draft Sent" in result
    assert "Jordan" in result


def test_legacy_direct_email_flag_is_rejected_without_mutation() -> None:
    called = False

    def mutate(*_args):
        nonlocal called
        called = True
        return {}

    result = send_draft(lambda _table: [], mutate, mutate, "abcd1234", use_email=True)
    assert "Direct email is disabled" in result
    assert called is False


def test_agent_email_chain_creates_only_an_isolated_reminder() -> None:
    saved: list[tuple[str, dict]] = []

    class FakeAPI:
        @staticmethod
        def admin_agent(command: str, text: str) -> str:
            assert command == "email"
            assert "Jordan" in text
            return "Draft saved"

    def add_record(table: str, record: dict) -> dict:
        saved.append((table, record))
        return {"id": "followup-1", **record}

    result = _handle_agent_workflow_chain(
        FakeAPI(),
        "draft an email to Jordan and remind me to check next week",
        {"_add_record": add_record},
    )

    assert "Draft saved" in result
    assert "Reminder created" in result
    assert saved[0][0] == "followups"
    assert saved[0][1]["owner"] == "thursday"


def test_audiogen_render_and_followup_cancel_use_the_returned_job() -> None:
    class FakeAPI:
        @staticmethod
        def audiogen_infer_emotion(_text: str) -> str:
            return "joy"

        @staticmethod
        def audiogen_render_full_song(**kwargs) -> dict:
            assert kwargs == {"emotion": "joy", "bars": 8, "k": 2}
            return {"ok": True, "job": {"id": "abcdef123456", "status": "queued"}}

        @staticmethod
        def audiogen_cancel_render(job_id: str) -> dict:
            assert job_id == "abcdef123456"
            return {"ok": True, "job": {"id": job_id, "status": "cancelled"}}

    rendered = handle_audiogen_render(FakeAPI(), "render an 8 bar joyful song with 2 variations")
    cancelled = handle_audiogen_job(
        FakeAPI(),
        "cancel that render",
        {"current_audiogen_job": "abcdef123456"},
    )

    assert "Job ID: abcdef123456" in rendered
    assert "Cancelled render abcdef123456" in cancelled


def test_creative_repair_promotion_targets_explicit_feedback_id() -> None:
    class FakeAPI:
        @staticmethod
        def creative_lab_promote_repair(feedback_id: str) -> dict:
            assert feedback_id == "abcdef123456"
            return {"ok": True, "feedback_id": feedback_id, "status": "promoted"}

    result = handle_creative_lab_repairs(FakeAPI(), "promote repair abcdef123456")
    assert '"status": "promoted"' in result


def test_conversational_cleanup_is_always_a_dry_run() -> None:
    calls: list[bool] = []

    class FakeAPI:
        @staticmethod
        def mix_review_cleanup_orphans(dry_run: bool = False) -> dict:
            calls.append(dry_run)
            return {"ok": True, "dry_run": dry_run, "deleted": 0}

    result = _handle_audio_storage(FakeAPI(), "clean up orphaned uploads")
    assert calls == [True]
    assert "'dry_run': True" in result
