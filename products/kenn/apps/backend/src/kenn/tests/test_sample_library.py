from __future__ import annotations

import math
import struct
import wave

import numpy as np
import pytest

from kenn.core import native_fft, sample_library
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
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
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
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    path = _tone_wav(tmp_path, freq=440.0)  # concert A4
    result, reason = analyze_sample_audio(path)
    assert reason is None
    assert result["estimated_key_pitch_class"] == "A"


def test_a_held_tone_gets_a_key_but_no_invented_bpm(tmp_path) -> None:
    # Adversary review, 17 Oct 2026: an 8 s sine read 112 BPM at strength 0.955.
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    path = _tone_wav(tmp_path, freq=220.0, seconds=8.0, framerate=44100)
    result, reason = analyze_sample_audio(path)
    assert reason is None
    assert result["estimated_key_pitch_class"] == "A"
    assert "estimated_bpm" not in result


def test_a_held_low_saw_gets_a_key_but_no_invented_bpm(tmp_path) -> None:
    # Adversary review, 17 Oct 2026: an 8 s 40 Hz band-limited saw at 44.1 kHz
    # swung >4 dB on alternate frames and read 120 BPM at strength 0.94.
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    rate = 44100
    freq = 40.0
    t = np.arange(8 * rate, dtype=np.float64) / rate
    saw = np.zeros_like(t)
    harmonic = 1
    while harmonic * freq < rate / 2.0:
        saw += ((-1.0) ** (harmonic + 1)) * np.sin(2.0 * np.pi * harmonic * freq * t) / harmonic
        harmonic += 1
    saw *= 0.8 / np.max(np.abs(saw))
    path = tmp_path / "saw_40hz.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((saw * 32767.0).astype("<i2").tobytes())
    result, reason = analyze_sample_audio(path)
    assert reason is None
    assert result["estimated_key_pitch_class"] in sample_library._KEY_NAMES
    assert "estimated_bpm" not in result


def test_two_kicks_are_not_a_tempo() -> None:
    # Re-review, 17 Oct 2026: two kicks read 148 BPM whatever their spacing,
    # because each kick's attack and its cut-off 0.4 s later made one onset pair.
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    rate = 44100
    tt = np.arange(int(0.4 * rate)) / rate
    kick = np.sin(2 * np.pi * np.cumsum(50 + 100 * np.exp(-tt * 30)) / rate) * np.exp(-tt * 9)
    for gap_seconds in (0.5, 3.0):
        audio = np.zeros(int((gap_seconds + 3.0) * rate), dtype=np.float32)
        for start in (0, int(gap_seconds * rate)):
            audio[start : start + kick.size] += kick
        assert native_fft.key_tempo_features(audio, rate)["tempo_bpm"] is None


