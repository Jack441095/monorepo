#!/usr/bin/env python3
"""
Phase 2 -- attack the vendor gap directly, on cached embeddings.

Phase 1 established that random CV overstates unseen-collection accuracy by
about 10 percentage points, and that vendor identity is linearly decodable from
the Perch+CLAP embedding far above chance. The representation encodes which
pack a sound came from, not only what the sound is.

This tests whether that is fixable with cheap methods over the frozen
embedding, before anything expensive is attempted.

  baseline        class-balanced logistic regression (the incumbent)
  vendor-balanced weight so a large vendor cannot dominate by file count alone
  class x vendor  balance the joint cell, not the margins
  vendor-capped   hard cap on examples per vendor
  groupDRO        worst-group objective rather than average loss
  DANN            projection + class head + vendor adversary (gradient reversal)
  CORAL           whiten/align second-order statistics across training vendors
  cosine kNN      metric baseline
  nearest centroid / multi-centroid / shrinkage LDA

Everything is evaluated with domain_generalization_eval's grouped splits, the
same folds and seeds for every method, and reported per seed.

PROMOTION GATE (stated before running, so it cannot be moved afterwards):
a method advances only on >= +2pp mean vendor-held-out accuracy across repeated
seeds with no macro-F1 regression, OR a material worst-group gain with stable
mean, OR equal accuracy with better precision-at-coverage.

Usage:
  python3 domain_robust_baselines.py --seeds 5 --mode vendor
"""
import os, json, time, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import domain_generalization_eval as dg   # noqa: E402

OUT_JSON = os.path.join(SD, "results_domain_robust_v1.json")
GATE_PP = 2.0


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def group_weights(y, g, scheme):
    """Per-example weights implementing the various balancing schemes."""
    from collections import Counter
    n = len(y)
    if scheme == "class":
        c = Counter(y)
        return np.array([n / (len(c) * c[v]) for v in y], dtype=float)
    if scheme == "vendor":
        c = Counter(g)
        return np.array([n / (len(c) * c[v]) for v in g], dtype=float)
    if scheme == "class_x_vendor":
        cy, cg = Counter(y), Counter(zip(y, g))
        return np.array([n / (len(cy) * max(cg[(a, b)], 1) * 1.0)
                         for a, b in zip(y, g)], dtype=float)
    raise ValueError(scheme)


def cap_per_vendor(y, g, cap, rng):
    """Indices after hard-capping examples per vendor (class-stratified)."""
    keep = []
    for v in np.unique(g):
        idx = np.where(g == v)[0]
        if len(idx) <= cap:
            keep.extend(idx)
        else:
            keep.extend(rng.choice(idx, cap, replace=False))
    return np.array(sorted(keep))


def worst_group_acc(pred, y, g, min_n=8):
    accs = []
    for v in np.unique(g):
        m = g == v
        if m.sum() >= min_n:
            accs.append(float((pred[m] == y[m]).mean()))
    return 100 * min(accs) if accs else float("nan")


