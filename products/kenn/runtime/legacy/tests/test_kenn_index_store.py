"""Crash, corruption, and concurrency tests for KENN index promotion."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from kenn.core import chat_retrieval
from kenn.retrieval.index_store import (
    IndexValidationError,
    active_artifact_path,
    active_version_dir,
    active_version_id,
    prune_old_versions,
    promote_index,
    rollback_index,
    validate_version,
)


def _chunks(count: int, label: str) -> list[dict]:
    return [
        {
            "id": f"{label}-{index}",
            "source": f"{label}.md",
            "page": 1,
            "text": f"{label} text {index}",
            "kind": "note",
            "title": label,
            "section": "test",
            "tags": [label],
            "topics": [label],
        }
        for index in range(count)
    ]


def _terms(count: int) -> dict:
    return {
        "version": 3,
        "total_docs": count,
        "avg_len": 1.0,
        "lengths": [1] * count,
        "term_counts": [{"test": 1} for _ in range(count)],
        "idf": {"test": 1.0},
    }


def _embeddings(count: int, value: float = 1.0) -> np.ndarray:
    return np.full((count, 4), value, dtype=np.float32)


def test_promotes_complete_version_and_resolves_all_artifacts(tmp_path) -> None:
    version = promote_index(
        _chunks(2, "first"),
        _terms(2),
        _embeddings(2),
        index_dir=tmp_path,
        version_id="v001",
    )

    assert version == "v001"
    assert active_version_id(tmp_path) == "v001"
    version_dir = active_version_dir(tmp_path)
    assert version_dir is not None
    manifest = validate_version(version_dir)
    assert manifest["chunk_count"] == 2
    assert set(manifest["artifacts"]) == {
        "chunks.jsonl",
        "terms.json",
        "embeddings.npy",
    }
    assert active_artifact_path("chunks.jsonl", tmp_path).parent == version_dir


def test_identical_default_promotions_reuse_content_addressed_version(tmp_path) -> None:
    metadata = {"index_schema": "test.v2", "parameters": {"limit": 8}}
    first = promote_index(
        _chunks(2, "same"),
        _terms(2),
        _embeddings(2),
        index_dir=tmp_path,
        manifest_metadata=metadata,
    )
    second = promote_index(
        _chunks(2, "same"),
        _terms(2),
        _embeddings(2),
        index_dir=tmp_path,
        manifest_metadata=metadata,
    )

    assert first == second
    assert first.startswith("v-")
    versions = [path for path in (tmp_path / "versions").iterdir() if path.is_dir()]
    assert [path.name for path in versions] == [first]
    manifest = validate_version(versions[0])
    assert manifest["schema_version"] == 2
    assert manifest["build"] == metadata


def test_explicit_rollback_swaps_valid_current_and_previous(tmp_path) -> None:
    promote_index(_chunks(1, "first"), _terms(1), index_dir=tmp_path, version_id="v001")
    promote_index(_chunks(1, "second"), _terms(1), index_dir=tmp_path, version_id="v002")

    assert rollback_index(tmp_path) == "v001"
    assert active_version_id(tmp_path) == "v001"
    assert (tmp_path / "PREVIOUS").read_text().strip() == "v002"


def test_explicit_rollback_rejects_missing_previous(tmp_path) -> None:
    promote_index(_chunks(1, "first"), _terms(1), index_dir=tmp_path, version_id="v001")

    with pytest.raises(IndexValidationError, match="No valid previous"):
        rollback_index(tmp_path)


@pytest.mark.parametrize("fault_point", ["after_stage", "after_version_rename", "before_pointer_replace"])
def test_crash_before_pointer_swap_keeps_last_known_good(
    tmp_path, fault_point: str
) -> None:
    promote_index(
        _chunks(1, "stable"), _terms(1), index_dir=tmp_path, version_id="v001"
    )

    def crash(point: str) -> None:
        if point == fault_point:
            raise RuntimeError("simulated crash")

    with pytest.raises(RuntimeError, match="simulated crash"):
        promote_index(
            _chunks(2, "new"),
            _terms(2),
            index_dir=tmp_path,
            version_id="v002",
            fault_hook=crash,
        )

    assert active_version_id(tmp_path) == "v001"
    assert (tmp_path / "CURRENT").read_text().strip() == "v001"
    assert not list((tmp_path / "versions").glob(".staging-*"))
    assert not list(tmp_path.glob(".CURRENT.*.tmp"))


def test_corrupt_current_version_falls_back_to_prior_valid_version(tmp_path) -> None:
    promote_index(
        _chunks(1, "stable"), _terms(1), index_dir=tmp_path, version_id="v001"
    )
    promote_index(
        _chunks(2, "new"), _terms(2), index_dir=tmp_path, version_id="v002"
    )
    (tmp_path / "versions" / "v002" / "terms.json").write_text("corrupt")

    assert active_version_id(tmp_path) == "v001"
    with pytest.raises(IndexValidationError):
        validate_version(tmp_path / "versions" / "v002")


def test_valid_orphan_is_never_treated_as_promoted(tmp_path) -> None:
    def crash(point: str) -> None:
        if point == "after_version_rename":
            raise RuntimeError("crash before first pointer")

    with pytest.raises(RuntimeError):
        promote_index(
            _chunks(1, "orphan"),
            _terms(1),
            index_dir=tmp_path,
            version_id="v001",
            fault_hook=crash,
        )

    assert validate_version(tmp_path / "versions" / "v001")
    assert active_version_dir(tmp_path) is None


def test_concurrent_promotions_never_publish_partial_bundle(tmp_path) -> None:
    def promote(index: int) -> str:
        count = (index % 4) + 1
        return promote_index(
            _chunks(count, f"build-{index}"),
            _terms(count),
            _embeddings(count, float(index)),
            index_dir=tmp_path,
            version_id=f"v{index:03d}",
            # This test inspects every promoted version's integrity after
            # the fact (see the loop below) -- disable the default
            # retention pruning (added 2026-08-11) so all 20 stay on disk;
            # pruning behavior itself is covered by test_prune_old_versions*.
            version_retention=0,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        versions = list(pool.map(promote, range(20)))

    assert len(set(versions)) == 20
    active = active_version_dir(tmp_path)
    assert active is not None
    validate_version(active)
    for version in versions:
        validate_version(tmp_path / "versions" / version)
    assert not list((tmp_path / "versions").glob(".staging-*"))
    assert not list(tmp_path.glob(".CURRENT.*.tmp"))


def test_promote_index_prunes_old_versions_but_keeps_current_and_previous(tmp_path) -> None:
    for index in range(8):
        promote_index(
            _chunks(1, f"build-{index}"),
            _terms(1),
            index_dir=tmp_path,
            version_id=f"v{index:03d}",
            version_retention=3,
        )

    remaining = {p.name for p in (tmp_path / "versions").iterdir() if p.is_dir()}
    assert len(remaining) == 3
    # The two most recent promotions (CURRENT and PREVIOUS) must always
    # survive, even though "keep 3" alone wouldn't guarantee PREVIOUS
    # specifically without the protected-set logic in prune_old_versions.
    assert "v007" in remaining
    assert "v006" in remaining
    for stale in ("v000", "v001", "v002", "v003", "v004"):
        assert stale not in remaining


def test_promote_index_version_retention_zero_disables_pruning(tmp_path) -> None:
    for index in range(6):
        promote_index(
            _chunks(1, f"build-{index}"),
            _terms(1),
            index_dir=tmp_path,
            version_id=f"v{index:03d}",
            version_retention=0,
        )

    remaining = {p.name for p in (tmp_path / "versions").iterdir() if p.is_dir()}
    assert remaining == {f"v{index:03d}" for index in range(6)}


def test_prune_old_versions_never_deletes_current_or_previous_even_if_older_than_window(
    tmp_path,
) -> None:
    # CURRENT/PREVIOUS must survive on protected-pointer status alone, not
    # recency -- age them artificially, then add several newer,
    # non-pointer-referenced directories (e.g. left over from an aborted
    # build) directly on disk, without another promotion moving the pointers.
    promote_index(
        _chunks(1, "old-previous"), _terms(1), index_dir=tmp_path,
        version_id="old-previous", version_retention=0,
    )
    promote_index(
        _chunks(1, "old-current"), _terms(1), index_dir=tmp_path,
        version_id="old-current", version_retention=0,
    )
    protected_current = (tmp_path / "CURRENT").read_text().strip()
    protected_previous = (tmp_path / "PREVIOUS").read_text().strip()
    assert protected_current == "old-current"
    assert protected_previous == "old-previous"

    import os
    import time

    old_time = time.time() - 999999
    for name in (protected_current, protected_previous):
        os.utime(tmp_path / "versions" / name, (old_time, old_time))

    for index in range(5):
        (tmp_path / "versions" / f"newer-junk-{index}").mkdir()

    removed = prune_old_versions(tmp_path, keep=3)
    remaining = {p.name for p in (tmp_path / "versions").iterdir() if p.is_dir()}
    assert protected_current in remaining
    assert protected_previous in remaining
    assert protected_current not in removed
    assert protected_previous not in removed


def test_chunk_and_term_loaders_share_one_bundle_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chat_retrieval, "CHUNKS_PATH", tmp_path / "chunks.jsonl")
    monkeypatch.setattr(chat_retrieval, "TERMS_PATH", tmp_path / "terms.json")
    promote_index(
        _chunks(1, "initial"), _terms(1), index_dir=tmp_path, version_id="v000"
    )

    def writer() -> None:
        for index in range(1, 16):
            count = (index % 3) + 1
            promote_index(
                _chunks(count, f"write-{index}"),
                _terms(count),
                index_dir=tmp_path,
                version_id=f"v{index:03d}",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(writer)
        while not future.done():
            chat_retrieval.load_chunks.cache_clear()
            chunks = chat_retrieval.load_chunks()
            terms = chat_retrieval.load_terms()
            assert len(chunks) == terms["total_docs"]
            assert len(chunks) == len(terms["term_counts"])
        future.result()
    chat_retrieval.load_chunks.cache_clear()
