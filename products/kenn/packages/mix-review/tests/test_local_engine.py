"""Tests for the KENN-owned local Mix Review engine and its fallback path.

These generate synthetic WAV fixtures in-memory (no external audio, no
network, no Audio_Too checkout) and assert that each qualified fault family
fires (or correctly abstains) on inputs constructed to exercise it.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import local_engine  # noqa: E402


def _wav_bytes(
    channels: list[list[float]],
    *,
    framerate: int = 44100,
    sampwidth: int = 2,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(len(channels))
        handle.setsampwidth(sampwidth)
        handle.setframerate(framerate)
        n = len(channels[0])
        scale = (1 << (sampwidth * 8 - 1)) - 1
        frames = bytearray()
        for i in range(n):
            for ch in channels:
                value = max(-1.0, min(1.0, ch[i]))
                ivalue = int(round(value * scale))
                if sampwidth == 2:
                    frames += struct.pack("<h", ivalue)
                elif sampwidth == 3:
                    ivalue &= 0xFFFFFF
                    frames += bytes([ivalue & 0xFF, (ivalue >> 8) & 0xFF, (ivalue >> 16) & 0xFF])
        handle.writeframes(bytes(frames))
    return buffer.getvalue()


def _sine(n: int, freq: float, framerate: int, amplitude: float = 0.5, phase: float = 0.0) -> list[float]:
    return [amplitude * math.sin(2 * math.pi * freq * i / framerate + phase) for i in range(n)]


def _healthy_stereo_wav(seconds: float = 2.0, framerate: int = 44100) -> bytes:
    # Amplitude chosen so RMS lands well below the loudness_estimate flag
    # threshold -- a full-scale sine tone has only ~3 dB crest factor and
    # would misleadingly read as "hot" despite being far from clipping.
    n = int(seconds * framerate)
    left = _sine(n, 440.0, framerate, amplitude=0.2)
    right = _sine(n, 440.0, framerate, amplitude=0.2, phase=0.05)
    return _wav_bytes([left, right], framerate=framerate)


def _finding(report: dict, family: str) -> dict:
    for finding in report["findings"]:
        if finding["fault_family"] == family:
            return finding
    raise AssertionError(f"no finding for {family}")


def test_validate_rejects_empty_and_non_wav_bytes() -> None:
    assert local_engine.validate_wav_upload(b"", "empty.wav")["ok"] is False
    assert local_engine.validate_wav_upload(b"not a wav file at all", "bad.wav")["ok"] is False


def test_validate_accepts_healthy_stereo_wav() -> None:
    result = local_engine.validate_wav_upload(_healthy_stereo_wav(), "healthy.wav")
    assert result["ok"] is True


def test_healthy_mix_flags_nothing_qualified() -> None:
    report = local_engine.analyze_wav(_healthy_stereo_wav(), filename="healthy.wav")
    assert report["ok"] is True
    for family in local_engine.QUALIFIED_FAULT_FAMILIES:
        assert _finding(report, family)["detected"] is False, family
    assert report["technical_rating"] == "No qualified issues found"
    assert report["input_context"]["channel_layout"] == "stereo"
    assert report["runtime_provenance"]["external_dependency"] is None


def test_clipping_is_detected_with_evidence() -> None:
    n = int(2.0 * 44100)
    hot = _sine(n, 440.0, 44100, amplitude=1.3)  # will be clamped to full scale in _wav_bytes
    payload = _wav_bytes([hot, hot], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="clipped.wav")
    finding = _finding(report, "clipping")
    assert finding["detected"] is True
    assert finding["evidence"]["clipped_sample_count"] > 0
    assert finding["severity"] in ("low", "high")


def test_low_headroom_is_detected() -> None:
    n = int(2.0 * 44100)
    hot = _sine(n, 440.0, 44100, amplitude=0.98)
    payload = _wav_bytes([hot, hot], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="hot.wav")
    finding = _finding(report, "headroom")
    assert finding["detected"] is True
    assert finding["evidence"]["sample_peak_dbfs"] > -1.0


def test_silence_is_detected() -> None:
    n = int(2.0 * 44100)
    silence = [0.0] * n
    payload = _wav_bytes([silence, silence], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="silent.wav")
    finding = _finding(report, "silence_or_truncation")
    assert finding["detected"] is True


def test_channel_imbalance_is_detected() -> None:
    n = int(2.0 * 44100)
    loud = _sine(n, 440.0, 44100, amplitude=0.5)
    quiet = _sine(n, 440.0, 44100, amplitude=0.05)
    payload = _wav_bytes([loud, quiet], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="imbalanced.wav")
    finding = _finding(report, "channel_imbalance")
    assert finding["detected"] is True
    assert finding["evidence"]["imbalance_db"] >= local_engine.IMBALANCE_FLAG_DB


def test_inverted_polarity_is_detected() -> None:
    n = int(2.0 * 44100)
    left = _sine(n, 440.0, 44100, amplitude=0.5)
    right = [-v for v in left]  # fully inverted -> perfect phase cancellation
    payload = _wav_bytes([left, right], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="out-of-phase.wav")
    finding = _finding(report, "phase_polarity_mono_compatibility")
    assert finding["detected"] is True
    assert finding["evidence"]["lr_correlation"] < 0


def test_loudness_estimate_is_detected_with_evidence() -> None:
    """loudness_estimate is a qualified fault family with no positive-detection
    test until now, the same gap dc_offset had. Peak stays well below the
    headroom threshold (-1.0 dBFS) so this exercises the RMS-based loudness
    check in isolation, not a confounded clipping/headroom finding."""
    n = int(2.0 * 44100)
    hot_rms = _sine(n, 440.0, 44100, amplitude=0.5)  # peak ~-6 dBFS, RMS ~-9 dBFS
    payload = _wav_bytes([hot_rms, hot_rms], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="hot-rms.wav")
    finding = _finding(report, "loudness_estimate")
    assert finding["detected"] is True
    assert finding["evidence"]["estimated_loudness_dbfs_rms"] > local_engine.HOT_LOUDNESS_ESTIMATE_DBFS
    headroom = _finding(report, "headroom")
    assert headroom["detected"] is False


def test_dc_offset_is_detected_with_evidence() -> None:
    """dc_offset is a qualified fault family (local_engine.QUALIFIED_FAULT_FAMILIES)
    but had no positive-detection test until now -- test_healthy_mix_flags_nothing_qualified
    only proved it stays quiet on a clean signal, never that it actually fires."""
    n = int(2.0 * 44100)
    biased = [v + 0.05 for v in _sine(n, 440.0, 44100, amplitude=0.3)]
    payload = _wav_bytes([biased, biased], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="dc-biased.wav")
    finding = _finding(report, "dc_offset")
    assert finding["detected"] is True
    assert finding["severity"] == "low"
    assert max(abs(v) for v in finding["evidence"]["per_channel_dc_offset"]) >= local_engine.DC_OFFSET_FLAG


def test_mono_audio_abstains_on_stereo_only_families() -> None:
    n = int(2.0 * 44100)
    mono = _sine(n, 440.0, 44100, amplitude=0.3)
    payload = _wav_bytes([mono], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="mono.wav")
    for family in ("channel_imbalance", "phase_polarity_mono_compatibility"):
        finding = _finding(report, family)
        assert finding["detected"] is False
        assert finding["confidence"] == 0.0
        assert finding["severity"] == "unknown"


def test_too_short_audio_abstains_on_all_qualified_families() -> None:
    n = int(0.2 * 44100)
    tiny = _sine(n, 440.0, 44100, amplitude=0.3)
    payload = _wav_bytes([tiny, tiny], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="tiny.wav")
    for family in local_engine.QUALIFIED_FAULT_FAMILIES:
        finding = _finding(report, family)
        assert finding["detected"] is False
        assert finding["confidence"] == 0.0


def test_not_evaluated_families_are_explicit_not_silent() -> None:
    report = local_engine.analyze_wav(_healthy_stereo_wav(), filename="healthy.wav")
    families = {f["fault_family"] for f in report["findings"]}
    for family in local_engine.NOT_EVALUATED_FAULT_FAMILIES:
        assert family in families
        finding = _finding(report, family)
        assert finding["confidence"] == 0.0
        assert "not implemented" in finding["explanation"]


def test_corrupted_wav_fails_analysis_honestly() -> None:
    truncated = _healthy_stereo_wav()[:20]
    validation = local_engine.validate_wav_upload(truncated, "truncated.wav")
    assert validation["ok"] is False


def test_receipt_has_provenance_and_timestamp() -> None:
    report = local_engine.analyze_wav(_healthy_stereo_wav(), filename="healthy.wav")
    assert report["receipt_id"]
    assert report["timestamp"]
    assert report["analysis_version"] == local_engine.ANALYSIS_VERSION
    assert report["runtime_provenance"]["external_dependency"] is None


def test_24bit_pcm_is_supported() -> None:
    payload = _healthy_stereo_wav()
    payload24 = _wav_bytes(
        [_sine(int(3.0 * 44100), 440.0, 44100, amplitude=0.4)] * 2,
        framerate=44100,
        sampwidth=3,
    )
    report = local_engine.analyze_wav(payload24, filename="24bit.wav")
    assert report["ok"] is True
    assert report["input_context"]["sample_rate_hz"] == 44100
    # This previously silently passed even though 24-bit decode had no numpy
    # fast path at all, so _calibrated_loudness_and_true_peak's own
    # numpy-array check always failed for every 24-bit file and it abstained
    # with "numpy acceleration is unavailable for this decode path" --
    # regardless of whether numpy was actually installed. Found by testing
    # against real 24-bit corpus files, where the abstention reason string
    # gave it away; this test only ever checked report["ok"], never that the
    # calibrated measurement itself actually ran.
    lufs_finding = _finding(report, "calibrated_lufs_bs1770")
    assert lufs_finding["explanation"] != "KENN abstained on calibrated_lufs_bs1770: numpy acceleration is unavailable for this decode path"
    assert lufs_finding["evidence"].get("integrated_lufs") is not None


def test_16bit_fast_decode_matches_standard_library_decode(monkeypatch) -> None:
    payload = _healthy_stereo_wav(seconds=1.0)
    fast_channels, fast_rate, fast_count = local_engine._decode_channels(payload)
    fast_values = [list(channel) for channel in fast_channels]

    monkeypatch.setattr(local_engine, "_np", None)
    fallback_channels, fallback_rate, fallback_count = local_engine._decode_channels(payload)

    assert (fast_rate, fast_count) == (fallback_rate, fallback_count)
    for fast, fallback in zip(fast_values, fallback_channels):
        assert fast == pytest.approx(list(fallback), abs=1e-12)


def test_24bit_fast_decode_matches_standard_library_decode(monkeypatch) -> None:
    """24-bit had no vectorized decode path at all until this fix -- only
    the per-sample Python loop below, found to cost ~56ms per second of
    real audio (a real ~200s 24-bit mixdown took ~11.2s to decode) versus
    near-instant for the equivalent numpy path used by 16-bit. Real 24-bit
    files are common in professional mixing/mastering, unlike this
    module's 16-bit-only synthetic benchmark fixtures, which never
    exercised this path's performance at all."""
    payload = _wav_bytes(
        [_sine(int(1.0 * 44100), 440.0, 44100, amplitude=0.4)] * 2,
        framerate=44100,
        sampwidth=3,
    )
    fast_channels, fast_rate, fast_count = local_engine._decode_channels(payload)
    fast_values = [list(channel) for channel in fast_channels]

    monkeypatch.setattr(local_engine, "_np", None)
    fallback_channels, fallback_rate, fallback_count = local_engine._decode_channels(payload)

    assert (fast_rate, fast_count) == (fallback_rate, fallback_count)
    for fast, fallback in zip(fast_values, fallback_channels):
        assert fast == pytest.approx(list(fallback), abs=1e-12)


