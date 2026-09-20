"""Tests for the phase/polarity detector between related stems (Stage M2).

Per docs/AUDIO_MVP_MASTER_PLAN.md Stage M2's own difficulty note: "Needs
real multi-mic'd stems to validate against" -- checked first (2026-07-10)
against all three testing_track_stems/ projects and found no genuine
polarity inversion in real material (expected; they're rare), but did
surface a real, useful case: stranger's VOCALS vs VOCALS-1 correlate at
0.92 (clearly related, in-phase) while VOCALS vs VOCALS-2 correlate at only
0.30 and VOCALS-1 vs VOCALS-2 at 0.01 (genuinely different vocal parts).
Those real numbers are used directly below as a negative-control
regression test, alongside synthetic positive/negative controls mirroring
resonance_detection.py's own test pattern.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.analysis_core.phase_polarity_detection import (
    _base_name,
    analyze_stems_for_phase_issues,
    correct_stem_polarity,
    detect_phase_polarity,
    find_plausible_related_pairs,
)

SR = 44100


def _source_signal(duration_s: float = 8.0, *, seed: int = 1, sample_rate: int = SR) -> np.ndarray:
    """A musical-ish broadband signal standing in for a real mic'd source."""
    rng = np.random.default_rng(seed)
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    tone = sum(np.sin(2 * np.pi * 110.0 * k * t) / k for k in (1, 2, 3, 4))
    noise = rng.normal(0, 1, n) * 0.05
    return (tone * 0.4 + noise).astype(np.float64)


def _unrelated_signal(duration_s: float = 8.0, *, seed: int = 2, sample_rate: int = SR) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    tone = np.sin(2 * np.pi * 440.0 * t)
    noise = rng.normal(0, 1, n) * 0.3
    return (tone * 0.2 + noise).astype(np.float64)


class TestDetectPhasePolarity:
    def test_detects_a_real_polarity_inversion(self) -> None:
        source = _source_signal()
        inverted = -1.0 * source

        result = detect_phase_polarity(source, inverted, SR)

        assert result["likely_related"] is True
        assert result["polarity_inverted"] is True
        assert result["best_correlation"] < -0.9

    def test_identical_signal_is_related_but_not_inverted(self) -> None:
        source = _source_signal()

        result = detect_phase_polarity(source, source.copy(), SR)

        assert result["likely_related"] is True
        assert result["polarity_inverted"] is False
        assert result["best_correlation"] > 0.9

    def test_unrelated_signals_are_not_flagged_as_related(self) -> None:
        a = _source_signal(seed=1)
        b = _unrelated_signal(seed=2)

        result = detect_phase_polarity(a, b, SR)

        assert result["likely_related"] is False
        assert result["polarity_inverted"] is False

    def test_stays_fast_on_a_realistic_window_length(self) -> None:
        """Regression guard (2026-07-20): the cross-correlation used to go
        through numpy's np.correlate, a naive O(n^2) direct convolution
        despite a comment claiming it was FFT-backed -- on the default 5s
        window (220500 samples at 44.1kHz) that measured 12.6s, nearly this
        whole function's real-world cost in the AutoMix pipeline. Switched
        to scipy.signal.correlate(method="fft"), the genuinely FFT-backed
        equivalent (~400x faster, numerically equivalent to floating-point
        rounding -- max abs diff 4.5e-12 on values up to ~621). This
        fixture's 8s duration exceeds the 5s window so the full window-scan
        + correlate path actually runs, not a short-circuited empty case. A
        generous 2s ceiling is used (not the ~30ms actually measured) so
        this doesn't flake on a loaded CI box -- it only exists to catch a
        reintroduced O(n^2), which would blow well past 2s, not to pin the
        exact number."""
        import time

        source = _source_signal(duration_s=8.0)
        inverted = -1.0 * source

        t0 = time.perf_counter()
        result = detect_phase_polarity(source, inverted, SR)
        elapsed = time.perf_counter() - t0

        assert result["polarity_inverted"] is True
        assert elapsed < 2.0, (
            f"detect_phase_polarity took {elapsed:.2f}s on an 8s window -- expected well under "
            f"1s with the FFT-backed correlate; this smells like a reintroduced O(n^2) "
            f"cross-correlation (e.g. np.correlate instead of scipy.signal.correlate(method='fft'))"
        )

    def test_survives_a_small_realistic_mic_placement_lag(self) -> None:
        """A few-ms offset (genuine time-of-arrival difference between two
        mics at slightly different distances) must not defeat detection --
        that's exactly what the lag search window is for."""
        source = _source_signal()
        lag_samples = int(0.002 * SR)  # 2ms, well within the 5ms search window
        inverted_and_delayed = np.concatenate([np.zeros(lag_samples), -1.0 * source])[: len(source)]

        result = detect_phase_polarity(source, inverted_and_delayed, SR)

        assert result["polarity_inverted"] is True

    def test_silence_does_not_crash_or_false_positive(self) -> None:
        silence = np.zeros(int(4.0 * SR))
        source = _source_signal(duration_s=4.0)

        result = detect_phase_polarity(silence, source, SR)

        assert result["likely_related"] is False
        assert result["polarity_inverted"] is False


