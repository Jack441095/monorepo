#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRODUCT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

cd "${PRODUCT_ROOT}"
export PYTHONPATH="${PRODUCT_ROOT}/apps/backend/src:${PRODUCT_ROOT}/tooling:${PYTHONPATH:-}"

echo "[1/8] Verifying canonical compatibility links"
test -f source/server.py
test -f vst3-plugin/CMakeLists.txt

echo "[2/8] Compiling Python sources"
"${PYTHON_BIN}" -m compileall -q apps/backend/src packages tooling/scripts chat automix

echo "[3/8] Running the canonical backend suite"
"${PYTHON_BIN}" -m pytest -q apps/backend/src/kenn/tests

echo "[4/8] Running the scoped chat suite"
"${PYTHON_BIN}" -m pytest -q chat/tests

echo "[5/8] Running Mix Review"
"${PYTHON_BIN}" -m pytest -q packages/mix-review

echo "[6/8] Running the product AutoMix boundary"
"${PYTHON_BIN}" -m pytest -q automix/tests

echo "[7/8] Running the package AutoMix boundary"
"${PYTHON_BIN}" -m pytest -q packages/automix/tests

echo "[8/8] Validating durable research receipts"
"${PYTHON_BIN}" - <<'PY'
import json
from pathlib import Path

root = Path("docs/research/results")
paths = sorted(root.glob("*.json"))
if not paths:
    raise SystemExit("no durable research receipts found")
for path in paths:
    with path.open("r", encoding="utf-8") as handle:
        json.load(handle)
print(f"validated {len(paths)} JSON receipts")
PY

echo "KENN core verification passed"
