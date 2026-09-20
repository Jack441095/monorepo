#!/usr/bin/env python3
"""Collection-held-out benchmark for the first factorised prediction head.

This is research-only: it emits metrics and a receipt, never production
weights, cache updates, approval decisions, or rename plans.  The sealed
class-gate validation manifest is excluded through the frozen training
manifest, and every fold asserts zero collection overlap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold


DRUMS = {"Kick", "Snare", "Clap", "Hi-Hat", "Hi-Hat Loop", "Crash",
         "Rimshot", "Percussion", "Percussion Loop", "Drum Loop",
         "Kick Loop", "Top Loop"}


def family_for(label: str) -> str:
    if label in DRUMS:
        return "drums"
    if label.startswith("Bass"):
        return "bass"
    if label.startswith("Vocal"):
        return "vocals"
    if label in {"Foley", "Foley Loop", "Impact", "Riser", "SFX"}:
        return "fx"
    if label == "Other/none":
        return "rejection"
    return "tonal"


def form_for(label: str) -> str:
    if label == "Other/none":
        return "rejection"
    if "Loop" in label:
        return "loop"
    if "Phrase" in label:
        return "phrase"
    if "Fill" in label:
        return "fill"
    return "one-shot"


def stable_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs(corpus: Path, manifest: Path):
    z = np.load(corpus, allow_pickle=True)
    by_path = {os.path.abspath(str(p)): i for i, p in enumerate(z["paths"])}
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    rows = payload["rows"]
    indices = []
    labels = []
    groups = []
    for row in rows:
        path = os.path.abspath(str(row["path"]))
        if path not in by_path:
            raise ValueError(f"manifest path missing from corpus: {path}")
        indices.append(by_path[path])
        labels.append(str(row["label"]))
        groups.append(str(row["vendor"]))
    X = np.asarray(z["emb"], dtype=np.float32)[indices]
    y = np.asarray(labels, dtype=object)
    g = np.asarray(groups, dtype=object)
    if len(set(indices)) != len(indices):
        raise ValueError("manifest contains duplicate corpus rows")
    return X, y, g


def centroid_predict(Xtr, ytr, Xte, classes):
    mean = Xtr.mean(0)
    scale = Xtr.std(0)
    scale[scale < 1e-6] = 1.0
    a = (Xtr - mean) / scale
    b = (Xte - mean) / scale
    a /= np.linalg.norm(a, axis=1, keepdims=True) + 1e-9
    b /= np.linalg.norm(b, axis=1, keepdims=True) + 1e-9
    centroids = []
    for cls in classes:
        vals = a[ytr == cls]
        centroids.append(vals.mean(0) if len(vals) else np.zeros(a.shape[1]))
    C = np.asarray(centroids)
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9
    scores = b @ C.T
    return np.asarray(classes, dtype=object)[scores.argmax(1)]


def train_predict(Xtr, ytr, Xte, classes, seed, epochs=80, batch_size=128):
    import torch
    from torch import nn

    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    mean = Xtr.mean(0).astype(np.float32)
    scale = Xtr.std(0).astype(np.float32)
    scale[scale < 1e-6] = 1.0
    A = ((Xtr - mean) / scale).astype(np.float32)
    B = ((Xte - mean) / scale).astype(np.float32)
    class_index = {cls: i for i, cls in enumerate(classes)}
    yi = np.asarray([class_index[str(v)] for v in ytr], dtype=np.int64)
    fams = sorted({family_for(str(v)) for v in classes})
    forms = sorted({form_for(str(v)) for v in classes})
    fi = {name: i for i, name in enumerate(fams)}
    oi = {name: i for i, name in enumerate(forms)}
    yf = np.asarray([fi[family_for(str(v))] for v in ytr], dtype=np.int64)
    yo = np.asarray([oi[form_for(str(v))] for v in ytr], dtype=np.int64)

    class_weights = np.bincount(yi, minlength=len(classes)).astype(np.float32)
    class_weights = 1.0 / np.maximum(class_weights, 1.0)
    class_weights *= len(classes) / class_weights.sum()

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.shared = nn.Sequential(
                nn.Linear(A.shape[1], 256), nn.LayerNorm(256), nn.GELU(),
                nn.Dropout(0.10), nn.Linear(256, 128), nn.GELU(),
            )
            self.identity = nn.Linear(128, len(classes))
            self.family = nn.Linear(128, len(fams))
            self.form = nn.Linear(128, len(forms))

        def forward(self, x):
            h = self.shared(x)
            return self.identity(h), self.family(h), self.form(h)

    model = Net().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    loss_id = nn.CrossEntropyLoss(weight=torch.tensor(class_weights, device=device))
    loss_family = nn.CrossEntropyLoss()
    loss_form = nn.CrossEntropyLoss()
    order_rng = np.random.default_rng(seed)
    model.train()
    for _ in range(epochs):
        order = order_rng.permutation(len(A))
        for start in range(0, len(order), batch_size):
            ix = order[start:start + batch_size]
            xb = torch.from_numpy(A[ix]).to(device)
            logits_id, logits_family, logits_form = model(xb)
            loss = (loss_id(logits_id, torch.from_numpy(yi[ix]).to(device))
                    + 0.35 * loss_family(logits_family, torch.from_numpy(yf[ix]).to(device))
                    + 0.35 * loss_form(logits_form, torch.from_numpy(yo[ix]).to(device)))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
    model.eval()
    with torch.no_grad():
        logits = model(torch.from_numpy(B).to(device))
        id_logits = logits[0].cpu().numpy()
        family_logits = logits[1].cpu().numpy()
        form_logits = logits[2].cpu().numpy()
    # Keep the identity head primary, but reward a structurally compatible
    # family/form prediction. This remains a prediction, not a policy action.
    fam_lookup = np.asarray([fi[family_for(str(cls))] for cls in classes])
    form_lookup = np.asarray([oi[form_for(str(cls))] for cls in classes])
    id_logits = id_logits + 0.20 * family_logits[:, fam_lookup]
    id_logits = id_logits + 0.20 * form_logits[:, form_lookup]
    return np.asarray(classes, dtype=object)[id_logits.argmax(1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=80)
    args = parser.parse_args()
    X, y, groups = load_inputs(args.corpus, args.manifest)
    inventory = {cls: {"n": int((y == cls).sum()),
                       "groups": int(len(set(groups[y == cls])))}
                 for cls in sorted(set(y))}
    classes = [cls for cls, rec in inventory.items()
               if rec["n"] >= 5 and rec["groups"] >= 5]
    keep = np.isin(y, classes)
    X, y, groups = X[keep], y[keep], groups[keep]
    print(f"training rows={len(y)} classes={len(classes)} collections={len(set(groups))}")
    result = {"centroid": [], "factorised_head": []}
    for seed in range(args.seeds):
        cv = StratifiedGroupKFold(args.splits, shuffle=True, random_state=seed)
        pred_centroid = np.empty(len(y), dtype=object)
        pred_head = np.empty(len(y), dtype=object)
        for tr, te in cv.split(X, y, groups=groups):
            overlap = set(groups[tr]) & set(groups[te])
            if overlap:
                raise AssertionError(f"collection leakage: {sorted(overlap)[:3]}")
            pred_centroid[te] = centroid_predict(X[tr], y[tr], X[te], classes)
            pred_head[te] = train_predict(X[tr], y[tr], X[te], classes,
                                          seed=seed, epochs=args.epochs)
        result["centroid"].append({
            "accuracy": 100 * float((pred_centroid == y).mean()),
            "macro_f1": 100 * float(f1_score(y, pred_centroid.astype(str),
                                             average="macro", zero_division=0)),
        })
        result["factorised_head"].append({
            "accuracy": 100 * float((pred_head == y).mean()),
            "macro_f1": 100 * float(f1_score(y, pred_head.astype(str),
                                             average="macro", zero_division=0)),
        })
        print(seed, result["centroid"][-1], result["factorised_head"][-1])

    summary = {}
    for name, rows in result.items():
        summary[name] = {
            metric: round(float(np.mean([row[metric] for row in rows])), 3)
            for metric in ("accuracy", "macro_f1")
        }
        summary[name]["accuracy_sd"] = round(float(np.std([row["accuracy"] for row in rows])), 3)
    payload = {
        "record_type": "slo_factorised_head_benchmark",
        "schema_version": "1.0.0",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "seeds": args.seeds, "splits": args.splits,
                     "epochs": args.epochs, "sealed_validation_excluded": True,
                     "decision_gate_pp": 2.0},
        "inputs": {"corpus": str(args.corpus.resolve()),
                   "manifest": str(args.manifest.resolve()),
                   "n_rows": int(len(y)), "n_classes": len(classes),
                   "n_collections": int(len(set(groups)))},
        "inventory": inventory,
        "per_seed": result,
        "summary": summary,
        "decision": "research evidence only; no production weights or rename actions",
        "safety": {"read_only": True, "production_model_changed": False,
                   "source_audio_modified": False, "rename_actions": False},
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

