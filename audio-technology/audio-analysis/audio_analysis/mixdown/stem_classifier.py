"""Automatic stem instrument classification from filename heuristics and spectral analysis.

Classifies uploaded audio stems into instrument categories (kick, snare, bass, vocal,
etc.) using a two-stage approach:
  1. Filename heuristics — pattern matching against common naming conventions
  2. Spectral fingerprinting — spectral centroid, fundamental frequency, transient
     density, and crest factor analysis for ambiguous cases
"""

from __future__ import annotations

import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


def _classify_worker_count(n_stems: int) -> int:
    """Same convention as stem_prep._decode_worker_count / mix_renderer.py's
    _render_worker_count. classify_stems decodes each stem independently
    (bounded preview, separate from prepare_stems' own full-rate decode) --
    a separate env var since this stage's I/O pattern differs from both.
    Override with AUTOMIX_CLASSIFY_WORKERS (=1 forces the sequential path)."""
    env = os.environ.get("AUTOMIX_CLASSIFY_WORKERS")
    if env:
        try:
            return max(1, min(int(env), max(1, n_stems)))
        except ValueError:
            pass
    return max(1, min(4, os.cpu_count() or 1, max(1, n_stems)))


# ---------------------------------------------------------------------------
# Instrument taxonomy
# ---------------------------------------------------------------------------

INSTRUMENT_TYPES = (
    "kick",
    "snare",
    "hihat",
    "percussion",
    "bass",
    "sub_bass",
    "vocal",
    "backing_vocal",
    "synth_lead",
    "synth_pad",
    "guitar",
    "keys",
    "strings",
    "brass",
    "fx",
    "ambient",
    "full_drum_bus",
    "other",
)

# ---------------------------------------------------------------------------
# Filename heuristic patterns — (regex, instrument, confidence)
# ---------------------------------------------------------------------------

