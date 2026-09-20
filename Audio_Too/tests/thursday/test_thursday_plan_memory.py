"""Tests for Thursday's planning memory (thursday/plan_memory.py) and its
wiring into thursday/brain.py's retrieval step and thursday/orchestrator.py's
plan-completion instrumentation.

Mirrors the testing conventions of tests/test_thursday_brain.py: LLM calls
are mocked via a MockLLMProvider monkeypatched onto thursday.brain.DEFAULT_LLM
so no live Ollama instance is required.
"""

from __future__ import annotations

import json

import pytest

from nite_core.model_runtime import LLMResult
from thursday import plan_memory
from thursday.brain import BrainDecision, build_brain_prompt, decide


class MockLLMProvider:
    """Mock LLM provider that records every prompt it was asked to answer."""

    def __init__(self, response_content: str):
        self.response_content = response_content
        self.calls: list[list[dict[str, str]]] = []

    def generate(
        self, messages: list[dict[str, str]], timeout: int = 10,
        response_schema: dict | None = None,
    ) -> LLMResult:
        self.calls.append(messages)
        return LLMResult(
            content=self.response_content,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )


@pytest.fixture
def isolated_plan_db(tmp_path, monkeypatch):
    """Point plan_memory at a throwaway SQLite DB + JSONL archive per test."""
    db_path = tmp_path / "plan_memory.sqlite3"
    archive_path = tmp_path / "plan_memory_archive.jsonl"
    monkeypatch.setenv("THURSDAY_PLAN_MEMORY_DB", str(db_path))
    monkeypatch.setenv("THURSDAY_PLAN_MEMORY_ARCHIVE", str(archive_path))
    return {"db_path": db_path, "archive_path": archive_path}


# ─── 8.1 Store: save / retrieve / query ────────────────────────────────────


def test_save_and_get_plan_trace(isolated_plan_db):
    plan_id = plan_memory.save_plan_trace(
        query="show my profile",
        abstract="Fetch the user's profile settings",
        steps=[{"kind": "service", "service_id": "user_profile_prefs", "params": {}}],
        status="success",
        service_id="user_profile_prefs",
        result_summary="Profile: Jack (default)",
    )
    assert plan_id is not None

    trace = plan_memory.get_plan_trace(plan_id)
    assert trace is not None
    assert trace["query"] == "show my profile"
    assert trace["status"] == "success"
    assert trace["steps"][0]["service_id"] == "user_profile_prefs"


def test_query_similar_plans_fts_match(isolated_plan_db):
    plan_memory.save_plan_trace(
        query="show my profile settings",
        abstract="Fetch the user's profile",
        steps=[{"kind": "service", "service_id": "user_profile_prefs"}],
        status="success",
    )
    plan_memory.save_plan_trace(
        query="cancel my audiogen render",
        abstract="Cancel a render job",
        steps=[{"kind": "service", "service_id": "audiogen_job"}],
        status="success",
    )

    hits = plan_memory.query_similar_plans("profile settings", limit=1)
    assert len(hits) == 1
    assert "profile" in hits[0]["query"]


def test_query_similar_plans_falls_back_gracefully_with_no_data(isolated_plan_db):
    assert plan_memory.query_similar_plans("anything at all") == []


def test_query_similar_plans_ranks_by_relevance_not_recency(isolated_plan_db):
    """Regression (2026-07-27), mirrors the identical fix in KENN's
    query_reasoning_traces: this used to ORDER BY created_at DESC, so a
    newer unrelated plan always won over an older, topically-relevant one
    just by sharing a stray word."""
    plan_memory.save_plan_trace(
        query="cancel my audiogen render",
        abstract="Cancel a render job",
        steps=[{"kind": "service", "service_id": "audiogen_job"}],
        status="success",
    )
    plan_memory.save_plan_trace(
        query="show my profile settings",
        abstract="Fetch the user's profile",
        steps=[{"kind": "service", "service_id": "user_profile_prefs"}],
        status="success",
    )

    hits = plan_memory.query_similar_plans("cancel my render job please", limit=1)
    assert len(hits) == 1
    assert "audiogen" in hits[0]["query"]


def test_query_similar_plans_with_only_stopwords_returns_no_hits(isolated_plan_db):
    plan_memory.save_plan_trace(
        query="show my profile settings",
        abstract="Fetch the user's profile",
        steps=[{"kind": "service", "service_id": "user_profile_prefs"}],
        status="success",
    )
    assert plan_memory.query_similar_plans("how do you do it") == []


# ─── 8.1 Retention: cap at N active, archive overflow to JSONL ─────────────


