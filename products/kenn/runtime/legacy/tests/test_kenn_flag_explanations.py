"""Stage D — KENN proactive Mix Review flag explanation tests.

Same grounding rigor as test_kenn_dynamic_eq_explanations.py (Stage C):
verifies real retrieval against the real KENN index (no mocking) for
``annotate_flags_with_kenn`` (the bulk/report-injection helper built on top
of the existing per-flag ``explain_mix_review_flag`` from Stage 9), plus the
wiring of that helper into Mix Review's ``refresh_closed_loop_payloads``.
Requires a built KENN index — skips gracefully if no index exists.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn" / "Training_Data_Notes"

# The real index lives under a version-promotion scheme (data/index/CURRENT
# points at data/index/versions/<version>/chunks.jsonl), not a flat
# data/index/chunks.jsonl — resolve it the same way retrieval.py does rather
# than a hardcoded flat path, which would silently always skip these tests
# once a version has actually been promoted (the same stale-flat-path bug
# already fixed in test_kenn_automix_parameter_explanations.py and
# test_kenn_dynamic_eq_explanations.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"))
from kenn.retrieval.index_store import active_artifact_path  # noqa: E402

INDEX_CHUNKS = active_artifact_path("chunks.jsonl")

pytestmark = pytest.mark.skipif(
    not INDEX_CHUNKS.exists(),
    reason="KENN index not built — run `KENN_MAX_CONTRADICTIONS=<n> python studio/kenn/kenn/retrieval/build_index.py` first.",
)


@pytest.fixture(scope="module")
def kenn_index_env(tmp_path_factory):
    import os
    state_dir = tmp_path_factory.mktemp("kenn-flag-explain")
    os.environ["KENN_CHATS_DIR"] = str(state_dir)
    os.environ["KENN_DB_PATH"] = str(state_dir / "kenn.db")
    os.environ["KENN_SESSION_FILE"] = str(state_dir / "session.json")
    yield


FLAG_CASES = [
    {"label": "true peak clipping", "detail": "True peak exceeded -1 dBFS ceiling", "severity": "high"},
    {"label": "mono compatibility", "detail": "Correlation dropped below 0 when summed to mono", "severity": "medium"},
]


@pytest.mark.parametrize("case", FLAG_CASES, ids=[c["label"] for c in FLAG_CASES])
def test_flag_explanation_cites_real_source_and_is_fast(kenn_index_env, case):
    from audio_analysis.integration.kenn_handoff import explain_mix_review_flag

    started = time.perf_counter()
    payload = explain_mix_review_flag(
        case["label"], detail=case["detail"], severity=case["severity"], allow_llm=False
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"took {elapsed:.2f}s, expected <5s"
    answer = payload.get("answer", "")
    assert answer, "KENN returned an empty answer"

    sources = payload.get("sources") or []
    if payload.get("weak_match"):
        assert not sources
        return
    real_sources = [s for s in sources if isinstance(s, dict) and (NOTES_DIR / s.get("source", "")).exists()]
    assert real_sources, f"no real cited note file among sources: {sources}"


def test_annotate_flags_with_kenn_bulk_helper(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_flags_with_kenn

    flags = [
        {"label": "true peak clipping", "detail": "True peak exceeded -1 dBFS ceiling", "severity": "high"},
        {"label": "mono compatibility", "detail": "Correlation dropped below 0 when summed to mono", "severity": "medium"},
    ]
    explanations = annotate_flags_with_kenn(flags, allow_llm=False)
    assert len(explanations) == 2
    for exp in explanations:
        assert exp["flag"]
        assert exp["sources"]


def test_annotate_flags_with_kenn_orders_by_severity(kenn_index_env):
    """Highest-severity flags must be explained first when bounded by
    max_items — a report shouldn't burn its KENN-call budget on a low-severity
    flag while a high-severity one goes unexplained."""
    from audio_analysis.integration.kenn_handoff import annotate_flags_with_kenn

    flags = [
        {"label": "low priority tonal note", "detail": "minor tonal imbalance", "severity": "low"},
        {"label": "true peak clipping", "detail": "True peak exceeded -1 dBFS ceiling", "severity": "high"},
        {"label": "mono compatibility", "detail": "Correlation dropped below 0 when summed to mono", "severity": "medium"},
    ]
    explanations = annotate_flags_with_kenn(flags, max_items=1, allow_llm=False)
    assert len(explanations) == 1
    assert explanations[0]["flag"] == "true peak clipping"


def test_annotate_flags_with_kenn_respects_max_items(kenn_index_env):
    from audio_analysis.integration.kenn_handoff import annotate_flags_with_kenn

    flags = [
        {"label": f"flag {i}", "detail": "some detail", "severity": "low"}
        for i in range(10)
    ]
    explanations = annotate_flags_with_kenn(flags, max_items=3, allow_llm=False)
    assert len(explanations) <= 3


def test_annotate_flags_with_kenn_empty_flags_returns_empty():
    from audio_analysis.integration.kenn_handoff import annotate_flags_with_kenn

    assert annotate_flags_with_kenn([]) == []
    assert annotate_flags_with_kenn(None) == []


def test_annotate_flags_with_kenn_swallows_individual_failures(kenn_index_env, monkeypatch):
    """A KENN/index problem on one flag must not block the others — same
    best-effort guarantee mix_delivery.py and annotate_dynamic_eq_with_kenn
    rely on."""
    import audio_analysis.integration.kenn_handoff as kh

    call_count = {"n": 0}
    real_fn = kh.explain_mix_review_flag

    def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated KENN failure")
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(kh, "explain_mix_review_flag", flaky)
    flags = [
        {"label": "true peak clipping", "detail": "True peak exceeded -1 dBFS ceiling", "severity": "high"},
        {"label": "mono compatibility", "detail": "Correlation dropped below 0 when summed to mono", "severity": "medium"},
    ]
    explanations = kh.annotate_flags_with_kenn(flags, allow_llm=False)
    assert len(explanations) == 1  # first (highest severity) one failed, second succeeded


def test_refresh_closed_loop_payloads_injects_kenn_explanations(kenn_index_env, monkeypatch):
    """Wiring test: refresh_closed_loop_payloads (Mix Review's report
    refresh entry point, used by both the API and the batch scanner) must
    merge annotate_flags_with_kenn's output into report['kenn_explanations'],
    the same field mix_delivery.py's package_mixdown_delivery already uses
    for AutoMix parameters/dynamic EQ, and which report_rendering.py already
    knows how to render for either shape."""
    import audio_analysis.mix_review.mix_review as mix_review

    # Stub out the other refresh_closed_loop_payloads side effects so this
    # test only exercises the KENN flag wiring, not the whole Mix Review
    # report-building pipeline.
    monkeypatch.setattr(mix_review, "ableton_repair_chain_export", lambda report: {})
    monkeypatch.setattr(mix_review, "closed_loop_action_plan", lambda report: {})
    monkeypatch.setattr(mix_review, "next_revision_plan", lambda report: {})
    monkeypatch.setattr(mix_review, "build_session_report", lambda report: {})
    monkeypatch.setattr(mix_review, "kenn_handoff", lambda report: {})

    report = {
        "flags": [
            {"label": "true peak clipping", "detail": "True peak exceeded -1 dBFS ceiling", "severity": "high"},
        ]
    }
    result = mix_review.refresh_closed_loop_payloads(report)

    assert "kenn_explanations" in result
    assert result["kenn_explanations"]
    assert result["kenn_explanations"][0]["flag"] == "true peak clipping"


def test_refresh_closed_loop_payloads_best_effort_on_kenn_failure(monkeypatch):
    """A KENN failure during flag annotation must never block the rest of
    refresh_closed_loop_payloads (mirrors mix_delivery.py's contract)."""
    import audio_analysis.mix_review.mix_review as mix_review

    monkeypatch.setattr(mix_review, "ableton_repair_chain_export", lambda report: {})
    monkeypatch.setattr(mix_review, "closed_loop_action_plan", lambda report: {})
    monkeypatch.setattr(mix_review, "next_revision_plan", lambda report: {})
    monkeypatch.setattr(mix_review, "build_session_report", lambda report: {})
    monkeypatch.setattr(mix_review, "kenn_handoff", lambda report: {})

    import audio_analysis.integration.kenn_handoff as kh

    def boom(*args, **kwargs):
        raise RuntimeError("simulated KENN outage")

    monkeypatch.setattr(kh, "annotate_flags_with_kenn", boom)

    report = {
        "flags": [
            {"label": "true peak clipping", "detail": "True peak exceeded -1 dBFS ceiling", "severity": "high"},
        ]
    }
    result = mix_review.refresh_closed_loop_payloads(report)

    assert "kenn_explanations" not in result
    assert result["next_revision_plan"] == {}


def test_refresh_closed_loop_payloads_no_flags_no_kenn_call(monkeypatch):
    """No flags means nothing to explain — must not attempt a KENN call at
    all (bounded/fast per Stage D's contract)."""
    import audio_analysis.mix_review.mix_review as mix_review

    monkeypatch.setattr(mix_review, "ableton_repair_chain_export", lambda report: {})
    monkeypatch.setattr(mix_review, "closed_loop_action_plan", lambda report: {})
    monkeypatch.setattr(mix_review, "next_revision_plan", lambda report: {})
    monkeypatch.setattr(mix_review, "build_session_report", lambda report: {})
    monkeypatch.setattr(mix_review, "kenn_handoff", lambda report: {})

    report = {"flags": []}
    result = mix_review.refresh_closed_loop_payloads(report)

    assert "kenn_explanations" not in result
