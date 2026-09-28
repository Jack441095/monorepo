"""Source tier and contradiction check verification suite.

In KENN, factual authority follows a strict hierarchy:
1. Official Ableton Reference Manual and real Live session measurements
   hold the highest authority (trust rating 1.0).
2. Curated KENN craft notes hold medium authority (trust rating 0.9).
3. Transcripts, web notes, and general advice hold advisory authority (0.7).

When sources disagree on numerical values (e.g., recommended headroom,
glue compressor threshold, or filter slopes), the contradiction registry
detects the mismatch, records it in SQLite, and prevents index rebuilds
until resolved. This suite verifies the full lifecycle: detection, tier
ranking, resolution, and index gating.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from kenn.core.chat_retrieval import (
    asks_for_official_reference,
    display_results,
    evidence_class,
    evidence_label,
)
from kenn.knowledge.contradictions import (
    list_contradictions,
    resolve_contradiction,
    scan_for_contradictions,
)
from kenn.knowledge.reasoning import init_db
from kenn.knowledge.trust_scores import (
    get_source_default_trust,
    get_source_trust,
    record_citation,
    record_correction,
    set_source_trust,
)


@pytest.fixture
def isolated_knowledge_env(monkeypatch):
    """Isolate SQLite database and note fixtures in a clean temporary directory.

    We redirect KENN_DB_PATH and KENN_CHATS_DIR so tests never pollute
    developer databases or user session memory.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kenn_test.db"
        notes_dir = Path(tmpdir) / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setenv("KENN_DB_PATH", str(db_path))
        monkeypatch.setenv("KENN_CHATS_DIR", tmpdir)
        init_db()
        yield db_path, notes_dir


def test_source_tier_default_trust_ratings() -> None:
    # Official manual documentation starts at highest trust (1.0).
    assert get_source_default_trust("live12-manual-en.pdf") == 1.0
    assert get_source_default_trust("official-ableton-manual.pdf") == 1.0

    # Curated markdown notes start at 0.9.
    assert get_source_default_trust("glue-compression-bus.md") == 0.9
    assert get_source_default_trust("vocal-eq-carving.md") == 0.9

    # Transcripts and external web material start at advisory trust (0.7).
    assert get_source_default_trust("youtube-interview-transcript.txt") == 0.7
    assert get_source_default_trust("podcast-mastering-workflow.txt") == 0.7

    # Unknown or unclassified sources receive a conservative baseline (0.5).
    assert get_source_default_trust("unclassified_source") == 0.5


def test_trust_scores_update_dynamically(isolated_knowledge_env) -> None:
    source = "gain-staging-note.md"
    initial = get_source_trust(source)
    assert initial == 0.9

    # Successful citations slightly increase confidence up to 1.0.
    record_citation(source)
    assert get_source_trust(source) == 0.91

    # User corrections penalize trust by 0.1 down to a floor of 0.1.
    record_correction(source)
    assert get_source_trust(source) == 0.81

    # Manual overrides take immediate effect within bounded [0.0, 1.0] range.
    set_source_trust(source, 0.95)
    assert get_source_trust(source) == 0.95


def test_display_results_prioritizes_official_manual_over_notes_when_asked() -> None:
    practical_note = {
        "kind": "note",
        "source": "sidechain-guide.md",
        "title": "Practical Sidechaining",
        "page": 0,
        "text": "Set compressor release to match song tempo.",
        "topics": ["routing", "sidechain"],
    }
    official_manual = {
        "kind": "manual",
        "source": "live12-manual-en.pdf",
        "title": "Ableton Live 12 Reference Manual",
        "page": 432,
        "text": "The Sidechain section routes external audio signals into the detector.",
        "topics": ["routing", "sidechain"],
        "evidence_class": "official_ableton_manual",
    }

    # When the user explicitly requests the manual, the official reference must rank first.
    query = "What does the official Ableton manual say about sidechain routing?"
    assert asks_for_official_reference(query) is True

    ranked = display_results(query, [(10.0, practical_note), (5.0, official_manual)])
    assert len(ranked) >= 1
    assert ranked[0][1]["source"] == "live12-manual-en.pdf"
    assert evidence_class(ranked[0][1]) == "official_ableton_manual"
    assert evidence_label(ranked[0][1]) == "Official Ableton manual"


def test_contradiction_detection_between_conflicting_notes(isolated_knowledge_env) -> None:
    _, notes_dir = isolated_knowledge_env

    # We author two notes with the same contradiction key and shared tags,
    # but opposing ceiling measurements.
    note_a = (
        "# Master Limiting Standard\n\n"
        "Type: Note\n"
        "Tags: mastering, limiting\n"
        "Status: Approved\n"
        "Contradiction-Key: master-ceiling-db\n\n"
        "Set the ceiling to -1.0 dB to prevent inter-sample distortion.\n"
    )
    note_b = (
        "# Hot Master Workflow\n\n"
        "Type: Note\n"
        "Tags: mastering, limiting\n"
        "Status: Approved\n"
        "Contradiction-Key: master-ceiling-db\n\n"
        "Set the ceiling to -0.1 dB for maximum loudness.\n"
    )
    (notes_dir / "standard_master.md").write_text(note_a, encoding="utf-8")
    (notes_dir / "hot_master.md").write_text(note_b, encoding="utf-8")

    conflicts = scan_for_contradictions(notes_dir)
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "measurement_mismatch"
    assert conflicts[0]["conflicting_data"]["contradiction_key"] == "master-ceiling-db"
    assert conflicts[0]["conflicting_data"]["measurement_context"] == "ceiling"

    stored = list_contradictions()
    assert len(stored) == 1
    assert stored[0]["status"] == "open"


