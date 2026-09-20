#!/usr/bin/env bash
set -euo pipefail

# Master bus DSP regression gate: return FX, master EQ, limiter, soft clip,
# and realtime/offline true-peak behavior.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
export PYTHONFAULTHANDLER="${PYTHONFAULTHANDLER:-1}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  PYTHON_BIN=python
fi

FRAMES="${MASTER_BUS_DSP_GATE_FRAMES:-512,1024,2048}"
MODES="${MASTER_BUS_DSP_GATE_MODES:-dry,returns_safe,limiter_rt,eq,full_rt,full_offline}"
ITERATIONS="${MASTER_BUS_DSP_GATE_ITERATIONS:-120}"
WARMUP="${MASTER_BUS_DSP_GATE_WARMUP:-12}"
OUTPUT="${MASTER_BUS_DSP_GATE_OUTPUT:-.cache/master_bus_dsp_gate.json}"
MAX_MEAN_MS="${MASTER_BUS_DSP_GATE_MAX_MEAN_MS:-16.0}"
MAX_P95_MS="${MASTER_BUS_DSP_GATE_MAX_P95_MS:-20.0}"
MAX_REALTIME_RATIO="${MASTER_BUS_DSP_GATE_MAX_REALTIME_RATIO:-0.35}"

cd "${ROOT_DIR}"
exec "${PYTHON_BIN}" tools/benchmark_master_bus_dsp.py \
  --frames "${FRAMES}" \
  --modes "${MODES}" \
  --iterations "${ITERATIONS}" \
  --warmup "${WARMUP}" \
  --output "${OUTPUT}" \
  --max-mean-ms "${MAX_MEAN_MS}" \
  --max-p95-ms "${MAX_P95_MS}" \
  --max-realtime-ratio "${MAX_REALTIME_RATIO}"
