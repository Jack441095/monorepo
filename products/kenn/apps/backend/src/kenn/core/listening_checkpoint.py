"""Listening-checkpoint mechanism (D2.4, docs/KENN_FUTURE_PLAN.md Phase 2).

When KENN proposes a specific, concrete change it made a judgment call
about -- a mix-revision job it just queued, an EQ-move suggestion it
just surfaced -- it attaches a short checkpoint asking the user to
listen and confirm. The user's VERY NEXT reply, if it reads as a short
yes/no-shaped response, is intercepted before normal chat dispatch runs
(see server.py::_maybe_handle_checkpoint_reply()) and logged as
accept/reject instead of being treated as an ordinary new question.

Pure text classification, deliberately free of any Business/AutoMix
imports -- same domain-boundary reasoning as mix_revision_intent.py.
Deliberately conservative: only a SHORT reply (<= 8 words) starting with
a recognized accept/reject word counts as a checkpoint response. A longer
or unrelated reply falls through to normal chat, and the checkpoint is
cleared either way (see session_memory.clear_pending_checkpoint) so it
can never linger and misinterpret a much later "yes" as an answer to a
stale proposal.
"""

from __future__ import annotations

import re

_MAX_REPLY_WORDS = 8

_ACCEPT_RE = re.compile(
    r"^\s*(yes|yeah|yep|yup|sure|sounds?\s+good|keep\s+it|love\s+it|nice|great|good|works?|"
    r"perfect|that('?s| is)\s+(good|great|better|it))\b",
    re.I,
)
_REJECT_RE = re.compile(
    r"^\s*(no|nah|nope|revert|undo|worse|not\s+(quite|really|it)|try\s+(something|another))\b",
    re.I,
)


def detect_concrete_proposal(payload: dict) -> str:
    """Returns a short description of the concrete change this payload
    just proposed, or "" if it didn't propose one worth a checkpoint.

    Deliberately scoped to INFERRED/suggested perceptual changes -- an EQ
    move KENN chose the specifics of, or a revision job it just queued --
    not every executed DAW write. An explicit, deterministic primitive
    ("mute track 2") is a different category (§1 Principle 3: "explicit
    user-requested primitives... are a different category") where the
    user already knows exactly what happened; asking "did that work?"
    for a toggle they explicitly commanded is redundant, not useful.
    A listening checkpoint earns its place specifically where KENN made
    a judgment call the user can't already predict."""
    if payload.get("contains_unvalidated_suggestions"):
        return "the suggested EQ move"
    automix_revision = payload.get("automix_revision") or {}
    if payload.get("route") == "automix_revision" and payload.get("found") and automix_revision.get("ok"):
        return "the revision once it renders"
    return ""


def classify_checkpoint_reply(text: str) -> str:
    """Returns "accept", "reject", or "" (not a checkpoint-shaped reply,
    fall through to normal chat)."""
    if not text or not text.strip():
        return ""
    stripped = text.strip()
    if len(stripped.split()) > _MAX_REPLY_WORDS:
        return ""
    if _ACCEPT_RE.match(stripped):
        return "accept"
    if _REJECT_RE.match(stripped):
        return "reject"
    return ""
