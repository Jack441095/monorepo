"""Tests for the masking-risk analysis across time-aligned stems.

These generate synthetic WAV fixtures in-memory, matching the style of
test_local_engine.py -- no external audio, no network.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import masking_analysis  # noqa: E402


def _wav_bytes(samples: list[float], *, framerate: int = 44100, sampwidth: int = 2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(sampwidth)
        handle.setframerate(framerate)
        scale = (1 << (sampwidth * 8 - 1)) - 1
        frames = bytearray()
        for value in samples:
            ivalue = int(round(max(-1.0, min(1.0, value)) * scale))
            frames += struct.pack("<h", ivalue) if sampwidth == 2 else struct.pack("<i", ivalue)[:3]
        handle.writeframes(bytes(frames))
    return buffer.getvalue()


def _sine(n: int, freq: float, framerate: int, amplitude: float = 0.5) -> list[float]:
    return [amplitude * math.sin(2 * math.pi * freq * i / framerate) for i in range(n)]


def _finding_bands(result: dict) -> set[str]:
    return {f["band"] for f in result["findings"]}


def test_same_frequency_range_stems_are_flagged_as_competing() -> None:
    n = int(5.0 * 44100)
    a = _wav_bytes(_sine(n, 440.0, 44100))
    b = _wav_bytes(_sine(n, 445.0, 44100))
    result = masking_analysis.analyze_stem_masking([("a", a), ("b", b)])
    assert result["ok"] is True
    assert result["findings"]
    assert all(f["stems"] == ["a", "b"] for f in result["findings"])
    assert all(f["evidence"]["competing_frame_fraction"] >= masking_analysis.COMPETING_FRACTION_FLAG for f in result["findings"])
    assert result["evidence"]["schema"] == "kenn.evidence.v1"
    assert result["evidence"]["source"] == "stem_masking_analysis"
    assert any(fact["name"] == "masking_highest_competing_frame_fraction" for fact in result["evidence"]["facts"])


def test_well_separated_frequency_stems_are_not_flagged() -> None:
    n = int(5.0 * 44100)
    low = _wav_bytes(_sine(n, 100.0, 44100))
    high = _wav_bytes(_sine(n, 10000.0, 44100))
    result = masking_analysis.analyze_stem_masking([("low", low), ("high", high)])
    assert result["ok"] is True
    assert result["findings"] == []


def test_one_stem_playing_alone_is_not_flagged_against_silence() -> None:
    n = int(5.0 * 44100)
    a = _wav_bytes(_sine(n, 440.0, 44100))
    silence = _wav_bytes([0.0] * n)
    result = masking_analysis.analyze_stem_masking([("a", a), ("silence", silence)])
    assert result["ok"] is True
    assert result["findings"] == []


def test_requires_at_least_two_stems() -> None:
    n = int(2.0 * 44100)
    a = _wav_bytes(_sine(n, 440.0, 44100))
    result = masking_analysis.analyze_stem_masking([("a", a)])
    assert result["ok"] is False
    assert "at least 2" in result["error"].lower()


def test_rejects_more_than_the_stem_limit() -> None:
    n = int(2.0 * 44100)
    stems = [(f"s{i}", _wav_bytes(_sine(n, 440.0, 44100))) for i in range(masking_analysis.MAX_STEMS + 1)]
    result = masking_analysis.analyze_stem_masking(stems)
    assert result["ok"] is False
    assert "at most" in result["error"].lower()


def test_rejects_duplicate_labels() -> None:
    n = int(2.0 * 44100)
    a = _wav_bytes(_sine(n, 440.0, 44100))
    result = masking_analysis.analyze_stem_masking([("a", a), ("a", a)])
    assert result["ok"] is False
    assert "unique" in result["error"].lower()


def test_rejects_mismatched_sample_rates() -> None:
    n = int(2.0 * 44100)
    a = _wav_bytes(_sine(n, 440.0, 44100), framerate=44100)
    b = _wav_bytes(_sine(int(2.0 * 48000), 440.0, 48000), framerate=48000)
    result = masking_analysis.analyze_stem_masking([("a44", a), ("b48", b)])
    assert result["ok"] is False
    assert "sample rate" in result["error"].lower()


def test_rejects_shared_duration_below_minimum() -> None:
    n = int(0.5 * 44100)
    a = _wav_bytes(_sine(n, 440.0, 44100))
    b = _wav_bytes(_sine(n, 445.0, 44100))
    result = masking_analysis.analyze_stem_masking([("a", a), ("b", b)])
    assert result["ok"] is False
    assert "minimum" in result["error"].lower()


def test_stems_of_different_lengths_are_compared_over_the_shared_overlap() -> None:
    long_n = int(5.0 * 44100)
    short_n = int(3.0 * 44100)
    long_stem = _wav_bytes(_sine(long_n, 440.0, 44100))
    short_stem = _wav_bytes(_sine(short_n, 445.0, 44100))
    result = masking_analysis.analyze_stem_masking([("long", long_stem), ("short", short_stem)])
    assert result["ok"] is True
    assert result["analyzed_seconds"] == 3.0
    assert result["truncated_stems"] == ["long"]


def test_rejects_invalid_wav_payload() -> None:
    n = int(2.0 * 44100)
    a = _wav_bytes(_sine(n, 440.0, 44100))
    result = masking_analysis.analyze_stem_masking([("a", a), ("bad", b"not a wav file")])
    assert result["ok"] is False


def test_abstains_honestly_when_numpy_is_unavailable(monkeypatch) -> None:
    n = int(2.0 * 44100)
    a = _wav_bytes(_sine(n, 440.0, 44100))
    b = _wav_bytes(_sine(n, 445.0, 44100))
    monkeypatch.setattr(masking_analysis, "_np", None)
    result = masking_analysis.analyze_stem_masking([("a", a), ("b", b)])
    assert result["ok"] is False
    assert "numpy" in result["error"].lower()
