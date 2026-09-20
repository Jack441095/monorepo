from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Callable

from nite_core import AudioFeatureSet

from audio_analysis.analysis_core.transient_groove import (
    analyze_groove,
    analyze_transients,
    transient_preservation as _transient_preservation,
)
from audio_analysis.analysis_core.analysis_features import stereo_asymmetry as _stereo_asymmetry
from audio_analysis.analysis_core.loudness import loudness_range_by_section as _loudness_range_by_section
from audio_analysis.analysis_core.loudness import LUFS_DECIMATION_TRIGGER_SAMPLES

# Spectral/genre fingerprinting and LUFS (K-weighting's high-shelf boost
# centers well above 2kHz) both need to resolve most of the audible band
# (Nyquist >= 20kHz) to be accurate -- neither tolerates the heavy decimation
# read_wav_mono()'s default max_samples applies to any track long enough to
# trigger it (frame_count > max_samples, i.e. most real songs; one real
# 48kHz track measured an effective analysis_sample_rate as low as 226Hz).
# Reusing that coarse signal silently zeroed every log-band above ~200-500Hz
# and, separately, produced a 5 LU phantom LUFS error on a real render
# (measured -14.0 vs the render's own correct, never-decimated -9.01) --
# both fixed 2026-07-10 by re-reading at this rate whenever the default read
# falls below it. loudness.py's own same-named constant is a different,
# unrelated thing: a hard floor below which the K-weighting filter design
# itself is not mathematically valid, not a re-read-for-accuracy threshold.
MIN_SPECTRAL_SAMPLE_RATE = 40000


def _call_with_diagnostics(func: Callable, diagnostics: list[str], *args: object) -> None:
    try:
        return func(*args, diagnostics=diagnostics)
    except TypeError as exc:
        if "diagnostics" not in str(exc) and "unexpected keyword" not in str(exc):
            raise
        return func(*args)


@dataclass(frozen=True)
class AnalysisContext:
    ableton_repair_chain_export: Callable
    ableton_repair_templates: Callable
    advice_from_metrics: Callable
    analyze_spectrum_and_correlation: Callable
    annotate_flags: Callable
    band_ratios: Callable
    calculate_lufs: Callable
    calculate_true_peak: Callable
    closed_loop_action_plan: Callable
    decode_audio_bytes: Callable
    detect_chords_and_key: Callable
    dynamic_profile: Callable
    frequency_repair_map: Callable
    goal_target_checks: Callable
    leading_silence_seconds: Callable
    lesson_cards: Callable
    loudness_profile: Callable
    mix_goal_info: Callable
    perceptual_summary: Callable
    priority_actions: Callable
    rating_from_score: Callable
    read_wav_mono: Callable
    refresh_report_interpretation: Callable
    report_summary: Callable
    review_flags: Callable
    revision_lesson: Callable
    section_analysis: Callable
    source_hypotheses: Callable
    spectral_features: Callable
    spectrum_magnitudes: Callable
    ms_band_ratio: Callable
    stereo_correlation_timeline: Callable
    stereo_field_summary: Callable
    stereo_metrics: Callable
    technical_score: Callable
    tonal_balance_summary: Callable
    trailing_silence_seconds: Callable
    windowed_rms_values: Callable
    analyze_thd_n: Callable
    detect_resonances: Callable
    detect_isp: Callable


