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
    assert "500 hz" in result["unsupported_measurements"]
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
