"""Tests for thursday/response_rewrite.py -- the opt-in conversational
polish pass over Thursday's mechanical, deterministic service replies."""

from __future__ import annotations

from nite_core.model_runtime import LLMResult
from thursday import response_rewrite
from thursday.formatter import format_response


def _mock_generate(content: str):
    def _generate(messages, timeout=10, response_schema=None, json_mode=True):
        return LLMResult(content=content, model="mock-model", usage={})
    return _generate


def _exploding_generate(*a, **k):
    raise AssertionError("must not call the LLM in this scenario")


def test_disabled_by_default_does_not_call_the_llm(monkeypatch):
    monkeypatch.delenv("THURSDAY_CONVERSATIONAL_REPLIES", raising=False)
    monkeypatch.setattr(response_rewrite.DEFAULT_LLM, "generate", _exploding_generate)

    assert response_rewrite.rewrite("how's business?", "  Revenue: 500", "Business Status") is None


def test_returns_none_when_no_question_given(monkeypatch):
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(response_rewrite.DEFAULT_LLM, "generate", _exploding_generate)

    assert response_rewrite.rewrite("", "  Revenue: 500", "Business Status") is None


def test_accepts_a_grounded_rewrite(monkeypatch):
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("You've pulled in 500 so far this month."),
    )

    result = response_rewrite.rewrite("how's business?", "  Revenue: 500", "Business Status")

    assert result == "You've pulled in 500 so far this month."


def test_calls_the_llm_in_plain_text_mode_not_json_mode(monkeypatch):
    """This feature must never force JSON-object output the way brain.py's
    structured decisions do -- that would fight a natural-language prompt.
    See audio_too/model_runtime.py's json_mode parameter."""
    captured = {}

    def _generate(messages, timeout=10, response_schema=None, json_mode=True):
        captured["json_mode"] = json_mode
        captured["response_schema"] = response_schema
        return LLMResult(content="You've pulled in 500 so far this month.", model="mock", usage={})

    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(response_rewrite.DEFAULT_LLM, "generate", _generate)

    response_rewrite.rewrite("how's business?", "  Revenue: 500", "Business Status")

    assert captured["json_mode"] is False
    assert captured["response_schema"] is None


def test_accepts_a_rewrite_that_only_adds_thousand_separator_commas(monkeypatch):
    """Regression (live-tested 2026-08-02 against the real local Ollama model):
    the LLM wrote "1,250" for a raw value of "1250" -- same number, just
    formatted for readability. The grounding check must not treat comma
    reformatting as a hallucinated new number."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("You've pulled in 1,250 so far this month."),
    )

    result = response_rewrite.rewrite(
        "how's business going?", "  Revenue This Month: 1250", "Business Status"
    )

    assert result == "You've pulled in 1,250 so far this month."


def test_rejects_a_rewrite_that_introduces_an_unsupported_number(monkeypatch):
    """The grounding safety net: a rewrite may not state any number that
    wasn't already in the raw service data -- mirrors KENN's own rejection
    of unsupported measurements (studio/kenn/kenn/core/chat_grounding.py)."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("You've pulled in 5000 so far this month."),  # hallucinated digit
    )

    result = response_rewrite.rewrite("how's business?", "  Revenue: 500", "Business Status")

    assert result is None


def test_accepts_a_number_immediately_followed_by_a_sentence_period(monkeypatch):
    """Regression (live-tested 2026-08-02): "...in revenue." was captured by
    the number regex as "1250." (trailing full stop included), which never
    matched raw text's "1250" and caused a false rejection."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("We brought in $1250 in revenue."),
    )

    result = response_rewrite.rewrite(
        "how's business going?", "  Revenue This Month: 1250", "Business Status"
    )

    assert result == "We brought in $1250 in revenue."


def test_rejects_a_rewrite_that_changes_a_count_using_a_spelled_out_number(monkeypatch):
    """Regression (live-tested 2026-08-02 against the real local Ollama
    model): asked to restate "Active Clients: 4", it wrote "five active
    clients" in one run -- a wrong fact using a spelled-out number the
    digit-only grounding check can't see at all."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("You've got five active clients right now."),
    )

    result = response_rewrite.rewrite(
        "how's business going?", "  Active Clients: 4", "Business Status"
    )

    assert result is None


def test_accepts_a_correctly_spelled_out_number_that_matches_the_raw_data(monkeypatch):
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("You've got four active clients right now."),
    )

    result = response_rewrite.rewrite(
        "how's business going?", "  Active Clients: 4", "Business Status"
    )

    assert result == "You've got four active clients right now."


