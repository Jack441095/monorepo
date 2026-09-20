#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "$0")/.." && pwd))"

prohibited='(^|/)([^/]+\.private|licensing\.db(-wal|-shm)?)$'
if git ls-files | grep -E "$prohibited"; then
  echo "Tracked licensing secret or runtime database detected" >&2
  exit 1
fi
