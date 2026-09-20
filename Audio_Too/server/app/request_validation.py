"""Structural limits shared by JSON API request bodies."""

from __future__ import annotations

import math

MAX_JSON_DEPTH = 12
MAX_OBJECT_KEYS = 200
MAX_LIST_ITEMS = 1_000
MAX_STRING_CHARS = 100_000
MAX_KEY_CHARS = 100
MAX_NUMBER_MAGNITUDE = 1_000_000_000_000


def validate_json_payload(value: object, *, depth: int = 0) -> dict:
    if depth == 0 and not isinstance(value, dict):
        raise ValueError("JSON request body must be an object.")
    if depth > MAX_JSON_DEPTH:
        raise ValueError("JSON request body is nested too deeply.")
    if isinstance(value, dict):
        if len(value) > MAX_OBJECT_KEYS:
            raise ValueError("JSON object contains too many fields.")
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > MAX_KEY_CHARS:
                raise ValueError("JSON field name is invalid or too long.")
            validate_json_payload(child, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise ValueError("JSON list contains too many items.")
        for child in value:
            validate_json_payload(child, depth=depth + 1)
    elif isinstance(value, str):
        if len(value) > MAX_STRING_CHARS:
            raise ValueError("JSON string exceeds the configured limit.")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not math.isfinite(number) or abs(number) > MAX_NUMBER_MAGNITUDE:
            raise ValueError("JSON number is outside the configured range.")
    elif value is not None and not isinstance(value, bool):
        raise ValueError("JSON request contains an unsupported value.")
    return value if isinstance(value, dict) else {}
