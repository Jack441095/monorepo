"""Unit tests for kenn.core.listening_checkpoint (D2.4,
docs/KENN_FUTURE_PLAN.md Phase 2)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.listening_checkpoint import classify_checkpoint_reply, detect_concrete_proposal  # noqa: E402


def test_detect_concrete_proposal_for_unvalidated_eq_move():
    payload = {"contains_unvalidated_suggestions": True}
    assert detect_concrete_proposal(payload) == "the suggested EQ move"


def test_detect_concrete_proposal_for_queued_revision():
    payload = {
        "route": "automix_revision",
        "found": True,
        "automix_revision": {"ok": True, "job_id": "job-1"},
    }
    assert detect_concrete_proposal(payload) == "the revision once it renders"


def test_detect_concrete_proposal_none_for_a_revision_that_failed_to_queue():
    payload = {
        "route": "automix_revision",
        "found": False,
        "automix_revision": {"ok": False},
    }
    assert detect_concrete_proposal(payload) == ""


def test_detect_concrete_proposal_none_for_a_plain_answer():
    assert detect_concrete_proposal({"answer": "here's some general advice", "found": True}) == ""


def test_detect_concrete_proposal_none_for_an_executed_daw_write():
    # Explicit user-requested primitives (mute/solo/volume the user
    # directly named) are a different category -- no checkpoint needed,
    # the user already knows exactly what they asked for.
    payload = {"orchestration": {"status": "executed", "agent": "ableton_controller"}}
    assert detect_concrete_proposal(payload) == ""


def test_classify_checkpoint_reply_accepts_common_affirmatives():
    for text in ["yes", "yeah", "yep", "sounds good", "keep it", "that's great", "perfect"]:
        assert classify_checkpoint_reply(text) == "accept", text


def test_classify_checkpoint_reply_rejects_common_negatives():
    for text in ["no", "nah", "nope", "revert", "undo", "try something else"]:
        assert classify_checkpoint_reply(text) == "reject", text


def test_classify_checkpoint_reply_falls_through_for_unrelated_message():
    assert classify_checkpoint_reply("how do I saturate sub bass?") == ""


def test_classify_checkpoint_reply_falls_through_for_a_long_reply():
    # Even if it starts with "yes", a long message is a new thought, not
    # a bare confirmation -- let it fall through to normal chat.
    long_reply = "yes but actually can you also check the low end on the bass track first"
    assert classify_checkpoint_reply(long_reply) == ""


def test_classify_checkpoint_reply_empty_text():
    assert classify_checkpoint_reply("") == ""
    assert classify_checkpoint_reply("   ") == ""
