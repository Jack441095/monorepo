"""Reference spectral matching for AutoMix.

Given a RENDERED mix and a genre reference (a single track or a directory of
same-genre references), derive a boost-biased, deadbanded, iterative master
match-EQ that moves the mix's spectral balance toward the reference on the
perceptually-correct LOG bands. This is the correct engine
(``log_band_ratios_track_average`` -> ``map_40_to_7_bands`` /
``compute_tonal_balance_score``), NOT the linear ``analyze_reference_track``
path (which reads bass as ~0 and can't drive the low end).

Validated by maximizing the reference tonal-balance score on real renders
(stranger vs Stromae 30 -> 76; generalises across tracks) -- see
``docs/audits/2026-07-23-render-speed-and-bass-findings.md``. Used by both the
``automix_local.py`` CLI and the ``automix_worker`` UI/server path.

Typical two-pass use: render once, ``compute_reference_match_bands(rendered_bytes,
ref)`` -> append to ``plan.bus.bus_eq_bands`` -> render again. Same pattern for
stereo width: ``compute_reference_width_factor(rendered_bytes, ref)`` -> set
``plan.bus.reference_width_factor`` -> render again -- deliberately a gentle
similarity NUDGE rather than a hard match (see that function's docstring),
since aggressive M/S width correction risks phase/mono-compatibility problems.
"""

from __future__ import annotations

import math
from pathlib import Path

AUDIO_SUFFIXES = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a"}

# The iterative matcher revisits fixed log-frequency centres. Keeping each
# historical pass creates duplicate master bells without adding a distinct
# musical decision, and makes zero-phase master processing needlessly costly.
MAX_REFERENCE_MATCH_BOOST_DB = 6.0
MAX_REFERENCE_MATCH_CUT_DB = 3.0


def _coalesce_iterative_bands(bands: list[dict]) -> list[dict]:
    """Keep one bounded reference-match bell for each exact centre/Q pair."""
    merged: dict[tuple[str, float, float], dict] = {}
    for band in bands:
        band_type = str(band.get("type", "peaking"))
        frequency = float(band.get("frequency", 0.0))
        q = float(band.get("q", 1.4))
        key = (band_type, frequency, q)
        gain = float(band.get("gain_db", 0.0))
        if key not in merged:
            merged[key] = dict(band)
            merged[key]["gain_db"] = gain
        else:
            merged[key]["gain_db"] = float(merged[key]["gain_db"]) + gain

    result: list[dict] = []
    for key in sorted(merged, key=lambda item: item[1]):
        band = merged[key]
        raw_gain = float(band["gain_db"])
        bounded_gain = max(-MAX_REFERENCE_MATCH_CUT_DB, min(MAX_REFERENCE_MATCH_BOOST_DB, raw_gain))
        band["gain_db"] = round(bounded_gain, 2)
        if abs(raw_gain - bounded_gain) > 1.0e-9:
            band["reason"] = (
                f"{band.get('reason', 'Reference match')} "
                f"(coalesced repeated iterations; bounded to {bounded_gain:+.1f} dB)."
            )
        result.append(band)
    return result


def reference_target_40band(reference_track: Path):
    """Build a 40-band log-spectrum target from a reference. If ``reference_track``
    is a DIRECTORY, use a robust MEDIAN average of every audio file in it -- a
    genre-average target (more stable than any one song). The median rejects
    outliers, which matters because references disagree most in sub/low_mids (a
    single acoustic track can skew a naive mean). A single file uses that file.
    Returns ``(target_40, n_refs)`` with the target renormalised to sum ~1 so it
    is comparable to a single track's band distribution."""
    import numpy as np
    from audio_analysis.utils.audio_io import read_wav_mono, decode_audio_bytes
    from audio_analysis.analysis_core.dsp_metrics import log_band_ratios_track_average

    p = Path(reference_track)
    files = (sorted(f for f in p.iterdir() if f.suffix.lower() in AUDIO_SUFFIXES)
             if p.is_dir() else [p])
    mats = []
    for f in files:
        try:
            wav = decode_audio_bytes(f.read_bytes(), f.name)["wav_bytes"]
            d = read_wav_mono(wav, max_samples=0)
            mats.append(np.asarray(log_band_ratios_track_average(d["samples"], int(d["sample_rate"])), dtype=np.float64))
        except Exception:
            continue
    if not mats:
        raise ValueError(f"No usable reference audio in {reference_track}")
    stacked = np.vstack(mats)
    target = np.median(stacked, axis=0) if stacked.shape[0] >= 2 else stacked[0]
    total = float(target.sum())
    if total > 0:
        target = target / total
    return target, stacked.shape[0]


