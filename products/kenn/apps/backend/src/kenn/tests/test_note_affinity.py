"""Which note leads an answer: the words the user typed, counted once each."""

from __future__ import annotations

from kenn.core.chat_retrieval import note_query_affinity


def test_singular_and_plural_of_one_word_count_once() -> None:
    # 27 Sept 2026: "drum" and "drums" both scored for "Mixing Drums — Overview", so it led the answer to "how do I
    # make drums punchier" over "Drum Punch And Transient Control", which retrieval had ranked first.
    overview = {"title": "Mixing Drums — Overview", "source": "mixing-drums-overview.md", "tags": ["drums"],
                "text": "Balance the drums without reaching for plugins."}
    punch = {"title": "Drum Punch And Transient Control", "source": "drum-punch-transient-control.md",
             "tags": ["drums"], "text": "Punchier drums come from transient shape."}
    question = "How do I make drums punchier without over-compressing?"
    assert note_query_affinity(question, punch) > note_query_affinity(question, overview)


def test_filler_words_are_not_evidence() -> None:
    plain = {"title": "Kick Tuning", "source": "kick-tuning.md", "tags": ["kick"], "text": "Tune the kick drum"}
    wordy = {**plain, "text": "Tune the kick drum without guessing and with care"}
    assert note_query_affinity("tune the kick without mud", wordy) == note_query_affinity("tune the kick without mud", plain)
