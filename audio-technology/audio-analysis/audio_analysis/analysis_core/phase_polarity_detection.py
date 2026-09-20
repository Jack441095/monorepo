"""Phase/polarity detector for related stems — Stage M2.

See docs/AUDIO_MVP_MASTER_PLAN.md Stage M2. Nothing else in this codebase
compares the TIME-DOMAIN phase relationship between two DIFFERENT stems --
`stereo_analysis.py` checks a single stem/bus's own L vs. R, and
`stem_analysis.py`'s masking analyzer compares frequency-band energy between
stems, not waveform phase. A classic real-world failure this misses
entirely: a DI + amp pair, or a multi-mic'd source (kick in/out, snare
top/bottom, doubled vocal takes), with one mic polarity-inverted -- summing
them causes destructive cancellation, most audible as a hollowed-out low
end. A human engineer's first move on any multi-mic'd source is always a
polarity/phase check before anything else.

Real-world validation, 2026-07-10: correlating dream_of_you/reggueton_pop/
stranger's actual stems found no genuine polarity inversion (expected --
they're rare in practice), but did surface a real, useful negative-control
case: `stranger`'s VOCALS vs VOCALS-1 correlate at 0.92 (clearly related,
in-phase, no inversion) while VOCALS vs VOCALS-2 correlate at only 0.30 and
VOCALS-1 vs VOCALS-2 at 0.01 (genuinely different vocal parts, not the same
source at all) -- exactly the "correlated because related" vs. "correlated
because coincidentally similar content" distinction this detector needs to
get right, confirmed against real production stems, not just synthetic
signals.
"""

from __future__ import annotations

import re

import numpy as np
import scipy.signal as sig
try:
    from audio_analysis.dsp_engine import native as _native
except ImportError:
    _native = None


