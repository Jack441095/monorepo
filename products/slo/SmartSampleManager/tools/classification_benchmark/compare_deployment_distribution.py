#!/usr/bin/env python3
"""
Does the classifier operate in-distribution on the files it actually serves?

The training labels come from filename/folder keyword matching, and
production only consults ML when filename/folder evidence is ABSENT. So the
model is trained on one population and deployed on another. This measures
how far apart those populations are, WITHOUT needing hand labels.

Method
------
1. Split the labelled population 80/20, stratified.
2. Train on the 80%.
3. Score two sets the model has never seen:
     A. held-out 20% of the labelled population  (what it was trained on)
     B. the no-evidence population                (what it actually serves)
4. Compare, on both:
     - max softmax confidence
     - max cosine similarity to the class centroids (the OOD score the
       product's own gate uses)
     - fraction falling below the per-class 10th-percentile centroid
       threshold, i.e. what the OOD gate would flag as unknown

A large gap means the deployment population is off-manifold and the
cross-validated accuracy does not transfer. Overlapping distributions mean
the keyword-labelled training data generalises and the selection bias is
less costly than feared.

Note this measures CONFIDENCE, not CORRECTNESS. Only hand labels can
establish accuracy on set B.
"""

import os
import sys
import argparse
import numpy as np
import torch
import torch.nn.functional as F
from sklearn.model_selection import train_test_split

import train_gpu_classifier_v4 as T

X_PATH = "hybrid_x.npy"
Y_PATH = "hybrid_y.npy"
EVAL_NPZ = "slo_no_evidence_evalset.npz"


def pct(a, qs=(5, 25, 50, 75, 95)):
    return {q: float(np.percentile(a, q)) for q in qs}


