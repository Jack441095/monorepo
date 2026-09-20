#!/usr/bin/env python3
"""
Domain-coverage labelling allocation.

The earlier active-learning simulation compared uncertainty, embedding
diversity, class balancing and random selection WITHIN the already-labelled
population, and found no difference. That result stands, but it answered a
narrower question than it appeared to: it never tested breadth across unseen
collections, because there were no unseen collections inside the pool it drew
from.

Phase 1 changed the question. Unseen-vendor accuracy is ~10pp below random-CV
accuracy, and the inventory shows 54 of 84 collections have zero by-ear labels
while 55% of existing labels come from three collections. The plausible reason
more labels help is no longer "more data" -- it is "more DOMAINS".

This builds a labelling manifest that maximises collection coverage rather than
file count, and seals a held-out set that must never be used for model
selection.

Selection rules
---------------
* breadth first: every eligible pack contributes before any pack contributes a
  second file
* exact duplicates are excluded outright (43.5% of the library is redundant, so
  ignoring this would waste roughly half the budget)
* only one file per normalised sample family, so velocity layers and round
  robins cannot consume the budget
* adjacent numbered variants are therefore excluded by construction
* the natural deployment distribution is preserved -- classes are NOT forced to
  equal counts, because the product meets libraries as they are
* files with no filename evidence are deliberately included, since that is the
  population the classifier actually decides
* a sealed vendor-held-out set is reserved and written separately

Usage:
  python3 labelling_allocation.py --n 600
  python3 labelling_allocation.py --n 600 --emit-manifest
"""
import os, re, json, random, argparse
from collections import defaultdict, Counter

SD = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.abspath(os.path.join(SD, "..", "..", "docs", "classification"))
INV = os.path.join(SD, "sample_library_inventory_v1.json")
OUT_PLAN = os.path.join(SD, "labelling_allocation_v1.json")
OUT_MANIFEST = os.path.join(SD, "label_manifest_domain_coverage.json")
OUT_SEALED = os.path.join(SD, "sealed_holdout_vendors_v1.json")
REPORT = os.path.join(DOCS, "SLO_LABELLING_ALLOCATION_V1.md")

# collections reserved as a permanently sealed evaluation set. Chosen to span
# large/small and electronic/acoustic rather than to flatter any model, and
# fixed here so the choice cannot drift with results.
SEALED_VENDORS = ["Drum Recollection", "Minimal Audio",
                  "Old Movies 1 - Vintage Collection (Drum Kit)"]


