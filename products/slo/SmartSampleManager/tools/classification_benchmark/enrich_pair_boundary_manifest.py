#!/usr/bin/env python3
"""Add concise physical-waveform evidence to the boundary labelling hints."""
from __future__ import annotations

import argparse
import csv
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-queue", default=None,
                    help="optional CSV copy with waveform evidence columns")
    args = ap.parse_args()

    import numpy as np
    import acoustic_evidence as ae

    source_rows = list(csv.DictReader(open(args.queue)))
    queue = {os.path.abspath(r["path"]): r for r in source_rows}
    z = np.load(args.manifest, allow_pickle=True)
    names = list(z["paths"])
    have = {os.path.abspath(str(p)): i for i, p in enumerate(names)}
    rows = []
    enriched = []
    evidence_fields = ["waveform_evidence", "attack_ms", "decay_seconds",
                       "sub_energy_ratio", "pitch_drop_cents",
                       "beating_rate_hz", "spectral_purity", "harmonicity",
                       "transient_strength", "noise_tonal_ratio", "stereo_width"]
    missing = 0
    for path, row in queue.items():
        if path not in have:
            missing += 1
            waveform = "no readable waveform evidence"
            values = {k: "" for k in evidence_fields[1:]}
        else:
            ev = {n: float(z["F"][have[path], j]) for j, n in enumerate(ae.NAMES)}
            waveform = ae.describe(ev)
            values = {k: round(ev[k], 6) for k in evidence_fields[1:]}
        hint = (f"audio: {row.get('full_taxonomy_class','')} | "
                f"filename: {row.get('filename_class','')} | "
                f"waveform: {waveform}")
        rows.append({"id": len(rows), "path": path, "hint": hint})
        enriched_row = dict(row)
        enriched_row["waveform_evidence"] = waveform
        enriched_row.update(values)
        enriched.append(enriched_row)
    with open(args.out, "w") as f:
        json.dump(rows, f, indent=2)
    if args.out_queue:
        fields = list(source_rows[0].keys()) + evidence_fields if source_rows else evidence_fields
        with open(args.out_queue, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(fields)))
            w.writeheader()
            w.writerows(enriched)
        print(f"wrote {args.out_queue}: {len(enriched)} rows")
    print(f"wrote {args.out}: {len(rows)} items; missing_waveform={missing}")


if __name__ == "__main__":
    raise SystemExit(main())