# --------------------------------------------------------------------------
# torch heads (GroupDRO / DANN / CORAL share a scaffold)
# --------------------------------------------------------------------------
def _torch_head(Xtr, ytr, gtr, Xte, n_classes, mode, seed,
                epochs=120, lr=1e-3, proj=128, alpha=1.0, dro_eta=0.01):
    import torch
    import torch.nn as nn
    torch.manual_seed(seed)
    dev = "cpu"
    Xtr_t = torch.tensor(Xtr, dtype=torch.float32, device=dev)
    ytr_t = torch.tensor(ytr, dtype=torch.long, device=dev)
    Xte_t = torch.tensor(Xte, dtype=torch.float32, device=dev)
    gid = {v: i for i, v in enumerate(np.unique(gtr))}
    gtr_t = torch.tensor([gid[v] for v in gtr], dtype=torch.long, device=dev)
    n_groups = len(gid)

    class GRL(torch.autograd.Function):
        @staticmethod
        def forward(ctx, x, a):
            ctx.a = a
            return x.view_as(x)

        @staticmethod
        def backward(ctx, gout):
            return -ctx.a * gout, None

    enc = nn.Sequential(nn.Linear(Xtr.shape[1], proj), nn.ReLU(),
                        nn.LayerNorm(proj)).to(dev)
    head = nn.Linear(proj, n_classes).to(dev)
    adv = nn.Linear(proj, n_groups).to(dev)
    params = list(enc.parameters()) + list(head.parameters())
    if mode == "dann":
        params += list(adv.parameters())
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=1e-4)

    cnt = np.bincount(ytr, minlength=n_classes).astype(np.float32)
    w = torch.tensor(len(ytr) / (n_classes * np.maximum(cnt, 1)),
                     dtype=torch.float32, device=dev)
    ce = nn.CrossEntropyLoss(weight=w)
    ce_none = nn.CrossEntropyLoss(weight=w, reduction="none")
    q = torch.ones(n_groups, device=dev) / n_groups     # GroupDRO weights

    for ep in range(epochs):
        opt.zero_grad()
        z = enc(Xtr_t)
        logits = head(z)
        if mode == "groupdro":
            per = ce_none(logits, ytr_t)
            gl = torch.zeros(n_groups, device=dev)
            for gi in range(n_groups):
                m = gtr_t == gi
                if m.any():
                    gl[gi] = per[m].mean()
            with torch.no_grad():
                q_new = q * torch.exp(dro_eta * gl)
                q.copy_(q_new / q_new.sum())
            loss = (q * gl).sum()
        elif mode == "dann":
            loss = ce(logits, ytr_t)
            prog = ep / max(epochs - 1, 1)
            a = alpha * (2.0 / (1.0 + np.exp(-10 * prog)) - 1.0)
            loss = loss + ce_adv(adv, GRL.apply(z, a), gtr_t)
        elif mode == "coral":
            loss = ce(logits, ytr_t)
            loss = loss + alpha * coral_penalty(z, gtr_t, n_groups)
        else:
            loss = ce(logits, ytr_t)
        loss.backward()
        opt.step()

    enc.eval(); head.eval()
    with torch.no_grad():
        pred = head(enc(Xte_t)).argmax(1).cpu().numpy()
        ztr = enc(Xtr_t).cpu().numpy()
        zte = enc(Xte_t).cpu().numpy()
    return pred, ztr, zte


def ce_adv(adv, z, g):
    import torch.nn as nn
    return nn.functional.cross_entropy(adv(z), g)


def coral_penalty(z, gid, n_groups):
    """Penalise differences in second-order statistics between training groups."""
    import torch
    covs = []
    for gi in range(n_groups):
        m = gid == gi
        if m.sum() < 4:
            continue
        zz = z[m] - z[m].mean(0, keepdim=True)
        covs.append(zz.T @ zz / (m.sum() - 1))
    if len(covs) < 2:
        return torch.zeros((), device=z.device)
    mean_cov = torch.stack(covs).mean(0)
    return torch.stack([((c - mean_cov) ** 2).mean() for c in covs]).mean()


