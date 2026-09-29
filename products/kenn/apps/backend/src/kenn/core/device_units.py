"""Evidence-backed conversions between selected Live display units and raw values."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from math import isfinite, log
from pathlib import Path


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
    # "linear" interpolates proportionally across the display span ("value"
    # passthrough aside); discrete exact steps reuse raw/display value pairs.
    # "log" maps raw 0..1 to display_min..display_max exponentially, matching
    # Live's frequency knobs. "table" piecewise-linearly interpolates the
    # measured (display_values[i] <-> raw_values[i]) calibration table, which
    # must ascend in display order. Only "linear" supports relative changes.
    mapping: str = "linear"


# These are limited to mappings confirmed by reversible real-Live probes.
# Compressor Threshold is a 20-point measured table (raw 0.05..1.0 <->
# -57.2..+6.0 dB, 2026-09-21, readback-verified; raw 0.0 separately measured
# as -inf dB). Auto Filter Frequency follows Live's 20 Hz..20 kHz log taper
# (verified at 20/112/632/1000/3560/20000 Hz). Saturator Drive is linear
# -36..+36 dB (verified at -36/-18/0/4/18/36 dB).
EVIDENCE_BACKED_PROFILES = (
    DeviceUnitProfile("Auto Filter", "Resonance", "%", 0.0, 1.0, 0.0, 100.0),
    DeviceUnitProfile("Auto Filter", "Frequency", "hz", 0.0, 1.0, 20.0, 20000.0, mapping="log"),
    DeviceUnitProfile("Compressor", "Threshold", "db", 0.0, 1.0, -57.2, 6.0,
                      raw_values=(0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5,
                                  0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
                      display_values=(-57.2, -48.6, -41.0, -34.4, -28.8, -24.2, -20.6, -18.0,
                                      -16.0, -14.0, -12.0, -10.0, -8.0, -6.0, -4.0, -2.0,
                                      0.0, 2.0, 4.0, 6.0),
                      mapping="table"),
    DeviceUnitProfile("Saturator", "Drive", "db", 0.0, 1.0, -36.0, 36.0),
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
        "dbs": "db", "decibel": "db", "decibels": "db",
        "hertz": "hz",
    }.get(value, value)


PROFILES_DIR = Path(os.environ.get("KENN_DEVICE_PROFILES_DIR", str(Path(__file__).with_name("device_profiles")))).expanduser()
_MAPPINGS = {"linear", "log", "table"}
_UNITS = {"db", "hz", "ms", "%", "ratio"}
MIN_QUALIFICATION_POINTS = 3


def _profile_from_entry(device: str, entry: dict) -> DeviceUnitProfile | None:
    """One profile from a data file, or None unless it carries a passed qualification and is internally consistent."""
    qualification = entry.get("qualification")
    if not (isinstance(qualification, dict) and qualification.get("status") == "passed"
            and int(qualification.get("points") or 0) >= MIN_QUALIFICATION_POINTS and qualification.get("qualified_at")):
        return None
    mapping, unit = str(entry.get("mapping") or ""), normalize_unit(entry.get("unit"))
    if mapping not in _MAPPINGS or unit not in _UNITS or not device or not entry.get("parameter"):
        return None
    try:
        numbers = [float(entry[key]) for key in ("raw_min", "raw_max", "display_min", "display_max")]
        raw_values = tuple(float(v) for v in entry.get("raw_values") or ())
        display_values = tuple(float(v) for v in entry.get("display_values") or ())
    except (KeyError, TypeError, ValueError):
        return None
    if not all(isfinite(n) for n in [*numbers, *raw_values, *display_values]) or numbers[1] <= numbers[0]:
        return None
    if mapping == "table" and (len(raw_values) < 2 or len(raw_values) != len(display_values)):
        return None
    if mapping == "log" and (numbers[2] <= 0 or numbers[3] <= numbers[2]):
        return None
    return DeviceUnitProfile(device, str(entry["parameter"]), unit, *numbers, raw_values=raw_values,
                             display_values=display_values, mapping=mapping)


@lru_cache(maxsize=1)
def qualified_profiles() -> tuple[DeviceUnitProfile, ...]:
    """Profiles from device_profiles/*.json. A candidate without a passed qualification is never loaded."""
    profiles: list[DeviceUnitProfile] = []
    for path in sorted(PROFILES_DIR.glob("*.json")) if PROFILES_DIR.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            device = str(data.get("device") or "")
            entries = data.get("profiles") or []
        except (OSError, ValueError, AttributeError):
            logging.getLogger("kenn.device_units").warning("Unreadable device profile file %s", path)
            continue
        for entry in entries:
            profile = _profile_from_entry(device, entry) if isinstance(entry, dict) else None
            if profile is not None:
                profiles.append(profile)
    return tuple(profiles)


def all_profiles() -> tuple[DeviceUnitProfile, ...]:
    """The hand-verified profiles first (they win on a clash), then the qualified data files."""
    return EVIDENCE_BACKED_PROFILES + qualified_profiles()


def reload_profiles() -> None:
    qualified_profiles.cache_clear()


def find_profile(device_name: str, parameter_name: str, unit: str | None) -> DeviceUnitProfile | None:
    normalized_unit = normalize_unit(unit)
    for profile in all_profiles():
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
        if profile.mapping == "table":
            return _table_lookup(profile, numeric, relative)
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
    if profile.mapping == "log":
        if relative:
            return None, "Relative changes are not supported for this logarithmic Live display mapping; specify an absolute displayed value."
        if profile.display_min <= 0.0 or profile.display_max <= profile.display_min:
            return None, "The qualified logarithmic profile has an invalid range."
        if numeric < profile.display_min or numeric > profile.display_max:
            display_unit = {"db": "dB", "hz": "Hz", "khz": "kHz"}.get(
                profile.display_unit.lower(), profile.display_unit
            )
            return None, (
                "That value is outside the safe range. "
                f"The verified range for {profile.parameter_name} is "
                f"{profile.display_min:g} to {profile.display_max:g} {display_unit}."
            )
        fraction = log(numeric / profile.display_min) / log(profile.display_max / profile.display_min)
        return profile.raw_min + fraction * (profile.raw_max - profile.raw_min), None
    if relative:
        raw = numeric / span * (profile.raw_max - profile.raw_min)
    else:
        raw = (numeric - profile.display_min) / span * (profile.raw_max - profile.raw_min) + profile.raw_min
    return raw, None


def _table_lookup(profile: DeviceUnitProfile, numeric: float, relative: bool) -> tuple[float | None, str | None]:
    """Piecewise-linear interpolation over a measured calibration table."""
    del relative  # Relative changes resolve through raw_to_display round-trips in the caller.
    pairs = sorted(zip(profile.display_values, profile.raw_values), key=lambda pair: pair[0])
    if len(pairs) < 2:
        return None, "The qualified table profile has too few calibration points."
    displays = [pair[0] for pair in pairs]
    if numeric < displays[0] or numeric > displays[-1]:
        display_unit = {"db": "dB", "hz": "Hz", "khz": "kHz"}.get(
            profile.display_unit.lower(), profile.display_unit
        )
        return None, (
            "That value is outside the safe range. "
            f"The verified range for {profile.parameter_name} is "
            f"{displays[0]:g} to {displays[-1]:g} {display_unit}."
        )
    for left, right in zip(pairs, pairs[1:]):
        if left[0] <= numeric <= right[0]:
            if right[0] == left[0]:
                return float(left[1]), None
            fraction = (numeric - left[0]) / (right[0] - left[0])
            return float(left[1] + fraction * (right[1] - left[1])), None
    return float(pairs[-1][1]), None


def raw_to_display(*, device_name: str, parameter_name: str, raw: float, unit: str | None) -> tuple[float | None, str | None]:
    """Invert an evidence-backed mapping: raw Live value to display units.

    Used to resolve relative display changes ("lower by 2 dB") against the
    current raw value. Returns (display_value, None) or (None, reason).
    """
    profile = find_profile(device_name, parameter_name, unit)
    if profile is None:
        return None, "That display unit has no evidence-backed raw-value mapping for this Live parameter yet."
    try:
        raw_value = float(raw)
    except (TypeError, ValueError):
        return None, "The current Live value is not numeric."
    if profile.mapping == "log":
        if profile.display_min <= 0.0 or profile.display_max <= profile.display_min:
            return None, "The qualified logarithmic profile has an invalid range."
        span = profile.raw_max - profile.raw_min
        if span == 0.0:
            return None, "The qualified logarithmic profile has an invalid range."
        fraction = (raw_value - profile.raw_min) / span
        return float(profile.display_min * (profile.display_max / profile.display_min) ** fraction), None
    if profile.mapping == "table":
        pairs = sorted(zip(profile.display_values, profile.raw_values), key=lambda pair: pair[0])
        raws = sorted(zip(profile.raw_values, profile.display_values), key=lambda pair: pair[0])
        if len(pairs) < 2:
            return None, "The qualified table profile has too few calibration points."
        if raw_value <= raws[0][0]:
            return float(pairs[0][0]), None
        if raw_value >= raws[-1][0]:
            return float(pairs[-1][0]), None
        for left, right in zip(raws, raws[1:]):
            if left[0] <= raw_value <= right[0]:
                if right[0] == left[0]:
                    return float(left[1]), None
                fraction = (raw_value - left[0]) / (right[0] - left[0])
                return float(left[1] + fraction * (right[1] - left[1])), None
        return float(pairs[-1][0]), None
    span = profile.display_max - profile.display_min
    return float(profile.display_min + (raw_value - profile.raw_min) / (profile.raw_max - profile.raw_min) * span), None


__all__ = ["DeviceUnitProfile", "EVIDENCE_BACKED_PROFILES", "all_profiles", "display_to_raw", "find_profile", "normalize_unit",
           "qualified_profiles", "raw_to_display", "reload_profiles"]
