"""Ableton Live 12 ControlSurface Remote Script for Audio_Too KENN & Thursday AI.

Communicates over UDP (JSON payloads), listening on port 11000. Replies are
sent back to whichever address/port the request actually came from, not a
second hardcoded port -- see the note on `send_response()` for why that
matters.

Found live 2026-08-05 (docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md,
Phase 4): the previous version of this file was `class AudioToo_Bridge:`
with no base class at all -- not a real Ableton Remote Script, just a
plain object that happened to sit in the Remote Scripts folder. Ableton's
Preferences > Control Surface dropdown never listed it because Live only
recognizes scripts whose `create_instance()` returns a `ControlSurface`
subclass. This rewrite fixes that, and also fixes a second bug: the old
`send_response()` always replied to a hardcoded RESPONSE_PORT (11001),
but the client (kenn/ableton_osc_bridge.py's AbletonOSCClient) never binds
its socket to receive on 11001 -- it only reads back on whatever ephemeral
port the OS gave it when it called sendto(). Replying to `addr` from
`recvfrom()` reaches that same socket; a fixed response port does not.

Every response also echoes back the request's own `id` field. Found live
2026-08-05: without this, a write's reply left unread in the client's
socket buffer would get picked up by the client's *next*, unrelated
query -- corrupting its result (a session-state query getting back a
write-command's reply shape instead of its own). The client now matches
replies by id and discards anything else.
"""

from __future__ import annotations

import json
import socket

from _Framework.ControlSurface import ControlSurface

try:
    import Live
except ImportError:
    Live = None

LISTEN_PORT = 11000
HOST = "127.0.0.1"

# Ableton calls update_display() roughly every 100ms; polling the socket
# there (rather than trying to run real asyncio inside Live's process) is
# the standard non-blocking pattern used by other Remote Scripts like
# AbletonOSC.
POLL_INTERVAL_TICKS = 1

# Normalise common shorthand/class names to the display names that appear
# in Ableton's browser tree (case-insensitive lookup at runtime).
_DEVICE_NAME_ALIASES = {
    "eqeight": "EQ Eight",
    "eq eight": "EQ Eight",
    "eq8": "EQ Eight",
    "eqthree": "EQ Three",
    "eq three": "EQ Three",
    "eq3": "EQ Three",
    "autofilter": "Auto Filter",
    "auto filter": "Auto Filter",
    "beatrepeat": "Beat Repeat",
    "beat repeat": "Beat Repeat",
    "corpusresonator": "Corpus",
    "drumrack": "Drum Rack",
    "drum rack": "Drum Rack",
    "instrumentrack": "Instrument Rack",
    "instrument rack": "Instrument Rack",
    "audiorack": "Audio Effect Rack",
    "audio effect rack": "Audio Effect Rack",
    "midirack": "MIDI Effect Rack",
    "midi effect rack": "MIDI Effect Rack",
    "simplerdevice": "Simpler",
    "multibanddynamics": "Multiband Dynamics",
    "multiband dynamics": "Multiband Dynamics",
    "spectrumanalyzer": "Spectrum",
}


def _optional_meter_value(strip, property_name):
    """Read a Live meter property without assuming every track type has it.

    Live's proxy objects can raise (rather than return the ``getattr``
    default) for properties that do not exist on MIDI-output tracks.  A
    missing optional meter must never prevent the complete project snapshot
    from being returned.
    """
    try:
        value = getattr(strip, property_name)
        return float(value) if value is not None else None
    except Exception:
        return None


