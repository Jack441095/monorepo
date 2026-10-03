import pytest

from kenn.core import chat_answer, chat_retrieval
from kenn.core.chat_routing import history_context_line, search_query_with_history, should_use_history
from kenn.core.evidence import EvidenceFact, EvidencePacket, history_turn
from kenn.llm import llm_rewrite


@pytest.fixture
def isolated_chat(monkeypatch, tmp_path):
    monkeypatch.setenv("KENN_CHATS_DIR", str(tmp_path / "chats"))
    monkeypatch.setenv("KENN_DB_PATH", str(tmp_path / "kenn.db"))
    monkeypatch.setattr(chat_answer, "latest_track_memory_lookup", lambda query: None)
    monkeypatch.setattr(chat_answer.get_orchestrator(), "dispatch", lambda *args, **kwargs: None)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    searches = []

    def search(query, *args, **kwargs):
        searches.append(query)
        return []

    for module in (chat_answer, chat_retrieval):
        monkeypatch.setattr(module, "load_chunks", lambda: [])
        monkeypatch.setattr(module, "load_terms", lambda: terms)
        monkeypatch.setattr(module, "search", search)
    return searches


def answer(query, history, stream, **kwargs):
    if stream:
        events = list(chat_answer.answer_payload_stream(query, history=history, allow_llm=False, **kwargs))
        return [event["data"] for event in events if event["event"] == "metadata"][-1]
    return chat_answer.answer_payload(query, history=history, allow_llm=False, **kwargs)


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
def test_cancel_that_i_will_do_it_myself_does_not_search_the_previous_question(stream, isolated_chat):
    # The five-turn run retrieved limiter advice after the user withdrew the request.
    history = [{"role": "user", "content": "What threshold would you suggest there?"}]
    payload = answer("Cancel that, I will do it myself.", history, stream, session_id="cancel-chat")

    assert isolated_chat == []
    assert payload["answer_delivery_discarded"] is True
    assert payload["inference_aborted"] is False
    assert payload["sources"] == []


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
def test_what_would_you_try_first_keeps_the_snare_and_the_volume_constraint(stream, isolated_chat):
    # A generic clarification menu lost both the named instrument and the later constraint.
    history = [
        {"role": "user", "content": "Make it sound bigger."},
        {"role": "assistant", "content": "Which instrument?"},
        {"role": "user", "content": "The snare."},
        {"role": "assistant", "content": "What would you like to change?"},
        {"role": "user", "content": "Without making it louder."},
    ]
    payload = answer("What would you try first?", history, stream)

    assert payload["route"] != "clarify"
    assert payload["used_history"]
    assert "The snare." in payload["search_query"]
    assert "Without making it louder." in payload["search_query"]


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
def test_clarification_about_the_problem_with_it_names_the_earlier_request(stream, isolated_chat):
    history = [
        {"role": "user", "content": "How did the analysis of my mix go?"},
        {"role": "assistant", "content": "I haven't analysed a mix in this chat."},
        {"role": "user", "content": "Run it again."},
        {"role": "assistant", "content": "There is no analysis to rerun."},
    ]
    payload = answer("What was the problem with it?", history, stream)

    assert payload["route"] == "clarify"
    assert "How did the analysis of my mix go?" in payload["answer"]
    assert "mix problem, an Ableton workflow" not in payload["answer"]
    assert payload["sources"] == []
    assert isolated_chat == []


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
@pytest.mark.parametrize("query", [
    "What do I need to export stems for a client?",
    "What loudness should I master to for streaming?",
])
def test_export_and_loudness_questions_do_not_search_with_the_old_drum_reverb(query, stream, isolated_chat):
    history = [{"role": "user", "content": "How long should a reverb decay be on drums?"}]
    payload = answer(query, history, stream)

    assert payload["used_history"] is False
    assert payload["search_query"] == query
    assert all("reverb" not in searched.lower() for searched in isolated_chat)


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
@pytest.mark.parametrize("followup", [False, True], ids=["new-subject", "followup"])
@pytest.mark.parametrize("with_evidence", [False, True], ids=["chat-only", "attached-evidence"])
def test_generation_drops_old_reverb_on_export_but_keeps_it_for_a_followup(
    stream, followup, with_evidence, isolated_chat, monkeypatch,
):
    # Retrieval changed subjects, but generation still received the old reverb exchange.
    history = [
        {"role": "user", "content": "How long should a reverb decay be on drums?"},
        {"role": "assistant", "content": "Compare the drum reverb tail with the next hit."},
    ]
    evidence = [history_turn(EvidencePacket(
        source="plugin_bus_snapshot", captured_at_age_seconds=0,
        facts=(EvidenceFact("peak_dbfs", -5.0, "dBFS"),), limitations=(),
    ))] if with_evidence else []
    history = evidence + history
    query = "What decay should I use?" if followup else "What do I need to export stems for a client?"
    results = [(20.0, {"source": "export-stems.md", "title": "Export Stems", "kind": "note",
                       "text": "Export stems from the same start point and check the rendered files."})]
    for module in (chat_answer, chat_retrieval):
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: results)
    monkeypatch.setattr(chat_answer, "constrain_results_for_query", lambda query, found: found)
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *args: False)
    monkeypatch.setattr(chat_answer, "intent_guard_failed", lambda *args: False)
    monkeypatch.setattr(chat_answer, "grounding_mode", lambda *args: "supported")
    monkeypatch.setattr(chat_answer, "answer_quality_report", lambda *args, **kwargs: {"score": 100, "warnings": []})
    monkeypatch.setattr(chat_answer, "llm_enabled", lambda: True)
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *args: True)
    monkeypatch.setattr(chat_answer, "build_template_answer", lambda *args, **kwargs: "Export stems from the same start point.")
    prompts = []

    def capture_generation(*args, **kwargs):
        messages, _ = llm_rewrite._build_synthesis_messages(*args, **kwargs)
        prompts.append(messages)
        return (_ for _ in ()) if stream else None

    monkeypatch.setattr(chat_answer, "llm_enhance_answer_stream" if stream else "llm_enhance_answer", capture_generation)
    if stream:
        list(chat_answer.answer_payload_stream(query, history=history, allow_llm=True))
    else:
        chat_answer.answer_payload(query, history=history, allow_llm=True)

    assert len(prompts) == 1
    prior_messages = prompts[0][1:-1]
    assert prior_messages == (history if followup else evidence)
    assert "User question:" in prompts[0][-1]["content"]
    assert query in prompts[0][-1]["content"]


