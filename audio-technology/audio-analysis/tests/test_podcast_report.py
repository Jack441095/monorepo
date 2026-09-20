"""Tests for the shareable podcast report renderer."""

from __future__ import annotations

from audio_analysis.podcast import analyze_podcast, render_podcast_report_html


def _report_with_issues() -> dict:
    return analyze_podcast({
        "integrated_lufs": -23.0,      # too quiet -> fail
        "true_peak_dbfs": -1.5,
        "peak_dbfs": -3.0,
        "loudness_range_lu": 6.0,
        "stereo_correlation": 0.95,
        "bands": {"sub": 0.12, "bass": 0.10, "low_mids": 0.22, "mids": 0.36,
                  "presence": 0.13, "sibilance": 0.05, "air": 0.02},  # rumble
    }, target="apple")


def test_renders_valid_self_contained_html():
    html = render_podcast_report_html(_report_with_issues(), title="Episode 12")
    assert "<!doctype html>" in html.lower()
    assert "Episode 12" in html
    assert "/100" in html
    # Self-contained: inline styles, no external script/stylesheet to fetch.
    assert "<style>" in html
    assert "<script" not in html
    assert 'rel="stylesheet"' not in html


def test_shows_target_and_fixes():
    html = render_podcast_report_html(_report_with_issues())
    assert "Apple Podcasts" in html
    assert "Normalise to -16 LUFS" in html
    assert "High-pass around 80 Hz" in html  # rumble fix surfaced


def test_html_escaped_title():
    html = render_podcast_report_html(analyze_podcast({}), title="<b>hi</b>")
    assert "<b>hi</b>" not in html
    assert "&lt;b&gt;hi" in html


def test_cta_present_and_customisable():
    html = render_podcast_report_html(analyze_podcast({}), cta_label="Book editing",
                                      cta_url="https://x.test/book")
    assert "Book editing" in html
    assert "https://x.test/book" in html


def test_empty_report_degrades():
    html = render_podcast_report_html({})
    assert "<!doctype html>" in html.lower()
    assert "Your episode" in html


def test_kenn_explanations_render_when_present():
    report = _report_with_issues()
    report["kenn_explanations"] = [{
        "parameter": "Low-end rumble",
        "answer": "A high-pass filter around 80 Hz removes rumble without touching the voice.",
        "sources": [{"source": "podcast-dialogue-edit.md"}],
    }]
    html = render_podcast_report_html(report)
    assert "What KENN says" in html
    assert "A high-pass filter around 80 Hz" in html
    assert "podcast-dialogue-edit.md" in html


def test_kenn_section_absent_when_no_explanations():
    # A report dict with no kenn_explanations key at all (e.g. analyze_podcast
    # called with explain=False, or the KENN lookup failed best-effort) must
    # render without the section -- pure renderer test, no KENN index needed.
    html = render_podcast_report_html({"checks": [], "score": 100, "summary": "ok"})
    assert "What KENN says" not in html
