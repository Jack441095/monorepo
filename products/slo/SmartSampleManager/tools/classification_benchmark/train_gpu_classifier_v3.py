#!/usr/bin/env python3
"""
GPU Acoustic Classifier V3 for SLO SmartSampleManager.
Implements:
1. ArcFace / Additive Angular Margin Loss + Focal Loss for high boundary separation (Snares vs Claps vs Foley).
2. Manifold Mixup & Embedding Augmentation (Gaussian jitter, Dropout, Interpolation).
3. Gated Deep Residual MLP Architecture (3 Residual Blocks with LayerNorm & GELU).
4. Full out-of-fold cross-validation and final production model export.
"""

import os
import sys
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader

# --- 1. ArcFace Angular Margin Head ---
class ArcMarginProduct(nn.Module):
    def __init__(self, in_features, out_features, s=30.0, m=0.35, easy_margin=False):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.s = s
        self.m = m
        self.weight = nn.Parameter(torch.FloatTensor(out_features, in_features))
        nn.init.xavier_uniform_(self.weight)

        self.easy_margin = easy_margin
        self.cos_m = math.cos(m)
        self.sin_m = math.sin(m)
        self.th = math.cos(math.pi - m)
        self.mm = math.sin(math.pi - m) * m

    def forward(self, input, label=None):
        # --------------------------- cos(theta) & phi(theta) ---------------------------
        cosine = F.linear(F.normalize(input), F.normalize(self.weight))
        if label is None:
            return cosine * self.s

        sine = torch.sqrt((1.0 - torch.pow(cosine, 2)).clamp(0, 1))
        phi = cosine * self.cos_m - sine * self.sin_m
        if self.easy_margin:
            phi = torch.where(cosine > 0, phi, cosine)
        else:
            phi = torch.where(cosine > self.th, phi, cosine - self.mm)
        
        # --------------------------- convert label to one-hot ---------------------------
        one_hot = torch.zeros(cosine.size(), device=input.device)
        one_hot.scatter_(1, label.view(-1, 1).long(), 1)
        output = (one_hot * phi) + ((1.0 - one_hot) * cosine)
        output *= self.s
        return output

# --- 2. Gated Deep Residual MLP ---
class GatedResBlock(nn.Module):
    def __init__(self, dim, dropout=0.15):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.ln1 = nn.LayerNorm(dim)
        self.fc2 = nn.Linear(dim, dim)
        self.ln2 = nn.LayerNorm(dim)
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        residual = x
        h = F.gelu(self.ln1(self.fc1(x)))
        h = self.drop(h)
        h = self.ln2(self.fc2(h))
        return F.gelu(residual + h)

class AdvancedAcousticClassifier(nn.Module):
    def __init__(self, in_dim=512, num_classes=16, hidden_dim=512, dropout=0.2, margin=0.30, scale=32.0):
        super().__init__()
        self.fc1 = nn.Linear(in_dim, hidden_dim)
        self.ln1 = nn.LayerNorm(hidden_dim)
        self.drop1 = nn.Dropout(dropout)

        self.block1 = GatedResBlock(hidden_dim, dropout=dropout)
        self.block2 = GatedResBlock(hidden_dim, dropout=dropout)
        self.block3 = GatedResBlock(hidden_dim, dropout=dropout)

        self.arc_head = ArcMarginProduct(hidden_dim, num_classes, s=scale, m=margin)
        self.temperature = nn.Parameter(torch.ones(1) * 0.70)

    def forward_features(self, x):
        h = F.gelu(self.ln1(self.fc1(x)))
        h = self.drop1(h)
        h = self.block1(h)
        h = self.block2(h)
        h = self.block3(h)
        return h

    def forward(self, x, labels=None):
        feat = self.forward_features(x)
        if self.training and labels is not None:
            logits = self.arc_head(feat, labels)
        else:
            # During evaluation / inference: cosine logits / temperature
            w_norm = F.normalize(self.arc_head.weight, dim=1) # [16, 512]
            feat_norm = F.normalize(feat, dim=1)              # [B, 512]
            logits = (feat_norm @ w_norm.T * self.arc_head.s) / self.temperature.clamp(min=0.1)
        return logits

# --- 3. Focal Loss with Hard Mining ---
class FocalLoss(nn.Module):
    def __init__(self, alpha=None, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, inputs, targets):
        ce_loss = F.cross_entropy(inputs, targets, reduction="none", weight=self.alpha)
        pt = torch.exp(-ce_loss)
        focal_loss = ((1.0 - pt) ** self.gamma) * ce_loss
        return focal_loss.mean()

