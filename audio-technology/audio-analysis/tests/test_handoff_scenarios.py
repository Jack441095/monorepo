"""Tests for handoff.py — KENN handoff payload builder.

Covers:
- kenn_handoff()                — 4 scenario tests
"""

from __future__ import annotations


from audio_analysis.integration.handoff import kenn_handoff


def _make_report(overrides: dict | None = None) -> dict:
    base = {
        "title": "My Mix",
        "summary": "A solid pop mix.",
        "metrics": {
            "filename": "my_mix.wav",
            "technical_score": 78,
            "technical_rating": "Good",
            "peak_dbfs": -3.2,
            "rms_dbfs_estimate": -18.0,
            "crest_factor_db": 14.0,
            "perceptual_summary": {"dominant_band": "mids"},
            "mix_goal": {"key": "premaster", "label": "Premaster"},
            "section_analysis": {
                "highlights": {
                    "loudest_section": {"label": "Chorus", "rms_dbfs": -12.0},
                    "lowest_correlation_section": {"label": "Verse", "stereo_correlation": 0.3},
                }
            },
        },
        "flags": [
            {"label": "low_dynamics", "severity": "medium", "confidence": "high"},
            {"label": "heavy_sub", "severity": "high", "confidence": "medium"},
        ],
        "action_plan": [
            {"rank": 1, "decision": "eq_adjust", "focus": "low_mids", "action": "Cut 250 Hz", "reason": "Muddy"},
        ],
        "ableton_repair_templates": [
            {"flag": "low_mids", "severity": "high", "device_chain": "EQ Eight", "move": "Cut 250 Hz", "target": "Mids", "check": "A/B"},
        ],
        "comparison": {"rms_delta_db": 3.5, "crest_delta_db": 2.0},
        "comparison_advice": ["The low end is louder than the reference."],
        "version_comparison": {"crest_delta_db": 1.5},
        "version_advice": ["Improved clarity."],
        "revision_impact": {"verdict": "improved"},
    }
    if overrides:
        for k, v in overrides.items():
            base[k] = v
    return base


class TestKennHandoff:

    def test_basic_structure(self):
        result = kenn_handoff(_make_report())
        assert result["schema"] == "kenn_mix_review_handoff.v1"
        assert "title" in result
        assert "metrics" in result
        assert "flags" in result
        assert "priority_actions" in result
        assert "context" in result
        assert "context_lines" in result
        assert "prompt" in result

    def test_metrics_payload(self):
        result = kenn_handoff(_make_report())
        metrics = result["metrics"]
        assert metrics["technical_score"] == 78
        assert metrics["peak_dbfs"] == -3.2
        assert metrics["dominant_band"] == "mids"
        assert metrics["mix_goal"] == "Premaster"

    def test_flag_payload(self):
        result = kenn_handoff(_make_report())
        assert len(result["flags"]) == 2
        assert result["flags"][0]["label"] == "low_dynamics"

    def test_action_payload(self):
        result = kenn_handoff(_make_report())
        assert len(result["priority_actions"]) == 1
        assert result["priority_actions"][0]["focus"] == "low_mids"

    def test_repair_templates(self):
        result = kenn_handoff(_make_report())
        assert len(result["ableton_repair_templates"]) == 1
        assert result["ableton_repair_templates"][0]["move"] == "Cut 250 Hz"

    def test_handoff_preserves_optional_measured_stem_and_transient_summaries(self):
        report = _make_report({
            "transient_preservation": {"preservation_score": 0.42, "matched_event_count": 18, "profile": "Smearing"},
            "stem_masking": {"ok": True, "stems": [
                {"name": "Kick", "overall_visibility": 0.81},
                {"name": "Bass", "overall_visibility": 0.31},
            ]},
            "stem_solo": {"low_end_summary": {"ranked": [
                {"name": "Kick", "low_end_share": 0.44}, {"name": "Bass", "low_end_share": 0.39},
            ]}},
        })
        evidence = kenn_handoff(report)["analysis_evidence"]
        assert evidence["transient_preservation"]["score"] == 0.42
        assert evidence["stem_masking"]["lowest_visibility_stem"] == "Bass"
        assert evidence["low_end_stems"][0]["name"] == "Kick"

    def test_reference_comparison_is_also_flat_not_only_nested(self):
        # server_payloads.py::mix_review_context_turn() reads
        # context.get("reference_comparison") at the top level -- found
        # 2026-08-06 that this function only ever nested it under
        # context["reference"]["comparison"], so eq_bands never actually
        # reached chat for a review sent through this handoff despite the
        # comparison dict itself containing it. Guard against regressing
        # back to nested-only.
        report = _make_report({
            "comparison": {"rms_delta_db": 3.5, "eq_bands": [{"freq": 3200, "gain": 2.1, "q": 1.0}]},
        })
        result = kenn_handoff(report)
        assert result["reference_comparison"]["eq_bands"] == [{"freq": 3200, "gain": 2.1, "q": 1.0}]
        assert result["reference"]["comparison"]["eq_bands"] == [{"freq": 3200, "gain": 2.1, "q": 1.0}]

    def test_mix_style_reaches_top_level_context(self):
        report = _make_report({
            "mix_style": {"genre": {"genre_key": "pop", "genre_name": "Pop", "confidence": 0.82}},
        })
        result = kenn_handoff(report)
        assert result["mix_style"]["genre"]["genre_name"] == "Pop"

    def test_mix_style_defaults_to_empty_dict_when_absent(self):
        result = kenn_handoff(_make_report())
        assert result["mix_style"] == {}

    def test_reference_comparison(self):
        result = kenn_handoff(_make_report())
        ref = result.get("reference", {})
        assert ref.get("comparison", {}).get("rms_delta_db") == 3.5

    def test_version_comparison(self):
        result = kenn_handoff(_make_report())
        assert result["version_comparison"]["crest_delta_db"] == 1.5

    def test_context_lines(self):
        result = kenn_handoff(_make_report())
        lines = "\n".join(result["context_lines"])
        assert "My Mix" in lines
        assert "78" in lines
        assert "Premaster" in lines

    def test_context_block(self):
        result = kenn_handoff(_make_report())
        ctx = result["context"]
        assert "Mix Review Lab context" in ctx
        assert "78/100" in ctx or "78 " in ctx

    def test_empty_report(self):
        result = kenn_handoff({})
        assert result["title"] == "uploaded mix"
        assert len(result["flags"]) == 0

    def test_revision_impact(self):
        result = kenn_handoff(_make_report())
        assert result["revision_impact"]["verdict"] == "improved"

    def test_context_lines_include_version_deltas(self):
        result = kenn_handoff(_make_report())
        ctx = "\n".join(result["context_lines"])
        assert "Version deltas" in ctx

    def test_context_lines_include_reference_deltas(self):
        result = kenn_handoff(_make_report())
        ctx = "\n".join(result["context_lines"])
        assert "Reference deltas" in ctx
