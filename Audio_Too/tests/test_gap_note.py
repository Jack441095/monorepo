"""Tests for gap → draft note workflow."""

from __future__ import annotations

import sys
from pathlib import Path

ABLETON = Path(__file__).resolve().parent.parent / "studio" / "kenn" / "kenn"
WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
sys.path.insert(0, str(ABLETON.parent))
sys.path.insert(0, str(WEBSITE))

from kenn.training.research import create_note_from_question, gap_note_template  # noqa: E402


def test_gap_note_template_has_sections() -> None:
    text = gap_note_template("Test Title", "how do I saturate bass?", "bass, saturation")
    assert "Status: Draft" in text
    assert "Short answer:" in text
    assert "saturate bass" in text


def test_create_note_from_question_writes_file(tmp_path, monkeypatch) -> None:
    from kenn.training import research

    monkeypatch.setattr(research, "NOTES_DIR", tmp_path)
    path = create_note_from_question("how do I saturate sub bass?", ["bass", "saturation"])
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Status: Draft" in content
    assert "saturate sub bass" in content.lower()
