#!/usr/bin/env bash
set -euo pipefail

# Realtime regression gate. Defaults are intentionally low-mode/live-path focused:
# cacheable chords, RT-safe master/reverb, and no over-budget profiled bars.
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

SECONDS_TO_RUN="${RT_GATE_SECONDS:-8}"
PERFORMANCE="${RT_GATE_PERFORMANCE:-low}"
OUTPUT="${RT_GATE_OUTPUT:-.cache/rt_performance_gate.json}"
MIN_PROFILED_BARS="${RT_GATE_MIN_PROFILED_BARS:-1}"
WARMUP_PROFILED_BARS="${RT_GATE_WARMUP_PROFILED_BARS:-1}"
MAX_RENDER_RATIO="${RT_GATE_MAX_RENDER_RATIO:-0.85}"
MAX_OVER_BUDGET_BARS="${RT_GATE_MAX_OVER_BUDGET_BARS:-0}"
MAX_COLD_START_MS="${RT_GATE_MAX_COLD_START_MS:-0}"

cd "${ROOT_DIR}"
exec "${PYTHON_BIN}" tools/benchmark_realtime_audio.py \
  --seconds "${SECONDS_TO_RUN}" \
  --performance "${PERFORMANCE}" \
  --output "${OUTPUT}" \
  --min-profiled-bars "${MIN_PROFILED_BARS}" \
  --gate-warmup-bars "${WARMUP_PROFILED_BARS}" \
  --max-render-ratio "${MAX_RENDER_RATIO}" \
  --max-over-budget-bars "${MAX_OVER_BUDGET_BARS}" \
  --max-cold-start-ms "${MAX_COLD_START_MS}"
