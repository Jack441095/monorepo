"""Regression tests for a real bug found 2026-07-10 running actual commercial
reference tracks through the style classifier for the first time
(scripts/eval/validate_style_classifier.py, Stage D).

Root cause: read_wav_mono()'s default max_samples=65536 budget means any
track with more than ~1.5s of audio gets decimated -- a real 48kHz commercial
track measured an effective analysis_sample_rate as low as ~226-444Hz. That
decimated, low-pass-smoothed signal was being reused for metrics that need
real bandwidth/precision:
  - crest_factor_db (RMS from the decimated signal was too low, inflating
    crest factor by ~2dB, enough to flip a vintage/modern classification)
  - log_bands_40 / raw_bands / ear_bands (Nyquist collapsed to ~200-450Hz,
    silently zeroing every frequency band above that -- every real track
    tested came back "Ambient" genre / "dark top-end" vintage classification
    regardless of the actual material)

Every existing test in this suite uses short synthetic clips (a few seconds
at most), which never trigger decimation (frame_count stays under 65536) --
exactly why this was invisible until real full-length audio was tested.
These tests use audio long enough to force decimation, so they'd have
caught the bug and will catch a regression.
"""

from __future__ import annotations

import io
import math
import wave

import numpy as np
import pytest

from audio_analysis.mix_review import mix_review

SAMPLE_RATE = 44100
# Long enough to force decimation: frame_count (SAMPLE_RATE * DURATION_S)
# must exceed read_wav_mono's default max_samples=65536.
DURATION_S = 30.0


def _wav_bytes(signal: np.ndarray, *, sample_rate: int = SAMPLE_RATE) -> bytes:
    pcm = np.clip(signal, -1.0, 1.0)
    payload = (pcm * 32767.0).astype("<i2").tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(payload)
    return output.getvalue()


def _broadband_signal(duration_s: float, *, sample_rate: int = SAMPLE_RATE, seed: int = 7) -> np.ndarray:
    """Deterministic full-bandwidth-ish signal: a few tones spread across the
    spectrum (sub/bass/mid/presence/air) plus light broadband noise, so every
    log-band and the 8-16kHz 'air' band have real, nonzero, verifiable energy
    -- not silence, which real commercial masters never are either."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    tones_hz = [60, 250, 1000, 4000, 12000]
    signal = sum(0.12 * np.sin(2 * np.pi * f * t) for f in tones_hz)
    signal += 0.02 * rng.standard_normal(len(t))
    return signal.astype(np.float64)


class TestDecimationTriggersOnLongTracks:
    def test_default_read_actually_decimates_a_long_track(self) -> None:
        """Sanity check the premise: without this, the rest of this file
        would be testing a scenario that never occurs."""
        from audio_analysis.utils.audio_io import read_wav_mono

        signal = _broadband_signal(DURATION_S)
        data = read_wav_mono(_wav_bytes(signal))
        assert data["analysis_sample_rate"] < SAMPLE_RATE / 2, (
            "expected default read_wav_mono to decimate a 30s track "
            f"(analysis_sample_rate={data['analysis_sample_rate']})"
        )


class TestCrestFactorFidelity:
    def test_crest_factor_matches_full_rate_ground_truth_on_a_long_track(self) -> None:
        signal = _broadband_signal(DURATION_S)
        wav_bytes = _wav_bytes(signal)

        report = mix_review.analyze_wav(wav_bytes, "long-track.wav", mix_goal="premaster")
        measured_crest = report["metrics"]["crest_factor_db"]

        true_peak = float(np.max(np.abs(signal)))
        true_rms = float(np.sqrt(np.mean(signal**2)))
        true_crest = 20 * math.log10(true_peak) - 20 * math.log10(true_rms)

        assert measured_crest == pytest.approx(true_crest, abs=0.15), (
            f"measured crest factor {measured_crest}dB should match the true "
            f"full-rate crest factor {true_crest:.2f}dB, not a decimated "
            "approximation"
        )

    def test_short_track_still_works_unchanged(self) -> None:
        """Short clips never hit the decimation path -- confirm the fix
        doesn't regress the common/existing case."""
        signal = _broadband_signal(1.0)
        report = mix_review.analyze_wav(_wav_bytes(signal), "short.wav", mix_goal="premaster")
        assert report["ok"] is True
        assert report["metrics"]["crest_factor_db"] > 0


