"""Bound streaming consumers must retain the engine's final answer and scope."""

import io
import json
import threading
from collections import defaultdict, deque
from types import SimpleNamespace
from urllib.request import Request, urlopen

import pytest

from kenn.core import answer_upgrades, chat_answer, chat_cli, session_memory


@pytest.fixture(autouse=True)
def isolated_stream_turns(monkeypatch):
    from kenn.core import project_memory_advisory

    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(project_memory_advisory, "evaluate_memory_chat_intent", lambda *args, **kwargs: None)


@pytest.fixture
def stream_http(monkeypatch):
    import kenn.server as server
    import kenn.server_rate_limit as rate_limit

    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(server, "live_context_summary", lambda *args: None)
    monkeypatch.setattr(server, "demo_feedback", None)
    monkeypatch.setattr(server.Handler, "_maybe_attach_checkpoint", lambda self, payload, session: payload)
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()

    def post(path, payload):
        request = Request(
            f"http://127.0.0.1:{httpd.server_port}{path}",
            data=json.dumps({"question": "Explain compressor release", "stream": True, **payload}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            assert response.headers["Content-Type"] == "text/event-stream"
            return [json.loads(line[6:]) for line in response.read().decode().splitlines() if line.startswith("data: ")]

    try:
        yield post
    finally:
        httpd.shutdown()
        worker.join(timeout=5)
        httpd.server_close()


@pytest.mark.parametrize("path", ["/api/ask", "/kenn/api/ask"])
@pytest.mark.parametrize("validation_warning", ["insufficient evidence overlap", "generation stream cut short"])
def test_http_stream_keeps_final_grounded_replacement_after_a_rejected_draft(stream_http, monkeypatch, path, validation_warning):
    import kenn.server as server

    # Completion metadata corrects already-emitted text; the HTTP adapter discarded that correction.
    def engine(*args, **kwargs):
        yield {"event": "token", "token": "Provisional draft that was rejected."}
        yield {"event": "metadata", "data": {
            "answer": "Grounded replacement from the evidence.",
            "route": "production", "confidence": "high", "llm_enhanced": False,
            "generation_validation": {"accepted": False, "warnings": [validation_warning]},
        }}

    monkeypatch.setattr(server, "answer_payload_stream", engine)
    events = stream_http(path, {"session_id": "song-a"})
    final = [event["data"] for event in events if event["event"] == "metadata"][-1]
    assert final["generation_validation"]["accepted"] is False
    assert final["answer"] == "Grounded replacement from the evidence."
    assert events[-1]["event"] == "done"


@pytest.mark.parametrize("path", ["/api/ask", "/kenn/api/ask"])
def test_http_stream_forwards_chat_plugin_history_and_original_correlation(stream_http, monkeypatch, path):
    import kenn.server as server

    calls = []

    def engine(query, **kwargs):
        calls.append({"query": query, **kwargs})
        yield {"event": "metadata", "data": {"answer": "Scoped answer", "route": "production"}}
        yield {"event": "token", "token": "Scoped answer"}

    monkeypatch.setattr(server, "answer_payload_stream", engine)
    history = [{"role": "user", "content": "Use this chat's drum bus context"}]
    events = stream_http(path, {
        "session_id": " song-a ", "plugin_session_id": " plugin-a ",
        "correlation_id": "correlation-fixture", "history": history,
    })
    call, = calls
    assert call["session_id"] == "song-a" and call["plugin_session_id"] == "plugin-a"
    assert call["history"] == history and call["correlation_id"] == "correlation-fixture"
    assert call["request_turn_id"] == answer_upgrades._TURNS["song-a"]["id"]
    final = [event["data"] for event in events if event["event"] == "metadata"][-1]
    assert final["correlation_id"] == "correlation-fixture"


@pytest.mark.parametrize("companion_online", [True, False])
def test_cli_stream_returns_final_grounded_metadata_instead_of_rejected_tokens(monkeypatch, companion_online, capsys):
    events = [
        {"event": "token", "token": "Rejected provisional draft"},
        {"event": "metadata", "data": {"answer": "Grounded replacement", "llm_enhanced": False}},
        {"event": "done"},
    ]
    if companion_online:
        class Response(io.BytesIO):
            status = 200

        encoded = "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode()
        monkeypatch.setattr(chat_cli.urllib.request, "urlopen", lambda *args, **kwargs: Response(encoded))
    else:
        def offline(*args, **kwargs):
            raise OSError("Companion fixture is offline")

        monkeypatch.setattr(chat_cli.urllib.request, "urlopen", offline)
        monkeypatch.setattr(chat_cli, "answer_payload_stream", lambda *args, **kwargs: iter(events))
    answer, metadata = chat_cli._stream_query("Explain compressor release", session_id="song-a")
    assert metadata["answer"] == "Grounded replacement"
    assert answer == metadata["answer"]


@pytest.mark.parametrize("query", ["status", "cancel", "play", "stop"])
def test_public_stream_runs_status_cancel_and_transport_before_retrieval_or_cache(monkeypatch, query):
    calls = []

    def short_circuit(question, history=None, session_id=""):
        calls.append((question, session_id))
        return {"answer": "Handled scoped request", "route": "ableton", "requires_confirmation": False}

    def forbidden(*args, **kwargs):
        raise AssertionError("A short command reached retrieval or a cached conversational answer")

    monkeypatch.setattr(chat_answer, "_short_circuit_evaluator", short_circuit)
    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", forbidden)
    monkeypatch.setattr(session_memory, "get_semantic_cache_hit", forbidden)
    monkeypatch.setattr(session_memory, "save_to_semantic_cache", forbidden)
    events = list(chat_answer.answer_payload_stream(query, session_id="song-a"))
    assert calls == [(query, "song-a")]
    assert [event["data"]["answer"] for event in events if event["event"] == "metadata"][-1] == "Handled scoped request"


@pytest.fixture
def isolated_stream_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(session_memory, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(session_memory, "_L1_EXACT_CACHE", {})
    monkeypatch.setattr(session_memory, "_L2_MATRIX", None)
    for name in ("_L2_QUERIES", "_L2_SESSION_IDS", "_L2_VERSIONS", "_L2_EVENTS", "_L2_TIMESTAMPS"):
        monkeypatch.setattr(session_memory, name, [])
    from kenn.retrieval import retrieval
    monkeypatch.setattr(retrieval, "embed_text", lambda *args: None)


def test_stream_does_not_reuse_one_plugin_sessions_answer_for_another(isolated_stream_cache, monkeypatch):
    calls = []

    def engine(query, *args, plugin_session_id="", **kwargs):
        calls.append(plugin_session_id)
        answer = f"Evidence from {plugin_session_id}"
        yield {"event": "metadata", "data": {"answer": answer, "confidence": "high"}}
        yield {"event": "token", "token": answer}

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", engine)
    list(chat_answer.answer_payload_stream("Explain compressor release", session_id="song-a", plugin_session_id="plugin-a"))
    events = list(chat_answer.answer_payload_stream("Explain compressor release", session_id="song-a", plugin_session_id="plugin-b"))
    answer = [event["data"]["answer"] for event in events if event["event"] == "metadata"][-1]
    assert answer == "Evidence from plugin-b"
    assert calls == ["plugin-a", "plugin-b"]


@pytest.mark.parametrize("path", ["/api/ask", "/kenn/api/ask"])
@pytest.mark.parametrize("query", ["play", "stop"])
def test_http_transport_stream_keeps_the_actual_confirmation_proposal(stream_http, monkeypatch, path, query):
    from kenn.core import confirmation, live_action_service
    from kenn.core.fake_live import FakeLiveBackend

    fake = FakeLiveBackend()
    monkeypatch.setattr(live_action_service, "live_client", fake)
    monkeypatch.setattr(live_action_service, "_PROPOSALS_BY_TOKEN", {})
    monkeypatch.setattr(confirmation, "_ISSUED_TOKENS", {})
    monkeypatch.setattr(confirmation, "_REVOKED_TOKENS", set())
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())

    def forbidden(*args, **kwargs):
        raise AssertionError("Transport shortcuts must not reach knowledge generation or cache")

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", forbidden)
    monkeypatch.setattr(session_memory, "get_semantic_cache_hit", forbidden)
    events = stream_http(path, {"question": query, "session_id": "song-a"})
    final = [event["data"] for event in events if event["event"] == "metadata"][-1]
    assert final["requires_confirmation"] is True
    assert final["proposal"]["action"] == f"transport_{query}"
    assert final["confirmation_token"] == final["proposal"]["confirmation_token"]
    assert final["confirmation_token"]
    assert fake.writes == []
    assert events[-1]["event"] == "done"


@pytest.fixture
def measured_note_stream(monkeypatch, isolated_stream_cache):
    from kenn.tests.test_streamed_generation_prefix_guard import CHUNKS, TERMS

    monkeypatch.setattr(chat_answer, "get_orchestrator", lambda: SimpleNamespace(dispatch=lambda *args, **kwargs: None))
    monkeypatch.setattr(chat_answer, "load_chunks", lambda: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "load_terms", lambda: TERMS)
    monkeypatch.setattr(chat_answer, "search", lambda *args, **kwargs: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "_critique_and_save_trace", lambda **kwargs: kwargs["confidence"])
    monkeypatch.setattr(chat_answer, "_get_llm_usage_stats", lambda: {})
    monkeypatch.setattr(chat_answer, "llm_enabled", lambda: False)


def test_http_stream_preserves_the_real_engines_low_overlap_replacement(stream_http, measured_note_stream, monkeypatch):
    from kenn.tests.test_streamed_generation_prefix_guard import LOW_OVERLAP_ANSWER, QUERY, _word_tokens

    monkeypatch.setattr(chat_answer, "llm_enabled", lambda: True)
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *args, **kwargs: True)
    def model_stream(*args, **kwargs):
        for token in _word_tokens(LOW_OVERLAP_ANSWER):
            yield {"event": "token", "token": token}

    monkeypatch.setattr(chat_answer, "llm_enhance_answer_stream", model_stream)
    events = stream_http("/api/ask", {"question": QUERY, "session_id": "song-a"})
    final = [event["data"] for event in events if event["event"] == "metadata"][-1]
    streamed = "".join(event["token"] for event in events if event["event"] == "token")
    assert final["generation_validation"]["accepted"] is False
    assert "generated answer has insufficient evidence overlap" in final["generation_validation"]["warnings"]
    assert streamed == LOW_OVERLAP_ANSWER
    assert final["answer"] != streamed
    assert "150 ms" in final["answer"] and "microdynamics" not in final["answer"]
    assert session_memory.load_session("song-a")["last_answer"] == final["answer"][:1000]


@pytest.mark.parametrize("supersede", ["cancel", "next-turn", "other-chat"])
def test_completed_raw_stream_writes_memory_only_for_its_current_turn(measured_note_stream, monkeypatch, supersede):
    from kenn.tests.test_streamed_generation_prefix_guard import QUERY

    writes = []
    monkeypatch.setattr(chat_answer, "_update_session", lambda *args, **kwargs: writes.append(kwargs["session_id"]))
    owner = answer_upgrades.begin_turn("song-a")
    stream = chat_answer._answer_payload_stream_raw(QUERY, session_id="song-a", request_turn_id=owner)
    for event in stream:
        if event["event"] == "metadata" and event["data"].get("answer"):
            break
    if supersede == "cancel":
        answer_upgrades.invalidate("song-a")
    else:
        answer_upgrades.begin_turn("song-b" if supersede == "other-chat" else "song-a")
    list(stream)
    assert writes == (["song-a"] if supersede == "other-chat" else [])


@pytest.mark.parametrize("supersede", ["cancel", "next-turn", "other-chat"])
def test_public_stream_does_not_cache_a_superseded_turn(isolated_stream_cache, monkeypatch, supersede):
    def engine(*args, **kwargs):
        yield {"event": "token", "token": "Measured advice"}
        yield {"event": "metadata", "data": {"answer": "Measured advice", "confidence": "high"}}

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", engine)
    stream = chat_answer.answer_payload_stream("Explain compressor release", session_id="song-a")
    assert next(stream)["event"] == "token"
    if supersede == "cancel":
        answer_upgrades.invalidate("song-a")
    else:
        answer_upgrades.begin_turn("song-b" if supersede == "other-chat" else "song-a")
    remaining = list(stream)
    cache_hit = session_memory.get_semantic_cache_hit("Explain compressor release", session_id="song-a")
    if supersede == "other-chat":
        assert cache_hit and remaining[-1]["data"]["answer"] == "Measured advice"
    else:
        assert cache_hit is None
        final, = remaining
        assert final["data"]["answer"] == "" and final["data"]["answer_delivery_discarded"] is True


def test_plain_chat_stream_cache_stays_scoped_and_does_not_mutate_prior_turn_metadata(isolated_stream_cache, monkeypatch):
    calls = []

    def engine(*args, session_id="", **kwargs):
        calls.append(session_id)
        yield {"event": "metadata", "data": {"answer": f"Evidence for {session_id}", "confidence": "high"}}
        yield {"event": "token", "token": f"Evidence for {session_id}"}

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", engine)
    first = list(chat_answer.answer_payload_stream("Explain compressor release", session_id="song-a", correlation_id="first-correlation"))
    original = dict(first[0]["data"])
    second = list(chat_answer.answer_payload_stream("Explain compressor release", session_id="song-a", correlation_id="second-correlation"))
    other = list(chat_answer.answer_payload_stream("Explain compressor release", session_id="song-b"))
    assert calls == ["song-a", "song-b"]
    assert second[0]["data"]["semantic_cache_hit"] is True
    assert second[0]["data"]["turn_id"] != original["turn_id"]
    assert second[0]["data"]["correlation_id"] == "second-correlation"
    assert second[0]["data"]["session_id"] == "song-a" and second[0]["data"]["plugin_session_id"] == ""
    assert original["correlation_id"] == "first-correlation"
    assert first[0]["data"] == original
    assert other[0]["data"]["answer"] == "Evidence for song-b"


@pytest.mark.parametrize("session_id", ["", None, 7, "x" * 129])
def test_unbound_http_stream_does_not_replace_an_anonymous_pending_owner(stream_http, monkeypatch, session_id):
    import kenn.server as server

    owner = answer_upgrades.begin_turn("")
    monkeypatch.setattr(server, "answer_payload_stream", lambda *args, **kwargs: iter([
        {"event": "metadata", "data": {"answer": "Unbound answer", "route": "production"}},
    ]))
    stream_http("/api/ask", {"session_id": session_id})
    assert answer_upgrades._TURNS[""]["id"] == owner


@pytest.mark.parametrize("session_id", ["", None, 7, "x" * 129])
def test_unbound_public_stream_does_not_replace_an_anonymous_pending_owner(monkeypatch, session_id):
    owner = answer_upgrades.begin_turn("")
    calls = []

    def handled(query, history=None, session_id=""):
        calls.append(session_id)
        return {"answer": "Unbound status", "route": "conversation"}

    monkeypatch.setattr(chat_answer, "_short_circuit_evaluator", handled)
    list(chat_answer.answer_payload_stream("status", session_id=session_id))
    assert calls == [""]
    assert answer_upgrades._TURNS[""]["id"] == owner


@pytest.mark.parametrize("has_final_answer", [True, False])
def test_http_stream_uses_tokens_only_when_final_metadata_has_no_answer(stream_http, monkeypatch, has_final_answer):
    import kenn.server as server

    def engine(*args, **kwargs):
        yield {"event": "token", "token": "Provisional tokens"}
        yield {"event": "metadata", "data": {"route": "production", **({"answer": ""} if has_final_answer else {})}}

    monkeypatch.setattr(server, "answer_payload_stream", engine)
    events = stream_http("/api/ask", {"session_id": "song-a"})
    final = [event["data"] for event in events if event["event"] == "metadata"][-1]
    assert final["answer"] == ("" if has_final_answer else "Provisional tokens")


@pytest.mark.parametrize("companion_online", [True, False])
@pytest.mark.parametrize("has_final_answer", [True, False])
def test_cli_stream_uses_tokens_only_when_final_metadata_has_no_answer(monkeypatch, capsys, companion_online, has_final_answer):
    events = [
        {"event": "token", "token": "Provisional tokens"},
        {"event": "metadata", "data": {"answer": ""} if has_final_answer else {}},
        {"event": "done"},
    ]
    if companion_online:
        class Response(io.BytesIO):
            status = 200

        encoded = "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode()
        monkeypatch.setattr(chat_cli.urllib.request, "urlopen", lambda *args, **kwargs: Response(encoded))
    else:
        monkeypatch.setattr(chat_cli.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("Offline fixture")))
        monkeypatch.setattr(chat_cli, "answer_payload_stream", lambda *args, **kwargs: iter(events))
    answer, _ = chat_cli._stream_query("Explain compressor release", session_id="song-a")
    assert answer == ("" if has_final_answer else "Provisional tokens")


