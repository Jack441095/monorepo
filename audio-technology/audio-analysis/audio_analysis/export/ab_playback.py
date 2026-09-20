"""Stage 11.1 — A/B playback between two mix versions.

AutoMix already serves mixdowns from disk through a simple, versioned
file-per-project pattern -- ``business/app/routes/automix_routes.py``'s
``handle_automix_get`` matches ``/api/automix/play/<project_id>`` to the
most recent ``mixdown_v{N}.wav`` under
``data/mix_outputs/<project_id>/`` (written by
``mix_delivery.package_mixdown_delivery``, which increments ``version`` on
every render). That existing pattern already gives every rendered version
of a project a stable, addressable WAV file on disk -- A/B comparison is
naturally "diff two of those files", not a new storage/streaming
architecture.

This module is the audio-prep layer a route like
``/api/automix/ab/<project_id>?a=1&b=2`` would call: given two decoded (or
raw WAV-byte) mix renders, it aligns them, verifies they're comparable,
optionally level-matches them (so the A/B comparison isn't biased by
"louder sounds better" -- a well-known perceptual effect that mastering
engineers routinely correct for during A/B critical listening), and builds
an equal-power crossfade preview buffer a caller can serve as a single WAV
alongside the two individual full-length renders and JSON sync metadata
(sample offset, crossfade point, per-version loudness). No HTTP handler is
added here (the read-only ``automix_routes.py`` is not touched by this
change) -- ``prepare_ab_comparison`` below returns exactly the payload
shape such a route would serialize to JSON + serve alongside WAV bytes.
"""

from __future__ import annotations

import math

import numpy as np

from ..analysis_core.loudness import calculate_loudness_profile
from ..mixdown.stem_prep import read_wav_stereo, write_wav


def _as_stereo_arrays(version: dict) -> tuple[np.ndarray, np.ndarray, int]:
    """Normalize a version input to (left, right, sample_rate) float64 arrays.

    Accepts either:
      - a decoded/rendered dict with ``"left"``, ``"right"``, ``"sample_rate"``
        (the shape ``mix_and_render_stems`` returns), or
      - a raw WAV-bytes dict with ``"wav_bytes"`` (decoded via
        ``stem_prep.read_wav_stereo``, the same decoder ``mix_delivery`` and
        the rest of the pipeline already use).
    """
    if "left" in version and "right" in version and "sample_rate" in version:
        left = np.asarray(version["left"], dtype=np.float64)
        right = np.asarray(version["right"], dtype=np.float64)
        sample_rate = int(version["sample_rate"])
        return left, right, sample_rate

    wav_bytes = version.get("wav_bytes") or version.get("mixdown_wav_bytes")
    if wav_bytes is None:
        raise ValueError(
            "A/B version must provide either 'left'/'right'/'sample_rate' or "
            "'wav_bytes'/'mixdown_wav_bytes'."
        )
    decoded = read_wav_stereo(wav_bytes)
    left = np.asarray(decoded["left"], dtype=np.float64)
    right = np.asarray(decoded["right"], dtype=np.float64)
    return left, right, int(decoded["sample_rate"])


def align_ab_buffers(version_a: dict, version_b: dict) -> dict:
    """Decode and align two mix versions to a common sample rate and length.

    Both versions must share a sample rate (AutoMix always renders at the
    project's input sample rate, so two versions of the *same* project are
    expected to match; a mismatch is a real error worth surfacing rather
    than silently resampling one version and subtly changing what's being
    compared).

    Length is trimmed to the shorter of the two (rather than zero-padded)
    so no artificial silence is introduced into the comparison -- if the
    two versions differ in length (e.g. a revision that also trimmed
    silence), the comparison covers only the overlapping duration and that
    fact is reported back in the result.
    """
    left_a, right_a, sr_a = _as_stereo_arrays(version_a)
    left_b, right_b, sr_b = _as_stereo_arrays(version_b)

    if sr_a != sr_b:
        raise ValueError(
            f"A/B versions have different sample rates ({sr_a} vs {sr_b}); "
            "cannot align without resampling one of them, which would change "
            "what is being compared."
        )

    len_a = min(len(left_a), len(right_a))
    len_b = min(len(left_b), len(right_b))
    common_len = min(len_a, len_b)
    if common_len <= 0:
        raise ValueError("A/B versions contain no comparable audio (zero-length overlap).")

    return {
        "left_a": left_a[:common_len],
        "right_a": right_a[:common_len],
        "left_b": left_b[:common_len],
        "right_b": right_b[:common_len],
        "sample_rate": sr_a,
        "length_samples": common_len,
        "length_a_samples": len_a,
        "length_b_samples": len_b,
        "trimmed_samples": max(len_a, len_b) - common_len,
    }


