#!/usr/bin/env python3
"""
Diagnostic-only: combine the two validated/plausible pieces toward matching
the reference master more holistically, per Jack's direction ("get the
mixdown looking more like the reference track... feels thin, lack of low-
mids... overall seems okay, a lot of high end"):

1. The low-shelf boost (v2: 300Hz corner, +4.0dB) -- validated by blind
   listening ("B is great"), refined to properly cover low-mids.
2. The master bus glue compressor tightened toward the reference's measured
   density, using dynamics_comparison()'s own suggested settings (never
   tested until now) -- addresses the "waveform is different" / density gap
   (median RMS -18.2dB vs reference -11.6dB) rather than more EQ.

No mid/presence/air cuts (that approach was already blind-rejected). This is
diagnostic only -- not a production default.
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
]

# From reference_track_comparison.py's dynamics_comparison() against
# Stromae/Pomme: mix crest factor 13.6-14.3dB vs reference 10.4dB.
# makeup_gain_db corrected empirically (see docs/audits/2026-07-17-reference-
# track-comparison.md "Root cause found" section): the tool's own heuristic
# (1.2dB) badly undershot what this threshold/ratio combination actually
# needs on real program material (~8.6dB, measured directly via
# scripts/eval/trace_density_chain.py) -- also only works now that
# mix_renderer.py's master glue-compressor stage actually applies
# makeup_gain_db at all (it silently discarded it before this session's fix).
BUS_COMPRESSOR = {
    "ratio": 3.0,
    "attack_ms": 10.0,
    "release_ms": 150.0,
    "threshold_db": -19.6,
    "makeup_gain_db": 8.6,
}


def main():
    project_id = sys.argv[1] if len(sys.argv) > 1 else "stranger-combined-refmatch"
    print("Applying low-shelf EQ + reference-derived bus compressor:")
    for b in EQ_BANDS:
        print(f"  EQ: {b['frequency']:>7.0f} Hz  {b['gain_db']:+.1f} dB  ({b['type']})")
    print(f"  Compressor: {BUS_COMPRESSOR}")

    delivery = run_local_automix(
        ROOT / "testing_track_stems" / "stranger" / "WAVs",
        genre="pop",
        target_lufs=-14.0,
        output_dir=ROOT / "artifacts" / "real_stem_validation_2026-07-15",
        project_id=project_id,
        apply_mono_compat_correction=True,
        extra_bus_eq_bands=EQ_BANDS,
        bus_compressor_override=BUS_COMPRESSOR,
    )
    print(f"\nOK: {delivery.get('zip_path')}")


if __name__ == "__main__":
    main()
