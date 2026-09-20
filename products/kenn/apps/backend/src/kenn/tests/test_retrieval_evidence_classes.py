from __future__ import annotations

from kenn.core.chat_answer import format_source_as_link
from kenn.core.chat_retrieval import (
    asks_for_official_reference,
    display_results,
    evidence_class,
    evidence_label,
    has_manual_subject_overlap,
    result_payload,
)
from kenn.retrieval.build_index import Chunk, build_terms
from kenn.retrieval.build_index import iter_note_chunks
from kenn.retrieval.retrieval import bm25_search
from kenn.retrieval.build_index import pdf_evidence_class


def test_ableton_manual_catalogue_entry_is_explicitly_classified() -> None:
    assert pdf_evidence_class(
        {
            "category": "ableton",
            "title": "Ableton Live 12 Reference Manual",
            "tags": "ableton manual official",
        }
    ) == "official_ableton_manual"
    assert pdf_evidence_class({"category": "ableton", "title": "Ableton workflow tips"}) == "reference_document"


def test_note_and_legacy_manual_have_conservative_evidence_classes() -> None:
    note = {"kind": "note", "source": "mixing.md", "title": "Mixing"}
    legacy_manual = {"kind": "manual", "source": "unknown.pdf", "page": 2}

    assert evidence_class(note) == "curated_kenn_note"
    assert evidence_label(note) == "Curated KENN guidance"
    assert evidence_class(legacy_manual) == "manual_reference"
    assert evidence_label(legacy_manual) == "Manual reference"


def test_transcript_note_exposes_advisory_provenance(tmp_path) -> None:
    note = tmp_path / "noisia-test.md"
    note.write_text(
        "# Noisia Test\n\nType: Mixing workflow\nTags: mixing\nStatus: Approved\n"
        "Source creator: Noisia\nSource title: Mixing session\n"
        "Transcript file: noisia-test.txt\n\nShort answer:\nKeep the bass centred.\n",
        encoding="utf-8",
    )

    chunks = iter_note_chunks(note)

    assert chunks[0].evidence_class == "youtube_transcript"
    assert chunks[0].source_creator == "Noisia"
    assert chunks[0].transcript_file == "noisia-test.txt"
    assert evidence_label({"kind": "note", "evidence_class": "youtube_transcript"}) == "Reviewed producer transcript"


def test_structured_sources_and_rendered_citations_keep_provenance_visible() -> None:
    chunk = {
        "kind": "manual",
        "source": "live12-manual-en.pdf",
        "page": 41,
        "title": "Ableton Live 12 Reference Manual",
        "evidence_class": "official_ableton_manual",
        "text": "A device workflow from the manual.",
    }

    payload = result_payload("device workflow", [(4.0, chunk)])

    assert payload[0]["evidence_class"] == "official_ableton_manual"
    assert payload[0]["evidence_label"] == "Official Ableton manual"
    assert format_source_as_link(chunk).endswith("— Official Ableton manual")


def test_explicit_manual_request_prefers_official_manual_over_practical_note() -> None:
    note = {
        "kind": "note", "source": "workflow.md", "title": "Workflow", "page": 0,
        "text": "A practical note.", "topics": ["routing"],
    }
    manual = {
        "kind": "manual", "source": "live12-manual-en.pdf", "title": "Live 12 Manual", "page": 12,
        "text": "Official routing documentation.", "topics": ["routing"],
        "evidence_class": "official_ableton_manual",
    }

    displayed = display_results(
        "What does the official Ableton manual say about routing?", [(9.0, note), (4.0, manual)]
    )

    assert asks_for_official_reference("show the official manual")
    assert not asks_for_official_reference("how can I make this feel wider?")
    assert displayed[0][1]["source"] == "live12-manual-en.pdf"


def test_domain_manual_term_does_not_trigger_official_ableton_route() -> None:
    assert not asks_for_official_reference(
        "Why might an Unreal Wwise project use one manual bank?"
    )


def test_official_manual_candidate_is_retained_when_notes_dominate_generic_ranking() -> None:
    chunks = [
        {
            "id": f"note-{index}", "kind": "note", "source": f"export-{index}.md",
            "title": "Export audio workflow", "text": "export render audio Ableton workflow", "topics": ["export"],
        }
        for index in range(12)
    ]
    chunks.append({
        "id": "manual-export", "kind": "manual", "source": "live12-manual-en.pdf",
        "title": "Live 12 Manual", "text": "export rendered audio from Live", "topics": ["export"],
        "evidence_class": "official_ableton_manual",
    })
    terms = build_terms([
        Chunk(
            id=str(chunk["id"]), source=str(chunk["source"]), page=0,
            text=str(chunk["text"]), kind=str(chunk["kind"]), title=str(chunk["title"]),
        )
        for chunk in chunks
    ])

    manual_only = bm25_search(
        "official Ableton manual export rendered audio", chunks, terms, limit=3,
        allowed=lambda chunk: chunk.get("evidence_class") == "official_ableton_manual",
    )

    assert [chunk["id"] for _score, chunk in manual_only] == ["manual-export"]


def test_explicit_manual_request_abstains_without_substantive_official_match() -> None:
    note = {"kind": "note", "source": "tax.md", "title": "Taxes", "text": "Tax guidance."}
    manual = {
        "kind": "manual", "source": "live12-manual-en.pdf", "title": "Live 12 Manual",
        "text": "Category: ableton\nTitle: Ableton Live 12 Reference Manual\nAudio routing and clips.",
        "evidence_class": "official_ableton_manual",
    }

    displayed = display_results(
        "What does the official Ableton manual say about taxes?", [(9.0, note), (8.0, manual)], limit=3,
    )

    assert displayed == []
    assert has_manual_subject_overlap("What does the official Ableton manual say about taxes?", manual) is False
    assert has_manual_subject_overlap("What does the official Ableton manual say about routing?", manual) is True


