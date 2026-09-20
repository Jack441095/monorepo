"""
SLO Master Plan V2, Phase 6 (B-007) -- cross-vendor OOD gate measurement.

Two halves:
1. False-known rate: scan fixtures/ood_negative_v1/ (real, genuinely
   out-of-taxonomy audio -- field recordings, guitar loops) and measure how
   often diagMlIsOod comes back false (the gate confidently claimed a known
   category for content that isn't one).
2. False-unknown rate: reuse the existing B-006 audio-only scan results
   (results_real_corpus_audio_only.json) -- no rescan needed -- and measure
   how often diagMlIsOod comes back true for genuinely known content.

Requires fixtures/ood_negative_v1/{*.wav,ood_negative_v1_manifest.json} to
exist (built by a one-off corpus-sampling step, see the master plan) and
results_real_corpus_audio_only.json from the B-006 benchmark run.

Usage:
    python3 run_ood_gate_analysis.py <path-to-ClassificationBenchmark-binary>
"""
import os
import sys
import json
import subprocess
from collections import Counter, defaultdict


def main():
    if len(sys.argv) < 2:
        print("Usage: run_ood_gate_analysis.py <path-to-ClassificationBenchmark-binary>")
        sys.exit(1)
    benchmark_bin = sys.argv[1]

    base_dir = os.path.dirname(os.path.abspath(__file__))
    negative_dir = os.path.join(base_dir, "fixtures", "ood_negative_v1")
    negative_manifest_path = os.path.join(negative_dir, "ood_negative_v1_manifest.json")
    audio_only_results_path = os.path.join(base_dir, "results_real_corpus_audio_only.json")
    real_corpus_manifest_path = os.path.join(base_dir, "fixtures", "real_corpus_v1", "real_corpus_v1_manifest.json")

    for p in (negative_manifest_path, audio_only_results_path, real_corpus_manifest_path):
        if not os.path.exists(p):
            print(f"FAIL: missing required artifact: {p}")
            sys.exit(1)

    # --- Half 1: false-known on genuinely OOD content ---
    print("Scanning OOD negative set...")
    negative_out = os.path.join(base_dir, "results_ood_negative.json")
    subprocess.run([benchmark_bin, "scan", negative_dir, negative_out], check=True)
    with open(negative_out) as f:
        negative_results = json.load(f)
    with open(negative_manifest_path) as f:
        negative_manifest = json.load(f)

    by_generic_name = {m["generic_name"]: m for m in negative_manifest}
    matched_negative = []
    for r in negative_results:
        m = by_generic_name.get(os.path.basename(r["filePath"]))
        if m:
            matched_negative.append((m, r))

    false_known = [(m, r) for m, r in matched_negative if not r["diagMlIsOod"]]
    by_source = defaultdict(lambda: {"total": 0, "false_known": 0})
    for m, r in matched_negative:
        by_source[m["source"]]["total"] += 1
        if not r["diagMlIsOod"]:
            by_source[m["source"]]["false_known"] += 1
    subcat_counter = Counter(r["subcategory"] for m, r in false_known)
    evidence_counter = Counter(r["winningEvidence"] for m, r in false_known)

    # --- Half 2: false-unknown on genuinely known content (reuse B-006 data) ---
    with open(audio_only_results_path) as f:
        audio_only_results = json.load(f)
    with open(real_corpus_manifest_path) as f:
        real_corpus_manifest = json.load(f)
    by_audio_name = {m["audio_only_filename"]: m for m in real_corpus_manifest}

    matched_known = []
    for r in audio_only_results:
        m = by_audio_name.get(os.path.basename(r["filePath"]))
        if m:
            matched_known.append((m, r))

    false_unknown = [(m, r) for m, r in matched_known if r["diagMlIsOod"]]
    by_class = defaultdict(lambda: {"total": 0, "false_unknown": 0})
    for m, r in matched_known:
        by_class[m["expected_subcategory"]]["total"] += 1
        if r["diagMlIsOod"]:
            by_class[m["expected_subcategory"]]["false_unknown"] += 1

    summary = {
        "false_known": {
            "matched": len(matched_negative),
            "count": len(false_known),
            "rate_pct": len(false_known) / len(matched_negative) * 100 if matched_negative else 0,
            "by_source": {k: v for k, v in by_source.items()},
            "evidence_sources": dict(evidence_counter),
            "predicted_subcategories": dict(subcat_counter.most_common()),
        },
        "false_unknown": {
            "matched": len(matched_known),
            "count": len(false_unknown),
            "rate_pct": len(false_unknown) / len(matched_known) * 100 if matched_known else 0,
            "by_class": {k: v for k, v in by_class.items()},
        },
    }

    print(f"\nFalse-known rate (genuinely OOD content): {summary['false_known']['rate_pct']:.1f}% "
          f"({summary['false_known']['count']}/{summary['false_known']['matched']})")
    print(f"False-unknown rate (genuinely known content): {summary['false_unknown']['rate_pct']:.1f}% "
          f"({summary['false_unknown']['count']}/{summary['false_unknown']['matched']})")

    summary_path = os.path.join(base_dir, "ood_gate_analysis_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to {summary_path}")
    print("See docs/classification/OOD_CROSS_VENDOR_GATE_V1_REPORT.md for the full written report.")


if __name__ == "__main__":
    main()
