"""Explicit-only tool-trigger detection for KENN chat (Phase 3 of
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md).

Jack's explicit decision (2026-08-05): KENN runs a registered tool only when
the user names the action directly ("run a mix review on this," "separate
this into stems") -- indirect/inferred phrasing ("this feels muddy, can you
check it") stays a normal chat answer, not a tool trigger. Deliberately
narrow and conservative: a knowledge-base chat that already answers
how-to questions about these exact topics ("how do I run a mix review in
Ableton") must NOT be hijacked into firing the tool instead of answering --
every pattern requires imperative framing and explicitly excludes
question-shaped text.
"""

from __future__ import annotations

import re

# Each pattern requires an imperative verb at/near the start of the request
# -- "run/start/please <verb> a mix review", not just the topic words
# appearing anywhere (which would also match "how do I improve my mix
# review process").
_TRIGGERS: dict[str, list[re.Pattern]] = {
    "run_mix_review": [
        re.compile(r"^(please\s+)?(run|start|do)\s+(a|the)\s+mix\s*review\b", re.I),
        re.compile(r"^(please\s+)?review\s+(this|my|the)\s+(mix|track)\b", re.I),
    ],
    "run_stem_separation": [
        re.compile(r"^(please\s+)?separate\s+(this|it|the track)\s+into\s+stems\b", re.I),
        re.compile(r"^(please\s+)?(run|start|do)\s+stem\s*separation\b", re.I),
        re.compile(r"^(please\s+)?split\s+(this|it|the track)\s+into\s+stems\b", re.I),
    ],
    "run_stem_masking": [
        re.compile(r"^(please\s+)?(run|start|do)\s+(a|the)\s+stem\s+masking\s+(analysis|check)\b", re.I),
        re.compile(r"^(please\s+)?(analyze|analyse|check|scan)\s+(these|the|my)\s+stems\s+for\s+masking\b", re.I),
        re.compile(r"^(please\s+)?review\s+masking\s+between\s+(these|the|my)\s+stems\b", re.I),
    ],
    "run_automix": [
        re.compile(r"^(please\s+)?(run|start|do)\s+(an|the)\s+automix\b", re.I),
        re.compile(r"^(please\s+)?render\s+(an|the)\s+automix\s+pass\b", re.I),
    ],
}

_INTERROGATIVE_START = re.compile(
    r"^(how|what|why|when|where|who|which|can you|could you|would you|does|is|are)\b", re.I
)


def detect_tool_trigger(text: str) -> str | None:
    """Return the registered tool name this message explicitly asks to run,
    or None. Deliberately conservative -- a question-shaped message never
    matches, even if it contains the same keywords, so "how do I run a mix
    review myself" still gets a normal chat answer instead of firing the
    tool."""
    stripped = text.strip()
    if not stripped:
        return None
    if _INTERROGATIVE_START.match(stripped) or stripped.rstrip().endswith("?"):
        return None
    for tool_name, patterns in _TRIGGERS.items():
        if any(pattern.match(stripped) for pattern in patterns):
            return tool_name
    return None
