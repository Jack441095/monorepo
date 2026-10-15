from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
import uuid

import pytest

from kenn.core.live_action_service import LiveActionService


def _source():
    return {
        "source_kind": "arrangement_main", "fingerprint": "synthetic-set-revision-1",
        "range_confirmed": True, "tail_policy": "within_range",
    }


def _request():
    return {
        "live_pid": 12345, "expected_window_title": "Disposable synthetic set",
        "render_start": "1.1.1", "render_length": "4.0.0",
        "sample_rate": 48000, "timeout_seconds": 10,
    }


class _NoLiveCalls:
    def __getattr__(self, name):
        # Source validation belongs to the injected job service, never snapshot's cached fallback.
        raise AssertionError(f"Offline scan unexpectedly called Live client: {name}")


class _Jobs:
    def __init__(self):
        self.validations = []
        self.starts = []
        self.validation_error = None
        self.start_failure = None
        self.entered = None
        self.release = None

    def validate_current(self, source, export_request):
        self.validations.append((deepcopy(source), deepcopy(export_request)))
        if self.validation_error:
            raise ValueError(self.validation_error)
        return {
            "source": deepcopy(source),
            "export_request": {**deepcopy(export_request), "schema": "kenn.live_export_request.v1", "action": "export"},
        }

    def start(self, owner_id, source, export_request):
        self.starts.append((owner_id, deepcopy(source), deepcopy(export_request)))
        if self.entered:
            self.entered.set()
            assert self.release.wait(5), "Scan fixture was not released within 5 seconds."
        if self.start_failure == "raise":
            raise RuntimeError("Synthetic export start failed")
        if self.start_failure == "decline":
            return {"ok": False, "error": "Synthetic export start refused"}
        return {"ok": True, "state": "exporting", "job_id": "synthetic-owned-job"}


@pytest.fixture
def candidate(monkeypatch):
    monkeypatch.setenv("KENN_LIVE_BACKEND", "fake")
    monkeypatch.setenv("KENN_EXPERIMENTAL_LIVE_EXPORT", "1")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
    jobs = _Jobs()
    service = LiveActionService(_NoLiveCalls(), offline_scans=jobs)
    return service, jobs, f"synthetic-owner-{uuid.uuid4().hex}"


def _proposal(service, owner):
    result = service.propose_offline_scan(source=_source(), export_request=_request(), session_id=owner)
    assert result["ok"] is True
    return result["proposal"]


def _execute(service, proposal, owner, key=None):
    return service.execute(
        proposal, confirm_token=proposal["confirmation_token"], session_id=owner,
        idempotency_key=key or uuid.uuid4().hex,
    )


def test_export_candidate_is_disabled_by_default_even_when_daw_control_is_allowed(candidate, monkeypatch):
    service, jobs, owner = candidate
    monkeypatch.delenv("KENN_EXPERIMENTAL_LIVE_EXPORT")

    result = service.propose_offline_scan(source=_source(), export_request=_request(), session_id=owner)

    assert result["ok"] is False and "gate is closed" in result["error"]
    assert jobs.validations == [] and jobs.starts == []


def test_direct_service_calls_obey_existing_daw_policy_before_validation(candidate, monkeypatch):
    service, jobs, owner = candidate
    monkeypatch.delenv("KENN_ALLOW_DAW_CONTROL")

    result = service.propose_offline_scan(source=_source(), export_request=_request(), session_id=owner)

    assert result["ok"] is False and "DAW control policy" in result["error"]
    assert jobs.validations == [] and jobs.starts == []


def test_enabled_gate_without_an_injected_exporter_does_not_create_a_proposal(candidate):
    _, _, owner = candidate
    service = LiveActionService(_NoLiveCalls())

    result = service.propose_offline_scan(source=_source(), export_request=_request(), session_id=owner)

    assert result["ok"] is False and "configured" in result["error"]


@pytest.mark.parametrize("owner", ["", "   ", None, "x" * 257])
def test_proposal_requires_a_bounded_owner_before_source_validation(candidate, owner):
    service, jobs, _ = candidate

    result = service.propose_offline_scan(source=_source(), export_request=_request(), session_id=owner)

    assert result["ok"] is False
    assert jobs.validations == [] and jobs.starts == []


def test_proposal_only_validates_and_binds_normalized_source_and_export_settings(candidate):
    # Opening a proposal must not open Live's export dialog or allocate a render job.
    service, jobs, owner = candidate
    source, request = _source(), _request()
    result = service.propose_offline_scan(source=source, export_request=request, session_id=owner)
    proposal = result["proposal"]
    source["fingerprint"] = "later-caller-edit"
    request["render_length"] = "8.0.0"

    assert proposal["requires_confirmation"] is True
    assert proposal["scope"] == "producer_confirmed_range"
    assert proposal["source"] == _source()
    assert proposal["export_request"] == {**_request(), "schema": "kenn.live_export_request.v1", "action": "export"}
    assert proposal["confirmation_meta"]["service_id"] == "ableton_offline_scan"
    assert len(jobs.validations) == 1 and jobs.starts == []
    assert _execute(service, proposal, owner)["ok"] is True
    assert jobs.starts == [(owner, proposal["source"], proposal["export_request"])]


