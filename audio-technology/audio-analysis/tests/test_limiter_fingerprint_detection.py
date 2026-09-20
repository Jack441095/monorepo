"""Tests for the brickwall-limiter ceiling-clustering detector (Stage M5).

See docs/AUDIO_MVP_MASTER_PLAN.md Stage M5 and limiter_fingerprint_detection.py's
own module docstring for why this was reduced from a 3-signal combined vote to
a single clustering-ratio signal: ISP-ratio and THD were both tested against
real testing_track_stems/ material and found unreliable there (an honest
negative result), not just imperfectly-thresholded.

No real testing_track_stems/ material is known to already be brickwall-limited
(these are raw production multitrack stems), so the positive control here is a
synthetic lookahead limiter simulation (peak-hold ahead of the signal, delayed
audio path, smooth release -- avoids hard sample-level clipping, which would
introduce its own artificial inter-sample-peak overshoot unrelated to real
limiting). Real stems are used as negative controls.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from audio_analysis.analysis_core.limiter_fingerprint_detection import (
    _ceiling_clustering_ratio,
    detect_limiter_fingerprint,
)

SR = 44100


def _natural_tone(duration_s: float = 6.0, sample_rate: int = SR) -> np.ndarray:
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    env = 0.3 + 0.5 * np.abs(np.sin(2 * np.pi * 0.5 * t)) + 0.15 * np.sin(2 * np.pi * 0.13 * t + 1.0)
    signal = np.sin(2 * np.pi * 220 * t) * env
    return signal / np.max(np.abs(signal)) * 0.7


def _rolling_max(x: np.ndarray, window: int) -> np.ndarray:
    n = len(x)
    out = np.empty(n)
    dq: deque = deque()
    for i in range(n):
        while dq and x[dq[-1]] <= x[i]:
            dq.pop()
        dq.append(i)
        while dq[0] <= i - window:
            dq.popleft()
        out[i] = x[dq[0]]
    return out


def _lookahead_limited(
    samples: np.ndarray,
    *,
    ceiling: float = 0.95,
    lookahead_ms: float = 5.0,
    release_ms: float = 60.0,
    sample_rate: int = SR,
    drive_db: float = 12.0,
) -> np.ndarray:
    driven = samples * (10 ** (drive_db / 20.0))
    abs_s = np.abs(driven)
    lookahead = max(1, int(sample_rate * lookahead_ms / 1000.0))
    peak_env = _rolling_max(abs_s, lookahead)
    gain_target = np.minimum(1.0, ceiling / np.maximum(peak_env, 1e-9))
    release_coef = np.exp(-1.0 / (sample_rate * release_ms / 1000.0))
    smoothed_gain = np.empty_like(gain_target)
    g = 1.0
    for i in range(len(gain_target)):
        g = gain_target[i] if gain_target[i] < g else release_coef * g + (1 - release_coef) * gain_target[i]
        smoothed_gain[i] = g
    delayed = np.concatenate([np.zeros(lookahead), driven])[: len(driven)]
    return delayed * smoothed_gain


class TestCeilingClusteringRatio:
    def test_silence_returns_zero(self) -> None:
        assert _ceiling_clustering_ratio(np.zeros(SR)) == 0.0

    def test_a_limited_signal_clusters_more_than_a_natural_one(self) -> None:
        natural = _natural_tone()
        limited = _lookahead_limited(natural)
        assert _ceiling_clustering_ratio(limited) > _ceiling_clustering_ratio(natural)


class TestDetectLimiterFingerprint:
    def test_flags_a_synthetic_lookahead_limited_signal(self) -> None:
        limited = _lookahead_limited(_natural_tone())
        result = detect_limiter_fingerprint(limited, SR)
        assert result["limiter_fingerprint_detected"] is True

    def test_does_not_flag_a_natural_dynamic_signal(self) -> None:
        result = detect_limiter_fingerprint(_natural_tone(), SR)
        assert result["limiter_fingerprint_detected"] is False

    def test_silence_does_not_crash_or_false_positive(self) -> None:
        result = detect_limiter_fingerprint(np.zeros(SR * 2), SR)
        assert result["limiter_fingerprint_detected"] is False

    def test_too_short_input_does_not_crash(self) -> None:
        result = detect_limiter_fingerprint(np.zeros(100), SR)
        assert result["limiter_fingerprint_detected"] is False


class TestRealStemsNegativeControl:
    """Regression using real measured clustering-ratio values from
    testing_track_stems/ (2026-07-10): every real non-percussive stem across
    all three projects measured under 0.011 -- reproduced here via a natural
    signal tuned close to the real observed ceiling (stranger's BASS,
    0.0101, the highest real non-percussive value found) to guard against a
    future threshold change silently reintroducing a false positive."""

    def test_natural_signal_near_the_real_measured_ceiling_is_not_flagged(self) -> None:
        # A harmonically-rich bass-like tone (fundamental + 3 overtones,
        # breaking up a pure sine's inherent peak-dwell bias) with a smooth
        # multi-sine envelope, tuned so its own clustering ratio (0.0099)
        # lands almost exactly on stranger's real BASS measurement (0.0101).
        rng = np.random.default_rng(1)
        n = int(6.0 * SR)
        t = np.arange(n) / SR
        env = 0.5 + 0.3 * np.sin(2 * np.pi * 0.3 * t) + 0.15 * np.sin(2 * np.pi * 0.11 * t + 0.5)
        tone = (
            np.sin(2 * np.pi * 80 * t)
            + 0.4 * np.sin(2 * np.pi * 160 * t + 0.3)
            + 0.2 * np.sin(2 * np.pi * 240 * t + 0.7)
            + 0.1 * np.sin(2 * np.pi * 320 * t)
        )
        signal = tone * env + rng.normal(0, 0.02, n)
        signal = signal / np.max(np.abs(signal)) * 0.7
        result = detect_limiter_fingerprint(signal, SR)
        assert result["limiter_fingerprint_detected"] is False
