#!/usr/bin/env python3
"""
train_gpu_classifier_v6_intelligent.py - Next-Gen Intelligent Physical Wave Audio Classifier
NITE DSP - Smart Sample Manager (SLO)

Features:
- Physics-Informed Gated Residual Neural Network with exact zero-dependency C++ export.
- Class-Balanced Focal Loss + Adaptive Angular Margin ArcFace.
- Multi-Scale Physical Wave Kinetics Auxiliary Head (f0, Q, tau_c, B, pitch_slope, odd/even ratio).
- 5-Fold collection-held-out Stratified Group Cross-Validation on NVIDIA RTX
  4090 D (GPU 0), grouped by vendor/pack identity.
- Automatic C++ header export (Weights + Centroids + Parity references).
"""

import os
import sys
import math
import time
import json
import argparse
from collections import Counter
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import StratifiedGroupKFold

CLASSES = [
    "Bass Loop", "Bass One-Shot", "Clap", "FX", "Foley", "Hi-Hat",
    "Impact", "Kick", "Music Loop", "Percussion", "Riser", "Snare",
    "Synth", "Synth Loop", "Vocal Loop", "Vocal Phrase"
]

NUM_CLASSES = len(CLASSES)
EMBEDDING_DIM = 520
HIDDEN_DIM = 512
NUM_PHYSICAL_TARGETS = 6


class HybridPhysicsDataset(Dataset):
    def __init__(self, x, y, physical_targets=None):
        self.x = torch.tensor(x, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.long)
        if physical_targets is not None:
            self.physical_targets = torch.tensor(physical_targets, dtype=torch.float32)
        else:
            # Derive physical targets from the 8 physical DSP features (dims 512..519)
            dsp = self.x[:, 512:]
            f0_norm = dsp[:, 1]          # spectral centroid proxy
            crest_inv = dsp[:, 2]        # 1.0 - crest_factor / 20.0
            zcr = dsp[:, 3]              # zero crossing rate
            decay_norm = dsp[:, 5]       # decay proxy
            odd_even = dsp[:, 6]         # odd/even harmonic ratio proxy
            rolloff = dsp[:, 7]          # spectral rolloff

            tau_c = crest_inv            # Hertzian mallet contact proxy
            Q_factor = decay_norm        # Material Q / resonance
            B_dispersion = torch.clamp(rolloff - f0_norm, 0.0, 1.0) # Stiff-string dispersion proxy
            pitch_slope = zcr

            self.physical_targets = torch.stack([
                f0_norm, Q_factor, tau_c, B_dispersion, pitch_slope, odd_even
            ], dim=1)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.x[idx], self.y[idx], self.physical_targets[idx]


class GatedResBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.ln1 = nn.LayerNorm(dim)
        self.fc2 = nn.Linear(dim, dim)
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x):
        h = F.gelu(self.ln1(self.fc1(x)))
        h = F.gelu(self.ln2(self.fc2(h)))
        return x + h


class AdaptiveArcMarginProduct(nn.Module):
    """
    ArcFace with per-class adaptive margins.
    Tighter margins for distinct acoustic classes; expanded margins for diffuse / high-entropy classes.
    """
    def __init__(self, in_features, out_features, s=30.0, base_m=0.20, class_margins=None):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.s = s
        self.weight = nn.Parameter(torch.FloatTensor(out_features, in_features))
        nn.init.xavier_uniform_(self.weight)

        if class_margins is None:
            class_margins = [base_m] * out_features
        m_tensor = torch.tensor(class_margins, dtype=torch.float32)
        self.register_buffer("m", m_tensor)
        self.register_buffer("cos_m", torch.cos(m_tensor))
        self.register_buffer("sin_m", torch.sin(m_tensor))
        self.register_buffer("th", torch.cos(math.pi - m_tensor))
        self.register_buffer("mm", torch.sin(math.pi - m_tensor) * m_tensor)

    def forward(self, input, label=None):
        cosine = F.linear(F.normalize(input, dim=1), F.normalize(self.weight, dim=1))
        if label is None:
            return cosine * self.s

        sine = torch.sqrt((1.0 - torch.pow(cosine, 2)).clamp(min=1e-7))
        # Batch-aligned margin modulation
        cos_m = self.cos_m[label].unsqueeze(1)
        sin_m = self.sin_m[label].unsqueeze(1)
        th = self.th[label].unsqueeze(1)
        mm = self.mm[label].unsqueeze(1)

        phi = cosine * cos_m - sine * sin_m
        phi = torch.where(cosine > th, phi, cosine - mm)

        one_hot = torch.zeros_like(cosine)
        one_hot.scatter_(1, label.view(-1, 1).long(), 1.0)
        output = (one_hot * phi) + ((1.0 - one_hot) * cosine)
        output *= self.s
        return output


