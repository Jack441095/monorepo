"""Validate observed raw parameters and bind the exact mutation to confirmation."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def indexed_parameter(parameters: list[dict], index: int) -> dict | None:
    """Resolve an exposed index; only wholly unindexed legacy lists are positional."""
    if not isinstance(parameters, list) or any(not isinstance(row, dict) for row in parameters):
        # Truncated or malformed lists cannot establish a target, even when one row looks valid.
        return None
    if any("index" in row for row in parameters):
        matches = [row for row in parameters if row.get("index") == index]
        # A partial or duplicate index list cannot identify one control.
        return matches[0] if len(matches) == 1 else None
    return parameters[index] if 0 <= index < len(parameters) else None


def validate_parameter(parameter: dict, requested: Any, *, device_name: str = "") -> str | None:
    """Return a refusal for incomplete metadata, protected controls or invalid raw values."""
    try:
        if isinstance(requested, bool):
            return "A boolean is not a raw parameter value."
        current, low, high = (float(parameter[key]) for key in ("value", "min", "max"))
        value = float(requested)
    except (KeyError, TypeError, ValueError):
        # Missing bounds are not a normalized range: a physical knob may use any raw law.
        return "Live returned incomplete numeric parameter metadata; inspect again."
    if not all(math.isfinite(item) for item in (current, low, high, value)) or low > high:
        return "Live returned non-finite or invalid parameter bounds."
    if not low <= current <= high or not low <= value <= high:
        return f"Requested or current raw value is outside valid range [{low:g}, {high:g}] reported by Live."
    if not str(parameter.get("name") or "").strip():
        return "Live returned no parameter name."
    if parameter.get("is_enabled") is False or parameter.get("state") in {1, 2, "disabled", "irrelevant"}:
        return "That parameter is disabled or irrelevant in Live."
    if parameter.get("automation_state") not in (None, 0, "none"):
        return "That parameter has automation; KENN will not override it."
    if parameter.get("macro_controlled") is True:
        return "That parameter is controlled by a macro; change the exposed macro instead."
    choices = parameter.get("choices")
    if choices is not None:
        try:
            options = [float(row["raw"]) for row in choices]
        except (KeyError, TypeError, ValueError):
            # Partial options cannot prove that the requested raw value belongs to this chooser.
            return "Live returned incomplete chooser metadata."
        if not options or any(not math.isfinite(item) for item in options) or value not in options:
            return "That raw value is not an exposed chooser option."
    elif parameter.get("quantized") is True and value not in {current, low, high}:
        # Bounds expose endpoints, not contiguous intermediate chooser positions or integer steps.
        # Legacy bulk reads omit options; only the existing measured profile can supply them.
        from kenn.core.device_units import find_choice

        qualified = find_choice(device_name, parameter["name"]) if device_name else None
        if qualified and value in {raw for raw, _label in qualified.options}:
            return None
        return "That quantized parameter requires a qualified raw option table for intermediate values."
    return None


def parameter_guard(parameter: dict) -> dict:
    """Capture semantics that must remain unchanged between proposal and Apply."""
    return {key: parameter.get(key) for key in (
        "name", "min", "max", "quantized", "choices", "is_enabled", "state",
        "automation_state", "macro_controlled",
    )}


def _same_number_same_json(value: Any) -> Any:
    """`value` with every number as a float, so an equal number always serialises the same way."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        # 0.0 for -0.0 too, as confirmation._canonical_number does: JSON.stringify writes -0 as 0.
        return 0.0 if value == 0 else float(value)
    if isinstance(value, dict):
        return {key: _same_number_same_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_same_number_same_json(item) for item in value]
    return value


def device_confirmation_text(proposal: dict) -> str:
    """Bind identity, before-state and semantics as well as the requested raw value."""
    fields = {key: proposal.get(key) for key in (
        "id", "operation", "target", "track_index", "track_name", "device_index",
        "device_name", "parameter_index", "parameter", "before", "after",
        "unit", "valid_range", "parameter_guard", "target_address", "topology", "observation_token",
        "target_label", "before_label", "after_label", "before_display", "after_display",
    )}
    # This many fields would make plain text long, so we bind a digest of them instead. The cost is that the
    # digest is opaque to confirmation._request_hash, which makes equal numbers agree only by rewriting them in
    # plain text. So we make them agree here first. The browser echoes the proposal through JSON.stringify,
    # which writes 1.0 as 1, so `valid_range` [0.0, 1.0] came back as ints [0, 1]. Until 11 Oct that changed the
    # digest and refused every device Apply from the web UI, while a Python round trip in the tests passed.
    fields = _same_number_same_json(fields)
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return f"set_device_parameter:{digest}"


def target_address(address: dict) -> dict:
    """Validate a topology position, without pretending it is a persistent host ID."""
    if not isinstance(address, dict) or set(address) != {"kind", "index", "device_path"}:
        raise ValueError("A target requires kind, index and device_path.")
    kind, index, path = address["kind"], address["index"], address["device_path"]
    if kind not in {"track", "return", "master"} or type(index) is not int or index < 0:
        raise ValueError("Target bus kind or index is invalid.")
    if kind == "master" and index != 0:
        raise ValueError("The master bus index must be zero.")
    # Alternating device/chain/device indices allow four nested chains (nine positions).
    if not isinstance(path, list) or not 1 <= len(path) <= 9 or len(path) % 2 != 1:
        raise ValueError("device_path must alternate device and chain indices.")
    if any(type(item) is not int or item < 0 for item in path):
        raise ValueError("Target positions must be non-negative integers.")
    return {"kind": kind, "index": index, "device_path": list(path)}
