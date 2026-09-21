#!/usr/bin/env python3
"""Verify the reference path remains functional when native DSP is disabled."""

from __future__ import annotations

import io
import math
import struct
import wave

from kenn.core.audio_analysis import analyze_wav
from kenn.core.native_fft import available, channel_metrics, spectral_powers


def _fixture() -> bytes:
    sample_rate = 48_000
    frames = bytearray()
    for index in range(sample_rate // 2):
        value = int(round(0.25 * 32767.0 * math.sin(2.0 * math.pi * 440.0 * index / sample_rate)))
        frames.extend(struct.pack("<h", value))
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)
    return output.getvalue()


def main() -> None:
    if available():
        raise AssertionError("native backend should be disabled for this check")
    if spectral_powers([0.0, 1.0], 256) is not None:
        raise AssertionError("disabled native spectral path returned a result")
    if channel_metrics([[0.0, 1.0]]) is not None:
        raise AssertionError("disabled native metrics path returned a result")

    result = analyze_wav(_fixture(), filename="native-fallback.wav", fft_size=1024)
    if result.get("ok") is not True or result.get("analysis_status") != "complete":
        raise AssertionError(f"reference analysis failed: {result}")
    spectral = result.get("spectral") or {}
    if spectral.get("implementation") != "python-reference":
        raise AssertionError(f"reference implementation was not visible: {spectral}")
    print("native-disabled reference fallback passed")


if __name__ == "__main__":
    main()
