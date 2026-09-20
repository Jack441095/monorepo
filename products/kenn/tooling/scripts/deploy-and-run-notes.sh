#!/usr/bin/env bash
################################################################################
# deploy-and-run-notes.sh
#
# Deploys KENN to a remote Ubuntu GPU server and runs the "notes pipeline":
#   1. Rsync repo (includes large Ableton manual PDF)
#   2. Set up Python venv + install deps
#   3. Install Ollama + pull an LLM (GPU-accelerated note generation)
#   4. Copy local YouTube transcript .txt files into Training_Data_Transcripts/
#   5. Ingest web pack + paraphrase transcripts + generate notes + build index
#
# Constraints respected:
#   - No server restarts (Ollama run as user background process)
#   - GPU 1 (Ollama uses available GPU automatically)
#   - Password auth via sshpass
#
# Usage:
#   chmod +x deploy-and-run-notes.sh
#   ./deploy-and-run-notes.sh
#
# Requires locally: sshpass, rsync, ssh, git
################################################################################

set -euo pipefail

# Disabled: the legacy steps below are not safe for this shared host.
# Use the read-only check instead; never fall through to legacy deployment.
SCRIPT_ROOT="$(cd "$(dirname "$0")" && pwd)"
exec bash "${SCRIPT_ROOT}/notes_server_preflight.sh" "$@"
exit 1

# ── Configuration ──────────────────────────────────────────────────────────
SERVER_USER="ubuntu"
SERVER_HOST="www.haoee.com"
SERVER_PORT="2022"
# Password — passed via env var to avoid leaking in ps output. Override with:
#   export KENN_SERVER_PASSWORD="yourpassword"
SERVER_PASSWORD="${KENN_SERVER_PASSWORD:-}"

# Local paths
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# NOTE: root disk on server is nearly full; repo + ollama models live on /mnt/data
# (47G free). A symlink ~/kenn-GPU -> /mnt/data/kenn-GPU is created in Step 0 so
# all later steps can keep using ~/kenn-GPU.
REMOTE_BASE="/mnt/data/kenn-GPU"
REMOTE_REPO="${REMOTE_BASE}"
REMOTE_VENV="${REMOTE_REPO}/.venv"
REMOTE_OLLAMA_MODELS="/mnt/data/ollama-models"

# Pin Ollama to GPU 1 (per user: use GPU 1; GPUs 0-7 present, GPU 1 lightly used)
CUDA_DEVICE="1"

# Transcript source: the velvet_thunder copy that actually has .txt files
TRANSCRIPTS_LOCAL="${REPO_ROOT}/apps/backend/src/kenn/Training_Data_Transcripts"

# Ollama model to pull (must match .env AUDIO_TOO_LLM_MODEL on server)
OLLAMA_MODEL="qwen2.5:7b"

# SSH/rsync helpers (functions instead of string vars to avoid quoting bugs)
ssh_remote() {
  sshpass -p "${SERVER_PASSWORD}" ssh -o StrictHostKeyChecking=no -p "${SERVER_PORT}" "${SERVER_USER}@${SERVER_HOST}" "$@"
}
rsync_to() {
  sshpass -p "${SERVER_PASSWORD}" rsync -avz --progress \
    -e "ssh -o StrictHostKeyChecking=no -p ${SERVER_PORT}" "$@"
}

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy:WARN]${NC} $*"; }
err()  { echo -e "${RED}[deploy:ERR]${NC} $*"; }

# ── Pre-flight checks ─────────────────────────────────────────────────────
log "Pre-flight checks..."

command -v sshpass >/dev/null 2>&1 || { err "sshpass not found."; exit 1; }
command -v rsync  >/dev/null 2>&1 || { err "rsync not found."; exit 1; }
command -v ssh    >/dev/null 2>&1 || { err "ssh not found."; exit 1; }

if [ ! -f "${REPO_ROOT}/apps/backend/src/kenn/main.py" ]; then
  err "Cannot find apps/backend/src/kenn/main.py — run this from the KENN repo root."
  exit 1
fi

if [ ! -d "${TRANSCRIPTS_LOCAL}" ]; then
  warn "Transcript source dir not found at: ${TRANSCRIPTS_LOCAL}"
  warn "Will skip the transcript copy step."
  TRANSCRIPTS_LOCAL=""
fi

if [ -n "${TRANSCRIPTS_LOCAL}" ]; then
  TRANSCRIPT_COUNT=$(find "${TRANSCRIPTS_LOCAL}" -type f -name "*.txt" 2>/dev/null | wc -l)
  log "Found ${TRANSCRIPT_COUNT} transcript .txt files to copy."
fi

log "Local repo root: ${REPO_ROOT}"
log "Remote target:   ${SERVER_USER}@${SERVER_HOST}:${REMOTE_BASE} (port ${SERVER_PORT})"
log "Ollama model:    ${OLLAMA_MODEL}"