def test_stream_cache_commit_rechecks_the_owner_after_its_last_event(isolated_stream_cache, monkeypatch):
    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", lambda *args, **kwargs: iter([
        {"event": "metadata", "data": {"answer": "Late advice", "confidence": "high"}},
    ]))
    stream = chat_answer.answer_payload_stream("Explain compressor release", session_id="song-a")
    assert next(stream)["data"]["answer"] == "Late advice"
    answer_upgrades.invalidate("song-a")
    final, = list(stream)
    assert final["data"]["answer"] == "" and final["data"]["answer_delivery_discarded"] is True
    assert session_memory.get_semantic_cache_hit("Explain compressor release", session_id="song-a") is None


def test_actual_orchestration_stream_forwards_scope_and_never_reuses_a_proposal(isolated_stream_cache, monkeypatch):
    calls = []

    def dispatch(query, **kwargs):
        calls.append(kwargs)
        proposal = {"action": "mute_track", "confirmation_token": f"fixture-token-{len(calls)}"}
        return {
            "message": "Confirm to mute the vocal", "agent_name": "ableton", "proposal": proposal,
            "confirmation_token": proposal["confirmation_token"], "requires_confirmation": True,
        }

    monkeypatch.setattr(chat_answer, "get_orchestrator", lambda: SimpleNamespace(dispatch=dispatch))
    for _ in range(2):
        events = list(chat_answer.answer_payload_stream("Mute the vocal", session_id="song-a", correlation_id="fixture-correlation"))
        final = [event["data"] for event in events if event["event"] == "metadata"][-1]
        assert final["requires_confirmation"] is True
        assert final["confirmation_token"] == final["proposal"]["confirmation_token"] == f"fixture-token-{len(calls)}"
    assert len(calls) == 2
    assert calls == [{"session_id": "song-a", "plugin_session_id": "", "correlation_id": "fixture-correlation"}] * 2


