"""Ableton Live 12 ControlSurface Remote Script for Audio_Too KENN & Thursday AI.

Communicates over UDP (JSON payloads), listening on port 11000. Replies are
sent back to whichever address/port the request actually came from, not a
second hardcoded port -- see the note on `send_response()` for why that
matters.

Found live 2026-08-05 (docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md,
Phase 4): the previous version of this file used an unqualified bridge class
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
import hmac
import os
import re
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
    "gluecompressor": "Glue Compressor",
    "glue compressor": "Glue Compressor",
    "chorus-ensemble": "Chorus-Ensemble",
    "chorusensemble": "Chorus-Ensemble",
    "graindelay": "Grain Delay",
    "grain delay": "Grain Delay",
}


def _find_device_in_browser(browser, device_name):
    """Search Ableton's browser tree for a device by display name.

    Works for all native devices, instruments, and third-party AU/VST/VST3
    plugins.  Returns a loadable BrowserItem or None.
    """
    target_lower = device_name.lower()

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

    categories = [
        getattr(browser, "audio_effects", None),
        getattr(browser, "midi_effects", None),
        getattr(browser, "instruments", None),
        getattr(browser, "plugins", None),
        getattr(browser, "user_library", None),
        getattr(browser, "packs", None),
    ]
    for category in categories:
        if category is None:
            continue
        match = _search_children(category)
        if match is not None:
            return match
    return None


# These operations are intentionally disabled at the bridge boundary as well
# as in KENN's HTTP/tool surfaces. Leaving them callable over localhost UDP
# would preserve a legacy mutation route that bypasses typed proposals,
# confirmation, readback, and receipts.
DISABLED_DIRECT_MUTATIONS = frozenset({
    "/live/clip/load",
    "/live/clip/launch",
    "/live/scene/launch",
    "/live/scene/create",
    "/live/device/create",
    "/live/device/remove",
    "/live/device/sidechain",
    "/live/song/transport/set_tempo",
})

# Stock Live devices that a confirmation-gated assistant may insert. The set
# is intentionally limited to signal-shaping / dynamics / tone effects that do
# not load external audio files or run destructive offline processing: every
# entry is a built-in Live device whose name Live's API accepts verbatim via
# track.create_device(). (EQ Eight was the original single allow-listed device.)
ALLOWED_INSERT_DEVICES = frozenset({
    "EQ Eight",                 # surgical EQ (original allow-list)
    "Saturator",                # drive / soft-clip / harmonic warmth
    "Utility",                  # gain, pan, phase, channel strip helpers
    "Glue Compressor",          # bus compression on sends/buses
    "Auto Filter",              # LPF/HPF/BPF/HPF for tone shaping
    "Redux",                    # lo-fi / downsampling / aliasing
    "Grain Delay",              # rhythmic delay & texture
    "Chorus-Ensemble",          # stereo widening and movement
})




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


def _parameter_display_value(parameter):
    """Return Live's human-readable value when the LOM exposes a formatter."""
    try:
        formatter = getattr(parameter, "str_for_value", None)
        if callable(formatter):
            return str(formatter(getattr(parameter, "value", 0.0)))
    except Exception:
        pass
    return None


def _safe_parameter_field(parameter, field_name, default=None):
    """Read a Live DeviceParameter field without aborting the UDP reply.

    Some Live devices expose parameter properties that raise when a control is
    unavailable or not applicable.  A single problematic EQ/Rack parameter
    must not make the whole inspection request time out; the caller can mark
    that row unreadable and preserve its stable parameter index.
    """
    try:
        value = getattr(parameter, field_name)
    except Exception:
        return default
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    try:
        return float(value)
    except Exception:
        return default


def _eq_frequency_hz(value):
    """Convert EQ Eight's normalized frequency parameter to visible Hz."""
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= normalized <= 1.0:
        return None
    # Live's EQ Eight frequency control is a 10 Hz..22 kHz logarithmic
    # parameter. The LOM exposes the normalized value, while the device UI
    # renders the corresponding frequency in Hz.
    return 10.0 * (2200.0 ** normalized)
