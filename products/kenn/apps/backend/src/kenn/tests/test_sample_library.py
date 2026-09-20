from __future__ import annotations

import math
import struct
import wave

from kenn.core import sample_library
from kenn.core.sample_library import (
    analyze_sample_audio,
    resolve_sample,
    scan_sample_library,
    search_samples,
)


def _make_fixture(tmp_path):
    (tmp_path / "Drum Breaks").mkdir()
    (tmp_path / "Drum Breaks" / "Funky Kick One Shot.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    (tmp_path / "Drum Breaks" / "Vintage Break Loop.WAV").write_bytes(b"RIFF" + b"\x00" * 40)
    (tmp_path / "Vocal Pack").mkdir()
    (tmp_path / "Vocal Pack" / "Adlib Take 3.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    (tmp_path / "Vocal Pack" / ".DS_Store").write_bytes(b"junk")
    (tmp_path / "Vocal Pack" / "notes.txt").write_text("not a sample")
    (tmp_path / "Vocal Pack" / "preset.fxp").write_bytes(b"not audio either")
    return tmp_path


def test_scan_only_indexes_audio_files_and_ignores_metadata(tmp_path) -> None:
    root = _make_fixture(tmp_path)
    entries = scan_sample_library(root)
    filenames = {entry.filename for entry in entries}
    assert filenames == {"Funky Kick One Shot.wav", "Vintage Break Loop.WAV", "Adlib Take 3.wav"}


def test_scan_extracts_tags_from_filename_and_pack(tmp_path) -> None:
    root = _make_fixture(tmp_path)
    entries = scan_sample_library(root)
    by_name = {entry.filename: entry for entry in entries}
    assert "kick" in by_name["Funky Kick One Shot.wav"].tags
    assert "one_shot" in by_name["Funky Kick One Shot.wav"].tags
    assert "drum_loop" in by_name["Vintage Break Loop.WAV"].tags
    assert by_name["Vintage Break Loop.WAV"].pack == "Drum Breaks"
    assert "vocal" in by_name["Adlib Take 3.wav"].tags  # from the pack name


def test_scan_respects_max_files_bound(tmp_path) -> None:
    root = _make_fixture(tmp_path)
    entries = scan_sample_library(root, max_files=1)
    assert len(entries) == 1


def test_scan_missing_root_returns_empty(tmp_path) -> None:
    assert scan_sample_library(tmp_path / "does-not-exist") == []


def test_search_ranks_tag_matches_above_unrelated_files(tmp_path) -> None:
    root = _make_fixture(tmp_path)
    entries = scan_sample_library(root)
    results = search_samples(entries, "kick")
    assert results
    assert results[0].filename == "Funky Kick One Shot.wav"


def test_search_no_match_returns_empty() -> None:
    assert search_samples([], "kick") == []


def test_search_respects_limit(tmp_path) -> None:
    root = _make_fixture(tmp_path)
    entries = scan_sample_library(root)
    results = search_samples(entries, "wav", limit=1)
    assert len(results) <= 1


def test_payload_never_exposes_a_raw_filesystem_path(tmp_path) -> None:
    root = _make_fixture(tmp_path)
    entries = scan_sample_library(root)
    for entry in entries:
        payload = entry.payload()
        assert "path" not in payload
        assert str(root) not in str(payload)


def test_resolve_sample_finds_exact_entry_by_opaque_id(tmp_path) -> None:
    root = _make_fixture(tmp_path)
    entries = scan_sample_library(root)
    target = entries[0]
    resolved = resolve_sample(entries, target.id)
    assert resolved is target


def _click_track_wav(tmp_path, *, bpm: float = 120.0, seconds: float = 8.0, framerate: int = 22050):
    interval = 60.0 / bpm
    n = int(seconds * framerate)
    samples = [0.0] * n
    t = 0.0
    click_len = int(0.01 * framerate)
    while t < seconds:
        idx = int(t * framerate)
        for offset in range(click_len):
            if idx + offset < n:
                samples[idx + offset] = 1.0
        t += interval
    path = tmp_path / "click_120bpm.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(framerate)
        scale = (1 << 15) - 1
        handle.writeframes(b"".join(struct.pack("<h", int(v * scale)) for v in samples))
    return path


def _tone_wav(tmp_path, *, freq: float = 440.0, seconds: float = 3.0, framerate: int = 22050):
    n = int(seconds * framerate)
    path = tmp_path / "tone_a4.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(framerate)
        scale = (1 << 15) - 1
        frames = bytearray()
        for i in range(n):
            v = 0.8 * math.sin(2 * math.pi * freq * i / framerate)
            frames += struct.pack("<h", int(v * scale))
        handle.writeframes(bytes(frames))
    return path


def test_analyze_sample_audio_estimates_known_bpm_within_tolerance(tmp_path) -> None:
    if sample_library._librosa is None:
        import pytest
        pytest.skip("librosa is not installed in this environment")
    path = _click_track_wav(tmp_path, bpm=120.0)
    result, reason = analyze_sample_audio(path)
    assert reason is None
    assert result is not None
    # Beat trackers can lock onto a half/double-time multiple of the true
    # tempo; accept any of 0.5x/1x/2x within a modest tolerance instead of
    # over-fitting the test to one exact estimator behaviour.
    ratio = result["estimated_bpm"] / 120.0
    assert any(abs(ratio - m) < 0.08 for m in (0.5, 1.0, 2.0))


def test_analyze_sample_audio_estimates_known_pitch_class(tmp_path) -> None:
    if sample_library._librosa is None:
        import pytest
        pytest.skip("librosa is not installed in this environment")
    path = _tone_wav(tmp_path, freq=440.0)  # concert A4
    result, reason = analyze_sample_audio(path)
    assert reason is None
    assert result["estimated_key_pitch_class"] == "A"


def test_analyze_sample_audio_abstains_honestly_when_dependency_is_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sample_library, "_librosa", None)
    path = _tone_wav(tmp_path)
    result, reason = analyze_sample_audio(path)
    assert result is None
    assert "not installed" in reason


def test_analyze_sample_audio_abstains_on_missing_file(tmp_path) -> None:
    result, reason = analyze_sample_audio(tmp_path / "does-not-exist.wav")
    assert result is None
    assert "not found" in reason


def test_analyze_sample_audio_abstains_on_too_short_audio(tmp_path) -> None:
    if sample_library._librosa is None:
        import pytest
        pytest.skip("librosa is not installed in this environment")
    path = _tone_wav(tmp_path, seconds=0.1)
    result, reason = analyze_sample_audio(path)
    assert result is None
    assert "shorter than" in reason


def test_analyze_sample_audio_never_called_from_bulk_scan_or_search(tmp_path, monkeypatch) -> None:
    # A regression guard for the module's core design law: the bulk scan and
    # keyword search must stay filename-only and never decode audio.
    calls = []
    monkeypatch.setattr(sample_library, "analyze_sample_audio", lambda p: calls.append(p))
    root = _make_fixture(tmp_path)
    entries = scan_sample_library(root)
    search_samples(entries, "kick")
    assert calls == []


def test_resolve_sample_returns_none_for_unknown_id(tmp_path) -> None:
    root = _make_fixture(tmp_path)
    entries = scan_sample_library(root)
    assert resolve_sample(entries, "not-a-real-id") is None
