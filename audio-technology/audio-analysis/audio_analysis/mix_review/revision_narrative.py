"""Revision narrative — human-readable diff between mix review versions.

Builds a compact, agent-friendly summary of what changed between two
versions of the same track. This is what the KENN context handoff uses
to explain "v3 vs v2: +4 score, cleared low dynamics, new heavy sub flag."
"""

from __future__ import annotations


def _float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _flag_labels(report: dict) -> set[str]:
    return {
        str(flag.get("label", ""))
        for flag in report.get("flags") or []
        if isinstance(flag, dict) and flag.get("label")
    }


def _goal_label(report: dict) -> str:
    metrics = report.get("metrics") or {}
    goal = metrics.get("mix_goal") if isinstance(metrics.get("mix_goal"), dict) else {}
    return str(goal.get("label") or goal.get("key") or "mix").strip()


def _metric_delta(current: dict, previous: dict, key: str) -> float | None:
    c = current.get(key)
    p = previous.get(key)
    if c is not None and p is not None:
        return _float(c) - _float(p)
    return None


def _tonal_balance_label(report: dict) -> str:
    metrics = report.get("metrics") or {}
    balance = metrics.get("tonal_balance") if isinstance(metrics.get("tonal_balance"), dict) else {}
    return str(balance.get("profile") or "").strip()


def _dynamic_profile_label(report: dict) -> str:
    metrics = report.get("metrics") or {}
    profile = metrics.get("dynamic_profile") if isinstance(metrics.get("dynamic_profile"), dict) else {}
    return str(profile.get("profile") or "").strip()


def _stereo_field_label(report: dict) -> str:
    metrics = report.get("metrics") or {}
    field = metrics.get("stereo_field") if isinstance(metrics.get("stereo_field"), dict) else {}
    return str(field.get("image") or "").strip()


def _dominant_band(report: dict) -> str:
    metrics = report.get("metrics") or {}
    summary = metrics.get("perceptual_summary") if isinstance(metrics.get("perceptual_summary"), dict) else {}
    return str(summary.get("dominant_band") or "").strip()