def test_calibrated_lufs_matches_known_bs1770_reference() -> None:
    # A full-scale 1 kHz MONO sine measures close to the well-known -3.01
    # LUFS ITU-R BS.1770 reference value (this specific reference value is
    # for one channel; a stereo dual-mono signal of the same content reads
    # ~3 dB higher since BS.1770 sums per-channel mean-square power with
    # equal per-channel weighting, not a mono downmix).
    n = int(3.0 * 44100)
    full_scale = _sine(n, 1000.0, 44100, amplitude=1.0)
    payload = _wav_bytes([full_scale], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="reference.wav")
    finding = _finding(report, "calibrated_lufs_bs1770")
    assert finding["evidence"]["integrated_lufs"] == pytest.approx(-3.0, abs=0.5)
    assert isinstance(finding["evidence"]["integrated_lufs"], float)  # never a numpy scalar
    assert report["metrics"]["integrated_lufs"] == finding["evidence"]["integrated_lufs"]


def test_true_peak_detects_inter_sample_overshoot_above_sample_peak() -> None:
    n = int(2.0 * 44100)
    # A near-full-scale sine has real inter-sample reconstruction overshoot;
    # true peak should read at or above the sample peak, not merely equal.
    hot = _sine(n, 997.0, 44100, amplitude=0.999)
    payload = _wav_bytes([hot, hot], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="true-peak.wav")
    finding = _finding(report, "true_peak_intersample")
    sample_peak_dbfs = _finding(report, "headroom")["evidence"]["sample_peak_dbfs"]
    assert finding["evidence"]["true_peak_dbtp"] >= sample_peak_dbfs
    assert isinstance(finding["evidence"]["true_peak_dbtp"], float)


