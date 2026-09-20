"""Deterministic agent logic for Mix Review Lab revision workflows.

Generates a goal-aware, proactive revision checklist from mix review data.
Uses the mix goal to decide which flags matter and which can be deprioritised.
"""

from __future__ import annotations

# Flags that are always worth fixing regardless of goal
ALWAYS_CHECK = {
    "Clipping risk",
    "Low headroom",
    "Mono risk",
    "Low-End Phase Cancellation",
    "DC offset",
    "Long intro silence",
    "Long tail silence",
}

# Flags that are goal-dependent — only worth adding as steps if the goal
# actually targets that area
GOAL_SENSITIVE_CHECKS: dict[str, set[str]] = {
    # For a loudness-first goal like club/hip_hop/edm, low dynamics are expected
    "club": {"Low dynamics", "Spiky transients", "Low presence"},
    "hip_hop": {"Low dynamics", "Low presence", "Low-mid build-up"},
    "edm": {"Low dynamics", "Low presence"},
    "master": {"Low dynamics", "Spiky transients"},
    "premaster": set(),  # All goal-sensitive flags matter for premaster
    "pop_vocal": {"Low presence", "Low-mid build-up"},
    "rap_vocal": {"Low presence", "Low-mid build-up"},
    "podcast": {"Heavy sub", "Low-end heavy balance", "Uneven loudness"},
    "game_audio": {"Uneven loudness", "Spiky transients"},
    "acoustic": {"Low dynamics", "Low presence", "Low-mid build-up"},
    "rock": {"Low dynamics", "Low-mid build-up"},
    "cinematic": {"Uneven loudness", "Low dynamics"},
    "lo_fi": {"Low dynamics", "Low-mid build-up"},
    "jazz": {"Low dynamics", "Low presence"},
}


def _number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _goal_key(report: dict) -> str:
    metrics = report.get("metrics") or {}
    goal = metrics.get("mix_goal") if isinstance(metrics.get("mix_goal"), dict) else {}
    return str(goal.get("key") or "premaster").strip().lower()


def _goal_label(report: dict) -> str:
    metrics = report.get("metrics") or {}
    goal = metrics.get("mix_goal") if isinstance(metrics.get("mix_goal"), dict) else {}
    return str(goal.get("label") or goal.get("key") or "mix").strip()


def _flag_labels(flags: list) -> set[str]:
    return {str(f.get("label", "")) for f in flags if isinstance(f, dict)}


def _is_relevant_flag(flag_label: str, goal_key: str) -> bool:
    """Return True if this flag matters for the chosen goal."""
    if flag_label in ALWAYS_CHECK:
        return True
    sensitive = GOAL_SENSITIVE_CHECKS.get(goal_key)
    if sensitive is None:
        return True  # Fall back to showing everything for unknown goals
    if goal_key == "premaster":
        return True  # Premaster cares about everything
    return flag_label not in sensitive


def _step_id(index: int) -> str:
    return f"step-{index}"


