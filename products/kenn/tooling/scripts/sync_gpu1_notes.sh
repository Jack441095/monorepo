#!/usr/bin/env bash
set -euo pipefail

# KENN GPU 1 Note Synchronizer & Index Builder
# Run this whenever you turn your Mac on to pull all notes generated overnight.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NOTES_DIR="${REPO_ROOT}/apps/backend/src/kenn/Training_Data_Notes"
PROGRESS_FILE="${REPO_ROOT}/apps/backend/src/kenn/Training_Data_Sources/.batch_distillation_progress.json"
# The box's hostname is not committed (AGENTS.md: no remote hostnames in git), so it comes from the
# environment. Sync scripts are run by hand, so failing here is better than an ssh error 90 seconds in.
REMOTE_HOST="${KENN_SERVER_TARGET:?set KENN_SERVER_TARGET to user@host for the notes box}"
REMOTE_PORT="${KENN_SERVER_PORT:-2022}"
REMOTE_DIR="/mnt/data/kenn-notes-gpu1/generated_notes/"
REMOTE_PROGRESS="/mnt/data/kenn-notes-gpu1/.batch_distillation_progress.json"

echo "================================================================="
echo "   KENN GPU 1 NOTE SYNCHRONIZER & INDEX BUILDER"
echo "================================================================="

# Authentication is by SSH key. Never put a password in this repo.

echo "[*] Syncing new notes from remote GPU 1 to local SSD..."
rsync -avz --progress -e "ssh -o StrictHostKeyChecking=no -p ${REMOTE_PORT}" \
  "${REMOTE_HOST}:${REMOTE_DIR}" \
  "${NOTES_DIR}/"

echo "[*] Syncing progress ledger..."
rsync -avz -e "ssh -o StrictHostKeyChecking=no -p ${REMOTE_PORT}" \
  "${REMOTE_HOST}:${REMOTE_PROGRESS}" \
  "${PROGRESS_FILE}"

NOTE_COUNT=$(find "${NOTES_DIR}" -name "*.md" | wc -l | tr -d ' ')
echo "[+] Total knowledge notes on local SSD: ${NOTE_COUNT}"

echo "[*] Rebuilding KENN Hybrid BM25 & Semantic Vector Index..."
cd "${REPO_ROOT}/apps/backend/src"
export PYTHONPATH="${REPO_ROOT}/apps/backend/src${PYTHONPATH:+:${PYTHONPATH}}"
python3 kenn/retrieval/build_index.py

echo "================================================================="
echo "[+] Sync & Re-indexing Complete! KENN brain is fully up to date."
echo "================================================================="
