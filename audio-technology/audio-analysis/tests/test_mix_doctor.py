"""Tests for the Mix Doctor shareable-report renderer (plan.md §14.1).

The renderer is a pure function: a review dict (the shape the Mix Review engine
already produces) -> a self-contained HTML string. These tests use a
representative synthetic review as *input fixture data* — they assert the
renderer's behaviour, not any real-world audio result.

Coverage:
- headline score/rating derivation and one-liner,
- priority actions render with their real field names,
- objective metric tiles appear,
- HTML escaping (no injection from report text),
- graceful degradation on empty / partial reports,
- the call-to-action is always present.
"""

from __future__ import annotations

from audio_analysis.mix_review import mix_doctor


def _sample_review() -> dict:
    return {
        "title": "Midnight Drive (v3)",
        "rating": "Good",
        "technical_score": 78,
        "summary": "Solid low end, but the vocal is masked and peaks are hot.",
        "metrics": {
            "integrated_lufs": -9.4,
            "true_peak_dbfs": -0.2,
            "crest_factor_db": 8.1,
            "stereo_correlation": 0.42,
            "loudness_range_lu": 6.3,
            "mix_goal": {"key": "pop_vocal", "name": "Pop Vocal"},
        },
        "flags": [
            {"severity": "high", "label": "Low headroom", "detail": "Peak level is above -1.0 dBFS."},
            {"severity": "medium", "label": "Vocal masking", "detail": "2-4 kHz build-up competes with the vocal."},
        ],
        "action_plan": [
            {
                "rank": 0,
                "priority": "high",
                "confidence": "high",
                "focus": "Headroom",
                "action": "Pull the master fader down ~2 dB and re-check the limiter ceiling at -1 dBTP.",
                "reason": "True peaks are near full scale, risking inter-sample clipping on lossy encoders.",
            },
            {
                "rank": 1,
                "priority": "medium",
                "confidence": "medium",
                "focus": "Vocal clarity",
                "action": "Add a gentle 2.5 kHz dip on the busiest synth bus to unmask the lead vocal.",
                "reason": "Energy in 2-4 kHz overlaps the vocal presence band.",
            },
        ],
        "prose_summary": {"mode": "deterministic", "available": True, "text": "A confident, loud mix that needs headroom and a touch of vocal separation."},
    }


def test_renders_headline_score_and_rating():
    html = mix_doctor.render_report_html(_sample_review())
    assert "Midnight Drive (v3)" in html
    assert "78" in html
    assert "Good" in html
    assert "Pop Vocal" in html  # goal chip


def test_priority_actions_render_with_real_fields():
    html = mix_doctor.render_report_html(_sample_review())
    assert "Headroom" in html
    assert "Pull the master fader down" in html
    assert "Vocal clarity" in html
    # priority labels are humanised
    assert "Fix first" in html
    assert "Worth doing" in html


def test_metric_tiles_present():
    html = mix_doctor.render_report_html(_sample_review())
    assert "-9.4 LUFS" in html
    assert "8.1 dB" in html  # crest factor
    assert "+0.42" in html  # stereo correlation, signed


def test_cta_always_present():
    html = mix_doctor.render_report_html(_sample_review(), cta_label="Book a mix", cta_url="https://x.test/enquire")
    assert "Book a mix" in html
    assert "https://x.test/enquire" in html


def test_html_is_escaped_no_injection():
    evil = _sample_review()
    evil["title"] = "<script>alert(1)</script>"
    evil["action_plan"][0]["action"] = "Do <b>this</b> & that"
    html = mix_doctor.render_report_html(evil)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp; that" in html


def test_graceful_on_empty_review():
    # Must not raise and must still produce a valid page with a CTA.
    html = mix_doctor.render_report_html({})
    assert "<!doctype html>" in html.lower()
    assert "Your mix" in html
    assert "cta" in html


def test_graceful_on_partial_review():
    html = mix_doctor.render_report_html({"title": "Half a report", "flags": [{"severity": "high", "label": "Clip"}]})
    assert "Half a report" in html
    # No action_plan -> the "nice work / polish" empty state
    assert "polish" in html.lower()


def _review_with_reference() -> dict:
    r = _sample_review()
    r["metrics"]["bands"] = {"sub": 0.10, "bass": 0.22, "low_mids": 0.18, "mids": 0.24,
                             "presence": 0.14, "sibilance": 0.06, "air": 0.06}
    r["reference"] = {"name": "Commercial Pop Ref", "metrics": {"bands": {
        "sub": 0.12, "bass": 0.20, "low_mids": 0.16, "mids": 0.22,
        "presence": 0.16, "sibilance": 0.07, "air": 0.07}}}
    r["comparison_advice"] = ["Your low-mids sit a touch high vs the reference."]
    return r


def test_tonal_balance_chart_renders_svg():
    html = mix_doctor.render_report_html(_review_with_reference())
    assert "<svg" in html
    assert "Your mix" in html and "Reference" in html
    assert "Commercial Pop Ref" in html
    # band labels present
    assert "Presence" in html and "Sub" in html


def test_no_chart_without_reference_bands():
    # Sample review has no reference -> no chart, no crash.
    html = mix_doctor.render_report_html(_sample_review())
    assert "<svg" not in html


def test_chart_omitted_when_too_few_bands():
    r = _sample_review()
    r["metrics"]["bands"] = {"sub": 0.5, "bass": 0.5}
    r["reference"] = {"name": "Ref", "metrics": {"bands": {"sub": 0.5, "bass": 0.5}}}
    html = mix_doctor.render_report_html(r)
    assert "<svg" not in html  # need >=3 shared bands


def test_reference_moves_render_from_comparison_eq_bands():
    r = _review_with_reference()
    r["comparison"] = {
        "eq_bands": [
            {"freq": 80.0, "gain": 2.4, "q": 0.7},
            {"freq": 3000.0, "gain": -1.8, "q": 1.0},
            {"freq": 12000.0, "gain": 0.2, "q": 0.7},  # below 0.5 dB -> omitted
        ],
        "tonal_balance_score": 0.8, "lufs_delta_db": -1.0,
        "stereo_width_delta": 0.0, "correlation_delta": 0.0,
    }
    html = mix_doctor.render_report_html(r)
    assert "Suggested moves to match the reference" in html
    assert "Boost 2.4 dB around 80 Hz" in html
    assert "Reduce 1.8 dB around 3000 Hz" in html
    assert "12000 Hz" not in html  # negligible move omitted


def test_match_score_badge_renders():
    r = _review_with_reference()
    r["comparison"] = {"tonal_balance_score": 0.9, "lufs_delta_db": 0.0,
                       "stereo_width_delta": 0.0, "correlation_delta": 0.0, "eq_bands": []}
    html = mix_doctor.render_report_html(r)
    assert "/100 match" in html


def test_headline_derives_from_flags_when_score_absent():
    review = _sample_review()
    review.pop("technical_score", None)
    review.pop("rating", None)
    head = mix_doctor.report_headline(review)
    assert isinstance(head["score"], int)
    assert head["rating"]
    assert head["title"] == "Midnight Drive (v3)"
