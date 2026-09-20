#!/usr/bin/env bash
# Import a few curated Ableton blog URLs as draft training notes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LIMIT="${1:-3}"
exec ./ableton import-web-pack "suggested: yes" "limit: ${LIMIT}"
