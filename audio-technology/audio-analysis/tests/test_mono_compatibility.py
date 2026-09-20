"""Evidence and fail-closed tests for mono compatibility contract v1."""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.mixdown.mono_compatibility import (
    MONO_COMPATIBILITY_SCHEMA,
    analyze_mono_compatibility,
)


SAMPLE_RATE = 8_000


def _stem(name: str, left: np.ndarray, right: np.ndarray) -> dict:
    return {
        "name": name,
        "samples": (0.5 * (left + right)).tolist(),
        "left_samples": left.tolist(),
        "right_samples": right.tolist(),
        "stereo_preserved": True,
        "sample_rate": SAMPLE_RATE,
    }


def _arrangement(name: str, duration: float = 1.0) -> dict:
    return {
        "schema": "audio-too.arrangement.v1",
        "sections": [{
            "section_id": "section-001",
            "start_seconds": 0.0,
            "end_seconds": duration,
            "active_stems": [name],
        }],
    }


def test_identical_channels_pass_without_false_width_warning() -> None:
    tone = 0.4 * np.sin(2.0 * np.pi * 220.0 * np.arange(SAMPLE_RATE) / SAMPLE_RATE)

    report = analyze_mono_compatibility(
        [_stem("Keys.wav", tone, tone)], _arrangement("Keys.wav")
    )
    section = report.stems[0].sections[0]

    assert report.schema == MONO_COMPATIBILITY_SCHEMA
    assert report.status == "pass"
    assert report.applies_automatically is False
    assert section.correlation == pytest.approx(1.0)
    assert section.fold_down_change_db == pytest.approx(0.0)
    assert section.side_energy_ratio == pytest.approx(0.0)
    assert section.low_frequency_side_ratio == pytest.approx(0.0)
    assert section.low_frequency_energy_ratio < 0.01


def test_antiphase_channels_are_critical_even_when_mid_proxy_is_silent() -> None:
    tone = 0.4 * np.sin(2.0 * np.pi * 220.0 * np.arange(SAMPLE_RATE) / SAMPLE_RATE)

    report = analyze_mono_compatibility(
        [_stem("Wide.wav", tone, -tone)], _arrangement("Wide.wav")
    )
    section = report.stems[0].sections[0]

    assert report.status == "critical"
    assert report.critical_stems == 1
    assert section.correlation == pytest.approx(-1.0)
    assert section.fold_down_change_db < -100.0
    assert section.side_energy_ratio == pytest.approx(1.0)
    assert "severe_fold_down_cancellation" in section.reasons
    assert "strong_negative_channel_correlation" in section.reasons


def test_low_frequency_side_energy_is_flagged_more_strictly_than_high_width() -> None:
    time = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    low = np.sin(2.0 * np.pi * 60.0 * time)
    high_mid = 0.3 * np.sin(2.0 * np.pi * 1_000.0 * time)
    left = high_mid + low
    right = high_mid - low

    report = analyze_mono_compatibility(
        [_stem("Bass Synth.wav", left, right)], _arrangement("Bass Synth.wav")
    )
    section = report.stems[0].sections[0]

    assert section.low_frequency_side_ratio > 0.99
    assert section.low_frequency_energy_ratio > 0.9
    assert section.severity == "critical"
    assert "low_frequency_energy_is_predominantly_side" in section.reasons


def test_negligible_low_band_side_energy_does_not_create_a_width_warning() -> None:
    time = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    high = np.sin(2.0 * np.pi * 1_000.0 * time)
    tiny_low_side = 0.001 * np.sin(2.0 * np.pi * 60.0 * time)
    left = high + tiny_low_side
    right = high - tiny_low_side

    report = analyze_mono_compatibility(
        [_stem("Lead.wav", left, right)], _arrangement("Lead.wav")
    )
    section = report.stems[0].sections[0]

    assert section.low_frequency_side_ratio > 0.99
    assert section.low_frequency_energy_ratio < 0.001
    assert section.severity == "pass"
    assert section.reasons == []


def test_near_zero_channel_correlation_is_treated_as_width_not_phase_failure() -> None:
    time = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    left = np.sin(2.0 * np.pi * 700.0 * time)
    right = np.sin(2.0 * np.pi * 1_100.0 * time)

    report = analyze_mono_compatibility(
        [_stem("Texture.wav", left, right)], _arrangement("Texture.wav")
    )
    section = report.stems[0].sections[0]

    assert abs(section.correlation) < 0.01
    assert section.fold_down_change_db == pytest.approx(-3.01, abs=0.02)
    assert section.severity == "pass"
    assert "negative_channel_correlation" not in section.reasons


