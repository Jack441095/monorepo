#!/bin/zsh
# Launches Thursday's HTTP server (this repo's own thursday/server.py, the
# canonical copy as of 2026-09-02 -- Audio_Too/thursday is now archived,
# not developed against) bound to this machine's current Tailscale IP, so
# it's reachable over the private tailnet only -- never the regular
# LAN/wifi (binding 0.0.0.0 would do that; this deliberately doesn't).
#
# Resolves the IP at every start rather than hardcoding it in the launchd
# plist: Tailscale IPs are normally stable per-device, but re-resolving here
# means a reassignment (re-auth, device re-registration) doesn't leave the
# service silently bound to a stale, wrong address.
#
# Working directory is THIS repo (autonomous-systems/thursday), not
# Audio_Too -- `python -m thursday.server` resolves the `thursday` package
# from cwd first, so this is what makes the extraction's copy the one that
# actually runs. thursday.repo_root.audio_too_root() (an upward search,
# not a fixed relative path -- see that module's docstring) still finds
# real Audio_Too/ on disk at runtime for the genuine live integrations
# documented in docs/EXTRACTION_COUPLING.md (Ableton bridge, AudioGen,
# Kokoro TTS model files, business/app/db, etc) -- this script does not
# need to know where Audio_Too lives.
#
# Python interpreter: reuses Audio_Too's own .venv rather than maintaining
# a duplicate one here. Every dependency this repo's pyproject.toml lists
# as a lazy/optional extra (numpy, onnxruntime, httpx, PyYAML,
# faster-whisper, kokoro-onnx, sounddevice, soundfile, psutil) is already
# installed there for the exact same real features (TTS/STT, HTTP calls,
# YAML configs) -- installing a second copy would just be duplication of
# the same real dependency set, not decoupling from anything.
#
# Invoked by ~/Library/LaunchAgents/com.nitedsp.thursday-server.plist.
# Can also be run directly for a one-off foreground start.

set -euo pipefail

THURSDAY_REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$THURSDAY_REPO_DIR"

TAILSCALE_BIN="/usr/local/bin/tailscale"
if [[ ! -x "$TAILSCALE_BIN" ]]; then
  TAILSCALE_BIN="$(command -v tailscale || true)"
fi

if [[ -z "$TAILSCALE_BIN" ]]; then
  echo "[run_server] tailscale CLI not found -- is Tailscale installed?" >&2
  exit 1
fi

HOST="$("$TAILSCALE_BIN" ip -4 2>/dev/null || true)"
if [[ -z "$HOST" ]]; then
  echo "[run_server] Could not resolve a Tailscale IPv4 address -- is Tailscale connected?" >&2
  exit 1
fi

PORT="${THURSDAY_SERVER_PORT:-8092}"

# Reuses Audio_Too's .venv (see header comment) -- resolved relative to
# THURSDAY_REPO_DIR's sibling Audio_Too/ so this still works if the
# monorepo is checked out somewhere other than this exact path.
AUDIO_TOO_VENV_PYTHON="$THURSDAY_REPO_DIR/../../Audio_Too/.venv/bin/python3"
if [[ -x "$AUDIO_TOO_VENV_PYTHON" ]]; then
  PYTHON="$AUDIO_TOO_VENV_PYTHON"
else
  PYTHON="python3"
fi

echo "[run_server] Starting Thursday server (autonomous-systems/thursday) on $HOST:$PORT using $PYTHON ($(date))"
exec "$PYTHON" -m thursday.server --host "$HOST" --port "$PORT"
