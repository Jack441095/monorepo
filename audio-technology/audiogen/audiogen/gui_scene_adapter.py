from __future__ import annotations

from typing import Any, Dict


class GuiSceneAdapter:
    """
    Thin GUI binding helper around AppController scene APIs.

    Keeps UI code simple: each control can call one setter here, and the adapter
    forwards a partial scene update to `AppController.apply_scene(...)`.
    """

    def __init__(self, controller):
        self.controller = controller

    def get_schema(self) -> Dict[str, Any]:
        return dict(self.controller.get_ui_schema() or {})

    def get_contract(self) -> Dict[str, Any]:
        return dict(self.controller.get_scene_contract() or {})

    def get_snapshot(self) -> Dict[str, Any]:
        return dict(self.controller.get_scene_snapshot() or {})

    def apply_partial(self, **kwargs) -> Dict[str, Any]:
        return dict(self.controller.apply_scene(dict(kwargs or {})) or {})

    def set_tempo(self, bpm: float) -> Dict[str, Any]:
        return self.apply_partial(tempo=float(bpm))

    def set_emotion(self, emotion: Any) -> Dict[str, Any]:
        return self.apply_partial(emotion=emotion)

    def set_arrangement_type(self, arrangement_type: str) -> Dict[str, Any]:
        return self.apply_partial(arrangement_type=str(arrangement_type))

    def set_instrument_source(self, instrument_source: str) -> Dict[str, Any]:
        return self.apply_partial(instrument_source=str(instrument_source))

    def set_style(self, style: str) -> Dict[str, Any]:
        return self.apply_partial(style=str(style))

    def set_fx_preset(self, fx_preset: str) -> Dict[str, Any]:
        return self.apply_partial(fx_preset=str(fx_preset))

    def set_swing(self, swing: Any) -> Dict[str, Any]:
        return self.apply_partial(swing=swing)
