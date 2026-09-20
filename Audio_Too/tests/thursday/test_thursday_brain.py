from unittest.mock import MagicMock

from nite_core.model_runtime import LLMResult
from thursday import brain
from thursday.brain import (
    _select_relevant_services,
    build_brain_prompt,
    build_decision_json_schema,
    decide,
    load_codebase_map,
    looks_like_codebase_question,
)
from thursday.orchestrator import classify_request


class _FakeService:
    def __init__(self, triggers, description="a fake service"):
        self.triggers = triggers
        self.description = description


def test_select_relevant_services_leaves_small_catalog_untouched():
    services = {"kenn": _FakeService(["mix"]), "client_info": _FakeService(["client"])}
    assert _select_relevant_services(services, "anything", limit=15) == services


def test_select_relevant_services_trims_large_catalog_and_ranks_by_trigger_match():
    services = {
        f"filler_{i}": _FakeService([f"filler{i}"]) for i in range(20)
    }
    services["invoice_lookup"] = _FakeService(["invoice", "invoices"])

    selected = _select_relevant_services(services, "show my invoices please", limit=15)

    assert len(selected) <= 15
    assert "invoice_lookup" in selected


def test_select_relevant_services_always_keeps_core_set_on_zero_matches():
    services = {f"filler_{i}": _FakeService([f"filler{i}"]) for i in range(20)}
    services["kenn"] = _FakeService(["mixing", "mastering"])
    services["client_info"] = _FakeService(["client"])

    selected = _select_relevant_services(services, "completely unrelated chit chat", limit=15)

    assert "kenn" in selected
    assert "client_info" in selected


def test_select_relevant_services_tolerates_malformed_service_definition():
    """A mocked/broken service (non-iterable .triggers) must score 0 and be
    skipped, never crash the brain's routing decision."""
    services = {f"filler_{i}": _FakeService([f"filler{i}"]) for i in range(20)}
    services["broken"] = MagicMock()  # .triggers is an auto-mock, not iterable as a real list

    selected = _select_relevant_services(services, "hello there", limit=15)

    assert len(selected) <= 15  # did not raise


def test_decide_only_offers_trimmed_services_to_the_llm(monkeypatch):
    """End-to-end: decide() must actually apply the trim to what's sent to
    the LLM, not just have the helper exist unused."""
    services = {f"filler_{i}": _FakeService([f"filler{i}"]) for i in range(20)}
    services["invoice_lookup"] = _FakeService(["invoices"])

    json_response = '{"type": "chat", "abstract": "ok", "steps": [], "confidence": "high"}'
    captured = {}

    class CapturingProvider:
        def generate(self, messages, timeout=10, response_schema=None):
            captured["messages"] = messages
            captured["schema"] = response_schema
            return LLMResult(content=json_response, model="mock-model", usage={})

    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", CapturingProvider())

    decide(session={"turns": []}, services=services, subagents=[], user_text="show my invoices")

    enum_ids = captured["schema"]["schema"]["properties"]["steps"]["items"]["properties"]["service_id"]["enum"]
    assert len(enum_ids) <= 15
    assert "invoice_lookup" in enum_ids
    assert not all(f"filler_{i}" in enum_ids for i in range(20))


def test_looks_like_codebase_question_matches_code_vocabulary():
    assert looks_like_codebase_question("which Python file handles this?")
    assert looks_like_codebase_question("what does this function do")
    assert looks_like_codebase_question("where is the database schema defined")


def test_looks_like_codebase_question_rejects_unrelated_text():
    assert not looks_like_codebase_question("how's business today?")
    assert not looks_like_codebase_question("check client info for Jack")
    assert not looks_like_codebase_question("what's the weather")


def test_build_decision_json_schema_constrains_service_and_kind_enums():
    services = {"kenn": object(), "automix": object()}
    schema = build_decision_json_schema(services, ["admin", "marketing"])
    props = schema["schema"]["properties"]
    assert props["type"]["enum"] == ["chat", "plan", "subagent", "abstain", "parallel_swarm"]
    step_props = props["steps"]["items"]["properties"]
    assert step_props["kind"]["enum"] == ["service", "subagent"]
    assert step_props["service_id"]["enum"] == ["automix", "kenn"]
    assert step_props["agent"]["enum"] == ["admin", "marketing"]


def test_build_decision_json_schema_handles_empty_services_and_subagents():
    schema = build_decision_json_schema({}, [])
    step_props = schema["schema"]["properties"]["steps"]["items"]["properties"]
    assert step_props["service_id"]["enum"] == [""]
    assert step_props["agent"]["enum"] == [""]


