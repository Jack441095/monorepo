"""Tests for Stage M1: per-stem dynamic EQ in mix_and_render_stems().

The detector (resonance_detection.py) and processor (dynamic_eq.py) are
already fully tested in isolation (test_resonance_detection.py,
test_dynamic_eq.py) -- this file verifies the NEW thing Stage M1 adds: that
mix_and_render_stems() actually runs that same detector/processor per-stem,
before mixing, and reports what it found/fixed via "stem_dynamic_eq_bands",
without breaking anything else in the render.
"""

from __future__ import annotations

import numpy as np

from audio_analysis.mixdown import mix_renderer
from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems

SR = 44100
DURATION_S = 6.0
N = int(SR * DURATION_S)
_T = np.arange(N) / SR


def _profile(name: str, instrument: str, *, frequency_profile: dict | None = None) -> StemProfile:
    return StemProfile(
        name=name, instrument=instrument, peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0,
        frequency_profile=frequency_profile or {},
    )


def _resonant_stem(seed: int = 1) -> np.ndarray:
    """A guitar-ish stem with a real, persistent, planted narrow resonance
    at 900Hz (a classic "boxy/nasal" mixing problem) riding on top of
    broadband harmonic content -- mirrors resonance_detection.py's own
    positive-control pattern, just as a full-length "stem" instead of a
    bare test spectrum."""
    rng = np.random.default_rng(seed)
    harm = sum(np.sin(2 * np.pi * 220.0 * k * _T) / k for k in (1, 2, 3, 4))
    resonance = 0.5 * np.sin(2 * np.pi * 900.0 * _T)
    noise = rng.normal(0, 1, N) * 0.02
    return (harm * 0.3 + resonance + noise).astype(np.float64)


def _clean_stem(freq: float, seed: int = 2) -> np.ndarray:
    """A simple, broadband-clean tone -- no planted resonance, the negative
    control (mirrors resonance_detection.py's own flat-noise negative
    control, just as a musical-sounding stem)."""
    rng = np.random.default_rng(seed)
    harm = sum(np.sin(2 * np.pi * freq * k * _T) / k for k in (1, 2, 3))
    noise = rng.normal(0, 1, N) * 0.03
    return (harm * 0.3 + noise).astype(np.float64)


def _render(stems_and_instruments: list[tuple[str, str, np.ndarray]]) -> dict:
    profiles = [_profile(name, instrument) for name, instrument, _ in stems_and_instruments]
    stem_dicts = [
        {"name": name, "samples": samples, "sample_rate": SR}
        for name, _, samples in stems_and_instruments
    ]
    plan = generate_mix_plan(profiles, genre="rock", target_lufs=-12.0)
    plan.genre = "rock"
    plan.bus.limiter_ceiling_db = -1.0
    return mix_and_render_stems(stem_dicts, plan)


