"""The gate must judge the model against the excerpts the model was actually given.

This seam has now failed in both directions on the same day, 2 Oct 2026, on the streaming chat surface with
kenn-brain-qwen3-8b and the cache off, and both failures came from each side deriving its own list.

Narrow: the gate read the top 3 while the model read 12, so a figure in chunk #7 was quoted back to us and
reported invented. Acceptance fell from 41% (12 of 29) to 27% (4 of 15) — 10 unsupported-measurement and 3
fabricated-source rejections, every one of them a chunk the gate had never opened.

Wide: the gate read every chunk's text in full while the prompt fitted 2 to 4 excerpts into 1200 chars at 400
each. On index v-db8c6334cf63 at the ask path's limit of 16, "send reverb on a vocal bus" gave the model 3
excerpts and the gate 10 chunks, with 21 measurements in gate evidence the model was never shown. The model
reached for "3 dB" from its training prior, the gate found "3db" in chunk #9, and an ungrounded answer was
accepted on evidence it had not been given.

Both are now the same edit away, so the fix is structural: llm_rewrite.model_evidence() computes the excerpt
list once under the real character budget and chat_grounding reads that list. These tests assert the two sides
agree, which is the property that matters. They do not assert a depth.

The fixtures below are built to the shape of the real index: several sections of ONE note, all page 0, with a
handful of further notes behind them. That shape is the point. The first version of this file used 12 distinct
sources and asserted len(_evidence_chunks(...)) == 12, and it passed for the wrong reason — display_results
de-duplicates on (kind, source, page) and all 3204 note sections in the live index carry page == 0, so a note's
sections can never occupy separate slots there. The fixture asserted a shape the corpus does not produce and
measured a depth the gate never had.

A third reader was still deriving its own list, and it cost 24 of 25 answers. llm_rewrite.sources_block()
walked the raw ranked results to build the "Sources:" line, so it counted Related-questions chunks that clean
to "" and notes the 1200-char block never paid for. Acceptance fell from 66% (19 of 29) to 1 of 25 on the
streaming surface, 23 of those rejections carrying nothing but "generated answer cites sources not in the
retrieved evidence". Those were correct rejections of a citation list naming notes the model had never been
shown. The tests at the end of this file cover that third reader.
"""

from __future__ import annotations

import pytest

import kenn.llm.llm_rewrite as llm_rewrite
from kenn.core.chat_constants import EVIDENCE_SCAN_WINDOW
from kenn.core.chat_grounding import (
    _cited_source_filenames,
    _evidence_chunks,
    _measurements,
    generated_answer_validation,
    grounding_report,
)
from kenn.core.chat_retrieval import normalized_terms, source_label
from kenn.llm.llm_rewrite import (
    _CONTEXT_SCAN_WINDOW,
    _with_sources,
    build_raw_context_block,
    model_evidence,
    sources_block,
)

QUERY = "How should I set up a send reverb on a vocal bus?"


def _note(source: str, text: str, page: int = 0, section: str = "") -> dict:
    return {
        "kind": "note",
        "source": source,
        "title": source.removesuffix(".md"),
        "text": text,
        "page": page,
        "section": section,
        "tags": ["reverb", "vocal", "mixing"],
    }


