"""Tests for thursday/specialists.py -- previously zero coverage. Focused on
the marketing specialist added 2026-09-05 and the route_task ordering fix
that makes "marketing" route correctly instead of being swallowed by the
bare "market" substring check for "research".
"""

from __future__ import annotations

from unittest.mock import MagicMock

from thursday.orchestration_models import SpecialistTask
from thursday.specialists import (
    DEFAULT_SPECIALISTS,
    REGISTRY,
    run_grounded_specialist,
    run_specialist_with_llm,
)


def test_marketing_specialist_is_registered():
    manifest = REGISTRY.get("marketing")
    assert manifest is not None
    assert "external_write" in manifest.required_approvals


def test_route_task_sends_marketing_objectives_to_marketing_not_research():
    assert REGISTRY.route_task("agent_tasks", "draft a marketing campaign for the launch") == "marketing"
    assert REGISTRY.route_task("agent_tasks", "write outreach to a new lead") == "marketing"
    assert REGISTRY.route_task("agent_tasks", "draft a social post about our rates") == "marketing"


def test_route_task_still_sends_bare_market_analysis_to_research():
    assert REGISTRY.route_task("agent_tasks", "do a market analysis of competitors") == "research"


def test_every_default_specialist_has_a_unique_id():
    ids = [s.specialist_id for s in DEFAULT_SPECIALISTS]
    assert len(ids) == len(set(ids))


def _task(specialist_id="commercial") -> SpecialistTask:
    return SpecialistTask(
        task_id="t1", parent_objective_id="o1", specialist_id=specialist_id,
        task_type="LIGHT", objective="Summarize this quarter's invoices", scope="commercial_sandbox",
    )


def test_run_specialist_with_llm_parses_real_content_not_the_result_object(monkeypatch):
    """Regression test for the .strip()-on-LLMResult bug found 2026-09-08:
    the provider returns an object with .content, not a plain string --
    this must extract .content before parsing, not call string methods
    on the result object itself. Rewired 2026-09-18 to mock the provider
    (thursday.llm_provider.get_llm_provider) instead of a fake
    audio_too.model_runtime module, because run_specialist_with_llm now
    goes through the provider abstraction like every other call site."""
    payload = '{"status": "SUCCESS", "summary": "Invoices look healthy", "confidence": 0.9}'
    _install_fake_llm_provider(monkeypatch, content=payload)

    result = run_specialist_with_llm(_task())
    assert result.status == "SUCCESS"
    assert result.summary == "Invoices look healthy"
    assert result.confidence == 0.9
    assert result.failures == []


def test_run_specialist_with_llm_strips_markdown_fences_from_content(monkeypatch):
    payload = '```json\n{"status": "SUCCESS", "summary": "ok"}\n```'
    _install_fake_llm_provider(monkeypatch, content=payload)

    result = run_specialist_with_llm(_task())
    assert result.status == "SUCCESS"
    assert result.summary == "ok"


def test_run_specialist_with_llm_uses_provider_timeout(monkeypatch):
    """Proves the audit fix: timeout comes from default_timeout() (env),
    not the old hardcoded 15."""
    import os
    from thursday import llm_provider as lp
    os.environ["THURSDAY_LLM_TIMEOUT"] = "7"
    lp.reset_provider_cache()
    try:
        fake_provider = _install_fake_llm_provider(monkeypatch, content='{"status": "SUCCESS", "summary": "ok"}')
        result = run_specialist_with_llm(_task())
        assert result.status == "SUCCESS"
        _, kwargs = fake_provider.generate.call_args
        assert kwargs.get("timeout") == 7.0
    finally:
        del os.environ["THURSDAY_LLM_TIMEOUT"]
        lp.reset_provider_cache()


def test_run_specialist_with_llm_fails_softly_when_provider_errors(monkeypatch):
    """Renamed 2026-09-18 (was ..._when_audio_too_missing): the function
    no longer imports audio_too directly, so the fail-soft path is a
    provider error, not an ImportError. Same contract: FAILED + cause."""
    _install_fake_llm_provider(monkeypatch, side_effect=RuntimeError("backend down"))
    result = run_specialist_with_llm(_task())
    assert result.status == "FAILED"
    assert "backend down" in result.summary


def test_run_specialist_with_llm_fails_softly_on_malformed_json(monkeypatch):
    _install_fake_llm_provider(monkeypatch, content="not json at all")
    result = run_specialist_with_llm(_task())
    assert result.status == "FAILED"
    assert result.failures


# ─── run_grounded_specialist (2026-09-08) ──────────────────────────────────
# These mock only the LLM provider, not the ops modules -- finance_ops,
# support_ops, documentation_ops, doc_search_ops, and qa_ops are all
# deterministic and safe to call for real in a test, and calling them for
# real is exactly what proves the gatherer wiring is correct rather than
# just asserting a mock was called.

