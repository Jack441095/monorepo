"""Regression: KENN must not silently repeat a technique the user just
said they already tried without success.

Live-tested 2026-08-03 through the real HTTP server: a 5-turn
troubleshooting conversation ("my mix sounds muddy" -> "its mostly in the
low mids" -> "i already tried eq cuts" -> "what about the bass and kick
specifically" -> "ok i did sidechain, still muddy") kept suggesting
techniques the user had just ruled out -- "i already tried eq cuts" got
another EQ-focused answer (Use EQ Eight for subtractive fixes...), and "i
did sidechain, still muddy" got a generic Multiband Dynamics explanation,
neither acknowledging what had already failed. This is a scoped fix (per
Jack's explicit direction: detect the phrasing, avoid repeating the same
technique next turn) -- not the fuller "track everything attempted across
the whole session and adapt" design, which is a bigger, separate project.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat_answer import (  # noqa: E402
    _already_tried_technique,
    _deprioritize_already_tried,
)


def test_detects_already_tried_eq():
    assert _already_tried_technique("i already tried eq cuts") == "EQ"


def test_detects_still_not_working_with_sidechain():
    assert _already_tried_technique("ok i did sidechain, still muddy") == "sidechaining"


def test_no_signal_for_an_ordinary_question():
    assert _already_tried_technique("how do i eq a vocal") == ""


def test_no_technique_named_returns_empty_even_with_already_tried_phrasing():
    assert _already_tried_technique("i already tried that") == ""


def test_deprioritize_drops_chunks_titled_about_the_technique():
    results = [
        (200.0, {"title": "EQ Eight Mixing Basics", "source": "eq-eight-mixing-basics.md"}),
        (150.0, {"title": "Mixing Chain Order", "source": "mixing-chain-order.md"}),
    ]
    filtered = _deprioritize_already_tried(results, "EQ")
    assert [c.get("source") for _, c in filtered] == ["mixing-chain-order.md"]


def test_deprioritize_keeps_a_note_that_merely_mentions_the_technique_in_tags():
    """Tags are a broad set of related keywords -- nearly every mixing note
    tags "eq" since it's used almost everywhere. Filtering on tags would
    exclude the entire result set for any EQ-adjacent query. Title is the
    precise signal of what a note is actually about."""
    results = [
        (200.0, {
            "title": "Fix Muddy Low-Mids In A Mix",
            "tags": ["balance clarity eq low-mids mixing mud workflow"],
            "source": "muddy-low-mids-fix.md",
        }),
    ]
    filtered = _deprioritize_already_tried(results, "EQ")
    assert [c.get("source") for _, c in filtered] == ["muddy-low-mids-fix.md"]


def test_deprioritize_never_filters_down_to_nothing():
    results = [(200.0, {"title": "EQ Eight Mixing Basics", "source": "eq-eight-mixing-basics.md"})]
    filtered = _deprioritize_already_tried(results, "EQ")
    assert [c.get("source") for _, c in filtered] == ["eq-eight-mixing-basics.md"]
