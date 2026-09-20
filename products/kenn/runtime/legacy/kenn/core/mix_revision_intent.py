"""Detect whether a KENN chat message is asking for a mix revision.

Pure text classification, deliberately free of any Business/AutoMix
imports -- this module stays inside the KENN domain package (see
docs/ARCHITECTURE.md's Dependency rule #1: domain packages must not
import route/application-adapter code, and the reverse -- an
application adapter reaching into a domain -- is fine, but a domain
reaching across into another domain's job-queue internals is not).
The actual cross-domain call into automix_jobs.queue_revision lives in
business/app/ableton_bridge.py (an application adapter, already allowed
to depend on multiple domains), mirroring exactly how
audiogen_bridge.prompt_requests_generation() is used from there today.

Deliberately conservative: requires both a recognized mix-topic word
(the same vocabulary apply_revision_feedback() already acts on, so a
detected request is guaranteed to actually produce a change, not a
silent no-op) and a direction/action word, and excludes anything
phrased as a question -- "why is my vocal too quiet" should get an
explanation, not silently queue a mutating job.
"""

from __future__ import annotations

import re

_TOPIC_WORDS = (
    "vocal", "voice", "sing", "lead",
    "bass", "kick", "sub", "low",
    "drum", "snare", "percussion", "beat",
    "bright", "treble", "high", "sizzle", "air",
    "warm", "mud", "box", "mid",
    "reverb", "wet", "roomy", "space", "ambience", "ambient", "dry", "drier", "damp",
)

_ACTION_WORDS = (
    "up", "down", "more", "less", "loud", "quiet", "boost", "cut",
    "bring", "turn", "add", "increase", "decrease", "brighten", "darken",
    "warm", "clear", "make",
)

_QUESTION_STARTS = ("why", "what", "how", "when", "where", "who", "is ", "does ", "can ", "could ", "should ")
# Interrogative words anywhere in the message, not just as the first word --
# "I want to know why my vocal is too quiet" starts with "I", but is still
# a question ("quiet" and "vocal" alone would otherwise satisfy has_topic +
# has_action above and misfire as a revision command).
_QUESTION_WORDS_RE = re.compile(r"\b(why|what|explain|wondering)\b", re.I)
_OUTCOME_REPORT_RE = re.compile(
    r"\b(already\s+tried|tried\s+(?:that|it)|still\s+(?:muddy|harsh|thin|boxy|quiet|loud)|"
    r"no\s+(?:change|difference|luck)|didn'?t\s+work|doesn'?t\s+work|not\s+working)\b",
    re.I,
)


def is_mix_revision_request(text: str) -> bool:
    """True if ``text`` reads as an instruction to change a mix, not a question."""
    if not text or not text.strip():
        return False
    lowered = text.strip().lower()
    if lowered.endswith("?"):
        return False
    if lowered.startswith(_QUESTION_STARTS):
        return False
    if _QUESTION_WORDS_RE.search(lowered):
        return False
    # A report that a prior move failed is diagnostic evidence, not an
    # instruction to mutate the mix.  Without this guard "I already tried
    # EQ cuts and it is still muddy" matched `cut` + `mud` and got routed to
    # an AutoMix action gate instead of allowing KENN to try the next cause.
    if _OUTCOME_REPORT_RE.search(lowered):
        return False
    has_topic = any(word in lowered for word in _TOPIC_WORDS)
    has_action = any(word in lowered for word in _ACTION_WORDS)
    return has_topic and has_action


def strip_revision_phrasing(text: str) -> str:
    """Trim a leading command verb ("make", "turn", "please") some users
    naturally use in chat but that would otherwise read oddly echoed back
    in a confirmation message. Best-effort only -- the full text is still
    what actually gets parsed/applied downstream, this is display-only."""
    cleaned = re.sub(r"^(please\s+)?(can you\s+)?(make|turn|bring)\s+", "", text.strip(), flags=re.I)
    return cleaned or text.strip()
