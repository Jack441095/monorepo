#!/usr/bin/env bash
set -euo pipefail

# Whole-system performance benchmark (offline + realtime + optional DSP).
# Local-only by default; thresholds can be overridden via SYS_BENCH_* env vars.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
export PYTHONFAULTHANDLER="${PYTHONFAULTHANDLER:-1}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_pick_python() {
  local cand
  for cand in \
    "${ROOT_DIR}/.venv/bin/python" \
    "${ROOT_DIR}/.venv/bin/python3" \
    python3 \
    python; do
    if [ -z "${cand}" ] || ! command -v "${cand}" >/dev/null 2>&1; then
      continue
    fi
    if "${cand}" -c "import numpy, scipy" >/dev/null 2>&1; then
      echo "${cand}"
      return 0
    fi
  done
  return 1
}

if ! PYTHON_BIN="$(_pick_python)"; then
  echo "No Python with numpy+scipy found. Install deps, e.g.:" >&2
  echo "  pip3 install -e '.[dev]'   # or: pip3 install numpy scipy sounddevice numba" >&2
  exit 1
fi

OUTPUT_DIR="${SYS_BENCH_OUTPUT_DIR:-.cache/system_performance_benchmark}"
RT_SECONDS="${SYS_BENCH_RT_SECONDS:-8}"
PERFORMANCE="${SYS_BENCH_PERFORMANCE:-low}"
EMOTION="${SYS_BENCH_EMOTION:-neutral}"
ROOT_MIDI="${SYS_BENCH_ROOT_MIDI:-60}"
SEED="${SYS_BENCH_SEED:-0}"

cd "${ROOT_DIR}"
exec "${PYTHON_BIN}" tools/system_performance_benchmark.py \
  --output-dir "${OUTPUT_DIR}" \
  --performance "${PERFORMANCE}" \
  --rt-seconds "${RT_SECONDS}" \
  --emotion "${EMOTION}" \
  --root "${ROOT_MIDI}" \
  --seed "${SEED}" \
  --gate

