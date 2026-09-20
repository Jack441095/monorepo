#!/usr/bin/env python3
"""
Phase 3 -- pack-mastering augmentation, extraction and evaluation.

Method
------
Augmenting a file does not depend on which fold it lands in, so every augmented
embedding is extracted ONCE and cached. At evaluation time only the augmented
rows whose SOURCE is in the training fold are added to training; test folds
always see original audio only. Augmented rows inherit their source's
collection, pack and family, so a variant can never cross the group boundary.

Resumability and alignment
--------------------------
Extraction writes each family's cache atomically after every chunk, keyed by the
source path list and a preprocessing version. A resumed run re-derives which
(file, variant) pairs are missing and extracts only those. The cache stores the
source path for every row, and loading asserts that those paths match the
current corpus in order -- an interrupted run cannot produce silent row
misalignment.

Usage:
  python3 aug_experiment.py --extract --family spectral --pilot 24
  python3 aug_experiment.py --extract --family all
  python3 aug_experiment.py --eval --seeds 3
"""
import os, json, time, glob, hashlib, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import domain_generalization_eval as dg   # noqa: E402
import pack_augment as pa                 # noqa: E402

CACHE_DIR = os.path.join(SD, "aug_cache")
OUT = os.path.join(SD, "results_augmentation_v1.json")
RECEIPT = os.path.join(SD, "incumbent_receipt_v1.json")
PERCH_GLOB = os.path.expanduser(
    "~/.cache/huggingface/hub/models--justinchuby--Perch-onnx/snapshots/*/perch_v2.onnx")
PERCH_SR, PERCH_LEN, CLAP_SR = 32000, 160000, 48000
NATIVE_SR = 32000            # augmentation is applied at this rate
GATE_PP = 2.0


# --------------------------------------------------------------------------
def _load_native(path):
    import soundfile as sf, librosa
    y, s = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(1)
    if s != NATIVE_SR:
        y = librosa.resample(y, orig_sr=s, target_sr=NATIVE_SR)
    return y.astype(np.float32)


def _for_perch(y):
    out = np.zeros(PERCH_LEN, dtype=np.float32)
    n = min(len(y), PERCH_LEN)
    out[:n] = y[:n]
    return out


def _for_clap(y):
    import librosa
    z = librosa.resample(y, orig_sr=NATIVE_SR, target_sr=CLAP_SR)
    return z.astype(np.float32) if len(z) else np.zeros(CLAP_SR, dtype=np.float32)


class Encoders:
    def __init__(self):
        import onnxruntime as ort
        from transformers import ClapModel, ClapProcessor
        so = ort.SessionOptions(); so.intra_op_num_threads = 8
        self.perch = ort.InferenceSession(glob.glob(PERCH_GLOB)[0], so,
                                          providers=["CPUExecutionProvider"])
        md = os.path.join(SD, "clap_model_music")
        self.proc = ClapProcessor.from_pretrained(md)
        self.clap = ClapModel.from_pretrained(md).eval()

    def embed(self, wavs):
        import torch
        p = self.perch.run(["embedding"],
                           {"inputs": np.stack([_for_perch(w) for w in wavs])})[0]
        with torch.no_grad():
            ai = self.proc(audio=[_for_clap(w) for w in wavs],
                           sampling_rate=CLAP_SR, return_tensors="pt", padding=True)
            c = self.clap.get_audio_features(**ai).pooler_output.numpy()
        return np.hstack([p, c]).astype(np.float32)


# --------------------------------------------------------------------------
def cache_path(family):
    return os.path.join(CACHE_DIR, f"{family}_{pa.PREPROC_VERSION}.npz")


def atomic_save(path, **kw):
    tmp = path + ".tmp.npz"
    np.savez(tmp, **kw)
    os.replace(tmp, path)


_W = {}


def _init_worker():
    """One encoder set per worker process; loading costs ~18s so it must not
    happen per file."""
    _W["enc"] = Encoders()


