"""Unit tests for KENN Autonomous Grounded DSP Agent.

tool_ltas_spectrum_match used to default to a hardcoded linear-ramp "mock
mix spectrum" whenever no real bands were supplied, and still reported
status "success" -- indistinguishable from a genuine measurement to
anything reading the response. It now measures a real AutoMix delivered
mixdown when given a project_id, or honestly reports that nothing was
analyzed when it has neither real bands nor a project_id.
"""

from __future__ import annotations

import json
import wave
from io import BytesIO
from pathlib import Path

from kenn.autonomous_agent import (
    KennAutonomousAgent,
    tool_audit_realtime_cpp,
    tool_configure_sidechain,
    tool_create_ableton_device,
    tool_create_ableton_scene,
    tool_ltas_spectrum_match,
    tool_set_ableton_arm,
    tool_set_ableton_macro,
    tool_set_ableton_mute,
    tool_set_ableton_pan,
    tool_set_ableton_solo,
    tool_set_ableton_volume,
)


def test_realtime_cpp_audit_tool():
    unsafe_cpp = """
    void processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer&) {
        float* data = new float[1024]; // Dynamic allocation warning
        std::cout << "Processing audio block" << std::endl; // IO syscall warning
        delete[] data;
    }
    """
    res = tool_audit_realtime_cpp(unsafe_cpp)
    assert res["status"] == "warning"
    assert res["violations_found"] == 2


def test_ltas_spectrum_match_tool_with_explicit_bands():
    res = tool_ltas_spectrum_match(genre="pop", mix_bands=[-10.0] * 40)
    assert res["status"] == "success"
    assert res["analyzed_real_audio"] is True
    assert "eq_recommendations" in res


def test_ltas_spectrum_match_tool_with_no_input_is_honest_not_fake():
    res = tool_ltas_spectrum_match(genre="pop")
    assert res["status"] == "no_audio"
    assert res["analyzed_real_audio"] is False
    assert res["eq_recommendations"] == []
    assert res["bands_analyzed"] == 0
    # The old bug: a hardcoded linear-ramp fingerprint with a "success" status.
    assert res.get("bands_analyzed") != 40


def test_ltas_spectrum_match_tool_with_unknown_project_id_is_honest():
    res = tool_ltas_spectrum_match(genre="pop", project_id="no-such-project")
    assert res["status"] == "no_audio"


def _write_wav(path: Path) -> None:
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(bytes([5, 0]) * 400)
    path.write_bytes(buf.getvalue())


def test_ltas_spectrum_match_tool_measures_a_real_delivered_mixdown(monkeypatch, tmp_path):
    import kenn.autonomous_agent as agent_module

    mix_output_root = tmp_path / "mix_outputs"
    proj_dir = mix_output_root / "proj-real"
    proj_dir.mkdir(parents=True)
    _write_wav(proj_dir / "mixdown_v1.wav")
    monkeypatch.setattr(agent_module, "_MIX_OUTPUT_ROOT", mix_output_root)

    res = tool_ltas_spectrum_match(genre="pop", project_id="proj-real")

    assert res["status"] == "success"
    assert res["analyzed_real_audio"] is True
    assert res["bands_analyzed"] == 40


def test_kenn_autonomous_agent_reasoning_loop():
    agent = KennAutonomousAgent()
    prompt = "Audit this C++ code safety and generate a JUCE patch for pop spectrum matching"
    code = "void processBlock() { malloc(1024); }"

    res = agent.run_agent_loop(user_prompt=prompt, code_context=code)
    assert res["ok"] is True
    assert res["steps_completed"] >= 3
    assert "audit_realtime_cpp" in res["tools_used"]
    assert "generate_juce_patch" in res["tools_used"]
    assert "advice" in res


