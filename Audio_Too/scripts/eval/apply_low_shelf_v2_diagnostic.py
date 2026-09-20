#!/usr/bin/env python3
"""
Diagnostic-only: v2 of the low-shelf correction. Jack's blind verdict on v1
(150Hz corner, +4.5dB): "B is great, but... lots of high frequencies and not
a lot of low mid" -- the tonal-balance tool's low_mids band (150-400Hz) only
needed +0.4dB per the numbers, but a 150Hz shelf corner's transition band
tapers off before properly reaching that range perceptually. Raising the
corner frequency extends the boost's reach up into low-mids while staying a
single, non-cutting move (same successful philosophy as v1).

Not a production default. One-off test.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from automix_local import run_local_automix  # noqa: E402

# v1 was 150Hz/+4.5dB (validated direction: "B is great"). v2 raises the
# corner to 300Hz (top of the low_mids band, 150-400Hz) so the shelf's
# transition properly covers low-mids instead of tapering out before it,
# addressing "not a lot of low mid" directly. Gain trimmed slightly (4.5->4.0)
# since the wider band now includes some low_mids content that measured
# closer to the reference already (+0.4dB needed there vs +3.8dB for bass).
BANDS = [
    {
        "type": "lowshelf",
        "frequency": 300.0,
        "gain_db": 4.0,
        "q": 0.707,
        "reason": "v2: widened low-shelf corner (150Hz->300Hz) to properly cover low-mids per Jack's blind-listening feedback on v1",
    },
]


def main():
    project_id = sys.argv[1] if len(sys.argv) > 1 else "stranger-lowshelf-v2"
    print(f"Applying {len(BANDS)} low-shelf band:")
    for b in BANDS:
        print(f"  {b['frequency']:>7.0f} Hz  {b['gain_db']:+.1f} dB  ({b['type']})")

    delivery = run_local_automix(
        ROOT / "testing_track_stems" / "stranger" / "WAVs",
        genre="pop",
        target_lufs=-14.0,
        output_dir=ROOT / "artifacts" / "real_stem_validation_2026-07-15",
        project_id=project_id,
        apply_mono_compat_correction=True,
        extra_bus_eq_bands=BANDS,
    )
    print(f"\nOK: {delivery.get('zip_path')}")


if __name__ == "__main__":
    main()