class TestSpectralBandFidelity:
    def test_log_bands_40_has_no_exact_zero_bands_on_a_long_broadband_track(self) -> None:
        """The smoking gun from the real bug: bands above ~200-500Hz came
        back exactly 0.0 for every real track tested, because the decimated
        signal's Nyquist had collapsed below them."""
        signal = _broadband_signal(DURATION_S)
        report = mix_review.analyze_wav(_wav_bytes(signal), "long-track.wav", mix_goal="premaster")
        bands = report["metrics"]["log_bands_40"]

        assert len(bands) == 40
        zero_bands = sum(1 for v in bands if v == 0.0)
        assert zero_bands == 0, f"{zero_bands}/40 bands are exactly zero -- Nyquist collapse regression"

    def test_air_band_share_is_nonzero_on_a_long_track_with_planted_high_frequency_energy(self) -> None:
        """raw_bands/ear_bands feed classify_vintage_or_modern's air-share
        (8-16kHz) check -- this was always reading ~0 (forcing a false
        'dark top-end/vintage' classification) because the 'air' band lives
        entirely above the decimated Nyquist ceiling."""
        signal = _broadband_signal(DURATION_S)
        report = mix_review.analyze_wav(_wav_bytes(signal), "long-track.wav", mix_goal="premaster")
        air_share = report["metrics"]["bands"].get("air")

        assert air_share is not None
        assert air_share > 0.0, "air (8-16kHz) share should reflect the planted 12kHz tone, not read as zero"

    def test_genre_fingerprint_differs_between_dissimilar_long_tracks(self) -> None:
        """Before the fix, every real track collapsed to the same
        near-silent-high-band profile and classified as the same genre
        ('Ambient', 0.0 confidence) regardless of actual content."""
        from audio_analysis.analysis_core.genre_profiles import classify_reference_profile

        bright_signal = _broadband_signal(DURATION_S, seed=1) + 0.15 * np.sin(
            2 * np.pi * 9000 * np.linspace(0, DURATION_S, int(SAMPLE_RATE * DURATION_S), endpoint=False)
        )
        dark_signal = 0.3 * np.sin(
            2 * np.pi * 80 * np.linspace(0, DURATION_S, int(SAMPLE_RATE * DURATION_S), endpoint=False)
        ) + 0.01 * np.random.default_rng(2).standard_normal(int(SAMPLE_RATE * DURATION_S))

        bright_report = mix_review.analyze_wav(_wav_bytes(bright_signal), "bright.wav", mix_goal="premaster")
        dark_report = mix_review.analyze_wav(_wav_bytes(dark_signal), "dark.wav", mix_goal="premaster")

        bright_profile = bright_report["metrics"]["log_bands_40"]
        dark_profile = dark_report["metrics"]["log_bands_40"]

        assert bright_profile != dark_profile, "two spectrally distinct long tracks must not collapse to the same fingerprint"

        # Also confirm the classifier itself sees a real difference, not
        # just that the raw bands differ trivially.
        bright_class = classify_reference_profile(bright_profile, bright_report["metrics"])
        dark_class = classify_reference_profile(dark_profile, dark_report["metrics"])
        assert bright_class["distance_db"] != dark_class["distance_db"]


