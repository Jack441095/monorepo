"""A plural in the question must match the singular in a note's title, and the other way round."""

from __future__ import annotations

from kenn.retrieval import retrieval


def _chunk(title: str) -> dict:
    return {"id": title, "title": title, "source": f"{title.lower().replace(' ', '-')}.md", "kind": "note",
            "text": "Notes on the vocal."}


def test_vocals_in_the_question_reaches_the_vocal_mixing_note_not_only_the_background_vocals_one():
    # 3 Oct: "i need help mixing vocals" answered only from the background-vocals note, because "Vocals" in that
    # title matched exactly and "Vocal Mixing Basics" did not.
    results = [(1.0, _chunk("Mixing Background And Harmony Vocals")), (1.0, _chunk("Vocal Mixing Basics"))]
    ranked = retrieval.rerank_results("i need help mixing vocals", results)
    assert ranked[0][1]["title"] == "Vocal Mixing Basics"


def test_a_singular_question_still_matches_a_plural_title():
    results = [(1.0, _chunk("Drum Bus Compression")), (1.0, _chunk("Drums And Bass Layering"))]
    ranked = retrieval.rerank_results("how do i compress a drum bus", results)
    assert ranked[0][1]["title"] == "Drum Bus Compression"
