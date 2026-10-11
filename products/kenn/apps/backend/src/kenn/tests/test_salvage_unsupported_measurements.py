"""One invented number must not cost the whole model answer (4 Oct 2026: 9 to 12 of about 41 rejections a run).

An aside that only illustrates a step goes on its own; any other figure takes its sentence with it. The gate
then judges what is left, and a number the notes lack still cannot get through.
"""

from __future__ import annotations

from kenn.core import chat_answer
from kenn.core.chat_grounding import (
    _excise_illustrative_figures,
    _measurements,
    drop_unsupported_sentences,
    generated_answer_validation,
    salvage_unsupported_figures,
)
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


def test_the_try_this_label_moves_to_the_next_step_when_the_first_step_is_dropped():
    # 4 Oct 2026: losing the labelled first step left no "Try this" at all and the gate said "missing steps section".
    answer = (
        "Short answer: Dynamic EQ suits a narrow resonance, such as one harsh frequency, better than a broad band.  \n"
        "Try this: 1. Use a dynamic EQ to cut the problem near 900 ms with a narrow Q on the loudest peaks. "
        "2. Avoid a multiband compressor unless the harshness spans a wide range of the vocal. "
        "3. Solo the vocal and compare the dry and processed signal to make sure the fix is targeted."
    )
    trimmed = drop_unsupported_sentences(answer, ["900ms"])
    assert "Try this: 1. Avoid a multiband" in trimmed
    assert "2. Solo the vocal" in trimmed


# lowend-fresh in /tmp/kenn-salvage-run7 (4 Oct 2026): step 2 had the invented number, the cap cut step 3
# mid-sentence, and the answer went out ending "...below 20Hz. 2." Trimmed, with the later numbers made up.
CAPPED_LOW_END = (
    "Short answer: Use a high-pass filter to cut low-end mud (20-100Hz) and a sub-bass enhancer to carve out "
    "space for the kick and bass.  \n"
    "Try this: 1. Apply a high-pass filter on the bass and kick tracks to cut below 20Hz. "
    "2. Boost the kick at 60Hz by 3dB so it sits above the bass. "
    "3. Check the low end in mono and listen for the kick and bass staying clear of each other in the"
    "\n\nSources:\n- Mixing To A Reference Track (mixing-to-reference-track.md)"
)


def test_a_salvaged_answer_never_ends_on_the_bare_number_of_a_step_the_cap_cut_off():
    trimmed = drop_unsupported_sentences(CAPPED_LOW_END, ["60hz", "3db"])
    assert "below 20Hz.\n\nSources:" in trimmed
    assert " 2." not in trimmed and "3." not in trimmed


def test_a_salvaged_answer_never_ends_mid_sentence():
    trimmed = drop_unsupported_sentences(CAPPED_LOW_END, ["60hz", "3db"])
    assert "in the" not in trimmed


def test_a_salvaged_answer_too_short_to_end_cleanly_is_given_up_rather_than_shown_cut():
    # end_on_a_whole_sentence leaves a short answer alone, so the salvage used to hand it on still cut off.
    answer = (
        "Short answer: Key the bass compressor from the kick drum so the bass ducks on every hit. "
        "Set the release to 900 ms. Then listen to the bass and kick together and check that the bass comes back "
        "before the next kick lands, and if it does not, shorten the release until the"
    )
    assert drop_unsupported_sentences(answer, ["900ms"]) == ""


def test_the_dynamic_eq_answer_keeps_no_empty_step_and_counts_from_one():
    # dyn-dynamic-eq-vs-multiband, /tmp/kenn-salvage-review-sheet.md (4 Oct 2026) went out as "Try this: 1. 2. Set
    # the threshold ... 3." with a "Check:" line stopped at "the harshness is".
    answer = (
        "Short answer: Dynamic EQ is better for narrow resonances like vocal harshness, while multiband "
        "compression is better for broad range issues.  \n"
        "Try this: 1. Cut 3500Hz by -2.5dB with a dynamic band. 2. Set the threshold to catch only the harsh "
        "moments. 3. Widen the band around 3500Hz if it still bites.\n"
        "Check: Solo the vocal and compare the original and processed version to make sure the harshness is"
    )
    trimmed = drop_unsupported_sentences(answer, ["3500hz", "-2.5db"])
    assert trimmed.endswith("Try this: 1. Set the threshold to catch only the harsh moments.")


# The figures in these tests are the shapes refused across the 12 probe runs of 10 Oct 2026, where cutting the
# whole sentence saved none of 32 answers: it took a step with it and the answer fell under the quality floor.
# The frequencies in brackets and on the high-pass are not in the sidechain note.
ILLUSTRATED = ACCEPTED_ANSWER.replace(
    "1. In Live, put a compressor on the bass bus and send the kick to its sidechain input.",
    "1. In Live, put a compressor on the bass bus (e.g., the 40–120 Hz body) and send the kick to its sidechain input.",
).replace(
    "2. Set the release to 150 ms so the bass recovers before the next kick.",
    "2. Set the release to 150 ms so the bass recovers before the next kick, and add a high-pass filter at 30 Hz "
    "to clear rumble.",
)


