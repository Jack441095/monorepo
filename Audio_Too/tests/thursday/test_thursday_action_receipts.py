"""Receipt integrity tests for ``thursday/action_receipts.py``.

Receipts are the audit/idempotency backbone for consequential actions:
one confirmed action must execute exactly once, be traceable, and never
be reusable for a different request. These tests pin those guarantees:
claim idempotency, conflict rejection, session-scoped reads, single
completion, ordering, and concurrent-claim safety.
"""

from __future__ import annotations

import threading

import pytest

from thursday import action_receipts as receipts


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3")
    )


def _claim_kwargs(session="s1", service="email.send", text="send invoice"):
    return dict(session_id=session, service_id=service, text=text)


# ─── Claim lifecycle ─────────────────────────────────────────────────────


def test_first_claim_wins_and_is_marked_processing():
    result = receipts.claim_action("act-1", **_claim_kwargs())
    assert result.claimed is True
    assert result.receipt.receipt_id == "act-1"
    assert result.receipt.status == "processing"
    assert result.receipt.completed_at is None


def test_replay_claim_returns_existing_receipt_without_double_claim():
    first = receipts.claim_action("act-2", **_claim_kwargs())
    second = receipts.claim_action("act-2", **_claim_kwargs())

    assert first.claimed is True
    assert second.claimed is False
    assert second.receipt == first.receipt


def test_reused_receipt_for_different_text_raises_conflict():
    receipts.claim_action("act-3", **_claim_kwargs(text="email Jordan"))
    with pytest.raises(receipts.ReceiptConflict):
        receipts.claim_action("act-3", **_claim_kwargs(text="email everyone"))


def test_reused_receipt_for_different_service_raises_conflict():
    receipts.claim_action("act-4", **_claim_kwargs(service="email.send"))
    with pytest.raises(receipts.ReceiptConflict):
        receipts.claim_action("act-4", **_claim_kwargs(service="calendar.book"))


def test_reused_receipt_from_other_session_raises_conflict():
    """A receipt captured in one session cannot be driven from another."""
    receipts.claim_action("act-5", **_claim_kwargs(session="owner"))
    with pytest.raises(receipts.ReceiptConflict):
        receipts.claim_action("act-5", **_claim_kwargs(session="attacker"))


def test_distinct_tokens_get_distinct_stable_receipt_ids():
    a = receipts.receipt_id_for_token("token-a")
    b = receipts.receipt_id_for_token("token-b")
    assert a != b
    assert receipts.receipt_id_for_token("token-a") == a  # stable


def test_request_hash_binds_service_and_text():
    h1 = receipts.request_hash("svc", "text one")
    h2 = receipts.request_hash("svc", "text two")
    h3 = receipts.request_hash("other", "text one")
    assert len({h1, h2, h3}) == 3
    # Whitespace-only differences do not change the binding.
    assert receipts.request_hash("svc", "  text one ") == h1


# ─── Completion ──────────────────────────────────────────────────────────


def test_complete_once_preserves_first_response_on_repeat():
    receipts.claim_action("act-6", **_claim_kwargs())
    done = receipts.complete_action("act-6", response_text="sent")
    again = receipts.complete_action("act-6", response_text="TAMPERED")

    assert done.status == "completed"
    assert again.response_text == "sent"  # original outcome survives replays
    assert again.completed_at == done.completed_at


def test_complete_unknown_receipt_raises_lookup_error():
    with pytest.raises(LookupError):
        receipts.complete_action("act-missing", response_text="nope")


# ─── Session-scoped reads ────────────────────────────────────────────────


def test_get_receipt_is_session_scoped():
    receipts.claim_action("act-7", **_claim_kwargs(session="owner"))

    mine = receipts.get_receipt("act-7", session_id="owner")
    theirs = receipts.get_receipt("act-7", session_id="someone-else")

    assert mine is not None
    assert theirs is None


# ─── Reporting surface ───────────────────────────────────────────────────


def test_recent_receipts_orders_newest_first_and_filters_by_since():
    r1 = receipts.claim_action("act-8", **_claim_kwargs()).receipt
    r2 = receipts.claim_action("act-9", **_claim_kwargs()).receipt
    # Guarantee strictly increasing timestamps even on coarse clocks.
    import time as time_module

    time_module.sleep(0.01)
    r3 = receipts.claim_action("act-10", **_claim_kwargs()).receipt

    recent = receipts.recent_receipts()
    ids = [r.receipt_id for r in recent]
    assert ids[:3] == [r3.receipt_id, r2.receipt_id, r1.receipt_id]

    # The since filter is inclusive of the boundary receipt (created_at >=).
    after = receipts.recent_receipts(since=r2.created_at)
    assert [r.receipt_id for r in after] == [r3.receipt_id, r2.receipt_id]
    strictly_after = receipts.recent_receipts(
        since=r2.created_at + 0.001
    )
    assert [r.receipt_id for r in strictly_after] == [r3.receipt_id]


def test_recent_receipts_respects_limit():
    for i in range(7):
        receipts.claim_action(f"act-l{i}", **_claim_kwargs())
    page = receipts.recent_receipts(limit=3)
    assert len(page) == 3


# ─── Concurrency ─────────────────────────────────────────────────────────


def test_concurrent_claims_execute_exactly_once():
    """N racing claims on one token → exactly one winner, rest are replays,
    and no exception escapes (conflicts/retries resolve via SQLite locks)."""
    winners: list[bool] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(8)

    def racer():
        try:
            barrier.wait(timeout=10)
            result = receipts.claim_action(
                "act-race", **_claim_kwargs()
            )
            if result.claimed:
                winners.append(True)
        except Exception as exc:  # pragma: no cover — surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=racer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors
    assert len(winners) == 1

    stored = receipts.get_receipt("act-race", session_id="s1")
    assert stored is not None and stored.status == "processing"


def test_concurrent_completions_settle_on_single_outcome():
    receipts.claim_action("act-done", **_claim_kwargs())
    results: list[str] = []
    lock = threading.Lock()

    def finish(tag: str):
        receipt = receipts.complete_action("act-done", response_text=f"outcome-{tag}")
        with lock:
            results.append(receipt.response_text)

    threads = [
        threading.Thread(target=finish, args=(str(i),)) for i in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 6
    # Every observer sees the SAME winning response — no torn state.
    assert len(set(results)) == 1
    assert results[0].startswith("outcome-")
