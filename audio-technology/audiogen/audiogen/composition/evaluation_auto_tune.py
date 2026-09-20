from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


def _history_update(cfg: Any, score: float, window: int) -> Tuple[List[float], float]:
    hist = list(getattr(cfg, "_self_eval_score_history", []) or [])
    hist.append(float(score))
    w = max(2, int(window))
    if len(hist) > w:
        hist = hist[-w:]
    setattr(cfg, "_self_eval_score_history", hist)
    trend = 0.0
    if len(hist) >= 2:
        trend = float(hist[-1]) - float(sum(hist[:-1]) / max(1, len(hist) - 1))
    return hist, float(trend)


def suggest_adjustments(
    *,
    metrics: Dict[str, Any],
    section_metrics: List[Dict[str, Any]],
    strength: float,
    trend: float,
) -> Dict[str, float]:
    s = _clamp(float(strength), 0.0, 1.0)
    out: Dict[str, float] = {}

    lead_rep = float(metrics.get("lead_repeat_frac", 0.0) or 0.0)
    chord_rep = float(metrics.get("chord_repeat_frac", 0.0) or 0.0)
    ov = float(metrics.get("lead_arp_overlap", 0.0) or 0.0)
    lead_act = float(metrics.get("lead_activity", 0.0) or 0.0)

    cad_vals = [float(m.get("cadence_landing_hit_rate", 0.0) or 0.0) for m in list(section_metrics or [])]
    cad_mean = float(sum(cad_vals) / len(cad_vals)) if cad_vals else 0.0

    if lead_rep > 0.30:
        out["melody_ngram_penalty_strength"] = +0.10 * s
        out["motif_variation_prob"] = +0.06 * s
    if chord_rep > 0.42:
        out["chord_rerank_change_bonus"] = +0.05 * s
        out["chord_rhythm_mult_hint"] = +0.04 * s
    if ov > 0.52:
        out["masking_constraints_strength"] = +0.08 * s
        out["arp_density_follow_melody"] = +0.06 * s
    if cad_mean < 0.45:
        out["transition_composer_strength"] = +0.08 * s
        out["cadence_strength"] = +0.07 * s
    if lead_act < 0.28:
        out["melody_amount_scale"] = +0.08 * s
    elif lead_act > 0.65:
        out["melody_amount_scale"] = -0.06 * s

    # If recent score trend declines, tighten structure slightly.
    if trend < -0.04:
        out["hook_development"] = -0.06 * s
        out["motif_use_chance"] = +0.06 * s
        out["bass_intelligence_strength"] = +0.05 * s
    return out


def apply_adjustments(cfg: Any, adjustments: Dict[str, float]) -> Dict[str, float]:
    comp = getattr(cfg, "composition", cfg)
    applied: Dict[str, float] = {}

    def _add(attr: str, delta: float, lo: float, hi: float) -> None:
        try:
            cur = float(getattr(comp, attr))
            new = _clamp(float(cur) + float(delta), float(lo), float(hi))
            setattr(comp, attr, float(new))
            applied[attr] = float(new)
        except Exception:
            return

    for k, dv in dict(adjustments or {}).items():
        d = float(dv)
        if k == "melody_ngram_penalty_strength":
            _add("melody_ngram_penalty_strength", d, 0.0, 1.0)
        elif k == "motif_variation_prob":
            _add("motif_variation_prob", d, 0.02, 0.95)
        elif k == "chord_rerank_change_bonus":
            _add("chord_rerank_change_bonus", d, 0.0, 0.8)
        elif k == "masking_constraints_strength":
            _add("masking_constraints_strength", d, 0.0, 1.0)
        elif k == "arp_density_follow_melody":
            _add("arp_density_follow_melody", d, 0.0, 1.0)
        elif k == "transition_composer_strength":
            _add("transition_composer_strength", d, 0.0, 1.0)
        elif k == "cadence_strength":
            _add("cadence_strength", d, 0.5, 2.5)
        elif k == "melody_amount_scale":
            _add("melody_amount_scale", d, 0.35, 1.5)
        elif k == "hook_development":
            _add("hook_development", d, 0.0, 1.0)
        elif k == "motif_use_chance":
            _add("motif_use_chance", d, 0.0, 1.0)
        elif k == "bass_intelligence_strength":
            _add("bass_intelligence_strength", d, 0.0, 1.0)
    return applied


def maybe_auto_tune_from_render(cfg: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
    comp = getattr(cfg, "composition", cfg)
    enabled = bool(getattr(comp, "self_eval_autotune_enabled", False))
    if not enabled:
        return {"enabled": False}

    strength = float(getattr(comp, "self_eval_autotune_strength", 0.35) or 0.35)
    window = int(getattr(comp, "self_eval_autotune_window", 4) or 4)

    m0 = dict((metadata or {}).get("metrics", {}) or {})
    cand = dict((metadata or {}).get("candidate_metrics", {}) or {})
    score = float((metadata or {}).get("picked_score", cand.get("score", 0.0)) or 0.0)
    section_metrics = list(cand.get("section_metrics", []) or [])
    metrics = dict(m0)
    # Fall back to candidate-derived averages when top-level metrics are sparse.
    if section_metrics and not metrics:
        try:
            metrics = {
                "lead_repeat_frac": float(sum(float(x.get("lead_repeat_frac", 0.0) or 0.0) for x in section_metrics) / len(section_metrics)),
                "chord_repeat_frac": float(sum(float(x.get("chord_repeat_frac", 0.0) or 0.0) for x in section_metrics) / len(section_metrics)),
                "lead_arp_overlap": float(sum(float(x.get("lead_arp_overlap", 0.0) or 0.0) for x in section_metrics) / len(section_metrics)),
                "lead_activity": float(sum(float(x.get("lead_activity", 0.0) or 0.0) for x in section_metrics) / len(section_metrics)),
            }
        except Exception:
            metrics = {}

    hist, trend = _history_update(cfg, score=float(score), window=int(window))
    suggestions = suggest_adjustments(
        metrics=metrics,
        section_metrics=section_metrics,
        strength=float(strength),
        trend=float(trend),
    )
    applied = apply_adjustments(cfg, suggestions)
    return {
        "enabled": True,
        "score": float(score),
        "trend": float(trend),
        "history_len": int(len(hist)),
        "suggestions": dict(suggestions),
        "applied": dict(applied),
    }
