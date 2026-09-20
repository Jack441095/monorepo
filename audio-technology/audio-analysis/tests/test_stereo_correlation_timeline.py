"""Tests for stereo_correlation_timeline() — A6.2 Correlation-Over-Time Vectorscope Data."""

from __future__ import annotations

import math
import pytest

from audio_analysis.analysis_core.analysis_features import stereo_correlation_timeline


SR = 44100
_440 = [math.sin(2 * math.pi * 440 * i / SR) * 0.3 for i in range(SR * 2)]


class TestStereoCorrelationTimeline:

    def test_correlated_signal_has_no_dips(self):
        """In-phase identical L/R → correlation ~1.0 throughout, no dip events."""
        result = stereo_correlation_timeline(_440, list(_440), SR)
        assert all(c > 0.95 for c in result["correlation"]), "Expected near-unity correlation for in-phase stereo"
        assert result["dip_events"] == []

    def test_out_of_phase_creates_dip_event(self):
        """Fully inverted R → correlation ~-1.0 throughout, at least one dip event."""
        anti = [-v for v in _440]
        result = stereo_correlation_timeline(_440, anti, SR)
        assert all(c < -0.95 for c in result["correlation"]), "Expected near-negative correlation for anti-phase stereo"
        assert len(result["dip_events"]) >= 1
        assert result["dip_events"][0]["min_correlation"] < 0

    def test_dip_event_fields_present(self):
        """Dip events contain required fields."""
        anti = [-v for v in _440]
        result = stereo_correlation_timeline(_440, anti, SR)
        dip = result["dip_events"][0]
        assert "start_seconds" in dip
        assert "end_seconds" in dip
        assert "duration_seconds" in dip
        assert "min_correlation" in dip
        assert dip["duration_seconds"] > 0

    def test_vectorscope_within_point_budget(self):
        """Point count stays at or below the requested budget."""
        result = stereo_correlation_timeline(_440, list(_440), SR, vectorscope_points=500)
        assert len(result["vectorscope_points"]) <= 550  # small tolerance for stride rounding

    def test_vectorscope_coordinate_format(self):
        """Each vectorscope point is a two-element [x, y] list."""
        result = stereo_correlation_timeline(_440, list(_440), SR, vectorscope_points=100)
        assert len(result["vectorscope_points"]) > 0
        for pt in result["vectorscope_points"][:10]:
            assert len(pt) == 2
            assert isinstance(pt[0], float)
            assert isinstance(pt[1], float)

    def test_ms_rotation_mono_is_vertical(self):
        """Mono (L==R) → side channel = 0 → x ≈ 0 for all points."""
        mono = [math.sin(2 * math.pi * 220 * i / SR) * 0.3 for i in range(SR)]
        result = stereo_correlation_timeline(mono, list(mono), SR, vectorscope_points=200)
        xs = [pt[0] for pt in result["vectorscope_points"]]
        assert all(abs(x) < 0.01 for x in xs), "Mono signal should produce near-zero x (side) on vectorscope"

    def test_window_seconds_matches_output(self):
        """Timestamps are spaced by window_seconds."""
        n_windows = 5
        n_samples = int(SR * 0.1 * n_windows)
        left = [math.sin(2 * math.pi * 440 * i / SR) * 0.3 for i in range(n_samples)]
        result = stereo_correlation_timeline(left, list(left), SR, window_seconds=0.1)
        assert len(result["timestamps"]) == n_windows
        for i in range(1, len(result["timestamps"])):
            gap = result["timestamps"][i] - result["timestamps"][i - 1]
            assert pytest.approx(gap, abs=0.001) == 0.1

    def test_empty_input_returns_empty(self):
        """Empty arrays → all lists empty, no errors."""
        result = stereo_correlation_timeline([], [], SR)
        assert result["timestamps"] == []
        assert result["correlation"] == []
        assert result["balance"] == []
        assert result["dip_events"] == []
        assert result["vectorscope_points"] == []

    def test_custom_dip_threshold(self):
        """Only windows below the threshold count as dips."""
        # Partially decorrelated: correlation ~0.5 (phase shifted by π/3)
        shifted = [math.sin(2 * math.pi * 440 * i / SR + math.pi / 3) * 0.3 for i in range(SR * 2)]
        result_loose = stereo_correlation_timeline(_440, shifted, SR, dip_threshold=0.8)
        result_strict = stereo_correlation_timeline(_440, shifted, SR, dip_threshold=0.2)
        # At a loose threshold we expect dips; at 0.2 the ~0.5 correlation is above threshold
        assert len(result_loose["dip_events"]) >= len(result_strict["dip_events"])
