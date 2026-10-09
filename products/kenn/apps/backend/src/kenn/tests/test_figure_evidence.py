"""The gate accepts a figure the producer typed or a shown note states, and still refuses one from anywhere else.

8 Oct 2026 bench (kenn-evaluation-data/2026-10-08-refused-figures): 116 figures refused over 12 runs. 20 were in the
producer's own question and 23 in a shown note past its 400-character excerpt.
"""

from __future__ import annotations

import pytest

from kenn.core import chat_grounding
from kenn.core.chat_grounding import (
    _evidence_chunks,
    _measurements,
    evidence_measurements,
    generated_answer_validation,
)

# 552 characters with no figure in them. The model is shown the first 400 (_CONTEXT_CHUNK_CHARS in llm_rewrite), so
# the sentence after this is in the note but never in the excerpt.
LEAD = "Streaming services turn loud masters down, so pushing level past their target buys nothing. " * 6

SHOWN = {
    "id": "loud-short",
    "kind": "note",
    "title": "Loudness For Streaming",
    "source": "loudness-for-streaming.md",
    "page": 0,
    "section": "Short answer",
    "text": LEAD + "Leave the true peak at -1 dBTP so the lossy encode does not clip.",
}
SIBLING = {
    "id": "loud-check",
    "kind": "note",
    "title": "Loudness For Streaming",
    "source": "loudness-for-streaming.md",
    "page": 0,
    "section": "Check",
    "text": "Measure the integrated level over the whole song; most services normalise to -14 LUFS.",
}
OTHER_NOTE = {
    "id": "vocal-comp",
    "kind": "note",
    "title": "Vocal Compression",
    "source": "vocal-compression.md",
    "page": 0,
    "section": "Try this",
    "text": "Start with 3 dB of gain reduction on the vocal and listen for the breaths.",
}
MANUAL_PAGE = {
    "id": "manual-212",
    "kind": "manual",
    "title": "Live 12 Reference Manual",
    "source": "live12-manual.pdf",
    "page": "212",
    "section": "",
    "text": "EQ Eight has eight bands per channel, each with its own filter type.",
}
NEXT_MANUAL_PAGE = {**MANUAL_PAGE, "id": "manual-213", "page": "213", "text": "The low cut defaults to 30 Hz."}

QUERY = "How loud should my master be for Spotify?"

# model_evidence() drops anything scored under 4.0 as too weak to show, so a fixture scored 1.0 is never evidence.
SCORE = 50.0


@pytest.fixture
def index(monkeypatch):
    """The whole-index copy the gate reads a shown note's other sections from."""
    def use(*chunks: dict) -> None:
        monkeypatch.setattr(chat_grounding, "load_chunks", lambda: list(chunks))

    use()
    return use


def _refused(answer: str, results: list[dict], query: str = QUERY) -> list[str]:
    return generated_answer_validation(
        query, [(SCORE, chunk) for chunk in results], answer,
        route="production", confidence="high", answer_mode="quick_fix",
    )["unsupported_measurements"]


def test_the_fixture_note_puts_its_figure_past_the_excerpt_the_model_sees():
    # Without this, the past-the-excerpt test below would pass on the old gate too and prove nothing.
    (_score, _chunk, body), = _evidence_chunks([(SCORE, SHOWN)])
    assert "-1dbtp" not in _measurements(body)


def test_a_figure_past_the_excerpt_of_a_shown_note_is_accepted(index):
    assert _refused("Keep the true peak at -1 dBTP before you export.", [SHOWN]) == []


def test_a_figure_from_another_section_of_a_shown_note_is_accepted(index):
    index(SHOWN, SIBLING, OTHER_NOTE)
    assert _refused("Aim for -14 LUFS integrated.", [SHOWN]) == []


def test_a_figure_only_an_unshown_note_states_is_still_refused(index):
    # The 2 Oct "wide" bug: a 3 dB waved through on a chunk the model never saw. Widening to the shown note's other
    # sections must not reopen that.
    index(SHOWN, SIBLING, OTHER_NOTE)
    assert _refused("Take 3 dB off the master bus first.", [SHOWN]) == ["3db"]


def test_a_figure_the_producer_typed_is_not_one_the_model_invented(index):
    # eq-kick-bass-phase, 8 Oct: all 8 answers that said the producer's "60 Hz" back were refused.
    query = "Why do my kick and bass cancel around 60 Hz?"
    assert _refused("The cancel around 60 Hz is the two waves out of phase.", [OTHER_NOTE], query) == []
    assert _refused("The cancel around 80 Hz is the two waves out of phase.", [OTHER_NOTE], query) == ["80hz"]


def test_a_shown_manual_page_does_not_open_the_rest_of_the_manual(index):
    # Every manual chunk shares one source, so widening to "the whole manual" would accept nearly any Hz.
    index(MANUAL_PAGE, NEXT_MANUAL_PAGE)
    assert _refused("Set the low cut to 30 Hz.", [MANUAL_PAGE]) == ["30hz"]


def test_the_stream_guard_allows_the_figures_the_final_gate_allows(index):
    # The guard stops a stream for good, so a figure it refuses and the final gate would accept costs the answer.
    index(SHOWN, SIBLING, OTHER_NOTE)
    allowed = evidence_measurements([(SCORE, SHOWN)], query="Is 60 Hz too low for the sub?")
    assert {"60hz", "-1dbtp", "-14lufs"} <= allowed
    assert "3db" not in allowed