def test_calibrated_loudness_is_json_serializable() -> None:
    import json

    report = local_engine.analyze_wav(_healthy_stereo_wav(), filename="healthy.wav")
    json.dumps(report)  # must not raise on numpy scalar leakage


def test_silence_abstains_on_calibrated_loudness_instead_of_reporting_negative_infinity() -> None:
    n = int(2.0 * 44100)
    silence = [0.0] * n
    payload = _wav_bytes([silence, silence], framerate=44100)
    report = local_engine.analyze_wav(payload, filename="silence.wav")
    finding = _finding(report, "calibrated_lufs_bs1770")
    assert finding["detected"] is False
    assert finding["confidence"] == 0.0
    assert "abstained" in finding["explanation"]


def test_calibrated_loudness_abstains_honestly_when_dependency_is_unavailable(monkeypatch) -> None:
    # Calibrated measurement is numpy-native now (vendored BS.1770; the
    # pyloudnorm/scipy path is preferred when installed but no longer
    # required). The honest-abstention contract therefore attaches to numpy
    # itself: with no numpy there is no measurement, only an explicit
    # abstention -- never a guessed number.
    monkeypatch.setattr(local_engine, "_np", None)
    report = local_engine.analyze_wav(_healthy_stereo_wav(), filename="healthy.wav")
    finding = _finding(report, "calibrated_lufs_bs1770")
    assert finding["detected"] is False
    assert finding["confidence"] == 0.0
    assert "not installed" in finding["explanation"]
    finding_tp = _finding(report, "true_peak_intersample")
    assert finding_tp["confidence"] == 0.0


