#!/usr/bin/env bash
# Frozen A/B tag for joint melody + harmony calibration (do not reuse for unrelated runs).
# Quick iteration (fewer sections):
#   PER_EMOTION=2 BARS=8 bash run_v012e_joint_tune_dataset_and_diagnostics.sh
# Subset of emotions (faster dry-run):
#   EMOTIONS="admiration neutral joy" PER_EMOTION=2 bash run_v012e_joint_tune_dataset_and_diagnostics.sh
# Full run (slower, default 32/section for all emotions):
#   bash run_v012e_joint_tune_dataset_and_diagnostics.sh
# A/B: use a new tag so outputs are not overwritten (timestamped example):
#   TAG="v012f_joint_$(date -u +%Y%m%d_%H%M%S)" bash run_v012e_joint_tune_dataset_and_diagnostics.sh
# Cinematic / sparse melody aesthetic (Einaudi– / score–style; see `cinematic_minimal` in data/sample_style_profiles.py):
#   STYLE=cinematic_minimal TAG=... bash run_v012e_joint_tune_dataset_and_diagnostics.sh
# Main.py listening preset that matches this style (ballad + ambient pack; see .audiogen/presets/cinematic_joint.json):
#   META_PRESET=cinematic_joint TAG=... bash run_v012e_joint_tune_dataset_and_diagnostics.sh
# By default the JSONL generator uses --disable-retrained-markov so the dataset is not shaped by an
# existing melody Markov pickle (good before a fresh retrain). To allow the loaded retrained .pkl:
#   USE_RETRAINED_MARKOV=1 TAG=... bash run_v012e_joint_tune_dataset_and_diagnostics.sh
# Full canonical rebuild (wipe old live_melody first if you want only this corpus):
#   rm -rf artifacts/datasets/live_melody/* && STYLE=cinematic_minimal TAG=primary bash run_v012e_joint_tune_dataset_and_diagnostics.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Canonicalized wrapper:
# Route this legacy script through scripts/run_training_pipeline.py so
# dataset generation, diagnostics, eval gating, and manifests are consistent.

# Dataset folder name under artifacts/datasets/live_melody/<TAG>/
: "${TAG:=v012e_joint_tune}"
: "${PER_EMOTION:=32}"
: "${DATASET_JOBS:=1}"
: "${BARS:=16}"
: "${ROLE_CYCLE:=6}"
# Optional space-separated list; when empty, all emotions.
: "${EMOTIONS:=}"
: "${STYLE:=}"
: "${META_PRESET:=}"
: "${USE_RETRAINED_MARKOV:=0}"

# Use existing venv if present.
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

export PYTHONUNBUFFERED=1

PIPELINE_ARGS=(
  --version "${TAG}"
  --per-emotion "${PER_EMOTION}"
  --dataset-jobs "${DATASET_JOBS}"
  --bars "${BARS}"
  --role-cycle-length "${ROLE_CYCLE}"
  --quality-mode
  --run-diagnostics
  --write-run-meta
  --skip-train
  --skip-promote
)

if [[ -n "${STYLE}" ]]; then
  PIPELINE_ARGS+=(--style "${STYLE}")
fi

case "${USE_RETRAINED_MARKOV}" in
  1 | true | yes | on | ON)
    PIPELINE_ARGS+=(--use-retrained-markov)
    ;;
  *)
    ;;
esac

if [[ -n "${EMOTIONS}" ]]; then
  # shellcheck disable=SC2206
  EMOTIONS_ARR=($EMOTIONS)
  PIPELINE_ARGS+=(--emotions "${EMOTIONS_ARR[@]}")
fi

# NOTE:
# META_PRESET is runtime-listening context for main.py and is not consumed by
# offline dataset generation. Kept as an env var for caller compatibility.
if [[ -n "${META_PRESET}" ]]; then
  echo "META_PRESET=${META_PRESET} (info: not used by run_training_pipeline dataset flow)"
fi

echo "Running canonical dataset+diagnostics pipeline for tag=${TAG}"
python3 -u scripts/run_training_pipeline.py "${PIPELINE_ARGS[@]}"

OUT_DIR="artifacts/datasets/live_melody/${TAG}"
OUT_JSONL="${OUT_DIR}/live_melody_training.jsonl"
RUN_META="${OUT_DIR}/run_meta.txt"
DIAG_JSON="artifacts/reports/${TAG}/melody_emotion_diagnostics.json"
GATE_JSON="artifacts/reports/${TAG}/melody_jsonl_eval.json"
MANIFEST_JSON="artifacts/manifests/${TAG}.json"

echo ""
echo "Done."
echo "JSONL: ${OUT_JSONL}"
echo "Melody diagnostics JSON: ${DIAG_JSON}"
echo "Eval gate report: ${GATE_JSON}"
echo "Run meta: ${RUN_META}"
echo "Manifest: ${MANIFEST_JSON}"