def test_kenn_autonomous_agent_ableton_tools(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient

    # Mock OSC client methods
    monkeypatch.setattr(AbletonOSCClient, "query_session_state", lambda self: {
        "status": "connected",
        "tracks": [{"name": "Synth", "volume": 0.75, "pan": 0.0}]
    })
    monkeypatch.setattr(AbletonOSCClient, "set_track_volume", lambda self, idx, vol: True)
    monkeypatch.setattr(AbletonOSCClient, "set_track_pan", lambda self, idx, pan: True)
    monkeypatch.setattr(AbletonOSCClient, "set_device_parameter", lambda self, t_idx, d_idx, p_idx, val: True)

    agent = KennAutonomousAgent()

    # 1. Test Query Session Tool
    res_query = agent.run_agent_loop(user_prompt="query_session tracks please")
    assert res_query["ok"] is True
    assert "query_ableton_session" in res_query["tools_used"]
    assert "Successfully queried Ableton session" in res_query["advice"]

    # 2. Test Set Volume Tool
    res_vol = agent.run_agent_loop(user_prompt="set_volume on track 1 to volume 0.7")
    assert res_vol["ok"] is True
    assert "set_ableton_volume" in res_vol["tools_used"]
    assert "Set Ableton track 1 volume index to 0.7" in res_vol["advice"]

    # 3. Test Set Pan Tool
    res_pan = agent.run_agent_loop(user_prompt="set_pan on track 2 to pan -0.5")
    assert res_pan["ok"] is True
    assert "set_ableton_pan" in res_pan["tools_used"]
    assert "Set Ableton track 2 pan index to -0.5" in res_pan["advice"]

    # 4. Test Set Parameter Tool
    res_param = agent.run_agent_loop(user_prompt="set_parameter track 0 device 1 parameter 2 value 0.5")
    assert res_param["ok"] is True
    assert "set_ableton_parameter" in res_param["tools_used"]
    assert "Adjusted Ableton track 0 device 1 parameter 2 value to 0.5" in res_param["advice"]


def test_kenn_autonomous_agent_volume_warning_reaches_the_chat_advice_text(monkeypatch):
    # Item 2 (docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md): the
    # guardrail warning must actually reach the user-facing advice text,
    # not just sit unread in the raw tool result dict.
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setattr(AbletonOSCClient, "query_session_state", lambda self: {
        "status": "connected",
        "tracks": [{"index": 1, "name": "Lead", "volume": 0.5, "output_meter_level": 0.97}],
    })
    monkeypatch.setattr(AbletonOSCClient, "set_track_volume", lambda self, idx, vol: True)

    agent = KennAutonomousAgent()
    res = agent.run_agent_loop(user_prompt="set_volume on track 1 to volume 0.9")

    assert res["ok"] is True
    assert "⚠️" in res["advice"]
    assert "ceiling" in res["advice"]


def test_kenn_autonomous_agent_mute_solo_arm_tools(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(AbletonOSCClient, "set_track_mute", lambda self, idx, muted: True)
    monkeypatch.setattr(AbletonOSCClient, "set_track_solo", lambda self, idx, soloed: True)
    monkeypatch.setattr(AbletonOSCClient, "set_track_arm", lambda self, idx, armed: True)

    agent = KennAutonomousAgent()

    res_mute = agent.run_agent_loop(user_prompt="mute track 2")
    assert res_mute["ok"] is True
    assert "set_ableton_mute" in res_mute["tools_used"]
    assert "Muted Ableton track 2" in res_mute["advice"]

    res_unmute = agent.run_agent_loop(user_prompt="unmute track 2")
    assert "Unmuted Ableton track 2" in res_unmute["advice"]

    res_solo = agent.run_agent_loop(user_prompt="solo track 1")
    assert "set_ableton_solo" in res_solo["tools_used"]
    assert "Soloed Ableton track 1" in res_solo["advice"]

    res_arm = agent.run_agent_loop(user_prompt="record arm track 0")
    assert "set_ableton_arm" in res_arm["tools_used"]
    assert "Record-armed Ableton track 0" in res_arm["advice"]

    res_disarm = agent.run_agent_loop(user_prompt="disarm track 0")
    assert "Disarmed Ableton track 0" in res_disarm["advice"]


def test_kenn_autonomous_agent_transport_tools(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(AbletonOSCClient, "start_playback", lambda self: True)
    monkeypatch.setattr(AbletonOSCClient, "stop_playback", lambda self: True)
    monkeypatch.setattr(AbletonOSCClient, "set_tempo", lambda self, bpm: True)

    agent = KennAutonomousAgent()

    res_play = agent.run_agent_loop(user_prompt="start playback")
    assert res_play["ok"] is True
    assert "start_ableton_playback" in res_play["tools_used"]
    assert "Started Ableton playback" in res_play["advice"]

    res_stop = agent.run_agent_loop(user_prompt="stop playback")
    assert "stop_ableton_playback" in res_stop["tools_used"]
    assert "Stopped Ableton playback" in res_stop["advice"]

    res_tempo = agent.run_agent_loop(user_prompt="set tempo to 140 bpm")
    assert "set_ableton_tempo" in res_tempo["tools_used"]
    assert "Set Ableton tempo to 140.0 BPM" in res_tempo["advice"]


def test_kenn_autonomous_agent_clip_and_scene_launch_tools(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(AbletonOSCClient, "launch_clip", lambda self, t_idx, c_idx: True)
    monkeypatch.setattr(AbletonOSCClient, "launch_scene", lambda self, s_idx: True)

    agent = KennAutonomousAgent()

    res_clip = agent.run_agent_loop(user_prompt="launch the clip on track 2 slot 0")
    assert "launch_ableton_clip" in res_clip["tools_used"]
    assert "Launched clip on track 2, slot 0" in res_clip["advice"]

    res_scene = agent.run_agent_loop(user_prompt="fire scene 3")
    assert "launch_ableton_scene" in res_scene["tools_used"]
    assert "Launched scene 3" in res_scene["advice"]


class TestLLMPlanningLoop:
    """D1.4, 2026-08-06 (Jack's call: full LLM-planning loop). The LLM plan
    is tried first when enabled; the keyword loop (already covered above)
    is the fallback -- never deleted, since a small local model can
    misjudge a real DAW-write request. These tests mock
    llm_rewrite.chat_completion so they run fast and deterministically."""

    def _enable_llm(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")
        monkeypatch.setenv("AUDIO_TOO_LLM_PROVIDER", "ollama")

    def test_valid_plan_executes_via_llm_path(self, monkeypatch):
        from kenn.llm import llm_rewrite
        from kenn.ableton_osc_bridge import AbletonOSCClient

        self._enable_llm(monkeypatch)
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(AbletonOSCClient, "set_track_mute", lambda self, idx, muted: True)
        monkeypatch.setattr(
            llm_rewrite,
            "chat_completion",
            lambda messages, task="rewrite", system_prompt=None: (
                '[{"tool": "set_ableton_mute", "args": {"track_index": 2, "muted": true}}]'
            ),
        )

        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="mute the second track please")

        assert res["ok"] is True
        assert res["plan_source"] == "llm"
        assert "set_ableton_mute" in res["tools_used"]
        assert res["trajectory"][0]["result"]["status"] == "success"

    def test_llm_disabled_falls_back_to_keyword_loop(self, monkeypatch):
        # The developer's local .env can legitimately enable LLM support.
        # Set an explicit false value so this test verifies the disabled
        # branch independently of machine configuration.
        monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "0")
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="query_session tracks please")
        assert res["ok"] is True
        assert "plan_source" not in res
        assert "query_ableton_session" in res["tools_used"]

    def test_malformed_json_response_falls_back_to_keyword_loop(self, monkeypatch):
        from kenn.llm import llm_rewrite

        self._enable_llm(monkeypatch)
        monkeypatch.setattr(
            llm_rewrite,
            "chat_completion",
            lambda messages, task="rewrite", system_prompt=None: "not valid json at all",
        )
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="query_session tracks please")
        assert "plan_source" not in res
        assert "query_ableton_session" in res["tools_used"]

    def test_markdown_fenced_json_is_parsed(self, monkeypatch):
        from kenn.llm import llm_rewrite

        self._enable_llm(monkeypatch)
        monkeypatch.setattr(
            llm_rewrite,
            "chat_completion",
            lambda messages, task="rewrite", system_prompt=None: (
                '```json\n[{"tool": "query_ableton_session", "args": {}}]\n```'
            ),
        )
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="what's in my session")
        assert res.get("plan_source") == "llm"
        assert "query_ableton_session" in res["tools_used"]

    def test_unknown_tool_name_is_dropped_not_executed(self, monkeypatch):
        from kenn.llm import llm_rewrite

        self._enable_llm(monkeypatch)
        monkeypatch.setattr(
            llm_rewrite,
            "chat_completion",
            lambda messages, task="rewrite", system_prompt=None: (
                '[{"tool": "delete_all_tracks", "args": {}}, '
                '{"tool": "query_ableton_session", "args": {}}]'
            ),
        )
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="do something")
        assert res.get("plan_source") == "llm"
        assert res["tools_used"] == ["query_ableton_session"]

    def test_missing_required_argument_drops_that_step(self, monkeypatch):
        from kenn.llm import llm_rewrite

        self._enable_llm(monkeypatch)
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            llm_rewrite,
            "chat_completion",
            lambda messages, task="rewrite", system_prompt=None: (
                # missing "volume" -- set_ableton_volume requires it
                '[{"tool": "set_ableton_volume", "args": {"track_index": 1}}, '
                '{"tool": "query_ableton_session", "args": {}}]'
            ),
        )
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="turn it up")
        assert res.get("plan_source") == "llm"
        assert res["tools_used"] == ["query_ableton_session"]

    def test_empty_plan_falls_back_to_keyword_loop(self, monkeypatch):
        from kenn.llm import llm_rewrite

        self._enable_llm(monkeypatch)
        monkeypatch.setattr(
            llm_rewrite,
            "chat_completion",
            lambda messages, task="rewrite", system_prompt=None: "[]",
        )
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="query_session tracks please")
        assert "plan_source" not in res
        assert "query_ableton_session" in res["tools_used"]

    def test_llm_request_exception_falls_back_to_keyword_loop(self, monkeypatch):
        from kenn.llm import llm_rewrite

        self._enable_llm(monkeypatch)

        def _raise(*_args, **_kwargs):
            raise ConnectionError("ollama unreachable")

        monkeypatch.setattr(llm_rewrite, "chat_completion", _raise)
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="query_session tracks please")
        assert "plan_source" not in res
        assert "query_ableton_session" in res["tools_used"]

    def test_multi_step_plan_executes_all_valid_steps_in_order(self, monkeypatch):
        from kenn.llm import llm_rewrite
        from kenn.ableton_osc_bridge import AbletonOSCClient

        self._enable_llm(monkeypatch)
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(AbletonOSCClient, "set_track_mute", lambda self, idx, muted: True)
        monkeypatch.setattr(AbletonOSCClient, "set_track_solo", lambda self, idx, soloed: True)
        monkeypatch.setattr(
            llm_rewrite,
            "chat_completion",
            lambda messages, task="rewrite", system_prompt=None: json.dumps([
                {"tool": "set_ableton_mute", "args": {"track_index": 2, "muted": True}},
                {"tool": "set_ableton_solo", "args": {"track_index": 1, "soloed": True}},
            ]),
        )
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="mute track 2 and solo track 1")
        assert res["tools_used"] == ["set_ableton_mute", "set_ableton_solo"]
        assert res["steps_completed"] == 2

    def test_daw_write_denied_by_default_still_applies_through_llm_path(self, monkeypatch):
        from kenn.llm import llm_rewrite

        self._enable_llm(monkeypatch)
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "0")
        monkeypatch.setattr(
            llm_rewrite,
            "chat_completion",
            lambda messages, task="rewrite", system_prompt=None: (
                '[{"tool": "set_ableton_mute", "args": {"track_index": 2, "muted": true}}]'
            ),
        )
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="mute track 2")
        assert res["trajectory"][0]["result"]["status"] == "denied"


