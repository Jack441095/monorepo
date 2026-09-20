"""Smoke tests for scripts/eval/reference_track_comparison.py.

This script is glue over already-tested analysis_core functions (tonal
balance, dynamics, stereo image) — these tests verify the glue itself:
report shape, self-comparison sanity, and the markdown/EQ8 export path.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path("/Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Audio_Too")
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

from reference_track_comparison import compare_tracks, render_markdown_report  # noqa: E402

SR = 44100
DURATION_S = 4.0
N = int(SR * DURATION_S)
_T = np.arange(N) / SR


def _write_wav(path: Path, left: np.ndarray, right: np.ndarray, sr: int = SR):
    left16 = np.clip(left, -1, 1) * 32767
    right16 = np.clip(right, -1, 1) * 32767
    interleaved = np.empty(2 * N, dtype=np.int16)
    interleaved[0::2] = left16.astype(np.int16)
    interleaved[1::2] = right16.astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(interleaved.tobytes())


def _tone_mix(seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    sig = (
        0.2 * np.sin(2 * np.pi * 80 * _T)
        + 0.15 * np.sin(2 * np.pi * 500 * _T)
        + 0.1 * np.sin(2 * np.pi * 4000 * _T)
        + rng.normal(0, 0.01, N)
    ).astype(np.float64)
    return sig, sig.copy()


@pytest.fixture
def two_wavs(tmp_path):
    l1, r1 = _tone_mix(1)
    l2, r2 = _tone_mix(2)
    p1 = tmp_path / "mix.wav"
    p2 = tmp_path / "ref.wav"
    _write_wav(p1, l1, r1)
    _write_wav(p2, l2, r2)
    return p1, p2


class TestCompareTracks:
    def test_report_has_expected_shape(self, two_wavs):
        mix_path, ref_path = two_wavs
        report = compare_tracks(mix_path, ref_path, "mix-label", "ref-label")
        assert report["mix"]["label"] == "mix-label"
        assert report["reference"]["label"] == "ref-label"
        assert 0.0 <= report["tonal_balance"]["score_0_100"] <= 100.0
        assert set(report["tonal_balance"]["mix_bands_7"]) == {
            "sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"
        }
        assert "crest_delta_db" in report["dynamics"]
        assert "width_delta" in report["stereo_image"]

    def test_self_comparison_scores_near_perfect(self, two_wavs):
        """A track compared against itself should score very highly on tonal
        balance and show ~zero dynamics/stereo delta."""
        mix_path, _ = two_wavs
        report = compare_tracks(mix_path, mix_path, "self", "self")
        assert report["tonal_balance"]["score_0_100"] >= 95.0
        assert abs(report["dynamics"]["crest_delta_db"]) < 0.5
        assert abs(report["stereo_image"]["correlation_delta"]) < 0.01

    def test_markdown_report_renders_without_error(self, two_wavs):
        mix_path, ref_path = two_wavs
        report = compare_tracks(mix_path, ref_path, "mix-label", "ref-label")
        md = render_markdown_report(report)
        assert "mix-label" in md
        assert "ref-label" in md
        assert "Tonal balance" in md
        assert "Suggested EQ gain" in md

    def test_eq_gains_are_within_musical_range(self, two_wavs):
        mix_path, ref_path = two_wavs
        report = compare_tracks(mix_path, ref_path, "mix-label", "ref-label")
        for gain in report["tonal_balance"]["suggested_eq_gains_db"].values():
            assert -6.0 <= gain <= 6.0
