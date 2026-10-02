"""Device-parameter reads and writes, and the miss when nothing matched.

``live_command.DEVICE_PARAMETER_ACTIONS`` plus the ``inspect_device_parameters``
read. This is the tail of the chain, reached only when the track rules found no
scalar change, so a request naming both a fader move and a compressor move
proposes the fader move and nothing else.

Lifted verbatim out of ``live_intent._parse_request_rules``.
"""

from __future__ import annotations

import re
from typing import Any

from kenn.core.live_intent import (
    _DEVICE_PARAMETER_ACTION,
    _NUMBER,
    _choice_request,
    _display_unit_error,
    _eq_band_qualified_parameter,
    _generic_device_parameter_match,
)


def resolve_device_rules(
    base: dict[str, Any],
    track: dict[str, Any],
    lower: str,
    inspect_device_parameters_match: Any,
) -> dict[str, Any]:
    """Always returns: reaching here with nothing found is the generic miss."""
    device_candidates = []
    for device_index, device in enumerate(track.get("devices", []) or []):
        if isinstance(device, dict):
            name = str(device.get("name", ""))
            device_candidates.append((device_index, name))
        else:
            device_candidates.append((device_index, str(device)))
    device = next(((index, name) for index, name in device_candidates if name and name.lower() in lower), None)
    if device is None and re.search(r"\b(?:threshold|ratio|attack|release|frequency|gain|q)\b", lower):
        base["missing_fields"].append("device")
        base["ambiguity"].append("I couldn't find that device on the track. Name the device as it appears in Live.")
        return base
    if device is not None:
        base["device"] = {"index": device[0], "name": device[1]}
    if inspect_device_parameters_match:
        if device is None:
            base["missing_fields"].append("device")
            base["ambiguity"].append("Specify one exact device whose parameters should be inspected.")
        else:
            base.update({"mode": "inspect", "action": "inspect_device_parameters", "confirmation_required": False, "confidence": 0.99})
        return base
    if device is not None:
        choice = _choice_request(lower, device[1])
        if choice:
            base.update({
                "mode": "assist",
                "action": "set_device_parameter",
                "parameter": {"name": choice["parameter"]},
                "desired_value": choice["raw"],
                "relative": False,
                "unit": "choice",
                "choice_label": choice["label"],
                "confirmation_required": True,
                "confidence": 0.9,
            })
            return base
    delta_match = re.search(r"\b(lower|reduce|decrease|raise|increase|boost)\b.*?\b(threshold|ratio|attack|release|frequency|gain|q)\b.*?by\s+" + _NUMBER + r"\s*(db|dbs|decibels?|hz|hertz|khz|kilohertz|%|percent|ms|milliseconds?|:1)?", lower)
    set_match = re.search(r"\bset\b.*?\b(threshold|ratio|attack|release|frequency|gain|q)\b.*?to\s+" + _NUMBER + r"\s*(db|dbs|decibels?|hz|hertz|khz|kilohertz|%|percent|ms|milliseconds?|:1)?", lower)
    if device is not None and (delta_match or set_match):
        match = delta_match or set_match
        relative = delta_match is not None
        direction = delta_match.group(1) if delta_match else "set"
        parameter_name = (delta_match.group(2) if delta_match else set_match.group(1)).title()
        band_qualified = _eq_band_qualified_parameter(lower, device[1], parameter_name)
        if band_qualified is not None:
            parameter_name = band_qualified
        amount = float(delta_match.group(3) if delta_match else set_match.group(2))
        requested_unit = (delta_match.group(4) if delta_match else set_match.group(3)) or "value"
        if str(requested_unit).lower() in {"khz", "kilohertz"}:
            amount = amount * 1000.0
            requested_unit = "hz"
        elif str(requested_unit).lower() in {"dbs", "decibel", "decibels"}:
            requested_unit = "db"
        elif str(requested_unit).lower() == "hertz":
            requested_unit = "hz"
        elif str(requested_unit).lower() == "percent":
            requested_unit = "%"
        display_error = _display_unit_error(
            device_name=device[1], parameter_name=parameter_name, value=amount,
            unit=requested_unit, relative=relative,
        )
        if display_error:
            base["missing_fields"].append("supported_unit_mapping")
            base["ambiguity"].append(display_error)
            return base
        if relative and direction in {"lower", "reduce", "decrease"}:
            amount = -abs(amount)
        elif relative:
            amount = abs(amount)
        base.update({
            "mode": "assist",
            "action": "set_device_parameter",
            "parameter": {"name": parameter_name},
            "desired_value": amount,
            "relative": relative,
            # Do not infer dB for an arbitrary device parameter. Threshold
            # and gain commonly use dB, but Live also exposes raw/discrete
            # controls such as Glue Compressor Attack and Ratio. An explicit
            # unit remains authoritative; otherwise the resolver labels the
            # value as a device value until Live metadata proves more.
            "unit": requested_unit,
            "confirmation_required": True,
            "confidence": 0.9,
        })
        return base
    if device is not None:
        generic_match = _generic_device_parameter_match(lower, device[1].lower())
        if not generic_match and _DEVICE_PARAMETER_ACTION.search(lower) and re.search(
                re.escape(device[1].lower()) + r"(?:\s+(?:on|for)\s+(?:the\s+)?[\w/&' -]+?)?\s+(?:to|by)\s+[-+]?\d", lower):
            # "set the compressor on the drum bus to -12 dB" names the device, not which of its settings.
            base.update(action="set_device_parameter")
            base["missing_fields"].append("parameter")
            base["ambiguity"].append(f"Which {device[1]} setting should change? For example \"set the "
                                     f"{device[1].lower()} threshold to -12 dB\". Nothing changed.")
            return base
        if generic_match:
            relative = generic_match["verb"].lower() == "by"
            amount = float(generic_match["value"])
            action_match = _DEVICE_PARAMETER_ACTION.search(lower)
            direction = action_match.group(1).lower() if action_match else "set"
            if relative and direction in {"lower", "reduce", "decrease", "back off"}:
                amount = -abs(amount)
            elif relative:
                amount = abs(amount)
            unit = generic_match["unit"] or ("dB" if relative else "value")
            if str(unit).lower() == "percent":
                unit = "%"
            if str(unit).lower() in {"khz", "kilohertz"}:
                # Live frequency displays use Hz; kilo-hertz is scaled here so
                # every downstream resolver sees canonical Hz values.
                amount = amount * 1000.0
                unit = "hz"
            elif str(unit).lower() in {"dbs", "decibel", "decibels"}:
                unit = "db"
            elif str(unit).lower() == "hertz":
                unit = "hz"
            parameter_name = generic_match["parameter"].strip().title()
            band_qualified = _eq_band_qualified_parameter(lower, device[1], parameter_name)
            if band_qualified is not None:
                parameter_name = band_qualified
            display_error = _display_unit_error(
                device_name=device[1], parameter_name=parameter_name, value=amount,
                unit=unit, relative=relative,
            )
            if display_error:
                base["missing_fields"].append("supported_unit_mapping")
                base["ambiguity"].append(display_error)
                return base
            base.update({
                "mode": "assist",
                "action": "set_device_parameter",
                "parameter": {"name": parameter_name},
                "desired_value": amount,
                "relative": relative,
                "unit": unit,
                "confirmation_required": True,
                "confidence": 0.88,
            })
            return base
    base["missing_fields"].append("action")
    base["ambiguity"].append("No supported Ableton action/value was recognized.")
    return base


__all__ = ["resolve_device_rules"]
