#!/usr/bin/env bash
set -euo pipefail

# Work around intermittent native segfaults during pytest runs when BLAS backends
# use multi-threading (macOS Accelerate / OpenBLAS / MKL). Pin to 1 thread.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"

# Optional: enable Python-level stack dumps on fatal errors.
export PYTHONFAULTHANDLER="${PYTHONFAULTHANDLER:-1}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  PYTHON_BIN=python
fi

"${PYTHON_BIN}" -m ruff check . --select F821,F601,E9
exec "${PYTHON_BIN}" -m pytest "$@"
