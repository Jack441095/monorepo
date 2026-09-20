#!/usr/bin/env python3
"""
Drive the granularity sprint one bucket at a time.

Each bucket asks a DIFFERENT question, so each gets its own short option list.
Sixty top/hat loops with six options is far faster and more accurate than 400
mixed files with thirty-four; a long list is scanned, a short one is recognised.

Every bucket ends with the same escape hatches, because the percussion sprint
showed that a missing option manufactures a fake Unknown.
"""
import os, csv, json, argparse, subprocess, sys

SD = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(SD, "SLO_GRANULARITY_LABEL_SPRINT_EXPORT_V1.csv")

ESCAPES = ["Not in list", "Not enough info", "Taxonomy gap", "Unknown"]

BUCKETS = {
    "top_hihat_loop": {
        "port": 8760,
        "question": "Is this a Top Loop or a Hi-Hat Loop? (the unevidenced overlap)",
        "groups": [("loop", ["Top Loop", "Hi-Hat Loop", "Percussion Loop", "Drum Loop"]),
                   ("one-shot", ["Hi-Hat", "Percussion"]),
                   ("none", ["Other/none"] + ESCAPES)],
    },
    "bass_family": {
        "port": 8761,
        "question": "Which bass mechanism? Sub Bass has only 2 labels today",
        "groups": [("sustained", ["Sub Bass", "Reese Bass", "Synth Bass Sustained"]),
                   ("hit", ["808", "Bass Hit", "Kick"]),
                   ("loop", ["Bass Loop"]),
                   ("none", ["Not Bass", "Other/none"] + ESCAPES)],
    },
    "percussion_family": {
        "port": 8762,
        "question": "Percussion one-shot or loop, and which kind?",
        "groups": [("one-shot", ["Tom", "Shaker/Tambourine", "Hand Drum",
                                 "Metallic", "Other Percussive Hit", "Rimshot"]),
                   ("loop", ["Percussion Loop", "Top Loop", "Drum Loop"]),
                   ("none", ["Other/none"] + ESCAPES)],
    },
    "foley_sfx_impact": {
        "port": 8763,
        "question": "Foley, SFX, Impact or texture? ('texture' measures 0%)",
        "groups": [("one-shot", ["Foley", "SFX", "Impact", "Riser"]),
                   ("sustained", ["Atmosphere", "Weather/Nature Atmos", "Foley Loop"]),
                   ("none", ["Other/none"] + ESCAPES)],
    },
    "rejection_boundary": {
        "port": 8764,
        "question": "Is this a supported sound at all? (~27% of all errors)",
        "groups": [("supported", ["Kick", "Snare", "Clap", "Hi-Hat", "Percussion",
                                  "Drum Loop", "Percussion Loop", "Foley", "SFX"]),
                   ("reject", ["Other/none", "Not a sample"] + ESCAPES)],
    },
    "low_conf_or_disagreement": {
        "port": 8765,
        "question": "Model abstained or disagreed with the filename -- who is right?",
        "groups": [("one-shot", ["Kick", "Snare", "Clap", "Hi-Hat", "Crash",
                                 "Rimshot", "Percussion", "Foley"]),
                   ("loop", ["Drum Loop", "Percussion Loop", "Hi-Hat Loop",
                             "Top Loop", "Synth Loop"]),
                   ("none", ["Other/none"] + ESCAPES)],
    },
}
ORDER = list(BUCKETS)


def counts():
    rows = list(csv.DictReader(open(EXPORT)))
    out = {}
    for b in ORDER:
        tot = sum(1 for r in rows if r["bucket"] == b)
        csvp = os.path.join(SD, f"verified_gran_{b}.csv")
        done = len(list(csv.DictReader(open(csvp)))) if os.path.exists(csvp) else 0
        out[b] = (done, tot)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=None)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.status or not a.bucket:
        c = counts()
        print("granularity sprint progress:\n")
        for b in ORDER:
            done, tot = c[b]
            bar = "#" * int(20 * done / max(tot, 1))
            print(f"  {b:26} {done:3d}/{tot:3d}  {bar:<20}  "
                  f"port {BUCKETS[b]['port']}")
        nxt = next((b for b in ORDER if c[b][0] < c[b][1]), None)
        total_done = sum(v[0] for v in c.values())
        total = sum(v[1] for v in c.values())
        print(f"\n  overall {total_done}/{total}")
        if nxt:
            print(f"\n  next:  python3 run_granularity_sprint.py --bucket {nxt}")
        else:
            print("\n  all buckets complete")
        return 0

    b = a.bucket
    if b not in BUCKETS:
        print(f"unknown bucket {b}; choose from {ORDER}"); return 1
    cfg = BUCKETS[b]
    rows = [r for r in csv.DictReader(open(EXPORT)) if r["bucket"] == b]
    items = [{"path": r["path"], "hint": "", "id": i}
             for i, r in enumerate(rows) if os.path.exists(r["path"])]
    man = os.path.join(SD, f"label_manifest_gran_{b}.json")
    json.dump(items, open(man, "w"))

    # register the set/groups in label_tool for this run
    flat = [c for _, cs in cfg["groups"] for c in cs]
    import label_tool as lt
    lt.SETS[b] = flat
    lt.GROUPS[b] = cfg["groups"]
    keys = "1234567890qwertyuiopadfghjklzxcvbnm"
    if len(flat) > len(keys):
        print(f"too many options ({len(flat)}) for the key alphabet"); return 1

    print(f"\n  {cfg['question']}\n")
    for i, c in enumerate(flat):
        print(f"    [{keys[i]}] {c}")
    print(f"\n  {len(items)} files   ->  http://localhost:{cfg['port']}\n")

    # persist the set so the spawned server sees it
    inject = os.path.join(SD, "_gran_set.json")
    json.dump({"set": b, "flat": flat, "groups": cfg["groups"]}, open(inject, "w"))
    env = dict(os.environ, SLO_GRAN_SET=inject)
    subprocess.Popen([sys.executable, "-u", os.path.join(SD, "label_tool.py"),
                      "--set", b, "--manifest", man,
                      "--csv", os.path.join(SD, f"verified_gran_{b}.csv"),
                      "--port", str(cfg["port"])],
                     env=env,
                     stdout=open(os.path.join(SD, f"_gran_{b}.log"), "w"),
                     stderr=subprocess.STDOUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
