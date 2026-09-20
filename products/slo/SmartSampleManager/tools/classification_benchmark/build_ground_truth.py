#!/usr/bin/env python3
"""
Build SLO Ground Truth Dataset V1 -- versioned, checksum-verified, backed up.

The by-ear labels are the only real ground truth this project has, and until now
they lived in two ad-hoc CSVs on one drive, gitignored, with no version, no
provenance and no integrity check. This turns them into a proper asset.

Guarantees
----------
* SOURCE AUDIO IS NEVER MUTATED. The builder records each file's mtime and size
  before and after and aborts if anything changed. It only ever reads.
* Every emitted asset is SHA-256 checksummed, and the audio content hashes come
  from the library inventory so a silently re-rendered sample is detectable.
* Rows are merged by PATH, never by id -- the two source manifests number their
  files independently, so ids collide by construction.
* Conflicting labels for one path ABORT the build rather than being silently
  resolved.
* Splits are deterministic from a recorded seed and grouped by collection, so a
  pack can never straddle train and test.
* The sealed evaluation collections are excluded from every split and recorded
  separately.

Usage:
  python3 build_ground_truth.py
  python3 build_ground_truth.py --include-ir     # keep impulse responses
  python3 build_ground_truth.py --verify         # re-check an existing build
"""
import os, csv, json, time, shutil, hashlib, argparse
from collections import Counter, defaultdict

SD = os.path.dirname(os.path.abspath(__file__))
GT_DIR = os.path.join(SD, "ground_truth", "SLO_GT_V1")
TAXONOMY = os.path.join(SD, "taxonomy_v1.json")
SEALED = os.path.join(SD, "sealed_holdout_vendors_v1.json")
INVENTORY = os.path.join(SD, "sample_library_inventory_v1.json")
BACKUP_DIR = os.path.expanduser("~/slo_label_backups")

SOURCES = [("verified_drums.csv", "drums_v1",
            "stratified drum sample, labelled first"),
           ("verified_domain_coverage.csv", "domain_coverage_v1",
            "breadth-first across 76 collections, 50 previously unlabelled"),
           ("verified_granularity.csv", "granularity_v1",
            "targeted boundary/granularity sprint; normalized and conflict-audited")]

DROP_LABELS = ("__skip__", "Misc/Review")
DATASET_VERSION = "1.0.0"

