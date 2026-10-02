"""The gate must read the chunks the model was actually shown.

Measured 2 Oct 2026 on the streaming chat surface, kenn-brain-qwen3-8b, cache off. The model's context was
widened to a 12-chunk scan with a 1200-char block and 400 chars per chunk, which was the right call. The
evidence gate was left on the top 3, so a figure that lived in a chunk past #3 was quoted back to us and
reported as invented, along with any source cited from one. Acceptance fell from 41% (12 of 29) to 27%
(4 of 15): 10 unsupported-measurement rejections and 3 fabricated-source rejections, all of them chunks the
gate had never opened. The earlier offline sweep confirmed the measurements reached the model and never
checked that the gate knew about them, which is why this looked like a model problem.

The two windows are not the same list, and that is the subtlety worth pinning. build_raw_context_block
scans results[:12] in retrieval order. display_results re-ranks notes by note_rank_key, which rewards query
affinity, and picks a source-diverse set. So a chunk can be in the model's 12 and outside the gate's 3 --
which is precisely how a quoted number ends up labelled invented. The first two tests below use a fixture
built around that gap: the figure lives in an off-topic note that the model was shown and the gate skipped.

The last four tests guard the other direction, because "read deeper" and "trust the answer" are one edit
apart and only one of them is correct.
"""

from __future__ import annotations

from kenn.core.chat_constants import EVIDENCE_SCAN_WINDOW
from kenn.core.chat_grounding import (
    _evidence_chunks,
    _measurements,
    generated_answer_validation,
    grounding_report,
)
from kenn.llm.llm_rewrite import _CONTEXT_SCAN_WINDOW, build_raw_context_block

from kenn.core.chat_retrieval import display_results, source_label

QUERY = "How should I set up a send reverb on a vocal bus?"


def _note(source: str, text: str, page: int = 0) -> dict:
    return {"kind": "note", "source": source, "title": source, "text": text, "page": page, "tags": []}


# The top of the list is on-topic, so display_results' affinity re-ranking keeps it there. The delivery,
# latency and encoding notes sit lower on raw score but still inside results[:12], which is the slice
# build_raw_context_block scans -- so the model reads them and the gate's top 3 does not.
#
# -9 LUFS is the figure under test. It appears in lufs-delivery.md at raw rank 6, in the model's block, and
# in neither the top 3 nor any other note here.
RANKED_RESULTS: list[tuple[float, dict]] = [
    (100.0, _note("reverb-send-basics.md", "Create a reverb return track and send the vocal bus to it.")),
    (98.0, _note("vocal-space.md", "A vocal sits forward when the reverb sits behind it in the balance.")),
    (96.0, _note("send-routing.md", "Post-fader sends follow the channel fader, pre-fader sends do not.")),
    (60.0, _note("buffer-size-latency.md", "A 512-sample buffer adds about 10 ms of round-trip latency.")),
    (58.0, _note("mp3-encoding.md", "320 kbps MP3 is transparent enough for a rough client reference.")),
    (56.0, _note("lufs-delivery.md", "Streaming platforms normalise to about -14 LUFS, so a -9 LUFS master runs quiet.")),
    (54.0, _note("dither-export.md", "Dither once on export to 16 bits; a 24-bit file needs none.")),
    (52.0, _note("stereo-imaging.md", "Keep the sub content below 120 Hz mono.")),
    (50.0, _note("room-acoustics.md", "A reflective room raises the RT60 and muddies the low mids.")),
    (48.0, _note("gain-structure.md", "Set the trim before the preamp so gain staging stays predictable.")),
    (46.0, _note("print-notes.md", "Print the mix from the session bus, not the master output.")),
    (44.0, _note("null-test.md", "Null one channel against the other to check the pan law.")),
]

# Quotes the -9 LUFS figure and cites the note it came from. Both live past the gate's top 3.
ANSWER_WITH_DEEP_MEASUREMENT = (
    "Short answer: Send the vocal to a dedicated reverb return, and keep the master near -9 LUFS or "
    "streaming will normalise it and take the level decision away from you.\n\n"
    "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it. 3. Check the master loudness "
    "before export.\n\n"
    "Check: Audition the vocal dry against the wet return at matched loudness."
)

# 63 dB is in no note, at any rank, and in no part of the answer's grounding.
ANSWER_WITH_INVENTED_MEASUREMENT = (
    "Short answer: Send the vocal to a dedicated reverb return and pull it back to 63%, otherwise the "
    "reverb swallows the lyric.\n\n"
    "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it. 3. Set the return fader to "
    "63%.\n\n"
    "Check: Audition the vocal dry against the wet return at matched loudness."
)


def _validate(answer: str, results: list[tuple[float, dict]] | None = None) -> dict:
    return generated_answer_validation(
        QUERY,
        list(results if results is not None else RANKED_RESULTS),
        answer,
        route="production_dialogue",
        confidence="medium",
        answer_mode="quick_fix",
    )


