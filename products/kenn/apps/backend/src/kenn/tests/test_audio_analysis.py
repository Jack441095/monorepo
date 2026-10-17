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


def test_a_polarity_flipped_stereo_file_is_not_reported_as_silent() -> None:
    # Until 16 Oct 2026 silence was counted on the mono sum, so L = -R read as
    # 100% silent and the spectrum abstained on a full-level file.
    left = sine(1.0, 1000.0, 48000)
    report = analyze_wav(wav([left, [-value for value in left]]), filename="flipped.wav")
    assert report["metrics"]["silence_percentage"] < 10.0
    assert report["analysis_status"] == "complete"
    assert report["spectral"]["signal"] == "side"
    assert abs(report["spectral"]["dominant_peaks"][0]["frequency_hz"] - 1000.0) < 48000 / 16384


def test_ordinary_stereo_spectrum_is_measured_on_the_mono_sum() -> None:
    tone = sine(1.0, 500.0, 48000)
    report = analyze_wav(wav([tone, tone]), filename="centred.wav")
    assert report["spectral"]["signal"] == "mono_sum"


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


def test_native_analysis_is_the_default_and_zero_still_forces_the_reference(monkeypatch) -> None:
    # Native became the default on 17 Oct 2026; KENN_DSP_NATIVE=0 is the rollback and must keep working.
    from kenn.core import native_fft

    monkeypatch.setattr(native_fft, "_load_attempted", False)
    monkeypatch.setattr(native_fft, "_native", None)
    monkeypatch.delenv("KENN_DSP_NATIVE", raising=False)
    try:
        from kenn.core import _kenn_dsp_native  # noqa: F401
    except (ImportError, OSError):
        # Without a built extension there is nothing to default to; the reference runs either way.
        assert native_fft.available() is False
    else:
        assert native_fft.available() is True
        default = analyze_wav(wav([sine(0.5, 440.0)], 48000), filename="default.wav")
        assert default["spectral"]["implementation"].startswith("cpp-")
    monkeypatch.setenv("KENN_DSP_NATIVE", "0")
    assert native_fft.available() is False
    assert analyze_wav(wav([sine(0.5, 440.0)], 48000), filename="rollback.wav")["spectral"]["implementation"] == "python-reference"


def test_native_peak_and_ltas_reports_match_reference(monkeypatch) -> None:
    from kenn.core import native_fft

    payload = wav([sine(2.0, 440.0),], 48000)
    native_report = analyze_wav(payload, filename="native-parity.wav", include_ltas=True)
    monkeypatch.setattr(native_fft, "decode_pcm", lambda _payload: None)
    monkeypatch.setattr(native_fft, "channel_metrics", lambda _channels: None)
    monkeypatch.setattr(native_fft, "spectral_powers", lambda *_args, **_kwargs: None)
    reference_report = analyze_wav(payload, filename="native-parity.wav", include_ltas=True)

    native_spectral = dict(native_report["spectral"])
    reference_spectral = dict(reference_report["spectral"])
    native_spectral.pop("implementation", None)
    reference_spectral.pop("implementation", None)
    native_spectral.pop("native_input_copied", None)
    reference_spectral.pop("native_input_copied", None)
    assert native_spectral == reference_spectral
    assert native_report["metrics"] == reference_report["metrics"]
    assert native_report["findings"] == reference_report["findings"]


def test_a_silent_channel_has_no_correlation_on_either_path(monkeypatch) -> None:
    # Until 17 Oct 2026 the native path reported 0.0 here and the reference None,
    # so one silent side read as "fully decorrelated" only when native was built.
    import pytest
    from kenn.core import native_fft

    if not native_fft.available():
        pytest.skip("native extension not built; both halves would run the reference")
    one_side = wav([sine(1.0, 440.0), [0.0] * 48000])
    all_silent = wav([[0.0] * 48000, [0.0] * 48000])
    native = [analyze_wav(payload, filename="flat.wav")["metrics"]["correlation"] for payload in (one_side, all_silent)]
    monkeypatch.setenv("KENN_DSP_NATIVE", "0")
    reference = [analyze_wav(payload, filename="flat.wav")["metrics"]["correlation"] for payload in (one_side, all_silent)]
    assert native == reference == [None, None]


def test_float_wav_with_nan_or_infinity_is_rejected_cleanly(monkeypatch) -> None:
    import json
    import pytest

    for poison in (float("nan"), float("inf"), float("-inf")):
        raw_data = struct.pack("<ffff", 0.1, poison, -0.1, 0.2) * 1024
        fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 3, 2, 48000, 48000 * 8, 8, 32)
        data_chunk = struct.pack("<4sI", b"data", len(raw_data)) + raw_data
        payload = struct.pack("<4sI4s", b"RIFF", 4 + len(fmt_chunk) + len(data_chunk), b"WAVE") + fmt_chunk + data_chunk

        monkeypatch.delenv("KENN_DSP_NATIVE", raising=False)
        native_report = analyze_wav(payload, filename="poison.wav")
        assert native_report["ok"] is False
        assert "NaN or infinite" in native_report["error"]
        json.dumps(native_report, allow_nan=False)

        monkeypatch.setenv("KENN_DSP_NATIVE", "0")
        ref_report = analyze_wav(payload, filename="poison.wav")
        assert ref_report["ok"] is False
        assert "NaN or infinite" in ref_report["error"]
        json.dumps(ref_report, allow_nan=False)

    monkeypatch.delenv("KENN_DSP_NATIVE", raising=False)
    from kenn.core import native_fft

    mod = native_fft._load()
    if mod is not None:
        import numpy as np

        bad = np.array([0.1, float("nan"), -0.1], dtype=np.float32)
        good = np.array([0.1, 0.2, -0.1], dtype=np.float32)
        with pytest.raises(ValueError, match="finite"):
            mod.mono_metrics(bad)
        with pytest.raises(ValueError, match="finite"):
            mod.stereo_metrics(good, bad)
        with pytest.raises(ValueError, match="finite"):
            mod.spectral_power(bad, 256, 48000, False)


def test_steady_tone_reports_zero_silence_and_accurate_off_bin_peak_level(monkeypatch) -> None:
    # A continuous -20 dBFS 1 kHz sine at 48 kHz falls 1/3 of a bin off the
    # 16384-point FFT grid (bin 341.333). Before log-parabola vertex evaluation
    # and 1024-sample block-RMS silence counting, it reported ~4% silence from
    # zero crossings and -20.61 dBFS peak from Hann scalloping loss.
    payload = wav([sine(2.0, 1000.0, amplitude=0.1, rate=48000)], 48000)
    for native_flag in ("1", "0"):
        monkeypatch.setenv("KENN_DSP_NATIVE", native_flag)
        report = analyze_wav(payload, filename="sine_1k.wav")
        assert report["ok"] is True
        assert report["metrics"]["silence_percentage"] == 0.0
        top_peak = report["spectral"]["dominant_peaks"][0]
        assert abs(top_peak["frequency_hz"] - 1000.0) < 0.1
        assert abs(top_peak["level_dbfs"] - (-20.0)) < 0.1

