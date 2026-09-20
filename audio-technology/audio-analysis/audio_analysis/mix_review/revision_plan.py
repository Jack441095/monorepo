"""Revision planning helpers for Mix Review Lab reports."""

from __future__ import annotations


def next_revision_plan(report: dict) -> dict:
    """Build one compact plan from flags, reference deltas, and version deltas."""
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    actions = report.get("action_plan") if isinstance(report.get("action_plan"), list) else []
    repairs = report.get("ableton_repair_templates") if isinstance(report.get("ableton_repair_templates"), list) else []
    reference_coach = report.get("reference_coaching") if isinstance(report.get("reference_coaching"), dict) else {}
    revision_coach = report.get("revision_coaching") if isinstance(report.get("revision_coaching"), dict) else {}
    revision_impact = report.get("revision_impact") if isinstance(report.get("revision_impact"), dict) else {}
    comparison_advice_items = [str(item).strip() for item in report.get("comparison_advice") or [] if str(item).strip()]
    version_advice_items = [str(item).strip() for item in report.get("version_advice") or [] if str(item).strip()]

    if revision_coach:
        headline = str(revision_coach.get("headline") or "Plan the next version from the previous-version comparison.")
    elif reference_coach:
        headline = str(reference_coach.get("headline") or "Plan the next version against the reference.")
    else:
        headline = str(report.get("summary") or "Plan one focused revision from the current review.")

    focus = ""
    if revision_coach.get("next_focus"):
        focus = str(revision_coach["next_focus"])
    elif reference_coach.get("next_move"):
        focus = str(reference_coach["next_move"])
    elif actions:
        first = actions[0]
        if isinstance(first, dict):
            focus = f"{first.get('focus', 'Main fix')}: {first.get('action', '')}".strip(": ")
    if not focus:
        focus = "Make one focused revision, then re-upload it for comparison."

    steps: list[dict] = []
    for action in actions[:2]:
        if not isinstance(action, dict):
            continue
        text = str(action.get("action", "")).strip()
        if text:
            steps.append(
                {
                    "source": "mix_review_action",
                    "focus": str(action.get("focus", "Main fix")),
                    "action": text,
                    "why": str(action.get("reason", "")),
                }
            )
    for repair in repairs[:2]:
        if not isinstance(repair, dict):
            continue
        move = str(repair.get("move", "")).strip()
        if move and not any(step["action"] == move for step in steps):
            steps.append(
                {
                    "source": "ableton_repair",
                    "focus": str(repair.get("flag", "Ableton repair")),
                    "action": move,
                    "why": str(repair.get("target", "")),
                    "device_chain": str(repair.get("device_chain", "")),
                    "check": str(repair.get("check", "")),
                }
            )
    for item in [*version_advice_items[:2], *comparison_advice_items[:2]]:
        if item and not any(step["action"] == item for step in steps):
            steps.append({"source": "comparison_advice", "focus": "Comparison check", "action": item, "why": ""})
    if not steps:
        steps.append(
            {
                "source": "listening",
                "focus": "Level-matched reference pass",
                "action": "Level-match the current mix against the previous version and reference, then make one audible change.",
                "why": f"Technical score is {metrics.get('technical_score', 'n/a')}/100.",
            }
        )

    checks = []
    if revision_coach.get("listening_test"):
        checks.append(str(revision_coach["listening_test"]))
    if reference_coach.get("level_message"):
        checks.append(str(reference_coach["level_message"]))
    checks.extend(
        [
            "Export with the same start/end points as the previous version.",
            "Re-upload the next WAV and compare score, cleared flags, new flags, loudness, width, and tonal deltas.",
        ]
    )

    return {
        "schema": "kenn.next_revision_plan.v1",
        "headline": headline,
        "focus": focus,
        "verdict": str(revision_impact.get("verdict") or revision_coach.get("verdict") or ""),
        "score_delta": revision_coach.get("score_delta"),
        "cleared_flags": list(revision_coach.get("cleared_flags") or []),
        "new_flags": list(revision_coach.get("new_flags") or []),
        "unchanged_flags": list(revision_coach.get("unchanged_flags") or []),
        "reference_note": str(reference_coach.get("next_move") or (comparison_advice_items[0] if comparison_advice_items else "")),
        "version_note": str(revision_coach.get("next_focus") or (version_advice_items[0] if version_advice_items else "")),
        "steps": steps[:6],
        "checks": checks[:5],
    }