class TestStemDynamicEqDetectsAndFixesRealResonance:
    def test_finds_and_reports_a_planted_resonance(self) -> None:
        result = _render([
            ("guitar.wav", "guitar", _resonant_stem()),
            ("bass.wav", "bass", _clean_stem(80.0, seed=3)),
        ])
        stem_eq = result["stem_dynamic_eq_bands"]
        assert "guitar.wav" in stem_eq
        bands = stem_eq["guitar.wav"]
        assert len(bands) >= 1
        # The planted resonance is at 900Hz -- confirm the detector actually
        # found something in that neighborhood, not an arbitrary band.
        assert any(700.0 <= b["frequency_hz"] <= 1100.0 for b in bands)

    def test_is_transparent_on_a_clean_stem(self) -> None:
        result = _render([
            ("bass.wav", "bass", _clean_stem(80.0, seed=3)),
        ])
        stem_eq = result["stem_dynamic_eq_bands"]
        assert "bass.wav" not in stem_eq

    def test_only_flags_the_stem_that_actually_has_a_resonance(self) -> None:
        result = _render([
            ("guitar.wav", "guitar", _resonant_stem()),
            ("bass.wav", "bass", _clean_stem(80.0, seed=3)),
        ])
        stem_eq = result["stem_dynamic_eq_bands"]
        assert "guitar.wav" in stem_eq
        assert "bass.wav" not in stem_eq

    def test_render_still_produces_valid_output_with_stem_dynamic_eq_engaged(self) -> None:
        """The new pre-mix stage must not break the existing render
        contract -- valid WAV bytes, correct sample rate, no clipping."""
        result = _render([
            ("guitar.wav", "guitar", _resonant_stem()),
            ("bass.wav", "bass", _clean_stem(80.0, seed=3)),
        ])
        assert isinstance(result["mixdown_wav_bytes"], bytes)
        assert len(result["mixdown_wav_bytes"]) > 44
        assert result["sample_rate"] == SR
        max_peak = float(np.max(np.abs(np.vstack([result["left"], result["right"]]))))
        assert max_peak <= 1.0 + 1e-6

    def test_stem_dynamic_eq_key_always_present_even_when_empty(self) -> None:
        """Backward-compatible contract: the key always exists (empty dict,
        not missing) even when no stem has a resonance -- callers can rely
        on result["stem_dynamic_eq_bands"] without a .get() fallback."""
        result = _render([("bass.wav", "bass", _clean_stem(80.0, seed=3))])
        assert result["stem_dynamic_eq_bands"] == {}

    def test_master_bus_prominence_is_reduced_relative_to_the_original_stem_level_finding(self) -> None:
        """The 'additive, self-correcting' claim from the Stage M1 design,
        stated honestly rather than over-claimed: the stem-level fix is
        capped at a max 6dB reduction per band (Stage C's own deliberate
        safety limit, "never over-cut to avoid dulling the mix"), so a very
        strong planted resonance can still show up at the master-bus level
        -- but measurably REDUCED versus what the stem-level detector
        originally found, not unchanged or worse. Verified empirically: for
        this test's deliberately strong planted resonance (~19dB
        prominence), the master-bus finding at the same frequency is lower
        than the original stem-level measurement, not eliminated outright --
        that's the real, calibrated behavior of a capped, conservative
        detector, not a bug."""
        result = _render([
            ("guitar.wav", "guitar", _resonant_stem()),
            ("bass.wav", "bass", _clean_stem(80.0, seed=3)),
        ])
        stem_bands = {b["frequency_hz"]: b["mean_prominence_db"] for b in result["stem_dynamic_eq_bands"]["guitar.wav"]}
        master_bands = {b["frequency_hz"]: b["mean_prominence_db"] for b in result["dynamic_eq_bands"]}

        matched = 0
        for freq, original_prominence in stem_bands.items():
            master_match = next((mp for mf, mp in master_bands.items() if abs(mf - freq) < 5.0), None)
            if master_match is not None:
                matched += 1
                assert master_match < original_prominence, (
                    f"master-bus prominence at ~{freq:.0f}Hz ({master_match}dB) should be lower than "
                    f"the original stem-level finding ({original_prominence}dB) -- the stem-level cut "
                    f"should have helped, even if capped reduction didn't eliminate it outright"
                )
        assert matched > 0, "expected at least one of the stem-level bands to still be measurable at the master bus for this comparison to mean anything"


class TestNeedsResonanceScanGate:
    """dsp_engine/dsp_necessity.py's needs_resonance_scan skips the per-stem
    detect_resonant_bands call entirely for a stem with negligible energy
    above 150Hz -- proves the actual call is skipped (the CPU-saving claim),
    not just that the output happens to be unaffected."""

    _PURE_SUB_BASS_PROFILE = {
        "sub": 0.85, "bass": 0.13, "low_mids": 0.01, "mids": 0.005,
        "presence": 0.003, "sibilance": 0.001, "air": 0.001,
    }
    _FULL_SPECTRUM_PROFILE = {
        "sub": 0.1, "bass": 0.1, "low_mids": 0.2, "mids": 0.3,
        "presence": 0.15, "sibilance": 0.1, "air": 0.05,
    }

    def test_plan_marks_pure_sub_bass_stem_as_not_needing_a_scan(self):
        profile = _profile("sub.wav", "sub_bass", frequency_profile=self._PURE_SUB_BASS_PROFILE)
        plan = generate_mix_plan([profile], genre="edm", target_lufs=-9.0)
        config = next(c for c in plan.stems if c.stem_name == "sub.wav")
        assert config.needs_resonance_scan is False

    def test_plan_marks_full_spectrum_stem_as_needing_a_scan(self):
        profile = _profile("guitar.wav", "guitar", frequency_profile=self._FULL_SPECTRUM_PROFILE)
        plan = generate_mix_plan([profile], genre="rock", target_lufs=-12.0)
        config = next(c for c in plan.stems if c.stem_name == "guitar.wav")
        assert config.needs_resonance_scan is True

    def test_render_skips_the_detector_call_for_a_stem_marked_unneeded(self, monkeypatch):
        calls = []
        real_detect = mix_renderer.detect_resonant_bands

        def _counting_detect(*args, **kwargs):
            calls.append(1)
            return real_detect(*args, **kwargs)

        monkeypatch.setattr(mix_renderer, "detect_resonant_bands", _counting_detect)

        profile = _profile("sub.wav", "sub_bass", frequency_profile=self._PURE_SUB_BASS_PROFILE)
        plan = generate_mix_plan([profile], genre="edm", target_lufs=-9.0)
        plan.bus.limiter_ceiling_db = -1.0
        stem_dicts = [{"name": "sub.wav", "samples": _clean_stem(50.0, seed=4), "sample_rate": SR}]

        mix_and_render_stems(stem_dicts, plan)

        # Only the master-bus pass (stage 8E, unconditional) should have run --
        # the per-stem pass (stage 1B) must have been skipped for this stem.
        assert len(calls) == 1

    def test_render_still_calls_the_detector_for_a_stem_marked_needed(self, monkeypatch):
        calls = []
        real_detect = mix_renderer.detect_resonant_bands

        def _counting_detect(*args, **kwargs):
            calls.append(1)
            return real_detect(*args, **kwargs)

        monkeypatch.setattr(mix_renderer, "detect_resonant_bands", _counting_detect)

        profile = _profile("guitar.wav", "guitar", frequency_profile=self._FULL_SPECTRUM_PROFILE)
        plan = generate_mix_plan([profile], genre="rock", target_lufs=-12.0)
        plan.bus.limiter_ceiling_db = -1.0
        stem_dicts = [{"name": "guitar.wav", "samples": _clean_stem(220.0, seed=5), "sample_rate": SR}]

        mix_and_render_stems(stem_dicts, plan)

        # Both the per-stem pass (stage 1B) and the master-bus pass (stage 8E) ran.
        assert len(calls) == 2


