#!/usr/bin/env bash
set -euo pipefail

# Mixer strip DSP regression gate. Thresholds include practical headroom over
# the current optimized channel EQ/filter path so normal machine jitter should
# not fail the gate, but large regressions will.
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

FRAMES="${MIXER_DSP_GATE_FRAMES:-256,512,1024,2048}"
MODES="${MIXER_DSP_GATE_MODES:-none,filters,eq,eq_filters}"
ITERATIONS="${MIXER_DSP_GATE_ITERATIONS:-200}"
WARMUP="${MIXER_DSP_GATE_WARMUP:-20}"
CHANNELS="${MIXER_DSP_GATE_CHANNELS:-7}"
OUTPUT="${MIXER_DSP_GATE_OUTPUT:-.cache/mixer_dsp_gate.json}"
MAX_MEAN_MS="${MIXER_DSP_GATE_MAX_MEAN_MS:-1.10}"
MAX_P95_MS="${MIXER_DSP_GATE_MAX_P95_MS:-1.50}"
MAX_REALTIME_RATIO="${MIXER_DSP_GATE_MAX_REALTIME_RATIO:-0.10}"

cd "${ROOT_DIR}"
exec "${PYTHON_BIN}" tools/benchmark_mixer_dsp.py \
  --channels "${CHANNELS}" \
  --frames "${FRAMES}" \
  --modes "${MODES}" \
  --iterations "${ITERATIONS}" \
  --warmup "${WARMUP}" \
  --sends \
  --output "${OUTPUT}" \
  --max-mean-ms "${MAX_MEAN_MS}" \
  --max-p95-ms "${MAX_P95_MS}" \
  --max-realtime-ratio "${MAX_REALTIME_RATIO}"