def _install_fake_llm_provider(monkeypatch, content=None, side_effect=None):
    fake_provider = MagicMock()
    if side_effect is not None:
        fake_provider.generate.side_effect = side_effect
    else:
        fake_provider.generate.return_value = MagicMock(content=content)
    import thursday.specialists as specialists_module
    monkeypatch.setattr("thursday.llm_provider.get_llm_provider", lambda: fake_provider)
    return fake_provider


def _grounded_task(specialist_id: str, objective: str = "test objective") -> SpecialistTask:
    return SpecialistTask(
        task_id="t1", parent_objective_id="o1", specialist_id=specialist_id,
        task_type="LIGHT", objective=objective, scope="test_scope",
    )


def test_security_and_data_abstain_with_zero_llm_calls(monkeypatch):
    fake_provider = _install_fake_llm_provider(monkeypatch, content="should never be called")
    for specialist_id in ("security", "data"):
        result = run_grounded_specialist(_grounded_task(specialist_id))
        assert result.status == "ABSTAINED"
        assert "no real data source" in result.summary.lower()
        assert result.confidence == 0.0
    fake_provider.generate.assert_not_called()


def test_commercial_gathers_real_pricing_evidence(monkeypatch):
    _install_fake_llm_provider(monkeypatch, content="We charge from £180 for mixing.")
    result = run_grounded_specialist(_grounded_task("commercial", "what do we charge for mixing"))
    assert result.status == "SUCCESS"
    assert result.summary == "We charge from £180 for mixing."
    assert "PRICING SUMMARY" in result.evidence["raw"]


def test_qa_gathers_real_beta_readiness_evidence(monkeypatch):
    _install_fake_llm_provider(monkeypatch, content="Not ready yet.")
    result = run_grounded_specialist(_grounded_task("qa", "are we ready for beta"))
    assert result.status == "SUCCESS"
    assert "BETA READINESS" in result.evidence["raw"] or "Evidence missing" in result.evidence["raw"]


def test_support_gathers_real_faq_and_known_issues_evidence(monkeypatch):
    _install_fake_llm_provider(monkeypatch, content="Here's what's known.")
    result = run_grounded_specialist(_grounded_task("support", "what issues do customers hit"))
    assert result.status == "SUCCESS"
    assert result.evidence["raw"]  # real support_ops output, whatever it currently says


def test_documentation_gathers_real_tracker_and_search_evidence(monkeypatch):
    _install_fake_llm_provider(monkeypatch, content="Here's the doc status.")
    result = run_grounded_specialist(_grounded_task("documentation", "how is the launch tracker looking"))
    assert result.status == "SUCCESS"
    assert "LAUNCH TRACKER" in result.evidence["raw"]
    assert "DOC SEARCH RESULTS" in result.evidence["raw"]


def test_grounded_specialist_llm_failure_still_returns_gathered_evidence(monkeypatch):
    _install_fake_llm_provider(monkeypatch, side_effect=RuntimeError("timed out"))
    result = run_grounded_specialist(_grounded_task("commercial", "pricing?"))
    assert result.status == "FAILED"
    assert "PRICING SUMMARY" in result.evidence["raw"]  # real evidence not lost
    assert "timed out" in result.summary.lower()


def test_grounded_specialist_never_calls_the_old_generic_llm_prompt_style(monkeypatch):
    """The grounded path's prompt must include the real evidence, not ask
    the LLM to invent the whole result the way run_specialist_with_llm does."""
    fake_provider = _install_fake_llm_provider(monkeypatch, content="ok")
    run_grounded_specialist(_grounded_task("commercial", "pricing?"))
    messages = fake_provider.generate.call_args[0][0]
    combined = " ".join(m["content"] for m in messages)
    assert "PRICING SUMMARY" in combined
    assert "never invent" in combined.lower() or "only that evidence" in combined.lower()


def test_specialist_timeout_policy_floor_and_env(monkeypatch):
    """Single policy (2026-09-18 unification): env floor via
    default_timeout(), minimum 90s for evidence-sized prompts."""
    import os
    from thursday import llm_provider as lp
    from thursday.specialists import specialist_timeout
    for k in ("THURSDAY_LLM_TIMEOUT", "AUDIO_TOO_LLM_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    lp.reset_provider_cache()
    assert specialist_timeout() == 90.0
    monkeypatch.setenv("THURSDAY_LLM_TIMEOUT", "120")
    lp.reset_provider_cache()
    assert specialist_timeout() == 120.0
    lp.reset_provider_cache()
