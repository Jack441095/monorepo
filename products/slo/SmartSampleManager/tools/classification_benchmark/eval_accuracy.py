#!/usr/bin/env python3
import os
import sys
import numpy as np
import torch
from collections import defaultdict

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
from test_sim import forward_cpp_sim

ckpt_path = os.path.join(script_dir, "slo_classifier_v2.pt")
data_path = os.path.join(script_dir, "slo_embeddings_v2.npz")

ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
classes = ckpt["classes"]
sd = ckpt["state_dict"]

data = np.load(data_path)
embeddings = data["embeddings"]
labels = data["labels"]
vendors = data["vendors"]

X = torch.tensor(embeddings, dtype=torch.float32)
logits = forward_cpp_sim(X, sd)
preds = [classes[i] for i in logits.argmax(dim=-1)]

y_true = list(labels)
y_pred = preds

correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
total = len(y_true)
acc = correct / total

print("=" * 65)
print(f"MULTI-VENDOR REAL AUDIO ACCURACY (N={total}): {acc * 100:.2f}%")
print("=" * 65)

per_class = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "total": 0})
for t, p in zip(y_true, y_pred):
    per_class[t]["total"] += 1
    if t == p:
        per_class[t]["tp"] += 1
    else:
        per_class[t]["fn"] += 1
        per_class[p]["fp"] += 1

hdr = "{:<16} | {:>5} | {:>10} | {:>10} | {:>10}".format("Class", "N", "Precision", "Recall", "F1")
print(hdr)
print("-" * 65)
f1_list = []
for c in sorted(classes):
    m = per_class[c]
    p = m["tp"] / (m["tp"] + m["fp"]) if (m["tp"] + m["fp"]) > 0 else 0
    r = m["tp"] / (m["tp"] + m["fn"]) if (m["tp"] + m["fn"]) > 0 else 0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
    f1_list.append(f1)
    row = "{:<16} | {:>5} | {:>9.1f}% | {:>9.1f}% | {:>9.1f}%".format(c, m["total"], p * 100, r * 100, f1 * 100)
    print(row)

print("-" * 65)
print("Macro F1 Score: {:.2f}%".format(np.mean(f1_list) * 100))
print("=" * 65)
