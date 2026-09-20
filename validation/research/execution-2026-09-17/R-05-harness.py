#!/usr/bin/env python3
"""R-05 DiskSweep harness: spec-conformance corpus + Trash fuzz (rules-only).

Run from products/disksweep/:  python3 <this>  (writes RESULTS + CSV next to itself)
Scope honesty: this tests SPEC-CONFORMANCE (code vs its own contracts) plus
adversarial normalization edges -- NOT real-world accuracy, which needs a
human-labelled corpus of real disks. Findings below are graded accordingly.
"""
import csv
import json
import os
import random
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../../../products/disksweep")
from sidecar import classifier as C
from sidecar import cli as CLI

OUT = os.path.dirname(os.path.abspath(__file__))

# (path, category, parent, expected_safety)
CORPUS = [
    ("/System/Library/x", "Other", None, "BLOCKED"),
    ("/System", "Other", None, "BLOCKED"),
    ("/bin/bash", "Other", None, "BLOCKED"),
    ("/usr/bin/x", "Other", None, "BLOCKED"),
    ("/private/var/vm/sleepimage", "Other", None, "BLOCKED"),
    ("/Library/Extensions/foo.kext/Contents/x", "Other", None, "BLOCKED"),
    ("/Volumes/B/Backups.backupdb/m/x", "Other", None, "BLOCKED"),
    ("/usr/local/var/cache/brew/x", "Cache", None, "SAFE"),      # carve-out
    ("/usr/local/Caches/pip/x", "Cache", None, "SAFE"),          # carve-out
    ("/usr/../tmp/evil", "Other", None, "REVIEW"),               # normalizes out of /usr
    ("/usr2/fake", "Other", None, "REVIEW"),                     # prefix-segment, not /usr
    ("/SYSTEM/x", "Other", None, "REVIEW"),                      # case: _norm keeps case
    ("/Library/Caches/com.foo/x", "Cache", None, "SAFE"),
    ("~/Library/Logs/a.log", "Log", None, "SAFE"),
    ("/x/.Trash/y", "Trash", None, "SAFE"),
    ("/x/node_modules/.npm/z", "Other", None, "SAFE"),
    ("/x/Library/Developer/Xcode/DerivedData/b", "Dev", None, "SAFE"),
    ("/Users/u/Library/Application Support/Orphan/x", "Other", None, "REVIEW"),
    ("/Users/u/Downloads/a.dmg", "Downloads", None, "REVIEW"),
    ("/Users/u/Documents/thesis.pdf", "Other", None, "REVIEW"),
    ("/Models/llama/q", "AIModel", None, "REVIEW"),
    ("/x/some/thing", "Mystery", None, "REVIEW"),
]

# Adversarial fuzz seeds for is_blocked (pure function, fast)
FUZZ_BASES = ["/System", "/usr", "/bin", "/private/var/vm", "/Library/Extensions/a.kext",
              "/V/Backups.backupdb", "/usr/local/var/cache", "/tmp", "/Users/u/Docs"]
MUT = ["", "/", "//", "/x", "/..", "/../y", "/./y", "2", "s", "/x/..", "/x/../.."]


def main():
    t0 = time.monotonic()
    items = [{"path": p, "size_bytes": 100, "category": c,
              "installed_parent_app_or_null": par} for p, c, par, _ in CORPUS]
    verdicts = C.classify(items, use_llm=False)
    dt = time.monotonic() - t0
    rows = []
    tp = collections_counter = {}
    for (p, c, par, exp), v in zip(CORPUS, verdicts):
        ok = v["safety"] == exp
        rows.append({"path": p, "category": c, "expected": exp, "got": v["safety"],
                     "action": v["action"], "pass": ok})
        tp.setdefault(exp, [0, 0])[ok] += 1
    with open(f"{OUT}/RESULTS_R-05-corpus.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    npass = sum(1 for r in rows if r["pass"])
    print(f"corpus: {npass}/{len(rows)} pass in {dt*1000:.1f}ms ({dt*1000/len(rows):.2f}ms/item)")
    for k, (fails, passes) in sorted(tp.items()):
        print(f"  {k}: {passes}/{passes+fails}")
    for r in rows:
        if not r["pass"]:
            print("  MISS:", r)

    # Adversarial is_blocked fuzz: invariant = BLOCKED verdict  <=>  is_blocked True,
    # and classify() final guard agrees with is_blocked on every mutant.
    random.seed(5)
    n = bad = 0
    for i in range(5000):
        p = random.choice(FUZZ_BASES) + random.choice(MUT)
        v = C.classify([{"path": p, "size_bytes": 1, "category": "Other"}], use_llm=False)[0]
        n += 1
        if (v["safety"] == "BLOCKED") != C.is_blocked(p):
            bad += 1
            if bad < 5:
                print("  GUARD-MISMATCH:", repr(p), v["safety"])
    print(f"fuzz: {n-bad}/{n} guard-consistent")

    # Trash end-to-end in isolated HOME
    home = tempfile.mkdtemp(prefix="dsfakehome")
    os.environ["HOME"] = home
    os.makedirs(f"{home}/.Trash", exist_ok=True)
    keep = f"{home}/precious.txt"
    open(keep, "w").write("do not touch")
    safe = f"{home}/Library/Caches/junk.bin"
    os.makedirs(os.path.dirname(safe), exist_ok=True)
    open(safe, "w").write("junk")
    blocked = "/System/x-decOY"
    vv = C.classify([
        {"path": safe, "size_bytes": 4, "category": "Cache"},
        {"path": blocked, "size_bytes": 1, "category": "Other"},
        {"path": keep, "size_bytes": 11, "category": "Other"},  # REVIEW, excluded w/o flag
    ], use_llm=False)
    log = CLI.cmd_trash(vv, include_review=False)
    undone = json.load(open(log))
    assert not os.path.exists(safe), "SAFE file must move"
    assert os.path.exists(keep), "REVIEW file must stay without flag"
    assert [u["src"] for u in undone] == [safe], f"undo log must list only SAFE move: {undone}"
    outside = []
    for root, _, files in os.walk(home):
        if ".Trash" not in root:
            outside += files
    assert set(outside) == {"precious.txt"}, f"stray writes outside Trash: {outside}"
    CLI.cmd_undo(log)
    assert open(safe).read() == "junk", "undo must restore bytes"
    print(f"trash e2e: SAFE moved+restored, REVIEW kept, BLOCKED skipped, log={os.path.basename(os.path.dirname(log))}")
    shutil.rmtree(home, ignore_errors=True)
    print("R-05 HARNESS GREEN")


if __name__ == "__main__":
    main()
