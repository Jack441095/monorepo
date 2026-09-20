from __future__ import annotations

from copy import deepcopy
import threading

from kenn.core.live_action_service import (
    CANDIDATE_DEVICE_INSERTION_ALLOWLIST,
    DEVICE_INSERTION_ALLOWLIST,
    LiveActionService,
)
from kenn.core.live_executor import LiveExecutor
from kenn.core import live_receipt_journal as receipt_journal
from kenn.autonomous_agent import tool_set_ableton_volume


class FakeLive:
    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "tempo": 120.0,
            "is_playing": False,
            "selected_track_index": 0,
            "current_song_time": 16.0,
            "locators": [],
            "tracks": [
                {
                    "index": 0,
                    "name": "Vocal",
                    "volume": 0.5,
                    "pan": 0.0,
                    "muted": False,
                    "soloed": False,
                    "armed": False,
                    "has_midi_input": True,
                    "devices": [{"index": 0, "name": "Compressor", "is_active": True}],
                },
            ],
            "scenes": [
                {"index": 0, "name": "Intro"},
                {"index": 1, "name": "Chorus"},
            ],
        }
        self.writes: list[tuple[str, object]] = []
        self.fail_readback = False
        self.device_value = -12.0
        self.scene_triggered: dict[int, bool] = {}
        self.fail_scene_readback = False
        self.clip_playing: dict[tuple[int, int], bool] = {(0, 0): True}
        self.fail_clip_stop_write = False
        self.scene_fire_too_fast_for_is_triggered = False
        self.return_tracks = [
            {"index": 0, "name": "A-Reverb", "devices": ["Reverb"]},
            {"index": 1, "name": "B-Delay", "devices": ["Delay"]},
        ]
        self.sends: dict[tuple[int, int], float] = {(0, 0): 0.2, (0, 1): 0.0}
        self.selected_device = {"success": True, "track_index": 0, "device_index": 0}

    def get_return_tracks(self) -> list[dict]:
        return deepcopy(self.return_tracks)

    def get_track_send(self, track_index: int, send_index: int) -> float | None:
        return self.sends.get((track_index, send_index))

    def set_track_send(self, track_index: int, send_index: int, value: float) -> bool:
        self.writes.append(("send", track_index, send_index, value))
        self.sends[(track_index, send_index)] = value
        return True

    def query_session_state(self):
        snapshot = deepcopy(self.state)
        if self.fail_readback:
            snapshot["tracks"][0]["volume"] = 0.5
        return snapshot

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

    def _set(self, field: str, value: object) -> bool:
        self.writes.append((field, value))
        if not self.fail_readback:
            self.state["tracks"][0][field] = value
        return True

    def set_track_volume(self, index: int, value: float) -> bool:
        assert index == 0
        return self._set("volume", value)

    def set_track_pan(self, index: int, value: float) -> bool:
        assert index == 0
        return self._set("pan", value)

    def set_track_mute(self, index: int, value: bool) -> bool:
        assert index == 0
        return self._set("muted", value)

    def set_track_solo(self, index: int, value: bool) -> bool:
        assert index == 0
        return self._set("soloed", value)

    def set_track_arm(self, index: int, value: bool) -> bool:
        assert index == 0
        return self._set("armed", value)

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

    def create_audio_track(self, insertion_index: int) -> bool:
        assert insertion_index == -1
        insertion_index = len(self.state["tracks"])
        self.writes.append(("create_audio_track", insertion_index))
        self.state["tracks"].append({
            "index": insertion_index,
            "name": "Audio",
            "volume": 0.5,
            "pan": 0.0,
            "muted": False,
            "soloed": False,
            "armed": False,
            "has_midi_input": False,
            "devices": [],
        })
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
        self.writes.append(("is_playing", True))
        self.state["is_playing"] = True
        return True

    def stop_playback(self) -> bool:
        self.writes.append(("is_playing", False))
        self.state["is_playing"] = False
        return True

    def get_device_parameters(self, track_index: int, device_index: int) -> dict:
        assert track_index == 0
        assert device_index == 0
        return {
            "success": True,
            "device_name": "Compressor",
            "parameters": [{"index": 0, "name": "Threshold", "value": self.device_value, "min": -60.0, "max": 0.0}],
        }

    def set_device_parameter(self, track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        assert (track_index, device_index, parameter_index) == (0, 0, 0)
        self.writes.append(("Threshold", value))
        self.device_value = value
        return True

    def launch_scene(self, scene_index: int) -> bool:
        self.writes.append(("scene", scene_index))
        if self.scene_fire_too_fast_for_is_triggered:
            # Real-Live qualification found is_triggered can transition to
            # actually playing faster than one network round-trip can
            # observe it. Model that: the fire is never caught as
            # "triggered", but transport genuinely starts playing.
            self.state["is_playing"] = True
        else:
            self.scene_triggered[scene_index] = True
        return True

    def get_scene_playback_state(self, scene_index: int) -> dict:
        if self.fail_scene_readback:
            return {"success": True, "scene_index": scene_index, "is_triggered": False}
        return {"success": True, "scene_index": scene_index, "is_triggered": bool(self.scene_triggered.get(scene_index))}

    def get_clip_playback_state(self, track_index: int, clip_slot_index: int) -> dict:
        playing = self.clip_playing.get((track_index, clip_slot_index), False)
        return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, "is_playing": playing, "is_triggered": False}

    def stop_clip_slot(self, track_index: int, clip_slot_index: int) -> bool:
        self.writes.append(("stop_clip", track_index, clip_slot_index))
        if not self.fail_clip_stop_write:
            self.clip_playing[(track_index, clip_slot_index)] = False
        return True


