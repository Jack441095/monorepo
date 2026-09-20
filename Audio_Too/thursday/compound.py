"""Compound Request Parser — splits compound requests into atomic actions.

Allows Thursday to parse and execute multi-part requests like:
  - "Invoice Jordan and tell me about Sarah"
  - "Check my pipeline and remind me to email Jordan"
  - "What's on my calendar? Also scan my audio files."

Uses conjunction detection and dependency analysis to split requests
into individual actionable parts.
"""

from __future__ import annotations

import re

# Conjunctions that typically separate independent requests
CONJUNCTIONS = [
    " and then ",
    " && ",
    " & ",
    " + ",
    ", then ",
    "; also ",
    ", also ",
]

# Conjunctions that indicate a compound WITHIN a single action
# (e.g., "draft an email and invoice" is one action with two outputs)
GROUPING_CONJUNCTIONS = [
    " and also ",
]

# Single " and " connector (handled specially to avoid false positives)
SIMPLE_AND = " and "

# Sequential markers that indicate order matters
SEQUENTIAL_MARKERS = [
    r"\b(?:first|then|next|after that|finally|lastly)\b",
]


def is_compound(text: str) -> bool:
    """Detect whether a request contains multiple separate actions.

    Args:
        text: The raw user input.

    Returns:
        True if the text appears to contain multiple requests.
    """
    try:
        from app.audiogen_bridge import requests_automix_chain
        if requests_automix_chain(text):
            return False
    except ImportError:
        pass

    text_lower = text.lower().strip()

    # Check for explicit multi-part conjunctions
    for conj in CONJUNCTIONS:
        if conj in text_lower:
                return True

    # Check for " and " as a conjunction between two different actions
    if SIMPLE_AND in text_lower:
        # Verify the text doesn't use the grouped conjunction variant
        if SIMPLE_AND not in text_lower or all(gc not in text_lower for gc in GROUPING_CONJUNCTIONS):
            # Verify there are multiple verbs/actions on either side of "and"
            parts = text_lower.split(SIMPLE_AND)
            if len(parts) >= 2:
                left_verbs = _extract_action_verbs(parts[0].strip())
                right_verbs = _extract_action_verbs(parts[1].strip())
                if left_verbs and right_verbs:
                    return True

    # Check for serial commas + conjunctions
    parts = _split_by_serial_comma(text_lower)
    if len(parts) > 1:
        return True

    # Check for sequential markers
    if len(re.findall(r"(?:^|\s)(?:first|then|next|finally|lastly)\b", text_lower)) > 0:
        # Only if there are multiple verbs/actions
        verbs = _extract_action_verbs(text_lower)
        if len(verbs) > 1:
            return True

    return False


def split_compound_request(text: str) -> list[str]:
    """Split a compound request into individual atomic requests.

    Handles various conjunction patterns and cleans up each part.

    Args:
        text: The raw user input (e.g., "Invoice Jordan and tell me about Sarah").

    Returns:
        List of individual request strings.
    """
    try:
        from app.audiogen_bridge import requests_automix_chain
        if requests_automix_chain(text):
            return [text]
    except ImportError:
        pass

    text_lower = text.lower().strip()

    # First try to split by serial comma patterns
    # e.g., "do X, do Y, and do Z"
    parts = _split_by_serial_comma(text_lower)
    if len(parts) > 1:
        return [p.strip().rstrip(".,") for p in parts if _is_valid_part(p)]

    # Try splitting by standard conjunctions (longest first)
    sorted_conjunctions = sorted(CONJUNCTIONS, key=len, reverse=True)
    for conj in sorted_conjunctions:
        if conj in text_lower:
            parts = text_lower.split(conj)
            cleaned = [p.strip().rstrip(".,;: ") for p in parts if _is_valid_part(p)]
            if len(cleaned) > 1:
                return cleaned

    # Split by " and " if both sides have action verbs
    if SIMPLE_AND in text_lower and all(gc not in text_lower for gc in GROUPING_CONJUNCTIONS):
        parts = text_lower.split(SIMPLE_AND)
        if len(parts) >= 2:
            left_verbs = _extract_action_verbs(parts[0].strip())
            right_verbs = _extract_action_verbs(parts[1].strip())
            if left_verbs and right_verbs:
                return [p.strip().rstrip(".,;: ") for p in parts if _is_valid_part(p)]

    # Check for sequential markers
    seq_parts = re.split(r"(?:,?\s*(?:then|next|after that)\s*,?|;\s*and\s+)", text_lower)
    seq_parts = [p.strip().rstrip(".,;: ") for p in seq_parts if _is_valid_part(p)]
    if len(seq_parts) > 1:
        return seq_parts

    # No compound detected — return as-is
    return [text]