# Built from the live index's shape rather than from what makes a test easiest: four sections of one note, all
# page 0, then four further notes. The sections carry the measurements, because that is how a curated note is
# actually stored — the guidance is split by heading, so "Try this" holds the numbers and "Common mistakes"
# holds the figure the model must not get.
#
# Section lengths are set so the 1200-char block pays for three of the four. A real chunk median is 532 chars,
# so short fixture text lets everything through and the budget stops being the thing under test.
#
# Real index, all four sections of reverb-send-basics.md share page == 0, which is exactly why the gate's
# (kind, source, page) de-duplication used to collapse them into a single evidence slot.
SIDE_CHAIN_BASIS = "reverb-send-basics.md"
RANKED_RESULTS: list[tuple[float, dict]] = [
    (100.0, _note(SIDE_CHAIN_BASIS, "Route the vocal to a dedicated return track and let that return carry the "
                  "reverb, never the vocal itself. Keeping the tail off the dry path is what stops it competing "
                  "with the lyric, and one return can then serve every vocal in the session instead of a separate "
                  "reverb copy per take.", section="Short answer")),
    (98.0, _note(SIDE_CHAIN_BASIS, "Create the return first and name it. Send the vocal to it and set the send to "
                  "20%. High-pass the return at 200 Hz so the sub content under the vocal does not muddy the tail. "
                  "Set the return fader, not the send, when you want more reverb; the send sets how much signal "
                  "enters, the fader sets how much comes out.", section="Try this")),
    (96.0, _note(SIDE_CHAIN_BASIS, "A send leaves the dry signal untouched, so the reverb cannot drag the vocal's "
                  "level down with it. It also means the tail is summed after the channel fader, which is why a "
                  "vocal still reads as forward when the space sits behind it rather than smeared across it.",
                  section="Why it matters")),
    (94.0, _note(SIDE_CHAIN_BASIS, "Reverb at 63% on the vocal itself buries the lyric, and a low-passed return "
                  "smears the consonants. When this does not apply: a mono check will show the send collapsing "
                  "the image if the return is hard-panned, so keep the return stereo and the send narrow.",
                  section="Common mistakes")),
    (60.0, _note("vocal-space.md", "A vocal sits forward when the reverb sits behind it in the balance.")),
    (58.0, _note("lufs-delivery.md", "Streaming platforms normalise to about -14 LUFS, so a -9 LUFS master runs quiet.")),
    (56.0, _note("buffer-size-latency.md", "A 512-sample buffer adds about 10 ms of round-trip latency.")),
    (54.0, _note("gain-structure.md", "Set the trim before the preamp so gain staging stays predictable.")),
]


def _validate(answer: str, results: list[tuple[float, dict]] | None = None) -> dict:
    return generated_answer_validation(
        QUERY,
        list(results if results is not None else RANKED_RESULTS),
        answer,
        route="production_dialogue",
        confidence="medium",
        answer_mode="quick_fix",
    )


def test_the_gate_scores_exactly_the_chunks_the_prompt_contains() -> None:
    # The property that replaces the false-green depth assertion. On the real index shape the gate reads 3
    # excerpts, not 12 and not 10, and set equality with the prompt is what makes that correct rather than
    # merely narrow.
    block, shown = model_evidence(RANKED_RESULTS, source_label)
    gate = _evidence_chunks(list(RANKED_RESULTS))

    assert [_chunk_key(c) for _s, c, _b in gate] == [_chunk_key(c) for _s, c, _b in shown]
    assert [body for _s, _c, body in gate] == [body for _s, _c, body in shown]
    # Set equality, not depth. On this fixture the gate reads 3 excerpts; asserting a count was the false-green
    # in the previous version of this file, because the right number here is whatever the budget paid for.
    assert {_chunk_key(c) for _s, c, _b in gate} == {_chunk_key(c) for _s, c, _b in shown}
    assert len(gate) == len(shown)
    # And the bodies are the ones actually present in the prompt text, not a parallel cleaning of them.
    assert block == build_raw_context_block(RANKED_RESULTS, source_label)
    for _s, _c, body in gate:
        assert body in block


def _chunk_key(chunk: dict) -> tuple[str, str, str]:
    """Identify a chunk by its section, because a note's sections all share source and page in the live index."""
    return (str(chunk.get("source", "")), str(chunk.get("section", "")), str(chunk.get("title", "")))


def test_the_gate_reads_the_sections_the_model_saw_not_the_whole_note() -> None:
    # A note split into sections is not one unit of evidence. Before the fix the gate read every section's full
    # text; now it reads only the sections the budget paid for, which for this fixture is 3 of the 4 the note
    # carries. The Common mistakes section sits fourth and is the one holding 63%.
    _block, shown = model_evidence(RANKED_RESULTS, source_label)
    sections_shown = [str(chunk.get("section", "")) for _s, chunk, _b in shown]

    assert len(sections_shown) == 3, "the 1200-char block fits three of these four sections, not four"
    assert "Common mistakes" not in sections_shown
    assert "63%" in RANKED_RESULTS[3][1]["text"], "the fixture must carry 63% past the budget to test anything"