_FILENAME_RULES: list[tuple[str, str, float]] = [
    # Drums & percussion
    (r"\bkick\b", "kick", 0.95),
    (r"\bbd\b", "kick", 0.85),
    (r"\bbass[\s_-]?drum\b", "kick", 0.90),
    (r"\bsnare\b", "snare", 0.95),
    (r"\bsn\b", "snare", 0.80),
    (r"\bsnr\b", "snare", 0.85),
    (r"\bclap\b", "snare", 0.80),
    (r"\bhi[\s_-]?hats?\b", "hihat", 0.95),
    (r"\bhh\b", "hihat", 0.85),
    (r"\bhats?\b", "hihat", 0.80),
    (r"\bcymbals?\b", "hihat", 0.75),
    (r"\bride\b", "hihat", 0.75),
    (r"\bcrash\b", "hihat", 0.75),
    (r"\bperc\b", "percussion", 0.90),
    (r"\bshakers?\b", "percussion", 0.90),
    (r"\btamb\b", "percussion", 0.90),
    (r"\bcongas?\b", "percussion", 0.90),
    (r"\bbongos?\b", "percussion", 0.90),
    (r"\btoms?\b", "percussion", 0.85),
    (r"\bdrum[\s_-]?bus\b", "full_drum_bus", 0.95),
    (r"\bdrums\b", "full_drum_bus", 0.90),
    (r"\bbeat\b", "full_drum_bus", 0.80),
    (r"\bloop\b", "full_drum_bus", 0.65),
    # Bass
    (r"\bsub[\s_-]?bass\b", "sub_bass", 0.95),
    (r"\bsub\b", "sub_bass", 0.85),
    (r"\b808\b", "sub_bass", 0.85),
    (r"\bbass\b", "bass", 0.90),
    # Vocals
    (r"\blead[\s_-]?voc", "vocal", 0.95),
    (r"\bvocals?\b", "vocal", 0.90),
    (r"\bvox\b", "vocal", 0.90),
    (r"\bvoice\b", "vocal", 0.85),
    (r"\bsing\b", "vocal", 0.80),
    (r"\brap\b", "vocal", 0.80),
    (r"\bbacking[\s_-]?voc", "backing_vocal", 0.95),
    (r"\bbv\b", "backing_vocal", 0.85),
    (r"\bharmony\b", "backing_vocal", 0.85),
    (r"\bchoir\b", "backing_vocal", 0.80),
    (r"\badlib\b", "backing_vocal", 0.80),
    # Synths
    (r"\bsynth[\s_-]?lead\b", "synth_lead", 0.95),
    (r"\blead[\s_-]?synth\b", "synth_lead", 0.95),
    (r"\blead\b", "synth_lead", 0.70),
    (r"\barp\b", "synth_lead", 0.75),
    (r"\bpluck\b", "synth_lead", 0.75),
    (r"\bpad\b", "synth_pad", 0.90),
    (r"\batmos\b", "synth_pad", 0.85),
    (r"\btexture\b", "synth_pad", 0.80),
    (r"\bsynth\b", "synth_lead", 0.70),
    # Guitar
    (r"\bgtr\b", "guitar", 0.90),
    (r"\bguitar\b", "guitar", 0.90),
    (r"\bacoustic[\s_-]?gtr\b", "guitar", 0.95),
    (r"\belec[\s_-]?gtr\b", "guitar", 0.95),
    # Keys
    (r"\bpiano\b", "keys", 0.90),
    (r"\bkeys\b", "keys", 0.90),
    (r"\borgan\b", "keys", 0.85),
    (r"\brhodes\b", "keys", 0.90),
    (r"\bwurlitzer\b", "keys", 0.90),
    (r"\bclavinet\b", "keys", 0.85),
    # Strings
    (r"\bstrings?\b", "strings", 0.90),
    (r"\bviolins?\b", "strings", 0.90),
    (r"\bcellos?\b", "strings", 0.90),
    (r"\borchestra\b", "strings", 0.80),
    (r"\borch\b", "strings", 0.75),
    # Brass -- dedicated category added 2026-07-13 (was mapped to "strings"
    # as a pragmatic stopgap since 2026-07-10, when a real "BRASS" stem fell
    # through to "fx" with no filename pattern to catch it at all). Brass
    # now gets its own INSTRUMENT_RULES/INSTRUMENT_PRIORITY/GENRE_MODIFIERS
    # entries in mix_rules.py rather than inheriting strings' lush-pad
    # treatment (wide stereo, long hall reverb, no compression) which never
    # fit a punchy horn section.
    (r"\bbrass\b", "brass", 0.70),
    (r"\btrumpets?\b", "brass", 0.80),
    (r"\btrombones?\b", "brass", 0.80),
    (r"\bsax(?:ophone)?s?\b", "brass", 0.75),
    (r"\bhorns?\b", "brass", 0.70),
    (r"\btuba\b", "brass", 0.80),
    (r"\bflugel(?:horn)?\b", "brass", 0.80),
    # FX / Ambient
    (r"\bfx\b", "fx", 0.85),
    (r"\bsfx\b", "fx", 0.90),
    (r"\briser\b", "fx", 0.85),
    (r"\bsweep\b", "fx", 0.80),
    (r"\bimpact\b", "fx", 0.80),
    (r"\bnoise\b", "fx", 0.75),
    (r"\bambien", "ambient", 0.85),
    (r"\broom\b", "ambient", 0.70),
    (r"\breverb\b", "ambient", 0.75),
]


# ---------------------------------------------------------------------------
# StemProfile dataclass
# ---------------------------------------------------------------------------


@dataclass
class StemProfile:
    """Complete profile for a single classified audio stem."""

    name: str
    instrument: str = "other"
    classification_confidence: float = 0.0
    classification_method: str = "none"  # "filename", "spectral", "combined"
    sample_rate: int = 44100
    bit_depth: int = 16
    channels: int = 1
    duration_seconds: float = 0.0
    peak_dbfs: float = -99.0
    rms_dbfs: float = -99.0
    spectral_centroid_hz: float = 0.0
    fundamental_hz: float | None = None
    transient_density: float = 0.0  # onsets per second
    crest_factor_db: float = 0.0
    has_dc_offset: bool = False
    has_silence_head: bool = False
    has_silence_tail: bool = False
    frequency_profile: dict[str, float] = field(default_factory=dict)
    erb_profile: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Filename classification