def is_sequential(text: str) -> bool:
    """Check if the parts should be executed in order (vs. independently).

    Sequential requests use words like 'then', 'next', 'after that'.

    Args:
        text: The raw user input.

    Returns:
        True if the compound request is sequential.
    """
    for marker in SEQUENTIAL_MARKERS:
        if re.search(marker, text, re.IGNORECASE):
            return True
    return False


def _split_by_serial_comma(text: str) -> list[str]:
    """Split text by serial comma patterns.

    Handles: "do X, do Y, and do Z" → ["do X", "do Y", "do Z"]
    """
    # Pattern: word, word, and/or word
    # Match the full serial list pattern
    serial_pattern = re.compile(
        r"^((?:\w[^,]+),\s*(?:\w[^,]+)(?:,\s*(?:\w[^,]+))*),\s+(?:and|or)\s+(\w.+)$",
        re.IGNORECASE,
    )
    m = serial_pattern.match(text)
    if m:
        prefix = m.group(1)
        last = m.group(2)
        # Split the prefix by commas
        pre_parts = [p.strip() for p in prefix.split(",")]
        return pre_parts + [last]

    # Simpler: just split on ", " and check for "and" before last
    if ", " in text and " and " in text:
        # Try to split on ", " first
        comma_parts = text.split(", ")
        result = []
        for part in comma_parts:
            if " and " in part and not any(part.startswith(w) for w in ("and ", "or ")):
                sub_parts = part.split(" and ")
                result.extend([s.strip().rstrip(".,") for s in sub_parts if _is_valid_part(s)])
            else:
                cleaned = part.strip().rstrip(".,")
                # Remove leading "and " or "or "
                for prefix in ("and ", "or ", "& "):
                    if cleaned.lower().startswith(prefix):
                        cleaned = cleaned[len(prefix):].strip()
                if _is_valid_part(cleaned):
                    result.append(cleaned)
        return result

    return [text]


def _extract_action_verbs(text: str) -> list[str]:
    """Extract action-oriented verbs from text.

    Returns a list of verbs (lowercase) found in the text.
    """
    action_verbs = [
        "invoice", "tell", "show", "check", "scan", "generate",
        "make", "create", "draft", "send", "remind", "schedule",
        "book", "analyse", "analyze", "find", "search", "list",
        "add", "update", "delete", "cancel", "retry", "publish",
        "compare", "run", "export", "save", "record", "promote",
        "approve", "rebuild", "refresh", "load", "open",
    ]
    found = []
    for verb in action_verbs:
        if re.search(rf"\b{verb}\b", text, re.IGNORECASE):
            if verb not in found:
                found.append(verb)
    return found


def _is_valid_part(part: str) -> bool:
    """Check if a split part is a valid action and not a connector."""
    text = part.strip().lower()
    if not text or len(text) < 2:
        return False
    # Skip purely connector words
    if text in ("and", "or", "also", "then", "&"):
        return False
    # Must have at least one meaningful word
    if re.match(r"^[\s,;:.!?]+$", text):
        return False
    return True


# ─── Queue Manager ────────────────────────────────────────────────────────


class CompoundQueue:
    """Manages sequential execution of compound request parts.

    Each part is processed one at a time, with results accumulated.
    Supports asking the user for clarification between parts.
    """

    def __init__(self, parts: list[str], is_sequential: bool = False):
        self.parts = parts
        self.is_sequential = is_sequential
        self.current_index = 0
        self.results: list[str] = []
        self.is_active = bool(len(parts) > 0)

    @property
    def current_part(self) -> str | None:
        if self.current_index < len(self.parts):
            return self.parts[self.current_index]
        return None

    @property
    def remaining(self) -> list[str]:
        return self.parts[self.current_index:]

    @property
    def is_done(self) -> bool:
        return self.current_index >= len(self.parts)

    def advance(self) -> str | None:
        """Move to the next part and return it (or None if done)."""
        self.current_index += 1
        return self.current_part

    def add_result(self, result: str) -> None:
        """Accumulate a result from processing a part."""
        self.results.append(result)

    def summarize(self) -> str:
        """Combine all results into a single response.

        Separates results with blank lines and sequential numbering.
        """
        if not self.results:
            return "No results from compound request."

        if len(self.results) == 1:
            return self.results[0]

        parts = []
        for i, result in enumerate(self.results, 1):
            if self.is_sequential:
                parts.append(f"Step {i}:\n{result}")
            else:
                parts.append(result)
        return "\n\n".join(parts)
