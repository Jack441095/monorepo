#!/usr/bin/env bash
set -e

echo "=== Audio_Too Docker Entrypoint ==="
echo "Mode: ${1:-web-server}"

# Ensure data and logs directories exist
mkdir -p /app/data /app/logs

# Initialize SQLite database pragmas & migrations
python3 -c "
import sys
sys.path.insert(0, 'business/app')
import db
conn = db.connect()
print('SQLite database initialized at', db.DB_PATH)
"

case "$1" in
  web-server)
    echo "Starting Audio_Too website server on port 8080..."
    exec python3 business/app/server.py
    ;;
  automix-worker)
    echo "Starting AutoMix background processing worker..."
    exec python3 business/app/automix_worker.py
    ;;
  thursday-agent)
    # thursday/main.py is a one-shot CLI (handles a single request and
    # exits), not a persistent daemon -- there is no long-running
    # orchestrator process to launch here yet. Left disabled rather than
    # execing something that would just exit immediately and loop-restart
    # under `restart: unless-stopped`.
    echo "thursday-agent has no persistent daemon mode yet -- not starting." >&2
    exit 1
    ;;
  *)
    exec "$@"
    ;;
esac
