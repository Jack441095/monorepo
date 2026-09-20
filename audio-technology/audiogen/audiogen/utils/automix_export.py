"""AutoMix Metadata Exporter for AudioGen.

Exports automix_meta.json alongside generated multitrack stems to provide
AutoMix with explicit stem role classifications and mix hints.
"""

from __future__ import annotations

import json
from pathlib import Path


def export_automix_meta(
    output_dir: Path | str,
    stem_roles: dict[str, str],
    genre: str = "pop",
    target_lufs: float = -14.0,
    bpm: float = 120.0,
    key: str = "C_major",
) -> Path:
    """Write an automix_meta.json metadata file to output_dir.

    Parameters
    ----------
    output_dir : Path or str
        Destination directory where stems are stored.
    stem_roles : dict[str, str]
        Mapping of stem filename -> instrument role (e.g. 'kick.wav': 'kick').
    genre : str
        Target genre for mixing ('pop', 'rock', 'hiphop', 'edm', 'acoustic').
    target_lufs : float
        Target integrated LUFS (-14.0, -16.0, -9.0).
    bpm : float
        Beats per minute.
    key : str
        Musical key.

    Returns
    -------
    Path
        Path to written automix_meta.json.
    """
    out_path = Path(output_dir) / "automix_meta.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "1.0",
        "genre": genre.lower(),
        "target_lufs": float(target_lufs),
        "bpm": float(bpm),
        "key": key,
        "stems": stem_roles,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return out_path
