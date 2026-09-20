"""Tests for the evidence-only AutoMix session mix graph adapter."""

from __future__ import annotations

from audio_analysis.integration.session_mix_graph import build_session_mix_graph


def test_graph_connects_stems_sections_and_relationship_evidence() -> None:
    graph = build_session_mix_graph(
        project_id="project-1",
        musical_roles=[
            {"stem_name": "kick.wav", "instrument": "kick", "role": "rhythmic_anchor", "priority": "support", "confidence": 0.84, "ambiguous": False},
            {"stem_name": "bass.wav", "instrument": "bass", "role": "rhythmic_anchor", "priority": "support", "confidence": 0.72, "ambiguous": False},
        ],
        arrangement={"sections": [{"section_id": "section-001", "start_seconds": 0, "end_seconds": 8, "active_stems": ["kick.wav", "bass.wav"], "density_band": "dense", "boundary_confidence": 0.8}]},
        relationships=[{
            "relationship_type": "kick_bass_competition", "source_stems": ["kick.wav", "bass.wav"],
            "protected_stem": "kick.wav", "intervention_target": "bass.wav", "confidence": 0.75,
            "status": "actionable", "evidence": {"measurement_scope": "section_local_erb"},
        }],
    )

    assert graph["schema"] == "audio-too.mix-graph.v1"
    assert {node["id"] for node in graph["nodes"]} >= {"bus:master", "stem:kick.wav", "stem:bass.wav", "section:section-001"}
    assert {edge["type"] for edge in graph["edges"]} >= {"routes_to", "active_in", "kick_bass_competition"}
    relationship = next(edge for edge in graph["edges"] if edge["type"] == "kick_bass_competition")
    assert relationship["protected"] == "stem:kick.wav"
    assert relationship["measurement_scope"] == "section_local_erb"


def test_graph_preserves_ambiguity_and_rejects_unknown_edge_stems() -> None:
    graph = build_session_mix_graph(
        project_id="project-2",
        musical_roles=[{"stem_name": "mystery.wav", "confidence": 0.4, "ambiguous": True}],
        arrangement={"sections": [{"section_id": "section-001", "active_stems": ["unknown.wav"]}]},
        relationships=[{"relationship_type": "spectral_competition", "source_stems": ["mystery.wav", "unknown.wav"]}],
    )

    assert graph["nodes"][1]["ambiguous"] is True
    assert not any(edge["type"] == "spectral_competition" for edge in graph["edges"])
    assert "remains ambiguous" in graph["warnings"][0]