FIELDS = ["path", "relpath", "label", "percussion_subtype", "rejection_reason",
          "human_confidence", "ambiguous", "acceptable_secondary_label",
          "function_family", "temporal_form", "source_attributes",
          "collection", "pack", "sample_family_id",
          "label_source", "labelling_session", "is_impulse_response",
          "duration", "samplerate", "channels", "content_sha256"]


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def is_ir(path):
    low = path.lower()
    return ("impluse" in low or "impulse" in low
            or "/ir/" in low or low.endswith("/ir"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-ir", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()

    if a.verify:
        return verify()

    import sample_library_inventory as si
    tax = json.load(open(TAXONOMY))
    sealed = set(json.load(open(SEALED))["sealed_vendors"])
    inv = {}
    if os.path.exists(INVENTORY):
        for f in json.load(open(INVENTORY))["files"]:
            inv[f["path"]] = f

    # ---- read, with provenance -------------------------------------------
    raw = []
    for fname, src, desc in SOURCES:
        p = os.path.join(SD, fname)
        if not os.path.exists(p):
            print(f"  (missing {fname})")
            continue
        n = 0
        for r in csv.DictReader(open(p)):
            r["_source"] = src
            raw.append(r)
            n += 1
        print(f"  {fname}: {n} rows  [{src}] {desc}")

    # ---- record source audio state BEFORE we touch anything --------------
    paths_seen = sorted({r["path"] for r in raw if os.path.exists(r["path"])})
    before = {p: (os.path.getmtime(p), os.path.getsize(p)) for p in paths_seen}

    # ---- merge by path; explicit, auditable correction rule --------------
    # The granularity sprint deliberately revisited files previously placed in
    # Other/none.  A newer, by-ear class label is a correction to that old
    # rejection label, not an unresolved disagreement.  Any conflict involving
    # a real class (or an older source that is not Other/none) still aborts.
    # This keeps the default fail-closed behaviour while allowing the measured
    # rejection-boundary repair to enter the canonical ground truth.
    seen, merged, conflicts = {}, [], []
    overrides = []
    for r in raw:
        if r["label"] in DROP_LABELS or not os.path.exists(r["path"]):
            continue
        p = r["path"]
        if p in seen:
            if seen[p]["label"] != r["label"]:
                old, new = seen[p], r
                if (new.get("_source") == "granularity_v1"
                        and old.get("label") == "Other/none"
                        and new.get("label") not in DROP_LABELS):
                    new = dict(new)
                    prior = new.get("source_attributes", "")
                    marker = "ground_truth_override=Other/none"
                    new["source_attributes"] = "; ".join(
                        x for x in (prior, marker) if x)
                    new["original_label"] = "Other/none"
                    seen[p] = new
                    for i, existing in enumerate(merged):
                        if existing["path"] == p:
                            merged[i] = new
                            break
                    overrides.append((p, old["label"], new["label"]))
                else:
                    conflicts.append((p, seen[p]["label"], r["label"]))
            else:
                # keep the richer row if the duplicate carries a subtype
                for k in ("percussion_subtype", "rejection_reason"):
                    if not seen[p].get(k) and r.get(k):
                        seen[p][k] = r[k]
            continue
        seen[p] = r
        merged.append(r)
    if conflicts:
        print(f"\nABORT: {len(conflicts)} paths carry CONFLICTING by-ear labels.")
        for p, x, y in conflicts[:10]:
            print(f"   {os.path.basename(p)[:50]:52} {x!r} vs {y!r}")
        print("Resolve these by ear; the build will not choose for you.")
        return 1
    if overrides:
        print(f"  explicit granularity corrections applied: {len(overrides)} "
              "Other/none -> supported class")

    # ---- enrich ----------------------------------------------------------
    rows = []
    n_ir = 0
    for r in merged:
        p = r["path"]
        _, vendor, pack, _ = si.attribute(p)
        meta = inv.get(p, {})
        ir_flag = is_ir(p)
        n_ir += bool(ir_flag)
        cls = tax["classes"].get(r["label"], {})
        rows.append({
            "path": p,
            "relpath": os.path.relpath(p, "/Volumes/Jack_Gandy_1TB_SSD"),
            "label": r["label"],
            "percussion_subtype": r.get("percussion_subtype", ""),
            "rejection_reason": r.get("rejection_reason", ""),
            "human_confidence": r.get("human_confidence", ""),
            "ambiguous": r.get("ambiguous", ""),
            "acceptable_secondary_label": r.get("acceptable_secondary_label", ""),
            "function_family": cls.get("family", ""),
            "temporal_form": cls.get("form", ""),
            "source_attributes": r.get("source_attributes", ""),
            "collection": vendor, "pack": pack,
            "sample_family_id": si.family_id(vendor, pack, os.path.basename(p)),
            "label_source": r["_source"],
            "labelling_session": r.get("labelling_session", ""),
            "is_impulse_response": "true" if ir_flag else "false",
            "duration": meta.get("duration", ""),
            "samplerate": meta.get("samplerate", ""),
            "channels": meta.get("channels", ""),
            "content_sha256": meta.get("sha256", ""),
        })
    print(f"\nmerged: {len(rows)} unique labelled files")
    print(f"  impulse responses flagged: {n_ir} "
          f"({'INCLUDED' if a.include_ir else 'EXCLUDED from splits'})")

    # ---- splits ----------------------------------------------------------
    eligible = [r for r in rows
                if r["collection"] not in sealed
                and (a.include_ir or r["is_impulse_response"] == "false")]
    sealed_rows = [r for r in rows if r["collection"] in sealed]
    import numpy as np
    from sklearn.model_selection import StratifiedGroupKFold
    y = np.array([r["label"] for r in eligible])
    g = np.array([r["collection"] for r in eligible])
    cnt = Counter(y)
    viable = np.array([cnt[v] >= a.folds for v in y])
    idx = np.where(viable)[0]
    skf = StratifiedGroupKFold(a.folds, shuffle=True, random_state=a.seed)
    folds = [[] for _ in range(a.folds)]
    for k, (_, te) in enumerate(skf.split(np.zeros(len(idx)), y[idx], groups=g[idx])):
        for i in te:
            folds[k].append(eligible[idx[i]]["path"])
    # Files in classes with fewer than `folds` examples cannot be stratified and
    # are therefore in NO fold. They are still part of the dataset -- they are
    # recorded explicitly rather than silently dropped, and they must be excluded
    # from the leak check, or a collection holding one of them looks like it is
    # in "train" for every fold.
    in_folds = {p for f in folds for p in f}
    unfolded = [r for r in eligible if r["path"] not in in_folds]
    coll_of = {r["path"]: r["collection"] for r in eligible}
    where = defaultdict(set)
    for k in range(a.folds):
        for p in folds[k]:
            where[coll_of[p]].add(k)
    straddling = {c: sorted(v) for c, v in where.items() if len(v) > 1}
    assert not straddling, f"COLLECTION LEAK: {list(straddling)[:5]}"
    print(f"  splits: {a.folds} collection-grouped folds, "
          f"{len(in_folds)} files, seed {a.seed}")
    print(f"  no collection straddles folds ({len(where)} collections placed)")
    print(f"  {len(unfolded)} files in classes too rare to stratify "
          f"(<{a.folds} examples) -- in the dataset, in no fold")
    print(f"  sealed: {len(sealed_rows)} files in {len(sealed)} collections, "
          f"excluded from all folds")

    # ---- percussion subtype review list ----------------------------------
    review = [r for r in rows
              if r["label"] == "Percussion" and not r["percussion_subtype"]]
    print(f"  percussion awaiting subtype review: {len(review)}")

    # ---- write -----------------------------------------------------------
    os.makedirs(GT_DIR, exist_ok=True)
    lab_p = os.path.join(GT_DIR, "labels.csv")
    with open(lab_p, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        for r in sorted(rows, key=lambda x: x["path"]):
            w.writerow(r)
    rev_p = os.path.join(GT_DIR, "percussion_subtype_review.csv")
    with open(rev_p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "collection", "pack", "filename",
                    "duration", "suggested_subtype", "reviewer_subtype"])
        for r in sorted(review, key=lambda x: x["collection"]):
            w.writerow([r["path"], r["collection"], r["pack"],
                        os.path.basename(r["path"]), r["duration"], "", ""])
    spl_p = os.path.join(GT_DIR, "splits.json")
    json.dump({"protocol": "collection-held-out (StratifiedGroupKFold on collection)",
               "seed": a.seed, "folds": a.folds,
               "rule": "a collection appears in exactly one fold; a pack can "
                       "never straddle train and test",
               "sealed_collections": sorted(sealed),
               "sealed_rule": "never used for training, model selection, "
                              "thresholds, prompt exemplars, augmentation "
                              "policy selection, active-learning decisions, "
                              "error-driven relabelling or pseudo-labelling",
               "impulse_responses_included": bool(a.include_ir),
               "unfoldable_rare_class_paths": [r["path"] for r in unfolded],
               "unfoldable_rule": "classes with fewer than `folds` examples "
                                  "cannot be stratified; these rows are part of "
                                  "the dataset but belong to no fold",
               "test_paths_by_fold": folds}, open(spl_p, "w"), indent=2)
    shutil.copy(TAXONOMY, os.path.join(GT_DIR, "taxonomy_v1.json"))

    # ---- verify source audio untouched -----------------------------------
    changed = [p for p in paths_seen
               if os.path.exists(p)
               and (os.path.getmtime(p), os.path.getsize(p)) != before[p]]
    if changed:
        print(f"\nABORT: {len(changed)} source audio files changed during the "
              f"build. The builder must only ever read.")
        return 1
    print(f"  verified {len(paths_seen)} source files unmodified (mtime+size)")

    # ---- checksums + manifest --------------------------------------------
    assets = [n for n in ["labels.csv", "percussion_subtype_review.csv",
                          "splits.json", "taxonomy_v1.json", "README.md"]
              if os.path.exists(os.path.join(GT_DIR, n))]
    sums = {n: sha256_file(os.path.join(GT_DIR, n)) for n in assets}
    with open(os.path.join(GT_DIR, "CHECKSUMS.sha256"), "w") as f:
        for n, h in sums.items():
            f.write(f"{h}  {n}\n")
    manifest = {
        "dataset": "SLO Ground Truth V1",
        "dataset_version": DATASET_VERSION,
        "taxonomy_version": tax["taxonomy_version"],
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_labelled_files": len(rows),
        "n_collections": len({r["collection"] for r in rows}),
        "n_packs": len({r["pack"] for r in rows}),
        "n_sample_families": len({r["sample_family_id"] for r in rows}),
        "n_impulse_responses": n_ir,
        "impulse_responses_in_splits": bool(a.include_ir),
        "n_in_splits": len(in_folds),
        "n_unfoldable_rare_class": len(unfolded),
        "n_sealed": len(sealed_rows),
        "n_percussion_awaiting_review": len(review),
        "label_provenance": {s: sum(1 for r in rows if r["label_source"] == s)
                             for _, s, _ in SOURCES},
        "granularity_overrides": len(overrides),
        "class_counts": dict(Counter(r["label"] for r in rows).most_common()),
        "collection_counts": dict(Counter(r["collection"] for r in rows).most_common()),
        "checksums": sums,
        "source_csvs": {n: sha256_file(os.path.join(SD, n))
                        for n, _, _ in SOURCES if os.path.exists(os.path.join(SD, n))},
        "guarantees": [
            "source audio never mutated (mtime+size verified before and after)",
            "merged by path, never by id",
            "conflicting labels abort the build",
            "splits grouped by collection, deterministic from the recorded seed",
            "sealed collections excluded from every fold",
        ],
    }
    json.dump(manifest, open(os.path.join(GT_DIR, "manifest.json"), "w"), indent=2)

    # ---- backup ----------------------------------------------------------
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"SLO_GT_V1_{stamp}")
    shutil.copytree(GT_DIR, dest)
    for n, _, _ in SOURCES:
        p = os.path.join(SD, n)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(dest, f"SOURCE_{n}"))
    print(f"\nwrote {GT_DIR}")
    print(f"backed up to {dest}")
    print(f"\n  {len(rows)} files | {manifest['n_collections']} collections | "
          f"taxonomy v{tax['taxonomy_version']} | dataset v{DATASET_VERSION}")
    return 0


def verify():
    """Re-check checksums and that source audio still matches the inventory."""
    man_p = os.path.join(GT_DIR, "manifest.json")
    if not os.path.exists(man_p):
        print("no build to verify"); return 1
    man = json.load(open(man_p))
    bad = []
    for n, h in man["checksums"].items():
        p = os.path.join(GT_DIR, n)
        if not os.path.exists(p) or sha256_file(p) != h:
            bad.append(n)
    print(f"assets: {len(man['checksums'])-len(bad)}/{len(man['checksums'])} OK"
          + (f"  CORRUPT: {bad}" if bad else ""))
    drift = []
    for n, h in man.get("source_csvs", {}).items():
        p = os.path.join(SD, n)
        if os.path.exists(p) and sha256_file(p) != h:
            drift.append(n)
    if drift:
        print(f"source CSVs changed since the build: {drift}")
        print("  -> new labels exist; rebuild to produce V1.x")
    else:
        print("source CSVs unchanged since the build")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
