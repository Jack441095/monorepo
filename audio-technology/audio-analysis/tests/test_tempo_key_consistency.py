"""Tests for the tempo consistency detector across stems (Stage M3).

See docs/AUDIO_MVP_MASTER_PLAN.md Stage M3 and tempo_key_consistency.py's own
module docstring for why the originally-planned key-consistency half was
investigated and dropped (an honest negative result: real testing showed
`key_confidence_score` doesn't gate atonal/percussive content at all, and
real tonal stems within the same song don't converge to a shared key via
whole-track chroma averaging). Only tempo consistency is tested here.
"""

from __future__ import annotations

import numpy as np

from audio_analysis.analysis_core.tempo_key_consistency import (
    _stem_bpm,
    analyze_stems_for_tempo_consistency,
)

SR = 44100


def _click_track(bpm: float, duration_s: float = 20.0, sample_rate: int = SR) -> np.ndarray:
    """A steady eighth-note click train at the given tempo. `estimate_bpm()`
    is calibrated for eighth-note-spaced onset patterns (its own skip-one
    interval math spans a complete beat for eighth notes -- confirmed
    against test_transient_groove.py's own `test_swung_eighths_...` fixture,
    which uses 0.25s-spaced onsets for a 120 BPM target), not raw
    quarter-note clicks -- confirmed empirically before relying on it here.
    """
    signal = np.zeros(int(sample_rate * duration_s), dtype=np.float64)
    tail = np.exp(-np.arange(int(0.02 * sample_rate)) / (0.004 * sample_rate))
    eighth_period = 30.0 / bpm
    t = 0.0
    while t < duration_s:
        start = int(round(t * sample_rate))
        end = min(len(signal), start + len(tail))
        if end > start:
            signal[start:end] += tail[: end - start]
        t += eighth_period
    return signal


def _sparse_transient(duration_s: float = 8.0, sample_rate: int = SR) -> np.ndarray:
    """A single isolated hit -- not enough onsets for any real tempo estimate."""
    signal = np.zeros(int(sample_rate * duration_s), dtype=np.float64)
    signal[int(sample_rate * duration_s / 2)] = 1.0
    return signal


class TestStemBpm:
    def test_estimates_a_clean_click_track_tempo(self) -> None:
        bpm, confidence = _stem_bpm(_click_track(120.0), SR)
        assert abs(bpm - 120.0) < 2.0
        assert confidence > 0.0

    def test_sparse_transients_produce_zero_confidence(self) -> None:
        bpm, confidence = _stem_bpm(_sparse_transient(), SR)
        assert confidence == 0.0


