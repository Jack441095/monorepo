"""FastAPI chat requests retain context and retire only their own older answers."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from kenn.core import answer_upgrades, chat_answer, chat_retrieval, session_memory
from kenn.core.assistant_profile_memory import AssistantProfileStore
from kenn.routes import chat_routes
from kenn.routes.fastapi_app import app


@pytest.fixture(autouse=True)
def isolated_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(session_memory, "CHATS_DIR", tmp_path)
    monkeypatch.setattr(session_memory, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_BUSY", threading.Lock())
    monkeypatch.setattr(answer_upgrades, "log_outcome", lambda *args: None)


@pytest.fixture
def engine_calls(monkeypatch):
    calls = []

    def answer(query, limit=4, history=None, **kwargs):
        calls.append({"question": query, "limit": limit, "history": history, **kwargs})
        return {"answer": "Use EQ to adjust the tonal balance.", "sources": []}

    # Keep the public answer function real: the route used to pass an unsupported keyword.
    monkeypatch.setattr(chat_answer, "_answer_payload", answer)
    return calls


def _completed_upgrade(session_id):
    turn = answer_upgrades.begin_turn(session_id)
    job = answer_upgrades.start(
        lambda: {"llm_enhanced": True, "answer": "Earlier advice"},
        session_id=session_id, turn_id=turn,
    )
    assert job is not None
    with answer_upgrades._BUSY:
        pass
    assert answer_upgrades.get(job, session_id=session_id)["status"] == "accepted"
    return job


def test_fastapi_ask_uses_the_public_answer_binding_with_all_request_context(engine_calls):
    history = [{"role": "user", "content": "The vocal feels dull."}]
    response = TestClient(app).post("/api/ask", json={
        "question": " How should I EQ this vocal? ",
        "session_id": " song-a ", "plugin_session_id": " plugin-a ", "limit": 3,
        "history": history,
        "session_context": {"mix_goal": "vocal clarity", "session_goal": "Keep the sibilance soft"},
    })
    assert response.status_code == 200
    result = response.json()
    call, = engine_calls
    assert call["question"] == "How should I EQ this vocal?"
    assert call["session_id"] == "song-a" and call["plugin_session_id"] == "plugin-a"
    assert call["limit"] == 3 and call["allow_llm"] is True
    assert call["history"][:-1] == history
    assert "Keep the sibilance soft" in call["history"][-1]["content"]
    assert call["correlation_id"] == result["correlation_id"]
    assert call["correlation_id"].startswith("req-")
    assert call["turn_id"] == result["turn_id"]
    assert result["envelope"]["result"]["session_id"] == "song-a"


@pytest.mark.parametrize("optional_context", [{}, {
    "session_id": None, "plugin_session_id": None, "limit": None,
    "history": None, "session_context": None,
}])
def test_fastapi_ask_treats_missing_and_null_optional_context_as_defaults(engine_calls, optional_context):
    response = TestClient(app).post("/api/ask", json={"question": "How does EQ work?", **optional_context})
    assert response.status_code == 200
    call, = engine_calls
    assert call["session_id"] == "" and call["plugin_session_id"] == ""
    assert call["limit"] == 5 and call["history"] == []


@pytest.mark.parametrize("payload, status", [({}, 422), ({"question": None}, 422), ({"question": "  "}, 400)])
def test_invalid_fastapi_questions_do_not_call_the_engine_or_expire_an_answer(engine_calls, payload, status):
    previous = _completed_upgrade("song-a")
    response = TestClient(app).post("/api/ask", json={**payload, "session_id": "song-a"})
    assert response.status_code == status
    assert engine_calls == []
    assert answer_upgrades.get(previous, session_id="song-a")["status"] == "accepted"


def test_a_fastapi_question_expires_only_the_same_chats_previous_upgrade(engine_calls):
    previous = _completed_upgrade("song-a")
    other = _completed_upgrade("song-b")
    response = TestClient(app).post("/api/ask", json={"question": "How does EQ work?", "session_id": "song-a"})
    assert response.status_code == 200
    assert answer_upgrades.get(previous, session_id="song-a") == {"status": "expired"}
    assert answer_upgrades.get(other, session_id="song-b")["status"] == "accepted"


@pytest.mark.parametrize("id_key", ["id", "session_id"])
def test_fastapi_clear_discards_a_late_answer_but_keeps_the_model_busy(id_key):
    entered, release = threading.Event(), threading.Event()
    other = _completed_upgrade("song-b")

    def write():
        entered.set()
        assert release.wait(5)
        return {"llm_enhanced": True, "answer": "Earlier advice"}

    turn = answer_upgrades.begin_turn("song-a")
    job = answer_upgrades.start(write, session_id="song-a", turn_id=turn)
    assert job is not None
    try:
        assert entered.wait(5)
        response = TestClient(app).post("/api/session/clear", json={id_key: " song-a "})
        assert response.status_code == 200
        assert answer_upgrades.get(job, session_id="song-a") == {"status": "expired"}
        assert answer_upgrades.get(other, session_id="song-b")["status"] == "accepted"
        assert answer_upgrades.start(lambda: {}, session_id="song-b") is None
    finally:
        release.set()
        with answer_upgrades._BUSY:
            pass
    assert answer_upgrades.get(job, session_id="song-a") == {"status": "expired"}


def test_route_preferences_and_memory_stay_in_the_requesting_project(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_answer, "_critique_and_save_trace", lambda **kwargs: None)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_retrieval, chat_answer):
        monkeypatch.setattr(module, "load_chunks", lambda: [])
        monkeypatch.setattr(module, "load_terms", lambda: terms)
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: [])
    store = AssistantProfileStore(tmp_path / "memory.db")
    store.record_preference(
        session_id="song-a", key="creative_direction", value="vocals bright",
        source_turn_id="preference", user_statement="I like my vocals bright",
    )
    history = [{"role": "user", "content": "The vocal feels dull."}]
    responses = {}
    for session_id in ("song-a", "song-b"):
        status, result = chat_routes.handle_ask({
            "question": "How should I EQ my vocal track?", "session_id": session_id,
            "history": history, "session_context": {"mix_goal": "vocal clarity"},
        }, request_id=f"test-{session_id}", allow_llm=False)
        assert status == 200
        responses[session_id] = result
        assert session_memory.load_session(session_id)["turn_count"] == 1
    assert responses["song-a"]["applied_preferences"][0]["value"] == "vocals bright"
    assert responses["song-b"]["applied_preferences"] == []
    assert history == [{"role": "user", "content": "The vocal feels dull."}]