class TestLufsFidelityOnLongTracks:
    """A second, independent instance of the same root bug -- found
    2026-07-10 running a real 15-stem AutoMix render through analyze_wav()
    for the first time. AutoMix's own render measured -9.01 LUFS against a
    -9.0 target (correct: computed from the full-rate in-memory signal,
    never decimated). Re-analyzing the identical rendered audio via
    analyze_wav() read -14.0 -- a 5 LU phantom error that was never in the
    audio.

    Root cause was NOT analyze_wav()'s own read_wav_mono() call (already
    fixed above for crest factor / spectral bands) -- it was one level
    deeper: calculate_lufs_numpy() (analysis_core/loudness.py) had its OWN
    internal decimation, unconditionally collapsing any input over 600,000
    samples (~12.5s at 48kHz -- nearly every real song) down to ~300,000
    samples, landing at an effective ~4000Hz analysis rate regardless of
    what rate analyze_wav() had already re-read at. calculate_loudness_
    profile_numpy (the sibling function AutoMix's own render actually uses)
    has no such internal guard and was always correct -- these tests target
    the specific broken function (calculate_lufs / calculate_lufs_numpy),
    not analyze_wav()'s own re-read logic, which was already correct.
    """

    def test_integrated_lufs_matches_full_rate_ground_truth_on_a_long_track(self) -> None:
        signal = _broadband_signal(DURATION_S)
        wav_bytes = _wav_bytes(signal)

        report = mix_review.analyze_wav(wav_bytes, "long-track.wav", mix_goal="premaster")
        measured_lufs = report["metrics"]["integrated_lufs"]

        from audio_analysis.analysis_core.loudness import calculate_loudness_profile_numpy
        ground_truth = calculate_loudness_profile_numpy(signal, signal, SAMPLE_RATE)["integrated_lufs"]

        assert measured_lufs == pytest.approx(ground_truth, abs=0.15), (
            f"analyze_wav's integrated_lufs ({measured_lufs}) should match the "
            f"full-rate ground truth ({ground_truth:.2f}), not a decimated "
            "approximation from calculate_lufs_numpy's internal step-down"
        )

    def test_calculate_lufs_numpy_matches_loudness_profile_numpy_on_a_long_signal(self) -> None:
        """Direct regression on the actual broken function, independent of
        analyze_wav()'s plumbing: the two sibling LUFS implementations must
        not disagree by LUs on the same long signal."""
        from audio_analysis.analysis_core.loudness import (
            calculate_lufs_numpy,
            calculate_loudness_profile_numpy,
        )

        signal = _broadband_signal(DURATION_S)
        lufs = calculate_lufs_numpy(signal, signal, SAMPLE_RATE)
        profile_lufs = calculate_loudness_profile_numpy(signal, signal, SAMPLE_RATE)["integrated_lufs"]

        assert lufs == pytest.approx(profile_lufs, abs=0.15), (
            f"calculate_lufs_numpy ({lufs}) and calculate_loudness_profile_numpy "
            f"({profile_lufs}) disagree on the same signal -- one of them is still "
            "decimating internally"
        )

    def test_short_signal_still_matches_unchanged(self) -> None:
        """A signal under the (now much higher) decimation trigger must
        behave exactly as before -- confirms this fix doesn't regress the
        common/existing case."""
        from audio_analysis.analysis_core.loudness import (
            calculate_lufs_numpy,
            calculate_loudness_profile_numpy,
        )

        signal = _broadband_signal(2.0)
        lufs = calculate_lufs_numpy(signal, signal, SAMPLE_RATE)
        profile_lufs = calculate_loudness_profile_numpy(signal, signal, SAMPLE_RATE)["integrated_lufs"]
        assert lufs == pytest.approx(profile_lufs, abs=0.15)

    def test_analyze_wav_lufs_reread_budget_survives_a_real_song_length_track(self) -> None:
        """Regression for a second instance of the same bug class, found
        immediately after the first fix on a real ~3.5min track ('stranger'):
        analyze_wav()'s own LUFS re-read had a 4,000,000-sample budget cap
        (copied from the spectral-fingerprint fix, which was verified against
        an 80s track where that cap happened to be enough) -- for a longer
        real song this cap alone bought only ~19kHz effective rate, still
        lossy enough to produce a real 2.63 LU error (-13.97 actual vs -16.6
        measured). The cap must scale to at least LUFS_DECIMATION_TRIGGER_
        SAMPLES (calculate_lufs_numpy's own ceiling), not a smaller one that
        silently reintroduces the bug for anything longer than ~100s.

        Uses 150s (not a full 3.5min) to keep this test reasonably fast while
        still exceeding the old 4,000,000-sample cap (150s * 44100Hz =
        6,615,000 samples; the old cap would have re-read at only ~26,667Hz,
        aliasing away most of a planted 12kHz tone's contribution)."""
        long_duration_s = 150.0
        signal = _broadband_signal(long_duration_s)
        wav_bytes = _wav_bytes(signal, sample_rate=SAMPLE_RATE)

        report = mix_review.analyze_wav(wav_bytes, "long-song.wav", mix_goal="premaster")
        measured_lufs = report["metrics"]["integrated_lufs"]

        from audio_analysis.analysis_core.loudness import calculate_loudness_profile_numpy
        ground_truth = calculate_loudness_profile_numpy(signal, signal, SAMPLE_RATE)["integrated_lufs"]

        assert measured_lufs == pytest.approx(ground_truth, abs=0.3), (
            f"analyze_wav's integrated_lufs ({measured_lufs}) should match the "
            f"full-rate ground truth ({ground_truth:.2f}) on a real song-length "
            "track, not a budget-capped approximation"
        )