class MockLLMProvider:
    """Mock LLM Provider to control LLM outputs deterministically in tests."""
    def __init__(self, response_content: str):
        self.response_content = response_content

    def generate(
        self, messages: list[dict[str, str]], timeout: int = 10,
        response_schema: dict | None = None,
    ) -> LLMResult:
        return LLMResult(
            content=self.response_content,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20}
        )


def test_build_brain_prompt():
    """Verify build_brain_prompt correctly constructs system instructions, services, and queries."""
    mock_service = MagicMock()
    mock_service.description = "Handle client management information"
    mock_service.triggers = ["client", "customer"]
    services = {"client_info": mock_service}

    prompt = build_brain_prompt(
        session_summary="USER: hello\nTHURSDAY: Hi Jack!",
        plan_memory_hits=[],
        services=services,
        subagents=["admin"],
        user_text="Show client info for Jack"
    )

    # Check prompt has system, summary, and user messages
    assert len(prompt) == 3
    assert prompt[0]["role"] == "system"
    assert "Handle client management information" in prompt[0]["content"]
    assert "client_info" in prompt[0]["content"]
    assert "admin" in prompt[0]["content"]
    
    assert prompt[1]["role"] == "system"
    assert "USER: hello" in prompt[1]["content"]
    
    assert prompt[2]["role"] == "user"
    assert prompt[2]["content"] == "Show client info for Jack"


def test_build_brain_prompt_encourages_general_knowledge_answers_when_chat_only():
    """2026-08-07 (Jack: "make her more like Siri"): chat_only calls are the
    unknown/contextual-intent escalation path (see decide()'s docstring) --
    the model should answer general-knowledge questions directly instead of
    deflecting, but this instruction is irrelevant (and was previously
    absent) for non-chat_only calls that have real services on offer."""
    prompt_chat_only = build_brain_prompt(
        session_summary="", plan_memory_hits=[], services={}, subagents=[],
        user_text="what's the capital of France?", chat_only=True,
    )
    assert "general-knowledge questions" in prompt_chat_only[0]["content"]
    assert "do NOT deflect" in prompt_chat_only[0]["content"]

    mock_service = MagicMock()
    mock_service.description = "Handle client management information"
    mock_service.triggers = ["client"]
    prompt_with_services = build_brain_prompt(
        session_summary="", plan_memory_hits=[], services={"client_info": mock_service},
        subagents=[], user_text="Show client info for Jack", chat_only=False,
    )
    assert "do NOT deflect" not in prompt_with_services[0]["content"]


def test_build_brain_prompt_includes_codebase_map_when_provided():
    """Stage O2: the brain prompt must actually include the codebase map
    when one is given, not just accept the parameter silently."""
    prompt = build_brain_prompt(
        session_summary="",
        plan_memory_hits=[],
        services={},
        subagents=[],
        user_text="where does AutoMix live?",
        codebase_map="## 1. business/app/\nThe local HTTP server.",
    )
    assert "## Codebase Map" in prompt[0]["content"]
    assert "server/app/" in prompt[0]["content"]


def test_build_brain_prompt_omits_codebase_map_section_when_empty():
    """Backward compatible: no map given (e.g. load failed) means no
    dangling empty section in the prompt."""
    prompt = build_brain_prompt(
        session_summary="",
        plan_memory_hits=[],
        services={},
        subagents=[],
        user_text="hello",
    )
    assert "## Codebase Map" not in prompt[0]["content"]


def test_load_codebase_map_reads_the_real_file(monkeypatch):
    monkeypatch.setattr(brain, "_codebase_map_cache", None)
    content = load_codebase_map()
    assert "server/app/" in content
    assert "thursday/" in content
    assert "studio/kenn" in content


def test_load_codebase_map_is_cached(monkeypatch):
    monkeypatch.setattr(brain, "_codebase_map_cache", "cached content")
    assert load_codebase_map() == "cached content"


def test_load_codebase_map_degrades_gracefully_on_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(brain, "_codebase_map_cache", None)
    monkeypatch.setattr(brain, "CODEBASE_MAP_PATH", tmp_path / "does-not-exist.md")
    assert load_codebase_map() == ""


