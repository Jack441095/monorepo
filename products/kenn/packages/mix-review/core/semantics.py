"""Portable deterministic Mix Review semantics owned by KENN."""

from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_mix_style(metrics: dict[str, Any]) -> dict[str, Any]:
    """Return auditable loudness/dynamics labels without external imports."""
    lufs = _number(metrics.get("integrated_lufs"))
    crest = _number(metrics.get("crest_factor_db"))
    if lufs is None or crest is None:
        return {"label": "unknown", "confidence": 0.0, "reasoning": "Loudness and crest factor are required."}
    hot = lufs > -9.0
    compressed = crest < 8.0
    if hot and compressed:
        label = "loudness-war-leaning"
    elif crest >= 12.0 and lufs <= -14.0:
        label = "classic-dynamic-leaning"
    else:
        label = "modern-balanced-leaning"
    return {
        "label": label,
        "confidence": 0.9 if hot == compressed or label == "classic-dynamic-leaning" else 0.55,
        "reasoning": f"Integrated loudness {lufs:.1f} LUFS; crest factor {crest:.1f} dB.",
        "integrated_lufs": lufs,
        "crest_factor_db": crest,
    }


def next_revision_plan(report: dict[str, Any]) -> dict[str, Any]:
    """Turn measured flags into at most three bounded revision steps."""
    actions = report.get("action_plan") if isinstance(report.get("action_plan"), list) else []
    steps = []
    for action in actions:
        if not isinstance(action, dict) or not str(action.get("action", "")).strip():
            continue
        steps.append({
            "focus": str(action.get("focus") or "Mix balance"),
            "action": str(action["action"]).strip(),
            "why": str(action.get("reason") or "Measured Mix Review flag."),
        })
        if len(steps) == 3:
            break
    if not steps:
        steps = [{
            "focus": "Focused listening pass",
            "action": "Make one audible revision, then re-upload the next version for comparison.",
            "why": "No bounded action was supplied by the report.",
        }]
    return {"schema": "kenn.next_revision_plan.v2", "steps": steps}


def deterministic_critique(report: dict[str, Any]) -> str:
    """Produce a traceable fallback critique from measured fields only."""
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else report
    rating = metrics.get("technical_rating") or "Technical review"
    lufs = metrics.get("integrated_lufs", "not measured")
    peak = metrics.get("true_peak_dbfs", "not measured")
    crest = metrics.get("crest_factor_db", "not measured")
    style = classify_mix_style(metrics)["label"]
    return f"{rating}. Loudness: {lufs} LUFS; true peak: {peak} dBFS; crest factor: {crest} dB. Style signal: {style}."
