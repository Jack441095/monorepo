"""Project memory advisory, matching, and explicit preference extraction.

Per KENN North Star Stage 4:
- Project memory: decisions, references, what was tried, kept per Live set.
- Opt-in producer preferences ("I like my vocals bright", "I master to -9 LUFS"), always cited when used.
- Memory view in the UI: see, edit, delete; nothing learned silently.
- Gate: testers can find and delete any memory; memory-using answers cite the memory; no cross-project leaks.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from kenn.core.assistant_profile_memory import AssistantProfileStore, PREFERENCE_KEYS


_KEYWORD_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\b(?:like\s+my\s+vocals?\s+bright|bright\s+vocals?|vocals?\s+bright)\b", re.I), "creative_direction", "vocals bright"),
    (re.compile(r"\b(?:master\s+to\s+(-?\d+\s*lufs)|target\s+(-?\d+\s*lufs)|-?\d+\s*lufs\s+master)\b", re.I), "workflow", "master to -9 LUFS"),
    (re.compile(r"\b(?:mix(?:ing)?\s+on\s+headphones|use\s+headphones|listen\s+on\s+headphones)\b", re.I), "monitoring", "headphones"),
    (re.compile(r"\b(?:mix(?:ing)?\s+on\s+monitors|use\s+monitors|studio\s+monitors)\b", re.I), "monitoring", "monitors"),
    (re.compile(r"\b(?:vocals?\s+forward|vocal\s+priority)\b", re.I), "mix_priority", "vocals forward"),
    (re.compile(r"\b(?:warm\s+and\s+vintage|vintage\s+tone|warm\s+sound)\b", re.I), "creative_direction", "warm and vintage"),
    (re.compile(r"\b(?:punchy\s+drums?|drums?\s+punchy)\b", re.I), "creative_direction", "punchy drums"),
]

_EXPLICIT_SET_PREFIX = re.compile(
    r"^(?:please\s+)?(?:remember(?:\s+that|\s+for\s+this\s+project)?|note(?:\s+that)?|set\s+preference|save\s+preference)[:\s]+",
    re.I,
)

_DIRECT_KEY_VALUE = re.compile(
    r"^(?:set\s+preference\s+|preference\s+)?([a-z_]+)\s*[:=]\s*(.+)$",
    re.I,
)

_SHOW_MEMORY_PATTERNS = re.compile(
    r"^(?:show|what\s+do\s+you\s+remember|what\s+are\s+my\s+preferences|view|list|get)\s+(?:about\s+this\s+project|project\s+memory|my\s+preferences|preferences|memory)\??$",
    re.I,
)

_CLEAR_MEMORY_PATTERNS = re.compile(
    r"^(?:clear|forget|delete|reset)\s+(?:all\s+)?(?:project\s+memory|preferences|my\s+preferences|memory)$",
    re.I,
)

_FORGET_PREF_PATTERNS = re.compile(
    r"^(?:forget|delete|remove)\s+(?:preference\s+|my\s+preference\s+(?:for\s+)?)([a-z0-9_]+)$",
    re.I,
)


def parse_explicit_preference(text: str) -> tuple[str, str, str] | None:
    """Extract an explicit, opt-in producer preference from user text.

    Returns (key, value, clean_statement) or None if no explicit preference is declared.
    """
    clean = text.strip()
    if not clean:
        return None

    stripped = _EXPLICIT_SET_PREFIX.sub("", clean).strip()

    # Direct key: value pattern (e.g. "set preference creative_direction: vocals bright")
    direct = _DIRECT_KEY_VALUE.match(stripped)
    if direct:
        k = direct.group(1).lower().strip()
        v = direct.group(2).strip()
        if k in PREFERENCE_KEYS and v:
            return k, v, clean

    # Keyword rules
    target_text = stripped or clean
    for pat, key, val in _KEYWORD_RULES:
        m = pat.search(target_text)
        if m:
            if pat.groups:
                # Only the LUFS rules carry capture groups, because there the
                # producer states the number: "I master to -14 LUFS" must store
                # -14, not the canned example. record_preference rejects any
                # value missing verbatim from the statement, so keep the matched
                # text as spoken. The old placeholder check for a backslash-1
                # marker never fired (no rule value ever contained it), so every
                # real target stored "master to -9 LUFS" and then failed that check.
                val = m.group(0)
            return key, val, clean

    return None


def match_preferences_for_query(query: str, preferences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Determine which active preferences are relevant to a user query."""
    if not query or not preferences:
        return []

    q_lower = query.lower()
    q_tokens = set(re.findall(r"\b[a-z0-9_-]+\b", q_lower))
    stemmed_q = set()
    for t in q_tokens:
        stemmed_q.add(t)
        if t.endswith("s") and len(t) > 3:
            stemmed_q.add(t[:-1])

    matches: list[dict[str, Any]] = []

    for pref in preferences:
        key = pref.get("key", "")
        val = str(pref.get("value", "")).lower()
        val_tokens = set(re.findall(r"\b[a-z0-9_-]+\b", val)) - {
            "i", "my", "the", "a", "an", "to", "for", "in", "on", "like", "want", "prefer", "this",
        }
        stemmed_val = set()
        for t in val_tokens:
            stemmed_val.add(t)
            if t.endswith("s") and len(t) > 3:
                stemmed_val.add(t[:-1])

        is_match = False

        if stemmed_q.intersection(stemmed_val):
            is_match = True

        if not is_match:
            if key == "monitoring" and any(w in q_lower for w in ("monitor", "monitoring", "headphone", "headphones", "cans", "listening", "stereo field")):
                is_match = True
            elif key == "workflow" and any(w in q_lower for w in ("workflow", "master", "mastering", "lufs", "gain stage", "level", "limiter", "ceiling")):
                is_match = True
            elif key == "creative_direction" and any(w in q_lower for w in ("tone", "vibe", "style", "sound", "aesthetic", "creative", "bright", "warm", "punchy")):
                is_match = True
            elif key == "mix_priority" and any(w in q_lower for w in ("priority", "balance", "mix", "level", "focus", "forward")):
                is_match = True
            elif key == "genre" and (val in q_lower or "genre" in q_lower or "style" in q_lower):
                is_match = True
            elif key == "reference_track" and any(w in q_lower for w in ("reference", "ref", "compare")):
                is_match = True

        if is_match:
            matches.append(pref)

    return matches


