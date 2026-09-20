from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from audio_analysis.analysis_core.transient_groove import (
    analyze_groove,
    analyze_transients,
    detect_transient_onsets,
    estimate_bpm,
    measure_transient_events,
)
from audio_analysis.mix_review import mix_review


SAMPLE_RATE = 44_100


def _click_track(times: list[float], duration: float = 4.0) -> np.ndarray:
    signal = np.zeros(int(SAMPLE_RATE * duration), dtype=np.float64)
    tail = np.exp(-np.arange(int(0.02 * SAMPLE_RATE)) / (0.004 * SAMPLE_RATE))
    for time_seconds in times:
        start = int(round(time_seconds * SAMPLE_RATE))
        end = min(len(signal), start + len(tail))
        signal[start:end] += tail[: end - start]
    return signal


def _wav_bytes(signal: np.ndarray) -> bytes:
    pcm = np.clip(signal, -1.0, 1.0)
    payload = (pcm * 32767.0).astype("<i2").tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(payload)
    return output.getvalue()


def test_spectral_flux_detects_click_onsets_without_double_triggers() -> None:
    expected = [0.5 + index * 0.25 for index in range(12)]
    onsets = detect_transient_onsets(_click_track(expected), SAMPLE_RATE)

    assert len(onsets) == len(expected)
    for detected, target in zip(onsets, expected):
        # Spectral windows lead the physical peak consistently; grid phase removes
        # this fixed offset during groove analysis.
        assert abs(detected["time_seconds"] - target) < 0.025


def test_transient_event_measures_slow_attack_and_200ms_sustain() -> None:
    signal = np.zeros(SAMPLE_RATE)
    onset = int(0.1 * SAMPLE_RATE)
    attack_samples = int(0.02 * SAMPLE_RATE)
    signal[onset : onset + attack_samples] = np.linspace(0.0, 1.0, attack_samples)
    signal[onset + attack_samples : onset + int(0.35 * SAMPLE_RATE)] = 0.2

    events = measure_transient_events(
        signal,
        SAMPLE_RATE,
        [{"sample": onset, "time_seconds": 0.1, "strength": 1.0}],
    )

    assert len(events) == 1
    assert 14.0 <= events[0]["attack_ms"] <= 22.0
    assert events[0]["sustain_200ms_dbfs"] == pytest.approx(-13.98, abs=0.3)
    assert events[0]["release_ms"] > 200.0


def test_transient_profiles_flag_crushed_and_slow_shapes() -> None:
    clicks = _click_track([0.5 + index * 0.25 for index in range(8)])
    crushed = analyze_transients(clicks, SAMPLE_RATE, crest_factor_db=5.0, target="club")
    assert crushed["profile"] == "Crushed"
    assert crushed["flags"][0]["label"] == "Crushed transients"
    assert crushed["compression_impact"]["status"] == "over-processed"
    assert crushed["target_ranges"] == {
        "attack_ms": (1.0, 12.0),
        "attack_sustain_db": (8.0, 22.0),
    }

    slow_signal = np.zeros(SAMPLE_RATE)
    for start_seconds in (0.1, 0.4, 0.7):
        start = int(start_seconds * SAMPLE_RATE)
        ramp = np.linspace(0.0, 1.0, int(0.025 * SAMPLE_RATE))
        slow_signal[start : start + len(ramp)] = ramp
    explicit = [
        {"sample": int(value * SAMPLE_RATE), "time_seconds": value, "strength": 1.0}
        for value in (0.1, 0.4, 0.7)
    ]
    measured = measure_transient_events(slow_signal, SAMPLE_RATE, explicit)
    assert np.median([event["attack_ms"] for event in measured]) > 15.0


def test_straight_grid_is_tight_and_detects_120_bpm() -> None:
    times = [0.5 + index * 0.25 for index in range(12)]
    groove = analyze_groove(_click_track(times), SAMPLE_RATE)

    assert groove["bpm"] == pytest.approx(120.0, abs=0.5)
    assert groove["timing_class"] == "Tight"
    assert groove["mean_abs_deviation_ms"] < 1.0
    assert groove["swing_percentage"] == pytest.approx(50.0, abs=1.0)
    assert groove["swing_class"] == "Straight"


def test_swung_eighths_report_triplet_swing_ratio() -> None:
    times = []
    for beat in range(6):
        times.extend([0.5 + beat * 0.5, 0.5 + beat * 0.5 + 1.0 / 3.0])
    groove = analyze_groove(_click_track(times), SAMPLE_RATE)

    assert groove["bpm"] == pytest.approx(120.0, abs=0.5)
    assert groove["swing_percentage"] == pytest.approx(66.7, abs=1.5)
    assert groove["swing_class"] == "Swung"


def test_timing_class_thresholds_are_represented_by_grid_deviation() -> None:
    base = [0.5 + index * 0.25 for index in range(12)]
    human = [time + (0.008 if index % 2 else -0.008) for index, time in enumerate(base)]
    loose = [time + (0.022 if index % 2 else -0.022) for index, time in enumerate(base)]
    sloppy = [time + (0.030 if index % 2 else -0.030) for index, time in enumerate(base)]

    assert analyze_groove(_click_track(human), SAMPLE_RATE, bpm=120.0)["timing_class"] == "Human"
    assert analyze_groove(_click_track(loose), SAMPLE_RATE, bpm=120.0)["timing_class"] == "Loose"
    assert analyze_groove(_click_track(sloppy), SAMPLE_RATE, bpm=120.0)["timing_class"] == "Sloppy"


def test_mix_review_report_contains_transient_and_groove_metrics() -> None:
    signal = _click_track([0.5 + index * 0.25 for index in range(12)])
    report = mix_review.analyze_wav(_wav_bytes(signal), "straight-groove.wav", mix_goal="club")

    assert report["metrics"]["transient_analysis"]["onset_count"] >= 10
    assert report["metrics"]["groove_analysis"]["bpm"] == pytest.approx(120.0, abs=0.5)
    assert any("Groove timing is tight" in item for item in report["advice"])


def test_estimate_bpm_requires_enough_onsets() -> None:
    assert estimate_bpm([0.0, 0.5]) == (0.0, 0.0)