def compute_reference_match_bands(
    mixdown_wav_bytes: bytes,
    reference_track: Path,
    *,
    n_bands: int = 10,
    q: float = 1.4,
    max_iterations: int = 4,
    cut_scale: float = 0.5,
    deadband_db: float = 0.5,
    step_boost_db: float = 6.0,
    step_cut_db: float = 3.0,
) -> list[dict]:
    """Iterative, boost-biased, DENSER-band spectral match to a reference (or a
    genre-average of references).

    * denser bands: correct on ``n_bands`` narrow log-spaced bells (Q~1.4) from
      the 40-band fingerprint -- finer resolution places energy precisely.
    * adaptive stop: iterate while the tonal-balance score improves, keep the
      best-scoring cascade (a fixed count over-corrects past the peak).
    * genre-average target: ``reference_track`` may be a directory (median).
    Boost-biased (cuts scaled by ``cut_scale``, clamped harder than boosts) so the
    low-end boosts carry the match while upper cuts stay gentle. Iterates on the
    rendered 2-track in memory (fast, no re-render); returns the accumulated
    master-bus EQ bands (a cascade -- collapsing to per-band sums lets adjacent
    narrow bells hit the cap and compound, scoring worse).
    """
    import numpy as np
    from audio_analysis.utils.audio_io import read_wav_mono
    from audio_analysis.analysis_core.dsp_metrics import log_band_ratios_track_average
    from audio_analysis.analysis_core.genre_profiles import log_spaced_boundaries, compute_tonal_balance_score
    from audio_analysis.dsp_engine.eq import ParametricEQ

    ref40, _n_refs = reference_target_40band(reference_track)
    ref40_list = ref40.tolist()

    # as_arrays=True skips a redundant list<->array round trip: this runs
    # on the full rendered mixdown for every reference-based AutoMix job
    # (automix_worker.py's compute_reference_match_bands call), not a short
    # probe -- measured ~3.4x faster on a real 205s track.
    mix = read_wav_mono(mixdown_wav_bytes, max_samples=0, as_arrays=True)
    sr = int(mix["sample_rate"])
    samples = np.asarray(mix["samples"], dtype=np.float64)

    bnd = log_spaced_boundaries(20.0, 20000.0, 40)
    centers40 = [math.sqrt(bnd[i] * bnd[i + 1]) for i in range(40)]
    edges = np.linspace(0, 40, n_bands + 1).astype(int)
    band_freq = [math.sqrt(centers40[edges[i]] * centers40[max(edges[i], edges[i + 1] - 1)])
                 for i in range(n_bands)]

    def score_of(s):
        return compute_tonal_balance_score(log_band_ratios_track_average(s, sr), ref40_list)

    applied: list[dict] = []
    best_bells: list[dict] = []
    best_score = score_of(samples)
    no_improve = 0
    for _ in range(max(1, max_iterations)):
        mix40 = np.asarray(log_band_ratios_track_average(samples, sr))
        step_bells: list[dict] = []
        eq = ParametricEQ(sr)
        for i in range(n_bands):
            lo, hi = edges[i], edges[i + 1]
            m = float(mix40[lo:hi].sum())
            r = float(ref40[lo:hi].sum())
            if m < 1e-9 or r < 1e-9:
                continue
            g = 20.0 * math.log10(r / m)
            if g < 0.0:
                g *= cut_scale
            if abs(g) < deadband_db:
                continue
            g = max(-step_cut_db, min(step_boost_db, g))
            eq.add_band("peaking", band_freq[i], g, q)
            step_bells.append({
                "type": "peaking", "frequency": round(band_freq[i], 1),
                "gain_db": round(g, 2), "q": q,
                "reason": f"Ref match {band_freq[i]:.0f}Hz {g:+.1f} dB (iterative {n_bands}-band spectral match).",
            })
        if not step_bells:
            break
        samples = np.asarray(eq.apply(samples), dtype=np.float64)
        applied.extend(step_bells)
        sc = score_of(samples)
        if sc > best_score + 0.1:
            best_score, best_bells, no_improve = sc, list(applied), 0
        else:
            no_improve += 1
            if no_improve >= 2:
                break

    # Each pass revisits the same log centres. Coalesce exact repeats before
    # rendering so the recorded plan remains explainable and resource-bounded;
    # neighbouring bands remain independent.
    return _coalesce_iterative_bands(best_bells)


