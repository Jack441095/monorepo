#!/usr/bin/env python3
"""Stage D — real reference-track validation for the mix style classifier.

The style/genre/era classifier (studio/audio_analysis/audio_analysis/
mix_review/mix_style_classifier.py + analysis_core/genre_profiles.py) has
only ever been tested against synthetic curated 40-band archetypes
(tests/audio_analysis/test_genre_profiles.py) -- never real commercial
audio. This script runs every audio file in reference_tracks/ (git-ignored;
copyrighted third-party audio never gets committed) through the real
analyze_wav() -> classify_mix_style() pipeline and prints the result for a
human to sanity-check against what they already know about the track.

This is deliberately NOT a pass/fail gate: "is this actually a loudness-war
90s pop master" is a judgment call a human makes by ear/knowledge, not
something to hardcode as a unit-test assertion against one person's
subjective take on a handful of tracks.

Usage:
  Drop some audio files (wav/mp3/flac/etc.) into reference_tracks/, then:
    python scripts/eval/validate_style_classifier.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = ROOT / "reference_tracks"

for extra in (".", "studio/audio_analysis", "server/app"):
    p = str(ROOT / extra)
    if p not in sys.path:
        sys.path.insert(0, p)

AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".aiff", ".aif", ".ogg"}


def _iter_reference_files() -> list[Path]:
    if not REFERENCE_DIR.exists():
        return []
    return sorted(p for p in REFERENCE_DIR.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES)


def run() -> int:
    from audio_analysis.mix_review.mix_review import analyze_wav
    from audio_analysis.mix_review.mix_style_classifier import classify_mix_style

    files = _iter_reference_files()
    if not files:
        print(f"No audio files found in {REFERENCE_DIR}/")
        print("Drop some in (wav/mp3/flac/m4a/aiff/ogg) and re-run.")
        return 0

    results = []
    for path in files:
        print(f"\n== {path.name} ==", flush=True)
        try:
            file_bytes = path.read_bytes()
            report = analyze_wav(file_bytes, path.name)
            metrics = report.get("metrics", report)
            style = classify_mix_style(metrics)
        except Exception as exc:
            print(f"  FAILED to analyze: {exc}")
            results.append({"file": path.name, "error": str(exc)})
            continue

        lufs = metrics.get("integrated_lufs")
        crest = metrics.get("crest_factor_db")
        print(f"  Measured:  LUFS {lufs}, crest factor {crest} dB")
        print(f"  Genre:     {style['genre']['genre_name']} (confidence {style['genre']['confidence']})")
        print(f"  Era:       {style['era'].get('label', 'unknown')}")
        print(f"  Mastering: {style['vintage_or_modern']['label']} (confidence {style['vintage_or_modern']['confidence']})")
        lw = style["loudness_war"]
        lw_desc = f"{lw['severity']}" if lw.get("participant") else "not a participant"
        print(f"  Loudness war: {lw_desc}")
        print(f"  Summary:   {style['summary']}")

        results.append({
            "file": path.name,
            "lufs": lufs,
            "crest_factor_db": crest,
            "genre": style["genre"]["genre_name"],
            "genre_confidence": style["genre"]["confidence"],
            "era": style["era"].get("label"),
            "mastering": style["vintage_or_modern"]["label"],
            "loudness_war": lw_desc,
            "summary": style["summary"],
        })

    out_path = REFERENCE_DIR / "validation_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nFull results written to {out_path}")
    print(
        "\nNow the human part: does each classification actually match what you "
        "know about the track? Tell me which ones look wrong and I'll dig into why."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
