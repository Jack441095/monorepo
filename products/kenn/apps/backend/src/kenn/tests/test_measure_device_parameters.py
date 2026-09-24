"""D1 measurement tool: parse Live's display strings and classify each parameter's mapping."""

from __future__ import annotations

import math

import pytest

from scripts.measure_device_parameters import candidate_profile, classify, parse_display


@pytest.mark.parametrize("text, expected", [
    ("-12.0 dB", (-12.0, "db")), ("1.01 kHz", (1010.0, "hz")), ("200 Hz", (200.0, "hz")),
    ("4.00 : 1", (4.0, "ratio")), ("30.0 ms", (30.0, "ms")), ("1.20 s", (1200.0, "ms")),
    ("50 %", (50.0, "%")), ("0.71", (0.71, "value")), ("-inf dB", (-math.inf, "db")),
])
def test_parse_live_display_strings(text, expected) -> None:
    assert parse_display(text) == expected


def test_unparseable_labels() -> None:
    assert parse_display("Peak") is None and parse_display("On") is None


def test_linear_parameter() -> None:
    samples = [(r / 10, f"{-36 + 7.2 * r:.1f} dB") for r in range(11)]
    info = classify(samples)
    assert info["mapping"] == "linear" and info["unit"] == "db"
    assert info["display_min"] == -36.0 and info["display_max"] == pytest.approx(36.0)
    assert candidate_profile("Saturator", "Drive", info).startswith('DeviceUnitProfile("Saturator", "Drive", "db", 0, 1, -36, 36')


def test_log_parameter() -> None:
    samples = [(r / 10, f"{10 * (2200 ** (r / 10)):.0f} Hz") for r in range(11)]
    info = classify(samples)
    assert info["mapping"] == "log" and info["unit"] == "hz"
    assert 'mapping="log"' in candidate_profile("EQ Eight", "1 Frequency A", info)


def test_irregular_parameter_keeps_a_measured_table_and_no_candidate() -> None:
    curve = [-57.2, -48.6, -41.0, -34.4, -28.8, -24.2, -20.6, -18.0, -16.0, -14.0, -12.0]
    info = classify([(r / 10, f"{v} dB") for r, v in enumerate(curve)])
    assert info["mapping"] == "table" and len(info["points"]) == len(curve)
    assert candidate_profile("Compressor", "Threshold", info) is None  # tables are adopted by hand after a real-Live test


def test_mixed_units_are_not_guessed() -> None:
    # Seconds and milliseconds are one unit (ms); a stray label ("Sync") is ignored.
    assert classify([(0.0, "1.00 ms"), (0.5, "300 ms"), (1.0, "1.00 s"), (0.9, "Sync")])["unit"] == "ms"
    assert classify([(0.0, "10 %"), (0.5, "1.0 dB"), (1.0, "2.0 dB")])["mapping"] == "unparsed"
