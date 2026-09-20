#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RUNS_PER_EMOTION="${RUNS_PER_EMOTION:-2}"
ROOT_MIDI="${ROOT_MIDI:-60}"
BARS_PER_SECTION="${BARS_PER_SECTION:-8}"
FORM="${FORM:-default}"
K="${K:-4}"
SONG_RERANK_MODEL="${SONG_RERANK_MODEL:-artifacts/song_rerank/rerank_v1.json}"
OUT_ROOT="${OUT_ROOT:-/private/tmp/audit_phase_c_plus}"

echo "Phase C audit (joint plan + Markov hook cell + Phase B rerank):"
echo "  runs_per_emotion=${RUNS_PER_EMOTION}"
echo "  k=${K}"
echo "  song_rerank_model=${SONG_RERANK_MODEL}"
echo "  out_root=${OUT_ROOT}"

.venv/bin/python scripts/batch_full_song_note_audit.py \
  --song-upgrade-phase-c \
  --song-rerank-model "${SONG_RERANK_MODEL}" \
  --runs-per-emotion "${RUNS_PER_EMOTION}" \
  --random-seeds \
  --root "${ROOT_MIDI}" \
  --bars "${BARS_PER_SECTION}" \
  --form "${FORM}" \
  --k "${K}" \
  --out-dir "${OUT_ROOT}"
