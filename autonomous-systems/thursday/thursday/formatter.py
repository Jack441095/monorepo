"""Unified Response Formatter — converts raw API responses into
human-readable text. Handles errors, empty results, success patterns.
Appends contextual follow-up suggestions.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─── Follow-up suggestions ───────────────────────────────────────────────


FOLLOW_UP_SUGGESTIONS = {
    "business_status": [
        "Ask me about 'reminders' for what's due",
        "Try 'pipeline summary' to see your sales funnel",
        "Want the 'weekly review'?",
    ],
    "weekly_review": [
        "Check 'week ahead' for upcoming items",
        "Try 'pipeline summary' for sales insights",
    ],
    "week_ahead": [
        "Ask 'reminders' for what's overdue",
        "Want to see the 'pipeline summary'?",
    ],
    "pipeline": [
        "Ask me about specific leads or clients",
        "Try 'profit report' for financial insights",
    ],
    "reminders": [
        "Try 'pipeline summary' to see bottlenecks",
        "Want to check 'invoices'?",
    ],
    "monthly_report": [
        "Ask about 'profit report' for financials",
        "Try 'pipeline summary' for sales data",
    ],
    "enquiries": [
        "Want to convert an enquiry to a lead?",
        "Try asking about a specific enquiry",
    ],
    "templates": [
        "Want to draft an email using a template?",
        "Try 'draft outreach to a new artist'",
    ],
    "client_info": [
        "Ask for their 'timeline' or 'history'",
        "Want to 'create a project' for this client?",
        "Try 'draft email' to reach out",
    ],
    "sessions": [
        "Want to 'schedule a session'?",
        "Check upcoming sessions for the week",
    ],
    "expenses": [
        "Try 'profit report' for P&L",
        "Want to see expenses by category?",
    ],
    "profit": [
        "Ask about 'expenses' for detailed breakdown",
        "Try 'invoices' for outstanding payments",
    ],
    "invoices": [
        "Generate a PDF for an invoice",
        "Try 'drafts' to check pending invoices",
    ],
    "drafts": [
        "Send all approved drafts",
        "Check pending drafts for review",
    ],
    "kenn": [
        "Want to save that as a note?",
        "Ask another production question",
        "Try 'analyze my mix' for audio analysis",
    ],
    "audiogen": [
        "Review the generated audio",
        "Try a different emotion or style",
        "Queue a full song render",
    ],
    "audio_analysis": [
        "Show the full QA report",
        "Ask KENN about the worst track",
        "Generate an Ableton correction rack",
    ],
    "mix_review": [
        "Compare versions of your mix",
        "Check mix review progress",
        "Ask KENN for mix advice based on the review",
    ],
    # ── Phase 3 follow-ups ──────────────────────────────────────────────
    "audiogen_status": [
        "Queue a full-song render",
        "Check the render queue",
        "Try 'render a joyful full song'",
    ],
    "audiogen_render": [
        "Check your render job status",
        "Cancel or retry the render",
        "Try a different emotion",
    ],
    "audiogen_job": [
        "Start another render",
        "Check AudioGen system status",
        "View render history",
    ],
    "mix_review_list": [
        "Show a specific review by ID",
        "Scan audio files for a new review",
        "Generate a correction rack",
    ],
    "mix_review_detail": [
        "Generate Ableton correction rack",
        "Check reference tracks",
        "Compare with another version",
    ],
    "mix_review_timeline": [
        "Compare two versions",
        "Show the latest review for that track",
        "Ask KENN about the mix progress",
    ],
    "mix_review_diff": [
        "Check the timeline for context",
        "Generate a correction rack",
        "Show review details",
    ],
    "correction_rack": [
        "Load the rack in Ableton",
        "Ask KENN about the repairs",
        "Show the mix review details",
    ],
    "references": [
        "Upload a new reference track",
        "Scan audio and compare to references",
        "Ask KENN about reference matching",
    ],
    "creative_lab": [
        "Check repair recommendations",
        "Record session feedback",
        "Promote a repair to training",
    ],
    "creative_lab_repairs": [
        "Create repair artifacts for a feedback ID",
        "Export repair training data",
        "Promote a repair case",
    ],
    "portfolio": [
        "Publish audio to portfolio",
        "Discover new audio files",
        "Ask KENN about portfolio tracks",
    ],
    "dashboard": [
        "Check KENN training notes",
        "Rebuild KENN index",
        "Check system health again",
    ],
    # ── End Phase 3 ────────────────────────────────────────────────────
    "admin_agent": [
        "Check 'invoices' for pending items",
        "Try 'reminders' for follow-ups",
    ],
    "marketing_agent": [
        "Check 'pipeline' for lead status",
        "Try 'draft social post' for marketing",
    ],
    "research_agent": [
        "Ask for another research topic",
        "Try KENN for production knowledge",
    ],
    "snapshot": [
        "List available snapshots",
        "Set up automatic daily snapshots",
    ],
    "list_snapshots": [
        "Create a new snapshot",
        "Restore from a snapshot",
    ],
    "search": [
        "Try a different search term",
        "Want to look up a client?",
    ],
    "error": [
        "Try rephrasing your request",
        "Use 'help' to see all available options",
        "Ask a specific question like 'how's business?'",
    ],
}


def format_response(
    result: Any,
    service_name: str,
    service_id: str | None = None,
    context: dict | None = None,
    *,
    question: str = "",
) -> str:
    """Format a service response with optional follow-up suggestions.

    Args:
        result: The raw response from the service.
        service_name: Human-readable name of the service.
        service_id: The service identifier for follow-up suggestions.
        context: Current session context (may influence suggestions).
        question: The user's original question, if available. When set and
            THURSDAY_CONVERSATIONAL_REPLIES is on, the mechanical rendering
            below is optionally passed through an LLM to phrase it naturally
            before follow-up suggestions are appended -- see
            thursday/response_rewrite.py. Leave unset for callers whose
            `result` is already natural-language text (e.g. a brain/KENN
            answer), since rewriting an already-conversational reply is
            redundant and only adds a chance of the grounding check
            discarding it for no benefit.

    Returns:
        Formatted response string with follow-up suggestions appended.
    """
    # Compatibility with the plan's original three-argument form:
    # format_response(result, service, context).
    if isinstance(service_id, dict) and context is None:
        context = service_id
        service_id = None

    if isinstance(result, dict):
        if result.get("ok") is False:
            error_code = str(result.get("error_code") or "service_unavailable")
            result = (
                f"{service_name} could not complete the request "
                f"(error code: {error_code})."
            )
        elif set(("ok", "data", "error")).issubset(result):
            result = _humanize(result.get("data"))
        else:
            result = _humanize(result)
    elif not isinstance(result, str):
        result = _humanize(result)

    if not result:
        result = f"(Thursday: {service_name} returned no output)"

    if question:
        try:
            from thursday.response_rewrite import rewrite as _conversational_rewrite
            rewritten = _conversational_rewrite(question, result, service_name)
            if rewritten:
                result = rewritten
        except Exception:
            logger.warning("Conversational rewrite pass failed, keeping mechanical text", exc_info=True)

    # Get follow-up suggestions
    has_embedded_followups = isinstance(result, str) and any(
        marker in result.lower()
        for marker in ("you could also ask:", "you can also ask:", "**try next:**")
    )
    suggestions = [] if has_embedded_followups else _get_suggestions(service_id, context)

    # Build the formatted response
    parts = [result]

    if suggestions:
        parts.append("")
        parts.append("**Try next:** " + " | ".join(suggestions))

    return "\n".join(parts)


def format_error(error: str, context: dict | None = None) -> str:
    """Format an error response."""
    suggestions = FOLLOW_UP_SUGGESTIONS.get("error", [])
    parts = [
        f"Sorry, I ran into a problem:\n  {error}",
        "",
        "**Try next:** " + " | ".join(suggestions),
    ]
    return "\n".join(parts)


def format_help(services: list[dict]) -> str:
    """Generate formatted help text from service list."""
    seen: set[str] = set()
    lines = [
        "🤖 Thursday — Audio_Too Orchestrator",
        "=" * 45,
        "I understand plain English. Just tell me what you need.\n",
    ]
    for svc in services:
        name = svc.get("name", svc.get("service_id", "?"))
        if name in seen:
            continue
        seen.add(name)
        desc = svc.get("description", "")
        examples = svc.get("examples", [])
        ex_str = f"  → Try: {', '.join(examples[:2])}" if examples else ""
        lines.append(f"  • {name} — {desc}")
        if ex_str:
            lines.append(ex_str)
    lines.extend([
        "",
        "Or just say what you want in your own words!",
    ])
    return "\n".join(lines)


def suggest_follow_ups(intent: str, result: Any = None, context: dict | None = None) -> list[str]:
    """Public follow-up API from the upgrade plan.

    ``intent`` may be either a service ID or an intent category. The result is
    currently reserved for future result-sensitive suggestions.
    """
    intent_defaults = {
        "business_ops": "business_status",
        "client_mgmt": "client_info",
        "financial": "invoices",
        "production_qa": "kenn",
        "audio_generation": "audiogen",
        "mix_review_audio_analysis": "audio_analysis",
        "agent_tasks": "admin_agent",
        "search": "search",
    }
    return _get_suggestions(intent_defaults.get(intent, intent), context)


# ─── Internal ────────────────────────────────────────────────────────────


def _get_suggestions(service_id: str | None, context: dict | None) -> list[str]:
    """Get contextual follow-up suggestions."""
    suggestions = FOLLOW_UP_SUGGESTIONS.get(service_id, []) if service_id else []
    context_suggestions = _get_context_suggestions(context)

    # Merge, limit to 3
    all_suggestions = suggestions + context_suggestions
    if not all_suggestions:
        all_suggestions = ["Ask for 'help' to see what Thursday can do"]
    return all_suggestions[:3]


def _humanize(value: Any) -> str:
    """Render structured service output without Python repr noise."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if not value:
            return "No results found."
        return "\n".join(f"  - {_humanize(item)}" for item in value)
    if isinstance(value, dict):
        return "\n".join(
            f"  {str(key).replace('_', ' ').title()}: {_humanize(item)}"
            for key, item in value.items()
            if key != "error" or item
        )
    return str(value)


def _get_context_suggestions(context: dict | None) -> list[str]:
    """Generate suggestions based on current context."""
    if not context:
        return []

    suggestions = []
    if context.get("current_client"):
        suggestions.append(f"Ask about '{context['current_client']}'")
    if context.get("current_mix_review"):
        suggestions.append("Check your mix review status")
    if context.get("last_search_query"):
        suggestions.append("Refine your last search")

    return suggestions[:2]