def _integrated_lufs(left: np.ndarray, right: np.ndarray, sample_rate: int) -> float:
    profile = calculate_loudness_profile(left.tolist(), right.tolist(), sample_rate)
    return float(profile.get("integrated_lufs", -99.0))


def level_match(
    left_a: np.ndarray,
    right_a: np.ndarray,
    left_b: np.ndarray,
    right_b: np.ndarray,
    sample_rate: int,
) -> dict:
    """Gain-match B to A's integrated loudness (BS.1770/EBU R128 LUFS).

    A/B testing is well documented to be biased toward whichever version is
    louder, independent of which one is actually better-processed -- this
    is why level-matching is standard practice before any critical A/B
    listening comparison. We measure both versions' integrated LUFS (the
    same K-weighted algorithm the renderer already uses for its own target
    loudness) and apply a static gain to B so both land at the same
    integrated loudness as A, leaving A untouched as the reference.
    """
    lufs_a = _integrated_lufs(left_a, right_a, sample_rate)
    lufs_b = _integrated_lufs(left_b, right_b, sample_rate)

    if lufs_a <= -99.0 or lufs_b <= -99.0:
        # Effectively silent material -- nothing meaningful to level-match.
        gain_db = 0.0
    else:
        gain_db = lufs_a - lufs_b

    gain_linear = 10.0 ** (gain_db / 20.0)
    return {
        "left_b": left_b * gain_linear,
        "right_b": right_b * gain_linear,
        "lufs_a": round(lufs_a, 2),
        "lufs_b_original": round(lufs_b, 2),
        "applied_gain_db": round(gain_db, 3),
    }