def _wav_bytes_float32(
    channels: list[list[float]],
    *,
    framerate: int = 44100,
) -> bytes:
    """Construct an IEEE 754 32-bit float WAV byte buffer."""
    num_channels = len(channels)
    num_frames = len(channels[0]) if channels else 0
    raw_data = bytearray()
    for i in range(num_frames):
        for ch in channels:
            raw_data += struct.pack("<f", float(ch[i]))
    byte_rate = framerate * num_channels * 4
    block_align = num_channels * 4
    fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 3, num_channels, framerate, byte_rate, block_align, 32)
    data_chunk = struct.pack("<4sI", b"data", len(raw_data)) + raw_data
    riff_size = 4 + len(fmt_chunk) + len(data_chunk)
    riff_header = struct.pack("<4sI4s", b"RIFF", riff_size, b"WAVE")
    return riff_header + fmt_chunk + data_chunk


def test_32bit_float_wav_is_supported_and_validated() -> None:
    n = int(2.0 * 44100)
    left = _sine(n, 440.0, 44100, amplitude=0.2)
    right = _sine(n, 440.0, 44100, amplitude=0.2, phase=0.05)
    payload = _wav_bytes_float32([left, right], framerate=44100)

    val = local_engine.validate_wav_upload(payload, "healthy_32bit.wav")
    assert val["ok"] is True

    report = local_engine.analyze_wav(payload, filename="healthy_32bit.wav")
    assert report["ok"] is True
    assert report["technical_rating"] == "No qualified issues found"
    assert report["metrics"]["integrated_lufs"] is not None
    assert report["metrics"]["peak_dbfs"] is not None


