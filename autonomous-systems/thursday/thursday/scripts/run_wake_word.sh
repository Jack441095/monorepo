#!/bin/zsh
# Hands-free "Hey Jarvis" wake word for Thursday -- desktop only (see
# thursday/wake_word.py's module docstring for why this can't work from
# the phone). Needs this project's own .venv with openwakeword and
# sounddevice installed; it used to borrow Audio_Too/.venv, which is gone
# (Audio_Too was removed on 18 Oct 2026).
#
# IMPORTANT: run this in a foreground Terminal (not as a background
# launchd service) the first time -- macOS needs an interactive session
# to show the microphone permission prompt. Once granted (System
# Settings -> Privacy & Security -> Microphone), a background launchd
# service can use it without re-prompting.

set -euo pipefail

THURSDAY_REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$THURSDAY_REPO_DIR"

# Unlike run_server.sh there is no system-python fallback: the wake word
# cannot run without openwakeword + sounddevice, so a missing venv is a
# hard stop rather than a crash loop under launchd.
PYTHON="$THURSDAY_REPO_DIR/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  echo "[run_wake_word] Thursday venv python3 not found at $PYTHON" >&2
  exit 1
fi

# Load the same .env server.py reads (autonomous-systems/thursday/.env, moved
# out of Audio_Too on 18 Oct 2026), so THURSDAY_BRAIN_ENABLED etc match the
# HTTP server. With no file the defaults apply.
ENV_FILE="$THURSDAY_REPO_DIR/.env"
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