def equal_power_crossfade(
    left_a: np.ndarray,
    right_a: np.ndarray,
    left_b: np.ndarray,
    right_b: np.ndarray,
    sample_rate: int,
    crossfade_point_s: float,
    crossfade_ms: float = 50.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a single preview buffer: A up to the crossfade point, then an
    equal-power (constant-power) crossfade into B, then B for the remainder.

    An equal-power (quarter-sine/cosine) curve is used rather than a linear
    fade because a linear crossfade of two decorrelated signals produces a
    perceptible dip in loudness at the midpoint (the RMS sum of two linear
    ramps summing to 1.0 is less than 1.0 partway through); the
    cos/sin quarter-wave pair keeps ``gain_a**2 + gain_b**2 == 1`` at every
    sample, which is the standard crossfade curve used in DAWs (Pro Tools,
    Logic, Ableton) for exactly this reason.
    """
    n = len(left_a)
    fade_samples = max(1, int(round((crossfade_ms / 1000.0) * sample_rate)))
    start = max(0, min(int(round(crossfade_point_s * sample_rate)), n))
    end = min(start + fade_samples, n)
    actual_fade_samples = end - start

    out_l = np.empty(n, dtype=np.float64)
    out_r = np.empty(n, dtype=np.float64)

    # Pre-crossfade: pure A.
    out_l[:start] = left_a[:start]
    out_r[:start] = right_a[:start]

    # Crossfade region: equal-power A -> B.
    if actual_fade_samples > 0:
        theta = np.linspace(0.0, math.pi / 2.0, actual_fade_samples, endpoint=True)
        gain_a = np.cos(theta)
        gain_b = np.sin(theta)
        out_l[start:end] = left_a[start:end] * gain_a + left_b[start:end] * gain_b
        out_r[start:end] = right_a[start:end] * gain_a + right_b[start:end] * gain_b

    # Post-crossfade: pure B.
    out_l[end:] = left_b[end:]
    out_r[end:] = right_b[end:]

    return out_l, out_r


def detect_discontinuities(
    left: np.ndarray,
    right: np.ndarray,
    *,
    window_start: int = 0,
    window_end: int | None = None,
    jump_threshold: float = 0.15,
) -> dict:
    """Detect clicks/pops (sample-to-sample discontinuities) in a region.

    A "click" is a sample-to-sample jump much larger than the signal's
    typical local jump size -- i.e. an outlier in the first difference of
    the waveform. We compare each per-sample delta in ``[window_start,
    window_end)`` against ``jump_threshold`` in absolute amplitude
    (samples are normalised to [-1, 1], so 0.15 is an audible discontinuity
    for anything but the loudest transient material) *and* against a
    local-median-based outlier check, so this catches an abrupt crossfade
    seam without flagging a normal fast transient (e.g. a kick drum
    attack), which is gradual over several samples rather than a single-
    sample jump.
    """
    window_end = len(left) if window_end is None else min(window_end, len(left))
    seg_l = left[window_start:window_end]
    seg_r = right[window_start:window_end]
    if len(seg_l) < 2:
        return {"clicks_found": 0, "max_jump": 0.0, "click_indices": []}

    delta_l = np.abs(np.diff(seg_l))
    delta_r = np.abs(np.diff(seg_r))
    delta = np.maximum(delta_l, delta_r)

    median_delta = float(np.median(delta)) if delta.size else 0.0
    outlier_threshold = max(jump_threshold, median_delta * 8.0 + 1e-6)

    click_mask = delta > outlier_threshold
    click_indices = (np.nonzero(click_mask)[0] + window_start).tolist()

    return {
        "clicks_found": int(click_mask.sum()),
        "max_jump": float(delta.max()) if delta.size else 0.0,
        "median_jump": median_delta,
        "outlier_threshold_used": outlier_threshold,
        "click_indices": click_indices[:50],  # cap for payload size
    }


def prepare_ab_comparison(
    version_a: dict,
    version_b: dict,
    *,
    label_a: str = "A",
    label_b: str = "B",
    crossfade_point_s: float | None = None,
    crossfade_ms: float = 50.0,
    level_match_enabled: bool = True,
    output_bit_depth: int = 24,
) -> dict:
    """Prepare an A/B comparison payload for two rendered mix versions.

    Returns a dict shaped like what an ``/api/automix/ab/<project_id>``
    route would serialize: full-length WAV bytes for each version
    (independently switchable, "instant switch" A/B), a single crossfade
    preview WAV (A -> equal-power crossfade -> B), and JSON-safe sync
    metadata (sample alignment, crossfade point, per-version loudness, and
    a discontinuity check across the crossfade seam so a caller can assert
    the splice is actually clean before shipping it).
    """
    aligned = align_ab_buffers(version_a, version_b)
    sample_rate = aligned["sample_rate"]
    n = aligned["length_samples"]
    duration_s = n / sample_rate

    left_a, right_a = aligned["left_a"], aligned["right_a"]
    left_b, right_b = aligned["left_b"], aligned["right_b"]

    level_match_info = None
    if level_match_enabled:
        matched = level_match(left_a, right_a, left_b, right_b, sample_rate)
        left_b, right_b = matched["left_b"], matched["right_b"]
        # Guard against the matched gain pushing B past full scale, which
        # would otherwise silently clip when written to WAV.
        peak = float(np.max(np.abs(np.concatenate([left_b, right_b])))) if n else 0.0
        if peak > 1.0:
            safety = 1.0 / peak
            left_b = left_b * safety
            right_b = right_b * safety
            matched["clip_safety_gain_db"] = round(20.0 * math.log10(safety), 3)
        else:
            matched["clip_safety_gain_db"] = 0.0
        level_match_info = matched

    if crossfade_point_s is None:
        crossfade_point_s = duration_s / 2.0
    crossfade_point_s = max(0.0, min(crossfade_point_s, duration_s))

    preview_l, preview_r = equal_power_crossfade(
        left_a, right_a, left_b, right_b, sample_rate, crossfade_point_s, crossfade_ms
    )

    fade_samples = max(1, int(round((crossfade_ms / 1000.0) * sample_rate)))
    seam_start = max(0, int(round(crossfade_point_s * sample_rate)) - 8)
    seam_end = min(n, int(round(crossfade_point_s * sample_rate)) + fade_samples + 8)
    discontinuity_report = detect_discontinuities(preview_l, preview_r, window_start=seam_start, window_end=seam_end)

    wav_a = write_wav(left_a.tolist(), right_a.tolist(), sample_rate, bit_depth=output_bit_depth)
    wav_b = write_wav(left_b.tolist(), right_b.tolist(), sample_rate, bit_depth=output_bit_depth)
    wav_preview = write_wav(preview_l.tolist(), preview_r.tolist(), sample_rate, bit_depth=output_bit_depth)

    return {
        "label_a": label_a,
        "label_b": label_b,
        "sample_rate": sample_rate,
        "duration_seconds": round(duration_s, 3),
        "length_samples": n,
        "sync_metadata": {
            "length_a_samples": aligned["length_a_samples"],
            "length_b_samples": aligned["length_b_samples"],
            "trimmed_samples": aligned["trimmed_samples"],
            "sample_offset": 0,  # both versions decode/render from t=0; no shift needed
        },
        "crossfade_point_s": round(crossfade_point_s, 3),
        "crossfade_ms": crossfade_ms,
        "level_match": level_match_info,
        "discontinuity_check": discontinuity_report,
        "wav_bytes_a": wav_a,
        "wav_bytes_b": wav_b,
        "wav_bytes_crossfade_preview": wav_preview,
    }
