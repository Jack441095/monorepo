from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence, Tuple


EventTuple = Tuple[int, Any, int, float, float, List[Any]]


def _event_dataclass(cls):
    """
    Python 3.10+ supports dataclass(slots=True). Older versions raise:
    TypeError: dataclass() got an unexpected keyword argument 'slots'
    """

    try:
        return dataclass(frozen=True, slots=True)(cls)  # type: ignore[call-arg]
    except TypeError:
        return dataclass(frozen=True)(cls)


@_event_dataclass
class Event:
    """
    Typed symbolic event used by the composition layer.

    The rest of the system historically used a 6-tuple:
      (channel, midi, velocity, start_beats, duration_beats, notes_list)
    We keep conversion helpers so audio/MIDI code can remain tuple-based.
    """

    channel: int
    midi: Any
    velocity: int
    start_beats: float
    duration_beats: float
    notes: List[Any]

    def to_tuple(self) -> EventTuple:
        return (
            int(self.channel),
            self.midi,
            int(self.velocity),
            float(self.start_beats),
            float(self.duration_beats),
            list(self.notes),
        )

    @staticmethod
    def from_tuple(ev: Sequence[Any]) -> "Event":
        if len(ev) != 6:
            raise ValueError(f"Expected 6-tuple event, got {ev!r}")
        ch, midi, vel, start, dur, notes = ev
        return Event(
            channel=int(ch),
            midi=midi,
            velocity=int(vel),
            start_beats=float(start),
            duration_beats=float(dur),
            notes=list(notes)
            if isinstance(notes, Iterable) and not isinstance(notes, (str, bytes))
            else [notes],
        )

