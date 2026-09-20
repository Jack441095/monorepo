"""Every KENN generation path must pass the same evidence gate."""

from __future__ import annotations

from unittest.mock import patch

from kenn.core import chat_answer
from kenn.core.chat_grounding import generated_answer_validation
from thursday.voice import stream_kenn_answer


QUERY = "How should I sidechain the bass to the kick?"
SOURCE = {
    "id": "sidechain-note",
    "source": "sidechain.md",
    "page": 1,
    "kind": "note",
    "title": "Sidechain Bass to Kick",
    "section": "workflow",
    "tags": ["compression", "sidechain"],
    "topics": ["compression", "bass", "drums"],
    "text": (
        "Status: Approved\n\nUse sidechain compression keyed from the kick. "
        "Start with roughly 4 dB of gain reduction and verify the release by ear."
    ),
}
RESULTS = [(20.0, SOURCE)]
VALID_ANSWER = """Short answer: Use sidechain compression keyed from the kick.

Try this:
1. Route the kick into the compressor sidechain input.
2. Start near 4 dB of gain reduction and adjust the release by ear.

Listening check: Bypass the compressor and confirm the kick and bass separate cleanly.

Sources:
- Sidechain Bass to Kick
"""
UNSUPPORTED_ANSWER = VALID_ANSWER.replace("4 dB", "999 dB")


def _validate(answer: str) -> dict:
    return generated_answer_validation(
        QUERY,
        RESULTS,
        answer,
        route="production",
        confidence="high",
        answer_mode="mix_diagnosis",
    )


def test_generated_answer_gate_accepts_supported_measurements() -> None:
    decision = _validate(VALID_ANSWER)
    assert decision["accepted"] is True
    assert decision["unsupported_measurements"] == []


def test_generated_answer_gate_rejects_unsupported_measurements() -> None:
    decision = _validate(UNSUPPORTED_ANSWER)
    assert decision["accepted"] is False
    assert decision["unsupported_measurements"] == ["999 db"]
    assert "unsupported measurements" in " ".join(decision["warnings"])


def test_remote_rewrite_cannot_bypass_grounding_gate(monkeypatch) -> None:
    monkeypatch.delenv("KENN_LM_ENABLED", raising=False)
    with (
        patch("kenn.core.chat_answer.build_template_answer", return_value=VALID_ANSWER),
        patch("kenn.core.chat_answer.results_are_weak", return_value=False),
        patch("kenn.core.chat_answer.intent_guard_failed", return_value=False),
        patch("kenn.core.chat_answer.should_use_llm_rewrite", return_value=True),
        patch("kenn.core.chat_answer.llm_enhance_answer", return_value=UNSUPPORTED_ANSWER),
    ):
        answer, used_generation = chat_answer.make_answer(
            QUERY,
            RESULTS,
            allow_llm=True,
            route="production",
            answer_mode="mix_diagnosis",
        )

    assert answer == VALID_ANSWER
    assert used_generation is False
    assert "999 dB" not in answer


def test_local_model_cannot_bypass_grounding_gate(monkeypatch) -> None:
    class FakeLocalModel:
        available = True

        @staticmethod
        def generate(*_args, **_kwargs) -> str:
            return UNSUPPORTED_ANSWER

    monkeypatch.setenv("KENN_LM_ENABLED", "1")
    monkeypatch.setenv("KENN_LM_ALLOW_REJECTED", "1")
    with (
        patch("kenn.core.chat_answer.build_template_answer", return_value=VALID_ANSWER),
        patch("kenn.core.chat_answer.results_are_weak", return_value=False),
        patch("kenn.core.chat_answer.intent_guard_failed", return_value=False),
        patch("kenn.core.chat_answer._get_kenn_lm", return_value=FakeLocalModel()),
        patch("kenn.core.chat_answer.should_use_llm_rewrite", return_value=False),
    ):
        answer, used_generation = chat_answer.make_answer(
            QUERY,
            RESULTS,
            allow_llm=True,
            route="production",
            answer_mode="mix_diagnosis",
        )

    assert answer == VALID_ANSWER
    assert used_generation is False
    assert "999 dB" not in answer


def test_rejected_local_model_requires_explicit_experimental_override(monkeypatch) -> None:
    monkeypatch.setenv("KENN_LM_ENABLED", "1")
    monkeypatch.delenv("KENN_LM_ALLOW_REJECTED", raising=False)
    with (
        patch("kenn.core.chat_answer.build_template_answer", return_value=VALID_ANSWER),
        patch("kenn.core.chat_answer.results_are_weak", return_value=False),
        patch("kenn.core.chat_answer.intent_guard_failed", return_value=False),
        patch(
            "kenn.core.chat_answer._get_kenn_lm",
            side_effect=AssertionError("rejected model must not load"),
        ),
        patch("kenn.core.chat_answer.should_use_llm_rewrite", return_value=False),
    ):
        answer, used_generation = chat_answer.make_answer(
            QUERY,
            RESULTS,
            allow_llm=True,
            route="production",
            answer_mode="mix_diagnosis",
        )

    assert answer == VALID_ANSWER
    assert used_generation is False


