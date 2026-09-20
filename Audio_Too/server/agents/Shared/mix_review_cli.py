"""CLI wrapper for the Mix Review revision agent.

Provides CLI commands that call the deterministic revision planner
and progress tracker, reading/writing JSON report files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
# The MixReview package moved to studio/agents/MixReview/ — this used to point
# at business/agents/MixReview, which no longer exists, so every command in
# this file failed with "Could not import revision agent" (see
# docs/CODEBASE_AUDIT_2026-07-06.md).
MIXREVIEW_DIR = ROOT.parent.parent / "studio" / "agents" / "MixReview"
REPORTS_DIR = ROOT / "Shared" / "data" / "mix_reviews"


def _load_report(filepath: str) -> dict:
    """Load a mix review report from a JSON file."""
    path = Path(filepath)
    if not path.is_absolute():
        # Try relative to cwd, then Shared/data/mix_reviews, then MixReview/data/mix_reviews
        candidates = [
            path,
            REPORTS_DIR / path.name,
            MIXREVIEW_DIR / "data" / "mix_reviews" / path.name,
        ]
        for c in candidates:
            if c.exists():
                path = c
                break

    if not path.exists():
        raise FileNotFoundError(f"Report not found: {filepath}")

    return json.loads(path.read_text(encoding="utf-8"))


def _save_report(report: dict, filepath: str | Path) -> Path:
    """Save a report dict to a JSON file."""
    path = Path(filepath)
    if not path.is_absolute():
        path = REPORTS_DIR / path.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def cmd_plan(filepath: str) -> str:
    """Generate a revision plan from a report file."""
    try:
        from MixReview.revision_agent import revision_agent_plan  # type: ignore
    except ImportError as e:
        # Try adding MixReview to path
        sys.path.insert(0, str(MIXREVIEW_DIR.parent))
        try:
            from MixReview.revision_agent import revision_agent_plan  # noqa
        except ImportError:
            return f"Could not import revision agent: {e}"

    try:
        report = _load_report(filepath)
    except FileNotFoundError as e:
        return str(e)
    except json.JSONDecodeError as e:
        return f"Invalid JSON in report: {e}"

    plan = revision_agent_plan(report)

    # Save the plan alongside the report
    input_path = Path(filepath)
    if not input_path.is_absolute():
        input_path = REPORTS_DIR / input_path.name
    plan_filename = f"{input_path.stem}_plan.json"
    save_path = _save_report(plan, plan_filename)

    # Format output
    lines = [
        "\U0001f3b5 Mix Review Plan",
        f"{'=' * 40}",
        f"  Goal: {plan.get('goal_label', 'mix')}",
        f"  Summary: {plan.get('summary', '')}",
        f"  Saved to: {save_path}",
        "",
    ]

    for step in plan.get("steps", []):
        status_emoji = {"todo": "\u25cb", "doing": "\U0001f504", "done": "\u2714\ufe0f"}.get(
            step.get("status", "todo"), "\u25cb"
        )
        lines.append(f"  {status_emoji} [{step.get('id', '?')}] {step.get('focus', '')}")
        lines.append(f"     Action: {step.get('action', '')}")
        if step.get("why"):
            lines.append(f"     Why: {step.get('why', '')}")
        lines.append("")

    return "\n".join(lines)


def cmd_progress(filepath: str, step_id: str, status: str) -> str:
    """Mark a step's status (todo/doing/done)."""
    try:
        from MixReview.revision_agent import update_step_status  # type: ignore
    except ImportError:
        sys.path.insert(0, str(MIXREVIEW_DIR.parent))
        try:
            from MixReview.revision_agent import update_step_status  # noqa
        except ImportError as e:
            return f"Could not import revision agent: {e}"

    try:
        plan = _load_report(filepath)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return str(e)

    if plan.get("agent") != "mix_revision_agent":
        return f"Not a valid revision plan: {filepath}"

    valid_statuses = {"todo", "doing", "done"}
    if status not in valid_statuses:
        return f"Invalid status: {status}. Valid: todo, doing, done"

    updated, changed = update_step_status(plan, step_id, status)
    if not changed:
        return f"Step not found: {step_id}"

    # Save updated plan
    input_path = Path(filepath)
    save_path = _save_report(updated, str(input_path))
    progress = updated.get("progress", 0)
    done = updated.get("done_count", 0)
    total = updated.get("total_steps", 0)
    return (
        f"Updated step {step_id} → {status}\n"
        f"Progress: {done}/{total} ({progress:.0%})\n"
        f"Saved to: {save_path}"
    )


def cmd_compare(filepath1: str, filepath2: str) -> str:
    """Compare two version reports."""
    try:
        from MixReview.revision_agent import revision_impact_summary  # type: ignore
    except ImportError:
        sys.path.insert(0, str(MIXREVIEW_DIR.parent))
        try:
            from MixReview.revision_agent import revision_impact_summary  # noqa
        except ImportError as e:
            return f"Could not import revision agent: {e}"

    try:
        report1 = _load_report(filepath1)
        report2 = _load_report(filepath2)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return str(e)

    # revision_impact_summary expects (current_report, previous_report)
    # Treat filepath2 as the newer version, filepath1 as older
    # Heuristic: whichever has the later title or higher score is "current"
    score1 = float(report1.get("metrics", {}).get("technical_score", 0) or 0)
    score2 = float(report2.get("metrics", {}).get("technical_score", 0) or 0)
    if score2 >= score1:
        summary = revision_impact_summary(report2, report1)
    else:
        summary = revision_impact_summary(report1, report2)
    if not summary:
        return "Cannot compare: no previous report provided."

    verdict = summary.get("verdict", "mixed")
    verdict_emoji = {
        "improved": "\U0001f4c8",
        "regressed": "\U0001f4c9",
        "similar": "\u27a1\ufe0f",
        "mixed": "\U0001f504",
    }.get(verdict, "\U0001f504")

    lines = [
        f"{verdict_emoji} Revision Impact — {verdict.upper()}",
        f"{'=' * 40}",
        f"  Goal: {summary.get('goal_label', 'mix')}",
    ]

    improvements = summary.get("improvements", [])
    regressions = summary.get("regressions", [])
    checks = summary.get("checks", [])

    if improvements:
        lines.append("")
        lines.append("  \u2705 Improvements:")
        for imp in improvements:
            lines.append(f"    - {imp}")

    if regressions:
        lines.append("")
        lines.append("  \u26a0\ufe0f Regressions:")
        for reg in regressions:
            lines.append(f"    - {reg}")

    if checks:
        lines.append("")
        lines.append("  \U0001f50d Notes:")
        for check in checks:
            lines.append(f"    - {check}")

    completed = summary.get("completed_steps", [])
    if completed:
        lines.append("")
        lines.append(f"  Completed steps ({summary.get('completed_step_count', 0)}):")
        for step in completed[:5]:
            lines.append(f"    - {step.get('focus', '')}: {step.get('action', '')}")

    return "\n".join(lines)


def cmd_help() -> str:
    return (
        "Mix Review CLI commands:\n\n"
        "  ./agent mix-review plan <report.json>\n"
        "    Generate a revision plan from a mix analysis report.\n"
        "    Reports can be a filename (looks in Shared/data/mix_reviews/)\n"
        "    or a full path.\n\n"
        "  ./agent mix-review progress <plan.json> <step-id> <status>\n"
        "    Update a step's status (todo, doing, done).\n\n"
        "  ./agent mix-review compare <v1.json> <v2.json>\n"
        "    Compare two version reports and show impact.\n\n"
        "  ./agent mix-review help\n"
        "    Show this help text."
    )
