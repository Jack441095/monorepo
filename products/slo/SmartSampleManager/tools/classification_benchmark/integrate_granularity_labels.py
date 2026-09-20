#!/usr/bin/env python3
"""
Normalise the granularity sprint + escape-hatch recovery into one source file
that build_ground_truth.py can consume like any other.

Why a normaliser and not a direct merge
---------------------------------------
The sprint buckets asked narrow questions, so they collected answers at a finer
resolution than the taxonomy holds: "Tom", "Shaker/Tambourine", "Hand Drum" and
"Other Percussive Hit" are all Percussion; "Reese Bass" is the sprint's spelling
of the taxonomy's "Bass Reese". Folding those in as new top-level classes would
expand the taxonomy on the strength of 2-8 examples, which is exactly the move
the taxonomy-repair experiment already showed loses accuracy.

So finer answers are demoted to the `subtype` field under a parent that already
exists and already has evidence. Nothing is invented and nothing is discarded:
the original string survives in `source_attributes` so any later promotion can
be done from the record rather than from memory.

Three bass mechanisms have NO defensible parent in taxonomy v1 and too few
examples to justify creating one. They are HELD: written to a separate file with
full provenance, excluded from the trained class set, and reported as an owner
decision. Quietly filing a sustained sine under "Bass Hit" to avoid an awkward
row in a report would be a labelling error dressed as tidiness.

Usage:
  python3 integrate_granularity_labels.py            # dry run, changes nothing
  python3 integrate_granularity_labels.py --write
"""
import os, csv, json, glob, argparse, shutil, time
from collections import Counter

SD = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SD, "verified_granularity.csv")
HELD = os.path.join(SD, "verified_granularity_HELD.csv")
DROPPED = os.path.join(SD, "verified_granularity_DROPPED.csv")
ARCHIVE = os.path.join(SD, "ground_truth", "frozen")

import label_tool as lt
SCHEMA = lt.SCHEMA

# The note parser proposes candidates from a synonym table that is deliberately
# WIDER than the taxonomy -- a reviewer who writes "sounds like a rhodes" should
# be understood, not ignored. But a candidate the taxonomy does not hold cannot
# become a dataset label: the first dry run happily proposed "Piano" and
# "Guitar" as classes, which would have invented two one-example classes out of
# free text. Anything the taxonomy does not recognise is HELD instead.
TAXONOMY_CLASSES = set(json.load(
    open(os.path.join(SD, "taxonomy_v1.json")))["classes"])

# The sprint's spelling vs the taxonomy's. Same sound, two names -- a naming
# defect, not a taxonomy question.
ALIASES = {"Reese Bass": "Bass Reese"}

# finer-than-taxonomy answers -> (parent class already in the taxonomy, subtype)
SUBTYPES = {
    "Tom":                  ("Percussion", "Tom"),
    "Shaker/Tambourine":    ("Percussion", "Shaker/Tambourine"),
    "Hand Drum":            ("Percussion", "Hand Drum"),
    "Other Percussive Hit": ("Percussion", "Other Percussive Hit"),
    "Metallic":             ("Percussion", "Metallic"),
}

# No defensible parent in taxonomy v1, and n far below the 15-example floor.
# Held rather than guessed.
HOLD_LABELS = {"808", "Sub Bass", "Synth Bass Sustained", "Not a sample",
               "Not Bass"}

# Escape hatches are evidence ABOUT the taxonomy, not labels of audio. They are
# never dataset rows.
ESCAPES = {"Not in list", "Not enough info", "Taxonomy gap", "Unknown"}
DROP = ESCAPES | {"__skip__", "Misc/Review"}


def load():
    src = []
    for f in sorted(glob.glob(os.path.join(SD, "verified_gran_*.csv"))):
        bucket = os.path.basename(f)[len("verified_gran_"):-4]
        for r in csv.DictReader(open(f)):
            r["_origin"] = f"granularity:{bucket}"
            src.append(r)
    rec = os.path.join(SD, "verified_escape_recovery.csv")
    n_rec = 0
    if os.path.exists(rec):
        for r in csv.DictReader(open(rec)):
            r["_origin"] = "escape_recovery"
            src.append(r)
            n_rec += 1
    return src, n_rec