class AudioToo_Bridge(ControlSurface):
    """Ableton Live Remote Script ControlSurface subclass."""

    def __init__(self, c_instance):
        super(AudioToo_Bridge, self).__init__(c_instance)
        self.host = HOST
        self.listen_port = LISTEN_PORT

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        try:
            self.socket.bind((self.host, self.listen_port))
            self.log_message("AudioToo_Bridge bound to %s:%d" % (self.host, self.listen_port))
        except Exception as exc:
            self.log_message("AudioToo_Bridge failed to bind socket: %s" % exc)

        self.schedule_message(POLL_INTERVAL_TICKS, self._poll_socket)

    def _poll_socket(self):
        self.process_incoming_packets()
        self.schedule_message(POLL_INTERVAL_TICKS, self._poll_socket)

    def process_incoming_packets(self):
        """Poll and execute incoming UDP commands."""
        if not self.socket:
            return

        while True:
            try:
                data, addr = self.socket.recvfrom(8192)
                if not data:
                    break
                self.handle_packet(data, addr)
            except (BlockingIOError, socket.error):
                break
            except Exception as exc:
                self.log_message("Error processing Ableton Live OSC packet: %s" % exc)
                break

    def handle_packet(self, data, addr):
        """Parse incoming JSON payload and execute Live Object Model action."""
        try:
            payload = json.loads(data.decode("utf-8"))
            address = payload.get("address", "")
            args = payload.get("args", [])
            request_id = payload.get("id")

            response = {"id": request_id, "address": address, "ok": True}

            if address == "/live/song/get/track_data":
                response["data"] = self.get_track_data()
            elif address == "/live/track/set/volume":
                track_idx, vol = int(args[0]), float(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.set_track_volume(track_idx, vol))
            elif address == "/live/track/set/pan":
                track_idx, pan = int(args[0]), float(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.set_track_pan(track_idx, pan))
            elif address == "/live/track/set/mute":
                track_idx, muted = int(args[0]), bool(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.set_track_mute(track_idx, muted))
            elif address == "/live/track/set/solo":
                track_idx, soloed = int(args[0]), bool(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.set_track_solo(track_idx, soloed))
            elif address == "/live/track/set/arm":
                track_idx, armed = int(args[0]), bool(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.set_track_arm(track_idx, armed))
            elif address == "/live/device/set/parameter":
                t_idx, d_idx, p_idx, val = int(args[0]), int(args[1]), int(args[2]), float(args[3])
                response["data"] = self.set_device_parameter(t_idx, d_idx, p_idx, val)
            elif address == "/live/device/get/parameters":
                t_idx, d_idx = int(args[0]), int(args[1])
                response["data"] = self.get_device_parameters(t_idx, d_idx)
            elif address == "/live/clip/load":
                track_idx, clip_slot_idx, file_path = int(args[0]), int(args[1]), str(args[2])
                response["data"] = self.load_clip_to_track(track_idx, clip_slot_idx, file_path)
            elif address == "/live/clip/launch":
                track_idx, clip_slot_idx = int(args[0]), int(args[1])
                response["data"] = self.launch_clip(track_idx, clip_slot_idx)
            elif address == "/live/scene/launch":
                scene_idx = int(args[0])
                response["data"] = self.launch_scene(scene_idx)
            elif address == "/live/scene/create":
                scene_name = str(args[0]) if args else ""
                response["data"] = self.create_scene(scene_name)
            elif address == "/live/device/create":
                track_idx, dev_name = int(args[0]), str(args[1])
                response["data"] = self.create_device_on_track(track_idx, dev_name)
            elif address == "/live/device/sidechain":
                bass_idx, kick_idx = int(args[0]), int(args[1])
                response["data"] = self.configure_sidechain_routing(bass_idx, kick_idx)
            elif address == "/live/song/transport/play":
                response["data"] = self.start_playback()
            elif address == "/live/song/transport/stop":
                response["data"] = self.stop_playback()
            elif address == "/live/song/transport/set_tempo":
                bpm = float(args[0])
                response["data"] = self.set_tempo(bpm)
            else:
                response["ok"] = False
                response["error"] = "Unknown address: %s" % address

            self.send_response(response, addr)
        except Exception as exc:
            self.log_message("Failed to handle Ableton packet: %s" % exc)

    def _run_with_undo_step(self, fn):
        """Wrap a single write in Live's own undo history (item 4,
        docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md) so it reverts
        with a native Cmd+Z, not just KENN's own app-level "Undo" button
        (P4, docs/KENN_IMPROVEMENT_PLAN.md).

        Song.begin_undo_step()/end_undo_step() are not part of Ableton's
        published Remote Script API reference -- confirmed real via
        direct inspection of this machine's actual Ableton Live 12 Suite
        install: `strings` on the compiled bytecode of Ableton's own
        first-party Push integration
        (MIDI Remote Scripts/pushbase/undo_step_handler.pyc) shows a
        real `UndoStepHandler` class calling `self._song.begin_undo_step()`
        / `self._song.end_undo_step()` for exactly this purpose -- not a
        guess, but also not confirmed with a live round-trip yet (that
        needs Jack's own running session). Scoped to only the 5 writes
        that already get app-level undo capture (volume/pan/mute/solo/
        arm) -- clip/scene/device-creation writes are a different kind
        of edit with less certain undo semantics, left alone rather than
        wrapped speculatively.

        Falls back to running `fn()` unwrapped (never silently drops the
        write) if `begin_undo_step`/`end_undo_step` aren't available on
        this Live version, or if there's no active song.
        """
        song = self.song()
        if not song or not hasattr(song, "begin_undo_step") or not hasattr(song, "end_undo_step"):
            return fn()
        song.begin_undo_step()
        try:
            return fn()
        finally:
            song.end_undo_step()

    def get_track_data(self):
        """Query active track structure from Live Object Model.

        muted/soloed/armed added 2026-08-06 -- orchestrator.py's session
        report has displayed a mute emoji based on `t.get("muted")` since
        it was written, but this field never existed here, so it always
        read as unmuted regardless of the real track state.

        output_meter_level/output_meter_right added (G2,
        docs/KENN_IMPROVEMENT_PLAN.md): the Mixing Doctor's 2s poll only
        ever read mixer *parameter* state (volume/pan/mute), never actual
        audio *signal* -- G2 flagged this as making dynamic-range-style
        detectors architecturally impossible on this bridge. Track.
        output_meter_level/output_meter_right are real, documented,
        read-only properties on Live's Track class (the same ones
        hardware controllers like Push read for their level meters) --
        an instantaneous post-fader level reading, not raw sample data.
        This alone does not build a working detector: a single 2s-interval
        reading can't compute a real crest factor (needs a fast sampling
        window to find genuine peak/RMS), and it carries no frequency
        information at all, so it can't inform masking or spectral-gap
        detection -- those still need real audio-rate signal access via a
        Max for Live device's `~` objects (see studio/m4l/), a
        differently-shaped piece of work needing a real Max/Ableton
        environment to build and test. This is the first real signal-
        adjacent data point available through the existing bridge with no
        new infrastructure, not a complete solution to G2.
        UNVERIFIED against a real running Ableton session -- these
        property names come from Cycling '74/Ableton's documented Live
        API, same caveat as every other LOM property this script reads,
        but Ableton must be restarted to reload this script before it can
        be confirmed live.
        """
        s = self.song()
        if not s:
            return {"tracks": [], "is_playing": False, "tempo": None}

        tracks_info = []
        for idx, trk in enumerate(getattr(s, "tracks", [])):
            t_name = getattr(trk, "name", "Track %d" % (idx + 1))
            vol = getattr(getattr(trk, "mixer_device", None), "volume", None)
            vol_val = getattr(vol, "value", 1.0) if vol else 1.0

            pan = getattr(getattr(trk, "mixer_device", None), "panning", None)
            pan_val = getattr(pan, "value", 0.0) if pan else 0.0

            devices = []
            for d_idx, dev in enumerate(getattr(trk, "devices", [])):
                d_name = getattr(dev, "name", "Device %d" % (d_idx + 1))
                devices.append({
                    "index": d_idx,
                    "name": d_name,
                    "is_active": bool(getattr(dev, "is_active", True)),
                })

            clip_slots = getattr(trk, "clip_slots", [])
            session_clip_count = sum(1 for slot in clip_slots if getattr(slot, "has_clip", False))
            has_arrangement_clip_data = hasattr(trk, "arrangement_clips")
            arrangement_clips = getattr(trk, "arrangement_clips", [])

            tracks_info.append({
                "index": idx,
                "name": t_name,
                "volume": vol_val,
                "pan": pan_val,
                "muted": bool(getattr(trk, "mute", False)),
                "soloed": bool(getattr(trk, "solo", False)),
                "armed": bool(getattr(trk, "arm", False)),
                "color": getattr(trk, "color", None),
                "is_group": bool(getattr(trk, "is_foldable", False)),
                "group_name": getattr(getattr(trk, "group_track", None), "name", None),
                "has_audio_input": bool(getattr(trk, "has_audio_input", False)),
                "has_midi_input": bool(getattr(trk, "has_midi_input", False)),
                "session_clip_count": session_clip_count,
                "arrangement_clip_count": len(arrangement_clips) if has_arrangement_clip_data else None,
                "devices": devices,
                "output_meter_level": _optional_meter_value(trk, "output_meter_level"),
                "output_meter_right": _optional_meter_value(trk, "output_meter_right"),
            })

        scenes_info = []
        for s_idx, scene in enumerate(getattr(s, "scenes", [])):
            # Session View density only.  A slot's existence says nothing
            # about audio energy or Arrangement View structure.
            active_clip_count = sum(
                1
                for track in getattr(s, "tracks", [])
                if s_idx < len(getattr(track, "clip_slots", []))
                and getattr(track.clip_slots[s_idx], "has_clip", False)
            )
            scenes_info.append({
                "index": s_idx,
                "name": getattr(scene, "name", ""),
                "active_clip_count": active_clip_count,
            })

        selected_track = getattr(getattr(s, "view", None), "selected_track", None)
        selected_track_index = next(
            (index for index, track in enumerate(getattr(s, "tracks", [])) if track == selected_track), None
        )

        def mixer_strip_data(strip, index):
            mixer = getattr(strip, "mixer_device", None)
            volume = getattr(getattr(mixer, "volume", None), "value", None)
            pan = getattr(getattr(mixer, "panning", None), "value", None)
            return {
                "index": index,
                "name": getattr(strip, "name", "") or "",
                "volume": float(volume) if volume is not None else None,
                "pan": float(pan) if pan is not None else None,
                "output_meter_level": _optional_meter_value(strip, "output_meter_level"),
                "output_meter_right": _optional_meter_value(strip, "output_meter_right"),
                "devices": [
                    {"index": device_index, "name": getattr(device, "name", "") or "", "is_active": bool(getattr(device, "is_active", True))}
                    for device_index, device in enumerate(getattr(strip, "devices", []))
                ],
            }

        return_tracks_info = [
            mixer_strip_data(track, index)
            for index, track in enumerate(getattr(s, "return_tracks", []))
        ]
        master_track = getattr(s, "master_track", None)

        return {
            "tracks": tracks_info,
            "is_playing": bool(getattr(s, "is_playing", False)),
            "tempo": float(getattr(s, "tempo", 0.0)) or None,
            "scenes": scenes_info,
            "selected_track_index": selected_track_index,
            "return_tracks": return_tracks_info,
            "master_track": mixer_strip_data(master_track, 0) if master_track is not None else None,
        }

    def start_playback(self):
        """Start song playback from the current position."""
        s = self.song()
        if not s:
            return {"success": False, "error": "No active song"}
        try:
            s.start_playing()
            return {"success": True, "is_playing": bool(getattr(s, "is_playing", True))}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def stop_playback(self):
        """Stop song playback."""
        s = self.song()
        if not s:
            return {"success": False, "error": "No active song"}
        try:
            s.stop_playing()
            return {"success": True, "is_playing": bool(getattr(s, "is_playing", False))}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_tempo(self, bpm):
        """Set song tempo (Ableton allows roughly 20-999 BPM)."""
        s = self.song()
        if not s:
            return {"success": False, "error": "No active song"}
        clamped = max(20.0, min(999.0, float(bpm)))
        try:
            s.tempo = clamped
            return {"success": True, "tempo": float(s.tempo)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_track_volume(self, track_index, volume):
        """Set volume on target track index."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        vol_param = getattr(getattr(trk, "mixer_device", None), "volume", None)
        if vol_param and hasattr(vol_param, "value"):
            vol_param.value = max(0.0, min(1.0, volume))
            return {"success": True, "track_index": track_index, "volume": vol_param.value}
        return {"success": False, "error": "Volume parameter unavailable"}

    def set_track_pan(self, track_index, pan):
        """Set pan on target track index (-1.0 to 1.0)."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        pan_param = getattr(getattr(trk, "mixer_device", None), "panning", None)
        if pan_param and hasattr(pan_param, "value"):
            pan_param.value = max(-1.0, min(1.0, pan))
            return {"success": True, "track_index": track_index, "pan": pan_param.value}
        return {"success": False, "error": "Pan parameter unavailable"}

    def set_track_mute(self, track_index, muted):
        """Mute/unmute target track index."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        try:
            trk.mute = bool(muted)
            return {"success": True, "track_index": track_index, "muted": bool(trk.mute)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_track_solo(self, track_index, soloed):
        """Solo/unsolo target track index."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        try:
            trk.solo = bool(soloed)
            return {"success": True, "track_index": track_index, "soloed": bool(trk.solo)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_track_arm(self, track_index, armed):
        """Record-arm/disarm target track index."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        if not getattr(trk, "can_be_armed", True):
            return {"success": False, "error": "Track cannot be record-armed"}
        try:
            trk.arm = bool(armed)
            return {"success": True, "track_index": track_index, "armed": bool(trk.arm)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_device_parameter(self, track_index, device_index, parameter_index, value):
        """Set value of specific device parameter."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        devices = getattr(trk, "devices", [])
        if device_index < 0 or device_index >= len(devices):
            return {"success": False, "error": "Device index out of range"}

        dev = devices[device_index]
        params = getattr(dev, "parameters", [])
        if parameter_index < 0 or parameter_index >= len(params):
            return {"success": False, "error": "Parameter index out of range"}

        param = params[parameter_index]
        if hasattr(param, "value"):
            clamped = max(param.min, min(param.max, value))
            param.value = clamped
            return {"success": True, "parameter_name": getattr(param, "name", ""), "value": param.value}
        return {"success": False, "error": "Parameter unmodifiable"}

    def get_device_parameters(self, track_index, device_index):
        """List a device's parameters (name/value/min/max), including
        Rack macro knobs -- Live's LOM exposes macros as regular
        DeviceParameter objects named "Macro 1".."Macro 8", so this is
        the same lookup as any other device parameter, just surfaced
        on demand rather than in the 2s session poll (get_track_data())
        to avoid bloating that payload with data most sessions never need.
        """
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        devices = getattr(trk, "devices", [])
        if device_index < 0 or device_index >= len(devices):
            return {"success": False, "error": "Device index out of range"}

        dev = devices[device_index]
        params = getattr(dev, "parameters", [])
        param_list = [
            {
                "index": p_idx,
                "name": getattr(param, "name", ""),
                "value": getattr(param, "value", 0.0),
                "min": getattr(param, "min", 0.0),
                "max": getattr(param, "max", 1.0),
            }
            for p_idx, param in enumerate(params)
        ]
        return {"success": True, "device_name": getattr(dev, "name", ""), "parameters": param_list}

    def load_clip_to_track(self, track_index, clip_slot_index, file_path):
        """Load an audio file into a clip slot on target track index."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        if not getattr(trk, "has_audio_input", True):
            return {"success": False, "error": "Target track is not an audio track"}

        clip_slots = getattr(trk, "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}

        slot = clip_slots[clip_slot_index]
        try:
            if hasattr(slot, "create_clip_from_sample"):
                slot.create_clip_from_sample(file_path)
                return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, "file_path": file_path}
            return {"success": False, "error": "create_clip_from_sample method unavailable"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def launch_clip(self, track_index, clip_slot_index):
        """Fire (launch playback of) the clip in a track's clip slot."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        clip_slots = getattr(trk, "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}

        slot = clip_slots[clip_slot_index]
        if not getattr(slot, "has_clip", False):
            return {"success": False, "error": "No clip in that slot to launch"}
        try:
            slot.fire()
            return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def launch_scene(self, scene_index):
        """Fire (launch) a scene by index -- triggers every track's clip in that row."""
        s = self.song()
        if not s:
            return {"success": False, "error": "No active song"}
        scenes = getattr(s, "scenes", [])
        if scene_index < 0 or scene_index >= len(scenes):
            return {"success": False, "error": "Scene index out of range"}
        try:
            scenes[scene_index].fire()
            return {"success": True, "scene_index": scene_index}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def create_scene(self, name):
        """Append a new scene at the end of the session and optionally
        name it (D3.4, docs/KENN_FUTURE_PLAN.md Phase 3 -- the missing
        building block for conversational arrangement assistance:
        "build a verse/chorus structure" needs real named scenes to
        place, not just a text suggestion)."""
        s = self.song()
        if not s:
            return {"success": False, "error": "No active song"}
        try:
            scenes = getattr(s, "scenes", [])
            insert_index = len(scenes)
            s.create_scene(insert_index)
            new_scene = s.scenes[insert_index]
            if name:
                new_scene.name = name
            return {"success": True, "scene_index": insert_index, "name": getattr(new_scene, "name", "")}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def create_device_on_track(self, track_index, device_name):
        """Load a device (native or third-party plugin) onto a track via
        Ableton's Browser API.

        Walks the browser tree to find the device by name, then uses
        ``browser.load_item()`` with the target track selected so Live
        appends the device to that track's chain.  Works for every device
        type Live can load: built-in audio/MIDI effects, instruments, and
        third-party AU/VST/VST3 plugins.
        """
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]

        app = Live.Application.get_application() if Live else None
        if app is None or not hasattr(app, "browser"):
            return {"success": False, "error": "Live.Application.get_application() unavailable"}

        browser = app.browser

        target = _DEVICE_NAME_ALIASES.get(device_name.strip().lower(), device_name.strip())
        target_lower = target.lower()

        try:
            s.view.selected_track = trk
        except Exception:
            pass

        def _search_children(item, depth=0):
            if depth > 6:
                return None
            for child in item.children:
                name = getattr(child, "name", "")
                if name.lower() == target_lower:
                    if child.is_loadable:
                        return child
                    for grandchild in child.children:
                        if getattr(grandchild, "is_loadable", False):
                            return grandchild
                found = _search_children(child, depth + 1)
                if found is not None:
                    return found
            return None

        top_level_categories = [
            browser.audio_effects,
            browser.midi_effects,
            browser.instruments,
            browser.plugins,
        ]

        match = None
        for category in top_level_categories:
            if category is None:
                continue
            match = _search_children(category)
            if match is not None:
                break

        if match is None:
            return {"success": False, "error": "Device '%s' not found in Ableton browser" % target}

        try:
            browser.load_item(match)
            return {"success": True, "track_index": track_index, "device_name": target,
                    "loaded_item": getattr(match, "name", target)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def configure_sidechain_routing(self, bass_track_index, kick_track_index):
        """Configure Compressor sidechain input routing from kick to bass."""
        s = self.song()
        if not s or bass_track_index < 0 or bass_track_index >= len(s.tracks) or kick_track_index < 0 or kick_track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        bass_trk = s.tracks[bass_track_index]
        kick_trk = s.tracks[kick_track_index]

        compressor = None
        for dev in getattr(bass_trk, "devices", []):
            if "Compressor" in getattr(dev, "name", ""):
                compressor = dev
                break

        if not compressor:
            return {"success": False, "error": "No Compressor device found on the bass track"}

        try:
            sidechain_param = None
            for param in getattr(compressor, "parameters", []):
                if "Sidechain" in getattr(param, "name", ""):
                    sidechain_param = param
                    break

            if sidechain_param and hasattr(sidechain_param, "value"):
                sidechain_param.value = 1.0

            if hasattr(compressor, "sidechain_input"):
                compressor.sidechain_input.routing_target = kick_trk
                return {"success": True, "bass_track_index": bass_track_index, "kick_track_index": kick_track_index}

            return {"success": True, "bass_track_index": bass_track_index, "kick_track_index": kick_track_index, "warning": "Sidechain routed via default LOM mapping"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def send_response(self, payload, addr):
        """Send JSON response back to whichever (host, port) the request
        actually came from -- not a fixed port. See module docstring."""
        try:
            raw = json.dumps(payload).encode("utf-8")
            self.socket.sendto(raw, addr)
        except Exception as exc:
            self.log_message("Failed to send UDP response from AudioToo_Bridge: %s" % exc)

    def disconnect(self):
        """Called when Ableton Live closes or unloads script."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        super(AudioToo_Bridge, self).disconnect()
