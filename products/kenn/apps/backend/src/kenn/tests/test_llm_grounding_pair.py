from __future__ import annotations

from kenn.core.chat_grounding import generated_answer_validation


RESULTS = [
    (
        12.0,
        {
            "kind": "note",
            "title": "Reverb send workflow",
            "source": "reverb-send-workflow.md",
            "topics": ["reverb", "routing", "mixing"],
            "tags": ["reverb", "return", "send", "mixing"],
            "text": (
                "Create a return track for the reverb, keep the return 100% wet, "
                "high-pass it around 200-400 Hz, and begin with a send around 10-20%."
            ),
            "status": "Approved",
        },
    )
]

QUERY = "How do I set up a send reverb?"
TEMPLATE = """Short answer: Use a return track so the dry source stays clear.

Try this:
1. Create a return track and put the reverb there.
2. Keep the return 100% wet and start with a 10-20% send.

Check: Level-match the processed and dry versions before deciding.

Sources:
- Reverb send workflow (reverb-send-workflow.md)
"""

PARAPHRASE = """Short answer: A dedicated return keeps the original track dry while you blend reverb.

Try this:
1. Add the reverb to a return track and leave that return fully wet.
2. High-pass the return around 200-400 Hz, then begin with a 10-20% send.

Check: Compare the reverb in context at matched level.

Sources:
- Reverb send workflow (reverb-send-workflow.md)
"""


def validate(answer: str) -> dict:
    return generated_answer_validation(
        QUERY,
        RESULTS,
        answer,
        route="production",
        confidence="high",
        answer_mode="quick_fix",
    )


def test_factual_paraphrase_passes_the_same_grounding_gate_as_the_template() -> None:
    template_result = validate(TEMPLATE)
    paraphrase_result = validate(PARAPHRASE)

    assert PARAPHRASE != TEMPLATE
    assert template_result["accepted"] is True
    assert paraphrase_result["accepted"] is True
    assert paraphrase_result["unsupported_measurements"] == []
    assert paraphrase_result["fabricated_sources"] == []


def test_structured_but_unsupported_llm_candidate_is_rejected() -> None:
    unsafe = PARAPHRASE.replace(
        "200-400 Hz", "500 Hz"
    ).replace(
        "reverb-send-workflow.md", "invented-reverb-guide.md"
    )
    result = validate(unsafe)

    assert result["accepted"] is False
    assert "500hz" in result["unsupported_measurements"]
    assert "invented-reverb-guide.md" in result["fabricated_sources"]


def test_typed_specialist_measurement_can_ground_generated_answer() -> None:
    result = generated_answer_validation(
        QUERY,
        RESULTS,
        PARAPHRASE + "\n\nThe supplied classifier recorded 88.6% audio-only accuracy.",
        route="production",
        confidence="high",
        answer_mode="quick_fix",
        additional_evidence_text=(
            "The supplied classifier recorded 88.6% audio-only accuracy."
        ),
    )

    assert result["accepted"] is True
    assert result["unsupported_measurements"] == []


def test_spacing_between_number_and_unit_does_not_decide_a_match() -> None:
    # A captured answer wrote "120Hz" where the note wrote "120 Hz"; the space was part of the key, so a
    # faithful quotation was rejected as invented. Audio writing puts it both ways, so it cannot be in the key.
    for note, quoted in (
        ("Set the crossover to 120 Hz.", "Use 120Hz for the crossover."),
        ("Sample rate 44.1 kHz.", "Print at 44.1kHz."),
        ("Set the send to -18 dBFS.", "Set the send to -18dBFS."),
        ("Begin with a send around 10-20%.", "Start with a 10–20% send."),
    ):
        result = generated_answer_validation(
            QUERY,
            RESULTS,
            f"Short answer: {quoted}\n\nTry this:\n1. Do it.\n2. Check it.\n\nSources:\n- Reverb send workflow (reverb-send-workflow.md)\n",
            route="production",
            confidence="high",
            answer_mode="quick_fix",
            additional_evidence_text=note,
        )
        assert result["unsupported_measurements"] == [], (note, result["unsupported_measurements"])


def test_steps_written_inline_after_the_label_still_count() -> None:
    # 18 of 29 captured candidates wrote the steps inline and were rejected for having none; all 4 accepted broke the lines.
    result = validate(PARAPHRASE.replace("2. Keep the return fully wet.", "Keep the return wet. 2. Keep the return fully wet."))
    assert "fewer than two actionable steps" not in result["warnings"], result["warnings"]


def test_numbered_text_in_prose_is_not_mistaken_for_a_step() -> None:
    from kenn.core.chat_constants import count_actionable_steps

    assert count_actionable_steps("In 1997. Something happened, and by 2. 3 standards it was fine.") == 0
    assert count_actionable_steps("Try this: 1. Cut at 200 Hz. 2. Level-match it.") == 2


def test_a_rejection_records_which_sections_were_missing() -> None:
    # This was the dominant rejection and named nothing. The aggregate stays first because the route report
    # groups on it; the specifics behind it are what make the count actionable.
    result = validate("Send the reverb from a return at around 10-20%.")

    assert result["accepted"] is False
    assert result["warnings"][0] == "generated answer is below the quality threshold"
    assert "missing short answer section" in result["warnings"]
    assert "fewer than two actionable steps" in result["warnings"]


def test_a_chat_answer_that_claims_it_changed_the_set_is_thrown_away() -> None:
    # Only the Live command path changes the set, after Apply. A brain answer saying it did is a false receipt.
    for claim in (
        "I've added a reverb return and set the send to 15%.",
        "I have lowered the Bass by 2 dB.",
        "Done! The return is now 100% wet.",
        "I’ve just muted the hats for you.",
    ):
        result = validate(claim + "\n\n" + PARAPHRASE)
        assert result["accepted"] is False, claim
        assert result["claims_live_change"] is True


def test_advice_in_the_first_person_is_not_mistaken_for_a_change() -> None:
    advice = PARAPHRASE.replace("Short answer:", "Short answer: I'd set up a return for this, and I'd cut the lows.")
    result = validate(advice)
    assert result["claims_live_change"] is False
    assert result["accepted"] is True


def test_restating_one_end_of_a_retrieved_range_is_not_charged_with_inventing_it() -> None:
    # The hyphen in "200-400 Hz" used to read as a minus, so the note held only "-400 Hz" and rejected the lower bound.
    result = validate(PARAPHRASE.replace("200-400 Hz", "200 Hz"))
    assert result["unsupported_measurements"] == []
    assert result["accepted"] is True


def test_a_send_level_the_notes_never_gave_is_caught() -> None:
    # A trailing \b cannot match after "%", so an invented send level used to pass as grounded.
    result = validate(PARAPHRASE.replace("10-20% send", "45% send"))
    assert "45%" in result["unsupported_measurements"]
    assert result["accepted"] is False


def test_flipping_the_sign_on_a_measured_level_is_caught() -> None:
    # The sign used to be dropped, so "-18 dBFS" in the evidence matched "+18 dBFS" in the answer.
    result = generated_answer_validation(
        QUERY,
        RESULTS,
        PARAPHRASE + "\n\nSet the send to +18 dBFS.",
        route="production",
        confidence="high",
        answer_mode="quick_fix",
        additional_evidence_text="Set the send to -18 dBFS.",
    )
    assert "18dbfs" in result["unsupported_measurements"]
    assert result["accepted"] is False
