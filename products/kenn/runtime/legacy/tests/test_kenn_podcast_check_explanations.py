"""Podcast readiness check explanations -- same grounding rigor as
test_kenn_bus_eq_band_explanations.py: real retrieval against the real KENN
index (no mocking), citations that exist on disk, and no leaked
"Past reasoning" audit block. Requires a built KENN index; skips gracefully
if none exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
HUM_NOTE = NOTES_DIR / "mains-hum-removal-for-dialogue.md"
LOUDNESS_NOTE = NOTES_DIR / "podcast-delivery-loudness-targets.md"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"))
from kenn.retrieval.index_store import active_artifact_path  # noqa: E402

INDEX_CHUNKS = active_artifact_path("chunks.jsonl")

pytestmark = pytest.mark.skipif(
    not INDEX_CHUNKS.exists(),
    reason="KENN index not built — run studio/kenn/kenn/retrieval/build_index.py first.",
)


def test_new_podcast_notes_exist_on_disk():
    assert HUM_NOTE.exists()
    assert LOUDNESS_NOTE.exists()


@pytest.fixture(scope="module")
def kenn_index_env(tmp_path_factory):
    import os
    state_dir = tmp_path_factory.mktemp("kenn-podcast-check-explain")
    os.environ["KENN_CHATS_DIR"] = str(state_dir)
    os.environ["KENN_DB_PATH"] = str(state_dir / "kenn.db")
    os.environ["KENN_SESSION_FILE"] = str(state_dir / "session.json")
    yield


def test_hum_check_cites_the_hum_note_and_has_no_leaked_audit_block(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import explain_podcast_check

    payload = explain_podcast_check(
        "Electrical hum", status="fail", measured="60 Hz tone +22 dB",
        target="no mains tone",
        fix="A 60 Hz mains hum is present — apply a narrow notch at 60 Hz.",
        allow_llm=False,
    )
    sources = {s.get("source") if isinstance(s, dict) else str(s) for s in (payload.get("sources") or [])}
    assert sources, "expected at least one cited source"
    assert "mains-hum-removal-for-dialogue.md" in sources
    assert "Past reasoning on this topic" not in payload.get("answer", "")


def test_loudness_check_cites_the_loudness_note(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import explain_podcast_check

    payload = explain_podcast_check(
        "Integrated loudness", status="fail", measured="-23.0 LUFS",
        target="-16 ±1 LUFS",
        fix="Normalise to -16 LUFS (7.0 LU too quiet) for Apple Podcasts (stereo).",
        allow_llm=False,
    )
    sources = {s.get("source") if isinstance(s, dict) else str(s) for s in (payload.get("sources") or [])}
    assert "podcast-delivery-loudness-targets.md" in sources


def test_annotate_podcast_checks_only_explains_non_ok_checks(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_podcast_checks_with_kenn

    checks = [
        {"id": "loudness", "label": "Integrated loudness", "status": "fail",
         "measured": "-23.0 LUFS", "target": "-16 ±1 LUFS", "fix": "Normalise to -16 LUFS."},
        {"id": "true_peak", "label": "True peak", "status": "ok",
         "measured": "-1.3 dBTP", "target": "≤ -1 dBTP", "fix": "True peak is within ceiling."},
        {"id": "sibilance", "label": "Sibilance", "status": "warn",
         "measured": "14% energy 6–8 kHz", "target": "< 9%", "fix": "Add a de-esser around 6-8 kHz."},
    ]
    explanations = annotate_podcast_checks_with_kenn(checks, allow_llm=False)
    labels = {e["parameter"] for e in explanations}
    assert labels == {"Integrated loudness", "Sibilance"}, "an 'ok' check must not be explained"
    for exp in explanations:
        assert exp["sources"]
        assert "Past reasoning on this topic" not in exp["answer"]


def test_annotate_podcast_checks_ranks_fail_before_warn(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_podcast_checks_with_kenn

    checks = [
        {"id": "dead_air", "label": "Dead air", "status": "warn",
         "measured": "65% silence", "target": "< 55%", "fix": "Tighten the edit."},
        {"id": "hum", "label": "Electrical hum", "status": "fail",
         "measured": "60 Hz tone +22 dB", "target": "no mains tone", "fix": "Apply a notch at 60 Hz."},
    ]
    explanations = annotate_podcast_checks_with_kenn(checks, allow_llm=False)
    assert [e["parameter"] for e in explanations] == ["Electrical hum", "Dead air"]


def test_annotate_podcast_checks_respects_max_items(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_podcast_checks_with_kenn

    checks = [
        {"id": f"c{i}", "label": f"Check {i}", "status": "warn", "measured": "x", "target": "y", "fix": "z"}
        for i in range(10)
    ]
    explanations = annotate_podcast_checks_with_kenn(checks, max_items=3, allow_llm=False)
    assert len(explanations) <= 3
