#!/usr/bin/env python3
"""
Head-to-head: PANNs CNN10 embeddings vs CLAP audio embeddings, same files,
same folds, same architecture. Answers whether the encoder is a binding
constraint on this task.

Context: the CLAP zero-shot audit (SLO_CLASSIFICATION_V4_REMEDIATION_2026-09-09
section 9) found several class boundaries in this taxonomy are not acoustic
(Foley vs Percussion is provenance; Vocal Phrase vs Vocal Loop is temporal).
If that is the binding constraint, a better encoder should NOT close the gap --
this run tests that prediction.

Pilot scale: the 4,359 held-out clips, which are the ones already converted to
48kHz for CLAP. Both arms see exactly the same files, so the comparison is
controlled; absolute numbers are lower than the full-corpus run because there
is ~5x less training data.
"""
import os, json, argparse
import numpy as np, torch, torch.nn.functional as F, soundfile as sf
from sklearn.model_selection import StratifiedKFold
import train_gpu_classifier_v4 as T

def clap_embed(audio_dir, model_dir, items, batch=16):
    from transformers import ClapModel, ClapProcessor
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    proc = ClapProcessor.from_pretrained(model_dir)
    model = ClapModel.from_pretrained(model_dir).to(dev).eval()
    out = []
    for s in range(0, len(items), batch):
        chunk = items[s:s+batch]
        wavs = []
        for m in chunk:
            y, _ = sf.read(os.path.join(audio_dir, f"{m['pos']:05d}.flac"), dtype="float32")
            if y.ndim > 1: y = y.mean(axis=1)
            wavs.append(y if len(y) else np.zeros(48000, dtype=np.float32))
        with torch.no_grad():
            ai = proc(audio=wavs, sampling_rate=48000, return_tensors="pt", padding=True)
            ai = {k: v.to(dev) for k, v in ai.items()}
            out.append(model.get_audio_features(**ai).pooler_output.cpu().numpy())
        if s and s % (batch*40) == 0: print(f"  clap {s}/{len(items)}", flush=True)
    return np.concatenate(out).astype(np.float32)

def cv(X, y, tag, epochs=90, seed=42):
    torch.manual_seed(seed); np.random.seed(seed)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_cls = len(T.CLASSES)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    oof = np.zeros(len(y), dtype=int); accs = []
    for k, (tr, va) in enumerate(skf.split(X, y)):
        cnt = np.bincount(y[tr], minlength=n_cls)
        w = torch.tensor([len(tr)/(n_cls*max(c,1)) for c in cnt], dtype=torch.float32, device=dev)
        m = T.ClassifierV4(in_features=X.shape[1], num_classes=n_cls).to(dev)
        opt = torch.optim.AdamW(m.parameters(), lr=1.2e-3, weight_decay=1e-4)
        sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
        crit = T.FocalLoss(gamma=2.0, weight=w)
        ld = torch.utils.data.DataLoader(T.HybridDataset(X[tr], y[tr]), batch_size=256, shuffle=True)
        for _ in range(epochs):
            T.train_epoch(m, ld, opt, crit, dev); sch.step()
        vl = torch.utils.data.DataLoader(T.HybridDataset(X[va], y[va]), batch_size=512)
        _, acc, pred, _ = T.evaluate(m, vl, crit, dev)
        oof[va] = pred; accs.append(acc)
        print(f"  {tag} fold {k+1}/5: {acc*100:.2f}%", flush=True)
    o = float((oof == y).mean())
    print(f">>> {tag}: OOF {o*100:.2f}%  folds " + ", ".join(f"{a*100:.2f}" for a in accs))
    return o, accs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default="clap_audio")
    ap.add_argument("--model-dir", default="clap_model")
    ap.add_argument("--cache", default="clap_embeddings.npy")
    a = ap.parse_args()

    man = json.load(open(os.path.join(a.audio_dir, "manifest.json")))
    classes = man["classes"]
    items = [m for m in man["items"]
             if m["ok"] and os.path.exists(os.path.join(a.audio_dir, f"{m['pos']:05d}.flac"))]
    y = np.array([classes.index(m["label"]) for m in items], dtype=np.int64)

    if os.path.exists(a.cache):
        Xc = np.load(a.cache); print(f"loaded cached CLAP embeddings {Xc.shape}")
    else:
        print(f"extracting CLAP embeddings for {len(items)} clips...")
        Xc = clap_embed(a.audio_dir, a.model_dir, items); np.save(a.cache, Xc)
    # PANNs rows for exactly the same clips
    idx = np.load("heldout_indices.npy")
    Xall = np.load("hybrid_x.npy")
    Xp = np.ascontiguousarray(Xall[idx[[m["pos"] for m in items]]][:, :512])

    print(f"\nsame {len(items)} clips | PANNs {Xp.shape} | CLAP {Xc.shape}\n")
    p_oof, _ = cv(Xp, y, "PANNs-512")
    print()
    c_oof, _ = cv(Xc, y, "CLAP-512")
    print(f"\n=== encoder delta (CLAP - PANNs): {(c_oof-p_oof)*100:+.2f} pp ===")
    print("Prediction under the section-9 finding: near zero, because the")
    print("binding constraint is non-acoustic label boundaries, not the encoder.")

if __name__ == "__main__":
    main()
