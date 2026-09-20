from __future__ import annotations

from pathlib import Path

import pytest

from kenn.retrieval import index_store
from kenn.retrieval.build_index import Chunk, build_terms
from kenn.retrieval.index_store import (
    IndexValidationError,
    active_version_dir,
    clear_validation_cache,
    promote_index,
    validate_version_cached,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_validation_cache()
    yield
    clear_validation_cache()


def _promote(root: Path, text: str) -> str:
    chunks = [{"id": "c-1", "source": "notes.md", "page": 1, "text": text, "kind": "note"}]
    terms = build_terms([Chunk(id="c-1", source="notes.md", page=1, text=text, kind="note")])
    return promote_index(chunks, terms, index_dir=root)


def _count_full_validations(monkeypatch) -> list[int]:
    calls = [0]
    original = index_store.validate_version

    def counting(version_dir: Path):
        calls[0] += 1
        return original(version_dir)

    monkeypatch.setattr(index_store, "validate_version", counting)
    return calls


def test_repeated_resolution_validates_the_bundle_once(tmp_path: Path, monkeypatch) -> None:
    _promote(tmp_path, "first bundle")
    clear_validation_cache()
    calls = _count_full_validations(monkeypatch)

    first = active_version_dir(tmp_path)
    for _ in range(20):
        assert active_version_dir(tmp_path) == first
    assert calls[0] == 1


def test_promotion_is_picked_up_without_a_stale_hit(tmp_path: Path) -> None:
    _promote(tmp_path, "first bundle")
    first = active_version_dir(tmp_path)
    second_id = _promote(tmp_path, "second bundle")
    resolved = active_version_dir(tmp_path)
    assert resolved is not None and resolved != first
    assert resolved.name == second_id


def test_rewriting_an_artifact_in_place_invalidates_the_cache(tmp_path: Path) -> None:
    _promote(tmp_path, "first bundle")
    version_dir = active_version_dir(tmp_path)
    assert version_dir is not None
    validate_version_cached(version_dir)

    chunks_path = version_dir / "chunks.jsonl"
    chunks_path.write_text(chunks_path.read_text(encoding="utf-8") + "\n{}\n", encoding="utf-8")

    with pytest.raises(IndexValidationError):
        validate_version_cached(version_dir)
    # A corrupt CURRENT falls through to no usable version rather than
    # returning the memoised pre-corruption answer.
    assert active_version_dir(tmp_path) is None


def test_failed_validation_is_not_cached(tmp_path: Path) -> None:
    _promote(tmp_path, "first bundle")
    version_dir = active_version_dir(tmp_path)
    assert version_dir is not None
    good = (version_dir / "chunks.jsonl").read_text(encoding="utf-8")

    (version_dir / "chunks.jsonl").write_text(good + "\n{}\n", encoding="utf-8")
    with pytest.raises(IndexValidationError):
        validate_version_cached(version_dir)

    (version_dir / "chunks.jsonl").write_text(good, encoding="utf-8")
    assert validate_version_cached(version_dir)["chunk_count"] == 1