@torch.no_grad()
def score(model, centroids, X, device, batch=2048):
    """Return (max softmax confidence, max centroid cosine, argmax class)."""
    confs, coss, preds = [], [], []
    for i in range(0, len(X), batch):
        xb = torch.tensor(X[i:i + batch], dtype=torch.float32, device=device)
        h = F.gelu(model.ln1(model.fc1(xb)))
        h = model.block1(h); h = model.block2(h); h = model.block3(h)
        hn = F.normalize(h, dim=1)

        logits = model.arc_head(h, None)
        p = F.softmax(logits, dim=1)
        confs.append(p.max(dim=1).values.cpu().numpy())
        preds.append(p.argmax(dim=1).cpu().numpy())
        coss.append((hn @ centroids.T).max(dim=1).values.cpu().numpy())
    return (np.concatenate(confs), np.concatenate(coss), np.concatenate(preds))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=90)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not os.path.exists(EVAL_NPZ):
        print(f"ERROR: {EVAL_NPZ} not found - run build_no_evidence_evalset.py first")
        return 1

    torch.manual_seed(args.seed); np.random.seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    X = np.load(X_PATH); y = np.load(Y_PATH)
    ev = np.load(EVAL_NPZ, allow_pickle=True)
    Xe = ev["embeddings"].astype(np.float32)
    paths = ev["paths"]
    print(f"labelled: {X.shape}   no-evidence: {Xe.shape}")

    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=args.seed)
    print(f"train {Xtr.shape[0]}  held-out {Xte.shape[0]}\n")

    num_classes = len(T.CLASSES)
    counts = np.bincount(ytr, minlength=num_classes)
    w = torch.tensor([len(ytr) / (num_classes * max(c, 1)) for c in counts],
                     dtype=torch.float32, device=device)

    model = T.ClassifierV4(in_features=X.shape[1], num_classes=num_classes).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1.2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    crit = T.FocalLoss(gamma=2.0, weight=w)
    loader = torch.utils.data.DataLoader(
        T.HybridDataset(Xtr, ytr), batch_size=256, shuffle=True)

    print(f"training {args.epochs} epochs on the 80% split...")
    for ep in range(args.epochs):
        loss, acc = T.train_epoch(model, loader, opt, crit, device)
        sched.step()
        if (ep + 1) % 30 == 0:
            print(f"  epoch {ep+1}/{args.epochs} loss {loss:.4f} acc {acc*100:.2f}%",
                  flush=True)

    # Centroids from the training split only.
    model.eval()
    with torch.no_grad():
        xt = torch.tensor(Xtr, dtype=torch.float32, device=device)
        h = F.gelu(model.ln1(model.fc1(xt)))
        h = model.block1(h); h = model.block2(h); h = model.block3(h)
        hn = F.normalize(h, dim=1)
    cents = torch.zeros(num_classes, hn.shape[1], device=device)
    thresholds = np.zeros(num_classes)
    for c in range(num_classes):
        m = (ytr == c)
        if m.sum() == 0:
            thresholds[c] = 0.5
            continue
        v = hn[torch.tensor(m, device=device)]
        cen = F.normalize(v.mean(dim=0), dim=0)
        cents[c] = cen
        thresholds[c] = float(np.percentile((v @ cen).cpu().numpy(), 10))

    conf_a, cos_a, pred_a = score(model, cents, Xte, device)
    conf_b, cos_b, pred_b = score(model, cents, Xe, device)

    held_acc = float((pred_a == yte).mean())
    print(f"\nheld-out accuracy on the labelled population: {held_acc*100:.2f}%")

    print("\n=== Max softmax confidence ===")
    print(f"{'':>26} {'mean':>8} {'p5':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p95':>8}")
    for name, a in (("A held-out labelled", conf_a), ("B no-evidence (served)", conf_b)):
        q = pct(a)
        print(f"{name:>26} {a.mean():8.4f} {q[5]:8.4f} {q[25]:8.4f} "
              f"{q[50]:8.4f} {q[75]:8.4f} {q[95]:8.4f}")
    print(f"{'gap (A-B) in mean':>26} {conf_a.mean()-conf_b.mean():8.4f}")

    print("\n=== Max cosine to class centroid (the OOD score) ===")
    print(f"{'':>26} {'mean':>8} {'p5':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p95':>8}")
    for name, a in (("A held-out labelled", cos_a), ("B no-evidence (served)", cos_b)):
        q = pct(a)
        print(f"{name:>26} {a.mean():8.4f} {q[5]:8.4f} {q[25]:8.4f} "
              f"{q[50]:8.4f} {q[75]:8.4f} {q[95]:8.4f}")
    print(f"{'gap (A-B) in mean':>26} {cos_a.mean()-cos_b.mean():8.4f}")

    # What the product's own OOD gate would do.
    flag_a = float(np.mean(cos_a < thresholds[pred_a]))
    flag_b = float(np.mean(cos_b < thresholds[pred_b]))
    print("\n=== What the per-class OOD gate would flag as unknown ===")
    print(f"  A held-out labelled   : {flag_a*100:5.1f}%   (calibration target is ~10%)")
    print(f"  B no-evidence (served): {flag_b*100:5.1f}%")

    print("\n=== Predicted class mix on the served population ===")
    ca = np.bincount(pred_a, minlength=num_classes)
    cb = np.bincount(pred_b, minlength=num_classes)
    print(f"{'class':>14} {'A held-out':>11} {'B served':>10}")
    for i in np.argsort(-cb):
        if cb[i] == 0 and ca[i] == 0:
            continue
        print(f"{T.CLASSES[i]:>14} {100*ca[i]/len(pred_a):10.1f}% "
              f"{100*cb[i]/len(pred_b):9.1f}%")

    out = "deployment_distribution_report.npz"
    np.savez(out, conf_a=conf_a, cos_a=cos_a, pred_a=pred_a, yte=yte,
             conf_b=conf_b, cos_b=cos_b, pred_b=pred_b, paths=paths,
             thresholds=thresholds, held_acc=held_acc)
    print(f"\nSaved {out}")

    print("\nReminder: this compares CONFIDENCE, not correctness. Establishing")
    print("accuracy on set B requires hand labels for a sample of those files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
