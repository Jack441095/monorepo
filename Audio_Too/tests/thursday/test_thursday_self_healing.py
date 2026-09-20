"""Tests for Thursday Phase 1: Autonomous Self-Healing & Process Supervision Loop."""

import time
from unittest.mock import MagicMock, patch


from thursday.diagnostics import CircuitBreaker, auto_heal_subsystems
from thursday.brain import decide, BrainDecision


def test_circuit_breaker_rate_limiting():
    cb = CircuitBreaker(max_attempts=2, cooldown_seconds=10.0)
    key = "test_service"

    assert cb.allow(key) is True
    cb.record_attempt(key)
    assert cb.allow(key) is True
    cb.record_attempt(key)
    
    # 3rd attempt within cooldown window should be blocked
    assert cb.allow(key) is False

    # Reset allows again
    cb.reset(key)
    assert cb.allow(key) is True


def test_circuit_breaker_cooldown_expiration():
    cb = CircuitBreaker(max_attempts=1, cooldown_seconds=0.1)
    key = "cooldown_service"

    assert cb.allow(key) is True
    cb.record_attempt(key)
    assert cb.allow(key) is False

    # Wait for cooldown to expire
    time.sleep(0.15)
    assert cb.allow(key) is True


@patch("thursday.diagnostics.check_all_systems")
@patch("thursday.diagnostics.try_fix")
def test_auto_heal_subsystems_all_healthy(mock_try_fix, mock_check_all):
    mock_check_all.return_value = {
        "all_healthy": True,
        "checks": [{"name": "Website Server", "healthy": True}],
    }
    res = auto_heal_subsystems()
    assert res["healed"] is True
    assert len(res["remediations"]) == 0
    mock_try_fix.assert_not_called()


@patch("thursday.diagnostics.check_all_systems")
@patch("thursday.diagnostics.try_fix")
def test_auto_heal_subsystems_remediation(mock_try_fix, mock_check_all):
    unhealthy = {
        "all_healthy": False,
        "checks": [{"name": "Website Server", "healthy": False}],
    }
    healthy = {
        "all_healthy": True,
        "checks": [{"name": "Website Server", "healthy": True}],
    }
    mock_check_all.side_effect = [unhealthy, healthy]
    mock_try_fix.return_value = {"ok": True, "action": "restarted", "message": "Website server restarted."}

    cb = CircuitBreaker(max_attempts=3, cooldown_seconds=600.0)
    res = auto_heal_subsystems(circuit_breaker=cb)

    assert res["healed"] is True
    assert len(res["remediations"]) == 1
    assert res["remediations"][0]["action"] == "restarted"


@patch("thursday.brain.DEFAULT_LLM")
def test_brain_llm_fallback_chain_on_error(mock_llm):
    mock_llm.generate.side_effect = Exception("Primary model connection failed")

    session = {"turns": []}
    services = {"search": MagicMock(description="search service", triggers=["search"])}
    subagents = ["admin"]

    decision = decide(session, services, subagents, "search for Jordan")

    assert isinstance(decision, BrainDecision)
    assert decision.type == "abstain"
    assert "LLM call failed" in decision.abstract
    # Generate should have been attempted twice (primary + fallback)
    assert mock_llm.generate.call_count == 2
