#!/usr/bin/env python3
"""Evaluate soft family/form bonuses without a hard cascade.

Every exact class remains eligible. Family and form are auxiliary prototype
scores, not gates, so an error on either axis cannot make the correct class
unrecoverable. The coefficients are fixed before looking at results.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()

    import full_taxonomy_eval as full
    import factorised_taxonomy as ft
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    d = full.load(args.corpus)
    inventory = full.eligible_classes(d, 5, 5)
    classes = [c for c, v in inventory.items() if v["eligible"]]
    tax = json.load(open(os.path.join(os.path.dirname(__file__), "taxonomy_v1.json")))
    family = {c: tax["classes"][c].get("family", c) for c in classes}
    form = {c: tax["classes"][c].get("form", c) for c in classes}
    fams = sorted(set(family.values()))
    forms = sorted(set(form.values()))
    keep = np.isin(d["labels"], classes)
    X, y, groups = d["X"][keep], d["labels"][keep], d["vendor"][keep]
    yf = np.asarray([family[c] for c in y], dtype=object)
    ym = np.asarray([form[c] for c in y], dtype=object)

    # Fixed before evaluation; these are separate named arms, not post-hoc
    # selection of the best coefficient.
    arms = {
        "flat": (0.0, 0.0),
        "soft_family_025": (0.25, 0.0),
        "soft_form_025": (0.0, 0.25),
        "soft_both_025": (0.25, 0.25),
        "soft_both_050": (0.50, 0.50),
    }
    scores = {name: [] for name in arms}
    f1s = {name: [] for name in arms}
    per_seed = {name: [] for name in arms}
    for seed in range(args.seeds):
        cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
        pred = {name: np.empty(len(y), dtype=object) for name in arms}
        for tr, te in cv.split(X, y, groups=groups):
            if set(groups[tr]) & set(groups[te]):
                raise AssertionError("collection leakage")
            se = ft.proto_scores(X[tr], y[tr], X[te], classes)
            sf = ft.proto_scores(X[tr], yf[tr], X[te], fams)
            sm = ft.proto_scores(X[tr], ym[tr], X[te], forms)
            # Normalize each axis into a probability distribution. The exact
            # scores remain the incumbent mechanism; auxiliary axes only add
            # a fixed log-probability bonus.
            pe = ft.softmax(se)
            pf = ft.softmax(sf)
            pm = ft.softmax(sm)
            for name, (af, am) in arms.items():
                joint = np.log(pe + 1e-12)
                for j, c in enumerate(classes):
                    joint[:, j] += af * np.log(pf[:, fams.index(family[c])] + 1e-12)
                    joint[:, j] += am * np.log(pm[:, forms.index(form[c])] + 1e-12)
                pred[name][te] = np.asarray(classes)[joint.argmax(1)]
        for name in arms:
            ok = pred[name] == y
            acc = 100.0 * float(ok.mean())
            f1 = 100.0 * float(f1_score(y, pred[name].astype(str), average="macro", zero_division=0))
            scores[name].append(acc)
            f1s[name].append(f1)
            per_seed[name].append(round(acc, 2))

    result = {}
    for name in arms:
        result[name] = {
            "family_bonus": arms[name][0],
            "form_bonus": arms[name][1],
            "accuracy_mean": round(float(np.mean(scores[name])), 2),
            "accuracy_sd": round(float(np.std(scores[name])), 2),
            "macro_f1": round(float(np.mean(f1s[name])), 2),
            "per_seed_accuracy": per_seed[name],
            "delta_vs_flat": round(float(np.mean(scores[name]) - np.mean(scores["flat"])), 2),
        }
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus": os.path.abspath(args.corpus),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                      "seeds": args.seeds, "splits": args.splits,
                      "coefficients_preregistered": True},
        "n_files": int(len(y)), "n_classes": len(classes),
        "n_families": len(fams), "n_forms": len(forms),
        "family_map": family, "form_map": form, "results": result,
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    for name, r in result.items():
        print(name, r["accuracy_mean"], r["macro_f1"], r["delta_vs_flat"])
    print(f"wrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
