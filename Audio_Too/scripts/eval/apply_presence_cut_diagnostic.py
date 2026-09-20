#!/usr/bin/env python3
"""
Diagnostic-only: a single, targeted bell cut in the 1k-5kHz region, where
Jack's ear identified the excess high end AND the LTAS chart confirms it
precisely -- our mix runs +4 to +6.5dB hotter than the reference right around
2-2.5kHz, tapering to +3-4dB by 5kHz (see
docs/audits/2026-07-17-reference-track-comparison.md).

This is deliberately narrower and more surgical than the earlier 7-band
correction that was blind-rejected (that one cut mids/presence/sibilance/air
broadly, likely dulling regions that didn't need it). One bell, centered on
the actual measured excess, on top of the validated low-shelf v2 boost.

Not a production default. One-off test.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from automix_local import run_local_automix  # noqa: E402

# Validated low-shelf (unchanged) + one new bell cut centered on the measured
# 1k-5kHz excess (peak deviation ~2.2-2.5kHz at +4.7 to +6.5dB over reference).
# Q~1.1 gives a moderately wide bell covering roughly 1.2k-4.5kHz without
# reaching down into the low-mids the shelf already fixed, or up into
# sibilance/air (6k+) which the chart shows is NOT excessive.
EQ_BANDS = [
    {
        "type": "lowshelf",
        "frequency": 300.0,
        "gain_db": 4.0,
        "q": 0.707,
        "reason": "Validated low-shelf (v2): boosts sub/bass/low-mids, no cuts",
    },
    {
        "type": "peaking",
        "frequency": 2200.0,
        "gain_db": -3.5,
        "q": 1.1,
        "reason": "Targeted cut at the measured 1k-5kHz excess (mix +4 to +6.5dB over reference, peak ~2.2-2.5kHz) -- narrower than the rejected 7-band attempt",
    },
]


def main():
    project_id = sys.argv[1] if len(sys.argv) > 1 else "stranger-presence-cut"
    print("Applying low-shelf + targeted presence cut:")
    for b in EQ_BANDS:
        print(f"  {b['frequency']:>7.0f} Hz  {b['gain_db']:+.1f} dB  q={b['q']}  ({b['type']})")

    delivery = run_local_automix(
        ROOT / "testing_track_stems" / "stranger" / "WAVs",
        genre="pop",
        target_lufs=-14.0,
        output_dir=ROOT / "artifacts" / "real_stem_validation_2026-07-15",
        project_id=project_id,
        apply_mono_compat_correction=True,
        extra_bus_eq_bands=EQ_BANDS,
    )
    print(f"\nOK: {delivery.get('zip_path')}")


if __name__ == "__main__":
    main()
