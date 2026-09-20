"""Tests for analyze_pcm_chunk() — A8.1 Live Audio Stream Analysis."""

from __future__ import annotations

import math
import struct

from audio_analysis.analysis_core.stream_analysis import analyze_pcm_chunk


_SR = 44100
_CHANNELS = 2
_DURATION_S = 0.4  # 400ms


def _make_pcm(freq: float = 440.0, amplitude: float = 0.3, sample_rate: int = _SR, duration: float = _DURATION_S) -> bytes:
    """Generate a stereo 16-bit signed PCM chunk of a sine tone."""
    n = int(sample_rate * duration)
    samples: list[int] = []
    for i in range(n):
        val = int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / sample_rate))
        val = max(-32768, min(32767, val))
        samples.append(val)  # left
        samples.append(val)  # right
    return struct.pack(f"<{len(samples)}h", *samples)


class TestAnalyzePcmChunk:

    def test_returns_expected_keys(self):
        """Result dict has all required keys."""
        pcm = _make_pcm()
        result = analyze_pcm_chunk(pcm, sample_rate=_SR, channels=2)
        for key in ("lufs_momentary", "bands", "correlation", "balance", "sample_count"):
            assert key in result, f"Missing key: {key}"

    def test_lufs_is_finite_and_negative(self):
        """LUFS for a non-silent signal should be finite and negative."""
        pcm = _make_pcm(amplitude=0.3)
        result = analyze_pcm_chunk(pcm, sample_rate=_SR, channels=2)
        lufs = result["lufs_momentary"]
        assert isinstance(lufs, float)
        assert math.isfinite(lufs)
        assert lufs < 0.0, f"Expected negative LUFS, got {lufs}"

    def test_silence_returns_low_lufs(self):
        """Silent PCM should yield very low (near -70) LUFS."""
        silence = bytes(int(_SR * _DURATION_S) * _CHANNELS * 2)  # all zeros
        result = analyze_pcm_chunk(silence, sample_rate=_SR, channels=2)
        assert result["lufs_momentary"] <= -60.0

    def test_bands_present_and_sum_roughly_one(self):
        """7-band spectrum should be present and sum to ~1.0."""
        pcm = _make_pcm()
        result = analyze_pcm_chunk(pcm, sample_rate=_SR, channels=2)
        bands = result["bands"]
        assert len(bands) > 0
        total = sum(bands.values())
        assert abs(total - 1.0) < 0.05, f"Bands sum to {total}, expected ~1.0"

    def test_in_phase_stereo_has_high_correlation(self):
        """Identical L/R channels → correlation close to 1.0."""
        pcm = _make_pcm()
        result = analyze_pcm_chunk(pcm, sample_rate=_SR, channels=2)
        assert result["correlation"] > 0.90, f"Expected high correlation, got {result['correlation']}"

    def test_correlation_in_valid_range(self):
        """Correlation must always be in [-1, 1]."""
        pcm = _make_pcm()
        result = analyze_pcm_chunk(pcm, sample_rate=_SR, channels=2)
        assert -1.0 <= result["correlation"] <= 1.0

    def test_balance_near_zero_for_equal_channels(self):
        """Identical L/R → balance near 0."""
        pcm = _make_pcm()
        result = analyze_pcm_chunk(pcm, sample_rate=_SR, channels=2)
        assert abs(result["balance"]) < 0.05, f"Expected balance near 0, got {result['balance']}"

    def test_sample_count_correct(self):
        """sample_count should match n_bytes // (2 bytes * channels)."""
        n_samples = int(_SR * _DURATION_S)
        pcm = _make_pcm()
        result = analyze_pcm_chunk(pcm, sample_rate=_SR, channels=2)
        assert result["sample_count"] == n_samples

    def test_mono_input(self):
        """Mono input (channels=1) should work without errors."""
        n = int(_SR * _DURATION_S)
        raw = [int(0.3 * 32767 * math.sin(2 * math.pi * 440 * i / _SR)) for i in range(n)]
        pcm = struct.pack(f"<{n}h", *raw)
        result = analyze_pcm_chunk(pcm, sample_rate=_SR, channels=1)
        assert result["sample_count"] == n
        assert math.isfinite(result["lufs_momentary"])

    def test_empty_input_returns_safe_defaults(self):
        """Empty bytes should not raise; defaults returned."""
        result = analyze_pcm_chunk(b"", sample_rate=_SR, channels=2)
        assert result["sample_count"] == 0
        assert result["lufs_momentary"] == -70.0
