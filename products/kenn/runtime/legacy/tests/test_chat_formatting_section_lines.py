"""Regression: section_lines() must recognize a decorated section heading,
not just an exact "Try this:"-style match.

Live-tested 2026-08-03: automix-reverb-and-delay-sends.md's real "Try this"
section is headed "Try this -- default reverb sends by instrument:", not
bare "Try this:". The old exact-match check (stripped line == heading, after
trailing colon) never recognized this as a heading at all, so none of its
14 real instrument-by-instrument values were ever extracted -- note_sections()
fell through to the generic fallback_steps() boilerplate, and since this
chunk ranked top for reverb-send queries (causing every other candidate note
to be skipped via the top_affinity gate), the whole answer degraded to
content-free filler ("Open the relevant Ableton view or device mentioned in
the sources...").
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat_formatting import note_sections, section_lines  # noqa: E402


DECORATED_HEADING_NOTE = """# AutoMix Reverb and Delay Send Levels

Short answer:
Every instrument rule carries a fixed reverb_send.

Try this — default reverb sends by instrument:
1. Kick / sub bass / bass: 0% reverb send.
2. Snare: 18% send, room reverb.

Why it matters:
Encodes front-to-back mix depth.
"""

PLAIN_HEADING_NOTE = """# Reverb Send Workflow

Short answer:
Use return tracks for reverb.

Try this:
1. Create a Return track with Reverb.
2. High-pass the return around 200-400 Hz.

Why it matters:
Clients often muddy mixes with per-track reverb.
"""


def test_section_lines_recognizes_decorated_heading():
    lines = section_lines(DECORATED_HEADING_NOTE, "Try this")
    assert lines == [
        "1. Kick / sub bass / bass: 0% reverb send.",
        "2. Snare: 18% send, room reverb.",
    ]


def test_section_lines_still_recognizes_plain_heading():
    lines = section_lines(PLAIN_HEADING_NOTE, "Try this")
    assert lines == [
        "1. Create a Return track with Reverb.",
        "2. High-pass the return around 200-400 Hz.",
    ]


def test_section_lines_stops_at_the_next_heading():
    lines = section_lines(DECORATED_HEADING_NOTE, "Try this")
    assert "Encodes front-to-back mix depth." not in lines


def test_section_lines_returns_empty_for_missing_heading():
    assert section_lines(PLAIN_HEADING_NOTE, "Related questions") == []


# ── note_sections() surfacing "Common mistakes" ──────────────────────────
#
# Found live-testing 2026-08-03: 122 notes in Training_Data_Notes/ have a
# "Common mistakes:" section, but nothing ever extracted or displayed it --
# every answer showed the same generic, mode-level "avoid" boilerplate
# regardless of topic. note_sections() now surfaces it the same way it
# already does "Try this"/"Why it matters".

NOTE_WITH_MISTAKES = {
    "kind": "note",
    "source": "test-note.md",
    "topics": ["compression"],
    "tags": ["compression", "sidechain"],
    "text": """# Sidechain Compression

Short answer:
Use sidechain compression keyed from the kick to duck the bass.

Try this:
1. Route the kick into the compressor sidechain input.
2. Set a fast attack and a moderate release.

Why it matters:
Ducking the bass under the kick keeps the low end from masking.

Common mistakes:
- Setting the release so slow the bass never recovers between kicks.
- Sidechaining from a bus instead of the actual kick transient.

When this does not apply:
- Genres with no sustained bass, where there is nothing to duck.
""",
}


def test_note_sections_extracts_common_mistakes(monkeypatch):
    import kenn.core.chat_formatting as chat_formatting

    monkeypatch.setattr(chat_formatting, "load_note_text", lambda chunk: chunk["text"])
    monkeypatch.setattr(chat_formatting, "query_topics", lambda query: [])

    sections = note_sections("how do i sidechain the bass to the kick", [(10.0, NOTE_WITH_MISTAKES)])

    assert sections["common_mistakes"] == [
        "Setting the release so slow the bass never recovers between kicks.",
        "Sidechaining from a bus instead of the actual kick transient.",
    ]


def test_note_sections_common_mistakes_empty_when_note_has_none(monkeypatch):
    import kenn.core.chat_formatting as chat_formatting

    note = dict(NOTE_WITH_MISTAKES)
    note["text"] = "# Sidechain Compression\n\nShort answer:\nUse sidechain compression.\n"
    monkeypatch.setattr(chat_formatting, "load_note_text", lambda chunk: chunk["text"])
    monkeypatch.setattr(chat_formatting, "query_topics", lambda query: [])

    sections = note_sections("how do i sidechain the bass to the kick", [(10.0, note)])

    assert sections["common_mistakes"] == []
    assert sections["scope_limits"] == []


def test_note_sections_extracts_scope_limits(monkeypatch):
    import kenn.core.chat_formatting as chat_formatting

    monkeypatch.setattr(chat_formatting, "load_note_text", lambda chunk: chunk["text"])
    monkeypatch.setattr(chat_formatting, "query_topics", lambda query: [])

    sections = note_sections("how do i sidechain the bass to the kick", [(10.0, NOTE_WITH_MISTAKES)])

    assert sections["scope_limits"] == [
        "Genres with no sustained bass, where there is nothing to duck.",
    ]


def test_template_answer_uses_notes_own_common_mistakes(monkeypatch):
    """End-to-end: build_template_answer() must show the retrieved note's
    own "Common mistakes" bullets, not the generic per-mode/per-route
    "avoid" boilerplate, when the note has real content to offer."""
    import kenn.core.chat_answer as chat_answer
    import kenn.core.chat_formatting as chat_formatting

    monkeypatch.setattr(chat_formatting, "load_note_text", lambda chunk: chunk["text"])
    monkeypatch.setattr(chat_formatting, "query_topics", lambda query: [])

    answer = chat_answer.build_template_answer(
        "how do i sidechain the bass to the kick", [(10.0, NOTE_WITH_MISTAKES)]
    )

    assert "Setting the release so slow the bass never recovers between kicks." in answer
    assert "Sidechaining from a bus instead of the actual kick transient." in answer


def test_template_answer_uses_notes_own_scope_limits(monkeypatch):
    """End-to-end: build_template_answer() must show the retrieved note's
    own "When this does not apply" scope boundary when present."""
    import kenn.core.chat_answer as chat_answer
    import kenn.core.chat_formatting as chat_formatting

    monkeypatch.setattr(chat_formatting, "load_note_text", lambda chunk: chunk["text"])
    monkeypatch.setattr(chat_formatting, "query_topics", lambda query: [])

    answer = chat_answer.build_template_answer(
        "how do i sidechain the bass to the kick", [(10.0, NOTE_WITH_MISTAKES)]
    )

    assert "This doesn't apply if:" in answer
    assert "Genres with no sustained bass, where there is nothing to duck." in answer
