"""Audio package public API.

The heavy realtime/player/sampler modules are imported lazily so simple
``import audio`` calls do not initialize optional audio-device dependencies.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AudioMixer",
    "EVENT_BUS",
    "PolyphonicPlayer",
    "AudioChunk",
    "SamplerEngine",
    "SamplerSynthesisEngine",
    "Sampler",
    "AudioContainer",
    "get_audio_container",
    "set_audio_container",
]


def __getattr__(name: str) -> Any:
    if name in {"AudioContainer", "get_audio_container", "set_audio_container"}:
        from .audio_container import AudioContainer, get_audio_container, set_audio_container

        values = {
            "AudioContainer": AudioContainer,
            "get_audio_container": get_audio_container,
            "set_audio_container": set_audio_container,
        }
        return values[name]

    if name in {"PolyphonicPlayer", "AudioChunk"}:
        from .RT_player import AudioChunk, PolyphonicPlayer

        values = {
            "PolyphonicPlayer": PolyphonicPlayer,
            "AudioChunk": AudioChunk,
        }
        return values[name]

    if name in {"EVENT_BUS", "AudioMixer"}:
        from .engine import EVENT_BUS, AudioMixer

        values = {
            "EVENT_BUS": EVENT_BUS,
            "AudioMixer": AudioMixer,
        }
        return values[name]

    if name in {"Sampler", "SamplerEngine", "SamplerSynthesisEngine"}:
        from sampler import Sampler, SamplerEngine, SamplerSynthesisEngine

        values = {
            "Sampler": Sampler,
            "SamplerEngine": SamplerEngine,
            "SamplerSynthesisEngine": SamplerSynthesisEngine,
        }
        return values[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
