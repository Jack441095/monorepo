"""One invented number must not cost the whole model answer (4 Oct 2026: 9 to 12 of about 41 rejections a run).

The sentence with the number goes; the gate then judges what is left, and a number the notes lack still cannot
get through.
"""

from __future__ import annotations

from kenn.core import chat_answer
from kenn.core.chat_grounding import _measurements, drop_unsupported_sentences, generated_answer_validation
from kenn.tests.test_streamed_generation_prefix_guard import ACCEPTED_ANSWER, CHUNKS, QUERY

# The model adds a 900 ms figure that the note does not have, in the middle of an otherwise good answer.
INVENTED_IN_A_STEP = ACCEPTED_ANSWER.replace(
    "2. Set the release to 150 ms so the bass recovers before the next kick.",
    "2. Set the release to 150 ms so the bass recovers before the next kick.\n"
    "3. Push the attack out to 900 ms if the kick feels choked.",
).replace("3. Set the ratio", "4. Set the ratio")


def _validate(answer: str) -> dict:
    return generated_answer_validation(
        QUERY, list(CHUNKS), answer, route="production", confidence="high", answer_mode="quick_fix"
    )


def test_the_fixture_answer_is_rejected_for_the_invented_number_and_for_nothing_else():
    check = _validate(INVENTED_IN_A_STEP)
    assert check["unsupported_measurements"] == ["900ms"]
    assert check["warnings"] == ["generated answer introduced unsupported measurements"]


def test_a_step_with_an_invented_number_is_dropped_and_the_steps_are_renumbered():
    trimmed = drop_unsupported_sentences(INVENTED_IN_A_STEP, ["900ms"])
    assert "900" not in trimmed
    assert "3. Set the ratio to 4:1" in trimmed
    assert "4." not in trimmed


def test_the_trimmed_answer_passes_the_same_gate_that_rejected_the_original():
    trimmed = drop_unsupported_sentences(INVENTED_IN_A_STEP, ["900ms"])
    check = _validate(trimmed)
    assert check["accepted"], check["warnings"]
    assert _measurements(trimmed) <= _measurements(" ".join(c["text"] for _s, c in CHUNKS))


def test_only_the_sentence_with_the_number_goes_when_a_line_holds_two():
    answer = "Short answer: " + ("Keep the bass tight and key it from the kick. " * 6) + "A 900 ms release is too long. Then listen."
    trimmed = drop_unsupported_sentences(answer, ["900ms"])
    assert "900" not in trimmed
    assert trimmed.endswith("Then listen.")


def test_a_bullet_keeps_its_marker_when_its_first_sentence_is_dropped():
    body = "Keep the bass tight and key it from the kick, then listen for the recovery. " * 4
    answer = f"- Use 900 ms here. {body}\n- Another point about the kick and the bass bus. {body}"
    trimmed = drop_unsupported_sentences(answer, ["900ms"])
    assert trimmed.startswith("- Keep the bass tight")


def test_a_heading_left_with_no_body_goes_with_it():
    body = "Key the bass compressor from the kick and let the release recover before the next hit. " * 3
    answer = f"Short answer: {body}\n\nAvoid:\nDo not set 900 ms.\n\nCheck:\nListen to the bass bus against the kick. {body}"
    trimmed = drop_unsupported_sentences(answer, ["900ms"])
    assert "Avoid:" not in trimmed
    assert "Check:" in trimmed


def test_an_answer_that_is_mostly_invented_numbers_is_not_rescued():
    answer = "Set 900 ms. Set 12 dB. Set 80 Hz. Set 3000 Hz. Set 40%. Short answer: key it from the kick."
    assert drop_unsupported_sentences(answer, ["900ms", "12db", "80hz", "3000hz", "40%"]) == ""


def test_nothing_to_drop_returns_nothing_rather_than_the_original():
    assert drop_unsupported_sentences(ACCEPTED_ANSWER, []) == ""


def test_a_number_still_unsupported_after_the_cut_is_still_rejected_by_the_gate():
    answer = INVENTED_IN_A_STEP.replace("Check:", "Check: a 900 ms attack is wrong.\nAlso try 40 Hz.")
    trimmed = drop_unsupported_sentences(answer, ["900ms"])
    assert "900" not in trimmed
    assert "40hz" in _measurements(trimmed)
    assert not _validate(trimmed)["accepted"]


def test_make_answer_returns_the_trimmed_answer_when_only_an_invented_number_stood_in_the_way(monkeypatch):
    monkeypatch.setattr(chat_answer, "load_chunks", lambda: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "search", lambda *a, **k: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", lambda *a, **k: INVENTED_IN_A_STEP)
    monkeypatch.setattr("kenn.llm.linter.lint_response", lambda answer, mode: answer)
    logged = []
    monkeypatch.setattr(chat_answer, "_log_generation_outcome", lambda accepted, validation, seconds: logged.append((accepted, validation)))

    answer, enhanced = chat_answer.make_answer(QUERY, list(CHUNKS), route="production")

    assert enhanced is True
    assert "900" not in answer
    assert logged[-1][0] is True and logged[-1][1]["salvaged"] == ["900ms"]


def test_steps_written_inline_on_one_line_lose_the_whole_step_and_count_again():
    # Real model output from 4 Oct 2026: the cut used to leave "2." standing alone where step 2 had been.
    answer = (
        "Short answer: A cardioid mic boosts bass when close, and you can avoid it by backing off or using a filter.  \n"
        "Try this: 1. Move the mic further away from the source. "
        "2. Add a high-pass filter at 900 ms to cut unwanted low-end. "
        "3. Use a pop filter close to the capsule to reduce plosives.  \n"
        "Check: Solo the vocal and listen for a smoother low end with the mic moved back from the source."
    )
    trimmed = drop_unsupported_sentences(answer, ["900ms"])
    assert "900" not in trimmed
    assert "1. Move the mic further away from the source. 2. Use a pop filter" in trimmed
    assert "3." not in trimmed