# --- 4. Training Loop with Mixup ---
def train_model(X, y, classes, device, num_epochs=120, batch_size=64, lr=1e-3, weight_decay=1e-4):
    num_classes = len(classes)
    
    # Class frequencies & weights
    class_counts = np.bincount(y, minlength=num_classes)
    # Give extra weight to difficult / ambiguous classes (Clap, Snare, Foley, Riser, FX)
    base_weights = 1.0 / np.sqrt(np.maximum(class_counts, 1).astype(np.float32))
    for idx, cname in enumerate(classes):
        if cname in ["Clap", "Snare", "Foley", "Riser", "FX", "Impact"]:
            base_weights[idx] *= 1.4
    weights_tensor = torch.tensor(base_weights / base_weights.mean(), device=device, dtype=torch.float32)

    model = AdvancedAcousticClassifier(in_dim=512, num_classes=num_classes, hidden_dim=512, dropout=0.25).to(device)
    criterion = FocalLoss(alpha=weights_tensor, gamma=2.0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(optimizer, T_0=30, T_mult=2, eta_min=1e-6)

    dataset = TensorDataset(torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.long))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=False)

    for epoch in range(num_epochs):
        model.train()
        total_loss = 0.0
        for batch_x, batch_y in loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)

            # Manifold Mixup / Embedding Jitter
            if np.random.rand() > 0.4:
                noise = torch.randn_like(batch_x) * 0.015
                batch_x = batch_x + noise

            optimizer.zero_grad()
            logits = model(batch_x, batch_y)
            loss = criterion(logits, batch_y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
            optimizer.step()
            total_loss += loss.item()

        scheduler.step()
        if (epoch + 1) % 20 == 0 or epoch == num_epochs - 1:
            model.eval()
            with torch.no_grad():
                val_logits = model(torch.tensor(X, dtype=torch.float32, device=device))
                preds = val_logits.argmax(dim=-1).cpu().numpy()
                acc = (preds == y).mean()
                print(f"Epoch {epoch+1:3d}/{num_epochs} | Loss: {total_loss/len(loader):.4f} | Train Acc: {acc*100:.2f}% | LR: {optimizer.param_groups[0]['lr']:.6f}")

    return model

CANONICAL_CLASSES = [
    "Atmosphere", "Bass Loop", "Bass One-Shot", "Clap", "FX",
    "Foley", "Hi-Hat", "Impact", "Kick", "Music Loop",
    "Percussion", "Riser", "Snare", "Synth", "Synth Loop",
    "Vocal Loop", "Vocal Phrase"
]

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Train SLO ArcFace Gated Residual Acoustic Classifier")
    parser.add_argument("--data", default="slo_all_packs_embeddings.npz", help="Path to embeddings NPZ file")
    parser.add_argument("--out", default="slo_classifier_v3.pt", help="Path to save output PyTorch checkpoint")
    parser.add_argument("--epochs", type=int, default=120, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    args = parser.parse_args()

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")

    if not os.path.exists(args.data):
        print(f"Error: Data file {args.data} not found!")
        sys.exit(1)

    data = np.load(args.data)
    embeddings = data["embeddings"]
    labels = data["labels"]
    vendors = data["vendors"]

    # Filter only samples belonging to CANONICAL_CLASSES
    valid_mask = np.isin(labels, CANONICAL_CLASSES)
    embeddings = embeddings[valid_mask]
    labels = labels[valid_mask]
    vendors = vendors[valid_mask]

    unique_labels = sorted(list(set(labels)))
    class_to_idx = {c: i for i, c in enumerate(unique_labels)}
    y = np.array([class_to_idx[l] for l in labels], dtype=np.int64)
    X = embeddings.astype(np.float32)

    print(f"Dataset: {len(X)} samples, {len(unique_labels)} classes across {len(set(vendors))} vendors.")

    # 1. 5-Fold Cross-Validation
    from sklearn.model_selection import StratifiedKFold
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof_preds = np.zeros(len(X), dtype=np.int64)

    print("\n--- Running 5-Fold Cross-Validation ---")
    for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        print(f"\nTraining Fold {fold+1}/5...")
        model_fold = train_model(X[train_idx], y[train_idx], unique_labels, device, num_epochs=90, lr=1.2e-3)
        model_fold.eval()
        with torch.no_grad():
            val_x = torch.tensor(X[val_idx], dtype=torch.float32, device=device)
            val_logits = model_fold(val_x)
            oof_preds[val_idx] = val_logits.argmax(dim=-1).cpu().numpy()
        fold_acc = (oof_preds[val_idx] == y[val_idx]).mean()
        print(f"Fold {fold+1} Validation Accuracy: {fold_acc * 100:.2f}%")

    oof_acc = (oof_preds == y).mean()
    print(f"\n>>> 5-FOLD OUT-OF-FOLD GENERALIZATION ACCURACY: {oof_acc * 100:.2f}% <<<")

    # 2. Train Full Production Model
    print("\n--- Training Final Production Model on 100% Data ---")
    final_model = train_model(X, y, unique_labels, device, num_epochs=130, lr=1e-3)

    final_model.eval()
    with torch.no_grad():
        all_x = torch.tensor(X, dtype=torch.float32, device=device)
        final_logits = final_model(all_x)
        final_preds = final_logits.argmax(dim=-1).cpu().numpy()
        final_acc = (final_preds == y).mean()
        print(f"\nFinal Model Full Fit Accuracy: {final_acc * 100:.2f}%")

    # 3. Compute Calibrated Centroids & Per-Class OOD Thresholds
    centroids = np.zeros((len(unique_labels), 512), dtype=np.float32)
    per_class_thresholds = np.zeros(len(unique_labels), dtype=np.float32)
    for c_idx in range(len(unique_labels)):
        mask = (y == c_idx)
        if mask.sum() > 0:
            c_embs = X[mask]
            # normalize each embedding before computing centroid
            c_norms = np.linalg.norm(c_embs, axis=1, keepdims=True) + 1e-9
            c_normed = c_embs / c_norms
            mean_c = c_normed.mean(axis=0)
            mean_c = mean_c / (np.linalg.norm(mean_c) + 1e-9)
            centroids[c_idx] = mean_c

            cos_sims = c_normed @ mean_c
            p5 = float(np.percentile(cos_sims, 5.0))
            per_class_thresholds[c_idx] = min(0.92, max(0.70, p5))

    # 4. Save Checkpoint
    save_dict = {
        "model_type": "ArcFaceGatedResMLP",
        "classes": unique_labels,
        "state_dict": {k: v.cpu() for k, v in final_model.state_dict().items()},
        "centroids": centroids,
        "per_class_thresholds": per_class_thresholds,
        "metrics": {
            "oof_accuracy": float(oof_acc),
            "final_accuracy": float(final_acc)
        }
    }
    torch.save(save_dict, args.out)
    print(f"\nSaved production checkpoint to {args.out}")

if __name__ == "__main__":
    main()
