#!/bin/sh
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: $0 /path/to/real_manifest.json [local-results.json]" >&2
  exit 2
fi

manifest_path=$1
if [ ! -f "$manifest_path" ]; then
  echo "Manifest not found: $manifest_path" >&2
  exit 2
fi

if [ "$#" -eq 2 ]; then
  results_path=$2
else
  manifest_dir=$(dirname "$manifest_path")
  results_path="$manifest_dir/validation_results.json"
fi

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cli_path=""
for candidate in \
  "$product_dir/artifacts/Submit-0.2.0-macOS.app/Contents/MacOS/nitesubmit-cli" \
  "$product_dir/.build/release/nitesubmit-cli" \
  "$product_dir/.build/debug/nitesubmit-cli"; do
  if [ -x "$candidate" ]; then
    cli_path=$candidate
    break
  fi
done

if [ -z "$cli_path" ]; then
  echo "No local nitesubmit-cli found. Build the app or run: swift build -c release" >&2
  exit 2
fi

results_dir=$(dirname "$results_path")
mkdir -p "$results_dir"
exec "$cli_path" validate --manifest "$manifest_path" --out "$results_path"