def format_preference_citation(preferences: list[dict[str, Any]]) -> str:
    """Format an explicit citation of project preferences for answer prose."""
    if not preferences:
        return ""
    if len(preferences) == 1:
        p = preferences[0]
        return f"\n\nNoting your preference for this project: {p['value']} ({p['key'].replace('_', ' ')})."
    lines = [f"- {p['key'].replace('_', ' ').title()}: {p['value']}" for p in preferences]
    return "\n\nNoting your preferences for this project:\n" + "\n".join(lines)


def evaluate_memory_chat_intent(
    query: str,
    *,
    session_id: str = "",
    store: AssistantProfileStore | None = None,
) -> dict[str, Any] | None:
    """Evaluate whether a chat query is an explicit memory management command."""
    clean = query.strip()
    if not clean:
        return None

    profile_store = store or AssistantProfileStore()

    # 1. View memory
    if _SHOW_MEMORY_PATTERNS.match(clean) or clean.lower() in {"show memory", "project memory", "my preferences"}:
        if not session_id:
            return {
                "answer": "Project memory is scoped to a specific Ableton Live set. Connect or specify a session to view its saved preferences.",
                "route": "conversation",
                "confidence": "high",
                "sources": [],
                "applied_preferences": [],
                "requires_confirmation": False,
            }
        prefs = profile_store.current_preferences(session_id)
        episodes = profile_store.recent_episodes(session_id)
        if not prefs and not episodes:
            return {
                "answer": (
                    "No project preferences or episodic memories are saved for this Live set yet. "
                    "Tell me what you prefer (e.g. 'I like my vocals bright' or 'I master to -9 LUFS') "
                    "and I'll remember it for this session."
                ),
                "route": "conversation",
                "confidence": "high",
                "sources": [],
                "applied_preferences": [],
                "requires_confirmation": False,
            }

        sections = []
        if prefs:
            pref_lines = [f"- **{p['key'].replace('_', ' ').title()}**: {p['value']}" for p in prefs]
            sections.append("### Active Preferences for this Project:\n" + "\n".join(pref_lines))
        if episodes:
            ep_lines = [f"- {e.get('goal', 'Task')}: verdict `{e.get('verdict')}` ({e.get('comment', '')})" for e in episodes]
            sections.append("### Recent Outcomes for this Project:\n" + "\n".join(ep_lines))

        sections.append("\n*These memories are advisory, never shared across projects, and cited whenever used. You can edit or delete them anytime.*")
        return {
            "answer": "\n\n".join(sections),
            "route": "conversation",
            "confidence": "high",
            "sources": [],
            "applied_preferences": prefs,
            "requires_confirmation": False,
        }

    # 2. Clear memory
    if _CLEAR_MEMORY_PATTERNS.match(clean):
        if not session_id:
            return {
                "answer": "No session ID was provided. Project memory requires a session ID to clear.",
                "route": "conversation",
                "confidence": "high",
                "sources": [],
                "applied_preferences": [],
                "requires_confirmation": False,
            }
        cleared = profile_store.clear_profile(session_id)
        return {
            "answer": f"Project memory cleared for this session ({cleared.get('preferences', 0)} preferences and {cleared.get('episodes', 0)} episodes removed).",
            "route": "conversation",
            "confidence": "high",
            "sources": [],
            "applied_preferences": [],
            "requires_confirmation": False,
        }

    # 3. Forget single preference
    forget_m = _FORGET_PREF_PATTERNS.match(clean)
    if forget_m:
        target_word = forget_m.group(1).lower()
        if not session_id:
            return {
                "answer": "No session ID was provided. Project memory requires a session ID.",
                "route": "conversation",
                "confidence": "high",
                "sources": [],
                "applied_preferences": [],
                "requires_confirmation": False,
            }
        matched_key = None
        if target_word in PREFERENCE_KEYS:
            matched_key = target_word
        else:
            for p in profile_store.current_preferences(session_id):
                if target_word in p["key"] or target_word in p["value"].lower():
                    matched_key = p["key"]
                    break
        if matched_key:
            profile_store.forget_preference(session_id=session_id, key=matched_key)
            return {
                "answer": f"Forgotten. Removed preference `{matched_key}` from this project's memory.",
                "route": "conversation",
                "confidence": "high",
                "sources": [],
                "applied_preferences": [],
                "requires_confirmation": False,
            }
        return {
            "answer": f"No active preference matching '{target_word}' was found in this project's memory.",
            "route": "conversation",
            "confidence": "high",
            "sources": [],
            "applied_preferences": [],
            "requires_confirmation": False,
        }

    # 4. Explicit preference setting
    parsed = parse_explicit_preference(clean)
    if parsed:
        key, value, statement = parsed
        if not session_id:
            return {
                "answer": (
                    f"Got it: {key.replace('_', ' ')} — {value}. "
                    "Connect an Ableton Live set so I can attach this preference to the project."
                ),
                "route": "conversation",
                "confidence": "high",
                "sources": [],
                "applied_preferences": [],
                "requires_confirmation": False,
            }

        turn_id = f"turn-{uuid4().hex[:8]}"
        res = profile_store.record_preference(
            session_id=session_id,
            key=key,
            value=value,
            source_turn_id=turn_id,
            user_statement=statement,
        )
        if res.get("ok"):
            pref = res["preference"]
            return {
                "answer": (
                    f"Saved to project memory: **{key.replace('_', ' ').title()}** — *{value}*. "
                    "I will cite this whenever advising on this project. "
                    "You can view, edit, or delete this in Project Memory anytime."
                ),
                "route": "conversation",
                "confidence": "high",
                "sources": [],
                "applied_preferences": [pref],
                "requires_confirmation": False,
            }

    return None
