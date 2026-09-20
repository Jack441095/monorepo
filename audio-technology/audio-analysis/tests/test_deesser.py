"""Tests for the de-esser (dsp_engine/deesser.py).

Closes CODEBASE_FORWARD_PLAN_2026-07-31.md §3.1 -- apply_deesser was a
missing module behind an already-existing flag/wiring. Verifies the same
core claims as dynamic_eq.py's own tests (it's a thin wrapper over that
primitive), tuned to the sibilance band: transparent when quiet, reduces a
loud sibilant burst, leaves low/mid content alone, and respects the
conservative <=4dB default cap.
"""

from __future__ import annotations

import math

import numpy as np

from audio_analysis.dsp_engine.deesser import DEFAULT_FREQUENCY_HZ, apply_deesser

SAMPLE_RATE = 44100


def _sine(freq: float, duration_s: float, *, amplitude: float = 0.3, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    return amplitude * np.sin(2.0 * np.pi * freq * t)


def _band_energy_db(signal: np.ndarray, freq: float, sample_rate: int, *, q: float = 2.0) -> float:
    import scipy.signal as sig
    nyq = 0.5 * sample_rate
    b, a = sig.iirpeak(freq / nyq, q)
    isolated = sig.lfilter(b, a, signal)
    rms = float(np.sqrt(np.mean(isolated ** 2)))
    return 20.0 * math.log10(max(rms, 1e-12))


def test_quiet_sibilance_band_is_transparent():
    quiet = _sine(DEFAULT_FREQUENCY_HZ, 0.5, amplitude=0.02)
    left, right = quiet.copy(), quiet.copy()
    out_l, out_r = apply_deesser(left, right, sample_rate=SAMPLE_RATE)
    assert np.max(np.abs(out_l - left)) < 0.01


def test_loud_sibilant_burst_is_reduced():
    ess = _sine(DEFAULT_FREQUENCY_HZ, 0.5, amplitude=0.5)
    left, right = ess.copy(), ess.copy()
    before_db = _band_energy_db(left, DEFAULT_FREQUENCY_HZ, SAMPLE_RATE)
    out_l, out_r = apply_deesser(left, right, sample_rate=SAMPLE_RATE)
    after_db = _band_energy_db(out_l, DEFAULT_FREQUENCY_HZ, SAMPLE_RATE)
    assert after_db < before_db - 1.0, f"expected measurable reduction, before={before_db:.1f} after={after_db:.1f}"


def test_vocal_body_frequencies_mostly_unaffected():
    """A de-esser should touch the sibilant band, not the body of the voice
    (e.g. ~500 Hz fundamentals/low formants)."""
    ess = _sine(DEFAULT_FREQUENCY_HZ, 0.5, amplitude=0.5)
    voice_body = _sine(500.0, 0.5, amplitude=0.3)
    signal = ess + voice_body
    left, right = signal.copy(), signal.copy()

    before_500 = _band_energy_db(left, 500.0, SAMPLE_RATE)
    out_l, out_r = apply_deesser(left, right, sample_rate=SAMPLE_RATE)
    after_500 = _band_energy_db(out_l, 500.0, SAMPLE_RATE)
    assert abs(after_500 - before_500) < 1.5, (
        f"500Hz voice body should be mostly untouched by de-essing, before={before_500:.1f} after={after_500:.1f}"
    )


def test_default_max_reduction_cap_is_conservative():
    """Forward-plan doc F1 specifies a <=4dB cap by default -- even a very
    loud, sustained ess shouldn't be pulled down harder than that."""
    very_loud = _sine(DEFAULT_FREQUENCY_HZ, 0.5, amplitude=0.9)
    left, right = very_loud.copy(), very_loud.copy()
    before_db = _band_energy_db(left, DEFAULT_FREQUENCY_HZ, SAMPLE_RATE)
    out_l, out_r = apply_deesser(left, right, sample_rate=SAMPLE_RATE, threshold_db=-40.0, ratio=10.0)
    after_db = _band_energy_db(out_l, DEFAULT_FREQUENCY_HZ, SAMPLE_RATE)
    actual_reduction = before_db - after_db
    assert actual_reduction < 4.0 + 2.0, f"reduction {actual_reduction:.1f}dB exceeded the 4dB default cap by too much"


def test_silent_input_stays_silent():
    silence = np.zeros(SAMPLE_RATE)
    out_l, out_r = apply_deesser(silence.copy(), silence.copy(), sample_rate=SAMPLE_RATE)
    assert np.max(np.abs(out_l)) < 1e-6


def test_no_nan_or_inf_in_output():
    signal = _sine(DEFAULT_FREQUENCY_HZ, 0.3, amplitude=0.4)
    left, right = signal.copy(), signal.copy()
    out_l, out_r = apply_deesser(left, right, sample_rate=SAMPLE_RATE)
    assert np.all(np.isfinite(out_l))
    assert np.all(np.isfinite(out_r))
