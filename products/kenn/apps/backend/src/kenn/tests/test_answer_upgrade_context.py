"""Background answers keep their chat context without becoming another user turn."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict, deque

import pytest

from kenn.core import answer_upgrades, chat_answer, chat_retrieval, session_memory
from kenn.core.assistant_profile_memory import AssistantProfileStore


def _wait(upgrade_id: str, session_id: str = "") -> dict:
    for _ in range(200):
        result = answer_upgrades.get(upgrade_id, session_id=session_id)
        if result["status"] != "pending":
            return result
        time.sleep(0.01)
    raise AssertionError("upgrade did not finish")


@pytest.fixture(autouse=True)
def isolated_jobs(monkeypatch):
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(answer_upgrades, "_TURNS", {}, raising=False)
    monkeypatch.setattr(answer_upgrades, "_BUSY", threading.Lock())
    monkeypatch.setattr(answer_upgrades, "log_outcome", lambda *args: None)


def test_an_upgrade_is_visible_only_in_its_originating_chat():
    upgrade_id = answer_upgrades.start(
        lambda: {"llm_enhanced": True, "answer": "Advice for song A"}, session_id="song-a"
    )
    assert _wait(upgrade_id, "song-a")["answer"] == "Advice for song A"
    assert answer_upgrades.get(upgrade_id, session_id="song-b") == {"status": "expired"}
    assert answer_upgrades.get(upgrade_id) == {"status": "expired"}


def test_a_new_turn_discards_a_late_answer_without_freeing_the_model_early():
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def write():
        entered.set()
        assert release.wait(2)
        finished.set()
        return {"llm_enhanced": True, "answer": "Old advice"}

    first_turn = answer_upgrades.begin_turn("song-a")
    first = answer_upgrades.start(write, session_id="song-a", turn_id=first_turn)
    assert entered.wait(2)
    try:
        answer_upgrades.begin_turn("song-b")
        assert answer_upgrades.get(first, session_id="song-a")["status"] == "pending"
        next_turn = answer_upgrades.begin_turn("song-a")
        assert answer_upgrades.get(first, session_id="song-a") == {"status": "expired"}
        assert answer_upgrades.start(lambda: {}, session_id="song-a", turn_id=next_turn) is None
    finally:
        release.set()
        with answer_upgrades._BUSY:
            pass
    assert finished.wait(2)
    assert answer_upgrades.get(first, session_id="song-a") == {"status": "expired"}


def test_an_older_foreground_request_cannot_start_a_job_after_the_next_turn():
    older = answer_upgrades.begin_turn("song-a")
    answer_upgrades.begin_turn("song-a")
    called = threading.Event()
    assert answer_upgrades.start(lambda: called.set(), session_id="song-a", turn_id=older) is None
    assert not called.is_set()


def test_turn_observation_rejects_cancelled_or_replaced_owners_only_in_their_chat():
    first = answer_upgrades.begin_turn("song-a")
    assert answer_upgrades.is_current_turn(session_id="song-a", turn_id=first)
    answer_upgrades.begin_turn("song-b")
    assert answer_upgrades.is_current_turn(session_id="song-a", turn_id=first)
    second = answer_upgrades.begin_turn("song-a")
    assert not answer_upgrades.is_current_turn(session_id="song-a", turn_id=first)
    assert answer_upgrades.is_current_turn(session_id="song-a", turn_id=second)
    answer_upgrades.invalidate("song-a")
    assert not answer_upgrades.is_current_turn(session_id="song-a", turn_id=second)


def test_a_bounded_write_finishes_before_cancel_and_cannot_run_again_after_cancel():
    # Owner validation and persistence share the turn lock; cancel waits for an already-started save.
    entered, release, cancelling, cancelled = (threading.Event() for _ in range(4))
    first = answer_upgrades.begin_turn("song-a")
    writes = []

    def save():
        assert answer_upgrades._LOCK.locked()
        entered.set()
        assert release.wait(2)
        writes.append("saved")

    def cancel():
        cancelling.set()
        answer_upgrades.invalidate("song-a")
        cancelled.set()

    writer = threading.Thread(target=lambda: answer_upgrades.write_if_current(save, session_id="song-a", turn_id=first))
    canceller = threading.Thread(target=cancel)
    writer.start()
    assert entered.wait(2)
    canceller.start()
    try:
        assert cancelling.wait(2)
        assert not cancelled.is_set()
    finally:
        release.set()
        writer.join(timeout=2)
        canceller.join(timeout=2)
    assert not writer.is_alive() and not canceller.is_alive()
    assert cancelled.is_set() and writes == ["saved"]
    assert not answer_upgrades.write_if_current(lambda: writes.append("late"), session_id="song-a", turn_id=first)
    assert writes == ["saved"]


def test_a_bounded_write_error_releases_the_owner_lock():
    first = answer_upgrades.begin_turn("song-a")

    def failed_save():
        raise OSError("Fixture persistence failed")

    with pytest.raises(OSError, match="Fixture persistence failed"):
        answer_upgrades.write_if_current(failed_save, session_id="song-a", turn_id=first)
    assert not answer_upgrades._LOCK.locked()
    assert answer_upgrades.is_current_turn(session_id="song-a", turn_id=first)


def test_expired_jobs_are_pruned_when_polled(monkeypatch):
    upgrade_id = answer_upgrades.start(lambda: {"llm_enhanced": True, "answer": "Advice"}, session_id="song-a")
    assert _wait(upgrade_id, "song-a")["status"] == "accepted"
    future = time.time() + answer_upgrades.KEEP_SECONDS + 1
    monkeypatch.setattr(answer_upgrades.time, "time", lambda: future)
    assert answer_upgrades.get(upgrade_id, session_id="song-a") == {"status": "expired"}


def test_current_turns_and_results_have_a_fixed_storage_bound():
    for number in range(answer_upgrades.MAX_KEPT + 5):
        session_id = f"song-{number}"
        turn = answer_upgrades.begin_turn(session_id)
        job = answer_upgrades.start(lambda: {"llm_enhanced": True, "answer": "Advice"}, session_id=session_id, turn_id=turn)
        assert _wait(job, session_id)["status"] == "accepted"
    assert len(answer_upgrades._TURNS) == answer_upgrades.MAX_KEPT
    assert len(answer_upgrades._RESULTS) == answer_upgrades.MAX_KEPT


def test_a_discarded_model_answer_counts_as_expired_instead_of_accepted(tmp_path, monkeypatch):
    from kenn.core import route_log

    entered, release, logged = threading.Event(), threading.Event(), threading.Event()
    log = tmp_path / "upgrades.jsonl"

    def record(outcome, milliseconds):
        route_log.record(f"answer_upgrade:{outcome}", milliseconds, brain=outcome == "accepted", proposal=False, path=log)
        logged.set()

    def write():
        entered.set()
        assert release.wait(2)
        return {"llm_enhanced": True, "answer": "Old advice"}

    monkeypatch.setattr(answer_upgrades, "log_outcome", record)
    answer_upgrades.start(write, session_id="song-a")
    assert entered.wait(2)
    answer_upgrades.invalidate("song-a")
    release.set()
    assert logged.wait(2)
    report = route_log.upgrade_summary(log)
    assert report["attempts"] == 1 and report["expired"] == 1
    assert report["accepted"] == 0 and report["accepted_rate"] == 0


def test_background_answer_reads_project_preferences_without_recording_a_second_turn(tmp_path, monkeypatch):
    # Dropping session_id avoided duplicate history but also dropped this project's preferences.
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
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
    question = "How should I EQ my vocal track?"
    chat_answer.answer_payload(question, session_id="song-a", allow_llm=False)
    before = session_memory.load_session("song-a")
    assert before["turn_count"] == 1
    answer = chat_answer.answer_payload(question, session_id="song-a", allow_llm=False, record_session=False)
    other = chat_answer.answer_payload(question, session_id="song-b", allow_llm=False, record_session=False)
    assert "vocals bright" in answer["answer"]
    assert answer["applied_preferences"][0]["value"] == "vocals bright"
    assert other["applied_preferences"] == []
    assert session_memory.load_session("song-a") == before
    assert session_memory.load_session("song-b")["turn_count"] == 0


def test_background_answer_does_not_use_or_populate_the_semantic_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(session_memory, "get_semantic_cache_hit", lambda *args, **kwargs: calls.append("read"))
    monkeypatch.setattr(session_memory, "save_to_semantic_cache", lambda *args, **kwargs: calls.append("write"))
    monkeypatch.setattr(chat_answer, "_short_circuit_evaluator", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_answer, "_answer_payload_raw", lambda *args, **kwargs: {"answer": "Model", "llm_enhanced": True})
    answer = chat_answer.answer_payload("How does EQ work?", session_id="song-a", record_session=False)
    assert answer["answer"] == "Model"
    assert calls == []


@pytest.fixture
def upgrade_http_server(monkeypatch, tmp_path):
    import kenn.server as server
    import kenn.server_rate_limit as rate_limit

    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "http-memory.db")
    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    monkeypatch.setattr(answer_upgrades, "enabled", lambda: True)
    monkeypatch.setattr(server, "live_context_summary", lambda *args: None)
    monkeypatch.setattr(server, "augment_payload", lambda result, **kwargs: result)
    for name in (
        "_maybe_handle_live_inspection", "_maybe_handle_midi_generation", "_maybe_handle_live_command_from_chat",
        "_maybe_handle_checkpoint_reply", "_maybe_run_explicit_tool_trigger", "_maybe_handle_project_analysis",
        "_maybe_handle_mix_revision",
    ):
        monkeypatch.setattr(server.Handler, name, lambda *args: None)
    monkeypatch.setattr(server.Handler, "_maybe_attach_checkpoint", lambda self, result, session_id: result)
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", server
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(2)


def _post(base: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def _poll(base: str, upgrade_id: str, session_id: str) -> dict:
    query = urllib.parse.urlencode({"id": upgrade_id, "session_id": session_id})
    with urllib.request.urlopen(f"{base}/api/ask/upgrade?{query}", timeout=5) as response:
        return json.load(response)


def test_http_background_answer_keeps_the_foreground_identifiers_and_history(upgrade_http_server, monkeypatch):
    base, server = upgrade_http_server
    calls = []

    def answer(question, **kwargs):
        calls.append(kwargs)
        return {"answer": "Template" if kwargs.get("allow_llm") is False else "Model", "llm_available": True,
                "llm_enhanced": kwargs.get("allow_llm") is not False, "sources": []}

    monkeypatch.setattr(server, "answer_payload", answer)
    result = _post(base, "/api/ask", {
        "question": "How do I EQ the vocal?", "session_id": "song-a", "plugin_session_id": "plugin-a",
        "correlation_id": "request-a", "history": [{"role": "user", "content": "My vocal is bright"}],
    })
    upgrade_id = result["answer_upgrade"]["id"]
    assert _wait(upgrade_id, "song-a")["answer"] == "Model"
    assert len(calls) == 2
    for call in calls:
        assert call["session_id"] == "song-a"
        assert call["plugin_session_id"] == "plugin-a"
        assert call["correlation_id"] == "request-a"
        assert call["history"] == [{"role": "user", "content": "My vocal is bright"}]
    assert calls[1]["record_session"] is False
    assert _poll(base, upgrade_id, "song-a")["status"] == "accepted"
    assert _poll(base, upgrade_id, "song-b") == {"status": "expired"}


def test_http_session_clear_discards_pending_and_late_answers(upgrade_http_server, monkeypatch):
    base, server = upgrade_http_server
    release, entered = threading.Event(), threading.Event()

    def answer(question, **kwargs):
        if kwargs.get("allow_llm") is not False:
            entered.set()
            assert release.wait(2)
        return {"answer": "Advice", "llm_available": True, "llm_enhanced": True, "sources": []}

    monkeypatch.setattr(server, "answer_payload", answer)
    result = _post(base, "/api/ask", {"question": "How do I EQ the vocal?", "session_id": "song-a"})
    upgrade_id = result["answer_upgrade"]["id"]
    assert entered.wait(2)
    try:
        assert _post(base, "/api/session/clear", {"id": "song-a"})["ok"] is True
        assert _poll(base, upgrade_id, "song-a") == {"status": "expired"}
    finally:
        release.set()
        with answer_upgrades._BUSY:
            pass
    assert _poll(base, upgrade_id, "song-a") == {"status": "expired"}


def test_http_proposals_do_not_start_a_second_background_dispatch(upgrade_http_server, monkeypatch):
    base, server = upgrade_http_server
    calls = []

    def answer(question, **kwargs):
        calls.append(kwargs)
        return {"answer": "Apply to proceed", "proposal": {"id": "p1"}, "llm_available": False}

    monkeypatch.setattr(server, "answer_payload", answer)
    result = _post(base, "/api/ask", {"question": "How do I EQ the vocal?", "session_id": "song-a"})
    assert "answer_upgrade" not in result
    assert len(calls) == 1
