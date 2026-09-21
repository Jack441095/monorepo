#!/usr/bin/env python3
"""Deterministic smoke and parity checks for the optional native DSP wheel.

This script is intentionally dependency-light so it can run immediately after
the wheel is installed on macOS or Windows CI. It checks the public exports,
the PCM decoder contract, basic numerical contracts, and the fail-fast
validation paths that are easy to miss in a one-value import smoke test.
"""

from __future__ import annotations

import math
import io
import struct
import wave

import numpy as np

import kenn.core._kenn_dsp_native as native
try:
    from kenn.core import audio_analysis, native_fft
except ImportError:
    # The installed wheel smoke intentionally contains only the extension;
    # source-tree parity is exercised when the backend source is available.
    audio_analysis = None
    native_fft = None


def _assert_close(actual: float, expected: float, *, tolerance: float = 1e-6) -> None:
    if not math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance):
        raise AssertionError(f"expected {expected}, got {actual}")


def _expect_error(callable_, message: str) -> None:
    try:
        callable_()
    except (TypeError, ValueError):
        return
    raise AssertionError(message)


def _wav_fixture(*, width: int = 2, channels: int = 2, audio_format: int = 1) -> bytes:
    values = [1200, -1200] if width == 2 else [120000, -120000]
    if width == 3:
        frame = b"".join(int(value).to_bytes(3, "little", signed=True) for value in values[:channels])
        frames = frame * 128
    elif width == 4 and audio_format == 3:
        frame = b"".join(struct.pack("<f", value / 1_000_000.0) for value in values[:channels])
        frames = frame * 128
    elif width == 4:
        frame = b"".join(struct.pack("<i", value * 1000) for value in values[:channels])
        frames = frame * 128
    else:
        frame = b"".join(struct.pack("<h", value) for value in values[:channels])
        frames = frame * 128
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(48_000)
        handle.writeframes(frames)
    payload = output.getvalue()
    if audio_format == 3:
        # wave writes PCM format 1; replace the format tag with IEEE float.
        payload = payload[:20] + struct.pack("<H", 3) + payload[22:]
    return payload


def _assert_decoder_parity(payload: bytes) -> None:
    if audio_analysis is None or native_fft is None:
        return
    native_result = dict(native.decode_pcm(np.frombuffer(payload, dtype=np.uint8)))
    native_channels = [np.asarray(channel, dtype=np.float32) for channel in native_result["channels"]]
    original_decode = native_fft.decode_pcm
    native_fft.decode_pcm = lambda _payload: None
    try:
        reference_channels, reference_rate, reference_count, reference_depth = audio_analysis._decode(payload)
    finally:
        native_fft.decode_pcm = original_decode
    if int(native_result["sample_rate"]) != reference_rate:
        raise AssertionError("native decoder changed the sample rate")
    if int(native_result["channel_count"]) != reference_count or int(native_result["bit_depth"]) != reference_depth:
        raise AssertionError("native decoder changed WAV metadata")
    if len(native_channels) != len(reference_channels):
        raise AssertionError("native decoder changed channel count")
    for actual, expected in zip(native_channels, reference_channels):
        np.testing.assert_allclose(actual, np.asarray(expected, dtype=np.float32), rtol=2e-6, atol=2e-6)