# ── Step 0: Prepare remote workspace ──────────────────────────────────────
log "Step 0: Preparing remote workspace on /mnt/data (root disk is 99% full)..."
ssh_remote "mkdir -p ${REMOTE_BASE} ${REMOTE_OLLAMA_MODELS} && ln -sfn ${REMOTE_BASE} ~/kenn-GPU && df -h /mnt/data | tail -1 && echo ready"

# ── Step 1: Rsync repo (includes the 92MB Ableton manual PDF) ─────────────
log "Step 1: Rsyncing repo to server (this may take a while)..."

rsync_to \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.runtime' \
  --exclude '*.pyc' \
  --exclude '*.pyo' \
  --exclude '.DS_Store' \
  --exclude 'node_modules' \
  --exclude 'dist' \
  --exclude 'build' \
  --exclude '.git' \
  "./" "${SERVER_USER}@${SERVER_HOST}:${REMOTE_BASE}/"

log "Rsync complete."


# ── Step 2: Set up Python venv + install deps ─────────────────────────────
log "Step 2: Setting up Python venv and installing dependencies on server..."

ssh_remote "${REMOTE_BASE}" <<'REMOTE_SETUP_PYTHON'
  set -euo pipefail
  cd ~/kenn-GPU

  if [ ! -d .venv ]; then
    python3 -m venv .venv
  fi

  . .venv/bin/activate
  pip install --upgrade pip --quiet
  pip install -r requirements.txt
  echo "PYTHON_READY"
REMOTE_SETUP_PYTHON

log "Python environment ready."

# ── Step 3: Install Ollama + pull model (user-level, no restart) ──────────
log "Step 3: Setting up Ollama on server (user-level, no restart)..."

ssh_remote "${REMOTE_BASE}" <<'REMOTE_SETUP_OLLAMA'
  set -euo pipefail
  cd ~/kenn-GPU

  if command -v ollama >/dev/null 2>&1; then
    echo "OLLAMA_ALREADY_INSTALLED"
    ollama --version
  else
    echo "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "OLLAMA_INSTALLED"
  fi
REMOTE_SETUP_OLLAMA

log "Starting Ollama serve (background, no restart)..."
ssh_remote "${REMOTE_BASE}" <<'REMOTE_START_OLLAMA'
  set -euo pipefail
  cd ~/kenn-GPU

  # Stop any ollama serve process we started previously (not a system restart)
  pkill -f "ollama serve" 2>/dev/null || true
  sleep 1

  # Models stored on /mnt/data (root disk full); pinned to GPU 1
  OLLAMA_MODELS=/mnt/data/ollama-models CUDA_VISIBLE_DEVICES=1 \
    nohup ollama serve > ~/kenn-GPU/ollama-serve.log 2>&1 &
  echo $! > ~/kenn-GPU/ollama.pid
  echo "OLLAMA_STARTED"
REMOTE_START_OLLAMA

log "Waiting for Ollama API to become ready (up to 60s)..."
OLLAMA_READY=0
for i in $(seq 1 12); do
  if ssh_remote "${REMOTE_BASE}" "curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1"; then
    log "Ollama API is up."
    OLLAMA_READY=1
    break
  fi
  sleep 5
done

if [ "${OLLAMA_READY}" -ne 1 ]; then
  err "Ollama API did not become ready in 60s. Check ~/kenn-GPU/ollama-serve.log on server."
  ssh_remote "${REMOTE_BASE}" "tail -20 ~/kenn-GPU/ollama-serve.log || true"
  exit 1
fi

log "Pulling Ollama model: ${OLLAMA_MODEL} (this may take a while on first run)..."
ssh_remote "${REMOTE_BASE}" "ollama pull ${OLLAMA_MODEL}" | tail -5


# ── Step 4: Copy local transcript .txt files to the server ────────────────
if [ -n "${TRANSCRIPTS_LOCAL}" ] && [ -d "${TRANSCRIPTS_LOCAL}" ]; then
  log "Step 4: Copying transcript .txt files to server..."

  ssh_remote "${REMOTE_BASE}" "mkdir -p ~/kenn-GPU/apps/backend/src/kenn/Training_Data_Transcripts"

  rsync_to \
    --include '*/' \
    --include '*.txt' \
    --exclude '*' \
    "${TRANSCRIPTS_LOCAL}/" \
    "${SERVER_USER}@${SERVER_HOST}:${REMOTE_BASE}/apps/backend/src/kenn/Training_Data_Transcripts/"

  TRANSCRIPT_COUNT_REMOTE=$(ssh_remote "${REMOTE_BASE}" "find ~/kenn-GPU/apps/backend/src/kenn/Training_Data_Transcripts -type f -name '*.txt' | wc -l")
  log "Transcripts on server after copy: ${TRANSCRIPT_COUNT_REMOTE}"
else
  warn "Step 4: Skipped — no transcript source directory."
fi

