#!/usr/bin/env python3
"""
Phase 6 -- multi-window representation.

Perch sees a fixed 5-second window from the START of a file and CLAP pools
globally. A crash's identity is in its tail; a kick's is in its first 50 ms; a
loop's is in how it repeats. All three are averaged away.

This is materially different from the handcrafted-feature routes that failed.
Those added new numbers ALONGSIDE the embedding, and the encoders already knew
the physics. This changes WHAT AUDIO THE ENCODER SEES, which no previous
experiment did.

Views:
  attack   first 250 ms      -- transient identity (Kick, Snare, Clap, Hi-Hat)
  short    first 1 s         -- the hit plus its early decay
  early    first 5 s         -- the incumbent's view (the control)
  centre   middle 5 s        -- steady state of a loop
  tail     last 2 s          -- decay character (Crash vs Hi-Hat)
  spread   4 evenly spaced 1s crops, averaged -- loop structure

Combination strategies compared: single views, normalised concatenation, and
late averaging of per-view prototype scores.

Cache keys include audio identity, encoder identity, crop spec, sample rate and
a preprocessing version, so a changed crop can never silently reuse old rows.
"""
import os, json, time, glob, hashlib, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import eval_corpus_v2 as ec
CACHE_DIR = os.path.join(SD, "mw_cache")
OUT = os.path.join(SD, "results_multiwindow.json")
NATIVE_SR, PERCH_LEN, CLAP_SR = 32000, 160000, 48000
PREPROC = "mw-v1"

VIEWS = {
    "attack": ("head", 0.25),
    "short":  ("head", 1.0),
    "early":  ("head", 5.0),
    "centre": ("centre", 5.0),
    "tail":   ("tail", 2.0),
    "spread": ("spread", 1.0),
}


