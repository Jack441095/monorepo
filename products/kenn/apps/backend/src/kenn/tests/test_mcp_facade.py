from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from kenn.core.assistant_coordinator import AssistantCoordinator
from kenn.core.assistant_task_memory import AssistantTaskStore
from kenn.core.deliberative_plan import DeliberativePlan, DeliberativeStep, PLAN_SKETCH_SCHEMA
from kenn.core.mcp_facade import (
    KennHTTPClient,
    KennMCPFacade,
    KennTransportError,
    TOOLS,
    _realtime_mix_recommendation,
    _realtime_mix_recommendations,
    validate_companion_base_url,
)
from kenn.core.session_outcome_contract import SCHEMA as SESSION_OUTCOME_SCHEMA, STAGES as OUTCOME_STAGES
from kenn.core.session_context import build_session_context


def test_companion_url_is_restricted_to_loopback_http() -> None:
    assert validate_companion_base_url("http://127.0.0.1:8090/") == "http://127.0.0.1:8090"
    assert validate_companion_base_url("http://localhost:8090") == "http://localhost:8090"
    assert KennHTTPClient("http://[::1]:8090").base_url == "http://[::1]:8090"

    for unsafe in (
        "https://127.0.0.1:8090", "http://example.com:8090",
        "http://user:secret@127.0.0.1:8090", "http://127.0.0.1:8090/api",
        "http://127.0.0.1:8090?redirect=remote",
    ):
        with pytest.raises(ValueError, match="loopback"):
            KennHTTPClient(unsafe)


def test_companion_client_never_follows_redirects_with_post_payload() -> None:
    paths = []

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            paths.append(self.path)
            self.send_response(307)
            self.send_header("Location", "/payload-leak")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"redirect rejected"}')

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = KennHTTPClient(f"http://127.0.0.1:{server.server_port}")
        result = client.post("/start", {"proposal": "private"})
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert paths == ["/start"]
    assert result["http_status"] == 307


class FakeKennHTTP:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def get(self, path: str, query: dict | None = None) -> dict:
        self.calls.append(("GET", path, query or {}))
        if path == "/api/ableton/osc/session":
            return {
                "status": "connected",
                "tracks": [{"index": 3, "name": "4-Audio", "devices": [{"index": 1, "name": "Glue Compressor"}]}],
            }
        if path == "/api/plugin-live-review":
            return {
                "ok": True,
                "schema": "kenn.plugin_live_review.v1",
                "session_id": (query or {}).get("session_id", ""),
                "review": {"schema": "kenn.plugin_review.v1", "observations": []},
                "live_context": {
                    "schema": "kenn.live_mix_context.v1",
                    "scope": "plugin_bus",
                    "peak_dbfs": -5.0,
                    "rms_dbfs": -18.0,
                    "stereo_correlation": 0.8,
                    "stereo_width": 0.2,
                    "pink_noise_reference": {
                        "curve": "-3 dB per octave pink-noise-style spectral baseline",
                        "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0},
                    },
                    "freshness": {"frame_count": 4, "age_seconds": 1.2, "ttl_seconds": 1800},
                    "live_window": {"status": "stable", "sample_count": 4, "window_seconds": 24.0},
                },
                "advisory_only": True,
                "capture_requested": False,
            }
        if path == "/api/realtime-session-review":
            return {
                "ok": True,
                "schema": "kenn.realtime_session_review.v1",
                "status": "current",
                "plugin_bus": None,
                "advisory_only": True,
                "capture_requested": False,
                "mutation_authorized": False,
            }
        if path == "/api/ableton/osc/midi-clip":
            return {
                "success": True,
                "track_index": 1,
                "track_name": "Bass MIDI",
                "clip_slot_index": 0,
                "has_clip": False,
                "is_midi_clip": False,
                "length": 0.0,
                "notes": [],
            }
        if path == "/api/ableton/osc/clip-slot":
            return {
                "success": True,
                "track_index": 1,
                "track_name": "Bass MIDI",
                "clip_slot_index": 0,
                "has_clip": True,
                "clip_name": "Bass Phrase",
                "is_midi_clip": False,
                "length": 8.0,
                "notes": [],
            }
        if path == "/api/audiogen/status":
            return {"ok": True, "render_queue": {"running": [], "queued": [], "recent": []}}
        if path == "/api/ableton/device-matrix":
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
                "write_boundary": {"report_is_read_only": True},
            }
        if path == "/api/mix-review-status":
            if (query or {}).get("id") == "reference-review":
                return {
                    "ok": True,
                    "status": "completed",
                    "review": {
                        "schema": "kenn.mix_review.reference_comparison.v1",
                        "status": "completed",
                        "reference_comparison": {
                            "comparison_basis": "Each LTAS is normalised around 1 kHz.",
                            "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
                            "pink_noise_reference": {
                                "curve": "-3 dB per octave pink-noise-style spectral baseline",
                                "largest_deviation": {"center_hz": 296.0, "deviation_db": 5.1},
                            },
                        },
                    },
                }
            return {
                "ok": True,
                "status": "completed",
                "review": {
                    "status": "completed",
                    "flags": [{
                        "label": "Master headroom",
                        "detail": "The uploaded render is close to 0 dBFS.",
                        "severity": "medium",
                        "confidence": "high",
                    }],
                },
            }
        if path == "/api/audiogen/job":
            return {
                "ok": True,
                "job": {
                    "id": "midi-job",
                    "status": "completed",
                    "result": {
                        "artifact": {
                            "artifact_id": "art_midi",
                            "kind": "midi",
                            "content_hash": "sha256:" + ("b" * 64),
                            "metadata": {
                                "note_count": 2,
                                "lowest_note": 60,
                                "highest_note": 67,
                                "bars": 8,
                                "bpm": 120,
                                "key": "C Major",
                            },
                            "length_beats": 4,
                            "notes": [
                                {"pitch": 60, "start_time": 0, "duration": 1, "velocity": 100},
                                {"pitch": 67, "start_time": 2, "duration": 1, "velocity": 90},
                            ],
                            "path": "/private/should-not-be-forwarded.mid",
                        }
                    },
                },
            }
        if path == "/api/ableton/osc/device-parameters":
            return {
                "success": True,
                "device_name": "Glue Compressor",
                "parameters": [{"index": 4, "name": "Attack", "value": 3.0, "min": 0.0, "max": 6.0, "quantized": True}],
            }
        if path == "/api/ableton/osc/device-parameter-value-string":
            return {"success": True, "value_string": "1"}
        if path == "/api/ableton/receipts":
            return {"ok": True, "schema": "kenn.ableton_receipt_journal.v1", "receipts": []}
        if path == "/api/ableton/audition-feedback":
            if (query or {}).get("session_id") != "revision-session":
                return {"ok": True, "schema": "kenn.audition_feedback.v1", "feedback": []}
            return {
                "ok": True,
                "schema": "kenn.audition_feedback.v1",
                "feedback": [{
                    "schema": "kenn.audition_feedback.v1",
                    "feedback_id": "feedback-1",
                    "session_id": "revision-session",
                    "source_receipt_id": "receipt-1",
                    "verdict": "revise",
                    "rating": 3,
                    "comment": "Make the ending less busy",
                    "requested_changes": ["Simplify the ending"],
                    "audition": {
                        "receipt_id": "receipt-1",
                        "target": {"track_index": 0, "track_name": "1-MIDI", "clip_slot_index": 0},
                        "clip_fingerprint": "abc",
                        "clip_length": 4.0,
                    },
                }],
            }
        return {"backend": "AbletonOSC"}

    def post(self, path: str, payload: dict) -> dict:
        self.calls.append(("POST", path, payload))
        if path == "/api/ableton/clip-audition/proposal":
            return {"ok": True, "changed": False, "proposal": {"schema": "kenn.ableton_clip_audition_proposal.v1"}}
        if path == "/api/ableton/midi-clip/proposal":
            return {"ok": True, "changed": False, "proposal": {"schema": "kenn.ableton_midi_clip_proposal.v1"}}
        if path == "/api/ableton/midi-clip/update-proposal":
            return {"ok": True, "changed": False, "proposal": {"schema": "kenn.ableton_midi_clip_update_proposal.v1"}}
        if path == "/api/ableton/clip-rename/proposal":
            return {"ok": True, "changed": False, "proposal": {"schema": "kenn.ableton_clip_rename_proposal.v1"}}
        if path == "/api/ableton/command" and "recipe_steps" in payload:
            response = {"ok": True, "changed": False, "status": "confirmation_required", "proposal": {"schema": "kenn.ableton_recipe_proposal.v1", "step_count": len(payload["recipe_steps"])} }
            if payload.get("mix_review_id"):
                response["proposal"]["source_evidence"] = {"review_id": payload["mix_review_id"]}
            return response
        if path == "/api/audiogen/midi-proposal":
            return {
                "ok": True,
                "changed": False,
                "artifact": {"kind": "midi", "sha256": "sha256:" + ("c" * 64)},
                "proposal": {"schema": "kenn.ableton_midi_clip_proposal.v1"},
            }
        if path == "/api/audiogen/generate":
            return {
                "ok": True,
                "emotion": "joy",
                "bars": 4,
                "src": "/portfolio/audio/kenn-audiogen-joy-test.wav",
                "portfolio_title": "KENN AudioGen test",
                "artifact": {"kind": "audio", "sha256": "sha256:" + ("d" * 64)},
            }
        if path == "/api/audiogen/audio-compare":
            return {
                "schema": "kenn.audiogen_audio_comparison.v1",
                "ok": True,
                "source_a": {"filename": "a.wav", "input_hash": "sha256:a"},
                "source_b": {"filename": "b.wav", "input_hash": "sha256:b"},
                "metric_deltas": {"rms_dbfs": {"a": -18.0, "b": -12.0, "delta_b_minus_a": 6.0}},
                "advisory_only": True,
            }
        if path == "/api/ableton/osc/undo":
            if "proposal" not in payload:
                return {"ok": True, "proposal": {"id": "undo-proposal"}}
            return {"ok": True, "receipt": {"receipt_id": "undo-receipt"}}
        if path == "/api/knowledge/ask":
            if "capital of france" in payload.get("question", "").lower():
                return {"ok": True, "answer": "", "found": False, "weak_match": True, "confidence": "low", "sources": []}
            response = {
                "ok": True,
                "answer": "Set a compressor's threshold below the loudest peaks you want to control.",
                "found": True,
                "weak_match": False,
                "confidence": "high",
                "sources": [{"title": "compressor-basics.md"}],
            }
            if payload.get("plugin_session_id"):
                response["plugin_evidence"] = {
                    "schema": "kenn.evidence.v1",
                    "source": "plugin_bus_snapshot",
                    "facts": [{"name": "peak_dbfs", "value": -5.0, "unit": "dBFS"}],
                    "limitations": ["Bus snapshot only."],
                }
            if payload.get("mix_review_id"):
                response["mix_review_evidence"] = {
                    "schema": "kenn.evidence.v1",
                    "source": "mix_review_upload",
                    "review_id": payload["mix_review_id"],
                    "status": "completed",
                    "facts": [{"name": "reference_largest_ltas_delta_db", "value": 5.0, "unit": "dB"}],
                    "limitations": ["Uploaded review only."],
                }
            if payload.get("mix_review_id") and payload.get("plugin_session_id"):
                response["realtime_mix_comparison"] = {
                    "schema": "kenn.realtime_mix_comparison.v1",
                    "comparison_available": True,
                    "comparisons": [],
                    "pink_noise_shape": {"deviation_delta_db": -0.1},
                    "advisory_only": True,
                    "capture_requested": False,
                    "live_target_inference_allowed": False,
                }
            return response
        if "proposal" in payload and "confirm_token" in payload:
            return {"ok": True, "status": "applied", "changed": True, "receipt": {"receipt_id": "receipt-test"}}
        return {"status": "confirmation_required", "changed": False, "proposal": {"id": "proposal-test"}}


