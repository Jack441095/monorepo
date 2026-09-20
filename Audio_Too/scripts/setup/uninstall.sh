#!/usr/bin/env bash
# Uninstall script for Audio_Too
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "=== Audio_Too Uninstall & Cleanup ==="
echo "This script will remove the virtual environment and clean up local runtime state."
echo ""

# 1. Remove virtual environment
if [[ -d .venv ]]; then
  echo "[-] Removing virtual environment (.venv)..."
  rm -rf .venv
  echo "[+] Virtual environment removed."
else
  echo "[*] No local .venv found in $ROOT."
fi

# 2. Offer to remove platform-specific Thursday state
echo ""
echo "Thursday state directory stores user databases, logs, and profiles."
echo "Locations by platform:"
echo "  macOS:   ~/Library/Application Support/Audio_Too/thursday/"
echo "  Linux:   ~/.local/state/audio-too/thursday/  (or \$XDG_STATE_HOME)"
echo "  Windows: %LOCALAPPDATA%\\Audio_Too\\thursday\\"
echo ""

# Determine platform state dir
STATE_DIR=""
if [[ "$OSTYPE" == "darwin"* ]]; then
  STATE_DIR="$HOME/Library/Application Support/Audio_Too"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
  STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/audio-too"
fi

if [[ -n "$STATE_DIR" && -d "$STATE_DIR" ]]; then
  read -p "Do you want to delete all user data and Thursday state in '$STATE_DIR'? (y/N): " -r CONFIRM
  if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "[-] Removing state directory: $STATE_DIR"
    rm -rf "$STATE_DIR"
    echo "[+] State directory removed."
  else
    echo "[*] Preserving user data in $STATE_DIR."
  fi
else
  echo "[*] No active state directory detected on this machine."
fi

# 3. Clean up cache and log files
echo "[-] Cleaning up python caches (*.pyc, __pycache__)..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

echo ""
echo "[+] Uninstall complete. To reinstall, run: ./audio-too setup"