def test_track_action_requires_exact_target_and_confirmation() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)

    missing = service.propose_track_action("set_volume", track_index=1, value=0.7, session_id="s")
    assert not missing["ok"]

    proposed = service.propose_track_action("set_volume", track_index=0, value=0.7, session_id="s")
    assert proposed["ok"]
    proposal = proposed["proposal"]
    assert service.execute(proposal, confirm_token="", session_id="s")["ok"] is False
    assert fake.writes == []

    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="s")
    assert applied["ok"]
    assert applied["receipt"]["verified"] is True
    assert fake.state["tracks"][0]["volume"] == 0.7

    replay = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="s")
    assert not replay["ok"]
    assert len(fake.writes) == 1


def test_midi_track_creation_is_append_only_named_verified_and_not_undoable() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)

    proposed = service.propose_midi_track_action(track_name="Hi Hats", session_id="midi-track")
    assert proposed["ok"] is True
    proposal = proposed["proposal"]
    assert proposal["insertion_index"] == 1
    assert proposal["new_track_name"] == "Hi Hats"
    assert fake.writes == []

    applied = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="midi-track",
    )
    assert applied["ok"] is True
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["readback"] == {
        "track_index": 1,
        "name": "Hi Hats",
        "type": "midi",
        "has_midi_input": True,
        "track_count": 2,
    }
    assert applied["receipt"]["undo"]["available"] is False
    assert fake.writes == [("create_midi_track", 1), ("name", 1, "Hi Hats")]

    replay = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="midi-track",
    )
    assert replay["ok"] is False
    assert len(fake.state["tracks"]) == 2


def test_midi_track_creation_rejects_stale_topology_without_writing() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_midi_track_action(session_id="midi-stale")
    proposal = proposed["proposal"]
    fake.state["tracks"][0]["name"] = "Renamed outside KENN"

    result = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="midi-stale",
    )
    assert result["ok"] is False
    assert "topology changed" in result["error"]
    assert fake.writes == []


def test_audio_track_creation_is_append_only_named_verified_and_not_undoable() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)

    proposed = service.propose_audio_track_action(track_name="Vox Print", session_id="audio-track")
    assert proposed["ok"] is True
    proposal = proposed["proposal"]
    assert proposal["action"] == "create_audio_track"
    assert proposal["after"]["type"] == "audio"
    assert fake.writes == []

    applied = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="audio-track",
    )
    assert applied["ok"] is True
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["readback"]["type"] == "audio"
    assert applied["receipt"]["readback"]["has_midi_input"] is False
    assert fake.state["tracks"][-1]["name"] == "Vox Print"
    assert fake.writes == [("create_audio_track", 1), ("name", 1, "Vox Print")]
    assert service.propose_undo(applied["receipt"], session_id="audio-track-undo")["ok"] is False


def test_execute_receipt_carries_correlation_id_retry_safety_and_stage_timings() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_track_action("set_volume", track_index=0, value=0.7, session_id="s")
    proposal = proposed["proposal"]

    applied = service.execute(
        proposal, confirm_token=proposal["confirmation_token"], session_id="s", correlation_id="caller-corr-1",
    )
    assert applied["ok"] is True
    receipt = applied["receipt"]
    assert receipt["correlation_id"] == "caller-corr-1"
    assert receipt["retry_safe"] == "safe"
    assert "snapshot" in receipt["stage_timings_ms"]
    assert "write" in receipt["stage_timings_ms"]
    assert "readback" in receipt["stage_timings_ms"]
    assert "total" in receipt["stage_timings_ms"]


def test_execute_mints_a_correlation_id_when_none_supplied() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_track_action("set_volume", track_index=0, value=0.7, session_id="s")
    proposal = proposed["proposal"]
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="s")
    assert applied["receipt"]["correlation_id"].startswith("corr-")


def test_failed_receipt_reports_requires_inspection_for_ambiguous_readback() -> None:
    fake = FakeLive()
    fake.fail_readback = True
    service = LiveActionService(fake)
    proposed = service.propose_track_action("set_volume", track_index=0, value=0.7, session_id="s")
    proposal = proposed["proposal"]
    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="s")
    assert result["ok"] is False
    assert result["receipt"]["status"] == "failed_verification"
    assert result["receipt"]["retry_safe"] == "requires_inspection"


