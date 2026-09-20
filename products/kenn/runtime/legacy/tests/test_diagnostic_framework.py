"""Behaviour tests for evidence-first audio diagnosis.

These deliberately assert the reasoning contract, not arbitrary EQ settings or
exact prose.  They protect KENN from regressing to a retrieved preset recipe.
"""

from __future__ import annotations

from kenn.core import chat_answer
from kenn.core.chat_answer import build_template_answer
from kenn.core.diagnostic_framework import plan_for, rank_with_evidence, render
from kenn.core.evidence import from_mix_review_context, from_plugin_context


def _results() -> list[tuple[float, dict]]:
    return [
        (10.0, {
            "kind": "note", "title": "Relevant engineering note", "source": "relevant.md",
            "text": "Tags: vocal harsh thin sibilance recording compression mixing\nShort answer:\nUse careful judgement for a harsh thin vocal.\n\nTry this:\n1. Compare changes.\n\nWhy it matters:\nEvidence matters.",
        })
    ]


def test_harsh_thin_vocal_is_hypothesis_led_not_a_deesser_recipe() -> None:
    plan = plan_for("My vocal sounds harsh and thin")
    assert plan is not None
    rendered = "\n".join(render(plan)).lower()
    assert "recording is naturally bright" in rendered
    assert "compression or saturation" in rendered
    assert "mix is masking" in rendered
    assert rendered.count("test:") >= 3
    assert "ease of testing, and reversibility" in rendered
    assert "most useful question:" in rendered


def test_diagnostic_renderer_adapts_explanation_depth_without_changing_plan() -> None:
    plan = plan_for("My vocal sounds harsh and thin")
    assert plan is not None
    beginner = "\n".join(render(plan, skill_level="beginner"))
    advanced = "\n".join(render(plan, skill_level="advanced"))
    assert "Plain-language approach:" in beginner
    assert "Advanced check:" in advanced
    assert "The recording is naturally bright" in beginner
    assert "The recording is naturally bright" in advanced


def test_kick_bass_plan_tests_phase_before_eq_prescription() -> None:
    plan = plan_for("The kick disappears when the bass comes in")
    assert plan is not None
    rendered = "\n".join(render(plan)).lower()
    assert "polarity, phase, or timing" in rendered
    assert "mute the bass only on kick hits" in rendered
    assert "do not use a large eq cut" in rendered


def test_mono_problem_is_marked_as_technical_but_width_as_creative() -> None:
    plan = plan_for("My wide mix collapses in mono and sounds phasey")
    assert plan is not None
    assert "measurable technical compatibility" in plan.issue_type
    assert "creative" in plan.issue_type


def test_template_uses_diagnostic_plan_for_ambiguous_symptom() -> None:
    answer = build_template_answer(
        "My vocal sounds harsh and thin.", _results(), route="production", answer_mode="mix_diagnosis"
    ).lower()
    assert "diagnosis first:" in answer
    assert "most useful hypotheses to test:" in answer
    assert "most useful question:" in answer
    assert "place a de-esser" not in answer


def test_unambiguous_how_to_does_not_receive_a_diagnostic_plan() -> None:
    assert plan_for("How do I set up a send reverb in Ableton?") is None


def test_flat_mix_diagnosis_tests_depth_cues_before_adding_reverb() -> None:
    plan = plan_for("My mix sounds flat and has no depth")
    assert plan is not None
    rendered = "\n".join(render(plan)).lower()
    assert "similar level and density" in rendered
    assert "ambience is masking" in rendered
    assert "before widening everything" in rendered


def test_translation_diagnosis_distinguishes_evidence_from_target_preference() -> None:
    plan = plan_for("My mix does not translate in my car and on small speakers")
    assert plan is not None
    assert "technical delivery problem" in plan.issue_type
    assert "reference systems matter" in plan.issue_type
    assert len(plan.hypotheses) == 3


def test_weak_low_end_diagnosis_does_not_start_with_a_bass_boost() -> None:
    plan = plan_for("My low end sounds weak")
    assert plan is not None
    rendered = "\n".join(render(plan)).lower()
    assert "low-frequency owner" in rendered
    assert "masked or cancelling" in rendered
    assert "not become louder merely because the mix is louder" in rendered


def test_flat_drums_diagnosis_tests_transient_and_time_masking() -> None:
    plan = plan_for("My drums lack punch")
    assert plan is not None
    rendered = "\n".join(render(plan)).lower()
    assert "transient is being reduced" in rendered
    assert "tails and sustained instruments" in rendered
    assert "matched loudness" in rendered


def test_clear_drum_symptom_bypasses_generic_clarification_gate() -> None:
    answer = chat_answer.answer_payload("My drums lack punch.", allow_llm=False, session_id="")["answer"]
    assert "Diagnosis first:" in answer
    assert "The transient is being reduced" in answer


def test_chat_diagnostic_uses_saved_skill_level(monkeypatch) -> None:
    monkeypatch.setattr(chat_answer, "_skill_level_for_session", lambda _session_id: "advanced")
    answer = build_template_answer(
        "My drums lack punch.", _results(), route="production", answer_mode="mix_diagnosis", session_id="experienced-session"
    )
    assert "Advanced check:" in answer