class TestNeedsMidCarveGate:
    """needs_mid_carve skips the vocal-lead mid-carve EQ cut entirely for a
    backing-role stem with negligible energy in the 400-2000Hz band the
    1.5kHz cut targets -- proves the actual call is skipped, not just that
    the output happens to be unaffected."""

    _PURE_SUB_BASS_PROFILE = {
        "sub": 0.85, "bass": 0.13, "low_mids": 0.01, "mids": 0.005,
        "presence": 0.003, "sibilance": 0.001, "air": 0.001,
    }
    _FULL_SPECTRUM_PROFILE = {
        "sub": 0.1, "bass": 0.1, "low_mids": 0.2, "mids": 0.3,
        "presence": 0.15, "sibilance": 0.1, "air": 0.05,
    }

    def _plan_with_lead_vocal(self, backing_profile: dict, *, genre: str = "pop") -> object:
        vocal = _profile("vocal.wav", "vocal", frequency_profile=self._FULL_SPECTRUM_PROFILE)
        backing = _profile("pad.wav", "pad", frequency_profile=backing_profile)
        plan = generate_mix_plan([vocal, backing], genre=genre, target_lufs=-12.0)
        plan.bus.limiter_ceiling_db = -1.0
        return plan

    def test_plan_marks_a_mids_light_backing_stem_as_not_needing_the_carve(self):
        plan = self._plan_with_lead_vocal(self._PURE_SUB_BASS_PROFILE)
        config = next(c for c in plan.stems if c.stem_name == "pad.wav")
        assert config.needs_mid_carve is False

    def test_plan_marks_a_full_spectrum_backing_stem_as_needing_the_carve(self):
        plan = self._plan_with_lead_vocal(self._FULL_SPECTRUM_PROFILE)
        config = next(c for c in plan.stems if c.stem_name == "pad.wav")
        assert config.needs_mid_carve is True

    def test_render_skips_the_carve_call_for_a_backing_stem_marked_unneeded(self, monkeypatch):
        calls = []
        real_carve = mix_renderer._apply_vocal_lead_mid_carve

        def _counting_carve(*args, **kwargs):
            calls.append(1)
            return real_carve(*args, **kwargs)

        monkeypatch.setattr(mix_renderer, "_apply_vocal_lead_mid_carve", _counting_carve)

        plan = self._plan_with_lead_vocal(self._PURE_SUB_BASS_PROFILE)
        stem_dicts = [
            {"name": "vocal.wav", "samples": _clean_stem(220.0, seed=6), "sample_rate": SR},
            {"name": "pad.wav", "samples": _clean_stem(60.0, seed=7), "sample_rate": SR},
        ]

        mix_and_render_stems(stem_dicts, plan)

        assert calls == []

    def test_render_still_calls_the_carve_for_a_backing_stem_marked_needed(self, monkeypatch):
        calls = []
        real_carve = mix_renderer._apply_vocal_lead_mid_carve

        def _counting_carve(*args, **kwargs):
            calls.append(1)
            return real_carve(*args, **kwargs)

        monkeypatch.setattr(mix_renderer, "_apply_vocal_lead_mid_carve", _counting_carve)

        plan = self._plan_with_lead_vocal(self._FULL_SPECTRUM_PROFILE)
        stem_dicts = [
            {"name": "vocal.wav", "samples": _clean_stem(220.0, seed=6), "sample_rate": SR},
            {"name": "pad.wav", "samples": _clean_stem(600.0, seed=7), "sample_rate": SR},
        ]

        mix_and_render_stems(stem_dicts, plan)

        assert len(calls) == 1
