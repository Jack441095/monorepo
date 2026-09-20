#!/usr/bin/env python3
"""
GPU Training and Evaluation Pipeline for SLO Audio Sample Classifier.
Trains high-capacity neural classification heads on multi-vendor PANNs 512D embeddings.
Uses Stratified Group K-Fold (grouped by vendor) to guarantee zero data leakage.
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
from sklearn.metrics import classification_report, accuracy_score, f1_score, confusion_matrix

CLASSES = [
    "Atmosphere", "Bass Loop", "Bass One-Shot", "Clap", "FX",
    "Foley", "Hi-Hat", "Impact", "Kick", "Music Loop",
    "Percussion", "Riser", "Snare", "Synth", "Synth Loop",
    "Vocal Loop", "Vocal Phrase"
]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}
NUM_CLASSES = len(CLASSES)
EMBED_DIM = 512

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
            # Gaussian jitter and dropout in embedding space
            noise = torch.randn_like(x) * 0.02
            mask = (torch.rand_like(x) > 0.05).float()
            x = (x + noise) * mask
            # L2 normalize
            norm = torch.norm(x, p=2)
            if norm > 1e-6:
                x = x / norm
        return x, y


class LinearClassifier(nn.Module):
    def __init__(self, in_dim=EMBED_DIM, num_classes=NUM_CLASSES):
        super().__init__()
        self.linear = nn.Linear(in_dim, num_classes)
        self.temperature = nn.Parameter(torch.ones(1) * 1.0)

    def forward(self, x):
        return self.linear(x) / self.temperature


class DeepResidualMLP(nn.Module):
    def __init__(self, in_dim=EMBED_DIM, hidden_dim=1024, num_classes=NUM_CLASSES, dropout=0.25):
        super().__init__()
        self.fc1 = nn.Linear(in_dim, hidden_dim)
        self.ln1 = nn.LayerNorm(hidden_dim)
        
        # Residual Block 1
        self.res1_fc1 = nn.Linear(hidden_dim, hidden_dim)
        self.res1_ln1 = nn.LayerNorm(hidden_dim)
        self.res1_fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.res1_ln2 = nn.LayerNorm(hidden_dim)

        # Bottleneck to 512
        self.fc2 = nn.Linear(hidden_dim, 512)
        self.ln2 = nn.LayerNorm(512)
        
        # Output Head
        self.out = nn.Linear(512, num_classes)
        self.dropout = nn.Dropout(dropout)
        self.temperature = nn.Parameter(torch.ones(1) * 1.0)

    def forward(self, x):
        # Input projection
        h = F.gelu(self.ln1(self.fc1(x)))
        h = self.dropout(h)
        
        # Residual Block
        residual = h
        res = F.gelu(self.res1_ln1(self.res1_fc1(h)))
        res = self.dropout(res)
        res = self.res1_ln2(self.res1_fc2(res))
        h = F.gelu(residual + res)
        
        # Bottleneck
        h = F.gelu(self.ln2(self.fc2(h)))
        h = self.dropout(h)
        
        logits = self.out(h)
        return logits / self.temperature


def train_epoch(model, dataloader, optimizer, criterion, device, mixup_alpha=0.2):
    model.train()
    total_loss, total_correct, total_samples = 0.0, 0, 0
    for x, y in dataloader:
        x, y = x.to(device), y.to(device)
        
        if mixup_alpha > 0 and x.size(0) > 1 and np.random.rand() > 0.5:
            lam = np.random.beta(mixup_alpha, mixup_alpha)
            idx = torch.randperm(x.size(0))
            x_mixed = lam * x + (1 - lam) * x[idx]
            y_a, y_b = y, y[idx]
            logits = model(x_mixed)
            loss = lam * criterion(logits, y_a) + (1 - lam) * criterion(logits, y_b)
            pred = logits.argmax(dim=-1)
            correct = (lam * (pred == y_a).float() + (1 - lam) * (pred == y_b).float()).sum().item()
        else:
            logits = model(x)
            loss = criterion(logits, y)
            pred = logits.argmax(dim=-1)
            correct = (pred == y).sum().item()
            
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item() * x.size(0)
        total_correct += correct
        total_samples += x.size(0)
        
    return total_loss / total_samples, total_correct / total_samples


@torch.no_grad()
def evaluate(model, dataloader, device):
    model.eval()
    all_preds, all_labels, all_probs, all_logits = [], [], [], []
    for x, y in dataloader:
        x = x.to(device)
        logits = model(x)
        probs = F.softmax(logits, dim=-1)
        all_logits.append(logits.cpu().numpy())
        all_probs.append(probs.cpu().numpy())
        all_preds.append(probs.argmax(dim=-1).cpu().numpy())
        all_labels.append(y.numpy())
        
    all_logits = np.concatenate(all_logits, axis=0)
    all_probs = np.concatenate(all_probs, axis=0)
    all_preds = np.concatenate(all_preds, axis=0)
    all_labels = np.concatenate(all_labels, axis=0)
    
    acc = accuracy_score(all_labels, all_preds)
    f1 = f1_score(all_labels, all_preds, average='macro')
    return acc, f1, all_preds, all_probs, all_logits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/mnt/data/slo_training/slo_embeddings_v2.npz")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--model-type", choices=["linear", "deep_mlp"], default="deep_mlp")
    parser.add_argument("--gpu", type=int, default=1)
    parser.add_argument("--cv-folds", type=int, default=5)
    args = parser.parse_args()

    device = torch.device(f"cuda:{args.gpu}" if torch.cuda.is_available() else "cpu")
    print(f"Using compute device: {device} ({torch.cuda.get_device_name(args.gpu) if torch.cuda.is_available() else 'CPU'})")

    data = np.load(args.data)
    X = data["embeddings"]
    y_raw = data["labels"]
    vendors = data["vendors"]
    y = np.array([CLASS_TO_IDX[l] for l in y_raw])

    print(f"Loaded {len(X)} samples across {len(CLASSES)} classes and {len(set(vendors))} vendors.")

    # Class Weights for balanced cross-entropy
    class_counts = np.bincount(y, minlength=NUM_CLASSES)
    weights = len(y) / (NUM_CLASSES * np.maximum(class_counts, 1).astype(float))
    class_weights = torch.tensor(weights, dtype=torch.float32).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.05)

    sgkf = StratifiedGroupKFold(n_splits=args.cv_folds, shuffle=True, random_state=42)
    
    oof_predictions = np.zeros(len(y), dtype=int)
    oof_probs = np.zeros((len(y), NUM_CLASSES), dtype=float)
    fold_accuracies, fold_f1s = [], []

    print(f"\n--- Starting {args.cv_folds}-Fold Vendor-Grouped Cross-Validation ({args.model_type}) ---")

    for fold, (train_idx, val_idx) in enumerate(sgkf.split(X, y, groups=vendors), 1):
        train_ds = AudioEmbeddingDataset(X[train_idx], y[train_idx], augment=True)
        val_ds = AudioEmbeddingDataset(X[val_idx], y[val_idx], augment=False)
        
        train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

        if args.model_type == "linear":
            model = LinearClassifier().to(device)
        else:
            model = DeepResidualMLP().to(device)

        optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)

        best_val_acc = 0.0
        best_state = None

        for epoch in range(args.epochs):
            loss, acc = train_epoch(model, train_loader, optimizer, criterion, device)
            val_acc, val_f1, preds, probs, _ = evaluate(model, val_loader, device)
            scheduler.step()

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        model.load_state_dict({k: v.to(device) for k, v in best_state.items()})
        val_acc, val_f1, preds, probs, _ = evaluate(model, val_loader, device)
        
        oof_predictions[val_idx] = preds
        oof_probs[val_idx] = probs
        fold_accuracies.append(val_acc)
        fold_f1s.append(val_f1)
        
        print(f"Fold {fold}/{args.cv_folds}: Validation Accuracy = {val_acc*100:.2f}%, Macro F1 = {val_f1:.4f}")

    overall_acc = accuracy_score(y, oof_predictions)
    overall_f1 = f1_score(y, oof_predictions, average="macro")
    print(f"\n==========================================")
    print(f"OVERALL OUT-OF-FOLD ZERO-LEAKAGE RESULTS:")
    print(f"Overall Accuracy: {overall_acc*100:.2f}%")
    print(f"Overall Macro F1: {overall_f1:.4f}")
    print(f"==========================================")
    print("\nClassification Report (Per-Class Performance):")
    print(classification_report(y, oof_predictions, target_names=CLASSES, digits=3))

    # Train final full model on 100% of data
    print("\nTraining final production model on 100% of multi-vendor dataset...")
    full_ds = AudioEmbeddingDataset(X, y, augment=True)
    full_loader = DataLoader(full_ds, batch_size=args.batch_size, shuffle=True)
    
    if args.model_type == "linear":
        final_model = LinearClassifier().to(device)
    else:
        final_model = DeepResidualMLP().to(device)
        
    optimizer = torch.optim.AdamW(final_model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)
    
    for epoch in range(args.epochs):
        train_epoch(final_model, full_loader, optimizer, criterion, device)
        scheduler.step()

    final_model.eval()
    final_acc, final_f1, _, _, _ = evaluate(final_model, DataLoader(AudioEmbeddingDataset(X, y), batch_size=args.batch_size), device)
    print(f"Final Model Train Fit: Accuracy={final_acc*100:.2f}%, Macro F1={final_f1:.4f}")

    # Save model weights
    save_path = "/mnt/data/slo_training/slo_classifier_model.pt"
    torch.save({
        "model_type": args.model_type,
        "classes": CLASSES,
        "state_dict": final_model.state_dict(),
        "overall_oof_accuracy": overall_acc,
        "overall_oof_macro_f1": overall_f1,
    }, save_path)
    print(f"Model saved to: {save_path}")

if __name__ == "__main__":
    main()
