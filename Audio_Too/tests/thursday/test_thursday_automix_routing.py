"""AutoMix-via-Thursday routing tests (audit fix, 2026-07-08, Stage 2).

docs/THURSDAY_ORCHESTRATOR_AUDIT_2026-07-08.md found Thursday had zero awareness of
AutoMix -- 0 registry references vs 5-11 for every other studio subsystem. This wires
it in via the same pattern used for mix_review/audiogen: thursday/client.py wrappers
over the existing automix_jobs API, a registry_handlers._handle_automix action, and
a ServiceDef in registry_studio.py.

Also covers a bug found while wiring this in: the shared "project_name" entity regex
is greedy over "for ...", so "run automix for project abc123" extracted the entity as
"project abc123" (including the literal word "project"), which then failed the
database's project foreign-key check. Fixed with dedicated, authoritative extraction
in _handle_automix.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday import orchestrator  # noqa: E402
from thursday.registry import build_services  # noqa: E402
from thursday.registry.handlers import _handle_automix  # noqa: E402
from thursday.session_manager import get_or_create_session  # noqa: E402


def test_automix_service_is_registered() -> None:
    services = build_services(orchestrator.api)
    assert "automix" in services


def test_project_id_extraction_strips_the_word_project() -> None:
    """Regression for the 'project abc123' -> project_id bug found during wiring."""
    calls = []

    class FakeApi:
        def automix_start(self, project_id, *, genre="pop", target_lufs=None, style_prefs=None, correlation_id=""):
            calls.append(project_id)
            return {"ok": True, "job_id": "test1234"}

    reply = _handle_automix(FakeApi(), "run automix for project abc123", {})
    assert calls == ["abc123"], f"expected clean project id, got {calls}"
    assert "abc123" in reply


def test_bare_project_id_without_project_keyword_is_extracted() -> None:
    calls = []

    class FakeApi:
        def automix_start(self, project_id, *, genre="pop", target_lufs=None, style_prefs=None, correlation_id=""):
            calls.append(project_id)
            return {"ok": True, "job_id": "test1234"}

    _handle_automix(FakeApi(), "start automix on 12bfbefd", {})
    assert calls == ["12bfbefd"]


def test_autonomous_phrasing_opts_into_kenn_advisor() -> None:
    """Stage H Workstream C: "let kenn mix" (and its synonyms) is the only
    thing that should turn on style_prefs["autonomous_kenn"] -- every other
    automix phrasing must leave it off."""
    calls = []

    class FakeApi:
        def automix_start(self, project_id, *, genre="pop", target_lufs=None, style_prefs=None, correlation_id=""):
            calls.append(style_prefs)
            return {"ok": True, "job_id": "test1234"}

    reply = _handle_automix(FakeApi(), "let kenn mix project abc123", {})
    assert calls[-1] == {"autonomous_kenn": True}
    assert "autonomously" in reply.lower()

    _handle_automix(FakeApi(), "kenn decide the mix for project abc123", {})
    assert calls[-1] == {"autonomous_kenn": True}

    _handle_automix(FakeApi(), "run automix for project abc123", {})
    assert calls[-1] == {}


def test_correlation_id_from_ctx_reaches_automix_start() -> None:
    """A Thursday command's trace id (thursday/command_gateway.py's
    CommandEnvelope, threaded through orchestrator.handle's handler_ctx as
    "_correlation_id") must reach the job so its worker/advisor/feedback
    domain events can be correlated back to the originating command."""
    calls = []

    class FakeApi:
        def automix_start(self, project_id, *, genre="pop", target_lufs=None, style_prefs=None, correlation_id=""):
            calls.append(correlation_id)
            return {"ok": True, "job_id": "test1234"}

    _handle_automix(
        FakeApi(), "run automix for project abc123", {"_correlation_id": "thursday-cmd:xyz"}
    )
    assert calls == ["thursday-cmd:xyz"]


def test_missing_correlation_id_in_ctx_passes_empty_string() -> None:
    calls = []

    class FakeApi:
        def automix_start(self, project_id, *, genre="pop", target_lufs=None, style_prefs=None, correlation_id=""):
            calls.append(correlation_id)
            return {"ok": True, "job_id": "test1234"}

    _handle_automix(FakeApi(), "run automix for project abc123", {})
    assert calls == [""]


def test_missing_project_asks_for_clarification() -> None:
    class FakeApi:
        def automix_start(self, *a, **k):
            raise AssertionError("should not be called without a project id")

    reply = _handle_automix(FakeApi(), "run automix", {})
    assert "which project" in reply.lower()


def test_status_query_reaches_status_action() -> None:
    calls = []

    class FakeApi:
        def automix_status(self, job_id):
            calls.append(job_id)
            return {"status": "queued", "history": []}

    reply = _handle_automix(FakeApi(), "check automix status abc12345", {})
    assert calls == ["abc12345"]
    assert "queued" in reply.lower()


def test_list_query_reaches_list_action() -> None:
    class FakeApi:
        def automix_list_jobs(self, *, project_id=None, limit=10):
            return [{"id": "j1", "project_id": "p1", "genre": "pop", "status": "complete"}]

    reply = _handle_automix(FakeApi(), "list my automix jobs", {})
    assert "j1" in reply
    assert "complete" in reply


def test_automix_request_does_not_fall_through_to_kenn(monkeypatch) -> None:
    kenn_hits = []

    def fake_ask_kenn(text, *a, **k):
        kenn_hits.append(text)
        return f"[KENN: {text[:20]}]"

    monkeypatch.setattr(orchestrator.api, "ask_kenn", fake_ask_kenn)
    session = get_or_create_session(f"test-automix-routing-{uuid.uuid4().hex[:8]}")

    for text in ["automix status", "list my automix jobs", "run automix for project x"]:
        orchestrator.handle(text, session, list_records=lambda _t: [])

    assert not kenn_hits, "AutoMix requests must not fall through to KENN"


def test_start_then_status_round_trip_through_real_orchestrator(monkeypatch) -> None:
    """End-to-end with a real (test-fixture) project id against the real DB path."""
    sys.path.insert(0, str(ROOT / "server" / "app"))
    from db import connect
    import stem_uploads

    monkeypatch.setattr(
        stem_uploads,
        "require_source_ready",
        lambda project_id, **kwargs: {
            "ready": True,
            "project_id": project_id,
            "file_count": 1,
            "total_bytes": 1,
        },
    )

    project_id = f"test{uuid.uuid4().hex[:6]}"
    with connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, client, project, service, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (project_id, "Test Client", "Test Project", "mixing", "Open"),
        )
        conn.commit()
    try:
        session = get_or_create_session(f"test-automix-e2e-{uuid.uuid4().hex[:8]}")
        start_reply = orchestrator.handle(
            f"run automix for project {project_id}", session, list_records=lambda _t: []
        )
        match = re.search(r"job ([a-f0-9]{8})", start_reply)
        assert match, f"expected a job id in: {start_reply}"
        job_id = match.group(1)

        status_reply = orchestrator.handle(
            f"automix status {job_id}", session, list_records=lambda _t: []
        )
        assert "queued" in status_reply.lower()
    finally:
        with connect() as conn:
            conn.execute("DELETE FROM automix_job_events WHERE job_id IN "
                         "(SELECT id FROM automix_jobs WHERE project_id = ?)", (project_id,))
            conn.execute("DELETE FROM automix_jobs WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
