#!/usr/bin/env bash
# Periodic batch job: eval gate → Markov retrain → optional logit-residual fit.
# Usage: scripts/melody_periodic_retrain.sh [JSONL_PATH]
# Env: OUT_PKL (default training_data/active_models/melody_markov.pkl), OUT_NPZ, SKIP_LOGIT=1 to skip train_melody_logit_residual.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JSONL="${1:-$ROOT/.cache/live_melody_training.jsonl}"
OUT_PKL="${OUT_PKL:-$ROOT/training_data/active_models/melody_markov.pkl}"
OUT_NPZ="${OUT_NPZ:-$ROOT/training_data/active_models/melody_logit_residual.npz}"
python "$ROOT/scripts/melody_eval_gate.py" "$JSONL"
python "$ROOT/scripts/melody_jsonl_retrain.py" "$JSONL" -o "$OUT_PKL"
if [[ "${SKIP_LOGIT:-0}" != "1" ]]; then
  python "$ROOT/scripts/train_melody_logit_residual.py" "$JSONL" -o "$OUT_NPZ"
fi