def test_changed_source_during_preview_is_a_refusal_without_a_confirmation(candidate):
    service, jobs, owner = candidate
    jobs.validation_error = "The source changed before confirmation."

    result = service.propose_offline_scan(source=_source(), export_request=_request(), session_id=owner)

    assert result["ok"] is False and "could not be validated" in result["error"]
    assert "proposal" not in result and jobs.starts == []


@pytest.mark.parametrize("disabled_flag", ["KENN_EXPERIMENTAL_LIVE_EXPORT", "KENN_ALLOW_DAW_CONTROL"])
def test_execution_rechecks_policy_after_a_proposal_was_issued(candidate, monkeypatch, disabled_flag):
    service, jobs, owner = candidate
    proposal = _proposal(service, owner)
    monkeypatch.delenv(disabled_flag)

    assert _execute(service, proposal, owner)["ok"] is False
    assert jobs.starts == []


def test_foreign_owner_cannot_consume_the_original_owners_confirmation(candidate):
    service, jobs, owner = candidate
    proposal = _proposal(service, owner)

    assert _execute(service, proposal, owner + "-other")["ok"] is False
    assert jobs.starts == []
    assert _execute(service, proposal, owner)["ok"] is True
    assert jobs.starts[0][0] == owner


@pytest.mark.parametrize("section,key,value", [
    ("source", "source_kind", "selected_insert"),
    ("source", "fingerprint", "synthetic-set-revision-2"),
    ("source", "tail_policy", "automatic_tail"),
    ("export_request", "render_start", "2.1.1"),
    ("export_request", "render_length", "8.0.0"),
    ("export_request", "sample_rate", 44100),
    ("export_request", "live_pid", 54321),
    ("export_request", "expected_window_title", "Other synthetic set"),
    ("export_request", "timeout_seconds", 20),
])
def test_confirmation_rejects_any_changed_source_range_or_export_setting(candidate, section, key, value):
    # A valid token for another range/settings must never export the edited payload.
    service, jobs, owner = candidate
    original = _proposal(service, owner)
    changed = deepcopy(original)
    changed[section][key] = value

    assert _execute(service, changed, owner)["ok"] is False
    assert jobs.starts == []
    assert _execute(service, original, owner)["ok"] is True


def test_replayed_confirmation_cannot_start_another_job_with_a_new_request_key(candidate):
    service, jobs, owner = candidate
    proposal = _proposal(service, owner)

    assert _execute(service, proposal, owner)["ok"] is True
    assert _execute(service, proposal, owner)["ok"] is False
    assert len(jobs.starts) == 1


def test_duplicate_request_is_refused_while_the_first_export_start_is_in_progress(candidate):
    service, jobs, owner = candidate
    jobs.entered, jobs.release = Event(), Event()
    proposal = _proposal(service, owner)
    key = uuid.uuid4().hex

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(_execute, service, proposal, owner, key)
        try:
            assert jobs.entered.wait(5), "Scan fixture did not enter start within 5 seconds."
            duplicate = _execute(service, proposal, owner, key)
            assert duplicate["ok"] is False and "already been used" in duplicate["error"]
            assert len(jobs.starts) == 1
        finally:
            jobs.release.set()
        assert pending.result(timeout=5)["ok"] is True


@pytest.mark.parametrize("failure", ["raise", "decline"])
def test_failed_start_consumes_confirmation_and_requires_both_a_fresh_proposal_and_request_key(candidate, failure):
    service, jobs, owner = candidate
    jobs.start_failure = failure
    proposal = _proposal(service, owner)
    key = uuid.uuid4().hex

    assert _execute(service, proposal, owner, key)["ok"] is False
    assert _execute(service, proposal, owner)["ok"] is False
    assert len(jobs.starts) == 1
    fresh = _proposal(service, owner)
    jobs.start_failure = None
    assert _execute(service, fresh, owner, key)["ok"] is False
    assert len(jobs.starts) == 1
    assert _execute(service, fresh, owner)["ok"] is True
    assert len(jobs.starts) == 2


@pytest.mark.parametrize("key", ["", "   ", None, "x" * 257])
def test_execution_requires_an_explicit_bounded_idempotency_key(candidate, key):
    service, jobs, owner = candidate
    proposal = _proposal(service, owner)

    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id=owner, idempotency_key=key)

    assert result["ok"] is False and "idempotency key" in result["error"]
    assert jobs.starts == []
