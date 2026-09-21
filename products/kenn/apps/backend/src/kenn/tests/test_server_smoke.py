"""Smoke tests proving apps/backend/src/kenn/server.py actually starts and serves
real requests standalone -- previously blocked entirely at import time
(unguarded `audio_too`/`thursday` imports and a REPO_ROOT path bug; see
docs/KNOWN_ISSUES.md ISSUE-08). This does not exercise every route (most
specialist routes need external hardware/services and are already
individually guarded in server.py itself) -- it proves the server process
comes up and the two routes needed for a local companion integration
(health check, ask) work end-to-end against the real, standalone-built
knowledge index.
"""

from __future__ import annotations

import json
import io
import struct
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402


def _index_available() -> bool:
    index_dir = Path(__file__).resolve().parents[1] / "data" / "index" / "CURRENT"
    return index_dir.exists()


@pytest.fixture(scope="module")
def running_server():
    if not _index_available():
        pytest.skip("Knowledge index not built -- run `python3 apps/backend/src/kenn/main.py build` first.")

    import os

    os.environ["KENN_PORT"] = "8099"
    os.environ["KENN_HOST"] = "127.0.0.1"
    # This suite proves the standalone deterministic server and its local
    # contracts. Keep optional model generation out of the smoke path so an
    # unloaded local model cannot turn a bounded HTTP check into a timeout.
    os.environ["AUDIO_TOO_LLM_ENABLED"] = "0"
    os.environ["KENN_LIVE_LLM_ENABLED"] = "0"

    import kenn.server as server_module

    httpd = server_module.ThreadingHTTPServer(("127.0.0.1", 8099), server_module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)
    try:
        yield "http://127.0.0.1:8099"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture(autouse=True)
def reset_rate_limit_buckets():
    import kenn.server_rate_limit as server_rate_limit
    server_rate_limit.RATE_BUCKETS.clear()
    yield
    server_rate_limit.RATE_BUCKETS.clear()


def test_health_endpoint_responds(running_server: str) -> None:
    with urllib.request.urlopen(f"{running_server}/api/health", timeout=5) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert body["app"] == "KENN"
    retrieval = body["subsystems"]["knowledge_index"]
    assert retrieval["schema"] == "kenn.retrieval_status.v1"
    assert retrieval["active_mode"] in {"unavailable", "bm25_only", "hybrid"}


def test_session_outcome_summary_endpoint_returns_aggregate_only(running_server: str) -> None:
    with urllib.request.urlopen(f"{running_server}/api/session-outcomes/summary?limit=1", timeout=5) as response:
        body = json.loads(response.read())
    assert body["schema"] == "kenn.session_outcome_summary.v1"
    assert body["sample_count"] <= 1
    assert body["privacy"]["records_returned"] is False
    assert body["privacy"]["raw_prompts_returned"] is False
    assert body["live_mutation_authorized"] is False


