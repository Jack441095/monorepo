#!/usr/bin/env bash
# Retrain V4 Hybrid classifier with C++-matched DSP features.
# Run from the classification_benchmark directory.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Step 1/3: Re-extract C++-matched DSP features ==="
python3 build_hybrid_v4_dataset.py

echo ""
echo "=== Step 2/3: Prepare X/Y numpy arrays ==="
python3 -c "
import numpy as np
d = np.load('slo_all_packs_hybrid_v4.npz', allow_pickle=True)
X = d['embeddings'].astype(np.float32)  # (N, 520)
y = d['labels'].astype(np.int64)
print(f'X shape: {X.shape}, y shape: {y.shape}')
np.save('hybrid_x.npy', X)
np.save('hybrid_y.npy', y)
print('Saved hybrid_x.npy and hybrid_y.npy')
"

echo ""
echo "=== Step 3/3: Train V4 classifier (90 epochs/fold, 130 final fit) ==="
python3 train_gpu_classifier_v4.py

echo ""
echo "=== Pipeline complete ==="
echo "Checkpoint: slo_classifier_v4_hybrid.pt"
echo "Compare OOF accuracy against V3 baseline (70.03%)"
