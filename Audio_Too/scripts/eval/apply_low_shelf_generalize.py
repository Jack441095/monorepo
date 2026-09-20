#!/usr/bin/env python3
"""
Generalization test: apply the validated low-shelf correction (v2: 300Hz
corner, +4.0dB, no cuts -- blind-listening confirmed positive on `stranger`
across two rounds of refinement) to a different song, to test whether the
now-confirmed-systemic bass/low-mid deficit
(docs/audits/2026-07-17-reference-track-comparison.md "Generalization" section
-- bass +3.5 to +4.5dB needed on all 3 test songs) responds to the same fix.

Not a production default. Diagnostic/evidence-gathering only -- still needs
a blind listen per song before any promotion.

Usage: apply_low_shelf_generalize.py <song> <project_id>
  <song> is one of: dream_of_you, reggueton_pop
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from automix_local import run_local_automix  # noqa: E402

SONGS = {
    "dream_of_you": {"stems": "testing_track_stems/dream_of_you/WAVs", "genre": "electronic"},
    "reggueton_pop": {"stems": "testing_track_stems/reggueton_pop/WAV's", "genre": "latin"},
}

# Same validated correction as stranger-lowshelf-v2, unchanged -- this tests
# whether it generalizes as-is, not a per-song retune (that would confound
# the "does the fix generalize" question with "did we also retune it").
EQ_BANDS = [
    {
        "type": "lowshelf",
        "frequency": 300.0,
        "gain_db": 4.0,
        "q": 0.707,
        "reason": "Validated low-shelf (v2), applied unchanged to test generalization across songs",
    },
]


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <song> <project_id>")
        print(f"  <song> is one of: {', '.join(SONGS)}")
        sys.exit(1)

    song = sys.argv[1]
    project_id = sys.argv[2]
    if song not in SONGS:
        print(f"Unknown song '{song}'. Options: {', '.join(SONGS)}")
        sys.exit(1)

    cfg = SONGS[song]
    print(f"Applying validated low-shelf (unchanged) to {song}:")
    for b in EQ_BANDS:
        print(f"  {b['frequency']:>7.0f} Hz  {b['gain_db']:+.1f} dB  ({b['type']})")

    delivery = run_local_automix(
        ROOT / cfg["stems"],
        genre=cfg["genre"],
        target_lufs=-14.0,
        output_dir=ROOT / "artifacts" / "real_stem_validation_2026-07-15",
        project_id=project_id,
        apply_mono_compat_correction=True,
        extra_bus_eq_bands=EQ_BANDS,
    )
    print(f"\nOK: {delivery.get('zip_path')}")


if __name__ == "__main__":
    main()