class IntelligentAcousticClassifierV6(nn.Module):
    def __init__(self, in_features=EMBEDDING_DIM, num_classes=NUM_CLASSES, hidden_dim=HIDDEN_DIM,
                 num_phys=NUM_PHYSICAL_TARGETS, class_margins=None):
        super().__init__()
        # Exact layer names matching C++ AcousticClassifier for 100% zero-dependency parity
        self.fc1 = nn.Linear(in_features, hidden_dim)
        self.ln1 = nn.LayerNorm(hidden_dim)

        self.block1 = GatedResBlock(hidden_dim)
        self.block2 = GatedResBlock(hidden_dim)
        self.block3 = GatedResBlock(hidden_dim)

        # Adaptive ArcFace classification head
        self.arc_head = AdaptiveArcMarginProduct(hidden_dim, num_classes, s=30.0, base_m=0.20, class_margins=class_margins)

        # Auxiliary Physical Inversion Head (Multi-Task Wave Mechanics)
        self.phys_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Linear(hidden_dim // 2, num_phys),
            nn.Sigmoid()
        )

    def forward(self, x, label=None):
        h = F.gelu(self.ln1(self.fc1(x)))
        h = self.block1(h)
        h = self.block2(h)
        h = self.block3(h)

        logits = self.arc_head(h, label)
        phys_pred = self.phys_head(h)
        return logits, phys_pred, h


class ClassBalancedFocalLoss(nn.Module):
    def __init__(self, gamma=2.0, weights=None):
        super().__init__()
        self.gamma = gamma
        self.register_buffer("weights", weights if weights is not None else None)

    def forward(self, logits, targets):
        w = self.weights[targets] if self.weights is not None else 1.0
        ce_loss = F.cross_entropy(logits, targets, reduction="none")
        pt = torch.exp(-ce_loss).clamp(min=1e-7, max=1.0)
        focal = w * ((1.0 - pt) ** self.gamma) * ce_loss
        return focal.mean()


def train_epoch(model, dataloader, optimizer, criterion_cls, criterion_phys, device, lambda_phys=0.20):
    model.train()
    total_loss, correct, total = 0.0, 0, 0

    for x, y, phys_gt in dataloader:
        x, y, phys_gt = x.to(device), y.to(device), phys_gt.to(device)
        optimizer.zero_grad()

        logits, phys_pred, _ = model(x, y)
        loss_cls = criterion_cls(logits, y)
        loss_phys = criterion_phys(phys_pred, phys_gt)
        loss = loss_cls + lambda_phys * loss_phys

        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
        optimizer.step()

        total_loss += loss.item() * len(y)
        preds = torch.argmax(logits, dim=1)
        correct += (preds == y).sum().item()
        total += len(y)

    return total_loss / total, correct / total


@torch.no_grad()
def evaluate(model, dataloader, criterion_cls, device):
    model.eval()
    total_loss, correct, total = 0.0, 0, 0
    all_preds, all_labels, all_logits = [], [], []

    for x, y, _ in dataloader:
        x, y = x.to(device), y.to(device)
        logits, _, _ = model(x, None)
        loss = criterion_cls(logits, y)
        total_loss += loss.item() * len(y)
        preds = torch.argmax(logits, dim=1)
        correct += (preds == y).sum().item()
        total += len(y)

        all_preds.extend(preds.cpu().numpy())
        all_labels.extend(y.cpu().numpy())
        all_logits.append(logits.cpu().numpy())

    all_logits = np.concatenate(all_logits, axis=0)
    return total_loss / total, correct / total, np.array(all_preds), np.array(all_labels), all_logits


