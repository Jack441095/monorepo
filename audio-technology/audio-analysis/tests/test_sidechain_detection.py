"""Tests for the sidechain/ducking and structured-dynamics detector (Stage K).

Per docs/AUDIO_MVP_MASTER_PLAN.md Stage K's own "Done means" spec: a real
detector, tested against a planted synthetic positive/negative control pair
(mirroring resonance_detection.py's own test pattern), plus real-world
validation against Jack's own stems (dream_of_you's kick/bass pair, a known
positive case).
"""

from __future__ import annotations

import numpy as np

from audio_analysis.analysis_core.sidechain_detection import (
    analyze_stems_for_dynamics,
    detect_sidechain_ducking,
    detect_structured_dynamics,
)

SR = 44100


def _kick_onsets(bpm: float, duration_s: float, *, sample_rate: int = SR) -> tuple[np.ndarray, list[float]]:
    """A synthetic kick track: short low-thump transients on every beat."""
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    beat_period = 60.0 / bpm
    phase = np.mod(t, beat_period)
    env = np.exp(-phase * 30.0)
    tone = np.sin(2 * np.pi * 55.0 * t) * env
    onset_times = list(np.arange(0, duration_s, beat_period))
    return tone, onset_times


def _ducked_bass(onset_times: list[float], duration_s: float, *, sample_rate: int = SR, duck_db: float = 8.0) -> np.ndarray:
    """A continuous bass tone whose amplitude genuinely dips right after
    each given onset time -- a real sidechain pump."""
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    base = 0.5 * np.sin(2 * np.pi * 80.0 * t)

    gain = np.ones(n)
    duck_amount = 10 ** (-duck_db / 20.0)
    attack_s = 0.005
    release_s = 0.15
    for onset in onset_times:
        onset_sample = int(onset * sample_rate)
        attack_len = int(attack_s * sample_rate)
        release_len = int(release_s * sample_rate)
        dip_end = min(n, onset_sample + attack_len)
        recover_end = min(n, dip_end + release_len)
        if dip_end > onset_sample:
            gain[onset_sample:dip_end] = np.linspace(1.0, duck_amount, dip_end - onset_sample)
        if recover_end > dip_end:
            gain[dip_end:recover_end] = np.linspace(duck_amount, 1.0, recover_end - dip_end)

    return base * gain


def _independent_bass(duration_s: float, *, sample_rate: int = SR) -> np.ndarray:
    """A continuous bass tone with its own slow, UNRELATED amplitude
    movement -- real dynamics, but not correlated to any trigger's onsets."""
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    base = 0.5 * np.sin(2 * np.pi * 80.0 * t)
    slow_env = 0.7 + 0.3 * np.sin(2 * np.pi * 0.37 * t)  # unrelated 0.37Hz drift
    return base * slow_env


