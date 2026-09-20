"""Disambiguation Engine — resolves ambiguous references in Thursday requests.

Detects cases where a user's request could refer to multiple entities
and generates clarifying questions.
"""

from __future__ import annotations

import re
from typing import Any, Callable



class Ambiguity:
    """Represents an ambiguous reference that needs clarification."""

    def __init__(
        self,
        entity_type: str,
        reference: str,
        options: list[dict],
        context_key: str | None = None,
    ):
        self.entity_type = entity_type
        self.reference = reference
        self.options = options
        self.context_key = context_key

    def to_dict(self) -> dict:
        return {
            "type": "ambiguity",
            "entity_type": self.entity_type,
            "reference": self.reference,
            "options": self.options,
            "context_key": self.context_key,
        }


def detect_ambiguity(
    text: str,
    intent: Any,
    context: dict,
    list_records: Callable[[str], list[dict]] | None = None,
) -> Ambiguity | None:
    """Detect ambiguous references in the user's request.

    Checks:
      1. Multiple clients with the same name fragment
      2. Multiple records matching an entity reference
      3. Pronoun ambiguity (multiple possible referents in context)

    Args:
        text: The user's request.
        intent: The classified Intent object.
        context: Current session context.
        list_records: Data access function.

    Returns:
        Ambiguity object if ambiguity detected, None otherwise.
    """
    text_lower = text.lower()

    # 1. Check client name ambiguity
    if list_records and ("client" in text_lower or "about" in text_lower):
        client_name = _extract_possible_name(text)
        if client_name:
            try:
                clients = list_records("clients")
                matches = _fuzzy_match_records(clients, client_name, name_fields=["name", "client", "lead", "company"])
                if len(matches) > 1:
                    return Ambiguity(
                        entity_type="client",
                        reference=client_name,
                        options=[{"id": c.get("id", ""), "name": c.get("name", c.get("client", "?")), "extra": c.get("email", c.get("service", ""))} for c in matches[:5]],
                        context_key="current_client",
                    )
                if len(matches) == 1 and matches[0].get("name", "").lower() != client_name.lower():
                    # Auto-correct: "show me Jorden" -> "Did you mean Jordan?"
                    corrected = matches[0].get("name", "")
                    if _is_spelling_variant(client_name, corrected):
                        return Ambiguity(
                            entity_type="client_spelling",
                            reference=client_name,
                            options=[{"id": matches[0].get("id", ""), "name": corrected, "original": client_name}],
                            context_key="current_client",
                        )
            except Exception:
                pass

    # 2. Check pronoun ambiguity
    if re.search(r"\b(?:him|her|they|it|that|those)\b", text_lower):
        filled_context_keys = [k for k, v in context.items() if v and k.startswith("current_")]
        if len(filled_context_keys) > 1:
            options = []
            for key in filled_context_keys:
                display_key = key.replace("current_", "").replace("_", " ").title()
                options.append({"key": key, "name": str(context[key]), "type": display_key})
            return Ambiguity(
                entity_type="pronoun",
                reference=text,
                options=options[:5],
                context_key=filled_context_keys[0],
            )

    # 3. Check for ambiguous IDs (could match multiple record types)
    id_match = re.search(r"\b([a-f0-9]{8,12})\b", text_lower)
    if id_match and list_records:
        possible_id = id_match.group(1)
        for record_type in ["invoices", "leads", "projects", "sessions"]:
            try:
                records = list_records(record_type)
                matches = [r for r in records if r.get("id", "").startswith(possible_id)]
                if len(matches) > 1:
                    return Ambiguity(
                        entity_type=record_type,
                        reference=possible_id,
                        options=[{"id": r.get("id", ""), "name": str(r.get("name", r.get("title", r.get("client", "?"))))[:40], "type": record_type} for r in matches[:5]],
                    )
            except Exception:
                continue

    return None


def ask_clarification(ambiguity: Ambiguity) -> str:
    """Generate a clarifying question for the user.

    Args:
        ambiguity: The Ambiguity object.

    Returns:
        Formatted clarification question string.
    """
    if ambiguity.entity_type == "client":
        lines = [f"I found multiple clients matching '{ambiguity.reference}':"]
        for i, opt in enumerate(ambiguity.options, 1):
            name = opt.get("name", "?")
            extra = f" — {opt.get('extra', '')}" if opt.get("extra") else ""
            lines.append(f"  {i}. {name}{extra}")
        lines.append("Which one did you mean?")
        return "\n".join(lines)

    if ambiguity.entity_type == "client_spelling":
        original = ambiguity.options[0].get("original", ambiguity.reference)
        corrected = ambiguity.options[0].get("name", "?")
        return (
            f"Did you mean '{corrected}'? (You said '{original}'.)\n"
            f"Reply with 'yes' or 'no'."
        )

    if ambiguity.entity_type == "pronoun":
        lines = ["I'm not sure who/what you're referring to. Options:"]
        for i, opt in enumerate(ambiguity.options, 1):
            entity_type = opt.get("type", "?")
            name = opt.get("name", "?")
            lines.append(f"  {i}. {entity_type}: {name}")
        lines.append("Which one?")
        return "\n".join(lines)

    if ambiguity.entity_type in ("invoices", "leads", "projects", "sessions"):
        lines = [f"Multiple {ambiguity.entity_type} match '{ambiguity.reference}':"]
        for i, opt in enumerate(ambiguity.options, 1):
            name = opt.get("name", "?")
            extra = f" ({opt.get('type', '')})" if opt.get("type") else ""
            lines.append(f"  {i}. {name}{extra}")
        lines.append("Which one?")
        return "\n".join(lines)

    return f"I found multiple options for '{ambiguity.reference}'. Can you be more specific?"


