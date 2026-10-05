"""The model is told which figures it may use, and the list is exactly what the gate will accept.

Added 5 Oct 2026: on that day's 8B baseline, unsupported measurements were 8 of 15 probe rejections and 14 of 32
holdout rejections. The system prompt already said "use only numbers printed in an excerpt"; the model still
reached for textbook values. If the list and the gate ever disagree, the list starts causing rejections, so
these tests tie it to the gate's own reading of the evidence.
"""

from __future__ import annotations

from kenn.core.chat_grounding import (
    _gate_evidence_text,
    _measurements,
    generated_answer_validation,
    measurements_in_order,
)
from kenn.llm.llm_rewrite import _ALLOWED_FIGURES_SHOWN, _build_synthesis_messages

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


STEM_SCAN = "Stem scan: the bass sits at -14.2 LUFS with its energy peaking at 55 Hz."


def test_every_listed_figure_written_into_an_answer_passes_the_real_gate_including_specialist_figures() -> None:
    # The first version of the list read only the excerpts, while the gate also accepts the classifier and stem-scan
    # text, so a measured "55 Hz" the gate would pass was missing from the list (adversary review, 5 Oct 2026).
    # The gate labels sources the way retrieval does, so this one needs a real note's fields.
    results = [(10.0, {**SIDECHAIN, "kind": "note", "source": "sidechain.md", "title": "Sidechain"})]
    messages, _shown = _build_synthesis_messages(
        QUERY, "Short answer: duck the bass under the kick.", results, None, "",
        lambda _chunk: "sidechain.md", lambda _history: "", additional_evidence_text=STEM_SCAN,
    )
    listed = _listed(messages[-1]["content"])
    assert "55 Hz" in listed and "-14.2 LUFS" in listed

    answer = ("Short answer: duck the bass under the kick.\n1. Use " + ", ".join(listed) + ".\n"
              "2. Key the compressor from the kick.\nSources: sidechain.md")
    gate = generated_answer_validation(
        QUERY, results, answer, route="mix", confidence="high", answer_mode="",
        additional_evidence_text=STEM_SCAN,
    )
    assert gate["unsupported_measurements"] == []


def test_a_long_list_is_cut_at_the_cap_and_stops_claiming_to_be_complete() -> None:
    timeline = {"text": " ".join(f"Bar {n}: {-20 + n} LUFS." for n in range(1, 21))}
    prompt, _shown = _prompt([(10.0, timeline)])
    line = next(line for line in prompt.splitlines() if line.startswith("Figures from the excerpts you may use"))
    assert line.count("LUFS") == _ALLOWED_FIGURES_SHOWN
    assert "and others printed in the excerpts" in line


def test_the_tail_of_a_thousands_comma_is_never_listed_as_a_figure() -> None:
    assert measurements_in_order("Air shelf from 10,000 Hz, presence at 3 kHz.") == ["3 kHz"]
