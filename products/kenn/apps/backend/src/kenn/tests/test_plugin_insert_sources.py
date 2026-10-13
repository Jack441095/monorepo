"""Browser source selection must preserve ownership, freshness and explicit opt-in."""

from copy import deepcopy

import pytest

import kenn.plugin_handoff as handoff
from kenn.tests.test_plugin_handoff import _payload, _window


@pytest.fixture(autouse=True)
def isolated_inserts(monkeypatch):
    monkeypatch.setattr(handoff, "_live_contexts", {})
    monkeypatch.setattr(handoff, "_pending_parameter_updates", {})


def _publish(insert="kick", owner="song", **changes):
    payload = _payload(conversation_id=owner, host_track_name="Kick", measurement_window=_window(),
                       plugin_state={"assistant_mode": "suggest", "analysis_enabled": True, "live_context_enabled": True})
    payload.update(changes)
    assert handoff.ingest_live_context(payload, session_id=insert)["ok"]


def test_discovery_is_compact_owner_scoped_and_does_not_select_the_latest_insert():
    _publish("kick")
    _publish("bass", host_track_name="Bass")
    _publish("foreign", owner="other song")
    result = handoff.plugin_insert_sources("song", "not-yet-published")
    assert result["selected_status"] == "waiting_for_publication"
    assert {source["insert_id"] for source in result["sources"]} == {"kick", "bass"}
    assert all(source["current_for_diagnosis"] for source in result["sources"])
    assert all("fft_spectra" not in source and "review" not in source for source in result["sources"])
    assert not handoff.plugin_insert_sources("song", "foreign")["ok"]


def test_discovery_caps_sources_at_64_and_preserves_the_explicit_selection():
    for index in range(65):  # One over the 64-insert native batch capacity.
        _publish(f"insert-{index}")
    result = handoff.plugin_insert_sources("song", "insert-0")
    assert len(result["sources"]) == 64 and result["sources"][0]["insert_id"] == "insert-0"


def test_pause_retires_diagnosis_without_claiming_the_host_has_acknowledged_it():
    _publish()
    assert handoff.queue_owned_plugin_parameters("kick", "song", {"live_context_enabled": False})["ok"]
    source = handoff.plugin_insert_sources("song", "kick")["sources"][0]
    assert not source["current_for_diagnosis"]
    assert source["requested_parameters"]["live_context_enabled"] is False
    assert source["reported_parameters"]["live_context_enabled"] is True
    assert not handoff.live_context_summary("kick")["freshness"]["current_for_diagnosis"]
    assert handoff.pop_pending_parameter_updates("kick")["pending_updates"] == {"live_context_enabled": False}
    _publish(analysed_samples=52800, measurement_window=_window(sequence=11, start_sample=48000, end_sample=52800))
    assert not handoff.plugin_insert_sources("song", "kick")["sources"][0]["current_for_diagnosis"]


def test_explicit_native_ask_does_not_require_background_publishing():
    # Ask deliberately captures audio even when idle publication has never been enabled.
    _publish(plugin_state={"assistant_mode": "suggest",
             "analysis_enabled": True, "live_context_enabled": False})
    assert handoff.live_context_summary("kick")["freshness"]["current_for_diagnosis"]


def test_first_publication_can_be_enabled_explicitly_without_routing_to_a_sibling():
    _publish("known", owner="new-insert")
    assert handoff.get_plugin_parameters("unpublished")["parameters"]["live_context_enabled"] is False
    # An unpublished insert ID can equal another conversation; explicit controls
    # must never use the old conversation-to-single-insert compatibility lookup.
    assert handoff.queue_owned_plugin_parameters("new-insert", "song", {"live_context_enabled": True})["ok"]
    assert handoff._pending_parameter_updates == {"new-insert": {"live_context_enabled": True}}
    assert handoff.pop_pending_parameter_updates("new-insert")["session_id"] == "new-insert"


def test_foreign_owner_cannot_queue_controls_or_relabel_the_selected_insert():
    _publish()
    before = deepcopy(handoff._live_contexts["kick"])
    assert not handoff.queue_owned_plugin_parameters("kick", "wrong", {"analysis_enabled": False})["ok"]
    assert handoff._pending_parameter_updates == {}
    assert handoff._live_contexts["kick"] == before


def test_status_ages_even_when_the_same_cached_frame_is_resent(monkeypatch):
    clock = [1000.0]  # Synthetic epoch seconds, independent of HTTP scheduling.
    monkeypatch.setattr(handoff.time, "time", lambda: clock[0])
    _publish()
    clock[0] += 1.2  # Outside the one-second continuous diagnosis lifetime.
    _publish()
    source = handoff.plugin_insert_sources("song", "kick")["sources"][0]
    assert source["audio_age_seconds"] == 1.2 and not source["current_for_diagnosis"]


@pytest.mark.parametrize("owner,insert", [("", "kick"), ("x" * 129, "kick"), ("song", "x" * 129)])
def test_malformed_launch_identity_never_discovers_a_global_source(owner, insert):
    _publish()
    assert not handoff.plugin_insert_sources(owner, insert)["ok"]
