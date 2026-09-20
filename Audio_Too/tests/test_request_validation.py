"""Structural request limits shared by API servers."""

from __future__ import annotations

import pytest

import request_validation


def test_accepts_bounded_json_object() -> None:
    payload = {"question": "hello", "history": [{"role": "user", "content": "hi"}]}
    assert request_validation.validate_json_payload(payload) is payload


@pytest.mark.parametrize(
    "payload, message",
    [
        (["not", "an", "object"], "must be an object"),
        ({"items": [0] * 1001}, "too many items"),
        ({"text": "x" * 100_001}, "string exceeds"),
        ({"number": float("inf")}, "outside"),
        ({"number": 10**13}, "outside"),
        ({"x" * 101: "value"}, "field name"),
    ],
)
def test_rejects_unbounded_json_shapes(payload, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        request_validation.validate_json_payload(payload)


def test_rejects_excessive_depth() -> None:
    payload: dict = {}
    cursor = payload
    for _ in range(14):
        cursor["child"] = {}
        cursor = cursor["child"]
    with pytest.raises(ValueError, match="deeply"):
        request_validation.validate_json_payload(payload)
