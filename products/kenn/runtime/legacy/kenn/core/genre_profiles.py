"""Genre-Aware Target Profile Engine for KENN.

Tailors diagnostic thresholds, target LUFS delivery standards, spectral balance targets,
and dynamics expectations based on the project's musical genre.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class GenreProfile:
    genre: str
    display_name: str
    target_lufs: float
    max_peak_dbfs: float
    sub_bass_weight: str  # "heavy", "moderate", "light", "subdued"
    midrange_focus_hz: tuple[float, float]
    target_crest_range_db: tuple[float, float]
    compression_character: str  # "punchy", "aggressive", "transparent", "glue"
    description: str


GENRE_PROFILES: dict[str, GenreProfile] = {
    "hip_hop": GenreProfile(
        genre="hip_hop",
        display_name="Hip-Hop / Trap / Rap",
        target_lufs=-9.0,
        max_peak_dbfs=-0.3,
        sub_bass_weight="heavy",
        midrange_focus_hz=(1000.0, 3000.0),
        target_crest_range_db=(6.0, 10.0),
        compression_character="punchy",
        description="Heavy sub-bass emphasis (30-60 Hz), prominent lead vocal in upper-mids, controlled dynamics for high streaming loudness.",
    ),
    "edm_pop": GenreProfile(
        genre="edm_pop",
        display_name="EDM / Dance / Pop",
        target_lufs=-8.5,
        max_peak_dbfs=-0.3,
        sub_bass_weight="heavy",
        midrange_focus_hz=(800.0, 4000.0),
        target_crest_range_db=(5.0, 9.0),
        compression_character="punchy",
        description="Wide stereo field, extended high-end air (>10 kHz), tight sidechain compression, very high density.",
    ),
    "rock_metal": GenreProfile(
        genre="rock_metal",
        display_name="Rock / Metal / Alternative",
        target_lufs=-11.0,
        max_peak_dbfs=-0.5,
        sub_bass_weight="moderate",
        midrange_focus_hz=(1500.0, 4500.0),
        target_crest_range_db=(7.0, 11.0),
        compression_character="aggressive",
        description="Dense guitar wall in mid-range, aggressive snare crack, punchy kick transient, controlled sub-bass to prevent mud.",
    ),
    "rnb_soul": GenreProfile(
        genre="rnb_soul",
        display_name="R&B / Soul / Funk",
        target_lufs=-12.0,
        max_peak_dbfs=-0.5,
        sub_bass_weight="moderate",
        midrange_focus_hz=(500.0, 2500.0),
        target_crest_range_db=(8.0, 12.0),
        compression_character="glue",
        description="Warm sub and bass groove, silky vocal high-end, smooth glue compression, open dynamic response.",
    ),
    "acoustic_folk": GenreProfile(
        genre="acoustic_folk",
        display_name="Acoustic / Folk / Jazz / Classical",
        target_lufs=-16.0,
        max_peak_dbfs=-1.0,
        sub_bass_weight="subdued",
        midrange_focus_hz=(300.0, 3000.0),
        target_crest_range_db=(12.0, 18.0),
        compression_character="transparent",
        description="Preserved natural micro-dynamics (high crest factor), zero hard clipping, warm room acoustics, uncompressed transients.",
    ),
    "cinematic_game": GenreProfile(
        genre="cinematic_game",
        display_name="Cinematic / Game Audio / Trailer",
        target_lufs=-14.0,
        max_peak_dbfs=-1.0,
        sub_bass_weight="moderate",
        midrange_focus_hz=(400.0, 5000.0),
        target_crest_range_db=(10.0, 16.0),
        compression_character="transparent",
        description="Extreme wide dynamic range, localized spatial imaging, dialogues/effects clarity, platform-budget compliant.",
    ),
}

DEFAULT_GENRE_PROFILE = GenreProfile(
    genre="general",
    display_name="General Production",
    target_lufs=-14.0,
    max_peak_dbfs=-0.5,
    sub_bass_weight="moderate",
    midrange_focus_hz=(500.0, 3500.0),
    target_crest_range_db=(8.0, 13.0),
    compression_character="glue",
    description="Balanced standard streaming target (ITU-R BS.1770 -14 LUFS), moderate compression, clean headroom.",
)


def get_genre_profile(genre_key: Optional[str]) -> GenreProfile:
    """Return the GenreProfile for a given genre key or the default general profile."""
    if not genre_key:
        return DEFAULT_GENRE_PROFILE
    key = genre_key.lower().strip()
    return GENRE_PROFILES.get(key, DEFAULT_GENRE_PROFILE)


def detect_genre_from_query(query: str) -> Optional[str]:
    """Scan query text for genre keywords and return matching genre key."""
    if not query:
        return None

    normalized = query.lower()
    
    keyword_map = {
        "hip_hop": [r"\bhip[\s_-]*hop\b", r"\btrap\b", r"\brap\b", r"\bboom[\s_-]*bap\b", r"\b808\b"],
        "edm_pop": [r"\bedm\b", r"\bdance\b", r"\bhouse\b", r"\btechno\b", r"\btrance\b", r"\bdubstep\b", r"\bpop\b"],
        "rock_metal": [r"\brock\b", r"\bmetal\b", r"\bheavy[\s_-]*metal\b", r"\bpunk\b", r"\balternative\b", r"\bhardcore\b"],
        "rnb_soul": [r"\br&b\b", r"\brnb\b", r"\bsoul\b", r"\bfunk\b", r"\bneo[\s_-]*soul\b"],
        "acoustic_folk": [r"\bacoustic\b", r"\bfolk\b", r"\bjazz\b", r"\bclassical\b", r"\borchestral\b"],
        "cinematic_game": [r"\bcinematic\b", r"\bgame[\s_-]*audio\b", r"\btrailer\b", r"\bfilm\b", r"\bscore\b"],
    }

    for genre_key, patterns in keyword_map.items():
        for pat in patterns:
            if re.search(pat, normalized):
                return genre_key

    return None