def test_rejects_a_rewrite_that_invents_a_time_comparison(monkeypatch):
    """Regression (live-tested 2026-08-02, second run against the real local
    model, after the first trend-marker list already shipped): "The
    revenue's up from a few weeks ago" slipped past the first version of
    _TREND_MARKERS ("up from" / "a few weeks ago" weren't covered yet)."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("The revenue's up from a few weeks ago at 1250."),
    )

    result = response_rewrite.rewrite(
        "how's business going?", "  Revenue This Month: 1250", "Business Status"
    )

    assert result is None


def test_rejects_a_bare_directional_claim(monkeypatch):
    """Regression (live-tested 2026-08-02, third pass): "client count and
    revenue are up!" -- not caught by the phrase-based _TREND_MARKERS list
    (which looks for "up by"/"up from", not a bare "are up" predicate)."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("Jack, client count and revenue are up! Two invoices pending."),
    )

    result = response_rewrite.rewrite(
        "how's business going?", "  Active Clients: 4\n  Pending Invoices: 2", "Business Status"
    )

    assert result is None


def test_does_not_reject_unrelated_uses_of_up(monkeypatch):
    """The directional-predicate check is scoped to an is/are/looks + up/down
    predicate, not a bare "up" substring -- must not reject harmless phrasing
    like "signed up" or "up next"."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("You've got 4 active clients signed up this month."),
    )

    result = response_rewrite.rewrite(
        "how's business going?", "  Active Clients: 4", "Business Status"
    )

    assert result == "You've got 4 active clients signed up this month."


def test_does_not_reject_up_to_date_or_up_for_renewal(monkeypatch):
    """Code-review finding (2026-08-02): the initial directional-predicate
    regex matched "is up to date" and "is up for renewal" -- plausible,
    non-trend business phrasing in exactly this domain (invoices, contracts)
    that isn't a directional claim at all. Both must be accepted."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")

    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("Your invoice for 2 items is up to date."),
    )
    assert (
        response_rewrite.rewrite("are my invoices current?", "  Pending Invoices: 2", "Business Status")
        == "Your invoice for 2 items is up to date."
    )

    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("The contract for 2 items is up for renewal."),
    )
    assert (
        response_rewrite.rewrite("what's my contract status?", "  Pending Invoices: 2", "Business Status")
        == "The contract for 2 items is up for renewal."
    )


def test_rejects_a_rewrite_that_invents_a_trend_using_spelled_out_numbers(monkeypatch):
    """Regression (live-tested 2026-08-02 against the real local Ollama
    model): given a flat, single-snapshot revenue figure, the model
    fabricated "moving past the halfway point" and "a bump up by twenty
    five thousand dollars" -- a false trend claim using spelled-out numbers,
    which the digit-only grounding check can't see at all."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate(
            "We're moving past the halfway point with a bump up by twenty five thousand dollars."
        ),
    )

    result = response_rewrite.rewrite(
        "how's business going?", "  Revenue This Month: 1250", "Business Status"
    )

    assert result is None


def test_rejects_empty_llm_output(monkeypatch):
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(response_rewrite.DEFAULT_LLM, "generate", _mock_generate("   "))

    assert response_rewrite.rewrite("how's business?", "  Revenue: 500", "Business Status") is None


def test_llm_call_failure_degrades_to_none_not_a_crash(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network blip")

    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(response_rewrite.DEFAULT_LLM, "generate", _boom)

    assert response_rewrite.rewrite("how's business?", "  Revenue: 500", "Business Status") is None


# ─── format_response() wiring ──────────────────────────────────────────────


def test_format_response_without_question_never_attempts_a_rewrite(monkeypatch):
    """The overwhelming majority of format_response() callers don't pass
    question= at all -- must be byte-for-byte the pre-existing behaviour."""
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(response_rewrite.DEFAULT_LLM, "generate", _exploding_generate)

    result = format_response({"revenue": 500}, "Business Status", "business_status", {})
    assert "Revenue: 500" in result


def test_format_response_uses_the_rewrite_when_question_is_given_and_grounded(monkeypatch):
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("You've pulled in 500 so far this month."),
    )

    result = format_response(
        {"revenue": 500}, "Business Status", "business_status", {}, question="how's business?"
    )

    assert "You've pulled in 500 so far this month." in result
    assert "Revenue: 500" not in result  # mechanical rendering was replaced, not appended


def test_format_response_falls_back_to_mechanical_text_when_rewrite_is_rejected(monkeypatch):
    monkeypatch.setenv("THURSDAY_CONVERSATIONAL_REPLIES", "1")
    monkeypatch.setattr(
        response_rewrite.DEFAULT_LLM,
        "generate",
        _mock_generate("You've pulled in 5000 so far this month."),  # hallucinated
    )

    result = format_response(
        {"revenue": 500}, "Business Status", "business_status", {}, question="how's business?"
    )

    assert "Revenue: 500" in result
    assert "5000" not in result
