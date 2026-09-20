"""Tests for Phase M8 — Advanced Automix Intelligence.

Covers:
- M8.1  stereo_image_comparison()
- M8.3  load_mix_modifiers() / quality_predictor integration
- M8.4c apply_tpdf_dither()
- M8.5  parse_mix_intent() / apply_intent_to_plan()
"""

from __future__ import annotations

import os
import numpy as np


# ---------------------------------------------------------------------------
# M8.1 — Stereo Image Comparison
# ---------------------------------------------------------------------------
from audio_analysis.analysis_core.reference_matching import stereo_image_comparison


class TestStereoImageComparison:

    def _metrics(self, width=0.45, balance=1.0, correlation=0.85) -> dict:
        return {"stereo_width_ratio": width, "stereo_balance": balance, "stereo_correlation": correlation}

    def test_matched_stereo_returns_no_issues(self):
        """Identical metrics should produce near-zero deltas and no warning advice."""
        m = self._metrics()
        result = stereo_image_comparison(m, m)
        assert abs(result["width_delta"]) < 0.01
        assert abs(result["balance_delta"]) < 0.01
        assert "well-matched" in result["advice"][0].lower()

    def test_over_wide_mix_flagged(self):
        """Mix significantly wider than reference should be flagged."""
        mix = self._metrics(width=0.80)
        ref = self._metrics(width=0.40)
        result = stereo_image_comparison(mix, ref)
        assert result["width_delta"] > 0.1
        assert result["width_correction_db"] < 0  # suggests reducing side

    def test_mono_safety_flag(self):
        """Mono-safe reference + phase-risky mix should set mono_safety flag."""
        mix = self._metrics(correlation=0.3)
        ref = self._metrics(correlation=0.9)
        result = stereo_image_comparison(mix, ref)
        assert result["mono_safety"] is True

    def test_result_keys_present(self):
        m = self._metrics()
        result = stereo_image_comparison(m, m)
        for k in ("width_delta", "balance_delta", "correlation_delta", "width_correction_db", "mono_safety", "advice"):
            assert k in result

    def test_width_correction_capped(self):
        """width_correction_db should never exceed ±6 dB regardless of extremes."""
        big = self._metrics(width=1.0)
        small = self._metrics(width=0.0)
        result = stereo_image_comparison(big, small)
        assert abs(result["width_correction_db"]) <= 6.0


# ---------------------------------------------------------------------------
# M8.4c — TPDF Dither
# ---------------------------------------------------------------------------
from audio_analysis.dsp_engine.dither import apply_tpdf_dither


class TestApplyTpdfDither:

    def test_output_shape_unchanged(self):
        signal = np.zeros(1024, dtype=np.float32)
        result = apply_tpdf_dither(signal, bit_depth=16)
        assert result.shape == signal.shape

    def test_dtype_preserved(self):
        signal = np.zeros(512, dtype=np.float64)
        result = apply_tpdf_dither(signal, bit_depth=16)
        assert result.dtype == np.float64

    def test_dither_adds_noise(self):
        """Dithered silence should not be all-zero."""
        silence = np.zeros(4096, dtype=np.float32)
        result = apply_tpdf_dither(silence, bit_depth=16)
        assert not np.all(result == 0.0)

    def test_dither_magnitude_within_2_lsb(self):
        """TPDF dither spans ±1 LSB; max deviation should be within 2 LSB for 16-bit."""
        silence = np.zeros(8192, dtype=np.float32)
        result = apply_tpdf_dither(silence, bit_depth=16)
        lsb = 2.0 / (2 ** 16)
        assert float(np.max(np.abs(result))) <= 2.0 * lsb + 1e-9

    def test_empty_input_unchanged(self):
        empty = np.zeros(0, dtype=np.float32)
        result = apply_tpdf_dither(empty, bit_depth=16)
        assert result.shape == (0,)


# ---------------------------------------------------------------------------
# M8.5 — NL Intent Parsing
# ---------------------------------------------------------------------------
from audio_analysis.integration.mix_intent import parse_mix_intent


class TestParseMixIntent:

    def setup_method(self):
        os.environ.pop("AUDIO_TOO_MIX_REVIEW_LLM", None)

    def test_brightness_instruction(self):
        """'make the vocal brighter' → master bus highshelf adjustment."""
        intent = parse_mix_intent("make the vocal brighter", {})
        assert intent["direction"] == "up"
        assert intent["target_stem"] in ("vocal", "all")
        assert intent["parameter"] == "brightness"

    def test_quieter_instruction(self):
        intent = parse_mix_intent("make the kick quieter", {})
        assert intent["direction"] == "down"

    def test_bass_instruction(self):
        intent = parse_mix_intent("more bass warmth", {})
        assert intent["target_stem"] in ("bass", "all")

    def test_returns_required_keys(self):
        intent = parse_mix_intent("punchier kick", {})
        for k in ("target_stem", "parameter", "direction", "magnitude"):
            assert k in intent

    def test_empty_instruction_returns_default(self):
        intent = parse_mix_intent("", {})
        assert "parameter" in intent
        assert "direction" in intent


# ---------------------------------------------------------------------------
# M8.3 — load_mix_modifiers (stub test, no DB)
# ---------------------------------------------------------------------------
from audio_analysis.integration.quality_predictor import load_mix_modifiers


class TestLoadMixModifiers:

    def test_returns_empty_when_no_connect_func(self):
        """No connect_func → empty dict."""
        result = load_mix_modifiers("pop", connect_func=None)
        assert result == {}

    def test_returns_empty_for_insufficient_data(self):
        """connect_func returning empty list → empty dict."""
        def noop_connect():
            pass

        from unittest.mock import patch
        with patch("audio_analysis.mix_review.review_store.load_feedback_training_data", return_value=[]):
            result = load_mix_modifiers("pop", connect_func=noop_connect)
        assert result == {}