# ---------------------------------------------------------------------------


def classify_from_filename(filename: str) -> tuple[str, float]:
    """Classify a stem's instrument type from its filename.

    Returns (instrument_type, confidence).  If nothing matches, returns
    ("other", 0.0).
    """
    # Normalise: lowercase, strip extension, replace separators with spaces
    stem = Path(filename).stem.lower()
    normalised = re.sub(r"[_\-\.\s]+", " ", stem).strip()

    best_instrument = "other"
    best_confidence = 0.0

    for pattern, instrument, confidence in _FILENAME_RULES:
        if re.search(pattern, normalised, re.IGNORECASE):
            if confidence > best_confidence:
                best_instrument = instrument
                best_confidence = confidence

    return best_instrument, best_confidence


# ---------------------------------------------------------------------------
# Spectral analysis helpers
# ---------------------------------------------------------------------------


def _spectral_centroid(magnitudes: list[float], sample_rate: int, fft_size: int) -> float:
    """Compute spectral centroid in Hz from FFT magnitudes."""
    if not magnitudes or fft_size <= 0:
        return 0.0
    total = sum(magnitudes)
    if total < 1e-12:
        return 0.0
    freq_step = sample_rate / fft_size
    weighted_sum = sum(mag * (i * freq_step) for i, mag in enumerate(magnitudes))
    return weighted_sum / total


def _estimate_fundamental(magnitudes: list[float], sample_rate: int, fft_size: int,
                          min_hz: float = 20.0, max_hz: float = 4000.0) -> float | None:
    """Estimate the fundamental frequency from FFT magnitudes using peak-picking."""
    if not magnitudes or fft_size <= 0:
        return None
    freq_step = sample_rate / fft_size
    min_bin = max(1, int(min_hz / freq_step))
    max_bin = min(len(magnitudes) - 1, int(max_hz / freq_step))
    if min_bin >= max_bin:
        return None

    # Find the bin with maximum magnitude in the fundamental range
    peak_bin = min_bin
    peak_mag = magnitudes[min_bin]
    for i in range(min_bin + 1, max_bin + 1):
        if magnitudes[i] > peak_mag:
            peak_mag = magnitudes[i]
            peak_bin = i

    # Parabolic interpolation for sub-bin accuracy
    if 1 <= peak_bin < len(magnitudes) - 1 and peak_mag > 1e-12:
        alpha = magnitudes[peak_bin - 1]
        beta = magnitudes[peak_bin]
        gamma = magnitudes[peak_bin + 1]
        denom = alpha - 2.0 * beta + gamma
        if abs(denom) > 1e-12:
            offset = 0.5 * (alpha - gamma) / denom
            return (peak_bin + offset) * freq_step

    return peak_bin * freq_step


def _transient_density(samples: list[float], sample_rate: int,
                       window_ms: float = 10.0, threshold_db: float = 6.0) -> float:
    """Estimate transient density as onsets per second using a simple spectral flux approach."""
    if not samples or sample_rate <= 0:
        return 0.0
    window_size = max(64, int(sample_rate * window_ms / 1000.0))
    hop = window_size // 2
    if len(samples) < window_size * 2:
        return 0.0

    # Compute short-term energy in each (overlapping, hop-strided) window --
    # vectorized: sliding_window_view produces every window of size
    # window_size, [::hop] selects the same start positions as
    # range(0, len(samples)-window_size+1, hop) did.
    arr = np.asarray(samples, dtype=np.float64)
    windows = np.lib.stride_tricks.sliding_window_view(arr, window_size)[::hop]
    energies = (np.sum(windows * windows, axis=1) / window_size).tolist()

    if len(energies) < 3:
        return 0.0

    # Count positive energy jumps above threshold
    threshold_ratio = 10.0 ** (threshold_db / 10.0)
    onset_count = 0
    for i in range(1, len(energies)):
        if energies[i - 1] > 1e-12:
            if energies[i] / energies[i - 1] > threshold_ratio:
                onset_count += 1
        elif energies[i] > 1e-9:
            onset_count += 1

    duration = len(samples) / sample_rate
    return onset_count / max(duration, 0.01)


