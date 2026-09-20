"""Tests for the automatic resonance/harshness detector (dynamic EQ Phase 0).

Per docs/SPECTRAL_DYNAMIC_EQ_PLUGIN_PLAN.md's own testing spec: does it find a
planted resonance and not false-positive on a flat/noise spectrum? Also checks
the persistence half of the design — a single-frame transient must NOT be
flagged, only something that sticks out consistently across frames.
"""

from __future__ import annotations

import math
import random

from audio_analysis.analysis_core.resonance_detection import (
    _local_neighborhood_prominence_db,
    detect_resonant_bands,
)

SAMPLE_RATE = 44100


def _sine(freq: float, duration_s: float, *, amplitude: float = 0.3, sample_rate: int = SAMPLE_RATE) -> list[float]:
    n = int(duration_s * sample_rate)
    return [amplitude * math.sin(2.0 * math.pi * freq * t / sample_rate) for t in range(n)]


def _white_noise(duration_s: float, *, amplitude: float = 0.2, seed: int = 42, sample_rate: int = SAMPLE_RATE) -> list[float]:
    rng = random.Random(seed)
    n = int(duration_s * sample_rate)
    return [amplitude * (rng.random() * 2.0 - 1.0) for _ in range(n)]


def _mix(*signals: list[float]) -> list[float]:
    n = min(len(s) for s in signals)
    return [sum(s[i] for s in signals) for i in range(n)]


class TestLocalNeighborhoodProminence:
    def test_flat_energy_has_zero_prominence(self):
        energies = [1.0] * 20
        assert _local_neighborhood_prominence_db(energies, 10) == 0.0

    def test_spike_has_positive_prominence(self):
        energies = [1.0] * 20
        energies[10] = 100.0  # 20 dB above neighbors
        prominence = _local_neighborhood_prominence_db(energies, 10)
        assert prominence > 15.0  # allow some tolerance from the neighborhood averaging

    def test_dip_has_negative_prominence(self):
        energies = [1.0] * 20
        energies[10] = 0.01
        assert _local_neighborhood_prominence_db(energies, 10) < 0.0

    def test_silent_band_returns_zero_not_error(self):
        energies = [0.0] * 20
        assert _local_neighborhood_prominence_db(energies, 10) == 0.0


class TestDetectResonantBands:
    def test_planted_resonance_at_2khz_is_detected(self):
        """The plan doc's own acceptance test: does it find a planted 6dB peak
        at 2kHz? Uses a much larger boost than 6dB at the source so it clears
        6dB of *neighborhood prominence* after ERB-band energy summation."""
        noise = _white_noise(2.0, amplitude=0.15)
        resonance = _sine(2000.0, 2.0, amplitude=0.35)
        signal = _mix(noise, resonance)

        results = detect_resonant_bands(signal, SAMPLE_RATE)
        assert results, "expected at least one flagged band"

        # Find the flagged band closest to 2kHz
        closest = min(results, key=lambda r: abs(r["frequency_hz"] - 2000.0))
        assert abs(closest["frequency_hz"] - 2000.0) < 200.0, (
            f"closest flagged band was {closest['frequency_hz']} Hz, expected near 2000 Hz"
        )
        assert closest["persistence"] >= 0.4
        assert closest["mean_prominence_db"] >= 6.0

    def test_flat_white_noise_does_not_false_positive(self):
        """A flat(-ish) noise spectrum shouldn't trigger persistent flags —
        random per-frame variance can cause occasional single-frame spikes,
        but nothing should clear the persistence threshold."""
        noise = _white_noise(3.0, amplitude=0.3, seed=7)
        results = detect_resonant_bands(noise, SAMPLE_RATE)
        assert results == [], f"expected no persistent flags on flat noise, got {results}"

    def test_single_frame_transient_is_not_flagged(self):
        """A resonance present in only one frame (not persistent) must not be
        flagged — this is the whole point of requiring persistence, not just
        prominence, distinguishing a real problem from a passing transient."""
        noise = _white_noise(3.0, amplitude=0.15, seed=3)
        # Inject a short, loud burst at 5kHz covering only ~1 of ~16 frames
        n = len(noise)
        burst = [0.0] * n
        burst_start = n // 2
        burst_samples = _sine(5000.0, 0.15, amplitude=0.5)
        for i, v in enumerate(burst_samples):
            if burst_start + i < n:
                burst[burst_start + i] = v
        signal = _mix(noise, burst)

        results = detect_resonant_bands(signal, SAMPLE_RATE, persistence_threshold=0.4)
        flagged_near_5k = [r for r in results if abs(r["frequency_hz"] - 5000.0) < 300.0]
        assert flagged_near_5k == [], (
            f"a single-frame transient should not clear the persistence threshold, got {flagged_near_5k}"
        )

    def test_two_planted_resonances_both_detected_and_ranked(self):
        """Multiple genuine resonances should all surface, sorted by how
        consistently-problematic they are (persistence, then prominence)."""
        noise = _white_noise(2.0, amplitude=0.1, seed=11)
        res_a = _sine(800.0, 2.0, amplitude=0.25)
        res_b = _sine(4000.0, 2.0, amplitude=0.35)
        signal = _mix(noise, res_a, res_b)

        results = detect_resonant_bands(signal, SAMPLE_RATE)
        frequencies = [r["frequency_hz"] for r in results]
        assert any(abs(f - 800.0) < 150.0 for f in frequencies)
        assert any(abs(f - 4000.0) < 300.0 for f in frequencies)
        # Sorted descending by (persistence, mean_prominence_db)
        keys = [(r["persistence"], r["mean_prominence_db"]) for r in results]
        assert keys == sorted(keys, reverse=True)

    def test_empty_or_too_short_input_returns_empty_list(self):
        assert detect_resonant_bands([], SAMPLE_RATE) == []
        assert detect_resonant_bands([0.1] * 10, SAMPLE_RATE) == []