def test_transcript_vs_manual_contradiction_classified_specifically(isolated_knowledge_env) -> None:
    _, notes_dir = isolated_knowledge_env

    manual_note = (
        "# Glue Compressor Manual\n\n"
        "Type: Manual\n"
        "Tags: compression\n"
        "Status: Approved\n"
        "Contradiction-Key: glue-threshold-setting\n\n"
        "Set the compressor threshold to -4 dB for glue.\n"
    )
    transcript_note = (
        "# Masterclass Video\n\n"
        "Type: Transcript\n"
        "Tags: compression\n"
        "Status: Approved\n"
        "Contradiction-Key: glue-threshold-setting\n\n"
        "Set the compressor threshold to -10 dB for heavy pumping.\n"
    )
    (notes_dir / "manual_ratio.md").write_text(manual_note, encoding="utf-8")
    (notes_dir / "transcript_ratio.md").write_text(transcript_note, encoding="utf-8")

    conflicts = scan_for_contradictions(notes_dir)
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "transcript_vs_manual"


def test_distinct_parameters_with_same_units_do_not_flag_false_contradictions(isolated_knowledge_env) -> None:
    _, notes_dir = isolated_knowledge_env

    # Both notes mention decibels, but one discusses headroom while the other discusses EQ boost.
    note_a = (
        "# Mix Bus Headroom\n"
        "Type: Note\n"
        "Tags: mixing, gain\n"
        "Status: Approved\n\n"
        "Leave -6 dB headroom for mastering.\n"
    )
    note_b = (
        "# Snare Presence Boost\n"
        "Type: Note\n"
        "Tags: mixing, eq\n"
        "Status: Approved\n\n"
        "Add a 3 dB boost at 5 kHz.\n"
    )
    (notes_dir / "headroom.md").write_text(note_a, encoding="utf-8")
    (notes_dir / "boost.md").write_text(note_b, encoding="utf-8")

    conflicts = scan_for_contradictions(notes_dir)
    assert conflicts == []
    assert list_contradictions() == []


def test_contradiction_resolution_primary_a_demotes_other_to_draft(isolated_knowledge_env) -> None:
    _, notes_dir = isolated_knowledge_env

    note_a = (
        "# Trusted Low End Guide\n"
        "Type: Note\n"
        "Tags: bass, filter\n"
        "Status: Approved\n"
        "Contradiction-Key: sub-hpf-cutoff\n\n"
        "Apply a low cut at 30 Hz.\n"
    )
    note_b = (
        "# Aggressive Low Cut\n"
        "Type: Note\n"
        "Tags: bass, filter\n"
        "Status: Approved\n"
        "Contradiction-Key: sub-hpf-cutoff\n\n"
        "Apply a low cut at 50 Hz.\n"
    )
    path_a = notes_dir / "note_a.md"
    path_b = notes_dir / "note_b.md"
    path_a.write_text(note_a, encoding="utf-8")
    path_b.write_text(note_b, encoding="utf-8")

    conflicts = scan_for_contradictions(notes_dir)
    assert len(conflicts) == 1
    assert conflicts[0]["source_a"] == "note_a.md"
    assert conflicts[0]["source_b"] == "note_b.md"
    cid = conflicts[0]["contradiction_id"]

    # When resolving as primary_a, note_a remains approved while note_b is demoted to Draft.
    resolved = resolve_contradiction(cid, "primary_a", notes_dir)
    assert resolved is True

    # Note A remains active
    assert "Status: Approved" in path_a.read_text(encoding="utf-8")
    # Note B is now Draft
    content_b = path_b.read_text(encoding="utf-8")
    assert "Status: Draft" in content_b
    assert "Status: Approved" not in content_b

    # A subsequent scan finds zero open contradictions because only approved notes are evaluated.
    assert scan_for_contradictions(notes_dir) == []


def test_index_build_blocks_when_contradictions_exceed_threshold(isolated_knowledge_env, monkeypatch) -> None:
    _, notes_dir = isolated_knowledge_env

    note_a = (
        "# Vocals A\nType: Note\nTags: vocal, compression\nStatus: Approved\n"
        "Contradiction-Key: vocal-threshold\n\nSet threshold to -18 dB.\n"
    )
    note_b = (
        "# Vocals B\nType: Note\nTags: vocal, compression\nStatus: Approved\n"
        "Contradiction-Key: vocal-threshold\n\nSet threshold to -24 dB.\n"
    )
    (notes_dir / "voc_a.md").write_text(note_a, encoding="utf-8")
    (notes_dir / "voc_b.md").write_text(note_b, encoding="utf-8")

    # When KENN_MAX_CONTRADICTIONS is 0, any unresolved contradiction prevents building the search index.
    monkeypatch.setenv("KENN_MAX_CONTRADICTIONS", "0")

    from kenn.retrieval.build_index import build_index

    with pytest.raises(SystemExit) as exc_info:
        build_index(pdf_dir=notes_dir, notes_dir=notes_dir)

    assert "Index rebuild blocked due to 1 open contradictions" in str(exc_info.value)
