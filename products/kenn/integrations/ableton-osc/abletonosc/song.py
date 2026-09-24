import os
import sys
import tempfile
import Live
import json
from functools import partial
from typing import Tuple, Any

from .handler import AbletonOSCHandler

class SongHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "song"

    def init_api(self):
        #--------------------------------------------------------------------------------
        # Callbacks for Song: methods
        #--------------------------------------------------------------------------------
        for method in [
            "capture_and_insert_scene",
            "capture_midi",
            "continue_playing",
            "create_audio_track",
            "create_midi_track",
            "create_return_track",
            "create_scene",
            "delete_return_track",
            "delete_scene",
            "delete_track",
            "duplicate_scene",
            "duplicate_track",
            "force_link_beat_time",
            "jump_by",
            "jump_to_prev_cue",
            "jump_to_next_cue",
            "redo",
            "re_enable_automation",
            "set_or_delete_cue",
            "start_playing",
            "stop_all_clips",
            "stop_playing",
            "tap_tempo",
            "trigger_session_record",
            "undo"
        ]:
            callback = partial(self._call_method, self.song, method)
            self.osc_server.add_handler("/live/song/%s" % method, callback)

        #--------------------------------------------------------------------------------
        # Callbacks for Song: properties (read/write)
        #--------------------------------------------------------------------------------
        properties_rw = [
            "arrangement_overdub",
            "back_to_arranger",
            "clip_trigger_quantization",
            "current_song_time",
            "groove_amount",
            "is_ableton_link_enabled",
            "loop",
            "loop_length",
            "loop_start",
            "metronome",
            "midi_recording_quantization",
            "nudge_down",
            "nudge_up",
            "punch_in",
            "punch_out",
            "record_mode",
            "root_note",
            "scale_name",
            "session_record",
            "signature_denominator",
            "signature_numerator",
            "tempo"
        ]

        #--------------------------------------------------------------------------------
        # Callbacks for Song: properties (read-only)
        #--------------------------------------------------------------------------------
        properties_r = [
            "can_redo",
            "can_undo",
            "is_playing",
            "song_length",
            "session_record_status"
        ]

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/song/get/%s" % prop, partial(self._get_property, self.song, prop))
            self.osc_server.add_handler("/live/song/start_listen/%s" % prop, partial(self._start_listen, self.song, prop))
            self.osc_server.add_handler("/live/song/stop_listen/%s" % prop, partial(self._stop_listen, self.song, prop))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/song/set/%s" % prop, partial(self._set_property, self.song, prop))

        #--------------------------------------------------------------------------------
        # Callbacks for Song: Track properties
        #--------------------------------------------------------------------------------
        self.osc_server.add_handler("/live/song/get/num_tracks", lambda _: (len(self.song.tracks),))

        def song_get_track_names(params):
            if len(params) == 0:
                track_index_min, track_index_max = 0, len(self.song.tracks)
            else:
                track_index_min, track_index_max = params
                if track_index_max == -1:
                    track_index_max = len(self.song.tracks)
            return tuple(self.song.tracks[index].name for index in range(track_index_min, track_index_max))
        self.osc_server.add_handler("/live/song/get/track_names", song_get_track_names)

        #--------------------------------------------------------------------------------
        # Return-track enumeration (read-only). Return tracks are a
        # separate Live collection (`song.return_tracks`) from regular
        # tracks (`song.tracks`); create_return_track/delete_return_track
        # already existed above, but nothing previously let a caller find
        # out what a return track actually is (name, device chain) --
        # this closes exactly that gap, without adding any return-track
        # mutation beyond what already existed.
        #--------------------------------------------------------------------------------
        self.osc_server.add_handler("/live/song/get/num_return_tracks", lambda _: (len(self.song.return_tracks),))

        def song_get_return_track_names(params):
            if len(params) == 0:
                track_index_min, track_index_max = 0, len(self.song.return_tracks)
            else:
                track_index_min, track_index_max = params
                if track_index_max == -1:
                    track_index_max = len(self.song.return_tracks)
            return tuple(self.song.return_tracks[index].name for index in range(track_index_min, track_index_max))
        self.osc_server.add_handler("/live/song/get/return_track_names", song_get_return_track_names)

        def song_get_return_track_devices(params):
            return_track_index, = params
            track = self.song.return_tracks[int(return_track_index)]
            return tuple([int(return_track_index)] + [device.name for device in track.devices])
        self.osc_server.add_handler("/live/song/get/return_track_devices", song_get_return_track_devices)

        #--------------------------------------------------------------------------------
        # KENN world-model reads (read-only, JSON payloads). AbletonOSC addresses
        # only song.tracks by index, so returns, the master track, rack chains and
        # parameter automation state need their own reads.
        #--------------------------------------------------------------------------------
        def _kenn_track(kind, index):
            kind = str(kind)
            if kind == "track":
                return self.song.tracks[int(index)]
            if kind == "return":
                return self.song.return_tracks[int(index)]
            if kind == "master":
                return self.song.master_track
            raise ValueError("kind must be track, return, or master")

        def _kenn_device_node(device, depth):
            node = {"name": str(device.name), "class_name": str(getattr(device, "class_name", "")),
                    "can_have_chains": bool(getattr(device, "can_have_chains", False))}
            if node["can_have_chains"] and depth < 3:
                node["chains"] = [
                    {"name": str(chain.name),
                     "devices": [_kenn_device_node(inner, depth + 1) for inner in chain.devices]}
                    for chain in device.chains
                ]
            return node

        def kenn_get_bus_mixer(params):
            kind, index = str(params[0]), int(params[1]) if len(params) > 1 else -1
            try:
                track = _kenn_track(kind, index)
                mixer = track.mixer_device
                payload = {"kind": kind, "index": index, "name": str(track.name),
                           "volume": float(mixer.volume.value), "panning": float(mixer.panning.value),
                           "devices": [str(device.name) for device in track.devices]}
                if kind != "master":
                    payload.update({"mute": bool(track.mute), "solo": bool(track.solo)})
            except Exception as exc:
                payload = {"kind": kind, "index": index, "error": str(exc)}
            return (json.dumps(payload),)
        self.osc_server.add_handler("/live/kenn/get/bus_mixer", kenn_get_bus_mixer)

        def kenn_get_device_tree(params):
            kind, index = str(params[0]), int(params[1]) if len(params) > 1 else -1
            try:
                track = _kenn_track(kind, index)
                payload = {"kind": kind, "index": index,
                           "devices": [_kenn_device_node(device, 0) for device in track.devices]}
            except Exception as exc:
                payload = {"kind": kind, "index": index, "error": str(exc)}
            return (json.dumps(payload),)
        self.osc_server.add_handler("/live/kenn/get/device_tree", kenn_get_device_tree)

        def kenn_get_device_parameters(params):
            kind, index, device_index = str(params[0]), int(params[1]), int(params[2])
            try:
                device = _kenn_track(kind, index).devices[device_index]
                rows = []
                for position, parameter in enumerate(device.parameters):
                    rows.append({
                        "index": position, "name": str(parameter.name),
                        "value": float(parameter.value), "min": float(parameter.min), "max": float(parameter.max),
                        "quantized": bool(parameter.is_quantized),
                        "value_display": str(parameter.str_for_value(parameter.value)),
                        "automation_state": int(getattr(parameter, "automation_state", 0)),
                    })
                payload = {"kind": kind, "index": index, "device_index": device_index,
                           "device_name": str(device.name), "parameters": rows}
            except Exception as exc:
                payload = {"kind": kind, "index": index, "device_index": device_index, "error": str(exc)}
            return (json.dumps(payload),)
        self.osc_server.add_handler("/live/kenn/get/device_parameters", kenn_get_device_parameters)

        def kenn_get_display_table(params):
            """Live's own display string at evenly spaced values of one parameter.

            Read-only: uses ``str_for_value`` and never writes the parameter.
            target is ``volume``, ``pan``, ``send:<r>`` or ``device:<d>:<p>``.
            Optional start/stop (fractions of the parameter's range) page a
            fine table in chunks: macOS drops UDP replies over 9,216 bytes.
            """
            kind, index, target = str(params[0]), int(params[1]), str(params[2])
            samples = max(2, min(200, int(params[3]) if len(params) > 3 else 101))
            start = max(0.0, min(1.0, float(params[4]) if len(params) > 4 else 0.0))
            stop = max(start, min(1.0, float(params[5]) if len(params) > 5 else 1.0))
            try:
                track = _kenn_track(kind, index)
                if target == "volume":
                    parameter = track.mixer_device.volume
                elif target == "pan":
                    parameter = track.mixer_device.panning
                elif target.startswith("send:"):
                    parameter = track.mixer_device.sends[int(target.split(":")[1])]
                elif target.startswith("device:"):
                    _, device_index, parameter_index = target.split(":")
                    parameter = track.devices[int(device_index)].parameters[int(parameter_index)]
                else:
                    raise ValueError("target must be volume, pan, send:<r> or device:<d>:<p>")
                low, high = float(parameter.min), float(parameter.max)
                points = []
                for step in range(samples):
                    fraction = start + (stop - start) * step / (samples - 1)
                    value = low + (high - low) * fraction
                    points.append([round(value, 7), str(parameter.str_for_value(value))])
                payload = {"kind": kind, "index": index, "target": target, "name": str(parameter.name),
                           "min": low, "max": high, "points": points}
            except Exception as exc:
                payload = {"kind": kind, "index": index, "target": target, "error": str(exc)}
            return (json.dumps(payload),)
        self.osc_server.add_handler("/live/kenn/get/display_table", kenn_get_display_table)

        def song_set_return_track_name(params):
            return_track_index, name = params
            self.song.return_tracks[int(return_track_index)].name = str(name)

        # Return tracks are not members of ``song.tracks``, so the regular
        # TrackHandler name setter cannot address them. Keep this explicit and
        # narrow; KENN binds the index and verifies the post-write identity.
        self.osc_server.add_handler("/live/song/set/return_track_name", song_set_return_track_name)

        def song_get_track_data(params):
            """
            Retrieve one more properties of a block of tracks and their clips.
            Properties must be of the format track.property_name or clip.property_name.

            For example:
                /live/song/get/track_data 0 12 track.name clip.name clip.length

            Queries tracks 0..11, and returns a list of values comprising:

            [track_0_name, clip_0_0_name,   clip_0_1_name,   ... clip_0_7_name,
                           clip_1_0_length, clip_0_1_length, ... clip_0_7_length,
             track_1_name, clip_1_0_name,   clip_1_1_name,   ... clip_1_7_name, ...]
            """
            track_index_min, track_index_max, *properties = params
            track_index_min = int(track_index_min)
            track_index_max = int(track_index_max)
            self.logger.info("Getting track data: %s (tracks %d..%d)" %
                             (properties, track_index_min, track_index_max))
            if track_index_max == -1:
                track_index_max = len(self.song.tracks)
            rv = []
            for track_index in range(track_index_min, track_index_max):
                track = self.song.tracks[track_index]
                for prop in properties:
                    obj, property_name = prop.split(".")
                    if obj == "track":
                        if property_name == "num_devices":
                            value = len(track.devices)
                        else:
                            value = getattr(track, property_name)
                            if isinstance(value, Live.Track.Track):
                                #--------------------------------------------------------------------------------
                                # Map Track objects to their track_index to return via OSC
                                #--------------------------------------------------------------------------------
                                value = list(self.song.tracks).index(value)
                        rv.append(value)
                    elif obj == "clip":
                        for clip_slot in track.clip_slots:
                            if clip_slot.clip is not None:
                                rv.append(getattr(clip_slot.clip, property_name))
                            else:
                                rv.append(None)
                    elif obj == "clip_slot":
                        for clip_slot in track.clip_slots:
                            rv.append(getattr(clip_slot, property_name))
                    elif obj == "device":
                        for device in track.devices:
                            rv.append(getattr(device, property_name))
                    else:
                        self.logger.error("Unknown object identifier in get/track_data: %s" % obj)
            return tuple(rv)
        self.osc_server.add_handler("/live/song/get/track_data", song_get_track_data)


        def song_export_structure(params):
            tracks = []
            for track_index, track in enumerate(self.song.tracks):
                group_track = None
                if track.group_track is not None:
                    group_track = list(self.song.tracks).index(track.group_track)
                track_data = {
                    "index": track_index,
                    "name": track.name,
                    "is_foldable": track.is_foldable,
                    "group_track": group_track,
                    "clips": [],
                    "devices": []
                }
                for clip_index, clip_slot in enumerate(track.clip_slots):
                    if clip_slot.clip:
                        clip_data = {
                            "index": clip_index,
                            "name": clip_slot.clip.name,
                            "length": clip_slot.clip.length,
                        }
                        track_data["clips"].append(clip_data)

                for device_index, device in enumerate(track.devices):
                    device_data = {
                        "class_name": device.class_name,
                        "type": device.type,
                        "name": device.name,
                        "parameters": []
                    }
                    for parameter in device.parameters:
                        device_data["parameters"].append({
                            "name": parameter.name,
                            "value": parameter.value,
                            "min": parameter.min,
                            "max": parameter.max,
                            "is_quantized": parameter.is_quantized,
                        })
                    track_data["devices"].append(device_data)

                tracks.append(track_data)
            song = {
                "tracks": tracks
            }

            if sys.platform == "darwin":
                #--------------------------------------------------------------------------------
                # On macOS, TMPDIR by default points to a process-specific directory.
                # We want to use a global temp dir (typically, tmp) so that other processes
                # know where to find this output .json, so unset TMPDIR.
                #--------------------------------------------------------------------------------
                os.environ["TMPDIR"] = ""
            fd = open(os.path.join(tempfile.gettempdir(), "abletonosc-song-structure.json"), "w")
            json.dump(song, fd)
            fd.close()
            self.logger.warning("Exported song structure to directory %s" % tempfile.gettempdir())
            return (1,)
        self.osc_server.add_handler("/live/song/export/structure", song_export_structure)

        #--------------------------------------------------------------------------------
        # Callbacks for Song: Scene properties
        #--------------------------------------------------------------------------------
        self.osc_server.add_handler("/live/song/get/num_scenes", lambda _: (len(self.song.scenes),))

        def song_get_scene_names(params):
            if len(params) == 0:
                scene_index_min, scene_index_max = 0, len(self.song.scenes)
            else:
                scene_index_min, scene_index_max = params
            return tuple(self.song.scenes[index].name for index in range(scene_index_min, scene_index_max))
        self.osc_server.add_handler("/live/song/get/scenes/name", song_get_scene_names)

        #--------------------------------------------------------------------------------
        # Callbacks for Song: Cue point properties
        #--------------------------------------------------------------------------------
        def song_get_cue_points(song, _):
            cue_points = song.cue_points
            cue_point_pairs = [(cue_point.name, cue_point.time) for cue_point in cue_points]
            return tuple(element for pair in cue_point_pairs for element in pair)
        self.osc_server.add_handler("/live/song/get/cue_points", partial(song_get_cue_points, self.song))

        def song_jump_to_cue_point(song, params: Tuple[Any] = ()):
            cue_point_index = params[0]
            if isinstance(cue_point_index, str):
                for cue_point in song.cue_points:
                    if cue_point.name == cue_point_index:
                        cue_point.jump()
            elif isinstance(cue_point_index, int):
                cue_point = song.cue_points[cue_point_index]
                cue_point.jump()
        self.osc_server.add_handler("/live/song/cue_point/jump", partial(song_jump_to_cue_point, self.song))

        self.osc_server.add_handler("/live/song/cue_point/add_or_delete", partial(self._call_method, self.song, "set_or_delete_cue"))
        def song_cue_point_set_name(song, params: Tuple[Any] = ()):
            cue_point_index = params[0]
            new_name = params[1]
            cue_point = song.cue_points[cue_point_index]
            cue_point.name = new_name
        self.osc_server.add_handler("/live/song/cue_point/set/name", partial(song_cue_point_set_name, self.song))

        #--------------------------------------------------------------------------------
        # Listener for /live/song/get/beat
        #--------------------------------------------------------------------------------
        self.last_song_time = -1.0

        def stop_beat_listener(params: Tuple[Any] = ()):
            try:
                self.song.remove_current_song_time_listener(self.current_song_time_changed)
                self.logger.info("Removing beat listener")
            except:
                pass

        def start_beat_listener(params: Tuple[Any] = ()):
            stop_beat_listener()
            self.logger.info("Adding beat listener")
            self.song.add_current_song_time_listener(self.current_song_time_changed)

        self.osc_server.add_handler("/live/song/start_listen/beat", start_beat_listener)
        self.osc_server.add_handler("/live/song/stop_listen/beat", stop_beat_listener)

    def current_song_time_changed(self):
        #--------------------------------------------------------------------------------
        # If song has rewound or skipped to next beat, sent a /live/beat message
        #--------------------------------------------------------------------------------
        if (self.song.current_song_time < self.last_song_time) or \
                (int(self.song.current_song_time) > int(self.last_song_time)):
            self.osc_server.send("/live/song/get/beat", (int(self.song.current_song_time),))
        self.last_song_time = self.song.current_song_time

    def clear_api(self):
        super().clear_api()
        try:
            self.song.remove_current_song_time_listener(self.current_song_time_changed)
        except:
            pass
