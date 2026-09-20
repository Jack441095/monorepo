"""Audit-aligned quality scoring for best-of-K rerank (Phase A upgrade)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def professional_quality_score(row: Mapping[str, Any]) -> float:
    """
    Composite 0..100 quality score aligned with ``scripts/batch_full_song_note_audit.py``.
    Higher is better.
    """
    in_key = _clamp01(float(row.get("in_key_primary_ratio", row.get("in_key_ratio", 0.0)) or 0.0))
    leap_p95 = float(row.get("lead_abs_interval_p95", 0.0) or 0.0)
    leap_score = _clamp01(1.0 - max(0.0, leap_p95 - 5.0) / 10.0)
    repeat = _clamp01(float(row.get("lead_repeat_frac", 0.0) or 0.0))
    repeat_score = _clamp01(1.0 - max(0.0, repeat - 0.12) / 0.45)
    overlap = _clamp01(float(row.get("lead_arp_overlap", 0.0) or 0.0))
    overlap_score = _clamp01(1.0 - max(0.0, overlap - 0.22) / 0.38)
    lead_activity = float(row.get("lead_activity", 0.0) or 0.0)
    if lead_activity <= 0.0:
        lead_activity_score = 0.0
    elif lead_activity < 0.18:
        lead_activity_score = _clamp01(lead_activity / 0.18)
    elif lead_activity <= 0.72:
        lead_activity_score = 1.0
    else:
        lead_activity_score = _clamp01(1.0 - (lead_activity - 0.72) / 0.28)
    chord_rate = float(row.get("chord_change_rate_per_bar", 0.0) or 0.0)
    if chord_rate <= 0.0:
        chord_score = 0.0
    elif chord_rate < 0.35:
        chord_score = _clamp01(chord_rate / 0.35)
    elif chord_rate <= 1.45:
        chord_score = 1.0
    else:
        chord_score = _clamp01(1.0 - (chord_rate - 1.45) / 0.75)
    strongbeat_ct = _clamp01(float(row.get("mh_strongbeat_chord_tone_frac", 0.5) or 0.5))
    phrase_end_ct = _clamp01(float(row.get("mh_phrase_end_chord_tone_frac", 0.5) or 0.5))
    ceiling_hit = _clamp01(float(row.get("lead_ceiling_hit_frac", 0.0) or 0.0))
    top_band = _clamp01(float(row.get("lead_top_band_frac", 0.0) or 0.0))
    top_pitch = _clamp01(float(row.get("lead_top_pitch_frac", 0.0) or 0.0))
    roots = int(row.get("unique_section_roots", 1) or 1)
    hook_identity = _clamp01(float(row.get("hook_identity_score", 0.0) or 0.0))
    chorus_payoff = _clamp01(float(row.get("chorus_payoff_score", 0.0) or 0.0))
    motif_development = _clamp01(float(row.get("motif_development_score", 0.0) or 0.0))

    ceiling_score = _clamp01(1.0 - (0.55 * ceiling_hit + 0.35 * top_band + 0.45 * top_pitch))
    root_variety_score = 1.0 if roots >= 3 else (0.72 if roots == 2 else 0.35)
    score01 = (
        0.20 * in_key
        + 0.11 * leap_score
        + 0.08 * repeat_score
        + 0.09 * overlap_score
        + 0.07 * lead_activity_score
        + 0.06 * chord_score
        + 0.08 * strongbeat_ct
        + 0.10 * phrase_end_ct
        + 0.04 * ceiling_score
        + 0.02 * root_variety_score
        + 0.06 * hook_identity
        + 0.05 * chorus_payoff
        + 0.04 * motif_development
    )
    return float(100.0 * _clamp01(score01))


def metrics_row_from_rerank_details(details: Mapping[str, Any]) -> Dict[str, Any]:
    """Map ``SongGenerator._score_candidate_song`` details to audit metric row keys."""
    row: Dict[str, Any] = {}
    for key in (
        "lead_activity",
        "lead_repeat_frac",
        "lead_arp_overlap",
        "chord_change_rate_per_bar",
        "lead_abs_interval_p95",
        "counter_activity",
        "arp_activity",
    ):
        if key in details:
            row[key] = details[key]
    row["in_key_primary_ratio"] = float(details.get("in_key_primary_ratio", details.get("in_key_ratio", 1.0)) or 1.0)
    row["unique_section_roots"] = int(details.get("section_scale_variety", details.get("unique_section_roots", 1)) or 1)
    row["mh_strongbeat_chord_tone_frac"] = float(details.get("mh_strongbeat_chord_tone_frac", 0.5) or 0.5)
    row["mh_phrase_end_chord_tone_frac"] = float(details.get("mh_phrase_end_chord_tone_frac", 0.5) or 0.5)
    row["lead_ceiling_hit_frac"] = float(details.get("lead_ceiling_hit_frac", 0.0) or 0.0)
    row["lead_top_band_frac"] = float(details.get("lead_top_band_frac", 0.0) or 0.0)
    row["lead_top_pitch_frac"] = float(details.get("lead_top_pitch_frac", 0.0) or 0.0)
    qr = details.get("quality_report")
    if isinstance(qr, dict):
        vals = dict(qr.get("values") or {})
        checks = dict(qr.get("checks") or {})
        if checks.get("memorable_hook"):
            row["hook_identity_score"] = max(float(row.get("hook_identity_score", 0.0) or 0.0), 0.72)
        if checks.get("chorus_stronger_than_verse"):
            row["chorus_payoff_score"] = max(float(row.get("chorus_payoff_score", 0.0) or 0.0), 0.65)
        if int(vals.get("chorus_motif_slots", 0) or 0) > 0:
            row["motif_development_score"] = max(float(row.get("motif_development_score", 0.0) or 0.0), 0.55)
    row["counter_melody_events_per_bar"] = float(details.get("counter_melody_events_per_bar", details.get("counter_activity", 0.0)) or 0.0)
    return row


def audit_aligned_score_from_details(details: Mapping[str, Any]) -> Tuple[float, Dict[str, Any]]:
    row = metrics_row_from_rerank_details(details)
    score = professional_quality_score(row)
    out = dict(row)
    out["audit_aligned_quality_score"] = float(score)
    return float(score), out


def blend_rerank_scores(
    legacy_score: float,
    details: Mapping[str, Any],
    *,
    weight: float = 0.55,
    model_path: str = "",
) -> Tuple[float, Dict[str, Any]]:
    """
    Blend heuristic ``_score_candidate_song`` score with audit-aligned 0..100 score.

    ``legacy_score`` is typically ~0..3; audit score is 0..100. We normalize legacy
    to 0..100 using a soft cap so both terms are comparable.

    When ``model_path`` is set, the audit term uses the learned ridge reranker (Phase B).
    """
    w = max(0.0, min(1.0, float(weight)))
    if str(model_path or "").strip():
        from composition.song_rerank_model import learned_rerank_score_from_details

        audit_score, audit_row = learned_rerank_score_from_details(details, model_path=str(model_path))
    else:
        audit_score, audit_row = audit_aligned_score_from_details(details)
    legacy_norm = max(0.0, min(100.0, float(legacy_score) * 28.0))
    blended = (1.0 - w) * legacy_norm + w * float(audit_score)
    meta = {
        "rerank_legacy_score": float(legacy_score),
        "rerank_legacy_norm": float(legacy_norm),
        "rerank_audit_weight": float(w),
        **audit_row,
    }
    return float(blended), meta


def enrich_rerank_details_from_song(
    details: Dict[str, Any],
    *,
    events: Sequence[Sequence[Any]],
    section_roles: Optional[Sequence[str]] = None,
    section_bars: Optional[Sequence[int]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    beats_per_bar: float = 4.0,
    bars: Optional[int] = None,
) -> Dict[str, Any]:
    """Attach ``quality_report`` and hook proxies used by audit-aligned rerank."""
    from composition.evaluation import quality_report

    out = dict(details)
    try:
        out["quality_report"] = quality_report(
            events,
            section_roles=section_roles,
            section_bars=section_bars,
            metadata=metadata,
            beats_per_bar=float(beats_per_bar),
            bars=bars,
        )
    except Exception:
        pass
    return out
