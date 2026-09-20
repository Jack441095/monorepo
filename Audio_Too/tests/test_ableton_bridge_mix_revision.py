"""Tests for the KENN chat -> AutoMix revision bridge in ableton_bridge.ask().

Mirrors the "mock automix_jobs.queue_revision, don't re-exercise the real
job queue" boundary-mocking pattern used elsewhere for the AudioGen chat
branch -- automix_jobs' own correctness (idempotency, feedback_history
accumulation, NoCompletedMix) is covered by its own tests; this file
covers the bridging logic: project resolution (explicit vs. remembered),
response shaping, and error handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

import ableton_bridge  # noqa: E402
import automix_jobs  # noqa: E402
import db  # noqa: E402
from kenn.core import session_memory  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_kenn_and_business_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")
    yield


def test_ask_does_not_trigger_revision_for_a_question(monkeypatch):
    calls = []
    monkeypatch.setattr(automix_jobs, "queue_revision", lambda req: calls.append(req) or (200, {"ok": True}))
    monkeypatch.setattr(
        ableton_bridge, "answer_payload",
        lambda *a, **k: {"question": "x", "answer": "normal Q&A path"},
    )

    result = ableton_bridge.ask("why is my vocal too quiet?", session_id="s1")

    assert calls == []
    assert result["answer"] == "normal Q&A path"


def test_ask_queues_a_real_revision_with_explicit_project_id(monkeypatch):
    captured = {}

    def fake_queue_revision(request):
        captured["project_id"] = request.project_id
        captured["feedback"] = request.feedback
        return 200, {"ok": True, "job_id": "job-abc12345", "status": "queued"}

    monkeypatch.setattr(automix_jobs, "queue_revision", fake_queue_revision)

    result = ableton_bridge.ask("make the vocals warmer", session_id="s1", project_id="proj-1")

    assert captured["project_id"] == "proj-1"
    assert captured["feedback"] == "make the vocals warmer"
    assert result["found"] is True
    assert result["intent"] == "revise_mix"
    assert result["automix_revision"]["job_id"] == "job-abc12345"
    assert "re-rendering" in result["answer"].lower()


def test_ask_records_the_revision_request_in_project_history(monkeypatch):
    import db
    import song_projects

    db.init_db()
    monkeypatch.setattr(
        automix_jobs, "queue_revision",
        lambda req: (200, {"ok": True, "job_id": "job-1", "status": "queued"}),
    )

    ableton_bridge.ask("make the vocals warmer", session_id="s1", project_id="proj-1")

    history = song_projects.get_revision_history("proj-1")
    assert len(history) == 1
    assert history[0]["feedback_text"] == "make the vocals warmer"


def test_ask_returns_the_revision_history_id_in_the_payload(monkeypatch):
    # §13.6.2: the listening-checkpoint accept/reject reply needs this id
    # to feed back into project_revision_history's outcome column.
    import db
    import song_projects

    db.init_db()
    monkeypatch.setattr(
        automix_jobs, "queue_revision",
        lambda req: (200, {"ok": True, "job_id": "job-1", "status": "queued"}),
    )

    result = ableton_bridge.ask("make the vocals warmer", session_id="s1", project_id="proj-1")

    history = song_projects.get_revision_history("proj-1")
    assert result["revision_history_id"] == history[0]["id"]


def test_ask_remembers_the_queued_job_as_pending_for_proactive_completion(monkeypatch):
    # D2.3: pollAutomixCompletions() needs to know which jobs this
    # session is waiting to hear back about.
    from kenn.core import session_memory

    monkeypatch.setattr(
        automix_jobs, "queue_revision",
        lambda req: (200, {"ok": True, "job_id": "job-xyz", "status": "queued"}),
    )

    ableton_bridge.ask("make the vocals warmer", session_id="s1", project_id="proj-1")

    assert session_memory.get_pending_automix_jobs("s1") == ["job-xyz"]


def test_ask_remembers_project_id_for_a_later_turn_without_it(monkeypatch):
    monkeypatch.setattr(
        automix_jobs, "queue_revision",
        lambda req: (200, {"ok": True, "job_id": "job-1", "status": "queued"}),
    )

    first = ableton_bridge.ask("make it brighter", session_id="s1", project_id="proj-9")
    assert first["found"] is True

    captured = {}

    def fake_second(request):
        captured["project_id"] = request.project_id
        return 200, {"ok": True, "job_id": "job-2", "status": "queued"}

    monkeypatch.setattr(automix_jobs, "queue_revision", fake_second)
    second = ableton_bridge.ask("add a bit more reverb on the vocal", session_id="s1")

    assert captured["project_id"] == "proj-9"
    assert second["found"] is True


def test_ask_asks_which_project_when_none_is_known(monkeypatch):
    calls = []
    monkeypatch.setattr(automix_jobs, "queue_revision", lambda req: calls.append(req))

    result = ableton_bridge.ask("make it warmer", session_id="brand-new-session")

    assert calls == []
    assert result["found"] is False
    assert "don't know which project" in result["answer"]


def test_ask_handles_no_completed_mix_gracefully(monkeypatch):
    def raise_no_completed_mix(request):
        raise automix_jobs.NoCompletedMix("No previous completed mix found to revise.")

    monkeypatch.setattr(automix_jobs, "queue_revision", raise_no_completed_mix)

    result = ableton_bridge.ask("make it brighter", session_id="s1", project_id="proj-1")

    assert result["found"] is False
    assert "no completed mix" in result["answer"].lower()


def test_ask_surfaces_validation_errors_without_crashing(monkeypatch):
    def raise_validation_error(request):
        from api_schemas import SchemaValidationError
        raise SchemaValidationError("project_id", "Invalid project ID.")

    monkeypatch.setattr(automix_jobs, "queue_revision", raise_validation_error)

    result = ableton_bridge.ask("make it brighter", session_id="s1", project_id="!!!bad!!!")

    assert result["found"] is False
    assert "couldn't queue" in result["answer"].lower()


# --- dynamic revision explanation --------------------------------------------
# Replaces the old static "This runs in the background..." filler with a real
# description of the DSP change parse_mix_intent() extracted -- the same
# parser apply_revision_feedback() (System A) calls internally when the job
# is actually claimed, so the explanation matches what will really happen.


def test_ask_explains_the_actual_dsp_change_for_brightness(monkeypatch):
    monkeypatch.setattr(
        automix_jobs, "queue_revision",
        lambda req: (200, {"ok": True, "job_id": "job-1", "status": "queued"}),
    )

    result = ableton_bridge.ask("boost the master bus brightness", session_id="s1", project_id="proj-1")

    assert result["found"] is True
    assert "brightness highshelf eq on the master bus" in result["answer"].lower()
    assert "+1.5 db" in result["answer"].lower()


def test_ask_explains_a_quieter_vocal_request(monkeypatch):
    monkeypatch.setattr(
        automix_jobs, "queue_revision",
        lambda req: (200, {"ok": True, "job_id": "job-2", "status": "queued"}),
    )

    result = ableton_bridge.ask("make the vocals quieter", session_id="s1", project_id="proj-1")

    assert result["found"] is True
    lowered = result["answer"].lower()
    assert "cut the overall level of vocal" in lowered
    assert "db adjustment" in lowered


def test_ask_gives_an_honest_fallback_when_intent_is_unrecognized(monkeypatch):
    """A message the deterministic parser genuinely can't extract a
    parameter from must not claim a specific DSP change is happening."""
    monkeypatch.setattr(
        automix_jobs, "queue_revision",
        lambda req: (200, {"ok": True, "job_id": "job-3", "status": "queued"}),
    )

    result = ableton_bridge.ask("please fix it up a bit for the client", session_id="s1", project_id="proj-1")

    assert result["found"] is True
    assert "db adjustment" not in result["answer"].lower()


def test_ask_still_queues_the_revision_even_if_the_explanation_step_fails(monkeypatch):
    """Chat-facing boundary: a bug describing the change must never prevent
    the already-successfully-queued revision from being reported."""
    monkeypatch.setattr(
        automix_jobs, "queue_revision",
        lambda req: (200, {"ok": True, "job_id": "job-4", "status": "queued"}),
    )

    import audio_analysis.integration.mix_intent as mix_intent
    monkeypatch.setattr(mix_intent, "parse_mix_intent", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    result = ableton_bridge.ask("make it brighter", session_id="s1", project_id="proj-1")

    assert result["found"] is True
    assert result["automix_revision"]["job_id"] == "job-4"
