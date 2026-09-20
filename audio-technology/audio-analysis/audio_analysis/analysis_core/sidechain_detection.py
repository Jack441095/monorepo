"""Sidechain/ducking and existing-dynamics-automation detector — Stage K.

See docs/AUDIO_MVP_MASTER_PLAN.md Stage K. Answers a narrow question, raised
by Jack reviewing his own real stems: does a stem already have an
intentional, existing dynamics treatment applied upstream (most commonly
sidechain compression, e.g. bass ducking against the kick) that AutoMix's
own rule-driven compressor should know about before deciding how hard to
compress that stem itself?

Two detectors, mirroring resonance_detection.py's own "detection brain"
pattern (deterministic signal analysis, no black box, evidence you can point
to a specific number for):

1. Sidechain/ducking correlation -- does a TARGET stem's envelope show a
   dip shortly after each onset in a TRIGGER stem (e.g. bass dipping right
   after each kick hit)? This is the specific, attributable case.
2. Structured dynamics -- does a stem's own envelope show non-random,
   periodic gain movement at all, regardless of what's driving it? A
   weaker, more general fallback signal for when the correlated-trigger
   pattern isn't clean enough to confirm sidechain specifically.

Both operate purely on rendered stem audio (no DAW-project-file reading --
see Stage K's own explicit scope boundary), reusing the existing transient
detector (`transient_groove.detect_transient_onsets`) rather than inventing
a second onset-detection algorithm.
"""

from __future__ import annotations

import numpy as np


def _fast_envelope(samples: "np.ndarray", sample_rate: int, *, window_ms: float = 10.0) -> tuple["np.ndarray", float]:
    """RMS envelope at a resolution fast enough to see real sidechain-speed
    ducking (typical sidechain attack is single-digit-to-tens of ms -- the
    0.4s window `analysis_features.windowed_rms_values` uses elsewhere in
    this codebase is far too coarse for this and would miss the dip
    entirely, not just measure it imprecisely).

    Returns (envelope_db, hop_seconds).
    """
    signal = np.asarray(samples, dtype=np.float64)
    hop = max(1, int(sample_rate * window_ms / 1000.0))
    if len(signal) < hop:
        return np.array([]), hop / sample_rate

    num_hops = len(signal) // hop
    trimmed = signal[: num_hops * hop].reshape(num_hops, hop)
    rms = np.sqrt(np.mean(trimmed * trimmed, axis=1))
    envelope_db = 20.0 * np.log10(np.maximum(rms, 1e-9))
    return envelope_db, hop / sample_rate