def test_kenn_autonomous_agent_bare_tempo_mention_does_not_fire_without_a_number():
    # "what tempo suits house music?" must not silently write a guessed
    # default BPM to a real Ableton session.
    agent = KennAutonomousAgent()
    res = agent.run_agent_loop(user_prompt="what tempo suits house music")
    assert "set_ableton_tempo" not in res["tools_used"]


def test_kenn_autonomous_agent_orchestrate_tool():
    agent = KennAutonomousAgent()
    # Test dispatch/delegate keyword mapping to the orchestrate tool
    res = agent.run_agent_loop(user_prompt="please delegate to mixing doctor")
    assert res["ok"] is True
    assert "orchestrate" in res["tools_used"]
    assert "Dispatched task to sub-agent" in res["advice"]


def test_kenn_autonomous_agent_device_tools(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient
    
    monkeypatch.setattr(AbletonOSCClient, "create_device", lambda self, track_idx, dev_name: True)
    monkeypatch.setattr(AbletonOSCClient, "configure_sidechain", lambda self, bass_idx, kick_idx: True)

    agent = KennAutonomousAgent()

    # 1. Test create device
    res_create = agent.run_agent_loop(user_prompt="create device Compressor on track 1")
    assert res_create["ok"] is True
    assert "create_ableton_device" in res_create["tools_used"]
    assert "Created Ableton device 'Compressor' on track 1" in res_create["advice"]

    # 2. Test configure sidechain
    res_sc = agent.run_agent_loop(user_prompt="sidechain track 1 to track 0")
    assert res_sc["ok"] is True
    assert "configure_sidechain" in res_sc["tools_used"]
    assert "Configured sidechain compression on track 1 routed from track 0" in res_sc["advice"]


class TestDeviceFallback:
    """Item 3 (docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md): a
    requested device with no native Ableton equivalent by that exact
    name (create_device() searches Live's browser by exact match) used
    to just fail -- one well-established substitution (de-esser -> EQ
    Eight), always communicated, never silent."""

    def test_de_esser_substitutes_eq_eight(self, monkeypatch):
        from kenn.autonomous_agent import tool_create_ableton_device

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        calls = []
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.create_device",
            lambda idx, name: calls.append((idx, name)) or True,
        )
        result = tool_create_ableton_device(2, "de-esser")

        assert result["status"] == "success"
        assert result["device_name"] == "EQ Eight"
        assert result["requested_device_name"] == "de-esser"
        assert "EQ Eight" in result["substitution_note"]
        assert calls == [(2, "EQ Eight")]

    def test_substitution_matching_is_case_insensitive(self, monkeypatch):
        from kenn.autonomous_agent import tool_create_ableton_device

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.create_device", lambda idx, name: True
        )
        result = tool_create_ableton_device(0, "De-Esser")
        assert result["device_name"] == "EQ Eight"

    def test_known_native_device_is_never_substituted(self, monkeypatch):
        from kenn.autonomous_agent import tool_create_ableton_device

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        calls = []
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.create_device",
            lambda idx, name: calls.append((idx, name)) or True,
        )
        result = tool_create_ableton_device(0, "Compressor")

        assert result["device_name"] == "Compressor"
        assert "requested_device_name" not in result
        assert "substitution_note" not in result
        assert calls == [(0, "Compressor")]

    def test_substitution_note_reaches_the_chat_advice_text(self, monkeypatch):
        from kenn.ableton_osc_bridge import AbletonOSCClient

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(AbletonOSCClient, "create_device", lambda self, idx, name: True)

        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="create device de-esser on track 1")

        assert res["ok"] is True
        assert "ℹ️" in res["advice"]
        assert "EQ Eight" in res["advice"]