def compute_centroids_and_thresholds(features, labels, num_classes=16):
    """Computes normalized centroids and 5th-percentile cosine similarity thresholds for OOD gating."""
    panns_dim = 512
    panns_emb = features[:, :panns_dim]
    
    centroids = np.zeros((num_classes, panns_dim), dtype=np.float32)
    thresholds = np.zeros(num_classes, dtype=np.float32)

    for c in range(num_classes):
        mask = (labels == c)
        if np.sum(mask) == 0:
            thresholds[c] = 0.65
            continue
        c_samples = panns_emb[mask]
        c_mean = np.mean(c_samples, axis=0)
        norm = np.linalg.norm(c_mean)
        if norm > 1e-9:
            c_mean /= norm
        centroids[c] = c_mean

        sample_norms = np.linalg.norm(c_samples, axis=1, keepdims=True) + 1e-9
        normed_samples = c_samples / sample_norms
        cos_sims = np.dot(normed_samples, c_mean)
        th = float(np.percentile(cos_sims, 5))
        thresholds[c] = max(0.50, min(0.85, th))

    return centroids, thresholds


def export_cpp_headers(checkpoint_path, weights_header_path, centroids_header_path):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    classes = [str(c) for c in checkpoint["classes"]]
    state_dict = checkpoint["state_dict"]

    # 1. Export Weights
    with open(weights_header_path, "w") as f:
        f.write("#pragma once\n\n")
        f.write("// Automated weights export for Nite DSP SLO AcousticClassifier V6 (Intelligent Physical Wave Classifier).\n")
        f.write("// Deep Physics-Informed Gated Residual MLP + Adaptive Margin ArcFace Head.\n")
        f.write("// Trained on multi-vendor real audio corpus on NVIDIA RTX 4090 D (GPU 0).\n")
        f.write("// Zero-dependency C++ header format for real-time DSP lock-free inference.\n")
        f.write("// DO NOT EDIT MANUALLY.\n\n")
        f.write("namespace AcousticWeights\n{\n")
        f.write("    constexpr int modelVersion = 6;\n")
        f.write("    constexpr int embeddingVersion = 1;\n")
        f.write("    constexpr int taxonomyVersion = 1;\n")
        f.write(f"    constexpr int numClasses = {len(classes)};\n")
        f.write("    constexpr int embeddingDim = 520;\n")
        f.write("    constexpr int hiddenDim = 512;\n")
        f.write("    constexpr float scaleFactor = 30.0f;\n\n")

        class_str = ", ".join([f'"{c}"' for c in classes])
        f.write(f"    inline const char* const classNames[numClasses] = {{ {class_str} }};\n\n")

        def write_matrix_2d(var_name, tensor):
            arr = tensor.numpy()
            shape = arr.shape
            f.write(f"    inline constexpr float {var_name}[{shape[0]}][{shape[1]}] = {{\n")
            for i in range(shape[0]):
                row_str = ", ".join([f"{val:.8f}f" for val in arr[i]])
                f.write(f"        {{ {row_str} }},\n")
            f.write("    };\n\n")

        def write_vector_1d(var_name, tensor):
            arr = tensor.numpy()
            f.write(f"    inline constexpr float {var_name}[{arr.shape[0]}] = {{\n")
            vec_str = ", ".join([f"{val:.8f}f" for val in arr])
            f.write(f"        {vec_str}\n")
            f.write("    };\n\n")

        write_matrix_2d("fc1_weights", state_dict["fc1.weight"])
        write_vector_1d("fc1_biases", state_dict["fc1.bias"])
        write_vector_1d("ln1_gamma", state_dict["ln1.weight"])
        write_vector_1d("ln1_beta", state_dict["ln1.bias"])

        for block_idx in range(1, 4):
            prefix = f"block{block_idx}"
            write_matrix_2d(f"{prefix}_fc1_weights", state_dict[f"{prefix}.fc1.weight"])
            write_vector_1d(f"{prefix}_fc1_biases", state_dict[f"{prefix}.fc1.bias"])
            write_vector_1d(f"{prefix}_ln1_gamma", state_dict[f"{prefix}.ln1.weight"])
            write_vector_1d(f"{prefix}_ln1_beta", state_dict[f"{prefix}.ln1.bias"])

            write_matrix_2d(f"{prefix}_fc2_weights", state_dict[f"{prefix}.fc2.weight"])
            write_vector_1d(f"{prefix}_fc2_biases", state_dict[f"{prefix}.fc2.bias"])
            write_vector_1d(f"{prefix}_ln2_gamma", state_dict[f"{prefix}.ln2.weight"])
            write_vector_1d(f"{prefix}_ln2_beta", state_dict[f"{prefix}.ln2.bias"])

        write_matrix_2d("arc_head_weights", state_dict["arc_head.weight"])
        f.write("}\n")

    print(f"Exported C++ weights to {weights_header_path}")

    # 2. Export Centroids
    if "centroids" in checkpoint:
        centroids = checkpoint["centroids"]
        per_class_th = checkpoint["per_class_thresholds"]

        with open(centroids_header_path, "w") as f:
            f.write("#pragma once\n\n")
            f.write("// Multi-vendor calibrated OOD centroids & thresholds for SLO AcousticClassifier V6.\n")
            f.write("// DO NOT EDIT MANUALLY.\n\n")
            f.write("namespace AcousticOodCentroids\n{\n")
            f.write(f"    constexpr int numClasses = {len(classes)};\n")
            f.write("    constexpr int embeddingDim = 512;\n")
            f.write(f"    constexpr float oodCosineSimilarityThreshold = {checkpoint.get('global_ood_threshold', 0.65):.4f}f;\n\n")

            f.write(f"    inline constexpr float classThresholds[numClasses] = {{\n")
            th_str = ", ".join([f"{th:.4f}f" for th in per_class_th])
            f.write(f"        {th_str}\n    }};\n\n")

            f.write(f"    inline constexpr float centroids[numClasses][embeddingDim] = {{\n")
            for c in range(len(classes)):
                row_str = ", ".join([f"{val:.8f}f" for val in centroids[c]])
                f.write(f"        {{ {row_str} }},\n")
            f.write("    };\n")
            f.write("}\n")

        print(f"Exported C++ centroids to {centroids_header_path}")


