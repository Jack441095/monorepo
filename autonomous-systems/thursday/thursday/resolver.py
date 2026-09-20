"""Context-aware Entity Resolver — enables multi-turn conversations.

Resolves pronouns, implicit entities, and temporal references
using the current session context.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# ─── Pronoun mapping ─────────────────────────────────────────────────────

PRONOUN_MAP = {
    "him": "current_client",
    "her": "current_client",
    "his": "current_client",
    "their": "current_client",
    "they": "current_client",
    "them": "current_client",
    "it": None,  # Resolved dynamically based on context
    "this": None,
    "that": None,
    "those": None,
    "these": None,
}

# ─── Temporal reference patterns ─────────────────────────────────────────

TEMPORAL_PATTERNS = [
    (r"\blast\s+week\b", "last_week"),
    (r"\blast\s+month\b", "last_month"),
    (r"\blast\s+year\b", "last_year"),
    (r"\blast\s+time\b", "last_time"),
    (r"\byesterday\b", "yesterday"),
    (r"\btoday\b", "today"),
    (r"\bthis\s+week\b", "this_week"),
    (r"\bthis\s+month\b", "this_month"),
    (r"\bnext\s+week\b", "next_week"),
]


# ─── Public API ───────────────────────────────────────────────────────────


def resolve_request(text: str, context: dict) -> tuple[str, dict]:
    """Resolve pronouns, implicit entities, and temporal references in text.

    Args:
        text: The raw user input.
        context: The current session context dict.

    Returns:
        Tuple of (resolved_text, resolved_entities) where resolved_text
        has pronouns replaced with actual names/IDs where possible,
        and resolved_entities contains any entities that were resolved
        from context.
    """
    resolved_text = text
    resolved_entities = {}

    # 1. Resolve pronouns to context
    resolved_text = _resolve_pronouns(resolved_text, context, resolved_entities)

    # 2. Resolve implicit entity references ("the client", "the invoice")
    resolved_text = _resolve_implicit_references(resolved_text, context, resolved_entities)

    # 3. Resolve temporal references
    resolved_text = _resolve_temporal(resolved_text, context, resolved_entities)

    # 4. Resolve semantic knowledge graph facts if named entity matches
    try:
        from thursday.memory import get_memory_manager
        graph = get_memory_manager().entity_graph
        words = [w.strip() for w in resolved_text.split() if len(w.strip()) > 2]
        for word in words:
            node = graph.get_entity(word)
            if node:
                resolved_entities[f"graph_entity_{node.entity_type}"] = node.name
                resolved_entities["entity_id"] = node.entity_id
    except Exception:
        pass

    # 5. Resolve image/PDF files for multimodal visual inspection
    try:
        from thursday.multimodal import is_image_path, inspect_image
        words = [w.strip() for w in text.split()]
        for word in words:
            if is_image_path(word):
                result = inspect_image(word, goal_hint=text)
                resolved_entities["multimodal_inspection"] = result.summary
                resolved_entities["image_path"] = result.image_path
                resolved_entities["inspection_type"] = result.inspection_type
    except Exception:
        pass

    return resolved_text, resolved_entities


def resolve_reply(text: str, context: dict) -> dict:
    """Resolve a short reply like 'yes', 'the first one', etc.

    Used when Thursday asks a clarifying question and the user responds.

    Args:
        text: The user's reply.
        context: The current session context including pending_action.

    Returns:
        Updated context with resolved values.
    """
    text_lower = text.lower().strip()
    updated_context = dict(context)

    pending_action = context.get("pending_action")

    if pending_action == "waiting_for_client_name":
        # User is providing a client name
        # Check for "yes, the one from..." or similar
        if text_lower in ("yes", "yeah", "sure", "ok", "okay", "yep"):
            # Keep current context as-is
            pass
        elif text_lower.startswith("the ") or text_lower.startswith("that "):
            # "the first one", "that client" — resolve from context
            pass
        else:
            # Assume plain text is the client name
            # Clean up common prefixes
            name = re.sub(r"^(?:his name is|her name is|it'?s|it is|call (?:him|her) )", "", text, flags=re.IGNORECASE).strip()
            name = re.sub(r"[.,!?]+$", "", name).strip()
            if name and len(name) > 1:
                updated_context["current_client"] = name.title()
                updated_context["pending_action"] = None

    elif pending_action == "waiting_for_confirmation":
        if text_lower in ("yes", "yeah", "sure", "ok", "okay", "yep", "do it"):
            updated_context["pending_action"] = "confirmed"
        elif text_lower in ("no", "nope", "nah", "cancel", "stop"):
            updated_context["pending_action"] = None

    return updated_context


# ─── Internal helpers ─────────────────────────────────────────────────────



# "it" in "is it raining"/"is it working"/"is it possible" etc. is a dummy
# subject (no real-world referent) — the same linguistic pattern as
# weather-it ("it's raining") and extraposition-it ("it's possible that...").
# Found 2026-08-07 building the weather utility: with any current_client set
# in context, "is it raining" silently became "is Jordan raining" (blind
# word-level substitution, no idiom awareness), breaking intent
# classification for that whole common phrasing — and the exact same bug
# already affected "is it working" (system_diagnostics' own example
# phrase). Scoped to this specific preceder/follower shape rather than a
# general NLP fix, but covers the real recurring cases.
_DUMMY_IT_PRECEDERS = {"is", "was", "does", "did", "will", "would"}
_DUMMY_IT_FOLLOWERS = {
    "raining", "snowing", "hailing", "sleeting", "sunny", "cloudy", "windy",
    "cold", "hot", "warm", "working", "done", "true", "false", "ok", "okay",
    "fine", "possible", "necessary", "going", "worth", "safe", "ready",
}


def _resolve_pronouns(text: str, context: dict, resolved_entities: dict) -> str:
    """Replace pronouns with actual names/IDs from context."""
    words = text.split()
    resolved_words = []

    for idx, word in enumerate(words):
        clean_word = word.strip(".,!?;:\"'")
        suffix = word[len(clean_word):] if len(clean_word) < len(word) else ""

        if clean_word.lower() == "it":
            prev_word = words[idx - 1].strip(".,!?;:\"'").lower() if idx > 0 else ""
            next_word = words[idx + 1].strip(".,!?;:\"'").lower() if idx + 1 < len(words) else ""
            if prev_word in _DUMMY_IT_PRECEDERS and next_word in _DUMMY_IT_FOLLOWERS:
                resolved_words.append(word)
                continue

        if clean_word.lower() in PRONOUN_MAP:
            context_key = PRONOUN_MAP[clean_word.lower()]
            if context_key is None:
                # Dynamic resolution — try common context keys
                context_key = _find_best_context_match(context)

            if context_key and context.get(context_key):
                resolved_entities[context_key] = context[context_key]
                resolved_words.append(context[context_key] + suffix)
            else:
                resolved_words.append(word)
        else:
            resolved_words.append(word)

    return " ".join(resolved_words)


def _resolve_implicit_references(text: str, context: dict, resolved_entities: dict) -> str:
    """Resolve 'the client', 'that invoice', 'the project' from context."""
    # Map of reference phrases to context keys
    reference_map = {
        r"\bthe\s+client\b": "current_client",
        r"\bthat\s+client\b": "current_client",
        r"\bthis\s+client\b": "current_client",
        r"\bthe\s+project\b": "current_project",
        r"\bthat\s+project\b": "current_project",
        r"\bthis\s+project\b": "current_project",
        r"\bthe\s+invoice\b": "current_invoice",
        r"\bthat\s+invoice\b": "current_invoice",
        r"\bthis\s+invoice\b": "current_invoice",
        r"\bthe\s+lead\b": "current_client",
        r"\bthe\s+track\b": "last_analyzed_track",
        r"\bthat\s+track\b": "last_analyzed_track",
        r"\bthe\s+review\b": "current_mix_review",
        r"\bthat\s+review\b": "current_mix_review",
        r"\bthe\s+scan\b": "current_audio_scan",
        r"\bthat\s+scan\b": "current_audio_scan",
        r"\bthe\s+report\b": "last_report",
        r"\bthat\s+report\b": "last_report",
    }

    for pattern, ctx_key in reference_map.items():
        if re.search(pattern, text, re.IGNORECASE):
            if context.get(ctx_key):
                resolved_entities[ctx_key] = context[ctx_key]
                # Replace the reference with the actual value for better routing
                text = re.sub(
                    pattern,
                    context[ctx_key],
                    text,
                    flags=re.IGNORECASE,
                )

    return text


def _resolve_temporal(text: str, context: dict, resolved_entities: dict) -> str:
    """Recognize and record temporal references."""
    for pattern, temporal_key in TEMPORAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            resolved_entities[temporal_key] = True
    return text


def temporal_date_range(resolved_entities: dict, *, today: date | None = None) -> tuple[str, str] | None:
    """Convert a resolved temporal flag (see TEMPORAL_PATTERNS) into an
    inclusive (start, end) ISO date range for handlers that list or filter
    date-bearing records ("what happened last month", "sessions this week").

    _resolve_temporal already extracts these flags into resolved_entities on
    every turn, but until now nothing consumed them — this is the missing
    other half. Returns None when no supported flag is present; "last_time"
    and "next_week" aren't date ranges (ambiguous / forward-looking) so are
    left for callers that want raw flags instead.
    """
    today = today or date.today()
    if resolved_entities.get("yesterday"):
        d = today - timedelta(days=1)
        return d.isoformat(), d.isoformat()
    if resolved_entities.get("today"):
        return today.isoformat(), today.isoformat()
    if resolved_entities.get("this_week"):
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), today.isoformat()
    if resolved_entities.get("last_week"):
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(days=1)
        return start.isoformat(), end.isoformat()
    if resolved_entities.get("this_month"):
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat()
    if resolved_entities.get("last_month"):
        first_of_this_month = today.replace(day=1)
        end = first_of_this_month - timedelta(days=1)
        start = end.replace(day=1)
        return start.isoformat(), end.isoformat()
    if resolved_entities.get("last_year"):
        return date(today.year - 1, 1, 1).isoformat(), date(today.year - 1, 12, 31).isoformat()
    return None


def _find_best_context_match(context: dict) -> str | None:
    """Find the most recently used context key for dynamic pronoun resolution."""
    priority_order = [
        "current_client",
        "current_project",
        "current_invoice",
        "current_mix_review",
        "current_audio_scan",
        "current_audiogen_job",
        "last_analyzed_track",
        "last_search_query",
    ]
    for key in priority_order:
        if context.get(key):
            return key
    return None