def test_retention_archives_overflow_instead_of_deleting(isolated_plan_db, monkeypatch):
    monkeypatch.setattr(plan_memory, "ACTIVE_LIMIT", 5)

    saved_ids = []
    for i in range(8):
        pid = plan_memory.save_plan_trace(
            query=f"task number {i}",
            abstract=f"plan {i}",
            steps=[{"kind": "service", "service_id": "svc"}],
            status="success",
        )
        saved_ids.append(pid)

    # Only the 5 most recent remain active.
    remaining = plan_memory.list_plan_history(limit=50)
    assert len(remaining) == 5
    remaining_queries = {r["query"] for r in remaining}
    assert "task number 7" in remaining_queries
    assert "task number 0" not in remaining_queries

    # The evicted rows were archived to JSONL, not silently deleted.
    archive_path = isolated_plan_db["archive_path"]
    assert archive_path.exists()
    archived_lines = archive_path.read_text().strip().splitlines()
    archived_records = [json.loads(line) for line in archived_lines]
    archived_queries = {r["query"] for r in archived_records}
    assert "task number 0" in archived_queries
    assert len(archived_records) == 3  # 8 saved - 5 kept active


# ─── 8.3 Retrieval step: build_brain_prompt injects past plans + lessons ──


def test_build_brain_prompt_injects_past_plans_and_lessons():
    hits = [
        {
            "query": "show my profile",
            "abstract": "Fetch the user's profile",
            "status": "success",
            "steps": [{"kind": "service", "service_id": "user_profile_prefs"}],
            "executed_steps": [{"kind": "service", "service_id": "user_profile_prefs"}],
            "lesson": None,
        },
        {
            "query": "cancel my render",
            "abstract": "Cancel an audiogen render",
            "status": "failed",
            "steps": [{"kind": "service", "service_id": "audiogen_job"}],
            "executed_steps": [{"kind": "service", "service_id": "audiogen_job"}],
            "lesson": "Avoid routing 'cancel my render' to audiogen_job without a job ID — it raised an error.",
        },
    ]

    prompt = build_brain_prompt(
        session_summary="",
        plan_memory_hits=hits,
        services={},
        subagents=[],
        user_text="cancel my current render job",
    )

    system_content = prompt[0]["content"]
    assert "Past Similar Plans & Outcomes" in system_content
    assert "user_profile_prefs" in system_content
    assert "Lesson learned: Avoid routing 'cancel my render'" in system_content


def test_decide_retrieves_similar_plans_and_injects_into_prompt(isolated_plan_db, monkeypatch):
    """decide() should call plan_memory.query_similar_plans and the resulting
    prompt sent to the LLM should contain the past plan's step sequence."""
    plan_memory.save_plan_trace(
        query="show my profile",
        abstract="Fetch the user's profile settings",
        steps=[{"kind": "service", "service_id": "user_profile_prefs"}],
        status="success",
        service_id="user_profile_prefs",
        executed_steps=[{"kind": "service", "service_id": "user_profile_prefs"}],
    )

    json_response = json.dumps(
        {"type": "chat", "abstract": "ok", "steps": [], "confidence": "high"}
    )
    provider = MockLLMProvider(json_response)
    monkeypatch.setattr("thursday.brain.DEFAULT_LLM", provider)

    session = {"turns": []}
    decide(session=session, services={}, subagents=[], user_text="show me my profile please")

    assert len(provider.calls) == 1
    sent_prompt_text = provider.calls[0][0]["content"]
    assert "user_profile_prefs" in sent_prompt_text
    assert "Fetch the user's profile settings" in sent_prompt_text


# ─── End-to-end: repeated task reuses prior plan; failure surfaces lesson ─


def _fake_plan_decision(service_id: str, abstract: str) -> BrainDecision:
    return BrainDecision(
        type="plan",
        abstract=abstract,
        steps=[{"kind": "service", "service_id": service_id, "params": {}}],
        confidence="high",
    )


def test_orchestrator_writes_plan_trace_on_successful_brain_execution(
    isolated_plan_db, monkeypatch, tmp_path
):
    from thursday import session_manager
    from thursday.orchestrator import handle

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")
    monkeypatch.setattr(
        "thursday.brain.decide",
        lambda **kw: _fake_plan_decision("user_profile_prefs", "Show the user's profile"),
    )
    monkeypatch.setattr(
        "thursday.registry.system._handle_user_profile",
        lambda text, ctx: "Your profile: Jack (default)",
    )
    monkeypatch.setattr("thursday.orchestrator.should_check", lambda: False)
    monkeypatch.setattr("thursday.orchestrator.get_pending_alerts", lambda: [])

    session = session_manager.get_or_create_session("plan-memory-success")
    result = handle("show my profile", session=session, list_records=lambda _: [])

    assert "profile" in result.lower()

    history = plan_memory.list_plan_history(limit=10)
    assert len(history) == 1
    assert history[0]["status"] == "success"
    assert history[0]["service_id"] == "user_profile_prefs"
    assert history[0]["query"] == "show my profile"


