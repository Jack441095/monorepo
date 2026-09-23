import io
import math

import numpy as np
import pytest
import soundfile as sf

from kenn.core.loudness_analysis import estimate_key_and_tempo, loudness_range_lu, measure_loudness, true_peak_dbtp

RATE = 48000


def _wav(signal: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, signal, RATE, format="WAV", subtype="FLOAT")
    return buffer.getvalue()


def _sine(freq: float, seconds: float, amplitude: float) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    tone = amplitude * np.sin(2 * math.pi * freq * t)
    return np.stack([tone, tone], axis=1)


def test_1khz_sine_loudness_and_peaks_match_bs1770_expectations() -> None:
    # A stereo 997 Hz sine at -20 dBFS peak reads about -20 LUFS (K-weighting is ~0 dB at 1 kHz,
    # and two channels add ~+3 dB against the -3 dB RMS-to-peak difference).
    result = measure_loudness(_wav(_sine(997.0, 10.0, 10 ** (-20 / 20))))
    assert result["integrated_lufs"] == pytest.approx(-20.0, abs=0.5)
    assert result["sample_peak_dbfs"] == pytest.approx(-20.0, abs=0.1)
    assert result["true_peak_dbtp"] == pytest.approx(-20.0, abs=0.3)
    assert result["loudness_range_lu"] == pytest.approx(0.0, abs=0.5)


def test_true_peak_catches_inter_sample_overs_that_sample_peak_misses() -> None:
    # fs/4 sine phase-shifted 45 degrees: samples land at 0.707 of the waveform peak.
    t = np.arange(RATE) / RATE
    tone = np.sin(2 * math.pi * (RATE / 4) * t + math.pi / 4)
    data = np.stack([tone, tone], axis=1) * 0.99
    sample_peak_db = 20 * math.log10(np.max(np.abs(data)))
    assert true_peak_dbtp(data) > sample_peak_db + 2.5


def test_loudness_range_uses_gated_percentiles() -> None:
    assert loudness_range_lu([-20.0] * 10) == pytest.approx(0.0)
    assert loudness_range_lu([-30.0] * 5 + [-20.0] * 5) == pytest.approx(10.0, abs=0.01)
    assert loudness_range_lu([-80.0, -90.0]) is None


def test_key_and_tempo_estimates_label_themselves_and_report_the_relative_key() -> None:
    # D minor triad sustained, with a click every 0.5 s (120 BPM).
    seconds = 12.0
    t = np.arange(int(seconds * RATE)) / RATE
    chord = sum(np.sin(2 * math.pi * f * t) for f in (146.83, 174.61, 220.0)) / 6
    clicks = np.zeros_like(t)
    for beat in np.arange(0, seconds, 0.5):
        start = int(beat * RATE)
        clicks[start:start + 200] = 0.8
    mono = chord + clicks
    result = estimate_key_and_tempo(_wav(np.stack([mono, mono], axis=1)))
    assert {result["key"], result["key_relative"]} == {"D minor", "F major"}
    assert result["tempo_bpm"] == pytest.approx(120.0, abs=3.0)
    assert result["key_confidence"] in {"high", "medium", "low"}
    assert "estimates" in result["method"]
