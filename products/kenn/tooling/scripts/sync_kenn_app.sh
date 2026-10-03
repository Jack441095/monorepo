#!/usr/bin/env bash
# Keep the manual entry point on the same guarded path as GitHub Actions.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
export PYTHONPATH="$repo_root/products/kenn/tooling${PYTHONPATH:+:$PYTHONPATH}"
exec python3 products/kenn/tooling/scripts/sync_kenn_app.py "$@"