def test_interrupted_writes_are_reconciled_by_readback_across_shared_actions() -> None:
    cases = []

    track_live = FakeLive()
    track_original = track_live.set_track_volume

    def interrupted_track(index: int, value: float) -> bool:
        track_original(index, value)
        raise TimeoutError("track acknowledgement lost")

    track_live.set_track_volume = interrupted_track  # type: ignore[method-assign]
    cases.append((track_live, LiveActionService(track_live).propose_track_action("set_volume", track_index=0, value=0.7, session_id="interrupted-track"), "interrupted-track"))

    transport_live = FakeLive()
    transport_original = transport_live.start_playback

    def interrupted_transport() -> bool:
        transport_original()
        raise TimeoutError("transport acknowledgement lost")

    transport_live.start_playback = interrupted_transport  # type: ignore[method-assign]
    cases.append((transport_live, LiveActionService(transport_live).propose_transport_action("transport_play", session_id="interrupted-transport"), "interrupted-transport"))

    scene_live = FakeLive()
    scene_original = scene_live.launch_scene

    def interrupted_scene(scene_index: int) -> bool:
        scene_original(scene_index)
        raise TimeoutError("scene acknowledgement lost")

    scene_live.launch_scene = interrupted_scene  # type: ignore[method-assign]
    cases.append((scene_live, LiveActionService(scene_live).propose_scene_action("launch_scene", scene_index=0, session_id="interrupted-scene"), "interrupted-scene"))

    clip_live = FakeLive()
    clip_original = clip_live.stop_clip_slot

    def interrupted_clip(track_index: int, clip_slot_index: int) -> bool:
        clip_original(track_index, clip_slot_index)
        raise TimeoutError("clip acknowledgement lost")

    clip_live.stop_clip_slot = interrupted_clip  # type: ignore[method-assign]
    cases.append((clip_live, LiveActionService(clip_live).propose_clip_action("stop_clip", track_index=0, clip_slot_index=0, session_id="interrupted-clip"), "interrupted-clip"))

    send_live = FakeLive()
    send_original = send_live.set_track_send

    def interrupted_send(track_index: int, send_index: int, value: float) -> bool:
        send_original(track_index, send_index, value)
        raise TimeoutError("send acknowledgement lost")

    send_live.set_track_send = interrupted_send  # type: ignore[method-assign]
    cases.append((send_live, LiveActionService(send_live).propose_send_action(track_index=0, return_track_index=0, value=0.6, session_id="interrupted-send"), "interrupted-send"))

    for fake, proposed, session_id in cases:
        assert proposed["ok"] is True
        proposal = proposed["proposal"]
        result = LiveActionService(fake).execute(
            proposal,
            confirm_token=proposal["confirmation_token"],
            session_id=session_id,
        )
        assert result["ok"] is True
        assert result["receipt"]["verified"] is True
        assert result["receipt"]["write_acknowledgement"] == "unacknowledged_write_reconciled"
        assert "acknowledgement lost" in result["receipt"]["write_error"]
        assert result["receipt"]["retry_safe"] == "safe"


def test_interrupted_write_with_failed_readback_is_transport_uncertain() -> None:
    fake = FakeLive()
    original = fake.set_track_volume

    def interrupted_write(index: int, value: float) -> bool:
        original(index, value)
        fake.fail_readback = True
        raise TimeoutError("acknowledgement and readback lost")

    fake.set_track_volume = interrupted_write  # type: ignore[method-assign]
    service = LiveActionService(fake)
    proposed = service.propose_track_action("set_volume", track_index=0, value=0.7, session_id="uncertain-track")
    proposal = proposed["proposal"]
    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="uncertain-track")

    assert result["ok"] is False
    assert result["receipt"]["verified"] is False
    assert result["receipt"]["status"] == "failed_verification"
    assert result["receipt"]["write_acknowledgement"] == "not_confirmed"
    assert result["receipt"]["retry_safe"] == "requires_inspection"


def test_track_rename_is_verified_and_identity_bound_undoable() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_track_action(
        "rename_track", track_index=0, track_name="Vocal", value="Lead Vocal", session_id="rename"
    )
    assert proposed["ok"]
    proposal = proposed["proposal"]
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="rename")
    assert applied["ok"] is True
    assert applied["receipt"]["verified"] is True
    assert fake.state["tracks"][0]["name"] == "Lead Vocal"

    inverse = service.propose_undo(applied["receipt"], session_id="rename")
    assert inverse["ok"]
    undo = inverse["proposal"]
    restored = service.execute(undo, confirm_token=undo["confirmation_token"], session_id="rename")
    assert restored["ok"] is True
    assert fake.state["tracks"][0]["name"] == "Vocal"


def test_track_action_undo_is_refused_after_a_later_change_to_the_same_track() -> None:
    """Real-Live interruption/recovery scenario: a second, legitimate volume
    change happens after the receipt being undone. Blindly restoring the
    older receipt's "before" would silently discard that later change."""
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_track_action("set_volume", track_index=0, value=0.6, session_id="vol")
    applied = service.execute(
        proposed["proposal"], confirm_token=proposed["proposal"]["confirmation_token"], session_id="vol",
    )
    assert applied["ok"] is True

    # Someone/something else changes the same track's volume after this receipt.
    fake.state["tracks"][0]["volume"] = 0.9

    stale = service.propose_undo(applied["receipt"], session_id="vol-undo-stale")
    assert stale["ok"] is False
    assert "stale" in stale["error"]
    assert fake.state["tracks"][0]["volume"] == 0.9


def test_track_rename_rejects_duplicate_names_before_write() -> None:
    fake = FakeLive()
    fake.state["tracks"].append({"index": 1, "name": "Drums", "devices": []})
    service = LiveActionService(fake)
    result = service.propose_track_action(
        "rename_track", track_index=0, track_name="Vocal", value="Drums", session_id="rename-duplicate"
    )
    assert result["ok"] is False
    assert "another Live track" in result["error"]
    assert fake.writes == []


