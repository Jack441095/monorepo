"""Stage C — KENN dynamic EQ cut explanation tests.

Same grounding rigor as test_kenn_automix_parameter_explanations.py (Stage 9):
verifies real retrieval against the real KENN index (no mocking), that
explanations cite a real Training_Data_Notes source, and respond quickly.
Requires a built KENN index with studio/kenn/kenn/Training_Data_Notes/
automix-dynamic-eq.md indexed — skips gracefully if no index exists.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
DYNAMIC_EQ_NOTE = NOTES_DIR / "automix-dynamic-eq.md"

# The real index lives under a version-promotion scheme (data/index/CURRENT
# points at data/index/versions/<version>/chunks.jsonl), not a flat
# data/index/chunks.jsonl — resolve it the same way retrieval.py does rather
# than a hardcoded flat path, which would silently always skip these tests
# once a version has actually been promoted (found 2026-07-09: this exact
# stale-flat-path bug was already silently skipping
# test_kenn_automix_parameter_explanations.py's 21 tests without anyone
# noticing, since a skip and a pass both report as "not failed").
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"))
from kenn.retrieval.index_store import active_artifact_path  # noqa: E402

INDEX_CHUNKS = active_artifact_path("chunks.jsonl")

pytestmark = pytest.mark.skipif(
    not INDEX_CHUNKS.exists(),
    reason="KENN index not built — run `KENN_MAX_CONTRADICTIONS=<n> python studio/kenn/kenn/retrieval/build_index.py` first.",
)


def test_dynamic_eq_note_exists_and_is_accurate():
    """Sanity check the note this whole test file depends on actually exists
    and describes the real, current implementation (not stale docs)."""
    assert DYNAMIC_EQ_NOTE.exists()
    text = DYNAMIC_EQ_NOTE.read_text(encoding="utf-8")
    # Spot-check real parameter values from the actual code, not invented ones.
    assert "6 dB" in text or "6dB" in text  # prominence_threshold_db default
    assert "40%" in text  # persistence_threshold default (0.4)
    assert "iirpeak" in text  # the real filter used


@pytest.fixture(scope="module")
def kenn_index_env(tmp_path_factory):
    import os
    state_dir = tmp_path_factory.mktemp("kenn-dynamic-eq-explain")
    os.environ["KENN_CHATS_DIR"] = str(state_dir)
    os.environ["KENN_DB_PATH"] = str(state_dir / "kenn.db")
    os.environ["KENN_SESSION_FILE"] = str(state_dir / "session.json")
    yield


DYNAMIC_EQ_CASES = [
    {"frequency_hz": 2300.0, "mean_prominence_db": 8.0, "persistence": 0.65, "genre": "rock"},
    {"frequency_hz": 500.0, "mean_prominence_db": 6.5, "persistence": 0.42, "genre": "hip_hop"},
    {"frequency_hz": 4200.0, "mean_prominence_db": 9.2, "persistence": 0.8, "genre": None},
]


@pytest.mark.parametrize("case", DYNAMIC_EQ_CASES, ids=[f"{c['frequency_hz']}hz-{c['genre']}" for c in DYNAMIC_EQ_CASES])
def test_dynamic_eq_explanation_cites_real_source_and_is_fast(kenn_index_env, case):
    from audio_analysis.integration.kenn_handoff import explain_dynamic_eq_cut

    started = time.perf_counter()
    payload = explain_dynamic_eq_cut(
        case["frequency_hz"],
        mean_prominence_db=case["mean_prominence_db"],
        persistence=case["persistence"],
        genre=case["genre"],
        allow_llm=False,
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"took {elapsed:.2f}s, expected <5s"
    sources = payload.get("sources") or []
    assert sources, "expected at least one cited source"
    source_names = {s.get("source") if isinstance(s, dict) else str(s) for s in sources}
    assert "automix-dynamic-eq.md" in source_names, (
        f"expected the real dynamic-eq note among cited sources, got {source_names}"
    )
    pdf_dir = NOTES_DIR.parent / "Training_Data_PDF"
    for name in source_names:
        assert (NOTES_DIR / name).exists() or (pdf_dir / name).exists(), (
            f"cited source {name} does not exist on disk (checked notes and PDF directories)"
        )


def test_annotate_dynamic_eq_with_kenn_bulk_helper(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_dynamic_eq_with_kenn

    bands = [
        {"frequency_hz": 2300.0, "mean_prominence_db": 8.0, "persistence": 0.65, "band_index": 12},
        {"frequency_hz": 500.0, "mean_prominence_db": 6.5, "persistence": 0.42, "band_index": 4},
    ]
    explanations = annotate_dynamic_eq_with_kenn(bands, genre="rock", allow_llm=False)
    assert len(explanations) == 2
    for exp in explanations:
        assert exp["parameter"] == "dynamic EQ cut"
        assert exp["stem_name"] == "master bus"
        assert exp["sources"]


def test_annotate_dynamic_eq_with_kenn_respects_max_items(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_dynamic_eq_with_kenn

    bands = [
        {"frequency_hz": 500.0 + i * 200, "mean_prominence_db": 6.5, "persistence": 0.5, "band_index": i}
        for i in range(10)
    ]
    explanations = annotate_dynamic_eq_with_kenn(bands, max_items=3, allow_llm=False)
    assert len(explanations) <= 3


def test_annotate_dynamic_eq_with_kenn_empty_bands_returns_empty():
    from audio_analysis.integration.kenn_handoff import annotate_dynamic_eq_with_kenn

    assert annotate_dynamic_eq_with_kenn([]) == []
    assert annotate_dynamic_eq_with_kenn(None) == []


def test_annotate_dynamic_eq_with_kenn_swallows_individual_failures(kenn_index_env, monkeypatch):
    """A KENN/index problem on one band must not block the others — same
    best-effort guarantee mix_delivery.py relies on."""
    import audio_analysis.integration.kenn_handoff as kh

    call_count = {"n": 0}
    real_fn = kh.explain_dynamic_eq_cut

    def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated KENN failure")
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(kh, "explain_dynamic_eq_cut", flaky)
    bands = [
        {"frequency_hz": 2300.0, "mean_prominence_db": 8.0, "persistence": 0.65},
        {"frequency_hz": 500.0, "mean_prominence_db": 6.5, "persistence": 0.42},
    ]
    explanations = kh.annotate_dynamic_eq_with_kenn(bands, allow_llm=False)
    assert len(explanations) == 1  # first one failed, second succeeded
