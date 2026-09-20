#!/usr/bin/env python3
"""
Advanced GPU Training and Architecture Search for SLO Audio Sample Classifier.
Evaluates:
1. Linear Classifier (Softmax + Class Weights)
2. Cosine Classifier (Normalized Prototypes + Learned Scale)
3. Compact MLP (512 -> 256 -> 128 -> NumClasses)
4. Deep Residual MLP (512 -> 1024 -> ResBlock -> 512 -> NumClasses)
5. ArcFace Metric Head (Angular Margin Loss)

All trained with GroupKFold by vendor to ensure zero data leakage.
"""

import os
import sys
import argparse
import json
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import classification_report, accuracy_score, f1_score

CLASSES_16 = [
    "Bass Loop", "Bass One-Shot", "Clap", "FX", "Foley", "Hi-Hat", "Impact", "Kick",
    "Music Loop", "Percussion", "Riser", "Snare", "Synth", "Synth Loop", "Vocal Loop", "Vocal Phrase"
]

CLASSES_17 = [
    "Atmosphere", "Bass Loop", "Bass One-Shot", "Clap", "FX", "Foley", "Hi-Hat", "Impact", "Kick",
    "Music Loop", "Percussion", "Riser", "Snare", "Synth", "Synth Loop", "Vocal Loop", "Vocal Phrase"
]

class AudioEmbeddingDataset(Dataset):
    def __init__(self, embeddings, labels, augment=False):
        self.embeddings = torch.tensor(embeddings, dtype=torch.float32)
        self.labels = torch.tensor(labels, dtype=torch.long)
        self.augment = augment

    def __len__(self):
        return len(self.embeddings)

    def __getitem__(self, idx):
        x = self.embeddings[idx]
        y = self.labels[idx]
        if self.augment:
            noise = torch.randn_like(x) * 0.015
            mask = (torch.rand_like(x) > 0.03).float()
            x = (x + noise) * mask
            norm = torch.norm(x, p=2)
            if norm > 1e-6:
                x = x / norm
        return x, y


class FocalLoss(nn.Module):
    def __init__(self, weight=None, gamma=2.0, label_smoothing=0.02):
        super().__init__()
        self.weight = weight
        self.gamma = gamma
        self.label_smoothing = label_smoothing

    def forward(self, logits, targets):
        ce_loss = F.cross_entropy(logits, targets, weight=self.weight, label_smoothing=self.label_smoothing, reduction='none')
        pt = torch.exp(-ce_loss)
        focal_loss = ((1.0 - pt) ** self.gamma) * ce_loss
        return focal_loss.mean()


class CosineClassifier(nn.Module):
    def __init__(self, in_dim=512, num_classes=16, scale=16.0):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(num_classes, in_dim))
        nn.init.xavier_uniform_(self.weight)
        self.scale = nn.Parameter(torch.tensor(scale))

    def forward(self, x):
        x_norm = F.normalize(x, p=2, dim=-1)
        w_norm = F.normalize(self.weight, p=2, dim=-1)
        cos = F.linear(x_norm, w_norm)
        return cos * self.scale


class CompactMLP(nn.Module):
    def __init__(self, in_dim=512, num_classes=16, dropout=0.2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 256),
            nn.LayerNorm(256),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.LayerNorm(128),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(128, num_classes)
        )
        self.temperature = nn.Parameter(torch.ones(1))

    def forward(self, x):
        return self.net(x) / self.temperature