def test_stale_state_is_rejected_before_write() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_track_action("set_pan", track_index=0, value=0.25, session_id="stale")
    proposal = proposed["proposal"]
    fake.state["tracks"][0]["pan"] = -0.25

    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="stale")
    assert not result["ok"]
    assert "changed" in result["error"]
    assert fake.writes == []


def test_changed_target_and_out_of_range_values_are_refused() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    invalid = service.propose_track_action("set_volume", track_index=0, value=1.5, session_id="bounds")
    assert not invalid["ok"]

    proposed = service.propose_track_action("set_mute", track_index=0, value=True, session_id="identity")
    proposal = proposed["proposal"]
    fake.state["tracks"][0]["name"] = "Renamed Vocal"
    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="identity")
    assert not result["ok"]
    assert "changed" in result["error"]
    assert fake.writes == []


def test_custom_idempotency_key_rejects_a_second_request() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    first = service.propose_track_action("set_pan", track_index=0, value=0.1, session_id="idem")
    first_proposal = first["proposal"]
    applied = service.execute(
        first_proposal,
        confirm_token=first_proposal["confirmation_token"],
        session_id="idem",
        idempotency_key="request-1",
    )
    assert applied["ok"]

    second = service.propose_track_action("set_pan", track_index=0, value=0.2, session_id="idem")
    second_proposal = second["proposal"]
    replay = service.execute(
        second_proposal,
        confirm_token=second_proposal["confirmation_token"],
        session_id="idem",
        idempotency_key="request-1",
    )
    assert not replay["ok"]
    assert len(fake.writes) == 1


def test_idempotency_key_is_reserved_while_a_write_is_in_flight() -> None:
    class BlockingLive(FakeLive):
        def __init__(self) -> None:
            super().__init__()
            self.started = threading.Event()
            self.release = threading.Event()

        def set_track_volume(self, index: int, value: float) -> bool:
            self.started.set()
            self.release.wait(timeout=2)
            return super().set_track_volume(index, value)

    fake = BlockingLive()
    service = LiveActionService(fake)
    first = service.propose_track_action("set_volume", track_index=0, value=0.6, session_id="race")
    second = service.propose_track_action("set_volume", track_index=0, value=0.7, session_id="race")
    result: dict = {}

    def execute_first() -> None:
        result.update(service.execute(first["proposal"], confirm_token=first["proposal"]["confirmation_token"], session_id="race", idempotency_key="race-1"))

    thread = threading.Thread(target=execute_first)
    thread.start()
    assert fake.started.wait(timeout=2)
    replay = service.execute(second["proposal"], confirm_token=second["proposal"]["confirmation_token"], session_id="race", idempotency_key="race-1")
    assert not replay["ok"]
    assert "progress" in replay["error"]
    fake.release.set()
    thread.join(timeout=2)
    assert result["ok"]
    assert len(fake.writes) == 1


def test_failed_readback_is_honest_and_receipted() -> None:
    fake = FakeLive()
    fake.fail_readback = True
    service = LiveActionService(fake)
    proposed = service.propose_track_action("set_volume", track_index=0, value=0.8, session_id="readback")
    proposal = proposed["proposal"]

    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="readback")
    assert not result["ok"]
    assert result["receipt"]["status"] == "failed_verification"
    assert result["receipt"]["verified"] is False


def test_write_exception_is_honest_and_retires_idempotency_key() -> None:
    class ExplodingLive(FakeLive):
        def set_track_volume(self, index: int, value: float) -> bool:
            raise RuntimeError("simulated Live write failure")

    fake = ExplodingLive()
    service = LiveActionService(fake)
    proposed = service.propose_track_action("set_volume", track_index=0, value=0.8, session_id="exception")
    proposal = proposed["proposal"]

    result = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="exception",
        idempotency_key="exception-1",
    )
    assert not result["ok"]
    assert result["receipt"]["status"] == "failed_verification"
    assert result["receipt"]["verified"] is False
    assert result["receipt"]["write_acknowledgement"] == "not_confirmed"
    assert result["receipt"]["retry_safe"] == "requires_inspection"
    retry = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="exception",
        idempotency_key="exception-1",
    )
    assert not retry["ok"]
    assert "already executed" in retry["error"]


def test_legacy_batch_executor_and_service_batch_path_are_fail_closed() -> None:
    fake = FakeLive()
    batch = {"schema": "kenn.batch_action_proposal.v1", "proposals": []}

    legacy = LiveExecutor(osc_client=fake).apply_proposal(batch, confirm_token="unused", session_id="batch")
    assert not legacy["ok"]
    assert "disabled" in legacy["error"]
    assert fake.writes == []

    service = LiveActionService(fake)
    routed = service.execute_device_action(batch, confirm_token="unused", session_id="batch")
    assert not routed["ok"]
    assert "disabled" in routed["error"]
    assert fake.writes == []


def test_transport_and_verified_undo_are_confirmation_gated() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_transport_action("transport_play", session_id="transport")
    proposal = proposed["proposal"]
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="transport")
    assert applied["ok"]
    receipt = applied["receipt"]

    undo_proposed = service.propose_undo(receipt, session_id="transport")
    assert undo_proposed["ok"]
    undo = service.execute(
        undo_proposed["proposal"],
        confirm_token=undo_proposed["proposal"]["confirmation_token"],
        session_id="transport",
    )
    assert undo["ok"]
    assert fake.state["is_playing"] is False


