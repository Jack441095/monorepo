#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
product_dir="$(cd "$script_dir/.." && pwd)"

VERSION="$(tr -d '[:space:]' < "$product_dir/VERSION")"
ARTIFACTS_DIR="$product_dir/artifacts"
DMG_PATH="$ARTIFACTS_DIR/Submit-$VERSION-macOS.dmg"
MANIFEST_PATH="$ARTIFACTS_DIR/Submit-$VERSION-release-manifest.json"

echo "=========================================================="
echo "NITE Submit — Automated Release Publisher (v$VERSION)"
echo "=========================================================="

# This is the final publication gate, not a development packager.
"$script_dir/check_public_release_source.sh"
"$script_dir/run_release_checks.sh"
"$script_dir/check_distribution_readiness.sh" --require-ready
"$script_dir/verify_release_artifacts.sh"

echo "Release package passed every local public-distribution gate."
echo "  DMG: $DMG_PATH"
echo "  Manifest: $MANIFEST_PATH"
echo "  Update feed: https://www.nitedsp.co.uk/submit/appcast.xml"
echo "=========================================================="
