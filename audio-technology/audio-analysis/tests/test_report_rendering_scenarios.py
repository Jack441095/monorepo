"""Tests for report_rendering.py — HTML report generation.

Covers:
- report_html()                     — 2 tests (structure, content)
- _escape()                         — 2 tests
- _metric()                         — 2 tests
- _list_items()                     — 2 tests
- _actions_html()                   — 2 tests
- _chords_html()                    — 2 tests
- _comparison_table()               — 1 test
"""

from __future__ import annotations


from audio_analysis.integration.report_rendering import report_html


# ==============================================================================
#  report_html
# ==============================================================================

class TestReportHTML:

    def test_returns_html_string(self):
        """report_html returns a complete HTML document."""
        html = report_html({})
        assert html.startswith("<!doctype html>")
        assert html.endswith("</html>")

    def test_contains_title(self):
        """Title appears in the HTML."""
        html = report_html({"title": "Test Mix Review"})
        assert "Test Mix Review" in html

    def test_score_present(self):
        """Technical score is rendered."""
        html = report_html({"metrics": {"technical_score": 82, "technical_rating": "Great"}})
        assert "82" in html
        assert "Great" in html

    def test_flag_labels_rendered(self):
        """Flag labels appear as list items."""
        html = report_html({"flags": [{"label": "low_dynamics"}, {"label": "heavy_sub"}]})
        assert "low_dynamics" in html
        assert "heavy_sub" in html

    def test_chords_section(self):
        """Chords section appears when chords data present."""
        html = report_html({"metrics": {"chords": {"estimated_key": "C Major"}, "filename": "test.wav"}})
        # The section should have the key and the h2
        assert "C Major" in html
        assert "Musical Chord" in html

    def test_reference_comparison(self):
        """Reference comparison renders when data present."""
        html = report_html({
            "comparison": {"rms_delta_db": 3.5},
            "comparison_advice": ["Check the low end."],
        })
        assert "3.5" in html
        assert "RMS delta" in html

    def test_actions_rendered(self):
        """Action plan items appear as ordered list."""
        html = report_html({
            "action_plan": [
                {"focus": "low_mids", "action": "Cut 250 Hz", "reason": "Muddy"},
            ],
        })
        assert "low_mids" in html

    def test_version_comparison(self):
        """Version comparison renders."""
        html = report_html({
            "version_comparison": {"rms_delta_db": -2.0},
            "version_advice": ["Tighter."],
        })
        assert "-2.0" in html
        assert "Revision Comparison" in html

    def test_engineer_critique(self):
        """Critique text renders in a pre block."""
        html = report_html({"mix_critique": {"text": "The low end needs work."}})
        assert "The low end needs work" in html

    def test_mix_review_critique_renders(self):
        """Stage 10 AI critique renders distinctly from the legacy mix_critique."""
        html = report_html({
            "mix_critique": {"text": "Legacy critique text."},
            "mix_review_critique": {"mode": "deterministic", "text": "Overall: Solid technical mix."},
        })
        assert "AI Mix Critique" in html
        assert "Overall: Solid technical mix." in html
        assert "Legacy critique text." in html  # legacy section untouched

    def test_mix_review_critique_absent_when_missing(self):
        """No mix_review_critique key -> no AI Mix Critique section."""
        html = report_html({"mix_critique": {"text": "Legacy only."}})
        assert "AI Mix Critique" not in html

    def test_mix_style_renders(self):
        """Stage 10 style classification renders era/loudness-war/genre."""
        html = report_html({
            "mix_style": {
                "summary": "Pop-leaning, streaming-normalized era (modern mastering character).",
                "era": {"label": "streaming-normalized era", "reasoning": "Loudness/dynamics both typical."},
                "loudness_war": {"severity": "none", "reasoning": "Not squashed."},
                "vintage_or_modern": {"label": "modern", "reasoning": "Narrow dynamics, bright top."},
                "genre": {"genre_name": "Pop"},
            },
        })
        assert "Mix Style" in html
        assert "streaming-normalized era" in html
        assert "Pop" in html

    def test_mix_style_absent_when_missing(self):
        html = report_html({})
        assert "Mix Style" not in html

    def test_stem_solo_renders_low_end_and_carving(self):
        """Stage 10 stem-solo/masking section renders when stem data is present."""
        html = report_html({
            "stem_solo": {
                "low_end_summary": {
                    "overlap_warning": "'bass' and 'kick' both carry substantial low-end energy.",
                    "ranked": [{"name": "bass", "low_end_share": 0.6}, {"name": "kick", "low_end_share": 0.5}],
                },
            },
            "stem_masking": {
                "ok": True,
                "erb_details": {
                    "carving_suggestions": [
                        {"masker": "vocal", "masked": "keys", "frequency_hz": 2500.0},
                    ]
                },
            },
        })
        assert "Stem Solo &amp; Masking" in html or "Stem Solo" in html
        assert "both carry substantial low-end energy" in html
        assert "vocal" in html and "keys" in html

    def test_stem_solo_absent_when_missing(self):
        html = report_html({})
        assert "Stem Solo" not in html

    def test_goal_target_checks(self):
        """Goal target checks section renders."""
        html = report_html({
            "metrics": {
                "goal_target_checks": {
                    "goal": {"key": "premaster", "label": "Premaster"},
                    "summary": "Standard checks.",
                    "checks": [
                        {"label": "Peak headroom", "status": "warn", "value": -0.5},
                    ],
                },
            },
        })
        assert "Peak headroom" in html
        assert "Needs attention" in html

    def test_disclaimer_default(self):
        """Default disclaimer used when missing."""
        html = report_html({})
        assert "First-pass technical analysis" in html