def normalise(r):
    """Return (row, disposition). Disposition is 'keep', 'hold' or 'drop'."""
    lab = (r.get("label") or "").strip()
    note = (r.get("note") or "").strip()
    alt = (r.get("not_in_list_label") or "").strip()

    # A recovered escape: the reviewer named the sound in the note or in the
    # alternative field. Promote it, and say so in the provenance.
    recovered_from = ""
    if lab in ESCAPES:
        cand = alt or (lt.parse_note(note)["candidates"] or [""])[0]
        cand = ALIASES.get(cand, cand)
        if not cand:
            return r, "drop"
        if cand not in TAXONOMY_CLASSES and cand not in SUBTYPES:
            # understood, but outside the taxonomy -- evidence of a real gap
            r["label"] = cand
            r["source_attributes"] = "; ".join(
                x for x in [r.get("source_attributes") or "",
                            f"recovered_from={lab}", f"note={note}",
                            "outside_taxonomy_v1"] if x)
            return r, "hold"
        recovered_from, lab = lab, cand

    lab = ALIASES.get(lab, lab)
    subtype = (r.get("subtype") or r.get("percussion_subtype") or "").strip()
    if lab in SUBTYPES:
        parent, sub = SUBTYPES[lab]
        r["source_attributes"] = "; ".join(
            x for x in [r.get("source_attributes") or "",
                        f"sprint_label={lab}"] if x)
        lab, subtype = parent, subtype or sub
    r["label"] = lab
    if subtype:
        r["percussion_subtype"] = subtype
    if recovered_from:
        r["source_attributes"] = "; ".join(
            x for x in [r.get("source_attributes") or "",
                        f"recovered_from={recovered_from}",
                        f"note={note}" if note else ""] if x)
    if lab in HOLD_LABELS:
        return r, "hold"
    if lab in DROP or not lab:
        return r, "drop"
    return r, "keep"


def write(path, rows):
    cols = SCHEMA + ["_origin"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (r.get(k) or "") for k in cols})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    src, n_rec = load()
    keep, hold, drop = [], [], []
    for r in src:
        row, d = normalise(dict(r))
        {"keep": keep, "hold": hold, "drop": drop}[d].append(row)

    # conflicts: the same file labelled two different ways across buckets
    by_path = {}
    conflicts = []
    for r in keep:
        p = r["path"]
        if p in by_path and by_path[p]["label"] != r["label"]:
            conflicts.append((p, by_path[p]["label"], r["label"],
                              by_path[p]["_origin"], r["_origin"]))
        by_path.setdefault(p, r)

    print(f"granularity sprint      {len(src) - n_rec} rows")
    print(f"escape-hatch recovery   {n_rec} rows")
    print(f"  -> dataset rows       {len(keep)}  ({len(by_path)} unique paths)")
    print(f"  -> HELD (no parent)   {len(hold)}")
    print(f"  -> dropped (no info)  {len(drop)}")
    if conflicts:
        print(f"\n  {len(conflicts)} CONFLICT(S) -- the same file labelled two ways:")
        for p, x, y, ox, oy in conflicts[:10]:
            print(f"    {os.path.basename(p)[:44]:46} {x!r} [{ox}] vs {y!r} [{oy}]")
        print("  These are not resolved automatically. Re-listen and pick one.")

    print("\n  class distribution:")
    for c, n in Counter(r["label"] for r in by_path.values()).most_common():
        print(f"    {c:26} {n}")
    if hold:
        print("\n  HELD for an owner decision (no parent class, n < 15):")
        for c, n in Counter(r["label"] for r in hold).most_common():
            print(f"    {c:26} {n}")
    rec_n = sum(1 for r in keep if "recovered_from=" in (r.get("source_attributes") or ""))
    print(f"\n  recovered from escape hatches: {rec_n}")

    if not a.write:
        print("\ndry run -- nothing written. re-run with --write")
        return 1 if conflicts else 0
    if conflicts:
        print("\nREFUSING to write while conflicts stand.")
        return 1

    stamp = time.strftime("%Y%m%d-%H%M%S")
    arch = os.path.join(ARCHIVE, f"PRE_GRAN_INTEGRATION_{stamp}")
    os.makedirs(arch, exist_ok=True)
    for f in glob.glob(os.path.join(SD, "ground_truth", "SLO_GT_V1", "*")):
        shutil.copy2(f, arch)
    print(f"\narchived previous ground truth -> {os.path.relpath(arch, SD)}")

    write(OUT, list(by_path.values()))
    write(HELD, hold)
    write(DROPPED, drop)
    print(f"wrote {os.path.basename(OUT)} ({len(by_path)}), "
          f"{os.path.basename(HELD)} ({len(hold)}), "
          f"{os.path.basename(DROPPED)} ({len(drop)})")
    print("\nnext:  python3 build_ground_truth.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
