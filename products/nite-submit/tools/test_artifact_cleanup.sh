#!/bin/zsh
set -euo pipefail

product_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
work_dir=$(mktemp -d /tmp/nite-submit-artifact-cleanup.XXXXXX)
trap 'rm -R -- "$work_dir"' EXIT

version="$(tr -d '[:space:]' < "$product_dir/VERSION")"
artifacts_dir="$work_dir/artifacts"
mkdir -p \
  "$artifacts_dir/Submit-0.1.0-macOS.app" \
  "$artifacts_dir/Submit-0.3.0-macOS.app" \
  "$artifacts_dir/Submit-${version}-macOS.app" \
  "$artifacts_dir/NITESubmit-${version}-macOS.app" \
  "$artifacts_dir/NITESubmit-not-a-release-macOS.app"
touch \
  "$artifacts_dir/Submit-0.1.0-macOS.zip" \
  "$artifacts_dir/Submit-0.3.0-macOS.zip" \
  "$artifacts_dir/Submit-${version}-macOS.zip" \
  "$artifacts_dir/NITESubmit-${version}-macOS.zip" \
  "$artifacts_dir/keep-me.json"

NITE_SUBMIT_ARTIFACTS_DIR="$artifacts_dir" \
  "$product_dir/tools/cleanup_old_release_artifacts.sh" "$version" >/dev/null

[[ -d "$artifacts_dir/Submit-${version}-macOS.app" ]]
[[ -f "$artifacts_dir/Submit-${version}-macOS.zip" ]]
[[ -d "$artifacts_dir/NITESubmit-not-a-release-macOS.app" ]]
[[ -f "$artifacts_dir/keep-me.json" ]]
[[ ! -e "$artifacts_dir/Submit-0.1.0-macOS.app" ]]
[[ ! -e "$artifacts_dir/Submit-0.1.0-macOS.zip" ]]
[[ ! -e "$artifacts_dir/Submit-0.3.0-macOS.app" ]]
[[ ! -e "$artifacts_dir/Submit-0.3.0-macOS.zip" ]]
[[ ! -e "$artifacts_dir/NITESubmit-${version}-macOS.app" ]]
[[ ! -e "$artifacts_dir/NITESubmit-${version}-macOS.zip" ]]

echo "Artifact cleanup check passed: stale versions removed; current and unrelated files retained."