# ── Step 5: Update .env on server to match the pulled model ───────────────
log "Step 5: Updating .env on server (model: ${OLLAMA_MODEL})..."

ssh_remote "${REMOTE_BASE}" <<REMOTE_ENV_UPGRADE
  set -euo pipefail
  cd ~/kenn-GPU

  if [ -f .env ]; then
    if grep -q '^AUDIO_TOO_LLM_MODEL=' .env; then
      sed -i "s/^AUDIO_TOO_LLM_MODEL=.*/AUDIO_TOO_LLM_MODEL=${OLLAMA_MODEL}/" .env
    else
      echo "AUDIO_TOO_LLM_MODEL=${OLLAMA_MODEL}" >> .env
    fi

    if grep -q '^AUDIO_TOO_LLM_ENABLED=' .env; then
      sed -i 's/^AUDIO_TOO_LLM_ENABLED=.*/AUDIO_TOO_LLM_ENABLED=1/' .env
    else
      echo "AUDIO_TOO_LLM_ENABLED=1" >> .env
    fi

    if grep -q '^AUDIO_TOO_LLM_PROVIDER=' .env; then
      sed -i 's/^AUDIO_TOO_LLM_PROVIDER=.*/AUDIO_TOO_LLM_PROVIDER=ollama/' .env
    else
      echo "AUDIO_TOO_LLM_PROVIDER=ollama" >> .env
    fi

    if grep -q '^AUDIO_TOO_LLM_BASE_URL=' .env; then
      sed -i 's|^AUDIO_TOO_LLM_BASE_URL=.*|AUDIO_TOO_LLM_BASE_URL=http://127.0.0.1:11434/v1|' .env
    else
      echo "AUDIO_TOO_LLM_BASE_URL=http://127.0.0.1:11434/v1" >> .env
    fi
  else
    cat > .env <<EOF
AUDIO_TOO_LLM_ENABLED=1
AUDIO_TOO_LLM_PROVIDER=ollama
AUDIO_TOO_LLM_BASE_URL=http://127.0.0.1:11434/v1
AUDIO_TOO_LLM_MODEL=${OLLAMA_MODEL}
AUDIO_TOO_LLM_TIMEOUT=120
EOF
  fi
  echo "--- .env on server ---"
  cat .env
REMOTE_ENV_UPGRADE

log ".env configured."

# ── Step 6: Run the notes pipeline on the server ──────────────────────────
log "Step 6: Running the notes pipeline on server (ingest → generate → build)..."

ssh_remote "${REMOTE_BASE}" <<'REMOTE_RUN_PIPELINE'
  set -uo pipefail
  cd ~/kenn-GPU
  . .venv/bin/activate

  echo "═══ 6a) Import web pack (draft notes from web_sources.json) ═══"
  python3 apps/backend/src/kenn/main.py import-web-pack "limit:10" "suggested:yes" || \
    echo "  (import-web-pack failed — continuing)"

  echo "═══ 6b) Paraphrase all transcripts into draft notes ═══"
  python3 apps/backend/src/kenn/main.py paraphrase-all-transcripts \
    "creator:velvet_thunder" \
    "tags:ableton,sound design,video tutorial" \
    "force:yes" || echo "  (paraphrase-all-transcripts had errors — continuing)"

  echo "═══ 6c) Generate new knowledge notes (LLM on GPU) ═══"
  python3 tooling/scripts/generate_knowledge_notes.py --dry-run || \
    echo "  (dry-run had errors — continuing)"

  python3 tooling/scripts/generate_knowledge_notes.py || \
    echo "  (note generation had errors — continuing)"

  echo "═══ 6d) Rebuild BM25 index ═══"
  python3 apps/backend/src/kenn/main.py build || echo "  (build had errors — continuing)"

  echo "═══ 6e) Final status check ═══"
  python3 apps/backend/src/kenn/main.py sources | head -30 || true
  python3 apps/backend/src/kenn/main.py transcripts | head -30 || true
REMOTE_RUN_PIPELINE

log "Notes pipeline finished."

# ── Step 7: Sync generated notes back to your Mac ─────────────────────────
log "Step 7: Syncing generated notes back to local machine..."

rsync_to \
  --include '*/' \
  --include '*.md' \
  --exclude '*' \
  "${SERVER_USER}@${SERVER_HOST}:${REMOTE_BASE}/apps/backend/src/kenn/Training_Data_Notes/" \
  "${REPO_ROOT}/apps/backend/src/kenn/Training_Data_Notes-from-server/"

log "Notes copied to: apps/backend/src/kenn/Training_Data_Notes-from-server/"
log "Review them, then merge into apps/backend/src/kenn/Training_Data_Notes/ and run:"
log "  python3 apps/backend/src/kenn/main.py build"
log "Done."


MODEL_CHECK=$(ssh_remote "${REMOTE_BASE}" "ollama list" || echo "FAILED")
log "Available models on server:"
echo "${MODEL_CHECK}" | sed 's/^/  /'