def test_a_measurement_from_a_chunk_the_model_never_saw_cannot_ground_an_answer() -> None:
    # The 2 Oct 2026 failure, on the real index shape. 63% is in the note and the note ranked highly, but its
    # section never fitted inside the 1200-char block, so the model never read it. Before this fix the gate read
    # chunk["text"] in full, found 63%, and passed an answer that had invented the figure.
    _block, shown = model_evidence(RANKED_RESULTS, source_label)
    assert "63%" not in " ".join(body for _s, _c, body in shown), (
        "the model must not have been shown 63%, or this test cannot fail"
    )
    assert "63%" in _measurements(RANKED_RESULTS[3][1]["text"])

    answer = (
        "Short answer: Send the vocal to a dedicated reverb return and pull it back to 63%, otherwise the "
        "reverb swallows the lyric.\n\n"
        "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it. 3. Set the return fader to "
        "63%.\n\n"
        "Check: Audition the vocal dry against the wet return at matched loudness."
    )
    report = _validate(answer)
    assert "63%" in report["unsupported_measurements"], (
        "63% is real note text, but the model never saw it, so an answer citing it is not grounded"
    )
    assert "generated answer introduced unsupported measurements" in report["warnings"]


def test_a_measurement_in_a_shown_section_still_grounds_an_answer() -> None:
    # The other direction. 20% and 200 Hz sit in the "Try this" section, which is inside the block, so quoting
    # them is supported. Without this the gate could be made to pass by reading nothing at all.
    _block, shown = model_evidence(RANKED_RESULTS, source_label)
    shown_measurements = _measurements(" ".join(body for _s, _c, body in shown))
    # Keyed through _measurements, not a substring search: the note writes "200 Hz" and the gate normalises
    # spacing, so a literal test would pass or fail on typography rather than on what was shown.
    assert "20%" in shown_measurements
    assert "200hz" in shown_measurements

    answer = (
        "Short answer: Send the vocal to a reverb return at 20%, high-pass the return at 200 Hz so the vocal "
        "stays forward.\n\n"
        "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it. 3. Set the send to 20%.\n\n"
        "Check: Audition the vocal dry against the wet return at matched loudness."
    )
    report = _validate(answer)
    assert report["unsupported_measurements"] == [], (
        "20% and 200 Hz are in a section the model was shown; rejecting them is the 2 Oct bug"
    )
    assert "generated answer introduced unsupported measurements" not in report["warnings"]


def test_the_gate_evidence_text_is_a_subset_of_what_the_model_was_handed() -> None:
    # No measurement may appear in the gate's evidence that is absent from the prompt text. Title and source are
    # included on the gate side because the prompt carries both inside the label attribute of the same excerpt.
    block, shown = model_evidence(RANKED_RESULTS, source_label)
    gate_text = " ".join(
        f"{chunk.get('title') or ''} {chunk.get('source') or ''} {body}"
        for _s, chunk, body in shown
    )
    prompt_measurements = _measurements(block)
    gate_measurements = _measurements(gate_text)

    assert gate_measurements <= prompt_measurements, (
        f"gate-only measurements: {sorted(gate_measurements - prompt_measurements)}"
    )
    # The chunk text as a whole is not what the gate reads, which is the whole point: one real measurement per
    # fixture note sits past the budget or in a section that never fitted.
    raw_text = " ".join(str(chunk.get("text") or "") for _score, chunk in RANKED_RESULTS[:_CONTEXT_SCAN_WINDOW])
    assert _measurements(raw_text) - prompt_measurements, (
        "the fixture must contain measurements the prompt cannot show, or this asserts nothing"
    )
    assert normalized_terms(gate_text) <= normalized_terms(block)


def test_the_gate_scores_every_excerpt_it_reads_at_the_same_depth() -> None:
    # grounding_report and answer_quality_report both start from this list, so a score derived from one set
    # against an answer written from another is not a stricter test, it is an incoherent one.
    report = grounding_report(
        QUERY,
        list(RANKED_RESULTS),
        "Short answer: Send the vocal to a reverb return at 20%, high-passed at 200 Hz.\n\n"
        "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it.\n\n"
        "Check: Audition the vocal dry against the wet return at matched loudness.",
        route="production_dialogue",
        confidence="medium",
    )
    assert report["source_topic_match"] is True
    assert report["warnings"] == []