def main() -> None:
    for name in ("decode_pcm", "spectral_power", "mono_metrics", "stereo_metrics", "loudness_metrics", "automix"):
        if not hasattr(native, name):
            raise AssertionError(f"native extension is missing {name}")

    sample_count = 4096
    phase = np.arange(sample_count, dtype=np.float32)
    samples = (0.35 * np.sin(2.0 * np.pi * phase / 64.0)).astype(np.float32)
    inverted = -samples

    decoded = dict(native.decode_pcm(np.frombuffer(_wav_fixture(), dtype=np.uint8)))
    decoded_channels = [np.asarray(channel) for channel in decoded["channels"]]
    if int(decoded["sample_rate"]) != 48_000 or int(decoded["channel_count"]) != 2 or int(decoded["bit_depth"]) != 16:
        raise AssertionError(f"unexpected decoded WAV metadata: {decoded}")
    if len(decoded_channels) != 2 or decoded_channels[0].shape != (128,) or decoded_channels[1].shape != (128,):
        raise AssertionError("native WAV decoder returned unexpected channel shapes")
    _assert_close(float(decoded_channels[0][0]), 1200.0 / 32768.0, tolerance=1e-7)
    _assert_close(float(decoded_channels[1][0]), -1200.0 / 32768.0, tolerance=1e-7)
    for payload in (
        _wav_fixture(width=2, channels=1),
        _wav_fixture(width=3, channels=1),
        _wav_fixture(width=4, channels=1),
        _wav_fixture(width=4, channels=2, audio_format=3),
    ):
        _assert_decoder_parity(payload)

    mono = dict(native.mono_metrics(samples))
    _assert_close(float(mono["peak"]), 0.35, tolerance=2e-5)
    _assert_close(float(mono["rms"]), 0.35 / math.sqrt(2.0), tolerance=2e-5)
    if int(mono["clipped_sample_count"]) != 0:
        raise AssertionError("unexpected clipping in the deterministic mono fixture")

    stereo = dict(native.stereo_metrics(samples, inverted))
    _assert_close(float(stereo["correlation"]), -1.0, tolerance=2e-6)
    _assert_close(float(stereo["mono_rms"]), 0.0, tolerance=2e-6)
    _assert_close(float(stereo["side_rms"]), 0.35 / math.sqrt(2.0), tolerance=2e-5)

    spectral = dict(native.spectral_power(samples, 1024, 48_000))
    if int(spectral["fft_size"]) != 1024:
        raise AssertionError(f"unexpected FFT size: {spectral['fft_size']}")
    powers = np.asarray(spectral["powers"])
    windows = np.asarray(spectral["window_powers"])
    window_rms = np.asarray(spectral["window_rms"])
    if powers.shape != (1, 513) or windows.ndim != 2 or windows.shape[1] != 513 or window_rms.shape != (windows.shape[0],):
        raise AssertionError(f"unexpected spectral shapes: {powers.shape}, {windows.shape}, {window_rms.shape}")
    if not np.isfinite(powers).all() or not np.isfinite(windows).all():
        raise AssertionError("native spectral output contains non-finite values")
    expected_window_rms = float(np.sqrt(np.mean(samples[:1024] * samples[:1024])))
    if not np.isfinite(window_rms).all() or not math.isclose(float(window_rms[0]), expected_window_rms, rel_tol=2e-5, abs_tol=2e-5):
        raise AssertionError("native localized RMS output is incorrect")
    if set(dict(spectral["band_energy_dbfs"])) != {"low", "low_mid", "mid", "upper_mid", "high"}:
        raise AssertionError("native band-energy output is incomplete")
    ltas_spectral = dict(native.spectral_power(samples, 1024, 48_000, True))
    ltas_levels = np.asarray(ltas_spectral["ltas_band_levels"])
    if ltas_levels.shape != (40,) or not np.isfinite(ltas_levels).any():
        raise AssertionError("native LTAS output is incomplete")

    masking = dict(native.masking_band_energy(samples, 48_000, 4096, 2048))
    masking_energy = np.asarray(masking["energy"])
    if masking_energy.shape[1] != 7 or not np.isfinite(masking_energy).all():
        raise AssertionError("native masking-band output is invalid")
    if masking.get("backend") not in {"cpp-accelerate", "cpp-scalar"}:
        raise AssertionError(f"unexpected native masking backend: {masking.get('backend')}")

    loudness_samples = np.column_stack((np.resize(samples, 24_000), np.resize(inverted, 24_000)))
    loudness = dict(native.loudness_metrics(loudness_samples, 48_000))
    if not math.isfinite(float(loudness["integrated_lufs"])):
        raise AssertionError("native loudness output is not finite")
    if not math.isfinite(float(loudness["true_peak_dbtp"])):
        raise AssertionError("native true-peak output is not finite")
    if loudness.get("backend") != "cpp-native-k-weighting":
        raise AssertionError(f"unexpected native loudness backend: {loudness.get('backend')}")

    automix = native.automix
    pulse = np.zeros(128, dtype=np.float64)
    pulse[32:96] = 0.5
    limited = dict(automix.limiter(pulse, 1.0, 0.9, 0.9, 2))
    if set(limited) != {"gain", "audio"} or any(np.asarray(limited[key]).shape != pulse.shape for key in limited):
        raise AssertionError("native AutoMix limiter output contract changed")
    if not np.isfinite(np.asarray(limited["audio"])).all():
        raise AssertionError("native AutoMix limiter returned non-finite samples")

    sos = np.asarray([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float64)
    filtered = np.asarray(automix.biquad(sos, pulse))
    np.testing.assert_allclose(filtered, pulse, rtol=1e-12, atol=1e-12)
    corr = dict(automix.correlation(pulse, -pulse, 8))
    _assert_close(float(corr["correlation"]), -1.0, tolerance=1e-12)
    if int(corr["lag"]) != 0:
        raise AssertionError("native AutoMix correlation chose a non-zero lag for inverted buffers")
    smooth = np.asarray(automix.smooth(np.abs(pulse), 0.5, 0.9, 0.0, False))
    gate = np.asarray(automix.gate(np.abs(pulse), 0.2, 0.5, 0.9, 2, 1.0, 0.0))
    threshold = np.asarray(automix.threshold(np.abs(pulse), 2, 0.01, 3.0))
    if any(values.shape != pulse.shape or not np.isfinite(values).all() for values in (smooth, gate, threshold)):
        raise AssertionError("native AutoMix envelope/threshold output contract changed")

    _expect_error(
        lambda: native.mono_metrics(np.asarray([], dtype=np.float32)),
        "empty mono input should be rejected",
    )
    _expect_error(
        lambda: native.stereo_metrics(samples, samples[:-1]),
        "mismatched stereo lengths should be rejected",
    )
    _expect_error(
        lambda: native.spectral_power(samples, 0),
        "zero FFT size should be rejected",
    )
    _expect_error(
        lambda: native.decode_pcm(np.frombuffer(b"not-a-wave", dtype=np.uint8)),
        "malformed WAV input should be rejected",
    )
    _expect_error(
        lambda: native.loudness_metrics(np.zeros((32, 1), dtype=np.float32), 48_000),
        "short loudness input should be rejected",
    )
    print("native DSP smoke/parity checks passed")


if __name__ == "__main__":
    main()
