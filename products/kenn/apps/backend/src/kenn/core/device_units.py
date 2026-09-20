"""Evidence-backed conversions between selected Live display units and raw values."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class DeviceUnitProfile:
    device_name: str
    parameter_name: str
    display_unit: str
    raw_min: float
    raw_max: float
    display_min: float
    display_max: float
    raw_values: tuple[float, ...] = ()
    display_values: tuple[float, ...] = ()


# These are limited to mappings confirmed by reversible real-Live probes.
EVIDENCE_BACKED_PROFILES = (
    DeviceUnitProfile("Auto Filter", "Resonance", "%", 0.0, 1.0, 0.0, 100.0),
    DeviceUnitProfile("Drum Buss", "Drive", "%", 0.0, 1.0, 0.0, 100.0),
    DeviceUnitProfile("Hybrid Reverb", "Dry/Wet", "%", 0.0, 1.0, 0.0, 100.0),
    DeviceUnitProfile("Echo", "Dry Wet", "%", 0.0, 1.0, 0.0, 100.0),
    # Ableton's Glue Compressor controls are discrete/non-linear in Live,
    # so interpolation would invent values that do not correspond to the UI.
    DeviceUnitProfile(
        "Glue Compressor", "Attack", "ms", 0.0, 6.0, 0.01, 30.0,
        raw_values=(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
        display_values=(0.01, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0),
    ),
    DeviceUnitProfile(
        "Glue Compressor", "Ratio", "ratio", 0.0, 2.0, 2.0, 10.0,
        raw_values=(0.0, 1.0, 2.0),
        display_values=(2.0, 4.0, 10.0),
    ),
    DeviceUnitProfile("Roar", "Drive", "dB", 0.0, 1.0, 0.0, 48.0),
    DeviceUnitProfile("Roar", "Dry/Wet", "%", 0.0, 1.0, 0.0, 100.0),
)


def normalize_unit(unit: str | None) -> str:
    value = str(unit or "").strip().lower()
    return {
        "percent": "%", "percentage": "%", "raw": "value", "device_value": "value",
        "millisecond": "ms", "milliseconds": "ms", ":1": "ratio",
    }.get(value, value)


def find_profile(device_name: str, parameter_name: str, unit: str | None) -> DeviceUnitProfile | None:
    normalized_unit = normalize_unit(unit)
    for profile in EVIDENCE_BACKED_PROFILES:
        if (
            profile.device_name.casefold() == str(device_name).strip().casefold()
            and profile.parameter_name.casefold() == str(parameter_name).strip().casefold()
            and profile.display_unit.casefold() == normalized_unit.casefold()
        ):
            return profile
    return None


def display_to_raw(*, device_name: str, parameter_name: str, value: float, unit: str | None, relative: bool = False) -> tuple[float | None, str | None]:
    """Convert a qualified display-unit value, or return a safe explanation."""
    normalized_unit = normalize_unit(unit)
    if normalized_unit in {"", "value"}:
        return float(value), None
    profile = find_profile(device_name, parameter_name, normalized_unit)
    if profile is None:
        return None, "That display unit has no evidence-backed raw-value mapping for this Live parameter yet."
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None, "The requested display-unit value is not numeric."
    if not isfinite(numeric):
        return None, "The requested display-unit value is not finite."
    if profile.raw_values and profile.display_values:
        if relative:
            return None, "Relative changes are not supported for this discrete Live display mapping; specify an absolute displayed value."
        matches = [
            raw for raw, displayed in zip(profile.raw_values, profile.display_values)
            if abs(float(displayed) - numeric) <= 1e-6
        ]
        if len(matches) != 1:
            choices = ", ".join(f"{value:g}" for value in profile.display_values)
            return None, f"That displayed value is not one of Live's verified steps; choose one of: {choices}."
        return float(matches[0]), None
    span = profile.display_max - profile.display_min
    if span <= 0.0:
        return None, "The qualified display-unit profile has an invalid range."
    if relative:
        raw = numeric / span * (profile.raw_max - profile.raw_min)
    else:
        raw = (numeric - profile.display_min) / span * (profile.raw_max - profile.raw_min) + profile.raw_min
    return raw, None


__all__ = ["DeviceUnitProfile", "EVIDENCE_BACKED_PROFILES", "display_to_raw", "find_profile", "normalize_unit"]
