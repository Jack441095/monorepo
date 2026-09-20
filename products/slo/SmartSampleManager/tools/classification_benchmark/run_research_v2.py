import os
import sys
import json
import shutil
import subprocess
import sqlite3
import struct
import math
import wave
import random
from collections import defaultdict, Counter
import numpy as np
from sklearn.model_selection import StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
import torch
import torch.nn as nn
import torch.optim as optim

def cosine_similarity_np(a, b):
    norm_a = np.linalg.norm(a, axis=1, keepdims=True)
    norm_b = np.linalg.norm(b, axis=1, keepdims=True)
    norm_a[norm_a == 0] = 1e-9
    norm_b[norm_b == 0] = 1e-9
    return np.dot(a, b.T) / np.dot(norm_a, norm_b.T)

def calculate_ece(y_true_indices, y_prob, n_bins=10):
    ece = 0.0
    confidences = np.max(y_prob, axis=1)
    predictions = np.argmax(y_prob, axis=1)
    
    for i in range(n_bins):
        bin_lower = i / n_bins
        bin_upper = (i + 1) / n_bins
        
        in_bin = (confidences >= bin_lower) & (confidences < bin_upper)
        prop_in_bin = np.mean(in_bin)
        
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(predictions[in_bin] == y_true_indices[in_bin])
            avg_confidence_in_bin = np.mean(confidences[in_bin])
            ece += prop_in_bin * np.abs(avg_confidence_in_bin - accuracy_in_bin)
            
    return ece

def calculate_brier_score(y_true_onehot, y_prob):
    return np.mean(np.sum((y_prob - y_true_onehot)**2, axis=1))

def calculate_f1_score(y_true, y_pred, labels):
    metrics = {}
    macro_f1 = 0.0
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        metrics[label] = {"precision": precision, "recall": recall, "f1": f1}
        macro_f1 += f1
    macro_f1 /= len(labels) if len(labels) > 0 else 1.0
    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true) if len(y_true) > 0 else 0.0
    return accuracy, macro_f1, metrics

class PyTorchLinearHead(nn.Module):
    def __init__(self, in_features, out_classes):
        super().__init__()
        self.fc = nn.Linear(in_features, out_classes)
    def forward(self, x):
        return self.fc(x)