class TestMacroKnobControl:
    """D1.3 (docs/KENN_FUTURE_PLAN.md Phase 1): macro knobs are regular
    DeviceParameter objects named "Macro N" -- tool_set_ableton_macro
    resolves the name to a parameter_index via get_device_parameters()
    then delegates to set_device_parameter(), the same write path every
    other parameter tool uses."""

    def test_tool_set_ableton_macro_resolves_name_and_writes(self, monkeypatch):
        from kenn.ableton_osc_bridge import AbletonOSCClient

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            AbletonOSCClient, "get_device_parameters",
            lambda self, t, d: {
                "success": True,
                "parameters": [
                    {"index": 0, "name": "Device On", "value": 1.0, "min": 0.0, "max": 1.0},
                    {"index": 1, "name": "Macro 2", "value": 20.0, "min": 0.0, "max": 127.0},
                ],
            },
        )
        captured = {}
        monkeypatch.setattr(
            AbletonOSCClient, "set_device_parameter",
            lambda self, t, d, p, v: captured.update(track=t, device=d, param=p, value=v) or True,
        )

        result = tool_set_ableton_macro(track_index=0, device_index=0, macro_number=2, value=64.0)

        assert result["status"] == "success"
        assert result["parameter_index"] == 1
        assert captured == {"track": 0, "device": 0, "param": 1, "value": 64.0}

    def test_tool_set_ableton_macro_fails_when_macro_not_found(self, monkeypatch):
        from kenn.ableton_osc_bridge import AbletonOSCClient

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            AbletonOSCClient, "get_device_parameters",
            lambda self, t, d: {"success": True, "parameters": [{"index": 0, "name": "Device On", "value": 1.0, "min": 0.0, "max": 1.0}]},
        )

        result = tool_set_ableton_macro(track_index=0, device_index=0, macro_number=5, value=64.0)

        assert result["status"] == "failed"
        assert "Macro 5" in result["error"]

    def test_tool_set_ableton_macro_denied_by_default(self, monkeypatch):
        monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
        result = tool_set_ableton_macro(track_index=0, device_index=0, macro_number=1, value=64.0)
        assert result["status"] == "denied"

    def test_kenn_autonomous_agent_macro_keyword_fires(self, monkeypatch):
        from kenn.ableton_osc_bridge import AbletonOSCClient

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            AbletonOSCClient, "get_device_parameters",
            lambda self, t, d: {"success": True, "parameters": [{"index": 3, "name": "Macro 2", "value": 0.0, "min": 0.0, "max": 127.0}]},
        )
        monkeypatch.setattr(AbletonOSCClient, "set_device_parameter", lambda self, t, d, p, v: True)

        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="set macro 2 on device 0 track 1 to 100")

        assert "set_ableton_macro" in res["tools_used"]
        macro_res = [t["result"] for t in res["trajectory"] if t.get("tool") == "set_ableton_macro"][0]
        assert macro_res["status"] == "success"
        assert macro_res["track_index"] == 1
        assert macro_res["device_index"] == 0
        assert macro_res["macro_number"] == 2

    def test_kenn_autonomous_agent_bare_macro_mention_without_value_does_not_fire(self):
        # "what does macro 2 do?" -- no "to <value>" target, must not fire.
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="what does macro 2 do on this synth")
        assert "set_ableton_macro" not in res["tools_used"]