@pytest.mark.parametrize("path", ["/api/ask", "/kenn/api/ask"])
def test_http_superseded_stream_discards_partial_text_and_finalization_side_effects(stream_http, monkeypatch, path):
    import kenn.server as server

    def engine(*args, **kwargs):
        yield {"event": "token", "token": "An unfinished earlier answer"}
        answer_upgrades.invalidate("song-a")
        yield {"event": "metadata", "data": {"answer": "Late completed answer", "route": "production"}}

    attempted = []

    def forbidden(*args, **kwargs):
        attempted.append("late context or checkpoint attachment")
        raise AssertionError("A discarded stream must not attach current project state")

    monkeypatch.setattr(server, "answer_payload_stream", engine)
    for name in ("_attach_explicit_audio_evidence", "_attach_stem_masking_evidence", "_attach_audio_classification_evidence"):
        monkeypatch.setattr(server, name, forbidden)
    monkeypatch.setattr(server.Handler, "_maybe_attach_checkpoint", forbidden)
    monkeypatch.setattr(server, "demo_feedback", SimpleNamespace(record_question=forbidden))
    events = stream_http(path, {"session_id": "song-a", "correlation_id": "fixture-correlation"})
    final = [event["data"] for event in events if event["event"] == "metadata"][-1]
    assert final["answer"] == "" and final["answer_delivery_discarded"] is True
    assert final["status"] == final["envelope"]["status"] == "cancelled"
    assert final["inference_aborted"] is False and final["correlation_id"] == "fixture-correlation"
    assert events[-1]["event"] == "done" and attempted == []


