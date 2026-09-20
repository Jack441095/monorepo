"""Structured error taxonomy and bounded retry policy contracts.

Errors are data, never prose. Retry policies are declarative contracts —
this module implements no execution loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nite_ai._serialization import dataclass_to_dict


class ErrorCategory(str, Enum):
    INVALID_INPUT = "invalid_input"
    NOT_SUPPORTED = "not_supported"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_FAILURE = "model_failure"
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_LIMIT = "resource_limit"
    VALIDATION_FAILURE = "validation_failure"
    INTERNAL_ERROR = "internal_error"


RETRYABLE_CATEGORIES = frozenset(
    {
        ErrorCategory.DEPENDENCY_UNAVAILABLE,
        ErrorCategory.MODEL_UNAVAILABLE,
        ErrorCategory.MODEL_FAILURE,
        ErrorCategory.TOOL_FAILURE,
        ErrorCategory.TIMEOUT,
        ErrorCategory.RESOURCE_LIMIT,
    }
)


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AgentError:
    """Structured error. `category` is the stable machine code."""

    category: ErrorCategory
    message: str
    retryable: bool | None = None  # None -> derive from category
    user_facing: bool = False
    severity: Severity = Severity.MEDIUM
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message:
            raise ValidationError("AgentError.message must not be empty")
        if self.retryable is None:
            object.__setattr__(self, "retryable", self.category in RETRYABLE_CATEGORIES)

    @property
    def code(self) -> str:
        return self.category.value

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry declaration. No execution logic lives here."""

    max_attempts: int = 3
    strategy: str = "exponential"  # "fixed" | "exponential"
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 30.0
    retryable_categories: tuple[ErrorCategory, ...] = tuple(sorted(RETRYABLE_CATEGORIES))
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise ValidationError("RetryPolicy.max_attempts must be within 1..10 (no infinite retries)")
        if self.strategy not in {"fixed", "exponential"}:
            raise ValidationError("RetryPolicy.strategy must be 'fixed' or 'exponential'")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValidationError("RetryPolicy backoff values must be non-negative")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValidationError("RetryPolicy.max_backoff_seconds must be >= initial_backoff_seconds")
        if self.timeout_seconds <= 0:
            raise ValidationError("RetryPolicy.timeout_seconds must be > 0")

    def is_retryable(self, error: AgentError) -> bool:
        if not error.retryable:
            return False
        return error.category in self.retryable_categories

    def backoff_for_attempt(self, attempt: int) -> float:
        """Backoff before the given 1-based retry attempt. Bounded, never infinite."""
        if attempt <= 1:
            return 0.0
        if self.strategy == "fixed":
            return self.initial_backoff_seconds
        return min(
            self.max_backoff_seconds,
            self.initial_backoff_seconds * (2 ** (attempt - 2)),
        )


class ValidationError(ValueError):
    """Raised when contract invariants are violated at construction time."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error = AgentError(
            category=ErrorCategory.VALIDATION_FAILURE, message=message, user_facing=False
        )


class DuplicateRegistrationError(ValidationError):
    def __init__(self, identifier: str, kind: str = "capability") -> None:
        super().__init__(f"duplicate {kind} id already registered: {identifier}")


__all__ = [
    "AgentError",
    "DuplicateRegistrationError",
    "ErrorCategory",
    "RETRYABLE_CATEGORIES",
    "RetryPolicy",
    "Severity",
    "ValidationError",
]
