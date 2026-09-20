"""Transient-shape and rhythmic micro-timing analysis.

The implementation is deterministic and dependency-light: spectral-flux onset
detection feeds both per-event envelope measurements and grid-based groove
analysis. It is intended for mix diagnostics, not forensic beat transcription.
"""

from __future__ import annotations

import math

import numpy as np

try:
    from audio_analysis.dsp_engine import native as _native
except Exception:  # pragma: no cover
    _native = None


TRANSIENT_TARGETS = {
    "premaster": {"attack_ms": (2.0, 15.0), "attack_sustain_db": (6.0, 20.0)},
    "master": {"attack_ms": (2.0, 15.0), "attack_sustain_db": (5.0, 18.0)},
    "club": {"attack_ms": (1.0, 12.0), "attack_sustain_db": (8.0, 22.0)},
    "pop_vocal": {"attack_ms": (2.0, 15.0), "attack_sustain_db": (6.0, 20.0)},
    "rap_vocal": {"attack_ms": (1.0, 12.0), "attack_sustain_db": (7.0, 22.0)},
    "podcast": {"attack_ms": (2.0, 30.0), "attack_sustain_db": (3.0, 18.0)},
    "game_audio": {"attack_ms": (1.0, 15.0), "attack_sustain_db": (6.0, 22.0)},
}


def _rolling_median_mad_threshold_py(flux: np.ndarray, radius: int, min_floor: float, mad_multiplier: float) -> np.ndarray:
    """Per-frame adaptive threshold: local median + mad_multiplier * local MAD
    (median absolute deviation), floored at min_floor. Window is truncated
    (not padded) at the signal edges."""
    threshold = np.zeros_like(flux)
    for index in range(len(flux)):
        local = flux[max(0, index - radius) : min(len(flux), index + radius + 1)]
        median = float(np.median(local))
        mad = float(np.median(np.abs(local - median)))
        threshold[index] = median + max(min_floor, mad_multiplier * mad)
    return threshold


def _as_mono(samples: list[float] | np.ndarray) -> np.ndarray:
    values = np.asarray(samples, dtype=np.float64).reshape(-1)
    if not len(values):
        return values
    values = np.nan_to_num(values, copy=False)
    peak = float(np.max(np.abs(values)))
    return values / peak if peak > 1e-12 else values


def detect_transient_onsets(
    samples: list[float] | np.ndarray,
    sample_rate: int,
    *,
    frame_size: int = 1024,
    hop_size: int = 256,
    minimum_spacing_ms: float = 80.0,
) -> list[dict]:
    """Detect onsets using positive spectral flux and a local adaptive threshold."""
    signal = _as_mono(samples)
    if sample_rate <= 0 or len(signal) < frame_size * 2:
        return []
    window = np.hanning(frame_size)
    # Batched equivalent of the original per-frame Python loop: stack every
    # frame (sliding_window_view + hop stride matches the original
    # range(0, len(signal)-frame_size+1, hop_size) start positions exactly),
    # then one rfft(..., axis=1) call replaces one rfft() call per frame --
    # numpy applies the same 1D FFT per row either way, so this is the
    # identical computation, just amortizing per-call Python/FFT-plan
    # overhead across all frames instead of paying it thousands of times
    # (measured 2026-07-30: 141,411 individual rfft calls for one real
    # render, ~38% of this function's cost).
    frames = np.lib.stride_tricks.sliding_window_view(signal, frame_size)[::hop_size]
    spectrum_batch = np.abs(np.fft.rfft(frames * window, axis=1))
    sums = np.maximum(np.sum(spectrum_batch, axis=1, keepdims=True), 1e-12)
    spectrum_batch = spectrum_batch / sums
    if spectrum_batch.shape[0] < 3:
        return []
    flux = np.zeros(spectrum_batch.shape[0], dtype=np.float64)
    flux[1:] = np.sum(np.maximum(spectrum_batch[1:] - spectrum_batch[:-1], 0.0), axis=1)

    radius = 8
    if _native is not None:
        try:
            if getattr(_native, "is_transient_threshold_available", lambda: False)():
                threshold = _native.native_rolling_median_mad_threshold(flux, radius, 0.015, 3.0)
            else:
                threshold = _rolling_median_mad_threshold_py(flux, radius, 0.015, 3.0)
        except Exception:
            threshold = _rolling_median_mad_threshold_py(flux, radius, 0.015, 3.0)
    else:
        threshold = _rolling_median_mad_threshold_py(flux, radius, 0.015, 3.0)

    minimum_frames = max(1, int(round(minimum_spacing_ms * sample_rate / (1000.0 * hop_size))))
    candidates = [
        index
        for index in range(1, len(flux) - 1)
        if flux[index] > threshold[index]
        and flux[index] >= flux[index - 1]
        and flux[index] >= flux[index + 1]
    ]
    selected: list[int] = []
    for index in candidates:
        if selected and index - selected[-1] < minimum_frames:
            if flux[index] > flux[selected[-1]]:
                selected[-1] = index
            continue
        selected.append(index)
    return [
        {
            "sample": int(index * hop_size),
            "time_seconds": round(index * hop_size / sample_rate, 6),
            "strength": round(float(flux[index]), 6),
            "threshold": round(float(threshold[index]), 6),
        }
        for index in selected
    ]


