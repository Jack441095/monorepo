# composition/song_generator/models.py
# Data containers shared across the song_generator package: the per-section
# spec used to drive arrangement forms, and the final stitched song render.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SongSectionSpec:
    emotion_name: str
    bars: int = 16
    root_note: int = 60
    temperature: float = 0.7
    target_notes_per_bar: float = 6.0
    melody_style: str = "auto"


@dataclass
class SongRender:
    """A fully arranged song render (events are in beats, global timeline)."""

    sections: List[SongSectionSpec]
    events: List[Tuple]
    tempo_map: List[Tuple[float, float]]  # (start_beat, bpm)
    metadata: Optional[Dict[str, Any]] = None
