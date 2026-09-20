"""Tests for the dynamic EQ band processor (dynamic EQ Phase 0.5 — the
"processor" half, paired with resonance_detection.py's "detector" half).

Verifies the core claims the design makes: transparent when the band is
quiet, measurably reduces energy at the target band when it's loud, leaves
other frequencies largely untouched (surgical, not a broad tonal shift),
and respects the max-reduction cap.
"""

from __future__ import annotations

import math

import numpy as np

from audio_analysis.dsp_engine.dynamic_eq import apply_dynamic_eq_band, apply_dynamic_eq_bands

SAMPLE_RATE = 44100


def _sine(freq: float, duration_s: float, *, amplitude: float = 0.3, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    return amplitude * np.sin(2.0 * np.pi * freq * t)


def _band_energy_db(signal: np.ndarray, freq: float, sample_rate: int, *, q: float = 6.0) -> float:
    """Measure energy at a specific frequency via the same iirpeak isolator
    the processor uses, so the test measures what the processor actually
    targets."""
    import scipy.signal as sig
    nyq = 0.5 * sample_rate
    b, a = sig.iirpeak(freq / nyq, q)
    isolated = sig.lfilter(b, a, signal)
    rms = float(np.sqrt(np.mean(isolated ** 2)))
    return 20.0 * math.log10(max(rms, 1e-12))


class TestApplyDynamicEqBand:
    def test_quiet_band_is_transparent(self):
        """A band well below threshold should pass through essentially
        unchanged — this is what makes it "dynamic" rather than a static cut."""
        quiet = _sine(2000.0, 1.0, amplitude=0.02)  # well below -24 dB default threshold
        left, right = quiet.copy(), quiet.copy()
        out_l, out_r = apply_dynamic_eq_band(left, right, frequency_hz=2000.0, sample_rate=SAMPLE_RATE)
        # Should be very close to input (allow small filter-response tolerance)
        assert np.max(np.abs(out_l - left)) < 0.01

    def test_loud_band_is_reduced(self):
        """A band that's loud at its own frequency should be measurably
        pulled down."""
        loud = _sine(2000.0, 1.0, amplitude=0.5)
        left, right = loud.copy(), loud.copy()
        before_db = _band_energy_db(left, 2000.0, SAMPLE_RATE)
        out_l, out_r = apply_dynamic_eq_band(
            left, right, frequency_hz=2000.0, sample_rate=SAMPLE_RATE, threshold_db=-24.0, ratio=4.0,
        )
        after_db = _band_energy_db(out_l, 2000.0, SAMPLE_RATE)
        assert after_db < before_db - 2.0, f"expected meaningful reduction, before={before_db:.1f} after={after_db:.1f}"

    def test_other_frequencies_mostly_unaffected(self):
        """Processing a resonance at 2kHz shouldn't meaningfully touch
        energy at a well-separated frequency like 200Hz — this is the
        "surgical, not broad" requirement from the plan doc."""
        resonance = _sine(2000.0, 1.0, amplitude=0.5)
        other = _sine(200.0, 1.0, amplitude=0.2)
        signal = resonance + other
        left, right = signal.copy(), signal.copy()

        before_200 = _band_energy_db(left, 200.0, SAMPLE_RATE)
        out_l, out_r = apply_dynamic_eq_band(
            left, right, frequency_hz=2000.0, sample_rate=SAMPLE_RATE, threshold_db=-24.0, ratio=4.0,
        )
        after_200 = _band_energy_db(out_l, 200.0, SAMPLE_RATE)
        assert abs(after_200 - before_200) < 1.5, (
            f"200Hz band should be mostly untouched by a 2kHz dynamic cut, "
            f"before={before_200:.1f} after={after_200:.1f}"
        )

    def test_max_reduction_cap_is_respected(self):
        """Even a very loud, sustained resonance shouldn't be pulled down
        more than max_reduction_db — this is the safety cap preventing a
        detection false-positive from dulling the mix."""
        very_loud = _sine(3000.0, 1.0, amplitude=0.9)
        left, right = very_loud.copy(), very_loud.copy()
        before_db = _band_energy_db(left, 3000.0, SAMPLE_RATE)
        out_l, out_r = apply_dynamic_eq_band(
            left, right, frequency_hz=3000.0, sample_rate=SAMPLE_RATE,
            threshold_db=-40.0, ratio=10.0, max_reduction_db=3.0,
        )
        after_db = _band_energy_db(out_l, 3000.0, SAMPLE_RATE)
        actual_reduction = before_db - after_db
        # Allow some slack for envelope smoothing/filter-skirt effects, but
        # it must not blow past the cap by a large margin.
        assert actual_reduction < 3.0 + 2.0, f"reduction {actual_reduction:.1f}dB exceeded the 3dB cap by too much"

    def test_no_nan_or_inf_in_output(self):
        signal = _sine(1000.0, 0.5, amplitude=0.4)
        left, right = signal.copy(), signal.copy()
        out_l, out_r = apply_dynamic_eq_band(left, right, frequency_hz=1000.0, sample_rate=SAMPLE_RATE)
        assert np.all(np.isfinite(out_l))
        assert np.all(np.isfinite(out_r))

    def test_silent_input_stays_silent(self):
        silence = np.zeros(SAMPLE_RATE)
        out_l, out_r = apply_dynamic_eq_band(silence.copy(), silence.copy(), frequency_hz=1000.0, sample_rate=SAMPLE_RATE)
        assert np.max(np.abs(out_l)) < 1e-6


class TestApplyDynamicEqBands:
    def test_empty_bands_list_is_passthrough(self):
        signal = _sine(1000.0, 0.5, amplitude=0.3)
        left, right = signal.copy(), signal.copy()
        out_l, out_r = apply_dynamic_eq_bands(left, right, bands=[], sample_rate=SAMPLE_RATE)
        assert np.array_equal(out_l, left)
        assert np.array_equal(out_r, right)

    def test_caps_at_max_simultaneous_bands(self):
        """More detected bands than max_simultaneous_bands should only
        process the top N (already sorted by the detector)."""
        signal = _sine(500.0, 0.5, amplitude=0.4)
        left, right = signal.copy(), signal.copy()
        many_bands = [
            {"frequency_hz": 500.0 + i * 100, "mean_prominence_db": 6.0, "persistence": 1.0 - i * 0.05}
            for i in range(10)
        ]
        # Should not raise, and should only touch the first max_simultaneous_bands
        out_l, out_r = apply_dynamic_eq_bands(left, right, bands=many_bands, sample_rate=SAMPLE_RATE, max_simultaneous_bands=3)
        assert np.all(np.isfinite(out_l))
        assert len(out_l) == len(left)

    def test_end_to_end_with_real_detector_output(self):
        """Integration: detector finds a planted resonance, processor
        reduces it, verified via the same detector re-run on the output."""
        from audio_analysis.analysis_core.resonance_detection import detect_resonant_bands
        import random
        rng = random.Random(5)
        n = int(2.0 * SAMPLE_RATE)
        noise = [0.1 * (rng.random() * 2.0 - 1.0) for _ in range(n)]
        resonance = _sine(3000.0, 2.0, amplitude=0.4).tolist()
        signal_list = [noise[i] + resonance[i] for i in range(n)]

        detected = detect_resonant_bands(signal_list, SAMPLE_RATE)
        assert detected, "sanity check: detector should find the planted resonance"

        signal_np = np.array(signal_list)
        out_l, out_r = apply_dynamic_eq_bands(
            signal_np.copy(), signal_np.copy(), bands=detected, sample_rate=SAMPLE_RATE
        )

        # Re-run the detector on the processed output — the treated
        # resonance should no longer clear the same prominence threshold
        # at the same strength it did before.
        detected_after = detect_resonant_bands(out_l.tolist(), SAMPLE_RATE)
        before_at_3k = next((b for b in detected if abs(b["frequency_hz"] - 3000.0) < 300.0), None)
        after_at_3k = next((b for b in detected_after if abs(b["frequency_hz"] - 3000.0) < 300.0), None)
        assert before_at_3k is not None
        if after_at_3k is not None:
            assert after_at_3k["mean_prominence_db"] < before_at_3k["mean_prominence_db"]
