#!/usr/bin/env python3
"""
Fold the percussion subtype sprint back into the ground truth.

The sprint asked for eleven answers that mix two different kinds of information,
because that is the distinction the ear actually makes on this material:

  * some answers REFINE the existing Percussion label (Shaker, Tom, Metallic)
    -> the primary label stays Percussion, a subtype is added
  * some answers CORRECT it (Percussion Loop, Top Loop, Hi-Hat Loop, Drum Loop,
    Other/none) -> the primary label changes, because the original was wrong
    about temporal form or family
  * Foley Percussion is a PROVENANCE answer -> the class stays Percussion and
    'foley' goes to source_attributes, per the established principle that
    provenance is an attribute, never a class
  * Unknown keeps Percussion, sets ambiguous=true, and keeps the note

Corrections are recorded, never silently applied: the original label is
preserved in `original_label` and every change is reported before it is written.
Nothing is deleted.
"""
import os, csv, json, shutil, argparse, time
from collections import Counter

SD = os.path.dirname(os.path.abspath(__file__))
SPRINT = os.path.join(SD, "verified_percussion_subtype.csv")
GT = os.path.join(SD, "ground_truth", "SLO_GT_V1", "labels.csv")
OUT = os.path.join(SD, "verified_percussion_corrections.csv")

# answer -> (new primary label or None to keep, subtype, source attribute, flags)
MAP = {
    "Percussion One-Shot":  (None, "Other Percussive Hit", "", {}),
    "Shaker/Tambourine":    (None, "Shaker/Tambourine", "", {}),
    "Tom/Conga/Bongo":      (None, "Tom", "", {}),
    "Metallic Percussion":  (None, "Metallic", "", {}),
    "Foley Percussion":     (None, "Other Percussive Hit", "foley", {}),
    "Percussion Loop":      ("Percussion Loop", "", "", {}),
    "Top Loop":             ("Top Loop", "", "", {}),
    "Hi-Hat Loop":          ("Hi-Hat Loop", "", "", {}),
    "Drum Loop":            ("Drum Loop", "", "", {}),
    "Other/none":           ("Other/none", "", "", {}),
    "Unknown":              (None, "Unsure", "", {"ambiguous": "true"}),
}

# Jack marked 11 files Unknown but wrote what each one was. Those notes are not
# hedges -- they are precise answers the option list had no key for (there was no
# plain Hi-Hat, Rimshot or SFX in a percussion-subtype sprint). Reading them is
# the difference between 11 unusable rows and 11 corrections, so they are parsed
# explicitly here rather than discarded. Anything unrecognised stays Unknown.
NOTE_RESOLVES = {
    "tom":     (None, "Tom", "", {}),
    "hi hat":  ("Hi-Hat", "", "", {}),
    "hihat":   ("Hi-Hat", "", "", {}),
    "hi-hat":  ("Hi-Hat", "", "", {}),
    "rimshot": ("Rimshot", "", "", {}),
    "rim":     ("Rimshot", "", "", {}),
    "sfx":     ("Other/none", "", "", {}),
}


def resolve_note(note):
    n = (note or "").strip().lower()
    for key, val in NOTE_RESOLVES.items():
        if key in n:
            return val
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the corrections (otherwise dry-run)")
    a = ap.parse_args()
    if not os.path.exists(SPRINT):
        raise SystemExit("no sprint labels yet")
    sprint = {r["path"]: r for r in csv.DictReader(open(SPRINT))
              if r["label"] not in ("__skip__",)}
    gt = {r["path"]: r for r in csv.DictReader(open(GT))}
    print(f"sprint: {len(sprint)} labelled")

    rows, relabels, refines, unknown = [], [], [], []
    for p, r in sprint.items():
        ans = r["label"]
        if ans not in MAP:
            print(f"  UNMAPPED answer {ans!r} -- skipping"); continue
        newlab, subtype, srcattr, flags = MAP[ans]
        note = r.get("note", "")
        resolved_from_note = False
        if ans == "Unknown":
            rv = resolve_note(note)
            if rv:
                newlab, subtype, srcattr, flags = rv
                resolved_from_note = True
        old = gt.get(p, {}).get("label", "?")
        rec = {"path": p, "original_label": old, "sprint_answer": ans,
               "new_label": newlab or old, "percussion_subtype": subtype,
               "source_attributes": srcattr,
               "ambiguous": flags.get("ambiguous", ""),
               "note": note,
               "resolved_from_note": "true" if resolved_from_note else ""}
        rows.append(rec)
        if newlab and newlab != old:
            relabels.append(rec)
        elif subtype and subtype != "Unsure":
            refines.append(rec)
        if ans == "Unknown" and not resolved_from_note:
            unknown.append(rec)

    fromnote = [r for r in rows if r["resolved_from_note"]]
    print(f"\n  {len(fromnote)} Unknowns RESOLVED from their notes")
    print(f"  {len(refines)} refine Percussion with a subtype")
    print(f"  {len(relabels)} CORRECT the primary label")
    print(f"  {len(unknown)} marked Unknown\n")
    if relabels:
        print("  corrections (original -> new):")
        for k, v in Counter((r["original_label"], r["new_label"])
                            for r in relabels).most_common():
            print(f"    {k[0]:20} -> {k[1]:20} {v}")
    if refines:
        print("\n  subtypes assigned:")
        for k, v in Counter(r["percussion_subtype"] for r in refines).most_common():
            print(f"    {k:24} {v}")
    if unknown:
        print("\n  Unknown, with notes:")
        for r in unknown[:12]:
            print(f"    {os.path.basename(r['path'])[:44]:46} {r['note'][:40]}")

    if not a.apply:
        print("\n(dry run -- rerun with --apply to write)")
        return 0
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, ["path", "original_label", "sprint_answer",
                               "new_label", "percussion_subtype",
                               "source_attributes", "ambiguous", "note",
                               "resolved_from_note"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    bk = os.path.expanduser("~/slo_label_backups")
    os.makedirs(bk, exist_ok=True)
    shutil.copy(OUT, os.path.join(bk, f"perc_corrections.{time.strftime('%Y%m%d-%H%M')}.csv"))
    shutil.copy(SPRINT, os.path.join(bk, f"verified_percussion_subtype.{time.strftime('%Y%m%d-%H%M')}.csv"))
    print(f"\nwrote {os.path.basename(OUT)} and backed up")
    print("next: python3 build_ground_truth.py   (picks up the corrections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