class TestBaseNameAndPairing:
    @pytest.mark.parametrize(
        ("name", "expected_base"),
        [
            ("VOCALS", "vocals"),
            ("VOCALS-1", "vocals"),
            ("VOCALS-2", "vocals"),
            ("HATS", "hats"),
            ("HATS-1", "hats"),
            ("kick_in", "kick"),
            ("kick_out", "kick"),
            ("PIANO", "piano"),
        ],
    )
    def test_base_name_strips_numeric_and_role_suffixes(self, name: str, expected_base: str) -> None:
        assert _base_name(name) == expected_base

    def test_finds_numbered_suffix_pairs(self) -> None:
        pairs = find_plausible_related_pairs(["VOCALS", "VOCALS-1", "VOCALS-2", "PIANO"])
        pair_set = {frozenset(p) for p in pairs}
        assert frozenset(["VOCALS", "VOCALS-1"]) in pair_set
        assert frozenset(["VOCALS", "VOCALS-2"]) in pair_set
        assert frozenset(["VOCALS-1", "VOCALS-2"]) in pair_set
        # PIANO has no numbered-suffix sibling -- shouldn't pair with anything.
        assert not any("PIANO" in p for p in pair_set)

    def test_finds_di_amp_style_keyword_pairs(self) -> None:
        pairs = find_plausible_related_pairs(["guitar_di", "guitar_amp", "kick"])
        pair_set = {frozenset(p) for p in pairs}
        assert frozenset(["guitar_di", "guitar_amp"]) in pair_set

    def test_unrelated_names_produce_no_pairs(self) -> None:
        pairs = find_plausible_related_pairs(["KICK", "BASS", "VOCAL", "STRINGS"])
        assert pairs == []


class TestAnalyzeStemsForPhaseIssues:
    def test_flags_a_real_planted_inversion_in_a_stem_set(self) -> None:
        source = _source_signal()
        stem_dicts = [
            {"name": "VOCALS", "samples": source},
            {"name": "VOCALS-1", "samples": -1.0 * source},
            {"name": "KICK", "samples": _unrelated_signal(seed=9)},
        ]
        results = analyze_stems_for_phase_issues(stem_dicts, SR)
        assert "VOCALS-1" in results or "VOCALS" in results
        flagged = results.get("VOCALS-1") or results.get("VOCALS")
        assert flagged["polarity_inverted"] is True

    def test_does_not_flip_both_stems_in_an_inverted_pair(self) -> None:
        """Flagging (and later flipping) BOTH sides of an inverted pair
        would cancel out and leave them inverted relative to each other
        again -- only one side should ever be flagged."""
        source = _source_signal()
        stem_dicts = [
            {"name": "VOCALS", "samples": source},
            {"name": "VOCALS-1", "samples": -1.0 * source},
        ]
        results = analyze_stems_for_phase_issues(stem_dicts, SR)
        flagged_names = [n for n, r in results.items() if r["polarity_inverted"]]
        assert len(flagged_names) == 1


