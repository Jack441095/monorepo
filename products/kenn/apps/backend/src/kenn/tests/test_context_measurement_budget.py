"""The measurements the evidence gate judges must survive the trip to the model.

Measured 2 Oct 2026 on "What release time should I use for sidechain compression on bass?". The "Try this"
chunk of the "Sidechain Bass To Kick" note ranked #2 at score 1030.88 and carried all four measurements —
150 ms, 4:1, 5 ms, 6 dB. chat_grounding.generated_answer_validation validates against the raw chunk text, so
the gate saw all four. The model saw a 240-char window over the same chunk and saw none of them, so it
answered from its training prior and the gate rejected the answer for measurements it had never been shown.
Acceptance sat at ~36% with "unsupported measurements" as the dominant rejection. The gate was right; the
context was too small.

These tests pin the two budgets so the asymmetry cannot come back silently.
"""

from __future__ import annotations

import inspect

import pytest

from kenn.llm.llm_rewrite import (
    _CONTEXT_BLOCK_CHARS,
    _CONTEXT_CHUNK_CHARS,
    _CONTEXT_SCAN_WINDOW,
    _build_synthesis_messages,
    _clean_chunk_for_synthesis,
    build_raw_context_block,
)

QUERY = "What release time should I use for sidechain compression on bass?"

# Shaped like the real note's "Try this" chunk: the numbers sit after two sentences of setup, which is exactly
# where the old 240-char window started cutting. At 240 the excerpt kept 150 ms and 4:1 and dropped 5 ms and
# 6 dB; at 400 it keeps all four.
SIDECHAIN_CHUNK = {
    "text": "Try this: Put a compressor on the bass bus and key it from the kick.\n"
            "1. Set the compressor's sidechain input to the kick track.\n"
            "2. Release around 150 ms so the bass recovers before the next kick.\n"
            "3. A ratio of 4:1 keeps the pumping shallow.\n"
            "4. Attack of 5 ms lets the bass transient through.\n"
            "5. Depth of 6 dB is plenty; deeper reads as a sidechain artefact.\n"
}
MEASUREMENTS = ("150 ms", "4:1", "5 ms", "6 dB")

# A higher-scoring but useless chunk in front, so the measurement chunk lands at rank #2 like the real run.
RANKED_RESULTS = [
    (1180.40, {"text": "Use the Utility for level matching between the master and the monitoring path."}),
    (1030.88, SIDECHAIN_CHUNK),
]


def _label(chunk: dict) -> str:
    return "sidechain-bass-to-kick.md" if chunk is SIDECHAIN_CHUNK else "live-set-utility.md"


def _answer_prompt() -> str:
    messages = _build_synthesis_messages(
        QUERY,
        "Short answer: key the bass compressor from the kick, then back the release off until the bass recovers.",
        RANKED_RESULTS,
        None,
        "",
        _label,
        lambda _history: "",
    )
    return messages[-1]["content"]


def test_release_time_in_a_ranked_try_this_chunk_reaches_the_model_context() -> None:
    """At the default budget every measurement in the ranked chunk survives to the prompt.

    It used to reach the model with 5 ms and 6 dB cut off at 240 characters, so a correct answer was
    indistinguishable from a guess once the gate scored it against the untruncated note.
    """
    block = build_raw_context_block(RANKED_RESULTS, _label)

    missing = [value for value in MEASUREMENTS if value not in block]
    assert not missing, f"truncated out of the model context: {missing}\n{block}"
    assert "150 ms" in block, "the release time is the number the producer asked for"
    assert block.count("<source_excerpt") == block.count("</source_excerpt>")
    assert len(block) <= _CONTEXT_BLOCK_CHARS, len(block)


def test_a_240_char_excerpt_window_dropped_two_of_the_four_measurements() -> None:
    """The loss this file exists to prevent, restated at the old window so it stays measurable.

    A partial set reads as evidence rather than as truncation, which is why the answer looked grounded and
    was not.
    """
    narrowed = _clean_chunk_for_synthesis(SIDECHAIN_CHUNK, max_len=240)
    assert "150 ms" in narrowed, "the loss is partial, not total, so it has to be stated"
    assert "5 ms" not in narrowed and "6 dB" not in narrowed, narrowed

    assert all(value in _clean_chunk_for_synthesis(SIDECHAIN_CHUNK, max_len=_CONTEXT_CHUNK_CHARS)
               for value in MEASUREMENTS)


def test_the_context_budgets_are_the_measured_knee_rather_than_the_old_650_and_240() -> None:
    """A silent revert to 650/240 puts the bug straight back, so both constants are asserted directly.

    Over five real sidechain and bass queries 650/240 averaged 389 chars and exposed 2 measurements across
    one of them; 1200/400 averaged 596 chars and exposed 10 across three. 1800/400 and 2600/600 gained
    nothing further, so content saturates well before the budget does and 1200/400 is the knee.
    """
    assert _CONTEXT_CHUNK_CHARS == 400, "a 240-char excerpt hides numbers the gate then demands"
    assert _CONTEXT_BLOCK_CHARS == 1200, "content saturates by ~600 chars; more block only costs prefill"

    chunk_default = inspect.signature(_clean_chunk_for_synthesis).parameters["max_len"].default
    assert chunk_default == _CONTEXT_CHUNK_CHARS, chunk_default

    block_default = inspect.signature(build_raw_context_block).parameters["max_chars"].default
    assert block_default == _CONTEXT_BLOCK_CHARS, block_default


