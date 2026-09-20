#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/promote_flow.sh --run-dir <offline-run-dir> [options]

Options:
  --run-dir <path>                Required. Offline run dir containing *_offline_training_manifest.json
  --kind <markov|logit|all>       Artifact kind (default: all)
  --active-dir <path>             Active models dir (default: training_data/active_models)
  --flow <full|candidate|canary|active>
                                  full: stage candidate -> canary -> active (default)
                                  candidate/canary/active: stage only that lane
  --activate-stage <candidate|canary|active>
                                  Optional extra activation step (copy staged lane into runtime root filenames)
  --dry-run                       Print plans only, no writes
  -h, --help                      Show this help
EOF
}

RUN_DIR=""
KIND="all"
ACTIVE_DIR="training_data/active_models"
FLOW="full"
ACTIVATE_STAGE=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir)
      RUN_DIR="${2:-}"
      shift 2
      ;;
    --kind)
      KIND="${2:-}"
      shift 2
      ;;
    --active-dir)
      ACTIVE_DIR="${2:-}"
      shift 2
      ;;
    --flow)
      FLOW="${2:-}"
      shift 2
      ;;
    --activate-stage)
      ACTIVATE_STAGE="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${RUN_DIR}" ]]; then
  echo "--run-dir is required." >&2
  usage
  exit 2
fi

if [[ "${KIND}" != "markov" && "${KIND}" != "logit" && "${KIND}" != "all" ]]; then
  echo "Invalid --kind: ${KIND}" >&2
  exit 2
fi

if [[ "${FLOW}" != "full" && "${FLOW}" != "candidate" && "${FLOW}" != "canary" && "${FLOW}" != "active" ]]; then
  echo "Invalid --flow: ${FLOW}" >&2
  exit 2
fi

if [[ -n "${ACTIVATE_STAGE}" && "${ACTIVATE_STAGE}" != "candidate" && "${ACTIVATE_STAGE}" != "canary" && "${ACTIVATE_STAGE}" != "active" ]]; then
  echo "Invalid --activate-stage: ${ACTIVATE_STAGE}" >&2
  exit 2
fi

DRY_FLAG=()
if [[ "${DRY_RUN}" -eq 1 ]]; then
  DRY_FLAG+=(--dry-run)
fi

promote_stage() {
  local stage="$1"
  echo "Staging ${stage} (${KIND}) from ${RUN_DIR}"
  python3 "scripts/promote_training_artifact.py" \
    "${RUN_DIR}" \
    --kind "${KIND}" \
    --stage "${stage}" \
    --active-dir "${ACTIVE_DIR}" \
    "${DRY_FLAG[@]}"
}

case "${FLOW}" in
  full)
    promote_stage candidate
    promote_stage canary
    promote_stage active
    ;;
  candidate|canary|active)
    promote_stage "${FLOW}"
    ;;
esac

if [[ -n "${ACTIVATE_STAGE}" ]]; then
  echo "Activating stage ${ACTIVATE_STAGE} into runtime root files"
  python3 "scripts/promote_training_artifact.py" \
    --activate-stage "${ACTIVATE_STAGE}" \
    --active-dir "${ACTIVE_DIR}" \
    "${DRY_FLAG[@]}"
fi

echo "Promotion flow complete."