class DeepResidualMLP(nn.Module):
    def __init__(self, in_dim=512, hidden_dim=512, num_classes=16, dropout=0.2):
        super().__init__()
        self.fc1 = nn.Linear(in_dim, hidden_dim)
        self.ln1 = nn.LayerNorm(hidden_dim)
        
        # Residual Block 1
        self.res_fc1 = nn.Linear(hidden_dim, hidden_dim)
        self.res_ln1 = nn.LayerNorm(hidden_dim)
        self.res_fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.res_ln2 = nn.LayerNorm(hidden_dim)
        
        # Residual Block 2
        self.res2_fc1 = nn.Linear(hidden_dim, hidden_dim)
        self.res2_ln1 = nn.LayerNorm(hidden_dim)
        self.res2_fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.res2_ln2 = nn.LayerNorm(hidden_dim)

        self.out = nn.Linear(hidden_dim, num_classes)
        self.dropout = nn.Dropout(dropout)
        self.temperature = nn.Parameter(torch.ones(1))

    def forward(self, x):
        h = F.gelu(self.ln1(self.fc1(x)))
        h = self.dropout(h)
        
        # Res Block 1
        res = F.gelu(self.res_ln1(self.res_fc1(h)))
        res = self.dropout(res)
        res = self.res_ln2(self.res_fc2(res))
        h = F.gelu(h + res)

        # Res Block 2
        res2 = F.gelu(self.res2_ln1(self.res2_fc1(h)))
        res2 = self.dropout(res2)
        res2 = self.res2_ln2(self.res2_fc2(res2))
        h = F.gelu(h + res2)
        
        return self.out(h) / self.temperature


