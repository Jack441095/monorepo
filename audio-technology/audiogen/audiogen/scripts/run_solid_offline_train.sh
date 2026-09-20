#!/usr/bin/env bash
# Solid offline training: eval gate (metadata + diversity) → Markov + logit + emotion
# dataset export/validation → optional promotion to training_data/active_models.
#
# Prerequisite: final melody JSONL at JSONL, or a sibling *.jsonl.raw.jsonl from a partial run
# (this script will run --split-existing-raw to produce the kept file). For a full build:
#   TAG=primary STYLE=cinematic_minimal bash run_v012e_joint_tune_dataset_and_diagnostics.sh
#
# Examples:
#   bash run_solid_offline_train.sh
#   JSONL=artifacts/datasets/live_melody/primary/live_melody_training.jsonl bash run_solid_offline_train.sh
#   TRAIN_TAG=my_run PROMOTE=0 bash run_solid_offline_train.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

: "${JSONL:=artifacts/datasets/live_melody/primary/live_melody_training.jsonl}"
# Version this run; default is timestamped so previous artifacts are not overwritten.
: "${TRAIN_TAG:=primary_train_$(date -u +%Y%m%d_%H%M%S)}"
: "${OFFLINE_TRAIN_DIR:=artifacts/runs/offline_training}"
# Set PROMOTE=0 to only train and leave files under OFFLINE_TRAIN_DIR/TRAIN_TAG.
: "${PROMOTE:=1}"
# Set DRY_RUN_PROMOTE=1 to print what promotion would do (no copy).
: "${DRY_RUN_PROMOTE:=0}"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

# Final export is live_melody_training.jsonl; an interrupted dataset run may leave only
# live_melody_training.jsonl.raw.jsonl. Split that into the kept JSONL (same as generate script's last step).
RAW_JSONL="${JSONL}.raw.jsonl"
if [[ ! -f "${JSONL}" ]]; then
  if [[ -f "${RAW_JSONL}" ]]; then
    echo "Found raw JSONL (interrupted or generate-only run). Splitting → ${JSONL}"
    python3 -u scripts/generate_live_melody_training_jsonl.py \
      --out "${JSONL}" \
      --split-existing-raw \
      --dedup-kept
  else
    echo "Missing training JSONL: ${JSONL}" >&2
    echo "No raw file at ${RAW_JSONL} to finalize. Build a dataset, e.g.:" >&2
    echo "  TAG=primary STYLE=cinematic_minimal bash run_v012e_joint_tune_dataset_and_diagnostics.sh" >&2
    echo "If you only have a .raw.jsonl, finalize manually with:" >&2
    echo "  python3 scripts/generate_live_melody_training_jsonl.py --out ${JSONL} --split-existing-raw --dedup-kept" >&2
    exit 2
  fi
fi
if [[ ! -f "${JSONL}" ]]; then
  echo "Still missing after split: ${JSONL}" >&2
  exit 2
fi

RUN_DIR="${OFFLINE_TRAIN_DIR}/${TRAIN_TAG}"

export PYTHONUNBUFFERED=1

echo "JSONL:     ${JSONL}"
echo "Train tag: ${TRAIN_TAG}"
echo "Run dir:   ${RUN_DIR}"
echo ""

python3 -u main.py --offline-train all \
  --offline-train-jsonl "${JSONL}" \
  --offline-train-tag "${TRAIN_TAG}" \
  --offline-train-dir "${OFFLINE_TRAIN_DIR}" \
  --offline-train-require-metadata \
  --offline-train-min-emotions 4 \
  --offline-train-min-section-roles 3 \
  --offline-train-max-emotion-share 0.45 \
  --offline-train-dedup

if [[ "${PROMOTE}" != "1" && "${PROMOTE}" != "true" && "${PROMOTE}" != "yes" ]]; then
  echo ""
  echo "Skipping promotion (PROMOTE=${PROMOTE}). Artifacts: ${RUN_DIR}"
  echo "To promote later:"
  echo "  python3 main.py --offline-promote-run ${RUN_DIR} --offline-promote-kind all --offline-promote-dir training_data/active_models"
  exit 0
fi

echo ""
echo "Promoting → training_data/active_models"
# Do not append an empty array to argv — bash may pass a stray "" and argparse errors with "unrecognized arguments: ".
if [[ "${DRY_RUN_PROMOTE}" == "1" || "${DRY_RUN_PROMOTE}" == "true" || "${DRY_RUN_PROMOTE}" == "yes" ]]; then
  python3 -u main.py --offline-promote-run "${RUN_DIR}" --offline-promote-kind all --offline-promote-dir training_data/active_models --offline-promote-dry-run
else
  python3 -u main.py --offline-promote-run "${RUN_DIR}" --offline-promote-kind all --offline-promote-dir training_data/active_models
fi

echo ""
echo "Done. Active models: training_data/active_models/"
echo "Listen with retrained Markov + logit, e.g.:"
echo "  python3 main.py --melody-retrained-markov --melody-retrained-markov-path training_data/active_models/melody_markov.pkl \\"
echo "    --melody-neural-logit-residual --melody-neural-logit-residual-path training_data/active_models/melody_logit_residual.npz"
