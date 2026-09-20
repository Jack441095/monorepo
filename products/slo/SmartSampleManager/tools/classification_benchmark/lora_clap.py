#!/usr/bin/env python3
"""
LoRA fine-tuning of the CLAP audio tower -- the one unused capability.

Every result in this project to date uses FROZEN embeddings with a linear head.
The encoder has never been trained on this data. Sections 31-33 established that
adding more evidence sources does nothing (embedded metadata, folder context,
three Meta encoders, four new descriptive axes -- all measured, all redundant
with what Perch+CLAP already encodes). If the residual errors are not a missing-
signal problem, the remaining possibility is that the signal IS present in the
embedding but is not linearly separable in the frozen space. Fine-tuning is the
direct test of that.

CLAP is chosen because Perch ships as ONNX and is not trainable. CLAP's audio
tower is an HTSAT swin transformer, 67.8M parameters; LoRA adapts the attention
query/value projections only.

THREE ARMS, identical folds, identical files, identical class filter:

  A. frozen CLAP + sklearn linear probe    -- the published baseline (69.1%)
  B. frozen CLAP + trained torch head      -- THE CONTROL
  C. LoRA CLAP  + trained torch head       -- the experiment

Arm B exists because without it, any difference between A and C could be caused
by the head, the optimiser or the schedule rather than by LoRA. B and C share
everything except whether the adapters are present and trainable. The LoRA
effect is C - B. A is reported only to tie back to the published number.

Overfitting is the obvious risk: ~460 training files against 67.8M frozen
parameters plus adapters. That is why the metric is out-of-fold accuracy across
multiple seeds, never training accuracy, and why the result is only believed if
it survives repeated CV (section 32: single-split deltas under ~2pp on this
corpus are noise).
"""
import os, csv, json, time, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
VERIFIED = os.path.join(SD, "verified_drums.csv")
FEAT_CACHE = os.path.join(SD, "clap_input_features.npy")
PATH_CACHE = os.path.join(SD, "clap_input_features_paths.json")
MODEL_DIR = os.path.join(SD, "clap_model_music")


def load_rows():
    rows = [r for r in csv.DictReader(open(VERIFIED))
            if r["label"] not in ("__skip__", "Misc/Review")
            and os.path.exists(r["path"])]
    return [r["path"] for r in rows], np.array([r["label"] for r in rows])