def handle_clarification_reply(reply: str, pending_action: dict) -> dict:
    """Process the user's reply to a clarification question.

    Args:
        reply: The user's response (e.g., "1", "the first one", "Jordan").
        pending_action: The stored pending action context.

    Returns:
        Updated context with the resolved value.
    """
    reply_lower = reply.strip().lower()
    context_updates = {}

    # Handle numbered selection
    number_match = re.match(r"^(?:the\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+one)?$", reply_lower)
    if number_match:
        try:
            index = int(number_match.group(1)) - 1
            if pending_action.get("options") and 0 <= index < len(pending_action["options"]):
                selected = pending_action["options"][index]
                context_key = pending_action.get("context_key")
                if context_key:
                    context_updates[context_key] = selected.get("name", selected.get("key", ""))
                    context_updates["pending_action"] = None
                    context_updates["_clarified"] = True
        except (ValueError, IndexError, TypeError):
            pass

    # Handle "yes" (confirm spelling correction)
    elif reply_lower in ("yes", "yeah", "yep", "sure", "ok", "correct"):
        if pending_action.get("ambiguity_type") == "client_spelling":
            context_key = pending_action.get("context_key")
            corrected_name = pending_action.get("corrected_name")
            if context_key and corrected_name:
                context_updates[context_key] = corrected_name
                context_updates["pending_action"] = None
                context_updates["_clarified"] = True

    # Handle "no" (reject spelling correction)
    elif reply_lower in ("no", "nope", "nah", "cancel"):
        context_updates["pending_action"] = None

    # Handle direct name entry
    elif len(reply) > 1 and not reply_lower.startswith("the "):
        context_key = pending_action.get("context_key")
        if context_key:
            context_updates[context_key] = reply.strip().title()
            context_updates["pending_action"] = None
            context_updates["_clarified"] = True

    return context_updates


# ─── Internal helpers ────────────────────────────────────────────────────


def _extract_possible_name(text: str) -> str | None:
    """Extract a possible client/entity name from the text."""
    text = text.strip()

    # "tell me about X", "who is X", "about X"
    for trigger in [
        "tell me about ", "who is ", "about ",
        "show me ", "find ", "search for ",
    ]:
        if trigger in text.lower():
            idx = text.lower().index(trigger) + len(trigger)
            name = text[idx:].strip().rstrip(".,!?;:")
            if name and len(name) > 1:
                # Filter out common stop words
                if name.lower() not in ("the", "a", "an", "this", "that", "it", "him", "her"):
                    return name

    # Try the last word or phrase that could be a name
    words = [w for w in text.split() if len(w) > 2 and w[0].isupper()]
    if words:
        return words[-1].rstrip(".,!?;:")

    return None


def _fuzzy_match_records(records: list[dict], name: str, name_fields: list[str]) -> list[dict]:
    """Find records that match a name (fuzzy, case-insensitive)."""
    name_lower = name.lower().strip()
    matches = []

    for record in records:
        for field in name_fields:
            record_name = str(record.get(field, "")).lower().strip()
            if not record_name:
                continue
            # Exact match
            if record_name == name_lower:
                matches.append(record)
                break
            # Starts with
            if record_name.startswith(name_lower):
                matches.append(record)
                break
            # Contains
            if name_lower in record_name:
                matches.append(record)
                break
            # Fuzzy: Levenshtein-ish check (first letter + some overlap)
            if _is_spelling_variant(name_lower, record_name):
                matches.append(record)
                break

    return matches


def _is_spelling_variant(a: str, b: str) -> bool:
    """Check if two strings are likely spelling variants of each other.

    Uses a simple length-based threshold:
      - Same first letter
      - Edit-distance-like heuristic based on length difference
      - At least 50% character overlap
    """
    if not a or not b:
        return False
    a = a.lower().strip()
    b = b.lower().strip()

    if a == b:
        return False  # Exact matches handled separately

    # Same first letter
    if a[0] != b[0]:
        return False

    # Length difference no more than 40%
    len_diff = abs(len(a) - len(b))
    if len_diff > min(len(a), len(b)) * 0.4:
        return False

    # At least 60% of characters from the shorter string appear in the longer
    shorter = a if len(a) < len(b) else b
    longer = b if len(a) < len(b) else a
    matches = sum(1 for c in shorter if c in longer)
    return matches / len(shorter) >= 0.6
