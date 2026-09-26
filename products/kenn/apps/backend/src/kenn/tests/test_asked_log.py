"""What testers typed when KENN had to ask: kept locally, shared only when they tick the box."""

from __future__ import annotations

import stat

import pytest

from kenn.core import asked_log


@pytest.fixture(autouse=True)
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "asked_log.jsonl"
    monkeypatch.setenv("KENN_ASKED_LOG", str(path))
    return path


def test_only_what_kenn_asked_about_is_kept_with_the_reply_that_followed(log_path) -> None:
    assert not asked_log.record("s1", "mute the kick", {"status": "proposal_ready"}, now=100)
    assert asked_log.record("s1", "make the drums slap", {"status": "clarification_required",
                                                          "answer": "Which track?"}, now=200)
    asked_log.record("s1", "the drum bus, up 2 dB", {"status": "proposal_ready"}, now=230)
    [row] = asked_log.entries()
    assert row["said"] == "make the drums slap" and row["kenn_said"] == "Which track?"
    assert row["next_said"] == "the drum bus, up 2 dB" and row["next_status"] == "proposal_ready"
    assert "session" not in row
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


def test_a_message_much_later_or_in_another_session_is_not_the_reply() -> None:
    asked_log.record("s1", "make it slap", {"status": "clarification_required"}, now=100)
    asked_log.record("s2", "solo the bass", {"status": "proposal_ready"}, now=110)
    asked_log.record("s1", "play", {"status": "proposal_ready"}, now=100 + asked_log.REPLY_WINDOW_S + 1)
    assert asked_log.entries()[0]["next_said"] is None


def test_the_log_is_capped_and_can_be_cleared() -> None:
    for i in range(asked_log.MAX_ROWS + 20):
        asked_log.record(f"s{i}", f"thing {i}", {"status": "refused"}, now=i)
    kept = asked_log.entries()
    assert len(kept) == asked_log.MAX_ROWS and kept[-1]["said"] == f"thing {asked_log.MAX_ROWS + 19}"
    assert asked_log.clear() == asked_log.MAX_ROWS
    assert asked_log.entries() == []


def test_a_chat_reply_counts_as_asking_when_kenn_asked_back() -> None:
    orchestrated = {"route": "ableton_controller", "status": "succeeded",
                    "orchestration": {"result": {"status": "clarification_required"}}}
    assert asked_log.reply_status(orchestrated) == "clarification_required"
    assert asked_log.reply_status({"route": "clarify", "status": "succeeded"}) == "clarification_required"
    assert asked_log.reply_status({"route": "ableton_controller", "status": "succeeded",
                                   "orchestration": {"result": {"status": "proposal_ready"}}}) == "proposal_ready"
    assert asked_log.reply_status({"route": "production", "status": "succeeded"}) not in asked_log.ASKED_STATUSES


def test_diagnostics_leave_the_requests_out_unless_the_tester_ticks_the_box(tmp_path) -> None:
    from kenn.core.support_diagnostics import build_support_diagnostics

    asked_log.record("s1", "make it slap", {"status": "clarification_required"}, now=1)
    plain = build_support_diagnostics(repo_root=tmp_path)
    assert "asked_log" not in plain and "request_text" in plain["redactions"]["excluded_fields"]
    shared = build_support_diagnostics(repo_root=tmp_path, include_asked_log=True)
    assert shared["asked_log"][0]["said"] == "make it slap"
    assert shared["checks"]["asked_log_included"] is True
    assert "request_text" not in shared["redactions"]["excluded_fields"]


def test_the_same_message_tried_twice_is_one_request() -> None:
    # The chat route can run a message through the command path twice; that stored it twice, as its own reply.
    asked_log.record("s1", "pan the snare a bit", {"status": "clarification_required"}, now=100)
    asked_log.record("s1", "pan the snare a bit", {"status": "clarification_required"}, now=100.5)
    asked_log.record("s1", "20% left", {"status": "proposal_ready"}, now=120)
    [row] = asked_log.entries()
    assert row["next_said"] == "20% left"
