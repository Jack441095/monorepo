"""The prompt and the gate have to read the same excerpts under the same budget, override included.

Sharing model_evidence() fixed the excerpt LIST on 2 Oct 2026 but not the budget it was read at. The prompt path
reads KENN_LLM_CONTEXT_CHARS; the gate took model_evidence()'s max_chars default, which is _CONTEXT_BLOCK_CHARS. So
an override moved one side and left the other, and the failure is the one the earlier list fix had just measured: at
300 chars on index v-db8c6334cf63 the model saw 1 excerpt and the gate judged 3, against the 41% to 27% drop recorded
hours earlier that day from 3 against 12 in the other direction. One run in
tooling/evaluation/results/KENN_LANDING_ATTRIBUTION_2026-10-01.json carried the override, so the gap was reachable
from a shell.

The budget is resolved once now, in llm_rewrite.resolve_context_chars(), and both sides ask it for the value. The
gate's thresholds are untouched by that: it judges fewer numbers, because the model was shown fewer numbers.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("KENN_LLM_ENABLED", "0")

from kenn.core import chat_grounding
from kenn.core.chat_retrieval import source_label
from kenn.llm import llm_rewrite
from kenn.llm.llm_rewrite import (
    _CONTEXT_BLOCK_CHARS,
    _build_synthesis_messages,
    resolve_context_chars,
)

QUESTION = "What release time should I use for sidechain compression on bass?"


# Seven ranked chunks, each with a distinct measurement, so the excerpt count is a real function of the budget
# rather than a coincidence. Shaped like the sidechain/bass notes that produced the original 1-vs-3 measurement: the
# usable chunks sit behind a Related-questions block that cleans to nothing, so rank order alone does not decide how
# many excerpts fit.
def _note(cid: str, text: str, title: str, *, section: str = "Try this", score: float = 12.0):
    return score, {
        "id": cid,
        "kind": "note",
        "title": title,
        "source": "sidechain-bass-to-kick.md",
        "page": 0,
        "section": section,
        "text": text,
    }


RANKED_RESULTS = [
    _note("rq", "- What release time for sidechain compression?", "Sidechain Bass To Kick",
          section="Related questions", score=18.0),
    _note("a", "Set the release around 150 ms so the bass recovers before the next kick. "
               "Watch the depth on short notes.", "Sidechain Bass To Kick", score=16.0),
    _note("b", "A ratio of 4:1 keeps the pumping shallow enough to mix under a vocal. "
               "Go past 6:1 and the bass starts to duck audibly.", "Sidechain Ratio", score=14.0),
    _note("c", "Attack of 5 ms lets the bass transient through untouched. "
               "Faster and the kick loses its click.", "Sidechain Attack", score=12.0),
    _note("d", "High-pass the keyed return above 300 Hz so the envelope never hears the vocal. "
               "Keep the knee soft at 2 dB.", "Sidechain Routing", score=10.0),
    _note("e", "Automate depth 3 dB down and up across the chorus rather than leaving it fixed. "
               "It sits better against 6 dB of vocal compression.", "Sidechain Automation", score=8.0),
    _note("f", "Shorten release to 80 ms when the tempo pushes the kick past 140 bpm. "
               "The bass stops pumping before the phrase changes.", "Sidechain Tempo", score=6.0),
]


def _prompt_excerpts(results: list[tuple[float, dict]] | None = None) -> list[tuple[float, dict, str]]:
    """The excerpt list the model is handed, straight off _build_synthesis_messages' return value."""
    _messages, shown = _build_synthesis_messages(
        QUESTION,
        "Short answer: key the bass compressor from the kick and back the release off until the bass recovers.",
        RANKED_RESULTS if results is None else results,
        None,
        "",
        source_label,
        lambda _history: "",
    )
    return shown


def _gate_excerpts() -> list[tuple[float, dict, str]]:
    """The excerpt list the gate judges, through the private helper every check in chat_grounding calls."""
    return chat_grounding._evidence_chunks(RANKED_RESULTS)


def _budgets_at(configured: str | None) -> dict[str, int]:
    """The max_chars each call site hands model_evidence, under one env configuration.

    Recorded as numbers rather than as excerpt counts, because a count can match by luck on a fixture whose chunks
    happen to fit. llm_rewrite.model_evidence is what _build_synthesis_messages calls; chat_grounding holds its own
    binding, which is the one that let the gate keep the default.
    """
    patcher = pytest.MonkeyPatch()
    seen: dict[str, int] = {}

    def _spy(label: str):
        def _inner(_results, _label, *, max_chars: int = 0):
            seen[label] = max_chars
            return "(no source excerpts provided)", []
        return _inner

    try:
        if configured is None:
            patcher.delenv("KENN_LLM_CONTEXT_CHARS", raising=False)
        else:
            patcher.setenv("KENN_LLM_CONTEXT_CHARS", configured)
        patcher.setattr(llm_rewrite, "model_evidence", _spy("prompt"))
        patcher.setattr(chat_grounding, "model_evidence", _spy("gate"))
        _prompt_excerpts()
        _gate_excerpts()
        return dict(seen)
    finally:
        patcher.undo()


