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
# Working directory is THIS repo (autonomous-systems/thursday) --
# `python -m thursday.server` resolves the `thursday` package from cwd
# first. Audio_Too, which held the live integrations listed in
# docs/EXTRACTION_COUPLING.md (Ableton bridge, Kokoro model files, the
# business DB), was removed on 18 Oct 2026, so Thursday is parked:
# the server starts, but those integrations report missing until they get
# a new home. See thursday/repo_root.py for the archive tag.
#
# Python interpreter: this project's own .venv (gitignored) when present.
# It used to borrow Audio_Too/.venv, which had already disappeared before
# Audio_Too itself was removed, so the launchd job had been exiting 78.
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

# No venv yet falls back to the system python3: `import thursday` is pure
# standard library, so the server still starts and only the optional
# extras (TTS/STT, httpx, YAML) fail lazily when called.
VENV_PYTHON="$THURSDAY_REPO_DIR/.venv/bin/python3"
if [[ -x "$VENV_PYTHON" ]]; then
  PYTHON="$VENV_PYTHON"
else
  PYTHON="python3"
fi

echo "[run_server] Starting Thursday server (autonomous-systems/thursday) on $HOST:$PORT using $PYTHON ($(date))"
exec "$PYTHON" -m thursday.server --host "$HOST" --port "$PORT"