def test_scene_launch_is_confirmation_gated_and_verified() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_scene_action("launch_scene", scene_index=1, scene_name="Chorus", session_id="scene")
    assert proposed["ok"]
    proposal = proposed["proposal"]
    assert proposal["scene_index"] == 1
    assert proposal["scene_name"] == "Chorus"
    assert proposal["requires_confirmation"]
    assert fake.writes == []  # nothing changed during proposal

    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="scene")
    assert applied["ok"]
    receipt = applied["receipt"]
    assert receipt["verified"]
    assert receipt["status"] == "applied"
    assert fake.writes == [("scene", 1)]

    # Exact replay of the same confirmation token must be rejected.
    replay = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="scene")
    assert not replay["ok"]


def test_scene_launch_rejects_unknown_scene_index() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_scene_action("launch_scene", scene_index=99, session_id="scene")
    assert not proposed["ok"]
    assert fake.writes == []


def test_scene_launch_has_no_bespoke_undo() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_scene_action("launch_scene", scene_index=0, scene_name="Intro", session_id="scene")
    proposal = proposed["proposal"]
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="scene")
    assert applied["ok"]

    undo_proposed = service.propose_undo(applied["receipt"], session_id="scene")
    assert not undo_proposed["ok"]
    assert "no reversible" in undo_proposed["error"]


def test_scene_launch_failed_verification_is_honest() -> None:
    fake = FakeLive()
    fake.fail_scene_readback = True
    service = LiveActionService(fake)
    proposed = service.propose_scene_action("launch_scene", scene_index=0, scene_name="Intro", session_id="scene")
    proposal = proposed["proposal"]
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="scene")
    assert not applied["ok"]
    assert applied["receipt"]["status"] == "failed_verification"
    assert applied["receipt"]["verified"] is False


def test_scene_launch_verified_via_transport_when_is_triggered_outruns_readback() -> None:
    """Real-Live qualification (2026-09-05): firing scene 1 on the disposable
    set genuinely started playback, but is_triggered read back False because
    the transition to actually-playing outran the network round-trip. This
    locks in the fallback verification that made that a verified success
    instead of a false failed_verification report."""
    fake = FakeLive()
    fake.scene_fire_too_fast_for_is_triggered = True
    service = LiveActionService(fake)
    proposed = service.propose_scene_action("launch_scene", scene_index=0, scene_name="Intro", session_id="scene")
    proposal = proposed["proposal"]
    assert proposal["transport_was_playing_before"] is False
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="scene")
    assert applied["ok"]
    assert applied["receipt"]["verified"] is True


def test_scene_launch_ambiguous_when_transport_already_playing_stays_unverified() -> None:
    """If transport was already playing before the fire, "is now playing"
    proves nothing about this specific fire -- the honest, conservative
    behavior is to still require is_triggered in that case."""
    fake = FakeLive()
    fake.state["is_playing"] = True
    fake.scene_fire_too_fast_for_is_triggered = True
    service = LiveActionService(fake)
    proposed = service.propose_scene_action("launch_scene", scene_index=0, scene_name="Intro", session_id="scene")
    proposal = proposed["proposal"]
    assert proposal["transport_was_playing_before"] is True
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="scene")
    assert not applied["ok"]
    assert applied["receipt"]["verified"] is False


def test_named_locator_add_is_confirmation_gated_and_verified() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_locator_action("add_locator", locator_name="Verse", session_id="locator")
    assert proposed["ok"]
    proposal = proposed["proposal"]
    assert proposal["locator_name"] == "Verse"
    assert proposal["locator_time_beats"] == 16.0
    assert fake.writes == []

    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="locator")
    assert applied["ok"]
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["readback"] == {"name": "Verse", "time_beats": 16.0}
    assert fake.writes == [("locator", "Verse", 16.0)]

    replay = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="locator")
    assert not replay["ok"]
    undo = service.propose_undo(applied["receipt"], session_id="locator")
    assert undo["ok"]
    undo_applied = service.execute(
        undo["proposal"],
        confirm_token=undo["proposal"]["confirmation_token"],
        session_id="locator",
    )
    assert undo_applied["ok"]
    assert undo_applied["receipt"]["verified"] is True
    assert undo_applied["receipt"]["readback"] == {"exists": False, "name": "Verse", "time_beats": 16.0}
    assert fake.state["locators"] == []
    assert fake.writes == [("locator", "Verse", 16.0), ("remove_locator", "Verse", 16.0)]


def test_locator_undo_refuses_after_playhead_moves() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_locator_action("add_locator", locator_name="Verse", session_id="locator-stale-undo")
    applied = service.execute(
        proposed["proposal"],
        confirm_token=proposed["proposal"]["confirmation_token"],
        session_id="locator-stale-undo",
    )
    fake.state["current_song_time"] = 20.0
    undo = service.propose_undo(applied["receipt"], session_id="locator-stale-undo")
    assert not undo["ok"]
    assert "playhead moved" in undo["error"]


