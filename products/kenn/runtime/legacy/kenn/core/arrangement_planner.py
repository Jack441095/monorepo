"""Conversational arrangement assistance (D3.4, docs/KENN_FUTURE_PLAN.md
Phase 3): "build a 32-bar verse/chorus structure with a build-up at bar
17" -> a suggested section-by-section plan, using the requested bar
numbers directly (never invented) and standard, well-established song-
form convention for how to label/split sections. This is explicitly a
starting SUGGESTION, not a claimed-correct arrangement -- deliberately
conservative in scope to avoid overclaiming musical authority the plan's
own North Star Principles (§1: no claim exceeds the evidence) guard
against elsewhere. A user says what direction to take it from here in
conversation; this doesn't try to be a taste-driven composition tool.

Pure text/structure logic, deliberately free of any DAW/Business
imports -- same domain-boundary reasoning as mix_revision_intent.py and
listening_checkpoint.py. The actual cross-domain call to create real
Ableton scenes lives in the caller (autonomous_agent.py).
"""

from __future__ import annotations

import re

_REQUEST_RE = re.compile(
    r"\b(?:build|create|make)\b.*\b(\d+)[\s-]?bars?\b.*\b(?:structure|arrangement|section)\b"
    r"|\b(\d+)[\s-]?bars?\b.*\b(?:verse|chorus|structure|arrangement)\b",
    re.I,
)
_BUILD_UP_RE = re.compile(r"\bbuild[\s-]?up\b.*?\bbar\s*(\d+)\b", re.I)


def parse_arrangement_request(text: str) -> dict | None:
    """Returns {"total_bars": int, "build_up_bar": int | None} if ``text``
    reads as a request to build a bar-count-specified structure, else
    None. Deliberately requires an explicit bar count AND a structure/
    arrangement word -- "how long should my intro be" has neither a bar
    count tied to a structure request nor should fire this."""
    if not text or not text.strip():
        return None
    match = _REQUEST_RE.search(text)
    if not match:
        return None
    total_bars = int(match.group(1) or match.group(2))
    if total_bars < 4 or total_bars > 512:
        return None
    build_match = _BUILD_UP_RE.search(text)
    build_up_bar = int(build_match.group(1)) if build_match else None
    if build_up_bar is not None and not (1 <= build_up_bar <= total_bars):
        build_up_bar = None
    return {"total_bars": total_bars, "build_up_bar": build_up_bar}


def suggest_song_structure(total_bars: int, build_up_bar: int | None = None) -> list[dict]:
    """Returns an ordered list of {"name", "start_bar", "length_bars"}
    sections spanning exactly ``total_bars``, 1-indexed.

    With a build-up bar given, uses the bar number the user actually
    specified as the split point (not invented) -- a 3-section
    Groove/Build-up/Drop shape, a standard electronic-music convention:
    - Groove: bar 1 up to the build-up bar
    - Build-up: a short section starting at the given bar (min(4, remaining))
    - Drop: the rest

    Without one, uses a standard verse/chorus proportional split
    (Intro 12.5% / Verse 37.5% / Chorus 37.5% / Outro 12.5%, each at
    least 1 bar, remainder folded into Chorus) -- a common pop/
    electronic song-form convention, not a specific creative claim about
    what THIS song should be."""
    total_bars = max(4, int(total_bars))
    if build_up_bar is not None and 1 <= build_up_bar <= total_bars:
        groove_len = build_up_bar - 1
        remaining_after_groove = total_bars - groove_len
        build_len = min(4, max(1, remaining_after_groove - 1))
        drop_len = total_bars - groove_len - build_len
        sections = []
        bar = 1
        if groove_len > 0:
            sections.append({"name": "Groove", "start_bar": bar, "length_bars": groove_len})
            bar += groove_len
        sections.append({"name": "Build-up", "start_bar": bar, "length_bars": build_len})
        bar += build_len
        if drop_len > 0:
            sections.append({"name": "Drop", "start_bar": bar, "length_bars": drop_len})
        return sections

    intro_len = max(1, round(total_bars * 0.125))
    verse_len = max(1, round(total_bars * 0.375))
    outro_len = max(1, round(total_bars * 0.125))
    chorus_len = total_bars - intro_len - verse_len - outro_len
    if chorus_len < 1:
        # Very short requests (e.g. 4 bars): drop the outro first, then
        # the intro, rather than ever emitting a zero/negative section.
        chorus_len = total_bars - intro_len - verse_len
        outro_len = 0
        if chorus_len < 1:
            chorus_len = total_bars - verse_len
            intro_len = 0
            if chorus_len < 1:
                verse_len = total_bars
                chorus_len = 0

    sections = []
    bar = 1
    for name, length in (
        ("Intro", intro_len),
        ("Verse", verse_len),
        ("Chorus", chorus_len),
        ("Outro", outro_len),
    ):
        if length <= 0:
            continue
        sections.append({"name": name, "start_bar": bar, "length_bars": length})
        bar += length
    return sections


def describe_structure(sections: list[dict]) -> str:
    """A short, readable line-per-section summary for the chat answer."""
    lines = []
    for section in sections:
        end_bar = section["start_bar"] + section["length_bars"] - 1
        lines.append(f"- {section['name']}: bars {section['start_bar']}-{end_bar}")
    return "\n".join(lines)
