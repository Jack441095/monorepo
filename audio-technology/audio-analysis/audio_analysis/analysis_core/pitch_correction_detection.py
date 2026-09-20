"""Pitch-correction (Auto-Tune/Melodyne-style) quantization signature — Stage M4a.

See docs/AUDIO_MVP_MASTER_PLAN.md Stage M4a. Hard pitch correction leaves a
measurable signature: the frame-by-frame fundamental-frequency track snaps to
exact equal-tempered semitone values with abnormally low variance, instead of
the continuous drift/vibrato/portamento a natural voice always has to some
degree. This runs the existing, proven `detect_fundamental_pitch()`
repeatedly across short successive frames (it currently runs once per whole
clip; this is a thin per-frame wrapper, not new pitch-tracking math) and
looks at how tightly the resulting f0 track clusters on the 12-tone
equal-tempered grid.

Downstream value is narrower and more honest than the other Stage M
candidates: the originally-proposed tie-in (suppressing a false positive in
Stage M3's key-consistency check) no longer applies -- M3's key-consistency
half was investigated and dropped as unreliable (see M3's own write-up), so
there is nothing left for this detector to suppress there. What remains is a
genuine, checkable diagnostic flag: a Mix Review annotation KENN can cite
when a vocal's pitch reads as unusually stable, surfaced the same
reported-flag-not-auto-fail way as every other Stage M candidate.
"""

from __future__ import annotations

import math

import numpy as np

from .distortion_resonance import detect_fundamental_pitch

# Calibrated against real vocal stems in testing_track_stems/ (2026-07-10):
# natural (uncorrected) vocal takes measured cents_std in the 15.2-24.7 range
# (a chopped/edited reggueton_pop vocal sample sat closest to the boundary at
# 15.15) and near_grid_share 0.09-0.33 -- both real-world floors sit well
# clear of these thresholds, with near_grid_share providing most of the
# margin as a second, independent AND-condition.
CENTS_STD_THRESHOLD = 12.0
NEAR_GRID_SHARE_THRESHOLD = 0.55
NEAR_GRID_CENTS_WINDOW = 5.0
MIN_VOICED_FRAMES = 30


def _cents_from_nearest_semitone(f0_hz: float) -> float:
    """Deviation, in cents, of `f0_hz` from the nearest 12-tone
    equal-tempered semitone (A440 reference)."""
    midi = 69.0 + 12.0 * math.log2(f0_hz / 440.0)
    nearest = round(midi)
    return (midi - nearest) * 100.0


def _frame_pitch_track(
    samples: np.ndarray,
    sample_rate: int,
    *,
    frame_size: int = 2048,
    hop_size: int = 1024,
) -> list[float]:
    f0s: list[float] = []
    for start in range(0, len(samples) - frame_size + 1, hop_size):
        frame = samples[start : start + frame_size]
        f0s.append(detect_fundamental_pitch(frame, sample_rate))
    return f0s


def detect_pitch_correction_signature(
    samples: np.ndarray,
    sample_rate: int,
    *,
    frame_size: int = 2048,
    hop_size: int = 1024,
    cents_std_threshold: float = CENTS_STD_THRESHOLD,
    near_grid_share_threshold: float = NEAR_GRID_SHARE_THRESHOLD,
    min_voiced_frames: int = MIN_VOICED_FRAMES,
) -> dict:
    """Check a vocal (or other monophonic melodic) stem's frame-by-frame
    pitch track for a hard-pitch-correction signature.

    Returns
    -------
    dict
        - "pitch_correction_detected": bool
        - "voiced_frame_count": int
        - "cents_std": float | None (std-dev of deviation from the nearest
          semitone, across all voiced frames -- low means "locked to grid")
        - "near_grid_share": float | None (fraction of voiced frames within
          `NEAR_GRID_CENTS_WINDOW` cents of an exact semitone)
    """
    empty = {
        "pitch_correction_detected": False,
        "voiced_frame_count": 0,
        "cents_std": None,
        "near_grid_share": None,
    }
    if sample_rate <= 0 or len(samples) < frame_size * 2:
        return empty

    f0_track = _frame_pitch_track(samples, sample_rate, frame_size=frame_size, hop_size=hop_size)
    voiced = [f0 for f0 in f0_track if f0 > 0.0]
    if len(voiced) < min_voiced_frames:
        return empty

    cents = np.asarray([_cents_from_nearest_semitone(f0) for f0 in voiced], dtype=np.float64)
    cents_std = float(np.std(cents))
    near_grid_share = float(np.mean(np.abs(cents) < NEAR_GRID_CENTS_WINDOW))

    detected = cents_std < cents_std_threshold and near_grid_share > near_grid_share_threshold

    return {
        "pitch_correction_detected": detected,
        "voiced_frame_count": len(voiced),
        "cents_std": round(cents_std, 2),
        "near_grid_share": round(near_grid_share, 3),
    }