def test_stream_and_voice_buffer_then_reject_unsupported_generation() -> None:
    def unsafe_stream(*_args, **_kwargs):
        yield {"event": "token", "token": UNSUPPORTED_ANSWER}
        yield {"event": "llm_usage", "data": {"total_tokens": 50}}

    with (
        patch("kenn.core.chat_answer.llm_enabled", return_value=True),
        patch("kenn.core.chat_answer.should_use_llm_rewrite", return_value=True),
        patch("kenn.core.chat_answer.llm_enhance_answer_stream", side_effect=unsafe_stream),
    ):
        events = list(chat_answer.answer_payload_stream(QUERY, allow_llm=True))

    metadata = [event["data"] for event in events if event["event"] == "metadata"][-1]
    streamed = "".join(
        str(event.get("token") or "") for event in events if event["event"] == "token"
    )
    assert metadata["generation_validation"]["attempted"] is True
    assert metadata["generation_validation"]["accepted"] is False
    assert metadata["llm_enhanced"] is False
    assert "999 dB" not in streamed
    assert streamed == metadata["answer"]

    spoken = "".join(
        stream_kenn_answer(
            QUERY,
            _stream_fn=lambda *_args, **_kwargs: iter(events),
        )
    )
    assert spoken == streamed
    assert "999 dB" not in spoken


# ── Fabricated "Sources:" citations ─────────────────────────────────────
#
# Live-tested 2026-08-03: asked KENN "whats the difference between
# compression and limiting". The real retrieved sources were
# mix-bus-glue-compression.md and vocal-deessing-and-sibilance.md, but the
# generated answer's own "Sources:" section cited "Compression vs Limiting
# (compression-vs-limiting.md)" and "How to Choose Between Compression and
# Limiting (choose-between-compression-and-limiting.md)" -- neither file
# exists anywhere in the knowledge base. llm_rewrite.py's system prompt asks
# the model to reproduce the exact labels it was given, but qwen2.5:1.5b
# invented new, plausible-looking ones instead. generated_answer_validation()
# had no check for this at all -- any non-empty "Sources:" section text was
# accepted.

FABRICATED_SOURCE_ANSWER = VALID_ANSWER.replace(
    "Sources:\n- Sidechain Bass to Kick\n",
    "Sources:\n- Compression vs Limiting (compression-vs-limiting.md)\n",
)
CORRECTLY_CITED_ANSWER = VALID_ANSWER.replace(
    "Sources:\n- Sidechain Bass to Kick\n",
    "Sources:\n- Sidechain Bass to Kick (sidechain.md)\n",
)


def test_generated_answer_gate_rejects_fabricated_source_citation() -> None:
    decision = _validate(FABRICATED_SOURCE_ANSWER)
    assert decision["accepted"] is False
    assert decision["fabricated_sources"] == ["compression-vs-limiting.md"]
    assert "cites sources not in the retrieved evidence" in " ".join(decision["warnings"])


def test_generated_answer_gate_accepts_correctly_cited_source() -> None:
    decision = _validate(CORRECTLY_CITED_ANSWER)
    assert decision["fabricated_sources"] == []


def test_generated_answer_gate_accepts_title_only_citation_with_no_filename() -> None:
    """The existing VALID_ANSWER fixture cites a bare title with no
    parenthesized filename at all -- nothing to check, so it must not be
    treated as fabricated."""
    decision = _validate(VALID_ANSWER)
    assert decision["fabricated_sources"] == []


# ── Punting to sources / echoing prompt instructions ────────────────────
#
# Live-tested 2026-08-03: asked "how do i set up a send reverb". The
# generated "Try this:" section was "Open the relevant Ableton view or
# device mentioned in the sources... Use the source pages below to verify
# the exact command or setting name" -- content-free filler punting the
# actual work back to the user. A separate run of the same query produced
# "Short answer: (one punchy paragraph — your verdict first, then the
# reason)" -- the model literally copied its own system prompt's
# instructional placeholder text instead of writing real content. Neither
# was caught by any existing check: measurements were fine, sources were
# real, and the rest of each answer had enough genuine evidence overlap to
# keep the aggregate score passing.

SOURCE_PUNT_ANSWER = VALID_ANSWER.replace(
    "1. Route the kick into the compressor sidechain input.\n"
    "2. Start near 4 dB of gain reduction and adjust the release by ear.\n",
    "1. Open the relevant Ableton view or device mentioned in the sources.\n"
    "2. Use the source pages below to verify the exact command or setting name.\n",
)
PROMPT_ECHO_ANSWER = VALID_ANSWER.replace(
    "Short answer: Use sidechain compression keyed from the kick.",
    "Short answer: (one punchy paragraph — your verdict first, then the reason)",
)


def test_generated_answer_gate_rejects_punting_to_sources() -> None:
    decision = _validate(SOURCE_PUNT_ANSWER)
    assert decision["accepted"] is False
    assert decision["punts_to_sources"] is True
    assert "punts to the sources" in " ".join(decision["warnings"])


def test_generated_answer_gate_rejects_prompt_instruction_echo() -> None:
    decision = _validate(PROMPT_ECHO_ANSWER)
    assert decision["accepted"] is False
    assert decision["echoes_prompt_instructions"] is True
    assert "echoes its own system prompt instructions" in " ".join(decision["warnings"])


def test_generated_answer_gate_accepts_normal_answer_without_false_positives() -> None:
    decision = _validate(VALID_ANSWER)
    assert decision["punts_to_sources"] is False
    assert decision["echoes_prompt_instructions"] is False
