"""Coverage for the non-mutating investor-demo script contract gate."""

from __future__ import annotations

from scripts.demo_script_gate import DemoScriptGate, MANUAL_STEPS, SCRIPT_STEPS, run_gate


class FakeGate(DemoScriptGate):
    def __init__(
        self,
        base_url: str = "http://kenn.test",
        *,
        max_latency_ms: float = 650.0,
        command_interval_ms: float = 0.0,
        fail_command: str = "",
        slow_command: str = "",
        route: str = "command",
    ) -> None:
        super().__init__(
            base_url,
            max_latency_ms=max_latency_ms,
            command_interval_ms=command_interval_ms,
            route=route,
        )
        self.fail_command = fail_command
        self.slow_command = slow_command
        self.commands: list[dict] = []

    def _command(self, command: str, *, session_id: str):
        self.commands.append({"command": command, "session_id": session_id})
        latency = 700.0 if command == self.slow_command else 25.0
        base = {"changed": False, "latency": {"total_ms": latency}}
        answers = {
            "How many tracks do I have?": {
                **base, "status": "inspected", "answer_mode": "session_question",
                "intent": {"action": "inspect_track_count"}, "answer": "8 tracks", "track_count": 8,
            },
            "What's selected?": {
                **base, "status": "inspected", "answer_mode": "session_question",
                "intent": {"action": "inspect_selected_track"}, "answer": "Drum Bus",
                "track": {"number": 4, "index": 3, "name": "Drum Bus"},
            },
            "Describe this session.": {
                **base, "status": "inspected", "answer_mode": "session_question",
                "intent": {"action": "inspect_overview"}, "answer": "overview",
                "tracks": [{"name": name} for name in (
                    "Kick", "Snare / Clap", "Hi-Hats", "Drum Bus", "Bass", "Synth", "Lead Vocal", "FX Print",
                )],
            },
            "Any duplicate track names?": {
                **base, "status": "inspected", "answer_mode": "session_question",
                "intent": {"action": "inspect_duplicate_names"}, "answer": "none",
                "duplicate_track_names": [],
            },
            "What did you change?": {
                **base, "status": "inspected", "answer_mode": "session_question",
                "intent": {"action": "inspect_change_history"}, "answer": "none", "changes": [],
            },
            "How does my low end sound?": {
                **base, "status": "inspected", "answer_mode": "session_question",
                "intent": {"action": "inspect_mix_advice"}, "answer": "measured", "advisory_only": True,
                "advice_mode": "audio_analysis", "analysis_scope": "low_end",
                "analysis_source": {"sha256": "a" * 64, "cache_hit": True},
                "findings": [{"type": "possible_low_end_excess"}],
            },
            "Check the vocals for clipping.": {
                **base, "status": "inspected", "answer_mode": "session_question",
                "intent": {"action": "inspect_mix_advice"}, "answer": "measured", "advisory_only": True,
                "advice_mode": "audio_analysis", "analysis_scope": "vocal",
                "analysis_source": {"sha256": "b" * 64, "cache_hit": True},
                "findings": [{"type": "clipping"}],
            },
            "Delete track 3.": {
                **base, "status": "refused", "confirmation_required": False,
                "answer": "Deleting is disabled by the KENN assistant boundary.",
            },
            "Set the master volume to maximum.": {
                **base, "status": "refused", "confirmation_required": False,
                "answer": "Master changes are outside KENN's qualified control boundary.",
            },
        }
        proposals = {
            "Set Compressor Output to 3 dB on track 7.": {
                "operation": "set_device_parameter", "track_name": "Lead Vocal", "device_name": "Compressor",
                "parameter": "Output", "after": 3.0,
            },
            "Pan the Synth hard left.": {
                "operation": "set_pan", "track_name": "Synth", "parameter": "pan", "after": -1.0,
            },
            "Focus EQ Eight on track 5.": {
                "operation": "focus_device", "track_name": "Bass", "device_name": "EQ Eight",
                "after": {"track_index": 4, "device_index": 0},
            },
            "Boost amplitude by 3 dB at 200 Hz on track 5 band 2A.": {
                "operation": "set_device_parameter", "track_name": "Bass", "device_name": "EQ Eight",
                "parameter": "2 Gain A", "after": 3.0, "eq_band": "2A", "requested_frequency_hz": 200.0,
            },
        }
        if command in proposals:
            body = {
                **base, "status": "confirmation_required",
                "proposal": {
                    **proposals[command], "requires_confirmation": True,
                    "confirmation_token": "v1.bound-token",
                },
            }
        else:
            body = answers[command]
        if command == self.fail_command:
            body = {**base, "status": "error", "changed": False}
        return body, 30.0