def test_named_locator_add_refuses_existing_position_and_moved_playhead() -> None:
    fake = FakeLive()
    fake.state["locators"] = [{"index": 0, "name": "Intro", "time_beats": 16.0}]
    service = LiveActionService(fake)
    occupied = service.propose_locator_action("add_locator", locator_name="Verse", session_id="locator-occupied")
    assert not occupied["ok"]
    assert fake.writes == []

    fake.state["locators"] = []
    proposed = service.propose_locator_action("add_locator", locator_name="Verse", session_id="locator-stale")
    assert proposed["ok"]
    fake.state["current_song_time"] = 20.0
    applied = service.execute(
        proposed["proposal"],
        confirm_token=proposed["proposal"]["confirmation_token"],
        session_id="locator-stale",
    )
    assert not applied["ok"]
    assert "playhead moved" in applied["error"]
    assert fake.writes == []


def test_focus_track_is_confirmation_gated_and_has_identity_bound_undo() -> None:
    fake = FakeLive()
    fake.state["tracks"].append({
        "index": 1,
        "name": "Drums",
        "volume": 0.5,
        "pan": 0.0,
        "muted": False,
        "soloed": False,
        "armed": False,
        "devices": [],
    })
    service = LiveActionService(fake)
    proposed = service.propose_view_action(
        "focus_track", track_index=1, track_name="Drums", session_id="focus"
    )
    assert proposed["ok"]
    proposal = proposed["proposal"]
    assert proposal["before"] == 0
    assert proposal["after"] == 1
    assert proposal["previous_track_name"] == "Vocal"
    assert fake.writes == []

    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="focus")
    assert applied["ok"]
    assert applied["receipt"]["readback"] == 1
    assert fake.state["selected_track_index"] == 1
    assert fake.writes == [("focus", 1)]

    undo_proposed = service.propose_undo(applied["receipt"], session_id="focus")
    assert undo_proposed["ok"]
    undo = undo_proposed["proposal"]
    assert undo["track_index"] == 0
    assert undo["track_name"] == "Vocal"
    undone = service.execute(undo, confirm_token=undo["confirmation_token"], session_id="focus")
    assert undone["ok"]
    assert fake.state["selected_track_index"] == 0
    assert fake.writes == [("focus", 1), ("focus", 0)]


def test_focus_device_is_confirmation_gated_and_has_identity_bound_undo() -> None:
    fake = FakeLive()
    fake.state["tracks"].append({
        "index": 1,
        "name": "Synth",
        "volume": 0.5,
        "pan": 0.0,
        "muted": False,
        "soloed": False,
        "armed": False,
        "devices": [{"index": 0, "name": "EQ Eight"}],
    })
    proposed = LiveActionService(fake).propose_view_action(
        "focus_device",
        track_index=1,
        track_name="Synth",
        device_index=0,
        device_name="EQ Eight",
        session_id="focus-device",
    )
    assert proposed["ok"]
    proposal = proposed["proposal"]
    assert proposal["before"] == {"track_index": 0, "device_index": 0}
    assert proposal["after"] == {"track_index": 1, "device_index": 0}
    assert proposal["previous_device_name"] == "Compressor"
    assert fake.writes == []

    service = LiveActionService(fake)
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="focus-device")
    assert applied["ok"]
    assert applied["receipt"]["readback"] == {"track_index": 1, "device_index": 0}
    assert fake.writes == [("focus_device", 1, 0)]

    undo_proposed = service.propose_undo(applied["receipt"], session_id="focus-device")
    assert undo_proposed["ok"]
    undo = undo_proposed["proposal"]
    assert undo["action"] == "focus_device"
    assert undo["track_index"] == 0
    assert undo["device_index"] == 0
    undone = service.execute(undo, confirm_token=undo["confirmation_token"], session_id="focus-device")
    assert undone["ok"]
    assert fake.selected_device["track_index"] == 0
    assert fake.writes == [("focus_device", 1, 0), ("focus_device", 0, 0)]


def test_clip_stop_is_confirmation_gated_and_verified() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_clip_action("stop_clip", track_index=0, clip_slot_index=0, session_id="clip")
    assert proposed["ok"]
    proposal = proposed["proposal"]
    assert proposal["track_index"] == 0
    assert proposal["clip_slot_index"] == 0
    assert fake.writes == []

    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="clip")
    assert applied["ok"]
    receipt = applied["receipt"]
    assert receipt["verified"]
    assert receipt["status"] == "applied"
    assert fake.writes == [("stop_clip", 0, 0)]
    assert fake.clip_playing[(0, 0)] is False

    replay = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="clip")
    assert not replay["ok"]


def test_clip_stop_refuses_when_nothing_is_playing() -> None:
    fake = FakeLive()
    fake.clip_playing[(0, 0)] = False
    service = LiveActionService(fake)
    proposed = service.propose_clip_action("stop_clip", track_index=0, clip_slot_index=0, session_id="clip")
    assert not proposed["ok"]
    assert fake.writes == []


def test_clip_stop_has_no_bespoke_undo() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_clip_action("stop_clip", track_index=0, clip_slot_index=0, session_id="clip")
    proposal = proposed["proposal"]
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="clip")
    assert applied["ok"]

    undo_proposed = service.propose_undo(applied["receipt"], session_id="clip")
    assert not undo_proposed["ok"]
    assert "no reversible" in undo_proposed["error"]