def _smoothed_envelope(signal: np.ndarray, sample_rate: int) -> np.ndarray:
    window = max(1, int(round(sample_rate * 0.001)))
    kernel = np.ones(window, dtype=np.float64) / window
    return np.convolve(np.abs(signal), kernel, mode="same")


def measure_transient_events(
    samples: list[float] | np.ndarray,
    sample_rate: int,
    onsets: list[dict] | None = None,
) -> list[dict]:
    """Measure attack, peak, sustain-at-200ms, release, and attack/sustain ratio."""
    signal = _as_mono(samples)
    if sample_rate <= 0 or not len(signal):
        return []
    onsets = onsets if onsets is not None else detect_transient_onsets(signal, sample_rate)
    envelope = _smoothed_envelope(signal, sample_rate)
    events = []
    for onset in onsets:
        onset_sample = int(onset["sample"])
        peak_end = min(len(envelope), onset_sample + int(0.08 * sample_rate))
        if peak_end <= onset_sample:
            continue
        peak_sample = onset_sample + int(np.argmax(envelope[onset_sample:peak_end]))
        peak = float(envelope[peak_sample])
        if peak <= 1e-9:
            continue
        attack_slice = envelope[onset_sample : peak_sample + 1]
        above_10 = np.flatnonzero(attack_slice >= peak * 0.1)
        above_90 = np.flatnonzero(attack_slice >= peak * 0.9)
        attack_start = onset_sample + (int(above_10[0]) if len(above_10) else 0)
        attack_end = onset_sample + (int(above_90[0]) if len(above_90) else len(attack_slice) - 1)

        release_end = min(len(envelope), peak_sample + int(0.6 * sample_rate))
        release_slice = envelope[peak_sample:release_end]
        below_10 = np.flatnonzero(release_slice <= peak * 0.1)
        release_sample = peak_sample + (int(below_10[0]) if len(below_10) else len(release_slice) - 1)

        sustain_start = min(len(envelope), peak_sample + int(0.18 * sample_rate))
        sustain_end = min(len(envelope), peak_sample + int(0.22 * sample_rate))
        sustain = float(np.sqrt(np.mean(signal[sustain_start:sustain_end] ** 2))) if sustain_end > sustain_start else 0.0
        peak_db = 20.0 * math.log10(max(peak, 1e-9))
        sustain_db = 20.0 * math.log10(max(sustain, 1e-9))
        events.append(
            {
                "onset_seconds": round(onset_sample / sample_rate, 4),
                "attack_ms": round(max(0, attack_end - attack_start) * 1000.0 / sample_rate, 3),
                "peak_dbfs": round(peak_db, 2),
                "sustain_200ms_dbfs": round(sustain_db, 2),
                "attack_sustain_ratio_db": round(peak_db - sustain_db, 2),
                "release_ms": round(max(0, release_sample - peak_sample) * 1000.0 / sample_rate, 3),
                "strength": onset.get("strength", 0.0),
            }
        )
    return events