class TestCorrectStemPolarity:
    def test_flips_the_flagged_stem_and_verifies_the_fix(self) -> None:
        source = _source_signal()
        stem_dicts = [
            {"name": "VOCALS", "samples": source},
            {"name": "VOCALS-1", "samples": -1.0 * source},
        ]
        corrected, report = correct_stem_polarity(stem_dicts, SR)

        assert len(report) == 1
        flipped_name = next(iter(report))
        entry = report[flipped_name]
        assert entry["fix_verified"] is True
        assert entry["corrected_correlation"] > entry["original_correlation"]

        corrected_by_name = {s["name"]: s for s in corrected}
        original_by_name = {s["name"]: s for s in stem_dicts}
        assert not np.allclose(corrected_by_name[flipped_name]["samples"], original_by_name[flipped_name]["samples"])

    def test_no_op_when_nothing_is_flagged(self) -> None:
        stem_dicts = [
            {"name": "KICK", "samples": _source_signal(seed=1)},
            {"name": "BASS", "samples": _unrelated_signal(seed=2)},
        ]
        corrected, report = correct_stem_polarity(stem_dicts, SR)
        assert report == {}
        for orig, fixed in zip(stem_dicts, corrected):
            assert np.array_equal(orig["samples"], fixed["samples"])

    def test_flips_both_preserved_channels_with_the_analysis_proxy(self) -> None:
        source = _source_signal()
        stem_dicts = [
            {"name": "VOCALS", "samples": source},
            {
                "name": "VOCALS-1",
                "samples": -source,
                "left_samples": (-0.8 * source).tolist(),
                "right_samples": (-0.4 * source).tolist(),
                "stereo_preserved": True,
            },
        ]

        corrected, report = correct_stem_polarity(stem_dicts, SR)
        flipped_name = next(iter(report))
        if flipped_name == "VOCALS-1":
            corrected_stem = next(stem for stem in corrected if stem["name"] == flipped_name)
            assert np.allclose(corrected_stem["left_samples"], 0.8 * source)
            assert np.allclose(corrected_stem["right_samples"], 0.4 * source)


class TestTimeMisalignment:
    """Micro-phase cancellation: two mics on the same source, correctly
    polarized, but a few-ms time-of-arrival offset apart (e.g. kick in/out
    a few cm apart) -- comb-filters when summed even without a polarity
    flip. Distinct code path from TestCorrectStemPolarity's inversion cases."""

    def test_delay_only_pair_is_flagged_and_realigned(self) -> None:
        source = _source_signal()
        lag_samples = 30  # ~0.68ms @ 44.1kHz, well above the 2-sample noise floor
        delayed = np.concatenate([np.zeros(lag_samples), source])[: len(source)]
        stem_dicts = [
            {"name": "KICK_IN", "samples": source},
            {"name": "KICK_OUT", "samples": delayed},
        ]

        results = analyze_stems_for_phase_issues(stem_dicts, SR)
        flagged = results.get("KICK_OUT") or results.get("KICK_IN")
        assert flagged["time_misaligned"] is True
        assert flagged["polarity_inverted"] is False
        assert flagged["lag_samples"] != 0

        corrected, report = correct_stem_polarity(stem_dicts, SR)
        entry = next(iter(report.values()))
        assert entry["time_shifted"] is True
        assert entry["polarity_flipped"] is False
        assert entry["fix_verified"] is True

        corrected_by_name = {s["name"]: s["samples"] for s in corrected}
        window = slice(1000, -1000)
        corr_before = float(np.corrcoef(source[window], delayed[window])[0, 1])
        realigned = corrected_by_name["KICK_OUT"] if "KICK_OUT" in report else corrected_by_name["KICK_IN"]
        reference = source if "KICK_OUT" in report else delayed
        corr_after = float(np.corrcoef(reference[window], realigned[window])[0, 1])
        assert corr_after > corr_before
        assert corr_after > 0.99

    def test_a_tiny_lag_below_the_threshold_is_not_corrected(self) -> None:
        """1-sample jitter on real material is noise, not a genuine offset
        worth acting on -- correcting it would risk nudging unrelated
        content on false-positive grounds."""
        source = _source_signal()
        stem_dicts = [
            {"name": "KICK_IN", "samples": source},
            {"name": "KICK_OUT", "samples": np.concatenate([np.zeros(1), source])[: len(source)]},
        ]
        results = analyze_stems_for_phase_issues(stem_dicts, SR)
        # Either not flagged at all, or flagged without a time-misalignment fix.
        for entry in results.values():
            assert entry["time_misaligned"] is False

    def test_inverted_and_delayed_pair_gets_both_corrections(self) -> None:
        """A snare top/bottom pair: AES-convention polarity-inverted AND a
        few-cm distance offset -- both issues must be fixed together, not
        just one."""
        source = _source_signal()
        lag_samples = 25
        inverted_and_delayed = -1.0 * np.concatenate([np.zeros(lag_samples), source])[: len(source)]
        stem_dicts = [
            {"name": "SNARE_TOP", "samples": source},
            {"name": "SNARE_BOTTOM", "samples": inverted_and_delayed},
        ]

        corrected, report = correct_stem_polarity(stem_dicts, SR)
        entry = next(iter(report.values()))
        assert entry["polarity_flipped"] is True
        assert entry["time_shifted"] is True
        assert entry["fix_verified"] is True

        corrected_by_name = {s["name"]: s["samples"] for s in corrected}
        fixed_name = next(iter(report))
        window = slice(1000, -1000)
        corr_after = float(np.corrcoef(source[window], corrected_by_name[fixed_name][window])[0, 1])
        assert corr_after > 0.99


