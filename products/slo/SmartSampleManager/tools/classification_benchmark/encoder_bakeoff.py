#!/usr/bin/env python3
"""
Full-corpus encoder bake-off.

Background: a pilot on 4,359 clips found CLAP embeddings beat PANNs CNN10 by
+10.23 pp (73.57% vs 63.34%) with identical folds and architecture. That
contradicted the earlier prediction that non-acoustic label boundaries were
the binding constraint -- the encoder mattered far more than expected. CLAP on
4,359 clips matched PANNs+DSP trained on all 21,793.

This runs the comparison at full scale, with the DSP block layered on top of
the winning encoder to check the +1.95 pp it contributed to PANNs still holds.

Row alignment: clap_audio_all/NNNNN.flac is written in npz row order, so
embedding row i corresponds to hybrid_x.npy row i and hybrid_y.npy row i.
No index mapping is required -- see prep_clap_audio.py --all.
"""

import os
import sys
import json
import time
import argparse
import numpy as np
import torch
import torch.nn.functional as F
import soundfile as sf
from sklearn.model_selection import StratifiedKFold

import train_gpu_classifier_v4 as T

CLAP_SR = 48000


def extract(audio_dir, model_dir, n, cache, batch=24):
    if os.path.exists(cache):
        X = np.load(cache)
        if len(X) == n:
            print(f"  cached {cache} {X.shape}", flush=True)
            return X
        print(f"  cache {cache} has {len(X)} rows, expected {n} - re-extracting", flush=True)

    from transformers import ClapModel, ClapProcessor
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    proc = ClapProcessor.from_pretrained(model_dir)
    model = ClapModel.from_pretrained(model_dir).to(dev).eval()

    out = []
    t0 = time.time()
    for s in range(0, n, batch):
        wavs = []
        for pos in range(s, min(s + batch, n)):
            f = os.path.join(audio_dir, f"{pos:05d}.flac")
            try:
                y, _ = sf.read(f, dtype="float32")
                if y.ndim > 1:
                    y = y.mean(axis=1)
            except Exception:
                y = np.zeros(CLAP_SR, dtype=np.float32)
            wavs.append(y if len(y) else np.zeros(CLAP_SR, dtype=np.float32))
        with torch.no_grad():
            ai = proc(audio=wavs, sampling_rate=CLAP_SR, return_tensors="pt", padding=True)
            ai = {k: v.to(dev) for k, v in ai.items()}
            out.append(model.get_audio_features(**ai).pooler_output.cpu().numpy())
        if s and s % (batch * 100) == 0:
            r = s / (time.time() - t0)
            print(f"    {s}/{n} - {r:.0f}/s - ETA {(n-s)/r/60:.1f} min", flush=True)

    X = np.concatenate(out).astype(np.float32)
    np.save(cache, X)
    print(f"  extracted {X.shape} -> {cache} in {(time.time()-t0)/60:.1f} min", flush=True)
    del model
    torch.cuda.empty_cache()
    return X


def cv(X, y, tag, epochs=90, seed=42):
    torch.manual_seed(seed)
    np.random.seed(seed)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_cls = len(T.CLASSES)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    oof = np.zeros(len(y), dtype=int)
    accs = []
    for k, (tr, va) in enumerate(skf.split(X, y)):
        cnt = np.bincount(y[tr], minlength=n_cls)
        w = torch.tensor([len(tr) / (n_cls * max(c, 1)) for c in cnt],
                         dtype=torch.float32, device=dev)
        m = T.ClassifierV4(in_features=X.shape[1], num_classes=n_cls).to(dev)
        opt = torch.optim.AdamW(m.parameters(), lr=1.2e-3, weight_decay=1e-4)
        sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
        crit = T.FocalLoss(gamma=2.0, weight=w)
        ld = torch.utils.data.DataLoader(T.HybridDataset(X[tr], y[tr]),
                                         batch_size=256, shuffle=True)
        for _ in range(epochs):
            T.train_epoch(m, ld, opt, crit, dev)
            sch.step()
        vl = torch.utils.data.DataLoader(T.HybridDataset(X[va], y[va]), batch_size=512)
        _, acc, pred, _ = T.evaluate(m, vl, crit, dev)
        oof[va] = pred
        accs.append(acc)
        print(f"    fold {k+1}/5 {acc*100:.2f}%", flush=True)
    o = float((oof == y).mean())
    print(f">>> {tag:28s} OOF {o*100:.2f}%", flush=True)
    return o, accs, oof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default="clap_audio_all")
    ap.add_argument("--epochs", type=int, default=90)
    a = ap.parse_args()

    Xp_full = np.load("hybrid_x.npy")          # (N, 520) = PANNs 512 + DSP 8
    y = np.load("hybrid_y.npy")
    n = len(y)
    Xp = np.ascontiguousarray(Xp_full[:, :512])
    Xd = np.ascontiguousarray(Xp_full[:, 512:])
    print(f"corpus {n} files, {len(T.CLASSES)} classes\n")

    print("Extracting CLAP embeddings:")
    arms = {}
    Xc = extract(a.audio_dir, "clap_model", n, "clap_all_unfused.npy")
    arms["CLAP-unfused-512"] = Xc
    if os.path.isdir("clap_model_music"):
        Xm = extract(a.audio_dir, "clap_model_music", n, "clap_all_music.npy")
        arms["CLAP-music-512"] = Xm
    else:
        Xm = None

    print("\nRunning 5-fold CV per arm (identical folds, seed 42):\n")
    results = {}
    for tag, X in [("PANNs-512 (baseline)", Xp),
                   ("PANNs+DSP-520 (shipping)", Xp_full)]:
        print(f"  {tag}")
        results[tag] = cv(X, y, tag, a.epochs)[0]

    for tag, X in arms.items():
        print(f"  {tag}")
        results[tag] = cv(X, y, tag, a.epochs)[0]
        combo = np.ascontiguousarray(np.hstack([X, Xd]).astype(np.float32))
        t2 = f"{tag.replace('-512','')}+DSP-{combo.shape[1]}"
        print(f"  {t2}")
        results[t2] = cv(combo, y, t2, a.epochs)[0]

    print("\n=== SUMMARY (OOF accuracy, same folds) ===")
    base = results.get("PANNs+DSP-520 (shipping)")
    for k, v in sorted(results.items(), key=lambda kv: -kv[1]):
        d = f"  ({(v-base)*100:+.2f} vs shipping)" if base else ""
        print(f"  {k:32s} {v*100:6.2f}%{d}")

    with open("encoder_bakeoff_results.json", "w") as f:
        json.dump({k: float(v) for k, v in results.items()}, f, indent=2)
    print("\nSaved encoder_bakeoff_results.json")


if __name__ == "__main__":
    main()
