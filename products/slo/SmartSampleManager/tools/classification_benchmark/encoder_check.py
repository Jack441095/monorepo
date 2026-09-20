#!/usr/bin/env python3
"""
Phase 8 -- limited new-encoder check. Dasheng-base.

PRE-REGISTRATION (written before the model was downloaded, so it cannot be
rewritten to fit the result).

Candidate
---------
  model        mispeech/dasheng-base
  licence      Apache-2.0  -- commercially usable
  size         342 MB (safetensors), ~86M parameters
  input        16 kHz mono, 64 mel filterbanks
  deployment   comparable in size to the current Perch+CLAP pair (210 MB
               quantised), so it is a plausible REPLACEMENT but a poor addition
  benchmark    Dasheng tops the HEAR benchmark (1.2B variant, avg 81.25 vs
               AudioMAE 57.67); base is the small sibling

Why this one and not another survey
-----------------------------------
The brief permits at most BEATs and one strong permissively-licensed encoder.
BEATs ships as research code in microsoft/unilm rather than a loadable
transformers checkpoint, so it costs materially more integration effort for the
same question; Dasheng-base is tested first and BEATs only if this shows promise.

Exact hypothesis
----------------
Dasheng differs from every 16 kHz encoder already rejected here (HuBERT,
wav2vec2) in that it is a MASKED AUDIO autoencoder trained on 272k hours of
GENERAL audio, not speech. The prior failures were attributed to speech-domain
mismatch. If that attribution was right, Dasheng should do materially better
than they did. If Dasheng also fails, the more likely explanation is the 16 kHz
ceiling itself -- which discards everything above 8 kHz, where much of a
hi-hat's and crash's identity lives -- and that would close the entire 16 kHz
family rather than one model at a time.

Stated expectation: I expect Dasheng-base to beat HuBERT/wav2vec2 comfortably
but NOT to beat Perch+CLAP, because Perch runs at 32 kHz and the corpus is
transient-heavy percussion. Recorded so it can be scored.

Gate
----
Stable +2pp VENDOR-HELD-OUT improvement, or an unusually valuable targeted class
gain. Random-CV improvement is explicitly NOT sufficient: Phase 1 showed random
CV overstates by ~9.7pp and systematically flatters methods that can exploit
vendor shortcuts. No encoder is added to an ensemble for a sub-2pp gain at
material deployment cost.

Usage:
  python3 encoder_check.py --extract
  python3 encoder_check.py --seeds 6
"""
import os, json, time, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import domain_generalization_eval as dg   # noqa: E402

CACHE = os.path.join(SD, "dasheng_emb.npz")
OUT = os.path.join(SD, "results_encoder_check_v1.json")
MODEL = "mispeech/dasheng-base"
SR = 16000
MAX_S = 10.0