class TestSceneCreation:
    """D3.4 (docs/KENN_FUTURE_PLAN.md Phase 3): the missing building
    block for conversational arrangement assistance -- creating a real,
    named scene, not just describing a structure in text."""

    def test_tool_create_ableton_scene_returns_index_and_name(self, monkeypatch):
        from kenn.ableton_osc_bridge import AbletonOSCClient

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            AbletonOSCClient, "create_scene",
            lambda self, name="": {"success": True, "scene_index": 4, "name": name},
        )

        result = tool_create_ableton_scene(name="Chorus")

        assert result["status"] == "success"
        assert result["scene_index"] == 4
        assert result["name"] == "Chorus"

    def test_tool_create_ableton_scene_denied_by_default(self, monkeypatch):
        monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
        result = tool_create_ableton_scene(name="Chorus")
        assert result["status"] == "denied"

    def test_kenn_autonomous_agent_create_scene_keyword_fires(self, monkeypatch):
        from kenn.ableton_osc_bridge import AbletonOSCClient

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            AbletonOSCClient, "create_scene",
            lambda self, name="": {"success": True, "scene_index": 3, "name": name},
        )

        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="create a new scene called Chorus")

        assert "create_ableton_scene" in res["tools_used"]
        scene_res = [t["result"] for t in res["trajectory"] if t.get("tool") == "create_ableton_scene"][0]
        assert scene_res["status"] == "success"
        assert scene_res["name"] == "chorus"

    def test_kenn_autonomous_agent_create_scene_without_a_name(self, monkeypatch):
        from kenn.ableton_osc_bridge import AbletonOSCClient

        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            AbletonOSCClient, "create_scene",
            lambda self, name="": {"success": True, "scene_index": 5, "name": name},
        )

        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="add a scene")

        scene_res = [t["result"] for t in res["trajectory"] if t.get("tool") == "create_ableton_scene"][0]
        assert scene_res["status"] == "success"
        assert scene_res["name"] == ""

    def test_kenn_autonomous_agent_read_query_mentioning_scene_does_not_fire(self):
        # "what's on scene 2?" is a read query, not a create request.
        agent = KennAutonomousAgent()
        res = agent.run_agent_loop(user_prompt="what's on scene 2?")
        assert "create_ableton_scene" not in res["tools_used"]