def _crest_factor_db(samples: list[float]) -> float:
    """Compute crest factor (peak / RMS) in dB."""
    if not samples:
        return 0.0
    arr = np.asarray(samples, dtype=np.float64)
    peak = float(np.max(np.abs(arr)))
    rms = float(np.sqrt(np.mean(arr * arr)))
    if rms < 1e-12:
        return 0.0
    return 20.0 * math.log10(max(peak / rms, 1e-12))


def _detect_dc_offset(samples: list[float], threshold: float = 0.005) -> bool:
    """Detect DC offset above the threshold."""
    if not samples:
        return False
    mean = float(np.mean(np.asarray(samples, dtype=np.float64)))
    return abs(mean) > threshold


def _detect_silence(samples: list[float], sample_rate: int,
                    threshold_db: float = -60.0, min_duration_ms: float = 50.0) -> tuple[bool, bool]:
    """Detect silence at the head and tail of the audio.

    Returns (has_silence_head, has_silence_tail).
    """
    if not samples or sample_rate <= 0:
        return False, False

    threshold_linear = 10.0 ** (threshold_db / 20.0)
    min_samples = max(1, int(sample_rate * min_duration_ms / 1000.0))

    # Head silence
    head_silent = True
    for i in range(min(min_samples, len(samples))):
        if abs(samples[i]) > threshold_linear:
            head_silent = False
            break

    # Tail silence
    tail_silent = True
    for i in range(max(0, len(samples) - min_samples), len(samples)):
        if abs(samples[i]) > threshold_linear:
            tail_silent = False
            break

    return head_silent, tail_silent


# ---------------------------------------------------------------------------
# Spectral classification rules
# ---------------------------------------------------------------------------

# (instrument, centroid_range_hz, fundamental_range_hz, transient_density_range, crest_range_db)
_SPECTRAL_RULES: list[tuple[str, tuple[float, float], tuple[float, float] | None,
                             tuple[float, float], tuple[float, float]]] = [
    ("kick",        (40, 250),    (30, 80),      (0, 8),    (10, 30)),
    ("sub_bass",    (30, 120),    (20, 80),      (0, 3),    (3, 15)),
    ("bass",        (60, 500),    (30, 250),     (0, 6),    (5, 20)),
    ("snare",       (800, 5000),  (100, 500),    (2, 15),   (10, 30)),
    ("hihat",       (4000, 16000), None,          (5, 40),   (8, 30)),
    ("percussion",  (500, 8000),  None,           (3, 30),   (8, 30)),
    ("vocal",       (800, 4000),  (80, 1200),    (0, 5),    (8, 25)),
    ("synth_lead",  (500, 6000),  (60, 2000),    (0, 8),    (5, 25)),
    ("synth_pad",   (200, 3000),  (40, 1000),    (0, 2),    (3, 15)),
    ("guitar",      (400, 4000),  (80, 1200),    (1, 12),   (8, 25)),
    ("keys",        (300, 5000),  (30, 4000),    (1, 10),   (8, 25)),
    ("strings",     (300, 4000),  (80, 1200),    (0, 3),    (5, 20)),
    ("fx",          (1000, 16000), None,          (0, 20),   (3, 30)),
    ("ambient",     (200, 8000),  None,           (0, 2),    (3, 15)),
]


