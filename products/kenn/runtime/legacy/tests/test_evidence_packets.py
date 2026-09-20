from __future__ import annotations

from kenn.core.chat_answer import build_template_answer
from kenn.core.chat import answer_payload
from kenn.server_payloads import mix_review_context_turn
from kenn.core.evidence import (
    EvidenceFact,
    EvidencePacket,
    from_ableton_session,
    from_mix_review_context,
    from_plugin_context,
    history_turn,
    current_for_diagnosis,
    packets_from_history,
    relevant_observations,
)
import time


def _plugin_context(**extra):
    context = {
        "schema": "kenn.live_mix_context.v1", "age_seconds": 2.0,
        "peak_dbfs": -0.1, "rms_dbfs": -12.0, "stereo_correlation": -0.2,
        "stereo_width": 0.8, "clipped_samples": 12,
    }
    context.update(extra)
    return context


def _results():
    return [(10.0, {"kind": "note", "title": "Master safety", "source": "master.md", "text": "Tags: master clipping loudness\nShort answer:\nCompare safely.\n\nTry this:\n1. Check stages.\n\nWhy it matters:\nAvoid assumptions."})]


def test_plugin_context_becomes_typed_measured_facts() -> None:
    packet = from_plugin_context(_plugin_context())
    assert packet is not None
    assert packet.source == "plugin_bus_snapshot"
    assert {fact.name for fact in packet.facts} >= {"peak_dbfs", "clipped_samples", "stereo_correlation"}
    assert all(fact.confidence == "measured" for fact in packet.facts)
    assert "no track" in packet.limitations[0].lower()


def test_mix_review_adapter_keeps_numeric_metrics_measured_but_not_flags() -> None:
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"integrated_lufs": -9.4, "true_peak_db": -0.3, "genre": "house"},
        "flags": [{"label": "Potential clipping"}],
    })
    assert packet is not None
    assert {fact.name for fact in packet.facts} == {"integrated_lufs", "true_peak_db"}
    assert all(fact.confidence == "measured" for fact in packet.facts)
    assert "flags" not in " ".join(fact.name for fact in packet.facts)


def test_mix_review_derived_technical_score_is_not_relabelled_as_a_measurement() -> None:
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"technical_score": 82, "true_peak_dbfs": -0.4},
    })
    assert packet is not None
    assert {fact.name for fact in packet.facts} == {"true_peak_dbfs"}


def test_ableton_adapter_reports_structure_without_claiming_audio_measurement() -> None:
    packet = from_ableton_session({
        "status": "connected", "tempo": 124.0,
        "tracks": [{"name": "Kick"}, {"name": "Bass"}],
    })
    assert packet is not None
    values = {fact.name: fact.value for fact in packet.facts}
    assert values["tempo"] == 124.0
    assert values["track_count"] == 2
    assert values["track_names"] == "Kick, Bass"
    assert "not clip content" in packet.limitations[0].lower()


def test_ableton_snapshot_is_only_shown_for_a_session_structure_question() -> None:
    packet = from_ableton_session({
        "status": "connected", "tempo": 124.0,
        "tracks": [{"name": "Kick"}, {"name": "Bass"}],
    })
    assert packet is not None
    assert relevant_observations("My vocal sounds harsh", [packet]) == []
    observation = relevant_observations("What is in my Ableton session?", [packet])[0]
    assert "124 BPM" in observation
    assert "Kick, Bass" in observation
    assert "not audio content" in observation


def test_mix_review_loudness_observation_is_tied_to_the_uploaded_render() -> None:
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"integrated_lufs": -8.2, "true_peak_db": -0.3},
    })
    assert packet is not None
    observation = relevant_observations("Is my master clipping or too loud?", [packet])[0]
    assert "uploaded Mix Review" in observation
    assert "integrated lufs -8.2 LUFS" in observation
    assert "not the cause inside individual tracks" in observation


def test_packet_round_trips_through_existing_chat_history_transport() -> None:
    packet = from_plugin_context(_plugin_context())
    assert packet is not None
    restored = packets_from_history([history_turn(packet)])
    assert len(restored) == 1
    assert restored[0].facts == packet.facts


def test_stale_plugin_snapshot_is_not_current_diagnostic_evidence() -> None:
    fresh = from_plugin_context(_plugin_context(age_seconds=2))
    stale = from_plugin_context(_plugin_context(age_seconds=16))
    uploaded = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1", "metrics": {"integrated_lufs": -9.0},
    })
    assert fresh and stale and uploaded
    assert current_for_diagnosis([fresh, stale, uploaded]) == [fresh, uploaded]


def test_historic_plugin_packet_expires_using_observation_time_not_original_age() -> None:
    packet = EvidencePacket(
        "plugin_bus_snapshot", 1.0,
        (EvidenceFact("peak_dbfs", -1.0, "dBFS", "plugin_bus_snapshot"),),
        ("Bus snapshot only.",),
        observed_at_epoch=time.time() - 30.0,
    )
    restored = packets_from_history([history_turn(packet)])
    assert len(restored) == 1
    assert current_for_diagnosis(restored) == []


def test_clipping_observation_does_not_claim_the_source_or_audibility() -> None:
    packet = from_plugin_context(_plugin_context())
    observations = relevant_observations("Why is my master clipping?", [packet])
    assert len(observations) == 1
    assert "12 clipped sample" in observations[0]
    assert "not its source or audibility" in observations[0]


def test_stereo_observation_is_not_injected_into_an_unrelated_vocal_question() -> None:
    packet = from_plugin_context(_plugin_context())
    assert relevant_observations("My vocal sounds harsh and thin", [packet]) == []


