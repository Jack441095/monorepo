#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RUNS_PER_EMOTION="${RUNS_PER_EMOTION:-5}"
ROOT_MIDI="${ROOT_MIDI:-60}"
BARS_PER_SECTION="${BARS_PER_SECTION:-8}"
FORM="${FORM:-default}"
K="${K:-1}"
OUT_ROOT="${OUT_ROOT:-/private/tmp/full_song_audit_emotion_match_random}"

echo "Running random-seed full-song audit with emotion-match scoring:"
echo "  runs_per_emotion=${RUNS_PER_EMOTION}"
echo "  root_midi=${ROOT_MIDI}"
echo "  bars_per_section=${BARS_PER_SECTION}"
echo "  form=${FORM}"
echo "  k=${K}"
echo "  out_root=${OUT_ROOT}"

.venv/bin/python scripts/batch_full_song_note_audit.py \
  --runs-per-emotion "${RUNS_PER_EMOTION}" \
  --random-seeds \
  --root "${ROOT_MIDI}" \
  --bars "${BARS_PER_SECTION}" \
  --form "${FORM}" \
  --k "${K}" \
  --out-dir "${OUT_ROOT}"