def test_device_action_uses_shared_receipt_idempotency_and_undo() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_device_action(
        track_index=0,
        device_index=0,
        parameter_index=0,
        proposed_value=-18.0,
        reason="test compressor threshold",
        session_id="device",
        parameter_name="Threshold",
        unit="dB",
        track_name="Vocal",
    )
    assert proposed["ok"]
    proposal = proposed["proposal"]
    applied = service.execute_device_action(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="device",
    )
    assert applied["ok"]
    receipt = applied["receipt"]
    assert receipt["schema"] == "kenn.ableton_action_receipt.v1"
    assert receipt["action"] == "set_device_parameter"
    assert receipt["verified"] is True
    replay = service.execute_device_action(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="device",
    )
    assert not replay["ok"]

    undo_proposed = service.propose_undo(receipt, session_id="device")
    assert undo_proposed["ok"]
    undo = undo_proposed["proposal"]
    undone = service.execute_device_action(
        undo,
        confirm_token=undo["confirmation_token"],
        session_id="device",
    )
    assert undone["ok"]
    assert fake.device_value == -12.0


def test_device_undo_after_restart_refuses_to_overwrite_a_later_edit(tmp_path, monkeypatch) -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_device_action(
        track_index=0,
        device_index=0,
        parameter_index=0,
        proposed_value=-18.0,
        reason="test restart-safe compressor undo",
        session_id="device-restart",
        parameter_name="Threshold",
        unit="dB",
        track_name="Vocal",
    )
    proposal = proposed["proposal"]
    applied = service.execute_device_action(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="device-restart",
    )
    assert applied["ok"]

    journal_path = tmp_path / "receipts.jsonl"
    monkeypatch.setattr(receipt_journal, "JOURNAL_PATH", journal_path)
    assert receipt_journal.record_receipt(applied["receipt"], session_id="device-restart")
    persisted_receipt = receipt_journal.list_receipts(session_id="device-restart")[0]["receipt"]
    assert "confirmation_token" not in persisted_receipt

    fake.device_value = -20.0  # A legitimate edit made while KENN was disconnected.
    writes_before_undo = list(fake.writes)
    restarted_service = LiveActionService(fake)
    undo = restarted_service.propose_undo(persisted_receipt, session_id="device-restarted")

    assert undo["ok"] is False
    assert "changed since the receipt" in undo["error"]
    assert fake.device_value == -20.0
    assert fake.writes == writes_before_undo


def test_device_undo_after_restart_issues_fresh_confirmation_when_state_is_unchanged(tmp_path, monkeypatch) -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_device_action(
        track_index=0,
        device_index=0,
        parameter_index=0,
        proposed_value=-18.0,
        reason="test recoverable compressor undo",
        session_id="device-before-restart",
        parameter_name="Threshold",
        unit="dB",
        track_name="Vocal",
    )
    proposal = proposed["proposal"]
    applied = service.execute_device_action(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="device-before-restart",
    )
    assert applied["ok"]

    journal_path = tmp_path / "receipts.jsonl"
    monkeypatch.setattr(receipt_journal, "JOURNAL_PATH", journal_path)
    assert receipt_journal.record_receipt(applied["receipt"], session_id="device-before-restart")
    persisted_receipt = receipt_journal.list_receipts(session_id="device-before-restart")[0]["receipt"]

    restarted_service = LiveActionService(fake)
    undo_proposed = restarted_service.propose_undo(persisted_receipt, session_id="device-after-restart")
    assert undo_proposed["ok"] is True
    undo = undo_proposed["proposal"]
    assert undo["requires_confirmation"] is True
    assert undo["confirmation_token"] != proposal["confirmation_token"]

    restored = restarted_service.execute_device_action(
        undo,
        confirm_token=undo["confirmation_token"],
        session_id="device-after-restart",
    )
    assert restored["ok"] is True
    assert restored["receipt"]["verified"] is True
    assert fake.device_value == -12.0


def test_device_timeout_returns_failed_receipt_without_success() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_device_action(
        track_index=0,
        device_index=0,
        parameter_index=0,
        proposed_value=-18.0,
        reason="test device timeout",
        session_id="device-timeout",
        parameter_name="Threshold",
        unit="dB",
        track_name="Vocal",
    )
    assert proposed["ok"]
    proposal = proposed["proposal"]

    def timed_out_snapshot():
        raise TimeoutError("simulated Live timeout")

    fake.query_session_state = timed_out_snapshot  # type: ignore[method-assign]
    result = service.execute_device_action(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="device-timeout",
        idempotency_key=proposal["id"],
    )

    assert not result["ok"]
    assert result["receipt"]["status"] == "failed"
    assert result["receipt"]["verified"] is False
    assert result["receipt"]["readback"] is None
    assert fake.writes == []


def test_autonomous_track_tool_uses_the_same_two_phase_boundary(monkeypatch) -> None:
    fake = FakeLive()
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr("kenn.core.live_action_service.live_client", fake)

    proposed = tool_set_ableton_volume(0, 0.6, session_id="agent")
    assert proposed["status"] == "confirmation_required"
    applied = tool_set_ableton_volume(
        0,
        0.6,
        confirm_token=proposed["confirm_token"],
        session_id="agent",
    )
    assert applied["status"] == "success"
    assert applied["verified"] is True
    assert fake.writes == [("volume", 0.6)]


