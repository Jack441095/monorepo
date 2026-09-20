"""Tests for automix stem classification and preparation."""

from __future__ import annotations

import math

import numpy as np
import pytest

from audio_analysis.mixdown.stem_classifier import (
    StemProfile,
    classify_from_filename,
    classify_from_spectral,
    classify_stems,
    verify_stem_spectral_targets,
)
from audio_analysis.mixdown.stem_prep import (
    prepare_stems,
    remove_dc_offset,
    resample,
    trim_silence,
    trim_stems_preserving_alignment,
    write_wav,
)
from audio_analysis.utils.audio_io import read_wav_mono


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("01_KICK-IN.wav", "kick"),
        ("Lead Vox.final.wav", "vocal"),
        ("backing-vocals_03.wav", "backing_vocal"),
        ("808 SUB BASS.wav", "sub_bass"),
        ("acoustic_gtr-L.wav", "guitar"),
        ("DRUM BUS print.wav", "full_drum_bus"),
        ("unlabelled_take.wav", "other"),
        # Regression, found 2026-07-10 running real stems through classify_
        # stems() for the first time: several `\bword\b`-style patterns had
        # no trailing plural, so a plural filename (very common in real DAW
        # exports -- "VOCALS.wav", "STRINGS.wav", "SHAKERS.wav") failed the
        # word-boundary check right after the singular form (next char is
        # 's', a word character, so \b doesn't match there) and silently
        # fell through to content-based classification, which mis-guessed
        # "hihat" for VOCALS and "fx" for STRINGS/SHAKERS on real audio.
        ("_ VOCALS.wav", "vocal"),
        ("_ VOCALS-1.wav", "vocal"),
        ("_ STRINGS.wav", "strings"),
        ("_ SHAKERS.wav", "percussion"),
        ("_ HATS.wav", "hihat"),
        ("_ HATS-1.wav", "hihat"),
        # Regression: BRASS had zero filename coverage at all (no dedicated
        # "brass" category existed in INSTRUMENT_TYPES) and fell through to
        # "fx" on real audio. Fixed 2026-07-13 with a dedicated "brass"
        # category (was a "strings" stopgap mapping before that).
        ("_ BRASS.wav", "brass"),
        ("_ TRUMPET.wav", "brass"),
        ("_ SAX.wav", "brass"),
    ],
)
def test_filename_classification_edge_cases(filename: str, expected: str) -> None:
    instrument, confidence = classify_from_filename(filename)

    assert instrument == expected
    assert confidence > 0.0 if expected != "other" else confidence == 0.0


@pytest.mark.parametrize(
    ("features", "expected"),
    [
        ((90.0, 55.0, 5.0, 18.0), "kick"),
        ((80.0, 45.0, 1.0, 6.0), "sub_bass"),
        ((9000.0, None, 18.0, 15.0), "hihat"),
    ],
)
def test_spectral_classification_known_profiles(features: tuple, expected: str) -> None:
    instrument, confidence = classify_from_spectral(*features)

    assert instrument == expected
    assert confidence >= 0.7


def test_real_wav_batch_classification() -> None:
    sample_rate = 8_000
    t = np.arange(sample_rate, dtype=np.float64) / sample_rate
    kick = 0.7 * np.sin(2.0 * np.pi * 55.0 * t) * np.exp(-5.0 * t)
    vocal = 0.35 * np.sin(2.0 * np.pi * 220.0 * t)
    stems = [
        {
            "name": "kick close.wav",
            "file_bytes": write_wav(kick.tolist(), kick.tolist(), sample_rate, bit_depth=16),
        },
        {
            "name": "lead_vocal.wav",
            "file_bytes": write_wav(vocal.tolist(), vocal.tolist(), sample_rate, bit_depth=16),
        },
    ]

    profiles = classify_stems(stems, read_wav_mono_fn=read_wav_mono)

    assert [profile.instrument for profile in profiles] == ["kick", "vocal"]
    assert all(profile.duration_seconds == pytest.approx(1.0) for profile in profiles)


def test_remove_dc_offset() -> None:
    signal = (np.sin(np.linspace(0.0, 4.0 * np.pi, 2_000)) + 0.25).tolist()

    corrected = remove_dc_offset(signal)

    assert np.mean(corrected) == pytest.approx(0.0, abs=1e-12)


