"""A gain-staging run that failed readback wrote volumes and rolled them back, but left the cached Live state in place.

The failure result carries no receipt, so the receipt journal never invalidated the world-state cache.
"""

from __future__ import annotations

from kenn.core import live_world_state
from kenn.core.live_action_service import LiveActionService
from kenn.tests.test_gain_staging_and_grouping import MultiTrackFakeLive


def _spy(monkeypatch):
    calls = []
    monkeypatch.setattr(live_world_state, "invalidate_world_state", lambda: calls.append(1))
    return calls


def _propose(fake, session_id):
    service = LiveActionService(fake)
    proposal = service.propose_gain_staging(target_headroom_db=-6.0, session_id=session_id)["proposal"]
    return service, proposal


def test_a_gain_staging_run_that_fails_readback_drops_the_cached_world_state(monkeypatch):
    calls = _spy(monkeypatch)
    fake = MultiTrackFakeLive()
    service, proposal = _propose(fake, "gs-fail")
    fake.fail_readback = True
    result = service.execute_gain_staging(proposal, confirm_token=proposal["confirmation_token"], session_id="gs-fail")
    assert result["ok"] is False
    assert "rolled back" in result["error"]
    assert calls == [1]


def test_a_refused_gain_staging_run_that_wrote_nothing_leaves_the_cache_alone(monkeypatch):
    calls = _spy(monkeypatch)
    fake = MultiTrackFakeLive()
    service, proposal = _propose(fake, "gs-refused")
    result = service.execute_gain_staging(proposal, confirm_token="wrong", session_id="gs-refused")
    assert result["ok"] is False
    assert fake.writes == []
    assert calls == []
