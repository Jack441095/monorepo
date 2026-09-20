#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
from collections import Counter
from pathlib import Path

PACKS_ROOT = Path("/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing")
BENCHMARK_BIN = Path("/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/_build/ssm-qualification/ClassificationBenchmark")
OUT_DIR = Path("/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/benchmark_reports")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Select a representative set of high-density packs across diverse genres and producers
TARGET_PACKS = [
    "Capsun ProAudio - City Pop",
    "Koan Sound",
    "IMANU",
    "Organic Electronics 2 J.Views",
    "Black Octopus Sound - Pure Analog Sweeps IV (2021)",
    "Minimal Audio",
    "Drum Recollection",
    "Loaded Samples - Lo-Fi Memphis 2",
    "Breaks",
    "Organic Drum Kit"
]

def run_pack(pack_name: str):
    pack_path = PACKS_ROOT / pack_name
    if not pack_path.exists():
        print(f"Skipping {pack_name} (not found)")
        return None
    
    out_json = OUT_DIR / f"{pack_name.replace(' ', '_').replace('-', '_')}_results.json"
    
    print(f"\n=======================================================")
    print(f"Scanning Pack: {pack_name}")
    print(f"Path: {pack_path}")
    print(f"Output: {out_json}")
    print(f"=======================================================")
    
    t0 = time.time()
    cmd = [str(BENCHMARK_BIN), "scan", str(pack_path), str(out_json)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.time() - t0
    
    if res.returncode != 0:
        print(f"FAIL ({res.returncode}): {res.stderr}")
        return None
    
    if not out_json.exists():
        print(f"FAIL: Output file not created: {out_json}")
        return None
        
    with open(out_json, "r") as f:
        data = json.load(f)
        
    n_samples = len(data)
    cats = Counter(d.get("category", "Unclassified") for d in data)
    subcats = Counter(d.get("subcategory", "Unclassified") for d in data)
    evidences = Counter(d.get("winningEvidence", "UNKNOWN") for d in data)
    ood_count = sum(1 for d in data if d.get("diagMlIsOod", False))
    overrides = sum(1 for d in data if d.get("diagMlOverrideApplied", False))
    confidences = [d.get("tagConfidence", 0.0) for d in data]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    
    print(f"Scanned {n_samples} samples in {dt:.2f}s ({n_samples/max(dt, 0.001):.1f} samples/sec)")
    print(f"Top Categories: {dict(cats.most_common(4))}")
    print(f"Top Subcategories: {dict(subcats.most_common(5))}")
    print(f"Evidence: {dict(evidences.most_common(4))}")
    print(f"OOD Rate: {ood_count}/{n_samples} ({ood_count/n_samples*100:.1f}%) | ML Overrides: {overrides} ({overrides/n_samples*100:.1f}%) | Mean Conf: {avg_conf:.3f}")
    
    return {
        "pack_name": pack_name,
        "sample_count": n_samples,
        "duration_seconds": dt,
        "samples_per_second": n_samples / max(dt, 0.001),
        "categories": dict(cats),
        "subcategories": dict(subcats),
        "evidences": dict(evidences),
        "ood_count": ood_count,
        "ood_percentage": (ood_count / n_samples * 100) if n_samples else 0.0,
        "ml_overrides": overrides,
        "mean_confidence": avg_conf
    }

def main():
    print(f"Starting Multi-Vendor Benchmark Suite...")
    reports = []
    
    for pack in TARGET_PACKS:
        rep = run_pack(pack)
        if rep:
            reports.append(rep)
            
    summary_path = OUT_DIR / "multivendor_benchmark_summary.json"
    with open(summary_path, "w") as f:
        json.dump(reports, f, indent=2)
        
    total_samples = sum(r["sample_count"] for r in reports)
    total_time = sum(r["duration_seconds"] for r in reports)
    total_ood = sum(r["ood_count"] for r in reports)
    total_overrides = sum(r["ml_overrides"] for r in reports)
    
    print(f"\n=======================================================")
    print(f"MULTI-VENDOR BENCHMARK COMPLETED")
    print(f"Total Packs Evaluated: {len(reports)}")
    print(f"Total Samples Classified: {total_samples}")
    print(f"Total Scan & Inference Time: {total_time:.2f}s ({total_samples/max(total_time, 0.001):.1f} samples/sec overall)")
    print(f"Aggregate OOD Rate: {total_ood}/{total_samples} ({total_ood/total_samples*100:.2f}%)")
    print(f"Total ML Overrides: {total_overrides}/{total_samples} ({total_overrides/total_samples*100:.2f}%)")
    print(f"Full Summary Saved: {summary_path}")
    print(f"=======================================================")

if __name__ == "__main__":
    main()

