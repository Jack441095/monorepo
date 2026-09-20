"""Tests for dsp_engine/dsp_necessity.py -- the per-stem "would this stage
actually do anything" gate that lets the render loop skip DSP a stem's own
measured content shows would be a no-op.

Covers a real bug caught and fixed while writing this: needs_highpass must
default to "keep the filter" (not "skip it") for a cutoff frequency the
7-band profile can't resolve down to (e.g. a 25Hz kick highpass -- no band
boundary sits at 25Hz, the "sub" band spans 20-60Hz), otherwise it would
have silently disabled every low-cutoff highpass rule in mix_rules.py
regardless of actual content.
"""

from __future__ import annotations

from audio_analysis.dsp_engine.dsp_necessity import (
    needs_deesser,
    needs_highpass,
    needs_mid_carve,
    needs_resonance_scan,
)

_FULL_SPECTRUM = {
    "sub": 0.1, "bass": 0.1, "low_mids": 0.2, "mids": 0.3,
    "presence": 0.15, "sibilance": 0.1, "air": 0.05,
}
_PURE_SUB_BASS = {
    "sub": 0.85, "bass": 0.13, "low_mids": 0.01, "mids": 0.005,
    "presence": 0.003, "sibilance": 0.001, "air": 0.001,
}


class TestNeedsHighpass:
    def test_missing_or_empty_profile_defaults_to_needed(self):
        assert needs_highpass(None, 90.0) is True
        assert needs_highpass({}, 90.0) is True

    def test_low_cutoff_the_7band_profile_cannot_resolve_defaults_to_needed(self):
        """25Hz (kick's real highpass_hz in mix_rules.py) falls inside the
        20-60Hz 'sub' band itself -- there's no way to tell what's below
        25Hz specifically, so this must stay True regardless of content."""
        assert needs_highpass(_FULL_SPECTRUM, 25.0) is True
        assert needs_highpass(_PURE_SUB_BASS, 25.0) is True

    def test_skips_when_energy_below_cutoff_is_already_negligible(self):
        clean_low_end = {
            "sub": 0.0, "bass": 0.005, "low_mids": 0.3, "mids": 0.4,
            "presence": 0.2, "sibilance": 0.05, "air": 0.045,
        }
        assert needs_highpass(clean_low_end, 90.0) is False

    def test_stays_needed_when_real_energy_exists_below_cutoff(self):
        assert needs_highpass(_FULL_SPECTRUM, 90.0) is True
        assert needs_highpass(_PURE_SUB_BASS, 200.0) is True

    def test_at_or_below_20hz_always_needed(self):
        assert needs_highpass(_PURE_SUB_BASS, 20.0) is True


class TestNeedsResonanceScan:
    def test_missing_or_empty_profile_defaults_to_needed(self):
        assert needs_resonance_scan(None) is True
        assert needs_resonance_scan({}) is True

    def test_pure_sub_bass_stem_skips_the_scan(self):
        assert needs_resonance_scan(_PURE_SUB_BASS) is False

    def test_full_spectrum_stem_needs_the_scan(self):
        assert needs_resonance_scan(_FULL_SPECTRUM) is True


class TestNeedsDeesser:
    def test_never_needed_on_a_non_vocal_role_regardless_of_sibilance_energy(self):
        loud_sibilance = {"sibilance": 0.5}
        assert needs_deesser(loud_sibilance, "bass") is False
        assert needs_deesser(loud_sibilance, "hihat") is False

    def test_vocal_with_elevated_sibilance_needs_it(self):
        assert needs_deesser({"sibilance": 0.15}, "vocal") is True
        assert needs_deesser({"sibilance": 0.15}, "backing_vocal") is True

    def test_vocal_with_low_sibilance_does_not_need_it(self):
        assert needs_deesser({"sibilance": 0.02}, "vocal") is False

    def test_missing_profile_defaults_to_not_needed(self):
        assert needs_deesser(None, "vocal") is False
        assert needs_deesser({}, "vocal") is False


class TestNeedsMidCarve:
    def test_missing_or_empty_profile_defaults_to_needed(self):
        assert needs_mid_carve(None) is True
        assert needs_mid_carve({}) is True

    def test_pure_sub_bass_stem_skips_the_carve(self):
        """400-2000Hz ("mids") is where the 1.5kHz mid-carve cut lands --
        a pure sub-bass/pad stem has nothing there to carve."""
        assert needs_mid_carve(_PURE_SUB_BASS) is False

    def test_full_spectrum_stem_needs_the_carve(self):
        assert needs_mid_carve(_FULL_SPECTRUM) is True

    def test_negligible_mids_energy_skips_regardless_of_other_bands(self):
        strong_everywhere_except_mids = {
            "sub": 0.3, "bass": 0.3, "low_mids": 0.2, "mids": 0.01,
            "presence": 0.1, "sibilance": 0.05, "air": 0.04,
        }
        assert needs_mid_carve(strong_everywhere_except_mids) is False
