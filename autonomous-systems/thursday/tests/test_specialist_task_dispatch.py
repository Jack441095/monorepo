"""Tests for thursday/registry/handlers.py::_handle_specialist_task -- the
chat-reachable entry point for run_grounded_specialist(). Mirrors
test_marketing_research_agent_dispatch.py's structure: mocks only the
underlying execution function, not the real ops modules it calls.
"""

from __future__ import annotations

from unittest.mock import patch

from thursday.registry.handlers import _handle_specialist_task


def test_routes_commercial_keyword_to_commercial_specialist():
    with patch("thursday.specialists.run_grounded_specialist") as mock_run:
        mock_run.return_value.summary = "ok"
        _handle_specialist_task("ask the commercial specialist about our pricing")
    task = mock_run.call_args[0][0]
    assert task.specialist_id == "commercial"
    assert "pricing" in task.objective.lower()


def test_routes_qa_keyword_to_qa_specialist():
    with patch("thursday.specialists.run_grounded_specialist") as mock_run:
        mock_run.return_value.summary = "ok"
        _handle_specialist_task("qa specialist: are we ready for beta")
    task = mock_run.call_args[0][0]
    assert task.specialist_id == "qa"


def test_routes_documentation_keyword_to_documentation_specialist():
    with patch("thursday.specialists.run_grounded_specialist") as mock_run:
        mock_run.return_value.summary = "ok"
        _handle_specialist_task("documentation specialist, how's the launch tracker looking")
    task = mock_run.call_args[0][0]
    assert task.specialist_id == "documentation"


def test_routes_support_keyword_to_support_specialist():
    with patch("thursday.specialists.run_grounded_specialist") as mock_run:
        mock_run.return_value.summary = "ok"
        _handle_specialist_task("support specialist: what issues do customers hit")
    task = mock_run.call_args[0][0]
    assert task.specialist_id == "support"


def test_security_directed_ask_still_reaches_run_grounded_specialist():
    """A security-directed ask must not be silently dropped by the handler
    -- it should reach run_grounded_specialist and get its own honest
    abstain message, not a generic "which specialist?" non-answer."""
    with patch("thursday.specialists.run_grounded_specialist") as mock_run:
        mock_run.return_value.summary = "No real data source exists yet for the security specialist."
        result = _handle_specialist_task("ask the security specialist about our licensing")
    task = mock_run.call_args[0][0]
    assert task.specialist_id == "security"
    assert "no real data source" in result.lower()


def test_data_directed_ask_still_reaches_run_grounded_specialist():
    with patch("thursday.specialists.run_grounded_specialist") as mock_run:
        mock_run.return_value.summary = "No real data source exists yet for the data specialist."
        _handle_specialist_task("ask the data specialist for our analytics")
    task = mock_run.call_args[0][0]
    assert task.specialist_id == "data"


def test_no_specialist_named_asks_which_one():
    result = _handle_specialist_task("hello there")
    assert "which specialist" in result.lower()


def test_returns_the_specialist_result_summary_verbatim():
    with patch("thursday.specialists.run_grounded_specialist") as mock_run:
        mock_run.return_value.summary = "a very specific grounded answer"
        result = _handle_specialist_task("commercial specialist: pricing?")
    assert result == "a very specific grounded answer"


def test_real_end_to_end_commercial_specialist_no_llm_mock():
    """No mocking at all -- exercises the real gatherer + REGISTRY lookup +
    task construction, only short-circuited by an unconfigured LLM provider
    (which fails soft, matching run_grounded_specialist's own contract)."""
    import os

    old = os.environ.pop("THURSDAY_LLM_PROVIDER", None)
    try:
        os.environ["THURSDAY_LLM_PROVIDER"] = "none"
        result = _handle_specialist_task("ask the commercial specialist about pricing")
    finally:
        if old is not None:
            os.environ["THURSDAY_LLM_PROVIDER"] = old
        else:
            os.environ.pop("THURSDAY_LLM_PROVIDER", None)
    assert "evidence was gathered" in result.lower()