def test_a_measurement_quoted_from_a_deeply_ranked_chunk_is_not_called_invented() -> None:
    # The -9 LUFS figure lives in a note the model was shown and the gate's top 3 skipped, which is the
    # 2 Oct 2026 bug: 10 rejections in a 15-answer run, all of them numbers we had put in front of the model.
    report = _validate(ANSWER_WITH_DEEP_MEASUREMENT)
    assert "-9lufs" not in report["unsupported_measurements"], (
        "-9 LUFS is in lufs-delivery.md, a chunk the model was shown; calling it invented is the bug"
    )
    assert "generated answer introduced unsupported measurements" not in report["warnings"]


def test_a_source_cited_from_a_deeply_ranked_chunk_is_not_called_fabricated() -> None:
    # The other half of the same run: 3 rejections for citing a source the gate had not retrieved.
    answer = (
        "Short answer: Keep the master near -9 LUFS so streaming normalisation does not override the mix.\n\n"
        "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it. "
        "3. Check the master loudness before export.\n\n"
        "Sources:\n- Streaming loudness targets (lufs-delivery.md)\n\n"
        "Check: Audition the vocal dry against the wet return at matched loudness."
    )
    report = _validate(answer)
    assert report["fabricated_sources"] == [], (
        "lufs-delivery.md was retrieved and shown to the model, so citing it is not fabrication"
    )
    assert "generated answer cites sources not in the retrieved evidence" not in report["warnings"]


def test_a_measurement_in_no_retrieved_chunk_is_still_caught_as_invented() -> None:
    # The guard against over-widening. 63 dB is in no note at any rank, so no window depth can excuse it. If
    # this passes, the change has become "the gate trusts the answer" rather than "the gate reads as deep as
    # the model was shown", and every other guarantee here is gone with it.
    report = _validate(ANSWER_WITH_INVENTED_MEASUREMENT)
    assert "63%" in report["unsupported_measurements"]
    assert "generated answer introduced unsupported measurements" in report["warnings"]


def test_a_source_absent_from_the_whole_retrieved_set_is_still_caught_as_fabricated() -> None:
    # Same guard for the citation check: a deeper window must not excuse a filename we never retrieved.
    answer = (
        "Short answer: Keep the master near -9 LUFS so streaming normalisation does not override the mix.\n\n"
        "Try this: 1. Create a reverb return track. 2. Send the vocal bus to it. "
        "3. Check the master loudness before export.\n\n"
        "Sources:\n- Loudness history (hall-verbs-2019.md)\n\n"
        "Check: Audition the vocal dry against the wet return at matched loudness."
    )
    report = _validate(answer)
    assert "hall-verbs-2019.md" in report["fabricated_sources"]
    assert "generated answer cites sources not in the retrieved evidence" in report["warnings"]


def test_the_gate_reads_as_deep_as_the_model_was_shown() -> None:
    # One constant behind both windows, so the asymmetry cannot come back by editing only one module.
    assert EVIDENCE_SCAN_WINDOW == 12
    assert _CONTEXT_SCAN_WINDOW == EVIDENCE_SCAN_WINDOW, (
        "the model's scan window and the gate's evidence window are one decision; keep them a single value"
    )
    assert len(_evidence_chunks(QUERY, list(RANKED_RESULTS))) == EVIDENCE_SCAN_WINDOW


def test_the_fixture_really_does_split_the_two_windows() -> None:
    # Without this the tests above could pass for the wrong reason. display_results re-ranks by query
    # affinity, so a note that is 6th on raw score can still surface inside the top 3 -- which is how my
    # first attempt at this fixture passed even with the gate still hard-coded to 3.
    gate_top3 = {chunk["source"] for _score, chunk in display_results(QUERY, list(RANKED_RESULTS), 3)}
    assert "lufs-delivery.md" not in gate_top3, (
        "the note carrying -9 LUFS must be outside the gate's top 3, or this file tests nothing"
    )
    block = build_raw_context_block(RANKED_RESULTS, source_label)
    assert source_label(RANKED_RESULTS[5][1]) in block, (
        "the model must actually be shown the note, or the gate is not the thing that dropped it"
    )
    assert "-9lufs" in _measurements(RANKED_RESULTS[5][1]["text"])
    assert "-9lufs" not in _measurements(
        " ".join(str(chunk.get("text", "")) for _score, chunk in display_results(QUERY, list(RANKED_RESULTS), 3))
    )


def test_grounding_scores_against_the_chunks_the_answer_was_written_from() -> None:
    # grounding_report and answer_quality_report both start from this set, so a score derived from 3 chunks
    # against an answer written from 12 is not a stricter test, it is an incoherent one.
    report = grounding_report(
        QUERY,
        list(RANKED_RESULTS),
        ANSWER_WITH_DEEP_MEASUREMENT,
        route="production_dialogue",
        confidence="medium",
    )
    assert report["source_topic_match"] is True
    assert report["warnings"] == []
