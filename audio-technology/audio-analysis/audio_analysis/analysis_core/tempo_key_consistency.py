"""Tempo consistency check across stems in the same project — Stage M3.

See docs/AUDIO_MVP_MASTER_PLAN.md Stage M3. `estimate_bpm()` is proven but
never compared *across stems within one project* -- nothing today catches a
wrong take or an unquantized/differently-timed element relative to the rest
of the project. This is a new comparison layer over an existing per-signal
output, not new DSP: it reuses `transient_groove.detect_transient_onsets()`/
`estimate_bpm()` unchanged.

**Key-consistency was investigated and dropped -- an honest negative result.**
The original Stage M3 design (see the plan doc) also proposed comparing each
stem's `detect_chords_and_key()` estimate against a project-wide consensus.
Tested against real `testing_track_stems/` stems (2026-07-10): nearly every
stem in both real multi-instrument projects was flagged "key inconsistent" --
including KICK, CLAP, HATS, and PERC, none of which carry real tonal content.
`key_confidence_score` turned out not to be a reliable tonality gate at all: a
synthetic pure-noise control scored a *higher* key confidence (0.97) than a
real major triad (0.93). Separately, even genuinely tonal real stems in the
*same* song (STRINGS, LEAD, GUITAR, BASS, PIANO) each landed on a different
best-matching key, because `detect_chords_and_key()`'s whole-track chroma
average is sensitive to which notes/register each instrument happens to play,
not a stable per-song "true key" signal. Both problems are structural, not a
threshold-tuning issue, so key-consistency is not shipped here -- reported
plainly rather than forced to pass, the same discipline the equal-loudness
spectral-centroid experiment used earlier in Stage M.

This is a reported flag for human judgment (intended to be surfaced via the
mix plan's `decisions_log`, mirroring Stage A's own "bright bass" precedent),
not an auto-fail -- tempo estimation on a single, sparsely-onset instrument
stem is inherently noisier than on a full mix, so some false positives on
ambiguous one-shot/FX-type stems are expected and acceptable for a
please-confirm flag, unlike an auto-correcting action.
"""

from __future__ import annotations

import numpy as np

from .transient_groove import detect_transient_onsets, estimate_bpm

# A stem within this percentage of the project consensus tempo is considered
# consistent. Calibrated against real testing_track_stems/ projects
# (2026-07-10): 5% was too tight (flagged a real STRINGS stem at 5.36% off
# a legitimate shared tempo), 6% cleanly separates ordinary per-stem
# estimation noise (STRINGS 5.36%, BASS 5.1%, INTRO_FX/RISER 5.6%, all
# correctly unflagged) from real outliers (SFX 11.3%, KICK 8.2%, DRUMS/PERC/
# VOCAL_CHOP ~30%, CLAP ~60%, all correctly flagged).
BPM_TOLERANCE_PCT = 0.06

MIN_OTHER_STEMS_FOR_CONSENSUS = 2


def _stem_bpm(samples: np.ndarray, sample_rate: int) -> tuple[float, float]:
    onsets = detect_transient_onsets(samples, sample_rate)
    onset_times = [o["time_seconds"] for o in onsets]
    return estimate_bpm(onset_times)


def analyze_stems_for_tempo_consistency(
    stem_dicts: list[dict],
    sample_rate: int,
    *,
    bpm_tolerance_pct: float = BPM_TOLERANCE_PCT,
    min_other_stems: int = MIN_OTHER_STEMS_FOR_CONSENSUS,
) -> dict[str, dict]:
    """Compare each stem's own detected tempo against a project-wide
    consensus formed from every OTHER stem with a real (non-zero-confidence)
    tempo estimate, and flag clear disagreements.

    A stem's own reported `estimate_bpm()` confidence is deliberately NOT
    used as a gate here beyond "produced any estimate at all" (confidence >
    0, i.e. it had enough onsets for `estimate_bpm()` to return something
    other than its hard 0.0/0.0 no-data case) -- real per-instrument stems
    were measured to have consistently low self-reported confidence (mostly
    0.03-0.3) even when their tempo estimates closely agreed with a dozen+
    other stems in the same project, so requiring individual high confidence
    would make consensus formation fail on almost every real project and
    silently suppress genuine anomalies (e.g. a real 152 BPM outlier
    measured against a real ~95 BPM project consensus, at only 0.089
    confidence, would never have been checked at all under a stricter gate).
    The cross-stem agreement itself is the real reliability signal.

    Parameters
    ----------
    stem_dicts : list[dict]
        Each dict has ``"name"`` and ``"samples"``.
    sample_rate : int

    Returns
    -------
    dict[str, dict]
        Keyed by stem name -- only flagged stems appear. Each value:
          - "tempo_inconsistent": True
          - "own_bpm": float
          - "own_bpm_confidence": float
          - "consensus_bpm": float
          - "deviation_pct": float
    """
    per_stem: dict[str, tuple[float, float]] = {}
    for stem in stem_dicts:
        name = stem["name"]
        samples = np.asarray(stem["samples"], dtype=np.float64)
        if len(samples) < sample_rate:  # under 1s of audio -- not enough to trust
            continue
        bpm, confidence = _stem_bpm(samples, sample_rate)
        if confidence <= 0.0:  # estimate_bpm's own no-data case (too few onsets)
            continue
        per_stem[name] = (bpm, confidence)

    results: dict[str, dict] = {}
    for name, (own_bpm, own_confidence) in per_stem.items():
        other_bpms = [bpm for n, (bpm, _) in per_stem.items() if n != name]
        if len(other_bpms) < min_other_stems:
            continue
        consensus_bpm = float(np.median(other_bpms))
        if consensus_bpm <= 0:
            continue
        deviation = abs(own_bpm - consensus_bpm) / consensus_bpm
        if deviation > bpm_tolerance_pct:
            results[name] = {
                "tempo_inconsistent": True,
                "own_bpm": own_bpm,
                "own_bpm_confidence": own_confidence,
                "consensus_bpm": round(consensus_bpm, 2),
                "deviation_pct": round(deviation * 100, 1),
            }

    return results
