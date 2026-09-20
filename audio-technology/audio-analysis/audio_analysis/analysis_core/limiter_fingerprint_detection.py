"""Existing brickwall-limiter fingerprint on an individual stem — Stage M5.

See docs/AUDIO_MVP_MASTER_PLAN.md Stage M5. `mix_decision_engine.py`'s existing
"already compressed" heuristic reads `crest_factor_db < 10` as one generic
signal -- it cannot tell a naturally low-crest sustained pad or drone apart
from a stem that's already been run through a brickwall limiter. This module
measures **ceiling clustering**: a limiter's gain-reduction envelope pushes a
disproportionate share of a stem's ACTIVE samples into a narrow band just
under its own peak (the limiter's own "shelf"); natural, unprocessed material
is comparatively sparse there.

**Originally designed as a 3-signal combined vote; reduced to 1 after real
testing -- an honest negative result, the same discipline Stage M3's
key-consistency check used.** The other two proposed signals were tested
against all three real `testing_track_stems/` projects (2026-07-10) and found
unreliable, not just imperfectly-thresholded:

- **ISP-to-sample-peak ratio** (`detect_isp()`) saturated near 1.0 for almost
  every real stem, tonal or not (e.g. PIANO, STRINGS, BASS all measured
  0.97-1.0) -- most stems here are digitally produced/sample-based
  (synths, one-shots, loops), which naturally has near-zero inter-sample
  overshoot as a byproduct of how the audio was created, not evidence of
  buss-level brickwall limiting. It doesn't discriminate on this kind of
  material.
- **THD** (`analyze_thd_n()`) produced values with no sane bound on real
  polyphonic/complex stems -- as high as 4945 (not a percentage; the
  function's f0-detection-based harmonic-accounting assumes clean
  monophonic tonal content, confirmed by a direct sanity check: a clean
  single sine measures 0.0 THD as expected, but real multi-voice synth/pad
  stems broke the fundamental detection it depends on). Not a threshold
  problem -- the underlying measurement itself is unreliable on this input.

Ceiling clustering alone measured cleanly on real material: every real
non-percussive stem across all three projects landed under 0.011, comfortably
below the calibrated 0.04 threshold, while a synthetic lookahead-limiter
positive control measured 0.08-0.28. Percussive one-shot instruments (kick,
snare, drum loops) were EXCLUDED from this calibration and must be excluded
from wherever this detector is wired in production -- real KICK/SNARE/DRUMS
stems measured 0.055-0.209 clustering purely from repeated, similar-peak
transient hits, an inherent property of that instrument type, not evidence of
limiting.
"""

from __future__ import annotations

import numpy as np

# Calibrated against all three real testing_track_stems/ projects
# (2026-07-10): every real non-percussive stem measured under 0.011; a
# synthetic lookahead-limiter positive control measured 0.08-0.28.
CEILING_WINDOW_DB = 1.0
ACTIVE_FLOOR_DB = 20.0
CLUSTERING_RATIO_THRESHOLD = 0.04


def _ceiling_clustering_ratio(
    samples: np.ndarray,
    *,
    window_db: float = CEILING_WINDOW_DB,
    active_floor_db: float = ACTIVE_FLOOR_DB,
) -> float:
    """Of a stem's ACTIVE (non-quiet) samples, what fraction sit within
    `window_db` of the stem's own peak -- a limiter's gain-reduction shelf
    shows up as a disproportionately dense cluster here.

    Restricted to active samples (within `active_floor_db` of peak) rather
    than the whole file: real music has quiet passages whose sample count
    would otherwise dilute the ratio regardless of whether the loud
    passages are limited or not, since limiting only ever affects the
    already-loud portions of a signal.
    """
    abs_samples = np.abs(samples)
    peak = float(np.max(abs_samples)) if len(abs_samples) else 0.0
    if peak < 1e-9:
        return 0.0
    active_threshold = peak * 10 ** (-active_floor_db / 20.0)
    active = abs_samples[abs_samples >= active_threshold]
    if len(active) == 0:
        return 0.0
    ceiling_threshold = peak * 10 ** (-window_db / 20.0)
    return float(np.mean(active >= ceiling_threshold))


def detect_limiter_fingerprint(
    samples: np.ndarray,
    sample_rate: int,
    *,
    clustering_ratio_threshold: float = CLUSTERING_RATIO_THRESHOLD,
) -> dict:
    """Check a stem for a brickwall-limiter ceiling-clustering fingerprint.

    Only meaningful for sustained/melodic material -- percussive one-shot
    instruments (kick, snare, drum loops/busses) show the same clustering
    signature from repeated similar-peak transient hits, unrelated to
    limiting, and must be excluded by the caller before trusting this flag.

    Returns
    -------
    dict
        - "limiter_fingerprint_detected": bool
        - "clustering_ratio": float
    """
    empty = {"limiter_fingerprint_detected": False, "clustering_ratio": 0.0}
    if sample_rate <= 0 or len(samples) < 512:
        return empty

    clustering_ratio = _ceiling_clustering_ratio(samples)
    return {
        "limiter_fingerprint_detected": clustering_ratio > clustering_ratio_threshold,
        "clustering_ratio": round(clustering_ratio, 4),
    }
