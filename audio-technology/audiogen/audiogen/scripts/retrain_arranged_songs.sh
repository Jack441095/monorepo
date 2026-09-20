#!/usr/bin/env bash
# End-to-end "solid retrain" using *arranged full songs* (multi-section context),
# while still training on the existing JOINT per-section JSONL schema.
#
# Usage:
#   bash scripts/retrain_arranged_songs.sh
#
# Common overrides:
#   TAG=v003 FORM=pop_ext STYLE=cinematic_minimal SONGS_PER_EMOTION=8 BARS_PER_SECTION=16 MAX_BARS=96 QUALITY=1 bash scripts/retrain_arranged_songs.sh
#   TAG=v003 PROMOTE=0 bash scripts/retrain_arranged_songs.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

: "${TAG:=v$(date -u +%Y%m%d_%H%M%S)}"
: "${STYLE:=}"
: "${FORM:=default}"                 # default|pop|pop_ext|rondo|ballad|wave|anthem|ambient
: "${SONGS_PER_EMOTION:=6}"
: "${BARS_PER_SECTION:=16}"
: "${MAX_BARS:=96}"
: "${TARGET_SECONDS:=150}"
: "${ACCEPT_THRESHOLD:=0.0}"
: "${DEDUP:=1}"
: "${QUALITY:=1}"
: "${QUALITY_K:=6}"
: "${PROMOTE:=1}"
: "${DRY_RUN_PROMOTE:=0}"

DATASET_DIR="artifacts/datasets/arranged_joint/${TAG}"
JSONL="${DATASET_DIR}/arranged_joint_training.jsonl"
REJECTS="${DATASET_DIR}/arranged_joint_rejects.jsonl"
TRAIN_DIR="artifacts/runs/offline_training"
RUN_DIR="${TRAIN_DIR}/${TAG}"

mkdir -p "${DATASET_DIR}"
mkdir -p "${TRAIN_DIR}"

echo "=== Arranged-song solid retrain ==="
echo "Tag:              ${TAG}"
echo "Form:             ${FORM}"
echo "Style:            ${STYLE:-<none>}"
echo "Songs/emotion:    ${SONGS_PER_EMOTION}"
echo "Bars/section:     ${BARS_PER_SECTION}"
echo "Max bars (forms): ${MAX_BARS}"
echo "JSONL:            ${JSONL}"
echo "Promote:          ${PROMOTE} (dry-run=${DRY_RUN_PROMOTE})"
echo ""

echo "== 1) Generate arranged-song joint JSONL (per-section rows) =="
GEN_ARGS=(
  --out "${JSONL}"
  --out-rejects "${REJECTS}"
  --accept-threshold "${ACCEPT_THRESHOLD}"
  --songs-per-emotion "${SONGS_PER_EMOTION}"
  --bars-per-section "${BARS_PER_SECTION}"
  --max-bars "${MAX_BARS}"
  --target-seconds "${TARGET_SECONDS}"
  --form "${FORM}"
  --disable-retrained-markov
)
if [[ "${DEDUP}" == "1" || "${DEDUP}" == "true" || "${DEDUP}" == "yes" ]]; then
  GEN_ARGS+=(--dedup-kept)
fi
if [[ -n "${STYLE}" ]]; then
  GEN_ARGS+=(--style "${STYLE}")
fi
if [[ "${QUALITY}" == "1" || "${QUALITY}" == "true" || "${QUALITY}" == "yes" ]]; then
  GEN_ARGS+=(--quality-mode --quality-k-samples "${QUALITY_K}")
fi

python3 -u scripts/generate_arranged_joint_training_jsonl.py "${GEN_ARGS[@]}"

if [[ ! -f "${JSONL}" ]]; then
  echo "ERROR: training JSONL not created: ${JSONL}" >&2
  exit 2
fi

echo ""
echo "== 2) Offline training (eval gate + markov + chord + logit + dataset validation) =="
python3 -u main.py --offline-train all \
  --offline-train-jsonl "${JSONL}" \
  --offline-train-tag "${TAG}" \
  --offline-train-dir "${TRAIN_DIR}" \
  --offline-train-require-metadata \
  --offline-train-min-emotions 4 \
  --offline-train-min-section-roles 3 \
  --offline-train-max-emotion-share 0.45 \
  --offline-train-dedup

if [[ "${PROMOTE}" != "1" && "${PROMOTE}" != "true" && "${PROMOTE}" != "yes" ]]; then
  echo ""
  echo "Skipping promotion (PROMOTE=${PROMOTE}). Artifacts are under: ${RUN_DIR}"
  exit 0
fi

echo ""
echo "== 3) Promote to training_data/active_models =="
if [[ "${DRY_RUN_PROMOTE}" == "1" || "${DRY_RUN_PROMOTE}" == "true" || "${DRY_RUN_PROMOTE}" == "yes" ]]; then
  python3 -u main.py --offline-promote-run "${RUN_DIR}" --offline-promote-kind all --offline-promote-dir training_data/active_models --offline-promote-dry-run
else
  python3 -u main.py --offline-promote-run "${RUN_DIR}" --offline-promote-kind all --offline-promote-dir training_data/active_models
fi

echo ""
echo "Done."
echo "Active models: training_data/active_models/"

