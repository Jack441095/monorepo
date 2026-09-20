"""Retry/backoff for transient service and subagent failures.

This is a synchronous, single-process app driving a live conversation, not a
distributed batch system — retries here exist to smooth over one flaky call
(a timed-out LLM ping, a dropped connection), not to paper over real bugs.
Validation, permission, and logic errors are never retried: retrying a bad
output doesn't fix it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, TypeVar

from nite_core import PublicError

T = TypeVar("T")

# Exception types treated as transient by default (network/timeout-shaped).
_TRANSIENT_EXCEPTION_TYPES: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    OSError,
)


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry schedule. Small on purpose — see module docstring."""

    max_attempts: int = 2
    backoff_seconds: tuple[float, ...] = (0.5, 2.0)


DEFAULT_RETRY_POLICY = RetryPolicy()


def is_retryable(exc: BaseException) -> bool:
    """Classify whether retrying after `exc` is likely to help.

    `PublicError` subclasses (e.g. `ServiceExecutionError`) carry an explicit
    `retryable` flag — honor it. Anything else is retried only if it looks
    like a transient network/timeout failure.
    """
    if isinstance(exc, PublicError):
        return bool(exc.details.retryable)
    return isinstance(exc, _TRANSIENT_EXCEPTION_TYPES)


def with_retry(
    fn: Callable[[], T],
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `fn()`, retrying on transient failures per `policy`.

    Re-raises the last exception once attempts are exhausted, or immediately
    if the failure doesn't classify as retryable.
    """
    last_exc: BaseException | None = None
    for attempt in range(policy.max_attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            is_last_attempt = attempt == policy.max_attempts - 1
            if not is_retryable(exc) or is_last_attempt:
                raise
            delay_index = min(attempt, len(policy.backoff_seconds) - 1)
            sleep(policy.backoff_seconds[delay_index])
    assert last_exc is not None  # loop always returns or raises
    raise last_exc
