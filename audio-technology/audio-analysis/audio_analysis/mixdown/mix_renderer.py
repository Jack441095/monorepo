"""Mix summing and rendering engine for automated mixdown system.

Applies stem-level DSP configs (EQ, compression, gate, panning, auxiliary sends),
sums stems to a stereo bus, applies master bus processing (width, saturation, glue compression),
measures intermediate LUFS to compute target gain, and renders the final limited stereo WAV output.
"""

from __future__ import annotations

import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import scipy.signal as sig

# 10**(x/20) == exp(x * _LN10_OVER_20) -- mathematically identical dB->linear
# conversion, but numpy's array power ufunc is a general pow() (handles
# arbitrary/negative/fractional exponents) while exp() is a dedicated fast
# path -- ~3-4x faster on full-track arrays (measured on the compressor gain
# envelope, one of the largest single costs in the per-stem chain). Differs
# from ** by ~1e-16 relative (float64 ULP noise), far below the 24-bit dither
# floor (~1e-7) and the golden-metrics regression guard's 1e-9 abs tolerance.
_LN10_OVER_20 = math.log(10.0) / 20.0

logger = logging.getLogger(__name__)


def _render_worker_count(n_stems: int) -> int:
    """Threads for per-stem processing. Default min(4, cores, stems) -- 4 matches
    typical performance-core counts and the measured per-stem speedup plateau.
    Override with env AUTOMIX_RENDER_WORKERS (set =1 to force the sequential path)."""
    env = os.environ.get("AUTOMIX_RENDER_WORKERS")
    if env:
        try:
            return max(1, min(int(env), max(1, n_stems)))
        except ValueError:
            pass
    return max(1, min(4, os.cpu_count() or 1, max(1, n_stems)))


from ..dsp_engine import (
    ParametricEQ,
    Compressor,
    Gate,
    Limiter,
    Reverb,
    Delay,
    apply_gain,
    apply_pan,
    apply_stereo_width,
    mono_below_frequency,
    apply_saturation,
    apply_dynamic_eq_bands,
)
from ..analysis_core.resonance_detection import detect_resonant_bands
from ..dsp_engine.dynamics import _smooth_attack_release
from .mix_decision_engine import MixPlan, BusMixConfig
from ..dsp_engine.dither import apply_noise_shaped_dither
from ..analysis_core.loudness import calculate_loudness_profile, calculate_true_peak  # Existing loudness measurement modules
from .stem_prep import write_wav        # Existing WAV writer


# Per-role fundamental-protection floor for the resonance detector. A narrow,
# persistent, prominent low peak on these roles is the instrument's body, not a
# resonance — cutting it weakens the low end (calibrated 2026-07-16 against real
# stems; a reggueton kick's own 99 Hz was being flagged). Low-bass roles protect
# their whole fundamental region; other roles protect only deep sub rumble so
# legitimate 200-500 Hz boxiness on vocals/keys stays correctable.
_LOW_FUNDAMENTAL_ROLES = frozenset({"kick", "bass", "sub_bass", "full_drum_bus"})
_FUNDAMENTAL_FLOOR_LOW_HZ = 150.0
_FUNDAMENTAL_FLOOR_DEFAULT_HZ = 60.0


def _resonance_protect_floor_hz(instrument: str | None) -> float:
    """Frequency below which the resonance detector must not flag a band, by role."""
    if instrument in _LOW_FUNDAMENTAL_ROLES:
        return _FUNDAMENTAL_FLOOR_LOW_HZ
    return _FUNDAMENTAL_FLOOR_DEFAULT_HZ


# Global budget on how many masking de-mask moves a single render may apply, so a
# song with dozens of relationships doesn't get processed everywhere at once —
# same precision-first philosophy as the resonance detector's simultaneous-band
# cap and the automation-preview move budget.
_MAX_MASKING_MOVES_PER_SONG = 8


def _stem_basename(name: str) -> str:
    """Normalize a stem name to basename-without-extension for cross-matching
    renderer stem names against relationship engine target_stem values."""
    base = name.rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base else base


def _masking_moves_by_target(relationships: list[dict]) -> dict[str, dict]:
    """Extract actionable dynamic-EQ de-mask moves from plan relationships,
    keyed by normalized target-stem basename.

    Only ``dynamic_eq`` candidates on relationships the engine already marked
    actionable (status ``candidate``) are eligible — ``review_required`` and
    ``existing_treatment_detected`` are skipped, exactly as the engine intends.
    Dynamic EQ is chosen (over static EQ / sidechain / automation) as the first
    wired correction because it is the most surgical and self-limiting: it only
    reduces the overlap band while that band is actually excessive. Ranked by
    candidate score, capped globally at ``_MAX_MASKING_MOVES_PER_SONG``.
    """
    scored: list[tuple[float, str, dict]] = []
    for rel in relationships or []:
        if rel.get("status") != "candidate":
            continue
        target = rel.get("intervention_target")
        if not target:
            continue
        for cand in rel.get("candidate_strategies", []) or []:
            if cand.get("strategy") != "dynamic_eq":
                continue
            params = cand.get("parameters", {}) or {}
            freq = params.get("frequency_hz")
            if not freq:
                continue
            move = {
                "relationship_id": rel.get("relationship_id"),
                "candidate_id": cand.get("candidate_id"),
                "target_stem": target,
                "frequency_hz": float(freq),
                "max_reduction_db": float(params.get("max_reduction_db", 3.0)),
                "q": float(params.get("q", 1.2)),
                "attack_ms": float(params.get("attack_ms", 20.0)),
                "release_ms": float(params.get("release_ms", 140.0)),
                "score": float(cand.get("score", 0.0)),
            }
            scored.append((move["score"], _stem_basename(target), move))

    scored.sort(key=lambda item: -item[0])
    moves_by_target: dict[str, dict] = {}
    applied = 0
    for _score, target_base, move in scored:
        if applied >= _MAX_MASKING_MOVES_PER_SONG:
            break
        # One dynamic-EQ de-mask move per target stem (the highest-scored).
        if target_base in moves_by_target:
            continue
        moves_by_target[target_base] = move
        applied += 1
    return moves_by_target


# Bounded additional narrowing applied on top of whatever stereo_width the
# decision engine already chose, keyed by mono-compat severity. Floored so a
# flagged stem is narrowed, never fully collapsed to mono -- that would erase
# the element's character (e.g. hi-hat "air") rather than just tame the fold-
# down/phase risk. Calibrated conservatively; see docs/audits/
# 2026-07-17-stranger-v6-listening-findings.md for the ear-confirmed case
# this targets (source-material decorrelation, not a pipeline bug).
_MONO_COMPAT_CORRECTION_FACTOR = {"warning": 0.6, "critical": 0.35}


def _mono_compat_severity_by_stem(mono_compatibility: dict | None) -> dict[str, str]:
    """Normalized-basename -> worst severity ('warning'/'critical') for stems
    the mono-compatibility detector flagged. 'pass'/'not_applicable' stems and
    stems with no measurement are omitted (nothing to correct)."""
    if not mono_compatibility:
        return {}
    out: dict[str, str] = {}
    for stem in mono_compatibility.get("stems", []) or []:
        severity = stem.get("severity")
        if severity not in ("warning", "critical"):
            continue
        name = stem.get("stem_name")
        if not name:
            continue
        out[_stem_basename(name)] = severity
    return out