def build_features(paths, batch=8):
    """Precompute CLAP mel input_features once; the tower then trains on these."""
    if os.path.exists(FEAT_CACHE) and os.path.exists(PATH_CACHE):
        if json.load(open(PATH_CACHE)) == paths:
            print("loaded cached CLAP input features")
            return np.load(FEAT_CACHE, mmap_mode="r")
    import torch, soundfile as sf, librosa
    from transformers import ClapProcessor
    proc = ClapProcessor.from_pretrained(MODEL_DIR)
    sr = proc.feature_extractor.sampling_rate
    out, t0 = [], time.time()
    for i in range(0, len(paths), batch):
        wavs = []
        for p in paths[i:i + batch]:
            y, s = sf.read(p, dtype="float32", always_2d=False)
            if y.ndim > 1:
                y = y.mean(1)
            if s != sr:
                y = librosa.resample(y, orig_sr=s, target_sr=sr)
            if len(y) < sr // 2:
                y = np.pad(y, (0, sr // 2 - len(y)))
            wavs.append(y.astype(np.float32))
        f = proc(audio=wavs, sampling_rate=sr, return_tensors="pt",
                 padding=True)["input_features"]
        out.append(f.numpy().astype(np.float32))
        if i and i % (batch * 20) == 0:
            print(f"  features {i}/{len(paths)} {i/(time.time()-t0):.1f}/s",
                  flush=True)
    X = np.concatenate(out)
    np.save(FEAT_CACHE, X)
    json.dump(paths, open(PATH_CACHE, "w"))
    print(f"cached input features {X.shape}")
    return X


def make_model(lora, n_classes, device, rank=8):
    import torch
    from transformers import ClapModel
    m = ClapModel.from_pretrained(MODEL_DIR)
    tower, proj = m.audio_model, m.audio_projection
    for p in tower.parameters():
        p.requires_grad = False
    for p in proj.parameters():
        p.requires_grad = False
    if lora:
        from peft import LoraConfig, get_peft_model
        cfg = LoraConfig(r=rank, lora_alpha=2*rank, lora_dropout=0.05, bias="none",
                         target_modules=["query", "value"])
        tower = get_peft_model(tower, cfg)

    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.tower, self.proj = tower, proj
            # LayerNorm is the in-graph equivalent of the StandardScaler that
            # arm A's sklearn pipeline applies. Without it the trained head sees
            # raw, badly-scaled 512-D CLAP projections and underfits badly --
            # the first run scored the CONTROL at 55.7% against 67.2% for the
            # same frozen features under sklearn, which made LoRA look worth
            # +12.2pp when the true effect is ~0.
            self.norm = torch.nn.LayerNorm(512)
            self.head = torch.nn.Linear(512, n_classes)

        def forward(self, x):
            h = self.tower(input_features=x).pooler_output
            return self.head(self.norm(self.proj(h)))

    return Net().to(device)


def train_eval(Xtr, ytr, Xte, lora, n_classes, device, epochs, bs, seed, rank=8):
    import torch
    torch.manual_seed(seed)
    net = make_model(lora, n_classes, device, rank)
    # Separate learning rates: a freshly-initialised linear head needs a much
    # larger step than low-rank adapters sitting on pretrained weights. Using one
    # LR for both starves the head, which would make the CONTROL arm look
    # artificially weak and manufacture a fake LoRA win.
    head_p = list(net.head.parameters()) + list(net.norm.parameters())
    hid = {id(q) for q in head_p}
    lora_p = [q for q in net.parameters() if q.requires_grad and id(q) not in hid]
    n_train = sum(q.numel() for q in head_p + lora_p)
    groups = [{"params": head_p, "lr": 2e-3}]
    if lora_p:
        groups.append({"params": lora_p, "lr": 3e-4})
    opt = torch.optim.AdamW(groups, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=[g["lr"] for g in groups],
        total_steps=max(1, epochs * ((len(Xtr) + bs - 1) // bs)))
    # class-balanced loss, matching the sklearn baseline's class_weight
    cnt = np.bincount(ytr, minlength=n_classes).astype(np.float32)
    w = torch.tensor(len(ytr) / (n_classes * np.maximum(cnt, 1)), device=device)
    lossf = torch.nn.CrossEntropyLoss(weight=w)
    yt = torch.tensor(ytr, device=device)
    net.train()
    # CRITICAL: requires_grad=False stops gradients but does NOT stop dropout or
    # BatchNorm running-stat updates. The CLAP audio tower contains 54 Dropout
    # layers and a BatchNorm2d, so under net.train() the "frozen" encoder emits
    # a DIFFERENT embedding every step (measured: max |eval - train| = 1.78, and
    # 0.32 between two train-mode passes of the same input). The head was
    # therefore fitting randomly corrupted features, which is why the CONTROL
    # arm scored 55.7% while sklearn reached 67.2% on the same frozen encoder.
    # Keeping the backbone in eval() leaves LoRA parameters fully trainable --
    # gradients still flow through eval-mode modules -- while making arm B a
    # genuine like-for-like control.
    net.tower.eval()
    net.proj.eval()
    for ep in range(epochs):
        perm = torch.randperm(len(Xtr))
        tot = 0.0
        for i in range(0, len(Xtr), bs):
            idx = perm[i:i + bs]
            xb = torch.tensor(np.ascontiguousarray(Xtr[idx.numpy()]),
                              device=device)
            opt.zero_grad()
            l = lossf(net(xb), yt[idx])
            l.backward()
            opt.step()
            sched.step()
            tot += float(l) * len(idx)
        print(f"      ep {ep+1}/{epochs} loss {tot/len(Xtr):.3f}", flush=True)
    net.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(Xte), bs):
            xb = torch.tensor(np.ascontiguousarray(Xte[i:i + bs]), device=device)
            preds.append(net(xb).argmax(1).cpu().numpy())
    del net
    return np.concatenate(preds), n_train


def make_bundle(out):
    """Pre-aligned (features, labels, frozen-embeddings) triple for remote runs.

    The remote box cannot evaluate os.path.exists on this machine's paths, so it
    must never re-derive the row set from the CSV -- doing so silently misaligns
    labels against embeddings (that mistake produced a bogus 53.7% earlier in
    this project). Everything is filtered and frozen HERE, once, and shipped as
    one object whose arrays correspond by construction.
    """
    paths, y = load_rows()
    X = np.asarray(build_features(paths))
    Xc = np.load(os.path.join(SD, "bioacoustic_emb.npz"))["clap"]
    assert len(Xc) == len(paths) == len(X) == len(y), (
        f"refusing to bundle misaligned arrays: {len(X)} feats, {len(y)} labels, "
        f"{len(Xc)} clap, {len(paths)} paths")
    np.savez(out, X=X, y=y, clap=Xc)
    print(f"bundle -> {out}  ({os.path.getsize(out)/1e6:.0f} MB, {len(y)} rows)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--min-class", type=int, default=15)
    ap.add_argument("--device", default=None)
    ap.add_argument("--model-dir", default=None)
    ap.add_argument("--bundle", default=None,
                    help="pre-aligned npz (X, y, clap); skips all path logic")
    ap.add_argument("--make-bundle", default=None)
    ap.add_argument("--rank", type=int, default=8)
    ap.add_argument("--out", default=None, help="write results json here")
    a = ap.parse_args()

    if a.make_bundle:
        return make_bundle(a.make_bundle)

    global MODEL_DIR
    if a.model_dir:
        MODEL_DIR = a.model_dir

    import torch
    dev = a.device or ("cuda" if torch.cuda.is_available()
                       else "mps" if torch.backends.mps.is_available() else "cpu")
    print(f"device: {dev}\n")

    if a.bundle:
        z = np.load(a.bundle, allow_pickle=True)
        X, y, clap_frozen = z["X"], z["y"], z["clap"]
        paths = None
        print(f"bundle: {X.shape} features, {len(y)} labels (pre-aligned)")
    else:
        paths, y = load_rows()
        X = build_features(paths)
        clap_frozen = np.load(os.path.join(SD, "bioacoustic_emb.npz"))["clap"]
        assert len(clap_frozen) == len(paths), "cache/label mismatch"

    from collections import Counter
    cnt = Counter(y)
    viable = sorted(c for c in cnt if cnt[c] >= a.min_class)
    m = np.isin(y, viable)
    idx_all = np.where(m)[0]
    classes = {c: i for i, c in enumerate(viable)}
    yi = np.array([classes[c] for c in y[m]])
    Xv = np.asarray(X[idx_all])
    print(f"{len(yi)} files, {len(viable)} classes, features {Xv.shape}\n")

    from sklearn.model_selection import StratifiedKFold
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict

    # ---- arm A: the published frozen baseline, for continuity -------------
    Xc = clap_frozen[idx_all]

    results = {"A frozen CLAP + sklearn probe": [],
               "B frozen CLAP + trained head (CONTROL)": [],
               "C LoRA CLAP + trained head": []}

    for seed in range(a.seeds):
        print(f"===== seed {seed} =====", flush=True)
        skf = StratifiedKFold(a.folds, shuffle=True, random_state=seed)
        clf = make_pipeline(StandardScaler(),
                            LogisticRegression(max_iter=3000,
                                               class_weight="balanced"))
        pa = cross_val_predict(clf, Xc, yi, cv=skf)
        results["A frozen CLAP + sklearn probe"].append(100 * (pa == yi).mean())
        print(f"  A frozen+probe   {100*(pa==yi).mean():5.1f}%", flush=True)

        for lora, key in ((False, "B frozen CLAP + trained head (CONTROL)"),
                          (True, "C LoRA CLAP + trained head")):
            oof = np.zeros_like(yi)
            for f, (tr, te) in enumerate(skf.split(Xv, yi)):
                print(f"    {key[0]} fold {f+1}/{a.folds}", flush=True)
                p, ntr = train_eval(Xv[tr], yi[tr], Xv[te], lora, len(viable),
                                    dev, a.epochs, a.bs, seed, a.rank)
                oof[te] = p
            acc = 100 * (oof == yi).mean()
            results[key].append(acc)
            print(f"  {key[0]} {acc:5.1f}%  ({ntr:,} trainable params)",
                  flush=True)
            np.save(os.path.join(SD, f"lora_oof_{key[0]}_{seed}.npy"), oof)

    print("\n================ RESULT ================")
    for k, v in results.items():
        v = np.array(v)
        print(f"  {k:42} {v.mean():5.1f}%  (seeds: "
              f"{' '.join(f'{x:.1f}' for x in v)})")
    b = np.array(results["B frozen CLAP + trained head (CONTROL)"])
    c = np.array(results["C LoRA CLAP + trained head"])
    print(f"\n  LoRA effect (C - B) = {(c-b).mean():+.2f}pp   "
          f"per-seed: {' '.join(f'{x:+.1f}' for x in (c-b))}")
    print("  (section 32: deltas under ~2pp on this corpus are not believed "
          "without repeated CV)")
    if a.out:
        json.dump({"results": {k: list(map(float, v)) for k, v in results.items()},
                   "lora_minus_control_pp": float((c - b).mean()),
                   "per_seed_delta": list(map(float, c - b)),
                   "epochs": a.epochs, "folds": a.folds, "seeds": a.seeds,
                   "rank": a.rank, "n_files": int(len(yi)),
                   "classes": viable}, open(a.out, "w"), indent=2)
        print(f"\n  wrote {a.out}")


if __name__ == "__main__":
    main()
