from __future__ import annotations

import io
import math
import struct
import wave

from kenn.core.audio_analysis import RESULT_SCHEMA, _pink_noise_reference, analyze_wav


def wav(channels: list[list[float]], rate: int = 48000, width: int = 2) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as handle:
        handle.setnchannels(len(channels))
        handle.setsampwidth(width)
        handle.setframerate(rate)
        frames = bytearray()
        scale = 32767 if width == 2 else 8388607
        for index in range(len(channels[0])):
            for channel in channels:
                value = max(-1.0, min(1.0, channel[index]))
                integer = int(round(value * scale))
                if width == 2:
                    frames.extend(struct.pack("<h", integer))
                else:
                    integer &= 0xFFFFFF
                    frames.extend(bytes((integer & 255, (integer >> 8) & 255, (integer >> 16) & 255)))
        handle.writeframes(frames)
    return out.getvalue()


def sine(seconds: float, hz: float, rate: int = 48000, amplitude: float = 0.5) -> list[float]:
    return [amplitude * math.sin(2 * math.pi * hz * index / rate) for index in range(int(seconds * rate))]


def test_sine_peak_is_measured_with_auditable_metadata() -> None:
    rate = 48000
    report = analyze_wav(wav([sine(1.0, 1000.0, rate)]), filename="tone.wav")
    assert report["schema"] == RESULT_SCHEMA
    assert report["ok"] is True
    assert report["analysis_status"] == "complete"
    assert abs(report["spectral"]["dominant_peaks"][0]["frequency_hz"] - 1000.0) < 48000 / 16384
    assert -10.0 < report["metrics"]["rms_dbfs"] < -8.0
    assert report["metrics"]["crest_factor_db"] > 2.5


def test_harmonic_fixture_reports_multiple_peaks_and_bands() -> None:
    rate = 44100
    fundamental = sine(1.0, 220.0, rate, 0.35)
    harmonic = sine(1.0, 440.0, rate, 0.18)
    report = analyze_wav(
        wav([[a + b for a, b in zip(fundamental, harmonic)]], rate),
        filename="harmonics.wav", include_ltas=True,
    )
    frequencies = [peak["frequency_hz"] for peak in report["spectral"]["dominant_peaks"]]
    assert any(abs(value - 220.0) < 44100 / 16384 for value in frequencies)
    assert any(abs(value - 440.0) < 44100 / 16384 for value in frequencies)
    assert set(report["spectral"]["band_energy_dbfs"]) == {"low", "low_mid", "mid", "upper_mid", "high"}
    ltas = report["spectral"]["ltas_40_band_relative_db"]
    assert ltas
    assert any(750.0 <= row["center_hz"] <= 1250.0 for row in ltas)
    assert all("relative_db" in row for row in ltas)


def test_pink_noise_reference_is_explicit_and_relative() -> None:
    comparison = _pink_noise_reference([
        {"index": 0, "center_hz": 1000.0, "relative_db": 0.0},
        {"index": 1, "center_hz": 250.0, "relative_db": 10.0},
    ])
    assert comparison["status"] == "complete"
    assert comparison["curve"] == "-3 dB per octave pink-noise-style spectral baseline"
    assert comparison["anchor_frequency_hz"] == 1000.0
    assert comparison["largest_deviation"]["center_hz"] == 250.0
    assert comparison["largest_deviation"]["deviation_db"] == 4.0
    assert "quality score" not in comparison["curve"].lower()


def test_pink_noise_reference_is_opt_in_on_audio_reports() -> None:
    report = analyze_wav(
        wav([sine(1.0, 300.0, 48000)]),
        filename="pink-reference-probe.wav",
        include_pink_noise_reference=True,
    )
    assert report["spectral"]["pink_noise_reference"]["status"] == "complete"
    assert report["spectral"]["pink_noise_reference"]["bands"]