def analyze_transients(
    samples: list[float] | np.ndarray,
    sample_rate: int,
    *,
    crest_factor_db: float = 0.0,
    target: str = "premaster",
) -> dict:
    onsets = detect_transient_onsets(samples, sample_rate)
    events = measure_transient_events(samples, sample_rate, onsets)
    duration = len(np.asarray(samples).reshape(-1)) / sample_rate if sample_rate > 0 else 0.0
    if not events:
        return {
            "onset_count": 0,
            "transient_density_hz": 0.0,
            "events": [],
            "profile": "No clear transients",
            "flags": [],
        }
    attacks = np.asarray([event["attack_ms"] for event in events])
    ratios = np.asarray([event["attack_sustain_ratio_db"] for event in events])
    releases = np.asarray([event["release_ms"] for event in events])
    median_attack = float(np.median(attacks))
    median_ratio = float(np.median(ratios))
    target_ranges = TRANSIENT_TARGETS.get(target, TRANSIENT_TARGETS["premaster"])
    attack_min, attack_max = target_ranges["attack_ms"]
    ratio_min, ratio_max = target_ranges["attack_sustain_db"]
    flags = []
    if median_attack < 2.0 and crest_factor_db < 6.0:
        flags.append({
            "severity": "medium",
            "label": "Crushed transients",
            "detail": f"Median attack is {median_attack:.1f} ms with only {crest_factor_db:.1f} dB crest factor.",
        })
        profile = "Crushed"
    elif median_attack > attack_max and len(events) / max(duration, 1e-9) >= 1.0:
        flags.append({
            "severity": "low",
            "label": "Slow transient attacks",
            "detail": f"Median transient attack is {median_attack:.1f} ms; percussive elements may feel softened.",
        })
        profile = "Softened"
    elif median_ratio >= 10.0 and crest_factor_db >= 8.0:
        profile = "Punchy"
    else:
        profile = "Controlled"
    attack_status = "below" if median_attack < attack_min else "above" if median_attack > attack_max else "within"
    ratio_status = "below" if median_ratio < ratio_min else "above" if median_ratio > ratio_max else "within"
    if profile == "Crushed":
        compression_impact = {
            "status": "over-processed",
            "diagnosis": "Fast attacks and low crest reserve are consistent with limiting, clipping, saturation, or fast compression flattening punch.",
        }
    elif profile == "Softened":
        compression_impact = {
            "status": "softened",
            "diagnosis": "Slow measured attacks are consistent with lookahead, slow source envelopes, saturation, or transient shaping reducing initial impact.",
        }
    elif profile == "Punchy":
        compression_impact = {
            "status": "punch-preserved",
            "diagnosis": "Attack-to-sustain contrast and crest reserve indicate that transient punch is being preserved.",
        }
    else:
        compression_impact = {
            "status": "controlled",
            "diagnosis": "Transient shape is controlled without strong evidence of crushing or excessive softening.",
        }
    return {
        "onset_count": len(events),
        "transient_density_hz": round(len(events) / max(duration, 1e-9), 3),
        "median_attack_ms": round(median_attack, 3),
        "median_peak_dbfs": round(float(np.median([event["peak_dbfs"] for event in events])), 2),
        "median_sustain_200ms_dbfs": round(float(np.median([event["sustain_200ms_dbfs"] for event in events])), 2),
        "median_attack_sustain_ratio_db": round(median_ratio, 2),
        "median_release_ms": round(float(np.median(releases)), 3),
        "crest_factor_db": round(float(crest_factor_db), 2),
        "target": target,
        "target_ranges": target_ranges,
        "target_comparison": {
            "attack": attack_status,
            "attack_sustain_ratio": ratio_status,
        },
        "compression_impact": compression_impact,
        "profile": profile,
        "flags": flags,
        "events": events[:128],
    }


