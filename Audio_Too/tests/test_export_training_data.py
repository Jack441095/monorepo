from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "studio" / "kenn" / "kenn" / "training" / "export_training_data.py"
SPEC = importlib.util.spec_from_file_location("kenn_export_training_data", MODULE_PATH)
assert SPEC and SPEC.loader
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def test_approved_note_questions_include_titles_and_related_questions(tmp_path, monkeypatch) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "approved.md").write_text(
        "# Gain Staging\n\nStatus: Approved\n\nRelated questions:\n"
        "- Why is my track clipping?\n- How much headroom do I need?\n",
        encoding="utf-8",
    )
    (notes / "draft.md").write_text(
        "# Secret Draft\n\nStatus: Draft\n\nRelated questions:\n- Should this be excluded?\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(exporter, "NOTES_DIR", notes)

    assert exporter.get_approved_note_questions() == {
        "How do I handle gain staging?",
        "Why is my track clipping?",
        "How much headroom do I need?",
    }


def test_curated_conversation_prompts_require_history(tmp_path) -> None:
    path = tmp_path / "conversations.json"
    path.write_text(
        '{"cases": ['
        '{"question": "What next?", "history": [{"role": "user", "content": "My bass is weak."}]},'
        '{"question": "Standalone", "history": []}'
        ']}' ,
        encoding="utf-8",
    )
    assert exporter.get_conversation_prompts(path) == [
        {
            "question": "What next?",
            "history": [{"role": "user", "content": "My bass is weak."}],
        }
    ]


def test_supplemental_questions_are_deduplicated(tmp_path) -> None:
    path = tmp_path / "prompts.json"
    path.write_text('{"questions": ["Question one?", "Question one?", "Question two?"]}', encoding="utf-8")
    assert exporter.get_supplemental_questions(path) == {"Question one?", "Question two?"}