def classify_from_spectral(centroid_hz: float, fundamental_hz: float | None,
                           transient_density: float, crest_db: float) -> tuple[str, float]:
    """Classify instrument type from spectral features.

    Returns (instrument_type, confidence).
    """
    best_instrument = "other"
    best_score = 0.0

    for inst, centroid_range, fund_range, td_range, crest_range in _SPECTRAL_RULES:
        score = 0.0
        checks = 0

        # Centroid match
        checks += 1
        if centroid_range[0] <= centroid_hz <= centroid_range[1]:
            score += 1.0
        elif centroid_hz < centroid_range[0]:
            distance = centroid_range[0] - centroid_hz
            score += max(0.0, 1.0 - distance / centroid_range[0])
        else:
            distance = centroid_hz - centroid_range[1]
            score += max(0.0, 1.0 - distance / centroid_range[1])

        # Fundamental match
        if fund_range is not None and fundamental_hz is not None:
            checks += 1
            if fund_range[0] <= fundamental_hz <= fund_range[1]:
                score += 1.0
            else:
                dist = min(abs(fundamental_hz - fund_range[0]),
                           abs(fundamental_hz - fund_range[1]))
                span = fund_range[1] - fund_range[0]
                score += max(0.0, 1.0 - dist / max(span, 1.0))

        # Transient density match
        checks += 1
        if td_range[0] <= transient_density <= td_range[1]:
            score += 1.0
        else:
            dist = min(abs(transient_density - td_range[0]),
                       abs(transient_density - td_range[1]))
            span = max(td_range[1] - td_range[0], 1.0)
            score += max(0.0, 1.0 - dist / span)

        # Crest factor match
        checks += 1
        if crest_range[0] <= crest_db <= crest_range[1]:
            score += 1.0
        else:
            dist = min(abs(crest_db - crest_range[0]),
                       abs(crest_db - crest_range[1]))
            span = max(crest_range[1] - crest_range[0], 1.0)
            score += max(0.0, 1.0 - dist / span)

        normalised = score / max(checks, 1)
        if normalised > best_score:
            best_score = normalised
            best_instrument = inst

    # Scale to a 0.0–0.85 confidence range (spectral alone is less certain)
    confidence = min(0.85, best_score * 0.85)
    return best_instrument, confidence


# ---------------------------------------------------------------------------
# Full classification pipeline
# ---------------------------------------------------------------------------


