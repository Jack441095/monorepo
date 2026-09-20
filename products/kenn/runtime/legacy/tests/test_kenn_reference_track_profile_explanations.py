"""Stage 9.8 — KENN reference track profile explanation tests.

Unlike the other kenn_handoff.py explain/annotate pairs, this one grounds a
question about a *reference track's own* measured tonal-balance profile
(scripts/eval/analyze_reference_tracks.py), not an AutoMix render decision.
Same grounding rigor as the other Stage 9.x test files: verifies real
retrieval against the real KENN index (no mocking), that explanations cite a
real Training_Data_Notes source, and respond quickly. Requires a built KENN
index with reference-track-profile-analysis.md indexed — skips gracefully if
no index exists.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
PROFILE_NOTE = NOTES_DIR / "reference-track-profile-analysis.md"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"))
from kenn.retrieval.index_store import active_artifact_path  # noqa: E402

INDEX_CHUNKS = active_artifact_path("chunks.jsonl")

pytestmark = pytest.mark.skipif(
    not INDEX_CHUNKS.exists(),
    reason="KENN index not built — run `KENN_MAX_CONTRADICTIONS=<n> python studio/kenn/kenn/retrieval/build_index.py` first.",
)


def test_reference_track_profile_note_exists_and_is_accurate():
    """Sanity check the note this whole test file depends on describes the
    real, measured values from analyze_reference_tracks.py (not invented)."""
    assert PROFILE_NOTE.exists()
    text = PROFILE_NOTE.read_text(encoding="utf-8")
    assert "1.05" in text  # Stromae/Pomme's measured ratio
    assert "analyze_reference_tracks.py" in text
    assert "acapella" in text.lower()


@pytest.fixture(scope="module")
def kenn_index_env(tmp_path_factory):
    import os
    state_dir = tmp_path_factory.mktemp("kenn-reference-track-profile-explain")
    os.environ["KENN_CHATS_DIR"] = str(state_dir)
    os.environ["KENN_DB_PATH"] = str(state_dir / "kenn.db")
    os.environ["KENN_SESSION_FILE"] = str(state_dir / "session.json")
    yield


def _source_names(payload: dict) -> set[str]:
    sources = payload.get("sources") or []
    return {s.get("source") if isinstance(s, dict) else str(s) for s in sources}


def test_reference_track_profile_explanation_cites_real_source_and_is_fast(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import explain_reference_track_profile

    started = time.perf_counter()
    payload = explain_reference_track_profile(
        "Stromae, Pomme - Ma Meilleure Ennemie",
        high_to_low_ratio=1.05,
        bands7={"bass": 0.181, "presence": 0.194, "sub": 0.02, "low_mids": 0.15},
        allow_llm=False,
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"took {elapsed:.2f}s, expected <5s"
    source_names = _source_names(payload)
    assert source_names, "expected at least one cited source"
    pdf_dir = NOTES_DIR.parent / "Training_Data_PDF"
    for name in source_names:
        assert (NOTES_DIR / name).exists() or (pdf_dir / name).exists()


def test_reference_track_profile_explanation_flags_acapella_outlier(kenn_index_env):
    """The acapella outlier (070 Shake, ratio 4.63) should still retrieve
    successfully -- it's a real measured value, just from a different kind
    of file, not something to guess past."""
    from audio_analysis.integration.kenn_handoff import explain_reference_track_profile

    payload = explain_reference_track_profile(
        "070 Shake - Cocoon (Studio Acapella)", high_to_low_ratio=4.63, allow_llm=False,
    )
    assert payload.get("reference_track_high_to_low_ratio") == 4.63
    assert _source_names(payload)


def test_annotate_reference_track_profiles_with_kenn_bulk_helper(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_reference_track_profiles_with_kenn

    profiles = {
        "stromae_pomme.mp3": {"high_to_low_ratio": 1.05, "bands7": {"bass": 0.181}},
        "weeknd_remix.mp3": {"high_to_low_ratio": 1.28, "bands7": {"bass": 0.143}},
    }
    explanations = annotate_reference_track_profiles_with_kenn(profiles, allow_llm=False)
    assert len(explanations) == 2
    for exp in explanations:
        assert exp["parameter"] == "reference track profile"
        assert exp["sources"]


def test_annotate_reference_track_profiles_with_kenn_respects_max_items(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_reference_track_profiles_with_kenn

    profiles = {f"track_{i}.mp3": {"high_to_low_ratio": 1.0 + i * 0.1} for i in range(10)}
    explanations = annotate_reference_track_profiles_with_kenn(profiles, max_items=3, allow_llm=False)
    assert len(explanations) <= 3


def test_annotate_reference_track_profiles_with_kenn_empty_returns_empty():
    from audio_analysis.integration.kenn_handoff import annotate_reference_track_profiles_with_kenn

    assert annotate_reference_track_profiles_with_kenn({}) == []
    assert annotate_reference_track_profiles_with_kenn(None) == []


def test_annotate_reference_track_profiles_with_kenn_swallows_individual_failures(kenn_index_env, monkeypatch):
    import audio_analysis.integration.kenn_handoff as kh

    call_count = {"n": 0}
    real_fn = kh.explain_reference_track_profile

    def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated KENN failure")
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(kh, "explain_reference_track_profile", flaky)
    profiles = {
        "stromae_pomme.mp3": {"high_to_low_ratio": 1.05},
        "weeknd_remix.mp3": {"high_to_low_ratio": 1.28},
    }
    explanations = kh.annotate_reference_track_profiles_with_kenn(profiles, allow_llm=False)
    assert len(explanations) == 1
