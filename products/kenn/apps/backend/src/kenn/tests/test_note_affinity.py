"""Which note leads an answer: the words the user typed, counted once each."""

from __future__ import annotations

from kenn.core.chat_retrieval import display_results, intent_guard_status, note_query_affinity, result_payload
from kenn.core.chat_routing import search_query_with_history


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


def test_the_intent_word_can_be_in_another_chunk_of_the_shown_note() -> None:
    # 27 Sept 2026: "Why might I high-pass a wide clap layer...?" retrieved only snare-clap-layering.md and was still
    # refused, because "wide" sat in the note's steps chunk, not the one displayed.
    from kenn.core.chat_retrieval import intent_guard_status

    base = {"kind": "note", "source": "snare-clap-layering.md", "title": "Snare And Clap Layering", "tags": ["clap"]}
    summary = {**base, "text": "Give each snare or clap layer one job and process the result as one sound."}
    steps = {**base, "text": "High-pass wide clap layers so their stereo low mids do not weaken mono playback."}
    question = "Why might I high-pass a wide clap layer before combining it with the main snare?"
    assert intent_guard_status(question, [(722.0, summary), (637.0, steps)]) == "strong"


def _drum_followup_candidates(reverb_score: float = 1160.0) -> list[tuple[float, dict]]:
    return [
        (1423.0, {"kind": "note", "source": "parallel.md", "title": "Drum Parallel Compression",
                  "tags": ["drums"], "text": "Control dense drums with parallel compression."}),
        (1160.0, {"kind": "note", "source": "overview.md", "title": "Mixing Drums Overview",
                  "tags": ["drums"], "text": "Balance the dense drums before processing."}),
        (1124.0, {"kind": "note", "source": "bus.md", "title": "Drum Bus Processing",
                  "tags": ["drums"], "text": "Keep the drum bus dynamics under control."}),
        (reverb_score, {"kind": "note", "source": "return.md", "title": "Reverb Send Workflow",
                        "tags": ["reverb"], "text": "High-pass the reverb return to avoid low-frequency buildup."}),
    ]


def _dense_drum_followup() -> str:
    return search_query_with_history(
        "Does that change if the drums are very dense?",
        [{"role": "user", "content": "Going back to the drum reverb, should I high-pass the return?"}],
    )


def test_dense_drum_followup_keeps_reverb_evidence_in_displayed_sources() -> None:
    # Generic drum titles displaced every reverb note after retrieval had found the follow-up's evidence.
    query = _dense_drum_followup()
    results = _drum_followup_candidates()

    shown = display_results(query, results, 3)

    assert shown[0][1]["source"] == "return.md"
    assert "return.md" in {chunk["source"] for _, chunk in shown}
    assert intent_guard_status(query, results) == "strong"
    assert "return.md" in {item["source"] for item in result_payload(query, results)}
    assert len(shown) == 3


def test_weak_reverb_candidate_does_not_displace_close_drum_evidence() -> None:
    query = _dense_drum_followup()
    results = _drum_followup_candidates(reverb_score=100.0)

    assert "return.md" not in {chunk["source"] for _, chunk in display_results(query, results)}
    assert intent_guard_status(query, results) == "weak"


def test_missing_reverb_evidence_still_fails_the_intent_guard() -> None:
    query = _dense_drum_followup()
    results = _drum_followup_candidates()[:-1]

    assert intent_guard_status(query, results) == "weak"


def test_one_display_slot_keeps_the_followup_intent_note() -> None:
    shown = display_results(_dense_drum_followup(), _drum_followup_candidates(), 1)

    assert len(shown) == 1
    assert shown[0][1]["source"] == "return.md"


def test_dense_drum_reverb_followup_fallback_uses_the_reverb_workflow() -> None:
    # Displaying a reverb companion still let the separately ranked fallback answer with parallel compression.
    from kenn.core.chat_answer import build_template_answer
    from kenn.core.chat_formatting import note_sections

    results = _drum_followup_candidates()
    for _, chunk in results:
        chunk["text"] = "Short answer:\n" + chunk["text"]
    query = _dense_drum_followup()

    sections = note_sections(query, results)
    answer = build_template_answer(query, results, route="knowledge")

    assert "High-pass the reverb return" in sections["short"]
    assert "High-pass the reverb return" in answer
    assert "Control dense drums with parallel compression." not in answer


def test_reverb_lead_requires_the_existing_close_score_boundary() -> None:
    from kenn.core.chat_retrieval import prefer_intent_note

    query = _dense_drum_followup()
    below = _drum_followup_candidates(reverb_score=1423.0 * 0.55 - 0.01)
    at_boundary = _drum_followup_candidates(reverb_score=1423.0 * 0.55)

    assert prefer_intent_note(query, below)[0][1]["source"] == "parallel.md"
    assert prefer_intent_note(query, at_boundary)[0][1]["source"] == "return.md"


def test_intent_promotion_does_not_mutate_retrieved_order() -> None:
    from kenn.core.chat_retrieval import prefer_intent_note

    results = _drum_followup_candidates()
    assert prefer_intent_note(_dense_drum_followup(), results)[0][1]["source"] == "return.md"
    assert results[0][1]["source"] == "parallel.md"
