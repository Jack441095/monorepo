"""KENN's own voice persona formatting (precise, terse, technically fluent).

Moved out of thursday/personality.py 2026-07-12 (Stage O1): this function
only ever formats KENN's own answers and never touched anything
Thursday-specific (no user_profile, no session state) -- it lived in
thursday/ for historical reasons only. Its transitive import of
thursday.personality (via `from thursday.personality import
format_kenn_voice` in response_contract.py) was a real, hard dependency
that made KENN fail outside a full Thursday-present checkout, found by
actually booting kenn/server.py in isolation, not by reading imports.
"""

from __future__ import annotations

import re


def format_kenn_voice(answer: str, payload: dict) -> str:
    """Format KENN's answer according to KENN Voice Persona (precise, terse, technically fluent)."""
    # 1. Parse confidence/grounding details
    grounding = payload.get("grounding") or {}
    score = grounding.get("score")

    # Try to find a numeric score or default to 90
    if score is None:
        try:
            score = int(payload.get("confidence") or 90)
        except (ValueError, TypeError):
            score = 90

    # Normalize score range
    if isinstance(score, str):
        try:
            score = int(score)
        except ValueError:
            score = 90

    # 2. Check uncertainty phrasing: grounding score < 90 or confidence is weak/low
    is_uncertain = score < 90 or payload.get("weak_match") or payload.get("confidence") in ("low", "weak", "unknown")

    sources = payload.get("sources") or []
    source_label = sources[0].get("label") if (sources and isinstance(sources[0], dict)) else "retrieved notes"

    # Uncertainty phrasing format:
    # "I'm [X]% confident this is correct based on [source]; the manual states [quotation]."
    if is_uncertain:
        # Extract quotation from answer or grounding modes
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if s.strip()]
        quotation = sentences[0] if sentences else "verify settings at matched loudness"
        if not quotation.endswith("."):
            quotation += "."
        # Format the precise uncertainty phrase
        uncertain_phrase = f"I'm {score}% confident this is correct based on {source_label}; the manual states: {quotation}"
        if len(sentences) > 1:
            answer = uncertain_phrase + " " + " ".join(sentences[1:])
        else:
            answer = uncertain_phrase

    # 3. Terminology cleanup: ensure precise, terse, technically fluent (no pleasantries)
    pleasantries = [
        "hope this helps", "let me know if", "feel free to", "glad to help",
        "sure thing", "here you go", "i would suggest", "maybe try"
    ]
    for p in pleasantries:
        answer = re.sub(r"(?i)\b" + re.escape(p) + r"\b[^.!?]*[.!?]?", "", answer)

    answer = answer.strip()

    words = answer.split()
    if len(words) >= 85:
        truncated = []
        word_count = 0
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if s.strip()]
        for s in sentences:
            s_words = s.split()
            if word_count + len(s_words) + 6 < 85:
                truncated.append(s)
                word_count += len(s_words)
            else:
                break

        if not truncated:
            truncated = words[:75]
            answer = " ".join(truncated) + "... [truncated]. Tell me more for additional details."
        else:
            answer = " ".join(truncated) + " Tell me more for additional details."

    return answer
