"""Evidence-backed conversions between selected Live display units and raw values."""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from math import isfinite, log
from pathlib import Path
from typing import Any


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
# Dry/Wet is linear 0..1 <-> 0..100% on every device that exposes it at a
# 0..1 range: Glue, Saturator, Auto Filter and Drum Buss each passed a
# reversible write/readback/restore run on 2026-09-06 (e.g. Glue 100% ->
# 50% -> 100%), and Compressor exposes the same 0..1 control. EQ Eight band
# frequency follows Live's 10 Hz * 2200^raw taper (fixture 20.2 Hz at raw
# 0.0914, 200 Hz at 0.3892, 1 kHz at 0.5984, 5 kHz at 0.8075, matching
# live_command.py's frequency_raw_value); we bound the profile to the
# user-safe 20 Hz..20 kHz span.
_EQ_BAND_PARAMETER = re.compile(r"^\s*([1-8])\s*(frequency|gain|q)\s*([ab])\s*$", re.I)


def _canonical_parameter(device_name: str, parameter_name: str) -> str:
    """Fold Live's per-band / per-spelling names to one profile name."""
    text = str(parameter_name or "").strip()
    if str(device_name or "").strip().casefold() == "eq eight":
        band = _EQ_BAND_PARAMETER.match(text)
        if band:
            return {"frequency": "Frequency", "gain": "Gain", "q": "Q"}[band.group(2).lower()]
    if text.casefold() in {"dry wet", "dry/wet"}:
        return "Dry/Wet"
    return text


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
    # Compressor Ratio, Attack and Release, measured from Live's display on 26 Sept 2026 and each checked by write,
    # readback and exact restore on real Live (docs/evidence/KENN_COMPRESSOR_PROFILES_2026-09-26.json): 4:1 shows
    # "4.00 : 1", 10 ms "10.0 ms", 250 ms "247 ms". Ratio and Release are measured tables; Attack is a log taper.
    DeviceUnitProfile("Compressor", "Ratio", "ratio", 0, 0.99, 1, 100,
                      raw_values=(0, 0.2, 0.335, 0.43, 0.5, 0.6, 0.665, 0.715, 0.75, 0.8, 0.835, 0.875, 0.9, 0.935, 0.95, 0.965, 0.98, 0.99),
                      display_values=(1, 1.25, 1.5, 1.75, 2, 2.5, 2.99, 3.51, 4, 5, 6.06, 8, 10, 15.4, 20, 28.6, 50, 100),
                      mapping="table"),
    DeviceUnitProfile("Compressor", "Attack", "ms", 0, 1, 0.01, 1000, mapping="log"),
    DeviceUnitProfile("Compressor", "Release", "ms", 0, 1, 1, 3000,
                      raw_values=(0, 0.02, 0.055, 0.085, 0.13, 0.155, 0.2, 0.24, 0.27, 0.32, 0.36, 0.425, 0.515, 0.6, 0.67, 0.78, 0.865, 1),
                      display_values=(1, 2.04, 5.25, 9.81, 20.7, 29.2, 50, 75.2, 98.9, 148, 198, 301, 495, 742, 998, 1510, 2010, 3000),
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
    DeviceUnitProfile("Saturator", "Dry/Wet", "%", 0.0, 1.0, 0.0, 100.0),
    DeviceUnitProfile("Drum Buss", "Dry/Wet", "%", 0.0, 1.0, 0.0, 100.0),
    DeviceUnitProfile("Auto Filter", "Dry/Wet", "%", 0.0, 1.0, 0.0, 100.0),
    DeviceUnitProfile("Glue Compressor", "Dry/Wet", "%", 0.0, 1.0, 0.0, 100.0),
    DeviceUnitProfile("Compressor", "Dry/Wet", "%", 0.0, 1.0, 0.0, 100.0),
    DeviceUnitProfile("EQ Eight", "Frequency", "hz", 0.09006341340106347, 0.9876159632964067, 20.0, 20000.0, mapping="log"),
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


@dataclass(frozen=True)
class DeviceChoice:
    """A switch or chooser: the label Live shows for each raw value (e.g. Compressor "Model": 0 Peak, 1 RMS, 2 Expand)."""

    device_name: str
    parameter_name: str
    options: tuple[tuple[float, str], ...]


def _choice_from_entry(device: str, entry: dict) -> DeviceChoice | None:
    qualification = entry.get("qualification")
    if not (isinstance(qualification, dict) and qualification.get("status") == "passed"
            and int(qualification.get("points") or 0) >= 2 and qualification.get("qualified_at")):
        return None
    try:
        options = tuple((float(item["raw"]), str(item["label"]).strip()) for item in entry.get("options") or [])
    except (KeyError, TypeError, ValueError):
        return None
    labels = [label.casefold() for _raw, label in options]
    if not device or not entry.get("parameter") or len(options) < 2 or "" in labels or len(set(labels)) != len(labels):
        return None
    if not all(isfinite(raw) for raw, _label in options):
        return None
    return DeviceChoice(device, str(entry["parameter"]), options)


@lru_cache(maxsize=1)
def qualified_choices() -> tuple[DeviceChoice, ...]:
    """Choosers from device_profiles/*.json; like profiles, only ones whose options were checked against Live's own labels."""
    choices: list[DeviceChoice] = []
    for path in sorted(PROFILES_DIR.glob("*.json")) if PROFILES_DIR.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            device, entries = str(data.get("device") or ""), data.get("choosers") or []
        except (OSError, ValueError, AttributeError):
            continue
        choices += [c for entry in entries if isinstance(entry, dict) and (c := _choice_from_entry(device, entry))]
    return tuple(choices)


def find_choice(device_name: str, parameter_name: str) -> DeviceChoice | None:
    for choice in qualified_choices():
        if (choice.device_name.casefold() == str(device_name).strip().casefold()
                and choice.parameter_name.casefold() == str(parameter_name).strip().casefold()):
            return choice
    return None


def choice_label(choice: DeviceChoice, raw: object) -> str | None:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return next((label for option, label in choice.options if abs(option - value) < 1e-6), None)


def all_profiles() -> tuple[DeviceUnitProfile, ...]:
    """The hand-verified profiles first (they win on a clash), then the qualified data files."""
    return EVIDENCE_BACKED_PROFILES + qualified_profiles()


def reload_profiles() -> None:
    qualified_profiles.cache_clear()
    qualified_choices.cache_clear()


def find_profile(device_name: str, parameter_name: str, unit: str | None) -> DeviceUnitProfile | None:
    normalized_unit = normalize_unit(unit)
    wanted = _canonical_parameter(device_name, parameter_name)
    # Echo shows "Dry Wet" while every other device shows "Dry/Wet"; both read the same control.
    # all_profiles() also carries the qualified data files, so a measured
    # profile wins over nothing while the hand-verified ones still come first.
    for profile in all_profiles():
        if (
            profile.device_name.casefold() == str(device_name).strip().casefold()
            and _canonical_parameter(profile.device_name, profile.parameter_name).casefold() == wanted.casefold()
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
    if math.isinf(numeric) and numeric < 0 and profile.device_name.lower() == "compressor" and profile.parameter_name.lower() == "threshold":
        return 0.0, None
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
        low, high = (f"{displays[0]:g}:1", f"{displays[-1]:g}:1") if display_unit == "ratio" else \
            (f"{displays[0]:g}", f"{displays[-1]:g} {display_unit}")
        return None, (
            "That value is outside the safe range. "
            f"The verified range for {profile.parameter_name} is {low} to {high}."
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
    return profile_raw_to_display(profile, raw)


def profile_raw_to_display(profile: DeviceUnitProfile, raw: float) -> tuple[float | None, str | None]:
    """What a profile predicts Live will display at a raw value (also used to test a candidate before it is loaded)."""
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
        # Silent Compressor threshold was separately measured in Live as -inf dB at raw 0.0
        if raw_value <= 0.0 and profile.device_name.lower() == "compressor" and profile.parameter_name.lower() == "threshold":
            return float("-inf"), None
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


_UNIT_LABELS = {"db": "dB", "hz": "Hz", "ms": "ms", "%": "%"}


def display_text(device_name: str, parameter_name: str, unit: str, raw: Any) -> str:
    """A raw device value in the units Live shows.

    Converts raw 0..1 values to Live's exact UI display strings. For example:
    - Mixer / track volume raw 0.85 renders as "0.0 dB" (unity), and raw 0.0 as "-inf dB".
    - Silent Compressor threshold raw 0.0 renders as "-inf dB".
    - Discrete and table-mapped parameters render in their measured physical units.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return ""

    device_clean = str(device_name or "").strip()
    param_clean = str(parameter_name or "").strip()
    norm_unit = normalize_unit(unit)

    # Track / Mixer volume follows volume_law (raw 0.85 is 0.0 dB unity, raw 0.0 is -inf dB).
    # Two conversion layers previously disagreed about unity volume: unmapped dB parameters
    # fell through to float(raw), formatting raw 0.85 as "0.8 dB" instead of unity "0.0 dB".
    if (
        (device_clean.lower() in {"mixer", "track", "master", "return", ""} and param_clean.lower() in {"volume", "fader"})
        or (param_clean.lower() == "volume" and norm_unit == "db")
    ):
        from kenn.core import volume_law

        db_val = volume_law.raw_to_db(float(raw))
        if db_val is not None:
            if math.isinf(db_val) and db_val < 0:
                return "-inf dB"
            return f"{db_val:.1f} dB"

    value: float | None = None
    if find_profile(device_name, parameter_name, unit) is not None:
        shown, error = raw_to_display(device_name=device_name, parameter_name=parameter_name, raw=float(raw), unit=unit)
        value = None if error else float(shown)
    elif norm_unit == "db":
        value = float(raw)  # unmapped dB parameters (EQ band gains) already read in dB

    if value is None:
        return ""
    if norm_unit == "ratio":
        return f"{value:.1f}:1"
    if math.isinf(value) and value < 0:
        return "-inf dB"
    if math.isinf(value) and value > 0:
        return "+inf dB"
    label = _UNIT_LABELS.get(norm_unit, str(unit))
    return f"{value:.1f} {label}" if label != "%" else f"{value:.0f}%"


__all__ = ["DeviceChoice", "DeviceUnitProfile", "EVIDENCE_BACKED_PROFILES", "all_profiles", "choice_label", "display_text", "display_to_raw",
           "find_choice", "find_profile", "normalize_unit", "profile_raw_to_display", "qualified_choices", "qualified_profiles",
           "raw_to_display", "reload_profiles"]