def test_decide_passes_codebase_map_into_the_llm_call(monkeypatch):
    """decide() must actually load and forward the map, not just have the
    plumbing exist unused."""
    json_response = """
    {
        "type": "chat",
        "abstract": "ok",
        "steps": [],
        "confidence": "high"
    }
    """
    captured = {}

    class CapturingProvider:
        def generate(self, messages, timeout=10, response_schema=None):
            captured["messages"] = messages
            return LLMResult(content=json_response, model="mock-model", usage={})

    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", CapturingProvider())
    monkeypatch.setattr(brain, "_codebase_map_cache", "## Test Map\nsome content")

    # Stage O2 reliability follow-up: the map is now only loaded for
    # requests that actually look codebase-related (prompt-size fix) -- use
    # a question that matches the keyword heuristic.
    decide(session={"turns": []}, services={}, subagents=[], user_text="which file handles this?")

    assert "## Codebase Map" in captured["messages"][0]["content"]
    assert "some content" in captured["messages"][0]["content"]


def test_decide_does_not_load_codebase_map_for_unrelated_questions(monkeypatch):
    """The other half of the reliability fix: non-codebase requests must not
    pay the prompt-size cost of the map at all."""
    json_response = '{"type": "chat", "abstract": "ok", "steps": [], "confidence": "high"}'
    captured = {}

    class CapturingProvider:
        def generate(self, messages, timeout=10, response_schema=None):
            captured["messages"] = messages
            return LLMResult(content=json_response, model="mock-model", usage={})

    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", CapturingProvider())
    monkeypatch.setattr(brain, "_codebase_map_cache", "## Test Map\nsome content")

    decide(session={"turns": []}, services={}, subagents=[], user_text="how's business today?")

    assert "## Codebase Map" not in captured["messages"][0]["content"]


def test_decide_chat_path(monkeypatch):
    """Verify decide() correctly parses a chat decision."""
    json_response = """
    {
        "type": "chat",
        "abstract": "Hello Jack, how can I help you today?",
        "steps": [],
        "confidence": "high"
    }
    """
    provider = MockLLMProvider(json_response)
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", provider)

    session = {"turns": []}
    decision = decide(
        session=session,
        services={},
        subagents=[],
        user_text="hello"
    )
    assert decision.type == "chat"
    assert decision.abstract == "Hello Jack, how can I help you today?"
    assert decision.confidence == "high"


def test_decide_chat_path_parses_the_dedicated_message_field(monkeypatch):
    """Regression (2026-08-02, Jack live report -- Thursday chat returning
    generic non-answers like "Assisting in crafting an empathetic text
    response"): the schema's "abstract" field is documented as an internal
    reasoning summary, not the reply -- decide() must parse a separate
    "message" field that holds the literal user-facing text."""
    json_response = """
    {
        "type": "chat",
        "abstract": "Greeting the user warmly",
        "message": "Hey Jack! What can I help you with today?",
        "steps": [],
        "confidence": "high"
    }
    """
    provider = MockLLMProvider(json_response)
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", provider)

    decision = decide(session={"turns": []}, services={}, subagents=[], user_text="hello")

    assert decision.type == "chat"
    assert decision.message == "Hey Jack! What can I help you with today?"
    assert decision.abstract == "Greeting the user warmly"


def test_decision_schema_includes_a_message_field(monkeypatch):
    schema = build_decision_json_schema({}, [])
    assert "message" in schema["schema"]["properties"]


def test_decide_plan_path(monkeypatch):
    """Verify decide() correctly parses and validates a plan decision with service steps."""
    json_response = """
    {
        "type": "plan",
        "abstract": "Retrieve active client list",
        "steps": [
            {
                "kind": "service",
                "service_id": "client_info",
                "params": {}
            }
        ],
        "confidence": "high"
    }
    """
    provider = MockLLMProvider(json_response)
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", provider)

    mock_service = MagicMock()
    services = {"client_info": mock_service}
    session = {"turns": []}

    decision = decide(
        session=session,
        services=services,
        subagents=[],
        user_text="show clients"
    )
    assert decision.type == "plan"
    assert len(decision.steps) == 1
    assert decision.steps[0]["kind"] == "service"
    assert decision.steps[0]["service_id"] == "client_info"


def test_decide_fallback_on_malformed_json(monkeypatch):
    """Verify decide() returns abstain when LLM returns malformed JSON."""
    provider = MockLLMProvider("Not valid JSON at all")
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", provider)

    session = {"turns": []}
    decision = decide(
        session=session,
        services={},
        subagents=[],
        user_text="run daily cleanup"
    )
    assert decision.type == "abstain"
    assert decision.confidence == "low"


