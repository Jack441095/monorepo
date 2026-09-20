#!/usr/bin/env python3
"""
Phase 5 -- a learned factorised taxonomy.

The flat formulation wastes structure. "Percussion Loop" and "Drum Loop" share
a temporal form; "Percussion" and "Percussion Loop" share a function family. A
flat classifier must learn each cell independently from its own examples, which
is expensive when several cells have fewer than thirty.

Two axes, each supervised by the SAME existing labels -- no new annotation:

  function family   Kick, Snare, Clap, Hi-Hat, Crash, Percussion, Foley,
                    Drum (mixed), Rejection
  temporal form     One-Shot, Loop, Rejection

Other/none stays REJECTION on both axes. It is not an acoustic family and must
not be asked to form a compact prototype; its heterogeneity is intended.

Five formulations compared on identical collection-held-out folds:
  flat            the incumbent
  independent     one prototype set per axis, combined through a validity mask
  hierarchical    predict form first, then family among forms that are valid
  form_gated      flat prediction, overruled when the form axis disagrees
  soft_parent     flat scores plus a bonus for agreeing with the family axis

Scored on EXACT labels, so nothing is won by predicting a coarser thing.
Family and form accuracy are reported alongside, because a system that gets the
family right and the subtype wrong is more useful to a user -- and cheaper to
correct -- than one that is wrong outright.
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import incumbent_receipt as ir, eval_corpus_v2 as ec
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import f1_score

OUT = os.path.join(SD, "results_factorised_taxonomy.json")
GATE = 2.0

FAMILY = {"Kick": "Kick", "Snare": "Snare", "Clap": "Clap", "Hi-Hat": "Hi-Hat",
          "Crash": "Crash", "Percussion": "Percussion",
          "Percussion Loop": "Percussion", "Drum Loop": "Drum",
          "Foley": "Foley", "Other/none": "Rejection"}
FORM = {"Kick": "One-Shot", "Snare": "One-Shot", "Clap": "One-Shot",
        "Hi-Hat": "One-Shot", "Crash": "One-Shot", "Percussion": "One-Shot",
        "Foley": "One-Shot", "Drum Loop": "Loop", "Percussion Loop": "Loop",
        "Other/none": "Rejection"}


def znorm(X):
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def proto_scores(Xtr, ytr, Xte, classes):
    """Cosine similarity to each class prototype (the incumbent's mechanism)."""
    sc = StandardScaler().fit(Xtr)
    Ztr, Zte = znorm(sc.transform(Xtr)), znorm(sc.transform(Xte))
    C = znorm(np.vstack([Ztr[ytr == c].mean(0) if (ytr == c).any()
                         else np.zeros(Ztr.shape[1]) for c in classes]))
    return Zte @ C.T


def softmax(S, T=8.0):
    e = np.exp((S - S.max(1, keepdims=True)) * T)
    return e / e.sum(1, keepdims=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    a = ap.parse_args()

    d = ec.load()
    keep = np.isin(d["y"], ec.DRUM10)
    X, y, g = d["X"][keep], d["y"][keep], d["vendor"][keep]
    exact = ec.DRUM10
    fams = sorted(set(FAMILY[c] for c in exact))
    forms = sorted(set(FORM[c] for c in exact))
    yf = np.array([FAMILY[c] for c in y])
    ym = np.array([FORM[c] for c in y])
    print(f"{len(y)} files, {len(set(g))} collections")
    print(f"axes: {len(exact)} exact, {len(fams)} families, {len(forms)} forms\n")

    methods = ["flat", "independent", "hierarchical", "form_gated", "soft_parent"]
    acc = {m: [] for m in methods}
    famacc = {m: [] for m in methods}
    formacc = {m: [] for m in methods}
    subgiven = {m: [] for m in methods}
    f1s = {m: [] for m in methods}
    invalid = {m: [] for m in methods}

    for s in range(a.seeds):
        cv = StratifiedGroupKFold(a.splits, shuffle=True, random_state=s)
        pred = {m: np.empty(len(y), dtype=object) for m in methods}
        for tr, te in cv.split(X, y, groups=g):
            assert not (set(g[tr]) & set(g[te])), "collection leak"
            Se = proto_scores(X[tr], y[tr], X[te], exact)
            Sf = proto_scores(X[tr], yf[tr], X[te], fams)
            Sm = proto_scores(X[tr], ym[tr], X[te], forms)
            Pe, Pf, Pm = softmax(Se), softmax(Sf), softmax(Sm)

            pred["flat"][te] = np.array(exact)[Se.argmax(1)]

            # independent: joint score over valid (family, form) cells only
            joint = np.zeros((len(te), len(exact)))
            for j, c in enumerate(exact):
                joint[:, j] = (Pf[:, fams.index(FAMILY[c])]
                               * Pm[:, forms.index(FORM[c])])
            pred["independent"][te] = np.array(exact)[joint.argmax(1)]

            # hierarchical: choose form, then best exact class within that form
            chosen = np.array(forms)[Pm.argmax(1)]
            out = []
            for i in range(len(te)):
                allowed = [j for j, c in enumerate(exact)
                           if FORM[c] == chosen[i]]
                if not allowed:
                    allowed = list(range(len(exact)))
                out.append(exact[allowed[int(np.argmax(Se[i, allowed]))]])
            pred["hierarchical"][te] = np.array(out)

            # form_gated: keep the flat answer unless the form axis is confident
            # and disagrees, in which case fall back within the predicted form
            out = []
            for i in range(len(te)):
                flat_c = exact[int(Se[i].argmax())]
                if Pm[i].max() > 0.6 and FORM[flat_c] != chosen[i]:
                    allowed = [j for j, c in enumerate(exact)
                               if FORM[c] == chosen[i]] or list(range(len(exact)))
                    out.append(exact[allowed[int(np.argmax(Se[i, allowed]))]])
                else:
                    out.append(flat_c)
            pred["form_gated"][te] = np.array(out)

            # soft_parent: flat scores nudged toward the predicted family
            bonus = np.zeros_like(Se)
            for j, c in enumerate(exact):
                bonus[:, j] = 0.25 * Pf[:, fams.index(FAMILY[c])]
            pred["soft_parent"][te] = np.array(exact)[(Se + bonus).argmax(1)]

        for m in methods:
            p = pred[m]
            ok = p != None
            acc[m].append(100 * float((p[ok] == y[ok]).mean()))
            pf = np.array([FAMILY[c] for c in p[ok]])
            pm = np.array([FORM[c] for c in p[ok]])
            famacc[m].append(100 * float((pf == yf[ok]).mean()))
            formacc[m].append(100 * float((pm == ym[ok]).mean()))
            corr_fam = pf == yf[ok]
            subgiven[m].append(100 * float((p[ok][corr_fam] == y[ok][corr_fam]).mean()))
            f1s[m].append(100 * f1_score(y[ok], p[ok].astype(str),
                                         average="macro", zero_division=0))
            invalid[m].append(0.0)   # construction guarantees valid combinations

    print(f"{'method':14} {'exact':>15} {'family':>9} {'form':>8} "
          f"{'sub|fam':>9} {'macroF1':>9} {'delta':>8}")
    base = float(np.mean(acc["flat"]))
    res = {}
    for m in methods:
        e = float(np.mean(acc[m])); dl = e - base
        flag = "  <-- GATE" if dl >= GATE else ""
        print(f"{m:14} {e:7.2f}% +-{np.std(acc[m]):4.2f} "
              f"{np.mean(famacc[m]):8.2f}% {np.mean(formacc[m]):7.2f}% "
              f"{np.mean(subgiven[m]):8.2f}% {np.mean(f1s[m]):8.2f} "
              f"{dl:+7.2f}{flag}")
        res[m] = {"exact": round(e, 2), "sd": round(float(np.std(acc[m])), 2),
                  "per_seed": [round(v, 2) for v in acc[m]],
                  "family": round(float(np.mean(famacc[m])), 2),
                  "form": round(float(np.mean(formacc[m])), 2),
                  "subtype_given_family": round(float(np.mean(subgiven[m])), 2),
                  "macro_f1": round(float(np.mean(f1s[m])), 2),
                  "invalid_combination_rate": 0.0,
                  "delta_vs_flat": round(dl, 2)}
    json.dump({"gate_pp": GATE, "seeds": a.seeds, "family_map": FAMILY,
               "form_map": FORM, "results": res,
               "promoted": [m for m in methods if res[m]["delta_vs_flat"] >= GATE]},
              open(OUT, "w"), indent=2)
    print(f"\npromoted: "
          f"{[m for m in methods if res[m]['delta_vs_flat'] >= GATE] or 'NONE'}")
    print(f"wrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
