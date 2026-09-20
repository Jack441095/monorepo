#!/usr/bin/env python3
"""
Canonical grouped evaluation for the by-ear corpus.

The problem this exists to measure
----------------------------------
Every accuracy figure in this project was produced with ordinary
StratifiedKFold. That silently assumes files are independent. They are not:
55% of the 576 by-ear labels come from three collections, and 175 of them share
a normalised sample family (velocity layers, round robins, note variants) with
another labelled file. Random CV therefore trains and tests on the same pack,
often on near-identical renders of the same hit, and reports a number that has
no bearing on how the product behaves when a user loads a library it has never
seen.

This script is the single source of truth for grouped evaluation. Any future
claim of improvement must be reproduced here, under a grouping, with repeated
seeds.

Grouping modes
--------------
  random   ordinary StratifiedKFold                       -- the old, optimistic number
  family   normalised sample families never split         -- removes near-duplicate leakage
  pack     whole packs held out                           -- unseen pack
  vendor   whole vendors/collections held out             -- unseen library (the product case)
  packfam  pack and family combined                       -- belt and braces

Guarantees
----------
* Alignment is asserted, never assumed: paths, labels and every feature matrix
  must have identical row counts, and paths must be unique. Fails closed.
* Group isolation is verified at run time for every fold, not just asserted in
  a comment. A group appearing on both sides of a split raises.
* Deterministic from an explicit seed.
* Reports raw per-seed scores, not just means, because this project has twice
  been misled by single-split deltas (sections 21 and 32).

Usage:
  python3 domain_generalization_eval.py --seeds 3          # cheap precheck
  python3 domain_generalization_eval.py --seeds 8 --report # canonical
"""
import os, csv, json, time, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.abspath(os.path.join(SD, "..", "..", "docs", "classification"))
VERIFIED = os.path.join(SD, "verified_drums.csv")
EMB = os.path.join(SD, "bioacoustic_emb.npz")
OUT_JSON = os.path.join(SD, "results_domain_generalization_v1.json")
OUT_MD = os.path.join(DOCS, "SLO_DOMAIN_GENERALIZATION_V1_REPORT.md")

MODES = ["random", "family", "pack", "vendor", "packfam"]


# --------------------------------------------------------------------------
# alignment-safe loading
# --------------------------------------------------------------------------
def load_corpus(min_class=15):
    import sample_library_inventory as inv
    rows = [r for r in csv.DictReader(open(VERIFIED))
            if r["label"] not in ("__skip__", "Misc/Review")
            and os.path.exists(r["path"])]
    paths = [r["path"] for r in rows]
    y = np.array([r["label"] for r in rows])

    z = np.load(EMB)
    feats = {"perch": z["perch"], "clap": z["clap"]}
    feats["perch+clap"] = np.hstack([z["perch"], z["clap"]])
    # The cache was built from this same ordered, same-filtered row list, so row
    # i of every feature matrix corresponds to paths[i]. Verify that before
    # touching anything -- if it does not hold, no amount of later care helps.
    for k, v in feats.items():
        if len(v) != len(paths):
            raise SystemExit(f"FAIL CLOSED: feature '{k}' has {len(v)} rows but "
                             f"{len(paths)} labelled files exist on disk. The "
                             f"embedding cache is stale -- rebuild it rather "
                             f"than indexing across a mismatch.")

    # Deduplicate by path. The labelling manifest queued six files under two ids
    # each (one via a requeue rewrite), so they were labelled twice. All six
    # pairs agree exactly, which is a small independent check on label
    # consistency, so dropping the later copy loses no information. Selecting
    # first-occurrence INDICES and slicing every array by the same index vector
    # keeps features, labels and groups aligned by construction.
    seen, keep, dup_pairs = {}, [], []
    for i, p in enumerate(paths):
        if p in seen:
            dup_pairs.append((seen[p], i, y[seen[p]] == y[i]))
        else:
            seen[p] = i
            keep.append(i)
    keep = np.array(keep, dtype=int)
    if dup_pairs:
        disagree = [dp for dp in dup_pairs if not dp[2]]
        if disagree:
            raise SystemExit(
                f"FAIL CLOSED: {len(disagree)} duplicate paths carry CONFLICTING "
                f"by-ear labels. That is a labelling problem, not a dedup "
                f"problem -- resolve it by ear rather than picking one silently.")
        print(f"  deduplicated {len(dup_pairs)} repeat-labelled files "
              f"(all labels agreed); {len(keep)} unique remain")
        paths = [paths[i] for i in keep]
        y = y[keep]
        feats = {k: v[keep] for k, v in feats.items()}
    attrib = [inv.attribute(p) for p in paths]
    vendor = np.array([a[1] for a in attrib])
    pack = np.array([f"{a[1]}||{a[2]}" for a in attrib])
    family = np.array([inv.family_id(a[1], a[2], os.path.basename(p))
                       for a, p in zip(attrib, paths)])
    if (vendor == "").any():
        raise SystemExit("FAIL CLOSED: empty vendor string present")

    from collections import Counter
    cnt = Counter(y)
    viable = sorted(c for c in cnt if cnt[c] >= min_class)
    m = np.isin(y, viable)
    return dict(paths=[p for p, k in zip(paths, m) if k], y=y[m],
                feats={k: v[m] for k, v in feats.items()},
                vendor=vendor[m], pack=pack[m], family=family[m],
                classes=viable, n_all=len(paths))