def test_second_similar_call_prompt_includes_first_plan(isolated_plan_db, monkeypatch, tmp_path):
    """Simpler, self-contained version of the reuse test: run task 1 through
    the orchestrator (saving a real plan trace via save_plan_trace), then
    call brain.decide() directly for a similar query and assert the prompt
    handed to the LLM contains the first run's plan abstract + step.
    """
    from thursday import session_manager
    from thursday.orchestrator import handle
    from thursday import brain as brain_module
    # Grab the real decide() before it gets monkeypatched below, so the
    # second, "similar" call in this test exercises the genuine retrieval
    # + prompt-building path instead of the canned fake used for run 1.
    real_decide = brain_module.decide

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")
    monkeypatch.setattr(
        "thursday.brain.decide",
        lambda **kw: _fake_plan_decision("user_profile_prefs", "Show the user's profile"),
    )
    monkeypatch.setattr(
        "thursday.registry.system._handle_user_profile",
        lambda text, ctx: "Your profile: Jack (default)",
    )
    monkeypatch.setattr("thursday.orchestrator.should_check", lambda: False)
    monkeypatch.setattr("thursday.orchestrator.get_pending_alerts", lambda: [])

    session = session_manager.get_or_create_session("plan-memory-reuse-2")
    handle("show my profile", session=session, list_records=lambda _: [])

    json_response = json.dumps(
        {"type": "chat", "abstract": "ok", "steps": [], "confidence": "high"}
    )
    provider = MockLLMProvider(json_response)
    monkeypatch.setattr(brain_module, "DEFAULT_LLM", provider)

    real_decide(
        session={"turns": []},
        services={},
        subagents=[],
        user_text="show me my profile again",
    )

    assert len(provider.calls) == 1
    sent_prompt_text = provider.calls[0][0]["content"]
    assert "user_profile_prefs" in sent_prompt_text
    assert "Show the user's profile" in sent_prompt_text


def test_failed_plan_surfaces_lesson_in_next_similar_attempt(
    isolated_plan_db, monkeypatch, tmp_path
):
    """A failed plan execution should record a lesson, and that lesson
    should appear in the prompt built for the next similar attempt."""
    from thursday import session_manager
    from thursday.orchestrator import handle
    from thursday import brain as brain_module
    # Grab the real decide() before it gets monkeypatched below, so the
    # next attempt exercises genuine retrieval instead of the canned fake.
    real_decide = brain_module.decide

    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")
    monkeypatch.setattr(
        "thursday.brain.decide",
        lambda **kw: _fake_plan_decision("user_profile_prefs", "Show the user's profile"),
    )

    def _boom(text, ctx):
        raise RuntimeError("profile store unavailable")

    monkeypatch.setattr("thursday.registry.system._handle_user_profile", _boom)
    monkeypatch.setattr("thursday.orchestrator.should_check", lambda: False)
    monkeypatch.setattr("thursday.orchestrator.get_pending_alerts", lambda: [])

    session = session_manager.get_or_create_session("plan-memory-failure")

    from thursday.errors import ServiceExecutionError

    with pytest.raises(ServiceExecutionError):
        handle("show my profile", session=session, list_records=lambda _: [])

    history = plan_memory.list_plan_history(limit=10)
    assert len(history) == 1
    assert history[0]["status"] == "failed"
    assert history[0]["lesson"]
    assert "user_profile_prefs" in history[0]["lesson"]

    # Now the next similar attempt's prompt should surface that lesson.
    json_response = json.dumps(
        {"type": "chat", "abstract": "ok", "steps": [], "confidence": "high"}
    )
    provider = MockLLMProvider(json_response)
    monkeypatch.setattr(brain_module, "DEFAULT_LLM", provider)

    real_decide(
        session={"turns": []},
        services={},
        subagents=[],
        user_text="show my profile once more",
    )

    assert len(provider.calls) == 1
    sent_prompt_text = provider.calls[0][0]["content"]
    assert "Lesson learned" in sent_prompt_text
    assert "profile store unavailable" in sent_prompt_text
