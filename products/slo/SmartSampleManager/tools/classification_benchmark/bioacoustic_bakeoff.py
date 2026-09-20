#!/usr/bin/env python3
"""
Bioacoustics encoder bake-off: Perch v2 vs CLAP vs handcrafted 33-D DSP.

Rationale: bioacoustics models are trained on short, transient, REAL-WORLD
recorded sounds (birdsong, insect clicks). That is structurally close to
percussion and especially Foley -- which is the class every music/AudioSet-
trained encoder we have tried handles worst. The hypothesis is not that Perch
beats CLAP overall, but that it may beat it specifically on the recorded-real-
world classes (Foley, Percussion), which would justify it as a SPECIALIST in
the fusion rather than a replacement.

Evaluated on the 649 by-ear labels -- the only non-circular ground truth in the
project (see section 16: the corpus benchmark's folder-derived truth is
circular and its DSP figure is an artifact).

Perch v2 takes [batch, 160000] = 5s @ 32kHz, which is exactly what the C++
production path already produces (sampleLen=160000), so deployment would need
no new resampling path.
"""
import os, csv, glob, time, argparse, warnings
import numpy as np, soundfile as sf, librosa
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFIED = os.path.join(SCRIPT_DIR, "verified_drums.csv")
PERCH_GLOB = os.path.expanduser(
    "~/.cache/huggingface/hub/models--justinchuby--Perch-onnx/snapshots/*/perch_v2.onnx")
PERCH_SR, PERCH_LEN = 32000, 160000
CLAP_SR = 48000


def load_audio(path, sr, length=None):
    y, s = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1: y = y.mean(1)
    if s != sr: y = librosa.resample(y, orig_sr=s, target_sr=sr)
    if length:
        out = np.zeros(length, dtype=np.float32)
        n = min(len(y), length); out[:n] = y[:n]; return out
    return y.astype(np.float32)


def perch_embed(paths, batch=8):
    import onnxruntime as ort
    p = glob.glob(PERCH_GLOB)[0]
    so = ort.SessionOptions(); so.intra_op_num_threads = 8
    s = ort.InferenceSession(p, so, providers=["CPUExecutionProvider"])
    out, t0 = [], time.time()
    for i in range(0, len(paths), batch):
        chunk = [load_audio(q, PERCH_SR, PERCH_LEN) for q in paths[i:i+batch]]
        e = s.run(["embedding"], {"inputs": np.stack(chunk)})[0]
        out.append(e)
        if i and i % (batch*20) == 0:
            r = i/(time.time()-t0); print(f"  perch {i}/{len(paths)} {r:.1f}/s", flush=True)
    return np.concatenate(out).astype(np.float32)


def clap_embed(paths, batch=12):
    import torch
    from transformers import ClapModel, ClapProcessor
    md = os.path.join(SCRIPT_DIR, "clap_model_music")
    if not os.path.isdir(md): md = os.path.join(SCRIPT_DIR, "clap_model")
    proc = ClapProcessor.from_pretrained(md); m = ClapModel.from_pretrained(md).eval()
    out, t0 = [], time.time()
    for i in range(0, len(paths), batch):
        wavs = [load_audio(q, CLAP_SR) for q in paths[i:i+batch]]
        wavs = [w if len(w) else np.zeros(CLAP_SR, dtype=np.float32) for w in wavs]
        with torch.no_grad():
            ai = proc(audio=wavs, sampling_rate=CLAP_SR, return_tensors="pt", padding=True)
            out.append(m.get_audio_features(**ai).pooler_output.numpy())
        if i and i % (batch*15) == 0:
            print(f"  clap {i}/{len(paths)} {i/(time.time()-t0):.1f}/s", flush=True)
    return np.concatenate(out).astype(np.float32)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", default="bioacoustic_emb.npz")
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(VERIFIED))
            if r["label"] not in ("__skip__", "Misc/Review") and os.path.exists(r["path"])]
    paths = [r["path"] for r in rows]; y = np.array([r["label"] for r in rows])
    print(f"{len(paths)} by-ear labelled files\n")

    cache = os.path.join(SCRIPT_DIR, a.cache)
    if os.path.exists(cache):
        z = np.load(cache); Xp, Xc = z["perch"], z["clap"]; print("loaded cached embeddings")
    else:
        print("extracting Perch v2 (1536-D)..."); Xp = perch_embed(paths)
        print("extracting CLAP (512-D)...");      Xc = clap_embed(paths)
        np.savez(cache, perch=Xp, clap=Xc)
    import drum_detector_features as ddf
    Xd = np.array([ddf.extract(p) if ddf.extract(p) is not None else np.zeros(33, np.float32)
                   for p in paths])
    print(f"\nperch {Xp.shape}  clap {Xc.shape}  dsp {Xd.shape}\n")

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict
    from collections import Counter
    cnt = Counter(y); viable = [c for c in cnt if cnt[c] >= 15]
    m = np.isin(y, viable)
    print(f"evaluating on {m.sum()} files, {len(viable)} classes (>=15 examples)\n")

    def run(X, name):
        # linear probe on embeddings (standard for frozen encoders); RF for DSP
        clf = (make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
               if X.shape[1] > 64 else
               RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0))
        pred = cross_val_predict(clf, X[m], y[m], cv=5)
        acc = 100*(pred == y[m]).mean()
        print(f"  {name:22} {acc:5.1f}%")
        return pred, acc

    preds = {}
    preds["Perch (1536-D)"], _ = run(Xp, "Perch (1536-D)")
    preds["CLAP (512-D)"], _   = run(Xc, "CLAP (512-D)")
    preds["handcrafted (33-D)"], _ = run(Xd, "handcrafted (33-D)")
    preds["Perch+CLAP"], _ = run(np.hstack([Xp, Xc]), "Perch+CLAP")
    preds["Perch+CLAP+DSP"], _ = run(np.hstack([Xp, Xc, Xd]), "Perch+CLAP+DSP")

    print("\nper-class recall (the real question: does Perch win on Foley/Percussion?)")
    hdr = f"  {'class':>16} {'n':>4}" + "".join(f"{k.split(' ')[0][:9]:>11}" for k in preds)
    print(hdr)
    for c in sorted(viable, key=lambda k: -cnt[k]):
        sel = y[m] == c
        line = f"  {c:>16} {int(sel.sum()):4d}"
        for k in preds: line += f"{100*(preds[k][sel]==c).mean():10.0f}%"
        print(line)


if __name__ == "__main__":
    main()