class TestAutonomousAgentDawControlPolicyGate:
    """2026-08-06: every DAW-write HTTP route in server.py checks
    action_allowed("daw_control") before touching Ableton, but these
    autonomous-agent tool functions -- reachable with no confirm step by
    design via /api/kenn/autonomous-execute -- never checked it at all,
    silently bypassing that policy switch. The no-confirm-click UX (Jack's
    explicit call, confirmed intentional) and the policy gate are separate
    safety layers; these tests guard against the gate being skipped again."""

    def test_set_volume_denied_by_default(self, monkeypatch):
        monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)

        def _fail_if_called(*_args, **_kwargs):
            raise AssertionError("live_client should never be reached when denied")

        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_volume", _fail_if_called
        )
        result = tool_set_ableton_volume(0, 0.85)
        assert result["status"] == "denied"
        assert "AUDIO_TOO_ALLOW_DAW_CONTROL" in result["error"]

    def test_set_volume_succeeds_when_explicitly_enabled(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_volume",
            lambda idx, vol: True,
        )
        result = tool_set_ableton_volume(0, 0.85)
        assert result["status"] == "success"

    def test_set_pan_denied_by_default(self, monkeypatch):
        monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
        result = tool_set_ableton_pan(0, 0.0)
        assert result["status"] == "denied"

    def test_create_device_denied_by_default(self, monkeypatch):
        monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
        result = tool_create_ableton_device(0, "Compressor")
        assert result["status"] == "denied"

    def test_configure_sidechain_denied_by_default(self, monkeypatch):
        monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
        result = tool_configure_sidechain(1, 0)
        assert result["status"] == "denied"

    def test_denied_result_still_includes_the_requested_args(self, monkeypatch):
        # So the caller/chat surface can still report what was *attempted*,
        # not just that it was denied.
        monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
        result = tool_set_ableton_volume(3, 0.85)
        assert result["track_index"] == 3
        assert result["volume"] == 0.85


