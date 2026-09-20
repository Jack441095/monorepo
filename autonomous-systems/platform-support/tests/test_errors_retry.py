"""Tests for error taxonomy and retry policy primitives."""

import pytest

from nite_ai.errors import AgentError, ErrorCategory, RetryPolicy, Severity, ValidationError


def test_retryable_defaults_derived_from_category() -> None:
    assert AgentError(ErrorCategory.TIMEOUT, "timed out").retryable is True
    assert AgentError(ErrorCategory.INVALID_INPUT, "bad").retryable is False


def test_error_code_is_machine_stable() -> None:
    err = AgentError(ErrorCategory.MODEL_UNAVAILABLE, "provider down", severity=Severity.HIGH)
    assert err.code == "model_unavailable"
    d = err.to_dict()
    assert d["category"] == "model_unavailable"
    assert d["severity"] == "high"


def test_empty_message_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentError(ErrorCategory.INTERNAL_ERROR, "")


def test_retry_policy_bounds() -> None:
    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=11)
    with pytest.raises(ValidationError):
        RetryPolicy(timeout_seconds=0)


def test_exponential_backoff_bounded() -> None:
    policy = RetryPolicy(max_attempts=6, initial_backoff_seconds=1.0, max_backoff_seconds=4.0)
    assert policy.backoff_for_attempt(1) == 0.0
    assert policy.backoff_for_attempt(2) == 1.0
    assert policy.backoff_for_attempt(3) == 2.0
    assert policy.backoff_for_attempt(4) == 4.0
    assert policy.backoff_for_attempt(5) == 4.0  # capped — never unbounded


def test_policy_respects_error_category() -> None:
    policy = RetryPolicy(retryable_categories=(ErrorCategory.TIMEOUT,))
    assert policy.is_retryable(AgentError(ErrorCategory.TIMEOUT, "t"))
    assert not policy.is_retryable(AgentError(ErrorCategory.MODEL_FAILURE, "m"))
    assert not policy.is_retryable(
        AgentError(ErrorCategory.TIMEOUT, "t", retryable=False)
    )
