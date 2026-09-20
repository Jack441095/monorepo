from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Protocol, Sequence, Tuple


EventTuple = Tuple[int, int, int, float, float, Sequence[int]]


class Composer(Protocol):
    """Produces symbolic events for a section (MIDI-like tuples)."""

    def reseed(self, seed: int) -> None: ...

    def generate_section(
        self,
        emotion: Any,
        *,
        root_note: int,
        bars: int,
        temperature: float,
        target_notes_per_bar: float,
        melody_style: str,
        humanization_scale: float,
        section_index: int,
    ) -> List[EventTuple]: ...


class Player(Protocol):
    """Realtime playback driver."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def load_emotion(self, emotion_index: int, root_note: int) -> None: ...


@dataclass(frozen=True)
class RunnerDeps:
    """Dependency bundle for a runner session."""

    composer: Composer
    player: Player
    config: Any