class TestAbletonWritePreviousValueCapture:
    """P4 (docs/KENN_IMPROVEMENT_PLAN.md): the doc claimed KENN already
    captured a "before" value internally for restore -- it didn't, nothing
    in the codebase did. This is that capture, added so a future undo
    button (or KENN's own "undo that" chat command) has something real to
    restore rather than needing to be built from scratch later too."""

    def test_set_volume_captures_previous_value_from_session_state(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {"status": "connected", "tracks": [{"index": 0, "volume": 0.62}]},
        )
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_volume", lambda idx, vol: True
        )
        result = tool_set_ableton_volume(0, 0.85)
        assert result["previous_value"] == 0.62

    def test_set_mute_captures_previous_value(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {"status": "connected", "tracks": [{"index": 2, "muted": False}]},
        )
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_mute", lambda idx, muted: True
        )
        result = tool_set_ableton_mute(2, True)
        assert result["previous_value"] is False

    def test_set_solo_captures_previous_value(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {"status": "connected", "tracks": [{"index": 1, "soloed": True}]},
        )
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_solo", lambda idx, soloed: True
        )
        result = tool_set_ableton_solo(1, False)
        assert result["previous_value"] is True

    def test_set_arm_captures_previous_value(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {"status": "connected", "tracks": [{"index": 0, "armed": False}]},
        )
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_arm", lambda idx, armed: True
        )
        result = tool_set_ableton_arm(0, True)
        assert result["previous_value"] is False

    def test_set_pan_captures_previous_value(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {"status": "connected", "tracks": [{"index": 0, "pan": -0.3}]},
        )
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_pan", lambda idx, pan: True
        )
        result = tool_set_ableton_pan(0, 0.0)
        assert result["previous_value"] == -0.3

    def test_previous_value_is_none_when_track_not_found(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {"status": "connected", "tracks": []},
        )
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_volume", lambda idx, vol: True
        )
        result = tool_set_ableton_volume(5, 0.5)
        assert result["previous_value"] is None

    def test_previous_value_capture_never_blocks_the_write_on_error(self, monkeypatch):
        # Session query can legitimately fail (Live offline, OSC timeout) --
        # that must never prevent the actual write from being attempted.
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")

        def _raise(*_args, **_kwargs):
            raise RuntimeError("OSC timeout")

        monkeypatch.setattr("kenn.ableton_osc_bridge.live_client.query_session_state", _raise)
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_volume", lambda idx, vol: True
        )
        result = tool_set_ableton_volume(0, 0.5)
        assert result["status"] == "success"
        assert result["previous_value"] is None


