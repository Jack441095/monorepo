"""Tests for demo feedback and tester analytics."""

from __future__ import annotations

import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))

import ableton_bridge  # noqa: E402
import db  # noqa: E402
import demo_auth  # noqa: E402
import demo_feedback  # noqa: E402
import demo_routes  # noqa: E402
import enquiry_guard  # noqa: E402


def test_demo_question_analytics_records_session(tmp_path, monkeypatch) -> None:
    # Isolate from the real production DB — this test used to write straight
    # into data/audio_too.db on every run, which is how demo_feedback ended up
    # dominated by synthetic test rows (docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md).
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "isolated_feedback.db")
    payload = {
        "confidence": "low",
        "source_quality": "low",
        "sources": [{"label": "Test source"}],
        "answer": "Short answer",
    }
    row = demo_feedback.record_question("session-test", "test weak question", payload)
    assert row["session_id"] == "session-test"
    data = demo_feedback.analytics(limit=25)
    assert data["total_recent_questions"] >= 1
    assert data["low_confidence"] >= 1
    assert any(item["session_id"] == "session-test" for item in data["sessions"])


def test_demo_feedback_records_source_quality(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "isolated_feedback.db")
    row = demo_feedback.record_feedback(
        {
            "question": "test feedback question",
            "rating": "not_useful",
            "comment": "Needs a better note",
            "answer": "Wrong answer preview",
            "sources": [{"label": "Weak source"}],
            "topics": ["mixing"],
            "confidence": "medium",
            "source_quality": "low",
            "session_id": "session-feedback",
            "channel": "dashboard",
        }
    )
    assert row["source_quality"] == "low"
    assert row["session_id"] == "session-feedback"
    assert row["channel"] == "dashboard"
    assert row["answer"] == "Wrong answer preview"
    items = demo_feedback.list_feedback(limit=10)
    saved = next(item for item in items if item["id"] == row["id"])
    assert saved["sources"][0]["label"] == "Weak source"
    assert saved["topics"] == ["mixing"]
    assert saved["top_source"] == "Weak source"
    assert demo_feedback.mark_repair_status(row["id"], "drafted", note_file="test-note.md") is True
    updated = demo_feedback.get_feedback(row["id"])
    assert updated is not None
    assert updated["repair_status"] == "drafted"
    assert updated["repair_note"] == "test-note.md"
    assert demo_feedback.mark_repair_result(
        row["id"],
        "needs_review",
        {"answer": "Retest answer", "sources": [{"label": "Retest source"}]},
    ) is True
    retested = demo_feedback.get_feedback(row["id"])
    assert retested is not None
    assert retested["repair_status"] == "needs_review"
    assert retested["repair_last_answer"] == "Retest answer"
    assert retested["repair_last_sources"][0]["label"] == "Retest source"


class _FakeHandler:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.headers = {"Cookie": "demo_session=fake-token"}
        self.status = 0
        self.response: dict = {}

    def read_json_body(self) -> dict:
        return self.payload

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.response = payload


def _authorize_demo(monkeypatch) -> None:
    monkeypatch.setattr(demo_auth, "cookie_value", lambda _cookie: "fake-token")
    monkeypatch.setattr(demo_auth, "verify_demo_token", lambda _token: True)
    monkeypatch.setattr(demo_auth, "demo_session_id", lambda _token: "demo-sess-1")


def test_demo_ask_route_does_not_crash_on_session_id_shadowing(monkeypatch) -> None:
    """Regression test: /api/demo/ask used to shadow the module-level
    session_id(handler) function with a local `session_id` string, so the
    demo_feedback.record_question(session_id(handler), ...) call raised
    TypeError: 'str' object is not callable on every single request."""
    _authorize_demo(monkeypatch)
    monkeypatch.setattr(
        ableton_bridge,
        "ask",
        lambda *_args, **_kwargs: {"answer": "Try a low shelf.", "sources": [], "confidence": "medium"},
    )
    recorded = {}
    monkeypatch.setattr(
        demo_feedback,
        "record_question",
        lambda session_id, question, result: recorded.update(session_id=session_id, question=question),
    )

    handler = _FakeHandler({"question": "how do I EQ a kick drum"})
    handled = demo_routes.handle_post(handler, "/api/demo/ask", log_event=lambda *_a: None)

    assert handled is True
    assert handler.status == 200
    assert recorded["session_id"] == "demo-sess-1"
    assert recorded["question"] == "how do I EQ a kick drum"


def test_demo_feedback_route_does_not_crash_on_session_id_shadowing(tmp_path, monkeypatch) -> None:
    """Regression test: /api/demo/feedback raised UnboundLocalError on every
    call because an earlier branch's local `session_id = str(...)` shadowed
    the module-level session_id(handler) function for the whole function
    scope, and this branch never assigned it before calling it."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "isolated_feedback.db")
    _authorize_demo(monkeypatch)

    handler = _FakeHandler({"rating": "useful", "question": "how do I EQ a kick drum"})
    handled = demo_routes.handle_post(handler, "/api/demo/feedback", log_event=lambda *_a: None)

    assert handled is True
    assert handler.status == 201
    assert handler.response.get("ok") is True


def test_demo_login_has_brute_force_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr(enquiry_guard, "is_rate_limited", lambda *_a, **_kw: True)
    handler = _FakeHandler({"password": "guess"})

    handled = demo_routes.handle_post(handler, "/api/demo/login", log_event=lambda *_a: None)

    assert handled is True
    assert handler.status == 429
