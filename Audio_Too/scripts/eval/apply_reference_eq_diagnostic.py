#!/usr/bin/env python3
"""
Diagnostic-only: render stranger with a master-bus EQ correction derived from
a reference_track_comparison.py report, on top of the mono-compat correction
(the best current baseline). Not a production default — a one-off test to see
whether closing the measured tonal-balance gap actually helps, before any
permanent change or listening promotion.

Usage:
    python3 scripts/eval/apply_reference_eq_diagnostic.py <report.json> <project_id>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from automix_local import run_local_automix  # noqa: E402

# 7-band -> representative center frequency (geometric mean of each band's
# range in genre_profiles.map_40_to_7_bands), q=1.0 for a musical, non-narrow
# correction -- same shape as the existing verbal-feedback EQ mechanism in
# mix_decision_engine.py.
BAND_CENTERS_HZ = {
    "sub": 35.0,
    "bass": 95.0,
    "low_mids": 245.0,
    "mids": 895.0,
    "presence": 3465.0,
    "sibilance": 6930.0,
    "air": 11310.0,
}


def bands_from_report(report_path: Path) -> list[dict]:
    report = json.loads(report_path.read_text())
    gains = report["tonal_balance"]["suggested_eq_gains_db"]
    bands = []
    for band_name, gain_db in gains.items():
        if abs(gain_db) < 0.2:
            continue
        bands.append({
            "type": "peaking",
            "frequency": BAND_CENTERS_HZ[band_name],
            "gain_db": gain_db,
            "q": 1.0,
            "reason": f"Reference-track tonal correction: {band_name} band, from {report_path.name}",
        })
    return bands


def main():
    if len(sys.argv) < 3:
        print("Usage: apply_reference_eq_diagnostic.py <report.json> <project_id>")
        sys.exit(1)

    report_path = Path(sys.argv[1]).expanduser().resolve()
    project_id = sys.argv[2]

    bands = bands_from_report(report_path)
    print(f"Applying {len(bands)} master-bus EQ bands derived from {report_path.name}:")
    for b in bands:
        print(f"  {b['frequency']:>7.0f} Hz  {b['gain_db']:+.1f} dB")

    delivery = run_local_automix(
        ROOT / "testing_track_stems" / "stranger" / "WAVs",
        genre="pop",
        target_lufs=-14.0,
        output_dir=ROOT / "artifacts" / "real_stem_validation_2026-07-15",
        project_id=project_id,
        apply_mono_compat_correction=True,
        extra_bus_eq_bands=bands,
    )
    print(f"\nOK: {delivery.get('zip_path')}")


if __name__ == "__main__":
    main()
