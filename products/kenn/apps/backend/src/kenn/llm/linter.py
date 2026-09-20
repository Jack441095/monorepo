"""Linter and sanitization layer for KENN response formatting."""

from __future__ import annotations

import re

# Matches the single SSML pause tag voice-mode LLM answers are allowed to use
# (see llm_rewrite.py's MODE_INSTRUCTIONS["voice"]) -- kept in sync with
# thursday/voice_output.py's _BREAK_TAG_RE (not imported from there: that
# would be a KENN -> Thursday cross-domain dependency for one regex).
_BREAK_TAG_RE = re.compile(r'<break\s+time="(\d+)(ms|s)"\s*/>')


def lint_response(text: str, answer_mode: str = "") -> str:
    """Clean and sanitize response text to guarantee stable, clean formatting.

    For written responses:
      - Removes duplicated or redundant headers.
      - Strips internal error/traceback keywords.

    For voice responses:
      - Strips raw markdown tables, links, bullet points, headers, and hashtags.
      - Keeps the text strictly under 85 words, truncating cleanly at the last sentence.
    """
    if not text:
        return ""

    # Protect <break time="..."/> tags from every filter below, most
    # importantly the voice-mode word-count truncation further down: the tag
    # contains a literal space ("<break time=..."), so text.split() sees it
    # as two separate "words" and the 85-word cutoff can land between them,
    # leaving a bare "<break" fragment that survives to TTS and gets
    # mispronounced. Swapping each tag for a single whitespace-free
    # placeholder makes it exactly one token -- atomic, never split -- and
    # it's restored once every filter has run. Mirrors
    # thursday/voice_output.py's _sanitize_for_speech() protection for the
    # same reason.
    protected_breaks: list[str] = []

    def _protect_break(match: re.Match) -> str:
        protected_breaks.append(match.group(0))
        return f"\x00BREAK{len(protected_breaks) - 1}\x00"

    text = _BREAK_TAG_RE.sub(_protect_break, text)

    # 1. Clean raw internal errors/tracebacks
    for pattern in (r"\[error\]", r"traceback\b", r"database error\b", r"exception occurred\b"):
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # 2. Fix duplicated headings (e.g. double "Short answer:" or mixed # titles)
    text = re.sub(r"^#+\s*Short\s*Answer\b:?", "", text, flags=re.IGNORECASE | re.M)
    text = re.sub(r"^#+\s*Try\s*This\b:?", "", text, flags=re.IGNORECASE | re.M)
    text = re.sub(r"^#+\s*Why\s*it\s*matters\b:?", "", text, flags=re.IGNORECASE | re.M)

    # Strip any consecutive duplicate header labels
    for header in ("Short answer:", "Try this:", "Why it matters:", "Sources:", "You could also ask:"):
        text = re.sub(rf"({header}\s*\n*){{2,}}", r"\1", text, flags=re.IGNORECASE)

    if answer_mode == "voice":
        # Strip markdown tables/grids (lines containing pipe symbols '|' or table dashes '---')
        lines = text.splitlines()
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") or "---" in stripped or stripped.count("|") > 1:
                continue
            clean_lines.append(line)
        text = "\n".join(clean_lines)

        # Strip markdown links: [link text](file://...) -> link text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # Strip markdown symbols, hashtags, headers, bullet characters
        text = re.sub(r"[*#_`~•-]", " ", text)

        # Collapse multiple spaces and newlines into a single space
        text = " ".join(text.split())

        # Enforce maximum word count of 85 words, truncating at a complete sentence boundary
        words = text.split()
        if len(words) > 85:
            truncated = " ".join(words[:85])
            # Match up to the last period, question mark, or exclamation mark
            match = re.search(r".*[.!?]", truncated)
            if match:
                text = match.group(0)
            else:
                text = truncated + "..."
    else:
        text = text.strip()

    text = text.strip()
    for i, tag in enumerate(protected_breaks):
        text = text.replace(f"\x00BREAK{i}\x00", tag)
    return text
