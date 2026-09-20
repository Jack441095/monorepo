#!/bin/zsh
# Launches Datasette as a read-only browser for Audio_Too's business
# database (leads, clients, invoices, projects, etc.) -- a companion to
# Thursday's ops modules, not a replacement: for anything not worth a
# dedicated command, this is a "just let me poke at the raw data" view.
#
# Same security model as Thursday's own server
# (com.nitedsp.thursday-server): bound to this machine's current
# Tailscale IP only, never 0.0.0.0 -- never reachable over the regular
# LAN/wifi. Additionally password-protected (datasette-auth-passwords,
# see datasette_metadata.json) since Datasette itself has no auth by
# default and this exposes real business data, unlike a plain read-only
# file share.
#
# Invoked by ~/Library/LaunchAgents/com.nitedsp.datasette.plist.
# Can also be run directly for a one-off foreground start.

set -euo pipefail

THURSDAY_REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
AUDIO_TOO_DIR="$THURSDAY_REPO_DIR/../../Audio_Too"

TAILSCALE_BIN="/usr/local/bin/tailscale"
if [[ ! -x "$TAILSCALE_BIN" ]]; then
  TAILSCALE_BIN="$(command -v tailscale || true)"
fi
if [[ -z "$TAILSCALE_BIN" ]]; then
  echo "[run_datasette] tailscale CLI not found -- is Tailscale installed?" >&2
  exit 1
fi

HOST="$("$TAILSCALE_BIN" ip -4 2>/dev/null || true)"
if [[ -z "$HOST" ]]; then
  echo "[run_datasette] Could not resolve a Tailscale IPv4 address -- is Tailscale connected?" >&2
  exit 1
fi

PORT="${DATASETTE_PORT:-8093}"
DB_PATH="$AUDIO_TOO_DIR/data/audio_too.db"

PYTHON="$AUDIO_TOO_DIR/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  echo "[run_datasette] Audio_Too venv python3 not found at $PYTHON" >&2
  exit 1
fi

# Load DATASETTE_JACK_PASSWORD_HASH from Audio_Too/.env (gitignored) --
# same pattern thursday/server.py already uses to load THURSDAY_SERVER_TOKEN.
ENV_FILE="$AUDIO_TOO_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    export "$key=$value"
  done < "$ENV_FILE"
fi

if [[ -z "${DATASETTE_JACK_PASSWORD_HASH:-}" ]]; then
  echo "[run_datasette] DATASETTE_JACK_PASSWORD_HASH not set in Audio_Too/.env -- refusing to start unauthenticated." >&2
  exit 1
fi

echo "[run_datasette] Starting Datasette on $HOST:$PORT ($(date)) -- immutable (read-only) view of $DB_PATH"
exec "$PYTHON" -m datasette \
  --host "$HOST" --port "$PORT" \
  --immutable "$DB_PATH" \
  --metadata "$THURSDAY_REPO_DIR/thursday/scripts/datasette_metadata.json" \
  --setting default_allow_sql off