def transient_preservation(
    pre_samples: list[float] | np.ndarray,
    post_samples: list[float] | np.ndarray,
    sample_rate: int,
    *,
    match_window_seconds: float = 0.05,
) -> dict:
    """Compare transient sharpness before/after a processing chain.

    Detects onsets independently in the "pre" (e.g. unprocessed multitrack
    bounce or a pre-limiter render) and "post" (e.g. after mastering,
    limiting, or a lossy codec pass) signals, then matches each pre-onset
    to the nearest post-onset within ``match_window_seconds`` (default
    50 ms — wide enough to absorb small look-ahead/latency shifts from
    limiters or codecs, tight enough not to cross-match unrelated hits).

    For each matched pair, measures how much the attack was *smeared*
    using two independent signals per event:

    - ``attack_ms`` growth: a longer attack (10%-90% rise time on the
      smoothed envelope) after processing means the transient's leading
      edge softened — the classic signature of limiting/lookahead/heavy
      saturation.
    - ``attack_sustain_ratio_db`` loss: how much the peak-to-200ms-sustain
      contrast collapsed. A limiter that catches transient peaks reduces
      this ratio even when attack *time* looks similar, because it's
      clamping the peak itself rather than slowing its rise.

    ``preservation_score`` (0-1, higher = better preserved) combines both
    signals: 1.0 minus the mean fractional attack-time growth and mean
    fractional attack/sustain-ratio loss, each clipped to [0, 1] and
    averaged. A score near 1.0 means transients arrived with essentially
    unchanged shape; a score near 0 means attacks were substantially
    smeared and their dynamic contrast was crushed — exactly the fingerprint
    left by a fast limiter or over-aggressive compression riding transients.

    Onsets present in only one signal (e.g. a limiter fully swallowing a
    quiet transient into the noise floor, or a new onset introduced by
    distortion) are reported separately as ``unmatched_pre_onsets`` /
    ``unmatched_post_onsets`` rather than silently dropped, since that is
    itself diagnostically meaningful (heavy smearing can merge or erase
    transients entirely).
    """
    pre = _as_mono(pre_samples)
    post = _as_mono(post_samples)
    empty = {
        "matched_event_count": 0,
        "unmatched_pre_onsets": 0,
        "unmatched_post_onsets": 0,
        "mean_attack_growth_ms": 0.0,
        "mean_attack_ratio_loss_db": 0.0,
        "preservation_score": None,
        "profile": "Insufficient data",
        "events": [],
    }
    if sample_rate <= 0 or len(pre) < 2048 or len(post) < 2048:
        return empty

    pre_events = measure_transient_events(pre, sample_rate)
    post_events = measure_transient_events(post, sample_rate)
    if not pre_events or not post_events:
        return {
            **empty,
            "unmatched_pre_onsets": len(pre_events),
            "unmatched_post_onsets": len(post_events),
            "profile": "No matched transients",
        }

    used_post = set()
    pairs = []
    for pre_event in pre_events:
        best_index = None
        best_delta = match_window_seconds
        for index, post_event in enumerate(post_events):
            if index in used_post:
                continue
            delta = abs(post_event["onset_seconds"] - pre_event["onset_seconds"])
            if delta <= best_delta:
                best_delta = delta
                best_index = index
        if best_index is not None:
            used_post.add(best_index)
            pairs.append((pre_event, post_events[best_index]))

    if not pairs:
        return {
            **empty,
            "unmatched_pre_onsets": len(pre_events),
            "unmatched_post_onsets": len(post_events),
            "profile": "No matched transients",
        }

    events = []
    attack_growth_fractions = []
    ratio_loss_fractions = []
    for pre_event, post_event in pairs:
        attack_growth_ms = post_event["attack_ms"] - pre_event["attack_ms"]
        ratio_loss_db = pre_event["attack_sustain_ratio_db"] - post_event["attack_sustain_ratio_db"]
        # Fractional growth relative to the pre-processing attack time (floored
        # at 1 ms so near-instant transients don't produce runaway ratios).
        growth_fraction = max(0.0, attack_growth_ms) / max(pre_event["attack_ms"], 1.0)
        # Fractional loss relative to the pre-processing ratio itself (floored
        # at 1 dB of ratio for the same reason).
        loss_fraction = max(0.0, ratio_loss_db) / max(abs(pre_event["attack_sustain_ratio_db"]), 1.0)
        attack_growth_fractions.append(min(1.0, growth_fraction))
        ratio_loss_fractions.append(min(1.0, loss_fraction))
        events.append({
            "onset_seconds": pre_event["onset_seconds"],
            "pre_attack_ms": pre_event["attack_ms"],
            "post_attack_ms": post_event["attack_ms"],
            "attack_growth_ms": round(attack_growth_ms, 3),
            "pre_attack_sustain_ratio_db": pre_event["attack_sustain_ratio_db"],
            "post_attack_sustain_ratio_db": post_event["attack_sustain_ratio_db"],
            "attack_ratio_loss_db": round(ratio_loss_db, 3),
        })

    mean_growth_fraction = float(np.mean(attack_growth_fractions))
    mean_loss_fraction = float(np.mean(ratio_loss_fractions))
    preservation_score = round(1.0 - 0.5 * (mean_growth_fraction + mean_loss_fraction), 4)
    mean_attack_growth_ms = float(np.mean([e["attack_growth_ms"] for e in events]))
    mean_ratio_loss_db = float(np.mean([e["attack_ratio_loss_db"] for e in events]))

    if preservation_score >= 0.85:
        profile = "Well preserved"
    elif preservation_score >= 0.6:
        profile = "Mildly smeared"
    elif preservation_score >= 0.35:
        profile = "Noticeably smeared"
    else:
        profile = "Heavily smeared/crushed"

    return {
        "matched_event_count": len(pairs),
        "unmatched_pre_onsets": len(pre_events) - len(pairs),
        "unmatched_post_onsets": len(post_events) - len(used_post),
        "mean_attack_growth_ms": round(mean_attack_growth_ms, 3),
        "mean_attack_ratio_loss_db": round(mean_ratio_loss_db, 3),
        "preservation_score": preservation_score,
        "profile": profile,
        "events": events[:128],
    }