def test_32bit_float_fast_decode_matches_standard_library_decode(monkeypatch) -> None:
    n = int(1.0 * 44100)
    left = _sine(n, 440.0, 44100, amplitude=0.3)
    right = _sine(n, 440.0, 44100, amplitude=0.3, phase=0.1)
    payload = _wav_bytes_float32([left, right], framerate=44100)

    fast_channels, fast_rate, fast_count = local_engine._decode_channels(payload)
    fast_values = [list(channel) for channel in fast_channels]

    monkeypatch.setattr(local_engine, "_np", None)
    fallback_channels, fallback_rate, fallback_count = local_engine._decode_channels(payload)

    assert (fast_rate, fast_count) == (fallback_rate, fallback_count)
    for fast, fallback in zip(fast_values, fallback_channels):
        assert fast == pytest.approx(list(fallback), abs=1e-6)


def test_32bit_float_clipping_is_detected() -> None:
    n = int(2.0 * 44100)
    clipped_sine = [min(1.0, max(-1.0, 1.5 * math.sin(2 * math.pi * 440.0 * i / 44100))) for i in range(n)]
    payload = _wav_bytes_float32([clipped_sine, clipped_sine], framerate=44100)

    report = local_engine.analyze_wav(payload, filename="clipped_32bit.wav")
    assert report["ok"] is True
    finding = _finding(report, "clipping")
    assert finding["detected"] is True
    assert finding["evidence"]["clipped_sample_count"] > 0


def test_unsupported_audio_format_tag_is_rejected() -> None:
    # Format tag 7 is mu-law
    fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 7, 2, 44100, 44100 * 2, 2, 8)
    data_chunk = struct.pack("<4sI", b"data", 100) + b"\x00" * 100
    riff_header = struct.pack("<4sI4s", b"RIFF", 4 + len(fmt_chunk) + len(data_chunk), b"WAVE")
    payload = riff_header + fmt_chunk + data_chunk

    val = local_engine.validate_wav_upload(payload, "mulaw.wav")
    assert val["ok"] is False
    assert "Unsupported audio format tag" in val["error"]


def test_extensible_wav_format_supported() -> None:
    n = int(1.5 * 44100)
    left = _sine(n, 440.0, 44100, amplitude=0.2)
    right = _sine(n, 440.0, 44100, amplitude=0.2, phase=0.05)
    raw_data = bytearray()
    for i in range(n):
        raw_data += struct.pack("<ff", float(left[i]), float(right[i]))
    # SubFormat GUID for IEEE float: {00000003-0000-0010-8000-00AA00389B71}
    subformat_guid = struct.pack("<H", 3) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
    fmt_data = struct.pack("<HHIIHHHHI", 0xFFFE, 2, 44100, 44100 * 8, 8, 32, 22, 32, 3) + subformat_guid
    fmt_chunk = struct.pack("<4sI", b"fmt ", len(fmt_data)) + fmt_data
    data_chunk = struct.pack("<4sI", b"data", len(raw_data)) + raw_data
    riff_header = struct.pack("<4sI4s", b"RIFF", 4 + len(fmt_chunk) + len(data_chunk), b"WAVE")
    payload = riff_header + fmt_chunk + data_chunk

    val = local_engine.validate_wav_upload(payload, "extensible.wav")
    assert val["ok"] is True

    report = local_engine.analyze_wav(payload, filename="extensible.wav")
    assert report["ok"] is True
    assert report["metrics"]["peak_dbfs"] is not None
