"""Integration tests for KENN Multi-Agent Orchestrator."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

import pytest
from kenn.core.chat_answer import answer_payload
from kenn.orchestrator import get_orchestrator


def test_orchestrator_integration_mix_reviewer():
    # Chat query that triggers the mix_reviewer sub-agent
    res = answer_payload("review my mix")
    assert res["found"] is True
    assert res["intent"] == "orchestration"
    assert res["route"] == "mix_reviewer"
    assert "orchestration" in res
    assert res["orchestration"]["agent_name"] == "mix_reviewer"
    assert "action" in res["orchestration"]
    assert res["orchestration"]["action"] == "upload_mix"


def test_orchestrator_integration_stem_separator():
    # Chat query that triggers the stem_separator sub-agent
    res = answer_payload("separate my stems")
    assert res["found"] is True
    assert res["intent"] == "orchestration"
    assert res["route"] == "stem_separator"
    assert "orchestration" in res
    assert res["orchestration"]["agent_name"] == "stem_separator"
    assert res["orchestration"]["action"] == "upload_stems"


def test_orchestrator_integration_audiogen():
    # Audiogen is deliberately NOT classified by the orchestrator (see
    # orchestrator.py's classify() comment) -- it defers to the real
    # chat_routing.audio_generation_payload(), which also handles
    # full-song/clarify requests that the orchestrator's stub can't.
    res = answer_payload("generate a pop loop")
    assert res["found"] is True
    assert res["intent"] == "generate"
    assert res["route"] == "audiogen"
    assert "orchestration" not in res
    assert res["audiogen"]["ok"] is True


def test_orchestrator_integration_mixing_doctor(monkeypatch):
    import kenn.mixing_doctor
    
    # 1. Test clean state (healthy)
    monkeypatch.setattr(kenn.mixing_doctor, "get_mixing_alerts", lambda: [])
    res_clean = answer_payload("mixing doctor health check")
    assert res_clean["found"] is True
    assert res_clean["intent"] == "orchestration"
    assert res_clean["route"] == "mixing_doctor"
    assert res_clean["orchestration"]["status"] == "healthy"

    # 2. Test dirty state (issues found)
    mock_alert = {
        "id": "mask-0-1",
        "type": "masking",
        "track_indices": [0, 1],
        "severity": "warning",
        "message": "Low-end masking detected.",
        "fix_action": "set_volume on track 1 to volume 0.7",
        "fix_label": "Dampen Kick Drum Volume",
    }
    monkeypatch.setattr(kenn.mixing_doctor, "get_mixing_alerts", lambda: [mock_alert])
    
    res_dirty = answer_payload("mixing doctor check alerts")
    assert res_dirty["found"] is True
    assert res_dirty["intent"] == "orchestration"
    assert res_dirty["route"] == "mixing_doctor"
    orch = res_dirty["orchestration"]
    assert orch["status"] == "issues_found"
    assert "proposed_actions" in orch
    assert len(orch["proposed_actions"]) == 1
    assert orch["proposed_actions"][0]["type"] == "set_volume"
    assert orch["proposed_actions"][0]["command"] == "set_volume on track 1 to volume 0.7"


def test_orchestrator_integration_ableton():
    res = answer_payload("show my ableton session status")
    assert res["found"] is True
    assert res["intent"] == "orchestration"
    assert res["route"] == "ableton_controller"
    assert "orchestration" in res


def test_orchestrator_integration_ableton_connected(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setattr(AbletonOSCClient, "query_session_state", lambda self: {
        "status": "connected",
        "tracks": [
            {"name": "Vocals", "volume": 0.8, "pan": -0.25, "devices": [{"name": "Compressor"}]},
            {"name": "Drums", "volume": 0.7, "pan": 0.1, "devices": []}
        ]
    })



    res = answer_payload("show my connected ableton tracks")
    assert res["found"] is True

    assert res["intent"] == "orchestration"
    assert res["route"] == "ableton_controller"
    assert "orchestration" in res
    
    orch = res["orchestration"]
    assert orch["status"] == "connected"
    assert "Vocals" in orch["message"]
    assert len(orch["result"]["tracks"]) == 2
    assert orch["result"]["tracks"][0]["name"] == "Vocals"



def test_orchestrator_integration_ableton_write_denied_by_default(monkeypatch):
    # 2026-08-06: Mixing Doctor's clickable "Fix" buttons submit exactly
    # this kind of phrase as a chat message (mixing_doctor.py's fix_action
    # strings, e.g. "set_volume on track {idx} to volume 0.85"). Before
    # this fix, _dispatch_ableton() always queried and reported session
    # state instead of ever executing the write -- clicking "Fix" silently
    # did nothing. This guards the fix stays in place.
    monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("live_client should never be reached when denied")

    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.set_track_volume", _fail_if_called
    )
    res = answer_payload("set_volume on track 3 to volume 0.85")
    assert res["intent"] == "orchestration"
    assert res["route"] == "ableton_controller"
    assert res["orchestration"]["status"] == "failed" or "denied" in res["answer"].lower()
    assert "denied" in res["answer"].lower()


def test_orchestrator_integration_ableton_write_executes_when_allowed(monkeypatch):
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.set_track_volume",
        lambda idx, vol: True,
    )
    res = answer_payload("set_volume on track 3 to volume 0.85")
    assert res["intent"] == "orchestration"
    assert res["route"] == "ableton_controller"
    assert res["orchestration"]["status"] == "executed"
    assert "status: success" in res["answer"].lower()


def test_orchestrator_integration_ableton_mute_executes_when_allowed(monkeypatch):
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.set_track_mute",
        lambda idx, muted: True,
    )
    res = answer_payload("mute track 2")
    assert res["intent"] == "orchestration"
    assert res["route"] == "ableton_controller"
    assert res["orchestration"]["status"] == "executed"
    assert "muted ableton track 2" in res["answer"].lower()


def test_orchestrator_integration_ableton_solo_executes_when_allowed(monkeypatch):
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.set_track_solo",
        lambda idx, soloed: True,
    )
    res = answer_payload("solo track 1")
    assert res["orchestration"]["status"] == "executed"
    assert "soloed ableton track 1" in res["answer"].lower()


def test_orchestrator_integration_ableton_record_arm_executes_when_allowed(monkeypatch):
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.set_track_arm",
        lambda idx, armed: True,
    )
    res = answer_payload("record arm track 0")
    assert res["orchestration"]["status"] == "executed"
    assert "record-armed ableton track 0" in res["answer"].lower()


def test_orchestrator_integration_ableton_mute_denied_by_default(monkeypatch):
    monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("live_client should never be reached when denied")

    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.set_track_mute", _fail_if_called
    )
    res = answer_payload("mute track 2")
    assert "denied" in res["answer"].lower()


def test_orchestrator_integration_ableton_transport_executes_when_allowed(monkeypatch):
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.start_playback",
        lambda: True,
    )
    res = answer_payload("start playback")
    assert res["intent"] == "orchestration"
    assert res["route"] == "ableton_controller"
    assert res["orchestration"]["status"] == "executed"
    assert "started ableton playback" in res["answer"].lower()


def test_orchestrator_integration_ableton_tempo_executes_when_allowed(monkeypatch):
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.set_tempo",
        lambda bpm: True,
    )
    res = answer_payload("set tempo to 140 bpm")
    assert res["orchestration"]["status"] == "executed"
    assert "set ableton tempo to 140.0 bpm" in res["answer"].lower()


def test_orchestrator_integration_bpm_question_does_not_trigger_write():
    # "is 128 bpm too fast for techno?" mentions a BPM number without
    # asking to change anything -- must fall through to normal Q&A, not
    # get misclassified into the ableton_controller write path.
    res = answer_payload("is 128 bpm too fast for techno?")
    assert res.get("route") != "ableton_controller"


def test_orchestrator_integration_ableton_clip_launch_executes_when_allowed(monkeypatch):
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.launch_clip",
        lambda t_idx, c_idx: True,
    )
    res = answer_payload("launch the clip on track 2 slot 0")
    assert res["orchestration"]["status"] == "executed"
    assert "launched clip on track 2, slot 0" in res["answer"].lower()


def test_orchestrator_integration_ableton_scene_launch_executes_when_allowed(monkeypatch):
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.launch_scene",
        lambda s_idx: True,
    )
    res = answer_payload("fire scene 3")
    assert res["orchestration"]["status"] == "executed"
    assert "launched scene 3" in res["answer"].lower()


def test_orchestrator_integration_ableton_macro_executes_when_allowed(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        AbletonOSCClient, "get_device_parameters",
        lambda self, t, d: {"success": True, "parameters": [{"index": 2, "name": "Macro 1", "value": 0.0, "min": 0.0, "max": 127.0}]},
    )
    monkeypatch.setattr(AbletonOSCClient, "set_device_parameter", lambda self, t, d, p, v: True)

    res = answer_payload("set macro 1 on device 0 track 0 to 90")
    assert res["orchestration"]["status"] == "executed"
    assert "macro 1" in res["answer"].lower()


def test_orchestrator_integration_bare_macro_question_does_not_trigger_write():
    # "what does macro 1 do on this rack?" mentions a macro number without
    # asking to change anything -- must fall through, not misfire a write.
    res = answer_payload("what does macro 1 do on this rack?")
    assert res.get("route") != "ableton_controller"


def test_orchestrator_integration_arrangement_suggests_and_creates_scenes(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    created = []
    monkeypatch.setattr(
        AbletonOSCClient, "create_scene",
        lambda self, name="": created.append(name) or {"success": True, "scene_index": len(created) - 1, "name": name},
    )

    res = answer_payload("build a 32-bar verse/chorus structure with a build-up at bar 17")

    assert res["route"] == "arrangement_planner"
    assert res["orchestration"]["status"] == "created"
    assert created == ["Groove", "Build-up", "Drop"]
    assert "bars 1-16" in res["answer"]
    assert "starting point" in res["answer"].lower()
    # G6 (docs/KENN_IMPROVEMENT_PLAN.md): the ⚠️ untested-suggestion badge
    # used to only reach mix-review-followup answers -- the structure
    # itself is KENN's judgment call even after real scenes were created.
    assert res["contains_unvalidated_suggestions"] is True


def test_orchestrator_integration_arrangement_denied_still_shows_suggestion(monkeypatch):
    monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)

    res = answer_payload("build a 16 bar arrangement")

    assert res["route"] == "arrangement_planner"
    assert res["orchestration"]["status"] == "suggested_only"
    assert "Intro" in res["answer"]
    assert res["contains_unvalidated_suggestions"] is True


def test_orchestrator_integration_ableton_query_is_not_flagged_as_unvalidated():
    # A plain session-status query measures real session state -- it must
    # NOT get the untested-suggestion badge just because it went through
    # the orchestrator.
    res = answer_payload("show my ableton session status")
    assert res["route"] == "ableton_controller"
    assert res.get("contains_unvalidated_suggestions") is False


def test_ableton_session_display_narrows_to_a_named_track(monkeypatch):
    # Item 1 (docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md): a query
    # naming a specific track should show just that track, not dump the
    # whole session.
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setattr(AbletonOSCClient, "query_session_state", lambda self: {
        "status": "connected",
        "tracks": [
            {"name": "Vocals", "volume": 0.8, "pan": -0.25, "devices": []},
            {"name": "Drums", "volume": 0.7, "pan": 0.1, "devices": []},
            {"name": "Bass", "volume": 0.75, "pan": 0.0, "devices": []},
        ],
    })

    res = answer_payload("show me the vocals track")

    assert "Vocals" in res["orchestration"]["message"]
    assert "Drums" not in res["orchestration"]["message"]
    assert "Bass" not in res["orchestration"]["message"]
    assert "1 of 3 tracks" in res["orchestration"]["message"]


def test_ableton_session_display_falls_back_to_everything_when_nothing_matches(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setattr(AbletonOSCClient, "query_session_state", lambda self: {
        "status": "connected",
        "tracks": [
            {"name": "Vocals", "volume": 0.8, "pan": -0.25, "devices": []},
            {"name": "Drums", "volume": 0.7, "pan": 0.1, "devices": []},
        ],
    })

    res = answer_payload("show my ableton session status")

    assert "Vocals" in res["orchestration"]["message"]
    assert "Drums" in res["orchestration"]["message"]
    assert "2 tracks found" in res["orchestration"]["message"]


def test_orchestrator_dispatch_is_not_disabled_by_an_unrelated_stack_frame_named_handle():
    # Real bug found via self-review, live in the working tree: a
    # re-entrancy guard matched the bare function name "handle" -- but
    # http.server.BaseHTTPRequestHandler.handle() puts a frame literally
    # named "handle" on the stack of every real HTTP request through
    # server.py, so the guard silently forced orchestration to None for
    # virtually all production traffic (invisible to every existing test,
    # since pytest never puts a "handle" frame on the stack calling
    # answer_payload() directly -- this test manufactures one to catch
    # exactly that gap).
    def handle():
        return answer_payload("show my ableton session status")

    res = handle()
    assert res["route"] == "ableton_controller"
    assert "orchestration" in res


def test_orchestrator_dispatch_is_disabled_when_called_from_thursdays_handle():
    # The guard's actual intended target: thursday.orchestrator.handle()
    # calls Client.ask_kenn() -> thursday.client.ask_kenn() ->
    # kenn.core.chat.answer_payload() in-process -- this must still be
    # caught (module-scoped, not just the bare name) to avoid a real
    # re-entrant double-dispatch. Built via exec() in a fresh namespace
    # rather than mutating this test module's own __globals__["__name__"]
    # (which would permanently corrupt this file's identity for the rest
    # of the test run -- f_globals IS the live module namespace, not a
    # copy).
    namespace: dict = {"__name__": "thursday.orchestrator", "answer_payload": answer_payload}
    exec(
        "def handle():\n"
        "    return answer_payload('show my ableton session status')\n",
        namespace,
    )
    res = namespace["handle"]()

    assert res.get("orchestration") is None


def test_orchestrator_integration_arrangement_without_a_bar_count_falls_through():
    # classify()'s pattern requires an explicit bar count -- "build me a
    # good arrangement" has none, so this must fall through to normal
    # chat rather than misfire.
    res = answer_payload("build me a good arrangement")
    assert res.get("route") != "arrangement_planner"


def test_dispatch_arrangement_clarifies_when_called_without_a_bar_count():
    # _dispatch_arrangement()'s own clarify branch, exercised directly --
    # classify() filters this case out before dispatch() ever runs, but
    # the branch stays as defensive code for any future direct caller.
    from kenn.orchestrator import _dispatch_arrangement

    result = _dispatch_arrangement(query="build me a good arrangement")
    assert result["status"] == "clarify"


def test_orchestrator_integration_bare_bar_count_does_not_trigger_arrangement():
    # "this loop is 8 bars long" has a bar count but no structure word --
    # must fall through to normal chat, not misfire.
    res = answer_payload("this loop is 8 bars long, is that too short?")
    assert res.get("route") != "arrangement_planner"


def test_orchestrator_integration_create_scene_executes_when_allowed(monkeypatch):
    from kenn.ableton_osc_bridge import AbletonOSCClient

    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(
        AbletonOSCClient, "create_scene",
        lambda self, name="": {"success": True, "scene_index": 2, "name": name},
    )

    res = answer_payload("create a new scene called Bridge")
    assert res["orchestration"]["status"] == "executed"
    assert "scene" in res["answer"].lower()


def test_orchestrator_integration_scene_read_query_does_not_trigger_write():
    # "what's happening in scene 2?" mentions a scene without asking to
    # create one -- must fall through, not misfire a write.
    res = answer_payload("what's happening in scene 2?")
    assert res.get("route") != "ableton_controller"


def test_orchestrator_integration_ableton_session_read_mentioning_clip_stays_read_only(monkeypatch):
    # Contains "clip" but no launch/fire/play/trigger verb -- must stay on
    # the read path, not misfire a clip launch.
    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("launch_clip should never be reached for a read query")

    monkeypatch.setattr(
        "kenn.ableton_osc_bridge.live_client.launch_clip", _fail_if_called
    )
    res = answer_payload("show my ableton session, especially the clip on track 2")
    assert res["route"] == "ableton_controller"
    assert res["orchestration"]["status"] in {"connected", "disconnected"}


def test_orchestrator_integration_ableton_read_only_query_still_reports_session():
    # A pure status/read query must NOT be routed into the write-execution
    # branch just because it mentions Ableton.
    res = answer_payload("show my connected ableton tracks")
    assert res["intent"] == "orchestration"
    assert res["route"] == "ableton_controller"
    assert res["orchestration"]["status"] in {"connected", "disconnected"}


def test_orchestrator_integration_fallback_to_rag():
    # Ordinary question should fallback to RAG instead of triggering an agent
    res = answer_payload("what is crest factor?")
    # It should not be an orchestration route
    assert res.get("intent") != "orchestration"


def test_orchestrator_integration_audiogen_importer(monkeypatch):
    import audiogen_bridge
    from kenn.ableton_osc_bridge import AbletonOSCClient

    # Mock loop generation
    monkeypatch.setattr(audiogen_bridge, "generate_for_kenn", lambda prompt, emotion="", bars=4, project_id="": {
        "ok": True,
        "emotion": emotion or "joy",
        "bars": bars,
        "wav_path": "/tmp/mock_loop.wav",
        "src": "/portfolio/mock_loop.wav",
        "portfolio_entry": {"title": "Mock AudioGen loop"}
    })

    # Mock OSC client load_clip method
    monkeypatch.setattr(AbletonOSCClient, "load_clip", lambda self, t_idx, c_idx, path: True)

    # Perform the query. Track-loading is handled inside
    # chat_routing.audio_generation_payload() itself now (ported from the
    # orchestrator's old _dispatch_audiogen), not via the orchestrator --
    # audiogen is deliberately not classify()'d by the orchestrator (see
    # orchestrator.py's classify() comment) so full-song requests still work.
    res = answer_payload("generate a 120bpm techno loop and load it into track 2")
    assert res["found"] is True
    assert res["intent"] == "generate"
    assert res["route"] == "audiogen"
    assert "orchestration" not in res

    result = res["audiogen"]
    assert result["ok"] is True
    assert result["load_success"] is True
    assert "Loaded into Ableton track 2 via OSC" in res["answer"]

