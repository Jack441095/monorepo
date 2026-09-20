from __future__ import annotations

from pathlib import Path

from kenn.core.retrieval_index_candidate import inspect_candidate
from kenn.core.retrieval_index_shadow import candidate_search
from kenn.core.chat_retrieval import display_results
from kenn.core.retrieval_index_promotion import promote_candidate
from kenn.retrieval.index_store import active_version_dir
from kenn.retrieval.build_index import Chunk, build_terms
from kenn.retrieval.index_store import promote_index


MANUAL_SHA = "8f87f16f63589615e77bc88fbaaeb92cd87a21ab2ff7a71318cce44b9dc249ec"


def _candidate(root: Path, *, source_sha: str = MANUAL_SHA, official: bool = True) -> None:
    chunks = [
        {
            "id": "manual-1",
            "source": "live12-manual-en.pdf",
            "page": 1,
            "text": "Official Ableton manual text about routing.",
            "kind": "manual",
            "title": "Ableton Live 12 Reference Manual",
            "evidence_class": "official_ableton_manual" if official else "manual_reference",
        }
    ]
    terms = build_terms([Chunk(id="manual-1", source=chunks[0]["source"], page=1, text=chunks[0]["text"], kind="manual")])
    promote_index(
        chunks,
        terms,
        index_dir=root,
        manifest_metadata={
            "source_manifest": {
                "count": 1,
                "sources": [{"path": "Training_Data_PDF/live12-manual-en.pdf", "kind": "manual", "sha256": source_sha}],
            }
        },
    )


def test_candidate_with_bound_official_manual_is_verified(tmp_path: Path) -> None:
    _candidate(tmp_path)

    report = inspect_candidate(tmp_path, expected_manual_sha256=MANUAL_SHA)

    assert report["status"] == "verified"
    assert report["promotion_eligible"] is True
    assert report["official_manual_chunk_count"] == 1


def test_candidate_rejects_wrong_manual_provenance(tmp_path: Path) -> None:
    _candidate(tmp_path, source_sha="0" * 64)

    report = inspect_candidate(tmp_path, expected_manual_sha256=MANUAL_SHA)

    assert report["promotion_eligible"] is False
    assert "does not bind exactly one expected manual" in report["errors"][0]


def test_candidate_rejects_manual_without_official_evidence_class(tmp_path: Path) -> None:
    _candidate(tmp_path, official=False)

    report = inspect_candidate(tmp_path, expected_manual_sha256=MANUAL_SHA)

    assert report["promotion_eligible"] is False
    assert "no official-manual chunks" in report["errors"][0]


def test_candidate_shadow_keeps_official_evidence_and_abstains_without_subject_overlap() -> None:
    chunks = [
        {
            "id": "note", "kind": "note", "source": "tax.md", "title": "Tax note",
            "text": "taxes and finance", "topics": [],
        },
        {
            "id": "manual", "kind": "manual", "source": "live12-manual-en.pdf",
            "title": "Live 12 Manual", "text": "audio routing between tracks",
            "topics": ["routing"], "evidence_class": "official_ableton_manual",
        },
    ]
    terms = build_terms([
        Chunk(id=str(chunk["id"]), source=str(chunk["source"]), page=0, text=str(chunk["text"]), kind=str(chunk["kind"]))
        for chunk in chunks
    ])

    routing = candidate_search("What does the official Ableton manual say about routing?", chunks, terms)
    taxes = candidate_search("What does the official Ableton manual say about taxes?", chunks, terms)

    assert display_results("What does the official Ableton manual say about routing?", routing)[0][1]["id"] == "manual"
    assert display_results("What does the official Ableton manual say about taxes?", taxes) == []


def test_candidate_promotion_is_dry_run_until_explicitly_applied(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    _candidate(candidate)

    dry_run = promote_candidate(candidate, target, expected_manual_sha256=MANUAL_SHA)

    assert dry_run["status"] == "dry_run_verified"
    assert not target.exists()

    applied = promote_candidate(candidate, target, expected_manual_sha256=MANUAL_SHA, apply=True)

    assert applied["status"] == "promoted"
    assert active_version_dir(target).name == applied["candidate_version_id"]
