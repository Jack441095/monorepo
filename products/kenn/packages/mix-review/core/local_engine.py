"""KENN-owned local Mix Review analysis engine.

Deterministic WAV analysis for a bounded set of qualified fault families. It
uses an optional NumPy accelerator when available and keeps a Python
standard-library fallback, with no runtime dependency on any external
``Audio_Too`` checkout, ``audio_analysis`` package, or network service.

Every measurement here is a plain, verifiable signal-processing calculation
(peak level, RMS, run-length clip detection, channel correlation). None of
it is a substitute for full ITU-R BS.1770 loudness metering, perceptual
masking analysis, or genre-aware critique -- those are explicitly listed in
``NOT_EVALUATED_FAULT_FAMILIES`` below and the engine abstains on them rather
than guessing. See docs/KENN_BETA_GAP_MATRIX.md for the qualification status
of each fault family.
"""

from __future__ import annotations

import io
import math
import os
import struct
import uuid
import wave
from array import array
from datetime import datetime, timezone
from typing import Any

try:  # Optional accelerator; the standard-library fallback remains supported.
    import numpy as _np
except ImportError:  # pragma: no cover - exercised only in minimal environments.
    _np = None

try:  # Calibrated loudness/true-peak needs numpy+scipy; abstain honestly if absent.
    import pyloudnorm as _pyln
except ImportError:  # pragma: no cover - exercised only in minimal environments.
    _pyln = None

try:
    from scipy.signal import resample_poly as _resample_poly
except ImportError:  # pragma: no cover - exercised only in minimal environments.
    _resample_poly = None

try:
    from scipy.io import wavfile as _scipy_wavfile
except ImportError:  # pragma: no cover - exercised only in minimal environments.
    _scipy_wavfile = None

ANALYSIS_VERSION = "kenn.mix_review.local_engine.v1"
RECEIPT_SCHEMA = "kenn.mix_review.local_analysis.v1"

DECODABLE_SUFFIXES = frozenset({".wav"})
DEFAULT_MIX_GOAL = "general"
MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # ~150MB: generous for a stereo mix, bounded for pure-Python decode time

_SUPPORTED_SAMPLE_WIDTHS_BYTES = (2, 3)  # 16-bit and 24-bit signed PCM only
_SUPPORTED_SAMPLE_WIDTHS_BYTES = (2, 3, 4)  # 16-bit, 24-bit integer PCM, and 32-bit float WAV

# --- fault-family thresholds -------------------------------------------------
CLIP_AMPLITUDE_THRESHOLD = 10 ** (-0.3 / 20.0)  # ~0.966, i.e. within 0.3 dB of full scale
CLIP_MIN_RUN_SAMPLES = 3           # consecutive full-scale samples before we call it clipping, not one hot transient
LOW_HEADROOM_PEAK_DBFS = -1.0      # peak above this is "hot" / low headroom
SILENCE_AMPLITUDE_THRESHOLD = 10 ** (-60.0 / 20.0)
SILENCE_FRACTION_FLAG = 0.98       # 98%+ of samples below the silence threshold -> flag
MIN_DURATION_SECONDS = 1.0         # below this, most metrics abstain rather than risk noise
IMBALANCE_FLAG_DB = 3.0
PHASE_CORRELATION_FLAG = -0.5      # Pearson correlation below this suggests a polarity/phase problem
MONO_SUM_DROP_FLAG_DB = 3.0
HOT_LOUDNESS_ESTIMATE_DBFS = -14.0  # unweighted RMS proxy threshold, not a calibrated LUFS target
DC_OFFSET_FLAG = 0.02
TRUE_PEAK_OVERSAMPLE_FACTOR = 4  # ITU-R BS.1770-4 Annex 2 minimum oversampling ratio
TARGET_INTEGRATED_LUFS = -14.0  # common streaming reference; informational only, not a pass/fail gate
TRUE_PEAK_CEILING_DBTP = -1.0   # common delivery ceiling; informational only, not a pass/fail gate

QUALIFIED_FAULT_FAMILIES = (
    "clipping",
    "headroom",
    "silence_or_truncation",
    "channel_imbalance",
    "phase_polarity_mono_compatibility",
    "dc_offset",
    "loudness_estimate",
    "calibrated_lufs_bs1770",
    "true_peak_intersample",
)

NOT_EVALUATED_FAULT_FAMILIES = (
    "masking",
    "eq_tonal_balance",
    "dynamics_arrangement",
    "genre_context",
)

GLOBAL_LIMITATIONS = (
    "loudness_estimate remains an unweighted RMS proxy, not calibrated LUFS -- use the "
    "separate calibrated_lufs_bs1770/true_peak_intersample findings for a real ITU-R "
    "BS.1770-4 integrated LUFS/LRA and 4x-oversampled true-peak measurement (both abstain "
    "explicitly if the optional pyloudnorm/scipy dependency is not installed). "
    "No masking, tonal-balance, arrangement, dynamics, or genre-context analysis is "
    "performed -- those fault families are explicitly not evaluated. Only mono or "
    "stereo 16-bit/24-bit PCM WAV is supported."
    "stereo 16-bit/24-bit PCM or 32-bit float WAV is supported."
)

_EVIDENCE_METRIC_UNITS = {
    "peak_dbfs": "dBFS",
    "rms_dbfs": "dBFS",
    "crest_db": "dB",
    "transient_ratio": "ratio",
    "clipped_samples": "samples",
    "stereo_correlation": "correlation",
    "stereo_width": "ratio",
    "low_energy": "linear energy",
    "mid_energy": "linear energy",
    "high_energy": "linear energy",
    "integrated_lufs": "LUFS",
    "loudness_range_lu": "LU",
    "true_peak_dbtp": "dBTP",
}


def _evidence_packet(metrics: dict[str, Any]) -> dict[str, Any]:
    """Build the stable language-neutral packet shared with the native plug-in."""
    facts: list[dict[str, Any]] = []
    for name, unit in _EVIDENCE_METRIC_UNITS.items():
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(float(value)):
            continue
        facts.append({
            "name": name,
            "value": float(value),
            "unit": unit,
            "source": "mix_review_upload",
            "confidence": "measured",
        })
    if not facts:
        facts.append({
            "name": "analysis_status",
            "value": "abstained",
            "unit": "",
            "source": "mix_review_upload",
            "confidence": "status",
        })
    return {
        "schema": "kenn.evidence.v1",
        "source": "mix_review_upload",
        "captured_at_age_seconds": None,
        "observed_at_epoch": None,
        "facts": facts,
        "limitations": [
            "Measurements apply to the uploaded render reviewed by Mix Review, not to unuploaded revisions.",
            "A stereo render cannot prove individual track, routing, plug-in, or automation causes.",
            "Masking, tonal balance, arrangement, dynamics, and genre context are not established by this packet.",
        ],
    }