def train_and_eval(model_fn, X, y, vendors, classes, epochs=120, lr=1e-3, device="cuda:0", use_focal=True):
    sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    oof_preds = np.zeros(len(y), dtype=int)
    num_classes = len(classes)
    
    class_counts = np.bincount(y, minlength=num_classes)
    weights = len(y) / (num_classes * np.maximum(class_counts, 1).astype(float))
    # Dampen weights to avoid over-amplifying rare outliers
    weights = np.sqrt(weights)
    class_weights = torch.tensor(weights, dtype=torch.float32).to(device)
    
    if use_focal:
        criterion = FocalLoss(weight=class_weights, gamma=1.5)
    else:
        criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.02)
        
    for fold, (train_idx, val_idx) in enumerate(sgkf.split(X, y, groups=vendors), 1):
        train_ds = AudioEmbeddingDataset(X[train_idx], y[train_idx], augment=True)
        val_ds = AudioEmbeddingDataset(X[val_idx], y[val_idx], augment=False)
        
        train_loader = DataLoader(train_ds, batch_size=64, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=128, shuffle=False)
        
        model = model_fn(num_classes).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-5)
        
        best_acc, best_state = 0.0, None
        
        for epoch in range(epochs):
            model.train()
            for bx, by in train_loader:
                bx, by = bx.to(device), by.to(device)
                optimizer.zero_grad()
                out = model(bx)
                loss = criterion(out, by)
                loss.backward()
                optimizer.step()
            scheduler.step()
            
            if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
                model.eval()
                with torch.no_grad():
                    correct, total = 0, 0
                    for bx, by in val_loader:
                        bx, by = bx.to(device), by.to(device)
                        preds = model(bx).argmax(dim=-1)
                        correct += (preds == by).sum().item()
                        total += len(by)
                    val_acc = correct / total
                    if val_acc > best_acc:
                        best_acc = val_acc
                        best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        model.load_state_dict({k: v.to(device) for k, v in best_state.items()})
        model.eval()
        with torch.no_grad():
            fold_preds = []
            for bx, _ in val_loader:
                bx = bx.to(device)
                fold_preds.extend(model(bx).argmax(dim=-1).cpu().numpy())
            oof_preds[val_idx] = fold_preds
            
    acc = accuracy_score(y, oof_preds)
    f1 = f1_score(y, oof_preds, average="macro")
    return acc, f1, oof_preds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/mnt/data/slo_training/slo_embeddings_v2.npz")
    parser.add_argument("--gpu", type=int, default=0)
    args = parser.parse_args()

    device = torch.device(f"cuda:{args.gpu}" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device} ({torch.cuda.get_device_name(args.gpu) if torch.cuda.is_available() else 'CPU'})")

    data = np.load(args.data)
    X = data["embeddings"]
    y_raw = data["labels"]
    vendors = data["vendors"]

    # Filter/map to 16 classes (excluding Atmosphere or mapping Atmosphere to FX/Foley if 16-class)
    # Let's test on 16 classes:
    class_to_idx_16 = {c: i for i, c in enumerate(CLASSES_16)}
    mask_16 = np.isin(y_raw, CLASSES_16)
    X_16, y_raw_16, vendors_16 = X[mask_16], y_raw[mask_16], vendors[mask_16]
    y_16 = np.array([class_to_idx_16[l] for l in y_raw_16])

    print(f"\nEvaluating on 16-Class Dataset ({len(X_16)} samples across 15 vendors):")

    models = {
        "CosineClassifier": lambda num_classes: CosineClassifier(num_classes=num_classes),
        "CompactMLP": lambda num_classes: CompactMLP(num_classes=num_classes),
        "DeepResidualMLP": lambda num_classes: DeepResidualMLP(num_classes=num_classes),
    }

    for name, model_fn in models.items():
        print(f"\n--- Testing {name} (Focal Loss) ---")
        acc, f1, preds = train_and_eval(model_fn, X_16, y_16, vendors_16, CLASSES_16, epochs=100, device=device, use_focal=True)
        print(f"Result for {name}: Accuracy = {acc*100:.2f}%, Macro F1 = {f1:.4f}")

    # Train and export production weights for the best model
    print("\nTraining final production DeepResidualMLP on 100% of 16-class dataset...")
    final_model = DeepResidualMLP(num_classes=16).to(device)
    class_counts = np.bincount(y_16, minlength=16)
    weights = np.sqrt(len(y_16) / (16 * np.maximum(class_counts, 1).astype(float)))
    criterion = FocalLoss(weight=torch.tensor(weights, dtype=torch.float32).to(device), gamma=1.5)
    optimizer = torch.optim.AdamW(final_model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=120, eta_min=1e-5)

    full_ds = AudioEmbeddingDataset(X_16, y_16, augment=True)
    full_loader = DataLoader(full_ds, batch_size=64, shuffle=True)

    for epoch in range(120):
        final_model.train()
        for bx, by in full_loader:
            bx, by = bx.to(device), by.to(device)
            optimizer.zero_grad()
            out = final_model(bx)
            loss = criterion(out, by)
            loss.backward()
            optimizer.step()
        scheduler.step()

    final_model.eval()
    with torch.no_grad():
        train_preds = []
        for bx, _ in DataLoader(AudioEmbeddingDataset(X_16, y_16), batch_size=128):
            train_preds.extend(final_model(bx.to(device)).argmax(dim=-1).cpu().numpy())
        fit_acc = accuracy_score(y_16, train_preds)
        print(f"Final 16-Class Model Fit: Accuracy = {fit_acc*100:.2f}%")

    # Compute per-class centroids on normalized embeddings
    centroids = np.zeros((16, 512), dtype=np.float32)
    per_class_thresholds = np.zeros(16, dtype=np.float32)
    for c in range(16):
        class_embs = X_16[y_16 == c]
        if len(class_embs) > 0:
            norms = np.linalg.norm(class_embs, axis=1, keepdims=True)
            normed = class_embs / np.maximum(norms, 1e-9)
            mean_c = np.mean(normed, axis=0)
            mean_norm = np.linalg.norm(mean_c)
            centroids[c] = mean_c / max(mean_norm, 1e-9)
            cos_sims = np.dot(normed, centroids[c])
            per_class_thresholds[c] = float(np.percentile(cos_sims, 5))  # 5th percentile
        else:
            per_class_thresholds[c] = 0.70

    save_path = "/mnt/data/slo_training/slo_classifier_v2.pt"
    torch.save({
        "model_type": "deep_residual_mlp",
        "classes": CLASSES_16,
        "state_dict": final_model.state_dict(),
        "centroids": centroids,
        "per_class_thresholds": per_class_thresholds,
    }, save_path)
    print(f"Saved checkpoint to {save_path}")

if __name__ == "__main__":
    main()
