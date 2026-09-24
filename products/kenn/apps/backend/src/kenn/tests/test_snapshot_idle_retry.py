"""A first offline read (Live waking after idle) is retried once before KENN says offline."""

from __future__ import annotations

import pytest

from kenn.core import live_action_service
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService


@pytest.fixture(autouse=True)
def _fresh_process_flag(monkeypatch):
    monkeypatch.setattr(live_action_service, "_LIVE_SEEN_CONNECTED", False)


class _WakesUp(FakeLiveBackend):
    def __init__(self, misses: int) -> None:
        super().__init__()
        self.misses, self.calls = misses, 0

    def query_session_state(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.misses:
            return {"status": "offline", "tracks": []}
        return super().query_session_state(*args, **kwargs)


def _service(misses: int) -> tuple[LiveActionService, _WakesUp]:
    backend = _WakesUp(misses)
    service = LiveActionService(backend)
    service.SNAPSHOT_RETRY_DELAY_S = 0.0
    return service, backend


def test_one_missed_read_after_a_connected_one_is_retried() -> None:
    service, _backend = _service(misses=0)
    assert service.snapshot()["status"] == "connected"
    # A later request builds a new service (as the server does); Live idles and misses its first reply.
    service, backend = _service(misses=1)
    assert service.snapshot()["status"] == "connected" and backend.calls == 2


def test_a_live_never_reached_is_not_retried(monkeypatch) -> None:
    import kenn.mixing_doctor as doctor

    monkeypatch.setattr(doctor, "get_latest_session_state", lambda: None)
    service, backend = _service(misses=5)
    assert service.snapshot()["status"] == "offline" and backend.calls == 1


def test_still_offline_after_the_retry_reports_offline(monkeypatch) -> None:
    import kenn.mixing_doctor as doctor

    monkeypatch.setattr(doctor, "get_latest_session_state", lambda: None)
    service, _backend = _service(misses=0)
    service.snapshot()
    service, backend = _service(misses=5)
    assert service.snapshot()["status"] == "offline" and backend.calls == 2