def test_decide_malformed_json_failure_never_logs_raw_content(monkeypatch, caplog):
    """docs/PROJECT_ACTION_PLAN_2026-07-18.md §8.1: the malformed-JSON fallback
    logs a length only, never the raw LLM output -- that output is generated
    directly from the user's own message/conversation history, so a raw dump
    here would be exactly the "customer prompts leaked to logs" case to avoid.
    """
    raw_content = "Not valid JSON at all, and this definitely mentions my private mixdown notes"
    provider = MockLLMProvider(raw_content)
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", provider)

    with caplog.at_level("WARNING"):
        decide(session={"turns": []}, services={}, subagents=[], user_text="run daily cleanup")

    warning_text = "\n".join(record.message for record in caplog.records)
    assert raw_content not in warning_text
    assert f"{len(raw_content)} chars" in warning_text


def test_classify_request_wiring_with_brain_enabled(monkeypatch):
    """Verify classify_request sets execution_target to brain when LLM brain
    is enabled, for a message the regex classifier can't confidently place.

    Uses ambiguous text rather than "hello": brain gating (latency fix) only
    invokes the LLM when the raw regex intent is "unknown"/"contextual" --
    a confident deterministic match like a plain greeting is intentionally
    never routed to the brain, since the regex path already answers it
    instantly. See test_classify_request_skips_brain_for_confident_intent
    for that side of the gate.
    """
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")

    json_response = """
    {
        "type": "chat",
        "abstract": "Sure thing!",
        "steps": [],
        "confidence": "high"
    }
    """
    provider = MockLLMProvider(json_response)
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", provider)

    session = {"turns": []}
    decision = classify_request("what do you make of all this then", session)

    assert decision.execution_target == "brain"
    assert decision.brain_decision is not None
    assert decision.brain_decision.type == "chat"
    assert decision.brain_decision.abstract == "Sure thing!"


def test_classify_request_skips_brain_for_confident_intent(monkeypatch):
    """Latency fix: a message the regex classifier confidently places
    (e.g. a plain greeting) must never invoke the LLM brain, even when
    enabled -- only "unknown"/"contextual" raw intents do. Uses a provider
    that raises if called at all, so this fails loudly if gating regresses
    back to calling the brain unconditionally.
    """
    monkeypatch.setenv("THURSDAY_BRAIN_ENABLED", "1")

    class ExplodingProvider:
        def generate(self, messages, timeout=10, response_schema=None):
            raise AssertionError("brain must not be called for a confident regex intent")

    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", ExplodingProvider())

    session = {"turns": []}
    decision = classify_request("hello", session)

    assert decision.intent.name == "greeting"
    assert decision.execution_target != "brain"
    assert decision.brain_decision is None


def test_classify_request_routes_pronoun_chitchat_to_brain_not_stale_service(monkeypatch):
    """Regression for the reported misroute: a casual message containing a
    pronoun ("her") classifies as "contextual" on regex alone and, with no
    brain, blindly inherits whatever service a completely unrelated earlier
    turn used (e.g. a mix review), producing "I need current_mix_review to
    look that up." With the brain enabled, this raw intent is exactly the
    case the latency gate escalates to the LLM instead of guessing.
    """
    monkeypatch.setenv("THURSDAY_BRAIN_ENABLED", "1")

    json_response = """
    {
        "type": "chat",
        "abstract": "I'll leave the horse commentary to you and Jasmine!",
        "steps": [],
        "confidence": "high"
    }
    """
    provider = MockLLMProvider(json_response)
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", provider)

    session = {"turns": []}
    decision = classify_request("Hey, Thursday. Can you tell Jasmine her horses suck?", session)

    assert decision.execution_target == "brain"
    assert decision.brain_decision.type == "chat"


def test_decide_excludes_given_services_from_prompt_and_schema(monkeypatch):
    """exclude_services must remove the service from both the prompt text
    and the schema's service_id enum -- structurally, not just deprioritized."""
    services = {
        "kenn": _FakeService([], description="Audio production, mixing, and mastering advice"),
        "client_info": _FakeService(["client"]),
    }
    json_response = '{"type": "chat", "abstract": "ok", "steps": [], "confidence": "high"}'
    captured = {}

    class CapturingProvider:
        def generate(self, messages, timeout=10, response_schema=None):
            captured["messages"] = messages
            captured["schema"] = response_schema
            return LLMResult(content=json_response, model="mock-model", usage={})

    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", CapturingProvider())

    decide(
        session={"turns": []}, services=services, subagents=[],
        user_text="hey how are you", exclude_services={"kenn"},
    )

    enum_ids = captured["schema"]["schema"]["properties"]["steps"]["items"]["properties"]["service_id"]["enum"]
    assert "kenn" not in enum_ids
    assert "client_info" in enum_ids
    assert "kenn" not in captured["messages"][0]["content"]


