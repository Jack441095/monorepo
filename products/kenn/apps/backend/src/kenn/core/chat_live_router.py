"""Does a chat message ask KENN to change Live, or ask how to do something?

Measured on 26 Sept 2026 by sending every labelled phrasing through the chat of a fake-Live KENN: only 61% of the
1,072 requests that should change Live reached Live ("can you solo the hats?", "bump the synth up 1 dB" got a notes
page, because the chat only recognised a fixed list of opening verbs), while 44 of 481 knowledge questions were taken
over by Live ("I'm mixing vocals and they sound muddy. How can I make them clearer?" became a proposal to turn the
Synth down). The rule parser already reads 94% of the requests correctly, so it decides, and asking how is kept for
the notes whatever else the message names.
"""

from __future__ import annotations

import re
from typing import Any

# Asking how, wherever it sits in the message: "My drums rumble. What's a quick way to clean them up?"
_HOW_TO = re.compile(
    r"\bhow\s+(?:can|do|should|would|could|might)\s+(?:i|we|you)\b|\bhow\s+to\b|\bhow\s+would\s+you\b"
    r"|\bwhat(?:'s|\s+is)?\s+(?:a|the)\s+(?:good|quick|best|easy|simple|clean|right|proper)\s+way\b"
    r"|\b(?:is|are)\s+there\s+(?:a|any)\s+(?:way|trick|tips?)\b|\bany\s+(?:tips|ideas|advice)\b"
    r"|\b(?:need|want|looking\s+for)\s+(?:a|some)\s+(?:way|method|technique|trick)s?\b"
    r"|\bwhat\s+(?:can|should|do|could)\s+i\b|\bwhat\s+(?:kind|type|sort)s?\s+of\b|\bwhat\s+would\s+you\b"
    r"|\bshould\s+i\b|\bexplain\b|\bteach\s+me\b|\bshow\s+me\s+how\b|\bwalk\s+me\s+through\b"
    r"|\bwhy\s+(?:is|does|do|are|would|can't|won't|doesn't)\b|\bwhat\s+(?:does|do)\s+\w+(?:\s+\w+)?\s+do\b"
    r"|\bdifference\s+between\b|\bwhat\s+causes\b|\bi(?:'m|\s+am)\s+not\s+sure\s+how\b"
    r"|\bdo\s+you\s+think\b|\bwould\s+(?:it|that)\s+help\b|\bi\s+wonder\b"
    # A wish with a condition is asking for advice: "more depth without it sounding muddy", "I want X, but not Y".
    r"|\bwithout\s+(?:losing|changing|making|affecting|ruining|killing|muddying|sounding|getting|"
    r"it\s+(?:sounding|getting|becoming))\b|\bi\s+(?:want|'d\s+like|would\s+like)\b[^.?!]*\bbut\b",
    re.I,
)
# Missing fields that still mean the parser found a Live change: the cached snapshot lacks the current fader level, or
# a send was named without an amount.
LIVE_WITHOUT_ACTION = frozenset({"current_volume", "send_amount", "negated", "deferred", "device_action",
                                 "return_track_action", "single_action"})


_RETURN_HINT = re.compile(r"\b(?:sends?|returns?|reverb|verb|delay|echo|aux)\b|\b[a-h]-[a-z]+\b", re.I)
_MIXER_VERB = re.compile(r"\b(?:mute|unmute|solo|pan|louder|quieter|volume|level|lower|raise|turn|bring|drop|boost|cut|set|up|down|db)\b",
                         re.I)


def needs_return_tracks(text: str, snapshot: dict[str, Any] | None) -> bool:
    """Whether to read the return tracks before parsing this message.

    Real Live's session snapshot never lists them (they're a separate read), so "lower the A-Reverb by 1 dB" parsed
    against an empty list and went to the mix notes; only "send" messages fetched them. The fake backend's snapshot
    carries them, which is why the fake walkthrough passed and the first real one didn't (30 Sept 2026). A return can
    have any name, so any message with a mixer verb in it counts.
    """
    if isinstance(snapshot, dict) and snapshot.get("return_tracks"):
        return False
    return bool(_RETURN_HINT.search(str(text or "")) or _MIXER_VERB.search(str(text or "")))


def asks_how_to(text: str) -> bool:
    from kenn.core.live_intent import LATER_CHANGE_REQUEST

    text = str(text or "")
    found = _HOW_TO.search(text)
    return bool(found) and not LATER_CHANGE_REQUEST.search(text[found.end():])


def wants_live_change(text: str, snapshot: dict[str, Any] | None) -> bool:
    """True when the rule parser reads a Live action in the message and it isn't asking how."""
    if not isinstance(snapshot, dict) or snapshot.get("status") != "connected" or asks_how_to(text):
        return False
    from kenn.core.live_intent import parse_request

    intent = parse_request(str(text or ""), snapshot)
    missing = set(intent.get("missing_fields") or [])
    if "how_to" in missing:
        return False
    return bool(intent.get("action")) or bool(missing & LIVE_WITHOUT_ACTION)


__all__ = ["LIVE_WITHOUT_ACTION", "asks_how_to", "needs_return_tracks", "wants_live_change"]
