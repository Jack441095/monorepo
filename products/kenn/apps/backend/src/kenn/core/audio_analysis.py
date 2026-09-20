"""KENN-owned, bounded WAV analysis with auditable spectral evidence.

This module intentionally uses only the Python standard library.  It is a
measurement layer, not a listening judge: FFT peaks are reported as features
and the findings below use cautious language and include a listening test.
There is no LUFS or true-peak claim in this module.
"""

from __future__ import annotations

import hashlib
import io
import math
import struct
import time
import uuid
import wave
from array import array
from datetime import datetime, timezone
from typing import Any


ANALYSIS_VERSION = "kenn.audio_analysis.v1"
RESULT_SCHEMA = "kenn.audio_analysis.result.v1"
MAX_INPUT_BYTES = 150 * 1024 * 1024
MIN_SPECTRAL_SECONDS = 0.25
DEFAULT_FFT_SIZE = 16384
MAX_FFT_WINDOWS = 4
MAX_LOCALIZED_PEAKS = 6
LTAS_BAND_COUNT = 40
PINK_NOISE_ANCHOR_FREQUENCY_HZ = 1000.0
PINK_NOISE_SLOPE_DB_PER_OCTAVE = -3.0
CLIP_THRESHOLD = 10 ** (-0.3 / 20.0)
SILENCE_THRESHOLD = 10 ** (-60.0 / 20.0)


class AudioAnalysisError(ValueError):
    """Raised when the input is not a bounded, supported PCM WAV."""


def _db(value: float, *, floor: float = -120.0) -> float:
    if value <= 0.0:
        return floor
    return 20.0 * math.log10(value)


def _rms(values: list[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))


def _next_power_of_two(value: int) -> int:
    result = 1
    while result < value:
        result <<= 1
    return result


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