def test_gate_covers_thirteen_steps_without_confirming_any_proposal() -> None:
    gate = FakeGate()

    results = gate.run_once()

    assert len(results) == 13
    assert all(item.passed for item in results)
    assert [item.step for item in results] == [2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 15, 16]
    assert all("confirm_token" not in item for item in gate.commands)
    assert all(item["session_id"].startswith("demo-script-gate-") for item in gate.commands)
    assert set(MANUAL_STEPS) == {1, 10, 14, 17, 18, 19, 20}
    assert len(SCRIPT_STEPS) + len(MANUAL_STEPS) == 20


def test_gate_stops_on_first_contract_failure() -> None:
    gate = FakeGate(fail_command="Pan the Synth hard left.")

    results = gate.run_once()

    assert results[-1].step == 7
    assert results[-1].passed is False
    assert "confirmation" in results[-1].detail
    assert len(gate.commands) == 6


def test_gate_fails_a_response_over_the_command_latency_budget() -> None:
    gate = FakeGate(slow_command="How many tracks do I have?")

    results = gate.run_once()

    assert len(results) == 1
    assert results[0].passed is False
    assert "700.0ms" in results[0].detail
    assert "650ms budget" in results[0].detail


def test_report_never_claims_full_demo_qualification(monkeypatch) -> None:
    monkeypatch.setattr("scripts.demo_script_gate.DemoScriptGate", FakeGate)

    report = run_gate(
        "http://kenn.test",
        runs=2,
        max_latency_ms=650.0,
        command_interval_ms=0.0,
    )

    assert report["passed_runs"] == 2
    assert report["full_demo_qualified"] is False
    assert report["mode"] == "non_mutating_contract_only"
    assert len(report["manual_steps"]) == 7


def test_ask_route_validates_the_gateway_result_embedded_in_chat_replies(monkeypatch) -> None:
    import io
    import json as _json

    import scripts.demo_script_gate as gate_module

    replies = {
        "/kenn/api/ask": {
            "route": "ableton_controller", "status": "succeeded",
            "orchestration": {"result": {"status": "refused", "changed": False}},
        },
    }

    class Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout):
        assert request.full_url.endswith("/kenn/api/ask")
        assert _json.loads(request.data)["question"] == "Delete track 3."
        return Response(_json.dumps(replies["/kenn/api/ask"]).encode())

    monkeypatch.setattr(gate_module.urllib.request, "urlopen", fake_urlopen)
    gate = DemoScriptGate("http://kenn.test", command_interval_ms=0.0, route="ask")

    body, _elapsed = gate._command("Delete track 3.", session_id="ask-route")

    assert body["status"] == "refused"
    assert isinstance(body["latency"]["total_ms"], float)


def test_ask_route_rebuilds_grounded_status_from_the_chat_envelope(monkeypatch) -> None:
    import io
    import json as _json

    import scripts.demo_script_gate as gate_module

    class Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    envelope = {"route": "ableton_live_inspection", "status": "succeeded", "found": True,
                "intent": "inspect_track_count", "live_intent": {"action": "inspect_track_count"},
                "answer_mode": "live_inspection", "changed": False, "answer": "8 tracks", "track_count": 8}
    monkeypatch.setattr(gate_module.urllib.request, "urlopen",
                        lambda request, timeout: Response(_json.dumps(envelope).encode()))
    gate = DemoScriptGate("http://kenn.test", command_interval_ms=0.0, route="ask")

    body, _elapsed = gate._command("How many tracks do I have?", session_id="ask-route")

    assert body["status"] == "inspected"
    assert body["intent"] == {"action": "inspect_track_count"}
