#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

JSONL="${1:-artifacts/datasets/live_melody/primary/live_melody_training.jsonl}"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

echo "Joint fast checks on: ${JSONL}"
echo ""

# Omit --emotions to score every label present in the file (any filtered subset
# that does not match the dataset yields rows_used=0 and looks broken).
python3 scripts/chord_emotion_diagnostics_fast.py "$JSONL" \
  --max-rows-per-emotion 80 \
  --top 32

echo ""
python3 scripts/joint_composition_diagnostics_fast.py "$JSONL" \
  --max-rows-per-emotion 80 \
  --top 32
