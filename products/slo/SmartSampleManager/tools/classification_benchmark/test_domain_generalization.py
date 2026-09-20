#!/usr/bin/env python3
"""
Tests for the grouped evaluation harness.

The harness exists to stop leakage inflating results. A leak-prevention tool
that is itself untested is worth nothing, so these check the properties the
conclusions actually rest on:

  1. alignment is asserted, not assumed
  2. no group crosses train/test in any grouped mode, on every fold, every seed
  3. random mode really does leak (a negative control -- if it does not, the
     grouping is not measuring what we think)
  4. vendor attribution never yields an empty group
  5. family normalisation merges variation markers but not class words
  6. results are deterministic from a seed

Run:  python3 test_domain_generalization.py
"""
import os, sys, numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SD)
import domain_generalization_eval as dg   # noqa: E402
import sample_library_inventory as inv    # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def main():
    print("loading corpus...")
    d = dg.load_corpus()
    n = len(d["y"])
    print(f"  {n} files, {len(d['classes'])} classes\n")

    print("1. alignment")
    check("labels match feature rows",
          all(len(v) == n for v in d["feats"].values()),
          f"{{{', '.join(f'{k}:{len(v)}' for k, v in d['feats'].items())}}}")
    check("group arrays match", len(d["vendor"]) == n and len(d["pack"]) == n
          and len(d["family"]) == n)
    check("paths unique", len(set(d["paths"])) == n)

    print("\n2. group isolation on every fold and seed")
    for mode in ("family", "pack", "vendor", "packfam"):
        g = dg.groups_for(mode, d)
        leaks, folds = 0, 0
        for seed in range(3):
            for tr, te in dg.splits_for(mode, d, 5, seed):
                folds += 1
                if set(g[tr]) & set(g[te]):
                    leaks += 1
                if set(tr) & set(te):
                    leaks += 1
        check(f"mode '{mode}' isolated", leaks == 0,
              f"{folds} folds checked, {leaks} leaks")

    print("\n3. negative control -- random mode SHOULD leak groups")
    gf = dg.groups_for("family", d)
    leaked = 0
    for tr, te in dg.splits_for("random", d, 5, 0):
        leaked += len(set(gf[tr]) & set(gf[te]))
    check("random mode leaks families (as expected)", leaked > 0,
          f"{leaked} family collisions -- this is exactly what inflates the old numbers")

    print("\n4. vendor attribution")
    check("no empty vendor", (d["vendor"] != "").all())
    check("no empty pack", (d["pack"] != "").all())
    r, v, p, _ = inv.attribute("/some/unrooted/path/x.wav")
    check("unrooted path gets sentinel, not empty", v == "_unrooted", f"got {v!r}")

    print("\n5. family normalisation semantics")
    same = lambda a, b: (inv.family_id("V", "P", a) == inv.family_id("V", "P", b))
    check("velocity layers merge", same("Snare_C3_vel120.wav", "Snare_C3_vel80.wav"))
    check("round robins merge", same("Perc_RR3.wav", "Perc_RR7.wav"))
    check("note variants merge", same("808_sub_F#1.wav", "808_sub_C2.wav"))
    check("numbered variants merge", same("Organic - Kick (45).wav", "Organic - Kick (7).wav"))
    check("distinct classes stay apart", not same("Snare.wav", "Kick.wav"))
    check("loop vs one-shot stay apart", not same("Crash.wav", "Crash Loop.wav"))

    print("\n6. determinism")
    a1 = [tuple(t.tolist()) for t in list(dg.splits_for("vendor", d, 5, 0))[0]]
    a2 = [tuple(t.tolist()) for t in list(dg.splits_for("vendor", d, 5, 0))[0]]
    check("same seed gives same split", a1 == a2)
    b1 = [tuple(t.tolist()) for t in list(dg.splits_for("vendor", d, 5, 1))[0]]
    check("different seed gives different split", a1 != b1)

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: {FAILED}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
