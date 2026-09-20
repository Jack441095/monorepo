"""Stage 9.7 — KENN masking de-mask and mono-compatibility correction
explanation tests.

Same grounding rigor as test_kenn_bus_eq_band_explanations.py (Stage 9.6):
verifies real retrieval against the real KENN index (no mocking), that
explanations cite a real Training_Data_Notes source, and respond quickly.
Requires a built KENN index with studio/kenn/kenn/Training_Data_Notes/
automix-masking-correction.md and automix-mono-compat-correction.md indexed
— skips gracefully if no index exists.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
MASKING_NOTE = NOTES_DIR / "automix-masking-correction.md"
MONO_COMPAT_NOTE = NOTES_DIR / "automix-mono-compat-correction.md"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"))
from kenn.retrieval.index_store import active_artifact_path  # noqa: E402

INDEX_CHUNKS = active_artifact_path("chunks.jsonl")

pytestmark = pytest.mark.skipif(
    not INDEX_CHUNKS.exists(),
    reason="KENN index not built — run `KENN_MAX_CONTRADICTIONS=<n> python studio/kenn/kenn/retrieval/build_index.py` first.",
)


def test_masking_note_exists_and_is_accurate():
    assert MASKING_NOTE.exists()
    text = MASKING_NOTE.read_text(encoding="utf-8")
    assert "dynamic_eq" in text
    assert "8" in text  # _MAX_MASKING_MOVES_PER_SONG
    assert "apply_masking_corrections" in text


def test_mono_compat_note_exists_and_is_accurate():
    assert MONO_COMPAT_NOTE.exists()
    text = MONO_COMPAT_NOTE.read_text(encoding="utf-8")
    assert "0.6" in text  # warning correction factor
    assert "0.35" in text  # critical correction factor
    assert "apply_mono_compat_correction" in text


@pytest.fixture(scope="module")
def kenn_index_env(tmp_path_factory):
    import os
    state_dir = tmp_path_factory.mktemp("kenn-masking-monocompat-explain")
    os.environ["KENN_CHATS_DIR"] = str(state_dir)
    os.environ["KENN_DB_PATH"] = str(state_dir / "kenn.db")
    os.environ["KENN_SESSION_FILE"] = str(state_dir / "session.json")
    yield


def _source_names(payload: dict) -> set[str]:
    sources = payload.get("sources") or []
    return {s.get("source") if isinstance(s, dict) else str(s) for s in sources}


# ── Masking de-mask correction ───────────────────────────────────────────


def test_masking_explanation_cites_real_source_and_is_fast(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import explain_masking_correction

    started = time.perf_counter()
    payload = explain_masking_correction(
        "LEAD_SYNTH", frequency_hz=1200.0, max_reduction_db=3.5, genre="electronic", allow_llm=False,
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"took {elapsed:.2f}s, expected <5s"
    source_names = _source_names(payload)
    assert "automix-masking-correction.md" in source_names, (
        f"expected the masking-correction note among cited sources, got {source_names}"
    )
    pdf_dir = NOTES_DIR.parent / "Training_Data_PDF"
    for name in source_names:
        assert (NOTES_DIR / name).exists() or (pdf_dir / name).exists()


def test_annotate_masking_corrections_with_kenn_bulk_helper(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_masking_corrections_with_kenn

    corrections = {
        "LEAD_SYNTH": {"frequency_hz": 1200.0, "max_reduction_db": 3.5, "q": 1.2, "score": 0.8},
        "PAD": {"frequency_hz": 800.0, "max_reduction_db": 2.0, "q": 1.0, "score": 0.6},
    }
    explanations = annotate_masking_corrections_with_kenn(corrections, genre="electronic", allow_llm=False)
    assert len(explanations) == 2
    for exp in explanations:
        assert exp["parameter"] == "masking de-mask correction"
        assert exp["sources"]


def test_annotate_masking_corrections_with_kenn_respects_max_items(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_masking_corrections_with_kenn

    corrections = {
        f"stem_{i}": {"frequency_hz": 500.0 + i * 100, "max_reduction_db": 2.0}
        for i in range(10)
    }
    explanations = annotate_masking_corrections_with_kenn(corrections, max_items=3, allow_llm=False)
    assert len(explanations) <= 3


def test_annotate_masking_corrections_with_kenn_empty_returns_empty():
    from audio_analysis.integration.kenn_handoff import annotate_masking_corrections_with_kenn

    assert annotate_masking_corrections_with_kenn({}) == []
    assert annotate_masking_corrections_with_kenn(None) == []


def test_annotate_masking_corrections_with_kenn_swallows_individual_failures(kenn_index_env, monkeypatch):
    import audio_analysis.integration.kenn_handoff as kh

    call_count = {"n": 0}
    real_fn = kh.explain_masking_correction

    def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated KENN failure")
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(kh, "explain_masking_correction", flaky)
    corrections = {
        "LEAD_SYNTH": {"frequency_hz": 1200.0, "max_reduction_db": 3.5},
        "PAD": {"frequency_hz": 800.0, "max_reduction_db": 2.0},
    }
    explanations = kh.annotate_masking_corrections_with_kenn(corrections, allow_llm=False)
    assert len(explanations) == 1


# ── Mono-compatibility correction ────────────────────────────────────────


def test_mono_compat_explanation_cites_real_source_and_is_fast(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import explain_mono_compat_correction

    started = time.perf_counter()
    payload = explain_mono_compat_correction(
        "DRUM_BREAK", severity="critical", correction_factor=0.35, genre="rock", allow_llm=False,
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"took {elapsed:.2f}s, expected <5s"
    source_names = _source_names(payload)
    assert "automix-mono-compat-correction.md" in source_names, (
        f"expected the mono-compat-correction note among cited sources, got {source_names}"
    )
    pdf_dir = NOTES_DIR.parent / "Training_Data_PDF"
    for name in source_names:
        assert (NOTES_DIR / name).exists() or (pdf_dir / name).exists()


def test_annotate_mono_compat_corrections_with_kenn_bulk_helper(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_mono_compat_corrections_with_kenn

    corrections = {
        "DRUM_BREAK": {"severity": "critical", "correction_factor": 0.35},
        "HI_HAT": {"severity": "warning", "correction_factor": 0.6},
    }
    explanations = annotate_mono_compat_corrections_with_kenn(corrections, genre="rock", allow_llm=False)
    assert len(explanations) == 2
    for exp in explanations:
        assert exp["parameter"] == "mono-compatibility correction"
        assert exp["sources"]


def test_annotate_mono_compat_corrections_with_kenn_respects_max_items(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_mono_compat_corrections_with_kenn

    corrections = {
        f"stem_{i}": {"severity": "warning", "correction_factor": 0.6}
        for i in range(10)
    }
    explanations = annotate_mono_compat_corrections_with_kenn(corrections, max_items=3, allow_llm=False)
    assert len(explanations) <= 3


def test_annotate_mono_compat_corrections_with_kenn_empty_returns_empty():
    from audio_analysis.integration.kenn_handoff import annotate_mono_compat_corrections_with_kenn

    assert annotate_mono_compat_corrections_with_kenn({}) == []
    assert annotate_mono_compat_corrections_with_kenn(None) == []


def test_annotate_mono_compat_corrections_with_kenn_swallows_individual_failures(kenn_index_env, monkeypatch):
    import audio_analysis.integration.kenn_handoff as kh

    call_count = {"n": 0}
    real_fn = kh.explain_mono_compat_correction

    def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated KENN failure")
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(kh, "explain_mono_compat_correction", flaky)
    corrections = {
        "DRUM_BREAK": {"severity": "critical", "correction_factor": 0.35},
        "HI_HAT": {"severity": "warning", "correction_factor": 0.6},
    }
    explanations = kh.annotate_mono_compat_corrections_with_kenn(corrections, allow_llm=False)
    assert len(explanations) == 1
