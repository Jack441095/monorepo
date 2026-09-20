#!/usr/bin/env python3
"""
Diagnostic-only: alternative to the 2.2kHz presence CUT
(apply_presence_cut_diagnostic.py). Reconciled measurement showed the
"1k-5kHz excess" isn't genuine absolute excess at 2.2kHz -- the reference's
2.2kHz level is actually slightly LOWER than ours in absolute terms. The real
difference: the reference has a much bigger, more prominent ~1kHz peak
(+3.3dB absolute vs our mix) that rolls off steeply after; our mix is
comparatively flat through that region. The perceived "hot highs" at
2-2.5kHz is a RELATIVE effect from missing body around 1kHz, not excess up
there (see docs/audits/2026-07-17-reference-track-comparison.md).

This tests the alternative: BOOST body around 900Hz-1kHz (consistent with
the "boost, don't cut" principle validated all session -- the low-shelf was
the only correction that won blind listening) rather than cutting the highs.
Leaves everything above ~1.5kHz untouched.

Not a production default. One-off test, for direct comparison against the
presence-cut diagnostic.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from automix_local import run_local_automix  # noqa: E402

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
        "frequency": 900.0,
        "gain_db": 2.5,
        "q": 1.0,
        "reason": "Body boost filling the measured ~1kHz gap vs reference (reference +3.3dB absolute there); alternative to cutting 2.2kHz",
    },
]


def main():
    project_id = sys.argv[1] if len(sys.argv) > 1 else "stranger-body-boost"
    print("Applying low-shelf + body boost:")
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