def _one(task):
    """Augment and embed a single source file. Returns (path, emb, variants)."""
    path, family = task
    try:
        y = _load_native(path)
        if len(y) < NATIVE_SR // 50:
            y = np.pad(y, (0, NATIVE_SR // 50 - len(y)))
        seed = int(hashlib.sha256((os.path.basename(path) + family).encode()
                                  ).hexdigest()[:8], 16)
        variants = (pa.combined(y, NATIVE_SR, seed) if family == "combined"
                    else pa.augment(y, NATIVE_SR, family, seed))
        em = _W["enc"].embed(variants)
        if not np.isfinite(em).all():
            return (path, None, None, "non-finite embedding")
        return (path, em.astype(np.float32),
                np.arange(len(variants), dtype=np.int16), None)
    except Exception as e:
        return (path, None, None, str(e)[:80])


def extract_family(paths, family, workers=4, chunk=25):
    """Extract every variant for every file; resumable at chunk granularity."""
    from multiprocessing import Pool
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = cache_path(family)
    done_src, blocks, vblocks = [], [], []
    if os.path.exists(cp):
        z = np.load(cp, allow_pickle=True)
        if str(z["version"]) == pa.PREPROC_VERSION:
            done_src = list(z["src"])
            blocks = [z["emb"]]
            vblocks = [z["variant"]]
            print(f"  resuming: {len(done_src)} rows / "
                  f"{len(set(done_src))} files cached")
    done_files = set(done_src)
    todo = [p for p in paths if p not in done_files]
    if not todo:
        print(f"  {family}: complete ({len(done_files)} files)")
        return
    print(f"  {family}: {len(todo)} files to extract on {workers} workers")

    src_new, emb_new, var_new, failures = [], [], [], []
    t0 = time.time()
    with Pool(workers, initializer=_init_worker) as pool:
        for i, (path, em, vs, err) in enumerate(
                pool.imap_unordered(_one, [(p, family) for p in todo], chunksize=1)):
            if err is not None:
                failures.append((path, err))
            else:
                for k in range(em.shape[0]):
                    src_new.append(path); emb_new.append(em[k]); var_new.append(vs[k])
            if (i + 1) % chunk == 0 or i == len(todo) - 1:
                allsrc = done_src + src_new
                allemb = (np.vstack(blocks + [np.array(emb_new, dtype=np.float32)])
                          if emb_new else np.vstack(blocks))
                allvar = (np.concatenate(vblocks + [np.array(var_new, dtype=np.int16)])
                          if var_new else np.concatenate(vblocks))
                atomic_save(cp, emb=allemb, src=np.array(allsrc, dtype=object),
                            variant=allvar, version=pa.PREPROC_VERSION)
                el = time.time() - t0
                rate = (i + 1) / el
                eta = (len(todo) - i - 1) / max(rate, 1e-9)
                print(f"    {family}: {i+1}/{len(todo)} files  {rate:.2f}/s  "
                      f"eta {eta/60:.1f}min  ({allemb.shape[0]} rows)", flush=True)
    if failures:
        print(f"    {len(failures)} failures, e.g. {failures[:2]}")


def load_family(family, paths):
    cp = cache_path(family)
    if not os.path.exists(cp):
        return None
    z = np.load(cp, allow_pickle=True)
    src = list(z["src"])
    idx = {p: [] for p in paths}
    missing = 0
    for r, p in enumerate(src):
        if p in idx:
            idx[p].append(r)
        else:
            missing += 1
    have = sum(1 for p in paths if idx[p])
    if have < len(paths):
        print(f"  WARNING {family}: only {have}/{len(paths)} source files have "
              f"augmented rows -- extraction incomplete, results would be biased")
        return None
    return z["emb"], idx


# --------------------------------------------------------------------------
def evaluate(d, family, seeds, splits, aug_per_file=None):
    """Centroid incumbent, augmented TRAINING rows only."""
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import f1_score
    import incumbent_receipt as ir
    X, y = d["feats"]["perch+clap"], d["y"]
    classes = d["classes"]
    loaded = load_family(family, d["paths"]) if family != "none" else None
    if family != "none" and loaded is None:
        return None
    Xa, idx = (loaded if loaded else (None, None))

    accs, f1s, covs, fas, worst = [], [], [], [], []
    for s in range(seeds):
        rng = np.random.RandomState(s)
        oof = np.empty(len(y), dtype=object)
        conf = np.zeros(len(y))
        fold_acc = []
        for tr, te in dg.splits_for("vendor", d, splits, s):
            Xtr, ytr = X[tr], y[tr]
            if Xa is not None:
                extra_X, extra_y = [], []
                for i in tr:
                    rows = idx[d["paths"][i]]
                    if aug_per_file is not None and len(rows) > aug_per_file:
                        rows = list(rng.choice(rows, aug_per_file, replace=False))
                    for r in rows:
                        extra_X.append(Xa[r]); extra_y.append(y[i])
                if extra_X:
                    Xtr = np.vstack([Xtr, np.array(extra_X, dtype=np.float32)])
                    ytr = np.concatenate([ytr, np.array(extra_y)])
            p, c = ir.centroid_fit_predict(Xtr, ytr, X[te], classes)
            oof[te], conf[te] = p, c
            fold_acc.append(float((p == y[te]).mean()))
        ok = oof != None                                        # noqa: E711
        correct = (oof == y).astype(float)
        accs.append(100 * float(correct[ok].mean()))
        f1s.append(100 * f1_score(y[ok], oof[ok].astype(str), average="macro",
                                  zero_division=0))
        covs.append(ir.coverage_at(conf, correct, 0.95))
        worst.append(100 * min(fold_acc))
        m = y == "Other/none"
        fas.append(100 * float(((oof[m] != "Other/none") & (conf[m] >= 0.5)).mean()))
    return dict(acc=round(float(np.mean(accs)), 2),
                sd=round(float(np.std(accs)), 2),
                per_seed=[round(v, 2) for v in accs],
                macro_f1=round(float(np.mean(f1s)), 2),
                coverage_at_95=round(float(np.mean(covs)), 1),
                other_none_false_accept=round(float(np.mean(fas)), 2),
                worst_fold=round(float(np.mean(worst)), 2))


def collection_probe(d, family):
    """Does augmentation reduce how much COLLECTION identity the features carry?

    The probe must be grouped by SOURCE FILE. Augmented copies of one file are
    near-identical to each other, so an ungrouped split puts a variant of file X
    in train while X itself is in test -- which is trivially decodable and scored
    99.2% on the first run. That was leakage in the diagnostic, not a finding.
    Grouping by source path removes it.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import StratifiedGroupKFold
    from collections import Counter
    X = d["feats"]["perch+clap"]
    vend = d["vendor"]
    vc = Counter(vend)
    big = [v for v in vc if vc[v] >= 15]
    m = np.isin(vend, big)
    rows = [X[i] for i in np.where(m)[0]]
    labs = [vend[i] for i in np.where(m)[0]]
    grps = [d["paths"][i] for i in np.where(m)[0]]
    if family != "none":
        loaded = load_family(family, d["paths"])
        if loaded is None:
            return None
        Xa, idx = loaded
        for i in np.where(m)[0]:
            for r in idx[d["paths"][i]]:
                rows.append(Xa[r]); labs.append(vend[i]); grps.append(d["paths"][i])
    Xu = np.array(rows, dtype=np.float32)
    yu = np.array(labs)
    gu = np.array(grps)
    cv = StratifiedGroupKFold(5, shuffle=True, random_state=0)
    pred = np.empty(len(yu), dtype=object)
    for tr, te in cv.split(Xu, yu, groups=gu):
        assert not (set(gu[tr]) & set(gu[te])), "probe group leak"
        clf = make_pipeline(StandardScaler(),
                            LogisticRegression(max_iter=3000,
                                               class_weight="balanced"))
        clf.fit(Xu[tr], yu[tr])
        pred[te] = clf.predict(Xu[te])
    ok = pred != None                                           # noqa: E711
    return round(100 * float((pred[ok] == yu[ok]).mean()), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--family", default="all")
    ap.add_argument("--pilot", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--aug-per-file", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    d = dg.load_corpus()
    paths = d["paths"]
    fams = (list(pa.FAMILIES) + ["combined"]) if a.family == "all" else [a.family]

    if a.extract:
        sub = paths[:a.pilot] if a.pilot else paths
        for f in fams:
            print(f"extracting '{f}' for {len(sub)} files...")
            extract_family(sub, f, a.workers)
        return 0

    if a.eval:
        if os.path.exists(RECEIPT):
            r = json.load(open(RECEIPT))
            print(f"incumbent receipt: {r['primary_result_vendor_held_out']}% "
                  f"collection-held-out ({r['generated']})")
        base = evaluate(d, "none", a.seeds, a.splits)
        print(f"\n{'policy':12} {'acc':>15} {'macroF1':>8} {'cov@95':>8} "
              f"{'O/n FA':>8} {'worst':>7} {'delta':>8}")
        print(f"{'none':12} {base['acc']:7.2f}% +-{base['sd']:4.2f} "
              f"{base['macro_f1']:7.1f}% {base['coverage_at_95']:7.1f}% "
              f"{base['other_none_false_accept']:7.1f}% {base['worst_fold']:6.1f}%")
        res = {"none": base}
        for f in fams:
            r = evaluate(d, f, a.seeds, a.splits, a.aug_per_file)
            if r is None:
                print(f"{f:12}  (no cache -- run --extract --family {f})")
                continue
            res[f] = r
            dlt = r["acc"] - base["acc"]
            flag = ""
            if dlt >= GATE_PP and r["macro_f1"] >= base["macro_f1"] \
               and r["other_none_false_accept"] <= base["other_none_false_accept"] + 2 \
               and r["coverage_at_95"] >= base["coverage_at_95"] - 1:
                flag = "  <-- GATE"
            elif dlt >= 1.5:
                flag = "  (pilot threshold)"
            print(f"{f:12} {r['acc']:7.2f}% +-{r['sd']:4.2f} "
                  f"{r['macro_f1']:7.1f}% {r['coverage_at_95']:7.1f}% "
                  f"{r['other_none_false_accept']:7.1f}% {r['worst_fold']:6.1f}% "
                  f"{dlt:+7.2f}{flag}")

        print("\ncollection-identity probe (does augmentation hide the pack?):")
        p0 = collection_probe(d, "none")
        print(f"  {'none':12} {p0}%")
        probes = {"none": p0}
        for f in fams:
            if f in res:
                pv = collection_probe(d, f)
                probes[f] = pv
                print(f"  {f:12} {pv}%   ({pv-p0:+.1f}pp)")

        json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "seeds": a.seeds, "splits": a.splits, "gate_pp": GATE_PP,
                   "baseline": base, "results": res,
                   "collection_probe": probes,
                   "promoted": [k for k, v in res.items() if k != "none"
                                and v["acc"] - base["acc"] >= GATE_PP
                                and v["macro_f1"] >= base["macro_f1"]]},
                  open(OUT, "w"), indent=2)
        print(f"\nwrote {os.path.basename(OUT)}")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