def test_resampling_preserves_duration_and_frequency() -> None:
    source_rate = 8_000
    target_rate = 16_000
    frequency = 440.0
    t = np.arange(source_rate, dtype=np.float64) / source_rate
    source = np.sin(2.0 * np.pi * frequency * t).tolist()

    converted = np.asarray(resample(source, source_rate, target_rate))
    peak_bin = int(np.argmax(np.abs(np.fft.rfft(converted))))
    peak_hz = peak_bin * target_rate / len(converted)

    assert len(converted) == target_rate
    assert peak_hz == pytest.approx(frequency, abs=1.0)


def test_trim_silence_keeps_requested_buffer() -> None:
    sample_rate = 1_000
    signal = [0.0] * 100 + [0.5] * 200 + [0.0] * 100

    trimmed = trim_silence(signal, sample_rate, threshold_db=-40.0, keep_ms=10.0)

    assert len(trimmed) == 220
    assert trimmed[:10] == [0.0] * 10
    assert trimmed[-10:] == [0.0] * 10


def test_shared_trim_preserves_relative_stem_entrances() -> None:
    sample_rate = 1_000
    early = [0.0] * 100 + [0.5] * 10 + [0.0] * 390
    late = [0.0] * 250 + [0.5] * 10 + [0.0] * 240

    trimmed, start, end = trim_stems_preserving_alignment(
        [early, late], sample_rate, threshold_db=-40.0, keep_ms=10.0
    )

    # trim_stems_preserving_alignment now returns numpy arrays (memory/perf
    # refactor); find the entrance index array-safely instead of list.index().
    def _entrance(stem):
        return int(np.where(np.asarray(stem) == 0.5)[0][0])

    assert (start, end) == (90, 270)
    assert _entrance(trimmed[0]) == 10
    assert _entrance(trimmed[1]) == 160
    assert _entrance(trimmed[1]) - _entrance(trimmed[0]) == 150


def test_shared_trim_preserves_all_silent_session_length() -> None:
    silence = [[0.0] * 500, [0.0] * 300]

    trimmed, start, end = trim_stems_preserving_alignment(silence, 1_000)

    assert (start, end) == (0, 500)
    assert {len(stem) for stem in trimmed} == {500}


def test_prepare_stems_keeps_offset_after_resampling_and_trim() -> None:
    source_rate = 8_000
    target_rate = 16_000
    early = np.zeros(source_rate, dtype=np.float64)
    late = np.zeros(source_rate, dtype=np.float64)
    early[800:880] = 0.5
    late[2_400:2_480] = 0.5
    stems = [
        {"name": "early.wav", "file_bytes": write_wav(early.tolist(), early.tolist(), source_rate, 16)},
        {"name": "late.wav", "file_bytes": write_wav(late.tolist(), late.tolist(), source_rate, 16)},
    ]

    prepared = prepare_stems(
        stems,
        read_wav_mono_fn=read_wav_mono,
        target_sample_rate=target_rate,
        trim=True,
        normalise=False,
    )

    threshold = 0.1
    entrances = [
        next(index for index, sample in enumerate(stem["samples"]) if abs(sample) > threshold)
        for stem in prepared
    ]
    assert entrances[1] - entrances[0] == pytest.approx(3_200, abs=2)
    assert len({len(stem["samples"]) for stem in prepared}) == 1
    trim_starts = {stem["session_trim_start_samples"] for stem in prepared}
    assert len(trim_starts) == 1
    assert next(iter(trim_starts)) > 0


def test_prepare_stems_resamples_normalises_and_aligns_real_wavs() -> None:
    first_rate = 8_000
    second_rate = 16_000
    first = (0.2 * np.sin(2.0 * np.pi * 220.0 * np.arange(4_000) / first_rate)).tolist()
    second = (0.4 * np.sin(2.0 * np.pi * 330.0 * np.arange(12_000) / second_rate)).tolist()
    stems = [
        {"name": "keys.wav", "file_bytes": write_wav(first, first, first_rate, bit_depth=16)},
        {"name": "guitar.wav", "file_bytes": write_wav(second, second, second_rate, bit_depth=16)},
    ]

    prepared = prepare_stems(
        stems,
        read_wav_mono_fn=read_wav_mono,
        target_sample_rate=16_000,
        trim=False,
        normalise=True,
        target_peak_dbfs=-6.0,
    )

    expected_peak = math.pow(10.0, -6.0 / 20.0)
    assert {stem["sample_rate"] for stem in prepared} == {16_000}
    assert {len(stem["samples"]) for stem in prepared} == {12_000}
    assert max(abs(value) for value in prepared[0]["samples"]) == pytest.approx(expected_peak)
    assert max(abs(value) for value in prepared[1]["samples"]) == pytest.approx(expected_peak)


