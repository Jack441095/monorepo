from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

import importlib
build_index = importlib.import_module("kenn.retrieval.build_index")


def test_hierarchical_chunking_retains_block_integrity() -> None:
    text = (
        "This is paragraph one which is relatively short.\n"
        "It spans across lines but should be treated as a single block.\n"
        "\n"
        "- A list item starting with a dash\n"
        "- Another list item that should be kept intact\n"
        "\n"
        "And a final concluding paragraph."
    )
    
    chunks = build_index.split_text(text, max_words=50, overlap=10)
    
    assert len(chunks) > 0
    assert any("\n\n- A list item" in chunk or "- A list item" in chunk for chunk in chunks)


def test_hierarchical_chunking_splits_on_sentences() -> None:
    text = (
        "Sentence number one. Sentence number two. Sentence number three. "
        "Sentence number four. Sentence number five. Sentence number six."
    )
    
    chunks = build_index.split_text(text, max_words=6, overlap=2)
    
    for chunk in chunks:
        assert chunk.endswith(".") or chunk.endswith("?") or chunk.endswith("!")
        words_count = len(chunk.split())
        assert words_count <= 6


def test_note_chunks_include_mistakes_and_boundaries(tmp_path) -> None:
    note = tmp_path / "boundary-note.md"
    note.write_text(
        """# Boundary Note

Type: Workflow
Tags: mixing, boundary, diagnosis
Status: Approved

Short answer:
Start with evidence.

Try this:
1. Listen.

Why it matters:
It prevents guessing.

Common mistakes:
- Boosting before level matching.

When this does not apply:
Ask for the session when the symptom is ambiguous.

Related questions:
- What evidence do I need?
""",
        encoding="utf-8",
    )
    chunks = build_index.iter_note_chunks(note)
    sections = {chunk.section for chunk in chunks}
    assert "Common mistakes" in sections
    assert "When this does not apply" in sections
    assert all("Tags: boundary diagnosis mixing" in chunk.text for chunk in chunks)


def test_reference_only_pdf_is_not_indexed() -> None:
    assert build_index.should_index_pdf({"index_policy": "reference_only"}) is False
    assert build_index.should_index_pdf({"index_policy": "index"}) is True
    assert build_index.should_index_pdf({}) is True