class TestSidechainDuckingDetection:
    def test_detects_a_real_sidechain_pump(self) -> None:
        _, kick_onsets = _kick_onsets(bpm=120, duration_s=8.0)
        bass = _ducked_bass(kick_onsets, duration_s=8.0)

        result = detect_sidechain_ducking(bass, SR, kick_onsets)

        assert result["detected"] is True
        assert result["correlation"] >= 0.6
        assert result["mean_dip_db"] > 0.0

    def test_does_not_false_positive_on_independent_dynamics(self) -> None:
        _, kick_onsets = _kick_onsets(bpm=120, duration_s=8.0)
        bass = _independent_bass(duration_s=8.0)

        result = detect_sidechain_ducking(bass, SR, kick_onsets)

        assert result["detected"] is False

    def test_does_not_false_positive_on_a_flat_static_signal(self) -> None:
        _, kick_onsets = _kick_onsets(bpm=120, duration_s=8.0)
        flat = 0.4 * np.ones(int(8.0 * SR))

        result = detect_sidechain_ducking(flat, SR, kick_onsets)

        assert result["detected"] is False

    def test_no_onsets_returns_not_detected_without_crashing(self) -> None:
        bass = _independent_bass(duration_s=4.0)
        result = detect_sidechain_ducking(bass, SR, [])
        assert result["detected"] is False
        assert result["num_trigger_onsets"] == 0

    def test_few_onsets_below_confidence_floor_does_not_detect(self) -> None:
        """Even a perfect duck on only 2 onsets shouldn't be trusted --
        min_onsets_for_confidence guards against noise on sparse data."""
        onset_times = [1.0, 2.0]
        bass = _ducked_bass(onset_times, duration_s=4.0)
        result = detect_sidechain_ducking(bass, SR, onset_times, min_onsets_for_confidence=4)
        assert result["detected"] is False

    def test_detects_sidechain_present_in_only_part_of_the_track(self) -> None:
        """Regression for a real finding (2026-07-10, dream_of_you's actual
        bass/kick pair): a genuine, confirmed sidechain doesn't necessarily
        duck on every single hit across a whole song -- many mixes apply it
        more heavily in some sections than others. Real data showed a clean
        bimodal split (~40 onsets near 0dB, ~63 onsets at 15-30dB+) giving
        an aggregate correlation (0.385) below a naive whole-track
        threshold, despite the present dips being maximally unambiguous.
        Builds an equivalent synthetic case: only the second half of the
        onsets get a real, deep duck; the first half get none at all."""
        _, all_onsets = _kick_onsets(bpm=120, duration_s=16.0)
        ducked_half_onsets = all_onsets[len(all_onsets) // 2:]
        bass = _ducked_bass(ducked_half_onsets, duration_s=16.0, duck_db=20.0)

        result = detect_sidechain_ducking(bass, SR, all_onsets)

        assert result["correlation"] < 0.6, "sanity check: this case is deliberately below the blanket threshold"
        assert result["detected"] is True, (
            "a large subset of onsets with a deep, unambiguous duck should "
            "still be detected even if the overall correlation is below the "
            "whole-track threshold"
        )

    def test_does_not_false_positive_on_sparse_weak_coincidental_dips(self) -> None:
        """The OR-based detection (correlation OR a strong-subset signal)
        must not become a loophole for noisy/coincidental material -- a few
        onsets that happen to land near modest, inconsistent envelope
        wobble (not a real, deep duck) must still be rejected."""
        _, kick_onsets = _kick_onsets(bpm=120, duration_s=8.0)
        rng = np.random.default_rng(3)
        n = int(8.0 * SR)
        t = np.arange(n) / SR
        # Continuous bass with small-amplitude, uncorrelated noise-driven
        # envelope wobble -- occasionally exceeds min_dip_db by chance, but
        # never approaches the 12dB "unambiguous" strong-subset floor.
        wobble = 1.0 + 0.15 * rng.standard_normal(n)
        bass = 0.5 * np.sin(2 * np.pi * 80.0 * t) * np.clip(wobble, 0.6, 1.4)

        result = detect_sidechain_ducking(bass, SR, kick_onsets)

        assert result["detected"] is False
        assert result["mean_dip_db"] < 12.0


class TestStructuredDynamicsDetection:
    def test_detects_periodic_gain_movement(self) -> None:
        _, kick_onsets = _kick_onsets(bpm=120, duration_s=8.0)
        bass = _ducked_bass(kick_onsets, duration_s=8.0)

        result = detect_structured_dynamics(bass, SR)

        assert result["has_structured_dynamics"] is True
        assert result["detected_period_s"] is not None
        # Beat period at 120bpm is 0.5s -- the detected period should land
        # near there (or a musically-related subdivision/multiple of it).
        assert result["periodicity_strength"] > 0.0

    def test_does_not_flag_a_flat_static_signal(self) -> None:
        flat = 0.4 * np.ones(int(8.0 * SR))
        result = detect_structured_dynamics(flat, SR)
        assert result["has_structured_dynamics"] is False

    def test_does_not_flag_random_noise_envelope(self) -> None:
        rng = np.random.default_rng(7)
        n = int(8.0 * SR)
        # White noise amplitude-modulated by independent random noise --
        # real dynamics, but genuinely non-periodic.
        chaotic_env = rng.uniform(0.2, 1.0, n)
        signal = rng.normal(0, 0.3, n) * chaotic_env
        result = detect_structured_dynamics(signal, SR)
        assert result["has_structured_dynamics"] is False


class TestAnalyzeStemsForDynamics:
    def test_flags_the_ducked_bass_against_the_kick_and_leaves_others_unflagged(self) -> None:
        kick, kick_onsets = _kick_onsets(bpm=120, duration_s=8.0)
        ducked_bass = _ducked_bass(kick_onsets, duration_s=8.0)
        independent_lead = 0.3 * np.sin(2 * np.pi * 440.0 * np.arange(int(8.0 * SR)) / SR)

        stem_dicts = [
            {"name": "kick.wav", "samples": kick},
            {"name": "bass.wav", "samples": ducked_bass},
            {"name": "lead.wav", "samples": independent_lead},
        ]

        class _Profile:
            def __init__(self, name, instrument):
                self.name = name
                self.instrument = instrument

        profiles = [
            _Profile("kick.wav", "kick"),
            _Profile("bass.wav", "bass"),
            _Profile("lead.wav", "synth_lead"),
        ]

        results = analyze_stems_for_dynamics(stem_dicts, profiles, SR)

        assert results["bass.wav"]["sidechain_detected"] is True
        assert results["bass.wav"]["sidechain_trigger"] == "kick.wav"
        # synth_lead isn't in the target-instrument set, so it's never even
        # checked for sidechain (a real, deliberate scope decision, not an
        # oversight) -- confirm it comes back unflagged.
        assert results["lead.wav"]["sidechain_detected"] is False

    def test_non_target_instrument_stems_are_never_flagged(self) -> None:
        """Only bass/sub_bass/synth_pad/keys/guitar/strings are checked for
        sidechain at all -- a kick or vocal must never come back flagged."""
        kick, kick_onsets = _kick_onsets(bpm=120, duration_s=6.0)

        class _Profile:
            def __init__(self, name, instrument):
                self.name = name
                self.instrument = instrument

        stem_dicts = [{"name": "kick.wav", "samples": kick}]
        profiles = [_Profile("kick.wav", "kick")]

        results = analyze_stems_for_dynamics(stem_dicts, profiles, SR)
        assert results["kick.wav"]["sidechain_detected"] is False
        assert results["kick.wav"]["sidechain_trigger"] is None
