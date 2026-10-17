import io
import math

import numpy as np
import pytest
import soundfile as sf

from kenn.core.loudness_analysis import loudness_range_lu, measure_loudness, true_peak_dbtp

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


def test_measure_loudness_decodes_aiff_and_runs_without_pyloudnorm_or_scipy(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    buffer = io.BytesIO()
    sf.write(buffer, _sine(997.0, 4.0, 10 ** (-20 / 20)), RATE, format="AIFF", subtype="PCM_16")
    aiff_bytes = buffer.getvalue()

    for blocked in ("pyloudnorm", "scipy", "scipy.signal", "soundfile"):
        monkeypatch.setitem(sys.modules, blocked, None)

    result = measure_loudness(aiff_bytes)
    assert result["integrated_lufs"] == pytest.approx(-20.0, abs=0.5)
    assert result["short_term_max_lufs"] == pytest.approx(-20.0, abs=0.5)
    assert result["momentary_max_lufs"] == pytest.approx(-20.0, abs=0.5)
    assert result["true_peak_dbtp"] == pytest.approx(-20.0, abs=0.3)
    assert result["sample_peak_dbfs"] == pytest.approx(-20.0, abs=0.1)


def test_loudness_analysis_raises_when_native_extension_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _wav(_sine(997.0, 1.0, 0.1))
    monkeypatch.setenv("KENN_DSP_NATIVE", "0")
    with pytest.raises(RuntimeError, match="Native decode_pcm kernel is required"):
        measure_loudness(payload)
    with pytest.raises(RuntimeError, match="Native true_peak_dbtp kernel is required"):
        true_peak_dbtp(np.zeros((128, 1), dtype=np.float32))
    with pytest.raises(RuntimeError, match="Native loudness_range_lu kernel is required"):
        loudness_range_lu([-20.0, -25.0])