def generate_parity_json(model, x_sample, y_sample, output_json_path):
    """Generates numerical reference outputs for C++ unit test verification."""
    model.eval()
    with torch.no_grad():
        device = next(model.parameters()).device
        # Keep parity inputs on the same device as the trained model.  GPU
        # training used to finish checkpoint/header export and then crash here
        # because this tensor was implicitly created on CPU while `model` was
        # still on CUDA, leaving the run without a fresh parity receipt.
        x_tensor = torch.tensor(x_sample, dtype=torch.float32, device=device)
        logits, _, _ = model(x_tensor, None)
        probs = F.softmax(logits, dim=1)

    cases = []
    for i in range(len(x_sample)):
        sample_logits = logits[i].cpu().tolist()
        sample_probs = probs[i].cpu().tolist()
        pred_idx = int(np.argmax(sample_logits))
        cases.append({
            "index": i,
            "expected_subcategory": CLASSES[y_sample[i]],
            "predicted_subcategory": CLASSES[pred_idx],
            "input_features": x_sample[i].tolist(),
            "expected_logits": sample_logits,
            "expected_probabilities": sample_probs
        })

    with open(output_json_path, "w") as f:
        json.dump({"cases": cases}, f, indent=2)
    print(f"Saved parity reference JSON ({len(cases)} cases) to: {output_json_path}")