def test_summed_section_finds_cross_stem_collapse_and_attributes_contributors() -> None:
    """Two individually coherent stems can cancel destructively only after summing."""
    tone = 0.3 * np.sin(2.0 * np.pi * 220.0 * np.arange(SAMPLE_RATE) / SAMPLE_RATE)
    first = _stem("Layer A.wav", tone, 0.5 * tone)
    second = _stem("Layer B.wav", -0.5 * tone, -tone)
    arrangement = {
        "sections": [{
            "section_id": "section-001",
            "start_seconds": 0.0,
            "end_seconds": 1.0,
            "active_stems": ["Layer A.wav", "Layer B.wav"],
        }]
    }

    report = analyze_mono_compatibility([first, second], arrangement)
    summed = report.summed_sections[0]

    assert [stem.severity for stem in report.stems] == ["pass", "pass"]
    assert report.status == "critical"
    assert report.problematic_summed_sections == 1
    assert summed.correlation == pytest.approx(-1.0)
    assert summed.fold_down_change_db < -100.0
    assert [item.stem_name for item in summed.contributors] == [
        "Layer A.wav", "Layer B.wav"
    ]
    assert all(item.score > 0.0 for item in summed.contributors)
    assert all(item.fold_down_improvement_db > 90.0 for item in summed.contributors)


def test_summed_sections_preserve_arrangement_bounds_and_active_sources() -> None:
    tone = np.sin(2.0 * np.pi * 440.0 * np.arange(SAMPLE_RATE) / SAMPLE_RATE)
    arrangement = {
        "sections": [
            {"section_id": "one", "start_seconds": 0.0, "end_seconds": 0.5,
             "active_stems": ["Keys.wav"]},
            {"section_id": "two", "start_seconds": 0.5, "end_seconds": 1.0,
             "active_stems": ["Keys.wav", "Pad.wav"]},
        ]
    }

    report = analyze_mono_compatibility(
        [_stem("Keys.wav", tone, tone), _stem("Pad.wav", tone, tone)], arrangement
    )

    assert [section.section_id for section in report.summed_sections] == ["one", "two"]
    assert report.summed_sections[1].active_stems == ["Keys.wav", "Pad.wav"]
    assert report.summed_sections[1].start_seconds == pytest.approx(0.5)


def test_evidence_is_attributed_only_to_sections_where_stem_is_active() -> None:
    tone = np.ones(SAMPLE_RATE)
    arrangement = {
        "sections": [
            {"section_id": "active", "start_seconds": 0.0, "end_seconds": 0.5,
             "active_stems": ["Keys.wav"]},
            {"section_id": "inactive", "start_seconds": 0.5, "end_seconds": 1.0,
             "active_stems": []},
        ]
    }

    report = analyze_mono_compatibility(
        [_stem("Keys.wav", tone, tone)], arrangement
    )

    assert [section.section_id for section in report.stems[0].sections] == ["active"]


def test_mono_sources_are_recorded_as_not_applicable() -> None:
    stem = {"name": "Kick.wav", "samples": [0.5] * SAMPLE_RATE, "sample_rate": SAMPLE_RATE}

    report = analyze_mono_compatibility([stem], _arrangement("Kick.wav"))

    assert report.measured_stereo_stems == 0
    assert report.status == "pass"
    assert report.stems[0].measured is False
    assert report.stems[0].severity == "not_applicable"


@pytest.mark.parametrize(
    "stem, match",
    [
        ({"name": "Bad.wav", "sample_rate": SAMPLE_RATE, "stereo_preserved": True,
          "left_samples": [0.1], "right_samples": []}, "invalid or unaligned"),
        ({"name": "Bad.wav", "sample_rate": 0, "samples": []}, "positive sample rates"),
    ],
)
def test_invalid_prepared_audio_fails_closed(stem: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        analyze_mono_compatibility([stem], _arrangement("Bad.wav"))


def test_missing_arrangement_fails_closed() -> None:
    with pytest.raises(ValueError, match="Arrangement v1"):
        analyze_mono_compatibility(
            [{"name": "Kick.wav", "samples": [0.1], "sample_rate": SAMPLE_RATE}], {}
        )


def test_unknown_active_stem_in_arrangement_fails_closed() -> None:
    stem = {"name": "Kick.wav", "samples": [0.1] * SAMPLE_RATE, "sample_rate": SAMPLE_RATE}
    with pytest.raises(ValueError, match="unknown active stems"):
        analyze_mono_compatibility([stem], _arrangement("Missing.wav"))
