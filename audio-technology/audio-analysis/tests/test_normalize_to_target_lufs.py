"""Tests for normalize_to_target_lufs() -- the closed-loop gain solve +
true-peak-safe limiter, extracted (2026-08-01, pure refactor) out of what
used to be inline in mix_and_render_stems' "9. Master Loudness
Normalization & Limiting" stage. That extraction was verified bit-identical
against the pre-refactor code (same wav bytes, same measured_lufs, same
loudness_solver diagnostics dict, dither neutralized to isolate the
deterministic gain-solve path) via a git-worktree A/B comparison -- this
file is the permanent, fast, committed regression coverage for the
extracted function on its own, independent of the full stem-mixing
pipeline mix_and_render_stems' own tests already exercise it through.
"""

from __future__ import annotations

import numpy as np

from audio_analysis.analysis_core.loudness import calculate_loudness_profile, calculate_true_peak
from audio_analysis.mixdown.mix_renderer import normalize_to_target_lufs

SR = 44100
DURATION_S = 6.0
N = int(SR * DURATION_S)
_T = np.arange(N) / SR


def _tone(freq: float, *, amplitude: float = 0.3, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    harm = sum(np.sin(2 * np.pi * freq * k * _T) / k for k in (1, 2, 3))
    noise = rng.normal(0, 1, N) * 0.02
    sig = (harm * amplitude + noise).astype(np.float64)
    return sig.copy(), sig.copy()


def test_converges_to_target_lufs_within_tolerance():
    left, right = _tone(220.0, amplitude=0.15)
    out_l, out_r, final_lufs, diag = normalize_to_target_lufs(
        left, right, SR, target_lufs=-11.0, ceiling_db=-1.0,
    )
    assert abs(final_lufs - (-11.0)) < 0.15
    measured = calculate_loudness_profile(out_l, out_r, SR)
    assert abs(measured["integrated_lufs"] - (-11.0)) < 0.15


def test_true_peak_ceiling_is_respected():
    # A hot, already-loud signal that needs real gain reduction (not boost)
    # to reach a conservative target -- exercises the safety check, not
    # just the happy path.
    left, right = _tone(440.0, amplitude=0.95)
    out_l, out_r, final_lufs, diag = normalize_to_target_lufs(
        left, right, SR, target_lufs=-14.0, ceiling_db=-1.0,
    )
    true_peak = calculate_true_peak(out_l, out_r, SR)
    assert true_peak <= -1.0 + 0.2  # ceiling + generous margin for measurement-path variance


def test_diagnostics_shape():
    left, right = _tone(220.0, amplitude=0.2)
    _, _, final_lufs, diag = normalize_to_target_lufs(
        left, right, SR, target_lufs=-11.0, ceiling_db=-1.0,
    )
    for key in (
        "ceiling_dbtp", "calibration_headroom_db", "limiter_release_ms",
        "proactive_crest_reduction", "crest_reduction", "gain_attempts",
        "selected_lufs", "selected_gap_lu", "found_safe_candidate",
    ):
        assert key in diag
    assert diag["ceiling_dbtp"] == -1.0
    assert diag["selected_lufs"] == final_lufs
    assert isinstance(diag["gain_attempts"], list) and len(diag["gain_attempts"]) >= 1
    assert diag["found_safe_candidate"] is True


def test_proactive_crest_reduction_flag_engages_when_requested():
    # A wide-crest signal (sparse sharp transients over a quiet sustain) is
    # exactly what this stage exists to correct.
    rng = np.random.default_rng(3)
    sustain = rng.normal(0, 0.04, N)
    left = sustain.copy()
    for pos in rng.integers(0, N - 200, size=10):
        left[pos:pos + 50] += 0.9
    right = left.copy()

    _, _, _, diag_off = normalize_to_target_lufs(
        left.copy(), right.copy(), SR, target_lufs=-11.0, ceiling_db=-1.0,
        apply_proactive_crest_reduction=False,
    )
    _, _, _, diag_on = normalize_to_target_lufs(
        left.copy(), right.copy(), SR, target_lufs=-11.0, ceiling_db=-1.0,
        apply_proactive_crest_reduction=True,
    )
    assert diag_off["proactive_crest_reduction"]["engaged"] is False
    assert diag_on["proactive_crest_reduction"]["engaged"] is True


def test_threshold_offset_shifts_the_limiter_without_changing_target_lufs():
    """threshold_offset_db (bus_config.limiter_threshold_db) should still
    let the closed loop converge on the same target -- it's an offset on
    the limiter threshold input, not an override of the loudness target."""
    left, right = _tone(220.0, amplitude=0.2)
    _, _, final_lufs_a, _ = normalize_to_target_lufs(
        left.copy(), right.copy(), SR, target_lufs=-11.0, ceiling_db=-1.0, threshold_offset_db=0.0,
    )
    _, _, final_lufs_b, _ = normalize_to_target_lufs(
        left.copy(), right.copy(), SR, target_lufs=-11.0, ceiling_db=-1.0, threshold_offset_db=2.0,
    )
    assert abs(final_lufs_a - (-11.0)) < 0.15
    assert abs(final_lufs_b - (-11.0)) < 0.15