def crop(y, sr, kind, secs):
    n = int(sr * secs)
    if len(y) == 0:
        return [np.zeros(n, dtype=np.float32)]
    if kind == "head":
        return [y[:n]]
    if kind == "tail":
        return [y[-n:]]
    if kind == "centre":
        m = len(y) // 2
        return [y[max(0, m - n // 2): m + n // 2]]
    if kind == "spread":
        if len(y) <= n:
            return [y]
        starts = np.linspace(0, len(y) - n, 4).astype(int)
        return [y[s:s + n] for s in starts]
    raise ValueError(kind)


_W = {}


def _init():
    import aug_experiment as ax
    _W["enc"] = ax.Encoders()


def _one(task):
    import aug_experiment as ax
    path, = task
    try:
        y = ax._load_native(path)
        if len(y) < NATIVE_SR // 50:
            y = np.pad(y, (0, NATIVE_SR // 50 - len(y)))
        out = {}
        for name, (kind, secs) in VIEWS.items():
            chunks = crop(y, NATIVE_SR, kind, secs)
            chunks = [c if len(c) else np.zeros(int(NATIVE_SR * secs), np.float32)
                      for c in chunks]
            em = _W["enc"].embed(chunks)
            out[name] = em.mean(0).astype(np.float32)
        if not all(np.isfinite(v).all() for v in out.values()):
            return (path, None, "non-finite")
        return (path, out, None)
    except Exception as e:
        return (path, None, str(e)[:70])


def cache_file():
    key = hashlib.sha256(
        (PREPROC + json.dumps(VIEWS, sort_keys=True)
         + f"|perch{PERCH_LEN}|clap{CLAP_SR}|sr{NATIVE_SR}").encode()
    ).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"mw_{PREPROC}_{key}.npz")


def extract(paths, workers, chunk=25):
    from multiprocessing import Pool
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = cache_file()
    done = {}
    if os.path.exists(cp):
        z = np.load(cp, allow_pickle=True)
        names = list(z["views"])
        for i, p in enumerate(list(z["paths"])):
            done[p] = {n: z["E"][j][i] for j, n in enumerate(names)}
        print(f"  resuming: {len(done)} cached")
    todo = [p for p in paths if p not in done]
    if not todo:
        print(f"  complete ({len(done)} files)")
        return done
    print(f"  {len(todo)} files on {workers} workers")
    t0 = time.time()
    fails = 0
    with Pool(workers, initializer=_init) as pool:
        for i, (p, o, err) in enumerate(
                pool.imap_unordered(_one, [(q,) for q in todo], chunksize=1)):
            if err:
                fails += 1
            else:
                done[p] = o
            if (i + 1) % chunk == 0 or i == len(todo) - 1:
                keep = [q for q in paths if q in done]
                names = list(VIEWS)
                E = np.stack([np.stack([done[q][n] for q in keep])
                              for n in names])
                tmp = cp + ".tmp.npz"
                np.savez(tmp, E=E, paths=np.array(keep, dtype=object),
                         views=np.array(names, dtype=object))
                os.replace(tmp, cp)
                r = (i + 1) / (time.time() - t0)
                print(f"    {i+1}/{len(todo)}  {r:.2f}/s  "
                      f"eta {(len(todo)-i-1)/max(r,1e-9)/60:.1f}min", flush=True)
    if fails:
        print(f"    {fails} failures")
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--splits", type=int, default=5)
    a = ap.parse_args()

    d = ec.load()
    keep = np.isin(d["y"], ec.DRUM10)
    paths = [p for p, k in zip(d["paths"], keep) if k]
    y, g = d["y"][keep], d["vendor"][keep]
    print(f"{len(paths)} files, {len(set(g))} collections")

    if a.extract:
        extract(paths, a.workers)
        return 0

    cp = cache_file()
    if not os.path.exists(cp):
        raise SystemExit("no cache -- run --extract first")
    z = np.load(cp, allow_pickle=True)
    names = list(z["views"])
    have = {p: i for i, p in enumerate(list(z["paths"]))}
    miss = [p for p in paths if p not in have]
    if miss:
        print(f"  {len(miss)} files missing from cache -- dropping them")
        sel = [i for i, p in enumerate(paths) if p in have]
        paths = [paths[i] for i in sel]; y = y[sel]; g = g[sel]
    V = {n: np.stack([z["E"][j][have[p]] for p in paths])
         for j, n in enumerate(names)}
    print(f"views: {names}, each {V[names[0]].shape}\n")

    import incumbent_receipt as ir
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.metrics import f1_score
    classes = ec.DRUM10

    def run(feat_fn, label):
        accs, f1s = [], []
        per_cls = {c: [] for c in classes}
        for s in range(a.seeds):
            cv = StratifiedGroupKFold(a.splits, shuffle=True, random_state=s)
            oof = np.empty(len(y), dtype=object)
            for tr, te in cv.split(np.zeros(len(y)), y, groups=g):
                assert not (set(g[tr]) & set(g[te])), "leak"
                oof[te] = feat_fn(tr, te, s)
            ok = oof != None
            accs.append(100 * float((oof[ok] == y[ok]).mean()))
            f1s.append(100 * f1_score(y[ok], oof[ok].astype(str),
                                      average="macro", zero_division=0))
            for c in classes:
                m = y == c
                per_cls[c].append(100 * float((oof[m] == c).mean()))
        return (float(np.mean(accs)), float(np.std(accs)), float(np.mean(f1s)),
                {c: round(float(np.mean(v)), 1) for c, v in per_cls.items()})

    def single(name):
        X = V[name]
        return lambda tr, te, s: ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)[0]

    def concat(ns):
        X = np.hstack([V[n] / (np.linalg.norm(V[n], axis=1, keepdims=True) + 1e-9)
                       for n in ns])
        return lambda tr, te, s: ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)[0]

    def late(ns):
        def f(tr, te, s):
            import factorised_taxonomy as ft
            tot = None
            for n in ns:
                X = V[n]
                sc = ft.proto_scores(X[tr], y[tr], X[te], classes)
                p = ft.softmax(sc)
                tot = p if tot is None else tot + p
            return np.array(classes)[tot.argmax(1)]
        return f

    res = {}
    print(f"{'representation':34} {'acc':>15} {'macroF1':>9} {'delta':>8}")
    base = None
    for n in names:
        m_, sd_, f_, pc = run(single(n), n)
        if n == "early":
            base = m_
        res[f"single:{n}"] = {"acc": round(m_, 2), "sd": round(sd_, 2),
                              "macro_f1": round(f_, 2), "per_class": pc}
        print(f"{'single: '+n:34} {m_:7.2f}% +-{sd_:4.2f} {f_:8.2f}"
              f"{'   (control)' if n=='early' else ''}")
    for label, ns in (("attack+early", ["attack", "early"]),
                      ("early+tail", ["early", "tail"]),
                      ("attack+early+tail", ["attack", "early", "tail"]),
                      ("all six", names)):
        m_, sd_, f_, pc = run(concat(ns), label)
        res[f"concat:{label}"] = {"acc": round(m_, 2), "sd": round(sd_, 2),
                                  "macro_f1": round(f_, 2), "per_class": pc}
        print(f"{'concat: '+label:34} {m_:7.2f}% +-{sd_:4.2f} {f_:8.2f} "
              f"{m_-base:+7.2f}")
        m_, sd_, f_, pc = run(late(ns), label)
        res[f"late:{label}"] = {"acc": round(m_, 2), "sd": round(sd_, 2),
                                "macro_f1": round(f_, 2), "per_class": pc}
        print(f"{'late-fuse: '+label:34} {m_:7.2f}% +-{sd_:4.2f} {f_:8.2f} "
              f"{m_-base:+7.2f}")

    print("\ntargeted questions:")
    e = res["single:early"]["per_class"]
    for view, q in (("attack", ["Kick", "Snare", "Clap", "Hi-Hat"]),
                    ("tail", ["Crash", "Hi-Hat"]),
                    ("spread", ["Drum Loop", "Percussion Loop"])):
        v = res[f"single:{view}"]["per_class"]
        bits = "  ".join(f"{c} {v[c]:.0f}% ({v[c]-e[c]:+.0f})" for c in q)
        print(f"  {view:8} {bits}")
    best = max(res, key=lambda k: res[k]["acc"])
    print(f"\nbest: {best} {res[best]['acc']}%  vs control(early) {base:.2f}%  "
          f"-> {res[best]['acc']-base:+.2f}pp")
    json.dump({"views": VIEWS, "seeds": a.seeds, "control": "single:early",
               "results": res, "best": best}, open(OUT, "w"), indent=2)
    print(f"wrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    raise SystemExit(main())
