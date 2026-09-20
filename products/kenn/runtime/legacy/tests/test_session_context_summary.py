"""Regression: the "[Session Summary]" shown on a follow-up query must read
as coherent English, not repeated/self-referential keyword soup.

Live-tested 2026-08-03 through the real running KENN server: a 3-turn
conversation ("how do i warp audio in ableton" -> "what about when the
tempo changes mid song" -> "and if the transients get smeared") produced
"Earlier, we were discussing tracks like the track, vocal, vocals,
techniques like transient shaping, warping, A/B comparison, topics around
warping, Ableton." Two distinct bugs:

1. extract_track_names() scanned `query + answer` (update_session's
   `combined`), so any generic instrument word KENN's own explanatory prose
   happened to use (e.g. "such as a bass synth, drum loop, or pad" from an
   unrelated answer) got treated as if the user mentioned a track. Fixed to
   scan the user's query only.
2. The track pattern matched bare "the track"/"my track" -- a self-
   referential generic phrase, not an identifiable element, rendered back
   as nonsense ("tracks like the track"). Removed from the pattern.
3. "vocal" and "vocals" (or "the vocal") were captured as separate,
   undeduplicated entries by different regex alternatives. Added article-
   stripping + singular normalization.
4. "warping" appeared in both techniques_mentioned and topics_mentioned,
   so the same word was repeated back-to-back in the rendered sentence.
   build_session_context() now excludes anything already used by an
   earlier part of the sentence.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core import session_memory  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_session_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")
    yield


def test_extract_track_names_ignores_the_bare_word_track():
    assert session_memory.extract_track_names("how do i fix the track") == []


def test_extract_track_names_dedupes_singular_and_plural():
    names = session_memory.extract_track_names("the vocal sounds off, my vocals are too quiet")
    assert names == ["vocal"]


def test_extract_track_names_strips_leading_article():
    names = session_memory.extract_track_names("fix the kick and my snare")
    assert names == ["kick", "snare"]


def test_update_session_does_not_pull_track_names_from_the_answer():
    """update_session's `combined = query + answer` used to feed the whole
    generated answer into extract_track_names() -- a generic instrument
    word in KENN's own explanation (not the user's question) should not be
    recorded as a track the user is working on."""
    session_memory.update_session(
        "how do i warp audio in ableton",
        "Try this: place Auto Filter on a bass synth, drum loop, or pad and adjust the vocal chain.",
        "production",
        "ableton_steps",
        "high",
        "general",
        session_id="s1",
    )
    state = session_memory.load_session(session_id="s1")
    assert state["track_names"] == []


def test_session_summary_does_not_repeat_a_topic_already_shown_as_a_technique(monkeypatch):
    monkeypatch.setattr(
        session_memory, "load_session",
        lambda session_id="": {
            "turn_count": 3,
            "last_question": "and if the transients get smeared",
            "topics_mentioned": ["warping", "ableton"],
            "techniques_mentioned": ["transient shaping", "warping"],
            "track_names": [],
            "current_project": "",
            "last_confidence": "high",
            "last_answer_mode": "ableton_steps",
        },
    )

    context = session_memory.build_session_context(session_id="s1")

    assert context.count("warping") == 1
    assert "the track" not in context