def test_cli_fallback_obeys_the_actual_public_streams_discarded_completion(isolated_stream_cache, monkeypatch, capsys):
    def offline(*args, **kwargs):
        raise OSError("Companion fixture is offline")

    def engine(*args, **kwargs):
        yield {"event": "token", "token": "An unfinished earlier answer"}
        answer_upgrades.invalidate("song-a")
        yield {"event": "metadata", "data": {"answer": "Late completed answer", "confidence": "high"}}

    monkeypatch.setattr(chat_cli.urllib.request, "urlopen", offline)
    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", engine)
    answer, final = chat_cli._stream_query("Explain compressor release", session_id="song-a")
    assert answer == "" and final["answer_delivery_discarded"] is True and final["status"] == "cancelled"


def test_cancel_stream_reports_its_revocation_instead_of_discarding_its_own_reply(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Cancel must not retrieve or generate")

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", forbidden)
    events = list(chat_answer.answer_payload_stream("cancel", session_id="song-a"))
    final = [event["data"] for event in events if event["event"] == "metadata"][-1]
    assert "Pending answer delivery" in final["answer"]
    assert final["answer_delivery_discarded"] is True and final["inference_aborted"] is False
    assert "song-a" not in answer_upgrades._TURNS


def test_http_checkpoint_write_rechecks_the_owner_after_contract_augmentation(stream_http, monkeypatch):
    import kenn.server as server

    augment = server.augment_payload

    def superseded_during_augmentation(payload, **kwargs):
        result = augment(payload, **kwargs)
        answer_upgrades.invalidate("song-a")
        return result

    attempted = []
    monkeypatch.setattr(server, "augment_payload", superseded_during_augmentation)
    monkeypatch.setattr(server, "answer_payload_stream", lambda *args, **kwargs: iter([
        {"event": "metadata", "data": {"answer": "Current advice", "route": "production"}},
    ]))
    monkeypatch.setattr(
        server.Handler, "_maybe_attach_checkpoint",
        lambda self, metadata, *args: attempted.append("stale checkpoint") or metadata,
    )
    events = stream_http("/api/ask", {"session_id": "song-a"})
    final = [event["data"] for event in events if event["event"] == "metadata"][-1]
    assert final["answer"] == "" and final["status"] == "cancelled"
    assert final["answer_delivery_discarded"] is True and attempted == []


def test_cache_replay_finishes_with_discarded_metadata_if_its_last_event_is_superseded(isolated_stream_cache, monkeypatch):
    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", lambda *args, **kwargs: iter([
        {"event": "metadata", "data": {"answer": "Cached advice", "confidence": "high"}},
        {"event": "token", "token": "Cached advice"},
    ]))
    list(chat_answer.answer_payload_stream("Explain compressor release", session_id="song-a"))
    stream = chat_answer.answer_payload_stream("Explain compressor release", session_id="song-a")
    assert next(stream)["data"]["semantic_cache_hit"] is True
    assert next(stream)["token"] == "Cached advice"
    answer_upgrades.invalidate("song-a")
    final, = list(stream)
    assert final["data"]["answer"] == "" and final["data"]["answer_delivery_discarded"] is True
