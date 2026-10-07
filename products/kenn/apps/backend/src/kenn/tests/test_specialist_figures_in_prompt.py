"""A stem-scan or classifier figure the gate accepts must reach the model, with enough of its context to be used.

Leftover from the review of draft/allowed-figures. The allowed-figures list read the specialist text
last, so the 12-figure cap dropped it first while the prompt told the model any unlisted figure goes in words.
"""

from __future__ import annotations

from kenn.llm.llm_rewrite import _ALLOWED_FIGURES_SHOWN, _build_synthesis_messages
from kenn.tests.test_allowed_figures import QUERY, SIDECHAIN

# Twenty LUFS readings are more than the cap, the way a long review timeline is.
TIMELINE = {"text": " ".join(f"Bar {n}: {-20 + n} LUFS." for n in range(1, 21))}


def _messages(results: list, specialist: str, template: str = "Short answer: duck the bass under the kick.") -> str:
    messages, _shown = _build_synthesis_messages(
        QUERY, template, results, None, "", lambda _chunk: "sidechain.md", lambda _history: "",
        additional_evidence_text=specialist,
    )
    return messages[-1]["content"]


def _figure_line(prompt: str) -> str:
    return next(line for line in prompt.splitlines() if line.startswith("Figures"))


def test_the_cap_drops_note_figures_before_a_specialist_figure() -> None:
    prompt = _messages([(10.0, TIMELINE)], "Stem scan: the bass peaks at 55 Hz.")

    line = _figure_line(prompt)
    assert "55 Hz" in line
    assert line.index("55 Hz") < line.index("LUFS")
    # The cap still holds, and the note readings that did not fit are the ones that went.
    assert line.count("Hz") + line.count("LUFS") == _ALLOWED_FIGURES_SHOWN
    assert "and others printed in the excerpts" in line


def test_the_note_figures_keep_their_reading_order_behind_the_specialist_ones() -> None:
    prompt = _messages([(10.0, SIDECHAIN)], "Stem scan: the bass peaks at 55 Hz.")

    listed = _figure_line(prompt).split(": ", 1)[1].rstrip(".").split(", ")
    assert listed[:4] == ["55 Hz", "150 ms", "5 ms", "6 dB"]