def test_arrangement_analysis_requires_a_session_id(running_server: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(f"{running_server}/api/ableton/arrangement-analysis", timeout=5)
    assert error.value.code == 400
    body = json.loads(error.value.read())
    assert body["ok"] is False
    assert "session_id" in body["error"]


def test_arrangement_analysis_returns_read_only_brief_from_current_snapshot(
    running_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    class ArrangementLive:
        def query_session_understanding(self) -> dict:
            return {
                "status": "connected",
                "tempo": 120.0,
                "is_playing": False,
                "tracks": [{
                    "index": 0,
                    "name": "Kick",
                    "type": "audio",
                    "devices": [],
                    "clip_slots": [{"index": 0, "name": "Kick", "has_clip": True}],
                    "arrangement_clips": [{"index": 0, "name": "Kick", "start_time_beats": 1.0, "length_beats": 16.0}],
                }],
                "scenes": [{"index": 0, "name": "Verse"}],
                "locators": [{"index": 0, "name": "Verse", "time_beats": 1.0}],
                "return_tracks": [],
            }

    monkeypatch.setattr(bridge_module, "live_client", ArrangementLive())
    with urllib.request.urlopen(
        f"{running_server}/api/ableton/arrangement-analysis?session_id=arrangement-http",
        timeout=5,
    ) as response:
        body = json.loads(response.read())
    assert body["schema"] == "kenn.arrangement_analysis.v1"
    assert body["status"] == "current"
    assert body["advisory_only"] is True
    assert body["mutation_authorized"] is False
    assert body["sections"][0]["active_clip_count"] == 1


def test_plugin_live_review_endpoint_returns_latest_context_without_new_capture(
    running_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = f"live-review-{uuid.uuid4().hex}"
    payload = {
        "schema": "kenn.plugin_handoff.v1",
        "audio_feature_schema": "audio_feature_frame.v1",
        "kind": "mix_review_snapshot",
        "assistant_mode": "ask",
        "session_id": session_id,
        "peak_dbfs": -5.0,
        "rms_dbfs": -18.0,
        "stereo_correlation": 0.8,
        "stereo_width": 0.2,
        "sample_rate": 48000.0,
        "analysed_samples": 48000,
        "low_energy": 0.04,
        "mid_energy": 0.01,
        "high_energy": 0.002,
        "spectrum_schema": "realtime_spectrum.v1",
        "spectrum_bands": [
            {"center_hz": 315.0, "low_hz": 280.6, "high_hz": 353.6, "energy": 0.02},
            {"center_hz": 1000.0, "low_hz": 891.0, "high_hz": 1122.5, "energy": 0.01},
        ],
        "plugin_state": {"assistant_mode": "ask", "analysis_enabled": True},
    }
    request = urllib.request.Request(
        f"{running_server}/api/plugin-handoff",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        posted = json.loads(response.read())
    assert posted["ok"] is True

    import kenn.mixing_doctor as mixing_doctor_module

    monkeypatch.setattr(mixing_doctor_module, "get_latest_session_state", lambda: {
        "status": "connected",
        "tracks": [{"index": 0, "name": "Vocal", "output_meter_level": 0.72}],
    })
    monkeypatch.setattr(mixing_doctor_module, "get_mixing_alerts", lambda: [])
    chat_request = urllib.request.Request(
        f"{running_server}/api/ask",
        data=json.dumps({
            "question": "scan the current Ableton session for advice",
            "session_id": "chat-realtime-scan",
            "plugin_session_id": session_id,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(chat_request, timeout=30) as response:
        chat_scan = json.loads(response.read())
    assert chat_scan["orchestration"]["agent_name"] == "realtime_session_reviewer"
    assert chat_scan["orchestration"]["report"]["plugin_bus"]["status"] == "current"
    assert chat_scan["orchestration"]["report"]["plugin_bus"]["scope"] == "plugin_bus"
    assert chat_scan["sources"] == chat_scan["orchestration"]["sources"]
    assert chat_scan["sources"]

    import kenn.core.realtime_session_review as realtime_review_module

    monkeypatch.setattr(realtime_review_module, "realtime_knowledge_guidance", lambda focus, report: [{
        "source": "live12-manual-en.pdf, page 398",
        "evidence_class": "official_ableton_manual",
        "evidence_label": "Official Ableton manual",
        "excerpt": "Use the meter to watch levels.",
        "advisory_only": True,
    }] if focus else [])
    with urllib.request.urlopen(
        f"{running_server}/api/realtime-session-review?plugin_session_id={session_id}&focus=headroom%20gain%20staging",
        timeout=30,
    ) as response:
        focused_scan = json.loads(response.read())
    assert focused_scan["status"] == "current"
    assert focused_scan["knowledge_guidance"][0]["evidence_class"] == "official_ableton_manual"
    assert focused_scan["knowledge_guidance"][0]["advisory_only"] is True

    with urllib.request.urlopen(f"{running_server}/api/plugin-live-review?session_id={session_id}", timeout=5) as response:
        result = json.loads(response.read())
    assert result["ok"] is True
    assert result["schema"] == "kenn.plugin_live_review.v1"
    assert result["capture_requested"] is False
    assert result["advisory_only"] is True
    assert result["live_context"]["freshness"]["frame_count"] == 1
    assert result["live_context"]["live_window"]["status"] == "insufficient"

    with urllib.request.urlopen(
        f"{running_server}/api/realtime-mix-recommendations?session_id={session_id}",
        timeout=5,
    ) as response:
        recommendations = json.loads(response.read())
    assert recommendations["ok"] is True
    assert recommendations["schema"] == "kenn.realtime_mix_recommendations.v1"
    assert recommendations["scope"] == "plugin_bus"
    assert recommendations["capture_requested"] is False
    assert recommendations["advisory_only"] is True
    assert recommendations["recommendations_available"] is True
    assert recommendations["recommendations"][0]["title"] == "Realtime bus: inspect around 315 Hz"
    assert recommendations["recommendations"][0]["requiresConfirmation"] is False
    assert all(item["canAutoFix"] is False for item in recommendations["recommendations"])

    knowledge_request = urllib.request.Request(
        f"{running_server}/api/knowledge/ask",
        data=json.dumps({
            "question": "Why is my mix darker than my reference?",
            "plugin_session_id": session_id,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(knowledge_request, timeout=30) as response:
        knowledge = json.loads(response.read())
    assert knowledge["ok"] is True
    assert "315 Hz" in knowledge["answer"]
    assert "2.0 dB below" in knowledge["answer"]
    assert knowledge["plugin_evidence"]["schema"] == "kenn.evidence.v1"
    assert knowledge["plugin_evidence"]["source"] == "plugin_bus_snapshot"
    assert any(
        fact["name"] == "realtime_pink_noise_largest_deviation_frequency_hz"
        and fact["value"] == 315.0
        for fact in knowledge["plugin_evidence"]["facts"]
    )


def test_realtime_session_review_endpoint_composes_or_fails_closed(running_server: str) -> None:
    try:
        with urllib.request.urlopen(
            f"{running_server}/api/realtime-session-review",
            timeout=10,
        ) as response:
            status = response.status
            body = json.loads(response.read())
    except urllib.error.HTTPError as error:
        status = error.code
        body = json.loads(error.read())

    assert status in {200, 503}
    assert body["schema"] == "kenn.realtime_session_review.v1"
    assert body["advisory_only"] is True
    assert body["capture_requested"] is False
    assert body["mutation_authorized"] is False
    assert body["status"] in {"current", "unavailable"}
    assert "live_session" in body
    assert "mixing_doctor" in body
    assert "project_health" in body
    if status == 503:
        assert body["status"] == "unavailable"
        assert body["mixing_doctor"]["alerts"] == []


def test_plugin_live_review_endpoint_requires_a_fresh_session(running_server: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(f"{running_server}/api/plugin-live-review?session_id=missing-{uuid.uuid4().hex}", timeout=5)
    assert error.value.code == 404
    body = json.loads(error.value.read())
    assert body["reason"] == "missing_or_expired_context"

    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(
            f"{running_server}/api/realtime-mix-recommendations?session_id=missing-{uuid.uuid4().hex}",
            timeout=5,
        )
    assert error.value.code == 404
    body = json.loads(error.value.read())
    assert body["schema"] == "kenn.realtime_mix_recommendations.v1"
    assert body["recommendations"] == []
    assert body["capture_requested"] is False

    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(
            f"{running_server}/api/realtime-mix-comparison?review_id=missing&session_id=missing-{uuid.uuid4().hex}",
            timeout=5,
        )
    assert error.value.code == 404
    body = json.loads(error.value.read())
    assert body["schema"] == "kenn.realtime_mix_comparison.v1"
    assert body["comparison_available"] is False
    assert body["capture_requested"] is False


def test_health_endpoint_reports_the_cached_deterministic_subsystem_rollup(
    running_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kenn.mixing_doctor as mixing_doctor_module

    monkeypatch.setattr(
        mixing_doctor_module, "get_latest_session_state",
        lambda: {"status": "connected", "tracks": [{"index": 0, "name": "Drums"}]},
    )
    with urllib.request.urlopen(f"{running_server}/api/health", timeout=5) as response:
        body = json.loads(response.read())
    assert body["ok"] is True  # base contract is unchanged
    assert body["app"] == "KENN"
    assert body["subsystems"]["abletonosc"] == {"status": "connected", "connected": True}
    assert body["subsystems"]["knowledge_index"]["available"] is True
    runtime_state = body["subsystems"]["runtime_state"]
    assert set(runtime_state) == {
        "pending_proposals", "action_receipts", "pending_proposals_limit",
        "action_receipts_limit", "mix_reviews", "mix_reviews_limit",
    }
    assert all(isinstance(value, int) and value >= 0 for value in runtime_state.values())


def test_health_endpoint_never_fails_when_cached_ableton_state_raises(
    running_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kenn.mixing_doctor as mixing_doctor_module

    def raising_cache():
        raise RuntimeError("cache exploded")

    monkeypatch.setattr(mixing_doctor_module, "get_latest_session_state", raising_cache)
    with urllib.request.urlopen(f"{running_server}/api/health", timeout=5) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert body["subsystems"]["abletonosc"]["status"] == "error"
    assert body["subsystems"]["abletonosc"]["connected"] is False


def test_health_endpoint_does_not_call_blocking_ableton_probe(
    running_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    def fail_if_called():
        raise AssertionError("health must not synchronously probe AbletonOSC")

    monkeypatch.setattr(bridge_module.live_client, "probe_connection", fail_if_called)
    with urllib.request.urlopen(f"{running_server}/api/health", timeout=1) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert body["subsystems"]["abletonosc"]["status"] in {"unknown", "offline", "connected"}


def test_ableton_status_endpoint_uses_local_bridge(running_server: str) -> None:
    with urllib.request.urlopen(f"{running_server}/api/ableton/status", timeout=5) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert body["status"] in {"connected", "offline", "dispatched"}
    assert body["connected"] is (body["status"] == "connected")
    assert body["port"] == 11000


def test_ableton_ping_and_watchdog_endpoints(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    monkeypatch.setattr(bridge_module.live_client, "ping", lambda timeout=0.5: True)
    monkeypatch.setattr(bridge_module.live_client, "_connection_state", "connected")
    with urllib.request.urlopen(f"{running_server}/api/ableton/ping", timeout=5) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert body["connected"] is True
    assert body["state"] == "connected"

    with urllib.request.urlopen(f"{running_server}/api/ableton/watchdog", timeout=5) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert "watchdog" in body
    assert body["watchdog"]["port"] == 11000


def test_ableton_return_tracks_endpoint_is_read_only_and_real(
    running_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    def fake_get_return_tracks():
        return [
            {"index": 0, "name": "A-Reverb", "devices": ["Reverb"]},
            {"index": 1, "name": "B-Delay", "devices": ["Delay"]},
        ]

    monkeypatch.setattr(bridge_module.live_client, "get_return_tracks", fake_get_return_tracks)
    with urllib.request.urlopen(f"{running_server}/api/ableton/osc/return-tracks", timeout=5) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert body["return_tracks"] == [
        {"index": 0, "name": "A-Reverb", "devices": ["Reverb"]},
        {"index": 1, "name": "B-Delay", "devices": ["Delay"]},
    ]


def test_ableton_session_understanding_endpoint_is_explicit_and_read_only(
    running_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    def fake_query_session_understanding() -> dict:
        return {
            "status": "connected", "read_only": True,
            "understanding_detail": "routing_sends_clip_inventory",
            "tracks": [{"index": 0, "name": "Vocal", "sends": []}],
            "return_tracks": [],
        }

    monkeypatch.setattr(bridge_module.live_client, "query_session_understanding", fake_query_session_understanding)
    with urllib.request.urlopen(f"{running_server}/api/ableton/osc/session?detail=understanding", timeout=5) as response:
        body = json.loads(response.read())
    assert body["status"] == "connected"
    assert body["read_only"] is True
    assert body["understanding_detail"] == "routing_sends_clip_inventory"


def test_ableton_capabilities_endpoint_reports_explicit_contract(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    class CapabilityFake:
        def capability_report(self) -> dict:
            return {
                "schema": "kenn.abletonosc_capabilities.v1",
                "transport": "AbletonOSC",
                "status": "connected",
                "connected": True,
                "endpoints": {"read": ["/live/song/get/track_names"], "write": ["/live/device/set/parameter/value"]},
                "write_boundary": {"confirmation_required": True, "readback_required": True, "replay_rejection": True},
            }

    monkeypatch.setattr(bridge_module, "live_client", CapabilityFake())
    with urllib.request.urlopen(f"{running_server}/api/ableton/capabilities", timeout=5) as response:
        body = json.loads(response.read())
    assert body["schema"] == "kenn.abletonosc_capabilities.v1"
    assert body["transport"] == "AbletonOSC"
    assert body["connected"] is True
    assert "/live/device/set/parameter/value" in body["endpoints"]["write"]
    assert body["write_boundary"]["confirmation_required"] is True


def test_ableton_receipts_endpoint_returns_read_only_journal_projection(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.server as server_module

    monkeypatch.setattr(
        server_module,
        "list_receipts",
        lambda *, session_id, limit: [{"session_id": session_id, "limit_seen": limit, "receipt": {"receipt_id": "receipt-test"}}],
    )
    with urllib.request.urlopen(f"{running_server}/api/ableton/receipts?session_id=smoke&limit=3", timeout=5) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert body["schema"] == "kenn.ableton_receipt_journal.v1"
    assert body["receipts"][0]["session_id"] == "smoke"
    assert body["receipts"][0]["limit_seen"] == 3


def test_ableton_device_parameters_endpoint_is_read_only_and_index_bound(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    class ParameterFake:
        def get_device_parameters(self, track_index: int, device_index: int) -> dict:
            assert (track_index, device_index) == (3, 0)
            return {
                "success": True,
                "device_name": "EQ Eight",
                "parameters": [{"index": 11, "name": "1 Frequency A", "value": 250.0}],
            }

    monkeypatch.setattr(bridge_module, "live_client", ParameterFake())
    with urllib.request.urlopen(f"{running_server}/api/ableton/osc/device-parameters?track_index=3&device_index=0", timeout=5) as response:
        body = json.loads(response.read())
    assert body["success"] is True
    assert body["device_name"] == "EQ Eight"
    assert body["parameters"][0]["name"] == "1 Frequency A"


def test_ableton_midi_clip_endpoint_is_read_only_and_index_bound(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    class MidiClipFake:
        def get_midi_clip_state(self, track_index: int, clip_slot_index: int) -> dict:
            assert (track_index, clip_slot_index) == (1, 0)
            return {
                "success": True,
                "track_index": 1,
                "clip_slot_index": 0,
                "has_clip": False,
                "is_midi_clip": False,
                "length": 0.0,
                "notes": [],
            }

        def query_session_topology(self) -> dict:
            return {"tracks": [{"index": 1, "name": "2-MIDI"}]}

    monkeypatch.setattr(bridge_module, "live_client", MidiClipFake())
    with urllib.request.urlopen(f"{running_server}/api/ableton/osc/midi-clip?track_index=1&clip_slot_index=0", timeout=5) as response:
        body = json.loads(response.read())
    assert body["success"] is True
    assert body["track_name"] == "2-MIDI"
    assert body["has_clip"] is False


def test_ableton_generic_clip_slot_endpoint_returns_audio_identity_without_writing(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    class ClipSlotFake:
        def get_clip_slot_state(self, track_index: int, clip_slot_index: int) -> dict:
            assert (track_index, clip_slot_index) == (1, 2)
            return {
                "success": True,
                "track_index": 1,
                "clip_slot_index": 2,
                "has_clip": True,
                "clip_name": "Vocal Chop",
                "is_midi_clip": False,
                "length": 4.0,
                "notes": [],
            }

        def query_session_topology(self) -> dict:
            return {"tracks": [{"index": 1, "name": "2-Audio"}]}

    monkeypatch.setattr(bridge_module, "live_client", ClipSlotFake())
    with urllib.request.urlopen(f"{running_server}/api/ableton/osc/clip-slot?track_index=1&clip_slot_index=2", timeout=5) as response:
        body = json.loads(response.read())
    assert body["success"] is True
    assert body["track_name"] == "2-Audio"
    assert body["clip_name"] == "Vocal Chop"
    assert body["is_midi_clip"] is False


def test_mix_review_recipe_boundary_fetches_server_owned_evidence(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.server as server_module

    class ReviewFake:
        def mix_review_status(self, review_id: str) -> dict:
            assert review_id == "review-smoke"
            return {
                "status": "completed",
                "review": {
                    "status": "completed",
                    "flags": [{
                        "label": "Headroom",
                        "detail": "Measured uploaded render is close to clipping.",
                        "severity": "medium",
                        "confidence": "high",
                    }],
                },
            }

    captured: dict = {}

    def fake_handle_command(command: str, **kwargs) -> dict:
        captured.update(kwargs)
        return {
            "status": "confirmation_required",
            "changed": False,
            "proposal": {"schema": "kenn.ableton_recipe_proposal.v1", "source_evidence": kwargs["source_evidence"]},
        }

    monkeypatch.setattr(server_module, "mix_review", ReviewFake())
    monkeypatch.setattr(server_module, "handle_command", fake_handle_command)
    body = json.dumps({
        "session_id": "review-recipe-smoke",
        "command": "prepare headroom recipe",
        "mix_review_id": "review-smoke",
        "recipe_steps": [{"action": "set_volume", "track_index": 3, "track_name": "4-Audio", "value": 0.4}],
    }).encode()
    request = urllib.request.Request(
        f"{running_server}/api/ableton/command",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        result = json.loads(response.read())
    evidence = result["proposal"]["source_evidence"]
    assert result["changed"] is False
    assert evidence["review_id"] == "review-smoke"
    assert evidence["source_scope"] == "uploaded_or_rendered_audio"
    assert evidence["live_target_inference_allowed"] is False
    assert evidence["recommendations"][0]["title"] == "Headroom"
    assert captured["recipe_steps"][0]["action"] == "set_volume"


def test_mix_review_recipe_boundary_rejects_incomplete_review(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.server as server_module

    class PendingReview:
        def mix_review_status(self, review_id: str) -> dict:
            return {"status": "running", "review": {"status": "running", "flags": []}}

    monkeypatch.setattr(server_module, "mix_review", PendingReview())
    body = json.dumps({
        "session_id": "review-recipe-pending",
        "command": "prepare recipe",
        "mix_review_id": "review-pending",
        "recipe_steps": [{"action": "set_volume", "track_index": 3, "track_name": "4-Audio", "value": 0.4}],
    }).encode()
    request = urllib.request.Request(
        f"{running_server}/api/ableton/command",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=5)
    assert error.value.code == 409
    response = json.loads(error.value.read())
    assert "not complete" in response["error"]


def test_ableton_device_matrix_endpoint_is_read_only_and_labels_candidates(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    class MatrixFake:
        def device_matrix_report(self, *, include_parameters: bool) -> dict:
            assert include_parameters is True
            return {
                "schema": "kenn.ableton_device_matrix.v1",
                "status": "connected",
                "connected": True,
                "entries": [{
                    "track_name": "4-Audio",
                    "device_name": "Glue Compressor",
                    "qualification": "candidate",
                    "parameter_probe": {"success": True, "parameter_count": 2, "parameters": []},
                }],
                "missing_candidate_families": ["Saturator"],
                "write_boundary": {"report_is_read_only": True},
            }

    monkeypatch.setattr(bridge_module, "live_client", MatrixFake())
    with urllib.request.urlopen(f"{running_server}/api/ableton/device-matrix", timeout=5) as response:
        body = json.loads(response.read())
    assert body["schema"] == "kenn.ableton_device_matrix.v1"
    assert body["entries"][0]["qualification"] == "candidate"
    assert body["write_boundary"]["report_is_read_only"] is True


def test_support_diagnostics_is_redacted(running_server: str) -> None:
    with urllib.request.urlopen(f"{running_server}/api/support/diagnostics", timeout=5) as response:
        body = json.loads(response.read())
    rendered = json.dumps(body)
    assert body["schema"] == "kenn.support_diagnostics.v1"
    assert body["redactions"]["safe_to_attach_to_support_ticket"] is True
    assert body["checks"]["audio_retained_by_diagnostics"] is False
    assert body["checks"]["project_content_included"] is False
    assert "confirmation_tokens" in body["redactions"]["excluded_fields"]
    assert "/Volumes/" not in rendered
    assert "raw_live_snapshot" not in rendered.split("excluded_fields", 1)[0]


def test_ask_endpoint_returns_grounded_answer(running_server: str) -> None:
    request = urllib.request.Request(
        f"{running_server}/api/ask",
        data=json.dumps({"question": "Why does my mix collapse when I check it in mono?"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read())
    assert body.get("found") is True
    assert body.get("sources")
    assert "schema_version" in body  # response_contract.augment_payload envelope


def test_ask_track_inventory_uses_read_only_live_gateway(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.server as server_module

    def fake_live_inspection(command: str, *, session_id: str) -> dict:
        assert command == "What is on track 4?"
        assert session_id == "plugin-inspect"
        return {
            "status": "inspected",
            "changed": False,
            "intent": {"action": "inspect_devices"},
            "target": {"index": 3, "name": "4-Audio"},
            "devices": [{"index": 0, "name": "EQ Eight", "is_active": True}],
            "answer": "Track '4-Audio' has 1 device(s): EQ Eight.",
        }

    monkeypatch.setattr(server_module, "handle_command", fake_live_inspection)
    request = urllib.request.Request(
        f"{running_server}/api/ask",
        data=json.dumps({"question": "What is on track 4?", "session_id": "plugin-inspect"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.loads(response.read())
    assert body["route"] == "ableton_live_inspection"
    assert body["answer_mode"] == "live_inspection"
    assert body["found"] is True
    assert body["changed"] is False
    assert body["devices"][0]["name"] == "EQ Eight"


def test_ask_session_fact_uses_read_only_live_gateway(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.server as server_module

    def fake_session_answer(question: str) -> dict:
        assert question == "What is the current tempo and time signature?"
        return {
            "schema": "kenn.ableton_session_answer.v1",
            "status": "inspected",
            "changed": False,
            "answer": "The current tempo is 120 BPM and the time signature is 4/4.",
            "intent": {"action": "inspect_tempo_signature"},
            "tempo": 120.0,
            "signature_numerator": 4,
            "signature_denominator": 4,
        }

    monkeypatch.setattr(server_module, "answer_live_session_question", fake_session_answer)
    request = urllib.request.Request(
        f"{running_server}/api/ask",
        data=json.dumps({
            "question": "What is the current tempo and time signature?",
            "session_id": "plugin-session-fact",
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.loads(response.read())

    assert body["route"] == "ableton_live_inspection"
    assert body["answer_mode"] == "live_inspection"
    assert body["found"] is True
    assert body["tempo"] == 120.0


def test_knowledge_ask_cites_real_live_track_evidence_when_session_id_given(
    running_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kenn.ableton_osc_bridge as bridge_module

    def fake_query_session_state():
        return {
            "status": "connected",
            "tracks": [
                {"index": 0, "name": "Vocal", "devices": [{"name": "EQ Eight"}, {"name": "Glue Compressor"}]},
                {"index": 1, "name": "Rhythm Guitar", "devices": [{"name": "Saturator"}]},
            ],
        }

    monkeypatch.setattr(bridge_module.live_client, "query_session_state", fake_query_session_state)
    request = urllib.request.Request(
        f"{running_server}/api/knowledge/ask",
        data=json.dumps({
            "question": "why is my vocal getting masked",
            "session_id": "smoke-test-session",
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert "Live session evidence" in body["answer"]
    assert body["session_evidence"] == [{
        "track_index": 0,
        "track_name": "Vocal",
        "role": "vocal_lead",
        "display_name": "Lead Vocal",
        "devices": ["EQ Eight", "Glue Compressor"],
    }]


def test_knowledge_ask_omits_session_evidence_without_session_id(running_server: str) -> None:
    request = urllib.request.Request(
        f"{running_server}/api/knowledge/ask",
        data=json.dumps({"question": "why is my vocal getting masked"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read())
    assert body["ok"] is True
    assert "session_evidence" not in body
    assert "Live session evidence" not in body["answer"]


def test_main_chat_can_combine_explicit_mix_review_and_plugin_evidence(running_server: str) -> None:
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"".join(struct.pack("<h", 3000) for _ in range(8000)))
    boundary = f"kenn-{uuid.uuid4().hex}".encode()
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="chat-review.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n" + audio.getvalue()
        + b"\r\n--" + boundary + b"--\r\n"
    )
    upload = urllib.request.Request(
        f"{running_server}/api/mix-review",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
        method="POST",
    )
    with urllib.request.urlopen(upload, timeout=30) as response:
        review = json.loads(response.read())
    assert review["ok"] is True

    session_id = f"chat-comparison-{uuid.uuid4().hex}"
    handoff = {
        "schema": "kenn.plugin_handoff.v1",
        "audio_feature_schema": "audio_feature_frame.v1",
        "kind": "mix_review_snapshot",
        "assistant_mode": "ask",
        "session_id": session_id,
        "peak_dbfs": -5.0,
        "rms_dbfs": -18.0,
        "stereo_correlation": 0.8,
        "stereo_width": 0.2,
        "sample_rate": 48000.0,
        "analysed_samples": 48000,
        "spectrum_schema": "realtime_spectrum.v1",
        "spectrum_bands": [
            {"center_hz": 315.0, "low_hz": 280.6, "high_hz": 353.6, "energy": 0.02},
            {"center_hz": 1000.0, "low_hz": 891.0, "high_hz": 1122.5, "energy": 0.01},
        ],
        "plugin_state": {"assistant_mode": "ask", "analysis_enabled": True},
    }
    handoff_request = urllib.request.Request(
        f"{running_server}/api/plugin-handoff",
        data=json.dumps(handoff).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(handoff_request, timeout=10) as response:
        assert json.loads(response.read())["ok"] is True

    question = {
        "question": "How does the live bus compare with my uploaded reference?",
        "plugin_session_id": session_id,
        "mix_review_id": review["review_id"],
    }
    ask_request = urllib.request.Request(
        f"{running_server}/api/ask",
        data=json.dumps(question).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(ask_request, timeout=30) as response:
        result = json.loads(response.read())
    assert result["realtime_mix_comparison"]["schema"] == "kenn.realtime_mix_comparison.v1"
    assert result["realtime_mix_comparison"]["comparison_available"] is True
    assert result["mix_review_evidence"]["source"] == "mix_review_upload"
    assert "Scope-labelled comparison" in result["answer"]
    assert "current/recent plugin-bus window" in result["answer"]

    stream_request = urllib.request.Request(
        f"{running_server}/api/ask",
        data=json.dumps({**question, "stream": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(stream_request, timeout=30) as response:
        events = [
            json.loads(line[6:])
            for line in response.read().decode("utf-8").splitlines()
            if line.startswith("data: ")
        ]
    stream_metadata = [event["data"] for event in events if event.get("event") == "metadata"][-1]
    assert stream_metadata["realtime_mix_comparison"]["comparison_available"] is True
    assert "Scope-labelled comparison" in stream_metadata["answer"]


def test_sample_import_proposal_endpoint_requires_session_id(running_server: str) -> None:
    request = urllib.request.Request(
        f"{running_server}/api/ableton/sample-import/proposal",
        data=json.dumps({"track_index": 2, "track_name": "3-Audio", "clip_slot_index": 0, "sample_id": "x"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=10)
    assert error.value.code == 400
    body = json.loads(error.value.read())
    assert "session_id" in body["error"]


def test_sample_import_proposal_endpoint_is_honest_without_configured_library(
    running_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KENN_SAMPLE_LIBRARY_ROOT", raising=False)
    request = urllib.request.Request(
        f"{running_server}/api/ableton/sample-import/proposal",
        data=json.dumps({
            "session_id": "smoke-import",
            "track_index": 2,
            "track_name": "3-Audio",
            "clip_slot_index": 0,
            "sample_id": "deadbeefdeadbeef",
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=10)
    assert error.value.code == 409
    body = json.loads(error.value.read())
    assert "No sample library is configured" in body["error"]


def test_audio_analysis_endpoint_returns_kenn_spectral_contract(running_server: str) -> None:
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"".join(struct.pack("<h", 5000) for _ in range(4000)))
    boundary = f"kenn-{uuid.uuid4().hex}".encode()
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="probe.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n"
        + audio.getvalue()
        + b"\r\n--"
        + boundary
        + b"--\r\n"
    )
    request = urllib.request.Request(
        f"{running_server}/api/audio-analysis?reference=pink_noise",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read())
    assert result["ok"] is True
    assert result["schema"] == "kenn.audio_analysis.result.v1"
    assert result["spectral"]["status"] == "complete"
    assert result["spectral"]["pink_noise_reference"]["status"] == "complete"


def test_audio_analysis_compare_returns_hashes_and_measured_deltas(running_server: str) -> None:
    def wav_bytes(level: int) -> bytes:
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"".join(struct.pack("<h", level) for _ in range(4000)))
        return audio.getvalue()

    boundary = f"kenn-{uuid.uuid4().hex}"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file_a"; filename="before.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + wav_bytes(3000)
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file_b"; filename="after.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + wav_bytes(6000)
        + f'\r\n--{boundary}--\r\n'.encode()
    )
    request = urllib.request.Request(
        f"{running_server}/api/audio-analysis/compare",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read())
    assert result["ok"] is True
    assert result["schema"] == "kenn.audio_analysis.comparison.v1"
    assert result["source_a"]["input_hash"] != result["source_b"]["input_hash"]
    assert "rms_dbfs" in result["metric_deltas"]


def test_mix_reference_endpoint_persists_metadata_only_receipt(running_server: str) -> None:
    def wav_bytes(frequency_hz: float) -> bytes:
        import math
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"".join(
                struct.pack("<h", int(6000 * math.sin(2 * math.pi * frequency_hz * index / 8000)))
                for index in range(8000)
            ))
        return audio.getvalue()

    boundary = f"kenn-{uuid.uuid4().hex}"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="mix"; filename="mix.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + wav_bytes(100)
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="reference"; filename="reference.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + wav_bytes(3000)
        + f'\r\n--{boundary}--\r\n'.encode()
    )
    request = urllib.request.Request(
        f"{running_server}/api/mix-review/reference",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read())
    assert result["ok"] is True
    assert result["review_id"].startswith("reference-")
    assert result["review"]["audio_retained"] is False

    with urllib.request.urlopen(f"{running_server}/api/mix-review-status?id={result['review_id']}", timeout=10) as response:
        stored = json.loads(response.read())
    assert stored["review"]["reference_comparison"]["largest_ltas_difference"]["center_hz"] > 0


def test_mix_reference_endpoint_handles_32_bit_float_wavs(running_server: str) -> None:
    import math

    def float32_wav_bytes(frequency_hz: float, sample_rate: int = 8000, duration_seconds: float = 1.0) -> bytes:
        num_samples = int(sample_rate * duration_seconds)
        raw_samples = b"".join(
            struct.pack("<f", 0.5 * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
            for i in range(num_samples)
        )
        num_channels = 1
        bits_per_sample = 32
        block_align = num_channels * (bits_per_sample // 8)
        byte_rate = sample_rate * block_align
        data_size = len(raw_samples)
        fmt_chunk = struct.pack(
            "<4sIHHIIHH",
            b"fmt ",
            16,
            3,  # WAVE_FORMAT_IEEE_FLOAT
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
        )
        data_chunk = b"data" + struct.pack("<I", data_size) + raw_samples
        riff_size = 4 + len(fmt_chunk) + len(data_chunk)
        return b"RIFF" + struct.pack("<I", riff_size) + b"WAVE" + fmt_chunk + data_chunk

    boundary = f"kenn-{uuid.uuid4().hex}"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="mix"; filename="mix_float32.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + float32_wav_bytes(150.0)
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="reference"; filename="ref_float32.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + float32_wav_bytes(2500.0)
        + f'\r\n--{boundary}--\r\n'.encode()
    )
    request = urllib.request.Request(
        f"{running_server}/api/mix-review/reference",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read())
    assert result["ok"] is True
    assert result["review_id"].startswith("reference-")
    assert result["review"]["audio_retained"] is False

    with urllib.request.urlopen(f"{running_server}/api/mix-review-status?id={result['review_id']}", timeout=10) as response:
        stored = json.loads(response.read())
    assert stored["review"]["reference_comparison"]["largest_ltas_difference"]["center_hz"] > 0
    assert "eq_bands" in stored["review"]["reference_comparison"]
    assert len(stored["review"]["reference_comparison"]["eq_bands"]) > 0


def test_mix_review_masking_endpoint_flags_competing_stems(running_server: str) -> None:
    import math

    def sine_wav_bytes(freq: float, seconds: float = 3.0, rate: int = 44100) -> bytes:
        n = int(seconds * rate)
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            frames = bytearray()
            for i in range(n):
                value = int(0.5 * math.sin(2 * math.pi * freq * i / rate) * 32767)
                frames += struct.pack("<h", value)
            wav.writeframes(bytes(frames))
        return audio.getvalue()

    boundary = f"kenn-{uuid.uuid4().hex}"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="stem_a"; filename="stem_a.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + sine_wav_bytes(440.0)
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="stem_b"; filename="stem_b.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + sine_wav_bytes(445.0)
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        f"{running_server}/api/mix-review/masking",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read())
    assert result["ok"] is True
    assert result["schema"] == "kenn.mix_review_masking_analysis.v1"
    assert set(result["stems"]) == {"stem_a", "stem_b"}
    assert result["findings"]
    assert all(f["fault_family"] == "masking" for f in result["findings"])


def test_mix_review_masking_endpoint_rejects_a_single_stem(running_server: str) -> None:
    import math

    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        n = int(3.0 * 44100)
        frames = bytearray()
        for i in range(n):
            value = int(0.5 * math.sin(2 * math.pi * 440.0 * i / 44100) * 32767)
            frames += struct.pack("<h", value)
        wav.writeframes(bytes(frames))
    boundary = f"kenn-{uuid.uuid4().hex}"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="stem_a"; filename="stem_a.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + audio.getvalue()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        f"{running_server}/api/mix-review/masking",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=10)
    assert error.value.code == 400
    body_json = json.loads(error.value.read())
    assert "at least 2" in body_json["error"].lower()


def test_audiogen_audio_compare_accepts_only_local_portfolio_references(
    running_server: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import kenn.server as server_module

    def wav_bytes(level: int) -> bytes:
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"".join(struct.pack("<h", level) for _ in range(4000)))
        return audio.getvalue()

    (tmp_path / "before.wav").write_bytes(wav_bytes(3000))
    (tmp_path / "after.wav").write_bytes(wav_bytes(6000))
    monkeypatch.setattr(server_module, "PORTFOLIO_AUDIO_ROOTS", [tmp_path])
    request = urllib.request.Request(
        f"{running_server}/api/audiogen/audio-compare",
        data=json.dumps({
            "source_a": "/portfolio/audio/before.wav",
            "source_b": "/portfolio/audio/after.wav",
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read())
    assert result["schema"] == "kenn.audiogen_audio_comparison.v1"
    assert result["ok"] is True
    assert result["source_a"]["filename"] == "before.wav"
    assert "rms_dbfs" in result["metric_deltas"]

    bad_request = urllib.request.Request(
        f"{running_server}/api/audiogen/audio-compare",
        data=json.dumps({"source_a": "/etc/passwd", "source_b": "/portfolio/audio/after.wav"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(bad_request, timeout=10)
    assert error.value.code == 400


def test_ableton_http_alias_uses_proposal_then_verified_execution(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    class RouteFakeLive:
        def __init__(self) -> None:
            self.volume = 0.5
            self.writes = 0

        def query_session_state(self):
            return {"status": "connected", "tempo": 120.0, "is_playing": False, "tracks": [{"index": 0, "name": "Vocal", "volume": self.volume, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "devices": []}]}

        def set_track_volume(self, index: int, value: float) -> bool:
            assert index == 0
            self.volume = value
            self.writes += 1
            return True

    fake = RouteFakeLive()
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr("kenn.core.live_action_service.live_client", fake)

    def post(payload: dict) -> dict:
        request = urllib.request.Request(
            f"{running_server}/api/ableton/osc/volume",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    proposed = post({"session_id": "http-safe", "track_index": 0, "volume": 0.75})
    assert proposed["ok"] is True
    proposal = proposed["proposal"]
    applied = post({"session_id": "http-safe", "proposal": proposal, "confirm_token": proposal["confirmation_token"]})
    assert applied["ok"] is True
    assert applied["receipt"]["verified"] is True
    assert fake.writes == 1


def test_live_command_insertion_route_returns_a_real_proposal_without_writing(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    class InsertionFakeLive:
        def __init__(self) -> None:
            self.writes = 0
            self.state = {
                "status": "connected",
                "is_playing": False,
                "tracks": [{
                    "index": 0,
                    "name": "Blank Audio",
                    "volume": 0.5,
                    "pan": 0.0,
                    "muted": False,
                    "soloed": False,
                    "armed": False,
                    "devices": [],
                }],
            }

        def query_session_state(self):
            return json.loads(json.dumps(self.state))

        def insert_device_with_result(self, track_index: int, device_name: str, insertion_index: int) -> dict:
            self.writes += 1
            self.state["tracks"][track_index]["devices"].append({"index": insertion_index, "name": device_name})
            return {"success": True}

    fake = InsertionFakeLive()
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr("kenn.core.live_action_service.live_client", fake)

    def post(payload: dict) -> dict:
        request = urllib.request.Request(
            f"{running_server}/api/ableton/command",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    proposed = post({"command": "add EQ on track 1", "session_id": "http-insert"})
    assert proposed["status"] == "confirmation_required"
    assert proposed["proposal"]["schema"] == "kenn.ableton_device_insertion_proposal.v1"
    assert proposed["proposal"]["before_devices"] == []
    assert proposed["proposal"]["after_devices"][0]["name"] == "EQ Eight"
    assert proposed["changed"] is False
    assert fake.writes == 0


def test_http_compound_eq_route_confirms_readback_and_undo(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import kenn.core.live_action_service as action_service_module
    import kenn.core.live_command as live_command_module
    import kenn.server as server_module

    class CompoundFakeLive:
        def __init__(self) -> None:
            self.frequency = 250.0
            self.gain = 0.0
            self.writes: list[tuple[int, float]] = []

        def query_session_state(self):
            return {
                "status": "connected", "tempo": 120.0, "is_playing": False,
                "tracks": [{
                    "index": 0, "name": "Test Audio", "volume": 0.5, "pan": 0.0,
                    "muted": False, "soloed": False, "armed": False,
                    "devices": [{"index": 0, "name": "EQ Eight"}],
                }],
            }

        def get_device_parameters(self, track_index: int, device_index: int) -> dict:
            assert (track_index, device_index) == (0, 0)
            return {
                "success": True, "device_name": "EQ Eight",
                "parameters": [
                    {"index": 11, "name": "1 Frequency A", "value": self.frequency, "value_display": f"{self.frequency:g} Hz", "min": 20.0, "max": 20000.0},
                    {"index": 12, "name": "1 Gain A", "value": self.gain, "min": -15.0, "max": 15.0},
                ],
            }

        def set_device_parameter(self, track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
            assert (track_index, device_index) == (0, 0)
            self.writes.append((parameter_index, float(value)))
            if parameter_index == 11:
                self.frequency = float(value)
            elif parameter_index == 12:
                self.gain = float(value)
            else:
                return False
            return True

    fake = CompoundFakeLive()
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    make_service = lambda: action_service_module.LiveActionService(fake)
    monkeypatch.setattr(server_module, "LiveActionService", make_service)
    monkeypatch.setattr(live_command_module, "LiveActionService", make_service)

    def post(path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{running_server}{path}", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    session_id = "http-compound-eq"
    command = "retune EQ Eight band 1A to 300 Hz and reduce gain by 3 dB on track 1"
    proposed = post("/api/ableton/command", {"session_id": session_id, "command": command})
    assert proposed["status"] == "confirmation_required"
    proposal = proposed["proposal"]
    assert proposal["schema"] == "kenn.ableton_eq_band_tuning_gain_proposal.v1"
    assert proposed["changed"] is False
    applied = post("/api/ableton/command", {
        "session_id": session_id, "command": command, "proposal": proposal,
        "confirm_token": proposal["confirmation_token"], "idempotency_key": proposal["action_id"],
    })
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.frequency == 300.0 and fake.gain == -3.0

    undo_proposed = post("/api/ableton/osc/undo", {"session_id": "http-compound-eq-undo", "receipt": applied["receipt"]})
    undo = undo_proposed["proposal"]
    assert undo["schema"] == "kenn.ableton_eq_band_tuning_gain_proposal.v1"
    undone = post("/api/ableton/osc/undo", {
        "session_id": "http-compound-eq-undo", "receipt": applied["receipt"], "proposal": undo,
        "confirm_token": undo["confirmation_token"], "idempotency_key": undo["action_id"],
    })
    assert undone["ok"] is True and undone["receipt"]["verified"] is True
    assert fake.frequency == 250.0 and fake.gain == 0.0
    assert fake.writes == [(11, 300.0), (12, -3.0), (11, 250.0), (12, 0.0)]


def test_http_undo_dispatches_device_proposal_to_device_executor(running_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A device receipt must undo through the device safety boundary.

    This protects the real plug-in lifecycle from a route-level regression
    where the undo endpoint sent a device proposal to the track/transport
    executor instead.
    """
    import kenn.core.live_action_service as action_service_module
    import kenn.core.live_command as live_command_module
    import kenn.server as server_module

    class DeviceFakeLive:
        def __init__(self) -> None:
            self.value = -3.0
            self.writes: list[float] = []

        def query_session_state(self):
            return {
                "status": "connected",
                "tempo": 120.0,
                "is_playing": False,
                "tracks": [{
                    "index": 0,
                    "name": "Test Audio",
                    "volume": 0.5,
                    "pan": 0.0,
                    "muted": False,
                    "soloed": False,
                    "armed": False,
                    "devices": [{"index": 0, "name": "EQ Eight"}],
                }],
            }

        def get_device_parameters(self, track_index: int, device_index: int) -> dict:
            assert (track_index, device_index) == (0, 0)
            return {
                "success": True,
                "device_name": "EQ Eight",
                "parameters": [{
                    "index": 17,
                    "name": "2 Gain A",
                    "value": self.value,
                    "min": -15.0,
                    "max": 15.0,
                }],
            }

        def set_device_parameter(self, track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
            assert (track_index, device_index, parameter_index) == (0, 0, 17)
            self.value = float(value)
            self.writes.append(self.value)
            return True

    fake = DeviceFakeLive()
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    # Inject the fake at both route construction sites.  The production
    # server and command gateway each import the service class, so patching
    # only the bridge singleton would not prove the HTTP dispatch itself.
    make_service = lambda: action_service_module.LiveActionService(fake)
    monkeypatch.setattr(server_module, "LiveActionService", make_service)
    monkeypatch.setattr(live_command_module, "LiveActionService", make_service)

    def post(path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{running_server}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    session_id = "http-device-undo"
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_device_parameter",
        "track_index": 0,
        "track_name": "Test Audio",
        "device_index": 0,
        "device_name": "EQ Eight",
        "parameter_index": 17,
        "parameter_name": "2 Gain A",
        "value": 0.0,
        "relative": False,
        "unit": "dB",
        "eq_band": "2A",
    }
    proposed = post("/api/ableton/command", {"session_id": session_id, "command": "restore test EQ", "llm_plan": plan})
    proposal = proposed["proposal"]
    applied = post("/api/ableton/command", {
        "session_id": session_id,
        "command": "restore test EQ",
        "proposal": proposal,
        "confirm_token": proposal["confirmation_token"],
        "idempotency_key": proposal["id"],
    })
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.value == 0.0

    undo_proposed = post("/api/ableton/osc/undo", {
        "session_id": "http-device-undo-reverse",
        "receipt": applied["receipt"],
    })
    undo = undo_proposed["proposal"]
    undone = post("/api/ableton/osc/undo", {
        "session_id": "http-device-undo-reverse",
        "receipt": applied["receipt"],
        "proposal": undo,
        "confirm_token": undo["confirmation_token"],
        "idempotency_key": undo["id"],
    })
    assert undone["ok"] is True
    assert undone["receipt"]["verified"] is True
    assert fake.value == -3.0
    assert fake.writes == [0.0, -3.0]
