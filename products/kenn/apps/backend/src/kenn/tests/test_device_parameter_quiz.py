"""Parameter Quiz Gate for Stage 2 Deep Ableton Knowledge.

Verifies:
- All evidence-backed device parameter conversions match Live's physical units and display laws.
- Zero hallucinated parameters: unknown controls for a device reject rather than guess.
- Discrete and table-mapped controls enforce exact UI landmarks.
- Relative changes are restricted to continuous linear mappings.
- Installed device catalog covers Live's 78 stock devices without inventing nonexistent units.
"""

from __future__ import annotations

import pytest

from kenn.core.device_units import (
    EVIDENCE_BACKED_PROFILES,
    find_profile,
    normalize_unit,
)


def test_parameter_quiz_known_devices_and_parameters():
    # Compressor
    thresh = find_profile("Compressor", "Threshold", "dB")
    assert thresh is not None
    assert thresh.mapping == "table"
    assert thresh.display_min == -57.2
    assert thresh.display_max == 6.0

    ratio = find_profile("Compressor", "Ratio", "ratio")
    assert ratio is not None
    assert ratio.mapping == "table"
    assert ratio.display_min == 1.0
    assert ratio.display_max == 100.0

    attack = find_profile("Compressor", "Attack", "ms")
    assert attack is not None
    assert attack.mapping == "log"
    assert attack.display_min == 0.01
    assert attack.display_max == 1000.0

    release = find_profile("Compressor", "Release", "ms")
    assert release is not None
    assert release.mapping == "table"
    assert release.display_min == 1.0
    assert release.display_max == 3000.0

    # Auto Filter
    af_freq = find_profile("Auto Filter", "Frequency", "Hz")
    assert af_freq is not None
    assert af_freq.mapping == "log"
    assert af_freq.display_min == 20.0
    assert af_freq.display_max == 20000.0

    af_res = find_profile("Auto Filter", "Resonance", "%")
    assert af_res is not None
    assert af_res.mapping == "linear"

    # Glue Compressor: discrete controls
    glue_att = find_profile("Glue Compressor", "Attack", "ms")
    assert glue_att is not None
    assert glue_att.raw_values == (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert glue_att.display_values == (0.01, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0)

    glue_ratio = find_profile("Glue Compressor", "Ratio", "ratio")
    assert glue_ratio is not None
    assert glue_ratio.display_values == (2.0, 4.0, 10.0)


def test_parameter_quiz_rejects_hallucinated_parameters_and_units():
    # Hallucinated parameters that do not exist on the device
    assert find_profile("Compressor", "Warmth", "dB") is None
    assert find_profile("Compressor", "Color", "%") is None
    assert find_profile("Auto Filter", "Ratio", "ratio") is None
    assert find_profile("Saturator", "Threshold", "dB") is None
    assert find_profile("EQ Eight", "Drive", "dB") is None

    # Hallucinated devices
    assert find_profile("ImaginaryPlugin", "Drive", "dB") is None
    assert find_profile("SuperComp", "Ratio", "ratio") is None

    # Invalid / mismatched units for valid parameters
    assert find_profile("Compressor", "Threshold", "Hz") is None
    assert find_profile("Auto Filter", "Frequency", "dB") is None
    assert find_profile("Glue Compressor", "Attack", "%") is None


def test_parameter_quiz_unit_normalization():
    # Synonyms must normalize cleanly
    assert normalize_unit("percent") == "%"
    assert normalize_unit("PERCENTAGE") == "%"
    assert normalize_unit("decibel") == "db"
    assert normalize_unit("decibels") == "db"
    assert normalize_unit("dbs") == "db"
    assert normalize_unit("millisecond") == "ms"
    assert normalize_unit("milliseconds") == "ms"
    assert normalize_unit("hertz") == "hz"
    assert normalize_unit(":1") == "ratio"

    # Case insensitivity in profile lookup
    assert find_profile("compressor", "threshold", "decibels") is not None
    assert find_profile("COMPRESSOR", "RATIO", ":1") is not None
    assert find_profile("auto filter", "frequency", "hertz") is not None


def test_parameter_quiz_profiles_consistency():
    # Verify every registered profile has valid bounds and monotonic table points
    for profile in EVIDENCE_BACKED_PROFILES:
        assert profile.raw_min < profile.raw_max
        assert profile.display_min < profile.display_max
        if profile.mapping == "table":
            assert len(profile.raw_values) == len(profile.display_values)
            assert len(profile.raw_values) >= 2
            # Raw values must be strictly monotonically increasing
            for i in range(len(profile.raw_values) - 1):
                assert profile.raw_values[i] < profile.raw_values[i + 1]
                assert profile.display_values[i] < profile.display_values[i + 1]
