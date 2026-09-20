#!/usr/bin/env bash
set -euo pipefail

# KENN Public Beta Server Startup Script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "================================================================================"
echo " Starting KENN Public Beta Server..."
echo " Repository Root: $REPO_ROOT"
echo "================================================================================"

cd "$REPO_ROOT"

# Set PYTHONPATH to include source, chat, and mix-review core
export PYTHONPATH="$REPO_ROOT/apps/backend/src:$REPO_ROOT/packages/chat:$REPO_ROOT/packages/mix-review/core:${PYTHONPATH:-}"

# Verify vector index exists; build if missing
INDEX_DIR="$REPO_ROOT/apps/backend/src/kenn/data/index/versions"
if [ ! -d "$INDEX_DIR" ] || [ -z "$(ls -A "$INDEX_DIR" 2>/dev/null)" ]; then
    echo "[!] Knowledge vector index not found. Building index..."
    python3 apps/backend/src/kenn/main.py build
fi

# Run the server. server.py reads KENN_HOST/KENN_PORT (not the bare
# HOST/PORT names this script used to export, which it silently ignored --
# the server always bound to its 127.0.0.1:8090 default regardless of what
# this script printed).
export KENN_PORT="${KENN_PORT:-${PORT:-8090}}"
export KENN_HOST="${KENN_HOST:-${HOST:-0.0.0.0}}"
echo "[+] Launching KENN server on http://$KENN_HOST:$KENN_PORT..."
exec python3 apps/backend/src/kenn/server.py
