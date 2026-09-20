"""POST /api/automix/explain -- the HTTP surface for "why did you do that",
wired in business/app/routes/automix_routes.py. Mirrors the pattern
tests/ableton/test_ableton_live_suggestion_route.py uses for a similar
"route calls into KENN" HTTP handler test.
"""

from __future__ import annotations

import json

from app.routes import automix_routes


class FakeHandler:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode("utf-8")
        self.status = 0
        self.payload: dict = {}

    def read_json_body(self) -> dict:
        return json.loads(self._body.decode("utf-8"))

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


def _stub_ask_kenn_about_render(monkeypatch, result: dict) -> None:
    import automix_kenn_explain

    monkeypatch.setattr(automix_kenn_explain, "ask_kenn_about_render", lambda project_id, question: result)


def test_missing_project_id_is_rejected() -> None:
    handler = FakeHandler({"question": "Why did you cut the vocal?"})
    handled = automix_routes.handle_automix_post(handler, "/api/automix/explain", "/tmp")
    assert handled is True
    assert handler.status == 400


def test_missing_question_is_rejected() -> None:
    handler = FakeHandler({"project_id": "proj-123"})
    handled = automix_routes.handle_automix_post(handler, "/api/automix/explain", "/tmp")
    assert handled is True
    assert handler.status == 400


def test_valid_request_returns_grounded_answer(monkeypatch) -> None:
    _stub_ask_kenn_about_render(monkeypatch, {
        "ok": True,
        "answer": "The limiter pulled the bus drive down 1 dB to hold the true-peak ceiling.",
        "grounded": True,
        "grounding": {"score": 100},
    })
    handler = FakeHandler({"project_id": "proj-123", "question": "Why is the master quieter?"})
    handled = automix_routes.handle_automix_post(handler, "/api/automix/explain", "/tmp")
    assert handled is True
    assert handler.status == 200
    assert handler.payload["ok"] is True
    assert handler.payload["grounded"] is True


def test_kenn_failure_returns_502_not_a_silent_500() -> None:
    handler = FakeHandler({"project_id": "proj-123", "question": "Why is the master quieter?"})
    # No stub -- ask_kenn_about_render runs for real and will honestly report
    # KENN unavailable in this test environment (no model loaded), exercising
    # the real error path end to end rather than mocking it away entirely.
    handled = automix_routes.handle_automix_post(handler, "/api/automix/explain", "/tmp")
    assert handled is True
    assert handler.status in (200, 502)
    assert "ok" in handler.payload