class TemperatureScaler(nn.Module):
    def __init__(self):
        super().__init__()
        self.temperature = nn.Parameter(torch.ones(1))
    def forward(self, logits):
        return logits / self.temperature

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(os.path.dirname(base_dir))
    build_dir = os.path.join(project_dir, "build-test")
    benchmark_bin = os.path.join(build_dir, "ClassificationBenchmark")
    combined_scan_dir = os.path.join(base_dir, "fixtures", "real_world_combined")
    combined_results_json = os.path.join(base_dir, "results_real_world_combined.json")
    
    # 1. LOAD EMBEDDINGS AND METADATA
    print("--- Loading real-world embeddings ---")
    db_path = os.path.join(base_dir, "fixtures", "cache", "sample_cache.sqlite3")
    manifest_path = os.path.join(base_dir, "real_world_manifest.json")
    
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    path_to_item = {item["filename"]: item for item in manifest}

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT path, category, subcategory, embedding FROM sample_cache WHERE embedding_status = 1 OR embedding_status IS NULL")
    rows = cursor.fetchall()
    
    real_embeddings = []
    real_labels = []
    real_packs = []
    real_vendors = []
    real_filenames = []
    real_confidences = []
    
    ood_embeddings = []
    ood_filenames = []
    
    for row in rows:
        db_path_str = row[0]
        filename = os.path.basename(db_path_str)
        blob = row[3]
        if not blob:
            continue
        embed = np.array(struct.unpack(f"{512}f", blob), dtype=np.float32)
        
        item = path_to_item.get(filename)
        if item:
            if item["expected_category"] == "OOD":
                ood_embeddings.append(embed)
                ood_filenames.append(filename)
            else:
                real_embeddings.append(embed)
                real_labels.append(item["expected_subcategory"])
                real_packs.append(item["source_pack"])
                real_vendors.append(item["source_vendor"])
                real_filenames.append(filename)
                real_confidences.append(item["label_confidence"])
                
    conn.close()
    
    X = np.array(real_embeddings)
    y = np.array(real_labels)
    packs = np.array(real_packs)
    vendors = np.array(real_vendors)
    filenames = np.array(real_filenames)
    confidences = np.array(real_confidences)
    
    classes = sorted(list(set(y)))
    class_to_idx = {c: i for i, c in enumerate(classes)}
    y_idx = np.array([class_to_idx[l] for l in y])
    
    print(f"Loaded {len(X)} real-world samples across {len(classes)} classes.")
    
    # DEDUPLICATION (LEAKAGE CONTROL)
    print("Executing deduplication to verify leakage-free accuracy...")
    sim_matrix = cosine_similarity_np(X, X)
    np.fill_diagonal(sim_matrix, 0.0)
    
    keep_mask = np.ones(len(X), dtype=bool)
    for i in range(len(X)):
        if not keep_mask[i]:
            continue
        duplicates = np.where(sim_matrix[i] > 0.995)[0]
        for d in duplicates:
            keep_mask[d] = False
            
    X_clean = X[keep_mask]
    y_clean = y[keep_mask]
    y_idx_clean = y_idx[keep_mask]
    packs_clean = packs[keep_mask]
    vendors_clean = vendors[keep_mask]
    filenames_clean = filenames[keep_mask]
    
    print(f"Cleaned dataset: {len(X_clean)} samples remaining (removed {len(X) - len(X_clean)} duplicates).")

    # 2. FLAT VS FACTORIZED EXPERIMENTS
    # Define Factorized taxonomy categories
    # Content subcategories mapping
    subcat_to_content = {
        "Kick": "Kick", "Snare": "Snare", "Hi-Hat": "Hi-Hat", "Clap": "Clap", "Percussion": "Percussion",
        "Bass One-Shot": "Bass", "Bass Loop": "Bass", "Synth": "Synth", "Synth Loop": "Synth",
        "Vocal Phrase": "Vocal", "Vocal Loop": "Vocal", "Impact": "Impact", "Riser": "Riser",
        "Foley": "Foley", "FX": "FX", "Atmosphere": "Atmosphere", "Music Loop": "Music"
    }
    subcat_to_temporal = {
        "Kick": "One-Shot", "Snare": "One-Shot", "Hi-Hat": "One-Shot", "Clap": "One-Shot", "Percussion": "One-Shot",
        "Bass One-Shot": "One-Shot", "Bass Loop": "Loop", "Synth": "One-Shot", "Synth Loop": "Loop",
        "Vocal Phrase": "Phrase", "Vocal Loop": "Loop", "Impact": "One-Shot", "Riser": "One-Shot",
        "Foley": "One-Shot", "FX": "One-Shot", "Atmosphere": "One-Shot", "Music Loop": "Loop"
    }
    
    content_labels = sorted(list(set(subcat_to_content.values())))
    temporal_labels = sorted(list(set(subcat_to_temporal.values())))
    
    content_to_idx = {c: i for i, c in enumerate(content_labels)}
    temporal_to_idx = {t: i for i, t in enumerate(temporal_labels)}
    
    y_content = np.array([content_to_idx[subcat_to_content[l]] for l in y_clean])
    y_temporal = np.array([temporal_to_idx[subcat_to_temporal[l]] for l in y_clean])

    # Run cross-validation on clean dataset
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    # Flat Logistic Regression
    flat_accs = []
    flat_macro_f1s = []
    
    # Factorized Logistic Regression
    fact_accs = []
    fact_macro_f1s = []
    
    for train_idx, test_idx in skf.split(X_clean, y_idx_clean):
        X_tr, X_te = X_clean[train_idx], X_clean[test_idx]
        y_tr, y_te = y_idx_clean[train_idx], y_idx_clean[test_idx]
        
        # Flat model
        lr_flat = LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0, max_iter=200)
        lr_flat.fit(X_tr, y_tr)
        pred_flat = lr_flat.predict(X_te)
        acc_f, f1_f, _ = calculate_f1_score(y_te, pred_flat, range(len(classes)))
        flat_accs.append(acc_f)
        flat_macro_f1s.append(f1_f)
        
        # Factorized models
        lr_content = LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0, max_iter=200)
        lr_content.fit(X_tr, y_content[train_idx])
        pred_content = lr_content.predict(X_te)
        
        lr_temporal = LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0, max_iter=200)
        lr_temporal.fit(X_tr, y_temporal[train_idx])
        pred_temporal = lr_temporal.predict(X_te)
        
        # Reconstruct subcategory predictions
        pred_fact = []
        for c_idx, t_idx in zip(pred_content, pred_temporal):
            c_lbl = content_labels[c_idx]
            t_lbl = temporal_labels[t_idx]
            # reconstruct to flat taxonomy subcategory
            if c_lbl == "Bass" and t_lbl == "One-Shot":
                pred_fact.append(class_to_idx["Bass One-Shot"])
            elif c_lbl == "Bass" and t_lbl == "Loop":
                pred_fact.append(class_to_idx["Bass Loop"])
            elif c_lbl == "Synth" and t_lbl == "One-Shot":
                pred_fact.append(class_to_idx["Synth"])
            elif c_lbl == "Synth" and t_lbl == "Loop":
                pred_fact.append(class_to_idx["Synth Loop"])
            elif c_lbl == "Vocal" and t_lbl == "Phrase":
                pred_fact.append(class_to_idx["Vocal Phrase"])
            elif c_lbl == "Vocal" and t_lbl == "Loop":
                pred_fact.append(class_to_idx["Vocal Loop"])
            elif c_lbl == "Music" and t_lbl == "Loop":
                pred_fact.append(class_to_idx["Music Loop"])
            else:
                # Default mapping back
                # E.g. Kick + One-Shot -> Kick
                # If content category matches directly, map it
                match_sub = None
                for sub in classes:
                    if subcat_to_content[sub] == c_lbl:
                        match_sub = sub
                        break
                pred_fact.append(class_to_idx[match_sub] if match_sub else 0)
                
        acc_fa, f1_fa, _ = calculate_f1_score(y_te, pred_fact, range(len(classes)))
        fact_accs.append(acc_fa)
        fact_macro_f1s.append(f1_fa)
        
    print(f"Flat clean CV Accuracy: {np.mean(flat_accs)*100.0:.1f}%, Macro F1: {np.mean(flat_macro_f1s):.3f}")
    print(f"Factorized clean CV Accuracy: {np.mean(fact_accs)*100.0:.1f}%, Macro F1: {np.mean(fact_macro_f1s):.3f}")

    # 3. TEMPERATURE SCALING CALIBRATION
    # Train Logistic Regression on full clean dataset to obtain clean logits
    lr_cal = LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0, max_iter=200)
    lr_cal.fit(X_clean, y_idx_clean)
    logits_full = lr_cal.decision_function(X_clean)
    
    # Train Temperature scaling in PyTorch
    val_targets = torch.tensor(y_idx_clean, dtype=torch.long)
    val_logits = torch.tensor(logits_full, dtype=torch.float32)
    
    scaler = TemperatureScaler()
    optimizer = optim.LBFGS(scaler.parameters(), lr=0.01, max_iter=50)
    
    def eval_loss():
        optimizer.zero_grad()
        loss = nn.CrossEntropyLoss()(scaler(val_logits), val_targets)
        loss.backward()
        return loss
        
    optimizer.step(eval_loss)
    T = scaler.temperature.item()
    print(f"Optimized Temperature T: {T:.4f}")
    
    # Evaluate calibration before/after
    # Unscaled probabilities
    probs_before = nn.Softmax(dim=1)(val_logits).numpy()
    # Scaled probabilities
    probs_after = nn.Softmax(dim=1)(val_logits / T).numpy()
    
    y_true_onehot = np.zeros_like(probs_before)
    y_true_onehot[np.arange(len(y_idx_clean)), y_idx_clean] = 1.0
    
    ece_before = calculate_ece(y_idx_clean, probs_before)
    ece_after = calculate_ece(y_idx_clean, probs_after)
    brier_before = calculate_brier_score(y_true_onehot, probs_before)
    brier_after = calculate_brier_score(y_true_onehot, probs_after)
    
    print(f"ECE Before: {ece_before:.4f}, ECE After: {ece_after:.4f}")
    print(f"Brier Before: {brier_before:.4f}, Brier After: {brier_after:.4f}")

    # 4. OOD AUROC ANALYSIS
    # Get predictions on OOD embeddings
    OOD = np.array(ood_embeddings)
    logits_ood = lr_cal.decision_function(OOD)
    probs_ood = nn.Softmax(dim=1)(torch.tensor(logits_ood, dtype=torch.float32) / T).numpy()
    
    # Max Softmax Probability (MSP)
    msp_in = np.max(probs_after, axis=1)
    msp_ood = np.max(probs_ood, axis=1)
    
    # Softmax Entropy
    ent_in = -np.sum(probs_after * np.log(probs_after + 1e-9), axis=1)
    ent_ood = -np.sum(probs_ood * np.log(probs_ood + 1e-9), axis=1)
    
    # Margin (top-1 - top-2)
    sorted_in = np.sort(probs_after, axis=1)
    margin_in = sorted_in[:, -1] - sorted_in[:, -2]
    sorted_ood = np.sort(probs_ood, axis=1)
    margin_ood = sorted_ood[:, -1] - sorted_ood[:, -2]
    
    # We want IN-distribution to have high scores, OOD to have low scores.
    # For entropy, OOD should have HIGH entropy, IN-distribution LOW entropy (so we flip entropy for AUROC)
    auroc_msp = roc_auc_score(np.concatenate([np.ones_like(msp_in), np.zeros_like(msp_ood)]), np.concatenate([msp_in, msp_ood]))
    auroc_ent = roc_auc_score(np.concatenate([np.ones_like(ent_in), np.zeros_like(ent_ood)]), np.concatenate([-ent_in, -ent_ood]))
    auroc_margin = roc_auc_score(np.concatenate([np.ones_like(margin_in), np.zeros_like(margin_ood)]), np.concatenate([margin_in, margin_ood]))
    
    print(f"OOD Rejection AUROC - MSP: {auroc_msp:.4f}, Entropy: {auroc_ent:.4f}, Margin: {auroc_margin:.4f}")

    # 5. CONSTRXPR WEIGHT EXPORT
    # Train final Logistic Regression on clean dataset to export
    lr_final = LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0, max_iter=300)
    lr_final.fit(X_clean, y_idx_clean)
    
    weights = lr_final.coef_ # shape (17, 512)
    biases = lr_final.intercept_ # shape (17,)
    
    weight_header_path = os.path.join(project_dir, "Source", "AcousticClassifierWeights.h")
    print(f"Exporting model weights to C++ header: {weight_header_path}")
    
    # Generate C++ arrays
    weight_str_list = []
    for cls_w in weights:
        w_vals = ", ".join(f"{w}f" for w in cls_w)
        weight_str_list.append(f"    {{ {w_vals} }}")
        
    weights_cpp = ",\n".join(weight_str_list)
    biases_cpp = ", ".join(f"{b}f" for b in biases)
    
    # Build class name initializer list
    classes_cpp = ", ".join(f"\"{c}\"" for c in classes)
    
    with open(weight_header_path, "w") as f:
        f.write(f"""#pragma once

// Automated weights export for Nite DSP SLO AcousticClassifier V2.
// Generated from training on deduplicated real-world mock dataset.
// DO NOT EDIT MANUALLY.

namespace AcousticWeights
{{
    constexpr int modelVersion = 2;
    constexpr int embeddingVersion = 1;
    constexpr int taxonomyVersion = 1;
    constexpr int numClasses = {len(classes)};
    constexpr int embeddingDim = 512;
    constexpr float temperature = {T}f;

    const char* const classNames[numClasses] = {{ {classes_cpp} }};

    constexpr float weights[numClasses][embeddingDim] = {{
{weights_cpp}
    }};

    constexpr float biases[numClasses] = {{ {biases_cpp} }};
}}
""")

    # 6. PYTHON/C++ NUMERICAL PARITY DATASET
    # Select 10 reference embeddings
    parity_list = []
    # Save first 10 files
    for idx in range(10):
        embed = X_clean[idx]
        expected_logits = np.dot(weights, embed) + biases
        expected_logits_t = expected_logits / T
        # Softmax
        exp_logits_t_exp = np.exp(expected_logits_t - np.max(expected_logits_t))
        expected_probs = exp_logits_t_exp / np.sum(exp_logits_t_exp)
        
        # Margin
        sorted_probs = np.sort(expected_probs)
        margin = float(sorted_probs[-1] - sorted_probs[-2])
        
        parity_list.append({
            "filename": filenames_clean[idx],
            "embedding": [float(v) for v in embed],
            "expected_logits": [float(v) for v in expected_logits],
            "expected_probs": [float(v) for v in expected_probs],
            "predicted_subcategory": classes[np.argmax(expected_probs)],
            "probability": float(np.max(expected_probs)),
            "margin": margin
        })
        
    parity_json_path = os.path.join(base_dir, "parity_references.json")
    with open(parity_json_path, "w") as f:
        json.dump(parity_list, f, indent=4)
    print(f"Parity references exported to: {parity_json_path}")
    
    # 7. CLEAN COMBINED SCAN FOLDERS
    shutil.rmtree(combined_scan_dir, ignore_errors=True)
    if os.path.exists(combined_results_json):
        os.remove(combined_results_json)

if __name__ == "__main__":
    main()
