#!/usr/bin/env bash
set -euo pipefail

# KENN GPU 1 Note Synchronizer & Index Builder
# Run this whenever you turn your Mac on to pull all notes generated overnight on GPU 1.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NOTES_DIR="${REPO_ROOT}/apps/backend/src/kenn/Training_Data_Notes"
PROGRESS_FILE="${REPO_ROOT}/apps/backend/src/kenn/Training_Data_Sources/.batch_distillation_progress.json"
REMOTE_HOST="ubuntu@www.haoee.com"
REMOTE_PORT="2022"
REMOTE_DIR="/mnt/data/kenn-notes-gpu1/generated_notes/"
REMOTE_PROGRESS="/mnt/data/kenn-notes-gpu1/.batch_distillation_progress.json"

echo "================================================================="
echo "   KENN GPU 1 NOTE SYNCHRONIZER & INDEX BUILDER"
echo "================================================================="

# Setup Askpass credentials for non-interactive SSH
ASKPASS_TMP="$(mktemp -t kenn_askpass.XXXXXX)"
cat << 'EOF' > "$ASKPASS_TMP"
#!/bin/sh
echo "srd123456."
EOF
chmod +x "$ASKPASS_TMP"
trap 'rm -f "$ASKPASS_TMP"' EXIT

export SSH_ASKPASS="$ASKPASS_TMP"
export SSH_ASKPASS_REQUIRE=force

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