def revision_agent_plan(report: dict) -> dict:
    """Create a deterministic revision checklist from review facts.

    Considers the mix goal to filter which flags deserve a dedicated step.
    Flags that are expected for the goal (e.g. low dynamics for 'club') are
    noted but not added as todo items unless they're extreme.
    """
    metrics = report.get("metrics") or {}
    actions = report.get("action_plan") or []
    flags = report.get("flags") or []
    comparison_advice_items = report.get("comparison_advice") or []
    version_advice_items = report.get("version_advice") or []
    impact = report.get("revision_impact") or {}
    title = str(report.get("title") or metrics.get("filename") or "Uploaded mix")
    goal_key = _goal_key(report)
    goal_label = _goal_label(report)

    steps: list[dict] = []
    step_num = 0

    def add_step(
        focus: str,
        action: str,
        why: str = "",
        *,
        category: str = "repair",
    ) -> None:
        nonlocal step_num
        if not action:
            return
        step_num += 1
        steps.append(
            {
                "id": _step_id(step_num),
                "status": "todo",
                "category": category,
                "focus": focus[:100],
                "action": action[:600],
                "why": why[:500],
            }
        )

    # --- Step 1: Prioritise regressions from previous version ---
    regressions = impact.get("regressions") if isinstance(impact.get("regressions"), list) else []
    for regression in regressions[:2]:
        add_step(
            "Regression fix",
            str(regression),
            "This area moved in the wrong direction since the last version.",
            category="revision",
        )

    # --- Steps from action plan, filtered by goal ---
    flag_labels = _flag_labels(flags)
    for item in actions[:5]:
        focus = str(item.get("focus") or "Mix fix")
        action = str(item.get("action") or "")
        reason = str(item.get("reason") or "")
        decision = str(item.get("decision") or "fix_first")

        # Skip goal-irrelevant flags (but still add as "watching" if marked)
        if not _is_relevant_flag(focus, goal_key) and decision != "fix_first":
            continue

        # For "needs_reference" decisions, mark as reference step
        cat = "reference" if decision == "needs_reference" else "repair"
        add_step(focus, action, reason, category=cat)

    # --- Flag-based steps that the action plan might have missed ---
    # (Only for high/medium flags that weren't already in actions)
    action_foci = {str(a.get("focus", "")) for a in actions if isinstance(a, dict)}
    for flag in flags:
        label = str(flag.get("label", ""))
        severity = str(flag.get("severity", "low"))
        if label in action_foci:
            continue
        if not _is_relevant_flag(label, goal_key):
            continue
        detail = str(flag.get("detail", ""))

        if label == "Low dynamics" and severity == "medium":
            add_step(
                "Level matched dynamics pass",
                "Bypass or ease the loudest bus processing, level-match against the current version, and check whether punch returns without losing intent.",
                "Low crest factor suggests the mix may be over-controlled.",
                category="verify",
            )
        elif label == "Low-mid build-up" and severity == "medium":
            add_step(
                "Low-mid cleanup pass",
                "Check bass, guitars, keys, room mics, reverbs, and vocal body around 150-400 Hz before adding more brightness.",
                "Low-mid buildup can make the whole mix feel smaller and less clear.",
                category="repair",
            )
        elif label == "Low headroom" and severity == "high":
            add_step(
                "Headroom fix",
                "Lower the mix bus or limiter output by 1-3 dB to create safer peak headroom for mastering or delivery.",
                detail,
                category="repair",
            )
        elif label == "Heavy sub":
            add_step(
                "Sub balance check",
                "Check kick and bass separation below 80 Hz in mono, then level-match against a reference.",
                detail,
                category="repair",
            )
        elif label == "Low presence":
            add_step(
                "Presence check",
                "Check whether vocal, snare, or lead clarity needs controlled 2-6 kHz presence. Clean masking before boosting.",
                detail,
                category="repair",
            )
        elif label == "Mono risk" or label == "Low-End Phase Cancellation":
            add_step(
                "Mono compatibility check",
                "Fold to mono and listen for vocal, snare, kick, and bass level changes. Fix phase issues or narrow wideners.",
                detail,
                category="verify",
            )
        elif label == "Uneven loudness":
            add_step(
                "Section level smoothing",
                "Smooth arrangement volume jumps with clip gain or automation before reassessing bus compression.",
                detail,
                category="repair",
            )

    # --- Comparison advice from reference (if present) ---
    for item in comparison_advice_items[:2]:
        text = str(item).strip()
        if text and not any(text in str(s.get("action", "")) for s in steps):
            add_step("Reference check", text, "Reference comparison from Mix Review Lab.", category="reference")

    # --- Version advice (if present) ---
    for item in version_advice_items[:2]:
        text = str(item).strip()
        if text and not any(text in str(s.get("action", "")) for s in steps):
            add_step("Revision check", text, "Previous-version comparison from Mix Review Lab.", category="revision")

    # --- Fallback: if no steps were generated, add a listening pass ---
    if not steps:
        add_step(
            "Listening pass",
            f"Level-match with a trusted reference ({goal_label} target), check mono compatibility, then make one small taste revision before re-exporting.",
            f"No major technical flags for this {goal_label} target. Next move is controlled listening.",
            category="listen",
        )

    # --- Always append the export step ---
    add_step(
        "Export next revision",
        f"Export {title} as the next version with the same track title in KENN, then run Mix Review Lab again.",
        "Keeping the title identical lets the timeline compare versions automatically.",
        category="export",
    )

    # Build the goal-aware summary line
    flag_count = len(flag_labels)
    relevant_flags = {label for label in flag_labels if _is_relevant_flag(label, goal_key)}
    filtered_count = flag_count - len(relevant_flags)
    summary_parts = [f"{len(steps)} step revision checklist for {goal_label}"]
    if filtered_count > 0:
        summary_parts.append(f"({filtered_count} flag(s) deprioritised as expected for {goal_label})")

    return {
        "agent": "mix_revision_agent",
        "status": "ready",
        "goal": f"Create the next focused revision for {title} ({goal_label} target).",
        "summary": ". ".join(summary_parts),
        "steps": steps[:10],
        "goal_key": goal_key,
        "goal_label": goal_label,
        "relevant_flag_count": len(relevant_flags),
        "filtered_flag_count": filtered_count,
    }


