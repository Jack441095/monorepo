from __future__ import annotations

import pytest

from kenn.core.feedback_input import (
    FeedbackInputError,
    optional_bool,
    optional_nonnegative_float,
    optional_rating,
)


def test_feedback_input_accepts_documented_values() -> None:
    assert optional_rating(None) is None
    assert optional_rating("5") == 5
    assert optional_rating(1) == 1
    assert optional_bool("false", field="has_followup") is False
    assert optional_bool(1, field="has_followup") is True
    assert optional_nonnegative_float("12.5", field="dwell_seconds") == 12.5


@pytest.mark.parametrize("value", [0, 6, -1, True, "not-a-rating"])
def test_feedback_input_rejects_invalid_ratings(value) -> None:
    with pytest.raises(FeedbackInputError):
        optional_rating(value)


@pytest.mark.parametrize("value", ["maybe", 2, object()])
def test_feedback_input_rejects_ambiguous_booleans(value) -> None:
    with pytest.raises(FeedbackInputError):
        optional_bool(value, field="has_followup")


@pytest.mark.parametrize("value", [-1, "nan", "inf", 86401])
def test_feedback_input_rejects_invalid_durations(value) -> None:
    with pytest.raises(FeedbackInputError):
        optional_nonnegative_float(value, field="dwell_seconds")
