"""Tests for the LLM-facing, confirmation-gated Ableton command gateway."""

from __future__ import annotations

from copy import deepcopy

from kenn.core.live_action_service import LiveActionService
from kenn.core.device_units import raw_to_display
from kenn.core.live_recipe import LiveRecipeService, RECIPE_SCHEMA, RECIPE_RECEIPT_SCHEMA
import kenn.core.live_command as live_command_module
from kenn.core.live_command import handle_command, validate_llm_plan


class FakeLive:
    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "is_playing": False,
            "selected_track_index": 0,
            "current_song_time": 16.0,
            "locators": [],
            "tracks": [
                {"index": 0, "name": "Kick", "volume": 0.5, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "has_midi_input": True, "devices": []},
                {"index": 1, "name": "Bass", "volume": 0.5, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "has_midi_input": True, "devices": []},
                {"index": 2, "name": "Vocal", "volume": 0.5, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "has_midi_input": False, "devices": [{"index": 0, "name": "Compressor"}]},
                {"index": 3, "name": "Synth", "volume": 0.5, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "has_midi_input": True, "devices": [{"index": 0, "name": "EQ Eight"}]},
            ],
            "scenes": [{"index": 0, "name": "Intro"}, {"index": 1, "name": "Chorus"}],
        }
        self.writes: list[tuple] = []
        # Production AbletonOSC reports Compressor Threshold raw-normalized
        # (measured real-Live 2026-09-21: raw 0.55 reads "-12 dB", range
        # 0.0..1.0). The double keeps raw domain so display conversions
        # resolve exactly as they do against Live.
        self.threshold = 0.55
        self.eq_gain = 0.0
        self.frequency_value = 250.0
        self.frequency_display = "250 Hz"
        self.scene_triggered: dict[int, bool] = {}
        self.clip_playing: dict[tuple[int, int], bool] = {(1, 0): True}
        self.return_tracks = [
            {"index": 0, "name": "A-Reverb", "devices": ["Reverb"]},
            {"index": 1, "name": "B-Delay", "devices": ["Delay"]},
        ]
        self.sends: dict[tuple[int, int], float] = {}
        self.selected_device = {"success": True, "track_index": 2, "device_index": 0}

    def query_session_state(self):
        return deepcopy(self.state)

    def get_current_song_time(self) -> float:
        return float(self.state["current_song_time"])

    def get_locators_with_status(self) -> tuple[list[dict], bool]:
        return deepcopy(self.state["locators"]), True

    def get_locators(self) -> list[dict]:
        return deepcopy(self.state["locators"])

    def add_locator(self, name: str) -> bool:
        self.writes.append(("locator", name, self.state["current_song_time"]))
        self.state["locators"].append({
            "index": len(self.state["locators"]),
            "name": name,
            "time_beats": self.state["current_song_time"],
        })
        return True

    def remove_locator(self, name: str, time_beats: float) -> bool:
        self.writes.append(("remove_locator", name, time_beats))
        before = len(self.state["locators"])
        self.state["locators"] = [
            item for item in self.state["locators"]
            if not (item.get("name") == name and abs(float(item.get("time_beats", -1)) - float(time_beats)) <= 1e-4)
        ]
        return len(self.state["locators"]) == before - 1

    def get_return_tracks(self) -> list[dict]:
        return deepcopy(self.return_tracks)

    def get_track_send(self, track_index: int, send_index: int) -> float | None:
        return self.sends.get((track_index, send_index), 0.2)

    def set_track_send(self, track_index: int, send_index: int, value: float) -> bool:
        self.writes.append(("send", track_index, send_index, value))
        self.sends[(track_index, send_index)] = value
        return True

    def set_track_volume(self, index: int, value: float) -> bool:
        self.writes.append(("volume", index, value))
        self.state["tracks"][index]["volume"] = value
        return True

    def set_track_pan(self, index: int, value: float) -> bool:
        self.writes.append(("pan", index, value))
        self.state["tracks"][index]["pan"] = value
        return True

    def set_track_mute(self, index: int, value: bool) -> bool:
        self.writes.append(("mute", index, value))
        self.state["tracks"][index]["muted"] = value
        return True

    def set_track_solo(self, index: int, value: bool) -> bool:
        self.writes.append(("solo", index, value))
        self.state["tracks"][index]["soloed"] = value
        return True

    def set_track_arm(self, index: int, value: bool) -> bool:
        self.writes.append(("arm", index, value))
        self.state["tracks"][index]["armed"] = value
        return True

    def set_track_name(self, index: int, value: str) -> bool:
        self.writes.append(("name", index, value))
        self.state["tracks"][index]["name"] = value
        return True

    def create_midi_track(self, insertion_index: int) -> bool:
        assert insertion_index == -1
        insertion_index = len(self.state["tracks"])
        self.writes.append(("create_midi_track", insertion_index))
        self.state["tracks"].append({
            "index": insertion_index,
            "name": "MIDI",
            "volume": 0.5,
            "pan": 0.0,
            "muted": False,
            "soloed": False,
            "armed": False,
            "has_midi_input": True,
            "devices": [],
        })
        return True

    def create_return_track(self) -> bool:
        self.writes.append(("create_return_track", len(self.return_tracks)))
        self.return_tracks.append({"index": len(self.return_tracks), "name": "Return", "devices": []})
        return True

    def set_return_track_name(self, index: int, value: str) -> bool:
        self.writes.append(("return_name", index, value))
        self.return_tracks[index]["name"] = value
        return True

    def get_track_has_midi_input(self, index: int) -> bool | None:
        track = next((item for item in self.state["tracks"] if item.get("index") == index), None)
        return None if track is None else bool(track.get("has_midi_input"))

    def set_selected_track(self, index: int) -> bool:
        self.writes.append(("focus", index))
        self.state["selected_track_index"] = index
        return True

    def get_selected_device(self) -> dict:
        return deepcopy(self.selected_device)

    def set_selected_device(self, track_index: int, device_index: int) -> bool:
        self.writes.append(("focus_device", track_index, device_index))
        self.selected_device = {"success": True, "track_index": track_index, "device_index": device_index}
        self.state["selected_track_index"] = track_index
        return True

    def start_playback(self) -> bool:
        self.writes.append(("play",))
        self.state["is_playing"] = True
        return True

    def stop_playback(self) -> bool:
        self.writes.append(("stop",))
        self.state["is_playing"] = False
        return True

    def get_device_parameters(self, track_index: int, device_index: int) -> dict:
        if track_index == 3 and any(
            isinstance(item, dict)
            and int(item.get("index", -1)) == device_index
            and str(item.get("name", "")).strip().lower() == "eq eight"
            for item in self.state["tracks"][3]["devices"]
        ):
            return {
                "success": True,
                "device_name": "EQ Eight",
                "parameters": [
                    # Match the filtered-but-sparse shape returned by the
                    # production bridge: EQ Eight's visible controls keep
                    # their original Live parameter indices.
                    {"index": 11, "name": "1 Frequency A", "value": self.frequency_value, "value_display": self.frequency_display, "min": 20.0, "max": 20000.0},
                    {"index": 12, "name": "1 Gain A", "value": self.eq_gain, "min": -15.0, "max": 15.0},
                ],
            }
        return {
            "success": True,
            "device_name": "Compressor",
            "parameters": [{"index": 0, "name": "Threshold", "value": self.threshold, "min": 0.0, "max": 1.0}],
        }

    def set_device_parameter(self, track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        if track_index == 3 and any(
            isinstance(item, dict)
            and int(item.get("index", -1)) == device_index
            and str(item.get("name", "")).strip().lower() == "eq eight"
            for item in self.state["tracks"][3]["devices"]
        ):
            if parameter_index == 11:
                self.writes.append(("eq_frequency", track_index, device_index, parameter_index, value))
                self.frequency_value = value
                self.frequency_display = f"{value:g} Hz"
            else:
                self.writes.append(("eq_gain", track_index, device_index, parameter_index, value))
                self.eq_gain = value
            return True
        self.writes.append(("threshold", track_index, device_index, parameter_index, value))
        self.threshold = value
        return True

    def get_device_parameter_value_string(self, track_index: int, device_index: int, parameter_index: int) -> dict:
        if track_index == 3 and device_index == 0 and parameter_index == 11:
            return {"success": True, "value_string": self.frequency_display}
        if track_index == 3 and device_index == 0 and parameter_index == 12:
            return {"success": True, "value_string": f"{self.eq_gain:g} dB"}
        if track_index == 2 and device_index == 0 and parameter_index == 0:
            display, error = raw_to_display(
                device_name="Compressor", parameter_name="Threshold",
                raw=self.threshold, unit="db",
            )
            if error is None:
                return {"success": True, "value_string": f"{display:g} dB"}
        return {"success": False, "error": "test double has no display metadata"}

    def insert_device_with_result(self, track_index: int, device_name: str, insertion_index: int) -> dict:
        assert track_index == 1
        assert device_name in {"EQ Eight", "Glue Compressor"}
        assert insertion_index == len(self.state["tracks"][track_index]["devices"])
        self.writes.append(("insert_device", track_index, insertion_index, device_name))
        self.state["tracks"][track_index]["devices"].append({"index": insertion_index, "name": device_name})
        return {"success": True, "track_index": track_index, "device_index": insertion_index, "device_name": device_name}

    def remove_device_with_result(self, track_index: int, device_index: int, device_name: str) -> dict:
        devices = self.state["tracks"][track_index]["devices"]
        assert devices[device_index]["name"] == device_name
        self.writes.append(("remove_device", track_index, device_index, device_name))
        devices.pop(device_index)
        for index, item in enumerate(devices):
            item["index"] = index
        return {"success": True, "track_index": track_index, "device_index": device_index, "device_name": device_name}

    def launch_scene(self, scene_index: int) -> bool:
        self.writes.append(("launch_scene", scene_index))
        self.scene_triggered[scene_index] = True
        return True

    def get_scene_playback_state(self, scene_index: int) -> dict:
        return {"success": True, "scene_index": scene_index, "is_triggered": bool(self.scene_triggered.get(scene_index))}

    def get_scene_names(self) -> list:
        return [scene["name"] for scene in self.state["scenes"]]

    def get_clip_playback_state(self, track_index: int, clip_slot_index: int) -> dict:
        playing = self.clip_playing.get((track_index, clip_slot_index), False)
        return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, "is_playing": playing, "is_triggered": False}

    def stop_clip_slot(self, track_index: int, clip_slot_index: int) -> bool:
        self.writes.append(("stop_clip", track_index, clip_slot_index))
        self.clip_playing[(track_index, clip_slot_index)] = False
        return True


class UnacknowledgedInsertionLive(FakeLive):
    """Simulate Live mutating successfully while the extension reply is lost."""

    def insert_device_with_result(self, track_index: int, device_name: str, insertion_index: int) -> dict:
        assert track_index == 1
        assert insertion_index == len(self.state["tracks"][track_index]["devices"])
        self.writes.append(("insert_device", track_index, insertion_index, device_name))
        self.state["tracks"][track_index]["devices"].append({"index": insertion_index, "name": device_name})
        return {"success": False, "error": "No response from AbletonOSC"}


