"""Guards against the exact gap found on 2026-07-18 (§4.3 of
docs/PROJECT_ACTION_PLAN_2026-07-18.md): a note can be written to
Training_Data_Notes/, have its own "note exists and is accurate" smoke test
pass (it just reads the file directly), and still be completely invisible to
retrieval because nobody re-ran build_index.py afterward. A source-cited
explain-function test can pass anyway if it happens to retrieve a different,
older note as a fallback -- which is exactly what happened to
automix-reference-tonal-balance-correction.md for a full day before the gap
was noticed and the index was rebuilt.

This test makes that failure mode loud and specific: for every .md file
under Training_Data_Notes/, assert its filename appears at least once as a
``source`` in the currently active index's chunks.jsonl. A stale index fails
here with the exact missing filenames, not just "some source got cited."
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NOTES_DIR = REPO_ROOT / "studio" / "kenn" / "kenn" / "Training_Data_Notes"

sys.path.insert(0, str(REPO_ROOT / "studio" / "kenn"))
from kenn.retrieval.index_store import active_artifact_path  # noqa: E402
from kenn.retrieval.build_index import should_index_note, clean_text  # noqa: E402

INDEX_CHUNKS = active_artifact_path("chunks.jsonl")

pytestmark = pytest.mark.skipif(
    not INDEX_CHUNKS.exists(),
    reason="KENN index not built — run `KENN_MAX_CONTRADICTIONS=<n> python studio/kenn/kenn/retrieval/build_index.py` first.",
)


def _indexed_sources() -> set[str]:
    sources: set[str] = set()
    with INDEX_CHUNKS.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            source = chunk.get("source")
            if source:
                sources.add(source)
    return sources


def test_every_training_note_is_present_in_the_active_index():
    """Only checks notes ``build_index.py`` itself would actually index
    (``should_index_note`` -- i.e. not explicitly marked Draft/Rejected).
    Draft notes awaiting approval are correctly absent from the index; this
    test must not flag those as the stale-index gap it exists to catch."""
    all_note_paths = sorted(NOTES_DIR.glob("*.md"))
    assert all_note_paths, f"expected at least one note in {NOTES_DIR}"

    indexable_names = [
        path.name for path in all_note_paths
        if should_index_note(clean_text(path.read_text(encoding="utf-8")))
    ]
    assert indexable_names, "expected at least one approved/unmarked note to check"

    indexed_sources = _indexed_sources()
    missing = [name for name in indexable_names if name not in indexed_sources]

    assert not missing, (
        f"{len(missing)} Training_Data_Notes file(s) exist on disk but are not in the "
        f"active index ({INDEX_CHUNKS}): {missing}. "
        "Run `KENN_MAX_CONTRADICTIONS=<n> python studio/kenn/kenn/retrieval/build_index.py` "
        "(from studio/kenn, with both studio/kenn and the repo root on PYTHONPATH) to rebuild."
    )
