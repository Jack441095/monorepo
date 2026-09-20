#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RUNS_PER_EMOTION="${RUNS_PER_EMOTION:-5}"
ROOT_MIDI="${ROOT_MIDI:-60}"
BARS_PER_SECTION="${BARS_PER_SECTION:-8}"
FORM="${FORM:-default}"
K="${K:-1}"
OUT_ROOT="${OUT_ROOT:-logs/current_baseline_sweep_after_fixes}"

echo "Running full-song random seed audit:"
echo "  runs_per_emotion=${RUNS_PER_EMOTION}"
echo "  root_midi=${ROOT_MIDI}"
echo "  bars_per_section=${BARS_PER_SECTION}"
echo "  form=${FORM}"
echo "  out_root=${OUT_ROOT}"

AUDIT_OUTPUT="$(
  .venv/bin/python scripts/batch_full_song_note_audit.py \
    --runs-per-emotion "${RUNS_PER_EMOTION}" \
    --root "${ROOT_MIDI}" \
    --bars "${BARS_PER_SECTION}" \
    --form "${FORM}" \
    --k "${K}" \
    --random-seeds \
    --out-dir "${OUT_ROOT}"
)"

printf '%s\n' "$AUDIT_OUTPUT"

AUDIT_DIR="$(printf '%s\n' "$AUDIT_OUTPUT" | awk -F'wrote: ' '/wrote: / {print $2}' | tail -n 1)"
if [[ -z "${AUDIT_DIR}" || ! -d "${AUDIT_DIR}" ]]; then
  echo "Could not locate audit output folder." >&2
  exit 1
fi

echo "Running deeper analysis on: ${AUDIT_DIR}"
DEEP_DIR="$(
  .venv/bin/python scripts/analyze_random_seed_audit_deep.py \
    "${AUDIT_DIR}" \
    --out-root "${OUT_ROOT}" \
    --tag "deep_random5"
)"

echo "Base audit: ${AUDIT_DIR}"
echo "Deep audit: ${DEEP_DIR}"
