from __future__ import annotations

from kenn.core.chat_answer import build_template_answer
from kenn.core.evidence import EvidenceFact, EvidencePacket, history_turn


def _classification_packet(*, unknown: bool = False) -> EvidencePacket:
    if unknown:
        facts = (
            EvidenceFact("classification_selected_label", "Unknown", source="audio_classification", confidence="specialist_inference"),
            EvidenceFact("classification_selected_source", "unknown", source="audio_classification", confidence="specialist_inference"),
            EvidenceFact("classification_confidence_band", "low", source="audio_classification", confidence="specialist_inference"),
            EvidenceFact("classification_ood_status", "out_of_distribution", source="audio_classification", confidence="specialist_inference"),
        )
    else:
        facts = (
            EvidenceFact("classification_selected_label", "kick", source="audio_classification", confidence="specialist_inference"),
            EvidenceFact("classification_selected_source", "audio_only", source="audio_classification", confidence="specialist_inference"),
            EvidenceFact("classification_confidence_band", "high", source="audio_classification", confidence="specialist_inference"),
            EvidenceFact("classification_ood_status", "in_distribution", source="audio_classification", confidence="specialist_inference"),
            EvidenceFact("classification_audio_only_top_k", "kick (90.0%), snare (10.0%)", source="audio_classification", confidence="specialist_inference"),
        )
    return EvidencePacket(
        source="audio_classification",
        captured_at_age_seconds=None,
        facts=facts,
        limitations=("Specialist inference only.",),
    )


def test_ordinary_answer_surfaces_classifier_evidence() -> None:
    answer = build_template_answer(
        "classify this sample",
        [],
        history=[history_turn(_classification_packet())],
        route="production",
        timeline_context="The supplied sample analysis is available.",
    )

    assert "Evidence from your supplied analysis:" in answer
    assert "audio classifier suggests 'kick'" in answer
    assert "Audio-only candidates: kick (90.0%), snare (10.0%)." in answer


def test_ordinary_answer_keeps_unknown_classifier_unresolved() -> None:
    answer = build_template_answer(
        "identify this sample",
        [],
        history=[history_turn(_classification_packet(unknown=True))],
        route="production",
        timeline_context="The supplied sample analysis is available.",
    )

    assert "identity as unresolved" in answer
    assert "Evidence from your supplied analysis:" in answer
