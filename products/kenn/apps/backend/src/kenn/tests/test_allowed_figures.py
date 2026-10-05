"""The model is told which figures it may use, and the list is exactly what the gate will accept.

Added 5 Oct 2026: on that day's 8B baseline, unsupported measurements were 8 of 15 probe rejections and 14 of 32
holdout rejections. The system prompt already said "use only numbers printed in an excerpt"; the model still
reached for textbook values. If the list and the gate ever disagree, the list starts causing rejections, so
these tests tie it to the gate's own reading of the evidence.
"""

from __future__ import annotations

from kenn.core.chat_grounding import _gate_evidence_text, _measurements, measurements_in_order
from kenn.llm.llm_rewrite import _build_synthesis_messages

QUERY = "How should I set the sidechain on my bass?"

SIDECHAIN = {"text": "Key the bass compressor from the kick. Release around 150 ms, attack 5 ms, 4:1, "
                     "and 6 dB of gain reduction. Keep the overlap at 60-120 Hz in check."}
ROUTING = {"text": "Put the compressor on the bass track and choose the kick as the sidechain source."}


def _prompt(results: list) -> tuple[str, list]:
    messages, shown = _build_synthesis_messages(
        QUERY, "Short answer: duck the bass under the kick.", results, None, "",
        lambda _chunk: "sidechain.md", lambda _history: "",
    )
    return messages[-1]["content"], shown


def _listed(prompt: str) -> list[str]:
    line = next(line for line in prompt.splitlines() if line.startswith("Figures you may use"))
    return line.split(": ", 1)[1].rstrip(".").split(", ")


def test_every_listed_figure_is_one_the_gate_accepts_and_none_are_missing() -> None:
    prompt, shown = _prompt([(10.0, SIDECHAIN)])
    listed = _listed(prompt)
    assert {"".join(f.lower().split()) for f in listed} == _measurements(_gate_evidence_text(shown))
    assert listed[:3] == ["150 ms", "5 ms", "6 dB"], "the note's own spelling, in reading order"


def test_a_range_is_listed_as_its_two_ends_because_that_is_how_the_gate_reads_it() -> None:
    assert measurements_in_order("Keep the overlap at 60-120 Hz.") == ["60 Hz", "120 Hz"]


def test_the_same_figure_spelled_two_ways_is_listed_once() -> None:
    assert measurements_in_order("Cut at 120 Hz, and again at 120Hz.") == ["120 Hz"]


def test_evidence_with_no_figures_tells_the_model_to_use_words() -> None:
    prompt, _shown = _prompt([(10.0, ROUTING)])
    assert "Figures you may use" not in prompt
    assert "The excerpts give no figures." in prompt