def test_display_results_keeps_distinct_relevant_note_sources() -> None:
    primary = {
        "kind": "note", "source": "reverb-send.md", "title": "Reverb Send",
        "text": "Return routing and feedback.", "topics": ["routing"],
    }
    related = {
        "kind": "note", "source": "reamping-and-printing-effects.md",
        "title": "Reamping and Printing Effects", "text": "Record processed effects to a new audio track.",
        "topics": ["routing", "recording"],
    }
    manual = {
        "kind": "manual", "source": "live12-manual-en.pdf", "page": 10,
        "text": "Official Ableton routing reference.", "topics": ["routing"],
        "evidence_class": "official_ableton_manual",
    }

    displayed = display_results(
        "What routing hazard should I avoid when recording processed effects?",
        [(10.0, primary), (9.0, related), (8.0, manual)],
        limit=3,
    )

    sources = [chunk["source"] for _score, chunk in displayed]
    assert len(sources) == 3
    assert {"reverb-send.md", "reamping-and-printing-effects.md"} <= set(sources)
    assert sources[-1] == "live12-manual-en.pdf"


def test_display_results_surfaces_authoritative_measurement_note() -> None:
    practical = {
        "kind": "note", "source": "true-peak-inter-sample-clipping.md",
        "title": "True Peak and Inter-Sample Clipping", "text": "Reconstruction can exceed samples.",
        "topics": ["mastering"],
    }
    authority = {
        "kind": "note", "source": "itu-bs1770-true-peak-measurement.md",
        "title": "ITU BS.1770 True-Peak Measurement", "text": "Continuous reconstruction between samples.",
        "topics": ["mastering"], "source_creator": "International Telecommunication Union",
    }

    displayed = display_results(
        "Why can true peak be higher than the largest stored PCM sample?",
        [(100.0, practical), (60.0, authority)],
        limit=3,
    )

    assert displayed[0][1]["source"] == "itu-bs1770-true-peak-measurement.md"


def test_note_affinity_prefers_album_sequence_for_perceived_loudness() -> None:
    from kenn.core.chat_retrieval import note_query_affinity

    query = "Two masters show the same integrated loudness but one feels much louder. Should I adjust the sequence by ear?"
    sequence = {
        "source": "mastering-album-sequencing.md",
        "title": "Mastering Album Sequencing and Consistency",
        "tags": ["mastering", "album", "sequencing", "perceived loudness"],
        "text": "Compare perceived loudness and integrated loudness across a sequence by ear.",
    }
    delivery = {
        "source": "mastering-streaming-loudness.md",
        "title": "Mastering for Streaming Loudness",
        "tags": ["mastering", "loudness"],
        "text": "Use integrated loudness and platform targets.",
    }

    assert note_query_affinity(query, sequence) > note_query_affinity(query, delivery)


def test_note_affinity_prefers_hat_workflow_over_vocal_deessing_for_hi_hat() -> None:
    from kenn.core.chat_retrieval import note_query_affinity

    query = "What should I check if my hi-hat sounds harsh?"
    hats = {
        "source": "harsh-hats-cymbals-control.md",
        "title": "Harsh Hats And Cymbals Control",
        "tags": ["hats", "hi-hats", "harshness", "drums"],
        "text": "Harsh hats usually need less level or dynamic control.",
    }
    vocal = {
        "source": "vocal-deessing-and-sibilance.md",
        "title": "Vocal De-Essing And Sibilance",
        "tags": ["vocals", "de-essing", "sibilance", "harsh"],
        "text": "Treat harsh S and T sounds with a de-esser.",
    }

    assert note_query_affinity(query, hats) > note_query_affinity(query, vocal)


def test_note_affinity_prefers_ableton_device_note_for_explicit_dry_wet_request() -> None:
    from kenn.core.chat_retrieval import note_query_affinity

    query = "How can I add reverb to the hi-hat at 25% dry/wet?"
    device = {
        "source": "ableton-hybrid-reverb-device.md",
        "title": "Ableton Hybrid Reverb Dual Engine",
        "tags": ["ableton", "hybrid reverb", "dry/wet", "device"],
        "text": "Insert Hybrid Reverb on a track and adjust Dry/Wet.",
    }
    send = {
        "source": "reverb-send-workflow.md",
        "title": "Reverb Send Workflow",
        "tags": ["reverb", "send", "return", "mixing"],
        "text": "Create a Return track with Reverb and set it 100% wet.",
    }

    assert note_query_affinity(query, device) > note_query_affinity(query, send)


def test_note_affinity_prefers_spectral_reference_note_for_measured_pink_noise_question() -> None:
    from kenn.core.chat_retrieval import note_query_affinity

    query = "My master is 5 dB above a pink-noise reference around 300 Hz. What does that suggest?"
    spectral = {
        "source": "spectral-reference-slope.md",
        "title": "Spectral Reference Slope",
        "tags": ["spectral analysis", "pink noise", "reference track"],
        "text": "A pink-noise-style slope is a useful baseline, not a universal target.",
    }
    translation = {
        "source": "mix-translation-checks.md",
        "title": "Mix Translation Checks",
        "tags": ["balance", "reference", "translation"],
        "text": "Check references, mono, quiet listening, and small speakers.",
    }

    assert note_query_affinity(query, spectral) > note_query_affinity(query, translation)