class UnsupportedAudioError(ValueError):
    pass


def _parse_wav(payload: bytes) -> tuple[int, int, int, bytes, int]:
    """Parse WAV container metadata and raw audio frames.

    Returns (channels, sampwidth, framerate, raw_data, audio_format).
    audio_format: 1 = PCM, 3 = IEEE_FLOAT.
    """
    if len(payload) < 12 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise wave.Error("file does not start with RIFF/WAVE id")
    pos = 12
    fmt_info = None
    data_bytes = None
    total_len = len(payload)
    while pos + 8 <= total_len:
        chunk_id = payload[pos : pos + 4]
        chunk_size = struct.unpack("<I", payload[pos + 4 : pos + 8])[0]
        chunk_data = payload[pos + 8 : pos + 8 + chunk_size]
        if chunk_id == b"fmt " and len(chunk_data) >= 16:
            audio_format, channels, framerate, _byte_rate, _block_align, bits_per_sample = struct.unpack(
                "<HHIIHH", chunk_data[:16]
            )
            if audio_format == 0xFFFE and len(chunk_data) >= 26:
                audio_format = struct.unpack("<H", chunk_data[24:26])[0]
            fmt_info = (channels, bits_per_sample // 8, framerate, audio_format)
        elif chunk_id == b"data":
            data_bytes = chunk_data
        pos += 8 + chunk_size + (chunk_size % 2)

    if fmt_info is None:
        raise wave.Error("fmt chunk missing in WAV file")
    if data_bytes is None:
        raise wave.Error("data chunk missing in WAV file")

    channels, sampwidth, framerate, audio_format = fmt_info
    return channels, sampwidth, framerate, data_bytes, audio_format


def validate_wav_upload(payload: bytes, filename: str, *, label: str = "Local mix") -> dict[str, Any]:
    """Cheap structural validation before any measurement runs."""
    if not payload:
        return {"ok": False, "error": f"{label} is empty."}
    try:
        channels, sampwidth, framerate, data_bytes, audio_format = _parse_wav(payload)
    except (wave.Error, EOFError, struct.error) as exc:
        return {"ok": False, "error": f"{label} could not be parsed as a valid WAV file: {exc}"}
    if channels not in (1, 2):
        return {
            "ok": False,
            "error": f"Unsupported channel count ({channels}); only mono or stereo WAV is supported in this build.",
        }
    if audio_format not in (1, 3):
        return {
            "ok": False,
            "error": f"Unsupported audio format tag ({audio_format}); only PCM and IEEE float WAV are supported.",
        }
    if sampwidth not in _SUPPORTED_SAMPLE_WIDTHS_BYTES:
        return {
            "ok": False,
            "error": (
                f"Unsupported bit depth ({sampwidth * 8}-bit); only 16-bit or 24-bit "
                "integer PCM WAV and 32-bit float WAV are supported in this build."
            ),
        }
    if framerate <= 0 or len(data_bytes) == 0:
        return {"ok": False, "error": f"{label} has no audio frames."}
    return {"ok": True}


def _decode_channels(payload: bytes) -> tuple[list[array], int, int]:
    # The Mix Review engine keeps its audited Python decoder as the default,
    # but can opt into the same native PCM decoder used by the spectral path.
    # This avoids the Python integer-to-float64 decode pass on large uploads;
    # the native loudness path can keep these float32 channels end-to-end.
    # The exact parser/error fallback remains in place when the optional wheel
    # is absent or rejects the container.
    if os.environ.get("KENN_DSP_MIX_REVIEW_DECODE_NATIVE", "0").strip().lower() in {
        "1", "true", "on", "yes",
    }:
        try:
            from kenn.core.native_fft import decode_pcm

            native_result = decode_pcm(payload)
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            native_result = None
        if native_result is not None and _np is not None:
            try:
                native_channels = native_result["channels"]
                native_rate = int(native_result["sample_rate"])
                native_count = int(native_result["channel_count"])
                if native_count in (1, 2) and native_rate > 0 and len(native_channels) == native_count:
                    channels = [
                        _np.asarray(channel, dtype=_np.float32, order="C")
                        for channel in native_channels
                    ]
                    if channels and all(channel.ndim == 1 and channel.size for channel in channels):
                        if all(channel.shape == channels[0].shape for channel in channels[1:]):
                            return channels, native_rate, native_count
            except (KeyError, TypeError, ValueError):
                # Fall through to the stable Python parser below.
                pass

    channels, sampwidth, framerate, raw, audio_format = _parse_wav(payload)

    if sampwidth == 2:
        if _np is not None:
            values = _np.frombuffer(raw[: (len(raw) // 2) * 2], dtype="<i2").astype(_np.float64)
            values /= 32768.0
            return [values[channel::channels] for channel in range(channels)], framerate, channels
        ints = array("h")
        ints.frombytes(raw[: (len(raw) // 2) * 2])
        scale = 32768.0
        # Build each channel directly from its interleaved samples. This
        # avoids a temporary flattened list plus a second redistribution pass
        # over every frame, which dominates the dependency-free hot path.
        channel_data = [
            array("d", (ints[index] / scale for index in range(channel, len(ints), channels)))
            for channel in range(channels)
        ]
    elif sampwidth == 3:
        scale = 8388608.0
        usable = (len(raw) // 3) * 3
        if _np is not None:
            # Real-world 24-bit files (common for professional mixing/
            # mastering, unlike the 16-bit-only synthetic benchmark
            # fixtures) previously had no vectorized path at all -- only
            # the per-sample Python loop below, ~56ms per second of audio
            # measured against a real ~200s mixdown. Found by testing
            # against real corpus files rather than only the 2-second
            # synthetic fixtures, which are 16-bit and never exercised
            # this path's performance. Combines each 24-bit little-endian
            # sample's 3 bytes the same way the loop below does (b0 |
            # b1<<8 | b2<<16, then sign-extend), just vectorized.
            frame_bytes = _np.frombuffer(raw[:usable], dtype=_np.uint8).reshape(-1, 3)
            combined = (
                frame_bytes[:, 0].astype(_np.int32)
                | (frame_bytes[:, 1].astype(_np.int32) << 8)
                | (frame_bytes[:, 2].astype(_np.int32) << 16)
            )
            combined = _np.where(combined & 0x800000, combined - 0x1000000, combined)
            values = combined.astype(_np.float64) / scale
            return [values[channel::channels] for channel in range(channels)], framerate, channels
        channel_data = [array("d") for _ in range(channels)]
        frame_width = channels * 3
        for frame_offset in range(0, usable, frame_width):
            for channel in range(channels):
                offset = frame_offset + channel * 3
                if offset + 2 >= usable:
                    break
                b0, b1, b2 = raw[offset], raw[offset + 1], raw[offset + 2]
                value = b0 | (b1 << 8) | (b2 << 16)
                if value & 0x800000:
                    value -= 0x1000000
                channel_data[channel].append(value / scale)
    elif sampwidth == 4:
        usable = (len(raw) // 4) * 4
        if audio_format == 3:  # IEEE 754 32-bit float
            if _np is not None:
                values = _np.frombuffer(raw[:usable], dtype="<f4").astype(_np.float64)
                return [values[channel::channels] for channel in range(channels)], framerate, channels
            floats = array("f")
            floats.frombytes(raw[:usable])
            channel_data = [
                array("d", (float(floats[index]) for index in range(channel, len(floats), channels)))
                for channel in range(channels)
            ]
        elif audio_format == 1:  # 32-bit integer PCM
            scale = 2147483648.0
            if _np is not None:
                values = _np.frombuffer(raw[:usable], dtype="<i4").astype(_np.float64) / scale
                return [values[channel::channels] for channel in range(channels)], framerate, channels
            ints = array("i")
            ints.frombytes(raw[:usable])
            channel_data = [
                array("d", (ints[index] / scale for index in range(channel, len(ints), channels)))
                for channel in range(channels)
            ]
        else:
            raise UnsupportedAudioError(f"unsupported 32-bit audio format: {audio_format}")
    else:
        raise UnsupportedAudioError(f"unsupported sample width: {sampwidth} bytes")

    return channel_data, framerate, channels


def _dbfs(linear: float) -> float | None:
    if linear <= 0:
        return None
    return 20.0 * math.log10(linear)


def _rms(values: array) -> float:
    if len(values) == 0:
        return 0.0
    if _np is not None and isinstance(values, _np.ndarray):
        return float(_np.sqrt(_np.mean(values * values)))
    total = 0.0
    for value in values:
        total += value * value
    return math.sqrt(total / len(values))


def _peak(values: array) -> float:
    if _np is not None and isinstance(values, _np.ndarray):
        return float(_np.max(_np.abs(values))) if values.size else 0.0
    peak = 0.0
    for value in values:
        magnitude = value if value >= 0 else -value
        if magnitude > peak:
            peak = magnitude
    return peak


def _mean(values: array) -> float:
    if len(values) == 0:
        return 0.0
    if _np is not None and isinstance(values, _np.ndarray):
        return float(_np.mean(values))
    return sum(values) / len(values)


def _clip_runs(values: array, threshold: float, min_run: int) -> tuple[int, int]:
    """Return (clipped_sample_count, run_count) for consecutive near-full-scale samples."""
    if _np is not None and isinstance(values, _np.ndarray):
        mask = _np.abs(values) >= threshold
        if not bool(mask.any()):
            return 0, 0
        starts = _np.flatnonzero(mask & _np.r_[True, ~mask[:-1]])
        ends = _np.flatnonzero(mask & _np.r_[~mask[1:], True])
        lengths = ends - starts + 1
        qualified = lengths[lengths >= min_run]
        return int(qualified.sum()), int(qualified.size)
    clipped = 0
    runs = 0
    run_length = 0
    for value in values:
        magnitude = value if value >= 0 else -value
        if magnitude >= threshold:
            run_length += 1
        else:
            if run_length >= min_run:
                runs += 1
                clipped += run_length
            run_length = 0
    if run_length >= min_run:
        runs += 1
        clipped += run_length
    return clipped, runs


def _finding(
    family: str,
    *,
    detected: bool,
    severity: str,
    confidence: float,
    evidence: dict[str, Any],
    explanation: str,
    suggested_next_step: str,
    limitations: str = "",
) -> dict[str, Any]:
    return {
        "fault_family": family,
        "detected": detected,
        "severity": severity,
        "confidence": round(confidence, 2),
        "evidence": evidence,
        "explanation": explanation,
        "suggested_next_step": suggested_next_step,
        "limitations": limitations,
    }


def _abstained_finding(family: str, reason: str) -> dict[str, Any]:
    return _finding(
        family,
        detected=False,
        severity="unknown",
        confidence=0.0,
        evidence={},
        explanation=f"KENN abstained on {family}: {reason}",
        suggested_next_step="Not applicable; no finding was made for this fault family.",
        limitations=reason,
    )


def analyze_wav(
    payload: bytes,
    *,
    filename: str,
    mix_goal: str = DEFAULT_MIX_GOAL,
    light: bool = False,
    include_bands: bool = True,
) -> dict[str, Any]:
    """Analyse one WAV file's bytes and return a measured, evidence-backed report.

    ``light``/``include_bands`` are accepted for interface compatibility with
    the historical adapter contract; this engine does not implement banded
    (per-frequency) analysis, so ``include_bands`` is recorded but not acted
    on -- see NOT_EVALUATED_FAULT_FAMILIES.
    """
    try:
        channel_data, framerate, channels = _decode_channels(payload)
    except (UnsupportedAudioError, struct.error, wave.Error) as exc:
        return {"ok": False, "error": f"Could not decode audio: {type(exc).__name__}: {exc}"}

    total_frames = len(channel_data[0]) if channel_data else 0
    duration_seconds = total_frames / framerate if framerate else 0.0

    findings: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}

    if duration_seconds < MIN_DURATION_SECONDS:
        for family in QUALIFIED_FAULT_FAMILIES:
            findings.append(
                _abstained_finding(
                    family,
                    f"audio is only {duration_seconds:.2f}s long; KENN requires at least "
                    f"{MIN_DURATION_SECONDS:.0f}s for a reliable measurement.",
                )
            )
    else:
        peaks = [_peak(ch) for ch in channel_data]
        rms_values = [_rms(ch) for ch in channel_data]
        overall_peak = max(peaks) if peaks else 0.0
        overall_peak_dbfs = _dbfs(overall_peak)
        metrics["sample_peak_dbfs"] = round(overall_peak_dbfs, 2) if overall_peak_dbfs is not None else None
        metrics["peak_dbfs"] = metrics["sample_peak_dbfs"]
        metrics["per_channel_peak_dbfs"] = [round(v, 2) if v is not None else None for v in (_dbfs(p) for p in peaks)]
        metrics["per_channel_rms_dbfs"] = [round(v, 2) if v is not None else None for v in (_dbfs(r) for r in rms_values)]
        avg_rms_val = sum(rms_values) / len(rms_values) if rms_values else None
        avg_rms_dbfs_val = _dbfs(avg_rms_val) if avg_rms_val is not None else None
        metrics["rms_dbfs"] = round(avg_rms_dbfs_val, 2) if avg_rms_dbfs_val is not None else None

        crest_db = None
        if overall_peak_dbfs is not None:
            avg_rms_dbfs = _dbfs(sum(rms_values) / len(rms_values)) if rms_values else None
            if avg_rms_dbfs is not None:
                crest_db = overall_peak_dbfs - avg_rms_dbfs
                metrics["crest_factor_db"] = round(crest_db, 2)
                metrics["crest_db"] = metrics["crest_factor_db"]


        clip_total = 0
        clip_runs_total = 0
        for ch in channel_data:
            clipped, runs = _clip_runs(ch, CLIP_AMPLITUDE_THRESHOLD, CLIP_MIN_RUN_SAMPLES)
            clip_total += clipped
            clip_runs_total += runs
        clip_fraction = clip_total / (total_frames * channels) if total_frames and channels else 0.0
        clipping_detected = clip_runs_total > 0
        findings.append(
            _finding(
                "clipping",
                detected=clipping_detected,
                severity="high" if clip_fraction > 0.001 else ("low" if clipping_detected else "none"),
                confidence=0.9 if clipping_detected else 0.85,
                evidence={
                    "clipped_sample_count": clip_total,
                    "clip_run_count": clip_runs_total,
                    "clipped_fraction": round(clip_fraction, 6),
                    "threshold_dbfs": -0.3,
                    "min_run_samples": CLIP_MIN_RUN_SAMPLES,
                },
                explanation=(
                    f"Found {clip_runs_total} run(s) of {CLIP_MIN_RUN_SAMPLES}+ consecutive samples within 0.3 dB "
                    f"of full scale ({clip_total} samples total, {clip_fraction * 100:.4f}% of all samples)."
                    if clipping_detected
                    else "No sustained runs of near-full-scale samples were found."
                ),
                suggested_next_step=(
                    "Reduce gain into the loudest section(s) or check for a clipped source/plugin stage, "
                    "then re-render and re-analyse."
                    if clipping_detected
                    else "No action needed for clipping."
                ),
                limitations="Detects sustained near-full-scale runs, not isolated inter-sample or analogue-style saturation.",
            )
        )

        low_headroom = overall_peak_dbfs is not None and overall_peak_dbfs > LOW_HEADROOM_PEAK_DBFS
        findings.append(
            _finding(
                "headroom",
                detected=bool(low_headroom),
                severity="medium" if low_headroom else "none",
                confidence=0.85,
                evidence={"sample_peak_dbfs": metrics.get("sample_peak_dbfs"), "flag_threshold_dbfs": LOW_HEADROOM_PEAK_DBFS},
                explanation=(
                    f"Sample peak is {overall_peak_dbfs:.2f} dBFS, above the {LOW_HEADROOM_PEAK_DBFS:.1f} dBFS "
                    "flag threshold, leaving little headroom before a mastering/limiting stage."
                    if low_headroom
                    else f"Sample peak is {overall_peak_dbfs:.2f} dBFS, within a safe headroom margin."
                    if overall_peak_dbfs is not None
                    else "Peak could not be measured."
                ),
                suggested_next_step=(
                    "Leave at least 1 dB of peak headroom before any mastering or limiting stage."
                    if low_headroom
                    else "No action needed for headroom."
                ),
                limitations="Sample-peak only; does not estimate inter-sample (true) peak.",
            )
        )

        silent_fraction = 0.0
        for ch in channel_data:
            if _np is not None and isinstance(ch, _np.ndarray):
                fraction = (
                    float(_np.mean(_np.abs(ch) < SILENCE_AMPLITUDE_THRESHOLD))
                    if ch.size
                    else 0.0
                )
            else:
                below = sum(1 for v in ch if (v if v >= 0 else -v) < SILENCE_AMPLITUDE_THRESHOLD)
                fraction = below / len(ch) if len(ch) else 0.0
            silent_fraction = max(silent_fraction, fraction)
        is_silent_or_truncated = silent_fraction >= SILENCE_FRACTION_FLAG
        findings.append(
            _finding(
                "silence_or_truncation",
                detected=is_silent_or_truncated,
                severity="high" if is_silent_or_truncated else "none",
                confidence=0.9,
                evidence={"max_channel_silent_fraction": round(silent_fraction, 4), "duration_seconds": round(duration_seconds, 3)},
                explanation=(
                    f"At least one channel is below -60 dBFS for {silent_fraction * 100:.1f}% of the file."
                    if is_silent_or_truncated
                    else "Audio content was present through the file (not effectively silent)."
                ),
                suggested_next_step=(
                    "Confirm the correct file/stem was exported and that the render was not truncated or muted."
                    if is_silent_or_truncated
                    else "No action needed."
                ),
            )
        )

        if channels == 2:
            left, right = channel_data[0], channel_data[1]
            left_rms_dbfs = _dbfs(rms_values[0])
            right_rms_dbfs = _dbfs(rms_values[1])
            imbalance_db = None
            if left_rms_dbfs is not None and right_rms_dbfs is not None:
                imbalance_db = abs(left_rms_dbfs - right_rms_dbfs)
            imbalance_detected = imbalance_db is not None and imbalance_db >= IMBALANCE_FLAG_DB
            findings.append(
                _finding(
                    "channel_imbalance",
                    detected=bool(imbalance_detected),
                    severity="medium" if imbalance_detected else "none",
                    confidence=0.8,
                    evidence={
                        "left_rms_dbfs": round(left_rms_dbfs, 2) if left_rms_dbfs is not None else None,
                        "right_rms_dbfs": round(right_rms_dbfs, 2) if right_rms_dbfs is not None else None,
                        "imbalance_db": round(imbalance_db, 2) if imbalance_db is not None else None,
                        "flag_threshold_db": IMBALANCE_FLAG_DB,
                    },
                    explanation=(
                        f"Left/right RMS level differs by {imbalance_db:.2f} dB across the whole file, "
                        f"at or above the {IMBALANCE_FLAG_DB:.1f} dB flag threshold."
                        if imbalance_detected
                        else "Left/right RMS levels are within a balanced range across the whole file."
                    ),
                    suggested_next_step=(
                        "Check for an unintended pan/gain offset between channels; if the imbalance is an "
                        "intentional wide arrangement choice, no correction is needed."
                        if imbalance_detected
                        else "No action needed."
                    ),
                    limitations="Whole-file average only; cannot distinguish a persistent level offset from intentional asymmetric panning/arrangement.",
                )
            )

            correlation = _pearson_correlation(left, right)
            mono_sum_drop_db = _mono_sum_drop_db(left, right, rms_values)
            phase_detected = (correlation is not None and correlation < PHASE_CORRELATION_FLAG) or (
                mono_sum_drop_db is not None and mono_sum_drop_db >= MONO_SUM_DROP_FLAG_DB
            )
            findings.append(
                _finding(
                    "phase_polarity_mono_compatibility",
                    detected=bool(phase_detected),
                    severity="high" if phase_detected else "none",
                    confidence=0.75,
                    evidence={
                        "lr_correlation": round(correlation, 3) if correlation is not None else None,
                        "mono_sum_drop_db": round(mono_sum_drop_db, 2) if mono_sum_drop_db is not None else None,
                    },
                    explanation=(
                        "Left/right correlation and/or mono-sum level drop indicate likely phase cancellation "
                        "or an inverted-polarity channel."
                        if phase_detected
                        else "No strong phase-cancellation or polarity-inversion signal was found."
                    ),
                    suggested_next_step=(
                        "Check for an accidentally inverted-polarity channel or heavily de-correlated wide "
                        "processing, then confirm the mix still sounds correct summed to mono."
                        if phase_detected
                        else "No action needed."
                    ),
                    limitations="Whole-file correlation only; does not localise the problem in time or isolate which source caused it.",
                )
            )
        else:
            findings.append(_abstained_finding("channel_imbalance", "audio is mono; channel imbalance requires stereo content."))
            findings.append(
                _abstained_finding(
                    "phase_polarity_mono_compatibility", "audio is mono; phase/polarity comparison requires stereo content."
                )
            )

        dc_offsets = [_mean(ch) for ch in channel_data]
        max_dc = max((abs(v) for v in dc_offsets), default=0.0)
        dc_detected = bool(max_dc >= DC_OFFSET_FLAG)
        findings.append(
            _finding(
                "dc_offset",
                detected=dc_detected,
                severity="low" if dc_detected else "none",
                confidence=0.85,
                evidence={"per_channel_dc_offset": [round(v, 5) for v in dc_offsets], "flag_threshold": DC_OFFSET_FLAG},
                explanation=(
                    f"Peak DC offset across channels is {max_dc:.4f} (linear), at or above the "
                    f"{DC_OFFSET_FLAG:.2f} flag threshold."
                    if dc_detected
                    else "No significant DC offset was found."
                ),
                suggested_next_step=(
                    "Apply a high-pass filter or DC-offset removal stage before further processing."
                    if dc_detected
                    else "No action needed."
                ),
            )
        )

        avg_rms = sum(rms_values) / len(rms_values) if rms_values else 0.0
        avg_rms_dbfs = _dbfs(avg_rms)
        loud_detected = avg_rms_dbfs is not None and avg_rms_dbfs > HOT_LOUDNESS_ESTIMATE_DBFS
        findings.append(
            _finding(
                "loudness_estimate",
                detected=bool(loud_detected),
                severity="low" if loud_detected else "none",
                confidence=0.4,
                evidence={"estimated_loudness_dbfs_rms": round(avg_rms_dbfs, 2) if avg_rms_dbfs is not None else None},
                explanation=(
                    f"Whole-file unweighted RMS is approximately {avg_rms_dbfs:.2f} dBFS, above the "
                    f"{HOT_LOUDNESS_ESTIMATE_DBFS:.0f} dBFS reference used here as a rough 'hot' signal."
                    if loud_detected
                    else "Whole-file unweighted RMS did not exceed the rough 'hot' reference level."
                ),
                suggested_next_step="Confirm target loudness with a calibrated LUFS meter before final delivery; this is a low-confidence proxy, not a calibrated measurement.",
                limitations=(
                    "This is an unweighted RMS proxy, not ITU-R BS.1770 K-weighted, gated integrated LUFS. "
                    "Treat it as a rough signal only, not a delivery-loudness measurement."
                ),
            )
        )

        calibrated, abstain_reason = _calibrated_loudness_and_true_peak(channel_data, framerate)
        if calibrated is None:
            findings.append(_abstained_finding("calibrated_lufs_bs1770", abstain_reason or "measurement failed"))
            findings.append(_abstained_finding("true_peak_intersample", abstain_reason or "measurement failed"))
        else:
            metrics["integrated_lufs"] = calibrated["integrated_lufs"]
            metrics["loudness_range_lu"] = calibrated["loudness_range_lu"]
            metrics["true_peak_dbtp"] = calibrated["true_peak_dbtp"]
            lufs_hot = calibrated["integrated_lufs"] > TARGET_INTEGRATED_LUFS
            findings.append(
                _finding(
                    "calibrated_lufs_bs1770",
                    detected=bool(lufs_hot),
                    severity="low" if lufs_hot else "none",
                    confidence=0.95,
                    evidence={
                        "integrated_lufs": calibrated["integrated_lufs"],
                        "loudness_range_lu": calibrated["loudness_range_lu"],
                    },
                    explanation=(
                        f"Integrated loudness is {calibrated['integrated_lufs']:.2f} LUFS "
                        f"(ITU-R BS.1770-4 K-weighted, gated), above the {TARGET_INTEGRATED_LUFS:.0f} LUFS "
                        "common streaming reference used here as an informational marker."
                        if lufs_hot
                        else f"Integrated loudness is {calibrated['integrated_lufs']:.2f} LUFS "
                        "(ITU-R BS.1770-4 K-weighted, gated), at or below the common streaming reference."
                    ),
                    suggested_next_step=(
                        "This is informational, not a pass/fail gate -- confirm the actual delivery "
                        "target for this release (streaming platforms vary) before adjusting gain."
                    ),
                    limitations="A single overall integrated-loudness figure; does not itself indicate where in the mix any loudness issue originates.",
                )
            )
            true_peak_hot = calibrated["true_peak_dbtp"] is not None and calibrated["true_peak_dbtp"] > TRUE_PEAK_CEILING_DBTP
            findings.append(
                _finding(
                    "true_peak_intersample",
                    detected=bool(true_peak_hot),
                    severity="low" if true_peak_hot else "none",
                    confidence=0.9,
                    evidence={"true_peak_dbtp": calibrated["true_peak_dbtp"]},
                    explanation=(
                        f"Estimated true peak is {calibrated['true_peak_dbtp']:.2f} dBTP "
                        f"({TRUE_PEAK_OVERSAMPLE_FACTOR}x oversampled), above the "
                        f"{TRUE_PEAK_CEILING_DBTP:.0f} dBTP common delivery ceiling used here as an "
                        "informational marker."
                        if true_peak_hot
                        else f"Estimated true peak is {calibrated['true_peak_dbtp']:.2f} dBTP "
                        f"({TRUE_PEAK_OVERSAMPLE_FACTOR}x oversampled), at or below the common delivery ceiling."
                    ),
                    suggested_next_step=(
                        "Consider a true-peak limiter before final delivery if this file will be lossy-encoded "
                        "(inter-sample peaks can clip after encoding even when sample-peak looks safe)."
                    ),
                    limitations=f"{TRUE_PEAK_OVERSAMPLE_FACTOR}x oversampling is an estimate, not a full reference true-peak meter implementation.",
                )
            )

    for family in NOT_EVALUATED_FAULT_FAMILIES:
        findings.append(_abstained_finding(family, "not implemented in this build; explicitly out of scope, not silently omitted."))

    action_plan = [
        {
            "focus": finding["fault_family"],
            "action": finding["suggested_next_step"],
            "reason": finding["explanation"],
        }
        for finding in findings
        if finding["detected"]
    ]

    return {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "analysis_version": ANALYSIS_VERSION,
        "receipt_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mix_goal": mix_goal,
        "light": light,
        "include_bands": include_bands,
        "input_context": {
            "filename": filename,
            "format": "wav",
            "duration_seconds": round(duration_seconds, 3),
            "sample_rate_hz": framerate,
            "channel_layout": {1: "mono", 2: "stereo"}.get(channels, f"{channels}ch"),
            "channel_count": channels,
        },
        "runtime_provenance": {
            "engine": "kenn-owned mix-review/core/local_engine.py",
            "external_dependency": None,
        },
        "metrics": metrics,
        "evidence": _evidence_packet(metrics),
        "technical_rating": _technical_rating(findings),
        "action_plan": action_plan,
        "findings": findings,
        "qualified_fault_families": list(QUALIFIED_FAULT_FAMILIES),
        "not_evaluated_fault_families": list(NOT_EVALUATED_FAULT_FAMILIES),
        "limitations": GLOBAL_LIMITATIONS,
    }


def _pearson_correlation(left: array, right: array) -> float | None:
    n = min(len(left), len(right))
    if n == 0:
        return None
    if _np is not None and isinstance(left, _np.ndarray) and isinstance(right, _np.ndarray):
        left_slice = left[:n]
        right_slice = right[:n]
        sum_lr = float(_np.dot(left_slice, right_slice))
        sum_ll = float(_np.dot(left_slice, left_slice))
        sum_rr = float(_np.dot(right_slice, right_slice))
        denom = math.sqrt(sum_ll * sum_rr)
        if denom == 0:
            return None
        return max(-1.0, min(1.0, sum_lr / denom))
    sum_lr = sum_ll = sum_rr = 0.0
    for i in range(n):
        l_val = left[i]
        r_val = right[i]
        sum_lr += l_val * r_val
        sum_ll += l_val * l_val
        sum_rr += r_val * r_val
    denom = math.sqrt(sum_ll * sum_rr)
    if denom == 0:
        return None
    return max(-1.0, min(1.0, sum_lr / denom))


def _mono_sum_drop_db(left: array, right: array, rms_values: list[float]) -> float | None:
    n = min(len(left), len(right))
    if n == 0:
        return None
    if _np is not None and isinstance(left, _np.ndarray) and isinstance(right, _np.ndarray):
        mixed = (left[:n] + right[:n]) / 2.0
        mono_rms = float(_np.sqrt(_np.mean(mixed * mixed)))
        expected_rms = max(rms_values) if rms_values else 0.0
        mono_dbfs = _dbfs(mono_rms)
        expected_dbfs = _dbfs(expected_rms)
        if mono_dbfs is None or expected_dbfs is None:
            return None
        return expected_dbfs - mono_dbfs
    total = 0.0
    for i in range(n):
        mixed = (left[i] + right[i]) / 2.0
        total += mixed * mixed
    mono_rms = math.sqrt(total / n)
    expected_rms = max(rms_values) if rms_values else 0.0
    mono_dbfs = _dbfs(mono_rms)
    expected_dbfs = _dbfs(expected_rms)
    if mono_dbfs is None or expected_dbfs is None:
        return None
    return expected_dbfs - mono_dbfs


def _k_filter_coefficients(fs: float) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """ITU-R BS.1770 K-weighting biquads (shelf + high-pass), any sample rate.

    Ported from the estate's own Audio_Too implementation
    (studio/audio_analysis/.../analysis_core/loudness.py
    get_k_filter_coefficients): RBJ high-shelf (G=+3.9998 dB, f0=1681.97 Hz,
    Q=0.7071) cascaded with a 2nd-order high-pass (f0=38.14 Hz, Q=0.5).
    Returns ((b0,b1,b2,a1,a2) shelf, (b0,b1,b2,a1,a2) high-pass) with a0=1.
    """
    db_gain = 3.99984380697339
    f0 = 1681.97445095553
    q = 0.707175236955419
    w0 = 2.0 * math.pi * f0 / fs
    alpha = math.sin(w0) / (2.0 * q)
    a = 10.0 ** (db_gain / 40.0)
    cos_w0 = math.cos(w0)
    a0 = (a + 1.0) - (a - 1.0) * cos_w0 + 2.0 * math.sqrt(a) * alpha
    shelf = (
        a * ((a + 1.0) + (a - 1.0) * cos_w0 + 2.0 * math.sqrt(a) * alpha) / a0,
        -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0) / a0,
        a * ((a + 1.0) + (a - 1.0) * cos_w0 - 2.0 * math.sqrt(a) * alpha) / a0,
        2.0 * ((a - 1.0) - (a + 1.0) * cos_w0) / a0,
        ((a + 1.0) - (a - 1.0) * cos_w0 - 2.0 * math.sqrt(a) * alpha) / a0,
    )
    f0_hp = 38.1354708761398
    q_hp = 0.5
    w0_hp = 2.0 * math.pi * f0_hp / fs
    alpha_hp = math.sin(w0_hp) / (2.0 * q_hp)
    cos_hp = math.cos(w0_hp)
    a0_hp = 1.0 + alpha_hp
    highpass = (
        (1.0 + cos_hp) / 2.0 / a0_hp,
        -(1.0 + cos_hp) / a0_hp,
        (1.0 + cos_hp) / 2.0 / a0_hp,
        -2.0 * cos_hp / a0_hp,
        (1.0 - alpha_hp) / a0_hp,
    )
    return shelf, highpass


def _biquad_response(b: tuple[float, ...], w: Any) -> Any:
    """Frequency response H(e^jw) of b = (b0,b1,b2,a1,a2) with a0 = 1."""
    ejw = _np.exp(-1j * w)
    ej2w = ejw * ejw
    return (b[0] + b[1] * ejw + b[2] * ej2w) / (1.0 + b[3] * ejw + b[4] * ej2w)


def _apply_k_filter(x: Any, fs: int) -> Any:
    """Zero-state K-weighting via FFT (exact linear convolution).

    Zero-padded FFT multiplication approximates the infinite IIR response;
    the slowest pole (38 Hz high-pass, ~4 ms decay) is settled orders of
    magnitude within the FFT pad, leaving <1e-6 residual error. Long inputs
    are chunked with overlap so memory stays bounded.
    """
    shelf, highpass = _k_filter_coefficients(float(fs))
    n = int(x.shape[0])
    if n == 0:
        return x
    chunk = 1 << 20
    overlap = 8192
    if n <= chunk:
        return _apply_k_filter_block(x, shelf, highpass, fs)
    out = _np.empty_like(x)
    pos = 0
    while pos < n:
        start = max(0, pos - overlap)
        piece = _apply_k_filter_block(x[start:pos + chunk], shelf, highpass, fs)
        keep_from = pos - start
        out[pos:pos + chunk] = piece[keep_from:keep_from + min(chunk, n - pos)]
        pos += chunk
    return out


def _apply_k_filter_block(x: Any, shelf: tuple[float, ...], highpass: tuple[float, ...], fs: int) -> Any:
    n = int(x.shape[0])
    pad = 8192
    size = n + pad
    # rfftfreq in cycles/sample -> radians/sample. (NOT scaled by fs: the
    # biquad response takes per-sample angular frequency.)
    w = _np.fft.rfftfreq(size) * (2.0 * _np.pi)
    h = _biquad_response(shelf, w) * _biquad_response(highpass, w)
    y = _np.fft.irfft(_np.fft.rfft(x, n=size) * h, n=size)
    return y[:n].astype(_np.float64)


def _gated_block_powers(y: Any, fs: int, block_s: float, hop_s: float) -> Any:
    """Mean-square powers of overlapping blocks (columns = channels)."""
    block = int(block_s * fs)
    hop = int(hop_s * fs)
    n = int(y.shape[0])
    if n < block or hop <= 0:
        return _np.empty((0,))
    count = (n - block) // hop + 1
    shape = (count, block, y.shape[1])
    strides = (y.strides[0] * hop, y.strides[0], y.strides[1])
    blocks = _np.lib.stride_tricks.as_strided(y, shape=shape, strides=strides)
    return _np.mean(blocks * blocks, axis=(1, 2))


def _numpy_integrated_lufs_and_lra(
    channels: list[Any], framerate: int
) -> tuple[float | None, float | None]:
    """BS.1770 integrated LUFS + LRA with numpy only (no pyloudnorm/scipy).

    K-weighting, 400 ms / 100 ms gating blocks, -70 absolute / -10 relative
    gates, equal per-channel weighting; LRA from 3 s / 100 ms windows with
    -70 absolute / -20 relative gates (P95-P10). Returns (lufs, lra_or_None).
    Silence (no block above the absolute gate) yields (None, None) so the
    caller abstains instead of reporting -infinity.
    """
    if not channels:
        return None, None
    stacked = _np.stack([_np.ravel(ch) for ch in channels], axis=-1)
    n = int(stacked.shape[0])
    if n < int(0.4 * framerate):
        return None, None
    y = _np.stack([_apply_k_filter(stacked[:, i], framerate) for i in range(stacked.shape[1])], axis=-1)
    powers = _gated_block_powers(y, framerate, 0.4, 0.1)
    if powers.size == 0:
        return None, None
    powers = _np.clip(powers, 1e-12, None)
    moments = -0.691 + 10.0 * _np.log10(powers)
    absolute = moments > -70.0
    if not bool(_np.any(absolute)):
        return None, None
    gated_mean = float(_np.mean(powers[absolute]))
    relative = absolute & (moments > (-0.691 + 10.0 * _np.log10(gated_mean) - 10.0))
    if not bool(_np.any(relative)):
        return -0.691 + 10.0 * float(_np.log10(gated_mean)), None
    integrated = -0.691 + 10.0 * float(_np.log10(float(_np.mean(powers[relative]))))
    short = _gated_block_powers(y, framerate, 3.0, 0.1)
    lra: float | None = None
    if short.size:
        short = _np.clip(short, 1e-12, None)
        short_moments = -0.691 + 10.0 * _np.log10(short)
        short_abs = short_moments > -70.0
        if bool(_np.any(short_abs)):
            short_mean = float(_np.mean(short[short_abs]))
            short_rel = short_abs & (short_moments > (-0.691 + 10.0 * _np.log10(short_mean) - 20.0))
            if bool(_np.any(short_rel)):
                vals = _np.sort(short_moments[short_rel])
                lo = float(vals[int(0.10 * (len(vals) - 1))])
                hi = float(vals[int(0.95 * (len(vals) - 1))])
                lra = hi - lo
    return integrated, lra


def _numpy_true_peak_dbtp(channels: list[Any]) -> float | None:
    """4x bandlimited (FFT zero-pad) true peak per BS.1770-4 Annex 2.

    Spectral zero-padding is exact sinc interpolation, so inter-sample
    overshoot reads at or above the sample peak. Chunked with overlap for
    long inputs. Returns None only for all-empty input.
    """
    peak = 0.0
    for ch in channels:
        x = _np.ravel(ch).astype(_np.float64)
        n = int(x.shape[0])
        if n == 0:
            continue
        chunk = 1 << 20
        overlap = 1024
        if n <= chunk:
            pieces = [(0, n)]
        else:
            pieces = []
            pos = 0
            while pos < n:
                start = max(0, pos - overlap)
                pieces.append((start, min(n, pos + chunk)))
                pos += chunk
        for start, end in pieces:
            seg = x[start:end]
            m = int(seg.shape[0])
            up = _np.fft.irfft(_np.fft.rfft(seg, n=4 * m), n=4 * m)
            peak = max(peak, float(_np.max(_np.abs(up))) if up.size else 0.0)
    if peak <= 0.0:
        return None
    return 20.0 * math.log10(peak)


def _calibrated_loudness_and_true_peak(
    channel_data: list[array], framerate: int
) -> tuple[dict[str, float] | None, str | None]:
    """Real ITU-R BS.1770-4 integrated LUFS/LRA and 4x-oversampled true-peak.

    Returns ``(measurements, abstain_reason)``: exactly one of the two is
    non-None. Prefers pyloudnorm/scipy when installed (battle-tested);
    otherwise uses the vendored numpy BS.1770 above, which needs nothing
    beyond numpy. Abstains explicitly (never guesses) when numpy itself is
    unavailable, the audio is shorter than the 400 ms gating block, or no
    block clears the absolute gate (silence).
    """
    if _np is None:
        return None, "numpy is not installed, so calibrated loudness cannot run"
    arrays = [_np.ravel(_np.asarray(ch, dtype=_np.float64)) for ch in channel_data]
    if not arrays or not all(a.size for a in arrays):
        return None, "no audio samples to measure"
    if len(arrays[0]) < int(0.4 * framerate):
        # pyloudnorm's gating blocks are 400 ms; shorter audio has no
        # well-defined integrated loudness under BS.1770.
        return None, "audio is shorter than the 400 ms BS.1770 gating block"
    native_loudness_enabled = os.environ.get("KENN_DSP_LOUDNESS_NATIVE", "0").strip().lower() in {
        "1", "true", "on", "yes",
    }
    # Native decoding already produced contiguous float32 channels. Keep that
    # representation for the native loudness call so it does not immediately
    # widen the whole upload back to float64; retain the float64 arrays above
    # as the exact Python oracle/fallback.
    native_arrays = arrays
    if native_loudness_enabled and all(
        isinstance(channel, _np.ndarray) and channel.dtype == _np.float32
        for channel in channel_data
    ):
        native_arrays = [_np.ravel(_np.asarray(channel, dtype=_np.float32)) for channel in channel_data]
    # pyloudnorm's LRA path appends 1.5 s of silence and requires a signal
    # longer than its 3 s short-term block. Keep the opt-in candidate on the
    # same abstention boundary when the pyloudnorm oracle is installed.
    pyloudnorm_lra_compatible = not (
        _pyln is not None
        and _resample_poly is not None
        and len(arrays[0]) + int(1.5 * framerate) <= int(3.0 * framerate)
    )
    if native_loudness_enabled and pyloudnorm_lra_compatible:
        try:
            from kenn.core.native_fft import loudness_metrics

            native_result = loudness_metrics(native_arrays, framerate)
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            native_result = None
        if native_result is not None:
            native_integrated = native_result.get("integrated_lufs")
            if isinstance(native_integrated, (int, float)) and math.isfinite(float(native_integrated)):
                native_lra = native_result.get("loudness_range_lu")
                native_true_peak = native_result.get("true_peak_dbtp")
                true_peak_dbtp = (
                    float(native_true_peak)
                    if isinstance(native_true_peak, (int, float)) and math.isfinite(float(native_true_peak))
                    else (
                        _pyloudnorm_true_peak_dbtp(arrays)
                        if _resample_poly is not None
                        else _numpy_true_peak_dbtp(arrays)
                    )
                )
                return {
                    "integrated_lufs": round(float(native_integrated), 2),
                    "loudness_range_lu": round(float(native_lra), 2)
                    if isinstance(native_lra, (int, float)) and math.isfinite(float(native_lra))
                    else None,
                    "true_peak_dbtp": round(float(true_peak_dbtp), 2)
                    if true_peak_dbtp is not None and math.isfinite(true_peak_dbtp)
                    else None,
                }, None
    if _pyln is not None and _resample_poly is not None:
        return _pyloudnorm_measurements(arrays, framerate)
    integrated, lra = _numpy_integrated_lufs_and_lra(arrays, framerate)
    if integrated is None or not math.isfinite(integrated):
        return None, "no 400 ms block above the -70 LUFS absolute gate (audio is likely silent or near-silent)"
    true_peak_dbtp = _numpy_true_peak_dbtp(arrays)
    return {
        "integrated_lufs": round(float(integrated), 2),
        "loudness_range_lu": round(float(lra), 2) if lra is not None and math.isfinite(lra) else None,
        "true_peak_dbtp": round(float(true_peak_dbtp), 2) if true_peak_dbtp is not None and math.isfinite(true_peak_dbtp) else None,
    }, None


def _pyloudnorm_measurements(
    arrays: list[Any], framerate: int
) -> tuple[dict[str, float] | None, str | None]:
    """Original pyloudnorm/scipy measurement path (preferred when installed)."""
    assert _pyln is not None and _resample_poly is not None
    channel_data = arrays
    if not channel_data or not all(isinstance(ch, _np.ndarray) for ch in channel_data):
        return None, "numpy acceleration is unavailable for this decode path"
    if len(channel_data[0]) < int(0.4 * framerate):
        return None, "audio is shorter than the 400 ms BS.1770 gating block"
    try:
        stacked = _np.stack(channel_data, axis=-1) if len(channel_data) > 1 else channel_data[0]
        meter = _pyln.Meter(framerate)
        integrated_lufs = meter.integrated_loudness(stacked)
        loudness_range = meter.loudness_range(stacked)
        true_peak_dbtp = _pyloudnorm_true_peak_dbtp(channel_data)
    except Exception as exc:  # pragma: no cover - defensive: never let a metering edge case crash the review
        return None, f"pyloudnorm/scipy raised on this input: {exc}"
    if not math.isfinite(integrated_lufs):
        return None, "integrated loudness was not finite (audio is likely silent or near-silent)"
    return {
        "integrated_lufs": round(float(integrated_lufs), 2),
        "loudness_range_lu": round(float(loudness_range), 2) if math.isfinite(loudness_range) else None,
        "true_peak_dbtp": round(float(true_peak_dbtp), 2)
        if true_peak_dbtp is not None and math.isfinite(float(true_peak_dbtp))
        else None,
    }, None


def _pyloudnorm_true_peak_dbtp(arrays: list[Any]) -> float | None:
    """Fallback true-peak implementation for older native wheels."""
    if _np is None or _resample_poly is None:
        return None
    peak_dbtp: float | None = None
    for channel in arrays:
        oversampled = _resample_poly(channel, up=TRUE_PEAK_OVERSAMPLE_FACTOR, down=1)
        channel_peak = float(_np.max(_np.abs(oversampled))) if oversampled.size else 0.0
        if channel_peak > 0.0:
            value = 20.0 * math.log10(channel_peak)
            peak_dbtp = value if peak_dbtp is None else max(peak_dbtp, value)
    return peak_dbtp


def _technical_rating(findings: list[dict[str, Any]]) -> str:
    detected = [f for f in findings if f["detected"]]
    if any(f["severity"] == "high" for f in detected):
        return "Issues found requiring attention"
    if detected:
        return "Minor issues found"
    return "No qualified issues found"
