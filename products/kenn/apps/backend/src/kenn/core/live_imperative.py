"""Typed words that route a chat message to the Live command gateway.

We keep this list beside the gateway instead of inside ``server.py`` so the
HTTP layer stays a thin dispatcher: it asks ``is_live_imperative`` and moves
on, without owning the vocabulary. The gateway still decides proposal, refusal
or undo, so a false positive here only costs a detour, while a false negative
sends "do that on the snare too" to the notes instead of Live.

The verb list was measured from owner rehearsals (Sept 2026): "et the master…"
with a dropped first letter, and swapped neighbours ("dleete"), both reached
the gateway, while "an", "am" and "remote" stayed in chat.
"""

from __future__ import annotations

import re

from kenn.core.live_intent import _within_one_edit

# Imperative Live control phrasing that must reach the typed command gateway
# rather than knowledge chat (e.g. "Focus EQ Eight on track 5", "Undo that.").
LIVE_IMPERATIVE_VERBS = (
    "set", "pan", "focus", "boost", "cut", "raise", "lower", "turn", "mute", "unmute", "solo", "unsolo", "center",
    "centre", "recenter", "recentre", "create", "make", "arm", "disarm", "insert", "add", "rename", "remove", "delete",
    "undo", "duplicate", "group", "select", "put", "bring", "push", "pull", "crank", "drop", "nudge", "tuck", "take",
    "kill", "max", "jump", "fold", "unfold", "toggle",
)
LIVE_IMPERATIVE_RE = re.compile(
    r"^\s*(?:please\s+)?(?:" + "|".join(LIVE_IMPERATIVE_VERBS) + r"|gain[- ]stage)\b",
    re.I,
)

# Ordinary words one letter away from a verb ("an" for "pan", "am" for "arm").
COMMON_SHORT_WORDS = frozenset({"an", "am", "as", "at", "ad", "ma", "pa", "se", "un", "ut", "mat", "ake", "ran", "ut"})


def is_live_imperative(question: str) -> bool:
    """Imperative Live phrasing, allowing a slip in the first word ("et the master…").

    A first word one letter short of a command verb ("et" for "set") or with two
    neighbouring letters swapped still counts; the gateway only takes over for
    a proposal, a refusal or an undo, so anything else still reaches chat.
    """
    text = str(question or "")
    if LIVE_IMPERATIVE_RE.match(text):
        return True
    match = re.match(r"^\s*(?:please\s+)?([A-Za-z]+)\b", text)
    if not match or len(match.group(1)) < 2:
        return False

    first = match.group(1).casefold()
    if first in COMMON_SHORT_WORDS:
        return False
    return any(_within_one_edit(first, verb) for verb in LIVE_IMPERATIVE_VERBS if len(verb) >= 3)
