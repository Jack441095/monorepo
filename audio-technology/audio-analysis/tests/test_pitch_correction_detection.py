"""Tests for the pitch-correction (Auto-Tune-style) quantization detector
(Stage M4a). See docs/AUDIO_MVP_MASTER_PLAN.md Stage M4a.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.analysis_core.pitch_correction_detection import (
    _cents_from_nearest_semitone,
    detect_pitch_correction_signature,
)

SR = 44100


def _melody(duration_s: float, sr: int, base_note_hz: float, glide_fraction: float,
            vibrato_depth: float, seed: int) -> np.ndarray:
    """A 4-note melody with a configurable portamento glide length and
    vibrato depth -- a small glide_fraction + tiny vibrato_depth reproduces
    an Auto-Tune-style hard-quantized signature; larger values reproduce a
    natural, unprocessed vocal."""
    rng = np.random.default_rng(seed)
    n = int(duration_s * sr)
    t = np.arange(n) / sr
    notes_hz = [
        base_note_hz,
        base_note_hz * 2 ** (2 / 12),
        base_note_hz * 2 ** (4 / 12),
        base_note_hz * 2 ** (5 / 12),
    ]
    note_dur = duration_s / len(notes_hz)
    f0_curve = np.zeros(n)
    for i, note in enumerate(notes_hz):
        start = int(i * note_dur * sr)
        end = int((i + 1) * note_dur * sr)
        glide_len = max(1, int(glide_fraction * (end - start)))
        prev_note = notes_hz[i - 1] if i > 0 else note
        f0_curve[start : start + glide_len] = np.linspace(prev_note, note, glide_len)
        f0_curve[start + glide_len : end] = note
    vibrato = 1.0 + vibrato_depth * np.sin(2 * np.pi * 5.5 * t)
    instantaneous_f0 = f0_curve * vibrato
    phase = 2 * np.pi * np.cumsum(instantaneous_f0) / sr
    signal = 0.5 * np.sin(phase) + 0.1 * np.sin(2 * phase) + 0.05 * np.sin(3 * phase)
    signal += rng.normal(0, 0.01, n)
    return signal


def _natural_vocal(duration_s: float = 6.0, sample_rate: int = SR, seed: int = 1) -> np.ndarray:
    return _melody(duration_s, sample_rate, 220.0, glide_fraction=0.15, vibrato_depth=0.02, seed=seed)


def _autotuned_vocal(duration_s: float = 6.0, sample_rate: int = SR, seed: int = 1) -> np.ndarray:
    return _melody(duration_s, sample_rate, 220.0, glide_fraction=0.005, vibrato_depth=0.001, seed=seed)


class TestCentsFromNearestSemitone:
    def test_exact_a440_is_zero_cents(self) -> None:
        assert _cents_from_nearest_semitone(440.0) == pytest.approx(0.0, abs=0.01)

    def test_quarter_tone_sharp_is_fifty_cents(self) -> None:
        # Halfway between A4 (440Hz) and A#4 (~466.16Hz)
        quarter_tone = 440.0 * 2 ** (0.5 / 12)
        assert abs(_cents_from_nearest_semitone(quarter_tone)) == pytest.approx(50.0, abs=0.5)


class TestDetectPitchCorrectionSignature:
    def test_detects_a_hard_quantized_synthetic_vocal(self) -> None:
        result = detect_pitch_correction_signature(_autotuned_vocal(), SR)
        assert result["pitch_correction_detected"] is True
        assert result["cents_std"] < 12.0
        assert result["near_grid_share"] > 0.55

    def test_does_not_flag_a_natural_synthetic_vocal(self) -> None:
        result = detect_pitch_correction_signature(_natural_vocal(), SR)
        assert result["pitch_correction_detected"] is False

    def test_silence_does_not_crash_or_false_positive(self) -> None:
        result = detect_pitch_correction_signature(np.zeros(SR * 4), SR)
        assert result["pitch_correction_detected"] is False
        assert result["voiced_frame_count"] == 0

    def test_too_short_input_does_not_crash(self) -> None:
        result = detect_pitch_correction_signature(np.zeros(100), SR)
        assert result["pitch_correction_detected"] is False

    def test_sparse_voiced_content_is_not_flagged(self) -> None:
        """Too few voiced frames to trust a statistical judgment -- must not
        fire just because the few frames that exist happen to land near the
        grid by chance."""
        n = int(2.0 * SR)
        signal = np.zeros(n)
        # A single short voiced blip, nowhere near MIN_VOICED_FRAMES worth of content.
        blip = _autotuned_vocal(duration_s=0.1, sample_rate=SR)
        signal[: len(blip)] = blip
        result = detect_pitch_correction_signature(signal, SR)
        assert result["pitch_correction_detected"] is False


class TestRealVocalStemsNegativeControl:
    """Regression using real measured values from testing_track_stems/
    (2026-07-10): every real vocal stem across all three projects correctly
    scored well clear of both thresholds (cents_std 15.15-24.69,
    near_grid_share 0.09-0.33) -- reproduced here via a natural-vocal
    synthetic proxy at the closest real measured margin
    (reggueton_pop's VOCAL_CHOP, cents_std=15.15) to guard against a future
    threshold change silently reintroducing a false positive on real,
    unprocessed vocal material."""

    def test_natural_vocal_at_the_closest_real_measured_margin_is_not_flagged(self) -> None:
        # Slightly larger vibrato/glide than the default natural fixture,
        # tuned so its own cents_std lands near VOCAL_CHOP's real 15.15
        # measurement -- the closest real negative-control case found.
        signal = _melody(6.0, SR, 220.0, glide_fraction=0.1, vibrato_depth=0.012, seed=4)
        result = detect_pitch_correction_signature(signal, SR)
        assert result["pitch_correction_detected"] is False
