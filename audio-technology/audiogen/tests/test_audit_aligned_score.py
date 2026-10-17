"""Audit-aligned rerank scoring (Phase A upgrade)."""

from __future__ import annotations

from composition.audit_aligned_score import (
    blend_rerank_scores,
    professional_quality_score,
)


def test_professional_quality_score_prefers_in_key_low_overlap():
    good = {
        "in_key_primary_ratio": 1.0,
        "lead_abs_interval_p95": 7.0,
        "lead_repeat_frac": 0.08,
        "lead_arp_overlap": 0.18,
        "lead_activity": 0.45,
        "chord_change_rate_per_bar": 0.9,
        "mh_strongbeat_chord_tone_frac": 0.8,
        "mh_phrase_end_chord_tone_frac": 0.85,
        "hook_identity_score": 0.7,
    }
    bad = dict(good)
    bad["in_key_primary_ratio"] = 0.7
    bad["lead_arp_overlap"] = 0.55
    assert professional_quality_score(good) > professional_quality_score(bad)


def test_blend_rerank_scores_increases_when_audit_high():
    details = {
        "lead_activity": 0.5,
        "lead_repeat_frac": 0.1,
        "lead_arp_overlap": 0.2,
        "chord_change_rate_per_bar": 0.8,
        "lead_abs_interval_p95": 7.0,
        "in_key_primary_ratio": 1.0,
        "quality_report": {
            "checks": {"memorable_hook": True, "chorus_stronger_than_verse": True},
            "values": {"chorus_motif_slots": 2},
        },
    }
    low_legacy = 0.5
    blended, meta = blend_rerank_scores(low_legacy, details, weight=0.8)
    assert blended > low_legacy * 28.0 * 0.2
    assert float(meta.get("audit_aligned_quality_score", 0.0)) >= 70.0