class TestFundamentalProtection:
    """protect_below_hz drops flags at/below a role's fundamental region — a
    kick/bass fundamental is the instrument's body, not a resonance to cut.
    Calibrated 2026-07-16 against a reggueton kick whose own 99 Hz was flagged."""

    def test_low_fundamental_flagged_without_protection(self):
        """Baseline: a persistent 100 Hz peak IS flagged by default (0.0)."""
        noise = _white_noise(2.0, amplitude=0.05, seed=21)
        kick_fundamental = _sine(100.0, 2.0, amplitude=0.4)
        signal = _mix(noise, kick_fundamental)
        results = detect_resonant_bands(signal, SAMPLE_RATE)
        assert any(r["frequency_hz"] <= 150.0 for r in results), (
            "expected the 100 Hz fundamental to be flagged without protection"
        )

    def test_low_fundamental_suppressed_with_protection(self):
        """With a 150 Hz floor (kick/bass role), the same 100 Hz peak is dropped."""
        noise = _white_noise(2.0, amplitude=0.05, seed=21)
        kick_fundamental = _sine(100.0, 2.0, amplitude=0.4)
        signal = _mix(noise, kick_fundamental)
        results = detect_resonant_bands(signal, SAMPLE_RATE, protect_below_hz=150.0)
        assert all(r["frequency_hz"] > 150.0 for r in results), (
            f"no band at/below 150 Hz should survive protection, got {results}"
        )

    def test_protection_does_not_touch_boxiness_above_floor(self):
        """A 400 Hz boxy resonance (piano/vocal territory) is still flagged even
        with the default 60 Hz floor — protection must not over-reach."""
        noise = _white_noise(2.0, amplitude=0.1, seed=23)
        boxy = _sine(400.0, 2.0, amplitude=0.3)
        signal = _mix(noise, boxy)
        results = detect_resonant_bands(signal, SAMPLE_RATE, protect_below_hz=60.0)
        assert any(abs(r["frequency_hz"] - 400.0) < 120.0 for r in results), (
            "a 400 Hz resonance must survive a 60 Hz protection floor"
        )

    def test_result_shape(self):
        noise = _white_noise(2.0, amplitude=0.15)
        resonance = _sine(3000.0, 2.0, amplitude=0.35)
        signal = _mix(noise, resonance)
        results = detect_resonant_bands(signal, SAMPLE_RATE)
        assert results
        for r in results:
            assert set(r.keys()) == {"band_index", "frequency_hz", "mean_prominence_db", "persistence"}
            assert isinstance(r["band_index"], int)
            assert 0.0 <= r["persistence"] <= 1.0
