"""The captured evidence_text has to be the evidence the gate read, or an offline leak check lies.

On 2 Oct 2026 the capture rendered its field from display_results(query, results, 3) and raw chunk["text"] while
the grounding gate had been reading model_evidence()'s cleaned, budgeted excerpts since that morning. 14 of the 22
rows in that day's capture disagreed with the gate, and a check for answers citing a measurement absent from
evidence reported 8 of 18 accepted answers leaking when the same check against the gate's own evidence reported 0
of 18. The field is now built from the bodies model_evidence() returns, and these tests keep it there.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

# Before any kenn import, so no model-backed path opens in a test.
os.environ["KENN_LLM_ENABLED"] = "0"

SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "measure_chat_latency.py"
module = importlib.util.module_from_spec(
    spec := importlib.util.spec_from_file_location("measure_chat_latency_capture", SCRIPT)
)
assert spec.loader
spec.loader.exec_module(module)

# 2889 characters, so the 400-char chunk budget has to cut it: a fixture that fits the budget would let a
# reverted field pass by luck.
LONG_CHUNK_TEXT = " ".join(
    f"step {i} sets the filter to {i} hz and a ratio of 4:1 with a {i} ms release" for i in range(40)
)


def _note(cid: str, text: str, title: str, *, section: str = "Try this", score: float = 12.0) -> tuple[float, dict]:
    return score, {
        "id": cid,
        "kind": "note",
        "title": title,
        "source": "sidechain-bass-to-kick.md",
        "page": 0,
        "section": section,
        "text": text,
    }


RESULTS = [
    _note("a", "Start the release at 150 ms and set the ratio to 4:1.", "Sidechain Bass To Kick"),
    _note("b", LONG_CHUNK_TEXT, "Sidechain Technique Detail"),
    # Cleans to "" inside model_evidence, which is why the old top-3 render disagreed with the gate on this shape.
    _note("c", "- What release time for sidechain compression?", "Sidechain Bass To Kick", section="Related questions"),
]

QUESTION = "What release time should I use for sidechain compression on bass?"


def _captured_row(tmp_path: Path) -> dict:
    """Install the capture, push one answer through the wrapped gate, and read back the row it wrote."""
    from kenn.core import chat_answer

    path = tmp_path / "answers.jsonl"
    real = chat_answer.generated_answer_validation
    try:
        module._install_capture(path)
        chat_answer.generated_answer_validation(
            QUESTION,
            RESULTS,
            "Short answer:\nStart the release at 150 ms at 4:1.\n",
            route="mix",
            confidence="high",
            answer_mode="ableton_steps",
        )
    finally:
        chat_answer.generated_answer_validation = real

    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


def test_captured_evidence_text_is_the_excerpt_bodies_the_gate_reads(tmp_path: Path) -> None:
    """The capture field must be model_evidence's returned bodies, not raw chunk text, or the two drift again.

    A field built from chunk["text"] once reported 8 of 18 accepted answers as citing an absent measurement when
    the gate held that measurement on screen. That was a harness artifact and it was nearly published as a gate
    regression, so this pins the field to the one function the prompt and the gate share.
    """
    from kenn.core.chat_grounding import _evidence_chunks
    from kenn.core.chat_retrieval import source_label
    from kenn.llm.llm_rewrite import model_evidence

    row = _captured_row(tmp_path)

    _block, shown = model_evidence(RESULTS, source_label)
    expected = " ".join(
        " ".join((str(chunk.get("title") or ""), str(chunk.get("source") or ""), body))
        for _score, chunk, body in shown
    )
    assert row["evidence_text"] == expected
    assert row["evidence_text"] == module.gate_evidence_text(_evidence_chunks(RESULTS))

    # Not vacuous: the long chunk was cut to the 400-char budget and the Related-questions chunk was dropped
    # entirely. A field that carried the raw text would show 2889 characters here and four chunks.
    assert [body for _s, _c, body in shown][1] != LONG_CHUNK_TEXT
    assert len(shown[1][2]) <= 400, shown[1][2]
    assert [str(chunk.get("id")) for _s, chunk, _b in shown] == ["a", "b"]


def test_captured_evidence_text_is_not_the_top_three_raw_chunk_render(tmp_path: Path) -> None:
    """The 2 Oct 2026 field shape specifically: display_results(query, results, 3) joined over chunk["text"].

    Reverting to this render is the exact regression the field exists to prevent, and on this fixture it also
    drops a chunk the gate held.
    """
    from kenn.core.chat_retrieval import display_results

    row = _captured_row(tmp_path)
    stale = " ".join(
        " ".join((str(chunk.get("title") or ""), str(chunk.get("source") or ""), str(chunk.get("text") or "")))
        for _score, chunk in display_results(QUESTION, RESULTS, 3)
    )

    assert row["evidence_text"] != stale
    # The old render was narrower than the gate's, which is the phantom-leak mechanism: a measurement the model
    # was shown counted as absent from evidence.
    assert len(row["evidence_text"]) > len(stale)


def test_capture_records_the_index_version_and_evidence_budget(tmp_path: Path) -> None:
    """A capture that records neither cannot be checked against today's gate, and that is why 2 Oct was re-measured."""
    from kenn.llm.llm_rewrite import _CONTEXT_BLOCK_CHARS

    row = _captured_row(tmp_path)

    assert row["evidence_budget_chars"] == _CONTEXT_BLOCK_CHARS
    assert row["prompt_context_chars"] == int(os.environ.get("KENN_LLM_CONTEXT_CHARS") or _CONTEXT_BLOCK_CHARS)
    assert row["evidence_chunks_shown"] == 2
    pointer = module.KENN_ROOT / "apps/backend/src/kenn/data/index/CURRENT"
    assert row["index_version"] == (pointer.read_text(encoding="utf-8").strip() if pointer.is_file() else "")


def test_capture_records_the_same_budget_the_prompt_and_the_gate_both_read(tmp_path: Path, monkeypatch) -> None:
    """KENN_LLM_CONTEXT_CHARS moves the prompt's budget and the gate's together, and the capture has to show that.

    The gate used to read model_evidence()'s 1200 default while the prompt honoured the override, so at
    KENN_LLM_CONTEXT_CHARS=300 the model was shown 1 excerpt and the gate judged 3. Both readers now go
    through resolve_context_chars(), so the two recorded numbers are equal by construction and a re-score of
    any row is exact. This test asserts equality rather than a split because the split was the defect; if a
    future change reintroduces one, it fails here instead of quietly flattering acceptance.
    """
    from kenn.llm.llm_rewrite import resolve_context_chars

    monkeypatch.setenv("KENN_LLM_CONTEXT_CHARS", "650")
    row = _captured_row(tmp_path)

    assert row["prompt_context_chars"] == 650
    assert row["evidence_budget_chars"] == 650
    assert row["prompt_context_chars"] == row["evidence_budget_chars"]

    monkeypatch.delenv("KENN_LLM_CONTEXT_CHARS", raising=False)
    # A second directory, because _captured_row reads the FIRST row of answers.jsonl and a second call on the
    # same path would append and then hand back the 650 row written above.
    unset = _captured_row(tmp_path / "unset")

    assert unset["prompt_context_chars"] == unset["evidence_budget_chars"] == int(resolve_context_chars())