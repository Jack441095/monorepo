"""Tests for optional LLM paraphrase helpers (no API calls)."""

from __future__ import annotations

import sys
from pathlib import Path

ABLETON = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(ABLETON.parent))

from kenn.llm.llm_rewrite import valid_note_structure  # noqa: E402


def test_valid_note_structure_accepts_training_note() -> None:
    text = """
Short answer:
Use a return track for reverb.

Key ideas:
- Sends keep the dry source clean

Try this:
1. Create a return track
2. Add reverb
3. Send from the source

Why it matters:
Cleaner mixes.

Related questions:
- How much send level?

Useful terms:
reverb, send

Editor notes:
Review before approve.
"""
    assert valid_note_structure(text)


def test_valid_note_structure_rejects_chat_only() -> None:
    text = "Short answer:\nHi\nTry this:\n1. Do thing\nSources:\n- note"
    assert not valid_note_structure(text)
