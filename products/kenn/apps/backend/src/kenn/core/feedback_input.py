"""Strict parsing for optional supervised-session feedback fields."""

from __future__ import annotations

import math
from typing import Any


class FeedbackInputError(ValueError):
    """Raised when a supplied feedback field is malformed or out of range."""


def optional_rating(value: Any) -> int | None:
    """Return a documented 1–5 rating, preserving omitted values as ``None``."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise FeedbackInputError("explicit_rating must be an integer from 1 to 5")
    try:
        rating = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise FeedbackInputError("explicit_rating must be an integer from 1 to 5") from exc
    if rating < 1 or rating > 5:
        raise FeedbackInputError("explicit_rating must be an integer from 1 to 5")
    return rating


def optional_bool(value: Any, *, field: str) -> bool | None:
    """Parse a JSON/native or conventional string boolean without coercion traps."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    raise FeedbackInputError(f"{field} must be a boolean")


def optional_nonnegative_float(value: Any, *, field: str, maximum: float = 86400.0) -> float | None:
    """Parse bounded duration telemetry without accepting NaN or infinity."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise FeedbackInputError(f"{field} must be a non-negative number") from exc
    if not math.isfinite(parsed) or parsed < 0 or parsed > maximum:
        raise FeedbackInputError(f"{field} must be between 0 and {int(maximum)} seconds")
    return parsed


__all__ = ["FeedbackInputError", "optional_bool", "optional_nonnegative_float", "optional_rating"]
