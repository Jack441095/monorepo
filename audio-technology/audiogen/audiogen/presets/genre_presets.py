"""AudioGen Genre Preset Generator Library.

Provides curated genre presets (Cyberpunk, Synthwave, Lofi Hip-Hop, Cinematic Film Trailer,
Deep House, Acoustic Folk) with pre-configured macro settings and harmonic profiles.
"""

from __future__ import annotations

from typing import Dict, List, Any
from .presets import PresetV1

GENRE_PRESETS: Dict[str, PresetV1] = {
    "cyberpunk": PresetV1(
        version=1,
        name="cyberpunk",
        sample_pack="electronic_dark",
        style_profile="aggressive_synth",
        arrangement_style="edm_drop",
        macros={"brightness": 0.85, "warmth": 0.3, "space": 0.6, "energy": 0.95},
        metadata={"bpm": 128.0, "genre": "Cyberpunk", "key": "F minor"}
    ),
    "synthwave": PresetV1(
        version=1,
        name="synthwave",
        sample_pack="synthwave_80s",
        style_profile="retro_analog",
        arrangement_style="pop_verse_chorus",
        macros={"brightness": 0.75, "warmth": 0.8, "space": 0.7, "energy": 0.8},
        metadata={"bpm": 115.0, "genre": "Synthwave", "key": "A minor"}
    ),
    "lofi_hiphop": PresetV1(
        version=1,
        name="lofi_hiphop",
        sample_pack="lofi_vintage",
        style_profile="chill_tape",
        arrangement_style="lofi_loop",
        macros={"brightness": 0.3, "warmth": 0.9, "space": 0.5, "energy": 0.4},
        metadata={"bpm": 85.0, "genre": "Lofi Hip-Hop", "key": "C major"}
    ),
    "cinematic_trailer": PresetV1(
        version=1,
        name="cinematic_trailer",
        sample_pack="orchestral_epic",
        style_profile="epic_strings",
        arrangement_style="build_climax",
        macros={"brightness": 0.6, "warmth": 0.7, "space": 0.95, "energy": 0.9},
        metadata={"bpm": 90.0, "genre": "Cinematic Film Trailer", "key": "D minor"}
    ),
    "deep_house": PresetV1(
        version=1,
        name="deep_house",
        sample_pack="house_four_floor",
        style_profile="sub_groove",
        arrangement_style="club_extended",
        macros={"brightness": 0.65, "warmth": 0.75, "space": 0.65, "energy": 0.85},
        metadata={"bpm": 124.0, "genre": "Deep House", "key": "G minor"}
    ),
    "acoustic_folk": PresetV1(
        version=1,
        name="acoustic_folk",
        sample_pack="organic_acoustic",
        style_profile="natural_wood",
        arrangement_style="folk_story",
        macros={"brightness": 0.5, "warmth": 0.85, "space": 0.4, "energy": 0.5},
        metadata={"bpm": 100.0, "genre": "Acoustic Folk", "key": "G major"}
    ),
}


def get_genre_preset(name: str) -> PresetV1:
    """Retrieve PresetV1 by genre name, defaulting to synthwave if unknown."""
    key = str(name or "").strip().lower().replace(" ", "_")
    return GENRE_PRESETS.get(key, GENRE_PRESETS["synthwave"])


def list_genre_presets() -> List[str]:
    """List all available genre preset keys."""
    return sorted(list(GENRE_PRESETS.keys()))
