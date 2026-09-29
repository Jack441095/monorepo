"""Measured Live data outranks the manual, the manual outranks our notes, and our notes outrank someone's video."""

from __future__ import annotations

from kenn.core import source_tiers
from kenn.core.chat_retrieval import evidence_label, result_payload
from kenn.retrieval.build_index import iter_note_chunks


def test_the_order_is_measured_manual_note_transcript() -> None:
    order = ["measured_live_data", "official_ableton_manual", "curated_kenn_note", "youtube_transcript"]
    assert [source_tiers.tier_of(name) for name in order] == sorted(source_tiers.tier_of(name) for name in order)
    assert len({source_tiers.tier_of(name) for name in order}) == 4


def test_a_session_read_is_as_good_as_a_measurement() -> None:
    assert source_tiers.tier_of("observed_session_fact") == source_tiers.tier_of("measured_live_data")


def test_the_higher_tier_wins_and_the_same_tier_does_not_pick() -> None:
    assert source_tiers.winner("youtube_transcript", "official_ableton_manual") == "official_ableton_manual"
    assert source_tiers.winner("curated_kenn_note", "measured_live_data") == "measured_live_data"
    assert source_tiers.winner("curated_kenn_note", "reference_document") is None


def test_an_unknown_class_ranks_last() -> None:
    assert source_tiers.tier_of("something new") == source_tiers.TIER_UNCLASSIFIED
    assert source_tiers.winner("something new", "youtube_transcript") == "youtube_transcript"


def test_every_cited_source_says_which_tier_it_is() -> None:
    chunk = {"source": "live12-manual-en.pdf", "page": 9, "kind": "manual", "evidence_class": "official_ableton_manual",
             "text": "Compressor threshold."}
    (source,) = result_payload("compressor threshold", [(9.0, chunk)])
    assert source["tier"] == source_tiers.TIER_MANUAL and source["tier_label"] == "Ableton manual"


def test_measured_data_has_its_own_label() -> None:
    assert evidence_label({"kind": "note", "evidence_class": "measured_live_data"}) == "Measured in Live"


NOTE = """# Compressor threshold, measured
Status: Approved
Tags: compressor
{extra}
Short answer:
Threshold runs from -57.2 dB to +6.0 dB.
"""


def test_only_a_generated_measured_note_gets_the_measured_class(tmp_path) -> None:
    generated = tmp_path / "measured-compressor.md"
    generated.write_text(NOTE.format(extra="Measured at: 2026-09-24"), encoding="utf-8")
    assert {c.evidence_class for c in iter_note_chunks(generated)} == {"measured_live_data"}

    # Same words under an ordinary name, or with no date, stay a KENN note: a note can't promote itself.
    claiming = tmp_path / "compressor.md"
    claiming.write_text(NOTE.format(extra="Measured at: 2026-09-24"), encoding="utf-8")
    undated = tmp_path / "measured-undated.md"
    undated.write_text(NOTE.format(extra=""), encoding="utf-8")
    assert {c.evidence_class for c in iter_note_chunks(claiming)} == {"curated_kenn_note"}
    assert {c.evidence_class for c in iter_note_chunks(undated)} == {"curated_kenn_note"}
