#!/usr/bin/env bash
set -euo pipefail

# KENN Public Beta Continuous Integration & Release Verification Script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/apps/backend/src:$REPO_ROOT/packages/chat:$REPO_ROOT/packages/mix-review/core:${PYTHONPATH:-}"

echo "================================================================================"
echo " 🛠️  KENN Public Beta CI & Release Verification Runner"
echo "================================================================================"

# 1. Python Syntax Compilation Check
echo "[1/6] Checking Python syntax compilation across repository..."
python3 -m compileall -q apps/backend/src packages tooling/scripts

# 2. Vector Index Build Verification
echo "[2/6] Verifying vector index build..."
python3 apps/backend/src/kenn/main.py build

# 3. Comprehensive Pytest Test Suite
echo "[3/6] Running Pytest test suite..."
python3 -m pytest -v

# 4. Mix Review Signal Analysis Qualification Benchmark
echo "[4/6] Running Mix Review qualification benchmark..."
python3 tooling/scripts/eval_mix_review.py

# 5. Chat & Knowledge Base Evaluation Suite
echo "[5/6] Running Chat evaluation runner..."
python3 packages/chat/eval_runner.py

# 6. Standalone Public API Health Probe Check
echo "[6/6] Verifying standalone import isolation..."
python3 -c "import app; print('✅ Standalone Public API imported successfully cleanly!')"

echo "================================================================================"
echo " ✅ ALL CI & RELEASE VERIFICATION CHECKS PASSED SUCCESSFULLY!"
echo "================================================================================"
