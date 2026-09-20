#!/usr/bin/env python3
"""
Re-label the rows the escape hatch swallowed.

The granularity sprint recorded 48 rows as "Not in list" and 3 as "Not enough
info" with no note. Those labels say only that the option list was wrong; they
do not say what the file is, so they cannot be used, corrected or even argued
with. label_tool.py now refuses to write such a row at all (see NOTE_REQUIRED),
which stops the bleeding but does not recover what was already lost. This does.

The option list here is deliberately WIDE. The original buckets each offered a
short, focused list -- correct for speed, and precisely why these rows escaped:
every one of them is a file whose true class was not on the short list it was
shown. Showing the same reviewer the same narrow list again would reproduce the
same escape. So this run offers the full supported taxonomy plus the families
that repeatedly turned up in the notes, and any remaining escape must carry a
written note before the server will accept it.

Usage:
  python3 run_escape_recovery.py            # status
  python3 run_escape_recovery.py --start    # serve on :8770
"""
import os, csv, json, argparse, subprocess, sys

SD = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(SD, "SLO_ESCAPE_HATCH_RECOVERY_EXPORT_V1.csv")
OUTCSV = os.path.join(SD, "verified_escape_recovery.csv")
MANIFEST = os.path.join(SD, "label_manifest_escape_recovery.json")
PORT = 8770

# Escapes still exist -- removing them would manufacture fake labels, which is
# the opposite failure. They just cannot be empty any more.
ESCAPES = ["Not in list", "Not enough info", "Taxonomy gap", "Unknown"]

GROUPS = [
    ("drum one-shot", ["Kick", "Snare", "Rimshot", "Clap", "Hi-Hat", "Crash"]),
    ("perc one-shot", ["Tom", "Shaker/Tambourine", "Hand Drum",
                       "Other Percussive Hit"]),
    # "Foley Loop" and "Weather/Nature Atmos" are deliberately absent: the key
    # alphabet holds 35 options and the wide list needs 37. Both are compound
    # refinements of a class that IS offered (Foley, Atmosphere), so a reviewer
    # loses nothing they cannot put in the note -- whereas dropping a primary
    # class would recreate the very gap these rows escaped through.
    ("loop",          ["Drum Loop", "Percussion Loop", "Hi-Hat Loop", "Top Loop",
                       "Bass Loop", "Synth Loop", "Vocal Loop"]),
    ("bass",          ["808", "Bass Hit", "Sub Bass", "Reese Bass",
                       "Synth Bass Sustained"]),
    ("tonal",         ["Synth One-Shot", "Pad", "Vocal One-Shot"]),
    ("fx",            ["Foley", "Impact", "SFX", "Riser", "Atmosphere"]),
    ("none",          ["Other/none"] + ESCAPES),
]
KEYS = "1234567890qwertyuiopadfghjklzxcvbnm"


def rows():
    return list(csv.DictReader(open(EXPORT)))


def done_ids():
    if not os.path.exists(OUTCSV):
        return set()
    return {int(r["id"]) for r in csv.DictReader(open(OUTCSV))}


def status():
    rs, d = rows(), done_ids()
    p1 = [r for r in rs if r["priority"] == "P1"]
    p2 = [r for r in rs if r["priority"] == "P2"]
    print(f"\nescape-hatch recovery: {len(d)}/{len(rs)} done")
    print(f"  P1  'Not in list' with no note      {len(p1)} rows")
    print(f"  P2  'Not enough info' with no note  {len(p2)} rows")
    if len(d) < len(rs):
        print(f"\n  start:  python3 run_escape_recovery.py --start"
              f"   ->  http://localhost:{PORT}")
    else:
        print("\n  complete -- run integrate_granularity_labels.py next")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", action="store_true")
    a = ap.parse_args()
    if not a.start:
        return status()

    rs = rows()
    items, missing = [], 0
    for i, r in enumerate(rs):
        if os.path.exists(r["path"]):
            # The hint carries the evidence the reviewer needs to beat the
            # original short list: what the model thought, and what the name
            # claims. It is shown, not applied.
            hint = f"was: {r['previous_label']}  |  model: {r['current_model_prediction']}"
            tok = r.get("token_evidence", "")
            if tok and tok != "(no recognised token)":
                hint += f"  |  name: {tok} ({r.get('token_risk','')})"
            items.append({"path": r["path"], "hint": hint, "id": i})
        else:
            missing += 1

    json.dump(items, open(MANIFEST, "w"))
    flat = [c for _, cs in GROUPS for c in cs]
    if len(flat) > len(KEYS):
        print(f"too many options ({len(flat)}) for the key alphabet")
        return 1

    print("\n  Recovering the rows the escape hatch swallowed.")
    print("  Every escape now REQUIRES a note -- say what the sound is.\n")
    for i, c in enumerate(flat):
        print(f"    [{KEYS[i]}] {c}")
    if missing:
        print(f"\n  {missing} file(s) no longer on disk -- skipped, reported as "
              f"unrecoverable")
    print(f"\n  {len(items)} files   ->  http://localhost:{PORT}\n")

    inject = os.path.join(SD, "_escape_recovery_set.json")
    json.dump({"set": "escape_recovery", "flat": flat, "groups": GROUPS},
              open(inject, "w"))
    env = dict(os.environ, SLO_GRAN_SET=inject)
    subprocess.Popen([sys.executable, "-u", os.path.join(SD, "label_tool.py"),
                      "--set", "escape_recovery", "--manifest", MANIFEST,
                      "--csv", OUTCSV, "--port", str(PORT)],
                     env=env,
                     stdout=open(os.path.join(SD, "_escape_recovery.log"), "w"),
                     stderr=subprocess.STDOUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
