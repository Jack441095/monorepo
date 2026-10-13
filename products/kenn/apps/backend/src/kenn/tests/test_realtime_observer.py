"""The cached review must expire and never combine different Live reads."""

from __future__ import annotations

import copy
import threading

import pytest

from kenn import mixing_doctor
from kenn.core.fake_live import FakeLiveBackend


@pytest.fixture
def observer(monkeypatch):
    """Isolate the daemon's cache and clock without starting a thread or Live."""
    clock = [100.0]
    monkeypatch.setattr(mixing_doctor.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(mixing_doctor, "_latest_session_state", {"status": "unknown", "tracks": []})
    monkeypatch.setattr(mixing_doctor, "_realtime_enabled", True)
    monkeypatch.setattr(mixing_doctor, "_poll_generation", 0, raising=False)
    fake = FakeLiveBackend()
    fake._session = {
        "status": "connected", "backend": "fake", "selected_track_index": 3,
        "is_playing": True, "session_name": "Synthetic Set",
        "tracks": [{"index": 3, "name": "Kick", "output_meter_level": 0.99}],
    }
    return fake, clock


def test_snapshot_and_alerts_expire_together_without_another_live_read(observer) -> None:
    # A stalled poll previously left the last connected snapshot current indefinitely.
    fake, clock = observer
    mixing_doctor._poll_once(fake)
    state = mixing_doctor.get_latest_session_state()
    assert state["freshness"]["current_for_diagnosis"] is True
    assert state["mixing_alerts"][0]["track_index"] == 3
    assert state["backend"] == "fake"
    clock[0] += 7.0  # seconds: beyond the observer's six-second current window
    expired = mixing_doctor.get_latest_session_state()
    assert expired["status"] == "stale"
    assert expired["tracks"] == []
    assert mixing_doctor.get_mixing_alerts() == []
    assert fake.writes == []


@pytest.mark.parametrize("response", [None, [], {"status": "dispatched"}, {"status": "offline"}, {"status": "connected", "tracks": "invalid"}])
def test_disconnect_or_malformed_read_replaces_cached_findings(observer, monkeypatch, response) -> None:
    fake, _clock = observer
    mixing_doctor._poll_once(fake)
    monkeypatch.setattr(fake, "query_session_state", lambda **kwargs: response)
    mixing_doctor._poll_once(fake)
    assert mixing_doctor.get_latest_session_state()["status"] != "connected"
    assert mixing_doctor.get_mixing_alerts() == []
    assert fake.writes == []


def test_read_timeout_clears_previous_observations(observer, monkeypatch) -> None:
    fake, _clock = observer
    mixing_doctor._poll_once(fake)

    def timeout(**kwargs):
        raise TimeoutError("synthetic timeout")

    monkeypatch.setattr(fake, "query_session_state", timeout)
    mixing_doctor._poll_once(fake)
    assert mixing_doctor.get_latest_session_state()["status"] == "offline"
    assert mixing_doctor.get_mixing_alerts() == []


def test_pause_discards_an_inflight_poll_even_after_resume(observer, monkeypatch) -> None:
    # Pausing and resuming during a read must not resurrect the pre-pause result.
    fake, _clock = observer
    entered, release = threading.Event(), threading.Event()
    state = fake.query_session_state()

    def delayed(**kwargs):
        entered.set()
        assert release.wait(1.0)  # seconds: deterministic test deadlock guard
        return state

    monkeypatch.setattr(fake, "query_session_state", delayed)
    worker = threading.Thread(target=mixing_doctor._poll_once, args=(fake,))
    worker.start()
    assert entered.wait(1.0)
    mixing_doctor.set_realtime_enabled(False)
    assert mixing_doctor.get_latest_session_state()["status"] == "paused"
    mixing_doctor.set_realtime_enabled(True)
    release.set()
    worker.join(1.0)
    assert not worker.is_alive()
    assert mixing_doctor.get_latest_session_state()["status"] != "connected"


@pytest.mark.parametrize("change", [
    {"selected_track_index": 4}, {"is_playing": False}, {"session_name": "Other Set"},
    {"tracks": [{"index": 3, "name": "Kick", "devices": [{"index": 0, "name": "Limiter"}]}]},
])
def test_context_revision_changes_with_selection_transport_project_and_devices(observer, change) -> None:
    fake, _clock = observer
    mixing_doctor._poll_once(fake)
    previous = mixing_doctor.get_latest_session_state()["state_revision"]
    fake._session.update(copy.deepcopy(change))
    mixing_doctor._poll_once(fake)
    assert mixing_doctor.get_latest_session_state()["state_revision"] != previous
    assert fake.writes == []


def test_nested_snapshot_is_detached_from_callers_and_alerts_use_host_indices(observer) -> None:
    fake, _clock = observer
    mixing_doctor._poll_once(fake)
    state = mixing_doctor.get_latest_session_state()
    state["tracks"][0]["name"] = "Changed by caller"
    state["mixing_alerts"][0]["message"] = "Changed by caller"
    current = mixing_doctor.get_latest_session_state()
    assert current["tracks"][0]["name"] == "Kick"
    assert "Kick" in current["mixing_alerts"][0]["message"]
    assert current["mixing_alerts"][0]["track_index"] == 3