def _active_window(
    samples_a: np.ndarray,
    samples_b: np.ndarray,
    sample_rate: int,
    *,
    window_s: float = 5.0,
    noise_floor: float = 0.001,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Find a representative window where BOTH stems have real signal
    present (not silence) -- polarity is a stable property of a recording,
    it doesn't change mid-take, so a single well-chosen active window is
    enough to measure it without paying the cost of correlating a whole
    multi-minute stem sample-by-sample.
    """
    n = min(len(samples_a), len(samples_b))
    if n == 0:
        return None
    a, b = samples_a[:n], samples_b[:n]

    hop = max(1, sample_rate // 100)  # 10ms coarse scan
    window_samples = int(window_s * sample_rate)
    if window_samples >= n:
        active = (np.abs(a) > noise_floor) & (np.abs(b) > noise_floor)
        return (a, b) if active.sum() > sample_rate else None

    best_start = None
    best_active_count = 0
    for start in range(0, n - window_samples, hop * 20):
        chunk_a = a[start : start + window_samples]
        chunk_b = b[start : start + window_samples]
        active_count = int(np.sum((np.abs(chunk_a) > noise_floor) & (np.abs(chunk_b) > noise_floor)))
        if active_count > best_active_count:
            best_active_count = active_count
            best_start = start
        if active_count >= window_samples * 0.9:
            break  # good enough, stop scanning

    if best_start is None or best_active_count < sample_rate:
        return None
    return a[best_start : best_start + window_samples], b[best_start : best_start + window_samples]


def detect_phase_polarity(
    samples_a: np.ndarray,
    samples_b: np.ndarray,
    sample_rate: int,
    *,
    max_lag_ms: float = 5.0,
    window_s: float = 5.0,
    inversion_threshold: float = -0.7,
    unrelated_threshold: float = 0.3,
) -> dict:
    """Cross-correlate two stems' raw waveforms across a small lag window
    (accounting for genuine mic-placement time-of-arrival offsets, not
    requiring sample-exact alignment) and report the strongest relationship
    found, signed.

    Parameters
    ----------
    max_lag_ms : float
        How far to search for the best-aligned lag -- a few ms covers
        realistic mic-placement distance offsets without searching so wide
        that unrelated material coincidentally aligns.
    inversion_threshold : float
        Correlation at or below this (a strong NEGATIVE correlation) is the
        signature of a polarity inversion.
    unrelated_threshold : float
        Below this (in absolute value), the two stems are considered simply
        unrelated -- most stem pairs in a real project -- and nothing fires.

    Returns
    -------
    dict
        - "best_correlation": float, signed, at the best-aligned lag
        - "best_lag_samples": int, signed. Convention: delay ``samples_b`` by
          this many samples (prepend zeros/trim the tail, negative = advance
          it instead) to bring it into time-alignment with ``samples_a``.
        - "likely_related": bool (abs(best_correlation) >= unrelated_threshold)
        - "polarity_inverted": bool (best_correlation <= inversion_threshold)
    """
    empty = {
        "best_correlation": 0.0,
        "best_lag_samples": 0,
        "likely_related": False,
        "polarity_inverted": False,
    }
    window = _active_window(samples_a, samples_b, sample_rate, window_s=window_s)
    if window is None:
        return empty
    a, b = window
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return empty

    max_lag = max(1, int(max_lag_ms / 1000.0 * sample_rate))

    # native_direct_cross_correlation (dsp_engine/native/phase_correlation_kernel.cpp)
    # is a direct O(N*max_lag) port, correctness-verified bit-identical to the
    # FFT path below (including lag sign convention) -- but measured 2026-07-30
    # at ~5x SLOWER than scipy.signal.correlate(..., method="fft")'s O(N log N),
    # so it's deliberately not called here. Kept unwired rather than deleted in
    # case a future FFT-based native port is worth it.

    a_c = a - np.mean(a)
    b_c = b - np.mean(b)
    norm = np.sqrt(np.sum(a_c * a_c) * np.sum(b_c * b_c))
    if norm < 1e-12:
        return empty

    raw = sig.correlate(a_c, b_c, mode="full", method="fft")
    center = len(raw) // 2
    lo = max(0, center - max_lag)
    hi = min(len(raw), center + max_lag + 1)
    windowed = raw[lo:hi] / norm

    best_idx = int(np.argmax(np.abs(windowed)))
    best_correlation = float(np.clip(windowed[best_idx], -1.0, 1.0))
    best_lag = (lo + best_idx) - center

    likely_related = abs(best_correlation) >= unrelated_threshold
    polarity_inverted = likely_related and best_correlation <= inversion_threshold

    return {
        "best_correlation": round(best_correlation, 4),
        "best_lag_samples": best_lag,
        "likely_related": likely_related,
        "polarity_inverted": polarity_inverted,
    }


_SUFFIX_STRIP_RE = re.compile(r"[\s_-]*(\d+|top|bottom|in|out|di|amp|close|room|l|r)$", re.IGNORECASE)
_MIC_PAIR_KEYWORDS = (
    ("di", "amp"), ("in", "out"), ("top", "bottom"), ("close", "room"),
)


def _base_name(name: str) -> str:
    """Strip a trailing numeric or common mic-pair-role suffix so
    'VOCALS-1'/'VOCALS-2'/'VOCALS' all reduce to the same base, and
    'kick_in'/'kick_out' both reduce to 'kick'."""
    stem = name.rsplit(".", 1)[0].strip().lower()
    prev = None
    while prev != stem:
        prev = stem
        stem = _SUFFIX_STRIP_RE.sub("", stem).strip()
    return stem


def find_plausible_related_pairs(stem_names: list[str]) -> list[tuple[str, str]]:
    """Decide which stem PAIRS are plausible mic-pair/related-source
    candidates, from filename convention alone (not audio) -- mirrors
    Stage K's `analyze_stems_for_dynamics()`, which pairs plausible
    triggers against plausible targets rather than brute-force-checking
    every stem against every other one. A bare "same classified instrument"
    heuristic was tested against real production stems and rejected: most
    same-instrument stems in real projects are different musical parts
    (e.g. two synth-lead layers), not multi-mic'd duplicates of one source
    -- filename convention (a shared base name, or a DI/amp-style keyword
    pair) is a much stronger, more precise signal.
    """
    pairs: list[tuple[str, str]] = []
    bases: dict[str, list[str]] = {}
    for name in stem_names:
        bases.setdefault(_base_name(name), []).append(name)

    for base, names in bases.items():
        if len(names) < 2 or not base:
            continue
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                pairs.append((names[i], names[j]))

    lowered = {name: name.rsplit(".", 1)[0].strip().lower() for name in stem_names}
    for kw_a, kw_b in _MIC_PAIR_KEYWORDS:
        a_matches = [n for n, low in lowered.items() if kw_a in low]
        b_matches = [n for n, low in lowered.items() if kw_b in low]
        for a in a_matches:
            for b in b_matches:
                if a != b and (a, b) not in pairs and (b, a) not in pairs:
                    pairs.append((a, b))

    return pairs


def analyze_stems_for_phase_issues(
    stem_dicts: list[dict],
    sample_rate: int,
    *,
    min_lag_samples: int = 2,
    min_lag_correlation: float = 0.5,
) -> dict[str, dict]:
    """Run the phase/polarity detector across all plausible related pairs in
    a stem set, flagging BOTH full polarity inversion and sub-inversion
    micro-phase misalignment (a genuine time-of-arrival offset between two
    mics on the same source -- e.g. kick in/out a few cm apart -- that isn't
    a polarity flip but still causes frequency-dependent comb-filter
    cancellation when summed).

    Parameters
    ----------
    stem_dicts : list[dict]
        Each dict has ``"name"`` and ``"samples"``.
    sample_rate : int
    min_lag_samples : int
        A lag estimate below this is indistinguishable from cross-correlation
        jitter on real material and is left uncorrected -- 2 samples
        (~45us @ 44.1kHz) comfortably clears that noise floor while still
        catching the few-sample-to-few-ms mic-placement offsets that
        actually cause audible comb filtering.
    min_lag_correlation : float
        Only trust (and act on) the lag estimate when the pair's correlation
        at the best-aligned lag is at least this strong -- weaker than this
        and the "best lag" is more likely coincidental than a real
        time-of-arrival offset. Deliberately stricter than
        ``detect_phase_polarity``'s own ``unrelated_threshold`` (0.3), since
        an actual sample-shift is applied here, not just a report.

    Returns
    -------
    dict[str, dict]
        Keyed by stem name -- only stems involved in at least one plausible
        pair appear. Each value:
          - "polarity_inverted": bool
          - "inverted_relative_to": str | None (the other stem's name)
          - "time_misaligned": bool
          - "lag_samples": int (signed; positive = this stem should be
            delayed to align with "aligned_to". 0 if not time_misaligned)
          - "aligned_to": str | None (the other stem's name)
          - "correlation": float
    """
    samples_by_name = {s["name"]: np.asarray(s["samples"], dtype=np.float64) for s in stem_dicts}
    stem_names = list(samples_by_name.keys())
    pairs = find_plausible_related_pairs(stem_names)

    results: dict[str, dict] = {}
    for name_a, name_b in pairs:
        if name_a not in samples_by_name or name_b not in samples_by_name:
            continue
        detection = detect_phase_polarity(samples_by_name[name_a], samples_by_name[name_b], sample_rate)
        if not detection["likely_related"]:
            continue

        polarity_inverted = detection["polarity_inverted"]
        time_misaligned = (
            abs(detection["best_correlation"]) >= min_lag_correlation
            and abs(detection["best_lag_samples"]) >= min_lag_samples
        )
        if not polarity_inverted and not time_misaligned:
            continue

        # Flag whichever stem isn't already flagged -- correct one side,
        # not both (correcting both would leave them right back out of
        # alignment/polarity relative to each other again).
        target = name_b if name_a not in results else name_a
        other = name_a if target == name_b else name_b
        # detect_phase_polarity(name_a, name_b, ...) reports best_lag_samples
        # in the convention "delay name_b by this many samples to align with
        # name_a" (see detect_phase_polarity's docstring/derivation). When
        # the flagged target is name_a instead, the correction direction is
        # the mirror image, so the sign flips.
        lag_samples = detection["best_lag_samples"] if target == name_b else -detection["best_lag_samples"]

        results[target] = {
            "polarity_inverted": polarity_inverted,
            "inverted_relative_to": other if polarity_inverted else None,
            "time_misaligned": time_misaligned,
            "lag_samples": lag_samples if time_misaligned else 0,
            "aligned_to": other if time_misaligned else None,
            "correlation": detection["best_correlation"],
        }

    return results


def _shift_delay(samples: np.ndarray, lag_samples: int) -> np.ndarray:
    """Time-shift ``samples`` by ``lag_samples`` (zero-padding one end and
    truncating the other, so length is preserved -- no wraparound, which
    would smear content from the opposite end of the stem into the shifted
    copy). Positive = delay (prepend zeros); negative = advance (append
    zeros, drop from the front). Matches the sign convention documented on
    ``detect_phase_polarity``'s ``best_lag_samples``."""
    n = len(samples)
    if lag_samples == 0 or n == 0:
        return samples
    if lag_samples > 0:
        k = min(lag_samples, n)
        return np.concatenate([np.zeros(k), samples])[:n]
    k = min(-lag_samples, n)
    return np.concatenate([samples[k:], np.zeros(k)])


def correct_stem_polarity(
    stem_dicts: list[dict],
    sample_rate: int,
) -> tuple[list[dict], dict[str, dict]]:
    """Detect and correct polarity inversions AND micro-phase (sample-delay)
    misalignment between related stems, then re-verify each fix -- the same
    "detect -> act -> re-verify" pattern Stage C's own dynamic-EQ
    integration test already uses (detector finds it -> processor fixes it
    -> detector re-run confirms the fix, not assumed).

    Returns
    -------
    (corrected_stem_dicts, report)
        report is keyed by stem name for every stem that was corrected:
          - "original_correlation": float
          - "corrected_correlation": float | None
          - "polarity_flipped": bool
          - "inverted_relative_to": str | None
          - "time_shifted": bool
          - "lag_samples_corrected": int
          - "aligned_to": str | None
          - "fix_verified": bool (corrected_correlation moved toward +1)
    """
    flags = analyze_stems_for_phase_issues(stem_dicts, sample_rate)
    if not flags:
        return stem_dicts, {}

    by_name = {s["name"]: dict(s) for s in stem_dicts}
    report: dict[str, dict] = {}

    for name, flag in flags.items():
        if name not in by_name:
            continue
        current = np.asarray(by_name[name]["samples"], dtype=np.float64)
        left = np.asarray(by_name[name].get("left_samples", []), dtype=np.float64)
        right = np.asarray(by_name[name].get("right_samples", []), dtype=np.float64)
        has_stereo = bool(by_name[name].get("stereo_preserved")) and len(left) and len(right)

        if flag["polarity_inverted"]:
            current = -1.0 * current
            if has_stereo:
                left = -1.0 * left
                right = -1.0 * right

        if flag["time_misaligned"]:
            current = _shift_delay(current, flag["lag_samples"])
            if has_stereo:
                left = _shift_delay(left, flag["lag_samples"])
                right = _shift_delay(right, flag["lag_samples"])

        by_name[name]["samples"] = current
        if has_stereo:
            by_name[name]["left_samples"] = left
            by_name[name]["right_samples"] = right

        other_name = flag["inverted_relative_to"] or flag["aligned_to"]
        other_samples = np.asarray(by_name.get(other_name, {}).get("samples", []), dtype=np.float64)
        if len(other_samples):
            recheck = detect_phase_polarity(current, other_samples, sample_rate)
            fix_verified = recheck["best_correlation"] > flag["correlation"]
        else:
            recheck = {"best_correlation": None}
            fix_verified = False

        report[name] = {
            "original_correlation": flag["correlation"],
            "corrected_correlation": recheck["best_correlation"],
            "polarity_flipped": flag["polarity_inverted"],
            "inverted_relative_to": flag["inverted_relative_to"],
            "time_shifted": flag["time_misaligned"],
            "lag_samples_corrected": flag["lag_samples"],
            "aligned_to": flag["aligned_to"],
            "fix_verified": fix_verified,
        }

    corrected_stems = [by_name[s["name"]] for s in stem_dicts]
    return corrected_stems, report
