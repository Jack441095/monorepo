"""Tests for the revision narrative module."""

from __future__ import annotations

from audio_analysis.mix_review.revision_narrative import (
    build_revision_narrative,
    version_diff,
    format_narrative_for_agent,
)


def _make_report(
    *,
    score: int = 75,
    crest: float = 8.2,
    rms: float = -18.0,
    width: float = 0.70,
    correlation: float = 0.85,
    peak: float = -2.5,
    flags: list[dict] | None = None,
    version_label: str = "v1",
    title: str = "Test Track",
) -> dict:
    metrics = {
        "technical_score": score,
        "crest_factor_db": crest,
        "rms_dbfs_estimate": rms,
        "stereo_width_ratio": width,
        "stereo_correlation": correlation,
        "peak_dbfs": peak,
    }
    report: dict = {
        "title": title,
        "version_label": version_label,
        "metrics": metrics,
        "flags": flags or [],
    }
    return report


def test_build_revision_narrative_returns_initial_for_no_previous() -> None:
    current = _make_report(score=75)
    narrative = build_revision_narrative(current, None)

    assert narrative["verdict"] == "initial"
    assert "no previous version" in narrative["narrative"].lower()
    assert narrative["deltas"] == {}
    assert narrative["cleared"] == []
    assert narrative["new_flags"] == []


def test_build_revision_narrative_improved_score() -> None:
    previous = _make_report(score=70, version_label="v1")
    current = _make_report(score=84, version_label="v2")

    narrative = build_revision_narrative(current, previous)

    assert narrative["score_delta"] == 14
    assert narrative["current_score"] == 84
    assert "improved" in narrative["narrative"]
    assert "14" in narrative["narrative"]


def test_build_revision_narrative_dropped_score() -> None:
    previous = _make_report(score=85, version_label="v1")
    current = _make_report(score=72, version_label="v2")

    narrative = build_revision_narrative(current, previous)

    assert narrative["score_delta"] == -13
    assert "dropped" in narrative["narrative"]
    assert "13" in narrative["narrative"]


def test_build_revision_narrative_cleared_flags() -> None:
    previous = _make_report(
        score=70,
        version_label="v1",
        flags=[
            {"label": "Low headroom", "severity": "high"},
            {"label": "Low dynamics", "severity": "medium"},
        ],
    )
    current = _make_report(
        score=82,
        version_label="v2",
        flags=[
            {"label": "Low headroom", "severity": "high"},
        ],
    )

    narrative = build_revision_narrative(current, previous)

    assert "Low dynamics" in narrative["cleared"]
    assert "Low headroom" in narrative["unchanged_flags"]
    assert "Low headroom" not in narrative["cleared"]


def test_build_revision_narrative_new_flags() -> None:
    previous = _make_report(score=80, version_label="v1")
    current = _make_report(
        score=75,
        version_label="v2",
        flags=[
            {"label": "Heavy sub", "severity": "medium"},
            {"label": "Low-mid build-up", "severity": "medium"},
        ],
    )

    narrative = build_revision_narrative(current, previous)

    assert "Heavy sub" in narrative["new_flags"]
    assert "Low-mid build-up" in narrative["new_flags"]
    assert len(narrative["new_flags"]) == 2


def test_build_revision_narrative_metric_deltas() -> None:
    previous = _make_report(score=75, crest=8.0, rms=-18.0, version_label="v1")
    current = _make_report(score=79, crest=10.5, rms=-19.5, version_label="v2")

    narrative = build_revision_narrative(current, previous)

    assert "crest" in narrative["deltas"]
    assert round(narrative["deltas"]["crest"], 1) == 2.5
    assert "rms" in narrative["deltas"]
    assert round(narrative["deltas"]["rms"], 1) == -1.5


def test_build_revision_narrative_action_summary_improved() -> None:
    previous = _make_report(
        score=65,
        version_label="v1",
        flags=[{"label": "Low headroom", "severity": "high"}],
    )
    current = _make_report(score=90, version_label="v2")

    narrative = build_revision_narrative(current, previous)

    assert narrative["cleared"] == ["Low headroom"]
    assert narrative["new_flags"] == []
    assert narrative["action_summary"] != ""


def test_build_revision_narrative_action_summary_new_flags() -> None:
    previous = _make_report(score=85, version_label="v1")
    current = _make_report(
        score=80,
        version_label="v2",
        flags=[{"label": "Heavy sub", "severity": "medium"}],
    )

    narrative = build_revision_narrative(current, previous)

    assert "Heavy sub" in narrative["action_summary"]
    assert "Heavy sub" in narrative["new_flags"]


def test_narrative_line_single_line_format() -> None:
    previous = _make_report(score=70, version_label="v1")
    current = _make_report(score=85, version_label="v2")

    narrative = build_revision_narrative(current, previous)

    assert isinstance(narrative["narrative_line"], str)
    assert len(narrative["narrative_line"]) > 0
    assert "+15" in narrative["narrative_line"] or "15" in narrative["narrative_line"]


def test_format_narrative_for_agent_includes_action() -> None:
    previous = _make_report(score=70, version_label="v1")
    current = _make_report(score=85, version_label="v2")

    narrative = build_revision_narrative(current, previous)
    formatted = format_narrative_for_agent(narrative)

    assert "Next:" in formatted
    assert "Next:" in formatted


def test_version_diff_returns_initial_for_no_previous() -> None:
    current = _make_report(score=75)
    result = version_diff(current, None)

    assert result["ok"] is True
    assert result["version_label_a"] == "initial"
    assert "no previous version" in result["narrative"]["narrative"].lower()


def test_version_diff_includes_labels() -> None:
    previous = _make_report(score=70, version_label="v1")
    current = _make_report(score=85, version_label="v2")

    result = version_diff(current, previous)

    assert result["ok"] is True
    assert result["version_label_a"] == "v1"
    assert result["version_label_b"] == "v2"
    assert result["score_delta"] == 15


def test_build_revision_narrative_uses_version_comparison_when_provided() -> None:
    current = _make_report(score=75, version_label="v2")
    previous = _make_report(score=70, version_label="v1")

    version_comparison = {
        "rms_delta_db": -2.5,
        "crest_delta_db": 3.0,
        "stereo_width_delta": 0.12,
        "correlation_delta": -0.05,
    }

    narrative = build_revision_narrative(
        current,
        previous,
        version_comparison=version_comparison,
    )

    assert narrative["deltas"]["rms"] == -2.5
    assert narrative["deltas"]["crest"] == 3.0
    assert narrative["deltas"]["width"] == 0.12


def test_build_revision_narrative_handles_identical_reports() -> None:
    report = _make_report(score=80, version_label="v1")
    narrative = build_revision_narrative(report, report)

    assert narrative["score_delta"] == 0
    assert narrative["cleared"] == []
    assert narrative["new_flags"] == []