def detect_sidechain_ducking(
    target_samples: "np.ndarray",
    target_sample_rate: int,
    trigger_onset_times_s: list[float],
    *,
    envelope_window_ms: float = 10.0,
    dip_search_window_ms: float = 60.0,
    min_dip_db: float = 3.0,
    min_onsets_for_confidence: int = 4,
    correlation_threshold: float = 0.6,
) -> dict:
    """Check whether ``target_samples``'s envelope dips shortly after each
    of ``trigger_onset_times_s`` -- the distinctive signature of a genuine
    sidechain pump (dips synchronized to a *different* stem's transients,
    not the target's own natural dynamics).

    Parameters
    ----------
    target_samples : np.ndarray
        The (mono) stem being checked for ducking, e.g. a bass stem.
    trigger_onset_times_s : list[float]
        Onset times (seconds) from the *other* stem, e.g.
        ``detect_transient_onsets(kick_samples, sr)``'s ``"time_seconds"``
        values.
    dip_search_window_ms : float
        How far after each trigger onset to look for the target's envelope
        minimum -- matches typical sidechain attack times (a few ms up to
        ~60ms for a slower "pumping" style).
    min_dip_db : float
        How far below the target's own pre-onset envelope level the dip
        must be to count as a real duck, not noise-floor wobble.

    Returns
    -------
    dict
        - "detected": bool
        - "correlation": float (fraction of *applicable* onsets with a
          matching dip -- see "num_applicable_onsets")
        - "num_trigger_onsets": int (total onsets passed in)
        - "num_applicable_onsets": int (onsets where the target had real
          signal present beforehand -- silent-target onsets, e.g. before a
          bass part has entered, are excluded from the correlation entirely
          rather than counted as non-matches)
        - "num_matched_dips": int
        - "mean_dip_db": float (average depth of matched dips)
    """
    envelope_db, hop_s = _fast_envelope(target_samples, target_sample_rate, window_ms=envelope_window_ms)
    empty = {
        "detected": False,
        "correlation": 0.0,
        "num_trigger_onsets": len(trigger_onset_times_s),
        "num_applicable_onsets": 0,
        "num_matched_dips": 0,
        "mean_dip_db": 0.0,
    }
    if len(envelope_db) == 0 or not trigger_onset_times_s:
        return empty

    search_frames = max(1, int(dip_search_window_ms / 1000.0 / hop_s))
    pre_frames = max(1, int(0.5 * search_frames))

    # A trigger onset only tells us anything about ducking if the target
    # actually has real signal present right before it -- otherwise "no dip"
    # just means "nothing was there to dip," not "not ducked." Found
    # 2026-07-10 on a real project: a bass stem silent for its intro (true
    # digital silence, ~-147dB noise floor) dragged the overall correlation
    # from what should have been a near-perfect match down to 0.198, because
    # every kick onset during that silent intro counted as a non-match. The
    # real, present dips measured a massive, unambiguous ~22dB -- textbook
    # sidechain -- once silent-target onsets were excluded from the count.
    min_active_level_db = -50.0

    applicable = 0
    matched = 0
    dip_depths: list[float] = []
    for onset_s in trigger_onset_times_s:
        onset_frame = int(onset_s / hop_s)
        if onset_frame >= len(envelope_db):
            continue
        pre_start = max(0, onset_frame - pre_frames)
        pre_level = float(np.mean(envelope_db[pre_start:onset_frame])) if onset_frame > pre_start else envelope_db[onset_frame]

        if pre_level < min_active_level_db:
            continue  # target is silent here; this onset says nothing about ducking

        search_end = min(len(envelope_db), onset_frame + search_frames)
        if search_end <= onset_frame:
            continue
        post_min = float(np.min(envelope_db[onset_frame:search_end]))

        applicable += 1
        dip_db = pre_level - post_min
        if dip_db >= min_dip_db:
            matched += 1
            dip_depths.append(dip_db)

    correlation = matched / applicable if applicable else 0.0
    mean_dip_db = float(np.mean(dip_depths)) if dip_depths else 0.0

    # Found 2026-07-10 on a real project: a genuine, confirmed sidechain
    # doesn't necessarily duck on every single trigger hit across a whole
    # song -- many mixes apply it more heavily in some sections (chorus/drop)
    # than others (verse/breakdown), or automate it on/off entirely.
    # Real data showed a clean BIMODAL split -- ~40 onsets near 0dB (no
    # duck) and ~63 onsets at 15-30dB+ (an extreme, unambiguous duck), with
    # a genuine gap in between (nothing 10-15dB) -- giving an aggregate
    # correlation (0.385) below a strict whole-track threshold despite the
    # real dips being maximally unambiguous, not borderline. A blanket
    # correlation-only threshold conflates "not sidechained" with
    # "sidechained in only part of the track" -- two different things.
    # Detect on EITHER a high overall correlation (the uniform-treatment
    # case) OR a smaller subset of matches whose average depth is large
    # enough that noise/coincidence is not a plausible explanation (the
    # section-varying case) -- this does not weaken rejection of genuinely
    # noisy/uncorrelated material, since noise doesn't also happen to
    # average a large, consistent dip depth across its matches.
    strong_subset_threshold_db = 12.0
    min_strong_matches = min_onsets_for_confidence
    detected = applicable >= min_onsets_for_confidence and (
        correlation >= correlation_threshold
        or (matched >= min_strong_matches and mean_dip_db >= strong_subset_threshold_db)
    )

    return {
        "detected": detected,
        "correlation": round(correlation, 3),
        "num_trigger_onsets": len(trigger_onset_times_s),
        "num_applicable_onsets": applicable,
        "num_matched_dips": matched,
        "mean_dip_db": round(mean_dip_db, 2),
    }


def detect_structured_dynamics(
    samples: "np.ndarray",
    sample_rate: int,
    *,
    envelope_window_ms: float = 10.0,
    min_period_s: float = 0.15,
    max_period_s: float = 2.0,
    periodicity_threshold: float = 0.4,
) -> dict:
    """Weaker, more general fallback: does this stem's own envelope show
    non-random, periodic gain movement at all (e.g. sidechain-style pumping
    whose trigger stem isn't available to correlate against directly)?

    Uses autocorrelation of the envelope to find a dominant period within a
    plausible musical range (150ms-2s covers roughly 30-400bpm-at-various
    subdivisions) rather than assuming a specific tempo.

    Returns
    -------
    dict
        - "has_structured_dynamics": bool
        - "periodicity_strength": float (normalised autocorrelation peak, 0-1)
        - "detected_period_s": float | None
    """
    envelope_db, hop_s = _fast_envelope(samples, sample_rate, window_ms=envelope_window_ms)
    empty = {"has_structured_dynamics": False, "periodicity_strength": 0.0, "detected_period_s": None}
    if len(envelope_db) < 8:
        return empty

    centered = envelope_db - np.mean(envelope_db)
    if np.std(centered) < 1e-6:
        return empty

    # Wiener–Khinchin autocorrelation avoids np.correlate's O(n²) cost on a
    # full ten-minute stem envelope. Zero-padding to >= 2n-1 preserves the
    # linear (not circular) positive-lag correlation used below.
    fft_size = 1 << max(1, (2 * len(centered) - 1).bit_length())
    spectrum = np.fft.rfft(centered, n=fft_size)
    autocorr = np.fft.irfft(spectrum * np.conjugate(spectrum), n=fft_size)[:len(centered)]
    if autocorr[0] <= 1e-12:
        return empty
    autocorr = autocorr / autocorr[0]

    min_lag = max(1, int(min_period_s / hop_s))
    max_lag = min(len(autocorr) - 1, int(max_period_s / hop_s))
    if max_lag <= min_lag:
        return empty

    window = autocorr[min_lag:max_lag]
    peak_idx = int(np.argmax(window))
    peak_strength = float(window[peak_idx])
    peak_lag = min_lag + peak_idx

    has_structure = peak_strength >= periodicity_threshold
    return {
        "has_structured_dynamics": has_structure,
        "periodicity_strength": round(peak_strength, 3),
        "detected_period_s": round(peak_lag * hop_s, 3) if has_structure else None,
    }


