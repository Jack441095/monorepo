#!/usr/bin/env python3
"""Apply measured filename/audio fusion to candidate predictions.

This creates a new review-only report. It never changes the source plan or
filesystem and keeps the original audio prediction beside the fused result.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter


TRUSTED_NAME = {
    "Kick": 0.97,
    "Hi-Hat": 0.94,
    "Snare": 0.92,
    "Clap": 0.90,
    "Crash": 0.89,
    "Percussion Loop": 1.00,
    "Drum Loop": 0.78,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--audio-confidence-cutoff", type=float, default=0.70)
    args = ap.parse_args()

    with open(args.predictions) as f:
        records = [json.loads(line) for line in f if line.strip()]
    header = records[0] if records and records[0].get("record_type") else {}
    rows = records[1:] if header else records
    changed = 0
    fused_counts = Counter()
    out_rows = []
    for row in rows:
        fused = dict(row)
        audio_class = row.get("full_taxonomy_class", "")
        audio_conf = float(row.get("full_taxonomy_confidence", 0.0))
        filename_class = row.get("filename_class", "")
        if (filename_class in TRUSTED_NAME and
                audio_conf < args.audio_confidence_cutoff):
            fused_class = filename_class
            fused_conf = TRUSTED_NAME[filename_class]
            source = "trusted_filename_override"
            reason = (f"filename class {filename_class!r} overrides audio confidence "
                      f"{audio_conf:.3f} below {args.audio_confidence_cutoff:.2f}")
        else:
            fused_class = audio_class
            fused_conf = audio_conf
            source = "full_taxonomy_audio"
            reason = "audio prediction retained"
        if fused_class != audio_class:
            changed += 1
        fused["fused_taxonomy_class"] = fused_class
        fused["fused_taxonomy_confidence"] = round(float(fused_conf), 6)
        fused["fusion_source"] = source
        fused["fusion_reason"] = reason
        fused["action"] = "review"
        fused_counts[fused_class] += 1
        out_rows.append(fused)

    out_header = dict(header)
    out_header.update({
        "record_type": "slo_full_taxonomy_fused_candidate_predictions",
        "schema_version": "1.0.0",
        "n_rows": len(out_rows),
        "fusion_audio_confidence_cutoff": args.audio_confidence_cutoff,
        "trusted_filename_precision_receipt": TRUSTED_NAME,
        "fused_rows_changed": changed,
        "fused_predicted_class_counts": dict(fused_counts),
        "safety": "fusion output is review-only; no filesystem mutation is performed",
    })
    directory = os.path.dirname(os.path.abspath(args.out)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fused_predictions_", suffix=".jsonl",
                               dir=directory, text=True)
    os.close(fd)
    try:
        with open(tmp, "w") as f:
            f.write(json.dumps(out_header, sort_keys=True) + "\n")
            for row in out_rows:
                f.write(json.dumps(row, sort_keys=True) + "\n")
        os.replace(tmp, args.out)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"wrote {args.out}: {len(out_rows)} rows")
    print(f"fusion changed {changed} rows; all actions remain review")
    print("top fused classes:", fused_counts.most_common(12))


if __name__ == "__main__":
    raise SystemExit(main())