def test_the_gate_reads_the_same_excerpt_list_the_prompt_built_at_the_configured_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At 300 chars the model and the gate must see the same excerpts, which is not the whole 1200-char list.

    The gate used to take model_evidence()'s default while the prompt honoured the override, so the model read 1
    excerpt and the gate judged 3 on the real sidechain query. Equal counts on this fixture are the regression, and
    equal counts alone can be luck, so the bodies are compared too: the gate's evidence text is built from them.
    """
    monkeypatch.setenv("KENN_LLM_CONTEXT_CHARS", "300")

    prompt = _prompt_excerpts()
    gate = _gate_excerpts()

    assert len(gate) == len(prompt)
    assert [body for _s, _c, body in gate] == [body for _s, _c, body in prompt]
    assert [str(chunk.get("id")) for _s, chunk, _b in gate] == [str(chunk.get("id")) for _s, chunk, _b in prompt]
    # Not vacuous: the override is still a real narrowing, and the gate narrowed with it. Measured on this fixture:
    # 1 excerpt at 300 chars, 2 at 650, 5 at 1200.
    monkeypatch.delenv("KENN_LLM_CONTEXT_CHARS")
    wider_prompt = _prompt_excerpts()
    assert len(wider_prompt) > len(gate), "300 chars has to hold fewer excerpts than 1200, or this fixture proves nothing"
    assert len(gate) >= 1


def test_an_override_reaches_both_call_sites_with_the_same_number() -> None:
    """Neither side may read the budget from anywhere but the shared resolver.

    650 rather than 300 because that is the value the 1 Oct latency sweep pinned, and a run under it is the one a
    capture gets compared against.
    """
    seen = _budgets_at("650")

    assert seen == {"prompt": 650, "gate": 650}
    assert seen["gate"] != _CONTEXT_BLOCK_CHARS, "the gate fell back to the default while the prompt was overridden"


def test_both_sides_resolve_to_the_block_default_when_the_env_var_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset is the production case: both readers get 1200, the value the sweep settled on.

    1200/400 exposed 10 measurements across 3 of 5 sidechain queries where 650/240 exposed 2 across 1, so falling back
    to anything else quietly puts the context back below what the gate then demands.
    """
    monkeypatch.delenv("KENN_LLM_CONTEXT_CHARS", raising=False)

    assert resolve_context_chars() == 1200
    assert resolve_context_chars() == _CONTEXT_BLOCK_CHARS
    assert _CONTEXT_BLOCK_CHARS == 1200
    assert _budgets_at(None) == {"prompt": 1200, "gate": 1200}

    prompt = _prompt_excerpts()
    gate = _gate_excerpts()
    assert [body for _s, _c, body in gate] == [body for _s, _c, body in prompt]
    assert len(gate) > 3, "the default has to carry more than the override, or the two cases are not distinguishable"

    # An empty value is the shell that exports an unset variable, and it means the same thing.
    monkeypatch.setenv("KENN_LLM_CONTEXT_CHARS", "")
    assert resolve_context_chars() == _CONTEXT_BLOCK_CHARS
    assert _budgets_at("") == {"prompt": 1200, "gate": 1200}


def test_the_two_capture_budget_fields_cannot_diverge() -> None:
    """fix-12 records evidence_budget_chars for the gate and prompt_context_chars for the prompt, and warns on a split.

    Each is read off the same resolver, so a run taken at any budget records the same number twice and the re-scorer's
    mismatch warning can only fire on a capture taken before this fix. The loop covers the values a run has actually
    been taken at: unset, the 300 from the attribution run, and the 650 the 1 Oct latency sweep pinned.
    """
    for configured in (None, "300", "650"):
        seen = _budgets_at(configured)

        evidence_budget_chars = seen["gate"]
        prompt_context_chars = seen["prompt"]
        assert evidence_budget_chars == prompt_context_chars == _resolved(configured), configured


def _resolved(configured: str | None) -> int:
    patcher = pytest.MonkeyPatch()
    try:
        if configured is None:
            patcher.delenv("KENN_LLM_CONTEXT_CHARS", raising=False)
        else:
            patcher.setenv("KENN_LLM_CONTEXT_CHARS", configured)
        return resolve_context_chars()
    finally:
        patcher.undo()


def test_a_non_numeric_override_stops_the_run_instead_of_quietly_rerunning_it_at_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in a measurement run should fail it, not re-measure it at 1200 and report a latency nobody asked for.

    This is the one place the old inline read could be second-guessed, and swallowing the ValueError to keep an
    import path quiet would put a capture on disk claiming 1200 while the run did something else.
    """
    monkeypatch.setenv("KENN_LLM_CONTEXT_CHARS", "12o0")

    with pytest.raises(ValueError):
        resolve_context_chars()
