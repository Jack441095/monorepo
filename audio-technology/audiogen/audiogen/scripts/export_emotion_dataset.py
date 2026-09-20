#!/usr/bin/env python3
"""Export in-repo emotion harmony tables to structured dataset files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _progression_rows(emotion: Any) -> Iterable[Dict[str, Any]]:
    name = str(getattr(emotion, "name", "") or "").strip().lower()
    for idx, progression in enumerate(list(getattr(emotion, "chord_progressions", []) or [])):
        yield {
            "emotion": name,
            "kind": "progression",
            "section_role": "",
            "index": int(idx),
            "progression": [str(ch) for ch in list(progression or [])],
            "source": "data.music_data",
        }
    for idx, progression in enumerate(list(getattr(emotion, "cadence_progressions", []) or [])):
        yield {
            "emotion": name,
            "kind": "cadence",
            "section_role": "cadence",
            "index": int(idx),
            "progression": [str(ch) for ch in list(progression or [])],
            "source": "data.music_data",
        }
    sets = getattr(emotion, "arrangement_chord_sets", None) or {}
    if isinstance(sets, dict):
        for role, progressions in sorted(sets.items()):
            for idx, progression in enumerate(list(progressions or [])):
                yield {
                    "emotion": name,
                    "kind": "arrangement",
                    "section_role": str(role or "").strip().lower(),
                    "index": int(idx),
                    "progression": [str(ch) for ch in list(progression or [])],
                    "source": "data.music_data.arrangement_chord_sets",
                }


def _emotion_profile_row(emotion: Any) -> Dict[str, Any]:
    name = str(getattr(emotion, "name", "") or "").strip().lower()
    return {
        "emotion": name,
        "scale_intervals": [int(v) for v in list(getattr(emotion, "scale_intervals", []) or [])],
        "tempo_multiplier": float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0),
        "velocity_multiplier": float(getattr(emotion, "velocity_multiplier", 1.0) or 1.0),
        "density": float(getattr(emotion, "density", 0.5) or 0.5),
        "progression_count": len(list(getattr(emotion, "chord_progressions", []) or [])),
        "cadence_count": len(list(getattr(emotion, "cadence_progressions", []) or [])),
        "arrangement_role_count": len(getattr(emotion, "arrangement_chord_sets", None) or {}),
    }


def main() -> int:
    try:
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    except Exception:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out-dir",
        default="data/datasets/emotions/v1",
        help="Output directory for emotion_profiles.json and harmony_progressions.jsonl.",
    )
    args = ap.parse_args()

    from data.music_data import EMOTIONS

    out_dir = Path(str(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    profiles = [_emotion_profile_row(e) for e in list(EMOTIONS or [])]
    progressions: List[Dict[str, Any]] = []
    for emotion in list(EMOTIONS or []):
        progressions.extend(list(_progression_rows(emotion)))

    profile_path = out_dir / "emotion_profiles.json"
    progression_path = out_dir / "harmony_progressions.jsonl"
    manifest_path = out_dir / "manifest.json"

    profile_path.write_text(json.dumps(profiles, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with progression_path.open("w", encoding="utf-8") as f:
        for row in progressions:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    manifest = {
        "schema_version": 1,
        "source": "data.music_data",
        "emotion_count": int(len(profiles)),
        "progression_rows": int(len(progressions)),
        "files": {
            "emotion_profiles": str(profile_path),
            "harmony_progressions": str(progression_path),
        },
        "schemas": {
            "emotion_profiles": "data/datasets/schemas/emotion_profile.schema.json",
            "harmony_progressions": "data/datasets/schemas/harmony_progression.schema.json",
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {profile_path}")
    print(f"wrote {progression_path} rows={len(progressions)}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