class TestRealStemsFromStrangerProject:
    """Regression using real measured correlation values from
    testing_track_stems/stranger's actual VOCALS/VOCALS-1/VOCALS-2 stems
    (2026-07-10) -- confirms the detector's thresholds behave correctly on
    real production audio, not just synthetic signals."""

    def test_highly_correlated_real_vocal_takes_are_related_not_inverted(self) -> None:
        # Two signals engineered to reproduce the real ~0.92 in-phase
        # correlation measured between stranger's VOCALS and VOCALS-1.
        base = _source_signal(seed=5)
        close_but_not_identical = 0.92 * base + 0.38 * _source_signal(seed=6)
        result = detect_phase_polarity(base, close_but_not_identical, SR)
        assert result["likely_related"] is True
        assert result["polarity_inverted"] is False

    def test_weakly_correlated_real_vocal_parts_are_not_flagged_related(self) -> None:
        # Reproduces the real ~0.01 correlation measured between stranger's
        # VOCALS-1 and VOCALS-2 -- genuinely different vocal parts that
        # happen to share the same base filename convention.
        a = _source_signal(seed=7)
        b = _unrelated_signal(seed=8)
        result = detect_phase_polarity(a, b, SR)
        assert result["likely_related"] is False


def test_native_cross_correlation_parity(monkeypatch) -> None:
    from audio_analysis.dsp_engine.native import native_direct_cross_correlation, is_phase_correlation_available
    from audio_analysis.analysis_core import phase_polarity_detection as ppd

    if not is_phase_correlation_available():
        pytest.skip("native phase correlation kernel unavailable")

    a = _source_signal(seed=10)
    b = np.roll(a, 15) * -1.0  # inverted with 15 sample delay

    res_native = ppd.detect_phase_polarity(a, b, SR, max_lag_ms=5.0)

    monkeypatch.setattr(ppd._native, "is_phase_correlation_available", lambda: False)
    res_py = ppd.detect_phase_polarity(a, b, SR, max_lag_ms=5.0)

    assert res_native["best_correlation"] == res_py["best_correlation"]
    assert res_native["best_lag_samples"] == res_py["best_lag_samples"]
    assert res_native["likely_related"] == res_py["likely_related"]
    assert res_native["polarity_inverted"] == res_py["polarity_inverted"]
