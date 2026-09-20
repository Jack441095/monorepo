"""Tests for business/agents/Shared/client_history.py's cross-domain timeline.

docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md flagged that asking Thursday about
a client couldn't surface their mix review status — the timeline builder only
ever touched business tables (projects, invoices, sessions, drafts,
followups, expenses, leads), never mix_review/audio_analysis data.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "business" / "agents"))

from Shared.client_history import _make_timeline_events, client_summary, client_timeline  # noqa: E402


def _no_records(_table: str) -> list[dict]:
    return []


def test_timeline_includes_mix_reviews_matched_by_title() -> None:
    reviews = [
        {
            "id": "abc123",
            "title": "Jordan Smith - Final Mix v3",
            "created_at": "2026-07-05",
            "status": "completed",
            "flags": ["low-end mud", "harsh top end"],
        },
        {
            "id": "def456",
            "title": "Unrelated Track",
            "created_at": "2026-07-01",
            "status": "completed",
            "flags": [],
        },
    ]
    events = _make_timeline_events(
        "Jordan Smith", _no_records, list_mix_reviews=lambda: reviews
    )
    mix_events = [e for e in events if e["type"] == "mix_review"]
    assert len(mix_events) == 1
    assert "Jordan Smith - Final Mix v3" in mix_events[0]["summary"]
    assert "2 flag(s)" in mix_events[0]["summary"]


def test_timeline_excludes_reviews_that_dont_match_client_name() -> None:
    reviews = [{"id": "x", "title": "Someone Else Track", "created_at": "2026-07-01", "status": "completed"}]
    events = _make_timeline_events("Jordan Smith", _no_records, list_mix_reviews=lambda: reviews)
    assert not [e for e in events if e["type"] == "mix_review"]


def test_timeline_degrades_gracefully_when_mix_review_source_fails() -> None:
    def broken_source() -> list[dict]:
        raise RuntimeError("audio_analysis import failed")

    # Must not raise — the rest of the timeline still has to work even if
    # mix review data is unavailable (e.g. torch import failure).
    events = _make_timeline_events("Jordan Smith", _no_records, list_mix_reviews=broken_source)
    assert events == []


def test_client_timeline_renders_mix_review_line() -> None:
    reviews = [
        {"id": "1", "title": "Jordan Smith - Radio Edit", "created_at": "2026-07-05", "status": "completed", "flags": ["mud"]}
    ]
    output = client_timeline(_no_records, "Jordan Smith", list_mix_reviews=lambda: reviews)
    assert "Mix review" in output
    assert "Jordan Smith - Radio Edit" in output


def test_client_summary_surfaces_latest_mix_review() -> None:
    reviews = [
        {"id": "1", "title": "Jordan Smith - v2", "created_at": "2026-07-05", "status": "completed", "flags": ["mud"]},
        {"id": "2", "title": "Jordan Smith - v1", "created_at": "2026-07-01", "status": "completed", "flags": []},
    ]
    output = client_summary(_no_records, "Jordan Smith", list_mix_reviews=lambda: reviews)
    assert "Latest mix review:" in output
    assert "Jordan Smith - v2" in output


def test_client_summary_omits_mix_review_line_when_none_exist() -> None:
    output = client_summary(_no_records, "Jordan Smith", list_mix_reviews=lambda: [])
    assert "Latest mix review:" not in output


# ─── AutoMix cross-domain join (audit fix Stage 3, 2026-07-08) ────────────
# docs/AUDIT_FIX_EXECUTION_PLAN_2026-07-08.md: once AutoMix was wired into
# Thursday (Stage 2), the natural follow-on is that asking about a client can
# surface their AutoMix job status too. automix_jobs has no client column —
# it's matched via the project(s) already confirmed to belong to this client.


def _projects_for(client: str, project_ids: list[str]):
    def _list(table: str) -> list[dict]:
        if table == "projects":
            return [{"id": pid, "client": client, "project": "Test", "service": "mixing"} for pid in project_ids]
        return []
    return _list


def test_timeline_includes_automix_jobs_matched_via_client_project() -> None:
    list_records = _projects_for("Jordan Smith", ["proj-1"])
    jobs = [
        {"id": "job-1", "project_id": "proj-1", "genre": "pop", "status": "complete", "created_at": "2026-07-05"},
        {"id": "job-2", "project_id": "other-proj", "genre": "rock", "status": "complete", "created_at": "2026-07-01"},
    ]
    events = _make_timeline_events("Jordan Smith", list_records, list_automix_jobs=lambda: jobs)
    automix_events = [e for e in events if e["type"] == "automix_job"]
    assert len(automix_events) == 1
    assert "pop" in automix_events[0]["summary"]
    assert "complete" in automix_events[0]["summary"]


def test_timeline_excludes_automix_jobs_for_other_clients_projects() -> None:
    list_records = _projects_for("Jordan Smith", ["proj-1"])
    jobs = [{"id": "job-2", "project_id": "unrelated-proj", "genre": "rock", "status": "complete", "created_at": "2026-07-01"}]
    events = _make_timeline_events("Jordan Smith", list_records, list_automix_jobs=lambda: jobs)
    assert not [e for e in events if e["type"] == "automix_job"]


def test_timeline_degrades_gracefully_when_automix_source_fails() -> None:
    def broken_source() -> list[dict]:
        raise RuntimeError("automix_jobs import failed")

    events = _make_timeline_events("Jordan Smith", _no_records, list_automix_jobs=broken_source)
    assert events == []


def test_client_summary_surfaces_latest_automix_job() -> None:
    list_records = _projects_for("Jordan Smith", ["proj-1"])
    jobs = [
        {"id": "job-1", "project_id": "proj-1", "genre": "pop", "status": "complete", "created_at": "2026-07-05"},
        {"id": "job-2", "project_id": "proj-1", "genre": "rock", "status": "queued", "created_at": "2026-07-01"},
    ]
    output = client_summary(list_records, "Jordan Smith", list_automix_jobs=lambda: jobs)
    assert "Latest AutoMix job:" in output
    assert "pop" in output


def test_client_summary_omits_automix_line_when_none_exist() -> None:
    output = client_summary(_no_records, "Jordan Smith", list_automix_jobs=lambda: [])
    assert "Latest AutoMix job:" not in output