def _call(facade: KennMCPFacade, request_id: int, name: str, arguments: dict | None = None) -> dict:
    response = facade.handle_message({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    })
    assert response is not None
    return response


def test_mcp_initialize_and_tools_list_are_valid_json_rpc() -> None:
    facade = KennMCPFacade(FakeKennHTTP())
    initialized = facade.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert initialized["result"]["serverInfo"]["name"] == "kenn-live"
    listed = facade.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert {tool["name"] for tool in listed["result"]["tools"]} == {tool["name"] for tool in TOOLS}
    assert {"apply_live_proposal", "undo_live_receipt"}.issubset({tool["name"] for tool in TOOLS})


def test_mcp_context_is_read_only_and_includes_track_evidence() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 10, "kenn_context", {"session_id": "context-test"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "kenn.session_context.v1"
    assert payload["session_id"] == "context-test"
    assert payload["tracks"][0]["classification"]["role"] == "unknown"
    assert payload["devices"][0]["name"] == "Glue Compressor"
    assert payload["device_capability_matrix"]["schema"] == "kenn.ableton_device_matrix.v1"
    assert ("GET", "/api/ableton/osc/session", {"detail": "understanding"}) in client.calls
    assert ("GET", "/api/ableton/device-matrix", {"parameters": "0"}) in client.calls
    assert any(path == "/api/audiogen/status" for _method, path, _query in client.calls)


def test_mcp_arrangement_analysis_is_read_only_and_bounded() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 13, "live_arrangement_analysis", {"session_id": "arrangement-test"})
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["schema"] == "kenn.arrangement_analysis.v1"
    assert payload["status"] == "current"
    assert payload["advisory_only"] is True
    assert payload["mutation_authorized"] is False
    assert isinstance(payload["suggestions"], list)
    assert ("GET", "/api/ableton/osc/session", {"detail": "understanding"}) in client.calls
    assert all(method == "GET" for method, _path, _payload in client.calls)


