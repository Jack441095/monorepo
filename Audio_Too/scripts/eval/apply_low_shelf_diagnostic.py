#!/usr/bin/env python3
"""
Diagnostic-only: render stranger with mono-compat correction + a SINGLE
low-shelf boost (no touching mids/presence/air at all), as a more surgical
alternative to the 7-band correction that was blind-rejected
(docs/audits/2026-07-17-reference-track-comparison.md -- "the mix has ~4.1x
more relative high-end-to-low-end energy than the reference; a single broad
shelf move (boost lows ~4.5dB) closes that gap without touching 7 bands").

Not a production default. One-off test.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from automix_local import run_local_automix  # noqa: E402

# Single low-shelf boost derived from the high-to-low energy ratio finding:
# mix=4.27 vs reference=1.05 -> boost lows ~4.5dB closes the gap in one move.
# Shelf at 150Hz (top of the "bass" band, bottom of "low_mids") so it lifts
# sub+bass without reaching up into low_mids/mids where the earlier 7-band
# attempt's mid/presence/air CUTS were the likely cause of the blind rejection
# -- this diagnostic deliberately touches nothing above 150Hz.
BANDS = [
    {
        "type": "lowshelf",
        "frequency": 150.0,
        "gain_db": 4.5,
        "q": 0.707,
        "reason": "Reference-track low-end deficit: single low-shelf boost, no mid/presence/air cuts (previous 7-band attempt was blind-rejected)",
    },
]


def main():
    project_id = sys.argv[1] if len(sys.argv) > 1 else "stranger-lowshelf-only"
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
