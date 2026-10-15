"""Critique consumes source-qualified comparisons without inferring audible damage."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from audio_analysis.mix_review.mix_review_critique import (
    critique_metrics_payload, deterministic_critique, generate_critique,
)
from audio_analysis.mix_review.mix_doctor import render_report_html


def _comparison():
    return {"preservation_score": 0.0, "profile": "Smeared", "matched_event_count": 3,
            "activity": {"schema": "kenn.transient_preservation.activity.v1",
                         "pre_rms_dbfs": -18.0, "post_rms_dbfs": -20.0}}


@pytest.mark.parametrize("level", [-100.0, -60.0, float("nan"), float("inf"), True, None])
def test_inactive_or_invalid_original_render_never_enters_critique(level):
    # Peak normalization previously made silent comparisons look like measured damage.
    comparison = _comparison()
    comparison["activity"]["pre_rms_dbfs"] = level
    payload = critique_metrics_payload({"transient_preservation": comparison})
    assert payload["transient_preservation"] == {}
    for candidate in (payload, {"transient_preservation": comparison}):
        text = deterministic_critique(candidate)
        assert "Transient preservation withheld" in text
        assert "score 0.00" not in text
        assert "attack smearing is measurable" not in text


def test_qualified_zero_survives_without_audible_damage_or_repair_claim():
    report = {"metrics": {"rms_dbfs": -20.0}, "transient_preservation": _comparison()}
    original = deepcopy(report)
    payload = critique_metrics_payload(report)
    assert payload["transient_preservation"]["preservation_score"] == 0.0
    text = deterministic_critique(payload)
    assert "score 0.00/1.0" in text
    assert "does not establish audible damage" in text
    assert "reduce limiting" not in text
    assert report == original


def test_canonical_abstention_wins_over_nested_cached_comparison():
    payload = critique_metrics_payload({"transient_preservation": {},
                                       "metrics": {"transient_preservation": _comparison()}})
    assert payload["transient_preservation"] == {}
    assert "withheld" in deterministic_critique(payload)


def test_missing_optional_comparison_does_not_invent_a_failure():
    payload = critique_metrics_payload({"metrics": {"rms_dbfs": -20.0}})
    assert payload["transient_preservation"] is None
    assert "Transient preservation withheld" not in deterministic_critique(payload)


def test_llm_prompt_receives_abstention_instead_of_cached_transient_claim(monkeypatch):
    monkeypatch.setenv("MIX_REVIEW_CRITIQUE_ENABLED", "1")
    captured = []

    class Provider:
        def generate(self, messages, timeout):
            captured.extend(messages)
            return SimpleNamespace(content="")

    comparison = _comparison()
    comparison.pop("activity")
    generate_critique({"transient_preservation": comparison,
                       "flags": [{"label": "Smeared cached attacks"}]}, provider=Provider())
    assert '"transient_preservation": {}' in captured[1]["content"]
    assert "Smeared" not in captured[1]["content"]


def test_signed_report_renderer_rebuilds_legacy_optional_repair_prose():
    report = {"metrics": {"rms_dbfs": -20.0}, "transient_preservation": {},
              "summary": "Measured attack smearing: reduce limiting.",
              "action_plan": [{"action": "Measured attack smearing: reduce limiting."}]}
    original = deepcopy(report)
    html = render_report_html(report)
    assert "Measured attack smearing" not in html
    assert report == original
