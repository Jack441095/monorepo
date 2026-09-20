from __future__ import annotations

from kenn.project_analysis import (
    Recommendation,
    analyze_project_doctor,
    normalize_session,
    prioritize_recommendations,
    recommendations_from_mix_review,
    summarize_recommendations,
)


def _rec(title: str, category: str, severity: str, confidence: float) -> Recommendation:
    return Recommendation(
        title=title,
        category=category,
        severity=severity,
        confidence=confidence,
        description=f"{title} description",
        reason="measured evidence",
        suggestedAction=f"Fix {title}",
    )


def test_prioritize_ranks_critical_before_warning_before_info() -> None:
    ranked = prioritize_recommendations([
        _rec("Low headroom", "mix_health", "info", 0.9),
        _rec("Clipping", "mix_health", "critical", 0.6),
        _rec("Channel imbalance", "mix_health", "warning", 0.8),
    ])
    assert [item.title for item in ranked] == ["Clipping", "Channel imbalance", "Low headroom"]


def test_prioritize_breaks_ties_within_severity_by_confidence() -> None:
    ranked = prioritize_recommendations([
        _rec("DC offset", "mix_health", "warning", 0.5),
        _rec("Phase issue", "mix_health", "warning", 0.95),
    ])
    assert [item.title for item in ranked] == ["Phase issue", "DC offset"]


def test_prioritize_merges_exact_duplicate_findings() -> None:
    ranked = prioritize_recommendations([
        _rec("Clipping", "mix_health", "critical", 0.6),
        _rec("Clipping", "mix_health", "critical", 0.6),
    ])
    assert len(ranked) == 1


def test_prioritize_without_genre_adds_no_reference_note() -> None:
    ranked = prioritize_recommendations([_rec("Clipping", "mix_health", "critical", 0.6)])
    assert all(item.category != "genre_reference" for item in ranked)


def test_prioritize_with_explicit_genre_adds_one_advisory_note_never_a_verdict() -> None:
    ranked = prioritize_recommendations(
        [_rec("Clipping", "mix_health", "critical", 0.6)], genre="hip_hop",
    )
    genre_notes = [item for item in ranked if item.category == "genre_reference"]
    assert len(genre_notes) == 1
    note = genre_notes[0]
    assert "Hip-Hop" in note.description
    assert note.requiresConfirmation is False
    assert "not inferred from the audio" in note.reason
    # The genre note never changes or removes the measured finding above it.
    assert ranked[0].title == "Clipping"
    assert ranked[0].severity == "critical"


def test_prioritize_with_unknown_genre_is_a_no_op() -> None:
    ranked = prioritize_recommendations(
        [_rec("Clipping", "mix_health", "critical", 0.6)], genre="not_a_real_genre",
    )
    assert len(ranked) == 1


def test_summarize_groups_by_severity_with_actions() -> None:
    text = summarize_recommendations([
        _rec("Clipping", "mix_health", "critical", 0.6),
        _rec("Channel imbalance", "mix_health", "warning", 0.8),
    ])
    assert "Fix first:" in text
    assert "Clipping: Fix Clipping" in text
    assert "Worth addressing" in text
    assert "Channel imbalance: Fix Channel imbalance" in text


def test_summarize_empty_list_says_no_issues() -> None:
    assert summarize_recommendations([]) == "No measured issues were found in this review."


def test_summarize_appends_genre_note_without_treating_it_as_an_issue() -> None:
    ranked = prioritize_recommendations(
        [_rec("Clipping", "mix_health", "critical", 0.6)], genre="rock_metal",
    )
    text = summarize_recommendations(ranked)
    assert "Fix first:" in text
    assert "Rock / Metal" in text


def test_reference_ltas_recommendation_is_specific_but_not_an_auto_eq_instruction() -> None:
    recommendations = recommendations_from_mix_review({
        "reference_comparison": {
            "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
        },
    })

    ltas = next(item for item in recommendations if item.title == "Check around 300 Hz against reference")
    assert "5.0 dB more prominent" in ltas.description
    assert "normalised around 1 kHz" in ltas.reason
    assert "not a universal pink-noise" in ltas.reason
    assert "bypass" in ltas.suggestedAction
    assert ltas.canAutoFix is False
    assert ltas.requiresConfirmation is True


def test_pink_noise_recommendation_is_bounded_and_not_an_auto_eq_instruction() -> None:
    recommendations = recommendations_from_mix_review({
        "reference_comparison": {
            "pink_noise_reference": {
                "curve": "-3 dB per octave pink-noise-style spectral baseline",
                "largest_deviation": {"center_hz": 296.0, "deviation_db": 5.1},
            },
        },
    })

    pink = next(item for item in recommendations if item.category == "reference" and "pink-noise" in item.title)
    assert "5.1 dB above" in pink.description
    assert "296 Hz" in pink.description
    assert "not a universal target" in pink.reason
    assert "automatic master EQ" in pink.suggestedAction
    assert pink.canAutoFix is False
    assert pink.requiresConfirmation is True


def test_project_health_reports_only_bounded_instantaneous_meters() -> None:
    project = normalize_session({
        "status": "connected",
        "tracks": [
            {"index": 2, "name": "Lead", "output_meter_level": 0.99, "output_meter_right": 0.94},
            {"index": 3, "name": "Invalid", "output_meter_level": 1.5},
        ],
    })

    findings = analyze_project_doctor(project)

    assert "instantaneous_track_meters" in project.available_capabilities
    assert len(findings) == 1
    assert findings[0].track_indices == (2,)
    assert "instantaneous post-fader" in findings[0].reason