def test_decide_chat_only_forbids_plan_and_subagent_types(monkeypatch):
    """chat_only must restrict the schema's "type" enum to chat/abstain only
    -- structurally, not just via prompt wording -- and offer no services or
    subagents at all, regardless of what's passed in."""
    services = {"automix": _FakeService(["mix"]), "kenn": _FakeService([])}
    json_response = '{"type": "chat", "abstract": "ok", "steps": [], "confidence": "high"}'
    captured = {}

    class CapturingProvider:
        def generate(self, messages, timeout=10, response_schema=None):
            captured["schema"] = response_schema
            captured["messages"] = messages
            return LLMResult(content=json_response, model="mock-model", usage={})

    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", CapturingProvider())

    decide(
        session={"turns": []}, services=services, subagents=["admin"],
        user_text="hey how are you", chat_only=True,
    )

    assert captured["schema"]["schema"]["properties"]["type"]["enum"] == ["chat", "abstain"]
    assert captured["schema"]["schema"]["properties"]["steps"]["items"]["properties"]["service_id"]["enum"] == [""]
    assert "automix" not in captured["messages"][0]["content"]
    assert "kenn" not in captured["messages"][0]["content"]


def test_decide_chat_only_drops_a_service_step_even_if_the_model_tries_one(monkeypatch):
    """Even if the model ignores the schema and emits a "plan" with a
    service step (real small models sometimes do), decide()'s own step
    validation must drop it: chat_only means the services dict it validates
    against is empty, so nothing can pass."""
    json_response = """
    {
        "type": "plan",
        "abstract": "trying to route anyway",
        "steps": [{"kind": "service", "service_id": "automix", "params": {}}],
        "confidence": "medium"
    }
    """
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", MockLLMProvider(json_response))

    decision = decide(
        session={"turns": []}, services={"automix": _FakeService(["mix"])}, subagents=[],
        user_text="hey how are you", chat_only=True,
    )

    assert decision.steps == []


def test_classify_request_brain_cannot_hand_off_chitchat_to_any_service(monkeypatch):
    """Regression (2026-07-27, Jack live-testing), in two stages:

    Stage 1: "Hey Thursday, how are you?" and similar plain chit-chat got
    routed to KENN's specialist pipeline instead of answered directly -- the
    small local model, unsure how to answer, over-applied the brain's
    "route production questions to KENN" instruction to messages the
    deterministic regex classifier had already decided were NOT production
    questions (that's the only reason the brain saw them at all -- see
    raw_intent_name gating in classify_request). First fix: exclude "kenn"
    specifically.

    Stage 2: that wasn't enough -- with "kenn" unavailable, live-testing
    showed the model just invented a *different* wrong service call
    ("automix", for a message about someone's horses) instead of replying.
    Real fix: classify_request passes chat_only=True, which structurally
    forbids "plan"/"subagent" decision types entirely for this escalation
    (see build_decision_json_schema's allowed_types), not just one service
    name. Even a real model trying hard to invent *any* tool call here
    cannot produce a validated step, because decide() validates every step
    against the services dict it was actually given -- which is empty.
    """
    monkeypatch.setenv("THURSDAY_BRAIN_ENABLED", "1")

    # A real small local model over-applying its instructions might still
    # try to emit a "plan"/service step despite the schema forbidding it --
    # decide()'s own step validation must reject it regardless, since
    # chat_only means the services dict it validates against is empty.
    json_response = """
    {
        "type": "plan",
        "abstract": "Route to a service for a studio check-in",
        "steps": [{"kind": "service", "service_id": "automix", "params": {}}],
        "confidence": "medium"
    }
    """
    provider = MockLLMProvider(json_response)
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", provider)

    session = {"turns": []}
    decision = classify_request("Hey Thursday, how are you?", session)

    assert decision.brain_decision is not None
    assert decision.brain_decision.steps == []


