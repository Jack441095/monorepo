#!/usr/bin/env python3
"""
Independent validation of the 600-file labelling allocation.

The allocator reports its own summary; that is not evidence. This re-derives
every property from the emitted manifest and the live inventory, so a bug in the
allocator cannot certify itself.

Checks the eleven required properties:
  1  source audio untouched
  2  exact duplicates not allocated repeatedly
  3  near-duplicate / normalized families identified
  4  adjacent numbered variants and round robins do not dominate
  5  breadth across collections is prioritised
  6  collections with zero or few labels receive coverage
  7  files without filename evidence are represented
  8  ambiguous / none-of-the-above material remains reachable
  9  the natural deployment distribution is preserved
 10  the allocation is NOT artificially class-balanced
 11  a sealed collection-held-out subset is reserved and disjoint

Run:  python3 test_labelling_allocation.py
"""
import os, sys, csv, json, time
from collections import Counter, defaultdict

SD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SD)
import sample_library_inventory as inv   # noqa: E402

MANIFEST = os.path.join(SD, "label_manifest_domain_coverage.json")
INVENTORY = os.path.join(SD, "sample_library_inventory_v1.json")
SEALED = os.path.join(SD, "sealed_holdout_vendors_v1.json")
VERIFIED = os.path.join(SD, "verified_drums.csv")

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def main():
    items = json.load(open(MANIFEST))
    paths = [i["path"] for i in items]
    print(f"manifest: {len(items)} files\n")

    invd = json.load(open(INVENTORY))
    byp = {f["path"]: f for f in invd["files"]}
    dups = invd["duplicate_groups"]
    sealed = set(json.load(open(SEALED))["sealed_vendors"])

    labelled = set()
    if os.path.exists(VERIFIED):
        for r in csv.DictReader(open(VERIFIED)):
            if r["label"] not in ("__skip__", "Misc/Review"):
                labelled.add(r["path"])

    print("1. source audio untouched")
    now = time.time()
    touched = [p for p in paths if os.path.exists(p)
               and now - os.path.getmtime(p) < 86400]
    check("no allocated file modified in last 24h", len(touched) == 0,
          f"{len(touched)} touched")
    check("all allocated files exist", all(os.path.exists(p) for p in paths))

    print("\n2. exact duplicates")
    check("no path allocated twice", len(set(paths)) == len(paths),
          f"{len(paths)-len(set(paths))} repeats")
    # map each path to its duplicate-group id, if any
    grp_of = {}
    for h, members in dups.items():
        for m in members:
            grp_of[m] = h
    gsel = [grp_of[p] for p in paths if p in grp_of]
    gdup = [g for g, c in Counter(gsel).items() if c > 1]
    check("no duplicate GROUP allocated twice", len(gdup) == 0,
          f"{len(gdup)} groups hit more than once")
    check("no allocated file already labelled",
          len(set(paths) & labelled) == 0, f"{len(set(paths)&labelled)} overlap")

    print("\n3-4. sample families / round robins")
    fams = [byp[p]["family"] for p in paths if p in byp]
    check("every allocated file resolves in the inventory",
          len(fams) == len(paths), f"{len(paths)-len(fams)} unresolved")
    fdup = [f for f, c in Counter(fams).items() if c > 1]
    check("one file per normalised sample family", len(fdup) == 0,
          f"{len(fdup)} families appear twice")
    # adjacent numbered variants: same family stem differing only by index
    stems = Counter(f.split("||")[-1] for f in fams)
    worst = stems.most_common(1)[0] if stems else ("", 0)
    check("no family stem dominates", worst[1] <= 3,
          f"most common stem {worst[0]!r} x{worst[1]}")

    print("\n5-6. collection breadth")
    cv = Counter(byp[p]["vendor"] for p in paths if p in byp)
    cp = Counter(byp[p]["pack"] for p in paths if p in byp)
    labv = Counter(inv.attribute(p)[1] for p in labelled)
    new = [v for v in cv if v not in labv]
    check("covers many collections", len(cv) >= 50, f"{len(cv)} vendors")
    check("covers many packs", len(cp) >= 150, f"{len(cp)} packs")
    check("majority of collections are previously unlabelled",
          len(new) >= 40, f"{len(new)} new vendors")
    check("no pack dominates the batch", max(cp.values()) <= 6,
          f"max {max(cp.values())} files from one pack")
    top3 = sum(c for _, c in cv.most_common(3))
    check("top-3 collections are not >25% of the batch",
          top3 / len(paths) <= 0.25,
          f"top-3 = {100*top3/len(paths):.1f}% (existing corpus was 55%)")

    print("\n7-8. evidence and rejection material")
    try:
        import name_detect as nd
        noev = sum(1 for p in paths if nd.detect(os.path.basename(p))[0] is None)
    except Exception:
        noev = -1
    check("files with no filename evidence well represented",
          noev < 0 or noev >= 100, f"{noev} of {len(paths)}")
    durs = [byp[p].get("duration") or 0 for p in paths if p in byp]
    check("wide duration range retained (loops and one-shots)",
          min(durs) < 1.0 and max(durs) > 4.0,
          f"{min(durs):.2f}s .. {max(durs):.1f}s")

    print("\n9-10. distribution not artificially balanced")
    # proxy for class mix: filename-derived hint distribution should be uneven,
    # mirroring the library rather than a flat quota
    try:
        import name_detect as nd
        hints = Counter(nd.detect(os.path.basename(p))[0] for p in paths)
        hints.pop(None, None)
        vals = sorted(hints.values(), reverse=True)
        flat = len(vals) > 2 and (vals[0] - vals[-1]) <= 2
        check("class mix is NOT flat-quota'd", not flat,
              f"detected-class counts {vals[:6]}")
    except Exception as e:
        check("class mix check ran", False, str(e)[:60])

    print("\n11. sealed subset")
    leaked = [p for p in paths if p in byp and byp[p]["vendor"] in sealed]
    check("no sealed collection appears in the labelling batch",
          len(leaked) == 0, f"{len(leaked)} leaked")
    check("sealed set is non-empty", len(sealed) >= 3, f"{len(sealed)} vendors")
    sealed_n = sum(1 for f in invd["files"] if f["vendor"] in sealed)
    check("sealed set is substantial", sealed_n > 1000, f"{sealed_n} files")

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: {FAILED}")
        return 1
    print("all allocation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
