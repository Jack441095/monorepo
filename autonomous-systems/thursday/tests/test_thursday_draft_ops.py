"""Tests for thursday/draft_ops.py (Phase 4 -- scoped writes).

Drafts are pure text from live data (compose invents nothing, sends
nothing). queue_draft is the one gated write: valid confirmation token
for this session + exact text, single-use receipts, replay-safe.
"""

from __future__ import annotations

import pytest

import thursday.ops.draft_ops as drafts
from thursday import action_receipts, confirmation


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(drafts, "OUTBOX_FILE", tmp_path / "outbox.jsonl")
    monkeypatch.setenv("THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3"))


def _token(session_id: str, text: str, ttl_seconds: int = 300) -> str:
    token, _record = confirmation.issue_confirmation(
        session_id=session_id, service_id=drafts.OUTBOX_SERVICE_ID,
        text=text, ttl_seconds=ttl_seconds)
    return token


def test_quote_draft_uses_live_price():
    out = drafts.quote_draft("mixing", "Jordan")
    assert out.startswith("QUOTE DRAFT — NOT SENT")
    assert "£180" in out
    assert "Hi Jordan," in out
    assert "business_knowledge.json" in out


def test_quote_draft_unknown_service_lists_valid_options():
    out = drafts.quote_draft("underwater basket weaving")
    assert "No live offering matches" in out
    assert "mixing" in out
    assert "NOT SENT" in out


def test_review_request_draft_asks_review_and_referral():
    out = drafts.review_request_draft("Mixing")
    assert "REVIEW REQUEST DRAFT — NOT SENT" in out
    assert "review" in out.lower() and "referral" in out.lower() or "intro" in out.lower()
    assert "Hi," in out  # generic greeting when unnamed, never an invented name


def test_reminder_draft_payment_cites_live_policy():
    out = drafts.reminder_draft("payment")
    assert "REMINDER DRAFT — NOT SENT" in out
    assert "deposit" in out.lower() or "payment" in out.lower()


def test_reminder_draft_unknown_kind_refuses():
    out = drafts.reminder_draft("birthday")
    assert "Unknown reminder kind" in out
    assert "NOT SENT" in out


def test_parse_draft_command_shapes():
    assert drafts.parse_draft_command("draft quote mixing") == ("quote", "mixing")
    assert drafts.parse_draft_command("draft review request") == ("review-request", "")
    assert drafts.parse_draft_command("draft reminder payment") == ("reminder", "payment")
    assert drafts.parse_draft_command("hello there") is None


def test_queue_draft_happy_path():
    text = drafts.quote_draft("mastering")
    token = _token("sess-1", text)
    result = drafts.queue_draft("quote", text, session_id="sess-1", confirmation_token=token)
    assert result["ok"] is True and result["replayed"] is False
    queued = drafts.read_outbox()
    assert len(queued) == 1 and queued[0]["kind"] == "quote"


def test_queue_draft_replay_returns_cached_receipt_without_duplicating():
    text = drafts.quote_draft("mastering")
    token = _token("sess-1", text)
    first = drafts.queue_draft("quote", text, session_id="sess-1", confirmation_token=token)
    second = drafts.queue_draft("quote", text, session_id="sess-1", confirmation_token=token)
    assert second["replayed"] is True
    assert second["receipt_id"] == first["receipt_id"]
    assert len(drafts.read_outbox()) == 1


def test_queue_draft_cross_session_replay_refused_at_verify():
    """Session-bound tokens fail closed at verify for the wrong session
    (defense in depth: claim/ReceiptConflict is the second gate, hit by
    same-session text-swaps -- see next test)."""
    text = drafts.quote_draft("mastering")
    token = _token("sess-1", text)
    drafts.queue_draft("quote", text, session_id="sess-1", confirmation_token=token)
    with pytest.raises(ValueError, match="Invalid or expired"):
        drafts.queue_draft("quote", text, session_id="sess-2", confirmation_token=token)
    assert len(drafts.read_outbox()) == 1


def test_queue_draft_same_session_text_swap_hits_receipt_conflict():
    text = drafts.quote_draft("mastering")
    token = _token("sess-1", text)
    drafts.queue_draft("quote", text, session_id="sess-1", confirmation_token=token)
    other = drafts.quote_draft("mixing")
    other_token = _token("sess-1", other)
    drafts.queue_draft("quote", other, session_id="sess-1", confirmation_token=other_token)
    # Replaying sess-1's FIRST token against DIFFERENT text fails verify
    # (text-bound); a forged same-receipt-id different-text claim raises
    # ReceiptConflict at the receipts layer -- proven directly here.
    from thursday import action_receipts as receipts
    receipt_id = receipts.receipt_id_for_token(token)
    with pytest.raises(receipts.ReceiptConflict):
        receipts.claim_action(receipt_id, session_id="sess-1",
                              service_id=drafts.OUTBOX_SERVICE_ID, text=other)
    assert len(drafts.read_outbox()) == 2


def test_queue_draft_bad_token_queues_nothing():
    text = drafts.quote_draft("mastering")
    with pytest.raises(ValueError, match="Invalid or expired"):
        drafts.queue_draft("quote", text, session_id="sess-1", confirmation_token="v1.dead.beef.0000")
    assert drafts.read_outbox() == []


def test_queue_draft_expired_token_queues_nothing():
    text = drafts.quote_draft("mastering")
    token = _token("sess-1", text, ttl_seconds=1)
    import time
    time.sleep(2.1)  # past expiry with margin for int() truncation at both ends
    with pytest.raises(ValueError, match="Invalid or expired"):
        drafts.queue_draft("quote", text, session_id="sess-1", confirmation_token=token)
    assert drafts.read_outbox() == []


def test_queue_draft_text_binding_blocks_swapped_text():
    text = drafts.quote_draft("mastering")
    token = _token("sess-1", text)
    with pytest.raises(ValueError, match="Invalid or expired"):
        drafts.queue_draft("quote", drafts.quote_draft("mixing"),
                           session_id="sess-1", confirmation_token=token)
    assert drafts.read_outbox() == []