def test_mix_overview_shows_current_bus_facts_without_claiming_a_mix_verdict() -> None:
    packet = from_plugin_context(_plugin_context())
    assert packet is not None
    observation = relevant_observations("What's wrong with my mix?", [packet])[0]
    assert "peak -0.1 dBFS" in observation
    assert "12 clipped sample" in observation
    assert "cannot identify what sounds wrong" in observation


def test_separate_uploaded_and_current_snapshots_get_a_context_boundary() -> None:
    plugin = from_plugin_context(_plugin_context())
    uploaded = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1", "metrics": {"true_peak_dbfs": -0.3},
    })
    assert plugin and uploaded
    observations = relevant_observations("Is my master clipping?", [uploaded, plugin])
    assert any("different captures" in observation for observation in observations)


def test_uploaded_dynamics_metrics_are_not_presented_as_a_universal_target() -> None:
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"crest_factor_db": 6.1, "rms_dbfs_estimate": -8.4},
    })
    assert packet is not None
    observation = relevant_observations("My mix sounds squashed and lacks dynamics", [packet])[0]
    assert "crest factor 6.1 dB" in observation
    assert "do not by themselves prove" in observation


def test_optional_stem_and_transient_measurements_remain_typed_and_bounded() -> None:
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"integrated_lufs": -10.0},
        "analysis_evidence": {
            "transient_preservation": {"score": 0.42, "profile": "Smearing"},
            "stem_masking": {"lowest_visibility": 0.31, "lowest_visibility_stem": "Bass"},
            "low_end_stems": [{"name": "Kick", "low_end_share": 0.44}, {"name": "Bass", "low_end_share": 0.39}],
        },
    })
    assert packet is not None
    values = {fact.name: fact.value for fact in packet.facts}
    assert values["transient_preservation_score"] == 0.42
    assert values["stem_masking_lowest_visibility_stem"] == "Bass"
    observations = relevant_observations("My drums lack punch and kick fights bass", [packet])
    assert any("cannot identify which processing stage" in item for item in observations)
    assert any("not assuming it is the audible cause" in item for item in observations)


def test_reference_comparison_is_measured_without_becoming_a_matching_command() -> None:
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"integrated_lufs": -10.0},
        "reference_comparison": {
            "largest_spectral_difference": {"band": "presence", "delta": -0.08},
            "lufs_delta_db": 0.3,
        },
    })
    assert packet is not None
    observations = relevant_observations("Why is my mix darker than my reference?", [packet])
    assert any("presence (-0.080)" in item for item in observations)
    assert any("does not identify the contributing source" in item for item in observations)


def test_saved_mix_review_timeline_keeps_causal_diagnosis_when_structured_evidence_exists() -> None:
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"integrated_lufs": -10.0},
        "reference_comparison": {
            "largest_spectral_difference": {"band": "presence", "delta": -0.08},
            "lufs_delta_db": 0.3,
        },
    })
    assert packet is not None
    answer = build_template_answer(
        "Why is my mix darker than my reference?", _results(), route="production", answer_mode="mix_diagnosis",
        history=[history_turn(packet)], timeline_context="Mix Review Lab timeline for uploaded mix.",
    )
    assert "Diagnosis first:" in answer
    assert "Measured evidence:" in answer
    assert "presence (-0.080)" in answer


def test_mix_review_followup_route_does_not_swallow_a_clear_reference_diagnosis() -> None:
    context = {
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"integrated_lufs": -10.0},
        "reference_comparison": {
            "largest_spectral_difference": {"band": "presence", "delta": -0.08},
            "lufs_delta_db": 0.3,
        },
    }
    packet = from_mix_review_context(context)
    assert packet is not None
    payload = answer_payload(
        "Why is my mix darker than my reference?",
        history=[mix_review_context_turn(context), history_turn(packet)],
        allow_llm=False,
    )
    assert "Diagnosis first:" in payload["answer"]
    assert "Evidence-informed priority:" in payload["answer"]


def test_diagnostic_response_places_relevant_measurement_before_hypotheses() -> None:
    packet = from_plugin_context(_plugin_context())
    answer = build_template_answer(
        "My master is too loud and distorted.", _results(), route="production", answer_mode="mix_diagnosis",
        history=[history_turn(packet)],
    )
    assert "Measured evidence:" in answer
    assert "12 clipped sample" in answer
    assert answer.index("Measured evidence:") < answer.index("Most useful hypotheses to test:")


def test_symptom_shaped_mastering_question_keeps_measured_clipping_evidence() -> None:
    packet = from_plugin_context(_plugin_context())
    answer = build_template_answer(
        "My master is too loud and distorted.", _results(), route="production", answer_mode="mastering_safety",
        history=[history_turn(packet)],
    )
    assert "Measured evidence:" in answer
    assert "not its source or audibility" in answer


def test_measured_clipping_transparently_changes_diagnostic_priority() -> None:
    packet = from_plugin_context(_plugin_context())
    assert packet is not None
    answer = build_template_answer(
        "My master is too loud and distorted.", _results(), route="production", answer_mode="mastering_safety",
        history=[history_turn(packet)],
    )
    assert "Evidence-informed priority:" in answer
    assert "does not identify that stage" in answer
    assert answer.index("A specific stage is clipping or overshooting") < answer.index("The limiter or clipper is being asked")


def test_stale_plugin_clipping_does_not_claim_to_describe_the_current_mix() -> None:
    stale = from_plugin_context(_plugin_context(age_seconds=30))
    assert stale is not None
    answer = build_template_answer(
        "My master is too loud and distorted.", _results(), route="production", answer_mode="mastering_safety",
        history=[history_turn(stale)],
    )
    assert "Measured evidence:" not in answer
    assert "Evidence-informed priority:" not in answer