def _fold_tempo(interval_seconds: float, minimum: float = 60.0, maximum: float = 180.0) -> float:
    bpm = 60.0 / max(interval_seconds, 1e-9)
    while bpm < minimum:
        bpm *= 2.0
    while bpm > maximum:
        bpm /= 2.0
    return bpm


def estimate_bpm(onset_times: list[float]) -> tuple[float, float]:
    """Estimate tempo from adjacent and skip-one onset intervals."""
    times = np.asarray(onset_times, dtype=np.float64)
    if len(times) < 3:
        return 0.0, 0.0
    # Skip-one intervals are stable for both straight and swung eighth-note
    # patterns because they span a complete beat; adjacent intervals are a
    # fallback for sparse patterns.
    intervals = times[2:] - times[:-2]
    if not len(intervals):
        intervals = np.diff(times)
    intervals = intervals[(intervals >= 0.12) & (intervals <= 2.0)]
    if not len(intervals):
        return 0.0, 0.0
    candidates = np.asarray([_fold_tempo(float(interval)) for interval in intervals])
    bins = np.arange(59.5, 181.5, 1.0)
    histogram, edges = np.histogram(candidates, bins=bins)
    best = int(np.argmax(histogram))
    selected = candidates[(candidates >= edges[best]) & (candidates < edges[best + 1])]
    bpm = float(np.median(selected)) if len(selected) else float((edges[best] + edges[best + 1]) / 2.0)
    confidence = float(histogram[best] / max(len(candidates), 1))
    return round(bpm, 2), round(confidence, 3)


def analyze_groove(
    samples: list[float] | np.ndarray,
    sample_rate: int,
    *,
    bpm: float | None = None,
) -> dict:
    onsets = detect_transient_onsets(samples, sample_rate)
    times = [float(onset["time_seconds"]) for onset in onsets]
    detected_bpm, tempo_confidence = estimate_bpm(times)
    tempo = float(bpm or detected_bpm)
    if tempo <= 0.0 or len(times) < 3:
        return {
            "bpm": round(tempo, 2),
            "tempo_confidence": tempo_confidence,
            "onset_count": len(times),
            "timing_class": "Insufficient rhythm",
            "swing_percentage": 50.0,
            "swing_class": "Straight",
            "deviations": [],
        }

    beat_seconds = 60.0 / tempo
    grid_seconds = beat_seconds / 4.0
    phases = np.mod(np.asarray(times), grid_seconds)
    phase = float(np.median(phases))
    deviations = []
    for onset_time in times:
        grid_index = int(round((onset_time - phase) / grid_seconds))
        grid_time = phase + grid_index * grid_seconds
        deviation_ms = (onset_time - grid_time) * 1000.0
        deviations.append({
            "onset_seconds": round(onset_time, 4),
            "grid_seconds": round(grid_time, 4),
            "deviation_ms": round(deviation_ms, 3),
        })
    absolute = np.abs([item["deviation_ms"] for item in deviations])
    mean_abs = float(np.mean(absolute))
    if mean_abs < 5.0:
        timing_class = "Tight"
    elif mean_abs < 15.0:
        timing_class = "Human"
    elif mean_abs < 30.0:
        timing_class = "Loose"
    else:
        timing_class = "Sloppy"

    # Measure alternating long/short subdivisions. Straight pairs report 50%;
    # triplet-eighth placement reports approximately 66.7%.
    intervals = np.diff(np.asarray(times))
    swing_values = []
    for index in range(0, len(intervals) - 1, 2):
        first, second = float(intervals[index]), float(intervals[index + 1])
        pair = first + second
        if pair > 0 and 0.5 * beat_seconds <= pair <= 1.5 * beat_seconds:
            swing_values.append(max(first, second) / pair * 100.0)
    swing = float(np.median(swing_values)) if swing_values else 50.0
    swing_class = "Straight" if swing < 54.0 else "Light swing" if swing < 61.0 else "Swung"
    std_ms = float(np.std([item["deviation_ms"] for item in deviations]))
    return {
        "bpm": round(tempo, 2),
        "tempo_confidence": tempo_confidence,
        "onset_count": len(times),
        "grid_division": "1/16",
        "mean_abs_deviation_ms": round(mean_abs, 3),
        "rms_deviation_ms": round(float(np.sqrt(np.mean(np.square(absolute)))), 3),
        "max_deviation_ms": round(float(np.max(absolute)), 3),
        "timing_class": timing_class,
        "timing_consistency_percent": round(max(0.0, 100.0 - std_ms * 2.0), 1),
        "swing_percentage": round(swing, 1),
        "swing_class": swing_class,
        "deviations": deviations[:256],
    }