def test_classify_request_abstain_counts_as_brain_handled(monkeypatch):
    """Regression (2026-07-27, Jack live-testing), stage 3 of the same
    incident: an "abstain" brain decision is a legitimate answer (the model
    genuinely doesn't know what the user means), not a failure -- it must
    still route to execution_target="brain" so handle() replies with a
    plain decline. Before this fix, "abstain" wasn't in the set that sets
    execution_target="brain", so it silently fell through to handle()'s
    stage-14 default, which treats any leftover unknown/contextual intent
    as "probably a production question" and asks KENN anyway -- the exact
    chit-chat-routed-to-KENN behavior chat_only was supposed to prevent.
    """
    monkeypatch.setenv("THURSDAY_BRAIN_ENABLED", "1")
    json_response = '{"type": "abstain", "abstract": "not sure what is meant", "steps": [], "confidence": "low"}'
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", MockLLMProvider(json_response))

    session = {"turns": []}
    decision = classify_request("Hi, hi, hi, Thursday. Hey, gal.", session)

    assert decision.brain_decision.type == "abstain"
    assert decision.execution_target == "brain"


def test_handle_abstain_declines_gracefully_without_calling_kenn(monkeypatch, tmp_path):
    """End-to-end: handle() must return a plain decline for an abstained
    brain decision and must NOT fall through to stage 14's KENN default."""
    from thursday import client as api, session_manager
    from thursday.orchestrator import handle

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("THURSDAY_BRAIN_ENABLED", "1")
    monkeypatch.setattr("thursday.orchestrator.should_check", lambda: False)
    monkeypatch.setattr("thursday.orchestrator.get_pending_alerts", lambda: [])

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("KENN must not be called when the brain already abstained")

    monkeypatch.setattr(api, "ask_kenn", _fail_if_called)
    monkeypatch.setattr(
        "thursday.brain.decide",
        lambda **kw: brain.BrainDecision(
            type="abstain", abstract="not sure what is meant", steps=[], confidence="low",
            question_for_user=None,
        ),
    )

    session = session_manager.get_or_create_session("test-abstain-no-kenn")
    result = handle("Hi, hi, hi, Thursday. Hey, gal.", session=session, list_records=lambda _: [])

    assert result  # graceful non-empty reply, not an exception


def test_handle_chat_with_empty_abstract_does_not_literally_say_none(monkeypatch, tmp_path):
    """Regression (2026-07-27, Jack live-testing): a small local model
    occasionally returns type="chat" with an empty/missing abstract.
    format_response() doesn't guard against a falsy result, so the answer
    shown to the user was the literal string "None"."""
    from thursday import session_manager
    from thursday.orchestrator import handle

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("THURSDAY_BRAIN_ENABLED", "1")
    monkeypatch.setattr("thursday.orchestrator.should_check", lambda: False)
    monkeypatch.setattr("thursday.orchestrator.get_pending_alerts", lambda: [])
    monkeypatch.setattr(
        "thursday.brain.decide",
        lambda **kw: brain.BrainDecision(
            type="chat", abstract="", steps=[], confidence="low", question_for_user=None,
        ),
    )

    session = session_manager.get_or_create_session("test-empty-abstract")
    result = handle("This day. Have a easy day.", session=session, list_records=lambda _: [])

    assert "None" not in result


def test_handle_chat_shows_the_message_field_not_the_internal_abstract(monkeypatch, tmp_path):
    """Regression (2026-08-02, Jack live report via screenshot: Thursday chat
    returning an empty bubble / non-answer for a real question). Root cause:
    handle() used to show bd.abstract to the user, but abstract is documented
    to the model as an internal reasoning summary ("Summary of your reasoning
    or planned tasks") -- so real chat questions came back as plan-summary
    text instead of an actual answer. Proves handle() now prefers the
    dedicated bd.message field when both are present."""
    from thursday import session_manager
    from thursday.orchestrator import handle

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("THURSDAY_BRAIN_ENABLED", "1")
    monkeypatch.setattr("thursday.orchestrator.should_check", lambda: False)
    monkeypatch.setattr("thursday.orchestrator.get_pending_alerts", lambda: [])
    monkeypatch.setattr(
        "thursday.brain.decide",
        lambda **kw: brain.BrainDecision(
            type="chat",
            abstract="Assisting in crafting an empathetic text response",
            message="Ha! Good one. Got any more?",
            steps=[],
            confidence="high",
            question_for_user=None,
        ),
    )

    session = session_manager.get_or_create_session("test-message-not-abstract")
    result = handle("tell me a short joke", session=session, list_records=lambda _: [])

    assert "Ha! Good one. Got any more?" in result
    assert "Assisting in crafting an empathetic text response" not in result
