#!/bin/zsh
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/kenn-live-export-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
xcrun swiftc -D KENN_EXPORT_TESTS -parse-as-library \
  "$script_dir/KENNLiveExportHelper.swift" "$script_dir/KENNLiveExportHelperTests.swift" \
  -o "$build_dir/KENNLiveExportHelperTests" \
  -framework AppKit -framework ApplicationServices
"$build_dir/KENNLiveExportHelperTests"
helper="$("$script_dir/build_live_export_helper.sh" "$build_dir")"
# Malformed input exercises the executable protocol without looking up or controlling any application.
receipt="$(printf '%s' '{"invalid":true}' | "$helper")"
[[ "$receipt" == *'"status":"failed"'* && "$receipt" == *'"writer_closed":false'* ]]
printf '%s\n' 'PASS: malformed executable request fails closed'
