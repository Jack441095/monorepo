#!/usr/bin/env python3
"""
Tests for SLO Ground Truth V1.

A dataset asset is worth exactly what its verification is worth. These check the
properties every downstream accuracy claim silently depends on.

Run:  python3 test_ground_truth.py
"""
import os, csv, sys, json, hashlib
from collections import Counter

SD = os.path.dirname(os.path.abspath(__file__))
GT = os.path.join(SD, "ground_truth", "SLO_GT_V1")
FAILED = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    man = json.load(open(os.path.join(GT, "manifest.json")))
    rows = list(csv.DictReader(open(os.path.join(GT, "labels.csv"))))
    spl = json.load(open(os.path.join(GT, "splits.json")))
    tax = json.load(open(os.path.join(GT, "taxonomy_v1.json")))
    print(f"SLO GT v{man['dataset_version']} / taxonomy "
          f"v{man['taxonomy_version']} / {len(rows)} rows\n")

    print("1. integrity")
    bad = [n for n, h in man["checksums"].items()
           if not os.path.exists(os.path.join(GT, n)) or sha(os.path.join(GT, n)) != h]
    check("every asset checksum matches", not bad, str(bad))
    check("manifest count matches labels.csv",
          man["n_labelled_files"] == len(rows), f"{man['n_labelled_files']} vs {len(rows)}")

    print("\n2. no duplicates, no empties")
    paths = [r["path"] for r in rows]
    check("paths unique", len(set(paths)) == len(paths),
          f"{len(paths)-len(set(paths))} dupes")
    check("no empty label", all(r["label"] for r in rows))
    check("no empty collection", all(r["collection"] for r in rows))
    check("no empty sample_family_id", all(r["sample_family_id"] for r in rows))

    print("\n3. taxonomy conformance")
    unknown = {r["label"] for r in rows} - set(tax["classes"])
    check("every label defined in the taxonomy", not unknown, str(sorted(unknown)))
    subs = set(tax["classes"]["Percussion"]["subtypes"])
    badsub = {r["percussion_subtype"] for r in rows
              if r["percussion_subtype"] and r["percussion_subtype"] not in subs}
    check("percussion subtypes are all defined", not badsub, str(badsub))
    badreason = {r["rejection_reason"] for r in rows
                 if r["rejection_reason"]
                 and r["rejection_reason"] not in tax["rejection_reasons"]}
    check("rejection reasons are all defined", not badreason, str(badreason))
    check("Other/none marked rejection_by_design",
          tax["classes"]["Other/none"]["status"] == "rejection_by_design")
    check("Foley marked provenance, not acoustic",
          tax["classes"]["Foley"]["status"] == "provenance_not_acoustic")

    print("\n4. splits: no collection straddles a fold")
    coll = {r["path"]: r["collection"] for r in rows}
    where = {}
    leaks = []
    for k, fold in enumerate(spl["test_paths_by_fold"]):
        for p in fold:
            c = coll[p]
            if c in where and where[c] != k:
                leaks.append(c)
            where[c] = k
    check("no collection appears in two folds", not leaks,
          f"{len(set(leaks))} straddling")
    infold = [p for f in spl["test_paths_by_fold"] for p in f]
    check("no path appears in two folds", len(set(infold)) == len(infold))

    print("\n5. sealed set is genuinely sealed")
    sealed = set(spl["sealed_collections"])
    inf = {coll[p] for p in infold}
    check("no sealed collection in any fold", not (sealed & inf),
          str(sealed & inf))
    check("sealed set non-empty", len(sealed) >= 3, f"{len(sealed)}")
    n_sealed = sum(1 for r in rows if r["collection"] in sealed)
    check("sealed rows present in the dataset", n_sealed > 0, f"{n_sealed} rows")

    print("\n6. impulse responses excluded but retained")
    irs = [r for r in rows if r["is_impulse_response"] == "true"]
    check("IRs retained in the dataset", len(irs) == man["n_impulse_responses"],
          f"{len(irs)}")
    check("no IR in any fold",
          not ({r["path"] for r in irs} & set(infold)))
    check("IR labels preserved, not blanked", all(r["label"] for r in irs),
          f"labels: {dict(Counter(r['label'] for r in irs))}")

    print("\n7. source audio untouched")
    missing = [r["path"] for r in rows if not os.path.exists(r["path"])][:3]
    check("every labelled file still exists", not missing, str(missing))

    print("\n8. review list")
    rev = list(csv.DictReader(open(os.path.join(GT, "percussion_subtype_review.csv"))))
    need = [r for r in rows if r["label"] == "Percussion"
            and not r["percussion_subtype"]]
    check("review list matches unlabelled Percussion rows",
          len(rev) == len(need), f"{len(rev)} vs {len(need)}")
    check("review list has an empty column for the reviewer",
          all(r["reviewer_subtype"] == "" for r in rev))

    print("\n9. backup exists off the sample drive")
    bk = os.path.expanduser("~/slo_label_backups")
    builds = [d for d in os.listdir(bk)] if os.path.isdir(bk) else []
    check("a backup of this dataset exists",
          any(d.startswith("SLO_GT_V1_") for d in builds),
          f"{sum(d.startswith('SLO_GT_V1_') for d in builds)} builds")
    check("backup is NOT on the sample drive",
          not bk.startswith("/Volumes/Jack_Gandy_1TB_SSD"), bk)

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: {FAILED}")
        return 1
    print("all ground truth tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