def _apply_stereo_compressor(
    left: np.ndarray,
    right: np.ndarray,
    comp_config: dict,
    sample_rate: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply stereo-linked compression to preserve the stereo image."""
    fs = float(sample_rate)
    ratio = comp_config["ratio"]
    attack_ms = comp_config["attack_ms"]
    release_ms = comp_config["release_ms"]
    threshold_db = comp_config["threshold_db"]

    # Sidechain detector: max of absolute left and right channels
    sc_max = np.maximum(np.abs(left), np.abs(right))
    sc_db = 20.0 * np.log10(np.maximum(sc_max, 1e-12))

    # Static compression curve (hard knee)
    gr_db = np.zeros_like(sc_db)
    above_thresh = sc_db > threshold_db
    if np.any(above_thresh):
        gr_db[above_thresh] = (threshold_db - sc_db[above_thresh]) * (1.0 - 1.0 / ratio)

    # Temporal smoothing
    alpha_att = np.exp(-1.0 / (fs * (attack_ms / 1000.0)))
    alpha_rel = np.exp(-1.0 / (fs * (release_ms / 1000.0)))

    # State-dependent one-pole smoothing (attack when gain reduction deepens,
    # i.e. target < current), numba-accelerated with a pure-Python fallback via
    # the shared dynamics helper — same recursion this loop used to inline, now
    # ~38x faster on full-length stems. Runs on every stem plus 3x per master
    # multiband call, so it was one of the largest per-render costs.
    smoothed_gr = _smooth_attack_release(
        np.ascontiguousarray(gr_db, dtype=np.float64),
        float(alpha_att), float(alpha_rel), 0.0, True,
    )

    gain = np.exp(smoothed_gr * _LN10_OVER_20)
    return left * gain, right * gain


# Internal safety headroom (Stage 7 follow-up, 2026-07-09): the limiter's
# true-peak ceiling targeting is itself an approximation (stereo-linked
# gain computed from a mono max(|L|,|R|) envelope, downsampled from a 4x
# oversampled per-block minimum) and can land ~0.1-0.2 dB over the requested
# ceiling on some signals even though the math is internally consistent —
# found via a real, deterministic ceiling violation (-0.848 dBTP against a
# -1.0 dBTP ceiling) that persisted unchanged across a wide range of input
# gains, proving it's a limiter-precision issue, not a gain-staging one.
# Standard mastering practice is to never target the ceiling exactly for
# exactly this reason; targeting slightly under it here closes the gap at
# the source rather than trying to compensate for it with gain changes
# that don't actually move the true peak.
_LIMITER_CEILING_HEADROOM_DB = 0.3


def _apply_stereo_limiter(
    left: np.ndarray,
    right: np.ndarray,
    ceiling_db: float,
    threshold_db: float,
    sample_rate: int,
    release_ms: float = 50.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply stereo-linked brickwall limiting to prevent stereo shift."""
    lim = Limiter(
        sample_rate=sample_rate,
        ceiling_db=ceiling_db - _LIMITER_CEILING_HEADROOM_DB,
        threshold_db=threshold_db,
        release_ms=release_ms,
        lookahead_ms=5.0,
        true_peak=True,  # Match professional true peak requirements
    )

    # Run the limiter on the stereo-linked maximum envelope and take the exact
    # gain (makeup + true-peak reduction) and look-ahead delay it applied, then
    # reproduce them identically on both channels. This holds the ceiling: at a
    # limited peak the gain is ceiling / (peak * makeup), so the boosted output
    # lands exactly at the ceiling. The previous version divided the delayed,
    # boosted limiter output by the undelayed input and clamped to 1.0, which
    # discarded the makeup gain and left peaks at makeup × ceiling (overshoot).
    x_max = np.maximum(np.abs(left), np.abs(right))
    _, total_gain, delay = lim.apply(x_max, return_gain=True)

    out_l = np.zeros_like(left)
    out_r = np.zeros_like(right)
    if delay > 0:
        out_l[delay:] = left[:-delay] * total_gain[delay:]
        out_r[delay:] = right[:-delay] * total_gain[delay:]
        out_l[:delay] = left[:delay] * total_gain[:delay]
        out_r[:delay] = right[:delay] * total_gain[:delay]
    else:
        out_l = left * total_gain
        out_r = right * total_gain

    return out_l, out_r


def _apply_multiband_compressor(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
    multiband_config: dict | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Split the stereo signal into 3 bands and apply independent stereo compression to each."""
    m_cfg = multiband_config or {}
    low_cross_hz = float(m_cfg.get("low_crossover_hz", 200.0))
    high_cross_hz = float(m_cfg.get("high_crossover_hz", 5000.0))
    default_mid_ratio = float(m_cfg.get("mid_ratio", 1.8))

    import os
    _mid_ratio_override = os.environ.get("AUTOMIX_DEBUG_MIDBAND_RATIO")
    mid_ratio = float(_mid_ratio_override) if _mid_ratio_override else default_mid_ratio

    nyq = 0.5 * sample_rate
    
    # Low Crossover
    b_low, a_low = sig.butter(4, low_cross_hz / nyq, btype="low")
    b_mid_h, a_mid_h = sig.butter(4, low_cross_hz / nyq, btype="high")
    
    # High Crossover
    b_mid_l, a_mid_l = sig.butter(4, high_cross_hz / nyq, btype="low")
    b_high, a_high = sig.butter(4, high_cross_hz / nyq, btype="high")
    
    # Filter Left
    l_low = sig.filtfilt(b_low, a_low, left)
    l_mid = sig.filtfilt(b_mid_l, a_mid_l, sig.filtfilt(b_mid_h, a_mid_h, left))
    l_high = sig.filtfilt(b_high, a_high, left)
    
    # Filter Right
    r_low = sig.filtfilt(b_low, a_low, right)
    r_mid = sig.filtfilt(b_mid_l, a_mid_l, sig.filtfilt(b_mid_h, a_mid_h, right))
    r_high = sig.filtfilt(b_high, a_high, right)
    
    # Apply compression on each band
    l_low, r_low = _apply_stereo_compressor(
        l_low, r_low,
        {"ratio": 2.5, "attack_ms": 50.0, "release_ms": 200.0, "threshold_db": -18.0},
        sample_rate
    )
    
    l_mid, r_mid = _apply_stereo_compressor(
        l_mid, r_mid,
        {"ratio": mid_ratio, "attack_ms": 30.0, "release_ms": 150.0, "threshold_db": -15.0},
        sample_rate
    )
    
    l_high, r_high = _apply_stereo_compressor(
        l_high, r_high,
        {"ratio": 1.5, "attack_ms": 20.0, "release_ms": 100.0, "threshold_db": -12.0},
        sample_rate
    )
    
    return l_low + l_mid + l_high, r_low + r_mid + r_high


def _apply_ms_stereo_enhancer(
    left: np.ndarray,
    right: np.ndarray,
    width_factor: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Enhance or narrow stereo image via Mid/Side gain scaling."""
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)

    # Scale side channel to widen/narrow the image
    side_enhanced = side * width_factor

    return mid + side_enhanced, mid - side_enhanced


# --- Stage A follow-up (2026-07-09): verified fixes for the two genre-matrix
# cases (edm, jazz) that a blind, unverified crest-factor-compression attempt
# earlier tonight made WORSE (see docs/AUDIO_MVP_MASTER_PLAN.md Stage A — that
# attempt shipped a single fixed-ratio pre-limiter compressor with no
# measurement of what it actually achieved, and EDM regressed from -1.42 LU to
# -8.99 LU off target). Everything below measures its own real effect
# (crest factor, reachable LUFS, real true-peak) before deciding to keep it,
# exactly mirroring the pattern the closed-loop gain solve above already uses.


def _measure_crest_factor_db(left: np.ndarray, right: np.ndarray) -> float:
    x = np.maximum(np.abs(left), np.abs(right))
    peak = float(np.max(x)) if x.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
    peak_db = 20.0 * np.log10(max(peak, 1e-12))
    rms_db = 20.0 * np.log10(max(rms, 1e-12))
    return peak_db - rms_db


def _apply_peak_catching_prelimiter(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
    pre_ceiling_db: float,
    release_ms: float,
) -> tuple[np.ndarray, np.ndarray]:
    """A fast, look-ahead, true-peak-aware limiter used as a pre-stage to
    genuinely shave transient peaks (real crest-factor reduction) before the
    final brickwall limiter, rather than an RMS-following compressor.

    2026-07-09 diagnostic (see AUDIO_MVP_MASTER_PLAN.md Stage A follow-up)
    found that RMS-following compressors — whether wideband or per-band, fixed
    threshold or RMS-adaptive threshold — systematically FAIL on short,
    fast-transient material (e.g. EDM kick drums): a typical attack time
    (10-50ms) is slower than the transient itself, so the transient largely
    escapes gain reduction while the surrounding sustained material (which
    stays above threshold the whole time) gets pulled down — the net effect
    INCREASES crest factor rather than reducing it. A look-ahead, peak-catching
    limiter (like the final master limiter, just at a higher intermediate
    ceiling) doesn't have this problem: it always catches the transient
    because look-ahead means the gain reduction is applied non-causally,
    exactly at the sample that needs it.

    Deliberately keeps `release_ms` >= ~5ms (never as fast as ~1ms): the same
    diagnostic found that release times faster than ~2ms can make the *output*
    of this stage change so quickly that a downstream true-peak limiter's own
    4x-oversampling (`scipy.signal.resample_poly`, an FIR-based polyphase
    resampler) rings on the near-step edges and produces NEW inter-sample
    peaks that exceed the safety margin -- a real, measured true-peak
    violation, not just a theoretical concern. This is a DSP quality bound,
    not a tuning knob to push further for more loudness.
    """
    lim = Limiter(
        sample_rate=sample_rate,
        ceiling_db=pre_ceiling_db,
        threshold_db=0.0,
        release_ms=release_ms,
        lookahead_ms=5.0,
        true_peak=True,
    )
    x_max = np.maximum(np.abs(left), np.abs(right))
    _, total_gain, delay = lim.apply(x_max, return_gain=True)

    out_l = np.zeros_like(left)
    out_r = np.zeros_like(right)
    if delay > 0:
        out_l[delay:] = left[:-delay] * total_gain[delay:]
        out_r[delay:] = right[:-delay] * total_gain[delay:]
        out_l[:delay] = left[:delay] * total_gain[:delay]
        out_r[:delay] = right[:delay] * total_gain[:delay]
    else:
        out_l = left * total_gain
        out_r = right * total_gain
    return out_l, out_r


def _probe_reachable_lufs(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
    ceiling_db_for_limiter: float,
    limiter_release_ms: float = 50.0,
) -> float:
    """Measure how loud this material can ACTUALLY get once brickwalled at
    `ceiling_db_for_limiter`: drives `_apply_stereo_limiter` with a large,
    fixed makeup gain so the output is pinned at the ceiling almost
    everywhere, then measures the REAL resulting integrated LUFS. This is the
    same "apply, then measure the real result" pattern the closed-loop gain
    solve below uses for its own convergence, applied here to answer a
    different question up front: is this material's dynamics even CAPABLE of
    reaching the target loudness at this ceiling, before spending gain-solve
    iterations trying?
    """
    probe_l, probe_r = _apply_stereo_limiter(
        left, right, ceiling_db=ceiling_db_for_limiter, threshold_db=-24.0,
        sample_rate=sample_rate, release_ms=limiter_release_ms,
    )
    try:
        profile = calculate_loudness_profile(probe_l, probe_r, sample_rate)
        return float(profile.get("integrated_lufs", -60.0))
    except Exception:
        # Same failure mode as the pre-limiter measurement below (the
        # 2026-07-08 LUFS-accuracy bug) -- this probe's -60.0 fallback feeds
        # directly into the "is this material capable of reaching target
        # loudness" decision, so a silent measurement failure must be
        # observable, not just guessed away.
        logger.warning(
            "calculate_loudness_profile failed in reachability probe; "
            "reporting -60 LUFS reachable-loudness guess", exc_info=True,
        )
        return -60.0


def _calibrate_limiter_headroom_db(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
    ceiling_db: float,
    limiter_release_ms: float = 50.0,
) -> float:
    """Per-render, measured (not guessed) correction for `_apply_stereo_limiter`'s
    own true-peak-estimation error.

    `_apply_stereo_limiter` computes its gain from a stereo-linked
    max(|L|,|R|) envelope and a limiter-internal 4x-oversampled true-peak
    estimate — an approximation the existing `_LIMITER_CEILING_HEADROOM_DB`
    constant (0.3 dB) already compensates for on typical material (~0.1-0.2 dB
    real-world error, per that constant's own comment). 2026-07-09 diagnostic
    on the jazz genre-matrix case (21.3 dB crest factor, independently-timed
    transients between channels) found this approximation error can be much
    larger — up to ~0.66 dB — on wide-crest-factor, transient-heavy stereo
    material, which was large enough that the closed-loop gain solve's
    per-candidate true-peak safety check (correctly) rejected nearly every
    useful candidate and collapsed to a far-too-conservative fallback gain
    (measured -21.0 LUFS against a -15.0 target).

    Rather than raise the fixed headroom constant globally (which would cost
    achievable loudness on material that doesn't need it), measure the actual
    error once per render with a single hard-limited probe pass and fold
    exactly that measured error (plus a small buffer) into the ceiling used
    for the rest of this render's limiter calls. Material with no real error
    gets ~0 dB of extra headroom (no behavior change); material with a large
    error gets exactly enough correction to stop the closed loop from
    rejecting viable candidates.
    """
    probe_l, probe_r = _apply_stereo_limiter(
        left, right, ceiling_db=ceiling_db, threshold_db=-24.0,
        sample_rate=sample_rate, release_ms=limiter_release_ms,
    )
    try:
        # Array-direct fast path (no write_wav encode + re-parse round trip) --
        # same fix as the gain-solve loop's own true-peak check below, verified
        # 0.0 dB diff against the byte-based path on real audio including
        # near-ceiling limited candidates (tests/audio_analysis/
        # test_true_peak_fast_path.py). This probe call site was missed when
        # that fix landed.
        real_true_peak_db = calculate_true_peak(probe_l, probe_r, sample_rate)
    except Exception:
        # A silent 0.0 dB fallback here means the closed-loop gain solve's
        # true-peak safety check runs uncorrected for this render's actual
        # limiter approximation error -- exactly the class of hidden
        # measurement failure the LUFS-accuracy bug (2026-07-08, see
        # _pre_limiter_makeup_gain above) was caused by, just for true peak
        # instead of LUFS. Must be observable.
        logger.warning(
            "calculate_true_peak failed in limiter-headroom calibration probe; "
            "reporting 0 dB correction (no calibration applied)", exc_info=True,
        )
        return 0.0
    overshoot_db = real_true_peak_db - ceiling_db
    if overshoot_db <= 0.0:
        return 0.0
    return overshoot_db + 0.05


# Ordered from mildest to most aggressive. Release never drops below 5ms —
# the safety bound found in the 2026-07-09 diagnostic (see
# `_apply_peak_catching_prelimiter` docstring).
_CREST_REDUCTION_ATTEMPTS: tuple[tuple[float, float], ...] = (
    (-10.0, 10.0),
    (-14.0, 8.0),
    (-18.0, 5.0),
)
_CREST_SATURATION_ATTEMPTS: tuple[tuple[float, float], ...] = (
    (3.0, 0.7),
    (6.0, 1.0),
    (9.0, 1.0),
    (12.0, 1.0),
    (15.0, 1.0),
)
_CREST_REDUCTION_SAFETY_BUFFER_DB = 0.05

# Ordered mildest to most aggressive, same primitive and safety bounds as
# _CREST_REDUCTION_ATTEMPTS above (see _apply_peak_catching_prelimiter's
# docstring for why release_ms never drops below ~5ms). A separate, gentler
# ladder than the reachability-gated one: this stage runs on material that
# can *already* hit its loudness target, so there's no pressure to reach for
# the more aggressive candidates -- the goal is closing a density gap, not
# rescuing an unreachable target.
_PROACTIVE_CREST_ATTEMPTS: tuple[tuple[float, float], ...] = (
    (-6.0, 15.0),
    (-9.0, 10.0),
    (-12.0, 8.0),
)
# Only engage above this measured crest factor -- a mix already at or below
# this is not the "peaky, thin-sounding" problem this stage exists to fix,
# and touching it would just be unexplained processing for no benefit.
# Reference point: stranger's baseline render (2026-07-17 reference-track
# comparison finding) measured well above typical dense-commercial-master
# territory at matched integrated loudness.
_PROACTIVE_CREST_TRIGGER_DB = 13.0
# Stop once density closes to roughly this crest factor -- not 0, which
# would be audibly over-limited; this is a target, not a floor to force.
_PROACTIVE_CREST_TARGET_DB = 11.0


def _apply_soft_saturation(
    left: np.ndarray,
    right: np.ndarray,
    drive_db: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Applies a smooth soft-knee tanh saturation curve to round transients and increase RMS warmth."""
    if drive_db <= 0.0:
        return left, right
    drive = 10.0 ** (drive_db / 20.0)
    sat_l = np.tanh(left * drive) / drive
    sat_r = np.tanh(right * drive) / drive
    return sat_l.astype(np.float64), sat_r.astype(np.float64)


def _apply_vocal_lead_mid_carve(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
    freq_hz: float = 1500.0,
    gain_db: float = -1.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Applies a subtle Mid-channel cut around 1.5 kHz to carve room for lead vocals."""
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)

    eq = ParametricEQ(sample_rate=sample_rate)
    eq.add_band("peaking", freq_hz, gain_db, q=1.0)
    mid_carved = eq.apply(mid, linear_phase=False)

    left_out = mid_carved + side
    right_out = mid_carved - side
    return left_out.astype(np.float64), right_out.astype(np.float64)


def _apply_drum_parallel_compression(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
    ratio: float = 4.0,
    threshold_db: float = -16.0,
    blend: float = 0.35,
) -> tuple[np.ndarray, np.ndarray]:
    """Applies parallel compression to drum stems to boost punch without crushing transients."""
    comp_l, comp_r = _apply_stereo_compressor(
        left, right,
        {"threshold_db": threshold_db, "ratio": ratio, "attack_ms": 30.0, "release_ms": 100.0},
        sample_rate
    )
    comp_l = apply_gain(comp_l, 4.0)
    comp_r = apply_gain(comp_r, 4.0)

    out_l = (1.0 - blend) * left + blend * comp_l
    out_r = (1.0 - blend) * right + blend * comp_r
    return out_l.astype(np.float64), out_r.astype(np.float64)


def _apply_proactive_crest_reduction(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Opt-in (MixPlan.apply_proactive_crest_reduction) proactive density
    correction, run before the closed-loop LUFS gain solve so the final
    integrated loudness is unaffected either way -- only how much of that
    fixed loudness budget goes to sustained density vs. transient peaks.

    Unlike `_reduce_crest_factor_if_needed` below (gated on reachability --
    only ever engages when the material genuinely can't hit target loudness
    at the render's ceiling), this engages purely on measured crest factor,
    independent of whether the target is already trivially reachable. That
    distinction matters: the 2026-07-17 density finding
    (docs/PROJECT_ACTION_PLAN_2026-07-14.md §10.16) was a mix whose
    pre-normalization signal measured -8.78 LUFS -- far *louder* than its
    -14 target, so `_reduce_crest_factor_if_needed` correctly saw the target
    as trivially reachable and never engaged, even though the mix's actual
    problem (a 6.6dB density gap vs. a commercial reference at matched
    integrated loudness) was real and measurable. Fixed-LUFS normalization
    alone can't fix that: it controls the average level, not the
    peak-to-average ratio.

    Same "apply, then measure the real result" pattern as
    `_reduce_crest_factor_if_needed`: never trusts a candidate's effect from
    its parameters alone, always re-measures, and never returns something
    with a worse (higher) crest factor than the input.
    """
    baseline_crest_db = _measure_crest_factor_db(left, right)
    diagnostics: dict = {
        "engaged": False,
        "baseline_crest_db": baseline_crest_db,
        "final_crest_db": baseline_crest_db,
        "attempts": [],
    }
    if baseline_crest_db <= _PROACTIVE_CREST_TRIGGER_DB:
        return left, right, diagnostics

    diagnostics["engaged"] = True
    best_l, best_r = left, right
    best_crest_db = baseline_crest_db
    for pre_ceiling_db, release_ms in _PROACTIVE_CREST_ATTEMPTS:
        sat_l, sat_r = _apply_soft_saturation(left, right, drive_db=1.0)
        cand_l, cand_r = _apply_peak_catching_prelimiter(
            sat_l, sat_r, sample_rate, pre_ceiling_db, release_ms
        )
        cand_crest_db = _measure_crest_factor_db(cand_l, cand_r)
        diagnostics["attempts"].append({
            "pre_ceiling_db": pre_ceiling_db, "release_ms": release_ms, "crest_db": cand_crest_db,
        })
        if cand_crest_db < best_crest_db:
            best_l, best_r, best_crest_db = cand_l, cand_r, cand_crest_db
        if best_crest_db <= _PROACTIVE_CREST_TARGET_DB:
            break

    diagnostics["final_crest_db"] = best_crest_db
    if best_crest_db >= baseline_crest_db:
        # No candidate actually helped -- ship the original rather than a
        # "different but not better" one.
        diagnostics["engaged"] = False
        return left, right, diagnostics
    return best_l, best_r, diagnostics


def _reduce_crest_factor_if_needed(
    left: np.ndarray,
    right: np.ndarray,
    sample_rate: int,
    target_lufs: float,
    ceiling_db_for_limiter: float,
    limiter_release_ms: float = 50.0,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Verified closed-loop pre-limiter crest reduction.

    Only engages if a probe shows the current material genuinely can't reach
    `target_lufs` at this ceiling (most genre profiles never hit this path at
    all — zero behavior change for material that doesn't need it). When it
    does engage, each candidate's ACTUAL effect (crest factor, reachable
    LUFS) is measured before being trusted or intensified — never assumed
    from the compression ratio alone, which is exactly the failure mode of
    the reverted 2026-07-09 attempt documented in
    docs/AUDIO_MVP_MASTER_PLAN.md Stage A. Only keeps a candidate that
    measurably improves on the baseline; never returns something worse than
    the input.
    """
    baseline_reachable = _probe_reachable_lufs(
        left, right, sample_rate, ceiling_db_for_limiter, limiter_release_ms
    )
    diagnostics = {
        "engaged": False,
        "baseline_reachable_lufs": baseline_reachable,
        "final_reachable_lufs": baseline_reachable,
        "attempts": [],
    }
    if baseline_reachable >= target_lufs - _CREST_REDUCTION_SAFETY_BUFFER_DB:
        return left, right, diagnostics

    diagnostics["engaged"] = True
    best_l, best_r = left, right
    best_reachable = baseline_reachable
    for pre_ceiling_db, release_ms in _CREST_REDUCTION_ATTEMPTS:
        cand_l, cand_r = _apply_peak_catching_prelimiter(
            left, right, sample_rate, pre_ceiling_db, release_ms
        )
        reachable = _probe_reachable_lufs(
            cand_l, cand_r, sample_rate, ceiling_db_for_limiter, limiter_release_ms
        )
        diagnostics["attempts"].append(
            {"pre_ceiling_db": pre_ceiling_db, "release_ms": release_ms, "reachable_lufs": reachable}
        )
        if reachable > best_reachable:
            best_l, best_r, best_reachable = cand_l, cand_r, reachable
        if reachable >= target_lufs - _CREST_REDUCTION_SAFETY_BUFFER_DB:
            break

    if best_reachable < target_lufs - _CREST_REDUCTION_SAFETY_BUFFER_DB:
        for drive_db, mix in _CREST_SATURATION_ATTEMPTS:
            cand_l = apply_saturation(left, drive_db=drive_db, mix=mix, oversample=True)
            cand_r = apply_saturation(right, drive_db=drive_db, mix=mix, oversample=True)
            reachable = _probe_reachable_lufs(
                cand_l, cand_r, sample_rate, ceiling_db_for_limiter, limiter_release_ms
            )
            diagnostics["attempts"].append({
                "method": "soft_saturation",
                "drive_db": drive_db,
                "mix": mix,
                "reachable_lufs": reachable,
            })
            if reachable > best_reachable:
                best_l, best_r, best_reachable = cand_l, cand_r, reachable
            if reachable >= target_lufs - _CREST_REDUCTION_SAFETY_BUFFER_DB:
                break

    diagnostics["final_reachable_lufs"] = best_reachable
    if best_reachable <= baseline_reachable:
        # No attempt actually helped -- ship the original rather than a
        # "different but not better" candidate.
        diagnostics["engaged"] = False
        return left, right, diagnostics
    return best_l, best_r, diagnostics


def refine_mix_if_needed(
    prepared_stems: list[dict],
    first_result: dict,
    mix_plan: MixPlan,
    *,
    quality_threshold: float = 70.0,
    connect_func=None,
) -> dict:
    """M8.2 — Multi-Pass Intelligent Refinement.

    Scores the first render using the quality predictor.  If the score is below
    ``quality_threshold``, uses the KENN LM prose summary to identify the most
    impactful improvement, applies it to the plan, and re-renders.  Returns
    whichever version scores higher.

    Falls back gracefully when quality_predictor or the LM is unavailable.
    """
    try:
        from audio_analysis.integration.quality_predictor import predict_quality, train_from_history
        from audio_analysis.mix_features import extract_feature_vector
        from audio_analysis.integration.mix_intent import parse_mix_intent, apply_intent_to_plan

        # Score the first render
        metrics = first_result.get("analysis", {})
        fv = extract_feature_vector(metrics)
        if connect_func:
            from audio_analysis.mix_review.review_store import load_feedback_training_data
            records = load_feedback_training_data(connect_func=connect_func, limit=200)
            if len(records) >= 6:
                model = train_from_history(records)
            else:
                return first_result
        else:
            return first_result

        prediction = predict_quality(model, fv)
        score = float(prediction.get("score", 100.0))

        if score >= quality_threshold:
            return first_result  # Already good enough

        # Get improvement suggestion from KENN LM prose summary
        try:
            from audio_analysis.analysis_core.analysis_interpretation import generate_prose_summary
            summary = generate_prose_summary({"metrics": metrics, "flags": [], "action_plan": []})
            improvement_text = summary.get("text", "")
            # Extract the third paragraph (most impactful improvement)
            paragraphs = [p.strip() for p in improvement_text.split("\n\n") if p.strip()]
            instruction = paragraphs[-1] if paragraphs else ""
        except Exception:
            instruction = ""

        if not instruction:
            return first_result

        intent = parse_mix_intent(instruction, {"metrics": metrics})
        adjusted_plan = apply_intent_to_plan(intent, mix_plan)
        second_result = mix_and_render_stems(prepared_stems, adjusted_plan)

        # Score the second render and keep the better one
        fv2 = extract_feature_vector(second_result.get("analysis", {}))
        score2 = float(predict_quality(model, fv2).get("score", 0.0))
        if score2 > score:
            second_result["refinement"] = {
                "applied": True,
                "first_score": round(score, 1),
                "second_score": round(score2, 1),
                "instruction": instruction,
                "intent": intent,
            }
            return second_result
        else:
            first_result["refinement"] = {
                "applied": False,
                "first_score": round(score, 1),
                "second_score": round(score2, 1),
                "note": "Second pass did not improve quality; keeping original.",
            }
            return first_result
    except Exception:
        return first_result


def render_unprocessed_stem_sum(prepared_stems: list[dict]) -> dict:
    """Sum prepared stems at unity gain with zero processing -- the "what did
    this sound like before AutoMix touched it" baseline for a before/after
    comparison. Same input contract as mix_and_render_stems (aligned samples,
    common sample_rate, "stereo_preserved" flag), but skips the entire
    MixPlan pipeline: no gain staging, EQ, compression, panning, or bus
    processing. Stereo-preserved stems keep their real left/right image
    (summed independently), not a mono-then-rewidened approximation.

    Parameters
    ----------
    prepared_stems : list[dict]
        Same shape prepare_stems() returns / mix_and_render_stems() consumes.

    Returns
    -------
    dict
        - "mixdown_wav_bytes": bytes (stereo WAV, safety-clipped at +-1.0)
        - "left": np.ndarray
        - "right": np.ndarray
        - "stem_audio": dict[str, tuple[np.ndarray, np.ndarray]] -- each raw
          stem's own (left, right) before any processing, same shape as
          mix_and_render_stems(capture_stem_audio=True)'s "stem_audio", so
          a caller can pair raw-vs-processed per stem for a per-stem
          before/after (not just the overall mix).
    """
    if not prepared_stems:
        raise ValueError("No prepared stems provided for the raw baseline sum.")

    sr = prepared_stems[0]["sample_rate"]
    num_samples = len(prepared_stems[0]["samples"])

    sum_l = np.zeros(num_samples, dtype=np.float64)
    sum_r = np.zeros(num_samples, dtype=np.float64)
    stem_audio: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    for stem_data in prepared_stems:
        name = stem_data["name"]
        if bool(stem_data.get("stereo_preserved")):
            source_l = np.asarray(stem_data.get("left_samples", []), dtype=np.float64)
            source_r = np.asarray(stem_data.get("right_samples", []), dtype=np.float64)
            if len(source_l) != num_samples or len(source_r) != num_samples:
                raise ValueError(f"Prepared stereo stem '{name}' has unaligned channels.")
            sum_l += source_l
            sum_r += source_r
            stem_audio[name] = (source_l, source_r)
        else:
            samples = np.asarray(stem_data["samples"], dtype=np.float64)
            if len(samples) != num_samples:
                raise ValueError(f"Prepared stem '{name}' has unaligned length.")
            sum_l += samples
            sum_r += samples
            stem_audio[name] = (samples, samples)

    wav_bytes = write_wav(sum_l.tolist(), sum_r.tolist(), sr, bit_depth=24)
    return {
        "mixdown_wav_bytes": wav_bytes, "left": sum_l, "right": sum_r, "stem_audio": stem_audio,
    }


def normalize_to_target_lufs(
    master_l: np.ndarray,
    master_r: np.ndarray,
    sr: int,
    *,
    target_lufs: float,
    ceiling_db: float = -1.0,
    threshold_offset_db: float = 0.0,
    apply_proactive_crest_reduction: bool = False,
) -> tuple[np.ndarray, np.ndarray, float, dict]:
    """Closed-loop gain solve + true-peak-safe limiting: normalize an
    already-fully-mixed stereo signal to target_lufs, re-measuring and
    correcting until converged (or safely falling back) rather than trusting
    a single limiter pass sized from the pre-limiter measurement.

    Extracted (2026-08-01, pure refactor, verified bit-identical against
    the inline version it replaced -- see
    tests/audio_analysis/test_normalize_to_target_lufs.py) from what used
    to be inline in mix_and_render_stems' "9. Master Loudness Normalization
    & Limiting" stage, so this closed-loop solve is reusable on a plain
    stereo signal without needing a MixPlan/BusMixConfig/full stem pipeline
    -- e.g. a future "conform this uploaded master to a delivery-spec
    target" caller. Does not itself change any AutoMix render behavior;
    mix_and_render_stems calls this with the exact same values it always
    computed for this stage.

    Returns (left, right, final_lufs, diagnostics) where diagnostics has
    the same fields mix_and_render_stems already reported under its
    "loudness_solver" key (ceiling_dbtp, calibration_headroom_db,
    limiter_release_ms, proactive_crest_reduction, crest_reduction,
    gain_attempts, selected_lufs, selected_gap_lu, found_safe_candidate).

    Raises RuntimeError if even the most conservative gain the closed-loop
    solve is willing to try still can't hold ceiling_db -- a genuinely
    pathological input (e.g. already-clipped or extreme-crest-factor
    source), not something to ship silently.
    """
    try:
        l_dict = calculate_loudness_profile(master_l, master_r, sr)
        measured_lufs = l_dict.get("integrated_lufs", -18.0)
    except Exception:
        # A silent fallback here feeds directly into makeup_gain_db below — the
        # exact mechanism behind the LUFS-accuracy bug fixed 2026-07-08
        # (docs/AUTOMIX_QUALITY_FINDINGS_2026-07-08.md finding #2). Must be
        # observable: a hidden loudness-measurement failure would silently
        # reintroduce a milder version of that bug.
        logger.warning("calculate_loudness_profile failed pre-limiter; "
                       "makeup gain will be computed from a -18 LUFS guess", exc_info=True)
        measured_lufs = -18.0

    # Target makeup gain
    makeup_gain_db = target_lufs - measured_lufs
    # The upper bound must cover the reachability probe's -24 dB drive. A lower
    # +18 dB cap previously made the solver stop below a target that its own
    # verified probe had shown to be attainable. Every candidate is still
    # independently true-peak checked below, so this expands search range, not
    # the safety envelope.
    max_makeup_gain_db = 24.0
    makeup_gain_db = max(-12.0, min(makeup_gain_db, max_makeup_gain_db))

    # Closed-loop gain solve (Stage 7 follow-up, 2026-07-09): a single limiter
    # pass sized from the *pre-limiter* LUFS measurement systematically
    # undershoots the target on heavily-limited material — the limiter's own
    # gain reduction removes loudness that the upfront makeup-gain estimate
    # never accounted for (measured up to -1.5 LU off on high-crest-factor
    # genres in tests/audio_analysis/test_mix_renderer_genre_matrix.py).
    # Fix: re-run the limiter from the pre-limiter signal, adjusting the
    # threshold by the previous pass's measured residual, until converged or
    # out of iterations. Always starts from `pre_limit_l/r`, never from an
    # already-limited signal, to avoid stacking limiter artifacts.
    lufs_convergence_tolerance = 0.05  # LU; safely under the ±0.1 target
    # Matches mix_validator.py's own `ceiling_margin_db` default (0.15) — the
    # established measurement-noise margin for this codebase's true-peak
    # checks. `calculate_true_peak_numpy` here and `calculate_true_peak` in
    # the validator use slightly different resampling/quantization paths and
    # can disagree by a few thousandths of a dB; a tighter margin than the
    # validator's own would reject candidates the validator itself accepts.
    true_peak_safety_margin_db = 0.15

    # Stage A follow-up (2026-07-09): measured, per-render correction for
    # `_apply_stereo_limiter`'s own true-peak-estimation error (see
    # `_calibrate_limiter_headroom_db` docstring), then — only if this
    # material genuinely can't reach the target loudness at that corrected
    # ceiling — a verified attempt at real pre-limiter crest reduction (see
    # `_reduce_crest_factor_if_needed` docstring). Both steps no-op (measured,
    # not assumed) on material that doesn't need them, so this cannot change
    # behavior on genres that already pass. This never touches
    # `true_peak_safety_margin_db` or the real per-candidate safety check
    # below — it only changes how much gain the closed loop below is willing
    # to feed into the limiter before that safety check runs.
    limiter_release_ms = 50.0

    # Proactive density correction (§10.4, opt-in, listening-gated —
    # MixPlan.apply_proactive_crest_reduction, default off). Runs before the
    # reachability-gated calibration/reduction below so the closed-loop gain
    # solve always re-measures and hits target_lufs exactly regardless; this
    # only changes the waveform's density/shape at that same final loudness.
    # See _apply_proactive_crest_reduction's docstring for why this needed a
    # separate trigger from _reduce_crest_factor_if_needed's reachability
    # gate (a mix can be far *louder* than its target pre-normalization and
    # still have a real density gap that reachability-gating never sees).
    proactive_crest_diag: dict = {"engaged": False}
    if apply_proactive_crest_reduction:
        master_l, master_r, proactive_crest_diag = _apply_proactive_crest_reduction(
            master_l, master_r, sr,
        )
        if proactive_crest_diag["engaged"]:
            logger.info(
                "Proactive crest-factor reduction engaged: %.2f dB -> %.2f dB",
                proactive_crest_diag["baseline_crest_db"],
                proactive_crest_diag["final_crest_db"],
            )

    calibration_headroom_db = _calibrate_limiter_headroom_db(
        master_l, master_r, sr, ceiling_db, limiter_release_ms
    )
    master_l, master_r, crest_reduction_diag = _reduce_crest_factor_if_needed(
        master_l, master_r, sr, target_lufs, ceiling_db - calibration_headroom_db,
        limiter_release_ms,
    )
    if crest_reduction_diag["engaged"]:
        # Crest reduction changed the signal's transient structure, which can
        # itself change the limiter's precision error -- recalibrate against
        # the final signal rather than trusting the pre-reduction measurement.
        calibration_headroom_db = _calibrate_limiter_headroom_db(
            master_l, master_r, sr, ceiling_db, limiter_release_ms
        )
        logger.info(
            "Crest-factor reduction engaged: reachable LUFS %.3f -> %.3f "
            "(target %.2f, ceiling %.2f dBTP)",
            crest_reduction_diag["baseline_reachable_lufs"],
            crest_reduction_diag["final_reachable_lufs"],
            target_lufs, ceiling_db,
        )
    ceiling_db_for_limiter = ceiling_db - calibration_headroom_db

    pre_limit_l, pre_limit_r = master_l, master_r
    max_gain_iterations = 6
    max_step_db = 6.0  # bound each correction step for stability
    final_lufs = target_lufs
    prev_gain_db: float | None = None
    prev_final_lufs: float | None = None

    # Track the best candidate that actually holds the true-peak ceiling.
    # `_apply_stereo_limiter` computes its gain from a stereo-linked
    # max(|L|,|R|) envelope, which is an approximation — it can understate
    # either channel's real inter-sample true peak. Chasing a hard LUFS
    # target by pushing makeup gain higher can drive that approximation
    # error past the ceiling (found via this exact loop: -0.8 dBTP against
    # a -1.5 dBTP ceiling on a wide-dynamic-range case). So every candidate
    # is independently re-verified with a real per-channel true-peak
    # measurement (`calculate_true_peak_numpy`, not the limiter's internal
    # estimate) before being trusted, and the final output is always the
    # best *safe* candidate found — never the most recent one, since the
    # most recent gain step is exactly the one most likely to be unsafe.
    best_safe_l, best_safe_r = master_l, master_r
    best_safe_lufs = final_lufs
    best_safe_gap = float("inf")
    found_safe_candidate = False
    gain_attempts: list[dict] = []

    for _ in range(max_gain_iterations):
        candidate_l, candidate_r = _apply_stereo_limiter(
            pre_limit_l,
            pre_limit_r,
            ceiling_db=ceiling_db_for_limiter,
            threshold_db=-makeup_gain_db + threshold_offset_db,
            sample_rate=sr,
            release_ms=limiter_release_ms,
        )
        try:
            final_l = calculate_loudness_profile(candidate_l, candidate_r, sr)
            final_lufs = final_l.get("integrated_lufs", target_lufs)
        except Exception:
            # This becomes the self-reported measured_lufs -- verified accurate
            # against independent measurement in the quality benchmark; a silent
            # failure here would quietly break that trustworthiness.
            logger.warning("Final loudness re-measurement failed; self-reporting target as measured", exc_info=True)
            final_lufs = target_lufs
            break

        # Direct array measurement (no write_wav encode + re-decode round trip) --
        # calculate_true_peak(left, right, sr) with no raw_bytes now takes the
        # array-native calculate_true_peak_numpy path. Verified 0.0 dB diff
        # against the byte-based path (what mix_validator.py's final safety
        # gate still uses) across real track audio, including near-ceiling
        # limited candidates (tests/audio_analysis/test_true_peak_fast_path.py)
        # -- 24-bit dither noise is far below any true-peak-relevant threshold.
        # (A synthetic full-bandwidth white-noise signal CAN make the two
        # diverge by several dB -- resample_poly's reconstruction filter isn't
        # designed for energy at Nyquist -- but real, band-limited music audio
        # doesn't trigger this.) The outer verify_render_output() in
        # mix_validator.py still does the accurate byte-based check as the
        # final gate before shipping either way.
        real_true_peak_db = calculate_true_peak(candidate_l, candidate_r, sr)
        is_safe = real_true_peak_db <= ceiling_db + true_peak_safety_margin_db
        gap = abs(target_lufs - final_lufs)
        gain_attempts.append({
            "makeup_gain_db": float(makeup_gain_db),
            "measured_lufs": float(final_lufs),
            "true_peak_dbtp": float(real_true_peak_db),
            "safe": bool(is_safe),
            "target_gap_lu": float(gap),
        })

        if is_safe:
            if gap < best_safe_gap:
                best_safe_l, best_safe_r = candidate_l, candidate_r
                best_safe_lufs = final_lufs
                best_safe_gap = gap
                found_safe_candidate = True
            if gap <= lufs_convergence_tolerance:
                break
        else:
            logger.warning(
                "Rejected gain candidate: real true peak %.3f dBTP exceeds ceiling %.2f "
                "(makeup_gain_db=%.2f); backing off rather than accepting an unsafe render",
                real_true_peak_db, ceiling_db, makeup_gain_db,
            )

        residual_db = target_lufs - final_lufs

        if not is_safe:
            # Back off decisively rather than trusting the secant slope —
            # an unsafe reading is not a trustworthy data point to
            # extrapolate from.
            step_db = -abs(max_step_db) / 2.0
            prev_gain_db, prev_final_lufs = makeup_gain_db, final_lufs
            makeup_gain_db = max(-12.0, min(makeup_gain_db + step_db, max_makeup_gain_db))
            continue

        # Secant-style correction: once heavy limiting is active, +1 dB of
        # makeup gain buys measurably less than +1 LU of loudness (the
        # limiter eats part of every increment), so a naive unity-slope
        # correction ("add the residual") converges too slowly. Use the
        # empirically observed gain->LUFS slope between the last two passes
        # to extrapolate the right step; fall back to unity slope on the
        # first pass (no prior data yet) or when the observed slope is too
        # small/noisy to trust (near-zero or wrong-signed).
        if prev_gain_db is not None and prev_final_lufs is not None:
            gain_delta = makeup_gain_db - prev_gain_db
            lufs_delta = final_lufs - prev_final_lufs
            slope = lufs_delta / gain_delta if abs(gain_delta) > 1e-6 else 1.0
            if slope < 0.05:
                slope = 1.0
        else:
            slope = 1.0

        step_db = residual_db / slope
        step_db = max(-max_step_db, min(step_db, max_step_db))
        prev_gain_db, prev_final_lufs = makeup_gain_db, final_lufs
        makeup_gain_db = max(-12.0, min(makeup_gain_db + step_db, max_makeup_gain_db))

    if not found_safe_candidate:
        # Every candidate this loop tried violated the ceiling (should be
        # rare — the very first candidate uses the same gain the old
        # single-pass renderer always used, and that never violated the
        # ceiling across the full genre test matrix). Fall back to the most
        # conservative possible gain (the floor of the makeup-gain range)
        # rather than shipping anything this loop couldn't itself verify as
        # safe — least gain into the limiter is the safest bet for holding
        # the ceiling, even though it will undershoot the loudness target.
        logger.warning(
            "No gain candidate held the true-peak ceiling safely; falling back to minimum makeup gain"
        )
        fallback_l, fallback_r = _apply_stereo_limiter(
            pre_limit_l, pre_limit_r, ceiling_db=ceiling_db_for_limiter,
            threshold_db=12.0 + threshold_offset_db, sample_rate=sr,
            release_ms=limiter_release_ms,
        )
        fallback_true_peak_db = calculate_true_peak(fallback_l, fallback_r, sr)
        if fallback_true_peak_db > ceiling_db + true_peak_safety_margin_db:
            # Even the most conservative gain the closed-loop solve is
            # willing to try still can't hold the ceiling — this points to
            # a genuinely pathological input (e.g. an already-clipped or
            # extreme-crest-factor source). Do not ship it silently.
            raise RuntimeError(
                f"normalize_to_target_lufs: unable to produce a render within the "
                f"{ceiling_db:.2f} dBTP ceiling even at minimum makeup gain "
                f"(measured {fallback_true_peak_db:.3f} dBTP) — input material may be pathological"
            )
        best_safe_l, best_safe_r = fallback_l, fallback_r
        try:
            fallback_l_dict = calculate_loudness_profile(fallback_l, fallback_r, sr)
            best_safe_lufs = fallback_l_dict.get("integrated_lufs", target_lufs)
        except Exception:
            best_safe_lufs = target_lufs

    diagnostics = {
        "ceiling_dbtp": float(ceiling_db),
        "calibration_headroom_db": float(calibration_headroom_db),
        "limiter_release_ms": float(limiter_release_ms),
        "proactive_crest_reduction": proactive_crest_diag,
        "crest_reduction": crest_reduction_diag,
        "gain_attempts": gain_attempts,
        "selected_lufs": float(best_safe_lufs),
        "selected_gap_lu": float(abs(target_lufs - best_safe_lufs)),
        "found_safe_candidate": bool(found_safe_candidate),
    }
    return best_safe_l, best_safe_r, best_safe_lufs, diagnostics


def apply_master_bus_chain(
    master_l: np.ndarray,
    master_r: np.ndarray,
    sr: int,
    bus_config: BusMixConfig | None,
    genre: str,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Master bus processing chain: saturation -> glue compressor ->
    multiband compressor -> master EQ -> M/S stereo enhancer -> dynamic EQ.

    Extracted (2026-08-01, pure refactor -- verified bit-identical against
    the inline version it replaced via a git-worktree A/B comparison) out
    of what used to be "8. Master Bus Processing" inline in
    mix_and_render_stems, completing the same Stage 8 -> Stage 9 split
    normalize_to_target_lufs already did for the stage right after this
    one. A no-op (returns the input unchanged, empty dynamic_eq_bands)
    when bus_config is None -- matches the original's `if bus_config :=
    mix_plan.bus:` guard exactly.
    """
    applied_dynamic_eq_bands: list[dict] = []  # always defined; only nonempty if bus_config exists and a resonance was found
    # A. Master Bus Saturation (tape warmth)
    if bus_config:
        if bus_config.saturation_drive_db > 0.0:
            master_l = apply_saturation(
                master_l, drive_db=bus_config.saturation_drive_db, mix=bus_config.saturation_mix, oversample=True
            )
            master_r = apply_saturation(
                master_r, drive_db=bus_config.saturation_drive_db, mix=bus_config.saturation_mix, oversample=True
            )

        # B. Master Glue Compressor
        if bus_config.bus_compressor:
            master_l, master_r = _apply_stereo_compressor(
                master_l, master_r, bus_config.bus_compressor, sr
            )
            # _apply_stereo_compressor only computes gain reduction -- it never
            # reads makeup_gain_db (unlike the per-stem compressor path a few
            # lines below, which explicitly applies it via apply_gain() after
            # the call). Found 2026-07-17 while diagnosing why an aggressive
            # glue-compressor override (ratio 3:1, threshold well below program
            # level) measured an 8.6dB RMS *drop* instead of the intended density
            # increase -- any makeup_gain_db set on the master bus compressor was
            # being silently discarded here.
            bus_makeup_gain = float(bus_config.bus_compressor.get("makeup_gain_db", 0.0))
            if bus_makeup_gain != 0.0:
                master_l = apply_gain(master_l, bus_makeup_gain)
                master_r = apply_gain(master_r, bus_makeup_gain)

        # C. Master Multiband Compressor
        master_l, master_r = _apply_multiband_compressor(
            master_l, master_r, sr, multiband_config=getattr(bus_config, "multiband_compressor", None)
        )

        # C2. Master Bus EQ (linear-phase for mastering — M8.4a)
        if bus_config.bus_eq_bands:
            bus_eq = ParametricEQ(sample_rate=sr)
            for band in bus_config.bus_eq_bands:
                bus_eq.add_band(band["type"], band["frequency"], band.get("gain_db", 0.0), band.get("q", 0.707))
            master_l = bus_eq.apply(master_l, linear_phase=True)
            master_r = bus_eq.apply(master_r, linear_phase=True)

        # D. Master Mid/Side Stereo Enhancer
        width_factor = 1.0
        if genre in ("pop", "edm", "hip_hop", "rock"):
            width_factor = 1.15  # 15% widening boost for commercial width
        # Reference-similarity nudge (spectral_match.compute_reference_width_factor):
        # a second width pass composes exactly as one combined pass since M/S mid
        # is invariant under width scaling (same property stage 7B above relies
        # on) -- multiplying here is mathematically identical to, not a fight
        # with, the genre default above. Pre-clamped to +/-15% by the caller, so
        # this can't push width far even combined with the genre boost.
        width_factor *= bus_config.reference_width_factor
        master_l, master_r = _apply_ms_stereo_enhancer(master_l, master_r, width_factor)

        # Master low-end mono collapse below 100 Hz (protects sub-bass center focus & mono compatibility)
        from ..dsp_engine.gain_pan import mono_below_frequency
        master_l, master_r = mono_below_frequency(master_l, master_r, cutoff_hz=100.0, sample_rate=sr)

        # E. Dynamic EQ (Stage C, 2026-07-09 — see docs/SPECTRAL_DYNAMIC_EQ_PLUGIN_PLAN.md)
        # Detect narrow resonances that persist across the mix and pull them
        # down surgically, late in the chain (post width, pre final gain/
        # limiting) — matches where a mastering engineer would place a
        # dynamic EQ pass. Transparent when nothing problematic is present
        # (see test_dynamic_eq.py's "quiet band is transparent" case), so
        # this is safe to run unconditionally rather than gate behind a flag.
        try:
            # A proper mono sum (mid channel), not a rectified envelope —
            # taking abs() of the waveform before spectral analysis would
            # introduce heavy harmonic distortion and corrupt the FFT.
            detector_mono = (master_l + master_r) * 0.5
            resonant_bands = detect_resonant_bands(detector_mono, sr)
            if resonant_bands:
                master_l, master_r = apply_dynamic_eq_bands(
                    master_l, master_r, bands=resonant_bands, sample_rate=sr,
                )
                applied_dynamic_eq_bands = resonant_bands[:6]  # matches apply_dynamic_eq_bands' default cap
        except Exception:
            logger.warning("Master bus dynamic EQ pass failed; continuing without it", exc_info=True)

    return master_l, master_r, applied_dynamic_eq_bands


def mix_and_render_stems(
    prepared_stems: list[dict],
    mix_plan: MixPlan,
    *,
    capture_stem_audio: bool = False,
) -> dict:
    """Apply the MixPlan to prepared stems, summing and rendering the final master.

    Parameters
    ----------
    prepared_stems : list[dict]
        Each dict has:
          - "name": str (filename)
          - "samples": list[float] or np.ndarray (aligned mono samples)
          - "sample_rate": int
    mix_plan : MixPlan
        The mix configuration generated by the MixDecisionEngine.
    capture_stem_audio : bool
        If True, also return each stem's fully-processed audio (post
        gain/EQ/compression/gate/saturation/pan/width/mono-below, exactly as
        it contributes to the mix bus) via the "stem_audio" key. Off by
        default -- this is extra memory (one L/R pair per stem) that only
        per-stem QA/verification tooling needs, not the normal render path.

    Returns
    -------
    dict
        Contains:
          - "mixdown_wav_bytes": bytes (stereo 24-bit WAV file)
          - "left": np.ndarray (rendered left channel)
          - "right": np.ndarray (rendered right channel)
          - "measured_lufs": float
          - "mix_plan": MixPlan
          - "stem_audio": dict[str, tuple[np.ndarray, np.ndarray]] | None
            (name -> (left, right), only populated if capture_stem_audio=True)
          - "stem_dynamic_eq_bands": dict[str, list[dict]] (Stage M1 -- name
            -> resonant bands found and cut on that stem before mixing;
            empty dict if nothing was found on any stem)
    """
    if not prepared_stems:
        raise ValueError("No prepared stems provided for mixing.")

    sr = prepared_stems[0]["sample_rate"]
    num_samples = len(prepared_stems[0]["samples"])

    # Initialize summing buses
    sum_l = np.zeros(num_samples, dtype=np.float64)
    sum_r = np.zeros(num_samples, dtype=np.float64)

    stem_audio: dict[str, tuple[np.ndarray, np.ndarray]] | None = {} if capture_stem_audio else None
    # Stage M1: per-stem dynamic EQ cuts, keyed by stem name -- always
    # defined, only nonempty for a stem where a resonance was actually found.
    applied_stem_dynamic_eq: dict[str, list[dict]] = {}

    # Masking correction stage (§6.2/§10.4): de-mask lower-priority stems using
    # the relationship engine's actionable dynamic-EQ candidates. Off unless the
    # plan opts in (listening-gated). Keyed by normalized target basename.
    masking_moves: dict[str, dict] = (
        _masking_moves_by_target(mix_plan.relationships)
        if getattr(mix_plan, "apply_masking_corrections", False)
        else {}
    )
    applied_masking_moves: dict[str, dict] = {}

    # Mono-compatibility correction stage: bounded additional stereo narrowing
    # on stems the detector flagged warning/critical. Off unless the plan opts
    # in (listening-gated). Keyed by normalized stem basename -> severity.
    mono_compat_flags: dict[str, str] = (
        _mono_compat_severity_by_stem(mix_plan.mono_compatibility)
        if getattr(mix_plan, "apply_mono_compat_correction", False)
        else {}
    )
    applied_mono_compat_corrections: dict[str, dict] = {}

    # Auxiliary Send Buses
    has_lead_vocal = any(c.instrument in ("vocal", "synth_lead") for c in mix_plan.stems)
    reverb_send_buses: dict[tuple[str, float], np.ndarray] = {}
    delay_send_bus = np.zeros(num_samples, dtype=np.float64)

    # Per-stem processing extracted into a pure closure so stems (which are
    # fully independent) can be processed in parallel across cores -- scipy
    # (lfilter/sosfilt), numba (dynamics/gate) and numpy all release the GIL, so
    # threads genuinely parallelize (measured ~2.75x on the per-stem chain).
    # The closure MUTATES no shared state: it returns each stem's outputs, which
    # are summed/collected in the ORIGINAL stem order by a serial reduce below,
    # so the mixdown is bit-identical to the sequential render (float summation
    # order preserved). Returns None for a stem with no matching config.
    def _process_stem(stem_data):
        _r_stem_dyn_eq = None
        _r_masking_move = None
        _r_mono_compat = None
        name = stem_data["name"]
        samples = np.asarray(stem_data["samples"], dtype=np.float64)
        stereo_source = bool(stem_data.get("stereo_preserved"))
        if stereo_source:
            source_l = np.asarray(stem_data.get("left_samples", []), dtype=np.float64)
            source_r = np.asarray(stem_data.get("right_samples", []), dtype=np.float64)
            if len(source_l) != num_samples or len(source_r) != num_samples:
                raise ValueError(f"Prepared stereo stem '{name}' has unaligned channels.")

        # Find corresponding mix config
        config = next((c for c in mix_plan.stems if c.stem_name == name), None)
        if not config:
            # Fallback if stem not in plan
            config = next((c for c in mix_plan.stems if c.stem_name.rsplit(".", 1)[0] == name.rsplit(".", 1)[0]), None)

        if not config:
            # Use default Config
            config = next((c for c in mix_plan.stems if c.instrument == "other"), None)
            if not config:
                return None

        # 1. Gain Staging
        if stereo_source:
            proc_l = apply_gain(source_l, config.gain_db)
            proc_r = apply_gain(source_r, config.gain_db)
            s_proc = 0.5 * (proc_l + proc_r)
        else:
            s_proc = apply_gain(samples, config.gain_db)

        # 1B. Per-stem Dynamic EQ (Stage M1, 2026-07-10 — see
        # docs/AUDIO_MVP_MASTER_PLAN.md Stage M1)
        # The exact same detector/processor Stage C already uses on the
        # post-mix master bus (unchanged — its signature was always generic,
        # never master-bus-specific), run here on each stem's own gain-staged
        # audio instead. Catches a resonance baked into ONE stem (a boxy
        # 400Hz on a rhythm guitar, a nasal 900Hz on a vocal) that may not be
        # prominent enough at the master-bus level to cross the detector's
        # prominence/persistence thresholds once summed and partially masked
        # by everything else, even though it's clearly present in isolation.
        # Additive, not a replacement: the master-bus pass (stage 8E below)
        # still runs unchanged afterward and will simply find nothing left
        # here if this stage already fixed it — no double-processing guard
        # needed, the detector is the guard (transparent when nothing found).
        #
        # needs_resonance_scan (dsp_engine/dsp_necessity.py, decided once at
        # plan-generation time from this stem's own frequency_profile) skips
        # the scan entirely for stems with negligible energy above 150Hz
        # (pure sub-bass/kick stems) — the detector always ran unconditionally
        # here before, a real cost on every stem per
        # docs/audits/2026-07-30-automix-cpp-kernel-and-vectorization-pass.md.
        try:
            stem_resonant_bands = (
                detect_resonant_bands(
                    s_proc, sr,
                    protect_below_hz=_resonance_protect_floor_hz(config.instrument),
                )
                if getattr(config, "needs_resonance_scan", True)
                else []
            )
            if stem_resonant_bands:
                if stereo_source:
                    proc_l, proc_r = apply_dynamic_eq_bands(
                        proc_l, proc_r, bands=stem_resonant_bands, sample_rate=sr,
                    )
                    s_proc = 0.5 * (proc_l + proc_r)
                else:
                    s_proc, _ = apply_dynamic_eq_bands(
                        s_proc, s_proc.copy(), bands=stem_resonant_bands, sample_rate=sr,
                    )
                _r_stem_dyn_eq = stem_resonant_bands[:6]
        except Exception:
            logger.warning("Per-stem dynamic EQ failed for '%s'; continuing without it", name, exc_info=True)

        # 1C. Masking de-mask stage (§6.2/§10.4, opt-in). If this stem is the
        # lower-priority target of an actionable masking relationship, reduce
        # only the overlapping band on THIS stem with a bounded dynamic-EQ move.
        # The protected (higher-priority) source is never touched. Dynamic, so
        # it only pulls the band down while it is actually excessive; capped in
        # frequency count and reduction by the candidate's own bounds.
        move = masking_moves.get(_stem_basename(name))
        if move is not None:
            try:
                band = [{
                    "frequency_hz": move["frequency_hz"],
                    "mean_prominence_db": move["max_reduction_db"],
                }]
                if stereo_source:
                    proc_l, proc_r = apply_dynamic_eq_bands(
                        proc_l, proc_r, bands=band, sample_rate=sr, q=move["q"],
                    )
                    s_proc = 0.5 * (proc_l + proc_r)
                else:
                    s_proc, _ = apply_dynamic_eq_bands(
                        s_proc, s_proc.copy(), bands=band, sample_rate=sr, q=move["q"],
                    )
                _r_masking_move = move
            except Exception:
                logger.warning("Masking de-mask move failed for '%s'; continuing without it", name, exc_info=True)

        # 1E. De-Esser stage (opt-in per plan.apply_deesser). needs_deesser
        # (dsp_engine/dsp_necessity.py) additionally requires this specific
        # stem to be a vocal role with already-elevated sibilance energy —
        # once apply_deesser is ever turned on, this stops it from running
        # on every stem regardless of role/content.
        if (
            getattr(mix_plan, "apply_deesser", False)
            and getattr(config, "deesser", None)
            and getattr(config, "needs_deesser", False)
        ):

            try:
                from ..dsp_engine.deesser import apply_deesser
                d_cfg = config.deesser
                if stereo_source:
                    proc_l, proc_r = apply_deesser(proc_l, proc_r, sample_rate=sr, **d_cfg)
                    s_proc = 0.5 * (proc_l + proc_r)
                else:
                    s_proc, _ = apply_deesser(s_proc, s_proc.copy(), sample_rate=sr, **d_cfg)
            except Exception:
                logger.warning("De-esser failed for '%s'; continuing without it", name, exc_info=True)

        # 1F. Transient Shaper stage (opt-in per config.transient_shaper)
        if getattr(config, "transient_shaper", None):
            try:
                from ..dsp_engine.transient_shaper import apply_transient_shaper
                ts_cfg = config.transient_shaper
                if stereo_source:
                    proc_l, proc_r = apply_transient_shaper(proc_l, proc_r, sample_rate=sr, **ts_cfg)
                    s_proc = 0.5 * (proc_l + proc_r)
                else:
                    s_proc, _ = apply_transient_shaper(s_proc, None, sample_rate=sr, **ts_cfg)
            except Exception:
                logger.warning("Transient shaper stage failed for '%s'; continuing without it", name, exc_info=True)

        # 2. Parametric EQ

        if config.eq_bands:
            eq = ParametricEQ(sample_rate=sr)
            for band in config.eq_bands:
                eq.add_band(band["type"], band["frequency"], band.get("gain_db", 0.0), band.get("q", 0.707))
            if stereo_source:
                proc_l = eq.apply(proc_l, linear_phase=False)
                proc_r = eq.apply(proc_r, linear_phase=False)
                s_proc = 0.5 * (proc_l + proc_r)
            else:
                s_proc = eq.apply(s_proc, linear_phase=False)

        # 3. Compressor
        if config.compressor:
            if stereo_source:
                proc_l, proc_r = _apply_stereo_compressor(
                    proc_l, proc_r, config.compressor, sr
                )
                makeup = float(config.compressor.get("makeup_gain_db", 0.0))
                proc_l = apply_gain(proc_l, makeup)
                proc_r = apply_gain(proc_r, makeup)
                s_proc = 0.5 * (proc_l + proc_r)
            else:
                comp = Compressor(
                    sample_rate=sr,
                    threshold_db=config.compressor["threshold_db"],
                    ratio=config.compressor["ratio"],
                    attack_ms=config.compressor["attack_ms"],
                    release_ms=config.compressor["release_ms"],
                    makeup_gain_db=config.compressor.get("makeup_gain_db", 0.0),
                )
                s_proc = comp.apply(s_proc)

        # 4. Dynamic Gate
        if config.gate:
            gate = Gate(
                sample_rate=sr,
                threshold_db=config.gate.get("threshold_db", -40.0),
                range_db=config.gate.get("range_db", -60.0),
                attack_ms=config.gate.get("attack_ms", 2.0),
                hold_ms=config.gate.get("hold_ms", 50.0),
                release_ms=config.gate.get("release_ms", 150.0),
            )
            if stereo_source:
                detector = np.maximum(np.abs(proc_l), np.abs(proc_r))
                gated_detector = gate.apply(detector)
                gain = np.ones_like(detector)
                active = detector > 1e-12
                gain[active] = np.clip(gated_detector[active] / detector[active], 0.0, 1.0)
                proc_l *= gain
                proc_r *= gain
                s_proc = 0.5 * (proc_l + proc_r)
            else:
                s_proc = gate.apply(s_proc)

        # 5. Per-stem saturation
        if config.saturation_drive_db > 0.0 and config.saturation_mix > 0.0:
            if stereo_source:
                proc_l = apply_saturation(
                    proc_l, drive_db=config.saturation_drive_db,
                    mix=config.saturation_mix, oversample=True,
                )
                proc_r = apply_saturation(
                    proc_r, drive_db=config.saturation_drive_db,
                    mix=config.saturation_mix, oversample=True,
                )
                s_proc = 0.5 * (proc_l + proc_r)
            else:
                s_proc = apply_saturation(
                    s_proc,
                    drive_db=config.saturation_drive_db,
                    mix=config.saturation_mix,
                    oversample=True,
                )

        # 6. Panning (Mono to Stereo)
        s_l, s_r = (
            apply_pan(proc_l, proc_r, config.pan)
            if stereo_source else apply_pan(s_proc, None, config.pan)
        )

        # 7. Stereo Width Adjustment
        if abs(config.stereo_width - 1.0) > 1e-4:
            s_l, s_r = apply_stereo_width(s_l, s_r, config.stereo_width)

        # 7B. Mono-compatibility correction (opt-in, listening-gated). A second
        # width pass is mathematically equivalent to one combined pass -- M/S
        # mid is invariant under width scaling, so applying apply_stereo_width
        # twice with factors w1 then w2 produces the same side signal as one
        # pass with w1*w2 -- so this composes safely with stage 7 above rather
        # than fighting it. Bounded by severity, floored so a flagged stem is
        # narrowed, not fully collapsed to mono.
        severity = mono_compat_flags.get(_stem_basename(name))
        if severity is not None:
            correction_factor = _MONO_COMPAT_CORRECTION_FACTOR[severity]
            s_l, s_r = apply_stereo_width(s_l, s_r, correction_factor)
            _r_mono_compat = {
                "severity": severity,
                "correction_factor": correction_factor,
            }

        # Lead vocal mid carving on backing harmonic instruments. needs_mid_carve
        # (dsp_engine/dsp_necessity.py) skips this for a stem with negligible
        # energy in the 400-2000Hz band the 1.5kHz cut targets (e.g. a
        # bass-heavy pad in one of these role buckets) -- previously ran
        # unconditionally on every stem in these roles regardless of content.
        if (
            has_lead_vocal
            and config.instrument in ("guitar", "keys", "pad", "synth_pad", "accordion", "strings", "brass", "other")
            and getattr(config, "needs_mid_carve", True)
        ):
            s_l, s_r = _apply_vocal_lead_mid_carve(s_l, s_r, sr, freq_hz=1500.0, gain_db=-1.5)

        # Parallel compression for drum punch
        if config.instrument in ("full_drum_bus", "drums", "snare", "percussion"):
            s_l, s_r = _apply_drum_parallel_compression(s_l, s_r, sr, ratio=3.5, threshold_db=-18.0, blend=0.25)

        # Keep the low-frequency foundation centred before stems interact on the bus.
        if config.mono_below_hz > 0.0:
            s_l, s_r = mono_below_frequency(s_l, s_r, config.mono_below_hz, sr)

        return {
            "name": name, "config": config, "s_l": s_l, "s_r": s_r, "s_proc": s_proc,
            "stem_dyn_eq": _r_stem_dyn_eq, "masking_move": _r_masking_move,
            "mono_compat": _r_mono_compat,
        }

    # Parallel map over stems (thread pool; GIL released by scipy/numba/numpy).
    # Warm the numba dynamics/gate JIT once single-threaded so the first parallel
    # batch doesn't race on compilation.
    _smooth_attack_release(np.zeros(4, dtype=np.float64), 0.5, 0.5, 0.0, True)
    _n_workers = _render_worker_count(len(prepared_stems))
    if _n_workers > 1:
        with ThreadPoolExecutor(max_workers=_n_workers) as _ex:
            _stem_results = list(_ex.map(_process_stem, prepared_stems))
    else:
        _stem_results = [_process_stem(sd) for sd in prepared_stems]

    # Serial reduce IN STEM ORDER (map preserves order) so float summation order
    # matches the sequential render exactly -> bit-identical mixdown.
    for _res in _stem_results:
        if _res is None:
            continue
        name = _res["name"]
        config = _res["config"]
        s_l, s_r, s_proc = _res["s_l"], _res["s_r"], _res["s_proc"]
        if _res["stem_dyn_eq"] is not None:
            applied_stem_dynamic_eq[name] = _res["stem_dyn_eq"]
        if _res["masking_move"] is not None:
            applied_masking_moves[name] = _res["masking_move"]
        if _res["mono_compat"] is not None:
            applied_mono_compat_corrections[name] = _res["mono_compat"]
        if stem_audio is not None:
            stem_audio[name] = (s_l.copy(), s_r.copy())
        sum_l += s_l
        sum_r += s_r
        if config.reverb_send > 0:
            reverb_key = (config.reverb_type, config.reverb_decay_s)
            reverb_send_buses.setdefault(reverb_key, np.zeros(num_samples, dtype=np.float64))
            reverb_send_buses[reverb_key] += s_proc * config.reverb_send
        if config.delay_send > 0:
            delay_send_bus += s_proc * config.delay_send

    # 7. Render AUX Sends
    # Reverb Aux Return
    reverb_return_l = np.zeros(num_samples)
    reverb_return_r = np.zeros(num_samples)
    
    reverb_profiles = {
        "plate": {"room_size": 0.5, "damping": 0.3, "pre_delay_ms": 20.0},
        "room": {"room_size": 0.45, "damping": 0.4, "pre_delay_ms": 8.0},
        "hall": {"room_size": 0.8, "damping": 0.3, "pre_delay_ms": 24.0},
    }
    def _render_reverb_item(item):
        (reverb_type, decay_s), send_bus = item
        if not np.any(send_bus != 0):
            return np.zeros(num_samples), np.zeros(num_samples)
        profile = reverb_profiles.get(reverb_type, reverb_profiles["room"])
        reverb = Reverb(
            sample_rate=sr,
            pre_delay_ms=profile["pre_delay_ms"],
            room_size=profile["room_size"],
            decay_time=decay_s,
            damping=profile["damping"],
            wet_dry=1.0,  # AUX return is 100% wet
        )
        return reverb.apply(send_bus)

    active_reverb_items = [item for item in reverb_send_buses.items() if np.any(item[1] != 0)]
    if _n_workers > 1 and len(active_reverb_items) > 1:
        with ThreadPoolExecutor(max_workers=min(_n_workers, len(active_reverb_items))) as _ex:
            reverb_returns = list(_ex.map(_render_reverb_item, active_reverb_items))
    else:
        reverb_returns = [_render_reverb_item(item) for item in active_reverb_items]

    for wet_l, wet_r in reverb_returns:
        reverb_return_l += wet_l
        reverb_return_r += wet_r

    # Delay Aux Return
    delay_return_l = np.zeros(num_samples)
    delay_return_r = np.zeros(num_samples)
    if np.any(delay_send_bus != 0):
        # Default ping pong delay for pop/edm
        ping_pong = mix_plan.genre in ("pop", "edm")
        delay = Delay(
            sample_rate=sr,
            delay_time_ms=300.0,
            feedback=0.4,
            ping_pong=ping_pong,
            wet_dry=1.0,  # AUX return is 100% wet
        )
        delay_return_l, delay_return_r = delay.apply(delay_send_bus)

    # Add AUX returns to master summing bus
    master_l = sum_l + reverb_return_l + delay_return_l
    master_r = sum_r + reverb_return_r + delay_return_r

    # 8. Master Bus Processing -- saturation -> glue compressor -> multiband
    # compressor -> master EQ -> M/S stereo enhancer -> dynamic EQ, extracted
    # into apply_master_bus_chain() (2026-08-01, pure refactor). bus_config
    # stays bound here (not hidden inside the extracted function) because
    # Stage 9's setup right below reads it again.
    applied_dynamic_eq_bands: list[dict] = []
    if bus_config := mix_plan.bus:
        master_l, master_r, applied_dynamic_eq_bands = apply_master_bus_chain(
            master_l, master_r, sr, bus_config, mix_plan.genre,
        )

    # 9. Master Loudness Normalization & Limiting -- closed-loop gain solve +
    # true-peak-safe limiting, extracted into normalize_to_target_lufs()
    # (pure refactor; see that function's docstring for the full mechanism).
    ceiling_db = bus_config.limiter_ceiling_db if bus_config else -1.0
    extra_offset = bus_config.limiter_threshold_db if bus_config else 0.0
    master_l, master_r, final_lufs, loudness_solver_diag = normalize_to_target_lufs(
        master_l, master_r, sr,
        target_lufs=mix_plan.target_lufs,
        ceiling_db=ceiling_db,
        threshold_offset_db=extra_offset,
        apply_proactive_crest_reduction=getattr(mix_plan, "apply_proactive_crest_reduction", False),
    )

    # Apply triangular, noise-shaped dither immediately before the final bit-depth
    # reduction (Stage 7 — never earlier in the chain, so quantisation noise is
    # not baked into upstream processing).
    output_bit_depth = 24
    master_l = apply_noise_shaped_dither(master_l, bit_depth=output_bit_depth)
    master_r = apply_noise_shaped_dither(master_r, bit_depth=output_bit_depth)
    wav_bytes = write_wav(master_l, master_r, sr, bit_depth=output_bit_depth)

    return {
        "mixdown_wav_bytes": wav_bytes,
        "left": master_l,
        "right": master_r,
        "measured_lufs": final_lufs,
        "sample_rate": sr,
        "source_num_samples": num_samples,
        "source_duration_seconds": num_samples / sr,
        "mix_plan": mix_plan,
        "dynamic_eq_bands": applied_dynamic_eq_bands,
        "stem_audio": stem_audio,
        "stem_dynamic_eq_bands": applied_stem_dynamic_eq,
        "masking_corrections": applied_masking_moves,
        "mono_compat_corrections": applied_mono_compat_corrections,
        "loudness_solver": {
            "target_lufs": float(mix_plan.target_lufs),
            **loudness_solver_diag,
        },
    }