def update_step_status(agent: dict, step_id: str, status: str) -> tuple[dict, bool]:
    """Return an updated revision agent payload and whether a step changed."""
    steps = agent.get("steps") if isinstance(agent.get("steps"), list) else []
    changed = False
    for step in steps:
        if isinstance(step, dict) and str(step.get("id", "")) == step_id:
            step["status"] = status
            changed = True
            break
    if not changed:
        return agent, False
    done_count = sum(1 for step in steps if isinstance(step, dict) and step.get("status") == "done")
    total_steps = len([step for step in steps if isinstance(step, dict)])
    agent["done_count"] = done_count
    agent["total_steps"] = total_steps
    agent["progress"] = round(done_count / total_steps, 3) if total_steps else 0
    return agent, True


def revision_impact_summary(current_report: dict, previous_report: dict | None) -> dict | None:
    """Summarise whether the current version moved in useful directions.

    Considers the mix goal when deciding whether a delta is meaningful.
    """
    if not previous_report:
        return None
    current_metrics = current_report.get("metrics") or {}
    previous_metrics = previous_report.get("metrics") or {}
    previous_agent = previous_report.get("revision_agent") or {}
    previous_steps = previous_agent.get("steps") if isinstance(previous_agent.get("steps"), list) else []
    completed_steps = [
        step
        for step in previous_steps
        if isinstance(step, dict) and step.get("status") == "done"
    ]
    comparison = current_report.get("version_comparison") or {}
    improvements: list[str] = []
    regressions: list[str] = []
    checks: list[str] = []
    goal_key = _goal_key(current_report)

    current_score = _number(current_metrics.get("technical_score"))
    previous_score = _number(previous_metrics.get("technical_score"))
    if current_score is not None and previous_score is not None:
        delta = current_score - previous_score
        if delta > 2:
            improvements.append(f"Technical score improved by {delta:.0f} points.")
        elif delta < -2:
            regressions.append(f"Technical score dropped by {abs(delta):.0f} points.")
        else:
            checks.append("Technical score stayed broadly similar; judge the revision by level-matched listening.")

    crest_delta = _number(comparison.get("crest_delta_db"))
    if crest_delta is not None:
        if crest_delta > 1:
            improvements.append("Crest factor increased, so the mix may have regained punch or transient movement.")
        elif crest_delta < -1:
            # For club/edm, lower crest is expected — only flag if extreme
            if goal_key in ("club", "hip_hop", "edm") and abs(crest_delta) < 2:
                checks.append(f"Crest factor reduced by {abs(crest_delta):.1f} dB — within expected range for {_goal_label(current_report)}.")
            else:
                regressions.append("Crest factor reduced; check whether the revision lost punch.")

    rms_delta = _number(comparison.get("rms_delta_db"))
    if rms_delta is not None and abs(rms_delta) > 1.5:
        checks.append(f"RMS changed by {rms_delta:+.1f} dB, so level-match before judging tone.")

    previous_labels = {str(flag.get("label", "")) for flag in previous_report.get("flags", []) if isinstance(flag, dict)}
    current_labels = {str(flag.get("label", "")) for flag in current_report.get("flags", []) if isinstance(flag, dict)}
    cleared = sorted(label for label in previous_labels - current_labels if label)
    new_flags = sorted(label for label in current_labels - previous_labels if label)

    # When filtering for the narrative, note which new flags are goal-expected
    unexpected_new = [label for label in new_flags if _is_relevant_flag(label, goal_key)]
    expected_new = [label for label in new_flags if not _is_relevant_flag(label, goal_key)]

    for label in cleared[:3]:
        improvements.append(f"Previous flag cleared: {label}.")
    for label in unexpected_new[:3]:
        regressions.append(f"New flag appeared: {label}.")
    for label in expected_new[:2]:
        checks.append(f"New flag '{label}' appeared but is within expected range for {_goal_label(current_report)} — listen rather than chase numbers.")

    if completed_steps:
        checks.append(f"{len(completed_steps)} previous checklist step(s) were marked done before this revision.")
    elif previous_agent:
        checks.append("No previous checklist steps were marked done, so treat this as an unchecked revision.")

    verdict = "mixed"
    if improvements and not unexpected_new and not regressions:
        verdict = "improved"
    elif regressions and not improvements:
        verdict = "regressed"
    elif not improvements and not regressions:
        verdict = "similar"

    return {
        "verdict": verdict,
        "completed_step_count": len(completed_steps),
        "completed_steps": [
            {
                "id": step.get("id", ""),
                "focus": step.get("focus", ""),
                "action": step.get("action", ""),
            }
            for step in completed_steps[:6]
        ],
        "improvements": improvements[:6],
        "regressions": regressions[:6],
        "checks": checks[:6],
        "goal_key": goal_key,
        "goal_label": _goal_label(current_report),
    }