def reference_target_stereo_width(reference_track: Path) -> float | None:
    """Median overall stereo width (side/mid RMS ratio, from
    ``stereo_image_analysis``) across a genre reference folder, or a single
    reference file's own width. ``None`` if no reference in ``reference_track``
    has usable stereo content (e.g. all mono -- can't derive a width target
    from that)."""
    from audio_analysis.utils.audio_io import read_wav_mono, decode_audio_bytes
    from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis

    p = Path(reference_track)
    files = (sorted(f for f in p.iterdir() if f.suffix.lower() in AUDIO_SUFFIXES)
             if p.is_dir() else [p])
    widths = []
    for f in files:
        try:
            wav = decode_audio_bytes(f.read_bytes(), f.name)["wav_bytes"]
            d = read_wav_mono(wav, max_samples=0)
            if int(d.get("channels", 1)) < 2:
                continue
            result = stereo_image_analysis(d["left_samples"], d["right_samples"], int(d["sample_rate"]))
            w = float(result.get("overall_width", 0.0))
            if w > 0:
                widths.append(w)
        except Exception:
            continue
    if not widths:
        return None
    widths.sort()
    mid = len(widths) // 2
    return widths[mid] if len(widths) % 2 else (widths[mid - 1] + widths[mid]) / 2.0


def compute_reference_width_factor(
    mixdown_wav_bytes: bytes,
    reference_track: Path,
    *,
    similarity_weight: float = 0.35,
    deadband_ratio: float = 0.15,
    min_factor: float = 0.85,
    max_factor: float = 1.15,
) -> float | None:
    """A gentle stereo-width NUDGE toward the reference's own width -- deliberately
    NOT a hard match. Aggressive M/S width correction risks phase/mono-compatibility
    problems (per-band correlation collapse, comb-filtering on mono playback), so
    this only:

    * moves ``similarity_weight`` of the way toward the reference (default 35%
      -- "similar to", not "matched to"),
    * ignores differences under ``deadband_ratio`` (15% relative) as ordinary
      within-genre variance, not something worth correcting,
    * clamps the final multiplier to ``[min_factor, max_factor]`` regardless of
      the computed gap -- at most a ~15% width nudge, ever, no matter how wide
      the reference is.

    Composes multiplicatively with the renderer's existing genre-based width
    boost (mid is invariant under width scaling, so two passes = one pass with
    the product of both factors).

    Returns ``None`` (no correction applied) if the reference has no usable
    stereo content, the mix's own width can't be measured (e.g. a mono
    mixdown), or the gap is within the deadband.
    """
    from audio_analysis.utils.audio_io import read_wav_mono
    from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis

    target_width = reference_target_stereo_width(reference_track)
    if target_width is None:
        return None

    mix = read_wav_mono(mixdown_wav_bytes, max_samples=0, as_arrays=True)
    if int(mix.get("channels", 1)) < 2:
        return None
    mix_result = stereo_image_analysis(mix["left_samples"], mix["right_samples"], int(mix["sample_rate"]))
    mix_width = float(mix_result.get("overall_width", 0.0))
    if mix_width <= 1e-6:
        return None

    relative_diff = abs(target_width - mix_width) / mix_width
    if relative_diff < deadband_ratio:
        return None

    raw_factor = target_width / mix_width
    nudged_factor = 1.0 + similarity_weight * (raw_factor - 1.0)
    return max(min_factor, min(max_factor, nudged_factor))


def compute_reference_dynamics_comp(
    mixdown_wav_bytes: bytes, reference_track: Path, *, min_crest_delta_db: float = 1.0,
) -> dict | None:
    """If the rendered mix is more dynamic (higher crest factor) than the
    reference, return the bus-compressor settings ``dynamics_comparison`` suggests
    to bring its density closer; else ``None``. Uses the first file when a
    genre-average directory is given."""
    from audio_analysis.utils.audio_io import read_wav_mono, decode_audio_bytes
    from audio_analysis.analysis_core.reference_matching import dynamics_comparison

    p = Path(reference_track)
    ref_file = (next((f for f in sorted(p.iterdir()) if f.suffix.lower() in AUDIO_SUFFIXES), None)
                if p.is_dir() else p)
    if ref_file is None:
        return None
    mix = read_wav_mono(mixdown_wav_bytes, max_samples=0, as_arrays=True)
    ref = read_wav_mono(
        decode_audio_bytes(ref_file.read_bytes(), ref_file.name)["wav_bytes"],
        max_samples=0,
        as_arrays=True,
    )
    # dynamics_comparison()'s internals (reference_matching.py) still assume
    # Python-list input for their rolling-window loops as of this change --
    # .tolist() here keeps that call site correct; the as_arrays=True reads
    # above still avoid the per-chunk decode-time list growth that made this
    # slow (see read_wav_mono's as_arrays docstring), independent of this
    # one whole-array conversion before the call.
    dyn = dynamics_comparison(mix["samples"].tolist(), ref["samples"].tolist(), int(mix["sample_rate"]))
    if float(dyn.get("crest_delta_db", 0.0)) <= min_crest_delta_db:
        return None
    return dyn.get("suggested_settings")