def test_the_chat_path_defaults_to_the_same_budget_the_gate_is_scored_against(monkeypatch: pytest.MonkeyPatch) -> None:
    """With KENN_LLM_CONTEXT_CHARS unset the answer prompt must carry the full 1200-char block.

    The chat path passes max_chars explicitly, so leaving 650 there would keep production answers on the old
    window no matter what build_raw_context_block defaults to.
    """
    monkeypatch.delenv("KENN_LLM_CONTEXT_CHARS", raising=False)

    user_message = _answer_prompt()
    missing = [value for value in MEASUREMENTS if value not in user_message]
    assert not missing, f"truncated out of the answer prompt: {missing}"


def test_the_env_override_still_wins_over_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run that pins KENN_LLM_CONTEXT_CHARS gets that budget, which is how the 1 Oct latency sweep worked."""
    monkeypatch.setenv("KENN_LLM_CONTEXT_CHARS", "300")

    user_message = _answer_prompt()
    assert "150 ms" not in user_message, "300 chars cannot hold the measurements, and that is the operator's call"


# A "Related questions" block as build_index chunks it: a list of the note's own question phrasings and no
# substance. It cleans to "" because of the section check, which is correct — but it scores high exactly when the
# user asks something the note covers, since the block echoes their wording. The real "Sidechain Bass To Kick"
# note carries the literal line "- What release time for sidechain compression?", near-verbatim the query above.
def _related_questions(note: str, *phrasings: str) -> dict:
    body = "\n".join(f"- {phrasing}" for phrasing in phrasings)
    return {"section": "Related questions", "text": f"{note}\nRelated questions:\n{body}"}


# The four body sections that chunk out of the same note. Each is a separate ranked result, and each carries a
# measurement, because that is what the gate will check the answer against.
BODY_SECTIONS = [
    {"section": "Short answer", "text": "Key the bass compressor from the kick so the bass ducks under every hit."},
    {"section": "Try this", "text": "Release around 150 ms and a ratio of 4:1 keeps the pumping shallow."},
    {"section": "Common mistakes", "text": "Depth past 6 dB reads as a sidechain artefact rather than musical pumping."},
    {"section": "When this does not apply", "text": "An attack of 5 ms or longer smears the bass transient against the kick."},
]
BODY_MEASUREMENTS = ("150 ms", "4:1", "6 dB", "5 ms")

# The three Related-questions blocks outrank all four body sections, as they did on the real run.
CROWDOUT_RANKED_RESULTS = [
    (1180.40, _related_questions(
        "Sidechain Bass To Kick",
        "What release time for sidechain compression?",
        "How deep should the sidechain send be?",
    )),
    (1142.07, _related_questions(
        "Bass Ducking Notes",
        "Why does my bass disappear when the kick plays?",
        "Should I sidechain the whole bass bus?",
    )),
    (1030.88, _related_questions(
        "Live Set Dynamics",
        "What release time for sidechain compression?",
        "When does pumping sound like a fault?",
    )),
    *[(1030.88, chunk) for chunk in BODY_SECTIONS],
]


def _crowdout_label(chunk: dict) -> str:
    return f"Sidechain Bass To Kick.md (curated note, section {chunk['section']} para)"


def test_a_notes_related_questions_block_does_not_crowd_out_its_own_body_sections() -> None:
    """A chunk that cleans to "" must not spend one of a small number of ranked slots.

    Three Related-questions blocks scoring above the note's own body used to take the first three of four slots,
    return nothing, and be skipped before the budget check — so the block lost 3 slots and stayed short rather than
    reaching the body sections behind them. 30% of top-4 slots across 14 real queries were wasted this way, and the
    worst case left "Why does my bass disappear when the kick plays?" with one usable chunk out of four. It cannot
    recur because the scan window is wider than the number of chunks that survive cleaning.
    """
    assert all(not _clean_chunk_for_synthesis(chunk) for _score, chunk in CROWDOUT_RANKED_RESULTS[:3]), \
        "the fixture only reproduces the bug if those top three really do clean to nothing"

    block = build_raw_context_block(CROWDOUT_RANKED_RESULTS, _crowdout_label)

    missing = [value for value in BODY_MEASUREMENTS if value not in block]
    assert not missing, f"body sections crowded out by their own note's question list: {missing}\n{block}"
    assert block.count("<source_excerpt") == len(BODY_SECTIONS), \
        "only the four body sections should contribute, one excerpt each"
    assert len(block) <= _CONTEXT_BLOCK_CHARS, len(block)


def test_the_scan_window_is_the_measured_12_ranked_slots() -> None:
    """The window is a number someone tuned against real queries, so a silent revert has to fail here.

    Going 4 -> 12 lifted the bass-disappears query from 1 usable chunk to 9 and gained 20 distinct measurements;
    13 of 14 queries gained measurements, and the one that did not already had 4 usable chunks. Asserted directly
    because the failure it guards is a one-character edit that no behavioural test in the suite would notice.
    """
    assert _CONTEXT_SCAN_WINDOW == 12, "widening past 4 is what stops discarded chunks from eating the slots"


def test_the_scan_window_bounds_the_scan_rather_than_reading_the_whole_ranking() -> None:
    """The window caps wasted scanning; _CONTEXT_BLOCK_CHARS still caps the block.

    A dead chunk at rank 13 costs a loop iteration and nothing else, so the scan must stop rather than walk an
    arbitrarily long ranked list looking for something that fits.
    """
    dead = [
        (1200.0 - rank, _related_questions("Padding Note", f"Why is chunk {rank} related to the bass?"))
        for rank in range(1, 13)
    ]
    inside_window = dead + [(900.0, BODY_SECTIONS[0])]
    beyond_window = dead + [(900.0, BODY_SECTIONS[0]), (899.0, BODY_SECTIONS[1])]

    assert "150 ms" not in build_raw_context_block(inside_window, _crowdout_label)
    assert "4:1" not in build_raw_context_block(beyond_window, _crowdout_label), \
        f"rank {len(dead) + 2} is past the window and must not be scanned"