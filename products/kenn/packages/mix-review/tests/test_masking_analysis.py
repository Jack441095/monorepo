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

import pytest

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


def _controlled_activity(monkeypatch, arrays: list[list[list[float]]]) -> dict:
    """Run the real publication path with deterministic per-frame band levels."""
    n = int(2.0 * 44100)
    silence = _wav_bytes([0.0] * n)
    queued = iter(arrays)
    monkeypatch.setattr(
        masking_analysis,
        "_band_energy_over_time_with_backend",
        lambda _signal, _rate: (masking_analysis._np.asarray(next(queued), dtype=float), "test"),
    )
    monkeypatch.setattr(masking_analysis, "_to_dbfs", lambda levels: levels)
    return masking_analysis.analyze_stem_masking(
        [(f"s{index}", silence) for index in range(len(arrays))]
    )


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
    assert result["activity"]["schema"] == "kenn.stem_masking.activity.v1"
    assert result["activity"]["active_floor_dbfs"] == masking_analysis.ACTIVE_FLOOR_DBFS


def test_well_separated_frequency_stems_are_not_flagged() -> None:
    n = int(5.0 * 44100)
    low = _wav_bytes(_sine(n, 100.0, 44100))
    high = _wav_bytes(_sine(n, 10000.0, 44100))
    result = masking_analysis.analyze_stem_masking([("low", low), ("high", high)])
    assert result["ok"] is True
    assert result["findings"] == []
    assert any(
        fact["name"] == "masking_candidate_count" and fact["value"] == 0
        for fact in result["evidence"]["facts"]
    )


def test_one_stem_playing_alone_is_not_flagged_against_silence() -> None:
    n = int(5.0 * 44100)
    a = _wav_bytes(_sine(n, 440.0, 44100))
    silence = _wav_bytes([0.0] * n)
    result = masking_analysis.analyze_stem_masking([("a", a), ("silence", silence)])
    assert result["ok"] is True
    assert result["findings"] == []


def test_quiet_stems_withhold_signal_facts_but_keep_activity_provenance(monkeypatch) -> None:
    quiet = [[[-90.0] * len(masking_analysis.MASKING_BANDS) for _ in range(3)]] * 2
    result = _controlled_activity(monkeypatch, quiet)
    assert result["activity"]["frame_count"] == 3
    assert [source["active_frame_count"] for source in result["activity"]["sources"]] == [0, 0]
    assert result["activity"]["pairs"][0]["simultaneously_active_frame_count"] == 0
    names = {fact["name"] for fact in result["evidence"]["facts"]}
    assert "stem_count" in names and "sample_rate" in names
    assert "masking_candidate_count" not in names
    assert not any(name.startswith("masking_highest_") for name in names)
    assert any("withheld" in item for item in result["limitations"])


def test_one_active_stem_does_not_qualify_a_pair(monkeypatch) -> None:
    quiet = [-90.0] * len(masking_analysis.MASKING_BANDS)
    active = [-20.0, *([-90.0] * (len(masking_analysis.MASKING_BANDS) - 1))]
    result = _controlled_activity(monkeypatch, [[active, active, active], [quiet, quiet, quiet]])
    assert [source["active_frame_count"] for source in result["activity"]["sources"]] == [3, 0]
    assert result["activity"]["pairs"][0]["simultaneously_active_frame_count"] == 0
    assert not any(fact["name"] == "masking_candidate_count" for fact in result["evidence"]["facts"])


def test_exact_activity_floor_is_inactive(monkeypatch) -> None:
    boundary = [-50.0] * len(masking_analysis.MASKING_BANDS)
    result = _controlled_activity(monkeypatch, [[boundary] * 2, [boundary] * 2])
    assert result["activity"]["pairs"][0]["simultaneously_active_frame_count"] == 0
    assert not any(fact["name"] == "masking_candidate_count" for fact in result["evidence"]["facts"])