class TestVolumeGuardrailWarning:
    """Item 2 (docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md):
    advisory-only guardrail -- the write always executes either way,
    this only checks that a warning is attached to the result when the
    guardrail flags one."""

    def test_warning_attached_when_meter_near_ceiling_and_volume_increases(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {
                "status": "connected",
                "tracks": [{"index": 0, "volume": 0.5, "output_meter_level": 0.95}],
            },
        )
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_volume", lambda idx, vol: True
        )
        result = tool_set_ableton_volume(0, 0.9)
        assert result["status"] == "success"
        assert "warning" in result
        assert "ceiling" in result["warning"]

    def test_no_warning_when_meter_reading_is_low(self, monkeypatch):
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {
                "status": "connected",
                "tracks": [{"index": 0, "volume": 0.2, "output_meter_level": 0.3}],
            },
        )
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_volume", lambda idx, vol: True
        )
        result = tool_set_ableton_volume(0, 0.9)
        assert "warning" not in result

    def test_the_write_still_executes_even_when_flagged(self, monkeypatch):
        # Advisory, never a block -- confirmed by the write actually
        # being attempted (set_track_volume called) despite the flag.
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {
                "status": "connected",
                "tracks": [{"index": 0, "volume": 0.5, "output_meter_level": 0.95}],
            },
        )
        calls = []
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_volume",
            lambda idx, vol: calls.append((idx, vol)) or True,
        )
        result = tool_set_ableton_volume(0, 0.9)
        assert result["status"] == "success"
        assert calls == [(0, 0.9)]

    def test_no_warning_when_meter_field_is_absent(self, monkeypatch):
        # Ableton not yet restarted to pick up the meter fields (G2) --
        # must never warn on missing data.
        monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.query_session_state",
            lambda: {"status": "connected", "tracks": [{"index": 0, "volume": 0.5}]},
        )
        monkeypatch.setattr(
            "kenn.ableton_osc_bridge.live_client.set_track_volume", lambda idx, vol: True
        )
        result = tool_set_ableton_volume(0, 0.9)
        assert "warning" not in result