def build_revision_narrative(
    current_report: dict,
    previous_report: dict | None,
    version_comparison: dict | None = None,
    revision_impact: dict | None = None,
) -> dict:
    """Create a compact, agent-readable narrative of what changed between versions.

    Args:
        current_report: The latest report dict.
        previous_report: The previous version's report dict, or None.
        version_comparison: Pre-computed version comparison dict, or None to compute.
        revision_impact: Pre-computed revision impact dict, or None to compute.

    Returns:
        Dict with 'verdict', 'narrative' (str), 'deltas', 'cleared', 'new_flags',
        'action_summary', 'narrative_line' (single-line for LLM context).
    """
    current_metrics = current_report.get("metrics") or {}
    previous_metrics = previous_report.get("metrics") or {} if previous_report else {}

    if previous_report is None:
        return {
            "verdict": "initial",
            "narrative": "First review — no previous version to compare against.",
            "deltas": {},
            "cleared": [],
            "new_flags": [],
            "unchanged_flags": [],
            "action_summary": "Run Mix Review Lab again after your next revision to see the delta.",
            "narrative_line": "First review uploaded. No version comparison available yet.",
        }

    # Scores
    current_score = _float(current_metrics.get("technical_score"))
    previous_score = _float(previous_metrics.get("technical_score"))
    score_delta = round(current_score - previous_score, 1)

    # Flags
    previous_flags = _flag_labels(previous_report)
    current_flags = _flag_labels(current_report)
    cleared = sorted(previous_flags - current_flags)
    new_flags = sorted(current_flags - previous_flags)
    unchanged = sorted(previous_flags & current_flags)

    # Key metric deltas
    deltas: dict[str, float | None] = {}
    for key, label in [
        ("crest_factor_db", "crest"),
        ("rms_dbfs_estimate", "rms"),
        ("stereo_width_ratio", "width"),
        ("stereo_correlation", "correlation"),
        ("peak_dbfs", "peak"),
    ]:
        delta = _metric_delta(current_metrics, previous_metrics, key)
        if delta is not None:
            deltas[label] = round(delta, 2)

    # Version comparison deltas (sometimes richer)
    comp = version_comparison or current_report.get("version_comparison") or {}
    for key, label in [
        ("rms_delta_db", "rms"),
        ("crest_delta_db", "crest"),
        ("stereo_width_delta", "width"),
        ("correlation_delta", "correlation"),
        ("lufs_delta_db", "lufs"),
    ]:
        value = comp.get(key)
        if value is not None:
            deltas[label] = round(_float(value), 2)

    # Profile changes
    tonal_shift = ""
    prev_tonal = _tonal_balance_label(previous_report)
    curr_tonal = _tonal_balance_label(current_report)
    if prev_tonal and curr_tonal and prev_tonal != curr_tonal:
        tonal_shift = f"Tonal profile moved from '{prev_tonal}' to '{curr_tonal}'."

    dynamic_shift = ""
    prev_dyn = _dynamic_profile_label(previous_report)
    curr_dyn = _dynamic_profile_label(current_report)
    if prev_dyn and curr_dyn and prev_dyn != curr_dyn:
        dynamic_shift = f"Dynamics profile moved from '{prev_dyn}' to '{curr_dyn}'."

    stereo_shift = ""
    prev_st = _stereo_field_label(previous_report)
    curr_st = _stereo_field_label(current_report)
    if prev_st and curr_st and prev_st != curr_st:
        stereo_shift = f"Stereo field shifted from '{prev_st}' to '{curr_st}'."

    # Use revision_impact if available
    impact = revision_impact or current_report.get("revision_impact") or {}
    verdict = str(impact.get("verdict") or "mixed")

    # Build narrative paragraphs
    lines: list[str] = []

    # Score line
    goal = _goal_label(current_report)
    if score_delta > 2:
        lines.append(f"Score improved by {score_delta:.0f} points to {current_score:.0f}/100 ({goal}).")
    elif score_delta < -2:
        lines.append(f"Score dropped by {abs(score_delta):.0f} points to {current_score:.0f}/100 ({goal}).")
    else:
        lines.append(f"Score stayed broadly similar at {current_score:.0f}/100 ({goal}).")

    # Cleared flags
    if cleared:
        lines.append(f"Cleared: {', '.join(cleared)}.")

    # New flags
    if new_flags:
        lines.append(f"New: {', '.join(new_flags)}.")

    # Unchanged flags
    if unchanged:
        lines.append(f"Still present: {', '.join(unchanged)}.")

    # Profile shifts
    if tonal_shift:
        lines.append(tonal_shift)
    if dynamic_shift:
        lines.append(dynamic_shift)
    if stereo_shift:
        lines.append(stereo_shift)

    # Dominant band change
    prev_band = _dominant_band(previous_report)
    curr_band = _dominant_band(current_report)
    if prev_band and curr_band and prev_band != curr_band:
        lines.append(f"Perceived dominant band shifted from '{prev_band}' to '{curr_band}'.")

    # Key metric movements
    metric_notes: list[str] = []
    crest_val = deltas.get("crest")
    if crest_val is not None and abs(crest_val) > 0.8:
        direction = "increased" if crest_val > 0 else "reduced"
        metric_notes.append(f"crest {direction} by {abs(crest_val):.1f} dB")
    rms_val = deltas.get("rms")
    if rms_val is not None and abs(rms_val) > 1.0:
        direction = "up" if rms_val > 0 else "down"
        metric_notes.append(f"RMS {direction} by {abs(rms_val):.1f} dB")
    width_val = deltas.get("width")
    if width_val is not None and abs(width_val) > 0.08:
        direction = "wider" if width_val > 0 else "narrower"
        metric_notes.append(f"stereo {direction} by {abs(width_val):.2f}")
    if metric_notes:
        lines.append(f"Metric movements: {'; '.join(metric_notes)}.")

    # Build action summary
    action_summary = "Looks good — no major technical flags remain." if verdict == "improved" and not new_flags and not unchanged else ""
    if not action_summary:
        if new_flags:
            action_summary = f"Address new flag(s): {', '.join(new_flags[:2])}."
        elif unchanged:
            action_summary = f"Still working on: {', '.join(unchanged[:2])}."
        elif cleared:
            action_summary = f"Good progress — {', '.join(cleared)} cleared. Refine further."
        else:
            action_summary = "Technically similar. Use a level-matched listening pass to judge."

    # Single-line for LLM context
    narrative_line_parts: list[str] = []
    if score_delta > 2:
        narrative_line_parts.append(f"+{score_delta:.0f} score")
    elif score_delta < -2:
        narrative_line_parts.append(f"{score_delta:.0f} score")
    if cleared:
        narrative_line_parts.append(f"cleared {', '.join(cleared)}")
    if new_flags:
        narrative_line_parts.append(f"new {', '.join(new_flags)}")
    if metric_notes:
        narrative_line_parts.append("; ".join(metric_notes))
    if not narrative_line_parts:
        narrative_line_parts.append("technically similar to previous version")
    narrative_line = f"v{current_report.get('version_label', '')}: {'; '.join(narrative_line_parts)}." if current_report.get("version_label") else "; ".join(narrative_line_parts) + "."

    return {
        "verdict": verdict,
        "narrative": "\n".join(lines),
        "deltas": deltas,
        "cleared": cleared,
        "new_flags": new_flags,
        "unchanged_flags": unchanged,
        "score_delta": score_delta,
        "current_score": current_score,
        "previous_score": previous_score,
        "action_summary": action_summary,
        "narrative_line": narrative_line,
    }


def format_narrative_for_agent(narrative: dict) -> str:
    """Format the narrative dict into a clean text block for LLM context."""
    parts = [narrative["narrative"]]
    if narrative.get("action_summary"):
        parts.append("")
        parts.append(f"Next: {narrative['action_summary']}")
    return "\n".join(parts)


def version_diff(current_report: dict, previous_report: dict | None) -> dict:
    """Build a clean, agent-friendly diff between two versions.

    Output is designed for direct injection into KENN context handoff.

    Returns:
        Dict with ok, version_label_a, version_label_b, narrative, deltas, etc.
    """
    if not previous_report:
        return {
            "ok": True,
            "version_label_a": "initial",
            "version_label_b": current_report.get("version_label") or "current",
            "narrative": build_revision_narrative(current_report, None),
            "deltas": {},
            "cleared": [],
            "new_flags": [],
        }
    narrative = build_revision_narrative(current_report, previous_report)
    return {
        "ok": True,
        "version_label_a": previous_report.get("version_label") or "previous",
        "version_label_b": current_report.get("version_label") or "current",
        "narrative": narrative,
        "deltas": narrative["deltas"],
        "cleared": narrative["cleared"],
        "new_flags": narrative["new_flags"],
        "unchanged_flags": narrative["unchanged_flags"],
        "score_delta": narrative["score_delta"],
    }