def test_signal_facts_return_after_quiet_capture(monkeypatch) -> None:
    quiet = [-90.0] * len(masking_analysis.MASKING_BANDS)
    active = [-20.0, *([-90.0] * (len(masking_analysis.MASKING_BANDS) - 1))]
    quiet_result = _controlled_activity(monkeypatch, [[quiet] * 2, [quiet] * 2])
    assert not any(fact["name"] == "masking_candidate_count" for fact in quiet_result["evidence"]["facts"])

    active_result = _controlled_activity(monkeypatch, [[active] * 2, [active] * 2])
    assert any(
        fact["name"] == "masking_candidate_count" and fact["value"] > 0
        for fact in active_result["evidence"]["facts"]
    )


def test_three_stems_count_only_the_pair_with_shared_active_frames(monkeypatch) -> None:
    quiet = [-90.0] * len(masking_analysis.MASKING_BANDS)
    a = [-20.0, *([-90.0] * (len(masking_analysis.MASKING_BANDS) - 1))]
    b = [-40.0, *([-90.0] * (len(masking_analysis.MASKING_BANDS) - 1))]
    c = [-20.0, *([-90.0] * (len(masking_analysis.MASKING_BANDS) - 1))]
    result = _controlled_activity(
        monkeypatch,
        [[a, quiet], [b, quiet], [quiet, c]],
    )
    assert result["activity"]["pairs"] == [
        {"stems": ["s0", "s1"], "simultaneously_active_frame_count": 1},
        {"stems": ["s0", "s2"], "simultaneously_active_frame_count": 0},
        {"stems": ["s1", "s2"], "simultaneously_active_frame_count": 0},
    ]
    assert any(
        fact["name"] == "masking_candidate_count" and fact["value"] == 0
        for fact in result["evidence"]["facts"]
    )


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



@pytest.mark.parametrize(
    ("backend", "setting", "expect_native"),
    [
        ("cpp-accelerate", None, True),
        ("cpp-scalar", None, True),
        ("", None, False),
        ("cpp-accelerate", "0", False),
        ("cpp-scalar", "0", False),
        ("cpp-scalar", "1", True),
    ],
)
def test_masking_takes_native_by_default_on_accelerate_and_scalar_builds(
    monkeypatch, backend, setting, expect_native
) -> None:
    # Both Accelerate and portable scalar (RealFFTPlan) builds beat NumPy and
    # match to machine precision, while an older module without a valid backend
    # label still falls back unless explicitly forced with =1.
    native_fft = pytest.importorskip("kenn.core.native_fft")

    class FakeModule:
        @staticmethod
        def masking_band_energy(values, sample_rate, fft_size, hop):
            return {"energy": [[0.0]], "backend": backend}

    monkeypatch.setattr(native_fft, "_load", lambda: FakeModule)
    monkeypatch.setattr(native_fft, "_masking_backend_label", None)
    if setting is None:
        monkeypatch.delenv("KENN_DSP_MASKING_NATIVE", raising=False)
    else:
        monkeypatch.setenv("KENN_DSP_MASKING_NATIVE", setting)

    result = native_fft.masking_band_energy([0.0] * 4096, 44100)

    assert (result is not None) == expect_native


def test_masking_band_energy_matches_numpy_reference(monkeypatch) -> None:
    native_fft = pytest.importorskip("kenn.core.native_fft")
    if not native_fft.available():
        pytest.skip("native DSP module not built")

    n = int(2.0 * 48000)
    signal = masking_analysis._np.asarray(_sine(n, 440.0, 48000, amplitude=0.4), dtype=float)
    monkeypatch.setenv("KENN_DSP_MASKING_NATIVE", "1")
    native_energy, native_backend = masking_analysis._band_energy_over_time_with_backend(signal, 48000)
    monkeypatch.setenv("KENN_DSP_MASKING_NATIVE", "0")
    ref_energy, ref_backend = masking_analysis._band_energy_over_time_with_backend(signal, 48000)

    assert native_backend in {"cpp-accelerate", "cpp-scalar"}
    assert ref_backend == "python-numpy-reference"
    assert native_energy.shape == ref_energy.shape
    assert float(masking_analysis._np.max(masking_analysis._np.abs(native_energy - ref_energy))) < 1e-6