def test_a_source_cited_from_a_note_the_model_was_shown_is_not_called_fabricated() -> None:
    # Labels come from the shown list now, so citing one of them is not fabrication.
    _block, shown = model_evidence(RANKED_RESULTS, source_label)
    shown_sources = {str(chunk.get("source", "")).lower() for _s, chunk, _b in shown}
    assert SIDE_CHAIN_BASIS in shown_sources

    answer = (
        "Short answer: Send the vocal to a dedicated reverb return and high-pass it at 200 Hz.\n\n"
        "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it. 3. Set the send to 20%.\n\n"
        "Sources:\n- Reverb send basics (reverb-send-basics.md)\n\n"
        "Check: Audition the vocal dry against the wet return at matched loudness."
    )
    report = _validate(answer)
    assert report["fabricated_sources"] == []
    assert "generated answer cites sources not in the retrieved evidence" not in report["warnings"]


def test_a_source_the_model_was_never_shown_is_still_called_fabricated() -> None:
    # The guard against over-narrowing. lufs-delivery.md is retrieved but did not fit the block, so a citation
    # of it is a label the model was never given.
    _block, shown = model_evidence(RANKED_RESULTS, source_label)
    assert "lufs-delivery.md" not in {str(c.get("source", "")) for _s, c, _b in shown}

    answer = (
        "Short answer: Send the vocal to a dedicated reverb return and keep the master near -9 LUFS.\n\n"
        "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it. 3. Set the send to 20%.\n\n"
        "Sources:\n- Streaming loudness targets (lufs-delivery.md)\n\n"
        "Check: Audition the vocal dry against the wet return at matched loudness."
    )
    report = _validate(answer)
    assert "lufs-delivery.md" in report["fabricated_sources"], (
        "a citation of a note that never reached the prompt is exactly what fabrication means"
    )
    assert "generated answer cites sources not in the retrieved evidence" in report["warnings"]


def test_the_scan_window_stays_one_number_shared_by_both_sides() -> None:
    # One constant behind both sides, so the seam cannot reopen by editing only one module. The gate no longer
    # reads this directly — it inherits it through model_evidence() — but the model still must not be moved off
    # it in isolation.
    assert EVIDENCE_SCAN_WINDOW == 12
    assert _CONTEXT_SCAN_WINDOW == EVIDENCE_SCAN_WINDOW


def _related_questions_chunk(source: str, *phrasings: str) -> dict:
    body = "\n".join(f"- {phrasing}" for phrasing in phrasings)
    return _note(source, f"{source.removesuffix('.md')}\nRelated questions:\n{body}", section="Related questions")


# The ranking as it arrives on a real query rather than as the budget ends up: a Related-questions block at rank
# 1 — it echoes the question back, so it scores highest — then the four sections of reverb-send-basics.md, then
# four notes the 1200-char block cannot reach. sources_block() used to take its top 3 straight off this list, so
# its first label was a note the model was shown no words of and its third was a note it never saw.
CROWDED_RANKING: list[tuple[float, dict]] = [
    (110.0, _related_questions_chunk(
        "vocal-space-notes.md",
        "How should I set up a send reverb on a vocal bus?",
        "When does a send reverb smear the vocal?",
    )),
    *RANKED_RESULTS,
]


def _listed_labels(block: str) -> set[str]:
    return {line[2:].strip() for line in block.splitlines() if line.startswith("- ")}


def test_the_sources_block_lists_only_notes_the_model_was_shown() -> None:
    # The 2 Oct 2026 failure. Acceptance went 66% (19 of 29) to 1 of 25 and 23 rejections read nothing but
    # "generated answer cites sources not in the retrieved evidence", because the block named notes the prompt
    # never carried. The gate was right; the list was wrong. An answer can only be credited with citing what it
    # was handed, so the labels have to come from model_evidence()'s excerpt list.
    _block, shown = model_evidence(CROWDED_RANKING, source_label)
    block = sources_block(shown, source_label)
    listed = _listed_labels(block)

    assert listed, "the fixture only proves anything if the block has a label in it"
    assert listed == {source_label(chunk) for _score, chunk, _body in shown}
    assert len([line for line in block.splitlines() if line.startswith("- ")]) == len(listed), (
        "a note's sections all share source and page, so without the de-duplication one note takes every slot "
        "and the producer sees the same filename three times"
    )
    assert "vocal-space-notes.md" not in listed, (
        "a Related-questions block cleans to an empty string, so the model was shown no words of that note"
    )
    assert "lufs-delivery.md" not in listed, (
        "lufs-delivery.md sits in the ranking but never fitted the 1200-char block"
    )


