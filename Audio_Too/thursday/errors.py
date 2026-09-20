"""Error Recovery & Clarification — strategies for handling ambiguous,
missing, or failed requests gracefully.
"""

from __future__ import annotations

from nite_core import PublicError, PublicErrorCode

# ─── Error Types ─────────────────────────────────────────────────────────


class ThursdayError(Exception):
    """Base class for Thursday errors."""
    pass


class AmbiguousEntityError(ThursdayError):
    """Multiple matches found — needs disambiguation."""
    def __init__(self, entity_type: str, options: list[dict]):
        self.entity_type = entity_type
        self.options = options
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        lines = [f"I found multiple matches for {self.entity_type}:"]
        for i, opt in enumerate(self.options, 1):
            name = opt.get("name", opt.get("id", "unknown"))
            extra = ""
            if "email" in opt:
                extra = f" ({opt['email']})"
            elif "service" in opt:
                extra = f" ({opt['service']})"
            lines.append(f"  {i}. {name}{extra}")
        lines.append("Which one did you mean?")
        return "\n".join(lines)


class MissingInfoError(ThursdayError):
    """Required information is missing."""
    def __init__(self, missing_field: str, suggestions: list[str] | None = None):
        self.missing_field = missing_field
        self.suggestions = suggestions or []
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        field_names = {
            "client_name": "a client name",
            "project_name": "a project name",
            "invoice_id": "an invoice ID",
            "review_id": "a review ID",
            "audio_path": "a file or folder path",
            "amount": "an amount",
        }
        field_name = field_names.get(self.missing_field, self.missing_field)
        msg = f"I need {field_name} to look that up."
        if self.suggestions:
            msg += f"\n\nTry: {', '.join(self.suggestions[:3])}"
        else:
            examples = {
                "client_name": "You can say 'tell me about Jordan' or 'check invoices for Sarah'.",
                "invoice_id": "You can say 'show invoice abc12345' or 'check invoice status'.",
                "review_id": "Try 'show review abc12345' or 'check mix review progress'.",
                "audio_path": "Try 'scan audio in ~/Music/my-project'.",
            }
            msg += f"\n\n{examples.get(self.missing_field, '')}"
        return msg


class NoMatchError(ThursdayError):
    """No matching service or record found."""
    def __init__(self, query: str, suggestions: list[str] | None = None):
        self.query = query
        self.suggestions = suggestions or [
            'Search for it',
            'Add it as a new record',
            'Try a different name or phrase',
        ]
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        return (
            f"I couldn't find anything matching '{self.query}'.\n"
            f"Would you like to:\n"
            + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(self.suggestions[:3]))
        )


class ServiceError(ThursdayError):
    """A service failed to execute properly."""
    def __init__(self, service_name: str, original_error: str):
        self.service_name = service_name
        self.original_error = original_error
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        return (
            f"I had trouble running {self.service_name}.\n\n"
            "Try again, or ask me something else."
        )


class ServiceExecutionError(PublicError):
    """A service failed internally; its original exception remains log-only."""

    def __init__(self, service_name: str):
        super().__init__(
            PublicErrorCode.SERVICE_UNAVAILABLE,
            f"Thursday could not complete the {service_name} request.",
            retryable=True,
            http_status=503,
        )


# ─── Recovery Strategies ─────────────────────────────────────────────────


def build_clarification(
    ambiguous: str | None = None,
    missing: str | None = None,
    no_match: str | None = None,
) -> str | None:
    """Build a clarification message based on what's missing/ambiguous."""
    if ambiguous:
        return f"Did you mean: {ambiguous}?"
    if missing:
        return f"I need more information: {missing}."
    if no_match:
        return f"I couldn't find that: {no_match}."
    return None


def suggest_alternatives(text: str) -> list[str]:
    """Suggest alternative phrasings based on common patterns."""
    text_lower = text.lower()
    suggestions = []

    # Check for common patterns and suggest alternatives
    if any(w in text_lower for w in ["how", "what", "why", "when"]):
        suggestions.append("Try asking KENN a production question")

    if any(w in text_lower for w in ["client", "customer"]):
        suggestions.append("Try 'tell me about [client name]'")

    if any(w in text_lower for w in ["invoice", "bill", "payment"]):
        suggestions.append("Try 'show me invoices' or 'check invoice [ID]'")

    if any(w in text_lower for w in ["scan", "analyze", "analyse"]):
        suggestions.append("Try 'scan audio in [folder path]'")

    if not suggestions:
        suggestions = [
            "Try 'how's business' for a health check",
            "Try 'help' to see all options",
            "Or ask a production question like 'how do I sidechain in Ableton?'",
        ]

    return suggestions