class TestAnalyzeStemsForTempoConsistency:
    def test_flags_a_stem_with_a_clearly_inconsistent_tempo(self) -> None:
        stems = [
            {"name": "drums", "samples": _click_track(120.0)},
            {"name": "bass", "samples": _click_track(120.0)},
            {"name": "guitar", "samples": _click_track(120.0)},
            {"name": "wrong_take", "samples": _click_track(90.0)},
        ]
        results = analyze_stems_for_tempo_consistency(stems, SR)
        assert "wrong_take" in results
        assert results["wrong_take"]["tempo_inconsistent"] is True
        assert abs(results["wrong_take"]["consensus_bpm"] - 120.0) < 1.0
        assert "drums" not in results
        assert "bass" not in results

    def test_small_tempo_jitter_within_tolerance_is_not_flagged(self) -> None:
        """Calibrated against real testing_track_stems/ data (2026-07-10):
        real same-tempo stems can differ by up to ~5.4% purely from
        per-stem estimation noise (e.g. a real STRINGS stem measured 5.36%
        off an otherwise-shared tempo) -- the tolerance must clear that
        without also swallowing real outliers."""
        stems = [
            {"name": "drums", "samples": _click_track(120.0)},
            {"name": "bass", "samples": _click_track(120.0)},
            {"name": "guitar", "samples": _click_track(126.0)},  # 5% off
        ]
        results = analyze_stems_for_tempo_consistency(stems, SR)
        assert "guitar" not in results

    def test_no_consensus_with_fewer_than_two_other_stems(self) -> None:
        """A lone stem has nothing to be compared against -- it must never
        be flagged relative to a consensus of zero or one other stem."""
        stems = [
            {"name": "drums", "samples": _click_track(120.0)},
            {"name": "guitar", "samples": _click_track(90.0)},
        ]
        results = analyze_stems_for_tempo_consistency(stems, SR)
        assert results == {}

    def test_stems_with_too_few_onsets_are_excluded_entirely(self) -> None:
        """A stem with no real tempo of its own (too sparse for
        `estimate_bpm()` to produce anything but its 0.0/0.0 no-data case)
        must be excluded both from consensus-building and from being
        flagged -- it has nothing genuine to compare."""
        stems = [
            {"name": "drums", "samples": _click_track(120.0)},
            {"name": "bass", "samples": _click_track(120.0)},
            {"name": "pad", "samples": _sparse_transient()},
        ]
        results = analyze_stems_for_tempo_consistency(stems, SR)
        assert "pad" not in results

    def test_consistent_project_produces_no_flags(self) -> None:
        stems = [
            {"name": "drums", "samples": _click_track(128.0)},
            {"name": "bass", "samples": _click_track(128.0)},
            {"name": "guitar", "samples": _click_track(128.0)},
            {"name": "keys", "samples": _click_track(129.0)},
        ]
        results = analyze_stems_for_tempo_consistency(stems, SR)
        assert results == {}

    def test_a_stem_is_never_flagged_against_a_consensus_it_dominates(self) -> None:
        """If two stems share an unusual tempo and only one other stem
        differs, the majority forms the consensus, not the minority -- this
        just confirms the median-of-others construction behaves as a real
        consensus (majority-wins), not an average that a single outlier can
        drag toward itself."""
        stems = [
            {"name": "a", "samples": _click_track(100.0)},
            {"name": "b", "samples": _click_track(100.0)},
            {"name": "c", "samples": _click_track(100.0)},
            {"name": "odd_one_out", "samples": _click_track(140.0)},
        ]
        results = analyze_stems_for_tempo_consistency(stems, SR)
        assert "odd_one_out" in results
        assert "a" not in results and "b" not in results and "c" not in results


class TestRealStemsFromStrangerProject:
    """Regression using real measured BPM values from
    testing_track_stems/stranger's actual stems (2026-07-10): most stems
    cluster tightly around ~93.75-100.45 BPM, but KICK measured 144.23 BPM
    (51% off the cluster) and SNARE measured 125.00 BPM (31% off) -- real,
    plausible tempo outliers worth a human's attention. Reproduced here via
    synthetic click tracks tuned to the real measured BPM values, confirming
    the detector's tolerance behaves correctly on real-world-derived
    numbers, not just round synthetic ones."""

    def test_flags_the_real_measured_kick_and_snare_outliers(self) -> None:
        stems = [
            {"name": "BASS", "samples": _click_track(93.75)},
            {"name": "DRUMS", "samples": _click_track(95.34)},
            {"name": "DRUM_BREAK", "samples": _click_track(93.75)},
            {"name": "PERC", "samples": _click_track(95.34)},
            {"name": "PERC_02", "samples": _click_track(95.34)},
            {"name": "PIANO", "samples": _click_track(95.34)},
            {"name": "VOCALS", "samples": _click_track(95.34)},
            {"name": "KICK", "samples": _click_track(144.23)},
            {"name": "SNARE", "samples": _click_track(125.00)},
        ]
        results = analyze_stems_for_tempo_consistency(stems, SR)
        assert "KICK" in results
        assert "SNARE" in results
        assert "BASS" not in results
        assert "DRUMS" not in results
        assert "PERC" not in results
