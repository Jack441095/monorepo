"""Follow-up and confirmation state for an in-progress Live change.

We keep this beside the gateway instead of inside ``server.py`` so the HTTP
layer only asks "are we mid-turn?" and "is a proposal waiting?". The chat
context and confirmation store stay the owners: this module reads them, never
writes, so a wrong answer only misroutes one message.

Follow-up handling dates to 26 Sept 2026: "do that on the snare too" and
"3 dB" carry no command verb, yet the gateway knows what they mean while the
chat is mid-turn.
"""

from __future__ import annotations

import re

SAYS_YES = re.compile(r"^\s*(?:yes|yeah|yep|yup|ok(?:ay)?|sure|do\s+it|go\s+ahead|apply(?:\s+(?:it|that|the\s+change))?|"
                       r"confirm(?:\s+it)?|sounds\s+good|please\s+do|go\s+for\s+it)\s*(?:please)?\s*[.!]*\s*$", re.I)


def continues_live_turn(question: str, session_id: str) -> bool:
    """A follow-up, correction or short reply to the Live change this chat is in the middle of.

    "Do that on the snare too", "no, I meant the kick" and "3 dB" don't start with a command verb, so until
    26 Sept 2026 the chat sent them to the notes even though the command gateway knows what they mean.
    """
    from kenn.core.live_command import _CORRECTION, _FOLLOW_UP_MARKER
    from kenn.core.session_context import live_conversation_context

    context = live_conversation_context(session_id)
    text = " ".join(str(question or "").split())
    if context.get("pending_question") and 0 < len(text.split()) <= 6:
        return True
    return bool(context.get("last_command")) and bool(_FOLLOW_UP_MARKER.search(text) or _CORRECTION.match(text))


def proposal_waiting(session_id: str) -> bool:
    """A confirmation the producer has not answered yet (Apply/Undo gate)."""
    from kenn.core.confirmation import pending_confirmation_count

    return pending_confirmation_count(session_id=session_id) > 0