def test_prepare_stems_preserves_rough_level_relationships_by_default() -> None:
    sample_rate = 8_000
    phase = 2.0 * np.pi * 220.0 * np.arange(sample_rate) / sample_rate
    quiet = 0.1 * np.sin(phase)
    loud = 0.4 * np.sin(phase)
    stems = [
        {"name": "quiet.wav", "file_bytes": write_wav(quiet.tolist(), quiet.tolist(), sample_rate, 16)},
        {"name": "loud.wav", "file_bytes": write_wav(loud.tolist(), loud.tolist(), sample_rate, 16)},
    ]

    prepared = prepare_stems(
        stems,
        read_wav_mono_fn=read_wav_mono,
        target_sample_rate=sample_rate,
        trim=False,
    )

    peaks = [max(abs(value) for value in stem["samples"]) for stem in prepared]
    assert peaks[1] / peaks[0] == pytest.approx(4.0, rel=0.01)


def test_prepare_stems_default_reads_full_audio_beyond_decoder_preview_limit() -> None:
    sample_rate = 8_000
    sample_count = 150_000
    tone = 0.2 * np.sin(2.0 * np.pi * 220.0 * np.arange(sample_count) / sample_rate)

    preview = read_wav_mono(
        write_wav(tone.tolist(), tone.tolist(), sample_rate, 16)
    )
    prepared = prepare_stems(
        [{"name": "long.wav", "file_bytes": write_wav(
            tone.tolist(), tone.tolist(), sample_rate, 16
        )}],
        read_wav_mono_fn=read_wav_mono,
        target_sample_rate=sample_rate,
        trim=False,
    )[0]

    assert len(preview["samples"]) < sample_count
    assert len(prepared["samples"]) == sample_count
    assert prepared["original_duration_seconds"] == pytest.approx(sample_count / sample_rate)


def test_prepare_stems_preserves_distinct_stereo_channels_and_mid_proxy() -> None:
    sample_rate = 8_000
    time = np.arange(sample_rate) / sample_rate
    left = 0.35 * np.sin(2.0 * np.pi * 220.0 * time)
    right = 0.2 * np.sin(2.0 * np.pi * 440.0 * time)

    prepared = prepare_stems(
        [{"name": "keys.wav", "file_bytes": write_wav(
            left.tolist(), right.tolist(), sample_rate, 16
        )}],
        read_wav_mono_fn=read_wav_mono,
        target_sample_rate=sample_rate,
        trim=False,
    )[0]

    prepared_left = np.asarray(prepared["left_samples"])
    prepared_right = np.asarray(prepared["right_samples"])
    assert prepared["stereo_preserved"] is True
    assert prepared["channel_layout"] == "stereo"
    assert prepared["source_channels"] == 2
    assert not np.allclose(prepared_left, prepared_right)
    assert np.allclose(
        prepared["samples"], 0.5 * (prepared_left + prepared_right), atol=1e-12
    )


def test_prepare_stems_does_not_trim_antiphase_stereo_as_silence() -> None:
    sample_rate = 8_000
    tone = 0.4 * np.sin(2.0 * np.pi * 220.0 * np.arange(800) / sample_rate)
    left = np.concatenate([np.zeros(400), tone, np.zeros(400)])
    right = -left

    prepared = prepare_stems(
        [{"name": "wide.wav", "file_bytes": write_wav(
            left.tolist(), right.tolist(), sample_rate, 16
        )}],
        read_wav_mono_fn=read_wav_mono,
        target_sample_rate=sample_rate,
        trim=True,
    )[0]

    assert prepared["stereo_preserved"] is True
    assert 800 <= len(prepared["left_samples"]) < len(left)
    assert max(abs(value) for value in prepared["left_samples"]) > 0.3
    assert np.allclose(prepared["right_samples"], -np.asarray(prepared["left_samples"]), atol=1e-4)


# ---------------------------------------------------------------------------
# Post-processing spectral target verification (2026-07-10)
# ---------------------------------------------------------------------------
#
# Real-world finding this covers: a real kick's processed spectral centroid
# landed at 888Hz (plain) / 1252Hz (equal-loudness-weighted), both well
# outside kick's expected 40-250Hz centroid range -- not because the kick
# lacked real low-end, but because its transient click dominates a
# single-number centroid average regardless of loudness weighting. The
# low-frequency-share floor check exists specifically to catch this case
# correctly (real bass content present) rather than false-flagging it.

_SR = 44100