def extract(paths, batch=8):
    """Dasheng takes MEL FEATURES (b, 64, frames) from its own feature
    extractor, not raw waveform -- passing waveform fails inside its einops
    Rearrange with KeyError: 3."""
    import torch, soundfile as sf, librosa
    from transformers import AutoModel, AutoFeatureExtractor
    fe = AutoFeatureExtractor.from_pretrained(MODEL, trust_remote_code=True)
    m = AutoModel.from_pretrained(MODEL, outputdim=None,
                                  trust_remote_code=True).eval()
    out, t0 = [], time.time()
    for i in range(0, len(paths), batch):
        wavs = []
        for p in paths[i:i + batch]:
            y, s = sf.read(p, dtype="float32", always_2d=False)
            if y.ndim > 1:
                y = y.mean(1)
            if s != SR:
                y = librosa.resample(y, orig_sr=s, target_sr=SR)
            y = y[: int(SR * MAX_S)]
            if len(y) < SR // 2:
                y = np.pad(y, (0, SR // 2 - len(y)))
            wavs.append(y.astype(np.float32))
        L = max(len(w) for w in wavs)
        arr = np.stack([np.pad(w, (0, L - len(w))) for w in wavs])
        with torch.no_grad():
            feats = fe(torch.tensor(arr), sampling_rate=SR,
                       return_tensors="pt")["input_values"]
            mo = m(feats)                       # NOT 'out' -- that is the list
            h = getattr(mo, "hidden_states", None)
            if h is None:
                h = getattr(mo, "last_hidden_state", None)
            if h is None:
                emb = mo.logits.cpu().numpy()           # mean-pooled 768-D
            else:
                emb = torch.cat([h.mean(1), h.max(1).values], -1).cpu().numpy()
        out.append(emb.astype(np.float32))
        if i and i % (batch * 20) == 0:
            print(f"  {i}/{len(paths)}  {i/(time.time()-t0):.1f}/s", flush=True)
    return np.concatenate(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--splits", type=int, default=5)
    a = ap.parse_args()

    d = dg.load_corpus()
    paths = d["paths"]

    if a.extract or not os.path.exists(CACHE):
        print(f"extracting {MODEL} for {len(paths)} files...")
        E = extract(paths)
        np.savez(CACHE, emb=E, paths=np.array(paths, dtype=object))
        print(f"cached {E.shape} -> {os.path.basename(CACHE)}")
    z = np.load(CACHE, allow_pickle=True)
    E = z["emb"]
    if list(z["paths"]) != list(paths):
        raise SystemExit("FAIL CLOSED: dasheng cache does not match the current "
                         "corpus row order -- re-extract rather than indexing "
                         "across a mismatch.")
    print(f"dasheng {E.shape}\n")

    d["feats"]["dasheng"] = E
    d["feats"]["perch+clap+dasheng"] = np.hstack([d["feats"]["perch+clap"], E])

    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    y = d["y"]
    classes = sorted(set(y))

    def znorm(X):
        return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)

    def run(feat, mode, head):
        accs, f1s = [], []
        X = d["feats"][feat]
        for s in range(a.seeds):
            oof = np.empty(len(y), dtype=object)
            for tr, te in dg.splits_for(mode, d, a.splits, s):
                sc = StandardScaler().fit(X[tr])
                if head == "centroid":
                    Ztr, Zte = znorm(sc.transform(X[tr])), znorm(sc.transform(X[te]))
                    C = znorm(np.vstack([Ztr[y[tr] == c].mean(0) for c in classes]))
                    oof[te] = np.array(classes)[(Zte @ C.T).argmax(1)]
                else:
                    clf = LogisticRegression(max_iter=3000, class_weight="balanced")
                    clf.fit(sc.transform(X[tr]), y[tr])
                    oof[te] = clf.predict(sc.transform(X[te]))
            ok = oof != None                                   # noqa: E711
            accs.append(100 * float((oof[ok] == y[ok]).mean()))
            f1s.append(100 * f1_score(y[ok], oof[ok].astype(str),
                                      average="macro", zero_division=0))
        return float(np.mean(accs)), float(np.std(accs)), float(np.mean(f1s))

    res = {}
    print(f"{'features':22} {'head':9} {'mode':7} {'acc':>16} {'macroF1':>9}")
    for feat in ("dasheng", "perch+clap", "perch+clap+dasheng"):
        for head in ("logreg", "centroid"):
            for mode in ("random", "vendor"):
                m_, sd_, f1_ = run(feat, mode, head)
                res[f"{feat}|{head}|{mode}"] = dict(acc=round(m_, 2),
                                                    sd=round(sd_, 2),
                                                    macro_f1=round(f1_, 2))
                print(f"{feat:22} {head:9} {mode:7} {m_:7.1f}% +-{sd_:4.1f} "
                      f"{f1_:8.1f}%")

    base = res["perch+clap|centroid|vendor"]["acc"]
    cand = res["perch+clap+dasheng|centroid|vendor"]["acc"]
    solo = res["dasheng|centroid|vendor"]["acc"]
    verdict = ("PROMOTE" if cand - base >= 2.0 else "REJECT")
    print(f"\nGATE: vendor-held-out, centroid head")
    print(f"  Perch+CLAP            {base:.1f}%")
    print(f"  Perch+CLAP+Dasheng    {cand:.1f}%   ({cand-base:+.2f}pp)")
    print(f"  Dasheng alone         {solo:.1f}%")
    print(f"  VERDICT: {verdict} (needs >= +2.0pp)")
    json.dump({"model": MODEL, "licence": "apache-2.0", "size_mb": 342,
               "seeds": a.seeds, "results": res,
               "delta_vendor_centroid": round(cand - base, 2),
               "verdict": verdict}, open(OUT, "w"), indent=2)
    print(f"wrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
