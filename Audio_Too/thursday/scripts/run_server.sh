#!/bin/zsh
# Launches Thursday's HTTP server bound to this machine's current Tailscale
# IP, so it's reachable over the private tailnet only -- never the regular
# LAN/wifi (binding 0.0.0.0 would do that; this deliberately doesn't).
#
# Resolves the IP at every start rather than hardcoding it in the launchd
# plist: Tailscale IPs are normally stable per-device, but re-resolving here
# means a reassignment (re-auth, device re-registration) doesn't leave the
# service silently bound to a stale, wrong address.
#
# Invoked by ~/Library/LaunchAgents/com.nitedsp.thursday-server.plist.
# Can also be run directly for a one-off foreground start.

set -euo pipefail

AUDIO_TOO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$AUDIO_TOO_DIR"

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

# Explicit interpreter path, not a bare `python3` relying on PATH: under
# launchd, PATH resolution picked up a *third* Python (3.11, system
# Framework build) with neither yaml nor httpx installed, ignoring both
# the .venv this project actually depends on and the EnvironmentVariables
# PATH set in the plist. Found 2026-09-02 debugging exactly this. Matches
# the project's own ./audio-too wrapper's precedent (.venv first, else
# system python3).
if [[ -x "$AUDIO_TOO_DIR/.venv/bin/python3" ]]; then
  PYTHON="$AUDIO_TOO_DIR/.venv/bin/python3"
else
  PYTHON="python3"
fi

echo "[run_server] Starting Thursday server on $HOST:$PORT using $PYTHON ($(date))"
exec "$PYTHON" -m thursday.server --host "$HOST" --port "$PORT"