def groups_for(mode, d):
    if mode == "random":
        return None
    if mode == "family":
        return d["family"]
    if mode == "pack":
        return d["pack"]
    if mode == "vendor":
        return d["vendor"]
    if mode == "packfam":
        # a family belongs to exactly one pack, so pack already dominates;
        # combining is a no-op guard against odd family IDs spanning packs
        return np.array([f"{p}##{f}" for p, f in zip(d["pack"], d["family"])])
    raise ValueError(mode)


def splits_for(mode, d, n_splits, seed):
    """Yield (train_idx, test_idx), verifying group isolation every time."""
    from sklearn.model_selection import StratifiedKFold, StratifiedGroupKFold
    y = d["y"]
    g = groups_for(mode, d)
    if g is None:
        cv = StratifiedKFold(n_splits, shuffle=True, random_state=seed)
        it = cv.split(np.zeros(len(y)), y)
    else:
        cv = StratifiedGroupKFold(n_splits, shuffle=True, random_state=seed)
        it = cv.split(np.zeros(len(y)), y, groups=g)
    for tr, te in it:
        if g is not None:
            overlap = set(g[tr]) & set(g[te])
            if overlap:
                raise AssertionError(
                    f"GROUP LEAK in mode '{mode}': {len(overlap)} groups on both "
                    f"sides, e.g. {sorted(overlap)[:3]}")
        yield tr, te


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def precision_at_coverage(proba, y_true, classes, cov=0.5):
    conf = proba.max(1)
    pred = np.array(classes)[proba.argmax(1)]
    k = max(1, int(len(conf) * cov))
    idx = np.argsort(-conf)[:k]
    return float((pred[idx] == y_true[idx]).mean())


def evaluate(d, feat_key, mode, seeds, n_splits, model="logreg"):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.metrics import f1_score
    X, y = d["feats"][feat_key], d["y"]
    classes = d["classes"]
    per_seed, per_seed_f1, worst_folds, top2s, pac = [], [], [], [], []
    oof_last = None
    for s in range(seeds):
        oof = np.empty(len(y), dtype=object)
        proba = np.zeros((len(y), len(classes)))
        fold_acc = []
        for tr, te in splits_for(mode, d, n_splits, s):
            if len(np.unique(y[tr])) < 2:
                continue
            if model == "knn":
                clf = make_pipeline(StandardScaler(),
                                    KNeighborsClassifier(15, metric="cosine",
                                                         weights="distance"))
            else:
                clf = make_pipeline(StandardScaler(),
                                    LogisticRegression(max_iter=3000,
                                                       class_weight="balanced"))
            clf.fit(X[tr], y[tr])
            p = clf.predict(X[te])
            oof[te] = p
            pr = clf.predict_proba(X[te])
            cls_order = list(clf.classes_)
            for j, c in enumerate(classes):
                if c in cls_order:
                    proba[te, j] = pr[:, cls_order.index(c)]
            fold_acc.append(float((p == y[te]).mean()))
        ok = oof != None                                       # noqa: E711
        acc = float((oof[ok] == y[ok]).mean())
        per_seed.append(100 * acc)
        per_seed_f1.append(100 * f1_score(y[ok], oof[ok].astype(str),
                                          average="macro", zero_division=0))
        worst_folds.append(100 * min(fold_acc) if fold_acc else float("nan"))
        order = np.argsort(-proba, 1)[:, :2]
        top2 = np.mean([y[i] in [classes[j] for j in order[i]]
                        for i in range(len(y))])
        top2s.append(100 * top2)
        pac.append(100 * precision_at_coverage(proba, y, classes, 0.5))
        oof_last = oof
    return dict(acc_mean=float(np.mean(per_seed)), acc_sd=float(np.std(per_seed)),
                per_seed=[round(v, 2) for v in per_seed],
                macro_f1=float(np.mean(per_seed_f1)),
                worst_fold=float(np.mean(worst_folds)),
                top2=float(np.mean(top2s)),
                prec_at_50cov=float(np.mean(pac)),
                oof=oof_last)