# Plausible sidechain trigger instruments -- things that produce clear,
# regular rhythmic transients a target stem could be ducked against.
_TRIGGER_INSTRUMENTS = {"kick", "snare", "full_drum_bus"}
# Plausible sidechain target instruments -- things commonly ducked in real
# production (bass-against-kick is the classic case Jack's own stems have;
# pads/keys/guitar are also routinely sidechained for pump/groove effect).
_TARGET_INSTRUMENTS = {"bass", "sub_bass", "synth_pad", "keys", "guitar", "strings", "brass"}


def analyze_stems_for_dynamics(
    stem_dicts: list[dict],
    profiles: list,
    sample_rate: int,
) -> dict[str, dict]:
    """Run both detectors across a full stem set, picking sensible
    trigger/target pairings from each stem's classified instrument rather
    than checking every stem against every other one.

    Parameters
    ----------
    stem_dicts : list[dict]
        Each dict has ``"name"`` and ``"samples"`` (mono or the left channel
        is used) -- the same shape ``mix_and_render_stems`` consumes.
    profiles : list[StemProfile]
        From ``classify_stems()`` -- used to decide which stems are
        plausible triggers vs. targets.
    sample_rate : int

    Returns
    -------
    dict[str, dict]
        Keyed by stem name. Each value has:
          - "sidechain_detected": bool
          - "sidechain_trigger": str | None (name of the stem it's ducking against)
          - "sidechain_correlation": float
          - "has_structured_dynamics": bool
          - "dynamics_periodicity": float
        Only stems classified as plausible targets get a sidechain check;
        every stem gets the structured-dynamics fallback check.
    """
    instrument_by_name = {p.name: p.instrument for p in profiles}
    samples_by_name = {s["name"]: np.asarray(s["samples"], dtype=np.float64) for s in stem_dicts}

    trigger_onsets: dict[str, list[float]] = {}
    for name, instrument in instrument_by_name.items():
        if instrument in _TRIGGER_INSTRUMENTS and name in samples_by_name:
            from audio_analysis.analysis_core.transient_groove import detect_transient_onsets
            onsets = detect_transient_onsets(samples_by_name[name], sample_rate)
            trigger_onsets[name] = [o["time_seconds"] for o in onsets]

    results: dict[str, dict] = {}
    for name, samples in samples_by_name.items():
        instrument = instrument_by_name.get(name, "other")

        best_sidechain = {
            "detected": False, "correlation": 0.0, "num_trigger_onsets": 0,
            "num_matched_dips": 0, "mean_dip_db": 0.0,
        }
        best_trigger_name = None
        if instrument in _TARGET_INSTRUMENTS:
            for trigger_name, onset_times in trigger_onsets.items():
                if trigger_name == name or not onset_times:
                    continue
                result = detect_sidechain_ducking(samples, sample_rate, onset_times)
                candidate_rank = (
                    bool(result["detected"]),
                    float(result["correlation"]),
                    float(result["mean_dip_db"]),
                )
                best_rank = (
                    bool(best_sidechain["detected"]),
                    float(best_sidechain["correlation"]),
                    float(best_sidechain["mean_dip_db"]),
                )
                if candidate_rank > best_rank:
                    best_sidechain = result
                    best_trigger_name = trigger_name

        structured = detect_structured_dynamics(samples, sample_rate)

        results[name] = {
            "sidechain_detected": best_sidechain["detected"],
            "sidechain_trigger": best_trigger_name if best_sidechain["detected"] else None,
            "sidechain_correlation": best_sidechain["correlation"],
            "sidechain_mean_dip_db": best_sidechain["mean_dip_db"],
            "has_structured_dynamics": structured["has_structured_dynamics"],
            "dynamics_periodicity": structured["periodicity_strength"],
        }

    return results
