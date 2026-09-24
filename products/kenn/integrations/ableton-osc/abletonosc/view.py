from functools import partial
from typing import Optional, Tuple, Any
from .handler import AbletonOSCHandler

class ViewHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "view"

    def init_api(self):
        def get_selected_scene(params: Optional[Tuple] = ()):
            return (list(self.song.scenes).index(self.song.view.selected_scene),)

        def selected_track_kind():
            """(kind, index) for the selected track; kind is track, return, or master."""
            selected = self.song.view.selected_track
            tracks = list(self.song.tracks)
            if selected in tracks:
                return ("track", tracks.index(selected))
            returns = list(self.song.return_tracks)
            if selected in returns:
                return ("return", returns.index(selected))
            if selected == self.song.master_track:
                return ("master", -1)
            return ("unknown", -1)

        def get_selected_track(params: Optional[Tuple] = ()):
            # -1 when a return/master track is selected: answer immediately
            # instead of raising, which left callers waiting for a timeout.
            kind, index = selected_track_kind()
            return (index if kind == "track" else -1,)

        def get_selected_track_kind(params: Optional[Tuple] = ()):
            kind, index = selected_track_kind()
            name = str(self.song.view.selected_track.name) if kind != "unknown" else ""
            return (kind, index, name)

        def get_selected_clip(params: Optional[Tuple] = ()):
            return (get_selected_track()[0], get_selected_scene()[0])

        def get_selected_device(params: Optional[Tuple] = ()):
            track_index = get_selected_track()[0]
            if track_index < 0:
                return (-1, -1)
            track = self.song.view.selected_track
            selected = track.view.selected_device
            devices = list(track.devices)
            return (track_index, devices.index(selected) if selected in devices else -1)

        def set_selected_scene(params: Optional[Tuple] = ()):
            self.song.view.selected_scene = self.song.scenes[params[0]]

        def set_selected_track(params: Optional[Tuple] = ()):
            self.song.view.selected_track = self.song.tracks[params[0]]

        def set_selected_clip(params: Optional[Tuple] = ()):
            set_selected_track((params[0],))
            set_selected_scene((params[1],))

        def set_selected_device(params: Optional[Tuple] = ()):
            track = self.song.tracks[params[0]]
            device = track.devices[params[1]]
            # With Live's device view (Detail/DeviceChain) hidden, select_device
            # alone leaves the selection unchanged (Live 12.4.6, 2026-09-24);
            # selecting the track first makes it take effect either way.
            self.song.view.selected_track = track
            self.song.view.select_device(device)
            return params[0], params[1]

        self.osc_server.add_handler("/live/view/get/selected_scene", get_selected_scene)
        self.osc_server.add_handler("/live/view/get/selected_track", get_selected_track)
        self.osc_server.add_handler("/live/view/get/selected_track_kind", get_selected_track_kind)
        self.osc_server.add_handler("/live/view/get/selected_clip", get_selected_clip)
        self.osc_server.add_handler("/live/view/get/selected_device", get_selected_device)
        self.osc_server.add_handler("/live/view/set/selected_scene", set_selected_scene)
        self.osc_server.add_handler("/live/view/set/selected_track", set_selected_track)
        self.osc_server.add_handler("/live/view/set/selected_clip", set_selected_clip)
        self.osc_server.add_handler("/live/view/set/selected_device", set_selected_device)

        self.osc_server.add_handler('/live/view/start_listen/selected_scene', partial(self._start_listen, self.song.view, "selected_scene", getter=get_selected_scene))
        self.osc_server.add_handler('/live/view/start_listen/selected_track', partial(self._start_listen, self.song.view, "selected_track", getter=get_selected_track))
        self.osc_server.add_handler('/live/view/stop_listen/selected_scene', partial(self._stop_listen, self.song.view, "selected_scene"))
        self.osc_server.add_handler('/live/view/stop_listen/selected_track', partial(self._stop_listen, self.song.view, "selected_track"))