def test_returning_to_drum_reverb_uses_the_reverb_turn_instead_of_the_latest_loudness_turn():
    history = [
        {"role": "user", "content": "How long should a reverb decay be on drums?"},
        {"role": "user", "content": "What do I need to export stems for a client?"},
        {"role": "user", "content": "What loudness should I master to for streaming?"},
    ]
    query = "Going back to the drum reverb, should I high-pass the return?"

    assert should_use_history(query, history)
    searched = search_query_with_history(query, history)
    assert searched.startswith(history[0]["content"])
    assert "streaming" not in searched
    assert "export" not in searched


def test_an_elliptical_release_time_question_still_uses_the_sidechain_question():
    history = [{"role": "user", "content": "How do I sidechain bass to the kick?"}]
    query = "What release time should I use?"

    assert should_use_history(query, history)
    assert search_query_with_history(query, history).startswith(history[0]["content"])


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
def test_threshold_suggestion_keeps_the_limiter_request_and_corrected_drum_bus(stream, isolated_chat):
    # The five-turn run searched this parameter question without its limiter or corrected target.
    history = [
        {"role": "user", "content": "Put a limiter on the master for me."},
        {"role": "assistant", "content": "Which bus do you want to discuss?"},
        {"role": "user", "content": "No, on the drum bus instead."},
        {"role": "assistant", "content": "Let's discuss the drum bus."},
    ]
    query = "What threshold would you suggest there?"
    payload = answer(query, history, stream)

    assert payload["used_history"]
    assert "Put a limiter" in payload["search_query"]
    assert "No, on the drum bus instead." in payload["search_query"]
    assert "limiter" in history_context_line(query, history).lower()
    assert "drum bus" in history_context_line(query, history).lower()


@pytest.mark.parametrize("query", [
    "What threshold would you suggest there?",
    "What release time would you recommend?",
])
def test_a_parameter_suggestion_without_history_stays_a_new_question(query):
    assert not should_use_history(query, None)
    assert search_query_with_history(query, None) == query


@pytest.mark.parametrize("query", [
    "What loudness would you suggest for streaming?",
    "What compressor would you suggest for the vocal?",
    "What restaurant would you suggest there?",
])
def test_a_new_named_subject_does_not_inherit_the_drum_bus_limiter(query):
    history = [
        {"role": "user", "content": "Put a limiter on the master for me."},
        {"role": "user", "content": "No, on the drum bus instead."},
    ]
    assert not should_use_history(query, history)
    assert search_query_with_history(query, history) == query


def test_a_parameter_followup_keeps_session_context_when_there_are_no_prior_questions():
    history = [{"role": "user", "content": "Session context for this KENN conversation\nTrack: bass\nDevice: compressor"}]

    assert should_use_history("What release time should I use?", history)
    assert history_context_line("What release time should I use?", history).startswith("[Session Context]")


def test_a_direct_loudness_question_with_no_history_stays_a_new_question():
    query = "What loudness should I master to for streaming?"
    assert not should_use_history(query, None)
    assert search_query_with_history(query, None) == query


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
def test_a_question_about_cancelling_is_not_a_withdrawn_request(stream, isolated_chat):
    payload = answer("How do I cancel an export?", None, stream)

    assert not payload.get("answer_delivery_discarded", False)


@pytest.mark.parametrize("stream", [False, True], ids=["payload", "stream"])
def test_a_clarification_without_history_still_asks_for_the_subject(stream, isolated_chat):
    payload = answer("Make it sound bigger.", None, stream)

    assert payload["route"] == "clarify"
    assert "Are you asking about a mix problem" in payload["answer"]
    assert not payload["used_history"]
    assert isolated_chat == []