def per_class_table(y, oof, classes):
    from sklearn.metrics import precision_recall_fscore_support
    ok = oof != None                                           # noqa: E711
    p, r, f, sup = precision_recall_fscore_support(
        y[ok], oof[ok].astype(str), labels=classes, zero_division=0)
    return {c: dict(precision=round(100 * p[i], 1), recall=round(100 * r[i], 1),
                    f1=round(100 * f[i], 1), n=int(sup[i]))
            for i, c in enumerate(classes)}


def vendor_breakdown(d, oof):
    out = {}
    ok = oof != None                                           # noqa: E711
    for v in sorted(set(d["vendor"])):
        m = (d["vendor"] == v) & ok
        if m.sum() >= 8:
            out[v] = dict(n=int(m.sum()),
                          acc=round(100 * float((oof[m] == d["y"][m]).mean()), 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--min-class", type=int, default=15)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    d = load_corpus(a.min_class)
    print(f"{len(d['y'])} files ({d['n_all']} labelled on disk), "
          f"{len(d['classes'])} classes")
    print(f"vendors {len(set(d['vendor']))}  packs {len(set(d['pack']))}  "
          f"families {len(set(d['family']))}\n")

    res = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "n_files": int(len(d["y"])), "classes": d["classes"],
           "seeds": a.seeds, "splits": a.splits,
           "n_vendors": len(set(d["vendor"])), "n_packs": len(set(d["pack"])),
           "n_families": len(set(d["family"])), "grid": {}}

    print(f"{'features':13} {'mode':9} {'acc':>15} {'macroF1':>8} "
          f"{'worstfold':>10} {'top2':>7} {'P@50%':>7}")
    for feat in ("clap", "perch", "perch+clap"):
        for mode in MODES:
            r = evaluate(d, feat, mode, a.seeds, a.splits)
            oof = r.pop("oof")
            r["per_class"] = per_class_table(d["y"], oof, d["classes"])
            if mode == "vendor":
                r["by_vendor"] = vendor_breakdown(d, oof)
            res["grid"][f"{feat}|{mode}"] = r
            print(f"{feat:13} {mode:9} {r['acc_mean']:7.1f}% +-{r['acc_sd']:4.1f} "
                  f"{r['macro_f1']:7.1f}% {r['worst_fold']:9.1f}% "
                  f"{r['top2']:6.1f}% {r['prec_at_50cov']:6.1f}%")

    # cosine kNN under the two decisive modes, same folds
    for mode in ("random", "vendor"):
        r = evaluate(d, "perch+clap", mode, a.seeds, a.splits, model="knn")
        r.pop("oof")
        res["grid"][f"perch+clap-knn|{mode}"] = r
        print(f"{'p+c cosKNN':13} {mode:9} {r['acc_mean']:7.1f}% "
              f"+-{r['acc_sd']:4.1f} {r['macro_f1']:7.1f}%")

    # how much vendor information does the representation carry?
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict, StratifiedKFold
    from collections import Counter
    vc = Counter(d["vendor"])
    big = [v for v in vc if vc[v] >= 15]
    mv = np.isin(d["vendor"], big)
    vp = cross_val_predict(
        make_pipeline(StandardScaler(),
                      LogisticRegression(max_iter=3000, class_weight="balanced")),
        d["feats"]["perch+clap"][mv], d["vendor"][mv],
        cv=StratifiedKFold(5, shuffle=True, random_state=0))
    vacc = 100 * float((vp == d["vendor"][mv]).mean())
    vmaj = 100 * max(vc[v] for v in big) / mv.sum()
    res["vendor_probe"] = dict(accuracy=round(vacc, 1), majority=round(vmaj, 1),
                               n=int(mv.sum()), n_vendors=len(big))
    print(f"\nvendor identity predictable from embedding: {vacc:.1f}% "
          f"(majority {vmaj:.1f}%, {len(big)} vendors, n={int(mv.sum())})")

    g = res["grid"]
    res["headline"] = {
        "random": g["perch+clap|random"]["acc_mean"],
        "family": g["perch+clap|family"]["acc_mean"],
        "pack": g["perch+clap|pack"]["acc_mean"],
        "vendor": g["perch+clap|vendor"]["acc_mean"],
        "random_minus_vendor": round(g["perch+clap|random"]["acc_mean"]
                                     - g["perch+clap|vendor"]["acc_mean"], 2),
        "random_minus_family": round(g["perch+clap|random"]["acc_mean"]
                                     - g["perch+clap|family"]["acc_mean"], 2),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {os.path.basename(OUT_JSON)}  ({time.time()-t0:.0f}s)")
    if a.report:
        write_report(res, d)
        print(f"wrote {OUT_MD}")


def write_report(res, d):
    g = res["grid"]
    h = res["headline"]
    L = []
    A = L.append
    A("# SLO Domain Generalisation — V1\n")
    A(f"_Generated {res['generated']} · {res['n_files']} by-ear files · "
      f"{res['seeds']} seeds × {res['splits']} folds_\n")
    A("## 1. The headline\n")
    A("Every previous accuracy figure in this project used ordinary "
      "StratifiedKFold. That assumes files are independent. They are not: 55% of "
      "the by-ear labels come from three collections, and 175 share a normalised "
      "sample family with another labelled file.\n")
    A("| grouping | what is held out | Perch+CLAP accuracy |")
    A("|---|---|---|")
    for m, desc in (("random", "nothing (the old number)"),
                    ("family", "sample families (velocity/RR/note variants)"),
                    ("pack", "whole packs"),
                    ("vendor", "whole collections — the product case"),
                    ("packfam", "packs and families")):
        r = g[f"perch+clap|{m}"]
        A(f"| `{m}` | {desc} | **{r['acc_mean']:.1f}%** ± {r['acc_sd']:.1f} |")
    A("")
    A(f"**Random-CV overstates unseen-vendor accuracy by "
      f"{h['random_minus_vendor']:.1f} percentage points.**\n")
    A(f"Vendor identity is predictable from the embedding at "
      f"**{res['vendor_probe']['accuracy']:.1f}%** against a "
      f"{res['vendor_probe']['majority']:.1f}% majority baseline "
      f"({res['vendor_probe']['n_vendors']} vendors, n={res['vendor_probe']['n']}), "
      f"so the representation encodes collection identity, not only sound.\n")
    A("## 2. Full grid\n")
    A("| features | grouping | accuracy | macro-F1 | worst fold | top-2 | P@50% cov |")
    A("|---|---|---|---|---|---|---|")
    for k, r in g.items():
        feat, mode = k.split("|")
        A(f"| {feat} | {mode} | {r['acc_mean']:.1f}% ± {r['acc_sd']:.1f} | "
          f"{r['macro_f1']:.1f}% | {r.get('worst_fold', float('nan')):.1f}% | "
          f"{r.get('top2', float('nan')):.1f}% | "
          f"{r.get('prec_at_50cov', float('nan')):.1f}% |")
    A("\n### Raw per-seed accuracy\n")
    A("| key | per-seed |")
    A("|---|---|")
    for k, r in g.items():
        A(f"| {k} | {', '.join(f'{v:.1f}' for v in r['per_seed'])} |")
    A("\n## 3. Which classes collapse on unseen vendors\n")
    A("| class | n | recall (random) | recall (vendor) | delta |")
    A("|---|---|---|---|---|")
    pr = g["perch+clap|random"]["per_class"]
    pv = g["perch+clap|vendor"]["per_class"]
    for c in sorted(pr, key=lambda x: -pr[x]["n"]):
        dlt = pv[c]["recall"] - pr[c]["recall"]
        A(f"| {c} | {pr[c]['n']} | {pr[c]['recall']:.0f}% | "
          f"{pv[c]['recall']:.0f}% | {dlt:+.0f}pp |")
    if "by_vendor" in g["perch+clap|vendor"]:
        A("\n## 4. Per-vendor accuracy when that vendor is unseen\n")
        A("| vendor | n | accuracy |")
        A("|---|---|---|")
        bv = g["perch+clap|vendor"]["by_vendor"]
        for v in sorted(bv, key=lambda x: bv[x]["acc"]):
            A(f"| {v} | {bv[v]['n']} | {bv[v]['acc']:.1f}% |")
    A("\n## 5. Reproduction\n")
    A("```\ncd SmartSampleManager/tools/classification_benchmark\n"
      "python3 sample_library_inventory.py --workers 8\n"
      f"python3 domain_generalization_eval.py --seeds {res['seeds']} --report\n```\n")
    os.makedirs(DOCS, exist_ok=True)
    with open(OUT_MD, "w") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