def _decode(payload: bytes) -> tuple[list[list[float]], int, int, int]:
    if not payload:
        raise AudioAnalysisError("audio payload is empty")
    if len(payload) > MAX_INPUT_BYTES:
        raise AudioAnalysisError(f"audio payload exceeds {MAX_INPUT_BYTES} bytes")
    try:
        channels, sample_width, sample_rate, raw, audio_format = _parse_wav(payload)
    except Exception as exc:
        raise AudioAnalysisError(f"invalid WAV: {exc}") from exc

    if channels not in (1, 2):
        raise AudioAnalysisError("only mono and stereo WAV files are supported")
    if sample_width not in (2, 3, 4):
        raise AudioAnalysisError("only 16-bit, 24-bit, and 32-bit WAV files are supported")
    if audio_format not in (1, 3):
        raise AudioAnalysisError(f"unsupported WAV audio format tag ({audio_format})")
    if sample_rate <= 0 or len(raw) == 0:
        raise AudioAnalysisError("WAV contains no audio frames")

    channel_data = [[] for _ in range(channels)]
    if sample_width == 2:
        frame_count = len(raw) // (channels * 2)
        expected = frame_count * channels * 2
        if len(raw) < expected:
            raise AudioAnalysisError("WAV data chunk is truncated")
        values = struct.iter_unpack("<h", raw[:expected])
        scale = 32768.0
        for index, (value,) in enumerate(values):
            channel_data[index % channels].append(value / scale)
    elif sample_width == 3:
        frame_count = len(raw) // (channels * 3)
        expected = frame_count * channels * 3
        if len(raw) < expected:
            raise AudioAnalysisError("WAV data chunk is truncated")
        for index in range(0, expected, 3):
            value = raw[index] | (raw[index + 1] << 8) | (raw[index + 2] << 16)
            if value & 0x800000:
                value -= 0x1000000
            channel_data[(index // 3) % channels].append(value / 8388608.0)
    elif sample_width == 4:
        frame_count = len(raw) // (channels * 4)
        expected = frame_count * channels * 4
        if audio_format == 3:  # IEEE 754 32-bit float
            values = struct.iter_unpack("<f", raw[:expected])
            for index, (value,) in enumerate(values):
                channel_data[index % channels].append(float(value))
        else:  # 32-bit integer PCM
            values = struct.iter_unpack("<i", raw[:expected])
            scale = 2147483648.0
            for index, (value,) in enumerate(values):
                channel_data[index % channels].append(value / scale)
    return channel_data, sample_rate, channels, sample_width * 8


def _fft(values: list[float]) -> list[complex]:
    """Iterative radix-2 FFT; kept here to make the measurement auditable."""
    n = len(values)
    output = [complex(value, 0.0) for value in values]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            output[i], output[j] = output[j], output[i]
    length = 2
    while length <= n:
        angle = -2.0 * math.pi / length
        root = complex(math.cos(angle), math.sin(angle))
        for start in range(0, n, length):
            factor = complex(1.0, 0.0)
            half = length // 2
            for offset in range(half):
                even = output[start + offset]
                odd = factor * output[start + offset + half]
                output[start + offset] = even + odd
                output[start + offset + half] = even - odd
                factor *= root
        length <<= 1
    return output


def _window_starts(length: int, fft_size: int) -> list[int]:
    if length <= fft_size:
        return [0]
    count = min(MAX_FFT_WINDOWS, max(1, math.ceil(length / fft_size)))
    last = length - fft_size
    if count == 1:
        return [0]
    return [round(last * index / (count - 1)) for index in range(count)]


def _dominant_peaks(
    powers: list[float],
    sample_rate: int,
    fft_size: int,
    window_sum: float,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Extract auditable local maxima from one power spectrum."""
    def frequency(index: float) -> float:
        return index * sample_rate / fft_size

    # Local maxima above a conservative noise floor.  The parabolic offset is
    # calculated in log-power space, which improves accuracy for off-bin tones.
    max_power = max(powers[1:], default=0.0)
    candidates: list[tuple[float, float]] = []
    for index in range(2, len(powers) - 1):
        if powers[index] < max_power * 1e-5:
            continue
        if powers[index] < powers[index - 1] or powers[index] < powers[index + 1]:
            continue
        left = math.log(max(powers[index - 1], 1e-30))
        center = math.log(max(powers[index], 1e-30))
        right = math.log(max(powers[index + 1], 1e-30))
        denominator = left - 2.0 * center + right
        offset = 0.0 if abs(denominator) < 1e-12 else 0.5 * (left - right) / denominator
        offset = max(-0.5, min(0.5, offset))
        peak_power = max(powers[index], 1e-30)
        amplitude = 2.0 * math.sqrt(peak_power) / max(window_sum, 1.0)
        candidates.append((frequency(index + offset), _db(amplitude)))
    candidates.sort(key=lambda item: item[1], reverse=True)

    peaks: list[dict[str, Any]] = []
    for peak_frequency, level in candidates[:limit]:
        bin_index = max(1, min(len(powers) - 2, round(peak_frequency * fft_size / sample_rate)))
        half_power = powers[bin_index] * 0.5
        left = bin_index
        right = bin_index
        while left > 1 and powers[left - 1] >= half_power:
            left -= 1
        while right < len(powers) - 2 and powers[right + 1] >= half_power:
            right += 1
        bandwidth = (right - left + 1) * sample_rate / fft_size
        peaks.append({
            "frequency_hz": round(peak_frequency, 3),
            "level_dbfs": round(level, 2),
            "bandwidth_hz": round(bandwidth, 3),
            "confidence": round(max(0.0, min(1.0, 0.55 + min(0.4, max(0.0, level - (-80.0)) / 100.0))), 2),
            "fft_bin": bin_index,
        })
    return peaks


def _spectral_measurement(
    samples: list[float], sample_rate: int, fft_size: int, *, include_ltas: bool = False,
) -> dict[str, Any]:
    n = min(_next_power_of_two(max(256, fft_size)), 131072)
    starts = _window_starts(len(samples), n)
    window = [0.5 - 0.5 * math.cos(2.0 * math.pi * index / (n - 1)) for index in range(n)]
    window_sum = sum(window)
    powers = [0.0] * (n // 2 + 1)
    localized_windows: list[dict[str, Any]] = []
    for start in starts:
        source_segment = samples[start : start + n]
        segment = source_segment
        if len(segment) < n:
            segment = segment + [0.0] * (n - len(segment))
        spectrum = _fft([segment[index] * window[index] for index in range(n)])
        window_powers = [
            (value.real ** 2 + value.imag ** 2)
            for value in spectrum[: n // 2 + 1]
        ]
        for index, value in enumerate(window_powers):
            powers[index] += value
        end = min(len(samples), start + n)
        localized_windows.append({
            "start_seconds": round(start / sample_rate, 6),
            "end_seconds": round(end / sample_rate, 6),
            "rms_dbfs": round(_db(_rms(source_segment)), 3),
            "dominant_peaks": _dominant_peaks(
                window_powers,
                sample_rate,
                n,
                window_sum,
                limit=MAX_LOCALIZED_PEAKS,
            ),
        })
    powers = [value / len(starts) for value in powers]

    def frequency(index: float) -> float:
        return index * sample_rate / n

    peaks = _dominant_peaks(powers, sample_rate, n, window_sum)

    bands = {
        "low": (20.0, 250.0),
        "low_mid": (250.0, 500.0),
        "mid": (500.0, 2000.0),
        "upper_mid": (2000.0, 6000.0),
        "high": (6000.0, min(20000.0, sample_rate / 2.0)),
    }
    band_levels: dict[str, float] = {}
    for name, (low, high) in bands.items():
        total = 0.0
        for index in range(1, len(powers)):
            hz = frequency(index)
            if low <= hz < high:
                multiplier = 1.0 if index in (0, len(powers) - 1) else 2.0
                total += powers[index] * multiplier
        band_rms = math.sqrt(total / (n * n))
        band_levels[name] = round(_db(band_rms), 2)

    measurement = {
        "fft_size": n,
        "window": "hann",
        "windows_averaged": len(starts),
        "time_localized_windows": localized_windows,
        "bin_width_hz": round(sample_rate / n, 6),
        "dominant_peaks": peaks,
        "band_energy_dbfs": band_levels,
    }
    if include_ltas:
        measurement["ltas_40_band_relative_db"] = _ltas_40_band_relative_db(powers, sample_rate, n)
    return measurement


def _ltas_40_band_relative_db(
    powers: list[float], sample_rate: int, fft_size: int,
) -> list[dict[str, Any]]:
    """A bounded 40-band log LTAS, normalised to the nearest 1 kHz band.

    This mirrors AutoMix's useful *measurement* contract without importing its
    pipeline: bins are aggregated into 40 log-spaced ranges and expressed
    relative to 1 kHz, so two renders can be compared despite level changes.
    It is not a pink-noise target and it is not an EQ command.
    """
    nyquist = sample_rate / 2.0
    lower, upper = 20.0, min(20000.0, nyquist)
    if upper <= lower:
        return []
    ratio = (upper / lower) ** (1.0 / LTAS_BAND_COUNT)
    edges = [lower * (ratio ** index) for index in range(LTAS_BAND_COUNT + 1)]
    raw: list[dict[str, Any]] = []
    for index, (low, high) in enumerate(zip(edges, edges[1:])):
        values = []
        for bin_index in range(1, len(powers)):
            hz = bin_index * sample_rate / fft_size
            if low <= hz < high:
                values.append(powers[bin_index])
        if not values:
            continue
        raw.append({
            "index": index,
            "low_hz": round(low, 3),
            "high_hz": round(high, 3),
            "center_hz": round(math.sqrt(low * high), 3),
            "level_db": _db(math.sqrt(sum(values) / len(values))),
        })
    if not raw:
        return []
    anchor = min(raw, key=lambda item: abs(float(item["center_hz"]) - 1000.0))
    anchor_level = float(anchor["level_db"])
    return [
        {
            "index": item["index"],
            "low_hz": item["low_hz"],
            "high_hz": item["high_hz"],
            "center_hz": item["center_hz"],
            "relative_db": round(float(item["level_db"]) - anchor_level, 3),
        }
        for item in raw
    ]


def _pink_noise_reference(ltas: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare measured LTAS bands with an explicit pink-noise-style slope.

    The curve is a diagnostic baseline, not a target for every mix.  It is
    anchored to the measured band nearest 1 kHz so the result remains a
    relative spectral shape comparison rather than a loudness judgement.
    """
    usable = [
        row for row in ltas
        if isinstance(row, dict)
        and isinstance(row.get("center_hz"), (int, float))
        and isinstance(row.get("relative_db"), (int, float))
        and float(row["center_hz"]) > 0.0
    ]
    if not usable:
        return {
            "status": "abstained",
            "reason": "No usable LTAS bands were available for the pink-noise-style comparison.",
        }
    anchor = min(usable, key=lambda row: abs(float(row["center_hz"]) - PINK_NOISE_ANCHOR_FREQUENCY_HZ))
    anchor_frequency = float(anchor["center_hz"])
    bands: list[dict[str, Any]] = []
    for row in usable:
        center = float(row["center_hz"])
        measured = float(row["relative_db"])
        expected = PINK_NOISE_SLOPE_DB_PER_OCTAVE * math.log2(center / anchor_frequency)
        bands.append({
            "index": row.get("index"),
            "center_hz": row.get("center_hz"),
            "measured_relative_db": round(measured, 3),
            "pink_expected_relative_db": round(expected, 3),
            "deviation_db": round(measured - expected, 3),
        })
    largest = max(bands, key=lambda row: abs(float(row["deviation_db"])), default=None)
    return {
        "status": "complete",
        "curve": "-3 dB per octave pink-noise-style spectral baseline",
        "slope_db_per_octave": PINK_NOISE_SLOPE_DB_PER_OCTAVE,
        "anchor_frequency_hz": round(anchor_frequency, 3),
        "positive_deviation_means": "more measured energy than the baseline at that band",
        "bands": bands,
        "largest_deviation": largest,
        "limitations": [
            "This is a broad spectral-shape reference, not a universal mix target or quality score.",
            "A deviation does not identify a track, arrangement choice, room problem, or processing cause.",
            "Level-match and listen before making any tonal change; no EQ move is implied.",
        ],
    }


def _correlation(left: list[float], right: list[float]) -> float | None:
    if not left or not right:
        return None
    count = min(len(left), len(right))
    left = left[:count]
    right = right[:count]
    left_mean = sum(left) / count
    right_mean = sum(right) / count
    numerator = sum((left[index] - left_mean) * (right[index] - right_mean) for index in range(count))
    left_energy = sum((value - left_mean) ** 2 for value in left)
    right_energy = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_energy * right_energy)
    return None if denominator == 0.0 else max(-1.0, min(1.0, numerator / denominator))


def _finding(kind: str, *, confidence: float, severity: str, evidence: dict[str, Any], explanation: str, test: str) -> dict[str, Any]:
    return {
        "type": kind,
        "confidence": round(confidence, 2),
        "severity": severity,
        "evidence": evidence,
        "explanation": explanation,
        "suggested_listening_test": test,
    }


def analyze_wav(
    payload: bytes, *, filename: str, fft_size: int = DEFAULT_FFT_SIZE,
    include_ltas: bool = False, include_pink_noise_reference: bool = False,
) -> dict[str, Any]:
    """Return a versioned measurement result, or a truthful abstention/error."""
    started = time.perf_counter()
    input_hash = hashlib.sha256(payload).hexdigest()
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        channels, sample_rate, channel_count, bit_depth = _decode(payload)
    except AudioAnalysisError as exc:
        return {
            "schema": RESULT_SCHEMA,
            "analysis_version": ANALYSIS_VERSION,
            "ok": False,
            "analysis_status": "error",
            "input_hash": input_hash,
            "filename": filename,
            "analysis_timestamp": timestamp,
            "error": str(exc),
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
        }

    duration = len(channels[0]) / sample_rate
    mono = [(sum(channel[index] for channel in channels) / channel_count) for index in range(len(channels[0]))]
    rms_values = [_rms(channel) for channel in channels]
    peaks = [max((abs(value) for value in channel), default=0.0) for channel in channels]
    sample_peak = max(peaks, default=0.0)
    rms = sum(rms_values) / len(rms_values) if rms_values else 0.0
    clip_count = sum(1 for channel in channels for value in channel if abs(value) >= CLIP_THRESHOLD)
    clip_runs = 0
    for channel in channels:
        in_run = False
        for value in channel:
            clipped = abs(value) >= CLIP_THRESHOLD
            if clipped and not in_run:
                clip_runs += 1
            in_run = clipped
    silence_percentage = 100.0 * sum(1 for value in mono if abs(value) < SILENCE_THRESHOLD) / max(1, len(mono))
    dc_offsets = [sum(channel) / len(channel) for channel in channels]
    metrics: dict[str, Any] = {
        "duration_seconds": round(duration, 6),
        "sample_rate_hz": sample_rate,
        "bit_depth": bit_depth,
        "channels": channel_count,
        "channel_layout": "mono" if channel_count == 1 else "stereo",
        "sample_peak_dbfs": round(_db(sample_peak), 3),
        "rms_dbfs": round(_db(rms), 3),
        "crest_factor_db": round(_db(sample_peak) - _db(rms), 3) if rms else None,
        "clipped_sample_count": clip_count,
        "clipped_run_count": clip_runs,
        "silence_percentage": round(silence_percentage, 4),
        "dc_offset": [round(value, 8) for value in dc_offsets],
    }

    if channel_count == 2:
        left, right = channels
        left_db, right_db = _db(rms_values[0]), _db(rms_values[1])
        mid = [(left[index] + right[index]) * 0.5 for index in range(len(left))]
        side = [(left[index] - right[index]) * 0.5 for index in range(len(left))]
        mid_rms = _rms(mid)
        side_rms = _rms(side)
        mono_rms = _rms([(left[index] + right[index]) * 0.5 for index in range(len(left))])
        metrics.update({
            "left_rms_dbfs": round(left_db, 3),
            "right_rms_dbfs": round(right_db, 3),
            "left_right_rms_difference_db": round(abs(left_db - right_db), 3),
            "correlation": round(_correlation(left, right), 5) if _correlation(left, right) is not None else None,
            "stereo_width_ratio": round(side_rms / mid_rms, 5) if mid_rms else None,
            "stereo_width_db": round(_db(side_rms / mid_rms), 3) if mid_rms else None,
            "mono_sum_rms_dbfs": round(_db(mono_rms), 3),
            "mono_cancellation_drop_db": round(max(left_db, right_db) - _db(mono_rms), 3) if mono_rms else None,
        })

    spectral_abstention_reason = None
    if duration < MIN_SPECTRAL_SECONDS:
        spectral_abstention_reason = f"audio is only {duration:.3f}s; at least {MIN_SPECTRAL_SECONDS:.2f}s is required"
    elif silence_percentage >= 99.9:
        spectral_abstention_reason = "audio is effectively silent"

    findings: list[dict[str, Any]] = []
    spectral: dict[str, Any] | None = None
    if spectral_abstention_reason:
        spectral = {"status": "abstained", "reason": spectral_abstention_reason}
        if include_pink_noise_reference:
            spectral["pink_noise_reference"] = {
                "status": "abstained", "reason": spectral_abstention_reason,
            }
    else:
        spectral = {
            "status": "complete",
            **_spectral_measurement(
                mono, sample_rate, fft_size,
                include_ltas=include_ltas or include_pink_noise_reference,
            ),
        }
        if include_pink_noise_reference:
            spectral["pink_noise_reference"] = _pink_noise_reference(
                spectral.get("ltas_40_band_relative_db") or []
            )
        peaks_found = spectral["dominant_peaks"]
        close_pairs = []
        for first_index, first in enumerate(peaks_found):
            for second in peaks_found[first_index + 1 :]:
                tolerance = max(30.0, min(first["frequency_hz"], second["frequency_hz"]) * 0.08)
                if abs(first["frequency_hz"] - second["frequency_hz"]) <= tolerance:
                    close_pairs.append({"frequency_a_hz": first["frequency_hz"], "frequency_b_hz": second["frequency_hz"], "separation_hz": round(abs(first["frequency_hz"] - second["frequency_hz"]), 3)})
        spectral["masking_candidates"] = close_pairs[:5]
        if close_pairs:
            findings.append(_finding(
                "possible_masking_candidate", confidence=0.45, severity="informational",
                evidence={"close_spectral_peaks": close_pairs[:5]},
                explanation="Two measured spectral peaks are close enough to merit a masking check; an FFT cannot prove that two musical sources are masking each other.",
                test="In Ableton, mute/solo the suspected sources, then compare at matched level in mono and in the densest section.",
            ))
        high = spectral["band_energy_dbfs"].get("high", -120.0)
        if high > -24.0:
            findings.append(_finding(
                "possible_high_frequency_harshness", confidence=0.35, severity="informational",
                evidence={"high_band_energy_dbfs": high},
                explanation="High-frequency energy is prominent in the measured spectrum; this is not proof of harshness or sibilance.",
                test="A/B a narrow dynamic cut around the offending consonant/cymbal moments at matched output, not on the whole file in isolation.",
            ))
        if peaks_found and peaks_found[0]["bandwidth_hz"] <= spectral["bin_width_hz"] * 3 and peaks_found[0]["level_dbfs"] > -30.0:
            findings.append(_finding(
                "possible_resonance", confidence=0.5, severity="informational",
                evidence={"peak": peaks_found[0]},
                explanation="A narrow, strong spectral peak was measured. It may be a tonal component or resonance; context and time localisation are required before cutting it.",
                test="Sweep a narrow EQ band around the measured frequency while listening to the full mix, then bypass at matched level.",
            ))

    if clip_runs:
        findings.append(_finding("clipping", confidence=0.95, severity="high", evidence={"clipped_sample_count": clip_count, "clipped_run_count": clip_runs, "threshold_dbfs": -0.3}, explanation="Sustained near-full-scale sample runs were measured; this does not include inter-sample true peaks.", test="Inspect the loudest section with a true-peak meter and bypass upstream limiters one at a time."))
    if channel_count == 2 and metrics.get("correlation") is not None and metrics["correlation"] < -0.5:
        findings.append(_finding("mono_compatibility_risk", confidence=0.9, severity="high", evidence={"correlation": metrics["correlation"], "mono_cancellation_drop_db": metrics.get("mono_cancellation_drop_db")}, explanation="The channel correlation is strongly negative, which is consistent with polarity or phase cancellation.", test="Switch Ableton Utility to Mono and compare the low end and lead elements before changing width."))

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "schema": RESULT_SCHEMA,
        "analysis_version": ANALYSIS_VERSION,
        "ok": True,
        "analysis_status": "abstained" if spectral_abstention_reason else "complete",
        "input_hash": input_hash,
        "filename": filename,
        "analysis_timestamp": timestamp,
        "metrics": metrics,
        "spectral": spectral,
        "findings": findings,
        "confidence": 0.0 if spectral_abstention_reason else 0.85,
        "severity": "unknown" if spectral_abstention_reason else ("high" if any(f["severity"] == "high" for f in findings) else "none"),
        "evidence": "Measurements are calculated from decoded PCM samples in this request; spectral features are not proof of a mix problem.",
        "explanation": "KENN reports signal measurements and bounded hypotheses. Use the suggested listening test before making a musical decision.",
        "limitations": [
            "Sample peak is measured; true peak/inter-sample reconstruction is not implemented.",
            "No calibrated ITU-R BS.1770 LUFS or LRA is reported.",
            "FFT peaks include a bounded set of localized windows, not a continuous STFT or source separation.",
            "Masking, resonance, harshness, and sibilance findings are hypotheses requiring listening context.",
        ],
        "suggested_ableton_workflow": "Open Spectrum or EQ Eight, inspect the measured region in the densest section, audition one narrow change, level-match, and bypass to compare.",
        "receipt_id": f"receipt-{uuid.uuid4().hex}",
        "runtime_ms": round(elapsed_ms, 3),
    }


__all__ = ["ANALYSIS_VERSION", "RESULT_SCHEMA", "AudioAnalysisError", "analyze_wav"]