def _kick_like_signal(duration_s: float = 1.0, *, sample_rate: int = _SR) -> np.ndarray:
    """A low 60Hz body plus a short, loud broadband click at the very start --
    the exact combination that makes a plain/perceptual centroid misleading
    but leaves real, measurable sub+bass energy in the signal."""
    n = int(sample_rate * duration_s)
    t = np.arange(n) / sample_rate
    body_env = np.exp(-t * 8.0)
    body = 0.6 * np.sin(2 * np.pi * 60.0 * t) * body_env
    click_len = int(0.003 * sample_rate)
    click = np.zeros(n)
    click[:click_len] = np.random.default_rng(1).normal(0, 1, click_len) * np.exp(
        -np.arange(click_len) / (click_len / 8)
    )
    return np.clip(body + click * 0.9, -1.0, 1.0)


def _thin_bright_signal(duration_s: float = 1.0, *, sample_rate: int = _SR) -> np.ndarray:
    """No meaningful low end at all -- a genuine "low_freq_check should fail"
    case, for contrast against the kick-like signal above."""
    n = int(sample_rate * duration_s)
    t = np.arange(n) / sample_rate
    return 0.5 * np.sin(2 * np.pi * 3000.0 * t)


def test_low_freq_share_check_passes_for_a_real_kick_despite_misleading_centroid() -> None:
    kick_signal = _kick_like_signal()
    stem_audio = {"kick.wav": (kick_signal, kick_signal)}
    profiles = [StemProfile(name="kick.wav", instrument="kick", classification_confidence=0.95)]

    results = verify_stem_spectral_targets(stem_audio, profiles, _SR)
    assert len(results) == 1
    r = results[0]

    assert r["low_freq_share"] is not None
    assert r["low_freq_check_passed"] is True, (
        f"a kick with real 60Hz body content should pass the low-frequency "
        f"floor check (share={r['low_freq_share']}, min={r['low_freq_share_min']})"
    )


def test_low_freq_share_check_fails_for_a_genuinely_thin_signal() -> None:
    thin_signal = _thin_bright_signal()
    stem_audio = {"kick.wav": (thin_signal, thin_signal)}
    profiles = [StemProfile(name="kick.wav", instrument="kick", classification_confidence=0.95)]

    results = verify_stem_spectral_targets(stem_audio, profiles, _SR)
    r = results[0]

    assert r["low_freq_check_passed"] is False, (
        "a 3kHz-only signal has no real low end and must fail the kick floor check"
    )


def test_low_freq_share_not_computed_for_instruments_outside_the_table() -> None:
    """vocal/guitar/etc. have no entry in _LOW_FREQ_SHARE_MIN -- the check
    should be skipped (None), not silently applied with some default."""
    signal = _thin_bright_signal()
    stem_audio = {"vocal.wav": (signal, signal)}
    profiles = [StemProfile(name="vocal.wav", instrument="vocal", classification_confidence=0.9)]

    results = verify_stem_spectral_targets(stem_audio, profiles, _SR)
    r = results[0]

    assert r["low_freq_share"] is None
    assert r["low_freq_share_min"] is None
    assert r["low_freq_check_passed"] is None


def test_verify_stem_spectral_targets_matches_stem_audio_to_profiles_by_name() -> None:
    """A stem in stem_audio with no matching profile must be skipped, not
    crash or produce a garbage entry."""
    signal = _kick_like_signal()
    stem_audio = {"unmatched.wav": (signal, signal)}
    profiles = [StemProfile(name="different_name.wav", instrument="kick", classification_confidence=0.9)]

    results = verify_stem_spectral_targets(stem_audio, profiles, _SR)
    assert results == []


def test_equal_loudness_weighted_centroid_differs_from_plain_centroid() -> None:
    """Confirms the perceptual weighting is actually doing something (not a
    no-op) -- a signal with both a low tone and high-frequency energy should
    get a measurably different centroid under equal-loudness weighting than
    under a plain linear average."""
    from audio_analysis.analysis_core.dsp_metrics import spectrum_magnitudes
    from audio_analysis.mixdown.stem_classifier import _perceptual_spectral_centroid, _spectral_centroid

    kick_signal = _kick_like_signal()
    mags, fft_n = spectrum_magnitudes(kick_signal.tolist(), _SR, size=4096)

    plain = _spectral_centroid(mags, _SR, fft_n)
    weighted = _perceptual_spectral_centroid(mags, _SR, fft_n)

    assert plain != pytest.approx(weighted, abs=1.0), (
        "equal-loudness weighting should change the centroid for a signal "
        "with meaningful high-frequency content, not leave it unchanged"
    )
