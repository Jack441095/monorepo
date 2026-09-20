"""Interactive decision branches — yes/no toggles embedded in the answer.

KENN's mode signatures and mode profiles already contain check questions
(e.g. "Did that change help the symptom?"). This module extracts those
decision points and structures them as clickable yes/no branches the user
can take after seeing an answer.

Branch flow:
  1. Answer is generated with a closing signature that asks a question
  2. `extract_branches()` identifies that question and creates DecisionPoints
  3. Frontend renders them as yes/no buttons
  4. User click triggers a contextual follow-up that is tracked in session memory
"""

from __future__ import annotations

import re


class DecisionPoint:
    """A single decision point embedded in the answer.

    Attributes:
        text: The question shown to the user (e.g. "Did this change help the symptom?")
        yes_followup: The query to send if user clicks Yes
        no_followup: The query to send if user clicks No
        mode: The answer mode that produced this decision point
    """
    __slots__ = ("text", "yes_followup", "no_followup", "mode", "id")

    def __init__(
        self,
        text: str,
        yes_followup: str,
        no_followup: str,
        mode: str = "",
    ):
        self.text = text
        self.yes_followup = yes_followup
        self.no_followup = no_followup
        self.mode = mode
        self.id = hash(text) & 0xFFFF  # short stable identifier

    def to_dict(self) -> dict[str, str]:
        return {
            "id": str(self.id),
            "text": self.text,
            "yes": self.yes_followup,
            "no": self.no_followup,
            "mode": self.mode,
        }


# ---------------------------------------------------------------------------
# Decision point definitions per answer mode
# ---------------------------------------------------------------------------

# Each mode maps to one (or more) decision points that appear after the answer
BRANCH_DEFINITIONS: dict[str, list[tuple[str, str, str]]] = {
    "mix_diagnosis": [
        (
            "Did that change help the symptom?",
            "Yes, it helped. What should I check next?",
            "No, it didn't help. What else could be causing this?",
        ),
    ],
    "ableton_steps": [
        (
            "Did that workflow work for you?",
            "Yes, it worked. How do I apply this to other tracks?",
            "No, it didn't work. What is another way to do this?",
        ),
    ],
    "quick_fix": [
        (
            "Did that quick move do what you needed?",
            "Yes, that sorted it. What should I check next?",
            "No, that was not enough. What should I try instead?",
        ),
    ],
    "client_delivery": [
        (
            "Does that cover everything you needed?",
            "Yes, I am ready to send the file.",
            "No, I need more help with the delivery requirements.",
        ),
    ],
    "deep_explanation": [
        (
            "Does the concept make sense in context?",
            "Yes, I understand. How do I apply this in my session?",
            "No, can you explain it differently?",
        ),
    ],
    "dialogue_cleanup": [
        (
            "Did the cleanup preserve the dialogue?",
            "Yes, it sounds natural now.",
            "No, it sounds too processed. How do I back it off?",
        ),
    ],
    "game_audio_implementation": [
        (
            "Does this implementation approach work for your project?",
            "Yes, this is what I needed.",
            "No, my engine setup is different. Can you suggest an alternative?",
        ),
    ],
    "mastering_safety": [
        (
            "Did the level-matched check pass?",
            "Yes, the translation checks pass.",
            "No, it does not translate well. What should I adjust?",
        ),
    ],
    "mix_review_followup": [
        (
            "Does the revision plan make sense for your mix?",
            "Yes, I will start with that change.",
            "No, I need a different approach for this revision.",
        ),
    ],
}


def extract_branches(answer_mode: str) -> list[DecisionPoint]:
    """Return the decision points for the given answer mode.

    Each answer mode has a single decision point by default. Returns an
    empty list if the mode has no branches defined.
    """
    raw = BRANCH_DEFINITIONS.get(answer_mode, [])
    return [DecisionPoint(text=text, yes_followup=yes, no_followup=no, mode=answer_mode)
            for text, yes, no in raw]


def extract_branches_from_answer(answer: str, answer_mode: str = "") -> list[DecisionPoint]:
    """Extract decision points by scanning the answer text.

    Falls back to mode-based branches if nothing can be parsed from the text.
    """
    # First try mode-based lookups
    if answer_mode and answer_mode in BRANCH_DEFINITIONS:
        return extract_branches(answer_mode)

    # Fallback: scan for check-like questions in the text
    lines = answer.splitlines()
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.endswith("?") and any(
            keyword in stripped.lower()
            for keyword in ("did", "does", "is that", "are you", "work", "help", "check", "pass")
        ):
            # General fallback: generic yes/no follow-ups
            return [
                DecisionPoint(
                    text=stripped,
                    yes_followup="Yes. What is the next step?",
                    no_followup="No. What should I try instead?",
                    mode=answer_mode,
                )
            ]

    return []


def branches_payload(answer_mode: str, answer: str) -> list[dict[str, str]]:
    """Build the 'branches' list for the answer payload."""
    branches = extract_branches_from_answer(answer, answer_mode)
    return [b.to_dict() for b in branches]


# ---------------------------------------------------------------------------
# Branch follow-up classifier
# ---------------------------------------------------------------------------

# Terms that indicate a "yes" branch choice
_YES_TERMS = {
    "yes", "yeah", "sorted", "helped", "worked", "pass", "fixed", "great",
    "good", "better", "improved", "solved", "clear", "understood",
}

# Terms that indicate a "no" branch choice
_NO_TERMS = {
    "no", "nah", "not really", "not yet", "still", "worse", "different",
    "unclear", "confused", "try something else", "alternative",
}


def classify_branch_turn(query: str) -> str | None:
    """Classify a follow-up query as a branch response.

    Returns 'yes', 'no', or None if it's not a branch response.
    """
    lowered = query.lower().strip()
    # Extract the first word, stripped of punctuation
    first = re.sub(r"^[^a-z]+|[^a-z]+$", "", lowered.split()[0]) if lowered.strip() else ""
    if first in _YES_TERMS:
        return "yes"
    if first in _NO_TERMS:
        return "no"
    # Also check the full query for single-word responses
    full = re.sub(r"^[^a-z]+|[^a-z]+$", "", lowered)
    if full in _YES_TERMS:
        return "yes"
    if full in _NO_TERMS:
        return "no"
    return None