def load_labelled():
    import csv
    lab = set()
    p = os.path.join(SD, "verified_drums.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            if r["label"] not in ("__skip__", "Misc/Review"):
                lab.add(r["path"])
    return lab


def has_filename_evidence(name):
    try:
        import name_detect as nd
        c, _ = nd.detect(name)
        return c is not None
    except Exception:
        return bool(re.search(r"kick|snare|hat|clap|perc|crash|tom|rim|loop",
                              name, re.I))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--emit-manifest", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(INV):
        raise SystemExit("run sample_library_inventory.py first")
    inv = json.load(open(INV))
    files = inv["files"]
    dups = inv["duplicate_groups"]
    labelled = load_labelled()
    rng = random.Random(a.seed)

    # every file that is a redundant copy of another (keep one representative)
    redundant = set()
    for group in dups.values():
        for p in sorted(group)[1:]:
            redundant.add(p)

    labv = Counter()
    for p in labelled:
        import sample_library_inventory as si
        labv[si.attribute(p)[1]] += 1

    # eligible pool
    seen_family = set()
    by_pack = defaultdict(list)
    for f in files:
        if f["path"] in labelled or f["path"] in redundant:
            continue
        if f["vendor"] in SEALED_VENDORS:
            continue
        if not f.get("readable"):
            continue
        d = f.get("duration") or 0
        if d < 0.05 or d > 45:
            continue
        if f["family"] in seen_family:
            continue                       # one file per sample family
        seen_family.add(f["family"])
        by_pack[f["pack"]].append(f)

    for v in by_pack.values():
        rng.shuffle(v)

    # breadth-first round robin, unlabelled vendors first
    packs = sorted(by_pack, key=lambda p: (labv.get(by_pack[p][0]["vendor"], 0),
                                           -len(by_pack[p]), p))
    chosen, r = [], 0
    while len(chosen) < a.n:
        added = 0
        for pk in packs:
            if r < len(by_pack[pk]):
                chosen.append(by_pack[pk][r])
                added += 1
                if len(chosen) >= a.n:
                    break
        if added == 0:
            break
        r += 1

    cv = Counter(c["vendor"] for c in chosen)
    cp = Counter(c["pack"] for c in chosen)
    new_vendors = [v for v in cv if v not in labv]
    no_ev = sum(1 for c in chosen if not has_filename_evidence(c["filename"]))

    print(f"eligible pool: {sum(len(v) for v in by_pack.values()):,} files "
          f"across {len(by_pack)} packs")
    print(f"  (excluded {len(redundant):,} redundant duplicates, "
          f"{len(labelled)} already labelled, "
          f"{sum(1 for f in files if f['vendor'] in SEALED_VENDORS):,} sealed)")
    print(f"\nselected {len(chosen)} files")
    print(f"  vendors covered      {len(cv)}   (of which NEW: {len(new_vendors)})")
    print(f"  packs covered        {len(cp)}")
    print(f"  max files per pack   {max(cp.values()) if cp else 0}")
    print(f"  no filename evidence {no_ev} ({100*no_ev/max(len(chosen),1):.0f}%)")
    print(f"\nsealed evaluation vendors (never used for selection or tuning):")
    for v in SEALED_VENDORS:
        n = sum(1 for f in files if f["vendor"] == v)
        print(f"  {n:6,}  {v}")

    plan = {"n_requested": a.n, "n_selected": len(chosen), "seed": a.seed,
            "vendors_covered": len(cv), "new_vendors": sorted(new_vendors),
            "packs_covered": len(cp),
            "excluded_redundant": len(redundant),
            "sealed_vendors": SEALED_VENDORS,
            "no_filename_evidence": no_ev,
            "per_vendor": dict(cv.most_common())}
    json.dump(plan, open(OUT_PLAN, "w"), indent=2)
    json.dump({"sealed_vendors": SEALED_VENDORS,
               "rule": "never use for model selection, thresholds, prompt "
                       "exemplars or error-driven relabelling"},
              open(OUT_SEALED, "w"), indent=2)

    if a.emit_manifest:
        items = [{"path": c["path"], "hint": "", "id": i}
                 for i, c in enumerate(chosen)]
        json.dump(items, open(OUT_MANIFEST, "w"))
        print(f"\nwrote {os.path.basename(OUT_MANIFEST)} "
              f"-- label with:\n  python3 label_tool.py --set drums --port 8749")
    print(f"wrote {os.path.basename(OUT_PLAN)}")

    write_report(plan, cv, labv, files)
    print(f"wrote {REPORT}")


def write_report(plan, cv, labv, files):
    L = []
    A = L.append
    A("# SLO Labelling Allocation — V1 (domain coverage)\n")
    A("## Why this differs from the previous conclusion\n")
    A("The earlier simulation compared uncertainty, diversity, class balancing "
      "and random selection and found no difference, so the conclusion recorded "
      "was \"label in any order\". That result stands for the question it asked, "
      "but it drew its pool from the already-labelled population — it could not "
      "test breadth across unseen collections, because there were none in the "
      "pool.\n")
    A("Phase 1 changed the question. Unseen-vendor accuracy is ~10pp below "
      "random-CV accuracy, 55% of existing labels come from three collections, "
      "and **54 of 84 collections have no by-ear labels at all**. The reason to "
      "expect more labels to help is no longer volume — it is domain coverage.\n")
    A("## The allocation\n")
    A("| | |")
    A("|---|---|")
    A(f"| files selected | {plan['n_selected']} |")
    A(f"| vendors covered | {plan['vendors_covered']} |")
    A(f"| **collections never labelled before** | **{len(plan['new_vendors'])}** |")
    A(f"| packs covered | {plan['packs_covered']} |")
    A(f"| with no filename evidence | {plan['no_filename_evidence']} |")
    A(f"| redundant duplicates excluded from the pool | {plan['excluded_redundant']:,} |")
    A("\n## Selection rules\n")
    A("* **Breadth first.** Every eligible pack contributes one file before any "
      "pack contributes a second.\n")
    A("* **Exact duplicates excluded.** 43.5% of the library is byte-identical "
      "redundancy; ignoring it would waste roughly half the budget.\n")
    A("* **One file per normalised sample family**, so velocity layers and round "
      "robins cannot consume the budget. Adjacent numbered variants are excluded "
      "by construction.\n")
    A("* **Natural distribution preserved.** Classes are not forced to equal "
      "counts — the product meets libraries as they are.\n")
    A("* **Files with no filename evidence are included**, since that is the "
      "population the classifier actually decides.\n")
    A("\n## Sealed evaluation set\n")
    A("These collections are reserved and must never be used for model "
      "selection, threshold fitting, prompt exemplars or error-driven "
      "relabelling:\n")
    for v in plan["sealed_vendors"]:
        n = sum(1 for f in files if f["vendor"] == v)
        A(f"* `{v}` — {n:,} files")
    A("\n## What to measure next\n")
    A("Acquisition policies must be compared on **vendor-held-out learning "
      "curves**, not random CV. The prior finding that selection strategy does "
      "not matter was measured under random CV, which Phase 1 shows is the wrong "
      "metric. Whether breadth beats random remains genuinely open until "
      "measured that way.\n")
    A("## Reproduction\n")
    A("```\npython3 labelling_allocation.py --n 600 --emit-manifest\n```\n")
    os.makedirs(DOCS, exist_ok=True)
    open(REPORT, "w").write("\n".join(L))


if __name__ == "__main__":
    main()