def analyze_wav(
    file_bytes: bytes, filename: str = "mix.wav", *, mix_goal: str, context: AnalysisContext,
    phon_level: float = 60.0, light: bool = False, include_bands: bool = True,
) -> dict:
    """light: skip every sub-analysis no current lightweight caller (the
    public podcast-check/delivery-check endpoints) reads -- chord/key,
    transient/groove, section analysis (+ per-section LRA), stereo
    asymmetry, THD/resonance/inter-sample-peak, the perceptual/tonal-
    balance spectral pass, and the entire report-interpretation tail
    (flags/advice/summary/ableton-repair/lesson-cards/etc). Returns
    ``{"ok": True, "metrics": metrics}`` only, not a full report -- only
    use this for a caller that reads specific `metrics` keys directly, the
    way podcast/delivery-check already do. Measured ~19-30% wall-time
    reduction on real tracks (see docs/audits -- this docstring doesn't
    duplicate the numbers so they can't drift out of sync with a re-measure).
    Default False is bit-identical to this function's pre-`light` behavior
    for every existing caller.

    include_bands: when light=True, whether to still pay for the high-
    fidelity spectral re-read to compute metrics["bands"] (needed by
    podcast-check, not by delivery-check). Ignored when light=False --
    bands are always computed there, as before.
    """
    diagnostics: list[str] = []
    goal = context.mix_goal_info(mix_goal)
    decoded_audio = context.decode_audio_bytes(file_bytes, filename)
    analysis_bytes = decoded_audio["wav_bytes"]
    data = context.read_wav_mono(analysis_bytes)
    samples = data["samples"]
    if not samples:
        raise ValueError("No audio samples found.")
    # Full-rate RMS (accumulated every frame in read_wav_mono, never gated by
    # the decimation `step`), not derived from the decimated/low-pass-smoothed
    # `samples` above -- that underestimates energy on any track long enough
    # to trigger decimation (frame_count > max_samples, i.e. most real songs),
    # which inflates crest_factor_db enough to flip a vintage/modern mastering
    # classification (measured 2026-07-10: 12.46dB decimated vs 10.31dB true
    # on a real commercial track).
    rms = float(data.get("true_rms") or 0.0) or math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    peak = max(float(data["peak"]), 1e-9)
    peak_db = 20 * math.log10(peak)
    rms_db = 20 * math.log10(max(rms, 1e-9))
    analysis_rate = float(data.get("analysis_sample_rate") or data["sample_rate"])
    window_values = context.windowed_rms_values(samples, analysis_rate)
    loudest_rms = max(window_values) if window_values else rms_db
    quietest_rms = min(window_values) if window_values else rms_db
    stereo = context.stereo_metrics(data["left_samples"], data["right_samples"])
    correlation_timeline = context.stereo_correlation_timeline(
        data["left_samples"], data["right_samples"], float(data["sample_rate"])
    )

    # Deliberately NOT converted to torch.Tensor: on this project's numpy 2.x /
    # torch 2.2 combination, tensor.numpy() raises (the same ABI break fixed for
    # KENN's retrieval via the ONNX embedder), which silently pushed every call
    # through a slower fallback and, for analyze_spectrum_and_correlation, a
    # *different and non-equivalent* torch.stft-based code path (measured
    # ~1.0 vs ~-0.02 band correlation for the same audio). Passing the plain
    # list/array through goes straight down the correct, faster numpy path.
    left_arr = data["left_samples"]
    right_arr = data["right_samples"]

    mid_bands, side_bands, correlation_bands = context.analyze_spectrum_and_correlation(
        left_arr, right_arr, int(data["sample_rate"])
    )

    # ITU-R BS.1770 K-weighting is defined over the full audible band (its
    # high-shelf boost centers well above 2kHz) -- measuring it from a signal
    # decimated below MIN_LUFS_SAMPLE_RATE's old 4000Hz floor (Nyquist 2kHz)
    # silently discards exactly the frequency range the filter cares most
    # about. Found 2026-07-10 on a real AutoMix render of treble-heavy
    # material (hats/claps/arpeggios): the render's own in-process LUFS
    # measurement (computed from the full-rate in-memory signal, never
    # decimated) read -9.01, matching its -9.0 target almost exactly: real
    # proof AutoMix's own DSP/gain-solve is correct. Re-analyzing the exact
    # same rendered audio through this decimated path read -14.0 -- a 5 LU
    # phantom error that was never in the audio, only in how this function
    # measured it. Raising the floor to the same MIN_SPECTRAL_SAMPLE_RATE
    # (40000Hz) used for the log_bands_40/raw_bands fix earlier tonight
    # fixed it exactly (verified: -9.01 at a 4,000,000-sample budget, same
    # cap already established for that fix).
    lufs_left = left_arr
    lufs_right = right_arr
    lufs_rate = int(data["analysis_sample_rate"])
    if lufs_rate < MIN_SPECTRAL_SAMPLE_RATE and float(data.get("duration_seconds") or 0) > 0:
        # Cap matches calculate_lufs_numpy's own LUFS_DECIMATION_TRIGGER_SAMPLES
        # (loudness.py), not the smaller 4,000,000 used for the spectral-
        # fingerprint re-read above. Found 2026-07-10 on a real 3.5min track:
        # a 4,000,000-sample cap (enough for the 80s track the original fix
        # was verified against) only bought ~19kHz effective rate here --
        # still lossy enough for a real 2.63 LU error. Re-reading up to the
        # same ceiling calculate_lufs_numpy itself won't decimate past keeps
        # the two functions' accuracy consistent for any real song length.
        lufs_sample_budget = min(
            LUFS_DECIMATION_TRIGGER_SAMPLES,
            max(200_000, int(float(data["duration_seconds"]) * MIN_SPECTRAL_SAMPLE_RATE)),
        )
        # as_arrays=True: lufs_left/lufs_right feed calculate_lufs,
        # loudness_profile, AND loudness_range_by_section below, each of
        # which independently np.asarray()'d the same underlying list at
        # its own entry point -- measured ~1.1s of a ~4s analyze_wav() call
        # on a real 205s track was exactly this redundant conversion.
        # read_wav_mono's own as_arrays path already returns bit-identical
        # values to the list path (existing, pre-tested machinery -- see
        # its docstring), and degrades to lists automatically when numpy
        # is unavailable (NUMPY_AVAILABLE-gated), so this changes nothing
        # about output, only how the data is threaded.
        lufs_data = context.read_wav_mono(analysis_bytes, max_samples=lufs_sample_budget, as_arrays=True)
        lufs_left = lufs_data["left_samples"]
        lufs_right = lufs_data["right_samples"]
        lufs_rate = int(lufs_data["analysis_sample_rate"])
    integrated_lufs = _call_with_diagnostics(context.calculate_lufs, diagnostics, lufs_left, lufs_right, lufs_rate)
    true_peak = _call_with_diagnostics(context.calculate_true_peak, diagnostics, left_arr, right_arr, int(data["sample_rate"]), analysis_bytes)
    lp = _call_with_diagnostics(context.loudness_profile, diagnostics, lufs_left, lufs_right, lufs_rate)
    if not isinstance(lp, dict):
        lp = {"integrated_lufs": -99.0, "momentary_max_lufs": -99.0, "short_term_max_lufs": -99.0, "loudness_range_lu": 0.0}

    # spectrum_magnitudes(samples, analysis_rate) used to be computed here too,
    # but nothing downstream ever read it (the hi-res re-read below always
    # supersedes it for every real consumer) -- confirmed dead, deleted
    # rather than kept as an unused call every caller paid for.

    raw_bands: dict = {}
    ear_bands: dict = {}
    spectrum_features: dict = {}
    tonal_balance: dict = {}
    if not light or include_bands:
        # High-fidelity re-read for band-ratio metrics that need real bandwidth
        # (Nyquist >= 20kHz) to be meaningful -- NOT the coarse `samples`/
        # `analysis_rate` above, which get decimated on any track long enough to
        # trigger it (frame_count > max_samples, i.e. most real songs) and
        # silently zero out every band above ~200-500Hz. Found 2026-07-10: every
        # real commercial track tested came back with a "dark"/near-zero air
        # (8-16kHz) share regardless of the actual master, because that band was
        # being measured from a signal whose real Nyquist was ~200-450Hz.
        spectral_samples, spectral_rate = samples, analysis_rate
        if analysis_rate < MIN_SPECTRAL_SAMPLE_RATE and float(data.get("duration_seconds") or 0) > 0:
            spectral_sample_budget = min(
                4_000_000,
                max(200_000, int(float(data["duration_seconds"]) * MIN_SPECTRAL_SAMPLE_RATE)),
            )
            spectral_data = context.read_wav_mono(analysis_bytes, max_samples=spectral_sample_budget)
            spectral_samples = spectral_data["samples"]
            spectral_rate = float(spectral_data.get("analysis_sample_rate") or spectral_data["sample_rate"])
        hires_magnitudes, hires_spectrum_n = context.spectrum_magnitudes(spectral_samples, int(spectral_rate))
        raw_bands = context.band_ratios(hires_magnitudes, int(spectral_rate), hires_spectrum_n)
    if not light:
        ear_bands = context.band_ratios(hires_magnitudes, int(spectral_rate), hires_spectrum_n, perceptual=True, phon_level=phon_level)
        # Use the SAME high-fidelity spectrum as the band ratios above -- not the
        # decimated `magnitudes`/`analysis_rate`, whose Nyquist collapses to a few
        # hundred Hz on any track long enough to trigger read_wav_mono's decimation
        # (i.e. most real songs). Measured 2026-07-23 on a real 205s AutoMix render:
        # the decimated path reported spectral_centroid = 84 Hz for a mix that is
        # actually ~72% high-frequency energy (true centroid several kHz). This was
        # the one metric the 2026-07-10 decimation fix missed -- centroid_hz,
        # rolloff_85_hz and high_frequency_share were all still read off the coarse
        # signal, and perceptual_summary's centroid<250 / centroid>3500 branches
        # misfired accordingly.
        spectrum_features = context.spectral_features(hires_magnitudes, int(spectral_rate), hires_spectrum_n)
        tonal_balance = context.tonal_balance_summary(raw_bands, ear_bands, spectrum_features)

    # log_band_ratios_track_average is only used below (log_bands_40), which
    # `light` mode also skips -- import stays local to keep it lazy either way.
    from audio_analysis.analysis_core.dsp_metrics import log_band_ratios_track_average

    dynamics: dict = {}
    transient_analysis: dict = {}
    groove_analysis: dict = {}
    sections: dict = {}
    stereo_asymmetry_metrics: dict = {}
    lra_by_section: list = []
    chords: dict = {}
    thd_data = {"thd": 0.0, "even_thd": 0.0, "odd_thd": 0.0, "thd_n": 0.0, "fundamental_hz": 0.0}
    resonances: list = []
    isp_max = 0.0
    if not light:
        dynamics = context.dynamic_profile(samples, analysis_rate, peak_db, rms_db, window_values)
        transient_analysis = analyze_transients(
            samples,
            int(analysis_rate),
            crest_factor_db=peak_db - rms_db,
            target=str(goal.get("key") or "premaster"),
        )
        groove_analysis = analyze_groove(samples, int(analysis_rate))
        sections = context.section_analysis(data["samples"], data["left_samples"], data["right_samples"], analysis_rate)

        # Stage 10 metrics: real L/R imbalance (distinct from correlation/width)
        # and per-section LRA (loudness range measured within each structural
        # section rather than only across the whole track). Both are pure,
        # deterministic DSP functions and are computed directly rather than via
        # AnalysisContext injection since they have no alternate backend/decoder
        # concerns the way LUFS/true-peak do.
        try:
            stereo_asymmetry_metrics = _stereo_asymmetry(data["left_samples"], data["right_samples"], analysis_rate)
        except Exception as exc:
            diagnostics.append(f"Stereo asymmetry computation failed ({exc.__class__.__name__}); skipped.")
            stereo_asymmetry_metrics = {}
        try:
            lra_by_section = _loudness_range_by_section(
                lufs_left, lufs_right, lufs_rate, sections.get("sections") or []
            )
        except Exception as exc:
            diagnostics.append(f"Per-section LRA computation failed ({exc.__class__.__name__}); skipped.")
            lra_by_section = []

        chords = context.detect_chords_and_key(samples, analysis_rate)

    perceptual_summary: dict = {}
    if not light:
        import numpy as np
        samples_np = np.array(samples, dtype=np.float32)
        thd_data = _call_with_diagnostics(context.analyze_thd_n, diagnostics, samples_np, int(analysis_rate))
        if not isinstance(thd_data, dict):
            thd_data = {"thd": 0.0, "even_thd": 0.0, "odd_thd": 0.0, "thd_n": 0.0, "fundamental_hz": 0.0}
        resonances = _call_with_diagnostics(context.detect_resonances, diagnostics, samples_np, int(analysis_rate))
        if not isinstance(resonances, list):
            resonances = []
        isp_results = _call_with_diagnostics(context.detect_isp, diagnostics, samples_np)
        if isinstance(isp_results, tuple) and len(isp_results) == 2:
            _, isp_max = isp_results
        else:
            isp_max = 0.0
        perceptual_summary = context.perceptual_summary(ear_bands, phon_level=phon_level)

    metrics = {
        "filename": filename,
        "source_format": decoded_audio.get("source_format", "wav"),
        "decoder": decoded_audio.get("decoder", "wave"),
        "mix_goal": goal,
        "phon_level": phon_level,
        "duration_seconds": round(float(data["duration_seconds"]), 2),
        "sample_rate": data["sample_rate"],
        "channels": data["channels"],
        "peak_dbfs": round(peak_db, 2),
        "left_peak_dbfs": round(20 * math.log10(max(float(data["left_peak"]), 1e-9)), 2),
        "right_peak_dbfs": round(20 * math.log10(max(float(data["right_peak"]), 1e-9)), 2),
        "rms_dbfs_estimate": round(rms_db, 2),
        "loudest_section_rms_dbfs": round(loudest_rms, 2),
        "dynamic_range_estimate_db": round(loudest_rms - quietest_rms, 2),
        "crest_factor_db": round(peak_db - rms_db, 2),
        "dc_offset": round(sum(samples) / len(samples), 5),
        "leading_silence_seconds": context.leading_silence_seconds(samples, analysis_rate),
        "trailing_silence_seconds": context.trailing_silence_seconds(samples, analysis_rate),
        "clipped_frames_estimate": data["clipped_frames_estimate"],
        "clipping_risk": int(data["clipped_frames_estimate"]) > 0 or true_peak > -0.1,
        "stereo_balance": data["stereo_balance"],
        "integrated_lufs": round(integrated_lufs, 2) if integrated_lufs != -99.0 else "n/a",
        "momentary_max_lufs": lp.get("momentary_max_lufs", -99.0),
        "short_term_max_lufs": lp.get("short_term_max_lufs", -99.0),
        "loudness_range_lu": lp.get("loudness_range_lu", 0.0),
        "true_peak_dbfs": round(true_peak, 2),
        "mid_bands": mid_bands,
        "side_bands": side_bands,
        "correlation_bands": correlation_bands,
        "ms_band_ratio": context.ms_band_ratio(mid_bands, side_bands),
        "correlation_timeline": correlation_timeline,
        **stereo,
        "bands": raw_bands,
        "perceptual_bands": ear_bands,
        "perceptual_summary": perceptual_summary,
        "spectral_features": spectrum_features,
        "tonal_balance": tonal_balance,
        "dynamic_profile": dynamics,
        "transient_analysis": transient_analysis,
        "groove_analysis": groove_analysis,
        "section_analysis": sections,
        "stereo_asymmetry": stereo_asymmetry_metrics,
        "loudness_range_by_section": lra_by_section,
        "chords": chords,
        "distortion_thd": thd_data.get("thd", 0.0),
        "distortion_even_thd": thd_data.get("even_thd", 0.0),
        "distortion_odd_thd": thd_data.get("odd_thd", 0.0),
        "distortion_thd_n": thd_data.get("thd_n", 0.0),
        "distortion_fundamental_hz": thd_data.get("fundamental_hz", 0.0),
        "resonances": resonances,
        "inter_sample_peak_dbfs": round(20 * math.log10(max(isp_max, 1e-9)), 2),
    }
    # This compact record is the stable, provenance-bound counterpart to the
    # richer report below. Keep its values scalar and JSON-safe so it can be
    # cached, compared, or handed to KENN without treating advice as a raw
    # measurement.
    feature_measurements = {
        key: metrics[key]
        for key in (
            "peak_dbfs", "rms_dbfs_estimate", "crest_factor_db", "integrated_lufs",
            "true_peak_dbfs", "loudness_range_lu", "clipped_frames_estimate",
        )
        if key in metrics
    }
    feature_set = AudioFeatureSet(
        source_hash="sha256:" + hashlib.sha256(file_bytes).hexdigest(),
        sample_rate=int(data["sample_rate"]),
        channels=int(data["channels"]),
        duration_seconds=float(data["duration_seconds"]),
        measurements=feature_measurements,
        analysis_profile="mix_review.light.v1" if light else "mix_review.full.v1",
        producer="audio-analysis",
        diagnostics=tuple(str(item) for item in diagnostics),
    ).to_dict()
    if light:
        # log_bands_40 and the whole report-interpretation tail below (flags/
        # advice/summary/ableton-repair/lesson-cards/source-hypotheses/
        # frequency-repair-map/revision-lesson/closed-loop-action-plan) are
        # never read by a light caller -- also true of log_bands_40's only
        # consumer, genre/reference-track matching. Return metrics only.
        metrics["analysis_diagnostics"] = diagnostics
        return {"ok": True, "metrics": metrics, "feature_set": feature_set}
    # Track-averaged, not a single mid-track window: genre/reference-track
    # matching (the only consumer of log_bands_40) needs a whole-song
    # fingerprint, not one ~93ms snapshot that can land on a quiet bridge or
    # breakdown and look nothing like the song overall. Reuses the same
    # high-fidelity `spectral_samples`/`spectral_rate` re-read computed above
    # for raw_bands/ear_bands -- one re-read serves both fixes.
    metrics["log_bands_40"] = log_band_ratios_track_average(spectral_samples, int(spectral_rate))
    metrics["analysis_diagnostics"] = diagnostics
    metrics["stereo_field"] = context.stereo_field_summary(metrics)
    metrics["goal_target_checks"] = context.goal_target_checks(metrics, phon_level=phon_level)
    flags = context.annotate_flags(context.review_flags(metrics))
    score = context.technical_score(flags)
    metrics["technical_score"] = score
    metrics["technical_rating"] = context.rating_from_score(score)
    actions = context.priority_actions(metrics, flags)
    advice = context.advice_from_metrics(metrics, flags, phon_level=phon_level)
    summary = context.report_summary(metrics, flags)
    report = {
        "ok": True,
        "metrics": metrics,
        "feature_set": feature_set,
        "flags": flags,
        "summary": summary,
        "action_plan": actions,
        "advice": advice,
        "disclaimer": "First-pass technical analysis only. Use references and human listening for final mix decisions.",
        "analysis_diagnostics": diagnostics,
    }
    context.refresh_report_interpretation(report)
    report["ableton_repair_templates"] = context.ableton_repair_templates(flags, metrics)
    report["ableton_repair_chains"] = context.ableton_repair_chain_export(report)
    report["lesson_cards"] = context.lesson_cards(flags, goal)
    report["source_hypotheses"] = context.source_hypotheses(metrics, flags)
    report["frequency_repair_map"] = context.frequency_repair_map(metrics, flags, phon_level=phon_level)
    report["revision_lesson"] = context.revision_lesson(report)
    report["closed_loop_action_plan"] = context.closed_loop_action_plan(report)
    return report


