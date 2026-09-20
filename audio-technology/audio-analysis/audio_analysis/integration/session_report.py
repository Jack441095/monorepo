from __future__ import annotations


def _clean(value: object, limit: int = 320) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _first(items: list, fallback: object = None) -> object:
    return items[0] if items else fallback


def _action_text(item: dict | None) -> str:
    if not isinstance(item, dict):
        return ""
    focus = _clean(item.get("focus") or item.get("title") or item.get("priority") or "Action")
    action = _clean(item.get("action"))
    if focus and action:
        return f"{focus}: {action}"
    return action or focus


def _repair_text(item: dict | None) -> str:
    if not isinstance(item, dict):
        return ""
    chain = _clean(item.get("device_chain"))
    move = _clean(item.get("move"))
    target = _clean(item.get("target"))
    check = _clean(item.get("check"))
    parts = []
    if chain:
        parts.append(f"Chain: {chain}")
    if move:
        parts.append(f"Move: {move}")
    if target:
        parts.append(f"Target: {target}")
    if check:
        parts.append(f"Check: {check}")
    return " | ".join(parts)


def build_session_report(report: dict) -> dict:
    """Create a concise engineer-facing session report from a Mix Review payload."""
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    mix_goal = metrics.get("mix_goal") if isinstance(metrics.get("mix_goal"), dict) else {}
    actions = report.get("action_plan") if isinstance(report.get("action_plan"), list) else []
    repairs = report.get("ableton_repair_templates") if isinstance(report.get("ableton_repair_templates"), list) else []
    revision_plan = report.get("next_revision_plan") if isinstance(report.get("next_revision_plan"), dict) else {}
    closed_loop = report.get("closed_loop_action_plan") if isinstance(report.get("closed_loop_action_plan"), dict) else {}
    reference = report.get("reference") if isinstance(report.get("reference"), dict) else {}
    comparison = report.get("comparison") if isinstance(report.get("comparison"), dict) else {}
    comparison_advice = [_clean(item) for item in report.get("comparison_advice") or [] if _clean(item)][:4]
    version_advice = [_clean(item) for item in report.get("version_advice") or [] if _clean(item)][:4]
    revision_steps = [
        _action_text(item)
        for item in revision_plan.get("steps") or []
        if isinstance(item, dict) and _action_text(item)
    ][:5]
    priority_actions = [_action_text(item) for item in actions if isinstance(item, dict) and _action_text(item)][:5]
    ableton_chain = _repair_text(_first(repairs))
    protect = [_clean(item) for item in closed_loop.get("protect", []) if _clean(item)][:4]
    lesson_cards = report.get("lesson_cards") if isinstance(report.get("lesson_cards"), list) else []
    stable_cards = [
        _clean(card.get("title") or card.get("metric"))
        for card in lesson_cards
        if isinstance(card, dict) and card.get("reading") == "normal" and _clean(card.get("title") or card.get("metric"))
    ][:3]
    leave_alone = protect or stable_cards or [
        "Do not chase extra loudness until the first balance issue is fixed.",
        "Avoid broad master EQ moves before checking the source groups.",
    ]
    fix_first = _action_text(_first(actions)) or _clean(revision_plan.get("focus")) or _clean(report.get("summary"))
    fix_next = revision_steps[0] if revision_steps else (_action_text(actions[1]) if len(actions) > 1 else "")
    client_summary_parts = [
        _clean(report.get("title") or metrics.get("filename") or "The uploaded mix"),
        f"scored {metrics.get('technical_score', 'n/a')}/100",
        _clean(metrics.get("technical_rating", "")),
    ]
    target_label = _clean(mix_goal.get("label") or mix_goal.get("key"))
    if target_label:
        client_summary_parts.append(f"for {target_label}")
    client_summary = " ".join(part for part in client_summary_parts if part).strip()
    if fix_first:
        client_summary += f". First revision focus: {fix_first}"
    report_payload = {
        "schema": "audio_too.session_report.v1",
        "title": _clean(report.get("title") or metrics.get("filename") or "Mix Review"),
        "version_label": _clean(report.get("version_label", "")),
        "mix_target": target_label,
        "summary": _clean(report.get("summary"), 600),
        "fix_first": fix_first,
        "fix_next": fix_next,
        "leave_alone": leave_alone,
        "ableton_repair_chain": ableton_chain,
        "v2_export_checklist": [
            *(revision_steps or priority_actions)[:3],
            "Export the loudest section and re-run Mix Review before sending the full revision.",
            "Compare at matched loudness against the previous version and reference.",
        ][:5],
        "reference_comparison": {
            "reference": _clean(reference.get("filename") or reference.get("name") or "Uploaded reference") if reference or comparison else "",
            "rms_delta_db": comparison.get("rms_delta_db"),
            "crest_delta_db": comparison.get("crest_delta_db"),
            "stereo_width_delta": comparison.get("stereo_width_delta"),
            "advice": comparison_advice,
        },
        "version_advice": version_advice,
        "client_summary": client_summary,
        "kenn_memory_lines": [
            f"Track: {_clean(report.get('title') or metrics.get('filename') or 'uploaded mix')}",
            f"Target: {target_label or 'unspecified'}",
            f"Summary: {_clean(report.get('summary'), 500)}",
            f"Fix first: {fix_first}",
            f"Fix next: {fix_next}",
            "Leave alone: " + " | ".join(leave_alone[:3]),
            f"Ableton repair chain: {ableton_chain}",
        ],
    }
    return report_payload
