"""Tests for Knowledge Admin note listing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import ableton_bridge  # noqa: E402


def test_list_notes_filters_by_status_and_query(tmp_path, monkeypatch) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "approved-note.md").write_text(
        "# Approved Note\n\nType: Production workflow\nTags: vocal, width\nStatus: Approved\n\nShort answer:\nWide vocal note.\n",
        encoding="utf-8",
    )
    (notes / "draft-note.md").write_text(
        "# Draft Note\n\nType: Production workflow\nTags: bass, sidechain\nStatus: Draft\n\nShort answer:\nBass note.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ableton_bridge, "NOTES_DIR", notes)

    approved = ableton_bridge.list_notes(status="Approved")
    assert [item["name"] for item in approved] == ["approved-note.md"]
    assert approved[0]["tags"] == "vocal, width"

    bass = ableton_bridge.list_notes(query="sidechain")
    assert [item["name"] for item in bass] == ["draft-note.md"]


def test_list_notes_returns_unmarked_status(tmp_path, monkeypatch) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "plain-note.md").write_text("# Plain Note\n\nShort answer:\nNo status.\n", encoding="utf-8")
    monkeypatch.setattr(ableton_bridge, "NOTES_DIR", notes)

    items = ableton_bridge.list_notes()

    assert items[0]["status"] == "Unmarked"
    assert items[0]["title"] == "Plain Note"