def classify_stem(
    filename: str,
    samples: list[float],
    sample_rate: int,
    *,
    fft_size: int = 4096,
    spectral_bands_fn=None,
) -> StemProfile:
    """Classify a single stem and return a full StemProfile.

    Parameters
    ----------
    filename : str
        Original filename (used for heuristic classification).
    samples : list[float]
        Mono audio samples normalised to [-1.0, 1.0].
    sample_rate : int
        Sample rate in Hz.
    fft_size : int
        FFT window size for spectral analysis.
    spectral_bands_fn : callable, optional
        A function ``(samples, sample_rate, size=N) -> dict`` that returns
        7-band spectral energy ratios.  If *None*, frequency_profile is left
        empty.
    """
    profile = StemProfile(name=filename)
    profile.sample_rate = sample_rate
    profile.duration_seconds = len(samples) / max(sample_rate, 1)

    # --- Basic level metrics ---
    if samples:
        _arr = np.asarray(samples, dtype=np.float64)
        profile.peak_dbfs = 20.0 * math.log10(max(float(np.max(np.abs(_arr))), 1e-12))
        rms = float(np.sqrt(np.mean(_arr * _arr)))
        profile.rms_dbfs = 20.0 * math.log10(max(rms, 1e-12))
        profile.crest_factor_db = _crest_factor_db(samples)
        profile.has_dc_offset = _detect_dc_offset(samples)
        profile.has_silence_head, profile.has_silence_tail = _detect_silence(samples, sample_rate)
        profile.transient_density = _transient_density(samples, sample_rate)

    # --- Spectral features ---
    from audio_analysis.analysis_core.dsp_metrics import spectrum_magnitudes

    usable_size = min(fft_size, len(samples))
    n = 1
    while n * 2 <= usable_size:
        n *= 2
    if n >= 256 and samples:
        mags, fft_n = spectrum_magnitudes(samples, sample_rate, size=n)
        if mags and fft_n > 0:
            profile.spectral_centroid_hz = _spectral_centroid(mags, sample_rate, fft_n)
            profile.fundamental_hz = _estimate_fundamental(mags, sample_rate, fft_n)

    # --- 7-band frequency profile ---
    if spectral_bands_fn is not None and samples:
        try:
            fb = spectral_bands_fn(samples, sample_rate, size=min(fft_size, len(samples)))
            profile.frequency_profile = {k: float(v) for k, v in fb.items()} if fb else {}
        except Exception:
            pass

    # --- Classification ---
    filename_inst, filename_conf = classify_from_filename(filename)
    spectral_inst, spectral_conf = classify_from_spectral(
        profile.spectral_centroid_hz,
        profile.fundamental_hz,
        profile.transient_density,
        profile.crest_factor_db,
    )

    # Decision: trust filename if high confidence; otherwise combine
    if filename_conf >= 0.85:
        profile.instrument = filename_inst
        profile.classification_confidence = filename_conf
        profile.classification_method = "filename"
    elif filename_conf >= 0.65 and filename_inst == spectral_inst:
        # Both agree — high confidence
        profile.instrument = filename_inst
        profile.classification_confidence = min(0.98, (filename_conf + spectral_conf) / 2 + 0.1)
        profile.classification_method = "combined"
    elif filename_conf >= 0.65:
        # Filename is decent but spectral disagrees — trust filename
        profile.instrument = filename_inst
        profile.classification_confidence = filename_conf
        profile.classification_method = "filename"
    elif spectral_conf >= 0.5:
        # Filename is weak, spectral has something
        profile.instrument = spectral_inst
        profile.classification_confidence = spectral_conf
        profile.classification_method = "spectral"
    else:
        profile.instrument = filename_inst if filename_conf > spectral_conf else spectral_inst
        profile.classification_confidence = max(filename_conf, spectral_conf)
        profile.classification_method = "filename" if filename_conf > spectral_conf else "spectral"

    return profile


def classify_stems(
    stems: list[dict],
    *,
    read_wav_mono_fn,
    spectral_bands_fn=None,
    max_samples: int = 131072,
) -> list[StemProfile]:
    """Classify a batch of stems.

    Parameters
    ----------
    stems : list[dict]
        Each dict must have ``"name"`` (filename) and ``"file_bytes"`` (raw
        WAV bytes).
    read_wav_mono_fn : callable
        ``(file_bytes, max_samples=N) -> dict`` with keys ``"samples"`` and
        ``"sample_rate"``.
    spectral_bands_fn : callable, optional
        Passed through to :func:`classify_stem`.
    max_samples : int
        Maximum samples to read per stem.

    Returns
    -------
    list[StemProfile]
    """
    # Each stem's decode + classification is independent, so this is
    # parallelized across a thread pool -- same pattern as
    # stem_prep._decode_worker_count / mix_renderer.py's per-stem render
    # loop. map() preserves input order, so output is identical to the
    # sequential loop, just not serialized on per-stem decode I/O.
    def _classify_one(stem: dict) -> "StemProfile":
        name = stem.get("name", "unknown.wav")
        file_bytes = stem.get("file_bytes", b"")
        try:
            wav_data = read_wav_mono_fn(file_bytes, max_samples=max_samples)
            samples = wav_data.get("samples", [])
            sr = wav_data.get("sample_rate", 44100)
        except Exception as exc:
            # Same fail-loud standard as stem_prep.prepare_stems (fixed 2026-07-08,
            # docs/AUTOMIX_QUALITY_FINDINGS_2026-07-08.md finding #3): classify_stems
            # runs BEFORE prepare_stems in the real pipeline, so a silent empty-stem
            # fallback here produced a nonsense classification even earlier than the
            # crash that finding originally traced.
            raise ValueError(f"Could not read audio stem '{name}': {exc}") from exc
        if not samples:
            raise ValueError(
                f"Audio stem '{name}' decoded to zero samples (empty, silent, or corrupt file)."
            )
        return classify_stem(name, samples, sr, spectral_bands_fn=spectral_bands_fn)

    _n_classify_workers = _classify_worker_count(len(stems))
    if _n_classify_workers > 1:
        with ThreadPoolExecutor(max_workers=_n_classify_workers) as _ex:
            return list(_ex.map(_classify_one, stems))
    return [_classify_one(stem) for stem in stems]