def test_the_sources_block_and_the_gate_read_the_same_excerpt_list() -> None:
    # Set equality with what the gate calls displayed_filenames, keyed through the gate's own citation reader so
    # the comparison cannot pass on a different idea of "cited". One list, two readers. The old raw-ranking
    # version produced three filenames where the gate's list holds one, which is the whole 2 Oct regression.
    gate = _evidence_chunks(list(CROWDED_RANKING))
    _block, shown = model_evidence(CROWDED_RANKING, source_label)

    gate_sources = {
        str(chunk.get("source") or "").lower()
        for _score, chunk, _body in gate
        if chunk.get("source")
    }
    assert _cited_source_filenames(sources_block(shown, source_label)) == gate_sources
    assert [c for _s, c, _b in gate] == [c for _s, c, _b in shown]


def test_an_answer_whose_sources_kenn_appended_is_not_called_fabricated() -> None:
    # The non-streaming path: a local model writes a good answer, forgets the "Sources:" line, and KENN adds it
    # from model_evidence()'s list. The answer is then scored against that same list, so appending the citations
    # can no longer be the thing that rejects the answer.
    _block, shown = model_evidence(CROWDED_RANKING, source_label)
    answer = (
        "Short answer: Send the vocal to a dedicated reverb return and high-pass it at 200 Hz.\n\n"
        "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it. 3. Set the send to 20%.\n\n"
        "Check: Audition the vocal dry against the wet return at matched loudness."
    )
    report = _validate(_with_sources(answer, shown, source_label), CROWDED_RANKING)

    assert report["fabricated_sources"] == []
    assert "generated answer cites sources not in the retrieved evidence" not in report["warnings"]


def test_the_streaming_sources_append_uses_the_shown_list_too(monkeypatch: pytest.MonkeyPatch) -> None:
    # enhance_stream builds the same block inline when the model never typed "sources:", and that is the surface
    # the 2 Oct 2026 measurement ran on. It read the raw ranking here, so every streamed answer credited notes
    # the model had never been shown.
    monkeypatch.setattr(llm_rewrite, "is_enabled", lambda task="rewrite": True)

    class _Usage:
        total_tokens = 24

        def to_dict(self) -> dict:
            return {"total_tokens": 24}

    def fake_stream(messages, task, **kwargs):
        yield ("Short answer: send the vocal to its own return.\n\n"
               "Try this: 1. Create the return. 2. Send the vocal bus to it.\n"), None
        yield "", _Usage()

    monkeypatch.setattr(llm_rewrite, "chat_completion_stream", fake_stream)

    tokens = [
        event["token"]
        for event in llm_rewrite.enhance_stream(
            QUERY, "", list(CROWDED_RANKING), None, "", source_label, lambda _history: [],
            answer_mode="quick_fix", route="production_dialogue",
        )
        if event["event"] == "token"
    ]
    answer = "".join(tokens)

    assert answer.endswith(f"Sources:\n- {source_label(CROWDED_RANKING[1][1])}"), answer
    assert "lufs-delivery.md" not in answer, answer
    assert "vocal-space-notes.md" not in answer, answer


def test_the_written_answers_sources_append_uses_the_shown_list_too(monkeypatch: pytest.MonkeyPatch) -> None:
    # The other caller. enhance() hands the block to the same gate, so the same two notes it never showed must
    # not turn up here either. Driving the real function rather than _with_sources is the point: a test of
    # _with_sources alone would pass even with the call site reading the raw ranking.
    monkeypatch.setattr(llm_rewrite, "is_enabled", lambda task="rewrite": True)
    monkeypatch.setattr(
        llm_rewrite, "_chat_completion",
        lambda messages, task, **kwargs: (
            "Short answer: send the vocal to its own reverb return.\n\n"
            "Try this: 1. Create the return track. 2. Send the vocal bus to it.\n\n"
            "Check: Audition the vocal dry against the wet return at matched loudness.",
            None,
        ),
    )

    answer = llm_rewrite.enhance(
        QUERY, "", list(CROWDED_RANKING), None, "", source_label, lambda _history: [],
        answer_mode="quick_fix", route="production_dialogue",
    )

    assert answer is not None, "the fixture answer must clear valid_structure or this asserts nothing"
    assert answer.endswith(f"Sources:\n- {source_label(CROWDED_RANKING[1][1])}"), answer
    assert "lufs-delivery.md" not in answer, answer
    assert "vocal-space-notes.md" not in answer, answer