def test_spectral_result_exposes_bounded_time_localized_windows() -> None:
    rate = 48000
    transient = [0.0] * rate + sine(1.0, 2200.0, rate, amplitude=0.5)
    report = analyze_wav(wav([transient], rate), filename="localized-transient.wav")

    spectral = report["spectral"]
    windows = spectral["time_localized_windows"]
    assert len(windows) == spectral["windows_averaged"] == 4
    assert windows[0]["start_seconds"] == 0.0
    assert windows[-1]["end_seconds"] == 2.0
    assert all(
        0.0 <= window["start_seconds"] < window["end_seconds"] <= 2.0
        for window in windows
    )

    quiet_windows = [window for window in windows if window["end_seconds"] <= 1.0]
    active_windows = [window for window in windows if window["start_seconds"] >= 1.0]
    assert quiet_windows and active_windows
    assert max(window["rms_dbfs"] for window in active_windows) > max(
        window["rms_dbfs"] for window in quiet_windows
    ) + 20.0
    assert any(
        abs(peak["frequency_hz"] - 2200.0) < max(5.0, rate / 16384)
        for window in active_windows
        for peak in window["dominant_peaks"]
    )
    assert not any(
        abs(peak["frequency_hz"] - 2200.0) < max(5.0, rate / 16384)
        for window in quiet_windows
        for peak in window["dominant_peaks"]
    )


def test_localized_windows_cover_the_tail_of_sub_two_fft_length_audio() -> None:
    rate = 48000
    duration = 0.4
    report = analyze_wav(wav([sine(duration, 900.0, rate)], rate), filename="overlap.wav")
    windows = report["spectral"]["time_localized_windows"]

    assert len(windows) == 2
    assert windows[0]["start_seconds"] == 0.0
    assert windows[-1]["end_seconds"] == duration
    assert windows[-1]["start_seconds"] > 0.0


def test_stereo_phase_cancellation_is_evidence_not_a_subjective_claim() -> None:
    left = sine(1.0, 100.0, 48000)
    report = analyze_wav(wav([left, [-value for value in left]]), filename="phase.wav")
    assert report["metrics"]["correlation"] < -0.99
    finding = next(item for item in report["findings"] if item["type"] == "mono_compatibility_risk")
    assert finding["evidence"]["correlation"] < -0.5
    assert "cannot" not in finding["explanation"].lower()


def test_silence_and_short_audio_abstain_from_spectral_interpretation() -> None:
    silent = analyze_wav(wav([[0.0] * 48000]), filename="silence.wav")
    assert silent["analysis_status"] == "abstained"
    assert silent["spectral"]["status"] == "abstained"
    short = analyze_wav(wav([[0.0] * 100]), filename="short.wav")
    assert short["analysis_status"] == "abstained"
    assert short["spectral"]["status"] == "abstained"


def test_24_bit_and_corrupt_inputs_are_handled_truthfully() -> None:
    report = analyze_wav(wav([sine(0.5, 80.0, 48000)], width=3), filename="sub.wav")
    assert report["ok"] is True
    bad = analyze_wav(b"RIFF-but-not-a-wave", filename="bad.wav")
    assert bad["ok"] is False
    assert "invalid WAV" in bad["error"]


def test_32_bit_float_wav_is_supported_in_audio_analysis() -> None:
    rate = 44100
    n = int(1.0 * rate)
    raw_data = bytearray()
    for i in range(n):
        val = 0.4 * math.sin(2 * math.pi * 440.0 * i / rate)
        raw_data += struct.pack("<ff", val, val)
    fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 3, 2, rate, rate * 8, 8, 32)
    data_chunk = struct.pack("<4sI", b"data", len(raw_data)) + raw_data
    riff_header = struct.pack("<4sI4s", b"RIFF", 4 + len(fmt_chunk) + len(data_chunk), b"WAVE")
    payload = riff_header + fmt_chunk + data_chunk

    report = analyze_wav(payload, filename="float32.wav", include_ltas=True)
    assert report["ok"] is True
    assert report["spectral"]["status"] == "complete"
    assert any(abs(peak["frequency_hz"] - 440.0) < 44100 / 16384 for peak in report["spectral"]["dominant_peaks"])