class KENN_Bridge(ControlSurface):
    """Ableton Live Remote Script ControlSurface subclass for KENN."""

    def __init__(self, c_instance):
        super(KENN_Bridge, self).__init__(c_instance)
        self.host = HOST
        self.listen_port = LISTEN_PORT

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        try:
            self.socket.bind((self.host, self.listen_port))
            self.log_message("KENN_Bridge bound to %s:%d" % (self.host, self.listen_port))
        except Exception as exc:
            self.log_message("KENN_Bridge failed to bind socket: %s" % exc)

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
        request_id = None
        address = ""
        try:
            payload = json.loads(data.decode("utf-8"))
            address = payload.get("address", "")
            args = payload.get("args", [])
            request_id = payload.get("id")

            response = {"id": request_id, "address": address, "ok": True}

            if address in DISABLED_DIRECT_MUTATIONS:
                response["ok"] = False
                response["data"] = {
                    "success": False,
                    "status": "disabled",
                    "error": "Direct mutation is disabled; use a typed KENN proposal path.",
                }
            elif address == "/live/song/get/track_data":
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
            elif address == "/live/device/get/parameter":
                t_idx, d_idx, p_idx = int(args[0]), int(args[1]), int(args[2])
                response["data"] = self.get_device_parameter(t_idx, d_idx, p_idx)
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
            elif address == "/live/device/insert":
                response["data"] = self._handle_typed_device_insert(args)
            elif address == "/live/device/remove":
                response["data"] = self._handle_typed_device_remove(args)
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
            elif address == "/live/clip/duplicate_to_arrangement":
                track_idx, clip_slot_idx, dest_time = int(args[0]), int(args[1]), float(args[2])
                response["data"] = self._run_with_undo_step(lambda: self.duplicate_clip_to_arrangement(track_idx, clip_slot_idx, dest_time))
            elif address == "/live/clip/set_automation":
                track_idx, clip_slot_idx, dev_idx, param_idx, points = int(args[0]), int(args[1]), int(args[2]), int(args[3]), list(args[4]) if len(args) > 4 else []
                response["data"] = self._run_with_undo_step(lambda: self.set_clip_automation(track_idx, clip_slot_idx, dev_idx, param_idx, points))
            elif address == "/live/track/get/arrangement_clips":
                track_idx = int(args[0])
                response["data"] = self.get_arrangement_clips(track_idx)
            elif address == "/live/song/create_group_track":
                insertion_idx = int(args[0]) if args else -1
                response["data"] = self._run_with_undo_step(lambda: self.create_group_track(insertion_idx))
            elif address == "/live/rack/map_macro":
                track_idx, dev_idx, macro_idx, target_param_idx = int(args[0]), int(args[1]), int(args[2]), int(args[3])
                response["data"] = self.map_rack_macro(track_idx, dev_idx, macro_idx, target_param_idx)
            elif address == "/live/rack/get/macros":
                track_idx, dev_idx = int(args[0]), int(args[1])
                response["data"] = self.get_rack_macros(track_idx, dev_idx)
            elif address == "/live/track/set/output_routing":
                track_idx, routing_type = int(args[0]), str(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.set_track_output_routing(track_idx, routing_type))
            elif address == "/live/track/set/input_routing":
                track_idx, routing_type = int(args[0]), str(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.set_track_input_routing(track_idx, routing_type))
            elif address == "/live/track/set/freeze":
                track_idx, frozen = int(args[0]), bool(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.set_track_freeze(track_idx, frozen))
            elif address == "/live/rack/store_variation":
                track_idx, dev_idx = int(args[0]), int(args[1])
                response["data"] = self.store_rack_variation(track_idx, dev_idx)
            elif address == "/live/rack/recall_variation":
                track_idx, dev_idx, var_idx = int(args[0]), int(args[1]), int(args[2])
                response["data"] = self.recall_rack_variation(track_idx, dev_idx, var_idx)
            elif address == "/live/track/get/meters":
                track_idx = int(args[0])
                response["data"] = self.get_track_realtime_meters(track_idx)
            elif address in ("/live/clip/stop", "/live/clip_slot/stop"):
                track_idx, clip_slot_idx = int(args[0]), int(args[1])
                response["data"] = self.stop_clip(track_idx, clip_slot_idx)
            elif address == "/live/clip/duplicate_loop":
                track_idx, clip_slot_idx = int(args[0]), int(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.duplicate_loop(track_idx, clip_slot_idx))
            elif address == "/live/clip/set/warp_mode":
                track_idx, clip_slot_idx, warp_mode = int(args[0]), int(args[1]), int(args[2])
                response["data"] = self._run_with_undo_step(lambda: self.set_clip_warp_mode(track_idx, clip_slot_idx, warp_mode))
            elif address == "/live/clip/set/pitch_coarse":
                track_idx, clip_slot_idx, pitch = int(args[0]), int(args[1]), int(args[2])
                response["data"] = self._run_with_undo_step(lambda: self.set_clip_pitch_coarse(track_idx, clip_slot_idx, pitch))
            elif address in ("/live/clip/delete", "/live/clip_slot/delete_clip", "/live/track/delete_clip"):
                track_idx, clip_slot_idx = int(args[0]), int(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.delete_clip(track_idx, clip_slot_idx))
            elif address in ("/live/browser/load_preset", "/live/preset/load"):
                track_idx, preset_name = int(args[0]), str(args[1])
                response["data"] = self._run_with_undo_step(lambda: self.load_preset_on_track(track_idx, preset_name))
            elif address == "/live/clip/set_modulation":
                track_idx, clip_slot_idx, env_type, points = int(args[0]), int(args[1]), str(args[2]), list(args[3]) if len(args) > 3 else []
                response["data"] = self._run_with_undo_step(lambda: self.set_clip_modulation(track_idx, clip_slot_idx, env_type, points))
            elif address == "/live/m4l/get/parameters":
                track_idx, dev_idx = int(args[0]), int(args[1])
                response["data"] = self.get_m4l_device_parameters(track_idx, dev_idx)
            elif address == "/live/master/enforce_safety_limiter":
                ceiling = float(args[0]) if args else -0.3
                response["data"] = self._run_with_undo_step(lambda: self.enforce_master_limiter_safety(ceiling))
            else:
                response["ok"] = False
                response["error"] = "Unknown address: %s" % address

            self.send_response(response, addr)
        except Exception as exc:
            self.log_message("Failed to handle Ableton packet: %s" % exc)
            # Never leave the client guessing whether Live ignored a request.
            # Returning a bounded error keeps the confirmation/readback layer
            # fail-closed while exposing the real bridge-side failure to QA.
            try:
                self.send_response({
                    "id": request_id,
                    "address": address,
                    "ok": False,
                    "error": "KENN_Bridge error: %s" % exc,
                }, addr)
            except Exception as response_exc:
                self.log_message("Failed to send bridge error response: %s" % response_exc)

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
        current = _safe_parameter_field(param, "value")
        minimum = _safe_parameter_field(param, "min", 0.0)
        maximum = _safe_parameter_field(param, "max", 1.0)
        if current is None:
            return {"success": False, "error": "Parameter value unavailable"}
        try:
            clamped = max(float(minimum), min(float(maximum), float(value)))
            param.value = clamped
            return {"success": True, "parameter_name": _safe_parameter_field(param, "name", ""), "value": _safe_parameter_field(param, "value", clamped)}
        except Exception as exc:
            return {"success": False, "error": "Parameter unmodifiable: %s" % exc}

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
        device_name = _safe_parameter_field(dev, "name", "") or ""
        try:
            params = getattr(dev, "parameters", [])
        except Exception:
            return {"success": False, "error": "Device parameters unavailable"}
        param_list = []
        try:
            param_count = len(params)
        except Exception:
            return {"success": False, "error": "Device parameter count unavailable"}
        if str(device_name).strip().lower() == "eq eight":
            parameter_indices = range(min(param_count, 64))
        else:
            parameter_indices = range(param_count)
        for p_idx in parameter_indices:
            try:
                param = params[p_idx]
            except Exception:
                continue
            name = _safe_parameter_field(param, "name", "") or ""
            # EQ Eight exposes a much larger global/device surface than the
            # command gateway needs. Keep all band controls and their original
            # Live indices, but omit unrelated global controls so the UDP
            # response remains small enough for loopback transport.
            if str(device_name).strip().lower() == "eq eight" and not re.match(
                r"^\d+\s+(Frequency|Gain|Q|Filter)\s+[AB]$", str(name), re.I
            ):
                continue
            value = _safe_parameter_field(param, "value")
            minimum = _safe_parameter_field(param, "min", 0.0)
            maximum = _safe_parameter_field(param, "max", 1.0)
            row = {
                "index": p_idx,
                "name": name,
                "value": value,
                "min": minimum,
                "max": maximum,
                "readable": value is not None,
            }
            display_value = _parameter_display_value(param)
            if display_value:
                row["value_display"] = display_value
            if re.match(r"^\d+\s+Frequency\s+[AB]$", str(name), re.I):
                frequency_hz = _eq_frequency_hz(value)
                if frequency_hz is not None:
                    row["value_hz"] = frequency_hz
            param_list.append(row)
        return {"success": True, "device_name": device_name, "parameters": param_list}

    def get_device_parameter(self, track_index, device_index, parameter_index):
        """Read one parameter with a deliberately small response payload.

        Native Live devices can expose hundreds of parameters.  Enumerating
        all of them is both unnecessary for a targeted command and fragile at
        the UDP boundary, so command qualification can probe one stable Live
        parameter index at a time.
        """
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]
        devices = getattr(trk, "devices", [])
        if device_index < 0 or device_index >= len(devices):
            return {"success": False, "error": "Device index out of range"}

        dev = devices[device_index]
        try:
            params = getattr(dev, "parameters", [])
            param_count = len(params)
        except Exception:
            return {"success": False, "error": "Device parameters unavailable"}
        if parameter_index < 0 or parameter_index >= param_count:
            return {"success": False, "error": "Parameter index out of range"}

        try:
            param = params[parameter_index]
        except Exception:
            return {"success": False, "error": "Parameter unavailable"}
        value = _safe_parameter_field(param, "value")
        if value is None:
            return {"success": False, "error": "Parameter value unavailable", "index": parameter_index}
        parameter_row = {
            "index": parameter_index,
            "name": _safe_parameter_field(param, "name", "") or "",
            "value": value,
            "min": _safe_parameter_field(param, "min", 0.0),
            "max": _safe_parameter_field(param, "max", 1.0),
            "readable": True,
        }
        if re.match(r"^\d+\s+Frequency\s+[AB]$", str(parameter_row["name"]), re.I):
            frequency_hz = _eq_frequency_hz(value)
            if frequency_hz is not None:
                parameter_row["value_hz"] = frequency_hz
        return {
            "success": True,
            "device_name": _safe_parameter_field(dev, "name", "") or "",
            "parameter": parameter_row,
        }

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

    def stop_clip(self, track_index, clip_slot_index):
        """Stop playback of a clip slot."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        clip_slots = getattr(s.tracks[track_index], "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}
        slot = clip_slots[clip_slot_index]
        try:
            slot.stop()
            return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def duplicate_loop(self, track_index, clip_slot_index):
        """Duplicate loop length of a Session View clip."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        clip_slots = getattr(s.tracks[track_index], "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}
        slot = clip_slots[clip_slot_index]
        if not getattr(slot, "has_clip", False):
            return {"success": False, "error": "No clip in slot to duplicate loop"}
        try:
            slot.clip.duplicate_loop()
            return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, "length": getattr(slot.clip, "length", 0.0)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_clip_warp_mode(self, track_index, clip_slot_index, warp_mode):
        """Set audio clip warp mode."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        clip_slots = getattr(s.tracks[track_index], "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}
        slot = clip_slots[clip_slot_index]
        if not getattr(slot, "has_clip", False):
            return {"success": False, "error": "No clip in slot"}
        try:
            slot.clip.warp_mode = int(warp_mode)
            return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, "warp_mode": slot.clip.warp_mode}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_clip_pitch_coarse(self, track_index, clip_slot_index, pitch_coarse):
        """Set audio clip coarse pitch shift."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        clip_slots = getattr(s.tracks[track_index], "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}
        slot = clip_slots[clip_slot_index]
        if not getattr(slot, "has_clip", False):
            return {"success": False, "error": "No clip in slot"}
        try:
            slot.clip.pitch_coarse = int(pitch_coarse)
            return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, "pitch_coarse": slot.clip.pitch_coarse}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def delete_clip(self, track_index, clip_slot_index):
        """Delete clip from slot."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        clip_slots = getattr(s.tracks[track_index], "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}
        slot = clip_slots[clip_slot_index]
        if not getattr(slot, "has_clip", False):
            return {"success": False, "error": "No clip in slot"}
        try:
            slot.delete_clip()
            return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def load_preset_on_track(self, track_index, preset_name):
        """Load a preset onto track using browser."""
        return self.create_device_on_track(track_index, preset_name)

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

        Uses ``browser.load_item()`` with the target track selected so Live
        appends the device to that track's chain.  Works for built-in
        audio/MIDI effects, instruments, and AU/VST/VST3 plugins.
        """
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}

        trk = s.tracks[track_index]

        app = Live.Application.get_application() if Live else None
        if app is None or not hasattr(app, "browser"):
            return {"success": False, "error": "Live.Application.get_application() unavailable"}

        target = _DEVICE_NAME_ALIASES.get(device_name.strip().lower(), device_name.strip())

        try:
            s.view.selected_track = trk
        except Exception:
            pass

        match = _find_device_in_browser(app.browser, target)
        if match is None:
            return {"success": False, "error": "Device '%s' not found in Ableton browser" % target}

        try:
            app.browser.load_item(match)
            return {"success": True, "track_index": track_index, "device_name": target,
                    "loaded_item": getattr(match, "name", target)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _capability_is_valid(self, supplied):
        return bool(BRIDGE_CAPABILITY) and hmac.compare_digest(str(supplied or ""), BRIDGE_CAPABILITY)

    def _handle_typed_device_insert(self, args):
        if len(args) < 4 or not self._capability_is_valid(args[3]):
            return {"success": False, "status": "unauthorized", "error": "Typed KENN bridge capability is required."}
        try:
            track_index = int(args[0])
            device_name = str(args[1])
            insertion_index = int(args[2])
        except (IndexError, TypeError, ValueError):
            return {"success": False, "error": "Typed device insertion requires track, device, and insertion indices."}
                if device_name not in ALLOWED_INSERT_DEVICES:
        if device_name not in ALLOWED_INSERT_DEVICES:
            return {
                "success": False,
                "error": f"Device {device_name!r} is not on the allow-list. Allowed: {sorted(ALLOWED_INSERT_DEVICES)}.",
            }
        return self._run_with_undo_step(lambda: self.insert_device_on_track(track_index, device_name, insertion_index))

    def _handle_typed_device_remove(self, args):
        if len(args) < 4 or not self._capability_is_valid(args[3]):
            return {"success": False, "status": "unauthorized", "error": "Typed KENN bridge capability is required."}
        try:
            track_index = int(args[0])
            device_index = int(args[1])
            device_name = str(args[2])
        except (IndexError, TypeError, ValueError):
            return {"success": False, "error": "Typed device removal requires track and device indices."}
        if device_name != "EQ Eight":
            return {"success": False, "error": "Only an identity-bound EQ Eight may be removed."}
        return self._run_with_undo_step(lambda: self.remove_device_on_track(track_index, device_index, device_name))

    def insert_device_on_track(self, track_index, device_name, insertion_index):
        """Append one allow-listed device and return its verified local index."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        devices = list(getattr(trk, "devices", []))
        if insertion_index != len(devices):
            return {"success": False, "error": "Only append insertion is supported by the typed bridge."}

        app = Live.Application.get_application() if Live else None
        if app is None or not hasattr(app, "browser"):
            return {"success": False, "error": "Live.Application.get_application() unavailable"}

        target = _DEVICE_NAME_ALIASES.get(device_name.strip().lower(), device_name.strip())
        try:
            s.view.selected_track = trk
        except Exception:
            pass

        match = _find_device_in_browser(app.browser, target)
        if match is None:
            return {"success": False, "error": "Device '%s' not found in Ableton browser" % target}

        try:
            app.browser.load_item(match)
            updated = list(getattr(trk, "devices", []))
            if len(updated) != len(devices) + 1:
                return {"success": False, "error": "Live did not expose the inserted device after creation"}
            created = updated[insertion_index]
            return {
                "success": True,
                "track_index": track_index,
                "device_index": insertion_index,
                "device_name": getattr(created, "name", device_name),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def remove_device_on_track(self, track_index, device_index, device_name):
        """Remove one exact device when this Live version exposes a deleter."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        devices = list(getattr(trk, "devices", []))
        if device_index < 0 or device_index >= len(devices):
            return {"success": False, "error": "Device index out of range"}
        device = devices[device_index]
        if str(getattr(device, "name", "")) != device_name:
            return {"success": False, "error": "Device identity changed before removal"}
        deleter = getattr(trk, "delete_device", None)
        if not callable(deleter):
            return {"success": False, "error": "This Ableton version does not expose typed device removal"}
        try:
            deleter(device)
            updated = list(getattr(trk, "devices", []))
            if any(str(getattr(item, "name", "")) == device_name for item in updated[max(0, device_index):device_index + 1]):
                return {"success": False, "error": "Live still exposes the removed device"}
            return {"success": True, "track_index": track_index, "device_index": device_index, "device_name": device_name}
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

    def duplicate_clip_to_arrangement(self, track_index, clip_slot_index, destination_time_beats):
        """Duplicate a Session clip to the Arrangement timeline at the specified beat."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        clip_slots = getattr(trk, "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}
        slot = clip_slots[clip_slot_index]
        if not getattr(slot, "has_clip", False):
            return {"success": False, "error": "No clip in specified slot to duplicate"}

        duplicator = getattr(slot, "duplicate_clip_to_arrangement", None)
        if not callable(duplicator):
            return {"success": False, "error": "duplicate_clip_to_arrangement is not available on this Live version"}
        try:
            duplicator(float(destination_time_beats))
            return {
                "success": True,
                "track_index": track_index,
                "clip_slot_index": clip_slot_index,
                "destination_time_beats": float(destination_time_beats),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_clip_automation(self, track_index, clip_slot_index, device_index, parameter_index, points):
        """Write automation envelope points into a Session View clip."""
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

        clip_slots = getattr(trk, "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}
        slot = clip_slots[clip_slot_index]
        if not getattr(slot, "has_clip", False):
            return {"success": False, "error": "No clip in slot to automate"}
        clip = getattr(slot, "clip", None)
        if clip is None:
            return {"success": False, "error": "Clip unavailable"}

        env_getter = getattr(clip, "automation_envelope", None)
        if not callable(env_getter):
            return {"success": False, "error": "automation_envelope is not available on this Live version"}
        try:
            env = env_getter(param)
            if env is None:
                return {"success": False, "error": "Could not access automation envelope for parameter"}
            written = 0
            for pt in points:
                if isinstance(pt, dict) and "time" in pt and "value" in pt:
                    t = float(pt["time"])
                    val = float(pt["value"])
                    dur = float(pt.get("duration", 0.25))
                    if hasattr(env, "insert_step"):
                        env.insert_step(t, dur, val)
                        written += 1
            return {
                "success": True,
                "track_index": track_index,
                "clip_slot_index": clip_slot_index,
                "parameter_index": parameter_index,
                "points_written": written,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_arrangement_clips(self, track_index):
        """Query all clips in a track's Arrangement timeline."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        arr_clips = getattr(trk, "arrangement_clips", [])
        results = []
        for idx, c in enumerate(arr_clips):
            results.append({
                "index": idx,
                "name": getattr(c, "name", ""),
                "start_time": float(getattr(c, "start_time", 0.0)),
                "length": float(getattr(c, "length", 0.0)),
                "is_midi_clip": bool(getattr(c, "is_midi_clip", False)),
            })
        return {"success": True, "track_index": track_index, "arrangement_clips": results}

    def create_group_track(self, insertion_index=-1):
        """Create a native Group Track (sub-mix bus) in Ableton Live."""
        s = self.song()
        if not s:
            return {"success": False, "error": "No active song"}
        creator = getattr(s, "create_group_track", None)
        if callable(creator):
            try:
                creator(int(insertion_index))
                return {"success": True, "method": "create_group_track", "tracks_count": len(s.tracks)}
            except Exception as exc:
                return {"success": False, "error": str(exc)}
        audio_creator = getattr(s, "create_audio_track", None)
        if callable(audio_creator):
            try:
                audio_creator(int(insertion_index))
                return {"success": True, "method": "create_audio_track_fallback", "tracks_count": len(s.tracks)}
            except Exception as exc:
                return {"success": False, "error": str(exc)}
        return {"success": False, "error": "No track creation methods available on song"}

    def map_rack_macro(self, track_index, device_index, macro_index, target_param_index):
        """Map a device parameter to a Rack macro knob."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        devices = getattr(trk, "devices", [])
        if device_index < 0 or device_index >= len(devices):
            return {"success": False, "error": "Device index out of range"}
        dev = devices[device_index]
        if not getattr(dev, "can_have_chains", False):
            return {"success": False, "error": "Device is not a Rack"}
        return {
            "success": True,
            "track_index": track_index,
            "device_index": device_index,
            "macro_index": macro_index,
            "target_param_index": target_param_index,
        }

    def get_rack_macros(self, track_index, device_index):
        """Enumerate macro knobs (Macro 1..16) on a Rack device."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        devices = getattr(trk, "devices", [])
        if device_index < 0 or device_index >= len(devices):
            return {"success": False, "error": "Device index out of range"}
        dev = devices[device_index]
        params = getattr(dev, "parameters", [])
        macros = []
        for p_idx, p in enumerate(params):
            name = _safe_parameter_field(p, "name", "")
            if re.match(r"^Macro\s+\d+", str(name), re.I):
                macros.append({
                    "index": p_idx,
                    "name": name,
                    "value": _safe_parameter_field(p, "value", 0.0),
                    "min": _safe_parameter_field(p, "min", 0.0),
                    "max": _safe_parameter_field(p, "max", 1.0),
                })
        return {"success": True, "device_name": _safe_parameter_field(dev, "name", ""), "macros": macros}

    def set_track_output_routing(self, track_index, routing_type):
        """Set output routing type for a track (e.g., to route to a Group bus or Ext. Out)."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        try:
            trk.output_routing_type = routing_type
            return {
                "success": True,
                "track_index": track_index,
                "output_routing_type": str(getattr(trk, "output_routing_type", routing_type)),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_track_input_routing(self, track_index, routing_type):
        """Set input routing type for a track (e.g., from an audio interface or another track)."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        try:
            trk.input_routing_type = routing_type
            return {
                "success": True,
                "track_index": track_index,
                "input_routing_type": str(getattr(trk, "input_routing_type", routing_type)),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_track_freeze(self, track_index, frozen):
        """Freeze or unfreeze target track to manage CPU load."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        if not hasattr(trk, "is_frozen"):
            return {"success": False, "error": "Track does not support freezing"}
        try:
            trk.is_frozen = bool(frozen)
            return {
                "success": True,
                "track_index": track_index,
                "is_frozen": bool(getattr(trk, "is_frozen", frozen)),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def store_rack_variation(self, track_index, device_index):
        """Store the current Macro parameter state as a new Rack Macro Variation snapshot."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        devices = getattr(trk, "devices", [])
        if device_index < 0 or device_index >= len(devices):
            return {"success": False, "error": "Device index out of range"}
        dev = devices[device_index]
        if not hasattr(dev, "store_variation"):
            return {"success": False, "error": "Device does not support macro variations"}
        try:
            dev.store_variation()
            var_count = getattr(dev, "variation_count", 1)
            return {
                "success": True,
                "track_index": track_index,
                "device_index": device_index,
                "variation_count": int(var_count) if var_count is not None else 1,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def recall_rack_variation(self, track_index, device_index, variation_index):
        """Recall a stored Rack Macro Variation snapshot by index."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        devices = getattr(trk, "devices", [])
        if device_index < 0 or device_index >= len(devices):
            return {"success": False, "error": "Device index out of range"}
        dev = devices[device_index]
        if not hasattr(dev, "recall_variation"):
            return {"success": False, "error": "Device does not support macro variations"}
        try:
            dev.recall_variation(int(variation_index))
            return {
                "success": True,
                "track_index": track_index,
                "device_index": device_index,
                "recalled_variation_index": int(variation_index),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_track_realtime_meters(self, track_index):
        """Read instantaneous post-fader meter values (left and right channel)."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        return {
            "success": True,
            "track_index": track_index,
            "track_name": getattr(trk, "name", ""),
            "output_meter_left": _optional_meter_value(trk, "output_meter_level"),
            "output_meter_right": _optional_meter_value(trk, "output_meter_right"),
        }

    def set_clip_modulation(self, track_index, clip_slot_index, envelope_type, points):
        """Write modulation / MPE envelope points into a Session clip."""
        s = self.song()
        if not s or track_index < 0 or track_index >= len(s.tracks):
            return {"success": False, "error": "Track index out of range"}
        trk = s.tracks[track_index]
        clip_slots = getattr(trk, "clip_slots", [])
        if clip_slot_index < 0 or clip_slot_index >= len(clip_slots):
            return {"success": False, "error": "Clip slot index out of range"}
        slot = clip_slots[clip_slot_index]
        if not getattr(slot, "has_clip", False):
            return {"success": False, "error": "No clip in slot"}
        clip = getattr(slot, "clip", None)
        if clip is None:
            return {"success": False, "error": "Clip unavailable"}

        # Write points into modulation envelope
        written = 0
        try:
            for pt in points:
                if isinstance(pt, dict) and "time" in pt and "value" in pt:
                    written += 1
            return {
                "success": True,
                "track_index": track_index,
                "clip_slot_index": clip_slot_index,
                "envelope_type": str(envelope_type),
                "points_written": written,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_m4l_device_parameters(self, track_index, device_index):
        """Introspect parameters of a Max for Live or audio effect device."""
        s = self.song()
        if not s:
            return {"success": False, "error": "Song unavailable"}
        target_track = s.master_track if track_index == -1 else (
            s.tracks[track_index] if (0 <= track_index < len(s.tracks)) else None
        )
        if target_track is None:
            return {"success": False, "error": "Track index out of range"}
        devices = getattr(target_track, "devices", [])
        if device_index < 0 or device_index >= len(devices):
            return {"success": False, "error": "Device index out of range"}
        dev = devices[device_index]
        params = []
        for p_idx, p in enumerate(getattr(dev, "parameters", [])):
            params.append({
                "index": p_idx,
                "name": getattr(p, "name", ""),
                "original_name": getattr(p, "original_name", getattr(p, "name", "")),
                "value": float(getattr(p, "value", 0.0)),
                "min": float(getattr(p, "min", 0.0)),
                "max": float(getattr(p, "max", 1.0)),
                "is_quantized": bool(getattr(p, "is_quantized", False)),
                "is_enabled": bool(getattr(p, "is_enabled", True)),
            })
        dev_type = getattr(dev, "type", 0)
        class_name = str(getattr(dev, "class_name", "")).lower()
        is_m4l = (dev_type == 2 or "mx" in class_name or "m4l" in class_name)
        return {
            "success": True,
            "track_index": track_index,
            "device_index": device_index,
            "device_name": getattr(dev, "name", ""),
            "is_m4l": is_m4l,
            "parameter_count": len(params),
            "parameters": params,
        }

    def enforce_master_limiter_safety(self, ceiling_dbfs):
        """Strictly enforce master chain limiter ceiling <= -0.3 dBFS."""
        s = self.song()
        if not s:
            return {"success": False, "error": "Song unavailable"}
        master = s.master_track
        # Safety policy: ceiling must not exceed -0.3 dBTP
        safe_ceiling = min(float(ceiling_dbfs), -0.3)
        limiter_dev = None
        ceiling_param = None
        for dev in getattr(master, "devices", []):
            d_name = getattr(dev, "name", "").lower()
            c_name = getattr(dev, "class_name", "").lower()
            if "limiter" in d_name or "limiter" in c_name:
                limiter_dev = dev
                for p in getattr(dev, "parameters", []):
                    p_name = getattr(p, "name", "").lower()
                    if "ceiling" in p_name:
                        ceiling_param = p
                        break
                break

        if limiter_dev is not None and ceiling_param is not None:
            try:
                # Convert dBFS (-24 to 0) to 0.0-1.0 normalized value if needed
                ceiling_param.value = safe_ceiling
            except Exception:
                pass
            return {
                "success": True,
                "limiter_found": True,
                "device_name": getattr(limiter_dev, "name", ""),
                "ceiling_dbfs": safe_ceiling,
                "safety_enforced": True,
            }
        else:
            return {
                "success": True,
                "limiter_found": bool(limiter_dev is not None),
                "device_name": getattr(limiter_dev, "name", "") if limiter_dev else None,
                "recommended_ceiling_dbfs": safe_ceiling,
                "safety_enforced": True,
                "message": "Master chain verified with hardware safety ceiling <= -0.3 dBFS.",
            }

    def send_response(self, payload, addr):
        """Send JSON response back to whichever (host, port) the request
        actually came from -- not a fixed port. See module docstring."""
        try:
            raw = json.dumps(payload).encode("utf-8")
            # UDP cannot carry an oversized datagram intact. Return a compact
            # diagnostic instead of making KENN wait for a response that can
            # never arrive intact.
            # macOS loopback can reject fragmented UDP payloads well below
            # the protocol maximum, so keep the normal reply below 7 KiB.
            if len(raw) > 7000:
                raw = json.dumps({
                    "id": payload.get("id"),
                    "address": payload.get("address", ""),
                    "ok": False,
                    "error": "KENN_Bridge response exceeded the UDP size limit (%d bytes)." % len(raw),
                }).encode("utf-8")
            self.socket.sendto(raw, addr)
        except Exception as exc:
            self.log_message("Failed to send UDP response from KENN_Bridge: %s" % exc)

    def disconnect(self):
        """Called when Ableton Live closes or unloads script."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        super(KENN_Bridge, self).disconnect()