def test_the_illustrated_answer_is_refused_and_the_sentence_drop_cannot_save_it():
    assert _validate(ILLUSTRATED)["unsupported_measurements"] == ["120hz", "30hz", "40hz"]
    assert drop_unsupported_sentences(ILLUSTRATED, ["120hz", "30hz", "40hz"]) == ""


def test_cutting_only_the_asides_keeps_every_step_and_passes_the_same_gate():
    salvaged = salvage_unsupported_figures(ILLUSTRATED, ["120hz", "30hz", "40hz"])
    assert "1. In Live, put a compressor on the bass bus and send the kick" in salvaged
    assert "add a high-pass filter to clear rumble." in salvaged
    assert "3. Set the ratio to 4:1" in salvaged
    check = _validate(salvaged)
    assert check["accepted"], check["warnings"]


def test_an_example_in_brackets_goes_and_its_step_reads_on():
    # eq-linear-vs-min-phase, v3 bench cand-run1.
    text = "1. Solo each track and apply a linear-phase EQ to the low-mid range (e.g., 100–300 Hz) to check for smearing."
    assert _excise_illustrative_figures(text, {"100hz", "300hz"}) == (
        "1. Solo each track and apply a linear-phase EQ to the low-mid range to check for smearing."
    )


def test_an_example_between_dashes_goes_and_the_sentence_closes_up():
    # dyn-dynamic-eq-vs-multiband, v3 bench cand-run1.
    text = "It acts only when the signal exceeds a threshold—like a narrow resonance at 3500 Hz—without touching the rest."
    assert _excise_illustrative_figures(text, {"3500hz"}) == (
        "It acts only when the signal exceeds a threshold without touching the rest."
    )
    assert _excise_illustrative_figures("Catch the harsh band — say 3500 Hz —, then let go.", {"3500hz"}) == (
        "Catch the harsh band, then let go."
    )


def test_a_range_inside_a_spaced_dash_aside_is_not_taken_for_its_closing_dash():
    text = "Find the mud – like 100–300 Hz – before you cut."
    assert _excise_illustrative_figures(text, {"300hz"}) == "Find the mud before you cut."


def test_a_high_pass_keeps_its_instruction_without_the_frequency():
    # rec-proximity, v3 bench cand-run2 and cand-run3; the second kept its citation.
    assert _excise_illustrative_figures("Apply a high-pass filter at around 100 Hz to reduce the effect.", {"100hz"}) == (
        "Apply a high-pass filter to reduce the effect."
    )
    assert _excise_illustrative_figures("Apply a high-pass filter at 100 Hz [#578a1b0b8faa].", {"100hz"}) == (
        "Apply a high-pass filter [#578a1b0b8faa]."
    )


def test_a_boost_or_cut_keeps_its_frequency_because_without_it_there_is_no_instruction():
    # "Boost at 5 kHz." would have come out as "Boost."; the sentence drop is the right outcome there.
    assert _excise_illustrative_figures("Boost at 5 kHz.", {"5khz"}) == "Boost at 5 kHz."
    assert _excise_illustrative_figures("Cut at 3 kHz by 2 dB.", {"3khz"}) == "Cut at 3 kHz by 2 dB."


def test_a_figure_that_is_the_step_itself_still_takes_its_sentence():
    # dig-gain-staging refused -18 dBFS on every probe run of 10 Oct: the note has no such figure, and no cut
    # can leave "so the preamp output is at" saying anything.
    step = "Set your track input gain so the preamp output is at -18 dBFS."
    assert _excise_illustrative_figures(step, {"-18dbfs"}) == step
    body = "Key the bass compressor from the kick and let the release recover before the next hit. " * 3
    answer = f"Short answer: {body}\n{step} Then listen to the bass and kick together."
    salvaged = salvage_unsupported_figures(answer, ["-18dbfs"])
    assert "-18" not in salvaged and salvaged.endswith("Then listen to the bass and kick together.")


def test_an_aside_with_only_supported_figures_or_none_is_left_alone():
    text = "Set the release (150 ms) and the gain (a safe starting point) before the high-pass filter at 30 Hz."
    assert _excise_illustrative_figures(text, {"900ms"}) == text


def test_nothing_to_salvage_returns_nothing_rather_than_the_original():
    assert salvage_unsupported_figures(ACCEPTED_ANSWER, []) == ""


def test_make_answer_keeps_every_step_when_only_asides_held_the_invented_figures(monkeypatch):
    monkeypatch.setattr(chat_answer, "load_chunks", lambda: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "search", lambda *a, **k: list(CHUNKS))
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", lambda *a, **k: ILLUSTRATED)
    monkeypatch.setattr("kenn.llm.linter.lint_response", lambda answer, mode: answer)
    logged = []
    monkeypatch.setattr(chat_answer, "_log_generation_outcome", lambda accepted, validation, seconds: logged.append((accepted, validation)))

    answer, enhanced = chat_answer.make_answer(QUERY, list(CHUNKS), route="production")

    assert enhanced is True
    assert "Hz" not in answer and "3. Set the ratio to 4:1" in answer
    assert logged[-1][0] is True and logged[-1][1]["salvaged"] == ["120hz", "30hz", "40hz"]