# ---------------------------------------------------------------------------
# Post-processing spectral target verification
# ---------------------------------------------------------------------------
#
# _SPECTRAL_RULES above answers "what instrument does this raw stem sound
# like" (input classification). This answers a different question: once
# AutoMix's own gain/EQ/compression/etc. have been applied, does the stem's
# PROCESSED spectral centroid still land where that instrument is expected
# to sit? Reuses the same range table deliberately -- if a kick's processed
# centroid drifts outside a kick's own expected range, that's a real signal
# something in the per-stem processing chain pushed it somewhere a kick
# shouldn't be, not a new, separately-calibrated standard.


def _perceptual_spectral_centroid(
    magnitudes: list[float], sample_rate: int, fft_size: int, *, phon_level: float = 60.0,
) -> float:
    """Spectral centroid weighted by ISO 226 equal-loudness contours, not a
    plain linear FFT-magnitude average.

    Found 2026-07-10 verifying real processed stems: a kick/bass's PLAIN
    centroid (`_spectral_centroid`) can land far outside the range a human
    would ever call "low end" -- a kick's sharp attack click is a genuine,
    often-wanted part of its punch, but it's broadband and loud enough in
    raw FFT-bin terms to drag a simple linear average up into the mids/highs,
    even though at any real monitoring level a listener's ear (per ISO 226)
    is dramatically less sensitive to that same energy than to the kick's
    low-frequency body. A plain average has no way to know that; weighting
    each bin by `equal_loudness_gain` before averaging does. This reuses the
    exact same ISO 226 engine `fletcher_munson_advice.py`'s mix critique
    already depends on -- not a new, separately-calibrated model.
    """
    if not magnitudes or fft_size <= 0:
        return 0.0
    from audio_analysis.analysis_core.dsp_metrics import fletcher_munson_corrected_spectrum

    freq_step = sample_rate / fft_size
    frequencies = [i * freq_step for i in range(len(magnitudes))]
    weighted_mags = fletcher_munson_corrected_spectrum(magnitudes, frequencies, phon_level)

    total = sum(weighted_mags)
    if total < 1e-12:
        return _spectral_centroid(magnitudes, sample_rate, fft_size)
    weighted_sum = sum(mag * freq for mag, freq in zip(weighted_mags, frequencies))
    return weighted_sum / total


# Minimum sub+bass energy SHARE (fraction of total spectral energy, 20-150Hz
# per dsp_metrics.BANDS) expected for instruments where spectral centroid is
# known unreliable -- confirmed 2026-07-10: a kick/bass's genuine low body
# can coexist with a broadband transient click loud enough (in raw or even
# equal-loudness-weighted terms) to drag a single centroid number well above
# where the instrument actually sits. Checking that the low end is *present*
# (a band-energy share) sidesteps that problem entirely instead of trying to
# make one number describe two very different things at once. Deliberately
# conservative (low thresholds) -- this is a floor check ("is there real low
# end here at all"), not a target ("should be exactly this bass-heavy").
_LOW_FREQ_SHARE_MIN: dict[str, float] = {
    "kick": 0.12,
    "sub_bass": 0.20,
    "bass": 0.08,
    "percussion": 0.03,
}


