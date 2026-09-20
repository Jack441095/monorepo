"""Shared quality checks used before a KENN note can be approved."""

from __future__ import annotations

import re

REQUIRED_SECTIONS = ("Short answer", "Try this", "Why it matters", "Related questions")
PLACEHOLDER_PATTERNS = (
    "write the practical idea",
    "answer this question in your own words",
    "replace this sentence",
    "add one plausible mistake",
    "rephrase the original question",
)


def _field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.*?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


_KNOWN_HEADINGS = (
    "short answer",
    "try this",
    "why it matters",
    "common mistakes",
    "when this does not apply",
    "related questions",
)


def _section(text: str, name: str) -> str:
    # Prefix match, not exact match: e.g. automix-reverb-and-delay-sends.md's
    # real "Try this" heading is "Try this -- default reverb sends by
    # instrument:", not bare "Try this:". chat_formatting.py::section_lines()
    # was already loosened to a prefix match for exactly this case
    # (2026-08-03); this audit function used a stricter exact-line pattern
    # and was flagging dozens of genuinely well-formed, already-approved
    # notes (including automix-compression-ratios.md) as missing sections
    # they actually have -- found 2026-08-06 running knowledge-audit.
    #
    # The stop-boundary previously matched ANY line consisting only of
    # letters/spaces ending in a colon -- which also matches ordinary body
    # prose that happens to end a sentence with a colon before a list (e.g.
    # "...depending on the client type:"), truncating the body to empty at
    # the very first such sentence. Found the same day auditing
    # jack-export-specs.md, a real note wrongly flagged as having no Short
    # answer despite visibly having one. Restricted the stop-boundary to
    # only the known heading names, matching chat_formatting.py's
    # section_lines() (the version this logic was originally copied from),
    # which already enumerates them for exactly this reason.
    headings = "|".join(re.escape(h) for h in _KNOWN_HEADINGS)
    match = re.search(
        rf"^{re.escape(name)}\b[^\n]*:\s*\n(?P<body>.*?)"
        rf"(?=^(?:{headings})\b[^\n]*:\s*(?:\n|$)|\Z)",
        text,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return match.group("body").strip() if match else ""


def validate_note_for_approval(text: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if not re.search(r"^#\s+\S", text, re.MULTILINE):
        errors.append("Add one H1 title (# Title).")
    for field in ("Type", "Tags"):
        if not _field(text, field):
            errors.append(f"Add a non-empty {field}: field.")
    for heading in REQUIRED_SECTIONS:
        if not _section(text, heading):
            errors.append(f"Complete the {heading}: section.")
    lowered = text.lower()
    placeholders = [pattern for pattern in PLACEHOLDER_PATTERNS if pattern in lowered]
    if placeholders:
        errors.append("Replace template placeholder text before approval.")
    source_values = [_field(text, key) for key in ("Source", "Source title", "Source URL", "Source ID")]
    if not any(source_values):
        warnings.append("Add a provenance field, for example Source: Audio_Too studio practice.")
    reviewed = _field(text, "Reviewed")
    if not reviewed:
        warnings.append("Add Reviewed: YYYY-MM-DD so stale guidance can be audited.")
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed):
        warnings.append("Use Reviewed: YYYY-MM-DD.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}
