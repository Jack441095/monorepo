"""The FastAPI feedback route used to say "Feedback recorded." for any rating and store nothing.

The stdlib server stores through demo_feedback and answers 503 when that module is missing, which is the case in
this tree. Both entry points now share one function, so neither can claim a rating it did not keep.
"""

from __future__ import annotations

import pytest

from kenn.routes import chat_routes, feedback_handler


class _Handler:
    def __init__(self):
        self.sent = None

    def send_json(self, status, body):
        self.sent = (status, body)


class _Store:
    def __init__(self):
        self.rows = []

    def record_feedback(self, payload):
        self.rows.append(dict(payload))
        return {"id": len(self.rows), "rating": payload["rating"], "channel": payload["channel"]}


@pytest.fixture
def store(monkeypatch):
    fake = _Store()
    monkeypatch.setattr(feedback_handler, "demo_feedback", fake)
    return fake


def test_fastapi_feedback_is_unavailable_when_nothing_can_store_it(monkeypatch):
    monkeypatch.setattr(feedback_handler, "demo_feedback", None)
    status, body = chat_routes.handle_feedback({"message_id": "m1", "rating": "useful"})
    assert status == 503 and "ok" not in body


@pytest.mark.parametrize("rating", ["great", "", 5, None])
def test_fastapi_feedback_rejects_a_rating_the_store_does_not_know(store, rating):
    status, _ = chat_routes.handle_feedback({"message_id": "m1", "rating": rating})
    assert status == 400 and store.rows == []


def test_fastapi_feedback_is_stored_and_returns_the_stored_row(store):
    status, body = chat_routes.handle_feedback({"message_id": "m1", "rating": "Not_Useful", "kind": "mix_review"})
    assert status == 201 and body["feedback"]["channel"] == "mix_review"
    assert len(store.rows) == 1


@pytest.mark.parametrize("payload", [
    {"rating": "useful"},
    {"rating": "maybe"},
    {"rating": "useful", "kind": "mix_review"},
])
def test_the_stdlib_server_and_fastapi_give_the_same_answer(store, payload):
    handler = _Handler()
    feedback_handler.handle_feedback(handler, dict(payload))
    store.rows.clear()
    assert handler.sent == chat_routes.handle_feedback(dict(payload))
