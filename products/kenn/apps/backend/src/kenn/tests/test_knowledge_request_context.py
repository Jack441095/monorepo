"""Read-only knowledge requests keep their context without changing another request's policy."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import defaultdict, deque
from types import SimpleNamespace

import pytest

from kenn.core import chat_answer, chat_retrieval, session_memory
from kenn.core.assistant_coordinator import AssistantCoordinator
from kenn.core.assistant_profile_memory import AssistantProfileStore
from kenn.core.assistant_task_memory import AssistantTaskStore
from kenn.core.mcp_facade import KennHTTPClient, KennMCPFacade


@pytest.fixture(autouse=True)
def isolated_knowledge(tmp_path, monkeypatch):
    import kenn.server as server

    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(session_memory, "CHATS_DIR", tmp_path)
    monkeypatch.setattr(session_memory, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(chat_answer, "_critique_and_save_trace", lambda **kwargs: None)
    monkeypatch.setattr(server, "_live_session_track_evidence", lambda *args: None)
    monkeypatch.setattr(server, "live_context_summary", lambda *args: None)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_retrieval, chat_answer):
        monkeypatch.setattr(module, "load_chunks", lambda: [])
        monkeypatch.setattr(module, "load_terms", lambda: terms)
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: [])


def test_a_paused_knowledge_request_does_not_replace_the_normal_chats_dispatcher(monkeypatch):
    import kenn.server as server

    entered, release = threading.Event(), threading.Event()
    knowledge_results, errors, dispatched = [], [], []

    def dispatch(query, **kwargs):
        dispatched.append(query)
        return {"message": "Normal specialist response", "agent_name": "fixture-specialist"}

    def chunks():
        if threading.current_thread().name == "knowledge-request":
            entered.set()
            assert release.wait(5)
        return []

    def knowledge():
        try:
            knowledge_results.append(server.grounded_knowledge_answer("How does EQ work?", "song-a"))
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(chat_answer, "get_orchestrator", lambda: SimpleNamespace(dispatch=dispatch))
    monkeypatch.setattr(chat_answer, "load_chunks", chunks)
    worker = threading.Thread(target=knowledge, name="knowledge-request")
    worker.start()
    try:
        assert entered.wait(5)
        answer = chat_answer.answer_payload("Explain compression", session_id="song-b", allow_llm=False)
        assert answer["route"] == "fixture-specialist"
        assert dispatched == ["Explain compression"]
    finally:
        release.set()
        worker.join(timeout=5)
    assert not worker.is_alive() and errors == []
    assert knowledge_results[0]["route"] == "production"


@pytest.mark.parametrize("question", ["play", "stop", "remember that I like my vocals bright", "clear memory"])
def test_knowledge_requests_cannot_create_transport_proposals_or_change_preferences(question, monkeypatch):
    import kenn.server as server
    from kenn.core import live_action_service

    proposals = []

    def propose(action, **kwargs):
        proposals.append(action)
        return {"ok": True, "proposal": {"kind": "transport"}, "confirmation_token": "fixture"}

    monkeypatch.setattr(live_action_service, "LiveActionService", lambda: SimpleNamespace(propose_transport_action=propose))
    store = AssistantProfileStore()
    store.record_preference(
        session_id="song-a", key="creative_direction", value="warm and vintage",
        source_turn_id="preference", user_statement="I prefer warm and vintage",
    )
    before = store.current_preferences("song-a")
    result = server.grounded_knowledge_answer(question, "song-a")
    assert proposals == []
    assert "proposal" not in result and not result.get("requires_confirmation")
    assert result["route"] == "production"
    assert store.current_preferences("song-a") == before


def test_knowledge_reads_only_the_named_projects_preferences_without_recording_a_chat_turn():
    import kenn.server as server

    store = AssistantProfileStore()
    store.record_preference(
        session_id="song-a", key="creative_direction", value="vocals bright",
        source_turn_id="preference", user_statement="I like my vocals bright",
    )
    before = {}
    for session_id in ("song-a", "song-b"):
        state = session_memory.load_session(session_id)
        state["turn_count"] = 2
        state["last_question"] = "Earlier question"
        session_memory.save_session(state)
        before[session_id] = session_memory.load_session(session_id)
    first = server.grounded_knowledge_answer("How should I EQ my vocal track?", "song-a")
    second = server.grounded_knowledge_answer("How should I EQ my vocal track?", "song-b")
    assert first["applied_preferences"][0]["value"] == "vocals bright"
    assert second["applied_preferences"] == []
    for session_id, state in before.items():
        assert session_memory.load_session(session_id) == state
    with sqlite3.connect(session_memory.DB_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2


def test_retrieval_only_policy_disables_model_memory_cache_and_shortcuts_even_when_requested(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only knowledge reached a mutable or model shortcut")

    def raw(*args, **kwargs):
        calls.append(kwargs)
        return {"answer": "Retrieved answer", "llm_enhanced": True}

    monkeypatch.setattr(chat_answer, "_short_circuit_evaluator", forbidden)
    monkeypatch.setattr(session_memory, "get_semantic_cache_hit", forbidden)
    monkeypatch.setattr(session_memory, "save_to_semantic_cache", forbidden)
    monkeypatch.setattr(chat_answer, "_answer_payload_raw", raw)
    result = chat_answer.answer_payload(
        "Explain EQ", session_id="song-a", retrieval_only=True,
        allow_llm=True, record_session=True,
    )
    assert result["answer"] == "Retrieved answer"
    call, = calls
    assert call["retrieval_only"] is True
    assert call["allow_llm"] is False and call["record_session"] is False


def test_knowledge_helper_preserves_context_through_the_real_public_engine(monkeypatch):
    import kenn.server as server

    calls = []

    def raw(*args, **kwargs):
        calls.append(kwargs)
        return {"answer": "Retrieved answer"}

    monkeypatch.setattr(chat_answer, "_answer_payload_raw", raw)
    server.grounded_knowledge_answer(
        "Explain EQ", "song-a", "plugin-a", correlation_id="request-a",
    )
    call, = calls
    assert call["session_id"] == "song-a"
    assert call["plugin_session_id"] == "plugin-a"
    assert call["correlation_id"] == "request-a"
    assert call["retrieval_only"] is True
    assert call["allow_llm"] is False and call["record_session"] is False


@pytest.mark.parametrize("hook", [
    "get_orchestrator", "audio_generation_payload", "mix_review_timeline_lookup",
    "latest_track_memory_lookup", "mix_review_followup_payload", "route_query",
])
def test_retrieval_only_policy_never_calls_a_specialist_hook(hook, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError(f"Read-only knowledge called {hook}")

    monkeypatch.setattr(chat_answer, hook, forbidden)
    result = chat_answer.answer_payload("Why is my vocal dull?", session_id="song-a", retrieval_only=True)
    assert result["route"] == "production"
    assert result["llm_enhanced"] is False
    assert session_memory.load_session("song-a")["turn_count"] == 0


def test_retrieval_only_can_preserve_ableton_knowledge_without_specialist_dispatch(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Ableton knowledge reached a specialist")

    monkeypatch.setattr(chat_answer, "get_orchestrator", forbidden)
    result = chat_answer.answer_payload(
        "How do I use EQ Eight in Ableton Live?", session_id="song-a",
        retrieval_only=True, retrieval_route="ableton",
    )
    assert result["route"] == "ableton" and result["llm_enhanced"] is False
    assert session_memory.load_session("song-a")["turn_count"] == 0


def test_retrieval_only_rejects_a_specialist_route_before_running_the_engine(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("An invalid retrieval route reached the engine")

    monkeypatch.setattr(chat_answer, "_answer_payload_raw", forbidden)
    with pytest.raises(ValueError, match="production or Ableton knowledge"):
        chat_answer.answer_payload("Explain EQ", retrieval_only=True, retrieval_route="mix_review")


@pytest.fixture
def knowledge_http(monkeypatch):
    import kenn.server as server
    import kenn.server_rate_limit as rate_limit

    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield KennHTTPClient(f"http://127.0.0.1:{httpd.server_port}")
    finally:
        httpd.shutdown()
        worker.join(timeout=5)
        httpd.server_close()


def test_mcp_to_real_http_route_preserves_mix_review_and_all_context_identifiers(knowledge_http, tmp_path, monkeypatch):
    import kenn.server as server

    calls = []

    def raw(question, limit, history, **kwargs):
        calls.append({"question": question, "history": history, **kwargs})
        return {"answer": "Measured review context"}

    def stored_review(review_id):
        assert review_id == "review-a"
        return {"status": "completed", "review": {"metrics": {"integrated_lufs": -14.0}}}

    monkeypatch.setattr(chat_answer, "_answer_payload_raw", raw)
    monkeypatch.setattr(server, "mix_review", SimpleNamespace(mix_review_status=stored_review))
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "tasks.db"))
    facade = KennMCPFacade(knowledge_http, coordinator)
    response = facade.handle_message({
        "jsonrpc": "2.0", "id": 17, "method": "tools/call",
        "params": {"name": "ask_audio_engineering_question", "arguments": {
            "question": "How does this uploaded mix compare?", "session_id": " song-a ",
            "plugin_session_id": " plugin-a ", "mix_review_id": " review-a ",
        }},
    })
    result = json.loads(response["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["mix_review_evidence"]["review_id"] == "review-a"
    call, = calls
    assert call["session_id"] == "song-a" and call["plugin_session_id"] == "plugin-a"
    assert call["correlation_id"] and call["retrieval_only"] is True
    context = json.loads(call["history"][0]["content"].split(":", 1)[1])
    assert context["source"] == "mix_review_upload"
    assert context["facts"][0]["name"] == "integrated_lufs"
    assert context["facts"][0]["value"] == -14.0


def test_null_optional_knowledge_http_identifiers_are_empty(knowledge_http, monkeypatch):
    calls = []

    def raw(*args, **kwargs):
        calls.append(kwargs)
        return {"answer": "Retrieved answer"}

    monkeypatch.setattr(chat_answer, "_answer_payload_raw", raw)
    result = knowledge_http.post("/api/knowledge/ask", {
        "question": "Explain EQ", "session_id": None,
        "plugin_session_id": None, "mix_review_id": None,
    })
    assert result["ok"] is True
    assert "mix_review_evidence" not in result
    call, = calls
    assert call["session_id"] == "" and call["plugin_session_id"] == ""


@pytest.mark.parametrize("question", [None, "  "])
def test_invalid_knowledge_http_questions_do_not_call_the_engine(knowledge_http, question, monkeypatch):
    import kenn.server as server

    calls = []
    monkeypatch.setattr(server, "grounded_knowledge_answer", lambda *args, **kwargs: calls.append(args) or {})
    result = knowledge_http.post("/api/knowledge/ask", {"question": question})
    assert result["http_status"] == 400
    assert calls == []