class DeviceSetupLive(FakeLive):
    """Small loopback model for insert-then-configure proposals."""

    def __init__(self) -> None:
        super().__init__()
        self.state["tracks"][1]["name"] = "Hi Hat"
        self.dry_wet = 0.0
        self.fail_setup_write = False

    def insert_device_with_result(self, track_index: int, device_name: str, insertion_index: int) -> dict:
        assert (track_index, device_name, insertion_index) == (1, "Hybrid Reverb", 0)
        self.writes.append(("insert_device", track_index, insertion_index, device_name))
        self.state["tracks"][track_index]["devices"].append({"index": insertion_index, "name": device_name})
        return {"success": True}

    def get_device_parameters(self, track_index: int, device_index: int) -> dict:
        if track_index == 1 and self.state["tracks"][1]["devices"]:
            return {
                "success": True,
                "device_name": "Hybrid Reverb",
                "parameters": [{"index": 7, "name": "Dry/Wet", "value": self.dry_wet, "min": 0.0, "max": 1.0}],
            }
        return super().get_device_parameters(track_index, device_index)

    def set_device_parameter(self, track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        if track_index == 1:
            assert (device_index, parameter_index) == (0, 7)
            self.writes.append(("dry_wet", value))
            if self.fail_setup_write:
                return False
            self.dry_wet = value
            return True
        return super().set_device_parameter(track_index, device_index, parameter_index, value)


class MismatchedNameInsertionLive(FakeLive):
    """Simulate AbletonOSC's browser search resolving the requested name to
    a different real device, exactly as found in real-Live qualification
    (2026-09-05): requesting "Reverb" actually inserted "Convolution Reverb"."""

    WRONG_NAME = "Convolution Reverb"

    def insert_device_with_result(self, track_index: int, device_name: str, insertion_index: int) -> dict:
        assert insertion_index == len(self.state["tracks"][track_index]["devices"])
        self.writes.append(("insert_device", track_index, insertion_index, self.WRONG_NAME))
        self.state["tracks"][track_index]["devices"].append({"index": insertion_index, "name": self.WRONG_NAME})
        return {"success": True, "track_index": track_index, "device_index": insertion_index, "device_name": self.WRONG_NAME}


class UnremovableMismatchedNameInsertionLive(MismatchedNameInsertionLive):
    """Same mismatch, but the automatic cleanup removal also fails."""

    def remove_device_with_result(self, track_index: int, device_index: int, device_name: str) -> dict:
        return {"success": False, "error": "simulated: Live refused the removal"}


def _service(fake: FakeLive) -> LiveActionService:
    return LiveActionService(fake)


def test_command_boundary_converts_unhandled_timeout_to_safe_plain_english() -> None:
    class TimedOutService:
        client = object()

        def snapshot(self, **_kwargs):
            raise TimeoutError("raw socket timeout details")

    result = handle_command("mute track 2", session_id="timeout", service=TimedOutService())

    assert result["status"] == "failed"
    assert result["changed"] is False
    assert result["error_code"] == "ableton_timeout"
    assert result["answer"] == "Ableton Live isn't responding — check the connection and try again."
    assert "raw socket" not in str(result)


def test_unknown_command_lists_supported_demo_capabilities() -> None:
    result = handle_command(
        "make it sound like a purple spaceship",
        session_id="unknown-command",
        service=_service(FakeLive()),
        allow_llm=False,
    )

    assert result["status"] == "clarification_required"
    assert result["changed"] is False
    assert result["answer"].startswith("I'm not sure what you're asking.")
    assert "track volume/pan/mute/solo" in result["answer"]
    assert "exact undo" in result["answer"]


def test_missing_eq_names_devices_visible_on_the_target_track() -> None:
    fake = FakeLive()
    fake.state["tracks"][1]["devices"] = [{"index": 0, "name": "Compressor"}]

    result = handle_command(
        "boost 3 dB at 200 Hz on the Bass EQ",
        session_id="missing-eq",
        service=_service(fake),
        allow_llm=False,
    )

    assert result["status"] == "clarification_required"
    assert result["changed"] is False
    assert "I can't find EQ Eight" in result["answer"]
    assert "Here's what I can see: Compressor" in result["answer"]
    assert "nothing changed" in result["answer"].lower()


def test_out_of_range_device_value_reports_verified_safe_range() -> None:
    result = handle_command(
        "set the Vocal Compressor threshold to -70 dB",
        session_id="unsafe-threshold",
        service=_service(FakeLive()),
        allow_llm=False,
    )

    assert result["status"] == "clarification_required"
    assert result["changed"] is False
    assert result["answer"] == "That value is outside the safe range. The verified range for Threshold is -57.2 to 6 dB."


def test_again_and_it_resolve_through_real_command_path() -> None:
    fake = FakeLive()
    service = _service(fake)
    first = handle_command("mute track 2", session_id="command-context", service=service, allow_llm=False)
    assert first["status"] == "confirmation_required"

    repeated = handle_command("again", session_id="command-context", service=service, allow_llm=False)
    assert repeated["status"] == "confirmation_required"
    assert repeated["resolved_command"] == "mute track 2"
    assert repeated["proposal"]["track_name"] == "Bass"

    anaphora = handle_command("unmute it", session_id="command-context", service=service, allow_llm=False)
    assert anaphora["status"] == "confirmation_required"
    assert anaphora["resolved_command"] == "unmute Bass"
    assert anaphora["proposal"]["track_name"] == "Bass"


def test_command_response_exposes_stage_latency_against_demo_budget() -> None:
    result = handle_command("mute track 2", session_id="command-latency", service=_service(FakeLive()), allow_llm=False)

    assert result["latency"]["parse_ms"] < 50
    assert result["latency"]["snapshot_ms"] < 200
    assert result["latency"]["total_ms"] < 650
    assert result["latency"]["budget_ms"]["total"] == 650.0
    assert result["latency"]["budget_exceeded"] == []


def test_numbered_track_is_proposed_without_a_write_then_verified_on_confirm() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command("mute track 2", session_id="command-track", service=service)
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["track_index"] == 1
    assert planned["proposal"]["track_name"] == "Bass"
    assert fake.writes == []

    applied = handle_command(
        "mute track 2",
        session_id="command-track",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.writes == [("mute", 1, True)]


def test_create_midi_track_command_is_confirmed_and_verified() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command(
        "create a MIDI track named Hi Hats",
        session_id="command-create-midi",
        service=service,
        allow_llm=False,
    )
    assert planned["status"] == "confirmation_required"
    assert planned["proposal_kind"] == "track_creation"
    assert planned["proposal"]["new_track_name"] == "Hi Hats"
    assert fake.writes == []

    applied = handle_command(
        "create a MIDI track named Hi Hats",
        session_id="command-create-midi",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
        allow_llm=False,
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.state["tracks"][-1]["name"] == "Hi Hats"


def test_audio_track_command_is_confirmation_only_and_type_specific() -> None:
    fake = FakeLive()
    planned = handle_command(
        "create an audio track named Vox Print",
        session_id="command-create-audio",
        service=_service(fake),
        allow_llm=False,
    )
    assert planned["status"] == "confirmation_required"
    assert planned["proposal_kind"] == "track_creation"
    assert planned["proposal"]["action"] == "create_audio_track"
    assert planned["proposal"]["new_track_name"] == "Vox Print"
    assert "new audio track" in planned["answer"]
    assert fake.writes == []


def test_return_track_command_is_confirmation_bound_and_readback_verified() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command(
        "create a return track named Vocal Verb",
        session_id="command-create-return",
        service=service,
        allow_llm=False,
    )
    assert planned["status"] == "confirmation_required"
    assert planned["proposal_kind"] == "return_track_creation"
    assert planned["proposal"]["new_return_track_name"] == "Vocal Verb"
    assert fake.writes == []

    applied = handle_command(
        "",
        session_id="command-create-return",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
        allow_llm=False,
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["undo"]["available"] is False
    assert fake.return_tracks[-1]["name"] == "Vocal Verb"
    assert fake.writes == [("create_return_track", 2), ("return_name", 2, "Vocal Verb")]


def test_reverb_setup_command_binds_display_value_without_writing_before_confirmation() -> None:
    fake = DeviceSetupLive()
    planned = handle_command(
        "add reverb to hi hat at 25% dry wet",
        session_id="command-device-setup",
        service=_service(fake),
        allow_llm=False,
    )

    assert planned["status"] == "confirmation_required"
    assert planned["proposal_kind"] == "device_setup"
    assert planned["proposal"]["device_name"] == "Hybrid Reverb"
    assert planned["proposal"]["parameter_name"] == "Dry/Wet"
    assert planned["proposal"]["parameter_display_value"] == 25.0
    assert planned["proposal"]["parameter_after_value"] == 0.25
    assert fake.writes == []


def test_compressor_threshold_setup_is_confirmation_bound_without_writing() -> None:
    fake = FakeLive()
    fake.state["tracks"][2]["devices"] = []

    planned = handle_command(
        "add a compressor to Vocal and set threshold to -20 dB",
        session_id="command-compressor-setup",
        service=_service(fake),
        allow_llm=False,
    )

    assert planned["status"] == "confirmation_required"
    assert planned["proposal_kind"] == "device_setup"
    assert planned["proposal"]["device_name"] == "Compressor"
    assert planned["proposal"]["parameter_name"] == "Threshold"
    assert planned["proposal"]["parameter_display_value"] == -20.0
    assert "Threshold to -20 dB" in planned["answer"]
    assert "-20%" not in planned["answer"]
    assert 0.0 <= planned["proposal"]["parameter_after_value"] <= 1.0
    assert fake.writes == []


def test_explicit_track_correction_is_replanned_through_the_gateway() -> None:
    fake = FakeLive()
    service = _service(fake)
    session_id = "command-correct-track"

    first = handle_command(
        "mute track 2",
        session_id=session_id,
        service=service,
        allow_llm=False,
    )
    corrected = handle_command(
        "I meant track 3",
        session_id=session_id,
        service=service,
        allow_llm=False,
    )

    assert first["proposal"]["track_name"] == "Bass"
    assert corrected["status"] == "confirmation_required"
    assert corrected["resolved_command"] == "mute track 3"
    assert corrected["context_resolution"]["resolution"] == "corrected_track_target"
    assert corrected["proposal"]["track_name"] == "Vocal"
    assert fake.writes == []


def test_other_one_requires_an_exact_identity_through_the_gateway() -> None:
    fake = FakeLive()

    result = handle_command(
        "no, the other one",
        session_id="command-other-one",
        service=_service(fake),
        allow_llm=False,
    )

    assert result["status"] == "clarification_required"
    assert result["context_resolution"]["resolution"] == "correction_requires_clarification"
    assert "Name the track or device" in result["answer"]
    assert fake.writes == []


def test_solo_and_analyze_never_silently_degrades_to_solo_only() -> None:
    fake = FakeLive()

    result = handle_command(
        "solo the Bass and check the low end",
        session_id="command-solo-analysis-guard",
        service=_service(fake),
        allow_llm=False,
    )

    assert result["status"] == "clarification_required"
    assert result["intent"]["action"] == "recipe"
    assert "fresh post-solo capture" in result["answer"]
    assert "proposal" not in result
    assert fake.writes == []


def test_reverb_setup_applies_parameter_after_insertion_and_supports_identity_bound_undo() -> None:
    fake = DeviceSetupLive()
    service = _service(fake)
    planned = handle_command(
        "add reverb to hi hat at 25% dry wet",
        session_id="command-device-setup-apply",
        service=service,
        allow_llm=False,
    )
    applied = handle_command(
        "",
        session_id="command-device-setup-apply",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
        allow_llm=False,
    )

    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.dry_wet == 0.25
    assert fake.state["tracks"][1]["devices"] == [{"index": 0, "name": "Hybrid Reverb"}]
    assert fake.writes == [("insert_device", 1, 0, "Hybrid Reverb"), ("dry_wet", 0.25)]

    undo = service.propose_undo(applied["receipt"], session_id="command-device-setup-undo")
    assert undo["ok"] is True
    undone = service.execute_device_removal(
        undo["proposal"],
        confirm_token=undo["proposal"]["confirmation_token"],
        session_id="command-device-setup-undo",
        idempotency_key=undo["proposal"]["action_id"],
    )
    assert undone["ok"] is True
    assert fake.state["tracks"][1]["devices"] == []


def test_reverb_setup_rolls_back_inserted_device_when_parameter_readback_fails() -> None:
    fake = DeviceSetupLive()
    fake.fail_setup_write = True
    service = _service(fake)
    planned = handle_command(
        "add reverb to hi hat at 25% dry wet",
        session_id="command-device-setup-rollback",
        service=service,
        allow_llm=False,
    )
    result = handle_command(
        "",
        session_id="command-device-setup-rollback",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
        allow_llm=False,
    )

    assert result["status"] == "failed"
    assert result["receipt"]["status"] == "failed_rolled_back"
    assert result["receipt"]["rollback"]["reverted"] is True
    assert fake.state["tracks"][1]["devices"] == []


def test_llm_create_midi_track_plan_is_append_bound_and_confirmation_only() -> None:
    fake = FakeLive()
    snapshot = fake.query_session_state()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "create_midi_track",
        "new_track_name": "Hi Hats",
        "insertion_index": None,
    }

    checked = validate_llm_plan(plan, snapshot)
    assert checked["ok"] is True
    result = handle_command("", session_id="command-llm-create-midi", service=_service(fake), llm_plan=plan)

    assert result["status"] == "confirmation_required"
    assert result["changed"] is False
    assert result["proposal"]["action"] == "create_midi_track"
    assert result["proposal"]["insertion_index"] == len(fake.state["tracks"])
    assert result["proposal"]["new_track_name"] == "Hi Hats"
    assert fake.writes == []

    middle_insert = {**plan, "insertion_index": 1}
    assert validate_llm_plan(middle_insert, snapshot)["ok"] is False
    unrelated_target = {**plan, "track_index": 0}
    assert validate_llm_plan(unrelated_target, snapshot)["ok"] is False


def test_llm_create_return_track_plan_is_append_bound_and_confirmation_only() -> None:
    fake = FakeLive()
    snapshot = fake.query_session_state()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "create_return_track",
        "new_track_name": "Vocal Verb",
        "insertion_index": None,
    }
    checked = validate_llm_plan(plan, snapshot)
    assert checked["ok"] is True
    result = handle_command("", session_id="command-llm-create-return", service=_service(fake), llm_plan=plan)
    assert result["status"] == "confirmation_required"
    assert result["proposal"]["action"] == "create_return_track"
    assert result["proposal"]["return_track_index"] == len(fake.return_tracks)
    assert fake.writes == []
    assert validate_llm_plan({**plan, "insertion_index": 1}, snapshot)["ok"] is False


def test_scene_launch_command_is_proposed_verified_and_replay_rejected() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command("play scene 2", session_id="command-scene", service=service)
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["scene_index"] == 1
    assert planned["proposal"]["scene_name"] == "Chorus"
    assert fake.writes == []

    applied = handle_command(
        "play scene 2",
        session_id="command-scene",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.writes == [("launch_scene", 1)]

    replay = handle_command(
        "play scene 2",
        session_id="command-scene",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert replay["status"] != "applied"
    assert fake.writes == [("launch_scene", 1)]


def test_named_locator_command_is_proposed_verified_and_replay_rejected() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command(
        "add a locator named Verse at the current position",
        session_id="command-locator",
        service=service,
    )
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["locator_name"] == "Verse"
    assert planned["proposal"]["locator_time_beats"] == 16.0
    assert fake.writes == []

    applied = handle_command(
        "add a locator named Verse at the current position",
        session_id="command-locator",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.writes == [("locator", "Verse", 16.0)]

    replay = handle_command(
        "add a locator named Verse at the current position",
        session_id="command-locator",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert replay["status"] != "applied"
    assert fake.writes == [("locator", "Verse", 16.0)]


def test_named_locator_removal_is_proposed_and_verified() -> None:
    fake = FakeLive()
    fake.state["locators"] = [{"index": 0, "name": "Verse", "time_beats": 16.0}]
    service = _service(fake)
    planned = handle_command(
        "remove the locator named Verse at the current position",
        session_id="command-remove-locator",
        service=service,
    )
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["action"] == "remove_locator"
    assert fake.writes == []
    applied = handle_command(
        "remove the locator named Verse at the current position",
        session_id="command-remove-locator",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["readback"] == {"exists": False, "name": "Verse", "time_beats": 16.0}
    assert fake.state["locators"] == []


def test_focus_track_command_is_proposed_and_verified() -> None:
    fake = FakeLive()
    planned = handle_command("focus track 2", session_id="command-focus", service=_service(fake))
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["track_index"] == 1
    assert planned["proposal"]["track_name"] == "Bass"
    assert planned["proposal"]["previous_track_index"] == 0
    assert fake.writes == []

    applied = handle_command(
        "focus track 2",
        session_id="command-focus",
        service=_service(fake),
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.state["selected_track_index"] == 1
    assert fake.writes == [("focus", 1)]


def test_focus_device_command_is_proposed_and_verified() -> None:
    fake = FakeLive()
    planned = handle_command("focus EQ Eight on track 4", session_id="command-focus-device", service=_service(fake))
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["action"] == "focus_device"
    assert planned["proposal"]["track_index"] == 3
    assert planned["proposal"]["device_index"] == 0
    assert planned["proposal"]["previous_track_index"] == 2
    assert planned["proposal"]["previous_device_name"] == "Compressor"
    assert fake.writes == []

    applied = handle_command(
        "focus EQ Eight on track 4",
        session_id="command-focus-device",
        service=_service(fake),
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.selected_device["track_index"] == 3
    assert fake.writes == [("focus_device", 3, 0)]


def test_stop_clip_command_is_proposed_verified_and_replay_rejected() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command("stop clip slot 1 on track 2", session_id="command-clip", service=service)
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["track_index"] == 1
    assert planned["proposal"]["track_name"] == "Bass"
    assert planned["proposal"]["clip_slot_index"] == 0
    assert fake.writes == []

    applied = handle_command(
        "stop clip slot 1 on track 2",
        session_id="command-clip",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.writes == [("stop_clip", 1, 0)]

    replay = handle_command(
        "stop clip slot 1 on track 2",
        session_id="command-clip",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert replay["status"] != "applied"
    assert fake.writes == [("stop_clip", 1, 0)]


def test_set_send_command_is_proposed_verified_and_replay_rejected() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command("set the reverb send on track 2 to 0.6", session_id="command-send", service=service)
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["action"] == "set_send"
    assert planned["proposal"]["track_index"] == 1
    assert planned["proposal"]["track_name"] == "Bass"
    assert planned["proposal"]["return_track_index"] == 0
    assert planned["proposal"]["return_track_name"] == "A-Reverb"
    assert planned["proposal"]["after"] == 0.6
    assert fake.writes == []

    applied = handle_command(
        "set the reverb send on track 2 to 0.6",
        session_id="command-send",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.writes == [("send", 1, 0, 0.6)]

    replay = handle_command(
        "set the reverb send on track 2 to 0.6",
        session_id="command-send",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert replay["status"] != "applied"
    assert fake.writes == [("send", 1, 0, 0.6)]


def test_set_send_percentage_is_converted_before_proposal() -> None:
    fake = FakeLive()
    service = _service(fake)

    planned = handle_command(
        "set reverb send on track 2 to 25%",
        session_id="command-send-percent",
        service=service,
    )

    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["after"] == 0.25
    assert planned["proposal"]["return_track_name"] == "A-Reverb"
    assert fake.writes == []


def test_set_send_named_track_is_identity_bound_before_proposal() -> None:
    fake = FakeLive()
    service = _service(fake)

    planned = handle_command(
        "set the reverb send on Bass to 25%",
        session_id="command-send-named-track",
        service=service,
    )

    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["track_index"] == 1
    assert planned["proposal"]["track_name"] == "Bass"
    assert planned["proposal"]["return_track_name"] == "A-Reverb"
    assert planned["proposal"]["after"] == 0.25
    assert fake.writes == []


def test_mute_send_proposes_zero_without_muting_source_track() -> None:
    fake = FakeLive()
    service = _service(fake)

    planned = handle_command(
        "mute the reverb send on Bass",
        session_id="command-mute-send",
        service=service,
    )

    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["action"] == "set_send"
    assert planned["proposal"]["track_name"] == "Bass"
    assert planned["proposal"]["return_track_name"] == "A-Reverb"
    assert planned["proposal"]["after"] == 0.0
    assert fake.writes == []


def test_unsupported_send_control_never_becomes_track_action() -> None:
    fake = FakeLive()
    service = _service(fake)

    result = handle_command(
        "unmute the reverb send on Bass",
        session_id="command-unmute-send",
        service=service,
    )

    assert result["status"] != "confirmation_required"
    assert result.get("proposal") is None
    assert fake.writes == []


def test_unsupported_device_control_never_becomes_track_action() -> None:
    fake = FakeLive()
    service = _service(fake)

    result = handle_command(
        "mute the Compressor on Bass",
        session_id="command-mute-device",
        service=service,
    )

    assert result["status"] != "confirmation_required"
    assert result.get("proposal") is None
    assert fake.writes == []


def test_abbreviated_device_control_never_becomes_track_action() -> None:
    fake = FakeLive()
    service = _service(fake)

    result = handle_command(
        "solo the compressor on Bass",
        session_id="command-solo-device-alias",
        service=service,
    )

    assert result["status"] != "confirmation_required"
    assert result.get("proposal") is None
    assert fake.writes == []


def test_generic_plugin_control_never_becomes_track_action() -> None:
    fake = FakeLive()
    service = _service(fake)

    result = handle_command(
        "mute the plugin on Bass",
        session_id="command-mute-plugin",
        service=service,
    )

    assert result["status"] != "confirmation_required"
    assert result.get("proposal") is None
    assert fake.writes == []


def test_unsupported_return_control_never_becomes_source_track_action() -> None:
    fake = FakeLive()
    service = _service(fake)

    result = handle_command(
        "solo the reverb return for Bass",
        session_id="command-solo-return",
        service=service,
    )

    assert result["status"] != "confirmation_required"
    assert result.get("proposal") is None
    assert fake.writes == []


def test_unsupported_clip_control_never_becomes_track_action() -> None:
    fake = FakeLive()
    service = _service(fake)

    result = handle_command(
        "mute the clip on Bass",
        session_id="command-mute-clip",
        service=service,
    )

    assert result["status"] != "confirmation_required"
    assert result.get("proposal") is None
    assert fake.writes == []


def test_unsupported_scene_control_never_becomes_track_action() -> None:
    fake = FakeLive()
    service = _service(fake)

    result = handle_command(
        "solo scene Verse on Bass",
        session_id="command-solo-scene",
        service=service,
    )

    assert result["status"] != "confirmation_required"
    assert result.get("proposal") is None
    assert fake.writes == []


def test_unsupported_master_control_never_becomes_track_action() -> None:
    fake = FakeLive()
    service = _service(fake)

    result = handle_command(
        "mute master for Bass",
        session_id="command-mute-master",
        service=service,
    )

    assert result["status"] != "confirmation_required"
    assert result.get("proposal") is None
    assert fake.writes == []

def test_set_send_command_ambiguous_return_name_is_a_clarification() -> None:
    fake = FakeLive()
    fake.return_tracks.append({"index": 2, "name": "A-Reverb", "devices": ["Reverb"]})
    service = _service(fake)
    result = handle_command("set the reverb send on track 2 to 0.6", session_id="command-send-ambiguous", service=service)
    assert result["status"] != "confirmation_required"
    assert fake.writes == []


def test_natural_language_track_rename_is_proposed_then_undoable() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command("rename track 2 to Low Bass", session_id="command-rename", service=service)
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["action"] == "rename_track"
    assert planned["proposal"]["before"] == "Bass"
    assert planned["proposal"]["after"] == "Low Bass"
    applied = handle_command(
        "rename track 2 to Low Bass",
        session_id="command-rename",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key="command-rename-apply",
    )
    assert applied["status"] == "applied"
    assert fake.state["tracks"][1]["name"] == "Low Bass"


def test_llm_rename_plan_requires_exact_new_name_and_rejects_duplicates() -> None:
    fake = FakeLive()
    snapshot = fake.query_session_state()
    valid = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "rename_track",
        "track_index": 1,
        "track_name": "Bass",
        "value": "Low Bass",
    }
    assert validate_llm_plan(valid, snapshot)["ok"] is True
    duplicate = {**valid, "value": "Kick"}
    assert validate_llm_plan(duplicate, snapshot)["ok"] is False


def test_llm_send_plan_requires_exact_return_identity_and_normalized_absolute_value() -> None:
    fake = FakeLive()
    snapshot = fake.query_session_state()
    snapshot["return_tracks"] = fake.get_return_tracks()
    valid = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_send",
        "track_index": 1,
        "track_name": "Bass",
        "return_track_index": 0,
        "return_track_name": "A-Reverb",
        "value": 0.35,
        "relative": False,
        "unit": "normalized",
    }

    assert validate_llm_plan(valid, snapshot)["ok"] is True
    assert validate_llm_plan({**valid, "return_track_index": 1}, snapshot)["ok"] is False
    assert validate_llm_plan({**valid, "return_track_name": "B-Delay"}, snapshot)["ok"] is False
    assert validate_llm_plan({**valid, "value": 35.0}, snapshot)["ok"] is False
    assert validate_llm_plan({**valid, "relative": True}, snapshot)["ok"] is False
    assert validate_llm_plan({**valid, "device_name": "Echo"}, snapshot)["ok"] is False


def test_llm_send_plan_routes_to_confirmation_bound_send_proposal() -> None:
    fake = FakeLive()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_send",
        "track_index": 1,
        "track_name": "Bass",
        "return_track_index": 0,
        "return_track_name": "A-Reverb",
        "value": 0.35,
        "relative": False,
        "unit": "normalized",
    }
    service = _service(fake)
    captured: dict[str, object] = {}
    original_propose = service.propose_send_action

    def capture_send(**kwargs):
        captured.update(kwargs)
        return original_propose(**kwargs)

    service.propose_send_action = capture_send

    result = handle_command(
        "set the reverb send on track 2 to 35%",
        session_id="command-llm-send",
        service=service,
        llm_plan=plan,
    )

    assert result["status"] == "confirmation_required"
    assert result["proposal_kind"] == "send"
    assert result["proposal"]["return_track_index"] == 0
    assert result["proposal"]["return_track_name"] == "A-Reverb"
    assert result["proposal"]["after"] == 0.35
    assert captured["return_track_index"] == 0
    assert fake.writes == []


def test_command_lifecycle_reports_snapshot_and_verification_timing() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command("add EQ on track 2", session_id="command-lifecycle", service=service)

    lifecycle = planned["lifecycle"]
    assert lifecycle["stage"] == "proposal_ready"
    assert lifecycle["snapshot_kind"] == "topology"
    assert lifecycle["snapshot_observed_at"] > 0
    assert lifecycle["snapshot_age_ms"] == 0.0
    assert lifecycle["snapshot_elapsed_ms"] >= 0.0

    proposal = planned["proposal"]
    applied = handle_command(
        "add EQ on track 2",
        session_id="command-lifecycle",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )
    assert applied["lifecycle"]["stage"] == "verified"
    assert applied["lifecycle"]["verification"] == "readback_verified"
    assert applied["lifecycle"]["execution_elapsed_ms"] >= 0.0


def test_device_parameter_inspection_is_read_only_and_returns_ranges() -> None:
    fake = FakeLive()
    result = handle_command(
        "show parameters for Compressor on track 3",
        session_id="command-inspect-parameters",
        service=_service(fake),
    )
    assert result["status"] == "inspected"
    assert result["changed"] is False
    assert result["target"] == {
        "track_index": 2,
        "track_name": "Vocal",
        "device_index": 0,
        "device_name": "Compressor",
    }
    assert result["parameters"] == [{
        "index": 0,
        "name": "Threshold",
        "value": 0.55,
        "min": 0.0,
        "max": 1.0,
    }]


def test_percent_device_command_is_converted_to_raw_before_proposal() -> None:
    fake = FakeLive()
    fake.state["tracks"][2]["devices"] = [{"index": 0, "name": "Auto Filter"}]

    def get_auto_filter_parameters(track_index: int, device_index: int) -> dict:
        assert (track_index, device_index) == (2, 0)
        return {
            "success": True,
            "device_name": "Auto Filter",
            "parameters": [{"index": 7, "name": "Resonance", "value": 0.0, "min": 0.0, "max": 1.0}],
        }

    fake.get_device_parameters = get_auto_filter_parameters
    result = handle_command(
        "set Auto Filter Resonance to 25 percent on track 3",
        session_id="command-percent-mapping",
        service=_service(fake),
    )

    assert result["status"] == "confirmation_required"
    assert result["proposal"]["after"] == 0.25
    assert result["proposal"]["unit"] == "%"
    assert fake.writes == []


def test_glue_attack_display_value_is_converted_to_verified_raw_step() -> None:
    fake = FakeLive()
    fake.state["tracks"][2]["devices"] = [{"index": 0, "name": "Glue Compressor"}]

    def get_glue_parameters(track_index: int, device_index: int) -> dict:
        assert (track_index, device_index) == (2, 0)
        return {
            "success": True,
            "device_name": "Glue Compressor",
            "parameters": [{"index": 4, "name": "Attack", "value": 3.0, "min": 0.0, "max": 6.0}],
        }

    fake.get_device_parameters = get_glue_parameters
    result = handle_command(
        "set Glue Compressor Attack to 3 ms on track 3",
        session_id="command-glue-attack-display",
        service=_service(fake),
    )

    assert result["status"] == "confirmation_required"
    assert result["proposal"]["unit"] == "ms"
    assert result["proposal"]["after"] == 4.0
    assert fake.writes == []


def test_eq_insertion_is_proposed_without_a_write_then_verified_on_confirm() -> None:
    fake = FakeLive()
    result = handle_command("add EQ on track 2", session_id="command-insert", service=_service(fake))
    assert result["status"] == "confirmation_required"
    assert result["changed"] is False
    assert fake.writes == []


    proposal = result["proposal"]
    assert proposal["track_index"] == 1
    assert proposal["track_name"] == "Bass"
    assert proposal["device_name"] == "EQ Eight"
    assert proposal["insertion_index"] == 0
    assert proposal["before_devices"] == []
    assert proposal["after_devices"] == [{"position": 0, "index": 0, "name": "EQ Eight"}]

    applied = handle_command(
        "add EQ on track 2",
        session_id="command-insert",
        service=_service(fake),
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.writes == [("insert_device", 1, 0, "EQ Eight")]

    replay = handle_command(
        "add EQ on track 2",
        session_id="command-insert",
        service=_service(fake),
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )
    assert replay["status"] == "failed"
    assert len(fake.writes) == 1

    undo = _service(fake).propose_undo(applied["receipt"], session_id="command-insert-undo")
    assert undo["ok"] is True
    undo_proposal = undo["proposal"]
    undone = _service(fake).execute_device_removal(
        undo_proposal,
        confirm_token=undo_proposal["confirmation_token"],
        session_id="command-insert-undo",
        idempotency_key=undo_proposal["action_id"],
    )
    assert undone["ok"] is True
    assert undone["receipt"]["verified"] is True
    assert fake.state["tracks"][1]["devices"] == []


def test_llm_device_setup_plan_is_validated_without_inventing_new_indices() -> None:
    fake = DeviceSetupLive()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "insert_device_with_parameter",
        "track_index": 1,
        "track_name": "Hi Hat",
        "device_name": "Hybrid Reverb",
        "parameter_name": "Dry/Wet",
        "value": 25.0,
        "relative": False,
        "unit": "%",
        "device_index": None,
        "parameter_index": None,
        "insertion_index": None,
        "frequency_hz": None,
        "eq_band": None,
        "locator_name": None,
        "new_track_name": None,
        "clarification": None,
        "steps": None,
    }

    checked = validate_llm_plan(plan, fake.query_session_state())
    assert checked["ok"] is True
    result = handle_command(
        "add reverb to hi hat at 25% dry wet",
        session_id="command-llm-device-setup",
        service=_service(fake),
        llm_plan=plan,
    )
    assert result["status"] == "confirmation_required"
    assert result["proposal_kind"] == "device_setup"
    assert fake.writes == []


def test_candidate_device_insertion_is_allowlisted_and_confirmation_bound() -> None:
    fake = FakeLive()
    result = handle_command("add Glue Compressor on track 2", session_id="command-glue-insert", service=_service(fake))
    assert result["status"] == "confirmation_required"
    assert result["changed"] is False
    assert result["proposal"]["device_name"] == "Glue Compressor"
    assert result["proposal"]["insertion_index"] == 0
    assert fake.writes == []


def test_insertion_reconciles_a_mutation_when_the_osc_ack_is_missing() -> None:
    fake = UnacknowledgedInsertionLive()
    planned = handle_command("add Glue Compressor on track 2", session_id="command-unack-insert", service=_service(fake))
    proposal = planned["proposal"]
    applied = handle_command(
        "add Glue Compressor on track 2",
        session_id="command-unack-insert",
        service=_service(fake),
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["write_acknowledgement"] == "unacknowledged_write_reconciled"
    assert fake.writes == [("insert_device", 1, 0, "Glue Compressor")]


def test_insertion_auto_reverts_when_browser_search_resolves_the_wrong_device() -> None:
    """Real-Live qualification (2026-09-05): AbletonOSC's browser-search
    insertion does not require an exact name match and can silently insert a
    different device than requested. execute_device_insertion() must never
    claim success for this, and must not leave the wrong device behind."""
    fake = MismatchedNameInsertionLive()
    planned = handle_command("add EQ on track 2", session_id="command-mismatch-insert", service=_service(fake))
    proposal = planned["proposal"]
    applied = handle_command(
        "add EQ on track 2",
        session_id="command-mismatch-insert",
        service=_service(fake),
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )
    assert applied["status"] == "failed"
    receipt = applied["receipt"]
    assert receipt["verified"] is False
    assert receipt["auto_revert"] == {
        "attempted": True,
        "reverted": True,
        "wrong_device_name": "Convolution Reverb",
        "after_devices": [],
    }
    assert "Convolution Reverb" in applied["answer"]
    assert "EQ Eight" in applied["answer"]
    # The track must be genuinely back to empty, not just reported as such.
    assert fake.state["tracks"][1]["devices"] == []
    assert fake.writes == [
        ("insert_device", 1, 0, "Convolution Reverb"),
        ("remove_device", 1, 0, "Convolution Reverb"),
    ]


def test_insertion_reports_honestly_when_auto_revert_itself_fails() -> None:
    fake = UnremovableMismatchedNameInsertionLive()
    planned = handle_command("add EQ on track 2", session_id="command-mismatch-insert-2", service=_service(fake))
    proposal = planned["proposal"]
    applied = handle_command(
        "add EQ on track 2",
        session_id="command-mismatch-insert-2",
        service=_service(fake),
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )
    assert applied["status"] == "failed"
    receipt = applied["receipt"]
    assert receipt["verified"] is False
    assert receipt["auto_revert"]["attempted"] is True
    assert receipt["auto_revert"]["reverted"] is False
    assert "remove it manually" in applied["answer"]
    # Honest: the wrong device really is still there; never silently hidden.
    assert fake.state["tracks"][1]["devices"] == [{"index": 0, "name": "Convolution Reverb"}]


def test_device_parameter_reconciles_a_mutation_when_the_osc_ack_is_missing() -> None:
    fake = FakeLive()
    original_set = fake.set_device_parameter

    def write_then_drop_ack(track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        original_set(track_index, device_index, parameter_index, value)
        return False

    fake.set_device_parameter = write_then_drop_ack
    planned = handle_command(
        "lower the Vocal Compressor threshold by 2 dB",
        session_id="command-unack-device",
        service=_service(fake),
    )
    proposal = planned["proposal"]
    applied = handle_command(
        "lower the Vocal Compressor threshold by 2 dB",
        session_id="command-unack-device",
        service=_service(fake),
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["id"],
    )

    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["write_acknowledgement"] == "unacknowledged_write_reconciled"
    assert fake.threshold == 0.5
    assert fake.writes == [("threshold", 2, 0, 0, 0.5)]


def test_eq_insertion_refuses_duplicate_and_never_writes() -> None:
    fake = FakeLive()
    result = handle_command("add EQ on track 4", session_id="command-insert-duplicate", service=_service(fake))
    assert result["status"] == "clarification_required"
    assert "already contains EQ Eight" in result["answer"]
    assert fake.writes == []


def test_eq_parameter_change_refuses_multiple_eq_devices_and_never_writes() -> None:
    fake = FakeLive()
    fake.state["tracks"][3]["devices"].append({"index": 1, "name": "EQ Eight"})

    result = handle_command(
        "set EQ Eight 1 Gain A to -3 dB on track 4",
        session_id="command-eq-duplicate-device",
        service=_service(fake),
    )

    assert result["status"] == "clarification_required"
    assert "multiple EQ Eight" in result["answer"]
    assert result["changed"] is False
    assert fake.writes == []


def test_explicit_eq_device_selection_targets_the_requested_chain_position() -> None:
    fake = FakeLive()
    fake.state["tracks"][3]["devices"].append({"index": 1, "name": "EQ Eight"})

    result = handle_command(
        "set EQ Eight device 2 1 Gain A to -3 dB on track 4",
        session_id="command-eq-explicit-device",
        service=_service(fake),
    )

    assert result["status"] == "confirmation_required"
    assert result["changed"] is False
    assert result["proposal"]["device_index"] == 1
    assert result["proposal"]["device_name"] == "EQ Eight"
    assert "set 1 Gain A on 'Synth' -> EQ Eight (device 2)" in result["answer"]
    assert fake.writes == []


def test_eq_insertion_rejects_changed_device_order_before_writing() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command("add EQ on track 2", session_id="command-insert-stale", service=service)
    proposal = planned["proposal"]
    fake.state["tracks"][1]["devices"].append({"index": 0, "name": "Compressor"})

    result = handle_command(
        "add EQ on track 2",
        session_id="command-insert-stale",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )
    assert result["status"] == "failed"
    assert "device order changed" in result["answer"]
    assert fake.writes == []


def test_read_only_track_inventory_question_lists_current_devices_without_writing() -> None:
    fake = FakeLive()
    result = handle_command("What is on track 4?", session_id="command-inspect", service=_service(fake))

    assert result["status"] == "inspected"
    assert result["changed"] is False
    assert result["target"] == {"index": 3, "name": "Synth"}
    assert [item["name"] for item in result["devices"]] == ["EQ Eight"]
    assert "EQ Eight" in result["answer"]
    assert fake.writes == []


def test_eq_band_gain_request_proposes_then_applies_one_existing_band() -> None:
    fake = FakeLive()
    service = _service(fake)
    result = handle_command("reduce amplitude by 3 dB at 250 Hz on track 4", session_id="command-eq", service=service)
    assert result["status"] == "confirmation_required"
    assert result["proposal"]["track_name"] == "Synth"
    assert result["proposal"]["parameter"] == "1 Gain A"
    assert result["proposal"]["eq_band"] == "1A"
    assert result["proposal"]["frequency_hz"] == 250.0
    assert result["proposal"]["after"] == -3.0
    assert result["proposal"]["parameter_index"] == 12
    assert result["proposal"]["before_display"] == "0 dB"
    assert fake.writes == []

    applied = handle_command(
        "reduce amplitude by 3 dB at 250 Hz on track 4",
        session_id="command-eq",
        service=service,
        proposal=result["proposal"],
        confirm_token=result["proposal"]["confirmation_token"],
        idempotency_key=result["proposal"]["id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["readback_display"] == "-3 dB"
    assert fake.eq_gain == -3.0
    assert len(fake.writes) == 1


def test_eq_band_gain_confirmation_is_idempotent_and_undoable() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command(
        "reduce amplitude by 3 dB at 250 Hz on track 4",
        session_id="command-eq-lifecycle",
        service=service,
    )
    proposal = planned["proposal"]
    applied = handle_command(
        "reduce amplitude by 3 dB at 250 Hz on track 4",
        session_id="command-eq-lifecycle",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["readback"] == -3.0
    assert fake.writes == [("eq_gain", 3, 0, 12, -3.0)]

    replay = handle_command(
        "reduce amplitude by 3 dB at 250 Hz on track 4",
        session_id="command-eq-lifecycle",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["id"],
    )
    assert replay["status"] == "failed"
    assert "already executed" in replay["answer"]
    assert len(fake.writes) == 1

    undo = service.propose_undo(applied["receipt"], session_id="command-eq-lifecycle-undo")
    assert undo["ok"] is True
    undo_proposal = undo["proposal"]
    undone = service.execute_device_action(
        undo_proposal,
        confirm_token=undo_proposal["confirmation_token"],
        session_id="command-eq-lifecycle-undo",
        idempotency_key=undo_proposal["id"],
    )
    assert undone["ok"] is True
    assert undone["receipt"]["verified"] is True
    assert fake.eq_gain == 0.0
    assert fake.writes[-1] == ("eq_gain", 3, 0, 12, 0.0)


def test_eq_band_boost_applies_positive_gain_and_undoes() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command(
        "boost amplitude by 3 dB at 250 Hz on track 4",
        session_id="command-eq-boost",
        service=service,
    )
    assert planned["status"] == "confirmation_required"
    proposal = planned["proposal"]
    assert proposal["eq_band"] == "1A"
    assert proposal["frequency_hz"] == 250.0
    assert proposal["after"] == 3.0
    assert fake.writes == []

    applied = handle_command(
        "boost amplitude by 3 dB at 250 Hz on track 4",
        session_id="command-eq-boost",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.eq_gain == 3.0

    undo = service.propose_undo(applied["receipt"], session_id="command-eq-boost-undo")
    assert undo["ok"] is True
    undo_proposal = undo["proposal"]
    undone = service.execute_device_action(
        undo_proposal,
        confirm_token=undo_proposal["confirmation_token"],
        session_id="command-eq-boost-undo",
        idempotency_key=undo_proposal["id"],
    )
    assert undone["ok"] is True
    assert undone["receipt"]["verified"] is True
    assert fake.eq_gain == 0.0


def test_compressor_threshold_display_db_converts_to_measured_raw() -> None:
    """Absolute -18 dB must resolve to raw 0.4 (measured real-Live table)."""
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command(
        "Set Compressor Threshold to -18 dB on track 3",
        session_id="command-threshold-display",
        service=service,
    )
    assert planned["status"] == "confirmation_required"
    proposal = planned["proposal"]
    assert proposal["after"] == 0.4
    assert fake.writes == []
    applied = handle_command(
        "Set Compressor Threshold to -18 dB on track 3",
        session_id="command-threshold-display",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["readback_display"] == "-18 dB"
    assert fake.threshold == 0.4
    assert fake.writes == [("threshold", 2, 0, 0, 0.4)]

    undo = service.propose_undo(applied["receipt"], session_id="command-threshold-display-undo")
    assert undo["ok"] is True
    undo_proposal = undo["proposal"]
    undone = service.execute_device_action(
        undo_proposal,
        confirm_token=undo_proposal["confirmation_token"],
        session_id="command-threshold-display-undo",
        idempotency_key=undo_proposal["id"],
    )
    assert undone["ok"] is True
    assert undone["receipt"]["verified"] is True
    assert fake.threshold == 0.55


def test_eq_band_tuning_and_gain_is_one_confirmed_transaction_and_undoable() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command(
        "retune EQ Eight band 1A to 300 Hz and reduce gain by 3 dB on track 4",
        session_id="command-eq-compound",
        service=service,
    )
    assert planned["status"] == "confirmation_required"
    assert "250 Hz / 0 dB to 300 Hz / -3 dB" in planned["answer"]
    proposal = planned["proposal"]
    assert proposal["frequency_parameter_index"] == 11
    assert proposal["gain_parameter_index"] == 12
    assert fake.writes == []

    applied = handle_command(
        "retune EQ Eight band 1A to 300 Hz and reduce gain by 3 dB on track 4",
        session_id="command-eq-compound",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.frequency_value == 300.0
    assert fake.eq_gain == -3.0
    assert fake.writes == [("eq_frequency", 3, 0, 11, 300.0), ("eq_gain", 3, 0, 12, -3.0)]

    replay = handle_command(
        "retune EQ Eight band 1A to 300 Hz and reduce gain by 3 dB on track 4",
        session_id="command-eq-compound",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )
    assert replay["status"] == "failed"
    assert "already executed" in replay["answer"]

    undo = service.propose_undo(applied["receipt"], session_id="command-eq-compound-undo")
    assert undo["ok"] is True
    undo_proposal = undo["proposal"]
    undone = service.execute_eq_band_tuning_gain(
        undo_proposal,
        confirm_token=undo_proposal["confirmation_token"],
        session_id="command-eq-compound-undo",
        idempotency_key=undo_proposal["action_id"],
    )
    assert undone["ok"] is True
    assert fake.frequency_value == 250.0
    assert fake.eq_gain == 0.0
    assert fake.writes[-2:] == [("eq_frequency", 3, 0, 11, 250.0), ("eq_gain", 3, 0, 12, 0.0)]


def test_absolute_eq_band_tuning_and_gain_uses_the_same_guarded_path() -> None:
    fake = FakeLive()
    service = _service(fake)
    command = "set EQ Eight band 1A frequency to 300 Hz and gain to -3 dB on track 4"
    planned = handle_command(command, session_id="command-eq-absolute-compound", service=service)

    assert planned["status"] == "confirmation_required"
    assert "250 Hz / 0 dB to 300 Hz / -3 dB" in planned["answer"]
    assert fake.writes == []

    proposal = planned["proposal"]
    applied = handle_command(
        command,
        session_id="command-eq-absolute-compound",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["action_id"],
    )

    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.frequency_value == 300.0
    assert fake.eq_gain == -3.0


def test_eq_band_gain_resolves_live_normalized_frequency() -> None:
    fake = FakeLive()
    fake.frequency_value = 0.3892475963
    fake.frequency_display = ""
    result = handle_command("reduce amplitude by 3 dB at 200 Hz on track 4", session_id="command-eq-normalized", service=_service(fake))
    assert result["status"] == "confirmation_required"
    assert result["proposal"]["eq_band"] == "1A"


def test_eq_band_gain_refuses_to_guess_when_frequency_is_not_configured() -> None:
    fake = FakeLive()
    result = handle_command("reduce amplitude by 3 dB at 400 Hz on track 4", session_id="command-eq-mismatch", service=_service(fake))
    assert result["status"] == "clarification_required"
    assert "not retune" in result["answer"]
    assert {item["eq_band"] for item in result["clarification_options"]} == {"1A"}
    assert all("frequency_hz" in item for item in result["clarification_options"])
    assert fake.writes == []


def test_eq_band_gain_accepts_explicit_band_when_frequency_is_ambiguous() -> None:
    fake = FakeLive()
    result = handle_command("reduce amplitude by 3 dB at 400 Hz on track 4 band 1A", session_id="command-eq-band", service=_service(fake))
    assert result["status"] == "clarification_required"

    fake.frequency_value = 200.0
    fake.frequency_display = "200 Hz"
    result = handle_command("reduce amplitude by 3 dB at 200 Hz on track 4 band 1A", session_id="command-eq-band", service=_service(fake))
    assert result["status"] == "confirmation_required"
    assert result["proposal"]["eq_band"] == "1A"


def test_eq_band_only_wording_requires_exact_side_before_proposing() -> None:
    fake = FakeLive()
    result = handle_command("reduce eq band 1 by 3 dB on track 4", session_id="command-eq-band-only", service=_service(fake))

    assert result["status"] == "clarification_required"
    assert "1A or 1B" in result["answer"]
    assert fake.writes == []


def test_eq_band_only_wording_can_propose_an_exact_existing_side() -> None:
    fake = FakeLive()
    result = handle_command("reduce eq band 1A by 3 dB on track 4", session_id="command-eq-band-only-exact", service=_service(fake))

    assert result["status"] == "confirmation_required"
    assert result["proposal"]["eq_band"] == "1A"
    assert result["proposal"]["after"] == -3.0
    assert fake.writes == []


def test_eq_band_absolute_gain_wording_resolves_exact_parameter() -> None:
    fake = FakeLive()
    result = handle_command(
        "set EQ Eight 1 Gain A to -3 dB on track 4",
        session_id="command-eq-absolute-band",
        service=_service(fake),
    )

    assert result["status"] == "confirmation_required"
    assert result["proposal"]["parameter"] == "1 Gain A"
    assert result["proposal"]["eq_band"] == "1A"
    assert result["proposal"]["after"] == -3.0
    assert fake.writes == []


def test_untyped_eq_setting_asks_for_parameter_and_band_side() -> None:
    fake = FakeLive()
    result = handle_command(
        "change band 2 to the EQ Eight setting of .99 track 4",
        session_id="command-eq-untyped-setting",
        service=_service(fake),
    )

    assert result["status"] == "clarification_required"
    assert "specific parameter" in result["answer"]
    assert "2A or 2B" in result["answer"]
    assert fake.writes == []


def test_existing_device_parameter_uses_current_value_for_relative_change() -> None:
    fake = FakeLive()
    service = _service(fake)
    planned = handle_command("lower the Vocal Compressor threshold by 2 dB", session_id="command-device", service=service)
    assert planned["status"] == "confirmation_required"
    assert planned["proposal"]["after"] == 0.5
    assert fake.writes == []

    applied = handle_command(
        "lower the Vocal Compressor threshold by 2 dB",
        session_id="command-device",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["id"],
    )
    assert applied["status"] == "applied"
    assert fake.threshold == 0.5


def test_llm_plan_must_bind_to_the_current_snapshot() -> None:
    fake = FakeLive()
    valid = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_mute",
        "track_index": 1,
        "track_name": "Bass",
        "value": True,
    }
    assert validate_llm_plan(valid, fake.state)["ok"] is True
    forged = {**valid, "track_index": 99, "track_name": "Ghost"}
    assert validate_llm_plan(forged, fake.state)["ok"] is False


def test_llm_plan_requires_exact_track_identity_and_boolean_track_values() -> None:
    fake = FakeLive()
    missing_name = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_mute",
        "track_index": 1,
        "value": True,
    }
    assert validate_llm_plan(missing_name, fake.state)["ok"] is False

    numeric_mute = {
        **missing_name,
        "track_name": "Bass",
        "value": 0,
    }
    checked = validate_llm_plan(numeric_mute, fake.state)
    assert checked["ok"] is False
    assert "boolean" in checked["error"]


def test_llm_track_control_requires_normalized_numeric_values() -> None:
    fake = FakeLive()
    valid = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_volume",
        "track_index": 0,
        "track_name": "Kick",
        "value": 0.5,
        "relative": False,
        "unit": "normalized",
    }
    assert validate_llm_plan(valid, fake.state)["ok"] is True

    db_value = {**valid, "value": -6.0, "unit": "dB"}
    checked = validate_llm_plan(db_value, fake.state)
    assert checked["ok"] is False
    assert "normalized" in checked["error"]

    out_of_range_pan = {
        **valid,
        "action": "set_pan",
        "value": 1.1,
        "unit": "normalized",
    }
    checked = validate_llm_plan(out_of_range_pan, fake.state)
    assert checked["ok"] is False
    assert "range" in checked["error"]


def test_llm_named_locator_plan_is_bounded_without_a_track_target() -> None:
    fake = FakeLive()
    valid = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "add_locator",
        "locator_name": "Verse",
        "unit": "beats",
    }
    assert validate_llm_plan(valid, fake.state)["ok"] is True

    hidden_track = {**valid, "track_index": 0, "track_name": "Kick"}
    checked = validate_llm_plan(hidden_track, fake.state)
    assert checked["ok"] is False
    assert "unrelated" in checked["error"]

    unnamed = {**valid, "locator_name": ""}
    checked = validate_llm_plan(unnamed, fake.state)
    assert checked["ok"] is False
    assert "locator_name" in checked["error"]


def test_llm_focus_plan_requires_exact_track_identity_and_no_unrelated_fields() -> None:
    fake = FakeLive()
    valid = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "focus_track",
        "track_index": 1,
        "track_name": "Bass",
    }
    assert validate_llm_plan(valid, fake.state)["ok"] is True

    hidden_write = {**valid, "value": True, "unit": "boolean"}
    checked = validate_llm_plan(hidden_write, fake.state)
    assert checked["ok"] is False
    assert "unrelated" in checked["error"]


def test_llm_device_focus_plan_requires_exact_device_identity() -> None:
    fake = FakeLive()
    valid = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "focus_device",
        "track_index": 3,
        "track_name": "Synth",
        "device_index": 0,
        "device_name": "EQ Eight",
    }
    assert validate_llm_plan(valid, fake.state)["ok"] is True

    wrong_name = {**valid, "device_name": "Compressor"}
    checked = validate_llm_plan(wrong_name, fake.state)
    assert checked["ok"] is False
    assert "exact match" in checked["error"]


def test_llm_planner_receives_target_device_capabilities_and_exact_profile_is_enforced() -> None:
    fake = FakeLive()
    enriched = live_command_module._llm_planner_snapshot(
        _service(fake),
        fake.state,
        {"track": {"index": 2, "name": "Vocal"}},
    )

    entries = enriched["planner_capabilities"]["entries"]
    assert entries[0]["device_name"] == "Compressor"
    assert entries[0]["parameters"][0]["name"] == "Threshold"
    valid = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_device_parameter",
        "track_index": 2,
        "track_name": "Vocal",
        "device_index": 0,
        "device_name": "Compressor",
        "parameter_index": 0,
        "parameter_name": "Threshold",
        "value": -6.0,
        "relative": False,
        "unit": "dB",
    }
    assert validate_llm_plan(valid, enriched)["ok"] is True
    invalid = {**valid, "parameter_index": 7}
    checked = validate_llm_plan(invalid, enriched)
    assert checked["ok"] is False
    assert "exact match" in checked["error"]

    out_of_range = {**valid, "value": -80.0}
    checked = validate_llm_plan(out_of_range, enriched)
    assert checked["ok"] is False
    assert "outside the safe range" in checked["error"]

    unsupported_unit = {**valid, "value": 10.0, "unit": "ms"}
    checked = validate_llm_plan(unsupported_unit, enriched)
    assert checked["ok"] is False
    assert "evidence-backed" in checked["error"]


def test_llm_plan_rejects_hidden_nested_actions_and_unknown_fields() -> None:
    fake = FakeLive()
    hidden = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_mute",
        "track_index": 1,
        "track_name": "Bass",
        "value": True,
        "steps": [{"action": "set_device_parameter", "value": -6.0}],
    }
    checked = validate_llm_plan(hidden, fake.state)
    assert checked["ok"] is False
    assert "nested steps" in checked["error"]

    unknown = {key: value for key, value in hidden.items() if key != "steps"}
    unknown["model_thought"] = "apply another action"
    checked = validate_llm_plan(unknown, fake.state)
    assert checked["ok"] is False
    assert "unsupported fields" in checked["error"]


def test_llm_eq_band_plan_uses_the_same_confirmation_boundary() -> None:
    fake = FakeLive()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_eq_band_gain",
        "track_index": 3,
        "track_name": "Synth",
        "device_index": 0,
        "device_name": "EQ Eight",
        "frequency_hz": 250.0,
        "eq_band": "1A",
        "value": -3.0,
        "relative": True,
        "unit": "dB",
    }
    assert validate_llm_plan(plan, fake.state)["ok"] is True
    result = handle_command("", session_id="command-llm-eq", service=_service(fake), llm_plan=plan)
    assert result["status"] == "confirmation_required"
    assert result["proposal"]["eq_band"] == "1A"
    assert fake.writes == []


def test_llm_compound_eq_plan_uses_the_same_confirmation_boundary() -> None:
    fake = FakeLive()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_eq_band_tuning_gain",
        "track_index": 3,
        "track_name": "Synth",
        "device_index": 0,
        "device_name": "EQ Eight",
        "frequency_hz": 300.0,
        "eq_band": "1A",
        "value": -3.0,
        "relative": False,
        "unit": "dB",
    }

    assert validate_llm_plan(plan, fake.state)["ok"] is True
    result = handle_command("", session_id="command-llm-compound-eq", service=_service(fake), llm_plan=plan)
    assert result["status"] == "confirmation_required"
    assert result["changed"] is False
    assert result["proposal"]["eq_band"] == "1A"
    assert result["proposal"]["frequency_after_hz"] == 300.0
    assert result["proposal"]["gain_after_value"] == -3.0
    assert fake.writes == []


def test_llm_eq_plan_can_target_an_explicit_duplicate_device() -> None:
    fake = FakeLive()
    fake.state["tracks"][3]["devices"].append({"index": 1, "name": "EQ Eight"})
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_eq_band_gain",
        "track_index": 3,
        "track_name": "Synth",
        "device_index": 1,
        "device_name": "EQ Eight",
        "frequency_hz": 250.0,
        "eq_band": "1A",
        "value": -3.0,
        "relative": False,
        "unit": "dB",
    }

    assert validate_llm_plan(plan, fake.state)["ok"] is True
    result = handle_command(
        "",
        session_id="command-llm-explicit-eq-device",
        service=_service(fake),
        llm_plan=plan,
    )

    assert result["status"] == "confirmation_required"
    assert result["changed"] is False
    assert result["proposal"]["device_index"] == 1
    assert fake.writes == []


def test_recipe_is_limited_and_proposal_only_before_confirmation() -> None:
    fake = FakeLive()
    recipes = LiveRecipeService(_service(fake))

    result = recipes.propose_recipe(
        [
            {"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": 0.4},
            {"action": "set_device_parameter", "track_index": 3, "track_name": "Synth", "device_index": 0, "device_name": "EQ Eight", "parameter_index": 12, "parameter": "1 Gain A", "value": -3.0, "unit": "dB"},
        ],
        reason="Bounded recipe test",
        session_id="recipe-proposal",
    )

    assert result["ok"] is True
    assert result["proposal"]["schema"] == RECIPE_SCHEMA
    assert result["proposal"]["step_count"] == 2
    assert result["proposal"]["requires_confirmation"] is True
    assert result["proposal"]["confirmation_token"]
    assert all("confirmation_token" not in step for step in result["proposal"]["steps"])
    assert fake.writes == []

    too_many = recipes.propose_recipe([{"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": 0.4}] * 4, reason="too many", session_id="recipe-limit")
    assert too_many["ok"] is False
    assert "between 1 and 3" in too_many["error"]
    assert fake.writes == []


def test_natural_recipe_resolves_existing_device_parameter_without_writing_before_confirmation() -> None:
    fake = FakeLive()
    command = "mute track 1 then lower the Vocal Compressor threshold by 2 dB"
    planned = handle_command(command, session_id="natural-device-recipe", service=_service(fake))

    assert planned["status"] == "confirmation_required"
    assert planned["proposal_kind"] == "recipe"
    assert planned["proposal"]["step_count"] == 2
    assert planned["proposal"]["steps"][0]["action"] == "set_mute"
    assert planned["proposal"]["steps"][1]["action"] == "set_device_parameter"
    assert planned["proposal"]["steps"][1]["parameter"] == "Threshold"
    assert planned["proposal"]["steps"][1]["before"] == 0.55
    assert planned["proposal"]["steps"][1]["after"] == 0.5
    assert fake.writes == []

    applied = handle_command(
        command,
        session_id="natural-device-recipe",
        service=_service(fake),
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.state["tracks"][0]["muted"] is True
    assert fake.threshold == 0.5
    assert fake.writes == [("mute", 0, True), ("threshold", 2, 0, 0, 0.5)]


def test_natural_send_recipe_applies_and_undoes_with_exact_return_identity() -> None:
    fake = FakeLive()
    command = "set the reverb send on track 2 to 35% then mute track 2"
    planned = handle_command(command, session_id="natural-send-recipe", service=_service(fake))

    assert planned["status"] == "confirmation_required"
    assert planned["proposal_kind"] == "recipe"
    assert planned["proposal"]["step_count"] == 2
    assert planned["proposal"]["steps"][0]["action"] == "set_send"
    assert planned["proposal"]["steps"][0]["return_track_index"] == 0
    assert planned["proposal"]["steps"][0]["return_track_name"] == "A-Reverb"
    assert fake.writes == []

    applied = handle_command(
        command,
        session_id="natural-send-recipe",
        service=_service(fake),
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["receipt"]["verified"] is True
    assert fake.sends[(1, 0)] == 0.35
    assert fake.state["tracks"][1]["muted"] is True

    undo = LiveRecipeService(_service(fake)).propose_undo(applied["receipt"], session_id="natural-send-recipe-undo")
    assert undo["ok"] is True
    undone = handle_command(
        command,
        session_id="natural-send-recipe-undo",
        service=_service(fake),
        proposal=undo["proposal"],
        confirm_token=undo["proposal"]["confirmation_token"],
        idempotency_key=undo["proposal"]["action_id"],
    )
    assert undone["status"] == "applied"
    assert fake.sends[(1, 0)] == 0.2
    assert fake.state["tracks"][1]["muted"] is False


def test_llm_recipe_accepts_a_typed_send_step_without_writing_before_confirmation() -> None:
    fake = FakeLive()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "recipe",
        "steps": [
            {
                "action": "set_send",
                "track_index": 1,
                "track_name": "Bass",
                "return_track_index": 0,
                "return_track_name": "A-Reverb",
                "value": 0.35,
                "relative": False,
                "unit": "normalized",
            },
            {"action": "set_mute", "track_index": 1, "track_name": "Bass", "value": True, "unit": "boolean"},
        ],
    }

    result = handle_command("", session_id="llm-send-recipe", service=_service(fake), llm_plan=plan)

    assert result["status"] == "confirmation_required"
    assert result["proposal_kind"] == "recipe"
    assert result["proposal"]["steps"][0]["return_track_name"] == "A-Reverb"
    assert fake.writes == []


def test_deterministic_only_gateway_never_calls_configured_llm(monkeypatch) -> None:
    fake = FakeLive()

    def unexpected_llm(*args, **kwargs):
        raise AssertionError("the deterministic-only command path called the LLM")

    monkeypatch.setattr(live_command_module, "_generate_llm_plan", unexpected_llm)
    monkeypatch.setenv("KENN_LIVE_LLM_ENABLED", "1")
    planned = handle_command(
        "mute track 2",
        session_id="deterministic-only",
        service=_service(fake),
        allow_llm=False,
    )

    assert planned["status"] == "confirmation_required"
    assert planned["llm"] == {
        "status": "disabled",
        "mode": "deterministic",
        "reason": "caller_requested_deterministic_only",
    }
    assert fake.writes == []

def test_recipe_executes_each_step_and_returns_verified_receipt() -> None:
    fake = FakeLive()
    service = _service(fake)
    recipes = LiveRecipeService(service)
    proposed = recipes.propose_recipe(
        [
            {"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": 0.4},
            {"action": "set_device_parameter", "track_index": 3, "track_name": "Synth", "device_index": 0, "device_name": "EQ Eight", "parameter_index": 12, "parameter": "1 Gain A", "value": -3.0, "unit": "dB"},
        ],
        reason="Bounded recipe apply test",
        session_id="recipe-apply",
    )
    recipe = proposed["proposal"]

    result = recipes.execute_recipe(
        recipe,
        confirm_token=recipe["confirmation_token"],
        session_id="recipe-apply",
        idempotency_key=recipe["action_id"],
    )

    assert result["ok"] is True
    assert result["receipt"]["schema"] == RECIPE_RECEIPT_SCHEMA
    assert result["receipt"]["verified"] is True
    assert result["receipt"]["step_count"] == 2
    assert fake.state["tracks"][0]["volume"] == 0.4
    assert fake.eq_gain == -3.0

    undo_proposed = recipes.propose_undo(result["receipt"], session_id="recipe-undo")
    assert undo_proposed["ok"] is True
    assert undo_proposed["proposal"]["step_count"] == 2
    undone = recipes.execute_recipe(
        undo_proposed["proposal"],
        confirm_token=undo_proposed["proposal"]["confirmation_token"],
        session_id="recipe-undo",
        idempotency_key=undo_proposed["proposal"]["action_id"],
    )
    assert undone["ok"] is True
    assert fake.state["tracks"][0]["volume"] == 0.5
    assert fake.eq_gain == 0.0


def test_recipe_reconciles_an_applied_step_when_acknowledgement_is_lost() -> None:
    fake = FakeLive()
    recipes = LiveRecipeService(_service(fake))
    proposed = recipes.propose_recipe(
        [{"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": 0.4}],
        reason="Recipe acknowledgement reconciliation test",
        session_id="recipe-unacknowledged",
    )
    recipe = proposed["proposal"]
    original = fake.set_track_volume

    def write_then_drop_ack(index: int, value: float) -> bool:
        original(index, value)
        raise TimeoutError("recipe acknowledgement lost")

    fake.set_track_volume = write_then_drop_ack
    result = recipes.execute_recipe(
        recipe,
        confirm_token=recipe["confirmation_token"],
        session_id="recipe-unacknowledged",
        idempotency_key=recipe["action_id"],
    )

    assert result["ok"] is True
    step = result["receipt"]["step_receipts"][0]
    assert step["verified"] is True
    assert step["write_acknowledgement"] == "unacknowledged_write_reconciled"
    assert "acknowledgement lost" in step["write_error"]
    assert fake.state["tracks"][0]["volume"] == 0.4


def test_shared_service_dispatches_recipe_receipt_to_fresh_recipe_undo() -> None:
    fake = FakeLive()
    result = LiveActionService(fake).propose_undo(
        {
            "schema": RECIPE_RECEIPT_SCHEMA,
            "receipt_id": "receipt-recipe-dispatch",
            "action": "recipe",
            "status": "applied",
            "verified": True,
            "step_receipts": [
                {
                    "action": "set_pan",
                    "target": {"track_index": 3, "track_name": "Synth", "parameter": "pan"},
                    "before": 0.0,
                    "requested": 0.1,
                    "readback": 0.1,
                    "verified": True,
                },
                {
                    "action": "set_device_parameter",
                    "target": {"track_index": 3, "track_name": "Synth", "device_index": 0, "device_name": "EQ Eight", "parameter_index": 12, "parameter": "1 Gain A"},
                    "before": 0.0,
                    "requested": -3.0,
                    "readback": -3.0,
                    "verified": True,
                },
            ],
        },
        session_id="recipe-dispatch-undo",
    )

    assert result["ok"] is True
    assert result["proposal"]["schema"] == RECIPE_SCHEMA
    assert result["proposal"]["step_count"] == 2
    assert fake.writes == []


def test_recipe_rolls_back_completed_and_partially_written_steps_on_failure() -> None:
    fake = FakeLive()
    service = _service(fake)
    recipes = LiveRecipeService(service)
    proposed = recipes.propose_recipe(
        [
            {"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": 0.4},
            {"action": "set_device_parameter", "track_index": 3, "track_name": "Synth", "device_index": 0, "device_name": "EQ Eight", "parameter_index": 12, "parameter": "1 Gain A", "value": -3.0, "unit": "dB"},
        ],
        reason="Bounded recipe rollback test",
        session_id="recipe-rollback",
    )
    recipe = proposed["proposal"]
    original_set = fake.set_device_parameter
    original_get = fake.get_device_parameters
    disconnect = {"next_read": False}

    def write_then_disconnect(track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        result = original_set(track_index, device_index, parameter_index, value)
        if value == -3.0:
            disconnect["next_read"] = True
        return result

    def transiently_disconnected_read(track_index: int, device_index: int) -> dict:
        if disconnect["next_read"]:
            disconnect["next_read"] = False
            raise TimeoutError("Live disconnected during recipe readback")
        return original_get(track_index, device_index)

    fake.set_device_parameter = write_then_disconnect
    fake.get_device_parameters = transiently_disconnected_read
    result = recipes.execute_recipe(
        recipe,
        confirm_token=recipe["confirmation_token"],
        session_id="recipe-rollback",
        idempotency_key=recipe["action_id"],
    )

    assert result["ok"] is False
    assert result["status"] == "failed_rolled_back"
    assert result["rolled_back"] is True
    assert result["receipt"]["status"] == "failed_rolled_back"
    assert result["receipt"]["retry_safe"] == "unsafe"
    assert result["receipt"]["step_receipts"][1]["write_acknowledgement"] == "confirmed"
    assert "disconnected during recipe readback" in result["receipt"]["step_receipts"][1]["readback_error"]
    assert fake.state["tracks"][0]["volume"] == 0.5
    assert fake.eq_gain == 0.0
    assert fake.writes == [
        ("volume", 0, 0.4),
        ("eq_gain", 3, 0, 12, -3.0),
        ("eq_gain", 3, 0, 12, 0.0),
        ("volume", 0, 0.5),
    ]


def test_recipe_reports_partial_recovery_when_compensating_rollback_fails() -> None:
    fake = FakeLive()
    recipes = LiveRecipeService(_service(fake))
    proposed = recipes.propose_recipe(
        [
            {"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": 0.4},
            {"action": "set_device_parameter", "track_index": 3, "track_name": "Synth", "device_index": 0, "device_name": "EQ Eight", "parameter_index": 12, "parameter": "1 Gain A", "value": -3.0, "unit": "dB"},
        ],
        reason="Partial recovery visibility test",
        session_id="recipe-partial-recovery",
    )
    recipe = proposed["proposal"]
    original_volume = fake.set_track_volume
    original_set = fake.set_device_parameter
    original_get = fake.get_device_parameters
    disconnect = {"next_read": False}

    def refuse_volume_restore(index: int, value: float) -> bool:
        if value == 0.5:
            fake.writes.append(("volume_restore_refused", index, value))
            return False
        return original_volume(index, value)

    def write_then_disconnect(track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        result = original_set(track_index, device_index, parameter_index, value)
        if value == -3.0:
            disconnect["next_read"] = True
        return result

    def transiently_disconnected_read(track_index: int, device_index: int) -> dict:
        if disconnect["next_read"]:
            disconnect["next_read"] = False
            raise TimeoutError("Live disconnected during recipe readback")
        return original_get(track_index, device_index)

    fake.set_track_volume = refuse_volume_restore
    fake.set_device_parameter = write_then_disconnect
    fake.get_device_parameters = transiently_disconnected_read
    result = recipes.execute_recipe(
        recipe,
        confirm_token=recipe["confirmation_token"],
        session_id="recipe-partial-recovery",
        idempotency_key=recipe["action_id"],
    )

    assert result["ok"] is False
    assert result["status"] == "partial_recovery"
    assert result["rolled_back"] is False
    assert result["rollback"] == [True, False]
    assert result["receipt"]["status"] == "partial_recovery"
    assert result["receipt"]["retry_safe"] == "requires_inspection"
    assert fake.eq_gain == 0.0
    assert fake.state["tracks"][0]["volume"] == 0.4


def test_send_recipe_aborts_without_writes_when_return_identity_is_stale() -> None:
    fake = FakeLive()
    recipes = LiveRecipeService(_service(fake))
    proposed = recipes.propose_recipe(
        [{
            "action": "set_send",
            "track_index": 1,
            "track_name": "Bass",
            "return_track_index": 0,
            "return_track_name": "A-Reverb",
            "value": 0.35,
        }],
        reason="Return identity freshness test",
        session_id="recipe-send-stale-return",
    )
    recipe = proposed["proposal"]
    fake.return_tracks[0]["name"] = "A-New-Reverb"

    result = recipes.execute_recipe(
        recipe,
        confirm_token=recipe["confirmation_token"],
        session_id="recipe-send-stale-return",
        idempotency_key=recipe["action_id"],
    )

    assert result["ok"] is False
    assert result["status"] == "failed_rolled_back"
    assert "return-track name changed" in result["error"]
    assert fake.writes == []


def test_send_recipe_rollback_refuses_a_replaced_source_track() -> None:
    fake = FakeLive()
    recipes = LiveRecipeService(_service(fake))
    proposed = recipes.propose_recipe(
        [
            {
                "action": "set_send",
                "track_index": 1,
                "track_name": "Bass",
                "return_track_index": 0,
                "return_track_name": "A-Reverb",
                "value": 0.35,
            },
            {"action": "set_mute", "track_index": 1, "track_name": "Bass", "value": True},
        ],
        reason="Source identity rollback test",
        session_id="recipe-send-source-rollback",
    )
    recipe = proposed["proposal"]
    original_mute = fake.set_track_mute

    def mutate_source_then_fail(index: int, value: bool) -> bool:
        fake.state["tracks"][index]["name"] = "Replacement Bass"
        original_mute(index, value)
        return False

    fake.set_track_mute = mutate_source_then_fail
    result = recipes.execute_recipe(
        recipe,
        confirm_token=recipe["confirmation_token"],
        session_id="recipe-send-source-rollback",
        idempotency_key=recipe["action_id"],
    )

    assert result["ok"] is False
    assert result["status"] == "partial_recovery"
    # The failed mute step is included in the receipt because it changed the
    # source name before its readback; neither it nor the earlier send may be
    # restored onto the replacement track.
    assert result["rollback"] == [False, False]
    assert fake.sends[(1, 0)] == 0.35
    assert not any(write[0] == "send" and write[3] == 0.2 for write in fake.writes)


def test_command_gateway_uses_recipe_proposal_and_confirmation_boundary() -> None:
    fake = FakeLive()
    service = _service(fake)
    steps = [{"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": 0.4}]

    planned = handle_command(
        "attenuate the kick slightly",
        session_id="command-recipe-gateway",
        service=service,
        recipe_steps=steps,
    )
    assert planned["status"] == "confirmation_required"
    assert planned["proposal_kind"] == "recipe"
    assert "1-step Live recipe" in planned["answer"]
    assert fake.writes == []

    applied = handle_command(
        "",
        session_id="command-recipe-gateway",
        service=service,
        proposal=planned["proposal"],
        confirm_token=planned["proposal"]["confirmation_token"],
        idempotency_key=planned["proposal"]["action_id"],
    )
    assert applied["status"] == "applied"
    assert applied["changed"] is True
    assert applied["receipt"]["verified"] is True
    assert fake.state["tracks"][0]["volume"] == 0.4


def test_natural_language_recipe_creates_one_confirmation_bound_proposal() -> None:
    fake = FakeLive()
    planned = handle_command(
        "mute track 1 then pan track 2 20% right",
        session_id="command-natural-recipe",
        service=_service(fake),
    )
    assert planned["status"] == "confirmation_required"
    assert planned["proposal_kind"] == "recipe"
    assert planned["proposal"]["step_count"] == 2
    assert fake.writes == []


def test_natural_language_recipe_rejects_device_insertion_inside_recipe() -> None:
    fake = FakeLive()
    result = handle_command(
        "mute track 1 then add EQ on track 2",
        session_id="command-natural-recipe-device",
        service=_service(fake),
    )
    assert result["status"] == "clarification_required"
    assert "device insertion" in result["answer"]
    assert fake.writes == []


def test_llm_recipe_plan_is_bounded_and_uses_the_recipe_gateway() -> None:
    fake = FakeLive()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "recipe",
        "steps": [
            {"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": 0.4, "relative": False, "unit": "normalized"},
            {"action": "set_device_parameter", "track_index": 3, "track_name": "Synth", "device_index": 0, "device_name": "EQ Eight", "parameter_index": 12, "parameter_name": "1 Gain A", "value": -3.0, "relative": False, "unit": "dB"},
        ],
    }

    assert validate_llm_plan(plan, fake.state)["ok"] is True
    result = handle_command(
        "make the supervised two-step mix adjustment",
        session_id="command-llm-recipe",
        service=_service(fake),
        llm_plan=plan,
    )

    assert result["status"] == "confirmation_required"
    assert result["proposal_kind"] == "recipe"
    assert result["proposal"]["step_count"] == 2
    assert result["changed"] is False
    assert fake.writes == []


def test_typed_llm_plan_must_match_actionable_command() -> None:
    fake = FakeLive()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_mute",
        "track_index": 2,
        "track_name": "Vocal",
        "value": True,
        "relative": False,
        "unit": "boolean",
    }

    result = handle_command(
        "mute track 2",
        session_id="command-llm-request-mismatch",
        service=_service(fake),
        llm_plan=plan,
    )

    assert result["status"] == "invalid"
    assert result["changed"] is False
    assert result["llm"]["status"] == "rejected"
    assert result["llm"]["comparison"]["status"] == "mismatch"
    assert "proposal" not in result
    assert fake.writes == []


def test_typed_llm_plan_cannot_bypass_deterministic_refusal() -> None:
    fake = FakeLive()
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_mute",
        "track_index": 1,
        "track_name": "Bass",
        "value": True,
        "relative": False,
        "unit": "boolean",
    }

    result = handle_command(
        "delete track 2",
        session_id="command-llm-request-refusal",
        service=_service(fake),
        llm_plan=plan,
    )

    assert result["status"] == "invalid"
    assert result["llm"]["status"] == "rejected"
    assert result["llm"]["comparison"]["status"] == "refusal_bypass"
    assert "proposal" not in result
    assert fake.writes == []


def test_llm_shadow_mode_records_conflict_but_keeps_deterministic_authority(monkeypatch) -> None:
    fake = FakeLive()
    model_plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_mute",
        "track_index": 0,
        "track_name": "Kick",
        "value": True,
        "relative": False,
    }

    monkeypatch.setenv("KENN_LIVE_LLM_ENABLED", "1")
    monkeypatch.setenv("KENN_LIVE_LLM_MODE", "shadow")
    monkeypatch.setattr(live_command_module, "record_shadow_result", lambda _result: True)
    monkeypatch.setattr(
        live_command_module,
        "_generate_llm_plan",
        lambda command, snapshot: (model_plan, {"status": "accepted", "usage": {}}),
    )

    result = handle_command("mute track 2", session_id="command-llm-shadow", service=_service(fake))

    assert result["status"] == "confirmation_required"
    assert result["proposal"]["track_index"] == 1  # deterministic parser: user track 2 = Bass
    assert result["llm"]["mode"] == "shadow"
    assert result["llm"]["comparison"]["status"] == "mismatch"
    assert any(item["field"] == "track.index" for item in result["llm"]["comparison"]["differences"])
    assert fake.writes == []


def test_active_llm_mismatch_falls_back_to_deterministic_proposal(monkeypatch) -> None:
    fake = FakeLive()
    model_plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_mute",
        "track_index": 2,
        "track_name": "Vocal",
        "value": True,
        "relative": False,
        "unit": "boolean",
    }

    monkeypatch.setenv("KENN_LIVE_LLM_ENABLED", "1")
    monkeypatch.setenv("KENN_LIVE_LLM_MODE", "active")
    monkeypatch.setattr(live_command_module, "load_promotion_state", lambda: {"stage": "active"})
    monkeypatch.setattr(
        live_command_module,
        "_generate_llm_plan",
        lambda command, snapshot: (model_plan, {"status": "accepted", "usage": {}}),
    )

    result = handle_command("mute track 2", session_id="command-llm-active-mismatch", service=_service(fake))

    assert result["status"] == "confirmation_required"
    assert result["changed"] is False
    assert result["llm"]["status"] == "accepted"
    assert result["llm"]["comparison"]["status"] == "mismatch"
    assert result["llm"]["proposal_authority"] == "deterministic_fallback"
    assert result["proposal"]["track_name"] == "Bass"
    assert fake.writes == []


def test_runtime_mode_cannot_leapfrog_reviewed_promotion_stage(monkeypatch) -> None:
    fake = FakeLive()
    conflicting_plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_mute",
        "track_index": 2,
        "track_name": "Vocal",
        "value": True,
        "relative": False,
        "unit": "boolean",
    }
    monkeypatch.setenv("KENN_LIVE_LLM_ENABLED", "1")
    monkeypatch.setenv("KENN_LIVE_LLM_MODE", "active")
    monkeypatch.setattr(live_command_module, "load_promotion_state", lambda: {"stage": "shadow"})
    monkeypatch.setattr(
        live_command_module,
        "_generate_llm_plan",
        lambda command, snapshot: (conflicting_plan, {"status": "accepted", "usage": {}}),
    )

    result = handle_command("mute track 2", session_id="command-llm-stage-cap", service=_service(fake))

    assert result["status"] == "confirmation_required"
    assert result["llm"]["mode"] == "shadow"
    assert result["proposal"]["track_name"] == "Bass"
    assert fake.writes == []


def test_propose_stage_can_prepare_a_validated_model_only_intent(monkeypatch) -> None:
    fake = FakeLive()
    model_plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_mute",
        "track_index": 1,
        "track_name": "Bass",
        "value": True,
        "relative": False,
        "unit": "boolean",
    }
    monkeypatch.setenv("KENN_LIVE_LLM_ENABLED", "1")
    monkeypatch.setenv("KENN_LIVE_LLM_MODE", "propose")
    monkeypatch.setattr(live_command_module, "load_promotion_state", lambda: {"stage": "propose"})
    monkeypatch.setattr(
        live_command_module,
        "_generate_llm_plan",
        lambda command, snapshot: (model_plan, {"status": "accepted", "usage": {}}),
    )

    result = handle_command("kill the low-end channel", session_id="command-llm-propose", service=_service(fake))

    assert result["status"] == "confirmation_required"
    assert result["llm"]["mode"] == "propose"
    assert result["llm"]["proposal_authority"] == "validated_model"
    assert result["proposal"]["track_name"] == "Bass"
    assert fake.writes == []


def test_llm_plan_gets_one_structural_repair_attempt(monkeypatch) -> None:
    class Usage:
        def __init__(self, latency_ms: int) -> None:
            self.latency_ms = latency_ms

        def to_dict(self) -> dict[str, int | str]:
            return {
                "model": "test-model",
                "provider": "ollama",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "latency_ms": self.latency_ms,
                "task": "command",
            }

    responses = iter([
        '{"action":"set_mute","track_index":1,"value":true}',
        '{"schema":"kenn.ableton_llm_plan.v1","action":"set_mute","track_index":1,"track_name":"Bass","value":true,"relative":false,"unit":"boolean"}',
    ])
    calls: list[dict] = []

    def fake_completion(messages, **kwargs):
        calls.append({"messages": messages, **kwargs})
        return next(responses), Usage(100 if len(calls) == 1 else 200)

    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")
    monkeypatch.setenv("AUDIO_TOO_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AUDIO_TOO_LLM_MODEL", "test-model")
    monkeypatch.setenv("KENN_LIVE_LLM_ENABLED", "1")
    monkeypatch.setattr("kenn.llm.llm_rewrite._chat_completion", fake_completion)

    plan, metadata = live_command_module._generate_llm_plan(
        "mute track 2",
        FakeLive().state,
    )

    assert plan is not None
    assert plan["schema"] == "kenn.ableton_llm_plan.v1"
    assert plan["track_name"] == "Bass"
    assert metadata["status"] == "accepted"
    assert metadata["repair"]["status"] == "accepted"
    assert metadata["usage"]["latency_ms"] == 300
    assert len(calls) == 2
    assert "Validation error:" in calls[1]["messages"][0]["content"]