def verify_stem_spectral_targets(
    stem_audio: dict[str, tuple[np.ndarray, np.ndarray]],
    profiles: list[StemProfile],
    sample_rate: int,
    *,
    fft_size: int = 4096,
    phon_level: float = 60.0,
) -> list[dict]:
    """Check each stem's POST-PROCESSING spectral centroid against the
    expected range for its classified instrument.

    Uses the equal-loudness-weighted centroid (`_perceptual_spectral_
    centroid`), not the plain linear one `classify_from_spectral()` uses for
    input classification -- deliberately: verification asks "would this
    sound right to a listener," a perceptual question, while classification
    is matching a raw acoustic fingerprint against a reference table.
    Conflating the two would mean re-deriving and re-validating the whole
    `_SPECTRAL_RULES` table against a differently-weighted signal; keeping
    them separate lets this land without touching classification's
    already-tested behavior at all.

    Parameters
    ----------
    stem_audio : dict[str, tuple[np.ndarray, np.ndarray]]
        From ``mix_and_render_stems(..., capture_stem_audio=True)``'s
        ``"stem_audio"`` key -- each stem's fully-processed L/R audio,
        exactly as it contributes to the mix bus.
    profiles : list[StemProfile]
        The same profiles ``classify_stems()`` produced for these stems
        (used to look up each stem's classified instrument and the range
        table entry that applies to it).
    sample_rate : int
    phon_level : float
        Monitoring level for the equal-loudness weighting (default 60,
        matching this codebase's other phon-aware analysis defaults).

    Returns
    -------
    list[dict]
        One entry per stem with matching audio+profile:
          - "name": stem name
          - "instrument": classified instrument
          - "processed_centroid_hz": float (equal-loudness-weighted)
          - "expected_centroid_range_hz": (low, high) | None (None if the
            instrument has no entry in the range table, e.g. "other")
          - "within_expected_range": bool | None (None if no range to check)
          - "low_freq_share": float | None (sub+bass energy fraction, only
            computed for instruments in _LOW_FREQ_SHARE_MIN)
          - "low_freq_share_min": float | None (the threshold applied)
          - "low_freq_check_passed": bool | None
    """
    from audio_analysis.analysis_core.dsp_metrics import band_ratios, spectrum_magnitudes

    range_by_instrument = {row[0]: row[1] for row in _SPECTRAL_RULES}
    profile_by_name = {p.name: p for p in profiles}

    results: list[dict] = []
    for name, (left, right) in stem_audio.items():
        profile = profile_by_name.get(name)
        if profile is None:
            continue

        mono = ((np.asarray(left, dtype=np.float64) + np.asarray(right, dtype=np.float64)) * 0.5).tolist()
        usable_size = min(fft_size, len(mono))
        n = 1
        while n * 2 <= usable_size:
            n *= 2
        if n < 256 or not mono:
            continue

        mags, fft_n = spectrum_magnitudes(mono, sample_rate, size=n)
        if not mags or fft_n <= 0:
            continue
        centroid_hz = _perceptual_spectral_centroid(mags, sample_rate, fft_n, phon_level=phon_level)

        expected_range = range_by_instrument.get(profile.instrument)
        within_range = (
            expected_range[0] <= centroid_hz <= expected_range[1]
            if expected_range is not None
            else None
        )

        # Complementary low-frequency-share floor check, for instruments
        # where centroid alone is known unreliable (see _LOW_FREQ_SHARE_MIN's
        # docstring) -- reports separately from within_expected_range rather
        # than folding into one bool, so it's clear which check is being
        # applied and why.
        low_freq_share_min = _LOW_FREQ_SHARE_MIN.get(profile.instrument)
        low_freq_share = None
        low_freq_check_passed = None
        if low_freq_share_min is not None:
            bands = band_ratios(mags, sample_rate, fft_n)
            low_freq_share = round(bands.get("sub", 0.0) + bands.get("bass", 0.0), 4)
            low_freq_check_passed = low_freq_share >= low_freq_share_min

        results.append({
            "name": name,
            "instrument": profile.instrument,
            "processed_centroid_hz": round(centroid_hz, 1),
            "expected_centroid_range_hz": expected_range,
            "within_expected_range": within_range,
            "low_freq_share": low_freq_share,
            "low_freq_share_min": low_freq_share_min,
            "low_freq_check_passed": low_freq_check_passed,
        })

    return results

    return profiles
