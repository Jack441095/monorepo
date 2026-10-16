#!/bin/zsh
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
output_dir="${1:-$(mktemp -d "${TMPDIR:-/tmp}/kenn-live-export-build.XXXXXX")}"
mkdir -p "$output_dir"
xcrun swiftc -parse-as-library "$script_dir/KENNLiveExportHelper.swift" "$script_dir/KENNExportAX.swift" \
  -o "$output_dir/KENNLiveExportHelper" \
  -framework AppKit -framework ApplicationServices
printf '%s\n' "$output_dir/KENNLiveExportHelper"
