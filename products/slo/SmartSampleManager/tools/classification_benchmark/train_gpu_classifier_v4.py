#!/usr/bin/env python3
"""
GPU Classifier V4 Training Script for SLO Acoustic Classifier (Hybrid 520D Feature Vector).
Features:
- Input: 520-D vector (512-D PANNs embedding + 8-D normalized acoustic DSP features)
- Model: Gated Residual MLP (3 blocks) + ArcFace Cosine Head (scale = 30.0, margin = 0.20)
- Loss: Focal Loss (gamma = 2.0) + ArcFace Loss
- Training: Cosine Annealing LR schedule, AdamW optimizer, 5-fold cross-validation
"""

import os
import sys
import math
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import StratifiedKFold
from collections import Counter

X_PATH = "hybrid_x.npy"
Y_PATH = "hybrid_y.npy"
CHECKPOINT_OUT = "slo_classifier_v4_hybrid.pt"

# Matched to train_gpu_classifier_v3.py so OOF numbers are comparable.
EPOCHS_PER_FOLD = 90
EPOCHS_FINAL = 130

CLASSES = [
    "Bass Loop", "Bass One-Shot", "Clap", "FX", "Foley", "Hi-Hat",
    "Impact", "Kick", "Music Loop", "Percussion", "Riser", "Snare",
    "Synth", "Synth Loop", "Vocal Loop", "Vocal Phrase"
]

class HybridDataset(Dataset):
    def __init__(self, features, labels):
        self.features = torch.tensor(features, dtype=torch.float32)
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return self.features[idx], self.labels[idx]

class GatedResBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.ln1 = nn.LayerNorm(dim)
        self.fc2 = nn.Linear(dim, dim)
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x):
        res = x
        h = F.gelu(self.ln1(self.fc1(x)))
        h = F.gelu(self.ln2(self.fc2(h)))
        return res + h

class ArcMarginProduct(nn.Module):
    def __init__(self, in_features, out_features, s=30.0, m=0.20):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.s = s
        self.m = m
        self.weight = nn.Parameter(torch.FloatTensor(out_features, in_features))
        nn.init.xavier_uniform_(self.weight)
        
        self.cos_m = math.cos(m)
        self.sin_m = math.sin(m)
        self.th = math.cos(math.pi - m)
        self.mm = math.sin(math.pi - m) * m

    def forward(self, input, label=None):
        cosine = F.linear(F.normalize(input, dim=1), F.normalize(self.weight, dim=1))
        if label is None:
            return cosine * self.s
            
        sine = torch.sqrt(1.0 - torch.pow(cosine, 2)).clamp(0, 1)
        phi = cosine * self.cos_m - sine * self.sin_m
        phi = torch.where(cosine > self.th, phi, cosine - self.mm)
        
        one_hot = torch.zeros(cosine.size(), device=input.device)
        one_hot.scatter_(1, label.view(-1, 1).long(), 1)
        output = (one_hot * phi) + ((1.0 - one_hot) * cosine)
        output *= self.s
        return output

class FocalLoss(nn.Module):
    def __init__(self, gamma=2.0, weight=None):
        super().__init__()
        self.gamma = gamma
        self.weight = weight

    def forward(self, input, target):
        ce_loss = F.cross_entropy(input, target, reduction='none', weight=self.weight)
        pt = torch.exp(-ce_loss)
        focal_loss = ((1 - pt) ** self.gamma) * ce_loss
        return focal_loss.mean()

class ClassifierV4(nn.Module):
    def __init__(self, in_features=520, num_classes=16, hidden_dim=512):
        super().__init__()
        self.fc1 = nn.Linear(in_features, hidden_dim)
        self.ln1 = nn.LayerNorm(hidden_dim)
        self.block1 = GatedResBlock(hidden_dim)
        self.block2 = GatedResBlock(hidden_dim)
        self.block3 = GatedResBlock(hidden_dim)
        self.arc_head = ArcMarginProduct(hidden_dim, num_classes, s=30.0, m=0.20)

    def forward(self, x, label=None):
        h = F.gelu(self.ln1(self.fc1(x)))
        h = self.block1(h)
        h = self.block2(h)
        h = self.block3(h)
        return self.arc_head(h, label)