def test_explicit_first_turn_beginner_level_adapts_current_diagnostic() -> None:
    answer = build_template_answer(
        "I am a beginner and my drums lack punch.", _results(), route="production", answer_mode="mix_diagnosis"
    )
    assert "Plain-language approach:" in answer


def test_clipping_evidence_promotes_stage_location_without_claiming_the_source() -> None:
    plan = plan_for("My master is too loud and distorted")
    packet = from_plugin_context({
        "schema": "kenn.live_mix_context.v1", "clipped_samples": 10, "peak_dbfs": 0.0,
    })
    assert plan is not None and packet is not None
    ranked, rationale = rank_with_evidence(plan, [packet])
    assert ranked.hypotheses[0].cause == "A specific stage is clipping or overshooting"
    assert "does not identify that stage" in rationale


def test_real_mix_review_true_peak_schema_can_rank_master_diagnosis() -> None:
    plan = plan_for("My master is too loud and distorted")
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1", "metrics": {"true_peak_dbfs": -0.2},
    })
    assert plan is not None and packet is not None
    ranked, rationale = rank_with_evidence(plan, [packet])
    assert ranked.hypotheses[0].cause == "A specific stage is clipping or overshooting"
    assert "does not identify that stage" in rationale


def test_current_plugin_snapshot_prevents_old_upload_from_driving_master_rank() -> None:
    plan = plan_for("My master is too loud and distorted")
    uploaded = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1", "metrics": {"true_peak_dbfs": -0.1},
    })
    current = from_plugin_context({
        "schema": "kenn.live_mix_context.v1", "age_seconds": 1, "peak_dbfs": -6.0, "clipped_samples": 0,
    })
    assert plan and uploaded and current
    ranked, rationale = rank_with_evidence(plan, [uploaded, current])
    assert ranked.hypotheses[0].cause == "The limiter or clipper is being asked to solve a mix-balance problem"
    assert rationale == ""


def test_measured_transient_loss_prioritises_processing_check_without_claiming_the_stage() -> None:
    plan = plan_for("My drums lack punch")
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"integrated_lufs": -9.0},
        "analysis_evidence": {"transient_preservation": {"score": 0.42, "profile": "Smearing"}},
    })
    assert plan and packet
    ranked, rationale = rank_with_evidence(plan, [packet])
    assert ranked.hypotheses[0].cause == "The transient is being reduced by processing or source layering"
    assert "cannot identify the responsible stage" in rationale


def test_reference_spectral_measurement_prioritises_relationship_check_not_copying() -> None:
    plan = plan_for("Why is my mix darker than my reference?")
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"integrated_lufs": -10.0},
        "reference_comparison": {
            "largest_spectral_difference": {"band": "presence", "delta": -0.08},
            "lufs_delta_db": 0.3,
        },
    })
    assert plan and packet
    ranked, rationale = rank_with_evidence(plan, [packet])
    assert ranked.hypotheses[0].cause == "A measured spectral difference is coming from one or a few musical relationships"
    assert "does not prove a cause" in rationale


def test_sibilance_diagnosis_checks_capture_and_processing_before_deessing() -> None:
    plan = plan_for("My vocal has too much sibilance")
    assert plan is not None
    rendered = "\n".join(render(plan)).lower()
    assert "capture emphasises sibilants" in rendered
    assert "compression, saturation, or bright eq" in rendered
    assert "before adding a de-esser" in rendered


def test_room_reflection_diagnosis_separates_capture_from_processing() -> None:
    plan = plan_for("My vocal recording has bad room reflections")
    assert plan is not None
    rendered = "\n".join(render(plan)).lower()
    assert "early reflections are colouring" in rendered
    assert "microphone distance" in rendered
    assert "mix processing is exaggerating" in rendered


def test_unspecified_mix_review_refuses_to_invent_an_audible_problem() -> None:
    plan = plan_for("What's wrong with my mix?")
    assert plan is not None
    assert "No specific audible symptom" in plan.symptom
    assert "cannot diagnose arrangement" in plan.issue_type
    assert "Which exact moment is failing first" in plan.question


def test_harsh_mix_diagnosis_checks_sources_processing_and_monitoring() -> None:
    plan = plan_for("My mix is harsh and brittle")
    assert plan is not None
    rendered = "\n".join(render(plan)).lower()
    assert "multiple sources are accumulating" in rendered
    assert "dynamics, clipping, saturation, or limiting" in rendered
    assert "monitoring level or playback response" in rendered
    assert "broad master cut" in rendered


def test_squashed_mix_diagnosis_treats_crest_as_evidence_not_a_target() -> None:
    plan = plan_for("My mix sounds squashed and has no dynamics")
    assert plan is not None
    rendered = "\n".join(render(plan)).lower()
    assert "crest-factor number alone is not a universal quality score" in rendered
    assert "arrangement or source envelopes" in rendered
    assert "level matching" in rendered


def test_named_new_topic_does_not_inherit_a_pronoun_triggered_session_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_answer,
        "_load_session",
        lambda **_kwargs: {"last_question": "My vocal sounds harsh and thin."},
    )
    assert chat_answer._session_context_is_relevant("My master is -7 LUFS. Is that too loud?", "session") is False
    assert chat_answer._session_context_is_relevant("Is that too loud?", "session") is True