# --------------------------------------------------------------------------
# methods
# --------------------------------------------------------------------------
def run_method(name, d, mode, seeds, splits, feat="perch+clap"):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.neighbors import KNeighborsClassifier, NearestCentroid
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.cluster import KMeans
    from sklearn.metrics import f1_score

    X, y = d["feats"][feat], d["y"]
    vend = d["vendor"]
    classes = sorted(set(y))
    cls_idx = {c: i for i, c in enumerate(classes)}
    accs, f1s, worst = [], [], []
    for s in range(seeds):
        rng = np.random.RandomState(s)
        oof = np.empty(len(y), dtype=object)
        for tr, te in dg.splits_for(mode, d, splits, s):
            Xtr, ytr, gtr = X[tr], y[tr], vend[tr]
            sw = None
            if name == "baseline":
                sw = group_weights(ytr, gtr, "class")
            elif name == "vendor-balanced":
                sw = group_weights(ytr, gtr, "class") * group_weights(ytr, gtr, "vendor")
            elif name == "class_x_vendor":
                sw = group_weights(ytr, gtr, "class_x_vendor")
            elif name == "vendor-capped":
                sel = cap_per_vendor(ytr, gtr, 40, rng)
                Xtr, ytr, gtr = Xtr[sel], ytr[sel], gtr[sel]
                sw = group_weights(ytr, gtr, "class")

            if name in ("baseline", "vendor-balanced", "class_x_vendor",
                        "vendor-capped"):
                sc = StandardScaler().fit(Xtr)
                clf = LogisticRegression(max_iter=3000)
                clf.fit(sc.transform(Xtr), ytr, sample_weight=sw)
                oof[te] = clf.predict(sc.transform(X[te]))
            elif name in ("groupDRO", "DANN", "CORAL"):
                sc = StandardScaler().fit(Xtr)
                yi = np.array([cls_idx[c] for c in ytr])
                m = {"groupDRO": "groupdro", "DANN": "dann", "CORAL": "coral"}[name]
                pred, _, _ = _torch_head(sc.transform(Xtr), yi, gtr,
                                         sc.transform(X[te]), len(classes), m, s)
                oof[te] = np.array(classes)[pred]
            elif name == "cosine-kNN":
                clf = make_pipeline(StandardScaler(),
                                    KNeighborsClassifier(15, metric="cosine",
                                                         weights="distance"))
                clf.fit(Xtr, ytr); oof[te] = clf.predict(X[te])
            elif name == "nearest-centroid":
                clf = make_pipeline(StandardScaler(), NearestCentroid())
                clf.fit(Xtr, ytr); oof[te] = clf.predict(X[te])
            elif name == "multi-centroid":
                sc = StandardScaler().fit(Xtr)
                Z = sc.transform(Xtr); Zt = sc.transform(X[te])
                cents, labs = [], []
                for c in classes:
                    zc = Z[ytr == c]
                    if len(zc) == 0:
                        continue
                    k = min(3, max(1, len(zc) // 12))
                    km = KMeans(k, n_init=4, random_state=s).fit(zc)
                    cents.append(km.cluster_centers_); labs += [c] * k
                C = np.vstack(cents)
                Cn = C / (np.linalg.norm(C, axis=1, keepdims=True) + 1e-9)
                Zn = Zt / (np.linalg.norm(Zt, axis=1, keepdims=True) + 1e-9)
                oof[te] = np.array(labs)[(Zn @ Cn.T).argmax(1)]
            elif name == "shrinkage-LDA":
                clf = make_pipeline(StandardScaler(),
                                    LinearDiscriminantAnalysis(solver="lsqr",
                                                               shrinkage="auto"))
                clf.fit(Xtr, ytr); oof[te] = clf.predict(X[te])
            else:
                raise ValueError(name)
        ok = oof != None                                       # noqa: E711
        accs.append(100 * float((oof[ok] == y[ok]).mean()))
        f1s.append(100 * f1_score(y[ok], oof[ok].astype(str), average="macro",
                                  zero_division=0))
        worst.append(worst_group_acc(oof[ok], y[ok], vend[ok]))
    return dict(acc=float(np.mean(accs)), sd=float(np.std(accs)),
                per_seed=[round(v, 2) for v in accs],
                macro_f1=float(np.mean(f1s)),
                worst_group=float(np.nanmean(worst)))


METHODS = ["baseline", "vendor-balanced", "class_x_vendor", "vendor-capped",
           "groupDRO", "DANN", "CORAL", "cosine-kNN", "nearest-centroid",
           "multi-centroid", "shrinkage-LDA"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--mode", default="vendor", choices=dg.MODES)
    ap.add_argument("--methods", default=",".join(METHODS))
    a = ap.parse_args()

    d = dg.load_corpus()
    print(f"{len(d['y'])} files, {len(d['classes'])} classes, mode={a.mode}, "
          f"{a.seeds} seeds\n")
    print(f"{'method':20} {'acc':>16} {'macroF1':>9} {'worstgrp':>9} {'vs base':>9}")
    res, base = {}, None
    for name in a.methods.split(","):
        t0 = time.time()
        r = run_method(name, d, a.mode, a.seeds, a.splits)
        res[name] = r
        if base is None:
            base = r["acc"]
        delta = r["acc"] - base
        flag = ""
        if name != "baseline":
            se = r["sd"] / max(np.sqrt(a.seeds), 1)
            flag = "  <-- GATE" if (delta >= GATE_PP and
                                    r["macro_f1"] >= res["baseline"]["macro_f1"]) else ""
        print(f"{name:20} {r['acc']:7.1f}% +-{r['sd']:4.1f} {r['macro_f1']:8.1f}% "
              f"{r['worst_group']:8.1f}% {delta:+8.2f}{flag}  ({time.time()-t0:.0f}s)")

    payload = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": a.mode,
               "seeds": a.seeds, "splits": a.splits, "gate_pp": GATE_PP,
               "n_files": int(len(d["y"])), "results": res,
               "promoted": [k for k, v in res.items()
                            if k != "baseline" and v["acc"] - base >= GATE_PP
                            and v["macro_f1"] >= res["baseline"]["macro_f1"]]}
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\npromoted: {payload['promoted'] or 'NONE -- no method cleared the gate'}")
    print(f"wrote {os.path.basename(OUT_JSON)}")


if __name__ == "__main__":
    main()