def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        optimizer.zero_grad()
        logits = model(x, y)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item() * len(y)
        preds = torch.argmax(logits, dim=1)
        correct += (preds == y).sum().item()
        total += len(y)
    return total_loss / total, correct / total

@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss, correct, total = 0.0, 0, 0
    all_preds, all_labels = [], []
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        logits = model(x)
        loss = criterion(logits, y)
        
        total_loss += loss.item() * len(y)
        preds = torch.argmax(logits, dim=1)
        correct += (preds == y).sum().item()
        total += len(y)
        all_preds.extend(preds.cpu().numpy())
        all_labels.extend(y.cpu().numpy())
    return total_loss / total, correct / total, np.array(all_preds), np.array(all_labels)

def main():
    parser = argparse.ArgumentParser(
        description="Train the V4 acoustic classifier. Use --input-dims to run "
                    "the PANNs-only (512) vs hybrid (520) ablation with every "
                    "other setting held identical.")
    parser.add_argument("--input-dims", type=int, default=520, choices=[512, 520],
                        help="512 = PANNs embedding only; 520 = PANNs + 8 DSP features")
    parser.add_argument("--out", type=str, default=None,
                        help="Checkpoint output path (default derived from --input-dims)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Torch/numpy seed, so the two ablation arms differ only in input dims")
    args = parser.parse_args()

    in_dims = args.input_dims
    checkpoint_out = args.out or (
        CHECKPOINT_OUT if in_dims == 520 else "slo_classifier_v4_pannsonly.pt")

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    if torch.cuda.is_available():
        print(f"GPU Device Name: {torch.cuda.get_device_name(0)}")

    features = np.load(X_PATH)
    labels = np.load(Y_PATH)
    classes = CLASSES
    num_classes = len(classes)

    # The hybrid file is always 520-D on disk; the 512 arm drops the 8 DSP
    # columns so the two runs differ ONLY in whether those features exist.
    if in_dims == 512:
        features = features[:, :512]
    features = np.ascontiguousarray(features)

    print(f"Dataset features shape: {features.shape}, num classes: {num_classes}")
    print(f"Input dims: {in_dims} ({'PANNs + 8 DSP' if in_dims == 520 else 'PANNs only'})")
    print(f"Checkpoint out: {checkpoint_out}")
    print(f"Protocol: {EPOCHS_PER_FOLD} epochs/fold, {EPOCHS_FINAL} final, "
          f"final-model OOF eval (matches V3)")

    # Compute class weights for Focal Loss
    counts = Counter(labels)
    total_samples = len(labels)
    class_weights = torch.tensor([total_samples / (num_classes * counts[i]) for i in range(num_classes)], dtype=torch.float32).to(device)

    # 5-Fold Cross Validation
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof_preds = np.zeros(len(labels), dtype=int)
    fold_accuracies = []

    print("\n=== Running 5-Fold Cross-Validation for Classifier V4 ===")
    for fold, (train_idx, val_idx) in enumerate(skf.split(features, labels)):
        train_ds = HybridDataset(features[train_idx], labels[train_idx])
        val_ds = HybridDataset(features[val_idx], labels[val_idx])
        
        train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=512, shuffle=False)
        
        model = ClassifierV4(in_features=in_dims, num_classes=num_classes).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1.2e-3, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS_PER_FOLD)
        criterion = FocalLoss(gamma=2.0, weight=class_weights)

        # Train the full schedule, then evaluate the FINAL model once.
        # This matches train_gpu_classifier_v3.py's protocol exactly.
        #
        # The previous behaviour evaluated every epoch and kept the
        # predictions from whichever epoch scored best on the validation
        # fold. That is model selection on the evaluation set: it inflates
        # OOF accuracy and makes any comparison against V3's honest OOF
        # number invalid. Do not reintroduce it.
        for epoch in range(EPOCHS_PER_FOLD):
            train_loss, train_acc = train_epoch(model, train_loader, optimizer, criterion, device)
            scheduler.step()
            if (epoch + 1) % 30 == 0 or epoch == EPOCHS_PER_FOLD - 1:
                print(f"    epoch {epoch+1:3d}/{EPOCHS_PER_FOLD} - loss {train_loss:.4f} "
                      f"- train acc {train_acc*100:.2f}%", flush=True)

        val_loss, val_acc, preds, _ = evaluate(model, val_loader, criterion, device)
        oof_preds[val_idx] = preds
        fold_accuracies.append(val_acc)
        print(f"  Fold {fold+1}/5 Val Acc: {val_acc*100:.2f}%", flush=True)

    oof_acc = (oof_preds == labels).mean()
    print(f"\n>>> 5-Fold Cross-Validation OOF Accuracy: {oof_acc*100:.2f}% <<<")

    print("\n=== Training Final Production Fit Model on Full Dataset ===")
    full_ds = HybridDataset(features, labels)
    full_loader = DataLoader(full_ds, batch_size=256, shuffle=True)
    
    final_model = ClassifierV4(in_features=in_dims, num_classes=num_classes).to(device)
    optimizer = torch.optim.AdamW(final_model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS_FINAL)
    criterion = FocalLoss(gamma=2.0, weight=class_weights)

    for epoch in range(EPOCHS_FINAL):
        t_loss, t_acc = train_epoch(final_model, full_loader, optimizer, criterion, device)
        scheduler.step()
        if (epoch + 1) % 10 == 0 or epoch == EPOCHS_FINAL - 1:
            print(f"  Epoch {epoch+1:03d}/{EPOCHS_FINAL} - Loss: {t_loss:.4f} - Accuracy: {t_acc*100:.2f}%", flush=True)

    # Compute centroids & per-class thresholds
    final_model.eval()
    with torch.no_grad():
        x_tensor = torch.tensor(features, dtype=torch.float32).to(device)
        h = F.gelu(final_model.ln1(final_model.fc1(x_tensor)))
        h = final_model.block1(h)
        h = final_model.block2(h)
        h = final_model.block3(h)
        h_norm = F.normalize(h, dim=1).cpu().numpy()

    centroids = np.zeros((num_classes, 512), dtype=np.float32)
    per_class_thresholds = np.zeros(num_classes, dtype=np.float32)

    for c in range(num_classes):
        c_mask = (labels == c)
        if np.sum(c_mask) > 0:
            c_vecs = h_norm[c_mask]
            centroid = np.mean(c_vecs, axis=0)
            centroid = centroid / np.linalg.norm(centroid)
            centroids[c] = centroid
            
            cosines = np.dot(c_vecs, centroid)
            per_class_thresholds[c] = float(np.percentile(cosines, 10))
        else:
            per_class_thresholds[c] = 0.50

    checkpoint = {
        "model_type": "ClassifierV4_ArcFace_Hybrid",
        "classes": classes,
        "state_dict": final_model.state_dict(),
        "centroids": centroids,
        "per_class_thresholds": per_class_thresholds,
        "metrics": {
            "cv_oof_accuracy": float(oof_acc),
            "fold_accuracies": [float(a) for a in fold_accuracies],
            "full_fit_accuracy": float(t_acc)
        }
    }

    torch.save(checkpoint, checkpoint_out)
    print(f"\nSaved production checkpoint to {checkpoint_out} ({os.path.getsize(checkpoint_out)/(1024*1024):.2f} MB)")

if __name__ == "__main__":
    main()
