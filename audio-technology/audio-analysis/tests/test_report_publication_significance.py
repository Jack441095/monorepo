"""Saved narrative copies cannot bypass optional-source qualification."""

from copy import deepcopy
import json

import pytest

from audio_analysis.integration.handoff import kenn_handoff, project_report_publication
from audio_analysis.integration.report_rendering import report_html
from audio_analysis.integration.session_report import build_session_report


CLAIM = "Bass and Kick both carry substantial low-end energy; try low-end EQ carving or sidechain ducking."


def _preview():
    return {"name": "Bass", "low_end_share": 0.0, "activity": {
        "schema": "kenn.low_end_stem.activity.v1", "active_floor_dbfs": -60.0,
        "source_rms_dbfs": -18.0, "window_rms_dbfs": -20.0,
        "sample_rate": 44100.0, "analysis_sample_count": 8192,
        "frame_size_samples": 4096, "window_start_sample": 2048,
    }}


def _report():
    return {"title": "Synthetic saved report", "metrics": {"rms_dbfs": -20.0, "low_end_share": 0.23},
            "stem_solo": {"low_end_summary": {"ranked": [_preview()], "overlap_warning": None}},
            "summary": CLAIM, "action_plan": [{"focus": "Low end", "action": CLAIM}],
            "mix_review_critique": {"text": CLAIM}, "mix_critique": {"text": CLAIM},
            "prose_summary": {"text": CLAIM}, "session_report": {"fix_first": CLAIM, "kenn_memory_lines": [CLAIM]},
            "kenn_handoff": {"context_lines": [CLAIM]}}


@pytest.mark.parametrize("publish", [report_html, build_session_report, kenn_handoff])
def test_every_publication_entry_rebuilds_cached_repairs_even_with_valid_preview(publish):
    # A proof of activity never validates the historical masking/EQ recommendation.
    report = _report()
    original = deepcopy(report)
    output = str(publish(report))
    assert "both carry substantial low-end" not in output
    assert "sidechain ducking" not in output
    assert "Bass" in output or publish is build_session_report
    assert report == original


def test_projection_is_stable_and_preserves_independent_sections():
    report = _report()
    report["stem_masking"] = {}
    report["comparison"] = {"rms_delta_db": 2.5}
    report["transient_preservation"] = {
        "preservation_score": 0.0, "profile": "Smeared", "matched_event_count": 3,
        "activity": {"schema": "kenn.transient_preservation.activity.v1", "pre_rms_dbfs": -18.0, "post_rms_dbfs": -20.0},
    }
    projected = project_report_publication(report)
    assert projected == project_report_publication(projected)
    assert projected["metrics"] == report["metrics"]
    assert projected["comparison"] == report["comparison"]
    assert projected["stem_masking"] == {}
    evidence = kenn_handoff(projected)["analysis_evidence"]
    assert evidence["transient_preservation"]["score"] == 0.0
    assert evidence["low_end_stems"][0]["name"] == "Bass"
    assert evidence["low_end_stems"][0]["low_end_share"] == 0.0


@pytest.mark.parametrize("nested", [False, True])
def test_quiet_transient_comparison_cannot_survive_in_any_report_container(nested):
    report = {"metrics": {"rms_dbfs": -20.0}, "summary": "Measured attack smearing: reduce limiting."}
    container = report["metrics"] if nested else report
    container["transient_preservation"] = {"preservation_score": 0.2, "profile": "Smeared", "matched_event_count": 3,
        "activity": {"schema": "kenn.transient_preservation.activity.v1", "pre_rms_dbfs": -100.0, "post_rms_dbfs": -100.0}}
    projected = project_report_publication(report)
    assert projected["transient_preservation"] == {}
    assert "Measured attack smearing" not in json.dumps(projected)
    assert kenn_handoff(projected)["analysis_evidence"]["transient_preservation"] == {}


def test_reports_without_optional_comparisons_keep_independent_narrative():
    report = {"summary": "Whole-mix crest factor is high.", "metrics": {"crest_factor_db": 18.0},
              "action_plan": [{"focus": "Dynamics", "action": "Compare matched-loudness exports."}]}
    assert project_report_publication(report) == report


def test_valid_nested_summary_cannot_override_a_failed_canonical_comparison():
    report = {"metrics": {"rms_dbfs": -20.0, "transient_preservation": {
        "preservation_score": 0.9, "profile": "Preserved", "matched_event_count": 3,
        "activity": {"schema": "kenn.transient_preservation.activity.v1", "pre_rms_dbfs": -18.0, "post_rms_dbfs": -20.0},
    }}, "transient_preservation": {}, "summary": "Transient preservation proves these attacks are intact."}
    projected = project_report_publication(report)
    assert projected["transient_preservation"] == {}
    assert "attacks are intact" not in str(projected)
    assert kenn_handoff(projected)["analysis_evidence"]["transient_preservation"] == {}
