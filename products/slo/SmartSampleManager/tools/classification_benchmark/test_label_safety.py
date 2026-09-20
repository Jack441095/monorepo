#!/usr/bin/env python3
"""
Task 4 -- label asset safety tests.

These fail loudly if the ground truth becomes vulnerable again.
"""
import os, sys, csv, json, subprocess, hashlib
SD = os.path.dirname(os.path.abspath(__file__))
CRITICAL = ["verified_drums.csv", "verified_domain_coverage.csv",
            "verified_percussion_subtype.csv",
            "verified_percussion_corrections.csv"]
FAILED = []


def check(n, c, d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}" + (f"  -- {d}" if d else ""))
    if not c:
        FAILED.append(n)


def main():
    print("label asset safety:\n")
    for f in CRITICAL:
        p = os.path.join(SD, f)
        if not os.path.exists(p):
            continue
        ig = subprocess.run(["git", "check-ignore", "-q", p],
                            capture_output=True).returncode == 0
        check(f"{f} is not gitignored", not ig)
    gt = os.path.join(SD, "ground_truth", "SLO_GT_V1")
    check("versioned dataset exists", os.path.isdir(gt))
    man = json.load(open(os.path.join(gt, "manifest.json")))
    check("dataset carries per-asset checksums", bool(man.get("checksums")))
    check("dataset records label provenance", bool(man.get("label_provenance")))
    rows = list(csv.DictReader(open(os.path.join(gt, "labels.csv"))))
    check("every row has a collection", all(r["collection"] for r in rows))
    check("every row has a label source", all(r["label_source"] for r in rows))
    check("no duplicate paths", len({r["path"] for r in rows}) == len(rows))
    bk = os.path.expanduser("~/slo_label_backups")
    n = len([d for d in os.listdir(bk)]) if os.path.isdir(bk) else 0
    check("off-drive backups exist", n > 0, f"{n} items")
    check("backups are NOT on the sample drive",
          not bk.startswith("/Volumes/Jack_Gandy_1TB_SSD"))
    # Optional granularity normalisation is deliberately outside the frozen
    # v1 dataset, but when present it must remain path-unique and auditable.
    norm = os.path.join(SD, "verified_granularity.csv")
    if os.path.exists(norm):
        nrows = list(csv.DictReader(open(norm)))
        check("normalized granularity rows have provenance",
              all(r.get("_origin") for r in nrows))
        check("normalized granularity has no duplicate paths",
              len({r.get("path") for r in nrows}) == len(nrows))
        held = os.path.join(SD, "verified_granularity_HELD.csv")
        dropped = os.path.join(SD, "verified_granularity_DROPPED.csv")
        check("held taxonomy-gap export is preserved", os.path.exists(held))
        check("dropped no-info export is preserved", os.path.exists(dropped))
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: {FAILED}"); return 1
    print("all label safety tests passed"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