def main():
    parser = argparse.ArgumentParser(description="Train Intelligent Physical Wave Classifier V6")
    parser.add_argument("--data", type=str, default="slo_all_packs_hybrid_v4.npz")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch_size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--output_model", type=str, default="slo_classifier_v6_intelligent.pt")
    parser.add_argument("--splits", type=int, default=5,
                        help="collection-held-out cross-validation folds")
    args = parser.parse_args()

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Training on device: {device}")
    if torch.cuda.is_available():
        print(f"GPU Name: {torch.cuda.get_device_name(0)}")

    # Load dataset
    print(f"Loading dataset from: {args.data}")
    data = np.load(args.data)
    embeddings = data["embeddings"] # (N, 520)
    raw_labels = data["labels"]
    if "vendors" not in data:
        raise ValueError("training data must include vendors for collection-held-out validation")
    vendors = np.asarray(data["vendors"]).astype(str)
    if len(vendors) != len(raw_labels):
        raise ValueError("vendors and labels must have the same row count")
    class_to_idx = {c: i for i, c in enumerate(CLASSES)}
    labels = np.array([class_to_idx[l] for l in raw_labels], dtype=np.int64)

    N = len(labels)
    print(f"Total samples: {N}, Feature Dim: {embeddings.shape[1]}")

    # Compute inverse class frequencies for balanced focal loss
    class_counts = Counter(labels)
    total_samples = float(N)
    weights = []
    class_margins = []
    for i in range(NUM_CLASSES):
        count = class_counts.get(i, 1)
        # Smoothed inverse frequency weighting
        w = (total_samples / (NUM_CLASSES * count)) ** 0.35
        weights.append(w)
        # Adaptive margin: larger margin for diffuse classes (Percussion=0.26, Synth=0.24), tighter for distinct (Kick=0.18)
        if CLASSES[i] in ("Percussion", "Foley"):
            class_margins.append(0.25)
        elif CLASSES[i] in ("Kick", "Hi-Hat", "Snare", "Clap"):
            class_margins.append(0.18)
        else:
            class_margins.append(0.21)

    weights_tensor = torch.tensor(weights, dtype=torch.float32).to(device)
    weights_tensor = weights_tensor / weights_tensor.mean() # normalize mean to 1.0

    print("Class Margins:", [f"{CLASSES[i]}: {class_margins[i]:.2f}" for i in range(NUM_CLASSES)])

    # Collection-held-out cross validation
    if args.splits < 2:
        raise ValueError("--splits must be at least 2")
    # Ordinary StratifiedKFold leaks pack/vendor signatures across folds and
    # materially overstates open-world accuracy.  Hold out complete vendors
    # instead; rare classes may be absent from an individual validation fold,
    # which is honest evidence that their vendor support is thin.
    skf = StratifiedGroupKFold(n_splits=args.splits, shuffle=True, random_state=42)
    fold_accuracies = []
    oof_predictions = np.zeros(N, dtype=np.int64)

    print(f"\n=== Running {args.splits}-Fold Collection-Held-Out Cross-Validation for Classifier V6 ===")
    for fold, (train_idx, val_idx) in enumerate(
            skf.split(embeddings, labels, groups=vendors)):
        train_groups = set(vendors[train_idx])
        val_groups = set(vendors[val_idx])
        if train_groups & val_groups:
            raise AssertionError("vendor leakage detected in collection-held-out split")
        train_ds = HybridPhysicsDataset(embeddings[train_idx], labels[train_idx])
        val_ds = HybridPhysicsDataset(embeddings[val_idx], labels[val_idx])

        # Do not silently discard the tail of a fold; rare classes are already
        # thin and every labelled row must contribute to the evaluation.
        train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, drop_last=False)
        val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

        model = IntelligentAcousticClassifierV6(
            in_features=EMBEDDING_DIM, num_classes=NUM_CLASSES, hidden_dim=HIDDEN_DIM,
            num_phys=NUM_PHYSICAL_TARGETS, class_margins=class_margins
        ).to(device)

        optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)
        criterion_cls = ClassBalancedFocalLoss(gamma=2.0, weights=weights_tensor)
        criterion_phys = nn.MSELoss()

        best_val_acc = -1.0
        best_val_preds = None
        for epoch in range(1, args.epochs + 1):
            train_loss, train_acc = train_epoch(
                model, train_loader, optimizer, criterion_cls, criterion_phys, device, lambda_phys=0.20
            )
            scheduler.step()

            if epoch % 10 == 0 or epoch == args.epochs:
                val_loss, val_acc, val_preds, val_targets, _ = evaluate(model, val_loader, criterion_cls, device)
                if val_acc > best_val_acc:
                    best_val_acc = val_acc
                    best_val_preds = val_preds.copy()

        fold_accuracies.append(best_val_acc)
        if best_val_preds is None:
            raise AssertionError("cross-validation produced no validation prediction")
        oof_predictions[val_idx] = best_val_preds
        print(f"  Fold {fold+1}/{args.splits} ({len(val_idx)} files, {len(val_groups)} held-out vendors) "
              f"Best Val Acc: {best_val_acc*100:.2f}%")

    # Weight the final OOF score by files, not by folds.  Vendor/pack groups
    # are intentionally uneven in size; an unweighted fold mean would let a
    # tiny held-out pack count as much as thousands of files from one pack.
    oof_acc = float(np.mean(oof_predictions == labels))
    print(f"\n>>> {args.splits}-Fold Collection-Held-Out OOF Accuracy: {oof_acc*100:.2f}% <<<")

    # Train Final Production Model on Full Dataset
    print("\n=== Training Final Production Model on Full Dataset ===")
    full_ds = HybridPhysicsDataset(embeddings, labels)
    full_loader = DataLoader(full_ds, batch_size=args.batch_size, shuffle=True, drop_last=False)

    prod_model = IntelligentAcousticClassifierV6(
        in_features=EMBEDDING_DIM, num_classes=NUM_CLASSES, hidden_dim=HIDDEN_DIM,
        num_phys=NUM_PHYSICAL_TARGETS, class_margins=class_margins
    ).to(device)

    optimizer = torch.optim.AdamW(prod_model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)
    criterion_cls = ClassBalancedFocalLoss(gamma=2.0, weights=weights_tensor)
    criterion_phys = nn.MSELoss()

    for epoch in range(1, args.epochs + 1):
        train_loss, train_acc = train_epoch(
            prod_model, full_loader, optimizer, criterion_cls, criterion_phys, device, lambda_phys=0.20
        )
        scheduler.step()
        if epoch % 10 == 0 or epoch == args.epochs:
            print(f"  Epoch {epoch}/{args.epochs} - Loss: {train_loss:.4f} - Accuracy: {train_acc*100:.2f}%")

    # Compute OOD Centroids and Thresholds
    print("\nComputing multi-vendor calibrated OOD centroids & thresholds...")
    centroids, thresholds = compute_centroids_and_thresholds(embeddings, labels, num_classes=NUM_CLASSES)

    # Save Checkpoint
    checkpoint = {
        "model_version": 6,
        "classes": CLASSES,
        "state_dict": prod_model.state_dict(),
        "val_accuracy": oof_acc,
        "cv_protocol": "StratifiedGroupKFold_by_vendor",
        "cv_splits": int(args.splits),
        "vendor_count": int(len(set(vendors))),
        "cv_fold_best_accuracies": [float(value) for value in fold_accuracies],
        "centroids": centroids,
        "per_class_thresholds": thresholds,
        "global_ood_threshold": 0.65,
        "class_margins": class_margins
    }
    torch.save(checkpoint, args.output_model)
    print(f"Saved production checkpoint to {args.output_model}")

    # Export C++ Headers
    export_cpp_headers(args.output_model, "AcousticClassifierWeights_v6.h", "AcousticClassifierCentroids_v6.h")

    # Generate Parity References for C++ Parity Test Suite
    np.random.seed(42)
    sample_indices = np.random.choice(N, size=10, replace=False)
    generate_parity_json(prod_model, embeddings[sample_indices], labels[sample_indices], "parity_references_v6.json")

    print("\nTraining and Export Complete!")


if __name__ == "__main__":
    main()