def compare_transient_preservation(
    pre_samples: list[float],
    post_samples: list[float],
    sample_rate: int,
) -> dict:
    """Stage 10 metric: compare transient sharpness across a processing chain.

    Unlike the single-file metrics in :func:`analyze_wav`, transient
    preservation is inherently a *comparison* between two renders of the
    same material (e.g. pre-limiter vs. post-limiter, or pre-master vs.
    final master) — there is no meaningful "transient preservation" value
    for a single file in isolation. Callers pass mono or interleaved-mono
    (already down-mixed) sample lists for the "pre" and "post" renders;
    see :func:`audio_analysis.analysis_core.transient_groove.transient_preservation`
    for the full scoring methodology.
    """
    return _transient_preservation(pre_samples, post_samples, sample_rate)


def stem_frequency_masking(stems: list[dict], *, read_wav_mono: Callable | None = None) -> dict:
    """Stage 10 metric: frequency-band isolation/masking detection between stems.

    Thin wrapper around the existing ERB-based masking engine in
    :mod:`audio_analysis.mixdown.stem_analysis` (``analyze_stems_masking``),
    which already computes per-stem band energy, a pairwise masking-index
    matrix, per-band simultaneous-masking visibility (via ERB critical
    bands and an absolute-threshold-of-hearing model), and EQ-carving
    suggestions. Reused here rather than reimplemented, per this module's
    convention of composing existing DSP primitives.

    ``stems`` is a list of ``{"name": str, "file_bytes": bytes}`` dicts.
    Returns ``{"ok": False, "reason": ...}`` when fewer than two stems are
    supplied (masking is undefined for a single stem).
    """
    if not stems or len(stems) < 2:
        return {"ok": False, "reason": "At least two stems are required to detect masking between them.", "stems": stems or []}
    from audio_analysis.mixdown.stem_analysis import analyze_stems_masking
    from audio_analysis.analysis_core.dsp_metrics import spectral_bands
    from audio_analysis.utils.audio_io_api import read_wav_mono as default_read_wav_mono

    reader = read_wav_mono or default_read_wav_mono
    result = analyze_stems_masking(stems, read_wav_mono=reader, spectral_bands=spectral_bands)
    result["ok"] = True
    return result