def test_click_track_tempo_scales_across_sample_rates() -> None:
    # Hop and window sizes scale with sample rate so a 120 BPM click track
    # reports the same tempo at 44.1, 48 and 96 kHz.
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    for rate in (44100, 48000, 96000):
        audio = np.zeros(rate * 8, dtype=np.float32)
        audio[:: rate // 2] = 1.0  # a click every 0.5 s, 120 BPM
        assert native_fft.key_tempo_features(audio, rate)["tempo_bpm"] == pytest.approx(120.0, rel=0.01)


def test_a_wav_declaring_a_2_hz_rate_abstains_instead_of_hanging(tmp_path) -> None:
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    path = tmp_path / "two_hertz.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(2)
        handle.writeframes(np.full(4000, 1000, dtype="<i2").tobytes())
    result, reason = analyze_sample_audio(path)
    assert result is None
    assert "2 Hz sample rate" in reason
    with pytest.raises(ValueError):
        native_fft.key_tempo_features(np.ones(4000, dtype=np.float32), 2)


def test_a_wav_declaring_a_60_mhz_rate_abstains_instead_of_allocating_gigabytes(tmp_path) -> None:
    # Adversary review, 17 Oct 2026: a 60 MHz header allocated ~5 GB of FFT buffers.
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    path = tmp_path / "sixty_mhz.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(60_000_000)
        handle.writeframes(np.full(4000, 1000, dtype="<i2").tobytes())
    result, reason = analyze_sample_audio(path)
    assert result is None
    assert "60000000 Hz sample rate" in reason
    with pytest.raises(ValueError):
        native_fft.key_tempo_features(np.ones(4000, dtype=np.float32), 768_001)


def test_a_nan_sample_abstains_rather_than_reporting_c(tmp_path, monkeypatch) -> None:
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    mono = np.sin(2 * np.pi * 261.63 * np.arange(44100 * 4) / 44100).astype(np.float32)
    mono[100000] = np.nan
    monkeypatch.setattr(sample_library, "_decode_mono", lambda _path: (mono, 44100))
    result, reason = analyze_sample_audio(_tone_wav(tmp_path))
    assert result is None
    assert "NaN" in reason


def test_a_stale_extension_without_key_tempo_abstains(tmp_path, monkeypatch) -> None:
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    real_module = native_fft._load()

    class _StaleModule:
        decode_pcm = staticmethod(real_module.decode_pcm)

    monkeypatch.setattr(native_fft, "_load", lambda: _StaleModule)
    assert native_fft.key_tempo_features(np.ones(44100, dtype=np.float32), 44100) is None
    result, reason = analyze_sample_audio(_tone_wav(tmp_path))
    assert result is None
    assert "out of date" in reason


def test_analyze_sample_audio_abstains_honestly_when_the_native_extension_is_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("KENN_DSP_NATIVE", "0")
    path = _tone_wav(tmp_path)
    result, reason = analyze_sample_audio(path)
    assert result is None
    assert "not built or is disabled" in reason


def test_an_aiff_sample_decodes_natively_and_abstains_when_malformed(tmp_path) -> None:
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    broken_path = tmp_path / "broken.aif"
    broken_path.write_bytes(b"FORM" + b"\x00" * 40)
    result, reason = analyze_sample_audio(broken_path)
    assert result is None
    assert "AIFF could not be decoded" in reason

    # Build a valid 16-bit big-endian 44.1 kHz mono AIFF containing a 2.0 s 440 Hz A4 sine
    rate = 44100
    frames = rate * 2
    t = np.arange(frames, dtype=np.float64) / rate
    pcm_be = (0.8 * np.sin(2.0 * np.pi * 440.0 * t) * 32767.0).astype(">i2").tobytes()
    # 44100.0 in 80-bit IEEE 754 extended precision is 0x400E AC44000000000000
    comm_data = struct.pack(">hIhHQ", 1, frames, 16, 0x400E, 0xAC44000000000000)
    ssnd_data = struct.pack(">II", 0, 0) + pcm_be
    form_body = b"AIFF" + b"COMM" + struct.pack(">I", len(comm_data)) + comm_data + b"SSND" + struct.pack(">I", len(ssnd_data)) + ssnd_data
    valid_aiff = tmp_path / "tone_440.aif"
    valid_aiff.write_bytes(b"FORM" + struct.pack(">I", len(form_body)) + form_body)

    aiff_res, aiff_reason = analyze_sample_audio(valid_aiff)
    assert aiff_reason is None
    assert aiff_res is not None
    assert aiff_res["estimated_key_pitch_class"] == "A"


def test_a_stereo_sample_is_folded_to_mono_and_capped_at_the_analysis_window(tmp_path) -> None:
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    rate = 8000
    t = np.arange(int(70 * rate)) / rate
    tone = (0.5 * np.sin(2 * np.pi * 220.0 * t) * 32767).astype("<i2")
    path = tmp_path / "long_stereo.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(np.column_stack([tone, tone]).tobytes())
    result, reason = analyze_sample_audio(path)
    assert reason is None
    assert result["analysis_seconds"] == sample_library.MAX_ANALYSIS_SECONDS
    assert result["estimated_key_pitch_class"] == "A"


def test_the_tonic_beats_a_louder_fifth_in_a_minor_triad() -> None:
    # Added 17 Oct 2026 when the chroma peak gave way to the key profile: a
    # loop whose E is loudest is still in A, and the old argmax said E.
    chroma = [0.0] * 12
    chroma[9], chroma[0], chroma[4] = 0.8, 0.6, 1.0  # A, C, E
    assert sample_library._KEY_NAMES[sample_library._profile_tonic(chroma)] == "A"
    assert sample_library._profile_tonic([0.25] * 12) is None


def test_an_unreadable_wav_abstains_with_the_supported_formats(tmp_path) -> None:
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
    path = tmp_path / "broken.wav"
    path.write_bytes(b"RIFF" + b"\x00" * 40)
    result, reason = analyze_sample_audio(path)
    assert result is None
    assert "could not be decoded" in reason


def test_analyze_sample_audio_abstains_on_missing_file(tmp_path) -> None:
    result, reason = analyze_sample_audio(tmp_path / "does-not-exist.wav")
    assert result is None
    assert "not found" in reason


def test_analyze_sample_audio_abstains_on_too_short_audio(tmp_path) -> None:
    if not native_fft.available():
        pytest.skip("the native DSP extension is not built in this environment")
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
