#!/usr/bin/env bash
# Weekly knowledge LM maintenance: validate, rebuild, evaluate, and rank real gaps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="python3"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
fi

echo "==> Auditing note quality and coverage"
"${PY}" "${ROOT}/main.py" knowledge-audit --strict

echo "==> Rebuilding KENN index"
"${ROOT}/ableton" build

echo "==> Running retrieval eval"
"${PY}" "${ROOT}/scripts/eval/ableton_eval.py"

echo "==> Running held-out multi-turn eval"
"${PY}" "${ROOT}/scripts/eval/ableton_eval.py" \
  --suite "${ROOT}/studio/kenn/kenn/evals/conversation_cases.json"

echo "==> Running held-out specialist eval"
"${PY}" "${ROOT}/scripts/eval/ableton_eval.py" \
  --suite "${ROOT}/studio/kenn/kenn/evals/knowledge_upgrade_cases.json"

echo "==> Running held-out official internet-source eval"
"${PY}" "${ROOT}/scripts/eval/ableton_eval.py" \
  --suite "${ROOT}/studio/kenn/kenn/evals/internet_source_cases.json"

echo "==> Ranking unresolved real-user gaps"
"${PY}" "${ROOT}/main.py" knowledge-gaps --limit 50

echo ""
echo "Done. Spot-check: ./audio-too ableton ask \"your test question\""
echo "See docs/KNOWLEDGE_LM_LOOP.md for the full weekly loop."
