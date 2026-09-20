#!/usr/bin/env bash
# Read-only shared-host preflight. Does not deploy, install, or run inference.
set -euo pipefail
if [[ "${1:-}" == "--help" ]]; then
  printf '%s\n' 'Read-only KENN server preflight (SSH key or KENN_SERVER_PASSWORD).' \
    'No services, packages, models, notes, or indexes are changed.'
  exit 0
fi
SSH_ARGS=(-o StrictHostKeyChecking=yes -o ConnectTimeout=15
  -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -p 2022)
if [[ -n "${KENN_SERVER_PASSWORD:-}" ]]; then
  command -v sshpass >/dev/null
  export SSHPASS="$KENN_SERVER_PASSWORD"
  unset KENN_SERVER_PASSWORD
  AUTH=(sshpass -e)
else
  AUTH=()
  SSH_ARGS+=(-o BatchMode=yes)
fi
"${AUTH[@]}" ssh "${SSH_ARGS[@]}" ubuntu@www.haoee.com 'bash -s' <<'REMOTE'
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
ROOT=/mnt/data/kenn-GPU
printf '\n=== Disk and GPU 1 (no inference) ===\n'
df -h / /mnt/data
nvidia-smi -i 1 --query-gpu=index,uuid,name,memory.used,memory.total --format=csv
printf '\n=== Python dependencies ===\n'
"$ROOT/.venv/bin/python" -m pip check
"$ROOT/.venv/bin/python" -c 'import httpx, pypdf; print("IMPORTS_OK")'
printf '\n=== Ableton manual ===\n'
ls -lh "$ROOT/apps/backend/src/kenn/Training_Data_PDF/live12-manual-en.pdf"
printf '\n=== Existing model endpoint metadata only ===\n'
curl --max-time 5 --fail --silent --show-error http://127.0.0.1:11434/api/tags
printf '\nPreflight only: GPU binding and source-grounded generation must be verified before inference.\n'
REMOTE
