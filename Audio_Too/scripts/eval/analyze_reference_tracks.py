#!/usr/bin/env python3
"""
Analyze every reference track in reference_tracks/ with the same 7-band
tonal-balance fingerprint reference_track_comparison.py uses for a mix (so
KENN can ground answers about a reference track's own measured profile, not
just about AutoMix's decisions relative to one). Glue, not new analysis --
reuses log_band_ratios_track_average + map_40_to_7_bands exactly.

Writes reference_track_profiles.json under artifacts/reference_track_profiles/,
keyed by filename, so this only needs to be re-run when reference_tracks/
changes, not on every KENN query.

Usage: analyze_reference_tracks.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.utils.audio_io import read_wav_mono  # noqa: E402
from audio_analysis.analysis_core.dsp_metrics import log_band_ratios_track_average  # noqa: E402
from audio_analysis.analysis_core.genre_profiles import map_40_to_7_bands  # noqa: E402

REFERENCE_TRACKS_DIR = ROOT / "reference_tracks"
OUTPUT_PATH = ROOT / "artifacts" / "reference_track_profiles" / "reference_track_profiles.json"

_LOW_BANDS = ("sub", "bass", "low_mids")
_HIGH_BANDS = ("presence", "sibilance", "air")


def high_to_low_ratio(bands7: dict[str, float]) -> float:
    """Sum of presence/sibilance/air energy over sum of sub/bass/low_mids
    energy -- the same single-number summary used earlier this session to
    describe "how much high end vs low end" a track has (e.g. the finding
    that a mix measured ~4x the reference's ratio)."""
    low = sum(max(bands7.get(b, 0.0), 0.0) for b in _LOW_BANDS)
    high = sum(max(bands7.get(b, 0.0), 0.0) for b in _HIGH_BANDS)
    if low <= 0.0:
        return float("inf") if high > 0.0 else 0.0
    return high / low


def analyze_track(path: Path) -> dict:
    data = read_wav_mono(path.read_bytes(), max_samples=0)
    bands40 = log_band_ratios_track_average(data["samples"], data["sample_rate"])
    bands7 = map_40_to_7_bands(bands40)
    return {
        "duration_seconds": data["duration_seconds"],
        "sample_rate": data["sample_rate"],
        "bands7": {k: round(v, 4) for k, v in bands7.items()},
        "high_to_low_ratio": round(high_to_low_ratio(bands7), 3),
    }


def main():
    tracks = sorted(
        p for p in REFERENCE_TRACKS_DIR.iterdir()
        if p.suffix.lower() in (".mp3", ".wav", ".flac", ".m4a") and p.is_file()
    )
    if not tracks:
        print(f"No audio files found in {REFERENCE_TRACKS_DIR}")
        sys.exit(1)

    profiles: dict[str, dict] = {}
    for path in tracks:
        print(f"Analyzing: {path.name}")
        try:
            profiles[path.name] = analyze_track(path)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue
        p = profiles[path.name]
        print(
            f"  {p['duration_seconds']:.1f}s, high/low ratio={p['high_to_low_ratio']:.2f}, "
            f"bass={p['bands7'].get('bass', 0):.3f}, presence={p['bands7'].get('presence', 0):.3f}"
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(profiles, indent=2))
    print(f"\nWrote {len(profiles)} profile(s) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
