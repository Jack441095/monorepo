#!/bin/zsh
# Hands-free "Hey Jarvis" wake word for Thursday -- desktop only (see
# thursday/wake_word.py's module docstring for why this can't work from
# the phone). Uses Audio_Too's venv (openwakeword, sounddevice, etc.
# already installed there) and reaches Audio_Too's real integrations via
# thursday.repo_root the same way the HTTP server does.
#
# IMPORTANT: run this in a foreground Terminal (not as a background
# launchd service) the first time -- macOS needs an interactive session
# to show the microphone permission prompt. Once granted (System
# Settings -> Privacy & Security -> Microphone), a background launchd
# service can use it without re-prompting.

set -euo pipefail

THURSDAY_REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$THURSDAY_REPO_DIR"

AUDIO_TOO_DIR="$THURSDAY_REPO_DIR/../../Audio_Too"
PYTHON="$AUDIO_TOO_DIR/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  echo "[run_wake_word] Audio_Too venv python3 not found at $PYTHON" >&2
  exit 1
fi

# Load Audio_Too/.env the same way run_server.sh does, so THURSDAY_BRAIN_ENABLED
# etc are set for thursday.bridge.ask() to behave the same as the HTTP server.
ENV_FILE="$AUDIO_TOO_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    export "$key=$value"
  done < "$ENV_FILE"
fi

# -u: unbuffered stdout. Without it, under launchd (no TTY) Python
# block-buffers stdout, so this script's [wake_word] progress prints sit
# invisible in the buffer for a long time rather than reaching the log
# file in real time -- found live, 2026-09-02, watching an apparently
# stuck-but-actually-fine launchd run.
exec "$PYTHON" -u -m thursday.wake_word
