"""A stem-scan or classifier figure the gate accepts must reach the model, with enough of its context to be used.

Leftovers from the review of draft/allowed-figures. The allowed-figures list read the specialist text last, so the
12-figure cap dropped it first while the prompt told the model any unlisted figure goes in words. The model also met
that text only through the 300-character draft, and the template puts the "Evidence from your supplied analysis"
lines at its very end, which is exactly the part a 300-character cut removes.
"""

from __future__ import annotations

import json

from kenn.core import chat_answer, chat_retrieval, route_log, session_memory
from kenn.core.evidence import MARKER
from kenn.llm import llm_rewrite as llm
from kenn.llm.llm_rewrite import _ALLOWED_FIGURES_SHOWN, _SPECIALIST_BLOCK_CHARS, _build_synthesis_messages
from kenn.tests.test_allowed_figures import QUERY, SIDECHAIN, _prompt
from kenn.tests.test_streamed_generation_prefix_guard import ACCEPTED_ANSWER, CHUNKS
from kenn.tests.test_streamed_generation_prefix_guard import QUERY as SIDECHAIN_QUERY

SPECIALIST_HEADER = "Results from the analysis you ran on the supplied audio"

# Twenty LUFS readings are more than the cap, the way a long review timeline is.
TIMELINE = {"text": " ".join(f"Bar {n}: {-20 + n} LUFS." for n in range(1, 21))}

# A specialist observation placed past the 300-character draft cut, ending on a figure only it carries.
LONG_SCAN = (
    "The supplied stem-energy proxy flagged the Bass + Piano pair in the bass band, with competing energy in "
    "45.4% of frames. Treat this as a listening-check priority, not proof of audible masking, a responsible "
    "track, or an automatic EQ move. The kick stem peaks near 62 Hz."
)


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


def test_specialist_text_past_the_draft_cut_still_reaches_the_model() -> None:
    template = "Short answer: " + "duck the bass under the kick. " * 30 + "\n" + LONG_SCAN
    prompt = _messages([(10.0, SIDECHAIN)], LONG_SCAN, template)

    assert "62 Hz" not in template[:300], "the fixture must put the figure beyond the draft cut"
    block = prompt.split(SPECIALIST_HEADER, 1)[1].split("\n\n", 1)[0]
    assert "Bass + Piano" in block and "45.4%" in block and "62 Hz" in block
    assert "not proof of audible masking" in block, "the tool's own limit travels with its figure"


def test_the_draft_and_the_note_excerpts_keep_their_own_windows() -> None:
    template = "Short answer: " + "duck the bass under the kick. " * 30
    prompt = _messages([(10.0, SIDECHAIN)], LONG_SCAN, template)

    draft = prompt.split("prefer synthesising directly from the source excerpts above):\n", 1)[1].split("\n\n", 1)[0]
    assert draft == template[:300]
    assert "Keep the overlap at 60-120 Hz in check." in prompt.split("Draft answer", 1)[0]


def test_a_very_long_specialist_text_is_cut_to_its_budget() -> None:
    prompt = _messages([(10.0, SIDECHAIN)], " ".join(f"Pair {n} competes at {n} Hz." for n in range(1, 200)))

    block = prompt.split(SPECIALIST_HEADER, 1)[1].split("\n", 1)[1].split("\n\n", 1)[0]
    assert len(block) <= _SPECIALIST_BLOCK_CHARS
    assert block.endswith("...")


def test_no_specialist_text_adds_no_block_and_changes_nothing_else() -> None:
    with_none = _messages([(10.0, SIDECHAIN)], "")

    assert SPECIALIST_HEADER not in with_none
    assert with_none == _prompt([(10.0, SIDECHAIN)])[0]


def _history_with_stem_scan() -> list[dict]:
    packet = {
        "schema": "kenn.evidence.v1",
        "source": "stem_masking_analysis",
        "facts": [
            {"name": "masking_candidate_count", "value": 2, "unit": "candidates"},
            {"name": "masking_highest_competing_frame_fraction", "value": 0.454, "unit": "ratio"},
            {"name": "masking_highest_pair", "value": "Bass + Piano"},
            {"name": "masking_highest_band", "value": "bass"},
        ],
        "limitations": ["Not a perceptual masking model."],
    }
    return [{"role": "user", "content": MARKER + json.dumps(packet)}]


def test_make_answer_carries_a_stem_scan_into_the_prompt_the_model_reads(monkeypatch, tmp_path) -> None:
    # Only the model call is faked: the template, the specialist read, the real prompt builder and the real gate
    # all run, so a stem-scan figure that stops short of the prompt anywhere along that path fails here.
    seen: list[list[dict]] = []

    def fake_completion(messages, *args, **kwargs):
        seen.append(messages)
        return ACCEPTED_ANSWER, None

    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(route_log, "record", lambda *a, **k: None)
    monkeypatch.setattr(llm, "is_enabled", lambda *a, **k: True)
    monkeypatch.setattr(llm, "_chat_completion", fake_completion)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", llm.enhance)
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: False)
    monkeypatch.setattr(chat_answer, "intent_guard_failed", lambda *a: False)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_retrieval, chat_answer):
        monkeypatch.setattr(module, "load_chunks", lambda: [c for _, c in CHUNKS])
        monkeypatch.setattr(module, "load_terms", lambda: terms)

    chat_answer.make_answer(SIDECHAIN_QUERY, list(CHUNKS), history=_history_with_stem_scan(), route="production")

    assert seen, "the model was never asked"
    prompt = seen[0][-1]["content"]
    block = prompt.split(SPECIALIST_HEADER, 1)[1]
    assert "Bass + Piano" in block and "45.4%" in block
    assert "45.4%" in _figure_line(prompt)
