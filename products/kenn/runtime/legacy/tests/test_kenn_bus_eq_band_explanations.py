"""Stage 9.6 — KENN master bus EQ band explanation tests.

Same grounding rigor as test_kenn_dynamic_eq_explanations.py (Stage C):
verifies real retrieval against the real KENN index (no mocking), that
explanations cite a real Training_Data_Notes source, and respond quickly.
Requires a built KENN index with studio/kenn/kenn/Training_Data_Notes/
automix-reference-tonal-balance-correction.md indexed — skips gracefully if
no index exists.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
REFERENCE_EQ_NOTE = NOTES_DIR / "automix-reference-tonal-balance-correction.md"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"))
from kenn.retrieval.index_store import active_artifact_path  # noqa: E402

INDEX_CHUNKS = active_artifact_path("chunks.jsonl")

pytestmark = pytest.mark.skipif(
    not INDEX_CHUNKS.exists(),
    reason="KENN index not built — run `KENN_MAX_CONTRADICTIONS=<n> python studio/kenn/kenn/retrieval/build_index.py` first.",
)


def test_reference_eq_note_exists_and_is_accurate():
    """Sanity check the note this whole test file depends on actually exists
    and describes the real, validated finding (not stale/invented numbers)."""
    assert REFERENCE_EQ_NOTE.exists()
    text = REFERENCE_EQ_NOTE.read_text(encoding="utf-8")
    assert "300 Hz" in text
    assert "+4.0 dB" in text
    assert "reference_track_comparison.py" in text


@pytest.fixture(scope="module")
def kenn_index_env(tmp_path_factory):
    import os
    state_dir = tmp_path_factory.mktemp("kenn-bus-eq-explain")
    os.environ["KENN_CHATS_DIR"] = str(state_dir)
    os.environ["KENN_DB_PATH"] = str(state_dir / "kenn.db")
    os.environ["KENN_SESSION_FILE"] = str(state_dir / "session.json")
    yield


BUS_EQ_CASES = [
    {
        "frequency_hz": 300.0,
        "gain_db": 4.0,
        "band_type": "lowshelf",
        "reason": "Validated low-shelf (v2), applied unchanged to test generalization across songs",
        "genre": "electronic",
    },
    {
        "frequency_hz": 100.0,
        "gain_db": 3.5,
        "band_type": "peaking",
        "reason": "Reference EQ Match: bass adjusted by +3.5 dB to match reference track profile.",
        "genre": None,
    },
]


@pytest.mark.parametrize("case", BUS_EQ_CASES, ids=[f"{c['frequency_hz']}hz-{c['genre']}" for c in BUS_EQ_CASES])
def test_bus_eq_band_explanation_cites_real_source_and_is_fast(kenn_index_env, case):
    from audio_analysis.integration.kenn_handoff import explain_bus_eq_band

    started = time.perf_counter()
    payload = explain_bus_eq_band(
        case["frequency_hz"],
        gain_db=case["gain_db"],
        band_type=case["band_type"],
        reason=case["reason"],
        genre=case["genre"],
        allow_llm=False,
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"took {elapsed:.2f}s, expected <5s"
    sources = payload.get("sources") or []
    assert sources, "expected at least one cited source"
    source_names = {s.get("source") if isinstance(s, dict) else str(s) for s in sources}
    pdf_dir = NOTES_DIR.parent / "Training_Data_PDF"
    for name in source_names:
        assert (NOTES_DIR / name).exists() or (pdf_dir / name).exists(), (
            f"cited source {name} does not exist on disk (checked notes and PDF directories)"
        )


def test_annotate_bus_eq_bands_with_kenn_bulk_helper(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_bus_eq_bands_with_kenn

    bands = [
        {
            "type": "lowshelf",
            "frequency": 300.0,
            "gain_db": 4.0,
            "q": 0.707,
            "reason": "Validated low-shelf (v2), applied unchanged to test generalization across songs",
        },
        {
            "type": "peaking",
            "frequency": 100.0,
            "gain_db": 3.5,
            "q": 1.0,
            "reason": "Reference EQ Match: bass adjusted by +3.5 dB to match reference track profile.",
        },
    ]
    explanations = annotate_bus_eq_bands_with_kenn(bands, genre="electronic", allow_llm=False)
    assert len(explanations) == 2
    for exp in explanations:
        assert exp["parameter"] == "master bus EQ band"
        assert exp["stem_name"] == "master bus"
        assert exp["sources"]


def test_annotate_bus_eq_bands_with_kenn_skips_unreasoned_bands(kenn_index_env):
    """A default bus EQ band with no stated reason has nothing real to
    ground a question in and must be skipped, not explained with a guess."""
    from audio_analysis.integration.kenn_handoff import annotate_bus_eq_bands_with_kenn

    bands = [
        {"type": "highshelf", "frequency": 10000.0, "gain_db": 1.0, "q": 0.707},  # no reason
        {
            "type": "lowshelf",
            "frequency": 300.0,
            "gain_db": 4.0,
            "reason": "Validated low-shelf (v2), applied unchanged to test generalization across songs",
        },
    ]
    explanations = annotate_bus_eq_bands_with_kenn(bands, allow_llm=False)
    assert len(explanations) == 1
    assert explanations[0]["instrument"] == "300 Hz"


def test_annotate_bus_eq_bands_with_kenn_respects_max_items(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_bus_eq_bands_with_kenn

    bands = [
        {"type": "peaking", "frequency": 200.0 + i * 100, "gain_db": 1.0, "reason": f"test reason {i}"}
        for i in range(10)
    ]
    explanations = annotate_bus_eq_bands_with_kenn(bands, max_items=3, allow_llm=False)
    assert len(explanations) <= 3


def test_annotate_bus_eq_bands_with_kenn_empty_bands_returns_empty():
    from audio_analysis.integration.kenn_handoff import annotate_bus_eq_bands_with_kenn

    assert annotate_bus_eq_bands_with_kenn([]) == []
    assert annotate_bus_eq_bands_with_kenn(None) == []


def test_annotate_bus_eq_bands_with_kenn_swallows_individual_failures(kenn_index_env, monkeypatch):
    """A KENN/index problem on one band must not block the others — same
    best-effort guarantee mix_delivery.py relies on."""
    import audio_analysis.integration.kenn_handoff as kh

    call_count = {"n": 0}
    real_fn = kh.explain_bus_eq_band

    def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated KENN failure")
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(kh, "explain_bus_eq_band", flaky)
    bands = [
        {"type": "lowshelf", "frequency": 300.0, "gain_db": 4.0, "reason": "reason one"},
        {"type": "peaking", "frequency": 100.0, "gain_db": 3.5, "reason": "reason two"},
    ]
    explanations = kh.annotate_bus_eq_bands_with_kenn(bands, allow_llm=False)
    assert len(explanations) == 1  # first one failed, second succeeded
