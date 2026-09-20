#!/usr/bin/env bash
set -euo pipefail

# Arranged-song quality audit (symbolic; no sample WAVs required).
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
export NUMBA_NUM_THREADS="${NUMBA_NUM_THREADS:-1}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  PYTHON_BIN=python
fi

OUTPUT_DIR="${SONG_QA_OUTPUT_DIR:-artifacts/quality_audits}"
EMOTIONS="${SONG_QA_EMOTIONS:-neutral,sadness,joy,anger,relief}"
SEEDS="${SONG_QA_SEEDS:-101,202}"
FORMS="${SONG_QA_FORMS:-default,ambient}"
PERFORMANCE="${SONG_QA_PERFORMANCE:-low}"
FAIL_UNDER="${SONG_QA_FAIL_UNDER:-0}"

cd "${ROOT_DIR}"
exec "${PYTHON_BIN}" tools/song_quality_audit.py \
  --output-dir "${OUTPUT_DIR}" \
  --emotions "${EMOTIONS}" \
  --seeds "${SEEDS}" \
  --forms "${FORMS}" \
  --performance "${PERFORMANCE}" \
  --fail-under-score "${FAIL_UNDER}" \
  "$@"