def test_candidate_insertion_devices_are_not_yet_active() -> None:
    """Candidates only become insertable after real-Live reversible-parameter
    qualification (see the module docstring on CANDIDATE_DEVICE_INSERTION_ALLOWLIST).
    This guards against an accidental promotion slipping in unqualified."""
    assert CANDIDATE_DEVICE_INSERTION_ALLOWLIST.isdisjoint(DEVICE_INSERTION_ALLOWLIST)
    assert CANDIDATE_DEVICE_INSERTION_ALLOWLIST == frozenset()
    assert "Compressor" in DEVICE_INSERTION_ALLOWLIST  # qualified 2026-09-05
    assert "Hybrid Reverb" in DEVICE_INSERTION_ALLOWLIST  # qualified 2026-09-06
    assert "Echo" in DEVICE_INSERTION_ALLOWLIST  # qualified 2026-09-06


def test_send_action_resolves_return_track_by_exact_name_and_is_verified() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_send_action(
        track_index=0, return_track_name="A-Reverb", value=0.6, session_id="send",
    )
    assert proposed["ok"] is True
    proposal = proposed["proposal"]
    assert proposal["return_track_index"] == 0
    assert proposal["return_track_name"] == "A-Reverb"
    assert proposal["before"] == 0.2
    assert proposal["after"] == 0.6

    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="send")
    assert applied["ok"] is True
    assert applied["receipt"]["verified"] is True
    assert fake.sends[(0, 0)] == 0.6
    assert fake.writes == [("send", 0, 0, 0.6)]

    replay = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="send")
    assert not replay["ok"]
    assert len(fake.writes) == 1


def test_return_track_creation_refuses_unavailable_identity_readback() -> None:
    fake = FakeLive()
    fake.get_return_tracks_with_status = lambda: ([], False)  # type: ignore[method-assign]

    result = LiveActionService(fake).propose_return_track_creation_action(
        track_name="Vocal Verb", session_id="return-unavailable",
    )

    assert result["ok"] is False
    assert "readback is unavailable" in result["error"]
    assert fake.writes == []


def test_send_action_resolves_return_track_by_exact_index() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_send_action(
        track_index=0, return_track_index=1, value=0.5, session_id="send",
    )
    assert proposed["ok"] is True
    assert proposed["proposal"]["return_track_name"] == "B-Delay"
    assert proposed["proposal"]["before"] == 0.0


def test_send_action_refuses_ambiguous_return_track_name() -> None:
    fake = FakeLive()
    fake.return_tracks.append({"index": 2, "name": "A-Reverb", "devices": ["Reverb"]})
    service = LiveActionService(fake)
    result = service.propose_send_action(
        track_index=0, return_track_name="A-Reverb", value=0.5, session_id="send",
    )
    assert result["ok"] is False
    assert "More than one" in result["error"]


def test_send_action_refuses_unknown_return_track_name() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    result = service.propose_send_action(
        track_index=0, return_track_name="C-Chorus", value=0.5, session_id="send",
    )
    assert result["ok"] is False
    assert "No return track matching" in result["error"]


def test_send_action_resolves_return_track_by_unambiguous_substring() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    result = service.propose_send_action(
        track_index=0, return_track_name="reverb", value=0.5, session_id="send",
    )
    assert result["ok"] is True
    assert result["proposal"]["return_track_name"] == "A-Reverb"


def test_send_action_rejects_stale_value_before_write() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_send_action(
        track_index=0, return_track_name="A-Reverb", value=0.6, session_id="send",
    )
    proposal = proposed["proposal"]
    fake.sends[(0, 0)] = 0.9  # changed by someone/something else before confirmation
    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="send")
    assert result["ok"] is False
    assert "changed since the proposal" in result["error"]
    assert fake.writes == []


def test_send_action_supports_verified_undo() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_send_action(
        track_index=0, return_track_name="A-Reverb", value=0.6, session_id="send",
    )
    proposal = proposed["proposal"]
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="send")
    assert applied["ok"] is True

    undo_proposed = service.propose_undo(applied["receipt"], session_id="send-undo")
    assert undo_proposed["ok"] is True
    undo_proposal = undo_proposed["proposal"]
    assert undo_proposal["after"] == 0.2
    restored = service.execute(undo_proposal, confirm_token=undo_proposal["confirmation_token"], session_id="send-undo")
    assert restored["ok"] is True
    assert fake.sends[(0, 0)] == 0.2


def test_send_action_undo_is_refused_after_a_later_change_to_the_same_send() -> None:
    """Real-Live interruption/recovery scenario: a second, legitimate send
    change happens after the receipt being undone. Blindly restoring the
    older receipt's "before" would silently discard that later change."""
    fake = FakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_send_action(
        track_index=0, return_track_name="A-Reverb", value=0.6, session_id="send",
    )
    applied = service.execute(
        proposed["proposal"], confirm_token=proposed["proposal"]["confirmation_token"], session_id="send",
    )
    assert applied["ok"] is True

    # Someone/something else changes the same send after this receipt.
    fake.sends[(0, 0)] = 0.9

    stale = service.propose_undo(applied["receipt"], session_id="send-undo-stale")
    assert stale["ok"] is False
    assert "stale" in stale["error"]
    assert fake.sends[(0, 0)] == 0.9


def test_send_action_rejects_out_of_range_value() -> None:
    fake = FakeLive()
    service = LiveActionService(fake)
    result = service.propose_send_action(
        track_index=0, return_track_name="A-Reverb", value=1.5, session_id="send",
    )
    assert result["ok"] is False
    assert "between 0.0 and 1.0" in result["error"]