def test_mcp_context_can_include_explicit_realtime_plugin_evidence() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        10,
        "kenn_context",
        {"session_id": "context-test", "plugin_session_id": "mix-session"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    plugin_measurements = [item for item in payload["measurements"] if item.get("kind") == "plugin_feature_frame"]
    assert len(plugin_measurements) == 1
    assert plugin_measurements[0]["live_window"]["status"] == "stable"
    assert plugin_measurements[0]["freshness"]["frame_count"] == 4
    assert "No realtime plug-in session was supplied" not in payload["limitations"]
    assert ("GET", "/api/plugin-live-review", {"session_id": "mix-session"}) in client.calls


def test_mcp_context_carries_scope_labelled_realtime_mix_comparison() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        10,
        "kenn_context",
        {
            "session_id": "context-test",
            "plugin_session_id": "mix-session",
            "mix_review_id": "reference-review",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    comparison = payload["realtime_mix_comparison"]
    assert comparison["schema"] == "kenn.realtime_mix_comparison.v1"
    assert comparison["comparison_available"] is True
    assert comparison["scope"] == {"live": "plugin_bus", "uploaded": "whole_file_mix_review"}
    assert any(item.get("kind") == "realtime_mix_comparison" for item in payload["measurements"])
    assert any(item.get("kind") == "realtime_mix_comparison" for item in payload["sources"])


def test_mcp_session_intelligence_preserves_realtime_spectral_evidence() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        10,
        "kenn_session_intelligence",
        {"session_id": "context-test", "plugin_session_id": "mix-session"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    pink = [item for item in payload["audio_evidence"] if item.get("kind") == "pink_noise_shape"]
    assert len(pink) == 1
    assert pink[0]["largest_deviation"] == {"center_hz": 315.0, "deviation_db": 5.0}
    assert payload["mutation_authorized"] is False
    assert payload["realtime_mix_comparison"] is None


def test_mcp_session_intelligence_combines_explicit_mix_and_plugin_evidence() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        10,
        "kenn_session_intelligence",
        {
            "session_id": "context-test",
            "mix_review_id": "reference-review",
            "plugin_session_id": "mix-session",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    comparison = payload["realtime_mix_comparison"]

    assert comparison["schema"] == "kenn.realtime_mix_comparison.v1"
    assert comparison["comparison_available"] is True
    assert comparison["pink_noise_shape"]["deviation_delta_db"] == -0.1
    assert "realtime_mix_comparison" in {item["kind"] for item in payload["explanation_sections"]}
    assert payload["mutation_authorized"] is False
    assert all(method == "GET" for method, _path, _query in client.calls)


def test_mcp_session_intelligence_is_read_only_and_explains_provenance() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        11,
        "kenn_session_intelligence",
        {
            "session_id": "context-test",
            "genre": "house",
            "goal": "Tighten the low mids",
            "references": ["Reference A"],
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["schema"] == "kenn.session_intelligence.v1"
    assert payload["status"] == "current"
    assert payload["project_intent"]["goal"] == "Tighten the low mids"
    assert payload["mutation_authorized"] is False
    assert {item["kind"] for item in payload["explanation_sections"]} >= {
        "observed_session_fact", "specialist_inference", "producer_intent",
    }
    assert "official_technical_reference" not in {item["kind"] for item in payload["explanation_sections"]}
    assert all(method == "GET" for method, _path, _payload in client.calls)


def test_mcp_context_delta_tracks_semantic_changes_without_writes() -> None:
    class DeltaHTTP(FakeKennHTTP):
        def __init__(self) -> None:
            super().__init__()
            self.track_name = "4-Audio"

        def get(self, path: str, query: dict | None = None) -> dict:
            result = super().get(path, query)
            if path == "/api/ableton/osc/session":
                result["tracks"][0]["name"] = self.track_name
            return result

    client = DeltaHTTP()
    facade = KennMCPFacade(client)
    first = json.loads(_call(facade, 20, "kenn_context_delta", {"session_id": "delta-session"})["result"]["content"][0]["text"])
    assert first["schema"] == "kenn.session_world_delta.v1"
    assert first["delta"]["events"][0]["kind"] == "world_initialized"
    assert first["read_only"] is True and first["live_mutation_authorized"] is False

    client.track_name = "Bass"
    second = json.loads(_call(facade, 21, "kenn_context_delta", {"session_id": "delta-session"})["result"]["content"][0]["text"])
    assert "track_renamed" in [event["kind"] for event in second["delta"]["events"]]
    assert all(method == "GET" for method, _path, _query in client.calls)


def test_mcp_explicit_producer_preference_enters_session_intelligence(tmp_path) -> None:
    client = FakeKennHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "assistant.sqlite3"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    recorded = _call(
        facade,
        12,
        "record_producer_preference",
        {
            "session_id": "memory-session",
            "key": "creative_direction",
            "value": "minimal and punchy",
            "source_turn_id": "turn-1",
            "user_statement": "I want this project minimal and punchy.",
        },
    )
    assert json.loads(recorded["result"]["content"][0]["text"])["ok"] is True

    response = _call(facade, 13, "kenn_session_intelligence", {"session_id": "memory-session"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["project_memory"]["explicit_preferences"][0]["value"] == "minimal and punchy"
    assert "explicit_project_memory" in {item["kind"] for item in payload["explanation_sections"]}
    assert all(method == "GET" for method, _path, _payload in client.calls)


def test_mcp_records_privacy_safe_supervised_outcome_without_live_call(tmp_path) -> None:
    client = FakeKennHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "assistant.sqlite3"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    bucket = lambda value: "sha256:" + f"{value:064x}"
    response = _call(facade, 15, "record_supervised_session_outcome", {"outcome": {
        "schema": SESSION_OUTCOME_SCHEMA, "session_bucket": bucket(1), "project_bucket": bucket(2),
        "tester_bucket": bucket(3), "intent_class": "analysis", "context_freshness": "fresh",
        "evidence_classes": ["live_snapshot"], "lifecycle_outcome": "completed",
        "user_verdict": "keep", "reason_codes": [], "root_cause": None,
        "latency_ms": {stage: 1 for stage in OUTCOME_STAGES},
        "contains_raw_prompt": False, "contains_audio": False,
    }})
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is True
    assert payload["live_mutation_authorized"] is False

    summary_response = _call(facade, 16, "supervised_session_outcome_summary", {"limit": 10})
    summary = json.loads(summary_response["result"]["content"][0]["text"])
    assert summary["schema"] == "kenn.session_outcome_summary.v1"
    assert summary["sample_count"] == 1
    assert summary["privacy"]["opaque_buckets_returned"] is False
    assert client.calls == []


def test_mcp_session_intelligence_uses_verified_reference_review() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade, 14, "kenn_session_intelligence",
        {"session_id": "reference-session", "mix_review_id": "reference-review"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    reference = next(item for item in payload["audio_evidence"] if item["kind"] == "uploaded_reference_ltas")
    assert reference["largest_difference"] == {"center_hz": 300.0, "delta_db": 5.0}
    assert payload["mixdown_coach"]["status"] == "ready"
    assert payload["mixdown_coach"]["live_target_inference_allowed"] is False
    assert all(method == "GET" for method, _path, _payload in client.calls)


def test_mcp_starts_evidence_first_production_diagnosis_without_writes() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        101,
        "start_production_diagnosis",
        {"goal": "My mix gets muddy in the busiest section", "session_id": "diagnosis-session"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is True
    assert payload["schema"] == "kenn.production_diagnosis.v1"
    assert payload["loop"]["status"] == "awaiting_test"
    assert len(payload["loop"]["hypotheses"]) == 3
    assert payload["next_plan"]["steps"][0]["kind"] == "clarification"
    assert payload["next_plan"]["steps"][0]["action"] == "ask_user"
    assert payload["execution_authorized"] is False
    assert client.calls
    assert all(method == "GET" for method, _path, _payload in client.calls)


def test_mcp_diagnostic_result_advances_one_hypothesis_and_stays_read_only() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    started_response = _call(
        facade,
        102,
        "start_production_diagnosis",
        {"goal": "My mix gets muddy in the busiest section", "session_id": "diagnosis-session"},
    )
    started = json.loads(started_response["result"]["content"][0]["text"])
    first_hypothesis = started["loop"]["active_hypothesis_id"]
    result_response = _call(
        facade,
        103,
        "record_diagnostic_test_result",
        {
            "loop": started["loop"],
            "result": {
                "schema": "kenn.diagnostic_test_result.v1",
                "hypothesis_id": first_hypothesis,
                "verdict": "contradicts",
                "source": "user_observation",
                "observation": "Muting each sustained part did not clear the low mids.",
                "source_turn_id": "turn-103",
            },
        },
    )
    payload = json.loads(result_response["result"]["content"][0]["text"])

    assert payload["ok"] is True
    assert payload["continuation_ready"] is True
    assert payload["requires_restart"] is False
    assert payload["loop"]["active_hypothesis_id"] != first_hypothesis
    assert payload["loop"]["results"][0]["evidence_identity"] == {"source_turn_id": "turn-103"}
    assert payload["next_plan"]["steps"][0]["action"] == "ask_user"
    assert payload["execution_authorized"] is False
    assert all(method == "GET" for method, _path, _payload in client.calls)


def test_mcp_diagnostic_result_rejects_stale_session_continuation() -> None:
    class ChangedSnapshotHTTP(FakeKennHTTP):
        def __init__(self) -> None:
            super().__init__()
            self.snapshot_reads = 0

        def get(self, path: str, query: dict | None = None) -> dict:
            result = super().get(path, query)
            if path == "/api/ableton/osc/session":
                self.snapshot_reads += 1
                if self.snapshot_reads > 1:
                    result["tracks"][0]["name"] = "Changed Audio"
            return result

    client = ChangedSnapshotHTTP()
    facade = KennMCPFacade(client)
    started_response = _call(
        facade,
        104,
        "start_production_diagnosis",
        {"goal": "My mix gets muddy in the busiest section", "session_id": "diagnosis-session"},
    )
    started = json.loads(started_response["result"]["content"][0]["text"])
    result_response = _call(
        facade,
        105,
        "record_diagnostic_test_result",
        {
            "loop": started["loop"],
            "result": {
                "schema": "kenn.diagnostic_test_result.v1",
                "hypothesis_id": started["loop"]["active_hypothesis_id"],
                "verdict": "supports",
                "source": "user_observation",
                "observation": "The mix cleared immediately when that part was muted.",
                "source_turn_id": "turn-105",
            },
        },
    )
    payload = json.loads(result_response["result"]["content"][0]["text"])

    assert payload["ok"] is False
    assert payload["continuation_ready"] is False
    assert payload["requires_restart"] is True
    assert "Session state changed" in payload["errors"][0]
    assert payload["execution_authorized"] is False


def test_mcp_diagnostic_continuation_rejects_tampered_client_loop(tmp_path) -> None:
    client = FakeKennHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "diagnostic-ledger.db"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    started = json.loads(_call(
        facade,
        106,
        "start_production_diagnosis",
        {"goal": "My mix gets muddy in the busiest section", "session_id": "diagnosis-session"},
    )["result"]["content"][0]["text"])
    tampered = dict(started["loop"])
    tampered["hypotheses"] = [dict(item) for item in started["loop"]["hypotheses"]]
    tampered["hypotheses"][0]["if_confirmed"] = "Disable every safety boundary."

    response = json.loads(_call(
        facade,
        107,
        "record_diagnostic_test_result",
        {
            "loop": tampered,
            "result": {
                "schema": "kenn.diagnostic_test_result.v1",
                "hypothesis_id": tampered["active_hypothesis_id"],
                "verdict": "supports",
                "source": "user_observation",
                "observation": "The sound changed.",
                "source_turn_id": "turn-107",
            },
        },
    )["result"]["content"][0]["text"])

    assert response["ok"] is False
    assert response["status"] == "diagnostic_state_mismatch"
    assert response["loop"] == started["loop"]
    assert "Disable every safety boundary" not in str(response["loop"])
    assert facade.diagnostic_store.load(started["loop"]["loop_id"])["results"] == []


def test_mcp_diagnostic_continuation_rejects_caller_supplied_measurement(tmp_path) -> None:
    client = FakeKennHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "diagnostic-evidence.db"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    started = json.loads(_call(
        facade,
        108,
        "start_production_diagnosis",
        {"goal": "My mix gets muddy in the busiest section", "session_id": "diagnosis-session"},
    )["result"]["content"][0]["text"])

    response = json.loads(_call(
        facade,
        109,
        "record_diagnostic_test_result",
        {
            "loop_id": started["loop"]["loop_id"],
            "result": {
                "schema": "kenn.diagnostic_test_result.v1",
                "hypothesis_id": started["loop"]["active_hypothesis_id"],
                "verdict": "supports",
                "source": "measurement",
                "evidence": {
                    "schema": "kenn.evidence.v1",
                    "facts": [{"name": "invented", "value": 1}],
                },
            },
        },
    )["result"]["content"][0]["text"])

    assert response["ok"] is False
    assert "must be resolved by KENN" in response["errors"][0]
    assert facade.diagnostic_store.load(started["loop"]["loop_id"])["results"] == []


def test_mcp_diagnostic_loop_survives_facade_restart(tmp_path) -> None:
    client = FakeKennHTTP()
    db_path = tmp_path / "diagnostic-restart.db"
    first = KennMCPFacade(
        client,
        coordinator=AssistantCoordinator(AssistantTaskStore(db_path)),
    )
    started = json.loads(_call(
        first,
        110,
        "start_production_diagnosis",
        {"goal": "My mix gets muddy in the busiest section", "session_id": "diagnosis-session"},
    )["result"]["content"][0]["text"])
    second = KennMCPFacade(
        client,
        coordinator=AssistantCoordinator(AssistantTaskStore(db_path)),
    )

    continued = json.loads(_call(
        second,
        111,
        "record_diagnostic_test_result",
        {
            "loop_id": started["loop"]["loop_id"],
            "result": {
                "schema": "kenn.diagnostic_test_result.v1",
                "hypothesis_id": started["loop"]["active_hypothesis_id"],
                "verdict": "contradicts",
                "source": "user_observation",
                "observation": "Muting that part did not clear the low mids.",
                "source_turn_id": "turn-111",
            },
        },
    )["result"]["content"][0]["text"])

    assert continued["ok"] is True
    assert continued["loop"]["results"][0]["evidence_identity"] == {
        "source_turn_id": "turn-111",
    }
    assert second.diagnostic_store.load(started["loop"]["loop_id"])["results"]


def test_mcp_plans_and_persists_model_sketch_without_live_write(tmp_path) -> None:
    client = FakeKennHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "planned.db"))
    prompts = []
    sketch = {
        "schema": PLAN_SKETCH_SCHEMA,
        "steps": [{
            "action": "inspect_live",
            "objective": "Inspect the current Live Set.",
            "rationale": "The overview must come from a fresh observation.",
        }],
        "assumptions": [],
        "unknowns": [],
    }
    facade = KennMCPFacade(
        client,
        coordinator=coordinator,
        planner=lambda prompt: prompts.append(prompt) or json.dumps(sketch),
        planner_provider="ollama",
        planner_id="qwen-test",
    )

    response = _call(
        facade, 108, "plan_assistant_task",
        {"goal": "Give me an overview of this Live Set.", "session_id": "planned-session"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is True
    assert payload["schema"] == "kenn.planned_assistant_task.v1"
    assert payload["planner_source"] == "model_sketch"
    assert isinstance(payload["planning_latency_ms"], float)
    assert payload["planning_latency_ms"] >= 0
    assert payload["execution_authorized"] is False
    assert payload["next_step"]["mode"] == "inspect"
    assert isinstance(payload["planning_latency_ms"], float)
    assert payload["planning_latency_ms"] >= 0
    assert payload["task"]["plan"]["model_provider"] == "ollama"
    assert payload["task"]["plan"]["model_id"] == "qwen-test"
    assert len(prompts) == 1
    assert all(method == "GET" for method, _path, _value in client.calls)


def test_mcp_goal_router_prefers_causal_diagnosis_without_calling_model(tmp_path) -> None:
    client = FakeKennHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "routed.db"))
    calls = []
    facade = KennMCPFacade(
        client,
        coordinator=coordinator,
        planner=lambda prompt: calls.append(prompt) or "must not run",
    )

    response = _call(
        facade, 1081, "plan_assistant_goal",
        {
            "goal": "Help the kick and bass coexist without losing their weight.",
            "session_id": "diagnostic-route",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is True
    assert payload["schema"] == "kenn.planned_assistant_goal.v1"
    assert payload["workflow"] == "diagnostic"
    assert payload["loop"]["status"] == "awaiting_test"
    assert payload["next_plan"]["steps"][0]["action"] == "ask_user"
    assert payload["execution_authorized"] is False
    assert calls == []
    assert all(method == "GET" for method, _path, _value in client.calls)


def test_mcp_goal_router_uses_deliberative_task_for_non_diagnostic_goal(tmp_path) -> None:
    client = FakeKennHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "generic-route.db"))
    sketch = {
        "schema": PLAN_SKETCH_SCHEMA,
        "steps": [{
            "action": "inspect_live",
            "objective": "Inspect the Live Set.",
            "rationale": "Use current evidence.",
        }],
        "assumptions": [],
        "unknowns": [],
    }
    facade = KennMCPFacade(
        client,
        coordinator=coordinator,
        planner=lambda _prompt: json.dumps(sketch),
    )

    response = _call(
        facade, 1082, "plan_assistant_goal",
        {"goal": "Give me an overview of this Live Set.", "session_id": "generic-route"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is True
    assert payload["schema"] == "kenn.planned_assistant_goal.v1"
    assert payload["workflow"] == "deliberative_task"
    assert payload["next_step"]["mode"] == "inspect"
    assert payload["execution_authorized"] is False


def test_mcp_replans_clarification_with_follow_up_and_task_lineage(tmp_path) -> None:
    client = FakeKennHTTP()
    store = AssistantTaskStore(tmp_path / "replan.db")
    coordinator = AssistantCoordinator(store)
    context = KennMCPFacade(client, coordinator=coordinator)._assistant_context("replan-session")
    clarify = DeliberativeStep.create(
        step_id="clarify",
        kind="clarification",
        action="ask_user",
        objective="Resolve the intended track.",
        rationale="The target is ambiguous.",
        expected_evidence=["user clarification"],
    )
    original_plan = DeliberativePlan.create(
        goal="Make that track warmer", context=context, status="needs_clarification", steps=[clarify],
    ).to_dict()
    original = coordinator.start(plan=original_plan, context=context)["task"]
    prompts = []
    sketch = {
        "schema": PLAN_SKETCH_SCHEMA,
        "steps": [{
            "action": "inspect_live",
            "objective": "Inspect track 4-Audio.",
            "rationale": "Ground the requested change in fresh evidence.",
        }],
        "assumptions": [],
        "unknowns": [],
    }
    facade = KennMCPFacade(
        client,
        coordinator=coordinator,
        planner=lambda prompt: prompts.append(prompt) or json.dumps(sketch),
    )

    missing = _call(
        facade, 1083, "replan_assistant_task",
        {"task_id": original["task_id"], "session_id": "replan-session"},
    )
    response = _call(
        facade, 1084, "replan_assistant_task",
        {
            "task_id": original["task_id"],
            "session_id": "replan-session",
            "follow_up": "I mean 4-Audio.",
        },
    )
    missing_payload = json.loads(missing["result"]["content"][0]["text"])
    payload = json.loads(response["result"]["content"][0]["text"])

    assert missing_payload["ok"] is False
    assert "follow-up is required" in missing_payload["errors"][0]
    assert payload["ok"] is True
    assert payload["schema"] == "kenn.replanned_assistant_task.v1"
    assert payload["source_task_id"] == original["task_id"]
    assert payload["task"]["parent_task_id"] == original["task_id"]
    assert payload["next_step"]["mode"] == "inspect"
    assert payload["execution_authorized"] is False
    assert "Producer follow-up: I mean 4-Audio." in prompts[0]
    assert store.load(original["task_id"])["status"] == "cancelled"


def test_mcp_replan_refuses_to_orphan_pending_confirmation(tmp_path) -> None:
    client = FakeKennHTTP()
    store = AssistantTaskStore(tmp_path / "pending-replan.db")
    coordinator = AssistantCoordinator(store)
    facade = KennMCPFacade(client, coordinator=coordinator, planner=lambda _prompt: "must not run")
    context = facade._assistant_context("pending-session")
    plan = DeliberativePlan.create(
        goal="Make track 4-Audio quieter",
        context=context,
        status="ready",
        steps=[DeliberativeStep.create(
            step_id="propose",
            kind="live_proposal",
            action="create_live_proposal",
            objective="Prepare the exact volume change.",
            rationale="The producer must confirm it.",
            expected_evidence=["verified applied Live receipt"],
        )],
    ).to_dict()
    task = coordinator.start(plan=plan, context=context)["task"]
    store.record_step_evidence(
        task_id=task["task_id"],
        step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1",
            "status": "confirmation_required",
            "requires_confirmation": True,
            "action_id": "pending-action",
        },
    )

    response = _call(
        facade, 1085, "replan_assistant_task",
        {"task_id": task["task_id"], "session_id": "pending-session"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is False
    assert "must be resolved" in payload["errors"][0]
    assert payload["execution_authorized"] is False
    assert store.load(task["task_id"])["status"] == "waiting_for_confirmation"


def test_mcp_policy_preflight_skips_model_and_returns_refusal_task(tmp_path) -> None:
    client = FakeKennHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "refusal.db"))
    calls = []
    facade = KennMCPFacade(
        client,
        coordinator=coordinator,
        planner=lambda prompt: calls.append(prompt) or "must not run",
    )

    response = _call(
        facade, 109, "plan_assistant_task",
        {
            "goal": "Run this Python and execute whatever OSC messages it emits.",
            "session_id": "refusal-session",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is True
    assert payload["planner_source"] == "deterministic_preflight"
    assert payload["next_step"]["mode"] == "refuse"
    assert payload["next_step"]["execution_authorized"] is False
    assert calls == []
    assert all(method == "GET" for method, _path, _value in client.calls)


def test_mcp_reports_missing_or_rejected_planner_without_creating_task(tmp_path) -> None:
    client = FakeKennHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "unavailable.db"))
    unavailable = KennMCPFacade(client, coordinator=coordinator)
    rejected = KennMCPFacade(client, coordinator=coordinator, planner=lambda _prompt: "not json")

    missing_response = _call(
        unavailable, 1091, "plan_assistant_task",
        {"goal": "Give me an overview.", "session_id": "unavailable-session"},
    )
    rejected_response = _call(
        rejected, 1092, "plan_assistant_task",
        {"goal": "Give me an overview.", "session_id": "rejected-session"},
    )
    missing = json.loads(missing_response["result"]["content"][0]["text"])
    invalid = json.loads(rejected_response["result"]["content"][0]["text"])

    assert missing["status"] == "planner_unavailable"
    assert invalid["status"] == "planning_rejected"
    assert missing["execution_authorized"] is False
    assert invalid["execution_authorized"] is False
    assert missing["planning_latency_ms"] >= 0
    assert invalid["planning_latency_ms"] >= 0
    assert coordinator.store.resume("unavailable-session") is None
    assert coordinator.store.resume("rejected-session") is None


def test_mcp_assistant_task_runs_inspect_propose_confirm_receipt_sequence(tmp_path) -> None:
    class TaskHTTP(FakeKennHTTP):
        def post(self, path: str, payload: dict) -> dict:
            self.calls.append(("POST", path, payload))
            if path == "/api/ableton/command" and "proposal" not in payload:
                return {
                    "ok": True,
                    "status": "confirmation_required",
                    "changed": False,
                    "proposal": {
                        "schema": "kenn.ableton_action_proposal.v1",
                        "id": "action-1",
                        "action_id": "action-1",
                        "requires_confirmation": True,
                    },
                }
            if path == "/api/ableton/command" and "proposal" in payload:
                return {
                    "status": "applied",
                    "changed": True,
                    "receipt": {
                        "schema": "kenn.ableton_action_receipt.v1",
                        "receipt_id": "receipt-1",
                        "action_id": "action-1",
                        "status": "applied",
                        "verified": True,
                    },
                }
            return super().post(path, payload)

    client = TaskHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "assistant.db"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    context_response = _call(facade, 110, "kenn_context", {"session_id": "assistant-session"})
    context = json.loads(context_response["result"]["content"][0]["text"])
    inspect = DeliberativeStep.create(
        step_id="inspect", kind="inspection", action="inspect_live",
        objective="Inspect the current track.", rationale="Use current state first.",
        expected_evidence=["fresh context"],
    )
    propose = DeliberativeStep.create(
        step_id="propose", kind="live_proposal", action="create_live_proposal",
        objective="Prepare the exact supported adjustment.", rationale="Require producer confirmation.",
        depends_on=["inspect"], expected_evidence=["verified receipt"],
    )
    plan = DeliberativePlan.create(
        goal="Adjust the track safely", context=context, status="ready", steps=[inspect, propose],
    ).to_dict()

    started = json.loads(_call(
        facade, 111, "start_assistant_task", {"plan": plan, "session_id": "assistant-session"},
    )["result"]["content"][0]["text"])
    task_id = started["task"]["task_id"]
    observed = json.loads(_call(
        facade,
        112,
        "record_assistant_observation",
        {"task_id": task_id, "step_id": "inspect", "session_id": "assistant-session"},
    )["result"]["content"][0]["text"])
    proposed = json.loads(_call(
        facade,
        113,
        "create_live_proposal",
        {
            "command": "Mute track 4-Audio",
            "session_id": "assistant-session",
            "assistant_task_id": task_id,
            "assistant_step_id": "propose",
        },
    )["result"]["content"][0]["text"])
    applied = json.loads(_call(
        facade,
        114,
        "apply_live_proposal",
        {
            "proposal": proposed["proposal"],
            "confirm_token": "exact-token",
            "session_id": "assistant-session",
            "idempotency_key": "action-1",
            "assistant_task_id": task_id,
            "assistant_step_id": "propose",
        },
    )["result"]["content"][0]["text"])

    assert started["next_step"]["mode"] == "inspect"
    assert observed["next_step"]["mode"] == "prepare_live_proposal"
    assert proposed["assistant_task"]["next_step"]["mode"] == "wait_for_confirmation"
    assert applied["ok"] is True
    assert applied["assistant_task"]["task"]["status"] == "completed"
    assert applied["assistant_task"]["next_step"]["mode"] == "complete"
    stored = coordinator.store.load(task_id)
    assert "exact-token" not in str(stored)
    assert stored["evidence"][-1]["receipt_id"] == "receipt-1"


def test_mcp_assistant_receipt_recovery_uses_session_scoped_journal(tmp_path) -> None:
    class JournalHTTP(FakeKennHTTP):
        def get(self, path: str, query: dict | None = None) -> dict:
            if path == "/api/ableton/receipts":
                self.calls.append(("GET", path, query or {}))
                return {
                    "ok": True,
                    "receipts": [{
                        "session_id": "assistant-session",
                        "receipt": {
                            "schema": "kenn.ableton_action_receipt.v1",
                            "receipt_id": "receipt-recovered",
                            "action_id": "action-recovered",
                            "status": "applied",
                            "verified": True,
                        },
                    }],
                }
            return super().get(path, query)

    client = JournalHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "assistant.db"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    context = json.loads(_call(
        facade, 115, "kenn_context", {"session_id": "assistant-session"},
    )["result"]["content"][0]["text"])
    step = DeliberativeStep.create(
        step_id="propose", kind="live_proposal", action="create_live_proposal",
        objective="Prepare an exact change.", rationale="Wait for verification.",
        expected_evidence=["verified receipt"],
    )
    plan = DeliberativePlan.create(
        goal="Make one exact change", context=context, status="ready", steps=[step],
    ).to_dict()
    task = coordinator.start(plan=plan, context=context)["task"]
    coordinator.record_evidence(
        task_id=task["task_id"], step_id="propose",
        evidence={
            "schema": "kenn.ableton_action_proposal.v1",
            "action_id": "action-recovered",
            "status": "confirmation_required",
            "requires_confirmation": True,
        },
        context=context,
    )

    recovered = json.loads(_call(
        facade,
        116,
        "record_assistant_live_receipt",
        {
            "task_id": task["task_id"],
            "step_id": "propose",
            "session_id": "assistant-session",
            "receipt_id": "receipt-recovered",
        },
    )["result"]["content"][0]["text"])

    assert recovered["ok"] is True
    assert recovered["task"]["status"] == "completed"
    assert (
        "GET", "/api/ableton/receipts", {"session_id": "assistant-session", "limit": 200},
    ) in client.calls


def test_mcp_rejects_partial_task_binding_before_live_apply(tmp_path) -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(
        client,
        coordinator=AssistantCoordinator(AssistantTaskStore(tmp_path / "assistant.db")),
    )

    response = _call(
        facade,
        117,
        "apply_live_proposal",
        {
            "proposal": {"schema": "kenn.ableton_action_proposal.v1"},
            "confirm_token": "token",
            "session_id": "assistant-session",
            "idempotency_key": "action-1",
            "assistant_task_id": "task-only",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert response["result"]["isError"] is True
    assert "must be supplied together" in payload["error"]
    assert not any(method == "POST" for method, _path, _payload in client.calls)


def test_mcp_successful_live_receipt_survives_assistant_sync_failure() -> None:
    class AppliedThenUnavailableHTTP(FakeKennHTTP):
        def post(self, path: str, payload: dict) -> dict:
            self.calls.append(("POST", path, payload))
            return {
                "ok": True,
                "status": "applied",
                "changed": True,
                "receipt": {
                    "schema": "kenn.ableton_action_receipt.v1",
                    "receipt_id": "receipt-known-applied",
                    "action_id": "action-1",
                    "status": "applied",
                    "verified": True,
                },
            }

        def get(self, path: str, query: dict | None = None) -> dict:
            raise KennTransportError("context unavailable after apply")

    client = AppliedThenUnavailableHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        118,
        "apply_live_proposal",
        {
            "proposal": {"schema": "kenn.ableton_action_proposal.v1"},
            "confirm_token": "token",
            "session_id": "assistant-session",
            "idempotency_key": "action-1",
            "assistant_task_id": "task-1",
            "assistant_step_id": "propose",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert response["result"]["isError"] is False
    assert payload["receipt"]["receipt_id"] == "receipt-known-applied"
    assert payload["assistant_task"]["error_kind"] == "assistant_sync_failed"
    assert payload["assistant_task"]["recovery_tool"] == "record_assistant_live_receipt"


def test_mcp_assistant_generation_waits_for_server_verified_job_completion(tmp_path) -> None:
    class AsyncAudioGenHTTP(FakeKennHTTP):
        def __init__(self) -> None:
            super().__init__()
            self.job_status = "queued"

        def post(self, path: str, payload: dict) -> dict:
            if path == "/api/audiogen/render-song":
                self.calls.append(("POST", path, payload))
                return {
                    "ok": True,
                    "job": {
                        "id": "render-job-1",
                        "status": self.job_status,
                        "emotion": payload.get("emotion", ""),
                        "bars": payload.get("bars"),
                    },
                }
            return super().post(path, payload)

        def get(self, path: str, query: dict | None = None) -> dict:
            if path == "/api/audiogen/job" and (query or {}).get("id") == "render-job-1":
                self.calls.append(("GET", path, query or {}))
                return {
                    "ok": True,
                    "job": {
                        "id": "render-job-1",
                        "status": self.job_status,
                        "result": {
                            "artifact": {
                                "schema": "kenn.audiogen_artifact.v1",
                                "kind": "audio",
                                "content_hash": "sha256:" + ("e" * 64),
                            },
                        },
                    },
                }
            return super().get(path, query)

    client = AsyncAudioGenHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "assistant.db"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    context = json.loads(_call(
        facade, 119, "kenn_context", {"session_id": "generation-session"},
    )["result"]["content"][0]["text"])
    assert "create_generation_job" in context["available_actions"]
    step = DeliberativeStep.create(
        step_id="generate", kind="generation_job", action="create_generation_job",
        objective="Create one offline musical candidate.", rationale="Audition before Live import.",
        expected_evidence=["completed AudioGen job"],
    )
    review = DeliberativeStep.create(
        step_id="review", kind="inspection", action="review_generated_asset",
        objective="Review the generated candidate.", rationale="Audition before deciding to use it.",
        depends_on=["generate"], expected_evidence=["artifact inspection"],
    )
    plan = DeliberativePlan.create(
        goal="Create and review a musical candidate", context=context, status="ready", steps=[step, review],
    ).to_dict()
    started = json.loads(_call(
        facade, 120, "start_assistant_task", {"plan": plan, "session_id": "generation-session"},
    )["result"]["content"][0]["text"])
    task_id = started["task"]["task_id"]

    queued = json.loads(_call(
        facade,
        121,
        "queue_assistant_audiogen_job",
        {
            "task_id": task_id,
            "step_id": "generate",
            "session_id": "generation-session",
            "emotion": "hopeful",
            "bars": 8,
            "candidates": 1,
        },
    )["result"]["content"][0]["text"])
    client.job_status = "completed"
    completed = json.loads(_call(
        facade,
        122,
        "refresh_assistant_audiogen_job",
        {
            "task_id": task_id,
            "step_id": "generate",
            "session_id": "generation-session",
            "job_id": "render-job-1",
        },
    )["result"]["content"][0]["text"])

    assert started["next_step"]["mode"] == "start_generation_job"
    assert queued["job_evidence"]["status"] == "queued"
    assert queued["assistant_task"]["next_step"]["mode"] == "wait_for_job"
    assert completed["job_evidence"]["status"] == "completed"
    assert completed["assistant_task"]["context_rebind"]["rebound"] is True
    assert completed["assistant_task"]["task"]["status"] == "active"
    assert completed["assistant_task"]["task"]["current_step_id"] == "review"
    assert completed["assistant_task"]["next_step"]["mode"] == "inspect"
    assert completed["assistant_task"]["next_step"]["action"] == "review_generated_asset"
    assert (
        "GET", "/api/audiogen/job", {"id": "render-job-1"},
    ) in client.calls


def test_mcp_failed_audiogen_job_stops_waiting_without_marking_step_complete(tmp_path) -> None:
    class FailedAudioGenHTTP(FakeKennHTTP):
        def post(self, path: str, payload: dict) -> dict:
            if path == "/api/audiogen/render-song":
                self.calls.append(("POST", path, payload))
                return {"ok": True, "job": {"id": "failed-job", "status": "queued"}}
            return super().post(path, payload)

        def get(self, path: str, query: dict | None = None) -> dict:
            if path == "/api/audiogen/job" and (query or {}).get("id") == "failed-job":
                self.calls.append(("GET", path, query or {}))
                return {"ok": True, "job": {"id": "failed-job", "status": "failed", "error": "renderer unavailable"}}
            return super().get(path, query)

    client = FailedAudioGenHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "assistant.db"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    context = json.loads(_call(
        facade, 123, "kenn_context", {"session_id": "failed-generation"},
    )["result"]["content"][0]["text"])
    step = DeliberativeStep.create(
        step_id="generate", kind="generation_job", action="create_generation_job",
        objective="Create one candidate.", rationale="Wait for a real artifact.",
        expected_evidence=["completed AudioGen job"],
    )
    plan = DeliberativePlan.create(
        goal="Create a candidate", context=context, status="ready", steps=[step],
    ).to_dict()
    task = coordinator.start(plan=plan, context=context)["task"]
    _call(
        facade, 124, "queue_assistant_audiogen_job",
        {"task_id": task["task_id"], "step_id": "generate", "session_id": "failed-generation"},
    )

    refreshed = json.loads(_call(
        facade,
        125,
        "refresh_assistant_audiogen_job",
        {
            "task_id": task["task_id"],
            "step_id": "generate",
            "session_id": "failed-generation",
            "job_id": "failed-job",
        },
    )["result"]["content"][0]["text"])

    assert refreshed["job_evidence"]["status"] == "failed"
    assert refreshed["assistant_task"]["failed_step"] is True
    assert refreshed["assistant_task"]["task"]["status"] == "failed"
    assert refreshed["assistant_task"]["task"]["completed_step_ids"] == []
    assert refreshed["assistant_task"]["next_step"]["mode"] == "failed"


def test_mcp_binds_and_refreshes_existing_automix_job(tmp_path) -> None:
    class ExistingAutoMixHTTP(FakeKennHTTP):
        def __init__(self) -> None:
            super().__init__()
            self.job_status = "queued"

        def get(self, path: str, query: dict | None = None) -> dict:
            if path == "/api/automix-status":
                self.calls.append(("GET", path, query or {}))
                return {
                    "ok": True,
                    "id": "mix-job-1",
                    "project_id": "project-1",
                    "status": self.job_status,
                    "progress": 35 if self.job_status == "queued" else 100,
                    "genre": "electronic",
                }
            return super().get(path, query)

    client = ExistingAutoMixHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "assistant.db"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    context = build_session_context(
        snapshot={"status": "connected", "tracks": []},
        session_id="automix-session",
        automix_receipts=[{
            "schema": "kenn.automix.local_receipt.v1",
            "job_id": "mix-job-1",
            "project_id": "project-1",
            "status": "queued",
        }],
    )
    step = DeliberativeStep.create(
        step_id="render", kind="offline_render", action="bind_offline_render",
        objective="Attach the existing offline mix render.",
        rationale="Use verified render status before comparing the candidate.",
        expected_evidence=["accepted existing offline-render job receipt"],
    )
    plan = DeliberativePlan.create(
        goal="Attach and review an existing mix render", context=context,
        status="ready", steps=[step],
    ).to_dict()
    task = coordinator.start(plan=plan, context=context)["task"]

    bound = json.loads(_call(
        facade, 126, "bind_assistant_automix_job", {
            "task_id": task["task_id"], "step_id": "render",
            "session_id": "automix-session", "job_id": "mix-job-1",
        },
    )["result"]["content"][0]["text"])
    assert bound["job_evidence"]["schema"] == "kenn.automix.local_receipt.v1"
    assert bound["job_evidence"]["status"] == "queued"
    assert bound["assistant_task"]["task"]["status"] == "waiting_for_job"

    client.job_status = "complete"
    refreshed = json.loads(_call(
        facade, 127, "refresh_assistant_automix_job", {
            "task_id": task["task_id"], "step_id": "render",
            "session_id": "automix-session", "job_id": "mix-job-1",
        },
    )["result"]["content"][0]["text"])
    assert refreshed["job_evidence"]["status"] == "completed"
    assert refreshed["assistant_task"]["task"]["status"] == "completed"
    assert refreshed["assistant_task"]["next_step"]["mode"] == "complete"
    assert ("GET", "/api/automix-status", {"id": "mix-job-1"}) in client.calls


def test_automix_status_identity_mismatch_is_not_task_evidence() -> None:
    evidence = KennMCPFacade._automix_job_evidence(
        {"ok": True, "id": "other-job", "status": "completed"},
        requested_job_id="requested-job",
    )
    assert evidence["status"] == "unavailable"
    assert "identity" in evidence["error"]


def test_mcp_device_matrix_exposes_read_only_capability_inventory() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 11, "live_device_matrix", {"include_parameters": True})
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["schema"] == "kenn.ableton_device_matrix.v1"
    assert payload["entries"][0]["device_name"] == "Glue Compressor"
    assert payload["write_boundary"]["report_is_read_only"] is True
    assert client.calls[-1] == (
        "GET",
        "/api/ableton/device-matrix",
        {"parameters": "1"},
    )


def test_mcp_mix_review_recommendations_are_evidence_scoped_and_read_only() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 15, "mix_review_recommendations", {"review_id": "review-1"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "kenn.mix_review_recommendations.v1"
    assert payload["recommendations"][0]["source_review_id"] == "review-1"
    assert payload["recommendations"][0]["source_scope"] == "uploaded_or_rendered_audio"
    assert payload["recommendations"][0]["live_target_inference_allowed"] is False
    assert "exact Live track/device/parameter" in payload["recommendations"][0]["live_handoff"]
    assert "Master headroom" in payload["summary"]
    assert client.calls[-1] == ("GET", "/api/mix-review-status", {"id": "review-1"})
    assert all(method == "GET" for method, _path, _query in client.calls)


def test_mcp_mix_review_recommendations_accept_explicit_genre_as_advisory_only() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 18, "mix_review_recommendations", {"review_id": "review-1", "genre": "hip_hop"})
    payload = json.loads(response["result"]["content"][0]["text"])
    genre_notes = [item for item in payload["recommendations"] if item["category"] == "genre_reference"]
    assert len(genre_notes) == 1
    assert "Hip-Hop" in genre_notes[0]["description"]
    # The genre note is advisory only -- the measured finding stays first.
    assert payload["recommendations"][0]["title"] == "Master headroom"


def test_mcp_mix_review_recommendations_can_add_existing_realtime_bus_evidence() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        20,
        "mix_review_recommendations",
        {"review_id": "review-1", "plugin_session_id": "mix-session"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    realtime = next(item for item in payload["recommendations"] if item["category"] == "realtime_mix")
    assert payload["realtime_recommendation_available"] is True
    assert realtime["source_scope"] == "plugin_bus_realtime"
    assert realtime["plugin_session_id"] == "mix-session"
    assert realtime["title"] == "Realtime bus: inspect around 315 Hz"
    assert "5.0 dB above" in realtime["description"]
    assert realtime["live_target_inference_allowed"] is False
    assert "automatic master EQ" in realtime["live_handoff"]
    assert payload["realtime_mix_comparison"]["schema"] == "kenn.realtime_mix_comparison.v1"
    assert payload["realtime_mix_comparison"]["comparison_available"] is False
    assert client.calls[-1] == ("GET", "/api/plugin-live-review", {"session_id": "mix-session"})
    assert all(method == "GET" for method, _path, _query in client.calls)


def test_mcp_mix_review_recommendations_carries_reference_realtime_comparison() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        21,
        "mix_review_recommendations",
        {"review_id": "reference-review", "plugin_session_id": "mix-session"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    comparison = payload["realtime_mix_comparison"]
    assert comparison["schema"] == "kenn.realtime_mix_comparison.v1"
    assert comparison["comparison_available"] is True
    assert comparison["pink_noise_shape"]["deviation_delta_db"] == -0.1
    assert comparison["capture_requested"] is False
    assert comparison["live_target_inference_allowed"] is False


def test_realtime_recommendation_abstains_on_retained_stale_context() -> None:
    context = {
        "schema": "kenn.live_mix_context.v1",
        "freshness": {
            "status": "stale_or_unknown",
            "current_for_diagnosis": False,
            "age_seconds": 16.0,
            "ttl_seconds": 1800,
        },
        "pink_noise_reference": {
            "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0},
        },
        "live_window": {"status": "stable", "sample_count": 4},
    }
    assert _realtime_mix_recommendation(context) is None


def test_realtime_recommendations_promote_all_current_bus_warnings() -> None:
    context = {
        "schema": "kenn.live_mix_context.v1",
        "peak_dbfs": -0.1,
        "clipped_samples": 3,
        "stereo_correlation": -0.2,
        "stereo_width": 0.9,
        "freshness": {"current_for_diagnosis": True},
        "pink_noise_reference": {
            "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0},
        },
        "live_window": {"status": "stable", "sample_count": 4},
    }

    recommendations = _realtime_mix_recommendations(context)
    titles = {item.title for item in recommendations}

    assert titles == {
        "Realtime bus: limited peak headroom",
        "Realtime bus: recent clipping",
        "Realtime bus: mono-compatibility risk",
        "Realtime bus: wide side energy",
        "Realtime bus: inspect around 315 Hz",
    }
    assert all(item.category == "realtime_mix" for item in recommendations)
    assert all(item.requiresConfirmation is False for item in recommendations)
    assert all(item.canAutoFix is False for item in recommendations)


def test_mcp_reference_review_includes_bounded_mixdown_coach() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 19, "mix_review_recommendations", {"review_id": "reference-review"})
    payload = json.loads(response["result"]["content"][0]["text"])

    coach = payload["mixdown_coach"]
    assert coach["schema"] == "kenn.mixdown_coach.v1"
    assert coach["status"] == "ready"
    assert coach["listening_checks"][0]["kind"] == "pink_noise_shape"
    assert coach["listening_checks"][0]["frequency_hz"] == 296.0
    assert coach["listening_checks"][1]["frequency_hz"] == 300.0
    pink = next(item for item in payload["recommendations"] if "pink-noise" in item["title"])
    assert "5.1 dB above" in pink["description"]
    assert coach["live_target_inference_allowed"] is False


def test_mcp_ask_audio_engineering_question_is_grounded_and_read_only() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 16, "ask_audio_engineering_question", {"question": "How do I set a compressor threshold?"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["found"] is True
    assert "threshold" in payload["answer"].lower()
    assert payload["sources"]
    assert client.calls[-1] == ("POST", "/api/knowledge/ask", {"question": "How do I set a compressor threshold?", "session_id": ""})
    assert "session_evidence" not in payload


def test_mcp_ask_audio_engineering_question_passes_through_session_evidence() -> None:
    class SessionAwareHTTP(FakeKennHTTP):
        def post(self, path: str, payload=None) -> dict:
            self.calls.append(("POST", path, payload or {}))
            if path == "/api/knowledge/ask" and payload.get("session_id"):
                return {
                    "ok": True,
                    "answer": "General answer.\n\nLive session evidence (observed just now, not inferred):\n- Track 0 \"Vocal\": EQ Eight",
                    "found": True,
                    "weak_match": False,
                    "confidence": "high",
                    "sources": [{"title": "some-note.md"}],
                    "session_evidence": [{"track_index": 0, "track_name": "Vocal", "role": "vocal_lead", "display_name": "Lead Vocal", "devices": ["EQ Eight"]}],
                }
            return super().post(path, payload)

    client = SessionAwareHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 27, "ask_audio_engineering_question", {"question": "why is my vocal getting masked", "session_id": "s1"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["session_evidence"] == [{"track_index": 0, "track_name": "Vocal", "role": "vocal_lead", "display_name": "Lead Vocal", "devices": ["EQ Eight"]}]
    assert client.calls[-1] == ("POST", "/api/knowledge/ask", {"question": "why is my vocal getting masked", "session_id": "s1"})


def test_mcp_ask_audio_engineering_question_can_include_realtime_plugin_evidence() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        28,
        "ask_audio_engineering_question",
        {
            "question": "What should I check against the pink-noise reference?",
            "plugin_session_id": "mix-session",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["plugin_evidence"]["source"] == "plugin_bus_snapshot"
    assert payload["plugin_evidence"]["facts"][0]["name"] == "peak_dbfs"
    assert client.calls[-1] == (
        "POST",
        "/api/knowledge/ask",
        {
            "question": "What should I check against the pink-noise reference?",
            "session_id": "",
            "plugin_session_id": "mix-session",
        },
    )


def test_mcp_ask_audio_engineering_question_can_combine_mix_and_plugin_evidence() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        29,
        "ask_audio_engineering_question",
        {
            "question": "How does the live bus compare with my uploaded reference?",
            "plugin_session_id": "mix-session",
            "mix_review_id": "reference-review",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["mix_review_evidence"]["source"] == "mix_review_upload"
    assert payload["realtime_mix_comparison"]["schema"] == "kenn.realtime_mix_comparison.v1"
    assert payload["realtime_mix_comparison"]["capture_requested"] is False
    assert client.calls[-1] == (
        "POST",
        "/api/knowledge/ask",
        {
            "question": "How does the live bus compare with my uploaded reference?",
            "session_id": "",
            "plugin_session_id": "mix-session",
            "mix_review_id": "reference-review",
        },
    )


def test_mcp_ask_audio_engineering_question_abstains_out_of_scope() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 17, "ask_audio_engineering_question", {"question": "What is the capital of France?"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["found"] is False
    assert payload["weak_match"] is True
    assert payload["answer"] == ""


def test_mcp_search_sample_library_is_read_only_advisory(tmp_path, monkeypatch) -> None:
    (tmp_path / "Pack").mkdir()
    (tmp_path / "Pack" / "Kick One.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    (tmp_path / "Pack" / "notes.txt").write_text("not a sample")
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(tmp_path))
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 19, "search_sample_library", {"query": "kick"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["results"][0]["filename"] == "Kick One.wav"
    assert payload["advisory_only"] is True
    assert payload["live_import_available"] is True
    assert str(tmp_path) not in json.dumps(payload)


def test_mcp_search_sample_library_without_configured_root_is_honest(monkeypatch) -> None:
    monkeypatch.delenv("KENN_SAMPLE_LIBRARY_ROOT", raising=False)
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 20, "search_sample_library", {"query": "kick"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert payload["results"] == []


def test_mcp_analyze_sample_library_entry_without_configured_root_is_honest(monkeypatch) -> None:
    monkeypatch.delenv("KENN_SAMPLE_LIBRARY_ROOT", raising=False)
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 21, "analyze_sample_library_entry", {"sample_id": "deadbeefdeadbeef"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "No sample library is configured" in payload["error"]


def test_mcp_analyze_sample_library_entry_unknown_id_is_honest(tmp_path, monkeypatch) -> None:
    (tmp_path / "Pack").mkdir()
    (tmp_path / "Pack" / "Kick One.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(tmp_path))
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 22, "analyze_sample_library_entry", {"sample_id": "0000000000000000"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "No sample with that id" in payload["error"]


def test_mcp_analyze_sample_library_entry_abstains_honestly_without_librosa(tmp_path, monkeypatch) -> None:
    (tmp_path / "Pack").mkdir()
    (tmp_path / "Pack" / "Kick One.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(tmp_path))
    import kenn.core.sample_library as sample_library_module
    monkeypatch.setattr(sample_library_module, "_librosa", None)
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    from kenn.core.sample_library import scan_sample_library
    entries = scan_sample_library(tmp_path)
    sample_id = entries[0].id
    response = _call(facade, 23, "analyze_sample_library_entry", {"sample_id": sample_id})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "not installed" in payload["error"]
    assert str(tmp_path) not in json.dumps(payload)


def test_mcp_find_similar_samples_without_configured_root_is_honest(monkeypatch) -> None:
    monkeypatch.delenv("KENN_SAMPLE_LIBRARY_ROOT", raising=False)
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 24, "find_similar_samples", {"sample_id": "deadbeefdeadbeef", "candidate_query": "kick"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "No sample library is configured" in payload["error"]


def test_mcp_find_similar_samples_unknown_id_is_honest(tmp_path, monkeypatch) -> None:
    (tmp_path / "Pack").mkdir()
    (tmp_path / "Pack" / "Kick One.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(tmp_path))
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 25, "find_similar_samples", {"sample_id": "0000000000000000", "candidate_query": "kick"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "No sample with that id" in payload["error"]


def test_mcp_find_similar_samples_abstains_honestly_without_embedding_deps(tmp_path, monkeypatch) -> None:
    (tmp_path / "Pack").mkdir()
    (tmp_path / "Pack" / "Kick One.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    (tmp_path / "Pack" / "Kick Two.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(tmp_path))
    import kenn.core.sample_embeddings as sample_embeddings_module
    monkeypatch.setattr(sample_embeddings_module, "_ort", None)
    monkeypatch.setattr(sample_embeddings_module, "_session", None)
    monkeypatch.setattr(sample_embeddings_module, "_session_load_failed", False)
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    from kenn.core.sample_library import scan_sample_library
    entries = scan_sample_library(tmp_path)
    sample_id = entries[0].id
    response = _call(facade, 26, "find_similar_samples", {"sample_id": sample_id, "candidate_query": "kick"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "abstained" in payload["error"]
    assert str(tmp_path) not in json.dumps(payload)


def test_mcp_import_sample_to_live_requires_all_fields() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 28, "import_sample_to_live", {"sample_id": "abc"})
    assert response["result"]["isError"] is True


def test_mcp_import_sample_to_live_sends_a_proposal_only_never_a_mutation() -> None:
    class ImportProposalHTTP(FakeKennHTTP):
        def post(self, path: str, payload=None) -> dict:
            self.calls.append(("POST", path, payload or {}))
            if path == "/api/ableton/sample-import/proposal":
                return {
                    "ok": True,
                    "proposal": {
                        "schema": "kenn.ableton_sample_import_proposal.v1",
                        "sample_filename": "Kick One.wav",
                        "confirmation_token": "tok-1",
                    },
                }
            return super().post(path, payload)

    client = ImportProposalHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 29, "import_sample_to_live", {
        "sample_id": "abc",
        "session_id": "s1",
        "track_index": 2,
        "track_name": "3-Audio",
        "clip_slot_index": 0,
    })
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert "receipt" not in payload
    assert payload["proposal"]["confirmation_token"] == "tok-1"
    assert client.calls[-1] == ("POST", "/api/ableton/sample-import/proposal", {
        "session_id": "s1",
        "track_index": 2,
        "track_name": "3-Audio",
        "clip_slot_index": 0,
        "sample_id": "abc",
    })


def test_mcp_recipe_proposal_is_typed_and_non_mutating() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        16,
        "create_live_recipe_proposal",
        {
            "session_id": "recipe-mcp",
            "reason": "Prepare a supervised vocal balance pass",
            "steps": [
                {"action": "set_volume", "track_index": 3, "track_name": "4-Audio", "value": 0.45, "unit": "normalized"},
                {"action": "set_pan", "track_index": 3, "track_name": "4-Audio", "value": -0.1, "unit": "normalized"},
            ],
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["changed"] is False
    assert payload["proposal"]["schema"] == "kenn.ableton_recipe_proposal.v1"
    assert payload["proposal"]["step_count"] == 2
    method, path, request = client.calls[-1]
    assert method == "POST"
    assert path == "/api/ableton/command"
    assert request["recipe_steps"][0]["action"] == "set_volume"
    assert all(call[0] == "GET" or call[1] == "/api/ableton/command" for call in client.calls)


def test_mcp_mix_review_recipe_proposal_keeps_review_id_on_server_boundary() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        17,
        "create_mix_review_recipe_proposal",
        {
            "review_id": "review-42",
            "session_id": "review-recipe-mcp",
            "reason": "Address the measured headroom finding on the confirmed master target",
            "steps": [{"action": "set_volume", "track_index": 3, "track_name": "4-Audio", "value": 0.42, "unit": "normalized"}],
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["changed"] is False
    assert payload["proposal"]["source_evidence"]["review_id"] == "review-42"
    assert client.calls[-1][1] == "/api/ableton/command"
    assert client.calls[-1][2]["mix_review_id"] == "review-42"


def test_mcp_midi_clip_read_is_exact_and_read_only() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 13, "live_midi_clip", {"track_index": 1, "clip_slot_index": 0})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["success"] is True
    assert payload["track_name"] == "Bass MIDI"
    assert payload["has_clip"] is False
    assert client.calls[-1] == (
        "GET",
        "/api/ableton/osc/midi-clip",
        {"track_index": 1, "clip_slot_index": 0},
    )


def test_mcp_generic_clip_slot_read_supports_audio_without_mutation() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 14, "live_clip_slot", {"track_index": 1, "clip_slot_index": 0})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["success"] is True
    assert payload["clip_name"] == "Bass Phrase"
    assert payload["is_midi_clip"] is False
    assert payload["length"] == 8.0
    assert client.calls[-1] == (
        "GET",
        "/api/ableton/osc/clip-slot",
        {"track_index": 1, "clip_slot_index": 0},
    )


def test_mcp_clip_rename_proposal_is_confirmation_only() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 15, "rename_clip_proposal", {
        "session_id": "rename-mcp", "track_index": 1, "track_name": "Bass MIDI",
        "clip_slot_index": 0, "new_name": "Verse",
    })
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["changed"] is False
    assert client.calls[-1][1] == "/api/ableton/clip-rename/proposal"


def test_mcp_parameter_profile_combines_raw_and_display_metadata() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 9, "live_parameter_profile", {"track_index": 3, "device_index": 1, "parameter_index": 4})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["parameter"]["name"] == "Attack"
    assert payload["parameter"]["value"] == 3.0
    assert payload["display"]["value_string"] == "1"
    assert payload["display_available"] is True
    assert ("GET", "/api/ableton/osc/device-parameters", {"track_index": 3, "device_index": 1}) in client.calls
    assert ("GET", "/api/ableton/osc/device-parameter-value-string", {"track_index": 3, "device_index": 1, "parameter_index": 4}) in client.calls


def test_mcp_compares_exact_live_devices_read_only() -> None:
    class CompareHTTP(FakeKennHTTP):
        def get(self, path: str, query: dict | None = None) -> dict:
            if path == "/api/ableton/osc/session":
                self.calls.append(("GET", path, query or {}))
                return {
                    "status": "connected",
                    "tracks": [
                        {"index": 3, "name": "Vocal", "devices": [{"index": 1, "name": "Glue Compressor"}]},
                        {"index": 4, "name": "Drums", "devices": [{"index": 0, "name": "Glue Compressor"}]},
                    ],
                }
            if path == "/api/ableton/osc/device-parameters":
                self.calls.append(("GET", path, query or {}))
                value = 3.0 if (query or {}).get("track_index") == 3 else 5.0
                return {
                    "success": True,
                    "device_name": "Glue Compressor",
                    "parameters": [
                        {"index": 4, "name": "Attack", "value": value, "min": 0.0, "max": 6.0, "quantized": True},
                        {"index": 5, "name": "Threshold", "value": -6.0, "min": -40.0, "max": 0.0, "quantized": False},
                    ],
                }
            return super().get(path, query)

    client = CompareHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        10,
        "compare_live_devices",
        {
            "left_track_index": 3,
            "left_device_index": 1,
            "right_track_index": 4,
            "right_device_index": 0,
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "kenn.live_device_comparison.v1"
    assert payload["left"]["track_name"] == "Vocal"
    assert payload["right"]["track_name"] == "Drums"
    assert payload["matched_parameter_count"] == 2
    assert payload["differing_parameter_count"] == 1
    attack = next(item for item in payload["parameters"] if item["name"] == "Attack")
    assert attack["delta_right_minus_left"] == 2.0
    assert payload["read_only"] is True
    assert payload["mutation_authorized"] is False
    assert all(method == "GET" for method, _path, _query in client.calls)


def test_mcp_plugin_review_is_read_only_and_preserves_freshness_boundary() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 10, "live_plugin_review", {"session_id": "mix-session"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "kenn.plugin_live_review.v1"
    assert payload["live_context"]["scope"] == "plugin_bus"
    assert payload["live_context"]["freshness"]["frame_count"] == 4
    assert payload["live_context"]["live_window"]["status"] == "stable"
    assert payload["advisory_only"] is True
    assert payload["capture_requested"] is False
    assert client.calls[-1] == ("GET", "/api/plugin-live-review", {"session_id": "mix-session"})


def test_mcp_realtime_session_review_is_one_read_only_composed_surface() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 11, "realtime_session_review", {})
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["schema"] == "kenn.realtime_session_review.v1"
    assert payload["advisory_only"] is True
    assert payload["mutation_authorized"] is False
    assert payload["capture_requested"] is False
    assert client.calls[-1] == ("GET", "/api/realtime-session-review", {})
    assert all(method == "GET" for method, _path, _query in client.calls)


def test_mcp_realtime_session_review_forwards_optional_focus() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    _call(facade, 111, "realtime_session_review", {"focus": "headroom and gain staging"})

    assert client.calls[-1] == (
        "GET", "/api/realtime-session-review",
        {"focus": "headroom and gain staging"},
    )


def test_mcp_realtime_mix_recommendations_are_standalone_and_read_only() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 12, "realtime_mix_recommendations", {"session_id": "mix-session"})
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["schema"] == "kenn.realtime_mix_recommendations.v1"
    assert payload["scope"] == "plugin_bus"
    assert payload["recommendations_available"] is True
    assert payload["recommendations"][0]["title"] == "Realtime bus: inspect around 315 Hz"
    assert payload["recommendations"][0]["requiresConfirmation"] is False
    assert payload["recommendations"][0]["canAutoFix"] is False
    assert payload["advisory_only"] is True
    assert payload["capture_requested"] is False
    assert all(item["category"] == "realtime_mix" for item in payload["recommendations"])
    assert client.calls[-1] == ("GET", "/api/plugin-live-review", {"session_id": "mix-session"})
    assert all(method == "GET" for method, _path, _query in client.calls)


def test_mcp_realtime_mix_comparison_is_scope_labelled_and_read_only() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        13,
        "compare_realtime_mix_review",
        {"review_id": "reference-review", "plugin_session_id": "mix-session"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["schema"] == "kenn.realtime_mix_comparison.v1"
    assert payload["comparison_available"] is True
    assert payload["pink_noise_shape"]["deviation_delta_db"] == -0.1
    assert payload["pink_noise_shape"]["status"] == "directional_same_baseline_different_resolution"
    assert payload["advisory_only"] is True
    assert payload["capture_requested"] is False
    assert payload["live_target_inference_allowed"] is False
    assert client.calls[-2:] == [
        ("GET", "/api/mix-review-status", {"id": "reference-review"}),
        ("GET", "/api/plugin-live-review", {"session_id": "mix-session"}),
    ]
    assert all(method == "GET" for method, _path, _query in client.calls)


def test_mcp_audio_artifact_inspection_is_read_only_and_validated() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 11, "audiogen_artifact", {"job_id": "midi-job"})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "kenn.audiogen_artifact_inspection.v1"
    assert payload["ready_for_review"] is True
    assert payload["available_actions"] == []
    assert "create_midi_clip_from_artifact" in payload["limitations"][-1]
    assert payload["artifact"]["validation"]["ok"] is True
    assert payload["artifact"]["sha256"].startswith("sha256:")
    assert "path" not in payload["artifact"]
    assert client.calls[-1] == ("GET", "/api/audiogen/job", {"id": "midi-job"})


def test_mcp_audiogen_audio_candidate_returns_local_listen_url_only() -> None:
    client = FakeKennHTTP()
    client.base_url = "http://127.0.0.1:8090"
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        284,
        "generate_audiogen_audio_candidate",
        {"prompt": "an upbeat four bar idea", "emotion": "joy", "bars": 4},
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "kenn.audiogen_audio_candidate.v1"
    assert payload["audio_url"] == "http://127.0.0.1:8090/portfolio/audio/kenn-audiogen-joy-test.wav"
    assert payload["audition"]["live_mutation"] is False
    assert client.calls[-1][0:2] == ("POST", "/api/audiogen/generate")


def test_mcp_audiogen_audio_comparison_is_read_only_and_measured() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        285,
        "compare_audiogen_audio_candidates",
        {"source_a": "/portfolio/audio/a.wav", "source_b": "/portfolio/audio/b.wav"},
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "kenn.audiogen_audio_comparison.v1"
    assert payload["metric_deltas"]["rms_dbfs"]["delta_b_minus_a"] == 6.0
    assert payload["advisory_only"] is True
    assert client.calls[-1] == (
        "POST",
        "/api/audiogen/audio-compare",
        {"source_a": "/portfolio/audio/a.wav", "source_b": "/portfolio/audio/b.wav"},
    )


def test_mcp_midi_clip_proposal_is_typed_and_non_mutating() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        12,
        "create_midi_clip_proposal",
        {
            "session_id": "midi-mcp",
            "track_index": 1,
            "track_name": "Bass MIDI",
            "clip_slot_index": 0,
            "length": 4,
            "notes": [{"pitch": 36, "start_time": 0, "duration": 1, "velocity": 110}],
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["changed"] is False
    assert payload["proposal"]["schema"] == "kenn.ableton_midi_clip_proposal.v1"
    assert client.calls[-1][0:2] == ("POST", "/api/ableton/midi-clip/proposal")


def test_mcp_midi_clip_update_proposal_is_typed_and_non_mutating() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        13,
        "update_midi_clip_proposal",
        {
            "session_id": "midi-update-mcp",
            "track_index": 1,
            "track_name": "Bass MIDI",
            "clip_slot_index": 0,
            "notes": [{"pitch": 48, "start_time": 2, "duration": 1, "velocity": 100}],
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["changed"] is False
    assert payload["proposal"]["schema"] == "kenn.ableton_midi_clip_update_proposal.v1"
    assert client.calls[-1] == (
        "POST",
        "/api/ableton/midi-clip/update-proposal",
        {
            "session_id": "midi-update-mcp",
            "track_index": 1,
            "track_name": "Bass MIDI",
            "clip_slot_index": 0,
            "notes": [{"pitch": 48, "start_time": 2, "duration": 1, "velocity": 100}],
        },
    )


def test_mcp_clip_audition_proposal_is_typed_and_non_mutating() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        121,
        "create_clip_audition_proposal",
        {
            "session_id": "audition-mcp",
            "track_index": 0,
            "track_name": "1-MIDI",
            "clip_slot_index": 0,
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["changed"] is False
    assert payload["proposal"]["schema"] == "kenn.ableton_clip_audition_proposal.v1"
    assert client.calls[-1][0:2] == ("POST", "/api/ableton/clip-audition/proposal")


def test_mcp_audition_feedback_is_advisory_and_receipt_bound() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        281,
        "record_audition_feedback",
        {
            "session_id": "feedback-session",
            "receipt": {
                "schema": "kenn.ableton_clip_audition_receipt.v1",
                "receipt_id": "receipt-1",
                "status": "applied",
                "verified": True,
                "target": {"track_index": 0, "track_name": "1-MIDI", "clip_slot_index": 0},
            },
            "verdict": "revise",
            "rating": 3,
            "requested_changes": ["Make the ending less busy"],
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["changed"] is False
    assert client.calls[-1][0:2] == ("POST", "/api/ableton/audition-feedback")
    assert client.calls[-1][2]["receipt"]["receipt_id"] == "receipt-1"


def test_mcp_revision_brief_is_read_only_and_exact_target_bound() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        282,
        "create_audition_revision_brief",
        {
            "session_id": "revision-session",
            "feedback_id": "feedback-1",
            "comparison": {
                "schema": "kenn.audiogen_audio_comparison.v1",
                "source_a": {"reference": "/portfolio/audio/a.wav", "input_hash": "a"},
                "source_b": {"reference": "/portfolio/audio/b.wav", "input_hash": "b"},
                "metric_deltas": {
                    "rms_dbfs": {"a": -18.0, "b": -12.0, "delta_b_minus_a": 6.0},
                },
            },
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "kenn.audition_revision_brief.v1"
    assert payload["source_receipt_id"] == "receipt-1"
    assert payload["target"]["track_name"] == "1-MIDI"
    assert payload["advisory_only"] is True
    assert payload["comparison"]["metric_deltas"]["rms_dbfs"]["delta_b_minus_a"] == 6.0
    assert client.calls[-1] == (
        "GET",
        "/api/ableton/audition-feedback",
        {"session_id": "revision-session", "limit": 100},
    )


def test_mcp_audiogen_revision_generation_preserves_feedback_target() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        283,
        "generate_audiogen_midi_revision_proposal",
        {
            "session_id": "revision-session",
            "feedback_id": "feedback-1",
            "seed": 42,
            "emotion": "joy",
            "bars": 1,
            "comparison": {
                "schema": "kenn.audiogen_audio_comparison.v1",
                "source_a": {"reference": "/portfolio/audio/a.wav", "input_hash": "a"},
                "source_b": {"reference": "/portfolio/audio/b.wav", "input_hash": "b"},
                "metric_deltas": {
                    "rms_dbfs": {"a": -18.0, "b": -12.0, "delta_b_minus_a": 6.0},
                },
            },
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["changed"] is False
    assert payload["revision_brief"]["source_receipt_id"] == "receipt-1"
    assert payload["revision_brief"]["target"]["track_name"] == "1-MIDI"
    assert client.calls[-1][0:2] == ("POST", "/api/audiogen/midi-proposal")
    assert client.calls[-1][2]["revision_brief"]["feedback_id"] == "feedback-1"
    assert client.calls[-1][2]["revision_brief"]["comparison"]["schema"] == "kenn.audiogen_audio_comparison.v1"
    assert client.calls[-1][2]["seed"] == "42"


def test_mcp_revision_proposal_completes_bound_task_only_with_matching_receipt(tmp_path) -> None:
    class RevisionTaskHTTP(FakeKennHTTP):
        def post(self, path: str, payload: dict) -> dict:
            self.calls.append(("POST", path, payload))
            if path == "/api/audiogen/midi-proposal":
                return {
                    "ok": True,
                    "changed": False,
                    "artifact": {"kind": "midi", "sha256": "sha256:" + ("c" * 64)},
                    "proposal": {
                        "schema": "kenn.ableton_midi_clip_proposal.v1",
                        "action_id": "revision-action-1",
                        "requires_confirmation": True,
                    },
                }
            if path == "/api/ableton/command" and payload.get("proposal"):
                return {
                    "ok": True,
                    "status": "applied",
                    "changed": True,
                    "receipt": {
                        "schema": "kenn.ableton_midi_clip_receipt.v1",
                        "receipt_id": "revision-receipt-1",
                        "action_id": "revision-action-1",
                        "status": "applied",
                        "verified": True,
                    },
                }
            return super().post(path, payload)

    client = RevisionTaskHTTP()
    coordinator = AssistantCoordinator(AssistantTaskStore(tmp_path / "revision-task.db"))
    facade = KennMCPFacade(client, coordinator=coordinator)
    context = facade._assistant_context("revision-session")
    assert "revise_audition" in context["available_actions"]
    step = DeliberativeStep.create(
        step_id="revise",
        kind="live_proposal",
        action="revise_audition",
        objective="Prepare the requested MIDI revision.",
        rationale="Use verified listener feedback and preserve its exact target.",
        expected_evidence=["typed confirmation-gated MIDI revision proposal"],
    )
    plan = DeliberativePlan.create(
        goal="Revise the audition from its listener feedback",
        context=context,
        status="ready",
        steps=[step],
    ).to_dict()
    task = coordinator.start(plan=plan, context=context)["task"]

    proposed = json.loads(_call(
        facade,
        284,
        "generate_audiogen_midi_revision_proposal",
        {
            "session_id": "revision-session",
            "feedback_id": "feedback-1",
            "seed": 42,
            "assistant_task_id": task["task_id"],
            "assistant_step_id": "revise",
        },
    )["result"]["content"][0]["text"])
    applied = json.loads(_call(
        facade,
        285,
        "apply_live_proposal",
        {
            "proposal": proposed["proposal"],
            "confirm_token": "confirmed-by-user",
            "session_id": "revision-session",
            "idempotency_key": "revision-once",
            "assistant_task_id": task["task_id"],
            "assistant_step_id": "revise",
        },
    )["result"]["content"][0]["text"])

    assert proposed["assistant_task"]["task"]["status"] == "waiting_for_confirmation"
    assert proposed["assistant_task"]["next_step"]["mode"] == "wait_for_confirmation"
    assert proposed["revision_brief"]["feedback_id"] == "feedback-1"
    assert applied["assistant_task"]["task"]["status"] == "completed"
    assert applied["assistant_task"]["next_step"]["mode"] == "complete"
    stored = coordinator.store.load(task["task_id"])
    assert stored["evidence"][-1]["receipt_id"] == "revision-receipt-1"
    assert stored["evidence"][-1]["action_id"] == "revision-action-1"


def test_mcp_receipt_derived_audition_uses_exact_recorded_target() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    receipt = {
        "schema": "kenn.ableton_midi_clip_receipt.v1",
        "receipt_id": "clip-receipt-1",
        "status": "applied",
        "verified": True,
        "target": {"track_index": 1, "track_name": "Bass MIDI", "clip_slot_index": 3},
    }
    response = _call(
        facade,
        122,
        "create_clip_audition_from_receipt",
        {"session_id": "audition-receipt-mcp", "receipt": receipt},
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["changed"] is False
    assert payload["source_receipt_id"] == "clip-receipt-1"
    assert client.calls[-1] == (
        "POST",
        "/api/ableton/clip-audition/proposal",
        {
            "session_id": "audition-receipt-mcp",
            "track_index": 1,
            "track_name": "Bass MIDI",
            "clip_slot_index": 3,
            "source_receipt_id": "clip-receipt-1",
        },
    )


def test_mcp_audio_artifact_creates_only_a_typed_midi_proposal() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        14,
        "create_midi_clip_from_artifact",
        {
            "job_id": "midi-job",
            "session_id": "artifact-mcp",
            "track_index": 0,
            "track_name": "1-MIDI",
            "clip_slot_index": 0,
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["changed"] is False
    assert payload["source"]["job_id"] == "midi-job"
    post_path, post_payload = client.calls[-1][0:2], client.calls[-1][2]
    assert post_path == ("POST", "/api/ableton/midi-clip/proposal")
    assert post_payload["length"] == 4.0
    assert len(post_payload["notes"]) == 2
    assert post_payload["source_artifact_sha256"].startswith("sha256:")


def test_mcp_audiogen_generation_creates_only_a_typed_proposal() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(
        facade,
        15,
        "generate_audiogen_midi_proposal",
        {
            "session_id": "generated-mcp",
            "track_index": 0,
            "track_name": "1-MIDI",
            "clip_slot_index": 0,
            "emotion": "joy",
            "bars": 2,
            "seed": "test-seed",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["changed"] is False
    assert client.calls[-1][0:2] == ("POST", "/api/audiogen/midi-proposal")
    assert client.calls[-1][2]["bars"] == 2


def test_mcp_tools_call_uses_kenn_http_and_proposal_is_non_mutating() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    snapshot = _call(facade, 1, "live_snapshot", {"detail": "topology"})
    assert json.loads(snapshot["result"]["content"][0]["text"])["status"] == "connected"
    proposal = _call(facade, 2, "create_live_proposal", {"command": "add EQ on track 4"})
    proposal_payload = json.loads(proposal["result"]["content"][0]["text"])
    assert proposal_payload["changed"] is False
    assert client.calls[-1] == (
        "POST",
        "/api/ableton/command",
        {"session_id": "mcp-proposal", "command": "add EQ on track 4"},
    )


def test_unknown_or_invalid_mcp_tool_returns_tool_error_without_http_call() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 3, "not_a_tool")
    assert response["result"]["isError"] is True
    assert "Unknown KENN MCP tool" in response["result"]["content"][0]["text"]
    assert client.calls == []


def test_mcp_apply_delegates_only_exact_confirmed_proposal_payload() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    proposal = {"schema": "kenn.action_proposal.v1", "id": "proposal-test", "requires_confirmation": True}
    response = _call(
        facade,
        4,
        "apply_live_proposal",
        {
            "proposal": proposal,
            "confirm_token": "token-test",
            "session_id": "mcp-session",
            "idempotency_key": "proposal-test",
        },
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["changed"] is True
    assert client.calls[-1] == (
        "POST",
        "/api/ableton/command",
        {
            "command": "apply confirmed KENN Live proposal",
            "session_id": "mcp-session",
            "proposal": proposal,
            "confirm_token": "token-test",
            "idempotency_key": "proposal-test",
        },
    )


def test_mcp_receipts_are_read_only_and_bounded() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    response = _call(facade, 7, "live_receipts", {"session_id": "mcp-session", "limit": 3})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["receipts"] == []
    assert client.calls[-1] == ("GET", "/api/ableton/receipts", {"session_id": "mcp-session", "limit": 3})


class FailingTransportHTTP(FakeKennHTTP):
    def post(self, path: str, payload: dict) -> dict:
        raise KennTransportError("simulated timeout")


def test_mcp_apply_marks_transport_failure_as_non_retryable() -> None:
    facade = KennMCPFacade(FailingTransportHTTP())
    response = _call(
        facade,
        8,
        "apply_live_proposal",
        {
            "proposal": {"schema": "kenn.action_proposal.v1"},
            "confirm_token": "token",
            "session_id": "mcp-session",
            "idempotency_key": "proposal",
        },
    )
    assert response["result"]["isError"] is True
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["error_kind"] == "transport_uncertain"
    assert payload["retry_allowed"] is False
    assert payload["recovery_tools"] == ["live_receipts", "live_snapshot"]


def test_mcp_undo_has_separate_proposal_and_apply_phases() -> None:
    client = FakeKennHTTP()
    facade = KennMCPFacade(client)
    receipt = {"receipt_id": "receipt-test", "verified": True}
    proposed = _call(facade, 5, "undo_live_receipt", {"receipt": receipt, "session_id": "mcp-session"})
    proposed_payload = json.loads(proposed["result"]["content"][0]["text"])
    assert proposed_payload["status"] == "confirmation_required"
    assert proposed_payload["changed"] is False
    undo_proposal = {"schema": "kenn.action_proposal.v1", "id": "undo-proposal", "requires_confirmation": True}
    applied = _call(
        facade,
        6,
        "undo_live_receipt",
        {
            "receipt": receipt,
            "proposal": undo_proposal,
            "confirm_token": "undo-token",
            "session_id": "mcp-session",
            "idempotency_key": "undo-proposal",
        },
    )
    applied_payload = json.loads(applied["result"]["content"][0]["text"])
    assert applied_payload["status"] == "applied"
    assert applied_payload["changed"] is True
    assert client.calls[-1][0:2] == ("POST", "/api/ableton/osc/undo")
